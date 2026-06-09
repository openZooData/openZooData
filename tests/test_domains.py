"""
test_domains.py — Tests für Domains-CRUD-Endpoints

Endpoints:
  GET    /api/v1/zoos/<zoo>/domains
  GET    /api/v1/zoos/<zoo>/domains/<id>
  POST   /api/v1/zoos/<zoo>/domains
  PUT    /api/v1/zoos/<zoo>/domains/<id>
  DELETE /api/v1/zoos/<zoo>/domains/<id>

Rate-Limit-Hinweise:
  - GET: 60/min — kein Problem
  - POST/PUT: 30/min — sleep(1) zwischen schreibenden Operationen
  - DELETE: 10/min — sleep(1) vor Delete-Tests
"""

import time
import pytest
import requests


###############################################################################
# ── GET /api/v1/zoos/<zoo>/domains ───────────────────────────────────────────
###############################################################################

def test_domains_list_requires_auth(base_url, test_zoo):
    """GET /api/v1/zoos/<zoo>/domains ohne Auth → 401/403."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/domains")
    assert resp.status_code in (401, 403)


@pytest.mark.jwt
def test_domains_list_returns_array(base_url, jwt_headers, test_zoo):
    """GET /api/v1/zoos/<zoo>/domains → 200 + Array."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/domains",
                        headers=jwt_headers)
    assert resp.status_code == 200, f"Domains: {resp.text}"
    assert isinstance(resp.json(), list)


