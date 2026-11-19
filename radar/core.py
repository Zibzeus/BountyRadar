"""Snapshot normalization and portable workspace serialization."""

import hashlib
import ipaddress
import io
import json
import re
import zipfile
from urllib.parse import urlsplit
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def normalize_rule(rule):
    if (
        not isinstance(rule, dict)
        or not isinstance(rule.get("raw"), str)
        or not rule["raw"].strip()
    ):
        raise ValueError("A scope rule must contain original asset text")
    raw = rule["raw"]
    value = raw.strip()
    kind = str(rule.get("kind") or "unknown").lower()
    aliases = {
        "source_code": "repository",
        "source-code": "repository",
        "github": "repository",
        "code": "repository",
        "google_play_app_id": "mobile_android",
        "apple_store_app_id": "mobile_ios",
        "android": "mobile_android",
        "ios": "mobile_ios",
        "smart-contract": "smart_contract",
        "web_api": "api",
        "ip range": "cidr",
    }
    kind = aliases.get(kind, kind)
    ambiguity = rule.get("ambiguity")
    if kind in {
        "other",
        "unknown",
        "url",
        "wildcard",
        "domain",
        "ip",
        "ip_address",
        "cidr",
        "website",
        "web",
        "web-application",
    }:
        try:
            address = (
                ipaddress.ip_network(value, strict=True)
                if "/" in value
                else ipaddress.ip_address(value)
            )
            kind, value = ("cidr" if "/" in value else "ip"), str(address)
        except ValueError:
            if re.fullmatch(r"(?:\*\.)?(?:[A-Za-z0-9-]+\.)+[A-Za-z0-9-]+\.?", value):
                kind = "wildcard" if value.startswith("*.") else "domain"
                value = value.lower().rstrip(".")
            elif value.startswith(("https://", "http://")):
                kind = "url"
            else:
                kind, ambiguity = (
                    "product",
                    ambiguity or "Interpret the original policy text.",
                )
    effect = rule.get("effect", "unknown")
    return {
        **rule,
        "raw": raw,
        "value": value,
        "kind": kind,
        "effect": effect if effect in {"include", "exclude"} else "unknown",
        "ambiguity": ambiguity,
    }


def normalize(row):
    row = dict(row)
    for key in ("external_id", "platform", "name", "url"):
        if not isinstance(row.get(key), str) or not row[key].strip():
            raise ValueError("Missing program " + key)
    url = urlsplit(row["url"])
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
    ):
        raise ValueError("Invalid program URL")
    rules = row.get("scope")
    if rules is not None:
        row["scope"] = sorted((normalize_rule(rule) for rule in rules), key=canonical)
    for key in (
        "policy",
        "reward",
        "testing_restrictions",
        "disclosure_requirements",
        "safe_harbor",
        "repositories",
        "scope",
        "technologies",
    ):
        row.setdefault(key, None)
    if row.get("repositories") is None:
        repos = sorted(
            {
                r["value"]
                for r in row.get("scope") or []
                if r["kind"] == "repository"
                and r["effect"] == "include"
                and r["value"].startswith("https://")
            }
        )
        row["repositories"] = repos or None
    row.setdefault("parser_version", "1")
    for key in ("kind", "status"):
        row[key] = row.get(key) or "unknown"
    return row


def changes(before, after):
    if before is None:
        events = [{"field": "discovery", "before": None, "after": after["name"]}]
        if after.get("published_at"):
            events.append(
                {
                    "field": "published_at",
                    "before": None,
                    "after": after["published_at"],
                }
            )
        return events
    result = []
    for field in sorted(set(after) | set(before)):
        a, b = before.get(field), after.get(field)
        if (
            field == "policy"
            and isinstance(a, str)
            and isinstance(b, str)
            and a.split() == b.split()
        ):
            continue
        if a == b or field in {
            "provenance",
            "source",
            "acquired_at",
            "last_verified",
            "updated_at",
            "parser_version",
            "last_verified_at",
            "fetched_at",
        }:
            continue
        if field == "scope" and isinstance(a, list) and isinstance(b, list):
            old, new = {canonical(x) for x in a}, {canonical(x) for x in b}
            result.extend(
                {"field": "scope", "before": json.loads(v), "after": None}
                for v in sorted(old - new)
            )
            result.extend(
                {"field": "scope", "before": None, "after": json.loads(v)}
                for v in sorted(new - old)
            )
        else:
            result.append({"field": field, "before": a, "after": b})
    return result


def export_files(data, history):
    common = {
        k: data.get(k)
        for k in (
            "id",
            "name",
            "url",
            "source",
            "provenance",
            "snapshot_id",
            "acquired_at",
            "last_verified_at",
            "verification",
        )
    }
    common["schema_version"] = "1.0"
    ambiguities = list(data.get("ambiguities") or []) + [
        r["ambiguity"] for r in data.get("scope") or [] if r.get("ambiguity")
    ]
    common["ambiguities"] = ambiguities

    def pretty(obj):
        return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    heading = (
        f"# {data['name']}\n\nOfficial program: {data['url']}\n\n"
        f"Source: {canonical(data.get('provenance'))}\n\nAcquired: {data['acquired_at']}\n\n"
        f"Snapshot: {data['snapshot_id']} · {data['verification']}\n\n"
        f"Unresolved ambiguities: {canonical(ambiguities)}\n\n"
    )
    rules = data.get("scope")
    lines = [f"- {r['effect']} · {r['kind']} · {r['raw']}" for r in rules or []]
    policy = [str(data.get("policy") or "Unknown")]
    for k in (
        "testing_restrictions",
        "disclosure_requirements",
        "safe_harbor",
        "out_of_scope",
        "reward_exclusions",
    ):
        policy.append(
            f"## {k.replace('_', ' ').title()}\n\n{data.get(k) if data.get(k) is not None else 'Unknown'}"
        )
    return {
        "PROGRAM_METADATA.json": pretty({**data, **common}),
        "SCOPE_RULES.json": pretty({**common, "rules": rules}),
        "PROGRAM_SCOPE.md": heading
        + "## Published scope\n\n"
        + ("\n".join(lines) or ("Unknown" if rules is None else "No rules listed."))
        + "\n",
        "PROGRAM_POLICY.md": heading + "\n\n".join(policy) + "\n",
        "SCOPE_CHANGELOG.md": heading
        + "\n".join(
            f"- {h['time']} · {h['verification']} · {d['field']}: {canonical(d['before'])} → {canonical(d['after'])}"
            for h in history
            for d in h["diff"]
        )
        + "\n",
    }


def zip_files(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    return stream.getvalue()


def scope_match(rules, value, chain=None):
    """Match published identifiers conservatively. Preserve conditions and exclusions."""
    matches = []
    for rule in rules or []:
        asset = rule["value"]
        if rule.get("chain") and rule["chain"] != chain:
            continue
        if rule["kind"] == "smart_contract" and not chain:
            continue
        if rule["kind"] == "wildcard":
            suffix = asset[1:].lower()
            host = value.removesuffix(".").lower()
            hit = host.endswith(suffix) and all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in host.split(".")
            )
        elif rule["kind"] == "cidr":
            try:
                hit = ipaddress.ip_address(value) in ipaddress.ip_network(asset)
            except ValueError:
                hit = False
        elif rule["kind"] == "domain":
            hit = value.lower().rstrip(".") == asset
        else:
            hit = value == asset
        if hit:
            matches.append(rule)
    effect = next(
        (
            e
            for e in ("exclude", "unknown", "include")
            if any(r["effect"] == e for r in matches)
        ),
        "unknown",
    )
    return {"effect": effect, "matches": matches, "advisory": True}
