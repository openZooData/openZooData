"""
routes/feed.py
--------------
Öffentlicher RSS-Feed-Endpoint für Zoo-Daten.

GET /feed/<zoo>  — kein API-Key nötig, öffentlich zugänglich.
GET /feed        — Liste aller Zoos auf diesem Server.

Der Feed folgt RSS 2.0 mit einem zoo:-Namespace und verwendet das
<enclosure>-Element (analog zu Podcast-Feeds) um auf die SQLite-Datei
zu verweisen.

Namespace: https://zooguide.app/rss/1.0
"""

import os
import logging
from datetime import datetime, timezone
from email.utils import formatdate
from flask import Blueprint, Response, jsonify
from helpers.coordinates import is_valid_slug
from db import get_pg_connection
from extensions import limiter

feed_bp = Blueprint("feed", __name__)

FEED_NS      = "https://zooguide.app/rss/1.0"
FEED_VERSION = "1.0"

# PUBLIC_BASE_URL aus .env — verhindert Host-Header-Poisoning in Feed-Links.
# Beispiel: PUBLIC_BASE_URL=https://api.zooguide.app
_PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
if not _PUBLIC_BASE_URL:
    raise RuntimeError(
        "PUBLIC_BASE_URL fehlt in .env. "
        "Beispiel: PUBLIC_BASE_URL=https://api.zooguide.app"
    )


def _base_url() -> str:
    """Gibt PUBLIC_BASE_URL zurück. Startup schlägt fehl wenn nicht gesetzt."""
    return _PUBLIC_BASE_URL


