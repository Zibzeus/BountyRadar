"""Generate installation-specific secrets, preserving existing configuration."""

import os
import secrets
import base64
from pathlib import Path

root = Path(__file__).resolve().parents[1]
(root / "secrets").mkdir(mode=0o700, exist_ok=True)


def create(path, value):
    try:
        fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(value + "\n")
    # Compose bind-mounts these individual files into non-root containers.
    # The host parent directory remains owner-only.
    if path.parent == root / "secrets" and os.name == "posix":
        path.chmod(0o444)


for name in ("admin", "reach", "master"):
    create(
        root / "secrets" / name,
        base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
    )
create(root / ".env", "RADAR_DB_PASSWORD=" + secrets.token_urlsafe(36))
print("Installation files ready. Admin password is in secrets/admin.")
