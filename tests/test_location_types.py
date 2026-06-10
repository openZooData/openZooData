"""
test_location_types.py — Tests für Location-Types-CRUD-Endpoints

Endpoints:
  GET    /api/v1/location-types
  GET    /api/v1/location-types/<id>
  POST   /api/v1/location-types          — nur super_admin
  PUT    /api/v1/location-types/<id>     — nur super_admin
  DELETE /api/v1/location-types/<id>     — nur super_admin

Rate-Limit-Hinweise:
  - GET: 60/min — kein Problem
  - POST/PUT: 30/min — sleep(1) zwischen schreibenden Operationen
  - DELETE: 10/min — sleep(1) vor Delete-Tests
"""

import time
import pytest
import requests


###############################################################################
# ── GET /api/v1/location-types ───────────────────────────────────────────────
###############################################################################

def test_location_types_requires_auth(base_url):
    """GET /api/v1/location-types ohne Auth → 401/403."""
    resp = requests.get(f"{base_url}/api/v1/location-types")
    assert resp.status_code in (401, 403)


@pytest.mark.jwt
def test_location_types_returns_array(base_url, jwt_headers):
    """GET /api/v1/location-types → 200 + Array."""
    resp = requests.get(f"{base_url}/api/v1/location-types",
                        headers=jwt_headers)
    assert resp.status_code == 200, f"Location Types: {resp.text}"
    assert isinstance(resp.json(), list)


@pytest.mark.jwt
def test_location_types_entry_structure(base_url, jwt_headers):
    """GET /api/v1/location-types → Einträge haben Pflichtfelder."""
    resp = requests.get(f"{base_url}/api/v1/location-types",
                        headers=jwt_headers)
    assert resp.status_code == 200
    types = resp.json()
    if len(types) == 0:
        pytest.skip("Keine Location-Typen vorhanden")
    t = types[0]
    for field in ("id", "slug", "name", "sort_order"):
        assert field in t, f"Pflichtfeld '{field}' fehlt"


@pytest.mark.jwt
def test_location_types_app_token_rejected(base_url, app_token_headers):
    """GET /api/v1/location-types mit App-Token → 403."""
    resp = requests.get(f"{base_url}/api/v1/location-types",
                        headers=app_token_headers)
    assert resp.status_code == 403, \
        f"App-Token darf keine Location-Types abrufen, got {resp.status_code}"


###############################################################################
# ── Fixtures ─────────────────────────────────────────────────────────────────
###############################################################################

@pytest.fixture(scope="module")
def created_location_type_id(base_url, jwt_headers):
    """Legt einen Test-Location-Typ an und löscht ihn nach den Tests."""
    resp = requests.post(
        f"{base_url}/api/v1/location-types",
        headers=jwt_headers,
        json={
            "slug": "pytest_test_type",
            "name": "Pytest Test Typ",
            "icon": "toilet",
            "sort_order": 99,
        }
    )
    assert resp.status_code == 201, \
        f"Location-Typ anlegen fehlgeschlagen: {resp.text}"
    type_id = resp.json()["id"]

    yield type_id

    # Cleanup
    time.sleep(1)
    requests.delete(
        f"{base_url}/api/v1/location-types/{type_id}",
        headers=jwt_headers
    )


###############################################################################
# ── POST /api/v1/location-types ──────────────────────────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_location_type_create(base_url, jwt_headers, created_location_type_id):
    """POST /api/v1/location-types → 201 + id."""
    assert isinstance(created_location_type_id, int)
    assert created_location_type_id > 0


@pytest.mark.jwt
@pytest.mark.write
def test_location_type_create_missing_slug(base_url, jwt_headers):
    """POST ohne slug → 400."""
    time.sleep(1)
    resp = requests.post(
        f"{base_url}/api/v1/location-types",
        headers=jwt_headers,
        json={"name": "Kein Slug"}
    )
    assert resp.status_code == 400


@pytest.mark.jwt
@pytest.mark.write
def test_location_type_create_missing_name(base_url, jwt_headers):
    """POST ohne name → 400."""
    time.sleep(1)
    resp = requests.post(
        f"{base_url}/api/v1/location-types",
        headers=jwt_headers,
        json={"slug": "kein_name"}
    )
    assert resp.status_code == 400


@pytest.mark.jwt
@pytest.mark.write
def test_location_type_create_duplicate_slug(base_url, jwt_headers,
                                              created_location_type_id):
    """POST mit doppeltem slug → 409."""
    time.sleep(1)
    resp = requests.post(
        f"{base_url}/api/v1/location-types",
        headers=jwt_headers,
        json={"slug": "pytest_test_type", "name": "Duplikat"}
    )
    assert resp.status_code == 409, \
        f"Doppelter Slug sollte 409 geben, got {resp.status_code}"


