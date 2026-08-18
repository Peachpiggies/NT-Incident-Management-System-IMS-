#!/usr/bin/env sh
# Takes a pg_dump custom-format (-Fc) backup of the live database via the
# running `db` container, applies a retention policy (delete backups older
# than RETENTION_DAYS), and logs every run. Custom format is used instead
# of plain SQL because it's compressed, and it's what db-restore.sh's
# pg_restore expects.
#
# On failure, alerts the same way nginx/renew-cert-if-needed.sh does:
# always to syslog via `logger`, and to DB_BACKUP_ALERT_WEBHOOK_URL if
# that's set (optional — everything else works without it).
#
# Usage: ./scripts/db-backup.sh
# Typically invoked by cron (see docs/deployment.md).

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$REPO_DIR/docker-compose.prod.yml"
ENV_FILE="$REPO_DIR/.env"
BACKUP_DIR="$REPO_DIR/backups"
LOG_FILE="$BACKUP_DIR/backup.log"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

log() {
    msg="$(date -u '+%Y-%m-%dT%H:%M:%SZ') $1"
    echo "$msg" | tee -a "$LOG_FILE"
}

alert() {
    reason="$1"
    logger -t db-backup -p user.err "IMS db backup FAILED: $reason" 2>/dev/null || true
    log "ALERT: $reason"

    if [ -n "${DB_BACKUP_ALERT_WEBHOOK_URL:-}" ]; then
        curl -fsS -X POST -H "Content-Type: application/json" \
            -d "{\"text\":\"IMS db backup failed: $reason\"}" \
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

TIMESTAMP="$(date -u '+%Y%m%d_%H%M%S')"
OUT_FILE="$BACKUP_DIR/${POSTGRES_DB}_${TIMESTAMP}.dump"
TMP_FILE="${OUT_FILE}.partial"

log "Starting backup of '$POSTGRES_DB' -> $OUT_FILE"

if ! docker compose -f "$COMPOSE_FILE" exec -T db \
    pg_dump -U "$POSTGRES_USER" -Fc -d "$POSTGRES_DB" > "$TMP_FILE"; then
    rm -f "$TMP_FILE"
    alert "pg_dump failed — see $LOG_FILE"
    exit 1
fi

# A 0-byte or near-empty file means pg_dump produced nothing usable even
# if it exited 0 (e.g. it wrote an error to stdout that we didn't catch).
SIZE="$(wc -c < "$TMP_FILE" | tr -d ' ')"
if [ "$SIZE" -lt 100 ]; then
    alert "backup file suspiciously small (${SIZE} bytes) — treating as failed, not keeping it"
    rm -f "$TMP_FILE"
    exit 1
fi

mv "$TMP_FILE" "$OUT_FILE"
log "Backup complete: $OUT_FILE (${SIZE} bytes)"

# Retention: delete backups older than RETENTION_DAYS. -mtime +N means
# "modified more than N*24h ago", so this always keeps at least today's.
DELETED="$(find "$BACKUP_DIR" -maxdepth 1 -name "${POSTGRES_DB}_*.dump" -mtime "+${RETENTION_DAYS}" -print)"
if [ -n "$DELETED" ]; then
    echo "$DELETED" | while IFS= read -r f; do
        rm -f "$f"
        log "Deleted old backup (older than ${RETENTION_DAYS}d): $f"
    done
fi

log "Backup run finished successfully."