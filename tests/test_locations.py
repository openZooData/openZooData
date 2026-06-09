"""
test_locations.py — Tests für Infrastruktur-Locations-CRUD-Endpoints

Endpoints:
  GET    /api/v1/zoos/<zoo>/locations
  GET    /api/v1/zoos/<zoo>/locations/<id>
  POST   /api/v1/zoos/<zoo>/locations
  PUT    /api/v1/zoos/<zoo>/locations/<id>
  DELETE /api/v1/zoos/<zoo>/locations/<id>

Rate-Limit-Hinweise:
  - GET: 60/min — kein Problem
  - POST/PUT: 30/min — sleep(1) zwischen schreibenden Operationen
  - DELETE: 10/min — sleep(1) vor Delete-Tests
"""

import time
import pytest
import requests


###############################################################################
# ── GET /api/v1/zoos/<zoo>/locations ─────────────────────────────────────────
###############################################################################

def test_locations_list_requires_auth(base_url, test_zoo):
    """GET /api/v1/zoos/<zoo>/locations ohne Auth → 401/403."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/locations")
    assert resp.status_code in (401, 403)


@pytest.mark.jwt
def test_locations_list_returns_array(base_url, jwt_headers, test_zoo):
    """GET /api/v1/zoos/<zoo>/locations → 200 + Array."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/locations",
                        headers=jwt_headers)
    assert resp.status_code == 200, f"Locations: {resp.text}"
    assert isinstance(resp.json(), list)


