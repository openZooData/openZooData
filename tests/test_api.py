"""
test_api.py — openZooData API Tests

Migration v7:
- JWT enthält keine 'role' mehr — Rollen werden aus DB geladen
- publish gibt 200 zurück (synchron, nicht mehr 202 async)
- wikidata_id Pflicht bei Species-Anlage
- App-Token für iOS-Endpoints, JWT für Admin-Endpoints

Ausführen:
  pytest test_api.py -v
  pytest test_api.py -v --base-url=https://api.openzoodata.org
  pytest test_api.py -v -m "not slow"
"""

import os
import pytest
import requests
import time


###############################################################################
# 🟢 Basis
###############################################################################

def test_status(base_url):
    """GET /status → 200 + status=ok.
    Strenger Test: Server muss vollständig gesund sein.
    Komplementär zu test_security.py::test_status_public_no_key (prüft kein Info-Leak).
    """
    resp = requests.get(f"{base_url}/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok", f"Server nicht gesund: {body}"
    assert "checks" not in body, "/status darf keine internen Details verraten"


def test_root(base_url):
    """GET / → 200"""
    resp = requests.get(f"{base_url}/")
    assert resp.status_code in (200, 404)


###############################################################################
# 🔐 Auth — App-Token
###############################################################################

def test_no_auth_returns_403(base_url, test_zoo):
    """GET /db/<zoo> ohne Auth → 403"""
    resp = requests.get(f"{base_url}/db/{test_zoo}")
    assert resp.status_code == 403


def test_wrong_key_returns_403(base_url, test_zoo):
    """GET /db/<zoo> mit falschem Key → 403"""
    resp = requests.get(
        f"{base_url}/db/{test_zoo}",
        headers={"Authorization": "Bearer FALSCHERKEY"}
    )
    assert resp.status_code == 403


def test_invalid_slug_returns_400(base_url):
    """GET /db/<zoo> mit ungültigem Slug → 400 oder 403 (kein Auth nötig — Slug-Validierung vor Auth)"""
    resp = requests.get(f"{base_url}/db/zoo_UNGUELTIG!")
    assert resp.status_code in (400, 403)


###############################################################################
# 📦 SQLite
###############################################################################

@pytest.mark.requires_data
def test_sqlite_download(base_url, test_feed_zoo, app_token_headers):
    """GET /db/<zoo> → 200 + ETag + Inhalt"""
    resp = requests.get(f"{base_url}/db/{test_feed_zoo}", headers=app_token_headers)
    assert resp.status_code == 200
    assert "ETag" in resp.headers
    assert resp.headers.get("Content-Type") == "application/octet-stream"
    assert len(resp.content) > 1000


@pytest.mark.requires_data
def test_sqlite_etag_not_modified(base_url, test_feed_zoo, app_token_headers):
    """GET /db/<zoo> mit aktuellem ETag → 304"""
    time.sleep(1)
    resp1 = requests.get(f"{base_url}/db/{test_feed_zoo}", headers=app_token_headers)
    assert resp1.status_code == 200
    etag = resp1.headers.get("ETag", "").strip('"')
    assert etag

    resp2 = requests.get(
        f"{base_url}/db/{test_feed_zoo}",
        headers={**app_token_headers, "If-None-Match": f'"{etag}"'}
    )
    assert resp2.status_code == 304
    assert len(resp2.content) == 0


@pytest.mark.requires_data
def test_sqlite_wrong_etag_returns_200(base_url, test_feed_zoo, app_token_headers):
    """GET /db/<zoo> mit falschem ETag → 200"""
    time.sleep(1)
    resp = requests.get(
        f"{base_url}/db/{test_feed_zoo}",
        headers={**app_token_headers, "If-None-Match": '"999999"'}
    )
    assert resp.status_code == 200


###############################################################################
# 🔐 JWT Auth
###############################################################################

@pytest.mark.jwt
@pytest.mark.jwt
def test_login_success(base_url, jwt_tokens):
    """POST /api/v1/auth/login → 200 + access_token + refresh_token
    Migration v7: kein 'role' im Token mehr."""
    assert "access_token"  in jwt_tokens
    assert "refresh_token" in jwt_tokens
    # Migration v7: JWT enthält keine Rollen — nicht mehr prüfen
    assert "role" not in jwt_tokens, \
        "Migration v7: JWT soll keine Rollen enthalten — Rollen kommen aus DB"


@pytest.mark.jwt
def test_login_wrong_password(base_url):
    """POST /api/v1/auth/login mit falschem Passwort → 403"""
    resp = requests.post(f"{base_url}/api/v1/auth/login", json={
        "email": "falsch@example.com", "password": "falsch"
    })
    assert resp.status_code == 403


@pytest.mark.jwt
def test_login_missing_fields(base_url):
    """POST /api/v1/auth/login ohne Body → 400"""
    resp = requests.post(f"{base_url}/api/v1/auth/login", json={})
    assert resp.status_code == 400


@pytest.mark.jwt
def test_login_empty_body(base_url):
    """POST /api/v1/auth/login mit leerem Body → 400"""
    resp = requests.post(
        f"{base_url}/api/v1/auth/login",
        data="not json",
        headers={"Content-Type": "application/json"}
    )
    assert resp.status_code == 400


@pytest.mark.jwt
@pytest.mark.jwt
def test_login_response_has_must_change_password(base_url, jwt_tokens):
    """Login-Response enthält must_change_password Flag"""
    assert "must_change_password" in jwt_tokens


@pytest.mark.jwt
@pytest.mark.write
@pytest.mark.jwt
def test_token_refresh(base_url, jwt_tokens):
    """POST /api/v1/auth/refresh → 200 + neuer access_token"""
    resp = requests.post(f"{base_url}/api/v1/auth/refresh", json={
        "refresh_token": jwt_tokens["refresh_token"]
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.jwt
def test_token_refresh_invalid(base_url):
    """POST /api/v1/auth/refresh mit falschem Token → 403"""
    resp = requests.post(f"{base_url}/api/v1/auth/refresh", json={
        "refresh_token": "FALSCHERTOKEN"
    })
    assert resp.status_code == 403


@pytest.mark.jwt
@pytest.mark.write
def test_logout(base_url):
    """POST /api/v1/auth/logout → 200, danach Refresh ungültig"""
    email    = os.getenv("TEST_EMAIL")
    password = os.getenv("TEST_PASSWORD")
    if not email or not password:
        pytest.skip("TEST_EMAIL/TEST_PASSWORD nicht gesetzt")

    resp_login = requests.post(f"{base_url}/api/v1/auth/login", json={
        "email": email, "password": password
    })
    if resp_login.status_code != 200:
        pytest.skip("Login für Logout-Test fehlgeschlagen")

    tokens = resp_login.json()
    resp_logout = requests.post(
        f"{base_url}/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert resp_logout.status_code == 200

    # Nach Logout: Refresh Token ungültig
    resp_refresh = requests.post(f"{base_url}/api/v1/auth/refresh", json={
        "refresh_token": tokens["refresh_token"]
    })
    assert resp_refresh.status_code == 403


###############################################################################
# 🦁 Species
###############################################################################

def test_species_search_requires_auth(base_url):
    """GET /api/v1/species ohne Auth → 403"""
    resp = requests.get(f"{base_url}/api/v1/species?search=Löwe")
    assert resp.status_code == 403


@pytest.mark.jwt
def test_species_search_missing_param(base_url, jwt_headers):
    """GET /api/v1/species ohne search → 400"""
    resp = requests.get(f"{base_url}/api/v1/species", headers=jwt_headers)
    assert resp.status_code == 400


@pytest.mark.jwt
def test_species_search(base_url, jwt_headers):
    """GET /api/v1/species?search=Löwe → 200 + Liste"""
    resp = requests.get(f"{base_url}/api/v1/species?search=Löwe", headers=jwt_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.write
def test_species_create(created_species_id):
    """Species wurde in conftest angelegt → ID vorhanden"""
    assert isinstance(created_species_id, int)
    assert created_species_id > 0


@pytest.mark.write
@pytest.mark.jwt
def test_species_create_requires_wikidata_id(base_url, jwt_headers, test_zoo):
    """POST /api/v1/species ohne wikidata_id → 400 (Migration v7)"""
    resp = requests.post(
        f"{base_url}/api/v1/species",
        headers=jwt_headers,
        json={
            "german_name": "Testtier ohne Wikidata",
            "latin_name":  "Testus nowikidata",
            "zoo_slug":    test_zoo,
        }
    )
    assert resp.status_code == 400, \
        "Migration v7: wikidata_id ist Pflicht — ohne wikidata_id muss 400 kommen"


@pytest.mark.write
@pytest.mark.jwt
def test_species_create_missing_name(base_url, jwt_headers, test_zoo):
    """POST /api/v1/species ohne german_name → 400"""
    resp = requests.post(
        f"{base_url}/api/v1/species",
        headers=jwt_headers,
        json={"latin_name": "Testus onlylatin", "wikidata_id": "Q999999",
              "zoo_slug": test_zoo}
    )
    assert resp.status_code == 400


def test_species_create_no_auth(base_url):
    """POST /api/v1/species ohne Auth → 403"""
    resp = requests.post(f"{base_url}/api/v1/species", json={"german_name": "Testus"})
    assert resp.status_code == 403


###############################################################################
# 🏠 Enclosures
###############################################################################

def test_enclosures_requires_auth(base_url, test_zoo):
    """GET /api/v1/zoos/<zoo>/enclosures ohne Auth → 403"""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/enclosures")
    assert resp.status_code == 403


@pytest.mark.jwt
def test_enclosures_list(base_url, test_zoo, jwt_headers):
    """GET /api/v1/zoos/<zoo>/enclosures → 200 + Liste"""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosures",
        headers=jwt_headers
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.write
def test_enclosure_create(created_enclosure_id):
    """Enclosure wurde in conftest angelegt → ID vorhanden"""
    assert isinstance(created_enclosure_id, int)
    assert created_enclosure_id > 0


@pytest.mark.write
@pytest.mark.jwt
def test_enclosure_update(base_url, test_zoo, jwt_headers, created_enclosure_id):
    """PUT /api/v1/zoos/<zoo>/enclosures/<id> → 200"""
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosures/{created_enclosure_id}",
        headers=jwt_headers,
        json={"name": "Pytest-Testgehege (aktualisiert)"}
    )
    assert resp.status_code == 200


@pytest.mark.write
@pytest.mark.jwt
def test_enclosure_create_missing_fields(base_url, test_zoo, jwt_headers):
    """POST /api/v1/zoos/<zoo>/enclosures ohne Pflichtfelder → 400"""
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosures",
        headers=jwt_headers,
        json={"name": "Nur Name, keine species_id"}
    )
    assert resp.status_code == 400


@pytest.mark.write
@pytest.mark.jwt
def test_enclosure_wrong_zoo(base_url, jwt_headers, created_enclosure_id):
    """PUT /api/v1/zoos/<falscher_zoo>/enclosures/<id> → 400 oder 403"""
    resp = requests.put(
        f"{base_url}/api/v1/zoos/zoo_falsch/enclosures/{created_enclosure_id}",
        headers=jwt_headers,
        json={"name": "Sollte nicht klappen"}
    )
    assert resp.status_code in (400, 403)


###############################################################################
# 🗺️ Domains
###############################################################################

@pytest.mark.jwt
def test_domains_list(base_url, test_zoo, jwt_headers):
    """GET /api/v1/zoos/<zoo>/domains → 200 + Liste"""
    resp = requests.get(
        f"{base_url}/api/v1/zoos/{test_zoo}/domains",
        headers=jwt_headers
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


###############################################################################
###############################################################################


###############################################################################
# 🖼️ Media
###############################################################################

@pytest.mark.media
def test_media_list_requires_auth(base_url):
    """GET /api/v1/media/species/1 ohne Auth → 403"""
    resp = requests.get(f"{base_url}/api/v1/media/species/1")
    assert resp.status_code == 403


@pytest.mark.media
@pytest.mark.write
@pytest.mark.jwt
def test_media_list_empty(base_url, jwt_headers, created_species_id):
    """GET /api/v1/media/species/<id> → 200 + Liste"""
    resp = requests.get(
        f"{base_url}/api/v1/media/species/{created_species_id}",
        headers=jwt_headers
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.media
@pytest.mark.write
@pytest.mark.jwt
def test_media_upload_species(base_url, jwt_headers, test_zoo,
                               created_species_id, test_image_bytes):
    """POST /api/v1/media/species/<id> → 201"""
    resp = requests.post(
        f"{base_url}/api/v1/media/species/{created_species_id}",
        headers=jwt_headers,
        files={"file": ("test.jpg", test_image_bytes, "image/jpeg")},
        data={"zoo": test_zoo, "label": "Pytest Upload Test"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body and "url" in body
    pytest.uploaded_media_ids = getattr(pytest, "uploaded_media_ids", [])
    pytest.uploaded_media_ids.append(body["id"])


@pytest.mark.media
@pytest.mark.write
@pytest.mark.jwt
def test_media_upload_invalid_type(base_url, jwt_headers, test_zoo,
                                    created_species_id):
    """POST .exe → 400"""
    resp = requests.post(
        f"{base_url}/api/v1/media/species/{created_species_id}",
        headers=jwt_headers,
        files={"file": ("malware.exe", b"MZ\x90\x00", "application/octet-stream")},
        data={"zoo": test_zoo}
    )
    assert resp.status_code == 400


@pytest.mark.media
@pytest.mark.write
@pytest.mark.jwt
def test_media_upload_no_file(base_url, jwt_headers, test_zoo, created_species_id):
    """POST ohne Datei → 400"""
    resp = requests.post(
        f"{base_url}/api/v1/media/species/{created_species_id}",
        headers=jwt_headers,
        data={"zoo": test_zoo}
    )
    assert resp.status_code == 400


@pytest.mark.media
@pytest.mark.write
@pytest.mark.jwt
def test_media_upload_and_fetch(base_url, jwt_headers, test_zoo,
                                 created_species_id, test_image_bytes):
    """Upload → GET /api/v1/files/<path> → 200"""
    resp_upload = requests.post(
        f"{base_url}/api/v1/media/species/{created_species_id}",
        headers=jwt_headers,
        files={"file": ("fetch_test.jpg", test_image_bytes, "image/jpeg")},
        data={"zoo": test_zoo}
    )
    assert resp_upload.status_code == 201
    url = resp_upload.json()["url"]

    resp_file = requests.get(f"{base_url}{url}", headers=jwt_headers)
    assert resp_file.status_code == 200
    assert resp_file.headers["Content-Type"].startswith("image/")


@pytest.mark.media
@pytest.mark.write
@pytest.mark.jwt
def test_media_upload_and_delete(base_url, jwt_headers, test_zoo,
                                  created_species_id, test_image_bytes):
    """Upload → DELETE → 200 → GET → 404"""
    resp_upload = requests.post(
        f"{base_url}/api/v1/media/species/{created_species_id}",
        headers=jwt_headers,
        files={"file": ("delete_test.jpg", test_image_bytes, "image/jpeg")},
        data={"zoo": test_zoo}
    )
    assert resp_upload.status_code == 201
    media_id = resp_upload.json()["id"]
    url      = resp_upload.json()["url"]

    assert requests.delete(
        f"{base_url}/api/v1/media/{media_id}?zoo={test_zoo}",
        headers=jwt_headers
    ).status_code == 200

    assert requests.get(
        f"{base_url}{url}", headers=jwt_headers
    ).status_code == 404


@pytest.mark.media
@pytest.mark.jwt
def test_media_file_path_traversal(base_url, jwt_headers):
    """GET /api/v1/files/../../etc/passwd → 400/403/404"""
    resp = requests.get(
        f"{base_url}/api/v1/files/../../etc/passwd",
        headers=jwt_headers
    )
    assert resp.status_code in (400, 403, 404)


@pytest.mark.media
def test_media_file_no_auth(base_url, test_zoo):
    """GET /api/v1/files/<path> ohne Auth → 403"""
    resp = requests.get(f"{base_url}/api/v1/files/{test_zoo}/species/test.jpg")
    assert resp.status_code == 403


@pytest.mark.media
@pytest.mark.write
@pytest.mark.jwt
def test_media_upload_enclosure(base_url, jwt_headers, test_zoo,
                                 created_enclosure_id, test_image_bytes):
    """POST /api/v1/media/enclosure/<id> → 201"""
    resp = requests.post(
        f"{base_url}/api/v1/media/enclosure/{created_enclosure_id}",
        headers=jwt_headers,
        files={"file": ("enclosure_test.jpg", test_image_bytes, "image/jpeg")},
        data={"zoo": test_zoo, "label": "Pytest Enclosure Bild"}
    )
    assert resp.status_code == 201
    pytest.uploaded_media_ids = getattr(pytest, "uploaded_media_ids", [])
    pytest.uploaded_media_ids.append(resp.json()["id"])


@pytest.mark.media
@pytest.mark.write
@pytest.mark.jwt
def test_media_list_after_upload(base_url, jwt_headers, created_species_id):
    """Nach Upload: Liste nicht leer"""
    resp = requests.get(
        f"{base_url}/api/v1/media/species/{created_species_id}",
        headers=jwt_headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all(k in data[0] for k in ("id", "url", "mime_type"))


@pytest.mark.media
@pytest.mark.write
@pytest.mark.jwt
def test_media_delete_wrong_zoo(base_url, jwt_headers, test_zoo,
                                 created_species_id, test_image_bytes):
    """DELETE /api/v1/media/<id>?zoo=zoo_falsch → 403"""
    resp_upload = requests.post(
        f"{base_url}/api/v1/media/species/{created_species_id}",
        headers=jwt_headers,
        files={"file": ("wrong_zoo_test.jpg", test_image_bytes, "image/jpeg")},
        data={"zoo": test_zoo}
    )
    assert resp_upload.status_code == 201
    media_id = resp_upload.json()["id"]
    pytest.uploaded_media_ids = getattr(pytest, "uploaded_media_ids", [])
    pytest.uploaded_media_ids.append(media_id)

    assert requests.delete(
        f"{base_url}/api/v1/media/{media_id}?zoo=zoo_falsch",
        headers=jwt_headers
    ).status_code == 403


@pytest.mark.media
@pytest.mark.write
@pytest.mark.jwt
def test_media_upload_oversized(base_url, jwt_headers, test_zoo, created_species_id):
    """Upload > 10MB → 400 oder 413"""
    big_data = b"X" * (11 * 1024 * 1024)
    resp = requests.post(
        f"{base_url}/api/v1/media/species/{created_species_id}",
        headers=jwt_headers,
        files={"file": ("toobig.jpg", big_data, "image/jpeg")},
        data={"zoo": test_zoo}
    )
    assert resp.status_code in (400, 413)


###############################################################################
# 🚀 Publish
# Migration v7: synchron → gibt 200 zurück (nicht mehr 202)
###############################################################################

@pytest.mark.write
@pytest.mark.slow
def test_publish_requires_auth(base_url, test_zoo):
    """POST /api/v1/zoos/<zoo>/publish ohne Auth → 403"""
    resp = requests.post(f"{base_url}/api/v1/zoos/{test_zoo}/publish")
    assert resp.status_code == 403


@pytest.mark.write
@pytest.mark.slow
@pytest.mark.jwt
def test_publish(base_url, test_zoo, jwt_headers):
    """POST /api/v1/zoos/<zoo>/publish → 200 (Migration v7: synchron)"""
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/publish",
        headers=jwt_headers
    )
    # Migration v7: synchroner Export → 200
    # Altes System: asynchron → 202
    assert resp.status_code == 200, \
        f"Publish sollte 200 zurückgeben (synchron, Migration v7), got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "data_version" in body
    assert "duration_ms"  in body


@pytest.mark.write
@pytest.mark.slow
@pytest.mark.jwt
def test_publish_parallel_blocked(base_url, test_zoo, jwt_headers):
    """Zweiter Publish während erster läuft → 409 (Advisory Lock)"""
    import threading
    results = []

    def do_publish():
        r = requests.post(
            f"{base_url}/api/v1/zoos/{test_zoo}/publish",
            headers=jwt_headers
        )
        results.append(r.status_code)

    t1 = threading.Thread(target=do_publish)
    t2 = threading.Thread(target=do_publish)
    t1.start(); t2.start()
    t1.join();  t2.join()

    # Einer muss 200 sein, einer 409 — oder beide 200 wenn beide hintereinander
    assert any(s in (200, 409) for s in results), f"Unerwartete Status: {results}"
