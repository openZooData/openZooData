"""
export/fetch.py
---------------
PostgreSQL-Abfragen: alle fetch_* Funktionen für den SQLite-Export.
"""

from typing import List, Optional


def fetch_zoo(pg, zoo_id: int) -> Optional[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT id, slug, name, url, description, email,
                   top_left_latitude, top_left_longitude,
                   bottom_right_latitude, bottom_right_longitude,
                   map_overlay, data_version, is_active::INT,
                   easy_language::INT, number_animals
            FROM zoos
            WHERE id = %s
        """, (zoo_id,))
        return cur.fetchone()


def fetch_zoo_opening_hours(pg, zoo_id: int) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT id, zoo_id, day_of_week,
                   open_time::TEXT, close_time::TEXT,
                   valid_from::TEXT, valid_until::TEXT, label
            FROM zoo_opening_hours
            WHERE zoo_id = %s
        """, (zoo_id,))
        return cur.fetchall()


def fetch_domains(pg, zoo_id: int) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT id, zoo_id, name, sort_order, is_infrastructure,
                   color_red, color_green, color_blue, color_alpha
            FROM domains
            WHERE zoo_id = %s OR zoo_id IS NULL
            ORDER BY sort_order, name
        """, (zoo_id,))
        return cur.fetchall()


def fetch_location_types(pg) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT id, slug, name, icon, sort_order
            FROM location_types
            ORDER BY sort_order
        """)
        return cur.fetchall()


def fetch_taxonomy(pg) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT id, wikidata_id, rank, name
            FROM taxonomy
            ORDER BY rank, name
        """)
        return cur.fetchall()


def fetch_iucn_status(pg) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT id, wikidata_id, code, name
            FROM iucn_status
            ORDER BY id
        """)
        return cur.fetchall()


def fetch_iucn_trend(pg) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT id, wikidata_id, name
            FROM iucn_trend
            ORDER BY id
        """)
        return cur.fetchall()


def fetch_species(pg, zoo_id: int) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT s.id, s.wikidata_id, s.latin_name, s.german_name,
                   s.tax_kingdom_id, s.tax_phylum_id, s.tax_class_id,
                   s.tax_order_id, s.tax_family_id, s.tax_genus_id,
                   s.iucn_status_id, s.iucn_population_trend_id,
                   s.gbif_taxon_key, s.id_valid, s.icon_media_id
            FROM zoo.species s
            JOIN zoo.enclosure_species es ON es.species_id = s.id
            WHERE es.zoo_id = %s
        """, (zoo_id,))
        return cur.fetchall()


def fetch_species_texts(pg, zoo_id: int) -> List[tuple]:
    """Lädt species_texts für alle species eines Zoos."""
    with pg.cursor() as cur:
        cur.execute("""
            SELECT st.id, st.species_id, st.field,
                   st.de, st.en, st.es, st.fr, st.it,
                   st.nl, st.pl, st.pt, st.ru, st.tr, st.uk, st.zh_hans,
                   st.generated_at::TEXT
            FROM zoo.species_texts st
            WHERE st.species_id IN (
                SELECT DISTINCT es.species_id
                FROM zoo.enclosure_species es
                WHERE es.zoo_id = %s
            )
            AND st.de IS NOT NULL
        """, (zoo_id,))
        return cur.fetchall()


def fetch_enclosures(pg, zoo_id: int) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT id, zoo_id, house_id, domain_id, name, sort_order,
                   osm_relation_id, history, sponsor, notes
            FROM enclosures
            WHERE zoo_id = %s
            ORDER BY sort_order, name
        """, (zoo_id,))
        return cur.fetchall()


def fetch_enclosure_species(pg, zoo_id: int) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT es.id, es.zoo_id, es.enclosure_id, es.house_id,
                   es.domain_id, es.species_id, es.note,
                   es.count_adult, es.count_juvenile,
                   es.counted_at::TEXT, es.icon_media_id
            FROM zoo.enclosure_species es
            WHERE es.zoo_id = %s
        """, (zoo_id,))
        return cur.fetchall()


def fetch_feeding_times(pg, zoo_id: int) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT ft.id, ft.enclosure_species_id, ft.species_id,
                   ft.feeding_time::TEXT, ft.day_of_week,
                   ft.note, ft.is_public::INT
            FROM feeding_times ft
            JOIN enclosure_species es ON es.id = ft.enclosure_species_id
            WHERE es.zoo_id = %s
        """, (zoo_id,))
        return cur.fetchall()


def fetch_locations(pg, zoo_id: int) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT id, zoo_id, name, name_display,
                   description, description_long, url,
                   location_type, location_type_id, domain_id, sort_order
            FROM locations
            WHERE zoo_id = %s
            ORDER BY sort_order, name
        """, (zoo_id,))
        return cur.fetchall()


def fetch_location_species(pg, zoo_id: int) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT ls.location_id, ls.species_id, ls.note
            FROM location_species ls
            JOIN locations l ON l.id = ls.location_id
            WHERE l.zoo_id = %s
        """, (zoo_id,))
        return cur.fetchall()


def fetch_opening_hours(pg, zoo_id: int) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT oh.id, oh.location_id, oh.day_of_week,
                   oh.open_time::TEXT, oh.close_time::TEXT,
                   oh.valid_from::TEXT, oh.valid_until::TEXT, oh.label
            FROM opening_hours oh
            JOIN locations l ON l.id = oh.location_id
            WHERE l.zoo_id = %s
        """, (zoo_id,))
        return cur.fetchall()


