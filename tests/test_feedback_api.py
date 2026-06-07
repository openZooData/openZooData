"""
test_feedback_api.py — openZooData Feedback API Tests

Migration v7:
- community_key → App-Token (nicht mehr MariaDB-API-Key)
- app_token_headers (Admin) → jwt_headers
- feedback POST braucht App-Token, Admin-Endpoints brauchen JWT

.env Einträge (zusätzlich zu conftest):
  TEST_APP_TOKEN=<App-Token>             ← Community-Requests (Feedback einreichen)
  TEST_ENCLOSURE_ID=<enclosure.id>
  TEST_SPECIES_ID=<species.id>
  TEST_ENRICHMENT_TEXT_ID=<species_texts.id>
"""

import os
import uuid
import pytest
import time
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


###############################################################################
# Fixtures
###############################################################################

@pytest.fixture(scope="session")
def community_headers(app_token):
    """
    Migration v7: Community nutzt App-Token, nicht mehr MariaDB-API-Key.
    Gleiche Fixture wie app_token_headers — explizit benannt für Lesbarkeit.
    """
    return {"Authorization": f"Bearer {app_token}"}


@pytest.fixture(scope="session")
def feedback_enclosure_id():
    val = os.getenv("TEST_ENCLOSURE_ID")
    if not val:
        pytest.skip("TEST_ENCLOSURE_ID nicht gesetzt")
    return int(val)


@pytest.fixture(scope="session")
def feedback_species_id():
    val = os.getenv("TEST_SPECIES_ID")
    if not val:
        pytest.skip("TEST_SPECIES_ID nicht gesetzt")
    return int(val)


@pytest.fixture(scope="session")
def feedback_enrichment_text_id():
    val = os.getenv("TEST_ENRICHMENT_TEXT_ID")
    if not val:
        pytest.skip("TEST_ENRICHMENT_TEXT_ID nicht gesetzt")
    return int(val)


@pytest.fixture(scope="session")
def contributor_uuid():
    return str(uuid.uuid4())


@pytest.fixture(scope="session")
def created_feedback_id(base_url, test_zoo, community_headers,
                        contributor_uuid, feedback_enclosure_id):
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
        headers=community_headers,
        json={"feedback_type_id": 1, "contributor_id": contributor_uuid,
              "enclosure_id": feedback_enclosure_id, "value_time": "14:00"}
    )
    if resp.status_code == 429:
        pytest.skip("Rate Limit erreicht")
    assert resp.status_code == 201, f"Feedback anlegen fehlgeschlagen: {resp.text}"
    return resp.json()["id"]


@pytest.fixture(scope="session")
def created_feedback_id_2(base_url, test_zoo, community_headers, feedback_enclosure_id):
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
        headers=community_headers,
        json={"feedback_type_id": 2, "contributor_id": str(uuid.uuid4()),
              "enclosure_id": feedback_enclosure_id,
              "value_latitude": 52.279, "value_longitude": 7.433}
    )
    if resp.status_code == 429:
        pytest.skip("Rate Limit erreicht")
    assert resp.status_code == 201
    return resp.json()["id"]


###############################################################################
# Feedback-Typen
###############################################################################

@pytest.mark.feedback
def test_feedback_types_no_auth(base_url):
    """GET /api/v1/feedback-types ohne Auth → 403"""
    resp = requests.get(f"{base_url}/api/v1/feedback-types")
    assert resp.status_code == 403


@pytest.mark.feedback
def test_feedback_types(base_url, app_token_headers):
    """GET /api/v1/feedback-types → 200 + Liste"""
    resp = requests.get(f"{base_url}/api/v1/feedback-types", headers=app_token_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 10


@pytest.mark.feedback
def test_feedback_types_structure(base_url, app_token_headers):
    """Feedback-Typen haben korrekte Felder"""
    resp  = requests.get(f"{base_url}/api/v1/feedback-types", headers=app_token_headers)
    types = {t["id"]: t for t in resp.json()}
    assert types[1]["slug"] == "feeding_time"
    assert types[1]["requires_admin_review"] is True
    assert types[8]["slug"] == "report"
    assert types[9]["requires_admin_review"] is False


@pytest.mark.feedback
def test_feedback_types_cache_control(base_url, app_token_headers):
    """GET /api/v1/feedback-types → Cache-Control vorhanden"""
    resp = requests.get(f"{base_url}/api/v1/feedback-types", headers=app_token_headers)
    assert "Cache-Control" in resp.headers


###############################################################################
# Feedback einreichen
###############################################################################

@pytest.mark.feedback
def test_feedback_post_no_auth(base_url, test_zoo, feedback_enclosure_id):
    """POST /feedback ohne Auth → 403"""
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
        json={"feedback_type_id": 1, "contributor_id": str(uuid.uuid4()),
              "enclosure_id": feedback_enclosure_id, "value_time": "10:00"}
    )
    assert resp.status_code == 403


