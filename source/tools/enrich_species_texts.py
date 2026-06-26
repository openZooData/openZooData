#!/usr/bin/env python3
"""
enrich_species_texts.py
-----------------------
Befüllt species_texts mit KI-generierten Texten via OpenAI API.
Der OpenAI-Key wird aus der .env Datei geladen (OPENAI_API_KEY_1 bis _4).
Setzt translations_valid = TRUE auf zoo.species wenn alle 5 Felder in
allen 12 Sprachen befüllt sind.

Beispiele:
    python3 tools/enrich_species_texts.py --lang de
    python3 tools/enrich_species_texts.py --lang de --dry-run
    python3 tools/enrich_species_texts.py --lang de --shard-count 4 --shard-index 0
"""

import argparse
import time
import logging
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def load_env():
    env = {}
    for path in [Path.home() / ".env"]:
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
            break
    return env


env = load_env()


PG_CONFIG = {
    "host": env.get("PG_HOST"),
    "user": env.get("PG_USER"),
    "password": env.get("PG_PASSWORD"),
    "dbname": env.get("PG_NAME", "zooguide"),
    "port": int(env.get("PG_PORT", "5432")),
    "options": "-c search_path=zoo,public",
}


FIELD_LENGTHS = {
    "description": "300 bis 500 Wörter",
    "habitat": "200 bis 300 Wörter",
    "food": "120 bis 220 Wörter",
    "family_life": "150 bis 250 Wörter",
    "fun_fact": "150 bis 250 Wörter",
}

LANGUAGES = {
    "de": "Deutsch",
    "en": "English",
    "es": "español",
    "fr": "français",
    "it": "italiano",
    "nl": "Nederlands",
    "pl": "polski",
    "pt": "português",
    "ru": "русский",
    "tr": "Türkçe",
    "uk": "українська",
    "zh_hans": "中文",
}

FIELDS = {"description", "food", "family_life", "habitat", "fun_fact"}


def build_prompt(field: str, german_name: str, latin_name: Optional[str],
                 iucn_code: Optional[str], language_name: str) -> str:
    length_text = FIELD_LENGTHS.get(field, "200 bis 300 Wörter")
    species_ref = f"„{german_name}“"
    if latin_name:
        species_ref += f" ({latin_name})"
    if iucn_code:
        species_ref += f", IUCN: {iucn_code}"

    questions = {
        "description": f"Beschreibe folgendes Tier für Zoobesucher: {species_ref}.",
        "food": f"Wovon ernährt sich folgendes Tier: {species_ref}?",
        "family_life": f"Wie lebt folgendes Tier in der Gruppe: {species_ref}?",
        "habitat": f"Wo lebt folgendes Tier in der Natur: {species_ref}?",
        "fun_fact": f"Was ist das Besonderste oder Überraschendste an folgendem Tier: {species_ref}?",
    }

    question = questions.get(field, f"Beschreibe {species_ref}.")

    return (
        f"{question} "
        f"Schreibe verständlich und interessant für Zoobesucher. "
        f"Schreibe etwa {length_text}. "
        f"Antworte auf {language_name}. "
        f"Antworte nur mit dem Text, ohne Überschrift oder Einleitung."
    )


def get_openai_key(shard_index: int = 0) -> str:
    """
    Lädt den OpenAI-Key aus der .env.
    Key-Mapping: shard_index 0 → OPENAI_API_KEY_1, index 1 → OPENAI_API_KEY_2, ...
    Fallback: OPENAI_API_KEY_1 wenn kein Shard-Index gesetzt.
    """
    key_name = f"OPENAI_API_KEY_{shard_index + 1}"
    api_key  = env.get(key_name)
    if not api_key:
        # Fallback auf Key 1 wenn spezifischer Key fehlt
        api_key = env.get("OPENAI_API_KEY_1")
    if not api_key:
        raise RuntimeError(
            f"{key_name} fehlt in ~/.env. "
            f"Bitte OPENAI_API_KEY_1 bis OPENAI_API_KEY_4 eintragen."
        )
    return api_key


