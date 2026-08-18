#!/usr/bin/env sh
# Proves the most recent backup is actually restorable — not just that a
# .dump file exists. Restores it into a disposable scratch database
# (never the live one), runs a couple of sanity checks, then drops the
# scratch database. Reuses db-restore.sh rather than reimplementing the
# restore logic, so this is testing the same code path a real recovery
# would use.
#
# Usage: ./scripts/db-restore-test.sh [path-to-dump]
# With no argument, uses the newest file in backups/. Meant to run on a
# schedule via cron (weekly is reasonable — see docs/deployment.md) in
# addition to any time you want to sanity-check a specific backup by hand.

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$REPO_DIR/docker-compose.prod.yml"
ENV_FILE="$REPO_DIR/.env"
BACKUP_DIR="$REPO_DIR/backups"
LOG_FILE="$BACKUP_DIR/restore-test.log"

log() {
    msg="$(date -u '+%Y-%m-%dT%H:%M:%SZ') $1"
    echo "$msg" | tee -a "$LOG_FILE"
}

alert() {
    reason="$1"
    logger -t db-restore-test -p user.err "IMS restore test FAILED: $reason" 2>/dev/null || true
    log "ALERT: $reason"

    if [ -n "${DB_BACKUP_ALERT_WEBHOOK_URL:-}" ]; then
        curl -fsS -X POST -H "Content-Type: application/json" \
            -d "{\"text\":\"IMS restore test failed: $reason\"}" \
            "$DB_BACKUP_ALERT_WEBHOOK_URL" \
            >/dev/null 2>&1 || log "WARN: alert webhook POST itself failed — check DB_BACKUP_ALERT_WEBHOOK_URL"
    fi
}

mkdir -p "$BACKUP_DIR"
touch "$LOG_FILE"

if [ ! -f "$ENV_FILE" ]; then
    alert "$ENV_FILE not found — needed for POSTGRES_USER/POSTGRES_DB"
    exit 1
fi
# shellcheck disable=SC1090
. "$ENV_FILE"
: "${POSTGRES_USER:?POSTGRES_USER not set in .env}"
: "${POSTGRES_DB:?POSTGRES_DB not set in .env}"

DUMP_FILE="${1:-}"
if [ -z "$DUMP_FILE" ]; then
    DUMP_FILE="$(find "$BACKUP_DIR" -maxdepth 1 -name "${POSTGRES_DB}_*.dump" | sort | tail -n 1)"
fi
if [ -z "$DUMP_FILE" ] || [ ! -f "$DUMP_FILE" ]; then
    alert "no backup file found to test (looked in $BACKUP_DIR)"
    exit 1
fi

TEST_DB="${POSTGRES_DB}_restore_test"
log "Testing restorability of: $DUMP_FILE (into scratch db '$TEST_DB')"

psql_exec() {
    # $1: -d target, $2: SQL. Runs against the `db` container.
    docker compose -f "$COMPOSE_FILE" exec -T db \
        psql -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1 -tAc "$2"
}

# Always try to clean up the scratch db on exit, success or failure, so a
# crashed run doesn't leave it lying around to confuse the next one.
cleanup() {
    psql_exec postgres "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! psql_exec postgres "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1; then
    alert "could not drop any pre-existing scratch db '$TEST_DB'"
    exit 1
fi
if ! psql_exec postgres "CREATE DATABASE ${TEST_DB} OWNER ${POSTGRES_USER};" >/dev/null 2>&1; then
    alert "could not create scratch db '$TEST_DB'"
    exit 1
fi

if ! "$SCRIPT_DIR/db-restore.sh" --file "$DUMP_FILE" --target-db "$TEST_DB" --yes >>"$LOG_FILE" 2>&1; then
    alert "restore into scratch db failed — backup '$DUMP_FILE' may not be usable. See $LOG_FILE"
    exit 1
fi

# Sanity check 1: table count in the restored scratch db should match the
# live db's current table count. A partial/corrupt restore would show
# fewer tables; this doesn't hardcode a number, so it won't go stale as
# the schema evolves.
LIVE_TABLE_COUNT="$(psql_exec "$POSTGRES_DB" "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")"
TEST_TABLE_COUNT="$(psql_exec "$TEST_DB" "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")"
LIVE_TABLE_COUNT="$(echo "$LIVE_TABLE_COUNT" | tr -d ' ')"
TEST_TABLE_COUNT="$(echo "$TEST_TABLE_COUNT" | tr -d ' ')"

if [ "$TEST_TABLE_COUNT" != "$LIVE_TABLE_COUNT" ]; then
    alert "table count mismatch after restore: live=$LIVE_TABLE_COUNT restored=$TEST_TABLE_COUNT"
    exit 1
fi
log "Table count check passed ($TEST_TABLE_COUNT tables)."

# Sanity check 2: core tables are actually queryable (catches a restore
# that created the right number of tables but left one broken/empty of
# structure — count() would still error on a genuinely broken table).
for TBL in users tickets; do
    if ! psql_exec "$TEST_DB" "SELECT count(*) FROM ${TBL};" >/dev/null 2>&1; then
        alert "core table '$TBL' is not queryable in the restored scratch db"
        exit 1
    fi
done
log "Core table query check passed (users, tickets)."

log "Restore test PASSED for $DUMP_FILE."