@pytest.mark.feedback
def test_feedback_post_missing_type(base_url, test_zoo, community_headers, contributor_uuid):
    """POST ohne feedback_type_id → 400"""
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
        headers=community_headers,
        json={"contributor_id": contributor_uuid}
    )
    assert resp.status_code == 400


@pytest.mark.feedback
def test_feedback_post_missing_contributor(base_url, test_zoo,
                                           community_headers, feedback_enclosure_id):
    """POST ohne contributor_id → 400"""
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
        headers=community_headers,
        json={"feedback_type_id": 1, "enclosure_id": feedback_enclosure_id,
              "value_time": "10:00"}
    )
    assert resp.status_code == 400


@pytest.mark.feedback
def test_feedback_post_invalid_type_id(base_url, test_zoo,
                                       community_headers, contributor_uuid):
    """POST mit ungültiger feedback_type_id → 400"""
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
        headers=community_headers,
        json={"feedback_type_id": 999, "contributor_id": contributor_uuid}
    )
    assert resp.status_code in (400, 429)


@pytest.mark.feedback
@pytest.mark.write
def test_feedback_post_feeding_time(base_url, test_zoo, community_headers,
                                    feedback_enclosure_id, created_feedback_id):
    """Feedback Typ 1 wurde angelegt → ID vorhanden"""
    assert isinstance(created_feedback_id, int) and created_feedback_id > 0


@pytest.mark.feedback
@pytest.mark.write
def test_feedback_post_position(base_url, test_zoo, community_headers,
                                feedback_enclosure_id, created_feedback_id_2):
    """Feedback Typ 2 wurde angelegt → ID vorhanden"""
    assert isinstance(created_feedback_id_2, int) and created_feedback_id_2 > 0


@pytest.mark.feedback
@pytest.mark.write
def test_feedback_post_new_species_wikidata(base_url, test_zoo,
                                            community_headers, feedback_enclosure_id):
    """POST Typ 3 → 201"""
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
        headers=community_headers,
        json={"feedback_type_id": 3, "contributor_id": str(uuid.uuid4()),
              "enclosure_id": feedback_enclosure_id, "value_wikidata_id": "Q140"}
    )
    assert resp.status_code in (201, 429)


@pytest.mark.feedback
@pytest.mark.write
def test_feedback_post_text_helpful_no_review(base_url, test_zoo,
                                              community_headers,
                                              feedback_enrichment_text_id):
    """POST Typ 9 → 201, status=None"""
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
        headers=community_headers,
        json={"feedback_type_id": 9, "contributor_id": str(uuid.uuid4()),
              "value_enrichment_text_id": feedback_enrichment_text_id}
    )
    assert resp.status_code in (201, 429)
    if resp.status_code == 201:
        assert resp.json().get("status") is None


@pytest.mark.feedback
@pytest.mark.write
def test_feedback_post_text_helpful_duplicate(base_url, test_zoo,
                                              community_headers, feedback_enrichment_text_id):
    """Gleiche UUID + gleicher Typ 9 → 409 beim zweiten Mal"""
    uid  = str(uuid.uuid4())
    body = {"feedback_type_id": 9, "contributor_id": uid,
            "value_enrichment_text_id": feedback_enrichment_text_id}
    r1 = requests.post(f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
                       headers=community_headers, json=body)
    if r1.status_code == 429:
        pytest.skip("Rate Limit")
    assert r1.status_code == 201
    r2 = requests.post(f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
                       headers=community_headers, json=body)
    assert r2.status_code == 409


###############################################################################
# Feedback-Queue (Admin) — braucht JWT
###############################################################################

@pytest.mark.write
@pytest.mark.feedback
def test_feedback_queue_no_auth(base_url, test_zoo):
    """GET /feedback ohne Auth → 403"""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/feedback")
    assert resp.status_code == 403


@pytest.mark.write
@pytest.mark.feedback
def test_feedback_queue_app_token_blocked(base_url, test_zoo, app_token_headers):
    """
    GET /feedback mit App-Token → 403
    Migration v7: Admin-Endpoints brauchen JWT, nicht App-Token.
    """
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
        headers=app_token_headers
    )
    assert resp.status_code == 403, \
        "Admin-Endpoints dürfen nicht mit App-Token erreichbar sein"


@pytest.mark.write
@pytest.mark.feedback
@pytest.mark.jwt
def test_feedback_queue_pending(base_url, test_zoo, jwt_headers, created_feedback_id):
    """GET /feedback?status=pending → 200 + Cluster-Liste"""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
        headers=jwt_headers,
        params={"status": "pending"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "clusters" in data and "total" in data
    assert data["total"] >= 1


@pytest.mark.write
@pytest.mark.feedback
@pytest.mark.jwt
def test_feedback_queue_cluster_structure(base_url, test_zoo,
                                          jwt_headers, created_feedback_id):
    """Cluster hat korrekte Felder"""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
        headers=jwt_headers,
        params={"status": "pending"}
    )
    c = resp.json()["clusters"][0]
    assert all(k in c for k in
               ("feedback_ids", "reporter_count", "feedback_type_slug", "first_reported"))


