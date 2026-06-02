#!/usr/bin/env bash
set -euo pipefail

# OpenZooData database initialization script
# Usage:
#   ./source/helpers/db_init.sh
#
# Optional:
#   ./source/helpers/db_init.sh --auth-only
#   ./source/helpers/db_init.sh --zoo-only

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
SCHEMA_DIR="$ROOT_DIR/source/schema"

AUTH_SCHEMA="$SCHEMA_DIR/auth_schema.sql"
ZOO_SCHEMA="$SCHEMA_DIR/zoo_schema.sql"

INIT_AUTH=true
INIT_ZOO=true

if [[ "${1:-}" == "--auth-only" ]]; then
  INIT_ZOO=false
fi

if [[ "${1:-}" == "--zoo-only" ]]; then
  INIT_AUTH=false
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env file not found at: $ENV_FILE"
  exit 1
fi

if [[ ! -d "$SCHEMA_DIR" ]]; then
  echo "ERROR: schema directory not found at: $SCHEMA_DIR"
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

run_psql() {
  local host="$1"
  local user="$2"
  local db="$3"
  local password="$4"
  local schema_file="$5"

  if [[ ! -f "$schema_file" ]]; then
    echo "ERROR: schema file not found: $schema_file"
    exit 1
  fi

  echo "Importing schema:"
  echo "  Database: $db"
  echo "  User:     $user"
  echo "  Host:     $host"
  echo "  File:     $schema_file"

  PGPASSWORD="$password" psql \
    -h "$host" \
    -U "$user" \
    -d "$db" \
    -v ON_ERROR_STOP=1 \
    -f "$schema_file"

  echo "Done: $schema_file"
  echo
}

if [[ "$INIT_AUTH" == true ]]; then
  : "${AUTH_DB_HOST:?AUTH_DB_HOST missing in .env}"
  : "${AUTH_DB_USER:?AUTH_DB_USER missing in .env}"
  : "${AUTH_DB_PASSWORD:?AUTH_DB_PASSWORD missing in .env}"
  : "${AUTH_DB_NAME:?AUTH_DB_NAME missing in .env}"

  run_psql \
    "$AUTH_DB_HOST" \
    "$AUTH_DB_USER" \
    "$AUTH_DB_NAME" \
    "$AUTH_DB_PASSWORD" \
    "$AUTH_SCHEMA"
fi

if [[ "$INIT_ZOO" == true ]]; then
  : "${PG_HOST:?PG_HOST missing in .env}"
  : "${PG_USER:?PG_USER missing in .env}"
  : "${PG_PASSWORD:?PG_PASSWORD missing in .env}"
  : "${PG_NAME:?PG_NAME missing in .env}"

  run_psql \
    "$PG_HOST" \
    "$PG_USER" \
    "$PG_NAME" \
    "$PG_PASSWORD" \
    "$ZOO_SCHEMA"
fi

echo "Database initialization completed."