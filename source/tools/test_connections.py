#!/usr/bin/env python3
"""
test_connections.py
-------------------
Testet alle Datenbankverbindungen aus .env
Aufruf: python3 tools/test_connections.py
"""

import sys
from pathlib import Path


def load_env():
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


def require_env(name):
    value = env.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


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


def test_pg_auth():
    import psycopg2

    conn = psycopg2.connect(
        host=require_env("AUTH_HOST"),
        user=require_env("AUTH_USER"),
        password=require_env("AUTH_PASSWORD"),
        dbname=require_env("AUTH_NAME"),
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


def test_pg_zooguide():
    import psycopg2

    conn = psycopg2.connect(
        host=require_env("PG_HOST"),
        user=require_env("PG_USER"),
        password=require_env("PG_PASSWORD"),
        dbname=require_env("PG_DATABASE"),
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


check("PostgreSQL Auth DB", test_pg_auth)
check("PostgreSQL ZooGuide", test_pg_zooguide)

print(f"\n{'=' * 40}")
print(f"Ergebnis: {ok} OK, {fail} Fehler")
if fail > 0:
    sys.exit(1)
