import os
import uuid
from sqlalchemy import (
    MetaData,
    Table,
    Column,
    String,
    Text,
    JSON,
    Integer,
    UniqueConstraint,
    create_engine,
    select,
    insert,
    update,
    event,
)
from .core import now, normalize, changes, digest


def uid():
    return uuid.uuid4().hex


def field(name, typ=Text, **kwargs):
    return Column(name, typ, **kwargs)


def pk():
    return field("id", String(64), primary_key=True)


meta = MetaData()
users = Table(
    "users",
    meta,
    pk(),
    field("username", String(120), unique=True, nullable=False),
    field("password"),
    field("role"),
)
sessions = Table(
    "sessions",
    meta,
    pk(),
    field("user_id", String(64)),
    field("csrf"),
    field("expires"),
)
programs = Table(
    "programs",
    meta,
    pk(),
    field("platform", String(100)),
    field("external_id", String(500)),
    field("snapshot_id"),
    field("rank", Integer),
    UniqueConstraint("platform", "external_id"),
)
snaps = Table(
    "snapshots",
    meta,
    pk(),
    field("program_id", String(64), index=True),
    field("source", String(120)),
    field("time"),
    field("hash"),
    field("verification"),
    field("data", JSON),
    field("diff", JSON),
)
checks = Table(
    "observations",
    meta,
    pk(),
    field("program_id", String(64), index=True),
    field("source", String(120)),
    field("last_seen"),
    field("missing_since"),
    UniqueConstraint("program_id", "source"),
)
jobs = Table(
    "jobs",
    meta,
    pk(),
    field("kind"),
    field("source"),
    field("owner"),
    field("state"),
    field("started"),
    field("finished"),
    field("active", String(256), unique=True),
    field("details", JSON),
)
prefs = Table("preferences", meta, pk(), field("profile", JSON))
marks = Table(
    "bookmarks",
    meta,
    field("user_id", String(64), primary_key=True),
    field("program_id", String(64), primary_key=True),
)
settings = Table("settings", meta, pk(), field("data", JSON))
conns = Table(
    "connections",
    meta,
    pk(),
    field("owner"),
    field("team", Integer),
    field("kind"),
    field("endpoint"),
    field("model"),
    field("name"),
    field("cipher"),
)
url = os.getenv("DATABASE_URL", "sqlite:///./bountyradar.db")
engine = create_engine(
    url,
    **(
        {"connect_args": {"check_same_thread": False, "timeout": 30}}
        if url.startswith("sqlite")
        else {"pool_pre_ping": True}
    ),
)
if url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def sqlite_config(dbapi_connection, _):
        dbapi_connection.execute("PRAGMA journal_mode=WAL")
        dbapi_connection.execute("PRAGMA foreign_keys=ON")


def get(c, table, key):
    return c.execute(select(table).where(table.c.id == key)).mappings().first()


def save(c, table, key, **values):
    if get(c, table, key):
        c.execute(update(table).where(table.c.id == key).values(**values))
    else:
        c.execute(insert(table).values(id=key, **values))


def ingest(c, source, records, complete=False):
    stamp = now()
    verified = source.startswith("api:")
    rank = 3 if verified else (2 if source.startswith("manual") else 1)
    label = "official" if verified else ("manual" if rank == 2 else "secondary")
    seen = set()
    for record in records:
        data = normalize(record)
        identity = (data["platform"].casefold(), data["external_id"])
        if identity in seen:
            raise ValueError("Duplicate program identifier within source")
        seen.add(identity)
        p = (
            c.execute(
                select(programs).where(
                    programs.c.platform == identity[0],
                    programs.c.external_id == identity[1],
                )
            )
            .mappings()
            .first()
        )
        pid = p["id"] if p else uid()
        obs = (
            c.execute(
                select(checks).where(
                    checks.c.program_id == pid, checks.c.source == source
                )
            )
            .mappings()
            .first()
        )
        save(
            c,
            checks,
            obs["id"] if obs else uid(),
            program_id=pid,
            source=source,
            last_seen=stamp,
            missing_since=None,
        )
        old = (
            c.execute(
                select(snaps)
                .where(snaps.c.program_id == pid, snaps.c.source == source)
                .order_by(snaps.c.time.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        diff = changes(old["data"] if old else None, data)
        if old and data.get("parser_version") != old["data"].get("parser_version"):
            diff = [
                {
                    "field": "parser_version",
                    "before": old["data"].get("parser_version"),
                    "after": data.get("parser_version"),
                }
            ]
        if obs and obs["missing_since"]:
            diff.append(
                {"field": "listing_presence", "before": "missing", "after": "listed"}
            )
        if (
            old
            and not diff
            and data.get("parser_version") == old["data"].get("parser_version")
        ):
            continue
        sid = uid()
        c.execute(
            insert(snaps).values(
                id=sid,
                program_id=pid,
                source=source,
                time=stamp,
                hash=digest(data),
                verification=label,
                data=data,
                diff=diff,
            )
        )
        if not p or rank >= p["rank"]:
            save(
                c,
                programs,
                pid,
                platform=identity[0],
                external_id=identity[1],
                snapshot_id=sid,
                rank=rank,
            )
    if complete and seen:
        for obs in c.execute(
            select(checks, programs.c.platform, programs.c.external_id)
            .join(programs, programs.c.id == checks.c.program_id)
            .where(checks.c.source == source, checks.c.missing_since.is_(None))
        ).mappings():
            if (obs["platform"], obs["external_id"]) not in seen:
                previous = (
                    c.execute(
                        select(snaps)
                        .where(
                            snaps.c.program_id == obs["program_id"],
                            snaps.c.source == source,
                        )
                        .order_by(snaps.c.time.desc())
                        .limit(1)
                    )
                    .mappings()
                    .one()
                )
                # Keep the last policy snapshot selected until another policy is observed.
                c.execute(
                    insert(snaps).values(
                        id=uid(),
                        program_id=obs["program_id"],
                        source=source,
                        time=stamp,
                        verification="listing observation",
                        data=previous["data"],
                        hash=previous["hash"],
                        diff=[
                            {
                                "field": "listing_presence",
                                "before": "listed",
                                "after": "missing",
                            }
                        ],
                    )
                )
                c.execute(
                    update(checks)
                    .where(checks.c.id == obs["id"])
                    .values(missing_since=stamp)
                )
    return len(seen)


def view(c, p):
    s = get(c, snaps, p["snapshot_id"])
    obs = (
        c.execute(
            select(checks).where(
                checks.c.program_id == p["id"], checks.c.source == s["source"]
            )
        )
        .mappings()
        .one()
    )
    return {
        **s["data"],
        "id": p["id"],
        "snapshot_id": s["id"],
        "acquired_at": s["time"],
        "source": s["source"],
        "verification": s["verification"],
        "updated_at": s["time"],
        "last_seen_at": obs["last_seen"],
        "possibly_removed": bool(obs["missing_since"]),
        "last_verified_at": obs["last_seen"]
        if s["verification"] == "official"
        else None,
    }


def history(c, pid):
    return [
        dict(s)
        for s in c.execute(
            select(
                snaps.c.id,
                snaps.c.source,
                snaps.c.time,
                snaps.c.verification,
                snaps.c.diff,
            )
            .where(snaps.c.program_id == pid)
            .order_by(snaps.c.time.desc())
        ).mappings()
    ]
