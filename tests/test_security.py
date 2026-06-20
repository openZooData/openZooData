"""
test_security.py — Security-Tests für openZooData

Migration v7:
- /status/details prüft db_auth + db_zoo
- JWT ohne Rollen

Ausführen:
  pytest test_security.py -v
  pytest test_security.py -v --base-url=https://api.openzoodata.org
"""

import time
import pytest
import requests


###############################################################################
# Health-Endpoint
###############################################################################

def test_status_public_no_key(base_url):
    """GET /status ohne Key → 200, kein 'checks' (keine internen Details)"""
    resp = requests.get(f"{base_url}/status")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert "status" in body
    assert "checks" not in body, "/status darf keine internen Details verraten"


def test_status_details_no_key(base_url):
    """GET /status/details ohne Key → 403"""
    resp = requests.get(f"{base_url}/status/details")
    assert resp.status_code == 403


def test_status_details_wrong_key(base_url):
    """GET /status/details mit falschem Key → 403"""
    resp = requests.get(
        f"{base_url}/status/details",
        headers={"X-Health-Key": "falscherkey12345678901234567890"}
    )
    assert resp.status_code == 403


def test_status_details_correct_key(base_url, health_check_key):
    """GET /status/details mit korrektem Key → 200 + db_auth + db_zoo
    Migration v7: db_auth und db_zoo — kein db_analytics."""
    resp = requests.get(
        f"{base_url}/status/details",
        headers={"X-Health-Key": health_check_key}
    )
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert "status"   in body
    assert "checks"   in body
    checks = body["checks"]
    assert "db_auth"      in checks, "db_auth fehlt in /status/details"
    assert "db_zoo"       in checks, "db_zoo fehlt in /status/details"
    assert "sqlite_files" in checks
    assert "db_analytics" not in checks, \
        "db_analytics gehört nicht in /status/details"


###############################################################################
# Login-Lockout
###############################################################################

@pytest.mark.slow
def test_login_lockout_nonexistent_user(base_url):
    """5 Fehlversuche mit nicht existierender E-Mail → alle 403"""
    for i in range(5):
        resp = requests.post(f"{base_url}/api/v1/auth/login", json={
            "email":    "pytest_lockout_nonexistent@example.com",
            "password": f"falsch_{i}"
        })
        assert resp.status_code == 403, f"Erwartet 403 bei Versuch {i+1}"
        time.sleep(1.5)


@pytest.mark.slow
def test_login_error_message_generic(base_url):
    """Fehlermeldung bei Login gibt keine internen Details preis"""
    time.sleep(8)
    resp = requests.post(f"{base_url}/api/v1/auth/login", json={
        "email": "nonexistent@example.com", "password": "falsch"
    })
    assert resp.status_code in (403, 429)
    body = resp.json()
    assert "error" in body
    msg = body["error"].lower()
    assert "sql"       not in msg
    assert "traceback" not in msg
    assert "exception" not in msg
    # Migration v7: kein "locked" oder "temporarily" in Fehlermeldung
    assert "locked"      not in msg, "Lockout-Status darf nicht verraten werden"
    assert "temporarily" not in msg, "Lockout-Status darf nicht verraten werden"


###############################################################################
# SVG-Upload abgelehnt
###############################################################################

@pytest.mark.media
@pytest.mark.write
@pytest.mark.jwt
def test_media_upload_svg_rejected(base_url, jwt_headers, test_zoo,
                                    created_species_id, test_svg_bytes):
    """POST SVG → 400"""
    resp = requests.post(
        f"{base_url}/api/v1/media/species/{created_species_id}",
        headers=jwt_headers,
        files={"file": ("evil.svg", test_svg_bytes, "image/svg+xml")},
        data={"zoo": test_zoo}
    )
    assert resp.status_code == 400


@pytest.mark.media
@pytest.mark.write
@pytest.mark.jwt
def test_media_upload_svg_disguised_as_jpg(base_url, jwt_headers, test_zoo,
                                            created_species_id, test_svg_bytes):
    """SVG als JPEG getarnt → 400 (Magic-Byte-Check)"""
    resp = requests.post(
        f"{base_url}/api/v1/media/species/{created_species_id}",
        headers=jwt_headers,
        files={"file": ("harmless.jpg", test_svg_bytes, "image/jpeg")},
        data={"zoo": test_zoo}
    )
    assert resp.status_code == 400


