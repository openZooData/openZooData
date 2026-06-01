#!/usr/bin/env python3
"""
test_connections.py
-------------------
Testet alle Datenbankverbindungen aus .env
Aufruf: python3 tools/test_connections.py
"""

import os
import sys
from pathlib import Path


def load_env():
    """Minimaler .env-Loader ohne externe Abhängigkeit."""
    env = {}
    path = Path(".env")
    if not path.exists():
        path = Path.home() / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


env = load_env()

ok = 0
fail = 0


def check(label, fn):
    global ok, fail
    print(f"\n[{label}]")
    try:
        fn()
        print("  ✓ Verbindung OK")
        ok += 1
    except Exception as e:
        print(f"  ✗ Fehler: {e}")
        fail += 1


# ------------------------------------------------------
# PostgreSQL Auth DB
# ------------------------------------------------------
def test_pg_auth():
    import psycopg2

    conn = psycopg2.connect(
        host=env.get("AUTH_HOST"),
        user=env.get("AUTH_USER"),
        password=env.get("AUTH_PASSWORD"),
        dbname=env.get("AUTH_NAME", "zooguide_auth"),
        port=int(env.get("AUTH_PORT", "5432")),
    )
    cur = conn.cursor()
    cur.execute("SELECT current_database()")
    print(f"  Datenbank: {cur.fetchone()[0]}")
    for table in ("users", "user_roles", "refresh_tokens", "app_tokens"):
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"  {table}: {cur.fetchone()[0]} Einträge")
    cur.close()
    conn.close()


check("PostgreSQL Auth DB", test_pg_auth)


# ------------------------------------------------------
# PostgreSQL ZooGuide
# ------------------------------------------------------
def test_pg_zooguide():
    import psycopg2

    conn = psycopg2.connect(
        host=env.get("PG_HOST"),
        user=env.get("PG_USER"),
        password=env.get("PG_PASSWORD"),
        dbname=env.get("PG_NAME", "zooguide"),
        port=int(env.get("PG_PORT", "5432")),
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


check("PostgreSQL ZooGuide", test_pg_zooguide)


# ------------------------------------------------------
# Ergebnis
# ------------------------------------------------------
print(f"\n{'=' * 40}")
print(f"Ergebnis: {ok} OK, {fail} Fehler")
if fail > 0:
    sys.exit(1)
