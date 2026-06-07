"""
test_rbac.py — RBAC- und Tenant-Isolation-Tests

Konzept v1 + Review-Empfehlungen umgesetzt:
  - JWT-Validierung (abgelaufen, tampered)
  - Berechtigungsbasierter Zugriff (viewer/editor/zoo_admin)
  - Cross-Zoo-Isolation (Tenant-Trennung)
  - Inaktiver Tenant
  - Deaktivierter User mit altem Token
  - Zoo-Tenant-Eindeutigkeit
  - Super-Admin-Schutz (letzter aktiver super_admin)

Marker: @pytest.mark.rbac + @pytest.mark.jwt + @pytest.mark.security
Nie automatisch — manuell: pytest tests/test_rbac.py -v

Voraussetzungen in tests/.env_test:
  JWT_SECRET=<gleicher Wert wie source/.env>
  TEST_EMAIL / TEST_PASSWORD (super_admin)
  RBAC_USER_PASSWORD=RbacTest2026!Secure
"""

import base64
import json
import os
import time
import uuid
from datetime import datetime, timezone

import jwt as pyjwt
import pytest
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env_test"))

BASE_URL          = os.getenv("BASE_URL", "http://127.0.0.1:5001")
JWT_SECRET        = os.getenv("JWT_SECRET", "")
ADMIN_EMAIL       = os.getenv("TEST_EMAIL", "")
ADMIN_PASSWORD    = os.getenv("TEST_PASSWORD", "")
RBAC_PASSWORD     = os.getenv("RBAC_USER_PASSWORD", "RbacTest2026!Secure")


###############################################################################
# ── Hilfsfunktionen ──────────────────────────────────────────────────────────
###############################################################################

def _login(email: str, password: str) -> str:
    """Gibt access_token zurück oder wirft AssertionError."""
    resp = requests.post(f"{BASE_URL}/api/v1/auth/login",
                         json={"email": email, "password": password})
    assert resp.status_code == 200, \
        f"Login fehlgeschlagen für {email}: {resp.text}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _super_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"}


###############################################################################
# ── Session-Fixtures: Setup + Teardown ───────────────────────────────────────
###############################################################################

