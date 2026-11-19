"""Run via python -m scripts.verify_slice from the project directory."""

import io, json, os, secrets, tempfile, zipfile
from pathlib import Path
from fastapi.testclient import TestClient


def main():
    with tempfile.TemporaryDirectory() as path:
        os.environ["DATABASE_URL"] = "sqlite:///" + (Path(path) / "test.db").as_posix()
        os.environ["RADAR_ADMIN_PASSWORD"] = secrets.token_urlsafe(30)
        from radar.app import app, engine

        for run in range(2):
            with TestClient(app) as client:
                assert client.post(
                    "/api/v1/login",
                    json={
                        "username": "admin",
                        "password": os.environ["RADAR_ADMIN_PASSWORD"],
                    },
                ).is_success
                if not run:
                    refresh = client.post(
                        "/api/v1/sources/dataset:yeswehack/refresh",
                        headers={"X-CSRF-Token": client.cookies["radar_csrf"]},
                    )
                    assert refresh.is_success, refresh.text
                    import time

                    jid = refresh.json()["id"]
                    for _ in range(180):
                        job = next(
                            j
                            for j in client.get("/api/v1/jobs").json()["items"]
                            if j["id"] == jid
                        )
                        if job["state"] not in ("queued", "running"):
                            break
                        time.sleep(1)
                    assert job["state"] in ("complete", "unchanged"), job
                page = client.get("/api/v1/programs").json()
                assert page["total"] > 0
                program = client.get(
                    "/api/v1/programs/" + page["items"][0]["id"]
                ).json()
                assert program["scope"] and program["provenance"]["url"]
                base = "/api/v1/programs/" + program["id"]
                with zipfile.ZipFile(
                    io.BytesIO(client.get(base + "/export").content)
                ) as bundle:
                    assert len(bundle.namelist()) == 5
                    assert (
                        json.loads(bundle.read("SCOPE_RULES.json"))["snapshot_id"]
                        == program["snapshot_id"]
                    )
                assert len(client.get(base + "/history").json()["items"]) == 1
                print(
                    "Verified",
                    page["total"],
                    "live records, scope detail, five-file export and snapshot history; pass",
                    run + 1,
                )
            engine.dispose()


if __name__ == "__main__":
    main()
