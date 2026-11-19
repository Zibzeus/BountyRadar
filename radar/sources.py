"""Read-only, fixed-origin source connectors. Parse a whole response before yielding writes."""

import hashlib
import json
import time
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


PLATFORMS = {
    "hackerone": "HackerOne",
    "bugcrowd": "Bugcrowd",
    "intigriti": "Intigriti",
    "yeswehack": "YesWeHack",
    "diodb": "Independent",
}
FEEDS = {
    f"dataset:{key}": f"https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/{key}_data.json"
    for key in PLATFORMS
    if key != "diodb"
}
FEEDS["dataset:diodb"] = (
    "https://raw.githubusercontent.com/disclose/diodb/master/program-list.json"
)
MAX_BYTES = 64 * 1024 * 1024
MIT_URL = "https://github.com/arkadiyt/bounty-targets-data/blob/main/LICENSE.md"
DIO_URL = "https://github.com/disclose/diodb/blob/master/LICENSE"


class SourceError(ValueError):
    """Short diagnostic safe for logs and source health."""


class NotModified(SourceError):
    """The stored validator still applies."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _delay(header, attempt):
    if header:
        try:
            return max(0, int(header))
        except ValueError:
            try:
                return max(0, parsedate_to_datetime(header).timestamp() - time.time())
            except (ValueError, TypeError, OverflowError):
                pass
    return 2 ** (attempt + 1)


def _get(url, headers=None):
    opener = build_opener(_NoRedirect())
    request = Request(
        url,
        headers={
            "User-Agent": "BountyRadar/1.0 (public program metadata)",
            "Accept": "application/json",
            **(headers or {}),
        },
    )
    for attempt in range(3):
        try:
            with opener.open(request, timeout=30) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise SourceError("Response exceeds 64 MiB limit")
                try:
                    return (
                        json.loads(raw),
                        dict(response.headers.items()),
                        hashlib.sha256(raw).hexdigest(),
                    )
                except (UnicodeError, ValueError) as exc:
                    raise SourceError("Source returned malformed JSON") from exc
        except HTTPError as exc:
            if exc.code == 304:
                raise NotModified("Not modified") from None
            delay = _delay(exc.headers.get("Retry-After"), attempt)
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2 or delay > 60:
                raise SourceError(f"Upstream HTTP {exc.code}") from None
            time.sleep(delay)
        except (URLError, TimeoutError, OSError):
            if attempt == 2:
                raise SourceError("Upstream connection failed or timed out") from None
            time.sleep(_delay(None, attempt))


def _public_link(value):
    if not isinstance(value, str):
        return None
    try:
        parts = urlsplit(value.strip())
        if (
            parts.scheme in {"http", "https"}
            and parts.hostname
            and not parts.username
            and not parts.password
        ):
            return value.strip()
    except ValueError:
        pass
    return None


def _scope(targets):
    if not isinstance(targets, dict) or not isinstance(targets.get("in_scope"), list):
        raise SourceError("Invalid or missing in-scope collection")
    result = []
    for key, effect in (("in_scope", "include"), ("out_of_scope", "exclude")):
        group = targets.get(key, [])
        if not isinstance(group, list):
            raise SourceError("Invalid scope collection")
        for row in group:
            if not isinstance(row, dict):
                raise SourceError("Invalid asset record")
            raw = (
                row.get("asset_identifier") or row.get("endpoint") or row.get("target")
            )
            if not isinstance(raw, str) or not raw.strip():
                raise SourceError("Asset identifier missing")
            result.append(
                {
                    "raw": raw,
                    "kind": str(
                        row.get("asset_type") or row.get("type") or "unknown"
                    ).lower(),
                    "effect": effect,
                    "instruction": row.get("instruction") or row.get("description"),
                    "eligible_for_bounty": row.get("eligible_for_bounty"),
                    "eligible_for_submission": row.get("eligible_for_submission"),
                    "severity": row.get("max_severity") or row.get("impact"),
                }
            )
    return result


def _program(key, row):
    if key == "yeswehack" and row.get("public") is not True:
        return None
    if key == "intigriti" and str(row.get("confidentiality_level")).lower() != "public":
        return None
    name = row.get("name") or row.get("program_name")
    if not isinstance(name, str) or not name.strip():
        raise SourceError("Missing program name")
    link = _public_link(row.get("url") or row.get("policy_url"))
    link_ambiguous = False
    if key == "diodb" and not link and str(row.get("policy_url")).startswith("www."):
        link = _public_link("https://" + row["policy_url"])
        link_ambiguous = True
    if key == "yeswehack" and row.get("id"):
        link = "https://yeswehack.com/programs/" + quote(str(row["id"]), safe="")
    if key == "diodb":
        external = name.strip()
    elif key == "hackerone":
        external = row.get("handle")
    elif key == "bugcrowd":
        external = link.rstrip("/").split("/")[-1] if link else None
    else:
        external = row.get("id")
    if not external:
        raise SourceError("Missing program identifier")
    status = str(row.get("submission_state") or row.get("status") or "").lower()
    status = {"open": "active", "active": "active", "paused": "paused"}.get(
        status, "unknown"
    )
    if row.get("disabled") is True:
        status = "paused"
    elif row.get("disabled") is False:
        status = "active"
    reward = {
        k: v
        for k, v in {
            "minimum": row.get("min_bounty"),
            "maximum": row.get("max_bounty", row.get("max_payout")),
            "currency": row.get("currency"),
        }.items()
        if v is not None
    }
    maximum = reward.get("maximum")
    value = maximum.get("value") if isinstance(maximum, dict) else maximum
    pays = row.get("offers_bounties", row.get("offers_bounty"))
    kind = "unknown"
    if pays is True or pays == "yes" or (isinstance(value, (float, int)) and value > 0):
        kind = "bug_bounty"
    elif pays is False or pays == "no":
        kind = "vdp"
    scopes = _scope(row.get("targets")) if key != "diodb" else None
    return {
        "external_id": str(external),
        "platform": PLATFORMS[key],
        "name": name.strip(),
        "url": link,
        "status": status,
        "kind": kind,
        "policy": row.get("policy"),
        "scope": scopes,
        "scope_complete": False,
        "reward": reward or None,
        "safe_harbor": row.get("safe_harbor") if row.get("safe_harbor") != "" else None,
        "disclosure_requirements": row.get(
            "allows_disclosure", row.get("public_disclosure")
        ),
        "ambiguities": ["Directory omitted the policy URL scheme; HTTPS assumed."]
        if link_ambiguous
        else [],
        "published_at": row.get("launch_date") or None,
    }


def parse_dataset(source, payload, digest=None):
    if source not in FEEDS or not isinstance(payload, list) or not payload:
        raise SourceError("Invalid or empty program feed")
    key = source.split(":")[1]
    records = []
    seen = {}
    for row in payload:
        if not isinstance(row, dict):
            raise SourceError("Invalid program object")
        item = _program(key, row)
        if item is None:
            continue
        external = item["external_id"]
        signature = hashlib.sha256(
            json.dumps(item, sort_keys=True, ensure_ascii=False).encode()
        ).digest()
        if external in seen:
            if seen[external] != signature:
                raise SourceError("Conflicting program records in feed")
            continue
        seen[external] = signature
        item["source"] = source
        item["source_url"] = FEEDS[source]
        item["provenance"] = {
            "source": source,
            "url": FEEDS[source],
            "authority": "secondary",
            "revision_sha256": digest,
            "license": DIO_URL if key == "diodb" else MIT_URL,
            "attribution": "disclose.io (adapted directory data)"
            if key == "diodb"
            else "Copyright (c) 2017 Arkadiy Tetelman",
        }
        records.append(item)
    if not records:
        raise SourceError("No public records found")
    return records


def fetch_source(source, credentials=None, cache=None):
    """Update caller's dataset validators only after full parse; commit validators with rows."""
    if source.startswith("api:"):
        from .official import fetch

        return fetch(source, credentials or {})
    if source not in FEEDS:
        raise SourceError("Source requires a supported official API or manual import")
    headers = {}
    if cache and cache.get("etag"):
        headers["If-None-Match"] = cache["etag"]
    if cache and cache.get("modified"):
        headers["If-Modified-Since"] = cache["modified"]
    payload, response_headers, digest = _get(FEEDS[source], headers)
    records = parse_dataset(source, payload, digest)
    if cache is not None:
        lower = {k.lower(): v for k, v in response_headers.items()}
        cache.update(etag=lower.get("etag"), modified=lower.get("last-modified"))
    return records
