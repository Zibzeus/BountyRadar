import base64
import io
import json
import os
import secrets
import zipfile
import pytest
from cryptography.exceptions import InvalidTag
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from radar import db, app as api, work, research
from radar.core import normalize_rule, scope_match, changes
from radar.score import DEFAULT, score


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite:///" + (tmp_path / "db").as_posix(),
        connect_args={"check_same_thread": False},
    )
    for module in (db, api, work):
        monkeypatch.setattr(module, "engine", engine)
    monkeypatch.setenv("RADAR_ADMIN_PASSWORD", "test-administrator-123")
    monkeypatch.setenv(
        "RADAR_MASTER_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode()
    )
    with TestClient(api.app) as c:
        assert c.post(
            "/api/v1/login",
            json={"username": "admin", "password": "test-administrator-123"},
        ).is_success
        c.headers["X-CSRF-Token"] = c.cookies["radar_csrf"]
        yield c
    engine.dispose()


def record(**fields):
    return {
        "name": "Policy lab",
        "platform": "Independent",
        "external_id": "example",
        "url": "https://example.org/policy",
        "kind": "vdp",
        "policy": "Published rules",
        "scope": [{"raw": "*.example.org", "effect": "include", "kind": "wildcard"}],
        **fields,
    }


def upload(c, r):
    p = c.post("/api/v1/imports/preview", json={"records": [r]})
    assert p.is_success, p.text
    return c.post("/api/v1/imports/" + p.json()["id"] + "/commit")


def test_import_history_export_and_bookmark(client):
    c = client
    assert upload(c, record()).is_success
    assert upload(c, record()).is_success
    items = c.get("/api/v1/programs").json()
    assert items["total"] == 1
    pid = items["items"][0]["id"]
    route = "/api/v1/programs/" + pid
    assert len(c.get(route + "/history").json()["items"]) == 1
    assert upload(c, record(policy="Updated rules", scope=None)).is_success
    detail = c.get(route).json()
    assert detail["scope"] is None and detail["verification"] == "manual"
    events = c.get(route + "/history").json()["items"]
    assert len(events) == 2 and {"scope", "policy"} <= {
        x["field"] for x in events[0]["diff"]
    }
    assert c.put(route + "/bookmark").is_success
    assert c.get("/api/v1/programs?bookmarked=true").json()["total"] == 1
    assert c.delete(route + "/bookmark").is_success
    with zipfile.ZipFile(io.BytesIO(c.get(route + "/export").content)) as z:
        assert len(z.namelist()) == 5
        assert json.loads(z.read("SCOPE_RULES.json"))["rules"] is None
        assert "Updated rules" in z.read("PROGRAM_POLICY.md").decode()


def test_permissions_and_secrets(client):
    c = client
    assert (
        c.post(
            "/api/v1/users",
            headers={"X-CSRF-Token": "bad"},
            json={
                "username": "r",
                "password": "long-password-123",
                "role": "researcher",
            },
        ).status_code
        == 403
    )
    for role in ("researcher", "viewer"):
        assert c.post(
            "/api/v1/users",
            json={"username": role, "password": "long-password-123", "role": role},
        ).is_success
    secret = secrets.token_hex(20)
    r = c.post(
        "/api/v1/connections",
        json={"kind": "hackerone", "model": "user", "name": "Personal", "key": secret},
    )
    assert r.is_success and secret not in r.text
    with db.engine.connect() as conn:
        stored = conn.execute(select(db.conns)).mappings().one()
        assert secret not in stored["cipher"]
        with pytest.raises(InvalidTag):
            research.decrypt_secret(stored["cipher"], work.master(), "different-id")
    for role in ("researcher", "viewer"):
        assert c.post(
            "/api/v1/login", json={"username": role, "password": "long-password-123"}
        ).is_success
        c.headers["X-CSRF-Token"] = c.cookies["radar_csrf"]
        assert c.delete("/api/v1/connections/" + r.json()["id"]).status_code in (
            403,
            404,
        )
        assert c.get("/api/v1/users").status_code == 403
    assert (
        c.post("/api/v1/imports/preview", json={"records": [record()]}).status_code
        == 403
    )


def test_outage_preserves_snapshot(client, monkeypatch):
    assert upload(client, record()).is_success
    monkeypatch.setattr(work.pool, "submit", lambda fn, i: fn(i))
    from radar.sources import SourceError

    def failed(*args):
        raise SourceError("Invalid page")

    monkeypatch.setattr(work, "fetch_source", failed)
    run = client.post("/api/v1/sources/dataset:yeswehack/refresh").json()
    assert run["state"] == "failed"
    assert client.get("/api/v1/programs").json()["total"] == 1


