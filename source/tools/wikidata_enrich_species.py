#!/usr/bin/env python3
"""
wikidata_enrich_species.py
--------------------------
Reichert species mit Taxonomie und IUCN-Daten von Wikidata an.

Abgerufen wird:
  - Taxonomie: Kingdom, Phylum, Class, Order, Family, Genus (via P171)
  - IUCN Status (via P141)
  - Populationstrend (via P2241)
  - IUCN Taxon ID (via P627) → Link zu iucnredlist.org
  - GBIF Taxon Key (via P846) → Link zu gbif.org

Nur Species mit:
  - id_valid = TRUE
  - wikidata_id IS NOT NULL
  - wiki_fetched_at IS NULL (noch nicht abgerufen)

Aufruf:
    python3 wikidata_enrich_species.py           # nur nicht-angereicherte
    python3 wikidata_enrich_species.py --all     # alle validen Species

Output:
    enrich_species.sql — SQL zum Einspielen in Postico
"""

import sys
import re
import time
import argparse
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
    "dbname":   env.get("PG_NAME"),
    "port":     int(env.get("DB_PORT", "5432")),
    "options":  "-c search_path=zoo,public",
}

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
API_DELAY       = 0.75  # etwas mehr Pause für SPARQL

# Taxonomie-Ebenen in Reihenfolge
TAX_RANKS = {
    "Q36732":  "kingdom",   # Königreich
    "Q38348":  "phylum",    # Stamm
    "Q37517":  "class",     # Klasse
    "Q36602":  "order",     # Ordnung
    "Q35409":  "family",    # Familie
    "Q34740":  "genus",     # Gattung
}

# ─── Wikidata SPARQL ──────────────────────────────────────────────────────────

def fetch_species_data(wikidata_id: str) -> Dict:
    """
    Ruft in einem SPARQL-Call ab:
    - Taxonomie (alle Ebenen via P171 parent taxon)
    - IUCN Status (P141)
    - Populationstrend (P2241)
    - IUCN Taxon ID (P627)
    - GBIF Taxon Key (P846)
    """
    sparql = f"""
    SELECT ?rank ?taxon ?iucnStatus ?popTrend ?iucnId ?gbifKey WHERE {{
      # Taxonomie — alle Parent Taxa
      OPTIONAL {{
        wd:{wikidata_id} wdt:P171+ ?taxon.
        ?taxon wdt:P105 ?rank.
        VALUES ?rank {{ wd:Q36732 wd:Q38348 wd:Q37517 wd:Q36602 wd:Q35409 wd:Q34740 }}
      }}
      # IUCN Status
      OPTIONAL {{ wd:{wikidata_id} wdt:P141 ?iucnStatus. }}
      # Populationstrend
      OPTIONAL {{ wd:{wikidata_id} wdt:P2241 ?popTrend. }}
      # IUCN Taxon ID (P627) → https://www.iucnredlist.org/species/<id>
      OPTIONAL {{ wd:{wikidata_id} wdt:P627 ?iucnId. }}
      # GBIF Taxon Key (P846) → https://www.gbif.org/species/<key>
      OPTIONAL {{ wd:{wikidata_id} wdt:P846 ?gbifKey. }}
    }}
    """
    try:
        r = requests.get(
            WIKIDATA_SPARQL,
            params={"query": sparql, "format": "json"},
            timeout=15,
            headers={"User-Agent": "ZooGuide/1.0 (thorsten@iborg.de)"}
        )
        r.raise_for_status()
        bindings = r.json().get("results", {}).get("bindings", [])
        time.sleep(API_DELAY)

        result = {
            "tax_kingdom_id":            None,
            "tax_phylum_id":             None,
            "tax_class_id":              None,
            "tax_order_id":              None,
            "tax_family_id":             None,
            "tax_genus_id":              None,
            "iucn_status_id":            None,
            "iucn_population_trend_id":  None,
            "iucn_id":                   None,
            "gbif_taxon_key":            None,
        }

        for b in bindings:
            # Taxonomie
            if "rank" in b and "taxon" in b:
                rank_id  = b["rank"]["value"].split("/")[-1]
                taxon_id = b["taxon"]["value"].split("/")[-1]
                level    = TAX_RANKS.get(rank_id)
                if level:
                    result[f"tax_{level}_id"] = taxon_id

            # IUCN Status
            if "iucnStatus" in b and not result["iucn_status_id"]:
                result["iucn_status_id"] = b["iucnStatus"]["value"].split("/")[-1]

            # Populationstrend
            if "popTrend" in b and not result["iucn_population_trend_id"]:
                result["iucn_population_trend_id"] = b["popTrend"]["value"].split("/")[-1]

            # IUCN Taxon ID (P627)
            if "iucnId" in b and not result["iucn_id"]:
                result["iucn_id"] = b["iucnId"]["value"]

            # GBIF Taxon Key (P846)
            if "gbifKey" in b and not result["gbif_taxon_key"]:
                try:
                    result["gbif_taxon_key"] = int(b["gbifKey"]["value"])
                except (ValueError, TypeError):
                    pass

        return result

    except Exception as e:
        time.sleep(API_DELAY)
        return {}

