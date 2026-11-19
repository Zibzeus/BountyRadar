import hashlib
import hmac
import os
import secrets
from pathlib import Path
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import delete, insert, select, update
from .db import (
    conns,
    engine,
    get,
    history,
    ingest,
    jobs,
    marks,
    meta,
    now,
    prefs,
    programs,
    save,
    sessions,
    settings,
    snaps,
    uid,
    users,
    view,
)
from .core import export_files, zip_files

hasher = PasswordHasher()


def env_secret(key):
    path = os.getenv(key + "_FILE")
    return Path(path).read_text().strip() if path else os.getenv(key)


@asynccontextmanager
async def lifespan(app):
    meta.create_all(engine)
    with engine.begin() as c:
        if not c.execute(select(users.c.id).limit(1)).first():
            password = env_secret("RADAR_ADMIN_PASSWORD")
            if not password or len(password) < 12:
                raise RuntimeError(
                    "Set RADAR_ADMIN_PASSWORD (12+ characters) before first start."
                )
            c.execute(
                insert(users).values(
                    id=uid(),
                    username=os.getenv("RADAR_ADMIN_USER", "admin"),
                    password=hasher.hash(password),
                    role="admin",
                )
            )
    yield


app = FastAPI(title="BountyRadar", version="1.0", lifespan=lifespan)
api = "/api/v1"


def fail(code, msg):
    raise HTTPException(code, msg)


def auth(req: Request):
    with engine.begin() as c:
        token = req.cookies.get("radar_session", "")
        session = get(c, sessions, hashlib.sha256(token.encode()).hexdigest())
        if not session or session["expires"] < now():
            fail(401, "Sign in required")
        if req.method not in ("GET", "HEAD", "OPTIONS") and not hmac.compare_digest(
            req.headers.get("X-CSRF-Token", ""), session["csrf"]
        ):
            fail(403, "Invalid CSRF token")
        user = get(c, users, session["user_id"])
        if not user:
            fail(401, "Account unavailable")
        return {k: user[k] for k in ("id", "username", "role")}


def writer(user=Depends(auth)):
    if user["role"] == "viewer":
        fail(403, "Researcher access required")
    return user


def admin(user=Depends(auth)):
    if user["role"] != "admin":
        fail(403, "Administrator access required")
    return user


class Login(BaseModel):
    username: str = Field(max_length=120)
    password: str = Field(max_length=1024)