def _xml_escape(value) -> str:
    if not value:
        return ""
    return (str(value)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _rfc2822(dt) -> str:
    """datetime → RFC 2822 für RSS pubDate / lastBuildDate."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return formatdate(dt.timestamp(), usegmt=True)


def _build_feed(zoo_row, item_rows, base_url: str) -> str:
    """
    zoo_row  — (id, slug, name, url, description,
                top_left_latitude, top_left_longitude, data_version, icon_url)
    item_rows — Liste von (version, file_size, exported_at, changelog)
    """
    (zoo_id, slug, name, zoo_url, description,
     latitude, longitude, data_version, media_version, icon_url) = zoo_row

    feed_url   = f"{base_url}/feed/{slug}"
    sqlite_url = f"{base_url}/db/{slug}"

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"',
        f'     xmlns:zoo="{FEED_NS}"',
        '     xmlns:atom="http://www.w3.org/2005/Atom">',
        '  <channel>',
        f'    <title>{_xml_escape(name)}</title>',
        f'    <link>{_xml_escape(zoo_url or feed_url)}</link>',
        f'    <atom:link href="{_xml_escape(feed_url)}" rel="self" type="application/rss+xml"/>',
        f'    <description>{_xml_escape(description or name)} — ZooGuide Datenfeed</description>',
        '    <language>de</language>',
        '    <generator>ZooGuide Server</generator>',
        '',
        '    <!-- Zoo-Metadaten -->',
        f'    <zoo:feedVersion>{FEED_VERSION}</zoo:feedVersion>',
        f'    <zoo:slug>{_xml_escape(slug)}</zoo:slug>',
        f'    <zoo:version>{data_version}</zoo:version>',
        f'    <zoo:mediaVersion>{media_version}</zoo:mediaVersion>',
        f'    <zoo:displayName>{_xml_escape(name)}</zoo:displayName>',
        f'    <zoo:id>{zoo_id}</zoo:id>',
    ]

    if latitude is not None:
        lines.append(f'    <zoo:latitude>{latitude}</zoo:latitude>')
    if longitude is not None:
        lines.append(f'    <zoo:longitude>{longitude}</zoo:longitude>')
    if zoo_url:
        lines.append(f'    <zoo:website>{_xml_escape(zoo_url)}</zoo:website>')
    if icon_url:
        lines += [
            '',
            '    <!-- Zoo Icon (RSS 2.0 standard <image> element) -->',
            '    <image>',
            f'      <url>{_xml_escape(icon_url)}</url>',
            f'      <title>{_xml_escape(name)}</title>',
            f'      <link>{_xml_escape(zoo_url or feed_url)}</link>',
            '    </image>',
            f'    <zoo:iconUrl>{_xml_escape(icon_url)}</zoo:iconUrl>',
        ]

    for (version, file_size, exported_at, changelog) in item_rows:
        lines += [
            '',
            '    <item>',
            f'      <title>{_xml_escape(name)} v{version}</title>',
            f'      <guid isPermaLink="false">{_xml_escape(slug)}-{version}</guid>',
            f'      <pubDate>{_rfc2822(exported_at)}</pubDate>',
        ]
        if changelog:
            lines.append(f'      <description>{_xml_escape(changelog)}</description>')
        lines += [
            f'      <zoo:version>{version}</zoo:version>',
            f'      <enclosure url="{_xml_escape(sqlite_url)}"',
            f'                 length="{file_size or 0}"',
            '                 type="application/x-sqlite3+gzip"/>',
            f'      <zoo:mediaBundle url="{_xml_escape(base_url)}/media-bundle/{_xml_escape(slug)}"'
            f'                       mediaVersion="{media_version}"'
            '                       type="application/zip"/>',
            '    </item>',
        ]

    lines += ['  </channel>', '</rss>']
    return "\n".join(lines)


@feed_bp.route("/feed/<zoo>", methods=["GET"])
@limiter.limit("30 per minute")
def get_feed(zoo):
    """Öffentlicher RSS-Feed für einen Zoo. Kein API-Key erforderlich."""
    if not is_valid_slug(zoo):
        return jsonify({"error": "Invalid zoo identifier"}), 400

    pg = None
    try:
        pg = get_pg_connection()

        with pg.cursor() as cur:
            cur.execute("""
                SELECT
                    id, slug, name, url, description,
                    top_left_latitude, top_left_longitude,
                    data_version, media_version, icon_url
                FROM zoo.zoos
                WHERE slug = %s AND is_active = TRUE
            """, (zoo,))
            zoo_row = cur.fetchone()

        if not zoo_row:
            return jsonify({"error": "Zoo not found"}), 404

        item_rows = []
        try:
            with pg.cursor() as cur:
                cur.execute("""
                    SELECT version, file_size, exported_at, changelog
                    FROM zoo.zoo_exports
                    WHERE zoo_slug = %s
                    ORDER BY version DESC
                    LIMIT 5
                """, (zoo,))
                item_rows = cur.fetchall()
        except Exception:
            pass  # zoo_exports existiert noch nicht

        if not item_rows:
            item_rows = [(zoo_row[7], None, datetime.now(timezone.utc), None)]

    except Exception:
        logging.exception(f"Feed-Fehler für {zoo}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()

    base_url = _base_url()
    xml = _build_feed(zoo_row, item_rows, base_url)

    return Response(
        xml,
        status=200,
        mimetype="application/rss+xml",
        headers={
            "Content-Type":  "application/rss+xml; charset=utf-8",
            "Cache-Control": "public, max-age=300",
            "X-Zoo-Version": str(zoo_row[7]),
        }
    )


@feed_bp.route("/feed", methods=["GET"])
@limiter.limit("10 per minute")
def list_feeds():
    """Listet alle öffentlichen Zoo-Feeds dieses Servers."""
    pg = None
    try:
        pg = get_pg_connection()
        with pg.cursor() as cur:
            cur.execute("""
                SELECT slug, name, data_version
                FROM zoo.zoos
                WHERE is_active = TRUE
                ORDER BY name
            """)
            zoos = cur.fetchall()
    except Exception:
        logging.exception("Fehler bei Feed-Liste")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        if pg:
            pg.close()

    base_url = _base_url()
    result = [
        {
            "slug":     row[0],
            "name":     row[1],
            "version":  row[2],
            "feed_url": f"{base_url}/feed/{row[0]}",
        }
        for row in zoos
    ]
    return jsonify(result), 200