# ─── Datenbank ────────────────────────────────────────────────────────────────

def load_species(conn, all_species: bool = False) -> List[Dict]:
    where = "" if all_species else "AND wiki_fetched_at IS NULL"
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, german_name, wikidata_id
            FROM species
            WHERE id_valid = TRUE
              AND wikidata_id IS NOT NULL
              {where}
            ORDER BY id
        """)
        rows = cur.fetchall()
    return [{"id": r[0], "name": r[1], "wikidata_id": r[2]} for r in rows]

# ─── SQL generieren ───────────────────────────────────────────────────────────

def escape(v: str) -> str:
    return v.replace("'", "''") if v else ""

def generate_sql(results: List[Dict]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "-- ============================================================",
        "-- Wikidata Anreicherung: Taxonomie + IUCN + GBIF",
        f"-- Generiert: {now}",
        f"-- {len(results)} Species",
        "-- ============================================================",
        "",
        "SET search_path TO zoo, public;",
        "BEGIN;",
        "",
        "-- Spalten anlegen falls nicht vorhanden",
        "ALTER TABLE species ADD COLUMN IF NOT EXISTS iucn_id VARCHAR(20);",
        "",
    ]

    for r in results:
        def val(v):
            return f"'{escape(str(v))}'" if v is not None else "NULL"

        lines.append(f"-- {r['name']} ({r['wikidata_id']})")
        lines.append(f"UPDATE species SET")
        lines.append(f"    tax_kingdom_id           = {val(r.get('tax_kingdom_id'))},")
        lines.append(f"    tax_phylum_id            = {val(r.get('tax_phylum_id'))},")
        lines.append(f"    tax_class_id             = {val(r.get('tax_class_id'))},")
        lines.append(f"    tax_order_id             = {val(r.get('tax_order_id'))},")
        lines.append(f"    tax_family_id            = {val(r.get('tax_family_id'))},")
        lines.append(f"    tax_genus_id             = {val(r.get('tax_genus_id'))},")
        lines.append(f"    iucn_status_id           = {val(r.get('iucn_status_id'))},")
        lines.append(f"    iucn_population_trend_id = {val(r.get('iucn_population_trend_id'))},")
        lines.append(f"    iucn_id                  = {val(r.get('iucn_id'))},")
        lines.append(f"    gbif_taxon_key           = {val(r.get('gbif_taxon_key'))},")
        lines.append(f"    wiki_fetched_at          = NOW()")
        lines.append(f"WHERE id = {r['id']};")
        lines.append("")

    lines += [
        "-- Prüfung",
        "SELECT",
        "    COUNT(*) AS gesamt,",
        "    COUNT(tax_kingdom_id) AS mit_taxonomie,",
        "    COUNT(iucn_status_id) AS mit_iucn,",
        "    COUNT(iucn_id) AS mit_iucn_id,",
        "    COUNT(gbif_taxon_key) AS mit_gbif_key",
        "FROM species WHERE id_valid = TRUE;",
        "",
        "COMMIT;",
    ]
    return "\n".join(lines)

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Wikidata Species Anreicherung")
    parser.add_argument("--all", action="store_true",
                        help="Alle validen Species anreichern (auch bereits geholte)")
    args = parser.parse_args()

    print("🌿 Zoo Guide — Wikidata Species Anreicherung")
    print(f"   Modus: {'alle validen' if args.all else 'nur nicht-angereicherte'}")
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
    print(f"   {len(species_list)} Species zu verarbeiten")

    if not species_list:
        print("\n✅ Alle Species bereits angereichert!")
        sys.exit(0)

    print(f"\n🔍 Rufe Wikidata-Daten ab ({len(species_list)} Species)...")
    print()

    results      = []
    no_data      = []
    partial_data = []

    for i, s in enumerate(species_list, 1):
        print(f"  [{i:3}/{len(species_list)}] {s['name']} ({s['wikidata_id']})", end=" ... ")

        data = fetch_species_data(s["wikidata_id"])

        if not data:
            print("❌ Fehler")
            no_data.append(s)
            continue

        has_tax  = any(data.get(f"tax_{l}_id") for l in
                       ["kingdom","phylum","class","order","family","genus"])
        has_iucn = bool(data.get("iucn_status_id"))

        status_parts = []
        if has_tax:  status_parts.append("Taxonomie ✅")
        if has_iucn: status_parts.append("IUCN ✅")
        if not has_tax and not has_iucn:
            status_parts.append("keine Daten")

        print(" | ".join(status_parts))

        entry = {**s, **data}
        results.append(entry)

        if not has_tax or not has_iucn:
            partial_data.append({"name": s["name"], "wikidata_id": s["wikidata_id"],
                                  "has_tax": has_tax, "has_iucn": has_iucn})

    # Zusammenfassung
    print()
    print("=" * 50)
    with_tax   = sum(1 for r in results if r.get("tax_kingdom_id"))
    with_iucn  = sum(1 for r in results if r.get("iucn_status_id"))
    with_trend = sum(1 for r in results if r.get("iucn_population_trend_id"))
    with_iucn_id = sum(1 for r in results if r.get("iucn_id"))
    with_gbif  = sum(1 for r in results if r.get("gbif_taxon_key"))
    print(f"✅ Verarbeitet:     {len(results)}")
    print(f"   Mit Taxonomie:  {with_tax}")
    print(f"   Mit IUCN:       {with_iucn}")
    print(f"   Mit IUCN ID:    {with_iucn_id}")
    print(f"   Mit GBIF Key:   {with_gbif}")
    print(f"   Mit Trend:      {with_trend}")
    print(f"❌ Fehler:          {len(no_data)}")

    if partial_data:
        print(f"\n⚠️  Unvollständige Daten ({len(partial_data)}):")
        for p in partial_data[:10]:
            missing = []
            if not p["has_tax"]:  missing.append("Taxonomie")
            if not p["has_iucn"]: missing.append("IUCN")
            print(f"   {p['name']} — fehlt: {', '.join(missing)}")
        if len(partial_data) > 10:
            print(f"   ... und {len(partial_data)-10} weitere")

    # SQL generieren
    if results:
        sql = generate_sql(results)
        sql_path = Path(__file__).parent / "enrich_species.sql"
        sql_path.write_text(sql, encoding="utf-8")
        print(f"\n📄 SQL: {sql_path}")
        print(f"\nNächster Schritt:")
        print(f"  → enrich_species.sql in Postico einspielen")
        print(f"  → python3 tools/export_sqlite.py --all  (SQLite neu generieren)")

    print("\n✅ Fertig!")

if __name__ == "__main__":
    main()
