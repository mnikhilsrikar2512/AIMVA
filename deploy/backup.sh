#!/bin/sh
# Nightly backups: a compressed Postgres dump and a tarball of uploads, kept BACKUP_KEEP_DAYS days.
#   sh backup.sh once     one backup now
#   sh backup.sh loop     every day at BACKUP_HOUR_UTC (what the compose service runs)
# Copy /backups off the server too (rclone, restic, or your host's snapshots): a backup on the same disk
# doesn't survive losing that disk.
set -eu
KEEP="${BACKUP_KEEP_DAYS:-14}"
HOUR="${BACKUP_HOUR_UTC:-21}"

backup() {
  stamp=$(date -u +%Y%m%d-%H%M%S)
  pg_dump --format=custom --no-owner --file="/backups/aimva-$stamp.dump.tmp"
  mv "/backups/aimva-$stamp.dump.tmp" "/backups/aimva-$stamp.dump"
  if [ -d /appdata ]; then
    tar -czf "/backups/uploads-$stamp.tgz.tmp" -C /appdata . && mv "/backups/uploads-$stamp.tgz.tmp" "/backups/uploads-$stamp.tgz"
  fi
  find /backups -name 'aimva-*.dump' -mtime "+$KEEP" -delete
  find /backups -name 'uploads-*.tgz' -mtime "+$KEEP" -delete
  echo "$(date -u +%FT%TZ) backup ok: aimva-$stamp.dump ($(du -h "/backups/aimva-$stamp.dump" | cut -f1))"
}

case "${1:-once}" in
  once) backup ;;
  loop)
    backup  # one at start, so a fresh server is never without a backup
    while true; do
      now=$(date -u +%s)
      next=$(date -u -d "@$(( (now / 86400) * 86400 + HOUR * 3600 ))" +%s 2>/dev/null || echo $((now + 86400)))
      [ "$next" -le "$now" ] && next=$((next + 86400))
      sleep $((next - now))
      backup || echo "$(date -u +%FT%TZ) BACKUP FAILED"
    done ;;
esac
