#!/usr/bin/env python3
"""
tools/generate_species_icons.py
--------------------------------
Generiert fehlende Species-Icons via OpenAI Images API und legt sie unter
media/species/generated/ ab. Erstellt anschließend einen zoo.media-Eintrag
und setzt species.icon_media_id.

Läuft als Cronjob oder manuell:
    python3 source/tools/generate_species_icons.py
    python3 source/tools/generate_species_icons.py --dry-run
    python3 source/tools/generate_species_icons.py --species 42
    python3 source/tools/generate_species_icons.py --limit 10

Voraussetzungen in .env:
    OPENAI_API_KEY_1=sk-...
    STORAGE_DIR=/pfad/zu/media      (optional, default: <repo>/media)
    PG_HOST, PG_USER, PG_PASSWORD, PG_NAME, PG_PORT

Ausgabepfad: <STORAGE_DIR>/species/generated/<wikidata_id>_<latin_name>.png
"""

import argparse
import base64
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import psycopg2
import psycopg2.extras


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ─── Konfiguration ────────────────────────────────────────────────────────────

def load_env() -> dict:
    env = {}

    for path in [
        Path(__file__).parent.parent.parent / ".env",
        Path(__file__).parent.parent / ".env",
        Path.home() / ".env",
    ]:
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
            logging.info(f".env geladen: {path}")
            break

    return env


env = load_env()

PG_CONFIG = {
    "host": env.get("PG_HOST"),
    "user": env.get("PG_USER"),
    "password": env.get("PG_PASSWORD"),
    "dbname": env.get("PG_NAME", "zooguide"),
    "port": int(env.get("PG_PORT", "5432")),
    "options": "-c search_path=zoo,public",
}

STORAGE_DIR = Path(
    env.get(
        "STORAGE_DIR",
        str(Path(__file__).parent.parent.parent / "media"),
    )
)

OUTPUT_DIR = STORAGE_DIR / "species" / "generated"

OPENAI_IMAGE_URL = "https://api.openai.com/v1/images/generations"

# Bestes aktuelles Modell für Bildgenerierung.
# Falls dein Account noch keinen Zugriff auf gpt-image-2 hat:
# in .env setzen: OPENAI_IMAGE_MODEL=gpt-image-1
IMAGE_MODEL = env.get("OPENAI_IMAGE_MODEL", "gpt-image-2")

IMAGE_SIZE = env.get("OPENAI_IMAGE_SIZE", "1024x1024")
IMAGE_QUALITY = env.get("OPENAI_IMAGE_QUALITY", "high")

# Für Cronjob konservativ lassen.
SLEEP_BETWEEN = int(env.get("OPENAI_IMAGE_SLEEP", "12"))


# ─── Prompt ──────────────────────────────────────────────────────────────────

def build_prompt(german_name: str, latin_name: str | None) -> str:
    species_ref = german_name

    if latin_name:
        species_ref += f" ({latin_name})"

    return (
        f"Create a transparent-background PNG icon of a {species_ref}. "
        "Professional zoo wildlife illustration. "
        "Portrait bust view: head, neck and upper body only. "
        "The animal should be centered and fill about 80 percent of the square canvas. "
        "Detailed, realistic digital painting with clean readable silhouette. "
        "Show species-specific features accurately. "
        "No habitat, no landscape, no floor, no shadow, no frame, no border, no text, no logo. "
        "The background must be fully transparent alpha, not white, not gray, not checkerboard. "
        "Suitable as a mobile app species icon."
    )


# ─── OpenAI Images API ────────────────────────────────────────────────────────

