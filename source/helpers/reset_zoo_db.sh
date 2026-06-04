#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

ENV_FILE="$ROOT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: .env not found: $ENV_FILE"
    exit 1
fi

set -a
source "$ENV_FILE"
set +a
: "${PG_HOST:?PG_HOST missing in .env}"
: "${PG_PORT:?PG_PORT missing in .env}"
: "${PG_USER:?PG_USER missing in .env}"
: "${PG_PASSWORD:?PG_PASSWORD missing in .env}"
: "${PG_NAME:?PG_NAME missing in .env}"

echo "WARNING!"
echo "This will delete schemas:"
echo "  - auth"
echo "  - community"
echo "  - zoo"
echo
echo "Database: $PG_NAME"
echo "Host:     $PG_HOST"
echo

read -rp "Continue? (yes/no): " answer

if [[ "$answer" != "yes" ]]; then
    echo "Aborted."
    exit 0
fi

PGPASSWORD="$PG_PASSWORD" psql \
    -h "$PG_HOST" \
    -p "$PG_PORT" \
    -U "$PG_USER" \
    -d "$PG_NAME" \
    -v ON_ERROR_STOP=1 \
    -c "

        DROP SCHEMA IF EXISTS auth CASCADE;
        DROP SCHEMA IF EXISTS community CASCADE;
        DROP SCHEMA IF EXISTS zoo CASCADE;

    "
echo
echo "Schemas removed successfully."