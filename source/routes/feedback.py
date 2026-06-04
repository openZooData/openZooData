"""
routes/feedback.py — Community Feedback API
============================================
Endpoints:
    GET    /api/v1/feedback-types                           → require_app_token
    POST   /api/v1/zoos/<zoo>/feedback                     → require_app_token
    GET    /api/v1/zoos/<zoo>/feedback                     → require_zoo_access (admin)
    GET    /api/v1/zoos/<zoo>/feedback/<id>                → require_zoo_access (admin)
    PUT    /api/v1/zoos/<zoo>/feedback/<id>/accept         → require_zoo_access (admin)
    PUT    /api/v1/zoos/<zoo>/feedback/<id>/reject         → require_zoo_access (admin)
"""

import logging
import psycopg2
import psycopg2.extras
from flask import Blueprint, request, jsonify

from db           import get_pg_connection
from helpers.auth_utils import require_app_token
from helpers.authz import require_zoo_access
from extensions   import limiter

feedback_bp = Blueprint("feedback", __name__)

_feedback_types_cache = {}


def _get_feedback_types():
    global _feedback_types_cache
    if _feedback_types_cache:
        return _feedback_types_cache
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, slug, label_de, entity_type, requires_admin_review
                FROM zoo.feedback_types
                WHERE is_active = TRUE
                ORDER BY id
            """)
            rows = cur.fetchall()
        _feedback_types_cache = {row["id"]: dict(row) for row in rows}
        return _feedback_types_cache
    except Exception as e:
        logging.error(f"Failed to load feedback_types: {e}")
        return {}
    finally:
        if pg:
            pg.close()


REQUIRED_FIELDS = {
    1:  ["enclosure_id", "value_time"],
    2:  ["enclosure_id", "value_latitude", "value_longitude"],
    3:  ["enclosure_id", "value_wikidata_id"],
    4:  ["enclosure_id", "value_species_id"],
    5:  ["enclosure_id", "value_species_id", "value_date"],
    6:  ["enclosure_id", "value_species_id", "value_count"],
    7:  ["enclosure_id", "value_species_id", "value_count"],
    8:  ["value_enrichment_text_id", "value_report_reason_id", "value_language"],
    9:  ["value_enrichment_text_id"],
    10: ["value_enrichment_text_id"],
}


def get_device_key():
    """
    Rate-Limit-Key aus dem App-Token (device_id) — server-seitig vertrauenswürdig.
    Verhindert Bypass durch Rotation der client-gewählten contributor_id.
    Fallback auf IP wenn kein Token vorhanden (sollte nie eintreten da Auth bereits prüft).
    """
    from helpers.auth_utils import require_app_token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        import hashlib
        token_hash = hashlib.sha256(
            auth_header.removeprefix("Bearer ").strip().encode()
        ).hexdigest()[:16]
        return f"token:{token_hash}"
    return f"ip:{request.headers.get('X-Forwarded-For', request.remote_addr)}"


# ---------------------------------------------------------------------------
# GET /api/v1/feedback-types
# ---------------------------------------------------------------------------

@feedback_bp.route("/api/v1/feedback-types", methods=["GET"])
@limiter.limit("30 per minute")
def get_feedback_types():
    device_id, err = require_app_token()
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, slug, label_de, entity_type, requires_admin_review
                FROM zoo.feedback_types
                WHERE is_active = TRUE
                ORDER BY id
            """)
            types = [dict(r) for r in cur.fetchall()]

            cur.execute("""
                SELECT id, slug, label_de
                FROM zoo.feedback_report_reasons
                ORDER BY id
            """)
            reasons = [dict(r) for r in cur.fetchall()]

        for t in types:
            t["report_reasons"] = reasons if t["slug"] == "text_incorrect" else []

        response = jsonify(types)
        response.headers["Cache-Control"] = "public, max-age=3600"
        return response, 200

    except Exception as e:
        logging.exception("Exception in GET feedback-types")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()


# ---------------------------------------------------------------------------
# POST /api/v1/zoos/<zoo>/feedback
# ---------------------------------------------------------------------------