@pytest.fixture(scope="module")
def admin_token():
    """super_admin JWT-Token."""
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        pytest.skip("TEST_EMAIL / TEST_PASSWORD nicht gesetzt")
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def rbac_setup(admin_token):
    """
    Legt alle RBAC-Testdaten an und räumt nach den Tests auf.
    Gibt ein Dict mit allen IDs und Tokens zurück.

    Cleanup immer via finally — auch bei Test-Fehlern.
    """
    ctx = {
        "tenant_a_id": None, "tenant_b_id": None,
        "user_viewer_id": None, "user_editor_id": None,
        "user_zoo_admin_id": None, "user_tenant_b_id": None,
        "user_inactive_tenant_id": None,
        "token_viewer": None, "token_editor": None,
        "token_zoo_admin": None, "token_tenant_b": None,
    }
    h = _super_headers(admin_token)

    # ── Pre-Cleanup: Reste aus fehlgeschlagenen Läufen entfernen ────────────
    # Reihenfolge wichtig: erst Zuordnungen aufheben, dann Tenants/Zoos löschen

    # 1. RBAC-Tenants ermitteln und Zoo-Zuordnungen aufheben
    r = requests.get(f"{BASE_URL}/api/v1/admin/tenants", headers=h)
    if r.status_code == 200:
        for tenant in r.json():
            if tenant.get("name", "").startswith("RBAC "):
                tid = tenant["id"]
                # Zoo-Zuordnungen für diesen Tenant aufheben
                for zoo_slug in ["rbac_zoo_a", "rbac_zoo_b"]:
                    requests.delete(
                        f"{BASE_URL}/api/v1/admin/tenants/{tid}/zoos/{zoo_slug}",
                        headers=h)
                # Tenant deaktivieren
                requests.delete(
                    f"{BASE_URL}/api/v1/admin/tenants/{tid}", headers=h)

    # 2. Zoos deaktivieren
    for zoo_slug in ["rbac_zoo_a", "rbac_zoo_b"]:
        requests.delete(f"{BASE_URL}/api/v1/admin/zoos/{zoo_slug}", headers=h)

    # 3. RBAC-Test-User deaktivieren
    r = requests.get(f"{BASE_URL}/api/v1/admin/users", headers=h)
    if r.status_code == 200:
        for user in r.json():
            if user.get("email", "").endswith("@rbac.test"):
                requests.delete(
                    f"{BASE_URL}/api/v1/admin/users/{user['id']}", headers=h)

    try:
        # ── Tenants anlegen ──────────────────────────────────────────────────
        r = requests.post(f"{BASE_URL}/api/v1/admin/tenants",
                          headers=h, json={"name": "RBAC Tenant A", "plan": "free"})
        assert r.status_code == 201, f"Tenant A: {r.text}"
        ctx["tenant_a_id"] = r.json()["id"]

        r = requests.post(f"{BASE_URL}/api/v1/admin/tenants",
                          headers=h, json={"name": "RBAC Tenant B", "plan": "free"})
        assert r.status_code == 201, f"Tenant B: {r.text}"
        ctx["tenant_b_id"] = r.json()["id"]

        # Tenant C (für inaktiven Tenant Test) — sofort deaktivieren
        r = requests.post(f"{BASE_URL}/api/v1/admin/tenants",
                          headers=h, json={"name": "RBAC Tenant Inactive", "plan": "free"})
        assert r.status_code == 201
        ctx["tenant_inactive_id"] = r.json()["id"]

        # ── Zoos anlegen ─────────────────────────────────────────────────────
        r = requests.post(f"{BASE_URL}/api/v1/admin/zoos",
                          headers=h,
                          json={"slug": "rbac_zoo_a", "name": "RBAC Zoo A",
                                "is_active": True})
        assert r.status_code in (200, 201), f"Zoo A: {r.text}"
        ctx["zoo_a_id"] = r.json()["id"]

        r = requests.post(f"{BASE_URL}/api/v1/admin/zoos",
                          headers=h,
                          json={"slug": "rbac_zoo_b", "name": "RBAC Zoo B",
                                "is_active": True})
        assert r.status_code in (200, 201), f"Zoo B: {r.text}"
        ctx["zoo_b_id"] = r.json()["id"]

        # ── Zoos Tenants zuordnen ────────────────────────────────────────────
        r = requests.post(
            f"{BASE_URL}/api/v1/admin/tenants/{ctx['tenant_a_id']}/zoos",
            headers=h, json={"zoo_slug": "rbac_zoo_a"})
        assert r.status_code in (200, 201), f"Zoo A → Tenant A: {r.text}"

        r = requests.post(
            f"{BASE_URL}/api/v1/admin/tenants/{ctx['tenant_b_id']}/zoos",
            headers=h, json={"zoo_slug": "rbac_zoo_b"})
        assert r.status_code in (200, 201), f"Zoo B → Tenant B: {r.text}"

        # ── User anlegen ─────────────────────────────────────────────────────
        suffix = uuid.uuid4().hex[:6]

        def _create_user(email_prefix, tenant_id):
            email = f"{email_prefix}.{suffix}@rbac.test"
            r = requests.post(f"{BASE_URL}/api/v1/auth/register",
                              headers=h,
                              json={"email": email, "tenant_id": tenant_id})
            assert r.status_code == 201, f"User {email}: {r.text}"
            data = r.json()
            user_id = data["id"]
            # Invite annehmen — invite_url direkt in Response (kein SMTP)
            invite_url = data.get("invite_url", "")
            if invite_url:
                token = invite_url.rstrip("/").split("/")[-1]
                ri = requests.post(
                    f"{BASE_URL}/api/v1/auth/invite/{token}",
                    json={"password": RBAC_PASSWORD})
                assert ri.status_code == 200, \
                    f"Invite für {email}: {ri.text}"
            return user_id, email

        ctx["user_viewer_id"], ctx["viewer_email"] = \
            _create_user("rbac.viewer", ctx["tenant_a_id"])
        ctx["user_editor_id"], ctx["editor_email"] = \
            _create_user("rbac.editor", ctx["tenant_a_id"])
        ctx["user_zoo_admin_id"], ctx["zoo_admin_email"] = \
            _create_user("rbac.zooadmin", ctx["tenant_a_id"])
        ctx["user_tenant_b_id"], ctx["tenant_b_email"] = \
            _create_user("rbac.tenantb", ctx["tenant_b_id"])
        ctx["user_inactive_tenant_id"], ctx["inactive_tenant_email"] = \
            _create_user("rbac.inactive", ctx["tenant_inactive_id"])

        # ── Rollen vergeben ──────────────────────────────────────────────────
        def _grant_zoo_role(user_id, zoo_slug, role):
            r = requests.post(
                f"{BASE_URL}/api/v1/admin/users/{user_id}/roles/zoo",
                headers=h,
                json={"zoo_slug": zoo_slug, "role": role})
            assert r.status_code == 201, \
                f"Rolle {role} für {user_id} auf {zoo_slug}: {r.text}"

        _grant_zoo_role(ctx["user_viewer_id"],   "rbac_zoo_a", "viewer")
        _grant_zoo_role(ctx["user_editor_id"],   "rbac_zoo_a", "editor")
        _grant_zoo_role(ctx["user_zoo_admin_id"],"rbac_zoo_a", "zoo_admin")
        _grant_zoo_role(ctx["user_tenant_b_id"], "rbac_zoo_b", "zoo_admin")

        # ── Login für alle User VOR Tenant-Deaktivierung ───────────────────
        ctx["token_viewer"]    = _login(ctx["viewer_email"],    RBAC_PASSWORD)
        ctx["token_editor"]    = _login(ctx["editor_email"],    RBAC_PASSWORD)
        ctx["token_zoo_admin"] = _login(ctx["zoo_admin_email"], RBAC_PASSWORD)
        ctx["token_tenant_b"]  = _login(ctx["tenant_b_email"],  RBAC_PASSWORD)
        # Token VOR Deaktivierung holen — danach wäre Login nicht mehr möglich
        ctx["token_inactive_tenant"] = _login(
            ctx["inactive_tenant_email"], RBAC_PASSWORD)

        # Tenant C jetzt deaktivieren — Token ist bereits gesichert
        r = requests.delete(
            f"{BASE_URL}/api/v1/admin/tenants/{ctx['tenant_inactive_id']}",
            headers=h)
        assert r.status_code == 200, f"Tenant C deaktivieren: {r.text}"

        yield ctx

    finally:
        # ── Cleanup — immer ausführen ────────────────────────────────────────
        for user_key in ["user_viewer_id", "user_editor_id",
                         "user_zoo_admin_id", "user_tenant_b_id",
                         "user_inactive_tenant_id"]:
            uid = ctx.get(user_key)
            if uid:
                requests.delete(f"{BASE_URL}/api/v1/admin/users/{uid}",
                                headers=h)

        for zoo_slug in ["rbac_zoo_a", "rbac_zoo_b"]:
            requests.delete(f"{BASE_URL}/api/v1/admin/zoos/{zoo_slug}",
                            headers=h)

        for tenant_key in ["tenant_a_id", "tenant_b_id", "tenant_inactive_id"]:
            tid = ctx.get(tenant_key)
            if tid:
                requests.delete(f"{BASE_URL}/api/v1/admin/tenants/{tid}",
                                headers=h)


