"""
routes/qr.py — QR-Code-Seite für den öffentlichen RSS-Feed

GET /qr/<zoo>
  → HTML-Seite mit QR-Code für https://api.openzoodata.org/feed/<zoo>
  → Kein Auth nötig — öffentlich zugänglich
  → Gedacht für Aushang im Zoo oder Einbettung in Zoo-Website
"""

import io
import base64
import logging

import qrcode
from flask import Blueprint, jsonify, render_template_string
from helpers.coordinates import is_valid_slug
from db import get_pg_connection

qr_bp = Blueprint("qr", __name__)

QR_PAGE = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ zoo_name }} — ZooGuide</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f5f5f0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 2rem;
    }

    .card {
      background: white;
      border-radius: 24px;
      padding: 3rem 2.5rem;
      max-width: 420px;
      width: 100%;
      text-align: center;
      box-shadow: 0 4px 24px rgba(0,0,0,0.08);
    }

    .logo {
      font-size: 2.5rem;
      margin-bottom: 0.5rem;
    }

    h1 {
      font-size: 1.5rem;
      font-weight: 700;
      color: #1a1a1a;
      margin-bottom: 0.25rem;
    }

    .subtitle {
      font-size: 0.95rem;
      color: #666;
      margin-bottom: 2rem;
    }

    .qr-container {
      background: white;
      border-radius: 16px;
      padding: 1rem;
      display: inline-block;
      margin-bottom: 2rem;
      border: 1px solid #eee;
    }

    .qr-container img {
      display: block;
      width: 240px;
      height: 240px;
    }

    .instruction {
      font-size: 1rem;
      font-weight: 600;
      color: #1a1a1a;
      margin-bottom: 0.5rem;
    }

    .hint {
      font-size: 0.85rem;
      color: #888;
      margin-bottom: 2rem;
      line-height: 1.5;
    }

    .feed-url {
      font-size: 0.75rem;
      color: #aaa;
      word-break: break-all;
      font-family: monospace;
    }

    .badge {
      display: inline-block;
      background: #34C759;
      color: white;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.25rem 0.75rem;
      border-radius: 20px;
      margin-bottom: 1.5rem;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🦁</div>
    <h1>{{ zoo_name }}</h1>
    <p class="subtitle">ZooGuide — Entdecke den Zoo</p>

    <span class="badge">openZooData</span>

    <div class="qr-container">
      <img src="data:image/png;base64,{{ qr_b64 }}" alt="QR-Code für {{ zoo_name }}">
    </div>

    <p class="instruction">QR-Code scannen</p>
    <p class="hint">
      Scanne den Code mit deiner Kamera-App oder dem QR-Scanner<br>
      um den {{ zoo_name }} in der ZooGuide-App zu öffnen.
    </p>

    <p class="feed-url">{{ feed_url }}</p>
  </div>
</body>
</html>"""


@qr_bp.route("/qr/<zoo>", methods=["GET"])
def zoo_qr(zoo):
    """QR-Code-Seite für den öffentlichen RSS-Feed eines Zoos."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute("""
                SELECT name FROM zoo.zoos
                WHERE slug = %s AND is_active = TRUE
            """, (zoo,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Zoo not found"}), 404
            zoo_name = row[0]
    except Exception:
        logging.exception(f"Exception in GET /qr/{zoo}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()

    # Feed-URL
    from flask import request
    base_url = request.host_url.rstrip("/")
    feed_url = f"{base_url}/feed/{zoo}"

    # QR-Code generieren
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(feed_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    qr_b64 = base64.b64encode(buf.read()).decode("utf-8")

    return render_template_string(
        QR_PAGE,
        zoo_name=zoo_name,
        feed_url=feed_url,
        qr_b64=qr_b64,
    )
