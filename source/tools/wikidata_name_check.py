#!/usr/bin/env python3
"""
wikidata_name_check.py
----------------------
Vergleicht deutsche Tiernamen in der Zoo Guide Datenbank
mit den Wikidata-Labels (Sprache: de).

Normalisierter Vergleich:
  - Kleinschreibung
  - Bindestriche → Leerzeichen
  - Mehrfache Leerzeichen → einfaches Leerzeichen
  - Führende/nachfolgende Leerzeichen entfernt

Nur Abweichungen werden gemeldet.

Voraussetzungen (Mac):
    pip3 install psycopg2-binary requests

Aufruf:
    python3 wikidata_name_check.py

Output:
    name_check_report.txt — Abweichungen mit Wikidata-URL
"""

import sys
import time
import re
import requests
import psycopg2
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

# ─── Konfiguration ────────────────────────────────────────────────────────────

def load_env():
    env = {}
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

env = load_env()

DB_CONFIG = {
    "host":     env.get("PG_HOST"),
    "user":     env.get("PG_USER"),
    "password": env.get("PG_PASSWORD"),
    "dbname":   env.get("PG_NAME"),
    "port":     int(env.get("DB_PORT", "5432")),
    "options":  "-c search_path=zoo,public",
}

PRODUCTIVE_ZOOS = ["zoo_berlin", "zoo_muenster", "zoo_osnabrueck", "zoo_rheine"]
WIKIDATA_API    = "https://www.wikidata.org/w/api.php"
API_DELAY       = 0.5  # Sekunden zwischen Requests

# ─── Normalisierung ───────────────────────────────────────────────────────────

def normalize(name: str) -> str:
    """
    Normalisiert einen Tiernamen für den Vergleich:
    - Kleinschreibung
    - Bindestriche → Leerzeichen
    - Mehrfache Leerzeichen → einfaches Leerzeichen
    - Strip
    """
    name = name.lower()
    name = name.replace("-", " ")
    name = re.sub(r"\s+", " ", name)
    return name.strip()

# ─── Wikidata ─────────────────────────────────────────────────────────────────

def get_wikidata_label_de(wikidata_id: str) -> Optional[str]:
    """
    Ruft das deutsche Label für eine Wikidata-ID ab.
    Gibt None zurück wenn kein Label gefunden.
    """
    params = {
        "action":   "wbgetentities",
        "ids":      wikidata_id,
        "props":    "labels",
        "languages": "de",
        "format":   "json",
    }
    try:
        r = requests.get(
            WIKIDATA_API,
            params=params,
            timeout=10,
            headers={"User-Agent": "ZooGuide/1.0 (thorsten@iborg.de)"}
        )
        r.raise_for_status()
        data = r.json()
        entity = data.get("entities", {}).get(wikidata_id, {})
        label = entity.get("labels", {}).get("de", {}).get("value")
        return label
    except Exception:
        return None

# ─── Datenbank ────────────────────────────────────────────────────────────────

def load_locations_with_wikidata(conn) -> List[Dict]:
    """
    Lädt alle Species der produktiven Zoos die bereits
    eine wikidata_id haben.
    """
    placeholders = ",".join(["%s"] * len(PRODUCTIVE_ZOOS))
    query = f"""
        SELECT DISTINCT s.id, s.german_name, s.wikidata_id, z.slug
        FROM species s
        JOIN enclosure_species es ON es.species_id = s.id
        JOIN enclosures e ON e.id = es.enclosure_id
        JOIN zoos z ON z.id = e.zoo_id
        WHERE z.slug IN ({placeholders})
          AND s.wikidata_id IS NOT NULL
        ORDER BY z.slug, s.german_name
    """
    with conn.cursor() as cur:
        cur.execute(query, PRODUCTIVE_ZOOS)
        rows = cur.fetchall()

    return [
        {"id": r[0], "name": r[1], "wikidata_id": r[2], "zoo": r[3]}
        for r in rows
    ]

# ─── Report ───────────────────────────────────────────────────────────────────

def generate_report(deviations: List[Dict]) -> str:
    lines = [
        "Zoo Guide — Wikidata Namensvergleich (Deutsch)",
        f"Erstellt: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Abweichungen: {len(deviations)}",
        "=" * 70,
        "",
    ]

    current_zoo = None
    for d in deviations:
        if d["zoo"] != current_zoo:
            current_zoo = d["zoo"]
            lines.append(f"── {current_zoo} {'─' * (50 - len(current_zoo))}")
            lines.append("")

        lines.append(f"  Species ID:     {d['id']}")
        lines.append(f"  DB Name:        {d['name']}")
        lines.append(f"  Wikidata Label: {d['wikidata_label']}")
        lines.append(f"  Wikidata ID:    {d['wikidata_id']}")
        lines.append(f"  URL:            https://www.wikidata.org/wiki/{d['wikidata_id']}")
        lines.append("")

    if not deviations:
        lines.append("✅ Keine Abweichungen gefunden — alle Namen stimmen überein.")

    return "\n".join(lines)

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("🔍 Zoo Guide — Wikidata Namensvergleich")
    print("=" * 50)

    # DB-Verbindung
    print("\n📡 Verbinde mit Datenbank...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.cursor().execute("SET search_path TO zoo, public")
        conn.commit()
        print("   ✅ Verbunden")
    except Exception as e:
        print(f"   ❌ Verbindung fehlgeschlagen: {e}")
        sys.exit(1)

    # Species laden
    print("\n📋 Lade Species mit Wikidata-ID...")
    locations = load_locations_with_wikidata(conn)
    conn.close()
    print(f"   {len(locations)} Arten gefunden")

    if not locations:
        print("\n⚠️  Keine Species mit Wikidata-ID gefunden.")
        sys.exit(0)

    # Vergleich
    print(f"\n🔍 Vergleiche Namen mit Wikidata ({len(locations)} Tiere)...")
    print()

    deviations = []

    for i, loc in enumerate(locations, 1):
        print(f"  [{i:3}/{len(locations)}] {loc['zoo']}: {loc['name']}", end=" ... ")

        label = get_wikidata_label_de(loc["wikidata_id"])
        time.sleep(API_DELAY)

        if label is None:
            print("⚠️  Kein Label gefunden")
            deviations.append({
                **loc,
                "wikidata_label": "(kein deutsches Label in Wikidata)",
            })
            continue

        if normalize(loc["name"]) == normalize(label):
            print("✅")
        else:
            print(f"⚠️  '{label}'")
            deviations.append({
                **loc,
                "wikidata_label": label,
            })

    # Zusammenfassung
    print()
    print("=" * 50)
    print(f"✅ Übereinstimmungen: {len(locations) - len(deviations)}")
    print(f"⚠️  Abweichungen:     {len(deviations)}")

    # Report
    report = generate_report(deviations)
    report_path = Path(__file__).parent / "name_check_report.txt"
    report_path.write_text(report)
    print(f"\n📄 Report: {report_path}")
    print("\n✅ Fertig!")

if __name__ == "__main__":
    main()
