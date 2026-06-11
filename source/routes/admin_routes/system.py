import logging
import psycopg2
import psycopg2.extras
from flask import Blueprint, jsonify, request
from db import get_pg_connection, get_auth_connection
from extensions import limiter
from helpers.authz import require_super_admin
from helpers.coordinates import is_valid_slug
from routes.admin_routes.helpers import _can_review_proposals

admin_system_bp = Blueprint("admin_system_bp", __name__)

@admin_system_bp.route("/api/v1/admin/settings", methods=["GET"])
@limiter.limit("60 per minute")
def get_settings():
    """System-Settings lesen. Nur super_admin."""
    actor_id, err = require_super_admin()
    if err: return err

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT key, value, value_type, updated_at
                FROM auth.system_settings ORDER BY key
            """)
            return jsonify([dict(r) for r in cur.fetchall()]), 200

    except Exception:
        logging.exception("Exception in GET /admin/settings")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@admin_system_bp.route("/api/v1/admin/settings/<key>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_setting(key):
    """
    System-Setting aktualisieren. Nur super_admin.
    Fix 8: Wert wird nicht ins Audit-Log geschrieben.
    """
    actor_id, err = require_super_admin()
    if err: return err

    data  = request.get_json(silent=True) or {}
    value = data.get("value")
    if value is None:
        return jsonify({"error": "value required"}), 400

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE auth.system_settings
                SET value = %s, updated_by = %s, updated_at = NOW()
                WHERE key = %s RETURNING key
            """, (str(value), actor_id, key))
            if not cur.fetchone():
                return jsonify({"error": "Setting not found"}), 404
        conn.commit()

        # Fix 8: Wert NICHT loggen — könnte sensitiv sein
        log_action("system_setting_updated", actor_user_id=actor_id,
                   details={"key": key, "changed": True})
        return jsonify({"message": f"Setting '{key}' updated"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in PUT /admin/settings/{key}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


# ── B9: Audit-Log ─────────────────────────────────────────────────────────────


@admin_system_bp.route("/api/v1/admin/audit", methods=["GET"])
@limiter.limit("30 per minute")
def get_audit_log():
    """
    Audit-Log lesen. Nur super_admin.
    Fix 9: limit-Parameter wird validiert.
    """
    actor_id, err = require_super_admin()
    if err: return err

    # Fix 9: saubere Validierung
    try:
        limit = int(request.args.get("limit", 100))
    except ValueError:
        return jsonify({"error": "limit must be an integer"}), 400
    limit = max(1, min(limit, 200))

    action    = request.args.get("action")
    from_dt   = request.args.get("from")
    to_dt     = request.args.get("to")

    # Fix v2.5: Integer- und Datum-Filter validieren
    def _int_param(name):
        val = request.args.get(name)
        if val is None:
            return None, None
        try:
            return int(val), None
        except ValueError:
            return None, f"{name} must be an integer"

    user_id,   user_err   = _int_param("user_id")
    zoo_id,    zoo_err    = _int_param("zoo_id")
    tenant_id, tenant_err = _int_param("tenant_id")
    for err_msg in (user_err, zoo_err, tenant_err):
        if err_msg:
            return jsonify({"error": err_msg}), 400

    from datetime import datetime as _dt
    for dt_val, dt_name in ((from_dt, "from"), (to_dt, "to")):
        if dt_val:
            try:
                _dt.fromisoformat(dt_val.replace("Z", "+00:00"))
            except ValueError:
                return jsonify({"error": f"{dt_name} must be ISO 8601 datetime"}), 400

    conditions, params = [], []
    if action:
        conditions.append("action = %s");        params.append(action)
    if user_id is not None:
        conditions.append("actor_user_id = %s"); params.append(user_id)
    if zoo_id is not None:
        conditions.append("zoo_id = %s");        params.append(zoo_id)
    if tenant_id is not None:
        conditions.append("tenant_id = %s");     params.append(tenant_id)
    if from_dt:
        conditions.append("created_at >= %s");   params.append(from_dt)
    if to_dt:
        conditions.append("created_at <= %s");   params.append(to_dt)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"""
                SELECT id, action, success, error_code,
                       actor_user_id, actor_email,
                       tenant_id, zoo_id,
                       target_type, target_id,
                       details, created_at
                FROM auth.audit_log
                {where}
                ORDER BY created_at DESC
                LIMIT %s
            """, params)
            return jsonify([dict(r) for r in cur.fetchall()]), 200

    except Exception:
        logging.exception("Exception in GET /admin/audit")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


# ── B10: Species-Proposals ────────────────────────────────────────────────────


@admin_system_bp.route("/api/v1/admin/proposals", methods=["GET"])
@limiter.limit("60 per minute")
def list_proposals():
    """Species-Proposals. super_admin oder moderator.
    Hinweis: Moderator ist aktuell global — keine Zoo-/Tenant-Einschränkung.
    Zoo-spezifische Moderation kommt in einer späteren Version."""
    actor_id = get_user_id_from_token()
    if not actor_id:
        return jsonify({"error": "Unauthorized"}), 401
    if not _can_review_proposals(actor_id):
        return jsonify({"error": "Unauthorized"}), 403

    status_filter  = request.args.get("status", "pending")
    valid_statuses = {"pending", "approved", "rejected",
                      "needs_more_info", "external_check_failed"}
    if status_filter not in valid_statuses:
        return jsonify({"error": "Invalid status"}), 400

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, status, wikidata_id, latin_name, german_name,
                       created_by_user_id, created_for_zoo_id,
                       created_at, reviewed_at, review_comment
                FROM auth.species_proposals
                WHERE status = %s
                ORDER BY created_at DESC
                LIMIT 100
            """, (status_filter,))
            return jsonify([dict(r) for r in cur.fetchall()]), 200

    except Exception:
        logging.exception("Exception in GET /admin/proposals")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@limiter.limit("30 per minute")
def approve_proposal(proposal_id):
    """Proposal genehmigen. super_admin oder moderator."""
    actor_id = get_user_id_from_token()
    if not actor_id:
        return jsonify({"error": "Unauthorized"}), 401
    if not _can_review_proposals(actor_id):
        return jsonify({"error": "Unauthorized"}), 403

    comment = (request.get_json(silent=True) or {}).get("comment", "")

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE auth.species_proposals
                SET status = 'approved',
                    reviewed_by_user_id = %s,
                    reviewed_at = NOW(),
                    review_comment = %s
                WHERE id = %s AND status = 'pending'
                RETURNING id
            """, (actor_id, comment or None, proposal_id))
            if not cur.fetchone():
                return jsonify({"error": "Proposal not found or not pending"}), 404
        conn.commit()

        log_action("species_confirmed", actor_user_id=actor_id,
                   target_type="species", target_id=proposal_id)
        return jsonify({"message": "Proposal approved"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in PUT /admin/proposals/{proposal_id}/approve")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()


@limiter.limit("30 per minute")
def reject_proposal(proposal_id):
    """Proposal ablehnen. super_admin oder moderator."""
    actor_id = get_user_id_from_token()
    if not actor_id:
        return jsonify({"error": "Unauthorized"}), 401
    if not _can_review_proposals(actor_id):
        return jsonify({"error": "Unauthorized"}), 403

    comment = (request.get_json(silent=True) or {}).get("comment", "")

    conn = None
    try:
        conn = get_auth_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE auth.species_proposals
                SET status = 'rejected',
                    reviewed_by_user_id = %s,
                    reviewed_at = NOW(),
                    review_comment = %s
                WHERE id = %s AND status = 'pending'
                RETURNING id
            """, (actor_id, comment or None, proposal_id))
            if not cur.fetchone():
                return jsonify({"error": "Proposal not found or not pending"}), 404
        conn.commit()

        log_action("species_rejected", actor_user_id=actor_id,
                   target_type="species", target_id=proposal_id)
        return jsonify({"message": "Proposal rejected"}), 200

    except Exception:
        if conn: conn.rollback()
        logging.exception(f"Exception in PUT /admin/proposals/{proposal_id}/reject")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if conn: conn.close()
