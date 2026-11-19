"""Authenticated readers. Only explicitly public program records cross the storage boundary."""

import base64
import time
from urllib.parse import quote, urlsplit
from .sources import _get, SourceError

BASE = {
    "hackerone": "https://api.hackerone.com/v1/hackers/programs",
    "bugcrowd": "https://hacker-api.bugcrowd.com/v1/health",
    "intigriti": "https://api.intigriti.com/external/researcher/v1/programs",
    "yeswehack": "https://api.yeswehack.com/programs",
}


def headers(kind, cred):
    key = cred.get("key")
    if not key:
        raise SourceError("Platform API key required")
    if kind in ("bugcrowd", "hackerone"):
        user = cred.get("username")
        if not user:
            raise SourceError("Platform API username required")
        auth = user + ":" + key
        return {
            "Authorization": "Basic " + base64.b64encode(auth.encode()).decode()
            if kind == "hackerone"
            else "Token " + auth
        }
    return (
        {"Authorization": "Bearer " + key}
        if kind == "intigriti"
        else {"X-AUTH-TOKEN": key}
    )


def test_credentials(source, cred):
    kind = source.split(":")[1]
    _get(
        BASE[kind]
        + {
            "hackerone": "?page[size]=1",
            "intigriti": "?limit=1",
            "yeswehack": "?resultsPerPage=1",
            "bugcrowd": "",
        }[kind],
        headers(kind, cred),
    )
    return {"ok": True, "provider": kind}


def enum(v):
    return (v or {}).get("value", "").lower()