def call_openai_image(prompt: str, api_key: str) -> bytes | None:
    """
    Ruft die OpenAI Images API auf und gibt PNG-Bytes zurück.
    Für echte Transparenz sind background='transparent' und output_format='png' entscheidend.
    """

    payload_dict = {
        "model": IMAGE_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": IMAGE_SIZE,
        "quality": IMAGE_QUALITY,
        "background": "transparent",
        "output_format": "png",
    }

    payload = json.dumps(payload_dict).encode("utf-8")

    req = urllib.request.Request(
        OPENAI_IMAGE_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
            item = data["data"][0]

            # GPT-Image-Modelle liefern normalerweise base64.
            if "b64_json" in item:
                return base64.b64decode(item["b64_json"])

            # Fallback für ältere DALL-E-Response-Formate.
            if "url" in item:
                with urllib.request.urlopen(item["url"], timeout=60) as img_resp:
                    return img_resp.read()

            logging.error(f"Unbekanntes Response-Format: {list(item.keys())}")
            return None

    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logging.error(f"OpenAI Images HTTP {e.code}: {body[:1200]}")

        if IMAGE_MODEL == "gpt-image-2":
            logging.error(
                "Hinweis: Falls dein Account keinen Zugriff auf gpt-image-2 hat, "
                "setze in .env: OPENAI_IMAGE_MODEL=gpt-image-1"
            )

        return None

    except Exception as e:
        logging.error(f"OpenAI Images Fehler: {e}")
        return None


def resize_to_180(img_bytes: bytes) -> bytes:
    """
    Skaliert auf 180x180 und erhält den Alpha-Kanal.
    Das ist die finale Größe die in media/species/ gespeichert wird.
    """
    try:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(img_bytes))
        img = img.convert("RGBA")
        img = img.resize((180, 180), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    except ImportError:
        logging.warning("Pillow nicht installiert — Bild wird in Originalgröße gespeichert")
        return img_bytes


def has_alpha(img_bytes: bytes) -> bool:
    """Prüft, ob die gespeicherte PNG-Datei einen Alpha-Kanal hat."""

    try:
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(img_bytes))

        if img.mode in ("RGBA", "LA"):
            return True

        if "transparency" in img.info:
            return True

        return False

    except Exception as e:
        logging.warning(f"Alpha-Prüfung fehlgeschlagen: {e}")
        return False


# ─── DB-Helpers ───────────────────────────────────────────────────────────────

def get_pending_species(pg, species_id: int | None, limit: int) -> list:
    """Gibt Species zurück, die noch kein Icon haben."""

    with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        params = []
        where = "s.icon_media_id IS NULL AND s.id_valid = TRUE"

        if species_id:
            where += " AND s.id = %s"
            params.append(species_id)

        params.append(limit)

        cur.execute(
            f"""
            SELECT s.id, s.wikidata_id, s.german_name, s.latin_name
            FROM zoo.species s
            WHERE {where}
            ORDER BY s.german_name
            LIMIT %s
            """,
            params,
        )

        return cur.fetchall()


