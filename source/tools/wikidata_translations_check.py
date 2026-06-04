#!/usr/bin/env python3
"""
wikidata_translations_check.py
-------------------------------
Vergleicht die übersetzten Tiernamen in der Zoo Guide Datenbank
mit den Wikidata-Labels in allen 12 App-Sprachen.

Normalisierter Vergleich:
  - Kleinschreibung
  - Bindestriche → Leerzeichen
  - Mehrfache Leerzeichen → einfaches Leerzeichen
  - Führende/nachfolgende Leerzeichen entfernt

Nur Abweichungen und fehlende Übersetzungen werden gemeldet.

Voraussetzungen (Mac):
    pip3 install psycopg2-binary requests

Aufruf:
    python3 wikidata_translations_check.py

Output:
    translations_check_report.txt — Abweichungen pro Zoo, Sprache und Tier
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
    "dbname":   env.get("PG_DATABASE", "zooguide"),
    "port":     int(env.get("DB_PORT", "5432")),
}

PRODUCTIVE_ZOOS = ["zoo_berlin", "zoo_muenster", "zoo_osnabrueck", "zoo_rheine"]

# Alle 12 App-Sprachen
APP_LANGUAGES = ["de", "en", "es", "fr", "it", "nl", "pl", "pt", "ru", "tr", "uk", "zh-Hans"]

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
API_DELAY    = 0.5  # Sekunden zwischen Requests

# ─── Normalisierung ───────────────────────────────────────────────────────────

def normalize(name: str) -> str:
    name = name.lower()
    name = name.replace("-", " ")
    name = re.sub(r"\s+", " ", name)
    return name.strip()

# ─── Wikidata ─────────────────────────────────────────────────────────────────

def get_wikidata_labels(wikidata_id: str) -> Dict[str, str]:
    """
    Ruft Labels für alle App-Sprachen in einem einzigen API-Call ab.
    Gibt dict {lang: label} zurück.
    """
    params = {
        "action":    "wbgetentities",
        "ids":       wikidata_id,
        "props":     "labels",
        "languages": "|".join(APP_LANGUAGES),
        "format":    "json",
    }
    try:
        r = requests.get(
            WIKIDATA_API,
            params=params,
            timeout=10,
            headers={"User-Agent": "ZooGuide/1.0 (thorsten@iborg.de)"}
        )
        r.raise_for_status()
        data     = r.json()
        entity   = data.get("entities", {}).get(wikidata_id, {})
        labels   = entity.get("labels", {})
        return {lang: labels[lang]["value"] for lang in APP_LANGUAGES if lang in labels}
    except Exception:
        return {}

# ─── Datenbank ────────────────────────────────────────────────────────────────

def load_locations_with_wikidata(conn) -> List[Dict]:
    """
    Lädt alle Tier-Locations der produktiven Zoos mit wikidata_id.
    """
    placeholders = ",".join(["%s"] * len(PRODUCTIVE_ZOOS))
    query = f"""
        SELECT l.id, l.name, l.wikidata_id, z.slug, z.id as zoo_id
        FROM locations l
        JOIN zoos z ON l.zoo_id = z.id
        WHERE z.slug IN ({placeholders})
          AND l.location_type = 'Tierbereich'
          AND l.wikidata_id IS NOT NULL
        ORDER BY z.slug, l.name
    """
    with conn.cursor() as cur:
        cur.execute(query, PRODUCTIVE_ZOOS)
        rows = cur.fetchall()
    return [
        {"id": r[0], "name": r[1], "wikidata_id": r[2], "zoo": r[3], "zoo_id": r[4]}
        for r in rows
    ]


def load_translations(conn, zoo_id: int, language: str, source: str) -> Optional[str]:
    """
    Lädt eine bestehende Übersetzung aus der translations-Tabelle.
    source = deutscher Kanonname (locations.name)
    """
    query = """
        SELECT target FROM translations
        WHERE zoo_id = %s AND language = %s AND source = %s
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(query, (zoo_id, language, source))
        row = cur.fetchone()
    return row[0] if row else None

# ─── Report ───────────────────────────────────────────────────────────────────

