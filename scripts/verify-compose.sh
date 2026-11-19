#!/bin/sh
# Isolated smoke test. Use COMPOSE to select a standalone Compose executable.
set -eu
compose() {
  if [ -n "${COMPOSE:-}" ]; then "$COMPOSE" -p "$project" "$@"; else docker compose -p "$project" "$@"; fi
}
project="brtest$(date +%s)$$"

stage=$(mktemp -d /tmp/bountyradar-test.XXXXXXXX)
cleanup() {
  if [ -f "$stage/.env" ]; then (cd "$stage" && compose down -v) >/dev/null 2>&1 || true; fi
  cd /
  case "$stage" in /tmp/bountyradar-test.????????) rm -rf -- "$stage";; esac
}
trap cleanup EXIT
tar --exclude=.git --exclude=.venv --exclude=node_modules --exclude=dist --exclude=.env --exclude=secrets --exclude=.pytest_cache --exclude=__pycache__ -cf - . | tar -C "$stage" -xf -
cd "$stage"
python3 scripts/setup.py
export RADAR_PORT=18098
compose config --quiet
compose up --build --wait -d
curl -fsS http://127.0.0.1:18098/health
python3 scripts/verify_deployment.py

