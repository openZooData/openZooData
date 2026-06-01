#!/usr/bin/env python3
"""
fetch_english_translations.py
------------------------------
Holt englische Tiernamen von Wikidata und generiert SQL
für fehlende oder falsche EN-Einträge in der translations-Tabelle.

Strategie:
  1. Species mit wikidata_id → Wikidata Label EN abrufen
  2. Fehlende EN-Einträge ergänzen
  3. EN-Einträge wo en = de korrigieren

Aufruf:
    python3 fetch_english_translations.py

Output:
    update_english_translations.sql
"""

import sys
import time
import requests
import psycopg2
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# ─── Konfiguration ────────────────────────────────────────────────────────────

def load_env() -> Dict[str, str]:
    env = {}
    for path in [Path(__file__).parent / ".env", Path.home() / ".env"]:
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
            break
    return env

env = load_env()

DB_CONFIG = {
    "host":     env.get("PG_HOST"),
    "user":     env.get("PG_USER"),
    "password": env.get("PG_PASSWORD"),
    "dbname":   env.get("PG_NAME", "zooguide"),
    "port":     int(env.get("DB_PORT", "5432")),
    "options":  "-c search_path=zoo,public",
}

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
API_DELAY    = 0.5

# ─── Wikidata ─────────────────────────────────────────────────────────────────

def get_english_label(wikidata_id: str) -> Optional[str]:
    """Ruft das englische Label für eine Wikidata-ID ab."""
    params = {
        "action":    "wbgetentities",
        "ids":       wikidata_id,
        "props":     "labels",
        "languages": "en",
        "format":    "json",
    }
    try:
        r = requests.get(
            WIKIDATA_API, params=params, timeout=10,
            headers={"User-Agent": "ZooGuide/1.0 (thorsten@iborg.de)"}
        )
        r.raise_for_status()
        entity = r.json().get("entities", {}).get(wikidata_id, {})
        label  = entity.get("labels", {}).get("en", {}).get("value")
        time.sleep(API_DELAY)
        return label
    except Exception:
        time.sleep(API_DELAY)
        return None

# ─── Datenbank ────────────────────────────────────────────────────────────────

def load_species(conn) -> List[Dict]:
    """
    Lädt alle Species die:
    - eine wikidata_id haben
    - kein EN haben ODER en = de (falsch)
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT s.id, s.german_name, s.wikidata_id, t.de, t.en
            FROM species s
            JOIN translations t ON t.entity_id = s.id AND t.entity_type = 'species'
            WHERE s.wikidata_id IS NOT NULL
              AND (t.en IS NULL OR t.en = t.de)
            ORDER BY s.id
        """)
        rows = cur.fetchall()
    return [
        {"id": r[0], "german_name": r[1], "wikidata_id": r[2],
         "de": r[3], "en_current": r[4]}
        for r in rows
    ]

# ─── SQL generieren ───────────────────────────────────────────────────────────

def escape(v: str) -> str:
    return v.replace("'", "''") if v else ""

def generate_sql(updates: List[Dict]) -> str:
    lines = [
        "-- ============================================================",
        "-- Englische Übersetzungen aus Wikidata",
        f"-- Generiert: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"-- {len(updates)} Updates",
        "-- ============================================================",
        "",
        "SET search_path TO zoo, public;",
        "BEGIN;",
        "",
    ]

    for u in updates:
        lines.append(f"-- {u['german_name']} → '{u['en_new']}'")
        lines.append(f"UPDATE translations SET en = '{escape(u['en_new'])}'")
        lines.append(f"  WHERE entity_type = 'species' AND entity_id = {u['id']};")
        lines.append("")

    lines += [
        "-- Prüfung",
        "SELECT",
        "    COUNT(*) FILTER (WHERE en IS NOT NULL) AS mit_en,",
        "    COUNT(*) FILTER (WHERE en IS NULL) AS ohne_en,",
        "    COUNT(*) FILTER (WHERE en = de) AS en_gleich_de",
        "FROM translations WHERE entity_type = 'species';",
        "",
        "COMMIT;",
    ]
    return "\n".join(lines)

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("🇬🇧 Zoo Guide — Englische Übersetzungen von Wikidata")
    print("=" * 50)

    print("\n📡 Verbinde mit Datenbank...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("   ✅ Verbunden")
    except Exception as e:
        print(f"   ❌ {e}")
        sys.exit(1)

    species_list = load_species(conn)
    conn.close()
    print(f"   {len(species_list)} Species ohne/falsche EN-Übersetzung")

    if not species_list:
        print("\n✅ Alle englischen Übersetzungen bereits vorhanden!")
        sys.exit(0)

    print(f"\n🔍 Rufe Wikidata-Labels ab...")
    print()

    updates   = []
    not_found = []

    for i, s in enumerate(species_list, 1):
        print(f"  [{i:3}/{len(species_list)}] {s['german_name']}", end=" ... ")

        label = get_english_label(s["wikidata_id"])

        if label:
            # Nicht überschreiben wenn Label = deutscher Name
            if label == s["de"]:
                print(f"⚠️  Label = DE Name ('{label}') — übersprungen")
                not_found.append(s)
            else:
                print(f"✅ '{label}'")
                updates.append({**s, "en_new": label})
        else:
            print("❌ Kein EN-Label")
            not_found.append(s)

    print()
    print("=" * 50)
    print(f"✅ Updates:       {len(updates)}")
    print(f"⚠️  Nicht gefunden: {len(not_found)}")

    if not_found:
        print(f"\n⚠️  Ohne EN-Label ({len(not_found)}):")
        for s in not_found[:10]:
            print(f"   {s['german_name']} ({s['wikidata_id']})")
        if len(not_found) > 10:
            print(f"   ... und {len(not_found)-10} weitere")

    if updates:
        sql = generate_sql(updates)
        sql_path = Path(__file__).parent / "update_english_translations.sql"
        sql_path.write_text(sql, encoding="utf-8")
        print(f"\n📄 SQL: {sql_path}")

    print("\n✅ Fertig!")

if __name__ == "__main__":
    main()
