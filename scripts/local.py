"""Serve the built dashboard locally with persistent SQLite storage and a scheduler."""

import base64
import os
import secrets
import threading
from pathlib import Path

root = Path(__file__).resolve().parents[1]
state = Path(
    os.getenv("RADAR_STATE_DIR")
    or Path(os.getenv("LOCALAPPDATA", Path.home() / ".local/share")) / "BountyRadar"
)


def main():
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    for key, name in (
        ("RADAR_ADMIN_PASSWORD_FILE", "admin"),
        ("RADAR_MASTER_KEY_FILE", "master"),
    ):
        path = state / name
        if not path.exists():
            with os.fdopen(
                os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
            ) as f:
                f.write(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
        os.environ.setdefault(key, str(path))
    os.environ.setdefault(
        "DATABASE_URL", "sqlite:///" + (state / "catalog.db").as_posix()
    )
    from radar.work import tick
    from radar.db import engine, meta
    import uvicorn

    if not (root / "frontend/dist/index.html").exists():
        raise SystemExit("Build frontend first (npm ci && npm run build)")
    meta.create_all(engine)

    def schedule():
        from time import sleep

        while True:
            tick()
            sleep(60)

    threading.Thread(target=schedule, daemon=True).start()
    uvicorn.run(
        "radar.app:app", host="127.0.0.1", port=int(os.getenv("RADAR_PORT", "8098"))
    )


if __name__ == "__main__":
    main()
