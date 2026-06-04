import os
import psycopg2


def get_pg_connection():
    return psycopg2.connect(
        host=os.getenv("PG_HOST"),
        port=os.getenv("PG_PORT", "5432"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        dbname=os.getenv("PG_DATABASE", "zooguide"),
    )


def get_auth_connection():
    return psycopg2.connect(
        host=os.getenv("AUTH_HOST"),
        port=os.getenv("AUTH_PORT", "5432"),
        user=os.getenv("AUTH_USER"),
        password=os.getenv("AUTH_PASSWORD"),
        dbname=os.getenv("AUTH_NAME", "zooguide_auth"),
    )