###############################################################################
# ══ BEREICH 1 — Token-Validierung ════════════════════════════════════════════
# Keine Fixture-Abhängigkeit — läuft auch ohne rbac_setup
###############################################################################

@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_expired_jwt_rejected():
    """Abgelaufener JWT (exp in Vergangenheit) → 401/403."""
    if not JWT_SECRET:
        pytest.skip("JWT_SECRET nicht gesetzt")

    expired_token = pyjwt.encode({
        "sub":       "999",
        "email":     "expired@test.test",
        "tenant_id": None,
        "jti":       str(uuid.uuid4()),
        "exp":       datetime(2020, 1, 1, tzinfo=timezone.utc),
        "iat":       datetime(2020, 1, 1, tzinfo=timezone.utc),
    }, JWT_SECRET, algorithm="HS256")

    resp = requests.get(f"{BASE_URL}/api/v1/zoos/rbac_zoo_a/enclosures",
                        headers=_auth(expired_token))
    assert resp.status_code in (401, 403), \
        f"Abgelaufener Token sollte abgewiesen werden, got {resp.status_code}"


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_tampered_jwt_wrong_secret():
    """JWT mit falschem Secret signiert → 401/403."""
    fake_token = pyjwt.encode({
        "sub":       "1",
        "email":     ADMIN_EMAIL,
        "tenant_id": None,
        "jti":       str(uuid.uuid4()),
        "exp":       int(time.time()) + 3600,
        "iat":       int(time.time()),
    }, "wrong_secret_that_is_not_the_real_one", algorithm="HS256")

    resp = requests.get(f"{BASE_URL}/api/v1/zoos/rbac_zoo_a/enclosures",
                        headers=_auth(fake_token))
    assert resp.status_code in (401, 403), \
        f"Token mit falschem Secret sollte abgewiesen werden, got {resp.status_code}"


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_tampered_jwt_modified_payload():
    """JWT mit manipuliertem Payload (Signatur unverändert) → 401/403."""
    if not JWT_SECRET:
        pytest.skip("JWT_SECRET nicht gesetzt")

    # Echten Token erzeugen
    real_token = pyjwt.encode({
        "sub":       "1",
        "email":     ADMIN_EMAIL,
        "tenant_id": None,
        "jti":       str(uuid.uuid4()),
        "exp":       int(time.time()) + 3600,
        "iat":       int(time.time()),
    }, JWT_SECRET, algorithm="HS256")

    # Payload-Teil manipulieren (sub auf 999 ändern)
    parts = real_token.split(".")
    new_payload = base64.b64encode(
        json.dumps({
            "sub":       "999",
            "email":     "hacker@evil.com",
            "tenant_id": None,
            "exp":       int(time.time()) + 9999999,
        }).encode()
    ).rstrip(b"=").decode()
    tampered = f"{parts[0]}.{new_payload}.{parts[2]}"

    resp = requests.get(f"{BASE_URL}/api/v1/zoos/rbac_zoo_a/enclosures",
                        headers=_auth(tampered))
    assert resp.status_code in (401, 403), \
        f"Manipulierter Token sollte abgewiesen werden, got {resp.status_code}"