def call_openai(prompt: str, api_key: str) -> Optional[str]:
    import urllib.request
    import urllib.error
    import json

    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1200,
        "temperature": 0.7,
    }

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logging.error(f"OpenAI HTTP Fehler {e.code}: {body[:500]}")
        return None
    except Exception as e:
        logging.error(f"OpenAI Fehler: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen was fehlt")
    parser.add_argument("--species", type=int, help="Nur diese species_id bearbeiten")
    parser.add_argument("--lang", help="Nur diese Sprache, z.B. de oder en")
    parser.add_argument("--field", help="Nur dieses Feld, z.B. description")
    parser.add_argument("--force", action="store_true", help="Vorhandene Texte überschreiben")
    parser.add_argument("--shard-count", type=int, help="Anzahl paralleler Worker, z.B. 4")
    parser.add_argument("--shard-index", type=int, help="Index dieses Workers, 0 bis shard-count-1")
    args = parser.parse_args()

    if args.lang and args.lang not in LANGUAGES:
        raise RuntimeError(f"Unbekannte Sprache: {args.lang}. Erlaubt: {', '.join(LANGUAGES.keys())}")

    if args.field and args.field not in FIELDS:
        raise RuntimeError(f"Unbekanntes Feld: {args.field}. Erlaubt: {', '.join(sorted(FIELDS))}")

    if (args.shard_count is None) != (args.shard_index is None):
        raise RuntimeError("--shard-count und --shard-index müssen zusammen gesetzt werden")

    if args.shard_count is not None:
        if args.shard_count < 1:
            raise RuntimeError("--shard-count muss >= 1 sein")
        if args.shard_index < 0 or args.shard_index >= args.shard_count:
            raise RuntimeError("--shard-index muss zwischen 0 und shard-count-1 liegen")

    langs = [args.lang] if args.lang else list(LANGUAGES.keys())

    pg = psycopg2.connect(**PG_CONFIG)

    with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        conditions = ["1=1"]
        params = []

        if args.species:
            conditions.append("st.species_id = %s")
            params.append(args.species)

        if args.field:
            conditions.append("st.field = %s")
            params.append(args.field)

        if args.shard_count is not None:
            conditions.append("MOD(st.species_id, %s) = %s")
            params.extend([args.shard_count, args.shard_index])

        if not args.force:
            missing_conditions = [f"(st.{lang} IS NULL OR trim(st.{lang}) = '')" for lang in langs]
            conditions.append("(" + " OR ".join(missing_conditions) + ")")

        language_columns = ", ".join([f"st.{lang}" for lang in LANGUAGES.keys()])

        cur.execute(f"""
            SELECT st.id, st.species_id, st.field,
                   {language_columns},
                   s.german_name, s.latin_name,
                   ist.code AS iucn_code
            FROM species_texts st
            JOIN species s ON s.id = st.species_id
            LEFT JOIN iucn_status ist ON ist.wikidata_id = s.iucn_status_id
            WHERE {' AND '.join(conditions)}
            ORDER BY s.german_name, st.field
        """, params)
        rows = cur.fetchall()

    shard_info = ""
    if args.shard_count is not None:
        shard_info = f" | Worker {args.shard_index}/{args.shard_count}"

    logging.info(f"Fehlende Einträge: {len(rows)}{shard_info}")
    logging.info(f"Sprachen: {langs}")

    if args.dry_run:
        shown = 0
        for row in rows:
            missing_langs = [
                lang for lang in langs
                if args.force or row.get(lang) is None or str(row.get(lang)).strip() == ""
            ]
            if not missing_langs:
                continue
            print(f"  {row['german_name']} / {row['field']} / {', '.join(missing_langs)}")
            shown += 1
            if shown >= 20:
                break
        if len(rows) > shown:
            print(f"  ... und {len(rows) - shown} weitere")
        pg.close()
        return

    shard_idx = args.shard_index if args.shard_index is not None else 0
    api_key = get_openai_key(shard_idx)
    logging.info(f"OpenAI Key geladen (OPENAI_API_KEY_{shard_idx + 1})")

    ok = 0
    fail = 0
    total = len(rows)

    for index, row in enumerate(rows, start=1):
        field = row["field"]
        german_name = row["german_name"]
        latin_name = row["latin_name"]
        iucn_code = row["iucn_code"]

        updates = {}

        for lang_code in langs:
            current_value = row.get(lang_code)
            if not args.force and current_value is not None and str(current_value).strip() != "":
                continue

            lang_name = LANGUAGES[lang_code]
            prompt = build_prompt(field, german_name, latin_name, iucn_code, lang_name)

            logging.info(f"[{index}/{total}] {german_name} / {field} / {lang_code}...")
            text = call_openai(prompt, api_key)

            if text:
                updates[lang_code] = text
                ok += 1
            else:
                fail += 1

            time.sleep(0.5)

        if updates:
            set_parts = ", ".join([f"{k} = %s" for k in updates.keys()])
            set_parts += ", generated_at = NOW()"
            values = list(updates.values()) + [row["id"]]

            with pg.cursor() as cur:
                cur.execute(
                    f"UPDATE zoo.species_texts SET {set_parts} WHERE id = %s",
                    values,
                )

                # translations_valid auf TRUE setzen wenn alle 5 Felder
                # in allen 12 Sprachen jetzt befüllt sind
                cur.execute("""
                    UPDATE zoo.species s
                    SET translations_valid = TRUE
                    WHERE s.id = %s
                      AND (
                          SELECT count(*)
                          FROM zoo.species_texts st
                          WHERE st.species_id = s.id
                            AND st.de IS NOT NULL AND trim(st.de) != ''
                            AND st.en IS NOT NULL AND trim(st.en) != ''
                            AND st.es IS NOT NULL AND trim(st.es) != ''
                            AND st.fr IS NOT NULL AND trim(st.fr) != ''
                            AND st.it IS NOT NULL AND trim(st.it) != ''
                            AND st.nl IS NOT NULL AND trim(st.nl) != ''
                            AND st.pl IS NOT NULL AND trim(st.pl) != ''
                            AND st.pt IS NOT NULL AND trim(st.pt) != ''
                            AND st.ru IS NOT NULL AND trim(st.ru) != ''
                            AND st.tr IS NOT NULL AND trim(st.tr) != ''
                            AND st.uk IS NOT NULL AND trim(st.uk) != ''
                            AND st.zh_hans IS NOT NULL AND trim(st.zh_hans) != ''
                      ) = 5
                """, (row["species_id"],))

            pg.commit()
            logging.info(f"  ✓ {german_name} / {field} gespeichert")

    pg.close()
    print(f"\nFertig: {ok} Texte generiert, {fail} Fehler{shard_info}")


if __name__ == "__main__":
    main()
