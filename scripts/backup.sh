#!/bin/sh
set -eu
umask 077
file=${1:?Usage: sh scripts/backup.sh NEW-FILE.dump}
[ ! -e "$file" ] || { echo "Backup destination already exists"; exit 1; }
docker compose exec -T db pg_dump -U radar -Fc radar > "$file.partial"
mv "$file.partial" "$file"