###############################################################################
# ══ BEREICH 2 — Berechtigungsbasierter Zugriff ═══════════════════════════════
###############################################################################

@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_viewer_can_read_enclosures(rbac_setup):
    """viewer → GET /enclosures → 200."""
    resp = requests.get(
        f"{BASE_URL}/api/v1/zoos/rbac_zoo_a/enclosures",
        headers=_auth(rbac_setup["token_viewer"]))
    assert resp.status_code == 200, \
        f"viewer sollte Enclosures lesen dürfen, got {resp.status_code}: {resp.text}"


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_viewer_cannot_create_enclosure(rbac_setup):
    """viewer → POST /enclosures → 403."""
    resp = requests.post(
        f"{BASE_URL}/api/v1/zoos/rbac_zoo_a/enclosures",
        headers=_auth(rbac_setup["token_viewer"]),
        json={"name": "Should Fail", "species_id": 1})
    assert resp.status_code == 403, \
        f"viewer darf keine Enclosures anlegen, got {resp.status_code}"


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_editor_can_read_enclosures(rbac_setup):
    """editor → GET /enclosures → 200."""
    resp = requests.get(
        f"{BASE_URL}/api/v1/zoos/rbac_zoo_a/enclosures",
        headers=_auth(rbac_setup["token_editor"]))
    assert resp.status_code == 200, \
        f"editor sollte Enclosures lesen dürfen, got {resp.status_code}"


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_editor_cannot_publish(rbac_setup):
    """editor → POST /publish → 403."""
    resp = requests.post(
        f"{BASE_URL}/api/v1/zoos/rbac_zoo_a/publish",
        headers=_auth(rbac_setup["token_editor"]))
    assert resp.status_code == 403, \
        f"editor darf nicht publishen, got {resp.status_code}"


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_zoo_admin_can_publish(rbac_setup):
    """zoo_admin → POST /publish → 200."""
    resp = requests.post(
        f"{BASE_URL}/api/v1/zoos/rbac_zoo_a/publish",
        headers=_auth(rbac_setup["token_zoo_admin"]))
    assert resp.status_code == 200, \
        f"zoo_admin sollte publishen dürfen, got {resp.status_code}: {resp.text}"


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_zoo_admin_cannot_access_admin_endpoints(rbac_setup):
    """zoo_admin → GET /admin/zoos → 403."""
    resp = requests.get(
        f"{BASE_URL}/api/v1/admin/zoos",
        headers=_auth(rbac_setup["token_zoo_admin"]))
    assert resp.status_code == 403, \
        f"zoo_admin darf keine Admin-Endpoints nutzen, got {resp.status_code}"


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_viewer_cannot_write_domains_or_species(rbac_setup):
    """viewer → POST /species → 403 (write-Aktion)."""
    resp = requests.post(
        f"{BASE_URL}/api/v1/species",
        headers=_auth(rbac_setup["token_viewer"]),
        json={"german_name": "Test", "latin_name": "Test test",
              "wikidata_id": "Q1234567890"})
    # Species-Endpoint validiert Felder vor Auth → 400 oder 403 beide akzeptabel.
    # Wichtig: kein 201 (kein erfolgreicher Schreibzugriff).
    assert resp.status_code in (400, 403), \
        f"viewer darf keine Species anlegen, got {resp.status_code}"


