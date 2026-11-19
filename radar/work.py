"""Persist jobs before dispatch and commit refresh data and validators together."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import logging
import os
from pathlib import Path
from celery import Celery
from sqlalchemy.exc import IntegrityError
from sqlalchemy import insert, select, update
from .db import (
    checks,
    conns,
    engine,
    get,
    ingest,
    jobs,
    now,
    programs,
    save,
    settings,
    uid,
    users,
    view,
)
from .sources import fetch_source, NotModified, SourceError

log = logging.getLogger("bountyradar.jobs")
pool = ThreadPoolExecutor(max_workers=2)
celery = Celery("radar", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))
celery.conf.update(
    task_ignore_result=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    beat_schedule={"refresh-due": {"task": "radar.tick", "schedule": 60.0}},
)


def master():
    path = os.getenv("RADAR_MASTER_KEY_FILE")
    value = Path(path).read_text().strip() if path else os.getenv("RADAR_MASTER_KEY")
    if not value:
        raise ValueError("Configure RADAR_MASTER_KEY")
    return value


def usable(c, cid, owner):
    row = get(c, conns, cid) if cid else None
    if not row or (row["owner"] != owner and not row["team"]):
        raise ValueError("Connection unavailable")
    from .research import decrypt_secret

    return {
        **row,
        "key": decrypt_secret(row["cipher"], master(), row["id"])
        if row["cipher"]
        else "",
    }


def job(kind, source, owner, details):
    jid = uid()
    active = kind + ":" + source + (":" + owner if kind == "research" else "")
    try:
        with engine.begin() as c:
            if kind == "research":
                c.execute(
                    select(users.c.id).where(users.c.id == owner).with_for_update()
                )
                config = get(c, settings, "schedule")
                limit = (config["data"] if config else {}).get(
                    "daily_research_limit", 20
                )
                midnight = (
                    datetime.now(timezone.utc)
                    .replace(hour=0, minute=0, second=0, microsecond=0)
                    .isoformat()
                )
                from sqlalchemy import func

                used = c.scalar(
                    select(func.count())
                    .select_from(jobs)
                    .where(
                        jobs.c.kind == "research",
                        jobs.c.owner == owner,
                        jobs.c.started >= midnight,
                    )
                )
                if used >= limit:
                    raise ValueError("Daily research limit reached")
            c.execute(
                insert(jobs).values(
                    id=jid,
                    kind=kind,
                    source=source,
                    owner=owner,
                    state="queued",
                    started=now(),
                    active=active,
                    details=details,
                )
            )
    except IntegrityError:
        raise ValueError("A job for this source is already active")
    try:
        if os.getenv("REDIS_URL"):
            run.delay(jid)
        else:
            pool.submit(run, jid)
    except Exception:
        end(jid, "failed", {"error": "Job queue unavailable"})
    with engine.connect() as c:
        return dict(get(c, jobs, jid))


def end(jid, state, details):
    with engine.begin() as c:
        c.execute(
            update(jobs)
            .where(jobs.c.id == jid, jobs.c.state.in_(["running", "queued"]))
            .values(state=state, active=None, finished=now(), details=details)
        )
    log.info("job=%s state=%s", jid, state)


def cancelled(jid):
    with engine.connect() as c:
        return get(c, jobs, jid)["state"] != "running"


@celery.task(name="radar.run")
def run(jid):
    with engine.begin() as c:
        if not c.execute(
            update(jobs)
            .where(jobs.c.id == jid, jobs.c.state == "queued")
            .values(state="running")
        ).rowcount:
            return
        j = get(c, jobs, jid)
    details = j["details"]
    source = j["source"]
    owner = j["owner"]
    try:
        if j["kind"] == "refresh":
            with engine.connect() as c:
                cred = (
                    usable(c, details["connection_id"], owner)
                    if details.get("connection_id")
                    else {}
                )
                cache_id = "cache:" + source
                cached = get(c, settings, cache_id)
                cache = dict(cached["data"] if cached else {})
            records = fetch_source(
                source, {"key": cred.get("key"), "username": cred.get("model")}, cache
            )
            with engine.begin() as c:
                if get(c, jobs, jid)["state"] != "running":
                    return
                count = ingest(c, source, records, complete=True)
                save(c, settings, cache_id, data=cache)
                c.execute(
                    update(jobs)
                    .where(jobs.c.id == jid)
                    .values(
                        state="complete",
                        active=None,
                        finished=now(),
                        details={"count": count},
                    )
                )
            log.info("refresh job=%s source=%s count=%d", jid, source, count)
        else:
            from .research import research_program

            with engine.connect() as c:
                prog = view(c, get(c, programs, source))
                llm = usable(c, details["llm_id"], owner)
                browser = (
                    usable(c, details["browser_id"], owner)
                    if details.get("browser_id")
                    else None
                )
            result = research_program(
                prog,
                llm,
                browser,
                approved_urls=tuple(
                    os.getenv("BOUNTYRADAR_APPROVED_POLICY_URLS", "").splitlines()
                ),
                cancelled=lambda: cancelled(jid),
            )
            end(
                jid,
                "needs_review",
                {"result": result, "snapshot_id": prog["snapshot_id"]},
            )
    except NotModified:
        with engine.begin() as c:
            c.execute(
                update(checks)
                .where(checks.c.source == source, checks.c.missing_since.is_(None))
                .values(last_seen=now())
            )
        end(jid, "unchanged", {})
    except Exception as e:
        # No provider bodies, prompts, credentials or URLs in logs.
        end(
            jid,
            "failed",
            {"error": str(e)[:160] if isinstance(e, SourceError) else type(e).__name__},
        )


@celery.task(name="radar.tick")
def tick():
    stamp = datetime.now(timezone.utc)
    with engine.begin() as c:
        # Recover leases after an interrupted worker or lost broker message.
        c.execute(
            update(jobs)
            .where(
                jobs.c.active.is_not(None),
                jobs.c.started < (stamp - timedelta(hours=6)).isoformat(),
            )
            .values(
                active=None,
                state="failed",
                finished=now(),
                details={"error": "Worker lease expired"},
            )
        )
        s = get(c, settings, "schedule")
        config = (
            s["data"] if s else {"sources": ["dataset:yeswehack"], "interval_hours": 24}
        )
        tasks = [
            ("refresh", src, "scheduler", {}, config["interval_hours"])
            for src in config["sources"]
        ]
        for entry in c.execute(
            select(settings.c.data).where(settings.c.id.like("daily:%"))
        ).scalars():
            tasks.append(("research", entry["program_id"], entry["owner"], entry, 24))
    for kind, src, owner, details, hours in tasks:
        with engine.connect() as c:
            previous = c.execute(
                select(jobs.c.started)
                .where(jobs.c.kind == kind, jobs.c.source == src, jobs.c.owner == owner)
                .order_by(jobs.c.started.desc())
                .limit(1)
            ).scalar()
        if (
            not previous
            or datetime.fromisoformat(previous) + timedelta(hours=hours) <= stamp
        ):
            try:
                job(kind, src, owner, details)
            except ValueError:
                pass