@pytest.mark.write
@pytest.mark.feedback
@pytest.mark.jwt
def test_feedback_queue_invalid_status(base_url, test_zoo, jwt_headers):
    """GET /feedback?status=ungueltig → 400"""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
        headers=jwt_headers,
        params={"status": "ungueltig"}
    )
    assert resp.status_code == 400


@pytest.mark.write
@pytest.mark.feedback
@pytest.mark.jwt
def test_feedback_queue_wrong_zoo(base_url, jwt_headers):
    """GET /feedback für falschen Zoo → 400 oder 403"""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/zoo_falsch/feedback",
        headers=jwt_headers
    )
    assert resp.status_code in (400, 403)


###############################################################################
# Einzelansicht
###############################################################################

@pytest.mark.write
@pytest.mark.feedback
@pytest.mark.jwt
def test_feedback_single(base_url, test_zoo, jwt_headers, created_feedback_id):
    """GET /feedback/<id> → 200"""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback/{created_feedback_id}",
        headers=jwt_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == created_feedback_id
    assert data["status"] == "pending"


@pytest.mark.write
@pytest.mark.feedback
@pytest.mark.jwt
def test_feedback_single_not_found(base_url, test_zoo, jwt_headers):
    """GET /feedback/999999 → 404"""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback/999999",
        headers=jwt_headers
    )
    assert resp.status_code == 404


@pytest.mark.write
@pytest.mark.feedback
def test_feedback_single_app_token_blocked(base_url, test_zoo,
                                           app_token_headers, created_feedback_id):
    """GET /feedback/<id> mit App-Token → 403"""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback/{created_feedback_id}",
        headers=app_token_headers
    )
    assert resp.status_code == 403


###############################################################################
# Accept / Reject
###############################################################################

@pytest.mark.write
@pytest.mark.feedback
@pytest.mark.jwt
def test_feedback_reject(base_url, test_zoo, jwt_headers, created_feedback_id_2):
    """PUT /feedback/<id>/reject → 200"""
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback/{created_feedback_id_2}/reject",
        headers=jwt_headers,
        json={"comment": "Position bereits korrekt."}
    )
    assert resp.status_code == 200
    assert resp.json().get("updated_count", 0) >= 1


@pytest.mark.write
@pytest.mark.feedback
@pytest.mark.jwt
def test_feedback_reject_already_reviewed(base_url, test_zoo,
                                          jwt_headers, created_feedback_id_2):
    """Nochmal rejecten → 404"""
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback/{created_feedback_id_2}/reject",
        headers=jwt_headers, json={}
    )
    assert resp.status_code == 404


@pytest.mark.write
@pytest.mark.feedback
@pytest.mark.jwt
def test_feedback_accept(base_url, test_zoo, jwt_headers, created_feedback_id):
    """PUT /feedback/<id>/accept → 200"""
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback/{created_feedback_id}/accept",
        headers=jwt_headers,
        json={"comment": "Bestätigt."}
    )
    assert resp.status_code == 200


@pytest.mark.write
@pytest.mark.feedback
@pytest.mark.jwt
def test_feedback_accept_status_updated(base_url, test_zoo,
                                        jwt_headers, created_feedback_id):
    """Nach Accept: status=accepted"""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback/{created_feedback_id}",
        headers=jwt_headers
    )
    assert resp.json()["status"] == "accepted"


@pytest.mark.write
@pytest.mark.feedback
def test_feedback_accept_app_token_blocked(base_url, test_zoo,
                                           app_token_headers, created_feedback_id):
    """PUT /feedback/<id>/accept mit App-Token → 403"""
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/feedback/{created_feedback_id}/accept",
        headers=app_token_headers, json={}
    )
    assert resp.status_code == 403


###############################################################################
# Rate Limiting
###############################################################################

@pytest.mark.feedback
@pytest.mark.slow
def test_feedback_rate_limit_uuid(base_url, test_zoo,
                                  community_headers, created_enclosure_id):
    """3 schnelle Requests → dritter mit 429"""
    time.sleep(62)
    uid  = str(uuid.uuid4())
    body = {"feedback_type_id": 1, "contributor_id": uid,
            "enclosure_id": created_enclosure_id, "value_time": "11:00"}
    r1 = requests.post(f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
                       headers=community_headers, json=body)
    r2 = requests.post(f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
                       headers=community_headers, json=body)
    r3 = requests.post(f"{base_url}/api/v1/zoos/{test_zoo}/feedback",
                       headers=community_headers, json=body)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r3.status_code == 429
