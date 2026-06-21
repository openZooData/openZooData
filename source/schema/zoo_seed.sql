-- zoo_seed.sql — Referenz-/Lookup-Tabellen für openZooData
-- Notwendig nach einem --schema-only-Rebuild (z.B. Testserver), da
-- pg_dump --schema-only keine Datenzeilen mitliefert. Werte hier
-- entsprechen dem bestätigten aktuellen lokalen Stand (21.06.2026).
-- Idempotent (ON CONFLICT DO NOTHING) — beliebig oft sicher ausführbar,
-- auch wenn einzelne Tabellen schon teilweise befüllt sind.

-- -----------------------------------------------------------------------
-- feedback_types (keine Sequence, feste IDs)
-- -----------------------------------------------------------------------
INSERT INTO zoo.feedback_types (id, slug, label_de, entity_type, requires_admin_review, is_active)
VALUES
  (1,  'feeding_time',         'Fütterungszeit korrigieren',  'enclosure', TRUE,  TRUE),
  (2,  'position',             'GPS-Position korrigieren',    'enclosure', TRUE,  TRUE),
  (3,  'new_species_wikidata', 'Neue Tierart (Wikidata)',     'enclosure', TRUE,  TRUE),
  (4,  'new_species_existing', 'Bekannte Tierart ergänzen',   'enclosure', TRUE,  TRUE),
  (5,  'species_birthday',     'Nachwuchs / Geburt',          'enclosure', TRUE,  TRUE),
  (6,  'count_adult',          'Anzahl adulte Tiere',         'enclosure', TRUE,  TRUE),
  (7,  'count_juvenile',       'Anzahl juvenile Tiere',       'enclosure', TRUE,  TRUE),
  (8,  'text_incorrect',       'Text fehlerhaft melden',      'text',      TRUE,  TRUE),
  (9,  'text_helpful',         'Text hilfreich',              'text',      FALSE, TRUE),
  (10, 'text_excellent',       'Text besonders gut',          'text',      FALSE, TRUE)
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------
-- location_types (Sequence vorhanden -> Sync nötig)
-- -----------------------------------------------------------------------
INSERT INTO zoo.location_types (id, slug, name, icon, sort_order)
VALUES
  (1,  'wc',                  'WC',                  'restroom',        1),
  (2,  'wickelraum',          'Wickelraum',          'baby-carriage',   2),
  (3,  'spielplatz',          'Spielplatz',          'playground',      3),
  (4,  'restaurant',          'Restaurant',          'fork-knife',      4),
  (5,  'kiosk',               'Kiosk',               'coffee',          5),
  (6,  'eis',                 'Eis',                 'ice-cream',       6),
  (7,  'shop',                'Shop',                'shopping-bag',    7),
  (8,  'eingang',             'Eingang',             'door-enter',      8),
  (9,  'ausgang',             'Ausgang',             'door-exit',       9),
  (10, 'backstube',           'Backstube',           'bread',           10),
  (11, 'sonstiges',           'Sonstiges',           'dots',            99),
  (12, 'museum',              'Museum',              'building',        11),
  (13, 'attraktion',          'Attraktion',          'star',            12),
  (14, 'service',             'Service',             'tool',            13),
  (15, 'behindertentoilette', 'Behindertentoilette', 'accessible',      3),
  (16, 'aussichtsplattform',  'Aussichtsplattform',  'Aussichtsplattform', 15),
  (17, 'bluehwiese',          'Blühwiese',           'flower',          0),
  (18, 'streichelzoo',        'Streichelzoo',        'hand',            0),
  (19, 'photo',               'Photo',               'camera',          0),
  (20, 'info',                'Info',                'info-circle',     0)
ON CONFLICT (id) DO NOTHING;

SELECT setval('zoo.location_types_id_seq', (SELECT max(id) FROM zoo.location_types));

-- -----------------------------------------------------------------------
-- feedback_report_reasons (keine Sequence, feste IDs)
-- -----------------------------------------------------------------------
INSERT INTO zoo.feedback_report_reasons (id, slug, label_de)
VALUES
  (1, 'factually_incorrect', 'Sachlich falsch'),
  (2, 'outdated',            'Veraltet'),
  (3, 'wrong_species',       'Falsche Tierart'),
  (4, 'inappropriate',       'Unangemessener Inhalt')
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------
-- iucn_status (Sequence vorhanden -> Sync nötig)
-- -----------------------------------------------------------------------
INSERT INTO zoo.iucn_status (id, wikidata_id, code, name)
VALUES
  (1,  'Q211005',  'LC', 'Least Concern'),
  (2,  'Q96377276','LC', 'Least Concern'),
  (3,  'Q278113',  'NT', 'Near Threatened'),
  (4,  'Q719675',  'VU', 'Vulnerable'),
  (5,  'Q11394',   'EN', 'Endangered'),
  (6,  'Q219127',  'CR', 'Critically Endangered'),
  (7,  'Q237350',  'EW', 'Extinct in the Wild'),
  (8,  'Q37517',   'EX', 'Extinct'),
  (9,  'Q2765491', 'DD', 'Data Deficient'),
  (10, 'Q3245245', 'NE', 'Not Evaluated')
ON CONFLICT (id) DO NOTHING;

SELECT setval('zoo.iucn_status_id_seq', (SELECT max(id) FROM zoo.iucn_status));

-- -----------------------------------------------------------------------
-- iucn_trend (Sequence vorhanden -> Sync nötig)
-- -----------------------------------------------------------------------
INSERT INTO zoo.iucn_trend (id, wikidata_id, name)
VALUES
  (1, 'Q2494557',  'Increasing'),
  (2, 'Q2494558',  'Stable'),
  (3, 'Q2494559',  'Decreasing'),
  (4, 'Q56364716', 'Unknown')
ON CONFLICT (id) DO NOTHING;

SELECT setval('zoo.iucn_trend_id_seq', (SELECT max(id) FROM zoo.iucn_trend));

-- -----------------------------------------------------------------------
-- Kontrolle
-- -----------------------------------------------------------------------
SELECT 'feedback_types' AS tbl, count(*) FROM zoo.feedback_types
UNION ALL SELECT 'location_types', count(*) FROM zoo.location_types
UNION ALL SELECT 'feedback_report_reasons', count(*) FROM zoo.feedback_report_reasons
UNION ALL SELECT 'iucn_status', count(*) FROM zoo.iucn_status
UNION ALL SELECT 'iucn_trend', count(*) FROM zoo.iucn_trend;
