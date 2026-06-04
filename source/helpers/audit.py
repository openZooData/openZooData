import logging
import uuid
import json
from flask import request

# helpers/audit.py — Audit-Logging (Migration v7)
#
# Verwendung:
#   from helpers.audit import log_action
#   log_action("login_success", actor_user_id=user_id)
#   log_action("login_failed", actor_email=email, success=False, error_code="wrong_password")


def _get_actor_ip() -> str | None:
    try:
        return request.remote_addr
    except RuntimeError:
        return None


def _get_request_id() -> str | None:
    try:
        return request.headers.get("X-Request-ID") or str(uuid.uuid4())
    except RuntimeError:
        return None


def log_action(action: str, *, actor_user_id=None, actor_email=None,
               tenant_id=None, zoo_id=None, target_type=None, target_id=None,
               correlation_id=None, success=True, error_code=None, details=None):
    """
    Schreibt einen Eintrag in auth.audit_log.
    Schlägt nie fehl — Fehler werden nur geloggt.
    """
    from db import get_auth_connection
    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO auth.audit_log (
                    action, success, error_code,
                    actor_user_id, actor_email, actor_ip,
                    tenant_id, zoo_id,
                    target_type, target_id,
                    request_id, correlation_id, details
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                action, success, error_code,
                actor_user_id, actor_email, _get_actor_ip(),
                tenant_id, zoo_id,
                target_type, target_id,
                _get_request_id(), correlation_id,
                json.dumps(details) if details else None,
            ))
        conn.commit()
    except Exception:
        logging.exception(f"audit.log_action failed for action='{action}'")
    finally:
        if conn:
            conn.close()


def anonymize_old_ips(days: int = 30) -> int:
    """DSGVO: IP nach `days` Tagen anonymisieren (IPv4 letztes Oktett, IPv6 /48)."""
    from db import get_auth_connection
    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE auth.audit_log SET actor_ip = CASE
                    WHEN actor_ip LIKE '%%.%%.%%.%%'
                        THEN regexp_replace(actor_ip, '\\.\\d+$', '.0')
                    WHEN actor_ip LIKE '%%:%%'
                        THEN regexp_replace(actor_ip,
                            '^([0-9a-fA-F:]+:[0-9a-fA-F]+:[0-9a-fA-F]+):.*$', '\\1::')
                    ELSE NULL
                END
                WHERE actor_ip IS NOT NULL
                  AND created_at < NOW() - (%s * INTERVAL '1 day')
            """, (days,))
            count = cur.rowcount
        conn.commit()
        logging.info(f"audit: {count} IPs anonymisiert")
        return count
    except Exception:
        logging.exception("audit.anonymize_old_ips failed")
        return 0
    finally:
        if conn:
            conn.close()


def archive_old_entries(months: int = 24) -> int:
    """
    Verschiebt Einträge älter als `months` Monate nach auth.audit_archive.
    Verwendet explizite Spaltenliste (Prio B correction_v1.md §8).
    """
    from db import get_auth_connection
    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                WITH moved AS (
                    DELETE FROM auth.audit_log
                    WHERE created_at < NOW() - (%s * INTERVAL '1 month')
                    RETURNING
                        id, action, success, error_code,
                        actor_user_id, actor_email, actor_ip, user_agent_hash,
                        tenant_id, zoo_id, target_type, target_id,
                        request_id, correlation_id, details, created_at
                )
                INSERT INTO auth.audit_archive (
                    id, action, success, error_code,
                    actor_user_id, actor_email, actor_ip, user_agent_hash,
                    tenant_id, zoo_id, target_type, target_id,
                    request_id, correlation_id, details, created_at
                )
                SELECT
                    id, action, success, error_code,
                    actor_user_id, actor_email, actor_ip, user_agent_hash,
                    tenant_id, zoo_id, target_type, target_id,
                    request_id, correlation_id, details, created_at
                FROM moved
            """, (months,))
            count = cur.rowcount
        conn.commit()
        logging.info(f"audit: {count} Einträge archiviert")
        return count
    except Exception:
        logging.exception("audit.archive_old_entries failed")
        return 0
    finally:
        if conn:
            conn.close()
