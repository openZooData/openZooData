#!/usr/bin/env python3
"""
validate_species_wikidata.py
-----------------------------
Validiert species.wikidata_id gegen Wikidata:
  - Deutsches Label == species.german_name (normalisiert)
  - Lateinischer Name (P225) == species.latin_name (normalisiert)

Falls beides korrekt → id_valid = TRUE im SQL Output.
Falls Abweichung → Review-Datei.

Output:
  - validate_species_valid.sql     → UPDATE id_valid = TRUE
  - validate_species_review.txt    → Abweichungen zur manuellen Prüfung
"""

import sys
import re
import time
import requests
import psycopg2
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple

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

WIKIDATA_API    = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
API_DELAY       = 0.5

# ─── Normalisierung ───────────────────────────────────────────────────────────

def normalize(name: str) -> str:
    if not name:
        return ""
    name = name.lower().replace("-", " ")
    return re.sub(r"\s+", " ", name).strip()

# ─── Wikidata ─────────────────────────────────────────────────────────────────

def get_wikidata_data(wikidata_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Ruft deutsches Label und lateinischen Namen (P225) für eine Wikidata-ID ab.
    Returns: (label_de, latin_name)
    """
    # Labels abrufen
    params = {
        "action":    "wbgetentities",
        "ids":       wikidata_id,
        "props":     "labels",
        "languages": "de",
        "format":    "json",
    }
    try:
        r = requests.get(
            WIKIDATA_API, params=params, timeout=10,
            headers={"User-Agent": "ZooGuide/1.0 (thorsten@iborg.de)"}
        )
        r.raise_for_status()
        entity  = r.json().get("entities", {}).get(wikidata_id, {})
        label_de = entity.get("labels", {}).get("de", {}).get("value")
    except Exception:
        label_de = None

    time.sleep(API_DELAY)

    # Lateinischen Namen via SPARQL P225
    sparql = f"""
    SELECT ?latinName WHERE {{
      wd:{wikidata_id} wdt:P225 ?latinName.
    }} LIMIT 1
    """
    try:
        r = requests.get(
            WIKIDATA_SPARQL,
            params={"query": sparql, "format": "json"},
            timeout=10,
            headers={"User-Agent": "ZooGuide/1.0 (thorsten@iborg.de)"}
        )
        r.raise_for_status()
        results = r.json().get("results", {}).get("bindings", [])
        latin_name = results[0].get("latinName", {}).get("value") if results else None
    except Exception:
        latin_name = None

    time.sleep(API_DELAY)

    return label_de, latin_name

# ─── Datenbank ────────────────────────────────────────────────────────────────

def load_species(conn, all_species: bool = False) -> List[Dict]:
    """
    Lädt Species mit wikidata_id.
    Standard: nur nicht-validierte (id_valid IS NOT TRUE)
    --all: alle Species mit wikidata_id
    """
    where = "WHERE wikidata_id IS NOT NULL" if all_species else \
            "WHERE wikidata_id IS NOT NULL AND (id_valid IS NULL OR id_valid = FALSE)"
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, german_name, latin_name, wikidata_id
            FROM species
            {where}
            ORDER BY id
        """)
        rows = cur.fetchall()
    return [
        {"id": r[0], "german_name": r[1], "latin_name": r[2], "wikidata_id": r[3]}
        for r in rows
    ]

# ─── Output ───────────────────────────────────────────────────────────────────

def escape(v: str) -> str:
    return v.replace("'", "''") if v else ""

def generate_sql(valid_ids: List[int]) -> str:
    lines = [
        "-- ============================================================",
        "-- Species Validierung — id_valid = TRUE",
        f"-- Generiert: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"-- {len(valid_ids)} Species validiert",
        "-- ============================================================",
        "",
        "SET search_path TO zoo, public;",
        "BEGIN;",
        "",
        f"UPDATE species SET id_valid = TRUE",
        f"WHERE id IN ({', '.join(map(str, valid_ids))});",
        "",
        "-- Prüfung",
        "SELECT COUNT(*) AS valid_count FROM species WHERE id_valid = TRUE;",
        "",
        "COMMIT;",
    ]
    return "\n".join(lines)