def test_listing_disappearance_and_return(client):
    first = record()
    second = record(external_id="other", name="Another program")
    source = "dataset:yeswehack"
    with db.engine.begin() as c:
        db.ingest(c, source, [first, second], complete=True)
    pid = client.get("/api/v1/programs?q=Policy%20lab").json()["items"][0]["id"]
    route = "/api/v1/programs/" + pid
    original = client.get(route).json()["snapshot_id"]
    with db.engine.begin() as c:
        db.ingest(c, source, [second], complete=True)
        db.ingest(c, source, [second], complete=True)
    detail = client.get(route).json()
    assert detail["possibly_removed"] and detail["snapshot_id"] == original
    history = client.get(route + "/history").json()["items"]
    assert len(history) == 2 and history[0]["verification"] == "listing observation"
    assert "missing" in client.get(route + "/export?file=SCOPE_CHANGELOG.md").text
    with db.engine.begin() as c:
        db.ingest(c, source, [first, second], complete=True)
    assert not client.get(route).json()["possibly_removed"]
    assert client.get(route + "/history").json()["items"][0]["diff"] == [
        {"field": "listing_presence", "before": "missing", "after": "listed"}
    ]


def test_match_boundaries():
    rules = [
        normalize_rule({"raw": raw, "kind": kind, "effect": effect})
        for raw, kind, effect in [
            ("*.Example.ORG", "wildcard", "include"),
            ("admin.example.org", "domain", "exclude"),
            ("2001:db8::/32", "cidr", "include"),
            ("https://example.org/private", "url", "include"),
        ]
    ]
    assert scope_match(rules, "example.org")["effect"] == "unknown"
    assert (
        scope_match(rules, "https://unrelated.test/path.example.org")["effect"]
        == "unknown"
    )
    assert scope_match(rules, "user@sub.example.org")["effect"] == "unknown"
    assert scope_match(rules, "admin.example.org")["effect"] == "exclude"
    assert scope_match(rules, "www.example.org")["effect"] == "include"
    assert scope_match(rules, "2001:db8::1")["effect"] == "include"
    assert scope_match(rules, "https://example.org/private/more")["effect"] == "unknown"
    assert changes({"policy": "some words"}, {"policy": "some  words"}) == []
    r = score(record(scope=None), DEFAULT, None)
    assert r["coverage"] < 100 and r["contributions"]["complexity"] is None
    excluded = record(scope=[{"kind": "repository", "effect": "exclude"}])
    assert score(excluded, DEFAULT, None)["contributions"]["repositories"] is None


@pytest.mark.parametrize(
    "url",
    [
        "file:///a",
        "http://127.0.0.1",
        "https://127.0.0.1",
        "https://user:secret@example.org",
    ],
)
def test_endpoint_guard(url):
    with pytest.raises(research.ResearchError):
        research.validated_target(url)


def test_preferences_schedules_review_and_quota(client, monkeypatch):
    c = client
    assert c.get("/health").json()["status"] == "ok"
    assert c.get("/api/v1/me").json()["role"] == "admin"
    assert len(c.get("/api/v1/sources").json()["items"]) >= 10
    assert c.post("/api/v1/sources/api:bugcrowd/refresh").status_code == 422
    assert c.get("/api/v1/schedule").is_success
    assert c.put(
        "/api/v1/schedule", json={"sources": [], "daily_research_limit": 1}
    ).is_success
    prefs = c.get("/api/v1/profile").json()
    prefs["interests"] = ["wildcard"]
    assert c.put("/api/v1/profile", json=prefs).is_success
    assert c.put("/api/v1/profile", json={"weights": {"junk": 0}}).status_code == 422
    assert upload(c, record()).is_success
    pid = c.get("/api/v1/programs").json()["items"][0]["id"]
    assert (
        c.get("/api/v1/programs/" + pid + "/scope-check?value=www.example.org").json()[
            "effect"
        ]
        == "include"
    )
    assert c.get("/api/v1/changes").json()["items"][0]["program_id"] == pid
    monkeypatch.setattr(research, "validated_target", lambda *a, **kw: None)
    body = {
        "kind": "openai",
        "endpoint": "https://example.org/v1",
        "key": "example",
        "model": "m",
        "name": "Gateway",
    }
    cid = c.post("/api/v1/connections", json=body).json()["id"]
    assert (
        c.put(
            "/api/v1/connections/" + cid,
            json={**body, "key": "", "endpoint": "https://another.example/v1"},
        ).status_code
        == 422
    )
    assert c.put(
        "/api/v1/connections/" + cid, json={**body, "key": "", "name": "New name"}
    ).is_success
    assert "example" not in str(
        c.get("/api/v1/connections").json()["items"][0].get("key")
    )
    monkeypatch.setattr(research, "_request", lambda *args, **kw: {"data": []})
    assert c.post("/api/v1/connections/" + cid + "/test").json()["ok"]
    monkeypatch.setattr(work.pool, "submit", lambda fn, i: fn(i))
    monkeypatch.setattr(research, "_answer", lambda *args: ("Policy [S1]", [], 20, 4))
    payload = {"program_id": pid, "llm_id": cid, "daily": True}
    j = c.post("/api/v1/research", json=payload).json()
    assert j["state"] == "needs_review"
    assert c.post("/api/v1/research/" + j["id"] + "/review").is_success
    assert c.get("/api/v1/research").json()["items"][0]["state"] == "reviewed"
    assert c.post("/api/v1/research", json=payload).status_code == 422
    assert c.delete("/api/v1/research/" + pid + "/schedule").is_success
    assert c.delete("/api/v1/connections/" + cid).is_success
    assert c.post("/api/v1/logout").is_success
    assert c.get("/api/v1/me").status_code == 401