def create_media_entry(
    pg,
    species_id: int,
    zoo_id: int | None,
    filename: str,
) -> int:
    """Legt media-Eintrag für das 180x180-Icon in species/ an."""

    with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            INSERT INTO zoo.media
                (entity_type, entity_id, zoo_id, storage_path,
                 filename, mime_type, label)
            VALUES ('species', %s, %s, 'species/', %s, 'image/png', 'icon')
            RETURNING id
            """,
            (species_id, zoo_id, filename),
        )
        return cur.fetchone()["id"]


def link_media_to_species(pg, species_id: int, media_id: int):
    with pg.cursor() as cur:
        cur.execute(
            """
            UPDATE zoo.species
            SET icon_media_id = %s
            WHERE id = %s
            """,
            (media_id, species_id),
        )


# ─── Dateinamen ───────────────────────────────────────────────────────────────

def safe_filename(wikidata_id: str, latin_name: str | None) -> str:
    if not latin_name:
        return f"{wikidata_id}_generated.png"

    safe = latin_name.replace(" ", "_").replace("/", "_")
    safe = "".join(c for c in safe if c.isalnum() or c == "_")

    return f"{wikidata_id}_{safe}.png"


# ─── Hauptlogik ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generiert fehlende Species-Icons via OpenAI Images API"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur anzeigen, kein API-Call, kein DB-Write",
    )

    parser.add_argument(
        "--species",
        type=int,
        help="Nur diese species_id bearbeiten",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximale Anzahl Icons pro Lauf, default: 50",
    )

    args = parser.parse_args()

    api_key = env.get("OPENAI_API_KEY_1") or env.get("OPENAI_API_KEY")

    if not api_key:
        logging.error("OPENAI_API_KEY_1 oder OPENAI_API_KEY fehlt in .env")
        sys.exit(1)

    try:
        pg = psycopg2.connect(**PG_CONFIG)
    except Exception as e:
        logging.error(f"DB-Verbindung fehlgeschlagen: {e}")
        sys.exit(1)

    pending = get_pending_species(pg, args.species, args.limit)

    if not pending:
        logging.info("Alle Species haben bereits ein Icon — nichts zu tun")
        pg.close()
        return

    logging.info(f"{len(pending)} Species ohne Icon:")
    for s in pending:
        logging.info(f"  id={s['id']}: {s['german_name']} ({s['wikidata_id']})")

    logging.info(f"Image-Modell: {IMAGE_MODEL}")
    logging.info(f"Image-Größe: {IMAGE_SIZE}")
    logging.info(f"Image-Qualität: {IMAGE_QUALITY}")
    logging.info("Hintergrund: transparent")
    logging.info("Output-Format: png")

    if args.dry_run:
        logging.info("Dry-run — kein API-Call gestartet")
        pg.close()
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    ok = 0
    fail = 0

    for i, s in enumerate(pending, start=1):
        species_id = s["id"]
        wikidata_id = s["wikidata_id"] or f"unknown_{species_id}"
        german_name = s["german_name"]
        latin_name = s["latin_name"]

        filename = safe_filename(wikidata_id, latin_name)

        logging.info(f"[{i}/{len(pending)}] {german_name} → {filename}")

        prompt = build_prompt(german_name, latin_name)

        img_bytes = call_openai_image(prompt, api_key)

        if not img_bytes:
            logging.error(f"  ✗ API-Fehler für {german_name}")
            fail += 1
            time.sleep(SLEEP_BETWEEN)
            continue

        # Original (1024x1024) als Backup in generated/ speichern
        original_path = OUTPUT_DIR / filename
        try:
            original_path.write_bytes(img_bytes)
            logging.info(f"  → Original gespeichert: {original_path} ({len(img_bytes) / 1024:.1f} KB)")
        except Exception as e:
            logging.warning(f"  ⚠ Original konnte nicht gespeichert werden: {e}")

        # Auf 180x180 skalieren für die App
        small_bytes = resize_to_180(img_bytes)

        if not has_alpha(small_bytes):
            logging.warning(f"  ⚠ Bild hat keinen erkennbaren Alpha-Kanal: {german_name}")
        else:
            logging.info("  ✓ Alpha-Kanal erkannt")

        # 180x180-Version in media/species/ speichern
        species_dir = STORAGE_DIR / "species"
        species_dir.mkdir(parents=True, exist_ok=True)
        small_path = species_dir / filename

        try:
            small_path.write_bytes(small_bytes)
            logging.info(f"  → 180x180 gespeichert: {small_path} ({len(small_bytes) / 1024:.1f} KB)")
        except Exception as e:
            logging.error(f"  ✗ Datei konnte nicht geschrieben werden: {e}")
            fail += 1
            continue

        try:
            media_id = create_media_entry(pg, species_id, None, filename)
            link_media_to_species(pg, species_id, media_id)
            pg.commit()

            logging.info(f"  ✓ media_id={media_id} → species.icon_media_id gesetzt")
            ok += 1

        except Exception as e:
            pg.rollback()
            logging.error(f"  ✗ DB-Fehler: {e}")
            fail += 1

        if i < len(pending):
            time.sleep(SLEEP_BETWEEN)

    pg.close()

    logging.info(f"\nFertig: {ok} Icons generiert, {fail} Fehler")


if __name__ == "__main__":
    main()