###############################################################################
# entity_type Whitelist
###############################################################################

@pytest.mark.media
@pytest.mark.jwt
def test_media_invalid_entity_type(base_url, jwt_headers, test_zoo):
    """GET /api/v1/media/exploit/1 → 400"""
    resp = requests.get(
        f"{base_url}/api/v1/media/exploit/1?zoo={test_zoo}",
        headers=jwt_headers
    )
    assert resp.status_code == 400


@pytest.mark.media
@pytest.mark.write
@pytest.mark.jwt
def test_media_valid_entity_types(base_url, jwt_headers, test_zoo, created_species_id):
    """Gültige entity_types → nicht 400"""
    for entity_type in ("species", "enclosure", "zoo", "house", "location"):
        resp = requests.get(
            f"{base_url}/api/v1/media/{entity_type}/{created_species_id}?zoo={test_zoo}",
            headers=jwt_headers
        )
        assert resp.status_code != 400, \
            f"entity_type='{entity_type}' wurde fälschlich mit 400 abgelehnt"


###############################################################################
# Cross-Tenant Dateizugriff
###############################################################################

@pytest.mark.media
@pytest.mark.jwt
def test_serve_file_path_traversal(base_url, jwt_headers):
    """GET /api/v1/files/../../etc/passwd → 400/403/404"""
    resp = requests.get(
        f"{base_url}/api/v1/files/../../etc/passwd",
        headers=jwt_headers
    )
    assert resp.status_code in (400, 403, 404)


###############################################################################
###############################################################################


###############################################################################
# App-Token UUID-Validierung
# @pytest.mark.security: Diese Tests senden ungültige POST-Requests gegen Auth-
# Endpunkte. Sie schreiben keine Nutzdaten, können aber Logs/Rate-Limit-Zähler
# beeinflussen. Bewusst im Safe-Smoke-Lauf belassen — dokumentierter Trade-off.
###############################################################################

@pytest.mark.security
def test_app_register_invalid_device_id(base_url):
    """POST /api/v1/auth/app_register mit nicht-UUID device_id → 400"""
    resp = requests.post(
        f"{base_url}/api/v1/auth/app_register",
        json={"device_id": "kein-uuid"}
    )
    assert resp.status_code == 400


@pytest.mark.security
def test_app_register_empty_device_id(base_url):
    """POST /api/v1/auth/app_register ohne device_id → 400"""
    resp = requests.post(f"{base_url}/api/v1/auth/app_register", json={})
    assert resp.status_code == 400


@pytest.mark.write
def test_app_register_valid_uuid(base_url, test_device_id):
    """POST /api/v1/auth/app_register mit gültiger UUID → 201"""
    resp = requests.post(
        f"{base_url}/api/v1/auth/app_register",
        json={"device_id": test_device_id}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "app_token"  in body
    assert "expires_at" in body


@pytest.mark.security
def test_app_refresh_invalid_device_id(base_url):
    """POST /api/v1/auth/app_refresh mit nicht-UUID device_id → 400"""
    resp = requests.post(
        f"{base_url}/api/v1/auth/app_refresh",
        json={"app_token": "irgendeintoken", "device_id": "kein-uuid"}
    )
    assert resp.status_code == 400


###############################################################################
# Security Headers
###############################################################################

def test_security_headers_present(base_url):
    """Responses enthalten X-Content-Type-Options, X-Frame-Options, Referrer-Policy"""
    resp = requests.get(f"{base_url}/status")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options")        == "DENY"
    assert resp.headers.get("Referrer-Policy")        == "no-referrer"


def test_no_server_header_leak(base_url):
    """Server-Header verrät kein Framework"""
    resp   = requests.get(f"{base_url}/status")
    server = resp.headers.get("Server", "")
    assert "Werkzeug" not in server, f"Server-Header verrät Framework: {server}"


def test_error_no_stacktrace(base_url):
    """404-Response enthält keinen Python-Stacktrace"""
    resp = requests.get(f"{base_url}/api/v1/nonexistent_endpoint_pytest")
    assert "Traceback" not in resp.text
    assert "File "     not in resp.text