def test_location_type_create_requires_auth(base_url):
    """POST ohne Auth → 401/403."""
    resp = requests.post(
        f"{base_url}/api/v1/location-types",
        json={"slug": "no_auth", "name": "Kein Auth"}
    )
    assert resp.status_code in (401, 403)


###############################################################################
# ── GET /api/v1/location-types/<id> ──────────────────────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_location_type_get_detail(base_url, jwt_headers,
                                   created_location_type_id):
    """GET /api/v1/location-types/<id> → 200 + korrekte Felder."""
    resp = requests.get(
        f"{base_url}/api/v1/location-types/{created_location_type_id}",
        headers=jwt_headers
    )
    assert resp.status_code == 200, f"Location-Typ Detail: {resp.text}"
    t = resp.json()
    assert t["id"] == created_location_type_id
    assert t["slug"] == "pytest_test_type"
    assert t["name"] == "Pytest Test Typ"
    assert t["icon"] == "toilet"
    assert t["sort_order"] == 99


@pytest.mark.jwt
def test_location_type_get_nonexistent(base_url, jwt_headers):
    """GET nicht existierender Location-Typ → 404."""
    resp = requests.get(
        f"{base_url}/api/v1/location-types/999999",
        headers=jwt_headers
    )
    assert resp.status_code == 404


###############################################################################
# ── PUT /api/v1/location-types/<id> ──────────────────────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_location_type_update(base_url, jwt_headers,
                               created_location_type_id):
    """PUT /api/v1/location-types/<id> → 200."""
    time.sleep(1)
    resp = requests.put(
        f"{base_url}/api/v1/location-types/{created_location_type_id}",
        headers=jwt_headers,
        json={"name": "Pytest Test Typ (aktualisiert)", "sort_order": 50}
    )
    assert resp.status_code == 200, f"Location-Typ Update: {resp.text}"

    # Änderung verifizieren
    get_resp = requests.get(
        f"{base_url}/api/v1/location-types/{created_location_type_id}",
        headers=jwt_headers
    )
    assert get_resp.json()["name"] == "Pytest Test Typ (aktualisiert)"
    assert get_resp.json()["sort_order"] == 50


@pytest.mark.jwt
@pytest.mark.write
def test_location_type_update_unknown_fields(base_url, jwt_headers,
                                              created_location_type_id):
    """PUT mit unbekannten Feldern → 400."""
    time.sleep(1)
    resp = requests.put(
        f"{base_url}/api/v1/location-types/{created_location_type_id}",
        headers=jwt_headers,
        json={"unknown_field": "value"}
    )
    assert resp.status_code == 400


@pytest.mark.jwt
@pytest.mark.write
def test_location_type_update_empty_name(base_url, jwt_headers,
                                          created_location_type_id):
    """PUT mit leerem name → 400."""
    time.sleep(1)
    resp = requests.put(
        f"{base_url}/api/v1/location-types/{created_location_type_id}",
        headers=jwt_headers,
        json={"name": ""}
    )
    assert resp.status_code == 400


def test_location_type_update_requires_auth(base_url,
                                             created_location_type_id=1):
    """PUT ohne Auth → 401/403."""
    resp = requests.put(
        f"{base_url}/api/v1/location-types/1",
        json={"name": "Kein Auth"}
    )
    assert resp.status_code in (401, 403)


###############################################################################
# ── DELETE /api/v1/location-types/<id> ───────────────────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_location_type_delete(base_url, jwt_headers):
    """DELETE /api/v1/location-types/<id> → 200."""
    time.sleep(1)
    # Separaten Typ für Delete-Test anlegen
    create_resp = requests.post(
        f"{base_url}/api/v1/location-types",
        headers=jwt_headers,
        json={"slug": "pytest_delete_type", "name": "Zu löschender Typ"}
    )
    assert create_resp.status_code == 201
    delete_id = create_resp.json()["id"]

    time.sleep(1)
    delete_resp = requests.delete(
        f"{base_url}/api/v1/location-types/{delete_id}",
        headers=jwt_headers
    )
    assert delete_resp.status_code == 200

    # Verifizieren dass es weg ist
    get_resp = requests.get(
        f"{base_url}/api/v1/location-types/{delete_id}",
        headers=jwt_headers
    )
    assert get_resp.status_code == 404


@pytest.mark.jwt
@pytest.mark.write
def test_location_type_delete_nonexistent(base_url, jwt_headers):
    """DELETE nicht existierender Typ → 404."""
    time.sleep(1)
    resp = requests.delete(
        f"{base_url}/api/v1/location-types/999999",
        headers=jwt_headers
    )
    assert resp.status_code == 404


def test_location_type_delete_requires_auth(base_url):
    """DELETE ohne Auth → 401/403."""
    resp = requests.delete(f"{base_url}/api/v1/location-types/1")
    assert resp.status_code in (401, 403)
