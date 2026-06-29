#!/usr/bin/env python3
"""
test_connections.py
-------------------
Testet die getrennten PostgreSQL-Datenbanken aus .env.

Aufruf:
    python3 source/tools/test_connections.py
"""

import os
import sys
from pathlib import Path

# Zentrale .env-Ladung -> os.environ (vereinheitlicht, siehe helpers/env_loader.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from helpers.env_loader import load_env
try:
    load_env()
except RuntimeError:
    pass  # Variablen evtl. schon vom Eltern-Prozess vererbt


import sys
from pathlib import Path

import psycopg2




def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


ok = 0
fail = 0


def check(label: str, fn) -> None:
    global ok, fail

    print(f"\n[{label}]")
    try:
        fn()
        print("  ✓ Verbindung OK")
        ok += 1
    except Exception as e:
        print(f"  ✗ Fehler: {e}")
        fail += 1


def test_pg_auth() -> None:
    conn = psycopg2.connect(
        host=require_env("AUTH_HOST"),
        user=require_env("AUTH_USER"),
        password=require_env("AUTH_PASSWORD"),
        dbname=require_env("AUTH_NAME"),
        port=int(os.environ.get("AUTH_PORT", "5432")),
        options="-c search_path=auth,public",
    )
    cur = conn.cursor()
    cur.execute("SELECT current_database()")
    print(f"  Datenbank: {cur.fetchone()[0]}")

    for table in ("users", "user_roles", "refresh_tokens", "app_tokens"):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"  {table}: {cur.fetchone()[0]} Einträge")

    cur.close()
    conn.close()


def test_pg_zooguide() -> None:
    conn = psycopg2.connect(
        host=require_env("PG_HOST"),
        user=require_env("PG_USER"),
        password=require_env("PG_PASSWORD"),
        dbname=require_env("PG_NAME"),
        port=int(os.environ.get("PG_PORT", "5432")),
        options="-c search_path=zoo,public",
    )
    cur = conn.cursor()
    cur.execute("SELECT current_database()")
    print(f"  Datenbank: {cur.fetchone()[0]}")

    for table in ("zoos", "species", "enclosures"):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"  {table}: {cur.fetchone()[0]} Einträge")

    cur.close()
    conn.close()


check("PostgreSQL Auth DB", test_pg_auth)
check("PostgreSQL ZooGuide", test_pg_zooguide)

print(f"\n{'=' * 40}")
print(f"Ergebnis: {ok} OK, {fail} Fehler")

if fail > 0:
    sys.exit(1)