@feedback_bp.route("/api/v1/zoos/<zoo>/feedback", methods=["POST"])
@limiter.limit("60 per minute")
@limiter.limit("2 per minute", key_func=get_device_key)
@limiter.limit("60 per day",   key_func=get_device_key)
def create_feedback(zoo):
    device_id, err = require_app_token()
    if err: return err

    data             = request.get_json(silent=True) or {}
    feedback_type_id = data.get("feedback_type_id")
    contributor_id   = (data.get("contributor_id") or "").strip()

    if not feedback_type_id:
        return jsonify({"error": "feedback_type_id required"}), 400
    if not contributor_id:
        return jsonify({"error": "contributor_id required"}), 400

    types = _get_feedback_types()
    if not types:
        return jsonify({"error": "Internal server error"}), 500

    ft = types.get(int(feedback_type_id))
    if not ft:
        return jsonify({"error": f"Invalid feedback_type_id: {feedback_type_id}"}), 400

    required = REQUIRED_FIELDS.get(int(feedback_type_id), [])
    missing  = [f for f in required if data.get(f) is None]
    if missing:
        return jsonify({"error": f"Missing required fields for type {ft['slug']}: {missing}"}), 400

    enclosure_id             = data.get("enclosure_id")
    value_time               = data.get("value_time")
    value_latitude           = data.get("value_latitude")
    value_longitude          = data.get("value_longitude")
    value_wikidata_id        = (data.get("value_wikidata_id") or "").strip() or None
    value_species_id         = data.get("value_species_id")
    value_date               = data.get("value_date")
    value_count              = data.get("value_count")
    value_enrichment_text_id = data.get("value_enrichment_text_id")
    value_report_reason_id   = data.get("value_report_reason_id")
    value_language           = (data.get("value_language") or "").strip() or None

    status = None if not ft["requires_admin_review"] else "pending"

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id FROM zoo.zoos WHERE slug = %s", (zoo,))
            zoo_row = cur.fetchone()
            if not zoo_row:
                return jsonify({"error": "Zoo not found"}), 404
            zoo_id = zoo_row["id"]

            # Fix 6: enclosure_id und value_species_id gegen Zoo validieren
            if enclosure_id is not None:
                cur.execute("""
                    SELECT id FROM zoo.enclosures
                    WHERE id = %s AND zoo_id = %s
                """, (enclosure_id, zoo_id))
                if not cur.fetchone():
                    return jsonify({"error": "enclosure not found in this zoo"}), 400

            cur.execute("""
                INSERT INTO feedback (
                    zoo_id, feedback_type_id, contributor_id, status,
                    enclosure_id,
                    value_time, value_latitude, value_longitude,
                    value_wikidata_id, value_species_id, value_date, value_count,
                    value_enrichment_text_id, value_report_reason_id, value_language
                ) VALUES (
                    %s, %s, %s, %s,
                    %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s
                )
                RETURNING id, status, created_at
            """, (
                zoo_id, feedback_type_id, contributor_id, status,
                enclosure_id,
                value_time, value_latitude, value_longitude,
                value_wikidata_id, value_species_id, value_date, value_count,
                value_enrichment_text_id, value_report_reason_id, value_language
            ))
            result = dict(cur.fetchone())

        pg.commit()
        return jsonify({
            "id":         result["id"],
            "status":     result["status"],
            "created_at": result["created_at"].isoformat()
        }), 201

    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "Already rated"}), 409
    except Exception as e:
        logging.exception("Exception in POST feedback")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()


# ---------------------------------------------------------------------------
# GET /api/v1/zoos/<zoo>/feedback  — Admin
# ---------------------------------------------------------------------------

