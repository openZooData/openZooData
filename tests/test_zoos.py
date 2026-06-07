"""
test_zoos.py — Tests für Zoos, Houses und Zoo-Species-Endpoints

Endpoints:
  GET  /api/v1/zoos
  GET  /api/v1/zoos/<zoo>
  GET  /api/v1/zoos/<zoo>/houses  (CRUD)
  GET  /api/v1/zoos/<zoo>/species

Rate-Limit-Hinweise:
  - Alle GET-Endpoints: 60/min — kein Problem im normalen Testlauf
  - POST/PUT/DELETE Houses: 30/10/min — Tests mit sleep(1) zwischen
    schreibenden Operationen um Rate-Limit nicht zu treffen
  - Tests mit Marker 'write' laufen nicht automatisch
"""

import time
import pytest
import requests


###############################################################################
# ── GET /api/v1/zoos ─────────────────────────────────────────────────────────
###############################################################################

def test_zoos_list_requires_auth(base_url):
    """GET /api/v1/zoos ohne Auth → 401/403."""
    resp = requests.get(f"{base_url}/api/v1/zoos")
    assert resp.status_code in (401, 403), \
        f"Zoo-Liste ohne Auth sollte abgewiesen werden, got {resp.status_code}"


@pytest.mark.jwt
def test_zoos_list_returns_array(base_url, jwt_headers):
    """GET /api/v1/zoos → 200 + Array."""
    resp = requests.get(f"{base_url}/api/v1/zoos", headers=jwt_headers)
    assert resp.status_code == 200, f"Zoo-Liste: {resp.text}"
    assert isinstance(resp.json(), list), "Antwort muss ein Array sein"


@pytest.mark.jwt
def test_zoos_list_contains_test_zoo(base_url, jwt_headers, test_zoo):
    """GET /api/v1/zoos → enthält TEST_ZOO."""
    resp = requests.get(f"{base_url}/api/v1/zoos", headers=jwt_headers)
    assert resp.status_code == 200
    slugs = [z["slug"] for z in resp.json()]
    assert test_zoo in slugs, \
        f"Test-Zoo '{test_zoo}' nicht in Zoo-Liste: {slugs}"


@pytest.mark.jwt
def test_zoos_list_entry_structure(base_url, jwt_headers):
    """GET /api/v1/zoos → Einträge haben Pflichtfelder."""
    resp = requests.get(f"{base_url}/api/v1/zoos", headers=jwt_headers)
    assert resp.status_code == 200
    zoos = resp.json()
    assert len(zoos) > 0, "Zoo-Liste ist leer"
    z = zoos[0]
    for field in ("id", "slug", "name", "data_version"):
        assert field in z, f"Pflichtfeld '{field}' fehlt in Zoo-Eintrag"


def test_zoos_list_app_token_rejected(base_url, app_token_headers):
    """GET /api/v1/zoos mit App-Token → 403.
    End-User-App hat keinen Zugriff auf die API — nur JWT (Backend-User).
    End-User-App nutzt ausschließlich GET /db/<zoo> (SQLite-Download).
    """
    resp = requests.get(f"{base_url}/api/v1/zoos", headers=app_token_headers)
    assert resp.status_code == 403, \
        f"App-Token darf keine Zoo-Liste abrufen, got {resp.status_code}"


###############################################################################
# ── GET /api/v1/zoos/<zoo> ───────────────────────────────────────────────────
###############################################################################

@pytest.mark.jwt
def test_zoo_details_returns_200(base_url, jwt_headers, test_zoo):
    """GET /api/v1/zoos/<zoo> → 200."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}",
                        headers=jwt_headers)
    assert resp.status_code == 200, \
        f"Zoo-Details: {resp.text}"


@pytest.mark.jwt
def test_zoo_details_structure(base_url, jwt_headers, test_zoo):
    """GET /api/v1/zoos/<zoo> → korrekte Felder."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}",
                        headers=jwt_headers)
    assert resp.status_code == 200
    z = resp.json()
    for field in ("id", "slug", "name", "data_version", "opening_hours"):
        assert field in z, f"Pflichtfeld '{field}' fehlt"
    assert isinstance(z["opening_hours"], list), \
        "opening_hours muss ein Array sein"
    assert z["slug"] == test_zoo, \
        f"slug '{z['slug']}' stimmt nicht mit {test_zoo} überein"


@pytest.mark.jwt
def test_zoo_details_invalid_slug(base_url, jwt_headers):
    """GET /api/v1/zoos/<ungültiger slug> → 400."""
    resp = requests.get(f"{base_url}/api/v1/zoos/../../etc/passwd",
                        headers=jwt_headers)
    assert resp.status_code in (400, 404), \
        f"Ungültiger Slug sollte 400 geben, got {resp.status_code}"


