import os
import logging
import subprocess
import time
from flask import Blueprint, jsonify
from helpers.authz import require_zoo_access
from helpers.audit import log_action
from helpers.coordinates import is_valid_slug
from db import get_pg_connection
from extensions import limiter

publish_bp = Blueprint("publish", __name__)

# Advisory Lock class-ID — dedizierter Namespace für Publish-Locks.
# Verhindert Kollisionen mit anderen pg_advisory_lock-Nutzern im System.
# Prio B (correction_v1.md §5): zwei-Argument-Form pg_try_advisory_lock(classid, objid)
PUBLISH_LOCK_CLASS = 1001


@publish_bp.route("/api/v1/zoos/<zoo>/publish", methods=["POST"])
@limiter.limit("5 per minute")
def publish_zoo(zoo):
    """
    Startet den SQLite-Export für einen Zoo.

    Migration v7:
    - Autorisierung via can_access_zoo (publish-Aktion)
    - Publish-Berechtigung: super_admin, tenant_admin, zoo_admin
    - editor und viewer dürfen NICHT publishen
    - PostgreSQL Advisory Lock (2-Arg-Form) verhindert parallele Exporte
    - data_version wird AUSSCHLIESSLICH hier nach Erfolg erhöht
      (writer.py ruft _increment_data_version nicht mehr auf — Bugfix v7)
    - Synchroner Export mit Ergebnisprüfung
    - Fehler-Mail an Tenant-Admins + Superadmins
    """
    # Slug-Validierung VOR Auth
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    user_id, err = require_zoo_access(zoo, "publish")
    if err: return err

    conn = None
    zoo_id = None
    start_time = time.time()

    try:
        conn = get_pg_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM zoo.zoos WHERE slug = %s", (zoo,))
            zoo_row = cur.fetchone()
            if not zoo_row:
                return jsonify({"error": "Zoo not found"}), 404
            zoo_id = zoo_row[0]

            # Advisory Lock — 2-Arg-Form (classid=1001, objid=zoo_id)
            # verhindert Kollisionen mit anderen Lock-Nutzern
            cur.execute("SELECT pg_try_advisory_lock(%s, %s)", (PUBLISH_LOCK_CLASS, zoo_id))
            lock_acquired = cur.fetchone()[0]

            if not lock_acquired:
                return jsonify({
                    "error": "Export bereits aktiv für diesen Zoo. Bitte warten."
                }), 409

        conn.commit()

        log_action("publish_started", actor_user_id=user_id,
                   zoo_id=zoo_id, target_type="zoo", target_id=zoo_id,
                   details={"zoo_slug": zoo})

        try:
            script_path = os.path.join(os.path.dirname(__file__), "..", "tools", "export_sqlite.py")
            venv_python = os.path.join(os.path.expanduser("~"), "api", "venv", "bin", "python3")

            result = subprocess.run(
                [venv_python, script_path, "--zoo", zoo],
                capture_output=True,
                text=True,
                timeout=300
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if result.returncode != 0:
                error_msg = (result.stderr or result.stdout or "")[:500]
                logging.error(f"Export fehlgeschlagen für {zoo}: {error_msg}")

                log_action("publish_failed", actor_user_id=user_id,
                           zoo_id=zoo_id, target_type="zoo", target_id=zoo_id,
                           success=False, error_code="export_error",
                           details={"zoo_slug": zoo, "error": error_msg,
                                    "duration_ms": duration_ms})

                _notify_publish_failure(zoo, zoo_id, error_msg)

                return jsonify({
                    "error": "Export fehlgeschlagen",
                    "details": "Administratoren wurden benachrichtigt."
                }), 500

            # data_version NUR HIER erhöhen — writer.py macht das nicht mehr
            new_version = None
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE zoo.zoos
                    SET data_version = COALESCE(data_version, 0) + 1
                    WHERE slug = %s
                    RETURNING data_version
                """, (zoo,))
                row = cur.fetchone()
                new_version = row[0] if row else None
            conn.commit()

            log_action("publish_success", actor_user_id=user_id,
                       zoo_id=zoo_id, target_type="zoo", target_id=zoo_id,
                       details={"zoo_slug": zoo, "duration_ms": duration_ms,
                                "data_version": new_version})

            return jsonify({
                "message":      f"Export für {zoo} erfolgreich",
                "data_version": new_version,
                "duration_ms":  duration_ms,
            }), 200

        finally:
            # Advisory Lock IMMER freigeben
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s, %s)", (PUBLISH_LOCK_CLASS, zoo_id))
                conn.commit()
            except Exception:
                logging.exception(f"Advisory Lock konnte nicht freigegeben werden für {zoo}")

    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - start_time) * 1000)
        error_msg = f"Export Timeout nach {duration_ms}ms"
        logging.error(f"Export Timeout für {zoo} nach {duration_ms}ms")
        log_action("publish_failed", actor_user_id=user_id, zoo_id=zoo_id,
                   target_type="zoo", target_id=zoo_id,
                   success=False, error_code="timeout",
                   details={"zoo_slug": zoo, "error": error_msg,
                            "duration_ms": duration_ms})
        if zoo_id is not None:
            _notify_publish_failure(zoo, zoo_id, error_msg)
        return jsonify({
            "error": "Export Timeout",
            "details": "Administratoren wurden benachrichtigt." if zoo_id is not None else None
        }), 500

    except Exception:
        logging.exception(f"Exception in publish für {zoo}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn:
            conn.close()


def _get_publish_email_enabled(zoo_id: int) -> bool:
    """
    Liest publish_error_email_enabled mit Settings-Hierarchie:
    Zoo → Tenant → Global → Default (True)
    Prio C (correction_v1.md §12): Settings-Vererbung für Publish-Mail.
    """
    from db import get_auth_connection as _get_conn
    conn = None
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            # Zoo-Setting
            cur.execute("""
                SELECT value FROM auth.zoo_settings
                WHERE zoo_id = %s AND key = 'publish_error_email_enabled'
            """, (zoo_id,))
            row = cur.fetchone()
            if row:
                return row[0].lower() != "false"

            # Tenant-Setting
            cur.execute("""
                SELECT ts.value FROM auth.tenant_settings ts
                JOIN auth.tenant_zoos tz ON tz.tenant_id = ts.tenant_id
                WHERE tz.zoo_id = %s AND ts.key = 'publish_error_email_enabled'
                LIMIT 1
            """, (zoo_id,))
            row = cur.fetchone()
            if row:
                return row[0].lower() != "false"

            # Global Setting
            cur.execute("""
                SELECT value FROM auth.system_settings
                WHERE key = 'publish_error_email_enabled'
            """)
            row = cur.fetchone()
            if row:
                return row[0].lower() != "false"

    except Exception:
        logging.exception("_get_publish_email_enabled: Fehler beim Lesen")
    finally:
        if conn:
            conn.close()
    return True  # Default: aktiviert


def _notify_publish_failure(zoo_slug: str, zoo_id: int, error_msg: str) -> None:
    """
    Sendet E-Mail bei Publish-Fehler an Tenant-Admins + Superadmins.
    """
    if not _get_publish_email_enabled(zoo_id):
        return

    from db import get_auth_connection as _get_conn
    conn = None
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT u.email
                FROM auth.users u
                JOIN auth.user_global_roles ugr ON ugr.user_id = u.id
                WHERE ugr.role = 'super_admin' AND u.is_active = TRUE

                UNION

                SELECT DISTINCT u.email
                FROM auth.users u
                JOIN auth.user_tenant_roles utr ON utr.user_id = u.id
                JOIN auth.tenant_zoos tz ON tz.tenant_id = utr.tenant_id
                WHERE tz.zoo_id = %s
                  AND utr.role = 'tenant_admin'
                  AND utr.is_active = TRUE
                  AND u.is_active = TRUE
            """, (zoo_id,))
            recipients = [r[0] for r in cur.fetchall()]
    except Exception:
        logging.exception("_notify_publish_failure: Empfänger nicht ermittelbar")
        return
    finally:
        if conn:
            conn.close()

    if not recipients:
        return

    try:
        import smtplib
        from email.mime.text import MIMEText

        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER")
        smtp_pass = os.getenv("SMTP_PASSWORD")
        smtp_from = os.getenv("SMTP_FROM", "noreply@zooguide.app")

        if not smtp_host or not smtp_user:
            logging.warning("SMTP nicht konfiguriert — Publish-Fehler-Mail nicht versendet")
            return

        msg = MIMEText(
            f"Der Export für Zoo '{zoo_slug}' ist fehlgeschlagen.\n\n"
            f"Fehler:\n{error_msg}\n\nBitte prüfen Sie den Server-Log."
        )
        msg["Subject"] = f"[openZooData] Publish fehlgeschlagen: {zoo_slug}"
        msg["From"]    = smtp_from
        msg["To"]      = ", ".join(recipients)

        with smtplib.SMTP(smtp_host, smtp_port) as smtp:
            smtp.starttls()
            smtp.login(smtp_user, smtp_pass)
            smtp.sendmail(smtp_from, recipients, msg.as_string())

        logging.info(f"Publish-Fehler-Mail an {len(recipients)} Empfänger für {zoo_slug}")

    except Exception:
        logging.exception("_notify_publish_failure: E-Mail-Versand fehlgeschlagen")
