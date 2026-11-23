#!/bin/sh
# Restore drill: restore the newest dump into a scratch database, check that it is complete and current, then drop
# it. Exit code 0 means a real restore works. Set KEEP_DRILL=1 to keep the scratch database for further checks.
set -eu
DIR="${BACKUP_DIR:-/backups}"
DB="${PGDATABASE:-invoiceflow}"
SCRATCH="${DB}_restore_drill"
latest="$(ls -1t "$DIR/$DB"-*.dump 2>/dev/null | head -1 || true)"
[ -n "$latest" ] || { echo "no dump in $DIR" >&2; exit 1; }

restore.sh "$latest" "$SCRATCH" --replace
q() { psql -d "$1" -Atc "$2"; }
src_ver="$(q "$DB" "SELECT version_num FROM alembic_version")"
dst_ver="$(q "$SCRATCH" "SELECT version_num FROM alembic_version")"
src_tables="$(q "$DB" "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")"
dst_tables="$(q "$SCRATCH" "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")"
orgs="$(q "$SCRATCH" "SELECT count(*) FROM organizations")"
fail=""
[ "$src_ver" = "$dst_ver" ] || fail="$fail schema version $dst_ver differs from live $src_ver (restore from an older backup?);"
[ "$src_tables" = "$dst_tables" ] || fail="$fail $dst_tables tables restored, live has $src_tables;"
[ "$orgs" -gt 0 ] || fail="$fail no organizations restored;"
echo "drill: $(basename "$latest") -> $SCRATCH | schema $dst_ver | tables $dst_tables | $(q "$SCRATCH" "SELECT format('%s organizations, %s invoices, %s audit entries', (SELECT count(*) FROM organizations), (SELECT count(*) FROM invoices), (SELECT count(*) FROM audit_logs))")"
[ "${KEEP_DRILL:-0}" = "1" ] || psql -d postgres -qc "DROP DATABASE \"$SCRATCH\" WITH (FORCE)"
if [ -n "$fail" ]; then echo "drill FAILED:$fail" >&2; exit 1; fi
echo "drill ok"
