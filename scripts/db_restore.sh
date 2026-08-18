#!/usr/bin/env sh
# Restores a pg_dump custom-format backup (as produced by db-backup.sh) into
# a PostgreSQL database via the running `db` container.
#
# Used two ways:
#   - Directly, for a real disaster-recovery restore (requires --yes,
#     since this is destructive to whatever's already in the target).
#   - By db-restore-test.sh, which calls this against a scratch database
#     to verify a backup is actually restorable — not just that the file
#     exists.
#
# Usage:
#   ./scripts/db-restore.sh --file backups/ims_20260818_030000.dump --yes
#   ./scripts/db-restore.sh --file <path> --target-db ims_restore_test --yes
#
# Without --yes, prints what it would do and exits without touching
# anything — a deliberate default given this can destroy data in the
# target database.

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$REPO_DIR/docker-compose.prod.yml"
ENV_FILE="$REPO_DIR/.env"

DUMP_FILE=""
TARGET_DB=""
CONFIRMED=0

usage() {
    echo "Usage: $0 --file <path-to-dump> [--target-db <name>] [--yes]"
    echo
    echo "  --file        Path to a pg_dump custom-format (-Fc) backup file. Required."
    echo "  --target-db   Database to restore into. Defaults to POSTGRES_DB from .env"
    echo "                (i.e. the live database) — pass a scratch name to avoid that."
    echo "  --yes         Actually perform the restore. Without this flag, the script"
    echo "                only prints what it would do and exits 0."
}

while [ $# -gt 0 ]; do
    case "$1" in
        --file) DUMP_FILE="$2"; shift 2 ;;
        --target-db) TARGET_DB="$2"; shift 2 ;;
        --yes) CONFIRMED=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
    esac
done

if [ -z "$DUMP_FILE" ]; then
    echo "ERROR: --file is required." >&2
    usage
    exit 1
fi

if [ ! -f "$DUMP_FILE" ]; then
    echo "ERROR: backup file not found: $DUMP_FILE" >&2
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: $ENV_FILE not found — needed for POSTGRES_USER/POSTGRES_DB." >&2
    exit 1
fi

# shellcheck disable=SC1090
. "$ENV_FILE"

: "${POSTGRES_USER:?POSTGRES_USER not set in .env}"
: "${POSTGRES_DB:?POSTGRES_DB not set in .env}"

if [ -z "$TARGET_DB" ]; then
    TARGET_DB="$POSTGRES_DB"
fi

echo "About to restore:"
echo "  Source file : $DUMP_FILE"
echo "  Target DB   : $TARGET_DB"
if [ "$TARGET_DB" = "$POSTGRES_DB" ]; then
    echo "  *** This is the LIVE database. Existing data will be dropped and replaced. ***"
fi

if [ "$CONFIRMED" != "1" ]; then
    echo
    echo "Dry run only (no --yes given) — nothing was changed. Re-run with --yes to proceed."
    exit 0
fi

echo "Restoring..."
# --clean --if-exists: drop existing objects before recreating, so this is
# safe to re-run against a target that already has the schema in it.
# --no-owner --no-privileges: don't fight over role ownership if the
# backup/restore environments' postgres roles ever diverge.
if ! cat "$DUMP_FILE" | docker compose -f "$COMPOSE_FILE" exec -T db \
    pg_restore -U "$POSTGRES_USER" -d "$TARGET_DB" \
    --clean --if-exists --no-owner --no-privileges; then
    echo "ERROR: pg_restore failed." >&2
    exit 1
fi

echo "Restore into '$TARGET_DB' completed."