def fetch_house_opening_hours(pg, zoo_id: int) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT hoh.id, hoh.house_id, hoh.day_of_week,
                   hoh.open_time::TEXT, hoh.close_time::TEXT,
                   hoh.valid_from::TEXT, hoh.valid_until::TEXT, hoh.label
            FROM house_opening_hours hoh
            JOIN houses h ON h.id = hoh.house_id
            WHERE h.zoo_id = %s
        """, (zoo_id,))
        return cur.fetchall()


def fetch_houses(pg, zoo_id: int) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT id, zoo_id, name, description,
                   history, sponsor, notes
            FROM houses
            WHERE zoo_id = %s
            ORDER BY name
        """, (zoo_id,))
        return cur.fetchall()


def fetch_geo_points(pg, zoo_id: int) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT g.id, g.entity_type, g.entity_id,
                   g.latitude, g.longitude, g.translation_id, g.sort_order
            FROM geo_points g
            WHERE (g.entity_type = 'zoo' AND g.entity_id = %s)
            OR (g.entity_type = 'location' AND g.entity_id IN (
                SELECT id FROM locations WHERE zoo_id = %s))
            OR (g.entity_type = 'enclosure' AND g.entity_id IN (
                SELECT id FROM enclosures WHERE zoo_id = %s))
            OR (g.entity_type = 'house' AND g.entity_id IN (
                SELECT id FROM houses WHERE zoo_id = %s))
            OR (g.entity_type = 'enclosure_species' AND g.entity_id IN (
                SELECT id FROM enclosure_species WHERE zoo_id = %s))
            ORDER BY g.entity_type, g.entity_id, g.sort_order
        """, (zoo_id, zoo_id, zoo_id, zoo_id, zoo_id))
        return cur.fetchall()


def fetch_births(pg, zoo_id: int) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT id, zoo_id, enclosure_species_id, species_id,
                   birth_date::TEXT, count, note,
                   is_public::INT, created_at::TEXT
            FROM births
            WHERE zoo_id = %s
            ORDER BY birth_date DESC
        """, (zoo_id,))
        return cur.fetchall()


def fetch_translations(pg, zoo_id: int) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT t.entity_type, t.entity_id, t.field,
                   t.de, t.en, t.es, t.fr, t.it,
                   t.nl, t.pl, t.pt, t.ru, t.tr, t.uk, t.zh_hans
            FROM translations t
            WHERE
                (t.entity_type = 'location' AND t.entity_id IN (
                    SELECT id FROM locations WHERE zoo_id = %s))
                OR
                (t.entity_type = 'enclosure' AND t.entity_id IN (
                    SELECT id FROM enclosures WHERE zoo_id = %s))
                OR
                (t.entity_type = 'house' AND t.entity_id IN (
                    SELECT id FROM houses WHERE zoo_id = %s))
                OR
                (t.entity_type = 'domain' AND t.entity_id IN (
                    SELECT id FROM domains WHERE zoo_id = %s OR zoo_id IS NULL))
                OR
                (t.entity_type = 'species' AND t.entity_id IN (
                    SELECT DISTINCT es.species_id
                    FROM enclosure_species es
                    JOIN enclosures e ON e.id = es.enclosure_id
                    WHERE e.zoo_id = %s))
                OR
                t.entity_type = 'location_type'
                OR
                t.entity_type = 'iucn_status'
                OR
                t.entity_type = 'iucn_trend'
        """, (zoo_id, zoo_id, zoo_id, zoo_id, zoo_id))
        return cur.fetchall()


def fetch_media(pg, zoo_id: int) -> List[tuple]:
    with pg.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT m.id, m.entity_type, m.entity_id,
                   m.wikidata_id, m.filename, m.storage_path,
                   m.mime_type, m.sort_order, m.label
            FROM zoo.media m
            WHERE (m.entity_type = 'zoo' AND m.entity_id = %s)
            OR (m.entity_type = 'species' AND m.entity_id IN (
                SELECT DISTINCT es.species_id
                FROM zoo.enclosure_species es
                WHERE es.zoo_id = %s))
            OR (m.entity_type = 'location' AND m.entity_id IN (
                SELECT id FROM zoo.locations WHERE zoo_id = %s))
            OR (m.entity_type = 'enclosure' AND m.entity_id IN (
                SELECT id FROM zoo.enclosures WHERE zoo_id = %s))
            OR (m.entity_type = 'enclosure_species' AND m.entity_id IN (
                SELECT id FROM zoo.enclosure_species WHERE zoo_id = %s))
            OR (m.entity_type = 'house' AND m.entity_id IN (
                SELECT id FROM zoo.houses WHERE zoo_id = %s))
        """, (zoo_id, zoo_id, zoo_id, zoo_id, zoo_id, zoo_id))
        return cur.fetchall()


def get_zoo_ids(pg, slugs: List[str]) -> List[tuple]:
    with pg.cursor() as cur:
        if slugs:
            cur.execute(
                "SELECT id, slug FROM zoos WHERE slug = ANY(%s) ORDER BY slug",
                (slugs,)
            )
        else:
            cur.execute(
                "SELECT id, slug FROM zoos WHERE is_active = TRUE ORDER BY slug"
            )
        return cur.fetchall()
