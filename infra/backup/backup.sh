#!/bin/sh
# Dump the database to BACKUP_DIR, prove the archive is readable, keep BACKUP_KEEP_DAYS of history, and copy it
# offsite when BACKUP_S3_URI is set. Connection: the standard PGHOST / PGUSER / PGPASSWORD / PGDATABASE variables.
set -eu
DIR="${BACKUP_DIR:-/backups}"
DB="${PGDATABASE:-invoiceflow}"
KEEP="${BACKUP_KEEP_DAYS:-14}"
mkdir -p "$DIR"
ts="$(date -u +%Y%m%dT%H%M%SZ)"
file="$DIR/$DB-$ts.dump"

pg_dump --format=custom --compress=6 --no-password --file "$file.partial" "$DB"
pg_restore --list "$file.partial" > /dev/null          # the archive can be read back
mv "$file.partial" "$file"
(cd "$DIR" && sha256sum "$(basename "$file")" > "$(basename "$file").sha256")

if [ -n "${BACKUP_S3_URI:-}" ]; then                   # e.g. s3://my-backups/invoiceflow
  endpoint=""
  [ -n "${AWS_ENDPOINT_URL:-}" ] && endpoint="--endpoint-url $AWS_ENDPOINT_URL"
  # shellcheck disable=SC2086
  aws s3 cp --only-show-errors $endpoint "$file" "$BACKUP_S3_URI/"
  # shellcheck disable=SC2086
  aws s3 cp --only-show-errors $endpoint "$file.sha256" "$BACKUP_S3_URI/"
fi

find "$DIR" -name "$DB-*.dump*" -type f -mtime +"$KEEP" -delete
date -u +%s > "$DIR/last_success"                     # read by the health check: stale backups raise an alert
echo "backup ok: $(basename "$file") $(du -h "$file" | cut -f1)${BACKUP_S3_URI:+, copied to $BACKUP_S3_URI}"
