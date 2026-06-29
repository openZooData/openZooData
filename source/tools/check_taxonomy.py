#!/usr/bin/env python3
"""
check_taxonomy.py
-----------------
Prüft welche Taxonomie-QIDs in species vorhanden aber nicht in
der taxonomy Tabelle eingetragen sind.
Fragt fehlende QIDs bei Wikidata im Batch ab (50 auf einmal).

Aufruf:
    python3 tools/check_taxonomy.py           # prüfen + eintragen
    python3 tools/check_taxonomy.py --dry-run # nur prüfen
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


import argparse
import requests
import psycopg2
import psycopg2.extras
from pathlib import Path
import time


PG_CONFIG = {
    "host":     os.environ.get("PG_HOST"),
    "user":     os.environ.get("PG_USER"),
    "password": os.environ.get("PG_PASSWORD"),
    "dbname":   os.environ.get("PG_NAME"),
    "port":     int(os.environ.get("PG_PORT", os.environ.get("DB_PORT", "5432"))),
    "options":  "-c search_path=zoo,public",
}

RANK_QID_MAP = {
    "Q36642": "kingdom", "Q38348": "phylum", "Q3965313": "phylum",
    "Q35409": "class", "Q10861375": "class",
    "Q36602": "order", "Q2136103": "order",
    "Q37581": "family", "Q5868144": "family", "Q164280": "family", "Q227936": "family",
    "Q34740": "genus", "Q3731207": "genus",
}

def resolve_rank(rank_qid):
    return RANK_QID_MAP.get(rank_qid, "family")

def batch_wikidata(qids):
    url = "https://www.wikidata.org/w/api.php"
    params = {
        "action": "wbgetentities", "ids": "|".join(qids),
        "props": "labels|claims", "languages": "la|en", "format": "json"
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
    except Exception as e:
        print(f"  Wikidata Fehler: {e}")
        return {}

    results = {}
    for qid, entity in data.get("entities", {}).items():
        if entity.get("missing"):
            continue
        claims = entity.get("claims", {})
        latin_name = None
        p225 = claims.get("P225", [])
        if p225:
            latin_name = p225[0].get("mainsnak", {}).get("datavalue", {}).get("value")
        if not latin_name:
            labels = entity.get("labels", {})
            latin_name = (labels.get("la", {}).get("value") or labels.get("en", {}).get("value"))
        if not latin_name:
            continue
        rank = "family"
        p105 = claims.get("P105", [])
        if p105:
            rank_qid = p105[0].get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id", "")
            rank = resolve_rank(rank_qid)
        results[qid] = {"name": latin_name, "rank": rank}
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = psycopg2.connect(**PG_CONFIG)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT DISTINCT unnest(ARRAY[
            tax_kingdom_id, tax_phylum_id, tax_class_id,
            tax_order_id, tax_family_id, tax_genus_id
        ]) AS qid FROM species WHERE id_valid = TRUE
    """)
    species_qids = {row["qid"] for row in cur.fetchall() if row["qid"]}

    cur.execute("SELECT wikidata_id FROM taxonomy")
    existing_qids = {row["wikidata_id"] for row in cur.fetchall()}

    missing = sorted(species_qids - existing_qids)
    print(f"Species Taxonomie QIDs gesamt:  {len(species_qids)}")
    print(f"Bereits in taxonomy Tabelle:    {len(existing_qids)}")
    print(f"Fehlend:                        {len(missing)}")

    if not missing:
        print("Alles vollständig.")
        cur.close(); conn.close(); return

    if args.dry_run:
        print(f"Dry-run — {len(missing)} QIDs würden abgefragt.")
        cur.close(); conn.close(); return

    BATCH_SIZE = 50
    batches = [missing[i:i+BATCH_SIZE] for i in range(0, len(missing), BATCH_SIZE)]
    inserted = 0
    not_found = 0

    print(f"\nStarte Wikidata Abfrage ({len(batches)} Batches)...")
    for i, batch in enumerate(batches):
        print(f"  Batch {i+1}/{len(batches)}...", end=" ", flush=True)
        results = batch_wikidata(batch)
        batch_inserted = 0
        for qid in batch:
            if qid in results:
                r = results[qid]
                try:
                    cur.execute("""
                        INSERT INTO taxonomy (wikidata_id, rank, name)
                        VALUES (%s, %s, %s) ON CONFLICT DO NOTHING
                    """, (qid, r["rank"], r["name"]))
                    inserted += 1; batch_inserted += 1
                except Exception as e:
                    conn.rollback(); print(f"\n  DB Fehler {qid}: {e}")
            else:
                not_found += 1
        conn.commit()
        print(f"✓ {batch_inserted} eingetragen")
        if i < len(batches) - 1:
            time.sleep(0.5)

    cur.execute("SELECT COUNT(*) AS total FROM taxonomy")
    total = cur.fetchone()["total"]
    print(f"\nFertig: {inserted} eingetragen, {not_found} nicht gefunden")
    print(f"taxonomy Tabelle gesamt: {total} Einträge")
    cur.close(); conn.close()

if __name__ == "__main__":
    main()
