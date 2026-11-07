#!/bin/sh
# Restore a backup into the running stack (replaces ALL current data).
#   ./restore.sh backups/aimva-20261106-210000.dump [backups/uploads-20261106-210000.tgz]
set -eu
cd "$(dirname "$0")"
[ -f "${1:-}" ] || { echo "usage: $0 <aimva-*.dump> [uploads-*.tgz]"; exit 1; }
printf "This replaces every row in the AIMVA database with %s. Type RESTORE to continue: " "$1"
read -r answer; [ "$answer" = "RESTORE" ] || exit 1
docker compose stop app
docker compose exec -T db pg_restore --clean --if-exists --no-owner -U aimva -d aimva < "$1"
if [ -n "${2:-}" ]; then
  docker compose run --rm -T -v "$(pwd)/$2:/restore.tgz:ro" --entrypoint sh app -c "tar -xzf /restore.tgz -C /app/backend/data"
fi
docker compose start app
echo "Restored. Check https://\$DOMAIN/api/ready"
