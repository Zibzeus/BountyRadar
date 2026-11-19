from datetime import datetime, timezone, timedelta

WEIGHTS = dict(
    interests=30,
    complexity=15,
    repositories=15,
    bounty=15,
    changes=10,
    technology=10,
    opportunities=5,
)
DEFAULT = {
    "interests": [],
    "technologies": [],
    "complexity": "small",
    "weights": WEIGHTS,
}


def score(record, profile, changed):
    rules = record.get("scope")
    kinds = {v["kind"].casefold() for v in rules or [] if v.get("effect") == "include"}
    technologies = {str(v).casefold() for v in record.get("technologies") or []}

    def match(options, present):
        terms = {s.casefold() for s in options}
        return len(terms & present) / len(terms) if terms and present else None

    complexity = None if rules is None else min(1, len(rules) / 50)
    if complexity is not None and profile["complexity"] == "small":
        complexity = 1 - complexity
    recent = bool(
        changed
        and datetime.fromisoformat(changed)
        > datetime.now(timezone.utc) - timedelta(days=30)
    )
    factors = {
        "interests": match(profile["interests"], kinds | technologies),
        "complexity": complexity,
        "repositories": 1
        if kinds & {"repository", "source_code", "repo"}
        else (
            bool(record["repositories"])
            if record.get("repositories") is not None
            else None
        ),
        "bounty": {"bug_bounty": 1, "vdp": 0}.get(record["kind"]),
        "changes": int(recent),
        "technology": match(profile["technologies"], technologies),
        "opportunities": bool(record["opportunities"])
        if record.get("opportunities") is not None
        else None,
    }
    w = profile["weights"]
    total = sum(w.values())
    parts = {
        k: None if v is None else round(w[k] * v * 100 / total, 2)
        for k, v in factors.items()
    }
    return {
        "score": round(sum(v for v in parts.values() if v is not None), 1),
        "contributions": parts,
        "coverage": round(
            100 * sum(w[k] for k, v in factors.items() if v is not None) / total
        ),
    }
