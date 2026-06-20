#!/usr/bin/env python3
"""
test_connections.py
-------------------
Testet die getrennten PostgreSQL-Datenbanken aus .env.

Aufruf:
    python3 source/tools/test_connections.py
"""

import sys
from pathlib import Path

import psycopg2


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}

    candidates = [
        Path(".env"),
        Path(__file__).resolve().parents[2] / ".env",
        Path.home() / ".env",
    ]

    env_path = next((p for p in candidates if p.exists()), None)
    if env_path is None:
        raise RuntimeError("No .env file found")

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")

    return env


env = load_env()


def require_env(name: str) -> str:
    value = env.get(name)
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


def test_pg_zooguide() -> None:
    conn = psycopg2.connect(
        host=require_env("PG_HOST"),
        user=require_env("PG_USER"),
        password=require_env("PG_PASSWORD"),
        dbname=require_env("PG_NAME"),
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