@pytest.mark.jwt
def test_domains_list_entry_structure(base_url, jwt_headers, test_zoo):
    """GET /api/v1/zoos/<zoo>/domains → Einträge haben Pflichtfelder."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/domains",
                        headers=jwt_headers)
    assert resp.status_code == 200
    domains = resp.json()
    if len(domains) == 0:
        pytest.skip("Keine Domains im Test-Zoo vorhanden")
    d = domains[0]
    for field in ("id", "name", "is_infrastructure", "sort_order"):
        assert field in d, f"Pflichtfeld '{field}' fehlt"


###############################################################################
# ── Fixtures ─────────────────────────────────────────────────────────────────
###############################################################################

@pytest.fixture(scope="module")
def created_domain_id(base_url, test_zoo, jwt_headers):
    """Legt eine Test-Domain an und löscht sie nach den Tests."""
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/domains",
        headers=jwt_headers,
        json={
            "name": "Test Domain",
            "is_infrastructure": False,
            "sort_order": 99,
            "color_red": 200,
            "color_green": 100,
            "color_blue": 50,
            "color_alpha": 1.0,
        }
    )
    assert resp.status_code == 201, \
        f"Domain anlegen fehlgeschlagen: {resp.text}"
    domain_id = resp.json()["id"]

    yield domain_id

    # Cleanup
    time.sleep(1)
    requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/domains/{domain_id}",
        headers=jwt_headers
    )


###############################################################################
# ── POST /api/v1/zoos/<zoo>/domains ──────────────────────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_domain_create(base_url, jwt_headers, test_zoo, created_domain_id):
    """POST /api/v1/zoos/<zoo>/domains → 201 + id."""
    assert isinstance(created_domain_id, int)
    assert created_domain_id > 0


@pytest.mark.jwt
@pytest.mark.write
def test_domain_create_missing_name(base_url, jwt_headers, test_zoo):
    """POST ohne name → 400."""
    time.sleep(1)
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/domains",
        headers=jwt_headers,
        json={"is_infrastructure": False}
    )
    assert resp.status_code == 400, \
        f"Domain ohne Name sollte 400 geben, got {resp.status_code}"


@pytest.mark.jwt
@pytest.mark.write
def test_domain_create_wrong_zoo(base_url, jwt_headers):
    """POST auf nicht existierendem Zoo → 403/404."""
    time.sleep(1)
    resp = requests.post(
        f"{base_url}/api/v1/zoos/zoo_does_not_exist/domains",
        headers=jwt_headers,
        json={"name": "Sollte fehlschlagen"}
    )
    assert resp.status_code in (403, 404)


@pytest.mark.jwt
def test_domain_create_requires_auth(base_url, test_zoo):
    """POST ohne Auth → 401/403."""
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/domains",
        json={"name": "Kein Auth"}
    )
    assert resp.status_code in (401, 403)


###############################################################################
# ── GET /api/v1/zoos/<zoo>/domains/<id> ──────────────────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_domain_get_detail(base_url, jwt_headers, test_zoo, created_domain_id):
    """GET /api/v1/zoos/<zoo>/domains/<id> → 200 + korrekte Felder."""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/domains/{created_domain_id}",
        headers=jwt_headers
    )
    assert resp.status_code == 200, f"Domain Detail: {resp.text}"
    d = resp.json()
    assert d["id"] == created_domain_id
    assert d["name"] == "Test Domain"
    assert d["is_infrastructure"] is False
    assert d["sort_order"] == 99
    assert d["color_red"] == 200


@pytest.mark.jwt
@pytest.mark.write
def test_domain_get_nonexistent(base_url, jwt_headers, test_zoo):
    """GET nicht existierende Domain → 404."""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/domains/999999",
        headers=jwt_headers
    )
    assert resp.status_code == 404


###############################################################################
# ── PUT /api/v1/zoos/<zoo>/domains/<id> ──────────────────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_domain_update(base_url, jwt_headers, test_zoo, created_domain_id):
    """PUT /api/v1/zoos/<zoo>/domains/<id> → 200."""
    time.sleep(1)
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/domains/{created_domain_id}",
        headers=jwt_headers,
        json={"name": "Test Domain (aktualisiert)", "sort_order": 50}
    )
    assert resp.status_code == 200, f"Domain Update: {resp.text}"

    # Änderung verifizieren
    get_resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/domains/{created_domain_id}",
        headers=jwt_headers
    )
    assert get_resp.json()["name"] == "Test Domain (aktualisiert)"
    assert get_resp.json()["sort_order"] == 50


@pytest.mark.jwt
@pytest.mark.write
def test_domain_update_unknown_fields(base_url, jwt_headers, test_zoo,
                                      created_domain_id):
    """PUT mit unbekannten Feldern → 400."""
    time.sleep(1)
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/domains/{created_domain_id}",
        headers=jwt_headers,
        json={"unknown_field": "value"}
    )
    assert resp.status_code == 400


@pytest.mark.jwt
@pytest.mark.write
def test_domain_update_empty_name(base_url, jwt_headers, test_zoo,
                                   created_domain_id):
    """PUT mit leerem name → 400."""
    time.sleep(1)
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/domains/{created_domain_id}",
        headers=jwt_headers,
        json={"name": ""}
    )
    assert resp.status_code == 400


###############################################################################
# ── DELETE /api/v1/zoos/<zoo>/domains/<id> ───────────────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_domain_delete(base_url, jwt_headers, test_zoo):
    """DELETE /api/v1/zoos/<zoo>/domains/<id> → 200."""
    time.sleep(1)
    # Separates Domain für Delete-Test anlegen
    create_resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/domains",
        headers=jwt_headers,
        json={"name": "Zu löschende Domain"}
    )
    assert create_resp.status_code == 201
    delete_id = create_resp.json()["id"]

    time.sleep(1)
    delete_resp = requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/domains/{delete_id}",
        headers=jwt_headers
    )
    assert delete_resp.status_code == 200

    # Verifizieren dass es weg ist
    get_resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/domains/{delete_id}",
        headers=jwt_headers
    )
    assert get_resp.status_code == 404


@pytest.mark.jwt
@pytest.mark.write
def test_domain_delete_nonexistent(base_url, jwt_headers, test_zoo):
    """DELETE nicht existierende Domain → 404."""
    time.sleep(1)
    resp = requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/domains/999999",
        headers=jwt_headers
    )
    assert resp.status_code == 404
