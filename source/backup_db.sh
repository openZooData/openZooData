#!/bin/bash
# ============================================================
# ZooGuide Server — PostgreSQL Backup
# Sichert das Schema 'zoo' der zooguide-Datenbank
#
# Aufruf:
#   chmod +x backup_db.sh
#   ~/backup_db.sh
#
# Backup-Format: PostgreSQL Custom (-F c)
#   Wiederherstellen mit:
#   pg_restore -h $PG_HOST -p $PG_PORT -U $PG_USER \
#     -d zooguide --schema=zoo -F c <datei>
# ============================================================

set -e

# Credentials aus ~/.env laden
if [ -f ~/.env ]; then
    export $(grep -E '^(PG_HOST|PG_PORT|PG_USER|PG_PASSWORD|PG_NAME)=' ~/.env | xargs)
else
    echo "FEHLER: ~/.env nicht gefunden"
    exit 1
fi

BACKUP_DIR=~/backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="zooguide_zoo_${TIMESTAMP}.dump"
FILEPATH="${BACKUP_DIR}/${FILENAME}"

mkdir -p "$BACKUP_DIR"

echo "=============================="
echo " ZooGuide PostgreSQL Backup"
echo " Ziel: $FILEPATH"
echo "=============================="

PGPASSWORD=$PG_PASSWORD pg_dump \
    -h "${PG_HOST}" \
    -p "${PG_PORT:-5432}" \
    -U "${PG_USER}" \
    -d "${PG_NAME:-zooguide}" \
    --schema=zoo \
    -F c \
    -f "$FILEPATH"

SIZE=$(du -sh "$FILEPATH" | cut -f1)
echo ""
echo " Backup erstellt: $FILENAME ($SIZE)"

# Alte Backups aufräumen — nur die letzten 10 behalten
BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/zooguide_zoo_*.dump 2>/dev/null | wc -l)
if [ "$BACKUP_COUNT" -gt 10 ]; then
    echo " Aufräumen: behalte die letzten 10 Backups..."
    ls -1t "$BACKUP_DIR"/zooguide_zoo_*.dump | tail -n +11 | xargs rm -f
    echo " Alte Backups gelöscht."
fi

echo "=============================="
echo " Fertig."
echo "=============================="
