#!/bin/bash
# ============================================================
# Media-Verzeichnisstruktur anlegen
# Ausführen auf: api.zooguide.app und api.openzoodata.org
#
# Aufruf:
#   chmod +x setup_media_dirs.sh
#   ./setup_media_dirs.sh
# ============================================================

set -e

# Credentials aus /Volumes/Daten/Projects/openzoodata/.env laden
if [ -f /Volumes/Daten/Projects/openzoodata/.env ]; then
    export $(grep -E '^(PG_HOST|PG_PORT|PG_USER|PG_PASSWORD|PG_NAME)=' /Volumes/Daten/Projects/openzoodata/.env | xargs)
else
    echo "FEHLER: /Volumes/Daten/Projects/openzoodata/.env nicht gefunden"
    exit 1
fi

MEDIA_ROOT=~/media

echo "=============================="
echo " Media-Setup"
echo " Root: $MEDIA_ROOT"
echo "=============================="

# ── Verzeichnisse anlegen ─────────────────────────────────
echo ""
echo "▶  Lege Verzeichnisstruktur an..."

mkdir -p "$MEDIA_ROOT/species"

# Zoo-Slugs aus der Datenbank holen
ZOOS=$(PGPASSWORD=$PG_PASSWORD psql \
    -h "${PG_HOST}" -p "${PG_PORT:-5432}" \
    -U "${PG_USER}" -d "${PG_NAME:-zooguide}" \
    -t -c "SELECT slug FROM zoo.zoos WHERE is_active = TRUE ORDER BY slug;" \
    | tr -d ' ' | grep -v '^$')

for slug in $ZOOS; do
    mkdir -p "$MEDIA_ROOT/zoo/$slug/enclosures"
    mkdir -p "$MEDIA_ROOT/zoo/$slug/houses"
    mkdir -p "$MEDIA_ROOT/zoo/$slug/locations"
    echo "  ✅  $slug"
done

echo ""
echo "=============================="
echo " Verzeichnisse angelegt."
echo "=============================="
echo ""
echo "▶  Aktualisiere storage_path in zoo.media..."

# ── storage_path in DB aktualisieren ─────────────────────
PGPASSWORD=$PG_PASSWORD psql \
    -h "${PG_HOST}" -p "${PG_PORT:-5432}" \
    -U "${PG_USER}" -d "${PG_NAME:-zooguide}" << 'SQL'

-- species: zoo-übergreifend
UPDATE zoo.media
SET storage_path = 'media/species/' || filename
WHERE entity_type = 'species';

-- enclosures: zoo-spezifisch
UPDATE zoo.media m
SET storage_path = 'media/zoo/' || z.slug || '/enclosures/' || m.filename
FROM zoo.enclosures e
JOIN zoo.zoos z ON z.id = e.zoo_id
WHERE m.entity_type = 'enclosure'
  AND m.entity_id = e.id;

-- houses: zoo-spezifisch
UPDATE zoo.media m
SET storage_path = 'media/zoo/' || z.slug || '/houses/' || m.filename
FROM zoo.houses h
JOIN zoo.zoos z ON z.id = h.zoo_id
WHERE m.entity_type = 'house'
  AND m.entity_id = h.id;

-- locations: zoo-spezifisch
UPDATE zoo.media m
SET storage_path = 'media/zoo/' || z.slug || '/locations/' || m.filename
FROM zoo.locations l
JOIN zoo.zoos z ON z.id = l.zoo_id
WHERE m.entity_type = 'location'
  AND m.entity_id = l.id;

-- zoo: direkt unter zoo/<slug>/
UPDATE zoo.media m
SET storage_path = 'media/zoo/' || z.slug || '/' || m.filename
FROM zoo.zoos z
WHERE m.entity_type = 'zoo'
  AND m.entity_id = z.id;

SQL

echo ""
echo "=============================="
echo " storage_path aktualisiert."
echo "=============================="
echo ""

# ── Verifikation ──────────────────────────────────────────
echo "▶  Verifikation:"
PGPASSWORD=$PG_PASSWORD psql \
    -h "${PG_HOST}" -p "${PG_PORT:-5432}" \
    -U "${PG_USER}" -d "${PG_NAME:-zooguide}" \
    -c "SELECT entity_type, COUNT(*) AS anzahl, COUNT(storage_path) AS mit_pfad
        FROM zoo.media
        GROUP BY entity_type
        ORDER BY entity_type;"

echo ""
echo "✅  Fertig."
