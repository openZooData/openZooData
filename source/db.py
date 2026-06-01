import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
 
load_dotenv()
 
PG_CONFIG = {
    "host":     os.getenv("PG_HOST"),
    "user":     os.getenv("PG_USER"),
    "password": os.getenv("PG_PASSWORD"),
    "dbname":   os.getenv("PG_NAME", "zooguide"),
    "port":     int(os.getenv("PG_PORT", "5432")),
    "options":  "-c search_path=zoo,public"
}
 
AUTH_CONFIG = {
    "host":     os.getenv("AUTH_HOST"),
    "user":     os.getenv("AUTH_USER"),
    "password": os.getenv("AUTH_PASSWORD"),
    "dbname":   os.getenv("AUTH_NAME", "zooguide_auth"),
    "port":     int(os.getenv("AUTH_PORT", "5432")),
}
 
def get_pg_connection():
    return psycopg2.connect(**PG_CONFIG)
 
def get_auth_connection():
    return psycopg2.connect(**AUTH_CONFIG)
