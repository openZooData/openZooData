#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# OpenZooData PostgreSQL backup script
#
# Creates one timestamped snapshot directory per run:
#   backup/YYYYMMDD_HHMMSS/
#     <PG_NAME>.dump
#     <PG_NAME>_schema.sql
#     <AUTH_NAME>.dump
#     <AUTH_NAME>_schema.sql
#
# Required environment variables can be provided by a .env file next to this
# script or by the shell environment.
# ---------------------------------------------------------------------------

#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [ -f "$ROOT_DIR/.env" ]; then
    set -a
    source "$ROOT_DIR/.env"
    set +a
else
    echo "ERROR: .env not found at $ROOT_DIR/.env"
    exit 1
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "ERROR: Required environment variable '${name}' is not set." >&2
    exit 1
  fi
}

require_command() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "ERROR: Required command '${cmd}' was not found." >&2
    exit 1
  fi
}

backup_database() {
  local label="$1"
  local host="$2"
  local port="$3"
  local user="$4"
  local password="$5"
  local db_name="$6"

  local dump_file="${BACKUP_DIR}/${db_name}.dump"
  local schema_file="${BACKUP_DIR}/${db_name}_schema.sql"

  echo ""
  echo "Backing up ${label} database: ${db_name}"
  echo "  dump:   ${dump_file}"
  echo "  schema: ${schema_file}"

  export PGPASSWORD="${password}"

  pg_dump \
    -h "${host}" \
    -p "${port}" \
    -U "${user}" \
    -Fc \
    "${db_name}" \
    > "${dump_file}"

  pg_dump \
    -h "${host}" \
    -p "${port}" \
    -U "${user}" \
    --schema-only \
    --no-owner \
    --no-privileges \
    "${db_name}" \
    > "${schema_file}"

  unset PGPASSWORD
}

# ---------------------------------------------------------------------------
# Validate configuration
# ---------------------------------------------------------------------------

require_command pg_dump

# Zoo database
require_var PG_HOST
require_var PG_PORT
require_var PG_USER
require_var PG_PASSWORD
require_var PG_NAME

# Auth database
require_var AUTH_HOST
require_var AUTH_PORT
require_var AUTH_USER
require_var AUTH_PASSWORD
require_var AUTH_NAME

# ---------------------------------------------------------------------------
# Backup directory
# ---------------------------------------------------------------------------

TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
BACKUP_ROOT="${BACKUP_ROOT:-${SCRIPT_DIR}/backup}"
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"

mkdir -p "${BACKUP_DIR}"

# ---------------------------------------------------------------------------
# Run backups
# ---------------------------------------------------------------------------

echo "OpenZooData database backup"
echo "Backup directory: ${BACKUP_DIR}"

backup_database \
  "zoo" \
  "${PG_HOST}" \
  "${PG_PORT}" \
  "${PG_USER}" \
  "${PG_PASSWORD}" \
  "${PG_NAME}"

backup_database \
  "auth" \
  "${AUTH_HOST}" \
  "${AUTH_PORT}" \
  "${AUTH_USER}" \
  "${AUTH_PASSWORD}" \
  "${AUTH_NAME}"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "Backup completed successfully."
echo ""
echo "Created snapshot:"
echo "  ${BACKUP_DIR}"
echo ""
echo "Files:"
ls -lh "${BACKUP_DIR}"
