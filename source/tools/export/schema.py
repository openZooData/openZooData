"""
export/schema.py
----------------
SQLite-Schema: Tabellen und Indizes für die iOS-App (GRDB).
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS zoos (
    id                     INTEGER PRIMARY KEY,
    slug                   TEXT UNIQUE NOT NULL,
    name                   TEXT NOT NULL,
    url                    TEXT,
    description            TEXT,
    email                  TEXT,
    top_left_latitude      REAL,
    top_left_longitude     REAL,
    bottom_right_latitude  REAL,
    bottom_right_longitude REAL,
    map_overlay            TEXT,
    data_version           INTEGER DEFAULT 0,
    is_active              INTEGER DEFAULT 1,
    easy_language          INTEGER DEFAULT 0,
    number_animals         INTEGER
);

CREATE TABLE IF NOT EXISTS domains (
    id                INTEGER PRIMARY KEY,
    zoo_id            INTEGER,
    name              TEXT NOT NULL,
    sort_order        INTEGER DEFAULT 0,
    is_infrastructure INTEGER DEFAULT 0,
    color_red         INTEGER DEFAULT 128,
    color_green       INTEGER DEFAULT 128,
    color_blue        INTEGER DEFAULT 128,
    color_alpha       REAL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS location_types (
    id         INTEGER PRIMARY KEY,
    slug       TEXT NOT NULL,
    name       TEXT NOT NULL,
    icon       TEXT,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS taxonomy (
    id          INTEGER PRIMARY KEY,
    wikidata_id TEXT NOT NULL UNIQUE,
    rank        TEXT NOT NULL,
    name        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS iucn_status (
    id          INTEGER PRIMARY KEY,
    wikidata_id TEXT NOT NULL UNIQUE,
    code        TEXT NOT NULL,
    name        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS iucn_trend (
    id          INTEGER PRIMARY KEY,
    wikidata_id TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS houses (
    id          INTEGER PRIMARY KEY,
    zoo_id      INTEGER NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    history     TEXT,
    sponsor     TEXT,
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS zoo_opening_hours (
    id          INTEGER PRIMARY KEY,
    zoo_id      INTEGER NOT NULL,
    day_of_week TEXT NOT NULL,
    open_time   TEXT,
    close_time  TEXT,
    valid_from  TEXT,
    valid_until TEXT,
    label       TEXT
);

CREATE TABLE IF NOT EXISTS house_opening_hours (
    id          INTEGER PRIMARY KEY,
    house_id    INTEGER NOT NULL,
    day_of_week TEXT NOT NULL,
    open_time   TEXT,
    close_time  TEXT,
    valid_from  TEXT,
    valid_until TEXT,
    label       TEXT
);

CREATE TABLE IF NOT EXISTS enclosures (
    id              INTEGER PRIMARY KEY,
    zoo_id          INTEGER NOT NULL,
    house_id        INTEGER,
    domain_id       INTEGER,
    name            TEXT,
    sort_order      INTEGER DEFAULT 0,
    osm_relation_id INTEGER,
    history         TEXT,
    sponsor         TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS locations (
    id               INTEGER PRIMARY KEY,
    zoo_id           INTEGER NOT NULL,
    name             TEXT NOT NULL,
    name_display     TEXT,
    description      TEXT,
    description_long TEXT,
    url              TEXT,
    location_type    TEXT,
    location_type_id INTEGER,
    domain_id        INTEGER,
    sort_order       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS location_species (
    location_id INTEGER NOT NULL,
    species_id  INTEGER NOT NULL,
    note        TEXT,
    PRIMARY KEY (location_id, species_id)
);

CREATE TABLE IF NOT EXISTS opening_hours (
    id          INTEGER PRIMARY KEY,
    location_id INTEGER NOT NULL,
    day_of_week TEXT NOT NULL,
    open_time   TEXT,
    close_time  TEXT,
    valid_from  TEXT,
    valid_until TEXT,
    label       TEXT
);

CREATE TABLE IF NOT EXISTS species (
    id                       INTEGER PRIMARY KEY,
    wikidata_id              TEXT,
    latin_name               TEXT,
    german_name              TEXT NOT NULL,
    tax_kingdom_id           TEXT,
    tax_phylum_id            TEXT,
    tax_class_id             TEXT,
    tax_order_id             TEXT,
    tax_family_id            TEXT,
    tax_genus_id             TEXT,
    iucn_status_id           TEXT,
    iucn_population_trend_id TEXT,
    gbif_taxon_key           INTEGER,
    id_valid                 INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS species_texts (
    id           INTEGER PRIMARY KEY,
    species_id   INTEGER NOT NULL,
    field        TEXT NOT NULL,
    de           TEXT,
    en           TEXT,
    es           TEXT,
    fr           TEXT,
    it           TEXT,
    nl           TEXT,
    pl           TEXT,
    pt           TEXT,
    ru           TEXT,
    tr           TEXT,
    uk           TEXT,
    zh_hans      TEXT,
    generated_at TEXT,
    UNIQUE (species_id, field)
);

CREATE TABLE IF NOT EXISTS enclosure_species (
    id             INTEGER PRIMARY KEY,
    zoo_id         INTEGER,
    enclosure_id   INTEGER,
    house_id       INTEGER,
    domain_id      INTEGER,
    species_id     INTEGER NOT NULL,
    note           TEXT,
    count_adult    INTEGER,
    count_juvenile INTEGER,
    counted_at     TEXT,
    icon_media_id  INTEGER
);

CREATE TABLE IF NOT EXISTS feeding_times (
    id                  INTEGER PRIMARY KEY,
    enclosure_species_id INTEGER NOT NULL,
    species_id          INTEGER,
    feeding_time        TEXT NOT NULL,
    day_of_week         INTEGER,
    note                TEXT,
    is_public           INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS births (
    id                  INTEGER PRIMARY KEY,
    zoo_id              INTEGER NOT NULL,
    enclosure_species_id INTEGER,
    species_id          INTEGER,
    birth_date          TEXT,
    count               INTEGER,
    note                TEXT,
    is_public           INTEGER DEFAULT 1,
    created_at          TEXT
);

CREATE TABLE IF NOT EXISTS geo_points (
    id             INTEGER PRIMARY KEY,
    entity_type    TEXT NOT NULL,
    entity_id      INTEGER NOT NULL,
    latitude       REAL NOT NULL,
    longitude      REAL NOT NULL,
    translation_id INTEGER,
    sort_order     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS translations (
    entity_type TEXT NOT NULL,
    entity_id   INTEGER NOT NULL,
    field       TEXT NOT NULL DEFAULT 'name',
    de          TEXT,
    en          TEXT,
    es          TEXT,
    fr          TEXT,
    it          TEXT,
    nl          TEXT,
    pl          TEXT,
    pt          TEXT,
    ru          TEXT,
    tr          TEXT,
    uk          TEXT,
    zh_hans     TEXT,
    PRIMARY KEY (entity_type, entity_id, field)
);

CREATE TABLE IF NOT EXISTS media (
    id           INTEGER PRIMARY KEY,
    entity_type  TEXT,
    entity_id    INTEGER,
    wikidata_id  TEXT,
    filename     TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    mime_type    TEXT,
    sort_order   INTEGER DEFAULT 0,
    label        TEXT
);

-- Indizes
CREATE INDEX IF NOT EXISTS idx_enclosures_zoo        ON enclosures(zoo_id);
CREATE INDEX IF NOT EXISTS idx_enc_species_enc        ON enclosure_species(enclosure_id);
CREATE INDEX IF NOT EXISTS idx_enc_species_sp         ON enclosure_species(species_id);
CREATE INDEX IF NOT EXISTS idx_locations_zoo          ON locations(zoo_id);
CREATE INDEX IF NOT EXISTS idx_geo_entity             ON geo_points(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_translations           ON translations(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_media_entity           ON media(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_media_wikidata         ON media(wikidata_id);
CREATE INDEX IF NOT EXISTS idx_opening_hours_loc      ON opening_hours(location_id);
CREATE INDEX IF NOT EXISTS idx_house_oh_house         ON house_opening_hours(house_id);
CREATE INDEX IF NOT EXISTS idx_zoo_oh_zoo             ON zoo_opening_hours(zoo_id);
CREATE INDEX IF NOT EXISTS idx_feeding_enclosure      ON feeding_times(enclosure_species_id);
CREATE INDEX IF NOT EXISTS idx_location_species_loc   ON location_species(location_id);
CREATE INDEX IF NOT EXISTS idx_location_species_sp    ON location_species(species_id);
CREATE INDEX IF NOT EXISTS idx_taxonomy_wikidata      ON taxonomy(wikidata_id);
CREATE INDEX IF NOT EXISTS idx_taxonomy_rank          ON taxonomy(rank);
CREATE INDEX IF NOT EXISTS idx_iucn_status_wikidata   ON iucn_status(wikidata_id);
CREATE INDEX IF NOT EXISTS idx_iucn_trend_wikidata    ON iucn_trend(wikidata_id);
CREATE INDEX IF NOT EXISTS idx_births_zoo             ON births(zoo_id);
CREATE INDEX IF NOT EXISTS idx_species_texts_species  ON species_texts(species_id);
CREATE INDEX IF NOT EXISTS idx_species_texts_field    ON species_texts(field);
"""
