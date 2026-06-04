import os
import psycopg2


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_pg_connection():
    return psycopg2.connect(
        host=_require_env("PG_HOST"),
        port=os.getenv("PG_PORT", "5432"),
        user=_require_env("PG_USER"),
        password=_require_env("PG_PASSWORD"),
        dbname=_require_env("PG_NAME"),
        options="-c search_path=zoo,public",
    )


def get_auth_connection():
    return psycopg2.connect(
        host=_require_env("AUTH_HOST"),
        port=os.getenv("AUTH_PORT", "5432"),
        user=_require_env("AUTH_USER"),
        password=_require_env("AUTH_PASSWORD"),
        dbname=_require_env("AUTH_NAME"),
    )