@pytest.mark.jwt
def test_zoo_details_nonexistent(base_url, jwt_headers):
    """GET /api/v1/zoos/does_not_exist → 403 oder 404."""
    resp = requests.get(f"{base_url}/api/v1/zoos/does_not_exist_xyz",
                        headers=jwt_headers)
    # 403 weil kein Zugriff auf diesen Zoo, oder 404 wenn explizit nicht gefunden
    assert resp.status_code in (403, 404), \
        f"Nicht existierender Zoo: {resp.status_code}"


@pytest.mark.jwt
def test_zoo_details_requires_auth(base_url, test_zoo):
    """GET /api/v1/zoos/<zoo> ohne Auth → 401/403."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}")
    assert resp.status_code in (401, 403)


###############################################################################
# ── GET /api/v1/zoos/<zoo>/species ───────────────────────────────────────────
###############################################################################

@pytest.mark.jwt
def test_zoo_species_returns_array(base_url, jwt_headers, test_zoo):
    """GET /api/v1/zoos/<zoo>/species → 200 + Array."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/species",
                        headers=jwt_headers)
    assert resp.status_code == 200, f"Zoo-Species: {resp.text}"
    assert isinstance(resp.json(), list)


@pytest.mark.jwt
def test_zoo_species_entry_structure(base_url, jwt_headers, test_zoo):
    """GET /api/v1/zoos/<zoo>/species → Einträge haben Pflichtfelder."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/species",
                        headers=jwt_headers)
    assert resp.status_code == 200
    species = resp.json()
    if len(species) == 0:
        pytest.skip("Keine Species im Test-Zoo vorhanden")
    s = species[0]
    for field in ("id", "german_name", "latin_name", "enclosure_count"):
        assert field in s, f"Pflichtfeld '{field}' fehlt"
    assert isinstance(s["enclosure_count"], int)


@pytest.mark.jwt
def test_zoo_species_search(base_url, jwt_headers, test_zoo):
    """GET /api/v1/zoos/<zoo>/species?search=... → filtert korrekt."""
    # Erst alle laden
    all_resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/species",
                            headers=jwt_headers)
    assert all_resp.status_code == 200
    all_species = all_resp.json()
    if len(all_species) == 0:
        pytest.skip("Keine Species im Test-Zoo vorhanden")

    # Suche nach erstem deutschen Namen
    first_name = all_species[0]["german_name"]
    search_term = first_name[:4]  # ersten 4 Zeichen

    search_resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/species",
        headers=jwt_headers,
        params={"search": search_term}
    )
    assert search_resp.status_code == 200
    results = search_resp.json()
    assert len(results) > 0, f"Suche nach '{search_term}' hat keine Treffer"
    assert len(results) <= len(all_species), \
        "Suche darf nicht mehr Ergebnisse als Gesamtliste haben"


@pytest.mark.jwt
def test_zoo_species_invalid_domain_id(base_url, jwt_headers, test_zoo):
    """GET /api/v1/zoos/<zoo>/species?domain_id=abc → 400."""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/species",
        headers=jwt_headers,
        params={"domain_id": "not_an_integer"}
    )
    assert resp.status_code == 400, \
        f"Ungültige domain_id sollte 400 geben, got {resp.status_code}"


@pytest.mark.jwt
def test_zoo_species_requires_auth(base_url, test_zoo):
    """GET /api/v1/zoos/<zoo>/species ohne Auth → 401/403."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/species")
    assert resp.status_code in (401, 403)


###############################################################################
# ── Houses CRUD ──────────────────────────────────────────────────────────────
###############################################################################

@pytest.fixture(scope="module")
def created_house_id(base_url, test_zoo, jwt_headers):
    """Legt ein Test-House an und löscht es nach den Tests."""
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/houses",
        headers=jwt_headers,
        json={"name": "Test Affenhaus", "description": "Für automatische Tests"}
    )
    assert resp.status_code == 201, \
        f"House anlegen fehlgeschlagen: {resp.text}"
    house_id = resp.json()["id"]

    yield house_id

    # Cleanup
    requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/houses/{house_id}",
        headers=jwt_headers
    )


