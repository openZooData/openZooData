"""
test_z_cleanup.py — Aufräum-Tests (laufen alphabetisch zuletzt)

Enthält destruktive Tests (DELETE), die nach allen anderen Tests laufen müssen,
insbesondere nach den Media-Tests.
"""

import pytest
import requests


###############################################################################
# 🧹 Cleanup — verwaiste Media-Einträge löschen
###############################################################################

@pytest.mark.media
@pytest.mark.write
@pytest.mark.jwt
def test_cleanup_uploaded_media(base_url, test_zoo, jwt_headers):
    """
    Löscht alle Media-Einträge die während der Test-Session hochgeladen wurden
    und nicht bereits durch test_media_upload_and_delete gelöscht wurden.
    Benötigt JWT (write_permission) — nicht App-Token.
    """
    media_ids = getattr(pytest, "uploaded_media_ids", [])
    if not media_ids:
        return  # nichts zu tun

    for media_id in media_ids:
        resp = requests.delete(
            f"{base_url}/api/v1/media/{media_id}?zoo={test_zoo}",
            headers=jwt_headers
        )
        # 200 = gelöscht, 404 = war schon weg — beides akzeptabel
        assert resp.status_code in (200, 404), \
            f"Unerwarteter Status beim Cleanup von media_id {media_id}: {resp.status_code}"


###############################################################################
# 🧹 Cleanup — Enclosure löschen
###############################################################################

@pytest.mark.write
@pytest.mark.jwt
def test_enclosure_delete(base_url, test_zoo, jwt_headers, created_enclosure_id):
    """
    DELETE /api/v1/zoos/<zoo>/enclosures/<id> → 200
    Benötigt JWT (write_permission) — nicht App-Token.
    """
    resp = requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosures/{created_enclosure_id}",
        headers=jwt_headers
    )
    assert resp.status_code == 200


###############################################################################
# 🧹 Cleanup — Species löschen
###############################################################################

@pytest.mark.write
@pytest.mark.jwt
def test_species_delete(base_url, jwt_headers, created_species_id, test_zoo):
    """
    DELETE /api/v1/species/<id> → 200
    Benötigt JWT (super_admin).
    Läuft nach Enclosure-Delete — Species darf erst weg wenn
    kein Enclosure mehr darauf verweist.
    """
    resp = requests.delete(
        f"{base_url}/api/v1/species/{created_species_id}",
        headers=jwt_headers
    )
    if resp.status_code == 404 and "Not Found" in resp.text:
        pytest.skip("DELETE /api/v1/species/<id> noch nicht implementiert")
    assert resp.status_code == 200
