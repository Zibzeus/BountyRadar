"""Exercise a running disposable Compose installation through its published origin."""

import http.cookiejar
import io
import json
import os
import time
import urllib.request
import zipfile
from pathlib import Path


def main():
    base = os.getenv("RADAR_TEST_ORIGIN", "http://127.0.0.1:18098") + "/api/v1"
    jar = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def request(path, body=None):
        headers = {
            "Content-Type": "application/json",
            "X-CSRF-Token": next((c.value for c in jar if c.name == "radar_csrf"), ""),
        }
        payload = json.dumps(body).encode() if body is not None else None
        with client.open(
            urllib.request.Request(base + path, data=payload, headers=headers),
            timeout=45,
        ) as res:
            return res.read()

    request(
        "/login",
        {"username": "admin", "password": Path("secrets/admin").read_text().strip()},
    )
    runs = json.loads(request("/jobs"))["items"]
    job = next(
        (
            r
            for r in runs
            if r["source"] == "dataset:yeswehack"
            and r["state"] in ("queued", "running", "complete")
        ),
        None,
    )
    if not job:
        job = json.loads(request("/sources/dataset:yeswehack/refresh", {}))
    for _ in range(120):
        latest = next(
            r for r in json.loads(request("/jobs"))["items"] if r["id"] == job["id"]
        )
        if latest["state"] not in ("queued", "running"):
            break
        time.sleep(1)
    if latest["state"] not in ("complete", "unchanged"):
        raise RuntimeError(str(latest["details"]))
    page = json.loads(request("/programs?page_size=1"))
    assert page["total"] > 0
    program = json.loads(request("/programs/" + page["items"][0]["id"]))
    with zipfile.ZipFile(
        io.BytesIO(request("/programs/" + page["items"][0]["id"] + "/export"))
    ) as archive:
        assert set(archive.namelist()) == {
            "PROGRAM_SCOPE.md", "PROGRAM_POLICY.md", "PROGRAM_METADATA.json",
            "SCOPE_RULES.json", "SCOPE_CHANGELOG.md",
        }
        rules = json.loads(archive.read("SCOPE_RULES.json"))
        assert rules["snapshot_id"] == program["snapshot_id"] and rules["provenance"]["url"]
    print(
        "Compose API, Postgres, broker, worker and export verified;",
        page["total"],
        "catalog entries.",
    )


if __name__ == "__main__":
    main()
