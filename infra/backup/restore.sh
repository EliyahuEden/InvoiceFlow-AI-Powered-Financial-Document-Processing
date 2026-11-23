#!/bin/sh
# Restore a dump into a database: restore.sh <file.dump> <target_db> [--replace]
# Checks the checksum first. Refuses to overwrite an existing database unless --replace is given.
set -eu
file="${1:?usage: restore.sh <file.dump> <target_db> [--replace]}"
target="${2:?usage: restore.sh <file.dump> <target_db> [--replace]}"
[ -f "$file" ] || { echo "no such dump: $file" >&2; exit 1; }
if [ -f "$file.sha256" ]; then
  (cd "$(dirname "$file")" && sha256sum -c --quiet "$(basename "$file").sha256") || { echo "checksum mismatch" >&2; exit 1; }
fi
exists="$(psql -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname = '$target'")"
if [ "$exists" = "1" ]; then
  [ "${3:-}" = "--replace" ] || { echo "database $target exists; add --replace to overwrite it" >&2; exit 1; }
  psql -d postgres -qc "DROP DATABASE \"$target\" WITH (FORCE)"
fi
psql -d postgres -qc "CREATE DATABASE \"$target\""
pg_restore --exit-on-error --no-password --dbname "$target" "$file"
echo "restored $(basename "$file") into $target"
