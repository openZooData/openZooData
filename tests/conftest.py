"""
conftest.py — pytest Konfiguration für openZooData API Tests

Migration v7: JWT-basierte Auth für Admin-Endpoints.
App-Token für iOS-Endpoints (SQLite, Feedback).

.env Datei anlegen (nicht in Git):
  BASE_URL=https://api.openzoodata.org
  TEST_APP_TOKEN=<App-Token aus /api/v1/auth/app_register>
  TEST_ZOO=zoo_berlin
  TEST_FEED_ZOO=zoo_berlin
  TEST_EMAIL=admin@example.com
  TEST_PASSWORD=<passwort>
  HEALTH_CHECK_KEY=<key aus .env auf dem Server>
"""

import os
import io
import uuid
import pytest
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env_test"))


def pytest_addoption(parser):
    parser.addoption(
        "--base-url",
        action="store",
        default=os.getenv("BASE_URL", "http://127.0.0.1:5001"),
        help="Base URL der API (default: http://127.0.0.1:5001)"
    )


@pytest.fixture(scope="session")
def base_url(request):
    return request.config.getoption("--base-url").rstrip("/")


@pytest.fixture(scope="session")
def test_zoo():
    return os.getenv("TEST_ZOO", "zoo_berlin")


@pytest.fixture(scope="session")
def test_feed_zoo():
    return os.getenv("TEST_FEED_ZOO", "zoo_berlin")


# ---------------------------------------------------------------------------
# Health Check Key
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def health_check_key():
    key = os.getenv("HEALTH_CHECK_KEY")
    if not key:
        pytest.skip("HEALTH_CHECK_KEY nicht gesetzt")
    return key


# ---------------------------------------------------------------------------
# App-Token — für iOS-Endpoints (SQLite, Feedback einreichen)
# Migration v7: App-Tokens laufen über auth.app_tokens in Auth-DB.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app_token():
    token = os.getenv("TEST_APP_TOKEN")
    if not token:
        pytest.skip("TEST_APP_TOKEN nicht gesetzt")
    return token


@pytest.fixture(scope="session")
def app_token_headers(app_token):
    """App-Token-Headers — für iOS-Endpoints (SQLite, Feedback POST). Nicht für Admin-Endpunkte."""
    return {"Authorization": f"Bearer {app_token}"}


# ---------------------------------------------------------------------------
# JWT — für Admin-Endpoints (ZooCreator, Enclosures, Media, Feedback Admin)
# Migration v7: JWT enthält sub, email, tenant_id, jti — KEINE Rollen.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def jwt_tokens(base_url):
    """Holt JWT Access + Refresh Token via Login."""
    email    = os.getenv("TEST_EMAIL")
    password = os.getenv("TEST_PASSWORD")
    if not email or not password:
        pytest.skip("TEST_EMAIL oder TEST_PASSWORD nicht gesetzt")

    resp = requests.post(f"{base_url}/api/v1/auth/login", json={
        "email":     email,
        "password":  password,
        "device_id": "pytest-test-device"
    })
    assert resp.status_code == 200, f"Login fehlgeschlagen: {resp.text}"
    data = resp.json()
    # Migration v7: JWT enthält keine 'role' mehr — Rollen kommen aus DB
    assert "access_token"  in data, "access_token fehlt in Login-Response"
    assert "refresh_token" in data, "refresh_token fehlt in Login-Response"
    return data


@pytest.fixture(scope="session")
def jwt_headers(jwt_tokens):
    """JWT-Headers für Admin-Endpoints."""
    return {"Authorization": f"Bearer {jwt_tokens['access_token']}"}


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Device-ID
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_device_id():
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Test-Daten
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_image_bytes():
    from PIL import Image
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color=(255, 100, 50))
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf.read()


@pytest.fixture(scope="session")
def test_svg_bytes():
    return b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


@pytest.fixture(scope="session")
def created_species_id(base_url, jwt_headers):
    """
    Legt einmalig eine Test-Species an und gibt die ID zurück.
    Migration v7: wikidata_id ist Pflicht für direktes Anlegen.

    wikidata_id ist pro Testlauf eindeutig (statt fest "Q999999") und wird
    am Ende der Session wieder gelöscht — sonst schlägt die Anlage beim
    nächsten Lauf an der UNIQUE-Constraint auf wikidata_id fehl, weil die
    Species vom letzten Mal noch in der DB liegt.

    Bereich Q900000000+ statt eines kleinen Zufallswerts: Wikidata hat
    aktuell ~122 Mio. echte Items (Stand 2026) — ein kleinerer Zufallsbereich
    könnte mit einer realen ID kollidieren. Q900000000+ liegt mit großem
    Sicherheitsabstand darüber und bleibt es auch bei weiterem Wachstum.
    """
    wikidata_id = f"Q{900_000_000 + (uuid.uuid4().int % 99_000_000)}"
    resp = requests.post(
        f"{base_url}/api/v1/species",
        headers=jwt_headers,
        json={
            "german_name": "Pytest-Testtier",
            "latin_name":  "Testus pytestus",
            "wikidata_id": wikidata_id,   # Migration v7: wikidata_id Pflicht
            "zoo_slug":    os.getenv("TEST_ZOO", "zoo_berlin"),
        }
    )
    if resp.status_code == 403:
        pytest.skip("Kein write_permission für Species-Anlage")
    assert resp.status_code == 201, f"Species anlegen fehlgeschlagen: {resp.text}"
    species_id = resp.json()["id"]

    yield species_id

    requests.delete(f"{base_url}/api/v1/species/{species_id}", headers=jwt_headers)


@pytest.fixture(scope="session")
def created_enclosure_id(base_url, test_zoo, jwt_headers, created_species_id):
    """Legt einmalig ein Test-Gehege an."""
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosures",
        headers=jwt_headers,
        json={
            
            "species_id": created_species_id,
            "domain_id":  None, "note": "Pytest Test"
        }
    )
    if resp.status_code == 403:
        pytest.skip("Kein write_permission für Enclosure-Anlage")
    assert resp.status_code == 201, f"Enclosure anlegen fehlgeschlagen: {resp.text}"
    return resp.json()["id"]
