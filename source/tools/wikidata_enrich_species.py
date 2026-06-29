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

import os
import sys
from pathlib import Path

# Zentrale .env-Ladung -> os.environ (vereinheitlicht, siehe helpers/env_loader.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from helpers.env_loader import load_env
try:
    load_env()
except RuntimeError:
    pass  # Variablen evtl. schon vom Eltern-Prozess vererbt


import sys
import time
import argparse
import requests
import psycopg2
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# ─── Konfiguration ────────────────────────────────────────────────────────────


DB_CONFIG = {
    "host":     os.environ.get("PG_HOST"),
    "user":     os.environ.get("PG_USER"),
    "password": os.environ.get("PG_PASSWORD"),
    "dbname":   os.environ.get("PG_NAME"),
    "port":     int(os.environ.get("DB_PORT", "5432")),
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

def resolve_qid_by_latin_name(latin_name: str) -> str | None:
    """
    Sucht via P225 (taxon name) die Wikidata-QID zu einem lateinischen Namen.
    Gibt die QID zurück (z.B. "Q26012") oder None.

    Bei 0 oder >1 Treffern -> None (kein Rateschluss; Aufrufer fällt auf die
    DB-wikidata_id zurück). So wird keine falsche Art zugeordnet.
    """
    if not latin_name or not latin_name.strip():
        return None

    name = latin_name.strip().replace('"', '\\"')
    sparql = f'''
    SELECT ?taxon WHERE {{
      ?taxon wdt:P225 "{name}".
    }} LIMIT 5
    '''
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

        qids = {b["taxon"]["value"].split("/")[-1] for b in bindings if "taxon" in b}
        if len(qids) == 1:
            return qids.pop()
        # 0 oder mehrdeutig -> kein Treffer
        return None
    except Exception:
        time.sleep(API_DELAY)
        return None


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

    except Exception:
        time.sleep(API_DELAY)
        return {}

# ─── Datenbank ────────────────────────────────────────────────────────────────

def load_species(conn, mode: str = "missing") -> List[Dict]:
    """
    mode='missing'  -> Tiere ohne Taxonomie (tax_class_id IS NULL),
                       unabhängig von wiki_fetched_at. Erfasst auch Tiere
                       deren früherer Abruf nichts lieferte.
    mode='new'      -> nur nie abgerufene (wiki_fetched_at IS NULL).
    mode='all'      -> alle validen Species (komplettes Refresh).
    """
    if mode == "all":
        where = ""
    elif mode == "new":
        where = "AND wiki_fetched_at IS NULL"
    else:  # missing
        where = "AND tax_class_id IS NULL"

    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT id, german_name, wikidata_id, latin_name
            FROM species
            WHERE id_valid = TRUE
              AND wikidata_id IS NOT NULL
              {where}
            ORDER BY id
        """)
        rows = cur.fetchall()
    return [{"id": r[0], "name": r[1], "wikidata_id": r[2], "latin_name": r[3]}
            for r in rows]


def write_species(conn, species_id: int, data: dict) -> None:
    """
    Schreibt Taxonomie/IUCN/GBIF einer Species direkt in die DB.
    wiki_fetched_at wird IMMER auf NOW() gesetzt — auch wenn data leer ist —
    damit Items ohne Wikidata-Taxonomie (z.B. Haustierrassen ohne P171)
    nicht bei jedem Lauf erneut abgefragt werden.
    Pro Species ein eigener Commit: robust gegen Abbruch.
    """
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE species SET
                tax_kingdom_id           = %s,
                tax_phylum_id            = %s,
                tax_class_id             = %s,
                tax_order_id             = %s,
                tax_family_id            = %s,
                tax_genus_id             = %s,
                iucn_status_id           = COALESCE(%s, iucn_status_id),
                iucn_population_trend_id = COALESCE(%s, iucn_population_trend_id),
                iucn_id                  = COALESCE(%s, iucn_id),
                gbif_taxon_key           = COALESCE(%s, gbif_taxon_key),
                wiki_fetched_at          = NOW()
            WHERE id = %s
        """, (
            data.get("tax_kingdom_id"),
            data.get("tax_phylum_id"),
            data.get("tax_class_id"),
            data.get("tax_order_id"),
            data.get("tax_family_id"),
            data.get("tax_genus_id"),
            data.get("iucn_status_id"),
            data.get("iucn_population_trend_id"),
            data.get("iucn_id"),
            data.get("gbif_taxon_key"),
            species_id,
        ))
    conn.commit()

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
        lines.append("UPDATE species SET")
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
        lines.append("    wiki_fetched_at          = NOW()")
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
                        help="Alle validen Species (komplettes Refresh, überschreibt vorhandene)")
    parser.add_argument("--new", action="store_true",
                        help="Nur nie abgerufene (wiki_fetched_at IS NULL)")
    parser.add_argument("--species", type=int, metavar="ID",
                        help="Nur eine einzelne Species-ID (zum Testen)")
    args = parser.parse_args()

    if args.all:
        mode = "all"
    elif args.new:
        mode = "new"
    else:
        mode = "missing"  # Default: Tiere ohne Taxonomie

    mode_label = {"all": "alle validen (Refresh)",
                  "new": "nur nie abgerufene",
                  "missing": "ohne Taxonomie"}[mode]

    print("🌿 Zoo Guide — Wikidata Species Anreicherung")
    print(f"   Modus: {mode_label}" + (f" | nur ID {args.species}" if args.species else ""))
    print("   Schreibt direkt in die Datenbank.")
    print("=" * 50)

    print("\n📡 Verbinde mit Datenbank...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("   ✅ Verbunden")
    except Exception as e:
        print(f"   ❌ {e}")
        sys.exit(1)

    species_list = load_species(conn, mode=mode)

    # Optional auf eine einzelne ID einschränken (Test)
    if args.species is not None:
        species_list = [s for s in species_list if s["id"] == args.species]
        if not species_list:
            # Auch wenn sie nicht im Filter ist: direkt laden (Test erzwingen)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, german_name, wikidata_id, latin_name FROM species
                    WHERE id = %s AND wikidata_id IS NOT NULL
                """, (args.species,))
                row = cur.fetchone()
            if row:
                species_list = [{"id": row[0], "name": row[1],
                                 "wikidata_id": row[2], "latin_name": row[3]}]

    print(f"   {len(species_list)} Species zu verarbeiten")

    if not species_list:
        print("\n✅ Nichts zu tun!")
        conn.close()
        sys.exit(0)

    print(f"\n🔍 Rufe Wikidata-Daten ab ({len(species_list)} Species)...")
    print()

    results      = []
    no_data      = []
    partial_data = []

    for i, s in enumerate(species_list, 1):
        print(f"  [{i:3}/{len(species_list)}] {s['name']} ({s['wikidata_id']})", end=" ... ")

        # Primär: QID über lateinischen Namen auflösen (P225).
        # Rückfall: die in der DB hinterlegte wikidata_id.
        resolved_qid = resolve_qid_by_latin_name(s.get("latin_name"))
        used_qid = resolved_qid or s["wikidata_id"]
        qid_source = "Name" if resolved_qid else "DB-QID"

        data = fetch_species_data(used_qid)

        # Wenn die namensaufgelöste QID keine Taxonomie brachte, mit der
        # DB-QID gegenprüfen (nur falls beide unterschiedlich sind).
        if resolved_qid and resolved_qid != s["wikidata_id"]:
            has_tax_resolved = any(data.get(f"tax_{l}_id") for l in
                                   ["kingdom","phylum","class","order","family","genus"])
            if not has_tax_resolved:
                fallback = fetch_species_data(s["wikidata_id"])
                if any(fallback.get(f"tax_{l}_id") for l in
                       ["kingdom","phylum","class","order","family","genus"]):
                    data = fallback
                    qid_source = "DB-QID (Fallback)"

        print(f"[{qid_source}: {used_qid}]", end=" ")

        if not data:
            # Kein Wikidata-Treffer: wiki_fetched_at trotzdem setzen, damit
            # dieses Item nicht bei jedem Lauf erneut abgefragt wird.
            try:
                write_species(conn, s["id"], {})
            except Exception:
                conn.rollback()
            print("❌ keine Wikidata-Daten (markiert)")
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

        # Direkt in die DB schreiben (pro Species ein Commit)
        try:
            write_species(conn, s["id"], data)
            status_parts.append("→ DB ✅")
        except Exception as e:
            conn.rollback()
            status_parts.append(f"→ DB-FEHLER: {e}")
            no_data.append(s)
            print(" | ".join(status_parts))
            continue

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

    conn.close()

    print(f"\n💾 {len(results)} Species direkt in die DB geschrieben.")
    if results:
        print("\nNächster Schritt:")
        print("  → python3 tools/export_sqlite.py --all  (SQLite neu generieren)")

    print("\n✅ Fertig!")

if __name__ == "__main__":
    main()