@pytest.mark.jwt
def test_houses_list_returns_array(base_url, jwt_headers, test_zoo):
    """GET /api/v1/zoos/<zoo>/houses → 200 + Array."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/houses",
                        headers=jwt_headers)
    assert resp.status_code == 200, f"Houses: {resp.text}"
    assert isinstance(resp.json(), list)


@pytest.mark.jwt
@pytest.mark.write
def test_houses_create(base_url, jwt_headers, test_zoo, created_house_id):
    """POST /api/v1/zoos/<zoo>/houses → 201 + id."""
    assert isinstance(created_house_id, int)
    assert created_house_id > 0


@pytest.mark.jwt
@pytest.mark.write
def test_houses_get_detail(base_url, jwt_headers, test_zoo, created_house_id):
    """GET /api/v1/zoos/<zoo>/houses/<id> → 200 + korrekte Felder."""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/houses/{created_house_id}",
        headers=jwt_headers
    )
    assert resp.status_code == 200, f"House Detail: {resp.text}"
    h = resp.json()
    assert h["id"] == created_house_id
    assert h["name"] == "Test Affenhaus"
    assert h["description"] == "Für automatische Tests"
    assert isinstance(h["enclosures"], list)


@pytest.mark.jwt
@pytest.mark.write
def test_houses_update(base_url, jwt_headers, test_zoo, created_house_id):
    """PUT /api/v1/zoos/<zoo>/houses/<id> → 200."""
    time.sleep(1)  # Rate-Limit: 30/min für POST, also kurz warten
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/houses/{created_house_id}",
        headers=jwt_headers,
        json={"name": "Test Affenhaus (aktualisiert)", "sponsor": "OpenZooData"}
    )
    assert resp.status_code == 200, f"House Update: {resp.text}"

    # Änderung verifizieren
    get_resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/houses/{created_house_id}",
        headers=jwt_headers
    )
    assert get_resp.json()["name"] == "Test Affenhaus (aktualisiert)"
    assert get_resp.json()["sponsor"] == "OpenZooData"


@pytest.mark.jwt
@pytest.mark.write
def test_houses_create_missing_name(base_url, jwt_headers, test_zoo):
    """POST /api/v1/zoos/<zoo>/houses ohne name → 400."""
    time.sleep(1)
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/houses",
        headers=jwt_headers,
        json={"description": "Kein Name"}
    )
    assert resp.status_code == 400, \
        f"House ohne Name sollte 400 geben, got {resp.status_code}"


@pytest.mark.jwt
@pytest.mark.write
def test_houses_create_wrong_zoo(base_url, jwt_headers):
    """POST /api/v1/zoos/<falscher_zoo>/houses → 403/404."""
    time.sleep(1)
    resp = requests.post(
        f"{base_url}/api/v1/zoos/zoo_does_not_exist/houses",
        headers=jwt_headers,
        json={"name": "Sollte fehlschlagen"}
    )
    assert resp.status_code in (403, 404), \
        f"Falscher Zoo sollte 403/404 geben, got {resp.status_code}"


@pytest.mark.jwt
@pytest.mark.write
def test_houses_update_unknown_fields(base_url, jwt_headers, test_zoo,
                                      created_house_id):
    """PUT mit unbekannten Feldern → 400."""
    time.sleep(1)
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/houses/{created_house_id}",
        headers=jwt_headers,
        json={"unknown_field": "value"}
    )
    assert resp.status_code == 400, \
        f"Unbekannte Felder sollten 400 geben, got {resp.status_code}"


@pytest.mark.jwt
@pytest.mark.write
def test_houses_delete(base_url, jwt_headers, test_zoo):
    """DELETE /api/v1/zoos/<zoo>/houses/<id> → 200."""
    time.sleep(1)
    # Separates House für Delete-Test anlegen
    create_resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/houses",
        headers=jwt_headers,
        json={"name": "Zu löschendes Haus"}
    )
    assert create_resp.status_code == 201
    delete_id = create_resp.json()["id"]

    time.sleep(1)
    delete_resp = requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/houses/{delete_id}",
        headers=jwt_headers
    )
    assert delete_resp.status_code == 200

    # Verifizieren dass es weg ist
    get_resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/houses/{delete_id}",
        headers=jwt_headers
    )
    assert get_resp.status_code == 404


@pytest.mark.jwt
@pytest.mark.write
def test_houses_delete_nonexistent(base_url, jwt_headers, test_zoo):
    """DELETE nicht existierendes House → 404."""
    time.sleep(1)
    resp = requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/houses/999999",
        headers=jwt_headers
    )
    assert resp.status_code == 404, \
        f"Nicht existierendes House sollte 404 geben, got {resp.status_code}"


@pytest.mark.jwt
def test_houses_requires_auth(base_url, test_zoo):
    """GET /api/v1/zoos/<zoo>/houses ohne Auth → 401/403."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/houses")
    assert resp.status_code in (401, 403)
