#!/usr/bin/env python3
"""
wikidata_sync.py
----------------
Sucht für alle Species ohne id_valid die passende Wikidata-ID.

Strategie:
  1. latin_name vorhanden → SPARQL P225 Suche (zuverlässig)
  2. Kein latin_name → deutsche Namenssuche

Output:
  - import_wikidata.sql   → direkt einspielbare UPDATEs
  - review_needed.txt     → Fälle die manuelles Review brauchen

Aufruf:
    python3 wikidata_sync.py           # nur nicht-validierte
    python3 wikidata_sync.py --all     # alle Species
"""

import sys
import re
import time
import requests
import psycopg2
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Tuple

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
    "dbname":   env.get("PG_NAME"),
    "port":     int(env.get("DB_PORT", "5432")),
    "options":  "-c search_path=zoo,public",
}

WIKIDATA_SEARCH_URL = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL_URL = "https://query.wikidata.org/sparql"
API_DELAY           = 0.5

def normalize(name: str) -> str:
    if not name:
        return ""
    name = name.lower().replace("-", " ")
    return re.sub(r"\s+", " ", name).strip()

def search_by_latin(latin_name: str) -> Optional[Dict]:
    """Sucht Wikidata-Eintrag via SPARQL P225."""
    sparql = f"""
    SELECT ?item ?itemLabel WHERE {{
      ?item wdt:P225 "{latin_name}".
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "de,en". }}
    }} LIMIT 1
    """
    try:
        r = requests.get(
            WIKIDATA_SPARQL_URL,
            params={"query": sparql, "format": "json"},
            timeout=10,
            headers={"User-Agent": "ZooGuide/1.0 (thorsten@iborg.de)"}
        )
        r.raise_for_status()
        results = r.json().get("results", {}).get("bindings", [])
        if results:
            wikidata_id = results[0]["item"]["value"].split("/")[-1]
            label       = results[0].get("itemLabel", {}).get("value", "")
            time.sleep(API_DELAY)
            return {
                "wikidata_id": wikidata_id,
                "label_de":    label,
                "latin_name":  latin_name,
                "url":         f"https://www.wikidata.org/wiki/{wikidata_id}",
            }
    except Exception:
        pass
    time.sleep(API_DELAY)
    return None

def search_by_german(german_name: str) -> List[Dict]:
    """Sucht Kandidaten via deutschem Namen."""
    params = {
        "action":  "wbsearchentities",
        "search":  german_name,
        "language": "de",
        "type":    "item",
        "limit":   10,
        "format":  "json",
        "uselang": "de",
    }
    try:
        r = requests.get(
            WIKIDATA_SEARCH_URL, params=params, timeout=10,
            headers={"User-Agent": "ZooGuide/1.0 (thorsten@iborg.de)"}
        )
        r.raise_for_status()
        time.sleep(API_DELAY)
        return [
            {
                "wikidata_id": item.get("id"),
                "label_de":   item.get("label", ""),
                "description": item.get("description", ""),
                "url":        f"https://www.wikidata.org/wiki/{item.get('id')}",
            }
            for item in r.json().get("search", [])
        ]
    except Exception:
        time.sleep(API_DELAY)
        return []

def get_latin_name(wikidata_id: str) -> str:
    sparql = f"SELECT ?n WHERE {{ wd:{wikidata_id} wdt:P225 ?n. }} LIMIT 1"
    try:
        r = requests.get(
            WIKIDATA_SPARQL_URL,
            params={"query": sparql, "format": "json"},
            timeout=10,
            headers={"User-Agent": "ZooGuide/1.0 (thorsten@iborg.de)"}
        )
        r.raise_for_status()
        results = r.json().get("results", {}).get("bindings", [])
        time.sleep(API_DELAY)
        return results[0]["n"]["value"] if results else ""
    except Exception:
        time.sleep(API_DELAY)
        return ""

def is_animal_candidate(candidate: Dict) -> bool:
    desc = candidate.get("description", "").lower()
    animal_keywords = [
        "tier", "art ", "gattung", "familie", "animal", "species", "taxon",
        "vogel", "fisch", "säugetier", "reptil", "amphibi", "insekt",
        "krebstier", "spinne", "molluske", "ordnung", "klasse"
    ]
    exclude_keywords = [
        "stadt", "gemeinde", "straße", "person", "musiker", "film",
        "software", "spiel", "familienname", "vorname", "begriffsklärung",
        "unternehmen", "company", "library", "bundesstaat", "fußball"
    ]
    if any(w in desc for w in exclude_keywords):
        return False
    if any(w in desc for w in animal_keywords):
        return True
    return False