def generate_review(review_cases: List[Dict]) -> str:
    lines = [
        "Zoo Guide — Species Validierung Review",
        f"Erstellt: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Fälle: {len(review_cases)}",
        "=" * 70,
        "",
    ]
    for c in review_cases:
        lines.append(f"Species ID:    {c['id']}")
        lines.append(f"DB Name:       {c['german_name']}")
        lines.append(f"DB Latin:      {c['latin_name'] or '—'}")
        lines.append(f"Wikidata ID:   {c['wikidata_id']}")
        lines.append(f"Wiki Label DE: {c['wiki_label'] or '(kein Label)'}")
        lines.append(f"Wiki Latin:    {c['wiki_latin'] or '(kein P225)'}")
        lines.append(f"Problem:       {c['problem']}")
        lines.append(f"URL:           https://www.wikidata.org/wiki/{c['wikidata_id']}")
        lines.append("-" * 70)
        lines.append("")
    return "\n".join(lines)

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Species Wikidata Validierung")
    parser.add_argument("--all", action="store_true",
                        help="Alle Species prüfen (auch bereits validierte)")
    args = parser.parse_args()

    print("✅ Zoo Guide — Species Wikidata Validierung")
    if args.all:
        print("   Modus: alle Species")
    else:
        print("   Modus: nur nicht-validierte Species (--all für alle)")
    print("=" * 50)

    print("\n📡 Verbinde mit Datenbank...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("   ✅ Verbunden")
    except Exception as e:
        print(f"   ❌ {e}")
        sys.exit(1)

    species_list = load_species(conn, all_species=args.all)
    conn.close()
    print(f"   {len(species_list)} Species geladen")

    valid_ids    = []
    review_cases = []

    print(f"\n🔍 Validiere {len(species_list)} Species gegen Wikidata...")
    print()

    for i, s in enumerate(species_list, 1):
        print(f"  [{i:3}/{len(species_list)}] {s['german_name']}", end=" ... ")

        wiki_label, wiki_latin = get_wikidata_data(s["wikidata_id"])

        # Validierungslogik
        label_ok  = False
        latin_ok  = False
        problems  = []

        # Deutsches Label prüfen
        if wiki_label and normalize(wiki_label) == normalize(s["german_name"]):
            label_ok = True
        elif wiki_label and s["latin_name"] and normalize(wiki_label) == normalize(s["latin_name"]):
            # Wikidata hat kein echtes DE-Label — lateinischer Name als Platzhalter
            # ID ist korrekt wenn P225 stimmt
            label_ok = True
        elif not wiki_label:
            problems.append("Kein deutsches Label in Wikidata")
        else:
            problems.append(f"Label abweichend: Wiki='{wiki_label}' DB='{s['german_name']}'")

        # Lateinischen Namen prüfen
        if s["latin_name"] and wiki_latin:
            if normalize(wiki_latin) == normalize(s["latin_name"]):
                latin_ok = True
            else:
                problems.append(f"Latin abweichend: Wiki='{wiki_latin}' DB='{s['latin_name']}'")
        elif not s["latin_name"] and not wiki_latin:
            latin_ok = True  # Beide leer — kein Widerspruch
        elif not s["latin_name"]:
            latin_ok = True  # DB hat keinen latin_name — nur Label zählt
            # Optional: latin_name aus Wikidata übernehmen
        elif not wiki_latin:
            problems.append("Kein P225 in Wikidata")

        # Entscheidung
        if label_ok and latin_ok:
            print(f"✅")
            valid_ids.append(s["id"])
        else:
            print(f"⚠️  {' | '.join(problems)}")
            review_cases.append({
                **s,
                "wiki_label": wiki_label,
                "wiki_latin": wiki_latin,
                "problem":    " | ".join(problems),
            })

    # Zusammenfassung
    print()
    print("=" * 50)
    print(f"✅ Valid:  {len(valid_ids)}")
    print(f"⚠️  Review: {len(review_cases)}")

    # SQL generieren
    if valid_ids:
        sql = generate_sql(valid_ids)
        sql_path = Path(__file__).parent / "validate_species_valid.sql"
        sql_path.write_text(sql, encoding="utf-8")
        print(f"\n📄 SQL: {sql_path}")

    # Review-Datei
    if review_cases:
        review = generate_review(review_cases)
        review_path = Path(__file__).parent / "validate_species_review.txt"
        review_path.write_text(review, encoding="utf-8")
        print(f"📋 Review: {review_path}")

    print("\n✅ Fertig!")


if __name__ == "__main__":
    main()