def generate_report(deviations: List[Dict], stats: Dict) -> str:
    lines = [
        "Zoo Guide — Wikidata Übersetzungsvergleich",
        f"Erstellt:    {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Sprachen:    {', '.join(APP_LANGUAGES)}",
        f"Geprüft:     {stats['checked']} Tier-Sprach-Kombinationen",
        f"Übereinstimmungen: {stats['matches']}",
        f"Abweichungen:      {stats['deviations']}",
        f"Fehlend (DB):      {stats['missing_db']}",
        f"Fehlend (Wiki):    {stats['missing_wiki']}",
        "=" * 70,
        "",
    ]

    # Gruppieren nach Zoo → Tier → Sprache
    by_zoo = {}
    for d in deviations:
        zoo = d["zoo"]
        if zoo not in by_zoo:
            by_zoo[zoo] = {}
        name = d["name"]
        if name not in by_zoo[zoo]:
            by_zoo[zoo][name] = []
        by_zoo[zoo][name].append(d)

    for zoo, animals in sorted(by_zoo.items()):
        lines.append(f"── {zoo} {'─' * (50 - len(zoo))}")
        lines.append("")

        for animal_name, diffs in sorted(animals.items()):
            # Hole wikidata_id vom ersten Eintrag
            wikidata_id = diffs[0]["wikidata_id"]
            lines.append(f"  {animal_name}")
            lines.append(f"  Wikidata: https://www.wikidata.org/wiki/{wikidata_id}")
            lines.append("")

            for d in sorted(diffs, key=lambda x: x["language"]):
                lang = d["language"]
                status = d["status"]

                if status == "missing_db":
                    lines.append(f"    [{lang:7}] ⚠️  Fehlt in DB — Wikidata: '{d['wikidata_label']}'")
                elif status == "missing_wiki":
                    lines.append(f"    [{lang:7}] ⚠️  Kein Wikidata-Label — DB: '{d['db_value']}'")
                elif status == "deviation":
                    lines.append(f"    [{lang:7}] ⚠️  DB: '{d['db_value']}'")
                    lines.append(f"    {' ':9}    Wiki: '{d['wikidata_label']}'")

            lines.append("")

    if not deviations:
        lines.append("✅ Keine Abweichungen — alle Übersetzungen stimmen überein.")

    return "\n".join(lines)

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("🌍 Zoo Guide — Wikidata Übersetzungsvergleich")
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

    # Locations laden
    print("\n📋 Lade Locations mit Wikidata-ID...")
    locations = load_locations_with_wikidata(conn)
    print(f"   {len(locations)} Tiere gefunden")

    if not locations:
        print("\n⚠️  Keine Locations mit Wikidata-ID gefunden.")
        print("   Zuerst wikidata_lookup.py ausführen.")
        conn.close()
        sys.exit(0)

    # Vergleich
    total    = len(locations) * len(APP_LANGUAGES)
    print(f"\n🔍 Vergleiche {total} Tier-Sprach-Kombinationen...")
    print()

    deviations = []
    stats = {"checked": 0, "matches": 0, "deviations": 0,
             "missing_db": 0, "missing_wiki": 0}

    for i, loc in enumerate(locations, 1):
        print(f"  [{i:3}/{len(locations)}] {loc['zoo']}: {loc['name']}", end=" ... ")

        # Alle Labels in einem API-Call
        wiki_labels = get_wikidata_labels(loc["wikidata_id"])
        time.sleep(API_DELAY)

        animal_deviations = 0

        for lang in APP_LANGUAGES:
            stats["checked"] += 1
            wiki_label = wiki_labels.get(lang)
            db_value   = load_translations(conn, loc["zoo_id"], lang, loc["name"])

            if wiki_label is None and db_value is None:
                # Beide fehlen — kein sinnvoller Vergleich
                continue
            elif wiki_label is None:
                # Kein Wikidata-Label für diese Sprache
                stats["missing_wiki"] += 1
                deviations.append({**loc, "language": lang, "status": "missing_wiki",
                                   "db_value": db_value, "wikidata_label": None})
                animal_deviations += 1
            elif db_value is None:
                # Fehlt in unserer DB
                stats["missing_db"] += 1
                deviations.append({**loc, "language": lang, "status": "missing_db",
                                   "db_value": None, "wikidata_label": wiki_label})
                animal_deviations += 1
            elif normalize(db_value) != normalize(wiki_label):
                # Abweichung
                stats["deviations"] += 1
                deviations.append({**loc, "language": lang, "status": "deviation",
                                   "db_value": db_value, "wikidata_label": wiki_label})
                animal_deviations += 1
            else:
                stats["matches"] += 1

        if animal_deviations == 0:
            print("✅")
        else:
            print(f"⚠️  {animal_deviations} Abweichung(en)")

    conn.close()

    # Zusammenfassung
    total_issues = len(deviations)
    print()
    print("=" * 50)
    print(f"✅ Übereinstimmungen: {stats['matches']}")
    print(f"⚠️  Abweichungen:     {stats['deviations']}")
    print(f"⚠️  Fehlend in DB:    {stats['missing_db']}")
    print(f"⚠️  Kein Wiki-Label:  {stats['missing_wiki']}")
    print(f"─────────────────────────────")
    print(f"   Gesamt Probleme:  {total_issues}")

    # Report
    report = generate_report(deviations, stats)
    report_path = Path(__file__).parent / "translations_check_report.txt"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n📄 Report: {report_path}")
    print("\n✅ Fertig!")

if __name__ == "__main__":
    main()