def load_species(conn, all_species: bool = False) -> List[Dict]:
    where = "" if all_species else "AND (id_valid IS NULL OR id_valid = FALSE)"
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, german_name, latin_name, wikidata_id
            FROM species
            WHERE 1=1 {where}
            ORDER BY id
        """)
        rows = cur.fetchall()
    return [
        {"id": r[0], "german_name": r[1], "latin_name": r[2], "wikidata_id": r[3]}
        for r in rows
    ]

def process_species(s: Dict) -> Tuple[Optional[Dict], List[Dict], str]:
    german_name = s["german_name"]
    latin_name  = s.get("latin_name")

    # Strategie 1: via latin_name (zuverlässig)
    if latin_name:
        result = search_by_latin(latin_name)
        if result:
            return (
                {**result, "location_id": s["id"], "name": german_name},
                [result],
                "confirmed"
            )

    # Strategie 2: via deutschen Namen
    candidates = search_by_german(german_name)
    if not candidates:
        return None, [], "not_found"

    animal_candidates = []
    for c in candidates[:5]:
        if is_animal_candidate(c):
            c["latin_name"] = get_latin_name(c["wikidata_id"])
            animal_candidates.append(c)
            time.sleep(API_DELAY)

    if not animal_candidates:
        return None, candidates[:3], "review"

    exact = [c for c in animal_candidates
             if normalize(c["label_de"]) == normalize(german_name)]

    if len(exact) == 1:
        return (
            {**exact[0], "location_id": s["id"], "name": german_name},
            animal_candidates,
            "confirmed"
        )
    elif len(exact) > 1:
        return None, exact, "review"
    elif len(animal_candidates) == 1:
        return None, animal_candidates, "review"
    else:
        return None, animal_candidates[:3], "review"

def escape(v: str) -> str:
    return v.replace("'", "''") if v else ""

def generate_sql(confirmed: List[Dict]) -> str:
    lines = [
        "-- Wikidata Import Script",
        f"-- Generiert von wikidata_sync.py am {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "SET search_path TO zoo, public;",
        "BEGIN;",
        "",
    ]
    for m in confirmed:
        latin       = escape(m.get("latin_name", ""))
        wikidata_id = m["wikidata_id"]
        species_id  = m["location_id"]
        name        = escape(m["name"])
        lines.append(f"-- {name} → {wikidata_id} ({latin})")
        lines.append(f"UPDATE species")
        lines.append(f"  SET wikidata_id = '{wikidata_id}',")
        lines.append(f"      latin_name  = '{latin}'")
        lines.append(f"  WHERE id = {species_id};")
        lines.append("")
    lines += ["COMMIT;", ""]
    return "\n".join(lines)

def generate_review(review_cases: List[Dict]) -> str:
    lines = [
        "Zoo Guide — Wikidata Review",
        f"Erstellt: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Fälle: {len(review_cases)}",
        "=" * 70,
        "",
    ]
    for case in review_cases:
        lines.append(f"Species ID:  {case['id']}")
        lines.append(f"Name:        {case['german_name']}")
        lines.append(f"Latin:       {case.get('latin_name') or '—'}")
        lines.append(f"Status:      {case['status']}")
        lines.append("Kandidaten:")
        for i, c in enumerate(case["candidates"], 1):
            latin = c.get("latin_name", "—")
            lines.append(f"  {i}. {c['wikidata_id']} — {c['label_de']}")
            lines.append(f"     Latin: {latin}")
            if c.get("description"):
                lines.append(f"     Beschr: {c['description']}")
            lines.append(f"     URL:   {c['url']}")
        if case["candidates"]:
            c = case["candidates"][0]
            latin = escape(c.get("latin_name", ""))
            lines.append(f"\nSQL: UPDATE species SET wikidata_id = '{c['wikidata_id']}', latin_name = '{latin}' WHERE id = {case['id']};")
        lines.append("-" * 70)
        lines.append("")
    return "\n".join(lines)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Species Wikidata Sync")
    parser.add_argument("--all", action="store_true",
                        help="Alle Species prüfen (auch bereits validierte)")
    args = parser.parse_args()

    print("🦁 Zoo Guide — Wikidata Sync")
    print(f"   Modus: {'alle Species' if args.all else 'nur nicht-validierte'}")
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

    if not species_list:
        print("\n✅ Alle Species bereits validiert!")
        sys.exit(0)

    confirmed  = []
    review     = []
    not_found  = []

    print(f"\n🔍 Verarbeite {len(species_list)} Species...")
    print()

    for i, s in enumerate(species_list, 1):
        label = f"[{i:3}/{len(species_list)}] {s['german_name']}"
        if s.get("latin_name"):
            label += f" ({s['latin_name']})"
        print(f"  {label}", end=" ... ")

        match, candidates, status = process_species(s)

        if status == "confirmed" and match:
            print(f"✅ {match['wikidata_id']}")
            confirmed.append(match)
        elif status == "review":
            print(f"⚠️  Review ({len(candidates)} Kandidaten)")
            review.append({**s, "status": status, "candidates": candidates})
        else:
            print("❌ Nicht gefunden")
            not_found.append({**s, "status": "not_found", "candidates": []})

    print()
    print("=" * 50)
    print(f"✅ Gefunden:       {len(confirmed)}")
    print(f"⚠️  Review:        {len(review)}")
    print(f"❌ Nicht gefunden: {len(not_found)}")

    if confirmed:
        sql = generate_sql(confirmed)
        sql_path = Path(__file__).parent / "import_wikidata.sql"
        sql_path.write_text(sql, encoding="utf-8")
        print(f"\n📄 SQL: {sql_path}")

    all_review = review + not_found
    if all_review:
        review_text = generate_review(all_review)
        review_path = Path(__file__).parent / "review_needed.txt"
        review_path.write_text(review_text, encoding="utf-8")
        print(f"📋 Review: {review_path} ({len(all_review)} Fälle)")

    print("\n✅ Fertig!")

if __name__ == "__main__":
    main()