@app.post(api + "/login")
def login(body: Login, response: Response):
    with engine.begin() as c:
        user = (
            c.execute(select(users).where(users.c.username == body.username))
            .mappings()
            .first()
        )
        if not user:
            fail(401, "Invalid credentials")
        try:
            hasher.verify(user["password"], body.password)
        except VerifyMismatchError:
            fail(401, "Invalid credentials")
        token = secrets.token_urlsafe(36)
        csrf = secrets.token_urlsafe(30)
        c.execute(
            insert(sessions).values(
                id=hashlib.sha256(token.encode()).hexdigest(),
                user_id=user["id"],
                csrf=csrf,
                expires=(datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
            )
        )
        for name, value in (("radar_session", token), ("radar_csrf", csrf)):
            response.set_cookie(
                name,
                value,
                httponly=name == "radar_session",
                samesite="strict",
                secure=os.getenv("COOKIE_SECURE") == "1",
                max_age=43200,
            )
    return {"username": user["username"], "role": user["role"]}


@app.post(api + "/logout")
def logout(req: Request, response: Response, user=Depends(auth)):
    with engine.begin() as c:
        c.execute(
            delete(sessions).where(
                sessions.c.id
                == hashlib.sha256(req.cookies["radar_session"].encode()).hexdigest()
            )
        )
    for name in ("radar_session", "radar_csrf"):
        response.delete_cookie(name)
    return {"ok": True}


@app.get(api + "/me")
def me(user=Depends(auth)):
    return user


@app.get("/health")
def health():
    with engine.connect() as c:
        c.execute(select(1))
    return {"status": "ok"}


def program(c, pid):
    p = get(c, programs, pid)
    if not p:
        fail(404, "Unknown program")
    return view(c, p)


@app.get(api + "/programs/{pid}")
def detail(pid: str, user=Depends(auth)):
    with engine.connect() as c:
        d = program(c, pid)
        profile = get(c, prefs, user["id"])
        recent = next(
            (
                v["time"]
                for v in history(c, pid)
                if any(x["field"] == "scope" for x in v["diff"])
            ),
            None,
        )
        fit = score(d, profile["profile"] if profile else DEFAULT, recent)
        return {**d, **fit, "score_breakdown": fit["contributions"]}


@app.get(api + "/programs/{pid}/export")
def export(pid: str, file: str | None = None, user=Depends(auth)):
    with engine.connect() as c:
        d = program(c, pid)
        files = export_files(d, history(c, pid))
    if file and file not in files:
        fail(404, "Unknown export")
    name = file or f"bountyradar-{pid}.zip"
    return Response(
        files[file] if file else zip_files(files),
        media_type=("application/json" if file.endswith(".json") else "text/markdown")
        if file
        else "application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.get(api + "/programs")
def catalog(
    q: str = "",
    platform: str = "",
    status: str = "",
    kind: str = "",
    sort: str = "name",
    bookmarked: bool = False,
    page: int = 1,
    page_size: int = 50,
    user=Depends(auth),
):
    with engine.connect() as c:
        rows = list(
            c.execute(
                select(
                    programs,
                    snaps.c.data,
                    snaps.c.time,
                    snaps.c.verification,
                    snaps.c.source,
                ).join(snaps, snaps.c.id == programs.c.snapshot_id)
            ).mappings()
        )
        bookmarks = set(
            c.execute(
                select(marks.c.program_id).where(marks.c.user_id == user["id"])
            ).scalars()
        )
        profile = get(c, prefs, user["id"])
        has_scope_change = {
            r.program_id: True
            for r in c.execute(
                select(snaps.c.program_id, snaps.c.diff, snaps.c.time).where(
                    snaps.c.time
                    > (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
                )
            )
            if any(x["field"] == "scope" for x in r.diff)
        }
    items = []
    for r in rows:
        d = r["data"]
        if (
            q.casefold() not in (d["name"] + " " + d["url"]).casefold()
            or any(
                v and v.casefold() != str(d.get(k)).casefold()
                for k, v in (("platform", platform), ("status", status), ("kind", kind))
            )
            or bookmarked
            and r["id"] not in bookmarks
        ):
            continue
        item = {
            k: v for k, v in d.items() if k not in {"policy", "scope", "provenance"}
        }
        item.update(
            id=r["id"],
            scope_count=len(d["scope"]) if d.get("scope") is not None else None,
            updated_at=r["time"],
            source=r["source"],
            verification=r["verification"],
            bookmarked=r["id"] in bookmarks,
        )
        item.update(
            score(
                d,
                profile["profile"] if profile else DEFAULT,
                r["time"] if has_scope_change.get(r["id"]) else None,
            )
        )
        items.append(item)
    key = sort.lstrip("-")
    items.sort(
        key=lambda x: (
            (x.get(key) or 0)
            if key in {"score", "scope_count", "coverage"}
            else str(x.get(key) or "").casefold()
        ),
        reverse=sort.startswith("-"),
    )
    size = max(1, min(200, page_size))
    start = (max(1, page) - 1) * size
    return {
        "items": items[start : start + size],
        "total": len(items),
        "page": page,
        "page_size": size,
    }


from .sources import FEEDS


@app.post(api + "/sources/{slug}/refresh")
def refresh(slug: str, connection_id: str | None = None, user=Depends(writer)):
    if slug not in FEEDS and slug not in OFFICIAL:
        fail(400, "Manual import required")
    if slug == "api:bugcrowd":
        fail(
            422,
            "Use dataset:bugcrowd for public discovery. This account API cannot certify public visibility.",
        )
    if slug in OFFICIAL:
        with engine.connect() as c:
            connection = permitted(c, connection_id, user)
            if connection["kind"] != slug.split(":")[1]:
                fail(400, "Select matching platform credentials")
    return work.job("refresh", slug, user["id"], {"connection_id": connection_id})


@app.get(api + "/programs/{pid}/history")
def snapshots(pid: str, user=Depends(auth)):
    with engine.connect() as c:
        return {"items": history(c, pid)}


from typing import Literal
from fastapi.responses import JSONResponse
from . import work
from .score import score, DEFAULT, WEIGHTS
from .research import encrypt_secret, test_connection

OFFICIAL = {"api:" + k for k in ("hackerone", "bugcrowd", "intigriti", "yeswehack")}
MANUAL = {
    "hackenproof": "HackenProof",
    "immunefi": "Immunefi",
    "code4rena": "Code4rena",
    "sherlock": "Sherlock",
    "cantina": "Cantina",
    "independent": "Independent",
}


from fastapi.exceptions import RequestValidationError


@app.exception_handler(RequestValidationError)
async def invalid_body(req, exc):
    issues = [
        {"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()
    ]
    return JSONResponse({"detail": issues}, status_code=422)


@app.exception_handler(ValueError)
async def invalid(req, exc):
    return JSONResponse(
        {
            "detail": "Invalid input or unavailable connection. Check configuration and source data."
        },
        status_code=422,
    )


@app.middleware("http")
async def security(req, call_next):
    if (
        req.method not in ("GET", "HEAD", "OPTIONS")
        and req.headers.get("sec-fetch-site") == "cross-site"
    ):
        return JSONResponse({"detail": "Cross-site request denied"}, status_code=403)
    response = await call_next(req)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if req.url.path.startswith(api):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get(api + "/sources")
def source_list(user=Depends(auth)):
    with engine.connect() as c:
        out = []
        for slug in sorted(set(FEEDS) | OFFICIAL | {"manual:" + k for k in MANUAL}):
            last = (
                c.execute(
                    select(jobs)
                    .where(jobs.c.kind == "refresh", jobs.c.source == slug)
                    .order_by(jobs.c.started.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
            mode, key = slug.split(":")
            if slug == "api:bugcrowd":
                mode = "manual · use public Bugcrowd feed"
            out.append(
                {
                    "slug": slug,
                    "name": MANUAL.get(key, key),
                    "mode": mode,
                    "last_run": dict(last) if last else None,
                }
            )
        return {"items": out}


@app.get(api + "/changes")
def change_list(page: int = 1, user=Depends(auth)):
    with engine.connect() as c:
        rows = c.execute(
            select(snaps)
            .order_by(snaps.c.time.desc(), snaps.c.id)
            .offset(max(0, page - 1) * 100)
            .limit(100)
        ).mappings()
        return {
            "items": [
                {
                    **{
                        k: r[k]
                        for k in (
                            "id",
                            "time",
                            "source",
                            "verification",
                            "program_id",
                            "diff",
                        )
                    },
                    "name": r["data"]["name"],
                }
                for r in rows
            ]
        }


@app.put(api + "/programs/{pid}/bookmark")
def bookmark(pid: str, user=Depends(auth)):
    with engine.begin() as c:
        program(c, pid)
        if not c.execute(
            select(marks).where(
                marks.c.user_id == user["id"], marks.c.program_id == pid
            )
        ).first():
            c.execute(insert(marks).values(user_id=user["id"], program_id=pid))
    return {"bookmarked": True}


@app.delete(api + "/programs/{pid}/bookmark")
def unmark(pid: str, user=Depends(auth)):
    with engine.begin() as c:
        c.execute(
            delete(marks).where(
                marks.c.user_id == user["id"], marks.c.program_id == pid
            )
        )
    return {"bookmarked": False}


class Profile(BaseModel):
    weights: dict[str, int] = WEIGHTS
    technologies: list[str] = []
    interests: list[str] = []
    complexity: Literal["small", "large"] = "small"


@app.get(api + "/profile")
def get_profile(user=Depends(auth)):
    with engine.connect() as c:
        row = get(c, prefs, user["id"])
        return row["profile"] if row else DEFAULT


@app.put(api + "/profile")
def put_profile(b: Profile, user=Depends(auth)):
    if (
        set(b.weights) != set(WEIGHTS)
        or any(v < 0 or v > 100 for v in b.weights.values())
        or not sum(b.weights.values())
    ):
        fail(422, "Invalid weights")
    with engine.begin() as c:
        save(c, prefs, user["id"], profile=b.model_dump())
    return b


class Account(Login):
    role: Literal["admin", "researcher", "viewer"] = "researcher"


@app.post(api + "/users")
def add_user(b: Account, user=Depends(admin)):
    if not b.username.strip() or len(b.password) < 12:
        fail(422, "Username and password of 12+ characters required")
    with engine.begin() as c:
        if c.execute(select(users.c.id).where(users.c.username == b.username)).first():
            fail(409, "Username in use")
        c.execute(
            insert(users).values(
                id=uid(),
                username=b.username,
                password=hasher.hash(b.password),
                role=b.role,
            )
        )
    return {"username": b.username, "role": b.role}


@app.get(api + "/users")
def user_list(user=Depends(admin)):
    with engine.connect() as c:
        return {
            "items": [
                dict(x)
                for x in c.execute(
                    select(users.c.id, users.c.username, users.c.role)
                ).mappings()
            ]
        }


class ImportPayload(BaseModel):
    records: list[dict] = Field(min_length=1, max_length=500)


@app.post(api + "/imports/preview")
def preview(b: ImportPayload, user=Depends(writer)):
    from .core import normalize

    records = []
    for row in b.records:
        if row.get("visibility", "public") != "public" or row.get("public") is False:
            fail(422, "Only public programs supported")
        if any(
            k in row and row[k] is not None and not isinstance(row[k], list)
            for k in (
                "scope",
                "repositories",
                "ambiguities",
                "technologies",
                "opportunities",
            )
        ):
            fail(422, "Scope and list fields must be arrays or null")
        for k in ("technologies", "ambiguities", "repositories", "opportunities"):
            if not all(isinstance(v, str) for v in row.get(k) or []):
                fail(422, "Expected text entries in " + k)
        item = normalize(row)
        prov = item.get("provenance") or {}
        if not isinstance(prov, dict):
            fail(422, "Provenance must be an object")
        item.update(
            source="manual",
            provenance={
                **prov,
                "authority": "manual",
                "url": prov.get("url") or item["url"],
                "imported_by": user["username"],
                "acquired_at": now(),
            },
        )
        records.append(item)
    key = uid()
    with engine.begin() as c:
        save(
            c, settings, "import:" + key, data={"owner": user["id"], "records": records}
        )
    return {"id": key, "items": records}


@app.post(api + "/imports/{key}/commit")
def commit_import(key: str, user=Depends(writer)):
    with engine.begin() as c:
        r = get(c, settings, "import:" + key)
        if not r or r["data"]["owner"] != user["id"]:
            fail(404, "Unknown preview")
        count = ingest(c, "manual", r["data"]["records"])
        c.execute(delete(settings).where(settings.c.id == "import:" + key))
    return {"count": count}


class Connection(BaseModel):
    kind: Literal[
        "openai",
        "anthropic",
        "firecrawl",
        "agent_reach",
        "hackerone",
        "bugcrowd",
        "intigriti",
        "yeswehack",
    ]
    name: str = Field(min_length=1, max_length=120)
    endpoint: str = ""
    model: str = ""
    team: bool = False
    key: str = Field(default="", max_length=8192)


def permitted(c, id, user, edit=False):
    r = get(c, conns, id) if id else None
    if not r or not (
        r["owner"] == user["id"] or r["team"] and (not edit or user["role"] == "admin")
    ):
        fail(404, "Connection unavailable")
    return r


def public_conn(row):
    return {
        **{
            k: row[k]
            for k in ("id", "kind", "name", "team", "endpoint", "model", "owner")
        },
        "configured": bool(row["cipher"]),
    }


def save_conn(c, id, b, user, old=None):
    if b.team and user["role"] != "admin":
        fail(403, "Administrator required for team connections")
    if b.kind not in {s.split(":")[1] for s in OFFICIAL}:
        from .research import validated_target

        validated_target(b.endpoint, private=True)
    if (
        old
        and (old["endpoint"] != b.endpoint or old["kind"] != b.kind)
        and old["cipher"]
        and not b.key
    ):
        fail(422, "Supply replacement key for a new endpoint")
    cipher = (
        encrypt_secret(b.key, work.master(), id)
        if b.key
        else (old["cipher"] if old else "")
    )
    save(
        c,
        conns,
        id,
        owner=old["owner"] if old else user["id"],
        cipher=cipher,
        **b.model_dump(exclude={"key"}),
    )
    return public_conn(get(c, conns, id))


@app.get(api + "/connections")
def list_conn(user=Depends(writer)):
    with engine.connect() as c:
        return {
            "items": [
                public_conn(r)
                for r in c.execute(
                    select(conns).where(
                        (conns.c.owner == user["id"]) | (conns.c.team == 1)
                    )
                ).mappings()
            ]
        }


@app.post(api + "/connections")
def add_conn(b: Connection, user=Depends(writer)):
    with engine.begin() as c:
        return save_conn(c, uid(), b, user)


@app.put(api + "/connections/{id}")
def edit_conn(id: str, b: Connection, user=Depends(writer)):
    with engine.begin() as c:
        return save_conn(c, id, b, user, permitted(c, id, user, True))


@app.delete(api + "/connections/{id}")
def delete_conn(id: str, user=Depends(writer)):
    with engine.begin() as c:
        permitted(c, id, user, True)
        c.execute(delete(conns).where(conns.c.id == id))
    return {"deleted": True}


@app.post(api + "/connections/{id}/test")
def check_conn(id: str, user=Depends(writer)):
    with engine.connect() as c:
        permitted(c, id, user)
        r = work.usable(c, id, user["id"])
    if "api:" + r["kind"] in OFFICIAL:
        from .official import test_credentials

        return test_credentials(
            "api:" + r["kind"], {"key": r["key"], "username": r["model"]}
        )
    return test_connection(r)


class ResearchRequest(BaseModel):
    program_id: str
    llm_id: str
    browser_id: str | None = None
    daily: bool = False


@app.post(api + "/research")
def start_research(b: ResearchRequest, user=Depends(writer)):
    if b.daily and user["role"] != "admin":
        fail(403, "Administrator required for schedules")
    with engine.begin() as c:
        program(c, b.program_id)
        if permitted(c, b.llm_id, user)["kind"] not in ("anthropic", "openai"):
            fail(422, "Select an LLM connection")
        if b.browser_id and permitted(c, b.browser_id, user)["kind"] not in (
            "firecrawl",
            "agent_reach",
        ):
            fail(422, "Select a browsing connection")
        if b.daily:
            save(
                c,
                settings,
                "daily:" + user["id"] + ":" + b.program_id,
                data={**b.model_dump(), "owner": user["id"]},
            )
    return work.job("research", b.program_id, user["id"], b.model_dump())


@app.delete(api + "/research/{pid}/schedule")
def remove_schedule(pid: str, user=Depends(admin)):
    with engine.begin() as c:
        c.execute(
            delete(settings).where(settings.c.id == "daily:" + user["id"] + ":" + pid)
        )
    return {"scheduled": False}


def list_jobs(user, kind=None):
    with engine.connect() as c:
        query = select(jobs).where(
            (jobs.c.kind == "refresh") | (jobs.c.owner == user["id"])
        )
        if kind:
            query = query.where(jobs.c.kind == kind)
        return {
            "items": [
                dict(r)
                for r in c.execute(
                    query.order_by(jobs.c.started.desc()).limit(100)
                ).mappings()
            ]
        }


@app.get(api + "/research")
def research_jobs(user=Depends(writer)):
    return list_jobs(user, "research")


@app.get(api + "/jobs")
def runs(user=Depends(auth)):
    return list_jobs(user)


@app.post(api + "/jobs/{id}/cancel")
def cancel(id: str, user=Depends(writer)):
    with engine.begin() as c:
        r = get(c, jobs, id)
        if not r or r["owner"] != user["id"]:
            fail(404, "Unknown job")
        if r["kind"] != "research" or r["state"] not in ("queued", "running"):
            fail(409, "Job cannot be cancelled")
        c.execute(
            update(jobs)
            .where(jobs.c.id == id)
            .values(state="cancelled", finished=now(), active=None)
        )
    return {"state": "cancelled"}


@app.post(api + "/research/{id}/review")
def review(id: str, user=Depends(writer)):
    with engine.begin() as c:
        r = get(c, jobs, id)
        if not r or r["owner"] != user["id"]:
            fail(404, "Unknown job")
        if r["state"] != "needs_review":
            fail(409, "Job is not awaiting review")
        c.execute(update(jobs).where(jobs.c.id == id).values(state="reviewed"))
    return {"state": "reviewed"}


class Schedule(BaseModel):
    sources: list[str] = ["dataset:yeswehack"]
    interval_hours: int = Field(default=24, ge=1, le=720)
    daily_research_limit: int = Field(default=20, ge=0, le=500)


@app.get(api + "/schedule")
def get_schedule(user=Depends(auth)):
    with engine.connect() as c:
        r = get(c, settings, "schedule")
        return r["data"] if r else Schedule().model_dump()


@app.put(api + "/schedule")
def set_schedule(b: Schedule, user=Depends(admin)):
    if set(b.sources) - set(FEEDS):
        fail(422, "Select public dataset feeds")
    with engine.begin() as c:
        save(c, settings, "schedule", data=b.model_dump())
    return b


@app.get(api + "/programs/{pid}/scope-check")
def check_scope(pid: str, value: str, chain: str | None = None, user=Depends(auth)):
    from .core import scope_match

    with engine.connect() as c:
        return scope_match(program(c, pid)["scope"], value, chain)


dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
