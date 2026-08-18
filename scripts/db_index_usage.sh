#!/usr/bin/env sh
# Reports actual index usage from PostgreSQL's own stats
# (pg_stat_user_indexes), rather than assuming the indexes added in
# migrations 0002/0004 etc. are actually earning their keep.
#
# Run this against a database that's seen real production traffic —
# right after deploy, every index will correctly show 0 scans, which
# doesn't mean anything is wrong yet. Re-run periodically (monthly is
# reasonable) once there's real usage to judge by.
#
# Usage: ./scripts/db-index-usage.sh

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$REPO_DIR/docker-compose.prod.yml"
ENV_FILE="$REPO_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found." >&2
    exit 1
fi
# shellcheck disable=SC1090
. "$ENV_FILE"
: "${POSTGRES_USER:?POSTGRES_USER not set in .env}"
: "${POSTGRES_DB:?POSTGRES_DB not set in .env}"

echo "=== Indexes with zero scans (candidates for review, not automatic removal) ==="
docker compose -f "$COMPOSE_FILE" exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'SQL'
SELECT
    schemaname || '.' || relname AS table,
    indexrelname AS index,
    idx_scan AS scans,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
FROM pg_stat_user_indexes
WHERE idx_scan = 0
  AND indexrelname NOT LIKE '%_pkey'  -- primary keys enforce uniqueness even at 0 scans, not a real candidate
ORDER BY pg_relation_size(indexrelid) DESC;
SQL

echo
echo "=== Tables with high sequential-scan counts relative to index scans (possible missing index) ==="
docker compose -f "$COMPOSE_FILE" exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'SQL'
SELECT
    schemaname || '.' || relname AS table,
    seq_scan,
    idx_scan,
    n_live_tup AS approx_rows
FROM pg_stat_user_tables
WHERE seq_scan > idx_scan
  AND n_live_tup > 1000  -- small tables are cheap to scan either way, not worth flagging
ORDER BY seq_scan DESC
LIMIT 20;
SQL

echo
echo "Reminder: these stats reset if postgres restarts (pg_stat_reset()) or the"
echo "container recreates the volume. Judge trends over a real traffic window,"
echo "not a single run right after a restart."