@pytest.mark.jwt
def test_locations_list_entry_structure(base_url, jwt_headers, test_zoo):
    """GET /api/v1/zoos/<zoo>/locations → Einträge haben Pflichtfelder."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/locations",
                        headers=jwt_headers)
    assert resp.status_code == 200
    locations = resp.json()
    if len(locations) == 0:
        pytest.skip("Keine Locations im Test-Zoo vorhanden")
    loc = locations[0]
    for field in ("id", "name", "location_type", "sort_order"):
        assert field in loc, f"Pflichtfeld '{field}' fehlt"


###############################################################################
# ── Fixtures ─────────────────────────────────────────────────────────────────
###############################################################################

@pytest.fixture(scope="module")
def created_location_id(base_url, test_zoo, jwt_headers):
    """Legt eine Test-Location an und löscht sie nach den Tests."""
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/locations",
        headers=jwt_headers,
        json={
            "name": "Test Toilette",
            "name_display": "WC",
            "description": "Öffentliche Toilette",
            "location_type": "Infrastruktur",
            "sort_order": 99,
        }
    )
    assert resp.status_code == 201, \
        f"Location anlegen fehlgeschlagen: {resp.text}"
    location_id = resp.json()["id"]

    yield location_id

    # Cleanup
    time.sleep(1)
    requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/locations/{location_id}",
        headers=jwt_headers
    )


###############################################################################
# ── POST /api/v1/zoos/<zoo>/locations ────────────────────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_location_create(base_url, jwt_headers, test_zoo, created_location_id):
    """POST /api/v1/zoos/<zoo>/locations → 201 + id."""
    assert isinstance(created_location_id, int)
    assert created_location_id > 0


@pytest.mark.jwt
@pytest.mark.write
def test_location_create_missing_name(base_url, jwt_headers, test_zoo):
    """POST ohne name → 400."""
    time.sleep(1)
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/locations",
        headers=jwt_headers,
        json={"location_type": "Infrastruktur"}
    )
    assert resp.status_code == 400, \
        f"Location ohne Name sollte 400 geben, got {resp.status_code}"


@pytest.mark.jwt
@pytest.mark.write
def test_location_create_wrong_zoo(base_url, jwt_headers):
    """POST auf nicht existierendem Zoo → 403/404."""
    time.sleep(1)
    resp = requests.post(
        f"{base_url}/api/v1/zoos/zoo_does_not_exist/locations",
        headers=jwt_headers,
        json={"name": "Sollte fehlschlagen"}
    )
    assert resp.status_code in (403, 404)


@pytest.mark.jwt
def test_location_create_requires_auth(base_url, test_zoo):
    """POST ohne Auth → 401/403."""
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/locations",
        json={"name": "Kein Auth"}
    )
    assert resp.status_code in (401, 403)


###############################################################################
# ── GET /api/v1/zoos/<zoo>/locations/<id> ────────────────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_location_get_detail(base_url, jwt_headers, test_zoo,
                              created_location_id):
    """GET /api/v1/zoos/<zoo>/locations/<id> → 200 + korrekte Felder."""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/locations/{created_location_id}",
        headers=jwt_headers
    )
    assert resp.status_code == 200, f"Location Detail: {resp.text}"
    loc = resp.json()
    assert loc["id"] == created_location_id
    assert loc["name"] == "Test Toilette"
    assert loc["name_display"] == "WC"
    assert loc["location_type"] == "Infrastruktur"
    assert isinstance(loc["opening_hours"], list)


@pytest.mark.jwt
@pytest.mark.write
def test_location_get_nonexistent(base_url, jwt_headers, test_zoo):
    """GET nicht existierende Location → 404."""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/locations/999999",
        headers=jwt_headers
    )
    assert resp.status_code == 404


@pytest.mark.jwt
def test_location_get_requires_auth(base_url, test_zoo):
    """GET ohne Auth → 401/403."""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/locations/1"
    )
    assert resp.status_code in (401, 403)


###############################################################################
# ── PUT /api/v1/zoos/<zoo>/locations/<id> ────────────────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_location_update(base_url, jwt_headers, test_zoo,
                          created_location_id):
    """PUT /api/v1/zoos/<zoo>/locations/<id> → 200."""
    time.sleep(1)
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/locations/{created_location_id}",
        headers=jwt_headers,
        json={"name": "Test Toilette (aktualisiert)", "sort_order": 50}
    )
    assert resp.status_code == 200, f"Location Update: {resp.text}"

    # Änderung verifizieren
    get_resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/locations/{created_location_id}",
        headers=jwt_headers
    )
    assert get_resp.json()["name"] == "Test Toilette (aktualisiert)"
    assert get_resp.json()["sort_order"] == 50


@pytest.mark.jwt
@pytest.mark.write
def test_location_update_unknown_fields(base_url, jwt_headers, test_zoo,
                                         created_location_id):
    """PUT mit unbekannten Feldern → 400."""
    time.sleep(1)
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/locations/{created_location_id}",
        headers=jwt_headers,
        json={"unknown_field": "value"}
    )
    assert resp.status_code == 400


@pytest.mark.jwt
@pytest.mark.write
def test_location_update_empty_name(base_url, jwt_headers, test_zoo,
                                     created_location_id):
    """PUT mit leerem name → 400."""
    time.sleep(1)
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/locations/{created_location_id}",
        headers=jwt_headers,
        json={"name": ""}
    )
    assert resp.status_code == 400


###############################################################################
# ── DELETE /api/v1/zoos/<zoo>/locations/<id> ─────────────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_location_delete(base_url, jwt_headers, test_zoo):
    """DELETE /api/v1/zoos/<zoo>/locations/<id> → 200."""
    time.sleep(1)
    # Separate Location für Delete-Test anlegen
    create_resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/locations",
        headers=jwt_headers,
        json={"name": "Zu löschende Location"}
    )
    assert create_resp.status_code == 201
    delete_id = create_resp.json()["id"]

    time.sleep(1)
    delete_resp = requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/locations/{delete_id}",
        headers=jwt_headers
    )
    assert delete_resp.status_code == 200

    # Verifizieren dass es weg ist
    get_resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/locations/{delete_id}",
        headers=jwt_headers
    )
    assert get_resp.status_code == 404


@pytest.mark.jwt
@pytest.mark.write
def test_location_delete_nonexistent(base_url, jwt_headers, test_zoo):
    """DELETE nicht existierende Location → 404."""
    time.sleep(1)
    resp = requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/locations/999999",
        headers=jwt_headers
    )
    assert resp.status_code == 404