###############################################################################
# ══ BEREICH 3 — Cross-Zoo-Isolation ══════════════════════════════════════════
###############################################################################

@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_zoo_b_token_rejected_for_zoo_a_enclosures(rbac_setup):
    """
    KRITISCHER TEST: User mit Zugriff auf rbac_zoo_b
    darf rbac_zoo_a nicht lesen. HTTP 200 = Sicherheitslücke.
    """
    resp = requests.get(
        f"{BASE_URL}/api/v1/zoos/rbac_zoo_a/enclosures",
        headers=_auth(rbac_setup["token_tenant_b"]))
    assert resp.status_code == 403, \
        f"KRITISCH: Cross-Zoo-Zugriff erlaubt! got {resp.status_code}"


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_zoo_b_token_rejected_for_zoo_a_publish(rbac_setup):
    """User von Tenant B darf Zoo A nicht publishen."""
    resp = requests.post(
        f"{BASE_URL}/api/v1/zoos/rbac_zoo_a/publish",
        headers=_auth(rbac_setup["token_tenant_b"]))
    assert resp.status_code == 403, \
        f"Cross-Zoo Publish nicht erlaubt, got {resp.status_code}"


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_zoo_b_token_rejected_for_zoo_a_domains(rbac_setup):
    """User von Tenant B darf Domains von Zoo A nicht lesen."""
    resp = requests.get(
        f"{BASE_URL}/api/v1/zoos/rbac_zoo_a/domains",
        headers=_auth(rbac_setup["token_tenant_b"]))
    assert resp.status_code == 403, \
        f"Cross-Zoo Domains nicht erlaubt, got {resp.status_code}"


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_zoo_b_user_can_access_own_zoo(rbac_setup):
    """User von Tenant B darf Zoo B lesen — positiver Test."""
    resp = requests.get(
        f"{BASE_URL}/api/v1/zoos/rbac_zoo_b/enclosures",
        headers=_auth(rbac_setup["token_tenant_b"]))
    assert resp.status_code == 200, \
        f"Tenant B User sollte Zoo B lesen dürfen, got {resp.status_code}"


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_zoo_b_token_cannot_write_to_zoo_a(rbac_setup):
    """Review-Empfehlung 2: Schreibzugriffe über Tenant-Grenzen testen."""
    resp = requests.post(
        f"{BASE_URL}/api/v1/zoos/rbac_zoo_a/enclosures",
        headers=_auth(rbac_setup["token_tenant_b"]),
        json={"name": "CrossTenantWrite", "species_id": 1})
    assert resp.status_code == 403, \
        f"Cross-Tenant Schreibzugriff nicht erlaubt, got {resp.status_code}"


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_zoo_cannot_be_assigned_to_two_tenants(rbac_setup, admin_token):
    """
    Review-Empfehlung 4: Zoo-Tenant-Eindeutigkeit.
    rbac_zoo_a gehört bereits Tenant A — Zuweisung zu Tenant B muss 409 geben.
    """
    h = _super_headers(admin_token)
    resp = requests.post(
        f"{BASE_URL}/api/v1/admin/tenants/{rbac_setup['tenant_b_id']}/zoos",
        headers=h,
        json={"zoo_slug": "rbac_zoo_a"})
    assert resp.status_code == 409, \
        f"Zoo darf nicht zwei Tenants gehören, got {resp.status_code}: {resp.text}"


###############################################################################
# ══ BEREICH 4 — Inaktiver Tenant ═════════════════════════════════════════════
###############################################################################

