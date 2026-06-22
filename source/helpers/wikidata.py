"""
helpers/wikidata.py

Wiederverwendbare Wikidata-SPARQL-Hilfsfunktionen für den Request-Context
(kein DB-Connect, kein sys.exit, kein argparse — reines HTTP + Parsing).

Extrahiert und erweitert aus source/tools/wikidata_enrich_species.py.
Ergänzt: P225 (latin_name / taxon name) fehlt im Original.
"""

import time
import logging
import requests
from typing import Dict, Optional

WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
API_DELAY       = 0.75   # Höfliche Pause zwischen SPARQL-Calls

# Taxonomie-Ebenen (P105-Werte)
TAX_RANKS = {
    "Q36732": "kingdom",
    "Q38348": "phylum",
    "Q37517": "class",
    "Q36602": "order",
    "Q35409": "family",
    "Q34740": "genus",
}


def fetch_species_data(wikidata_id: str) -> Dict:
    """
    Ruft in einem SPARQL-Call ab:
    - latin_name (P225 taxon name)
    - Taxonomie: Kingdom, Phylum, Class, Order, Family, Genus (via P171)
    - IUCN Status (P141)
    - Populationstrend (P2241)
    - IUCN Taxon ID (P627)
    - GBIF Taxon Key (P846)

    Gibt ein Dict zurück (alle Schlüssel vorhanden, ggf. None).
    Bei Fehler: leeres Dict {}.
    """
    sparql = f"""
    SELECT ?latinName ?rank ?taxon ?iucnStatus ?popTrend ?iucnId ?gbifKey WHERE {{
      # Lateinischer Name (P225)
      OPTIONAL {{ wd:{wikidata_id} wdt:P225 ?latinName. }}
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
      # IUCN Taxon ID
      OPTIONAL {{ wd:{wikidata_id} wdt:P627 ?iucnId. }}
      # GBIF Taxon Key
      OPTIONAL {{ wd:{wikidata_id} wdt:P846 ?gbifKey. }}
    }}
    """
    try:
        r = requests.get(
            WIKIDATA_SPARQL,
            params={"query": sparql, "format": "json"},
            timeout=15,
            headers={"User-Agent": "OpenZooData/1.0 (thorsten@codelab.cafe)"}
        )
        r.raise_for_status()
        bindings = r.json().get("results", {}).get("bindings", [])
        time.sleep(API_DELAY)

        result = {
            "latin_name":                None,
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
            # Lateinischer Name (P225)
            if "latinName" in b and not result["latin_name"]:
                result["latin_name"] = b["latinName"]["value"]

            # Taxonomie
            if "rank" in b and "taxon" in b:
                rank_id  = b["rank"]["value"].split("/")[-1]
                taxon_id = b["taxon"]["value"].split("/")[-1]
                level    = TAX_RANKS.get(rank_id)
                if level and not result[f"tax_{level}_id"]:
                    result[f"tax_{level}_id"] = taxon_id

            # IUCN Status
            if "iucnStatus" in b and not result["iucn_status_id"]:
                result["iucn_status_id"] = b["iucnStatus"]["value"].split("/")[-1]

            # Populationstrend
            if "popTrend" in b and not result["iucn_population_trend_id"]:
                result["iucn_population_trend_id"] = b["popTrend"]["value"].split("/")[-1]

            # IUCN Taxon ID
            if "iucnId" in b and not result["iucn_id"]:
                result["iucn_id"] = b["iucnId"]["value"]

            # GBIF Taxon Key
            if "gbifKey" in b and not result["gbif_taxon_key"]:
                try:
                    result["gbif_taxon_key"] = int(b["gbifKey"]["value"])
                except (ValueError, TypeError):
                    pass

        return result

    except Exception:
        logging.exception(
            f"Wikidata SPARQL-Fehler für {wikidata_id}")
        time.sleep(API_DELAY)
        return {}


def build_species_filename(wikidata_id: str, latin_name: Optional[str]) -> str:
    """
    Erzeugt den Dateinamen für ein Species-Icon.
    Konvention: <WikidataID>_<Lateinischer_Name>.png
    Leerzeichen → Unterstrich, Sonderzeichen entfernt.
    Fallback falls kein latin_name: <WikidataID>.png
    """
    if not latin_name:
        return f"{wikidata_id}.png"
    safe = latin_name.replace(" ", "_").replace("/", "_")
    # nur alphanumerisch + Unterstrich erlaubt
    safe = "".join(c for c in safe if c.isalnum() or c == "_")
    return f"{wikidata_id}_{safe}.png"
