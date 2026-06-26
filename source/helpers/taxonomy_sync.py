"""
helpers/taxonomy_sync.py

Taxonomy-Sync: prüft ob alle tax_*_id-QIDs der Species in zoo.taxonomy
eingetragen sind — und fragt nur die fehlenden bei Wikidata ab.
Wird beim Publish-/Export-Flow aufgerufen (nicht beim App-Start).

Gibt die Anzahl neu eingetragener Zeilen zurück.
Schlägt Wikidata fehl, wird nur gewarnt — der Export läuft trotzdem weiter.
"""

import logging
import time
import requests

WIKIDATA_API = "https://www.wikidata.org/w/api.php"
BATCH_SIZE   = 50

RANK_QID_MAP = {
    "Q36642":   "kingdom", "Q38348":   "phylum",  "Q3965313": "phylum",
    "Q35409":   "class",   "Q10861375":"class",
    "Q36602":   "order",   "Q2136103": "order",
    "Q37581":   "family",  "Q5868144": "family",  "Q164280":  "family",
    "Q227936":  "family",  "Q34740":   "genus",   "Q3731207": "genus",
}


def _resolve_rank(rank_qid: str) -> str:
    return RANK_QID_MAP.get(rank_qid, "family")


def _batch_wikidata(qids: list) -> dict:
    """Holt Namen + Rang für eine Liste von QIDs von Wikidata."""
    try:
        resp = requests.get(
            WIKIDATA_API,
            params={
                "action": "wbgetentities",
                "ids":    "|".join(qids),
                "props":  "labels|claims",
                "languages": "la|en",
                "format": "json",
            },
            timeout=30,
            headers={"User-Agent": "OpenZooData/1.0 (thorsten@codelab.cafe)"}
        )
        data = resp.json()
    except Exception as e:
        logging.warning(f"Taxonomy-Sync: Wikidata-Fehler: {e}")
        return {}

    results = {}
    for qid, entity in data.get("entities", {}).items():
        if entity.get("missing"):
            continue
        claims = entity.get("claims", {})

        # Latin name via P225
        latin_name = None
        p225 = claims.get("P225", [])
        if p225:
            latin_name = (p225[0].get("mainsnak", {})
                                  .get("datavalue", {})
                                  .get("value"))
        if not latin_name:
            labels = entity.get("labels", {})
            latin_name = (labels.get("la", {}).get("value") or
                          labels.get("en", {}).get("value"))
        if not latin_name:
            continue

        # Rank via P105
        rank = "family"
        p105 = claims.get("P105", [])
        if p105:
            rank_qid = (p105[0].get("mainsnak", {})
                                .get("datavalue", {})
                                .get("value", {})
                                .get("id", ""))
            rank = _resolve_rank(rank_qid)

        results[qid] = {"name": latin_name, "rank": rank}
    return results


def sync_missing_taxonomy(pg) -> int:
    """
    Prüft welche tax_*_id-QIDs der Species noch nicht in zoo.taxonomy stehen
    und fragt nur die fehlenden bei Wikidata ab.

    Args:
        pg: offene psycopg2-Connection (zoo-Schema)

    Returns:
        Anzahl neu eingetragener Taxonomy-Zeilen (0 wenn alles aktuell war)
    """
    try:
        with pg.cursor() as cur:
            # Alle QIDs die in species referenziert werden
            cur.execute("""
                SELECT DISTINCT unnest(ARRAY[
                    tax_kingdom_id, tax_phylum_id, tax_class_id,
                    tax_order_id,   tax_family_id, tax_genus_id
                ]) AS qid
                FROM zoo.species
                WHERE id_valid = TRUE
            """)
            species_qids = {row[0] for row in cur.fetchall() if row[0]}

            # Bereits bekannte QIDs
            cur.execute("SELECT wikidata_id FROM zoo.taxonomy")
            existing_qids = {row[0] for row in cur.fetchall()}

        missing = sorted(species_qids - existing_qids)

        if not missing:
            logging.info("Taxonomy-Sync: alles vollständig, kein Wikidata-Call nötig")
            return 0

        logging.info(f"Taxonomy-Sync: {len(missing)} fehlende QIDs → Wikidata-Abfrage")

        batches  = [missing[i:i+BATCH_SIZE]
                    for i in range(0, len(missing), BATCH_SIZE)]
        inserted = 0

        for i, batch in enumerate(batches):
            results = _batch_wikidata(batch)
            with pg.cursor() as cur:
                for qid in batch:
                    if qid in results:
                        r = results[qid]
                        cur.execute("""
                            INSERT INTO zoo.taxonomy (wikidata_id, rank, name)
                            VALUES (%s, %s, %s)
                            ON CONFLICT DO NOTHING
                        """, (qid, r["rank"], r["name"]))
                        inserted += 1
            pg.commit()
            if i < len(batches) - 1:
                time.sleep(0.5)

        logging.info(f"Taxonomy-Sync: {inserted} neue Einträge")
        return inserted

    except Exception:
        logging.exception("Taxonomy-Sync fehlgeschlagen — Export läuft weiter")
        return 0