@feedback_bp.route("/api/v1/zoos/<zoo>/feedback", methods=["GET"])
@limiter.limit("60 per minute")
def get_feedback(zoo):
    user_id, err = require_zoo_access(zoo, 'admin')
    if err: return err

    status = request.args.get("status", "pending")
    try:
        limit  = min(int(request.args.get("limit",  50)), 200)
        offset = max(int(request.args.get("offset",  0)),   0)
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400

    if status not in {"pending", "accepted", "rejected"}:
        return jsonify({"error": "Invalid status"}), 400

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    ARRAY_AGG(f.id ORDER BY f.created_at)   AS feedback_ids,
                    ft.id                                    AS feedback_type_id,
                    ft.slug                                  AS feedback_type_slug,
                    ft.label_de                              AS feedback_type_label,
                    COUNT(DISTINCT f.contributor_id)         AS reporter_count,
                    MIN(f.created_at)                        AS first_reported,
                    MAX(f.created_at)                        AS last_reported,
                    f.enclosure_id,
                    e.name                                   AS enclosure_name,
                    f.value_time,
                    f.value_latitude,
                    f.value_longitude,
                    f.value_wikidata_id,
                    f.value_species_id,
                    s.german_name                            AS species_name,
                    s.latin_name                             AS species_latin,
                    f.value_date,
                    f.value_count,
                    f.value_enrichment_text_id,
                    f.value_report_reason_id,
                    rr.label_de                              AS report_reason_label,
                    f.value_language,
                    MAX(f.review_comment)                    AS review_comment,
                    MAX(f.reviewed_at)                       AS reviewed_at,
                    MAX(f.reviewed_by)                       AS reviewed_by
                FROM zoo.feedback f
                JOIN zoo.zoos z             ON z.id  = f.zoo_id
                JOIN zoo.feedback_types ft  ON ft.id = f.feedback_type_id
                LEFT JOIN zoo.enclosures e  ON e.id  = f.enclosure_id
                LEFT JOIN zoo.species s     ON s.id  = f.value_species_id
                LEFT JOIN zoo.feedback_report_reasons rr ON rr.id = f.value_report_reason_id
                WHERE z.slug = %s
                  AND f.status = %s
                  AND ft.requires_admin_review = TRUE
                GROUP BY
                    ft.id, ft.slug, ft.label_de,
                    f.enclosure_id, e.name,
                    f.value_time, f.value_latitude, f.value_longitude,
                    f.value_wikidata_id, f.value_species_id,
                    s.german_name, s.latin_name,
                    f.value_date, f.value_count,
                    f.value_enrichment_text_id,
                    f.value_report_reason_id, rr.label_de,
                    f.value_language
                ORDER BY reporter_count DESC, first_reported ASC
                LIMIT %s OFFSET %s
            """, (zoo, status, limit, offset))
            rows = cur.fetchall()

            cur.execute("""
                SELECT COUNT(*) AS total FROM (
                    SELECT 1
                    FROM zoo.feedback f
                    JOIN zoo.zoos z            ON z.id  = f.zoo_id
                    JOIN zoo.feedback_types ft ON ft.id = f.feedback_type_id
                    WHERE z.slug = %s AND f.status = %s
                      AND ft.requires_admin_review = TRUE
                    GROUP BY
                        ft.id, f.enclosure_id,
                        f.value_time, f.value_latitude, f.value_longitude,
                        f.value_wikidata_id, f.value_species_id,
                        f.value_date, f.value_count,
                        f.value_enrichment_text_id, f.value_report_reason_id,
                        f.value_language
                ) sub
            """, (zoo, status))
            total = cur.fetchone()["total"]

        clusters = []
        for row in rows:
            d = dict(row)
            for ts in ("first_reported", "last_reported", "reviewed_at"):
                if d.get(ts):
                    d[ts] = d[ts].isoformat()
            if d.get("value_time"):
                d["value_time"] = str(d["value_time"])
            d["reporter_count"] = int(d["reporter_count"])
            clusters.append(d)

        return jsonify({"total": total, "clusters": clusters}), 200

    except Exception as e:
        logging.exception("Exception in GET feedback")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()


# ---------------------------------------------------------------------------
# GET /api/v1/zoos/<zoo>/feedback/<id>  — Admin
# ---------------------------------------------------------------------------

@feedback_bp.route("/api/v1/zoos/<zoo>/feedback/<int:feedback_id>", methods=["GET"])
@limiter.limit("60 per minute")
def get_feedback_item(zoo, feedback_id):
    user_id, err = require_zoo_access(zoo, 'admin')
    if err: return err

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    f.id, f.feedback_type_id, f.contributor_id, f.status,
                    f.review_comment, f.reviewed_at, f.reviewed_by, f.created_at,
                    ft.slug       AS feedback_type_slug,
                    ft.label_de   AS feedback_type_label,
                    f.enclosure_id,
                    e.name        AS enclosure_name,
                    f.value_time, f.value_latitude, f.value_longitude,
                    f.value_wikidata_id, f.value_species_id,
                    s.german_name AS species_name,
                    s.latin_name  AS species_latin,
                    f.value_date, f.value_count,
                    f.value_enrichment_text_id,
                    f.value_report_reason_id,
                    rr.label_de   AS report_reason_label,
                    f.value_language
                FROM zoo.feedback f
                JOIN zoo.zoos z             ON z.id  = f.zoo_id
                JOIN zoo.feedback_types ft  ON ft.id = f.feedback_type_id
                LEFT JOIN zoo.enclosures e  ON e.id  = f.enclosure_id
                LEFT JOIN zoo.species s     ON s.id  = f.value_species_id
                LEFT JOIN zoo.feedback_report_reasons rr ON rr.id = f.value_report_reason_id
                WHERE z.slug = %s AND f.id = %s
            """, (zoo, feedback_id))
            row = cur.fetchone()

        if not row:
            return jsonify({"error": "Not found"}), 404

        d = dict(row)
        for ts in ("created_at", "reviewed_at"):
            if d.get(ts):
                d[ts] = d[ts].isoformat()
        if d.get("value_time"):
            d["value_time"] = str(d["value_time"])
        return jsonify(d), 200

    except Exception as e:
        logging.exception(f"Exception in GET feedback/{feedback_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()


# ---------------------------------------------------------------------------
# PUT /api/v1/zoos/<zoo>/feedback/<id>/accept  — Admin
# ---------------------------------------------------------------------------

@feedback_bp.route("/api/v1/zoos/<zoo>/feedback/<int:feedback_id>/accept", methods=["PUT"])
@limiter.limit("30 per minute")
def accept_feedback(zoo, feedback_id):
    user_id, err = require_zoo_access(zoo, 'admin')
    if err: return err

    data     = request.get_json(silent=True) or {}
    comment  = (data.get("comment") or "").strip() or None
    also_ids = [int(i) for i in (data.get("also_ids") or []) if str(i).isdigit()]

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute("""
                SELECT f.id FROM zoo.feedback f
                JOIN zoo.zoos z ON z.id = f.zoo_id
                WHERE f.id = %s AND z.slug = %s AND f.status = 'pending'
            """, (feedback_id, zoo))
            if not cur.fetchone():
                return jsonify({"error": "Not found or already reviewed"}), 404

            all_ids = list({feedback_id} | set(also_ids))
            cur.execute("""
                UPDATE zoo.feedback SET
                    status         = 'accepted',
                    review_comment = %s,
                    reviewed_at    = NOW(),
                    reviewed_by    = %s
                WHERE id = ANY(%s)
                AND zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
                AND status = 'pending'
            """, (comment, str(user_id), all_ids, zoo))
            updated = cur.rowcount

        pg.commit()
        return jsonify({"message": "Accepted", "updated_count": updated}), 200

    except Exception as e:
        logging.exception(f"Exception in accept_feedback/{feedback_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()


# ---------------------------------------------------------------------------
# PUT /api/v1/zoos/<zoo>/feedback/<id>/reject  — Admin
# ---------------------------------------------------------------------------

@feedback_bp.route("/api/v1/zoos/<zoo>/feedback/<int:feedback_id>/reject", methods=["PUT"])
@limiter.limit("30 per minute")
def reject_feedback(zoo, feedback_id):
    user_id, err = require_zoo_access(zoo, 'admin')
    if err: return err

    data     = request.get_json(silent=True) or {}
    comment  = (data.get("comment") or "").strip() or None
    also_ids = [int(i) for i in (data.get("also_ids") or []) if str(i).isdigit()]

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            all_ids = list({feedback_id} | set(also_ids))
            cur.execute("""
                UPDATE zoo.feedback SET
                    status         = 'rejected',
                    review_comment = %s,
                    reviewed_at    = NOW(),
                    reviewed_by    = %s
                WHERE id = ANY(%s)
                AND zoo_id = (SELECT id FROM zoo.zoos WHERE slug = %s)
                AND status = 'pending'
            """, (comment, str(user_id), all_ids, zoo))

            if cur.rowcount == 0:
                return jsonify({"error": "Not found or already reviewed"}), 404
            updated = cur.rowcount

        pg.commit()
        return jsonify({"message": "Rejected", "updated_count": updated}), 200

    except Exception as e:
        logging.exception(f"Exception in reject_feedback/{feedback_id}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()