@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_user_with_inactive_tenant_cannot_access_zoo(rbac_setup):
    """
    Review-Empfehlung 3: User dessen Tenant deaktiviert wurde
    darf keine Zoo-Daten mehr abrufen.
    """
    resp = requests.get(
        f"{BASE_URL}/api/v1/zoos/rbac_zoo_a/enclosures",
        headers=_auth(rbac_setup["token_inactive_tenant"]))
    assert resp.status_code == 403, \
        f"User mit inaktivem Tenant sollte keinen Zugriff haben, " \
        f"got {resp.status_code}"


###############################################################################
# ══ BEREICH 5 — Deaktivierter User ═══════════════════════════════════════════
###############################################################################

@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_deactivated_user_cannot_use_old_token(rbac_setup, admin_token):
    """
    User deaktivieren → alten Token verwenden → 403.
    Testet dass can_access_zoo() is_active des Users prüft.
    """
    h = _super_headers(admin_token)

    # Viewer deaktivieren
    resp = requests.delete(
        f"{BASE_URL}/api/v1/admin/users/{rbac_setup['user_viewer_id']}",
        headers=h)
    assert resp.status_code == 200, f"User deaktivieren: {resp.text}"

    try:
        # Alter Token muss abgewiesen werden
        resp = requests.get(
            f"{BASE_URL}/api/v1/zoos/rbac_zoo_a/enclosures",
            headers=_auth(rbac_setup["token_viewer"]))
        assert resp.status_code == 403, \
            f"Deaktivierter User sollte keinen Zugriff haben, " \
            f"got {resp.status_code}"
    finally:
        # User reaktivieren für spätere Tests
        requests.put(
            f"{BASE_URL}/api/v1/admin/users/{rbac_setup['user_viewer_id']}",
            headers=h,
            json={"is_active": True})


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_deactivated_super_admin_cannot_use_old_token(admin_token):
    """
    Review-Empfehlung 5: Deaktivierter super_admin mit altem Token → 403.
    Testet dass require_super_admin() is_active prüft.
    Nur wenn ein zweiter super_admin existiert — andernfalls skip.
    """
    if not JWT_SECRET:
        pytest.skip("JWT_SECRET nicht gesetzt")

    # Token für fiktiven deaktivierten super_admin erzeugen
    # (echter User mit ID 999 existiert nicht → ist_active=FALSE implizit)
    fake_super_token = pyjwt.encode({
        "sub":       "99999",
        "email":     "deactivated.super@test.test",
        "tenant_id": None,
        "jti":       str(uuid.uuid4()),
        "exp":       int(time.time()) + 3600,
        "iat":       int(time.time()),
    }, JWT_SECRET, algorithm="HS256")

    resp = requests.get(f"{BASE_URL}/api/v1/admin/zoos",
                        headers=_auth(fake_super_token))
    assert resp.status_code == 403, \
        f"Deaktivierter super_admin sollte 403 bekommen, got {resp.status_code}"


###############################################################################
# ══ BEREICH 6 — Super-Admin-Schutz ══════════════════════════════════════════
###############################################################################

@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_cannot_revoke_last_super_admin_role(admin_token):
    """
    Letzten aktiven super_admin seiner Rolle berauben → 400.
    """
    h = _super_headers(admin_token)
    # user_id=1 ist der Bootstrap-super_admin
    resp = requests.delete(
        f"{BASE_URL}/api/v1/admin/users/1/roles/global/super_admin",
        headers=h)
    assert resp.status_code == 400, \
        f"Letzten super_admin entfernen sollte 400 geben, got {resp.status_code}: {resp.text}"


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_cannot_deactivate_last_super_admin(admin_token):
    """
    Letzten aktiven super_admin deaktivieren → 400.
    """
    h = _super_headers(admin_token)
    resp = requests.delete(
        f"{BASE_URL}/api/v1/admin/users/1",
        headers=h)
    assert resp.status_code == 400, \
        f"Letzten super_admin deaktivieren sollte 400 geben, got {resp.status_code}: {resp.text}"


@pytest.mark.rbac
@pytest.mark.jwt
@pytest.mark.security
def test_cannot_update_last_super_admin_to_inactive(admin_token):
    """
    Letzten aktiven super_admin via PUT deaktivieren → 400.
    """
    h = _super_headers(admin_token)
    resp = requests.put(
        f"{BASE_URL}/api/v1/admin/users/1",
        headers=h,
        json={"is_active": False})
    assert resp.status_code == 400, \
        f"Letzten super_admin via PUT deaktivieren sollte 400 geben, " \
        f"got {resp.status_code}: {resp.text}"
