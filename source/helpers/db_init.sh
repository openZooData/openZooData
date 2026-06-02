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
  local port="$2"
  local user="$3"
  local db="$4"
  local password="$5"
  local schema_file="$6"

  if [[ ! -f "$schema_file" ]]; then
    echo "ERROR: schema file not found: $schema_file"
    exit 1
  fi

  echo "Importing schema:"
  echo "  Database: $db"
  echo "  User:     $user"
  echo "  Host:     $host"
  echo "  Port:     $port"
  echo "  File:     $schema_file"

  PGPASSWORD="$password" psql \
    -h "$host" \
    -p "$port" \
    -U "$user" \
    -d "$db" \
    -v ON_ERROR_STOP=1 \
    -f "$schema_file"

  echo "Done: $schema_file"
  echo
}

if [[ "$INIT_AUTH" == true ]]; then
  : "${AUTH_HOST:?AUTH_HOST missing in .env}"
  : "${AUTH_PORT:=?AUTH_PORT missing in .env}}"
  : "${AUTH_USER:?AUTH_USER missing in .env}"
  : "${AUTH_PASSWORD:?AUTH_PASSWORD missing in .env}"
  : "${AUTH_NAME:?AUTH_NAME missing in .env}"

  run_psql \
    "$AUTH_HOST" \
    "$AUTH_PORT" \
    "$AUTH_USER" \
    "$AUTH_NAME" \
    "$AUTH_PASSWORD" \
    "$AUTH_SCHEMA"
fi

if [[ "$INIT_ZOO" == true ]]; then
  : "${PG_HOST:?PG_HOST missing in .env}"
  : "${PG_PORT:=?PG_PORT missing in .env}}"
  : "${PG_USER:?PG_USER missing in .env}"
  : "${PG_PASSWORD:?PG_PASSWORD missing in .env}"
  : "${PG_NAME:?PG_NAME missing in .env}"

  run_psql \
    "$PG_HOST" \
    "$PG_PORT" \
    "$PG_USER" \
    "$PG_NAME" \
    "$PG_PASSWORD" \
    "$ZOO_SCHEMA"
fi

echo "Database initialization completed."