#!/bin/bash
# ============================================================
# ZooGuide Server — Setup Script
# Ausführen nach einem frischen git clone auf einem neuen Server
#
# Voraussetzungen:
#   - Python 3.11 installiert
#   - ~/.env mit allen Credentials befüllt (siehe env_template.txt)
#   - Git Repo bereits geklont nach ~/
#
# Aufruf:
#   chmod +x setup.sh
#   ./setup.sh
# ============================================================

set -e  # Abbrechen bei Fehler

echo "=============================================="
echo " ZooGuide Server Setup"
echo "=============================================="

# ------------------------------------------------------
# 1. Prüfen ob .env vorhanden
# ------------------------------------------------------
echo ""
echo "[1/6] Prüfe .env..."
if [ ! -f ~/.env ]; then
    echo "FEHLER: ~/.env nicht gefunden!"
    echo "Bitte ~/.env anlegen (siehe env_template.txt) und Setup erneut starten."
    exit 1
fi

# Pflichtfelder prüfen
for VAR in DB_HOST DB_USER DB_PASSWORD DB_NAME PG_HOST PG_USER PG_PASSWORD; do
    VALUE=$(grep "^${VAR}=" ~/.env | cut -d'=' -f2)
    if [ -z "$VALUE" ]; then
        echo "FEHLER: ${VAR} fehlt oder ist leer in ~/.env"
        exit 1
    fi
done
echo "   .env OK"

# ------------------------------------------------------
# 2. JWT_SECRET generieren falls fehlend
# ------------------------------------------------------
echo ""
echo "[2/6] Prüfe Secrets..."
if ! grep -q "^JWT_SECRET=" ~/.env || [ -z "$(grep '^JWT_SECRET=' ~/.env | cut -d'=' -f2)" ]; then
    echo "   Generiere JWT_SECRET..."
    echo "JWT_SECRET=$(openssl rand -hex 32)" >> ~/.env
fi
echo "   Secrets OK"

# ------------------------------------------------------
# 3. Virtualenv anlegen
# ------------------------------------------------------
echo ""
echo "[3/6] Virtualenv anlegen..."
if [ -d ~/myapi-env ]; then
    echo "   ~/myapi-env existiert bereits — überspringe"
else
    python3 -m venv ~/myapi-env
    echo "   Virtualenv angelegt"
fi

source ~/myapi-env/bin/activate

# ------------------------------------------------------
# 4. Dependencies installieren
# ------------------------------------------------------
echo ""
echo "[4/6] Dependencies installieren..."
pip install -q -r ~/requirements.txt
echo "   Dependencies installiert"

# ------------------------------------------------------
# 5. Verzeichnisse anlegen
# ------------------------------------------------------
echo ""
echo "[5/6] Verzeichnisse anlegen..."
mkdir -p ~/sqlite
mkdir -p ~/backup
mkdir -p ~/storage
echo "   sqlite/, backup/, storage/ OK"

# ------------------------------------------------------
# 6. Server starten
# ------------------------------------------------------
echo ""
echo "[6/6] Server starten..."
pkill gunicorn 2>/dev/null || true
sleep 1
gunicorn --bind 127.0.0.1:5000 app:app --daemon
sleep 2

# Status prüfen
if pgrep gunicorn > /dev/null; then
    echo "   Gunicorn läuft ✓"
else
    echo "   FEHLER: Gunicorn nicht gestartet — starte manuell mit:"
    echo "   gunicorn --bind 127.0.0.1:5000 app:app"
    exit 1
fi

# ------------------------------------------------------
# Fertig
# ------------------------------------------------------
echo ""
echo "=============================================="
echo " Setup abgeschlossen!"
echo ""
echo " Nächste Schritte:"
echo "   1. SQLite Daten generieren: ~/export_all.sh"
echo "   2. API testen:              curl http://127.0.0.1:5000/status"
echo "=============================================="