def fetch(source, cred):
    kind = source.split(":")[1]
    if kind == "bugcrowd":
        raise SourceError(
            "Public visibility unavailable in this API. Use dataset:bugcrowd or import."
        )
    base = BASE[kind]
    auth = headers(kind, cred)
    records = []
    last = 0

    def read(url):
        nonlocal last
        if urlsplit(url).netloc != urlsplit(base).netloc or not url.startswith(base):
            raise SourceError("Invalid upstream pagination URL")
        time.sleep(max(0, 2 - (time.monotonic() - last)))
        last = time.monotonic()
        obj, _, _ = _get(url, auth)
        if not isinstance(obj, dict):
            raise SourceError("Invalid API page")
        return obj

    def pages_h1(url):
        visited = set()
        while url:
            if url in visited:
                raise SourceError("Pagination cycle")
            visited.add(url)
            data = read(url)
            yield from data["data"]
            url = (data.get("links") or {}).get("next")

    if kind == "hackerone":
        for item in pages_h1(base + "?page[size]=100"):
            a = item["attributes"]
            if a.get("state") != "public_mode":
                continue
            slug = a["handle"]
            detail = base + "/" + quote(slug, safe="")
            scopes = []
            for row in pages_h1(detail + "/structured_scopes?page[size]=100"):
                r = row["attributes"]
                eligible = r.get("eligible_for_submission")
                scopes.append(
                    {
                        "raw": r["asset_identifier"],
                        "kind": r["asset_type"].lower(),
                        "effect": {True: "include", False: "exclude"}.get(
                            eligible, "unknown"
                        ),
                        "instruction": r.get("instruction"),
                        "eligible_for_bounty": r.get("eligible_for_bounty"),
                    }
                )
            if len(scopes) >= 10000:
                raise SourceError("Large scope requires cursor pagination; use import")
            records.append(
                dict(
                    external_id=slug,
                    platform="HackerOne",
                    name=a["name"],
                    url="https://hackerone.com/" + quote(slug, safe=""),
                    policy=a.get("policy"),
                    safe_harbor=a.get("gold_standard_safe_harbor"),
                    published_at=a.get("started_accepting_at"),
                    reward_exclusions=[
                        r.get("attributes", {})
                        for r in pages_h1(detail + "/scope_exclusions")
                    ],
                    scope=scopes,
                    status={"open": "active", "paused": "paused"}.get(
                        a.get("submission_state"), "unknown"
                    ),
                    kind={True: "bug_bounty", False: "vdp"}.get(
                        a.get("offers_bounties"), "unknown"
                    ),
                    source_url=detail,
                )
            )
    else:
        page = 1
        offset = 0
        while True:
            url = base + (
                f"?page={page}&resultsPerPage=100"
                if kind == "yeswehack"
                else f"?offset={offset}&limit=100"
            )
            data = read(url)
            rows = data["items" if kind == "yeswehack" else "records"]
            for a in rows:
                if kind == "yeswehack":
                    if a.get("public") is not True:
                        continue
                    slug = a["slug"]
                    link = base + "/" + quote(slug, safe="")
                    d = read(link)
                    if d.get("public") is not True:
                        continue
                    records.append(
                        dict(
                            external_id=slug,
                            name=d["title"],
                            platform="YesWeHack",
                            url="https://yeswehack.com/programs/"
                            + quote(slug, safe=""),
                            scope=[
                                dict(
                                    raw=r["scope"],
                                    kind=r["scope_type"],
                                    effect="include",
                                )
                                for r in d["scopes"]
                            ]
                            if "scopes" in d
                            else None,
                            out_of_scope=d.get("out_of_scope"),
                            policy=d.get("rules"),
                            kind={"bug-bounty": "bug_bounty", "vdp": "vdp"}.get(
                                d.get("type"), "unknown"
                            ),
                            status="removed"
                            if d.get("archived")
                            else {True: "paused", False: "active"}.get(
                                d.get("disabled"), "unknown"
                            ),
                            reward={
                                k: d[k]
                                for k in (
                                    "bounty_reward_min",
                                    "bounty_reward_max",
                                    "currency",
                                )
                                if k in d
                            },
                            source_url=link,
                        )
                    )
                else:
                    if enum(a.get("confidentialityLevel")) != "public":
                        continue
                    link = base + "/" + quote(a["id"], safe="")
                    d = read(link)
                    if enum(d.get("confidentialityLevel")) != "public":
                        continue
                    rules = (d.get("rulesOfEngagement") or {}).get("content") or {}
                    assets = []
                    for r in d["domains"]["content"]:
                        tier = enum(r.get("tier"))
                        effect = (
                            "exclude"
                            if tier.replace(" ", "") == "outofscope"
                            else (
                                "include"
                                if tier
                                in {
                                    "tier 1",
                                    "tier 2",
                                    "tier 3",
                                    "tier 4",
                                    "tier 5",
                                    "critical",
                                    "high",
                                    "medium",
                                    "low",
                                }
                                else "unknown"
                            )
                        )
                        assets.append(
                            dict(
                                raw=r["endpoint"],
                                kind=enum(r["type"]),
                                effect=effect,
                                instruction=r.get("description"),
                                tier=tier,
                            )
                        )
                    records.append(
                        dict(
                            external_id=d["id"],
                            platform="Intigriti",
                            name=d["name"],
                            url=d["webLinks"]["detail"],
                            scope=assets,
                            policy=rules.get("description"),
                            safe_harbor=rules.get("safeHarbour"),
                            testing_restrictions=rules.get("testingRequirements"),
                            kind={"bug bounty": "bug_bounty", "vdp": "vdp"}.get(
                                enum(d.get("type")), "unknown"
                            ),
                            status={"open": "active", "paused": "paused"}.get(
                                enum(d.get("status")), "unknown"
                            ),
                            reward={
                                "minimum": a.get("minBounty"),
                                "maximum": a.get("maxBounty"),
                            },
                            source_url=link,
                        )
                    )
            page += 1
            offset += len(rows)
            if (kind == "yeswehack" and page > int(data["pagination"]["nb_pages"])) or (
                kind == "intigriti" and offset >= int(data["maxCount"])
            ):
                break
            if not rows:
                raise SourceError("Incomplete pagination")
    if not records:
        raise SourceError("No verified public entries returned")
    for r in records:
        r["provenance"] = {
            "authority": "official",
            "url": r["source_url"],
            "source": source,
        }
    return records
