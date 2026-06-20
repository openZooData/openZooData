"""
test_enclosure_species.py — Tests für feeding_times & births innerhalb von
enclosure_species

Endpoints:
  GET    /api/v1/zoos/<zoo>/enclosure_species
  POST   /api/v1/zoos/<zoo>/enclosure_species
  PUT    /api/v1/zoos/<zoo>/enclosure_species/<id>
  DELETE /api/v1/zoos/<zoo>/enclosure_species/<id>

Fokus dieser Datei: feeding_times und births werden ausschließlich über
enclosure_species angesprochen (kein eigener Endpoint). Der Client schickt
für births NIE enclosure_species_id/species_id/zoo_id mit — die kommen aus
dem Parent-Kontext (POST: frisch erzeugte es_id; PUT: es_id aus der URL).

Es gibt absichtlich kein GET .../enclosure_species/<id> — daher holt sich
_find_es() den Eintrag über die Liste.

Rate-Limit-Hinweise:
  - GET: 60/min — kein Problem
  - POST/PUT: 30/min — sleep(1) zwischen schreibenden Operationen
  - DELETE: 10/min — sleep(7) vor jedem Delete-Call (mehrere Tests in dieser
    Datei räumen über DELETE auf; bei sleep(1) wird das 10/min-Limit über den
    ganzen Testlauf hinweg gerissen)
"""

import time
import uuid
import pytest
import requests


###############################################################################
# ── Helper ────────────────────────────────────────────────────────────────────
###############################################################################

def _find_es(base_url, jwt_headers, test_zoo, es_id):
    """Holt eine enclosure_species über die Liste (kein Detail-GET vorhanden)."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
                        headers=jwt_headers)
    assert resp.status_code == 200, f"Liste laden fehlgeschlagen: {resp.text}"
    matches = [e for e in resp.json() if e["id"] == es_id]
    assert matches, f"enclosure_species {es_id} nicht in Liste gefunden"
    return matches[0]


###############################################################################
# ── Fixtures ─────────────────────────────────────────────────────────────────
###############################################################################

@pytest.fixture(scope="module")
def birth_test_species_id(base_url, test_zoo, jwt_headers):
    """
    Eigene, von created_species_id getrennte Species — ausschließlich für
    Tests, die births erzeugen.

    births bleiben absichtlich als historisches Faktum bestehen (DELETE
    einer enclosure_species setzt nur enclosure_species_id auf NULL,
    births_species_id_fkey hat kein ON DELETE). Eine Species, an der
    births hängen, ist über die API also nie wieder löschbar. Würden wir
    dafür die geteilte created_species_id-Fixture nutzen, könnte
    test_z_cleanup.py::test_species_delete sie am Ende nie mehr aufräumen.
    Diese Species bleibt deshalb bewusst als Test-Datenmüll im Test-Zoo
    zurück — es wird kein Löschversuch unternommen.
    """
    wikidata_id = f"Q{800_000_000 + (uuid.uuid4().int % 99_000_000)}"
    resp = requests.post(
        f"{base_url}/api/v1/species",
        headers=jwt_headers,
        json={
            "german_name": "Pytest-Geburtstier",
            "latin_name":  "Natus pytestus",
            "wikidata_id": wikidata_id,
            "zoo_slug":    test_zoo,
        }
    )
    assert resp.status_code == 201, f"Birth-Test-Species anlegen fehlgeschlagen: {resp.text}"
    return resp.json()["id"]


@pytest.fixture(scope="module")
def created_enclosure_species_id(base_url, test_zoo, jwt_headers, birth_test_species_id):
    """
    Legt eine Test-enclosure_species mit feeding_times UND births gleichzeitig an
    (deckt das Cartesian-Product-Risiko aus der GET-Query ab) und löscht sie
    nach den Tests wieder.
    """
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
        headers=jwt_headers,
        json={
            "species_id": birth_test_species_id,
            "note": "Pytest enclosure_species",
            "feeding_times": ["09:00", "13:00", "17:30"],
            "births": [
                {"birth_date": "2026-02-01", "count": 2, "note": "Zwillinge", "is_public": True},
                {"birth_date": "2026-04-15", "count": 1, "note": None, "is_public": False},
            ],
        }
    )
    assert resp.status_code == 201, \
        f"enclosure_species mit feeding_times/births anlegen fehlgeschlagen: {resp.text}"
    es_id = resp.json()["id"]

    yield es_id

    time.sleep(7)
    requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers
    )


###############################################################################
# ── GET /api/v1/zoos/<zoo>/enclosure_species — Basics ───────────────────────
###############################################################################

def test_enclosure_species_list_requires_auth(base_url, test_zoo):
    """GET ohne Auth → 401/403."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species")
    assert resp.status_code in (401, 403)


@pytest.mark.jwt
def test_enclosure_species_list_returns_array(base_url, jwt_headers, test_zoo):
    """GET → 200 + Array."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
                        headers=jwt_headers)
    assert resp.status_code == 200, f"enclosure_species Liste: {resp.text}"
    assert isinstance(resp.json(), list)


@pytest.mark.jwt
def test_enclosure_species_entries_have_feeding_times_and_births_keys(
        base_url, jwt_headers, test_zoo):
    """Jeder Eintrag hat die Felder feeding_times und births (auch wenn leer/null)."""
    resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
                        headers=jwt_headers)
    assert resp.status_code == 200
    entries = resp.json()
    if len(entries) == 0:
        pytest.skip("Keine enclosure_species im Test-Zoo vorhanden")
    entry = entries[0]
    assert "feeding_times" in entry
    assert "births" in entry


###############################################################################
# ── POST: feeding_times + births gemeinsam anlegen ──────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_create_with_feeding_and_births(
        created_enclosure_species_id):
    """POST mit feeding_times + births → 201 + gültige id."""
    assert isinstance(created_enclosure_species_id, int)
    assert created_enclosure_species_id > 0


@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_get_includes_feeding_times(
        base_url, jwt_headers, test_zoo, created_enclosure_species_id):
    """
    GET zeigt die angelegten feeding_times korrekt — und nicht mehr/weniger
    als 3 (Regressionsschutz gegen das Cartesian-Product mit births).
    """
    es = _find_es(base_url, jwt_headers, test_zoo, created_enclosure_species_id)
    feeding_times = es["feeding_times"]
    assert feeding_times is not None
    assert len(feeding_times) == 3, \
        f"Erwarte genau 3 Fütterungszeiten, bekam {feeding_times}"
    # Postgres castet TIME::TEXT als HH:MM:SS
    assert sorted(feeding_times) == ["09:00:00", "13:00:00", "17:30:00"]


@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_get_includes_births(
        base_url, jwt_headers, test_zoo, created_enclosure_species_id):
    """
    GET zeigt die angelegten births korrekt — und nicht mehr/weniger als 2
    (Regressionsschutz gegen das Cartesian-Product mit feeding_times).
    """
    es = _find_es(base_url, jwt_headers, test_zoo, created_enclosure_species_id)
    births = es["births"]
    assert births is not None
    assert len(births) == 2, f"Erwarte genau 2 Geburten, bekam {births}"

    by_date = {b["birth_date"]: b for b in births}
    assert "2026-02-01" in by_date
    assert by_date["2026-02-01"]["count"] == 2
    assert by_date["2026-02-01"]["note"] == "Zwillinge"
    assert by_date["2026-02-01"]["is_public"] is True

    assert "2026-04-15" in by_date
    assert by_date["2026-04-15"]["count"] == 1
    assert by_date["2026-04-15"]["is_public"] is False


@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_births_response_excludes_internal_fields(
        base_url, jwt_headers, test_zoo, created_enclosure_species_id):
    """
    births-Einträge in der Response enthalten kein enclosure_species_id/
    species_id/zoo_id — diese Felder sind reine Server-interne Zuordnung.
    """
    es = _find_es(base_url, jwt_headers, test_zoo, created_enclosure_species_id)
    for b in es["births"]:
        assert set(b.keys()) == {"id", "birth_date", "count", "note", "is_public"}


###############################################################################
# ── POST: Validierung ───────────────────────────────────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_create_births_missing_birth_date(
        base_url, jwt_headers, test_zoo, created_species_id):
    """POST mit births-Eintrag ohne birth_date → 400."""
    time.sleep(1)
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
        headers=jwt_headers,
        json={
            "species_id": created_species_id,
            "births": [{"count": 1}],
        }
    )
    assert resp.status_code == 400, \
        f"births ohne birth_date sollte 400 geben, got {resp.status_code}: {resp.text}"


@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_create_births_applies_defaults(
        base_url, jwt_headers, test_zoo, birth_test_species_id):
    """
    births-Eintrag mit nur birth_date → count default 1, is_public default True.
    Erfolgreiches 201 beweist gleichzeitig, dass species_id/zoo_id serverseitig
    korrekt aus dem Parent-Kontext befüllt wurden (births.species_id ist NOT NULL).
    """
    time.sleep(1)
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
        headers=jwt_headers,
        json={
            "species_id": birth_test_species_id,
            "births": [{"birth_date": "2026-05-01"}],
        }
    )
    assert resp.status_code == 201, f"enclosure_species anlegen fehlgeschlagen: {resp.text}"
    es_id = resp.json()["id"]

    es = _find_es(base_url, jwt_headers, test_zoo, es_id)
    assert len(es["births"]) == 1
    birth = es["births"][0]
    assert birth["birth_date"] == "2026-05-01"
    assert birth["count"] == 1
    assert birth["is_public"] is True

    # Cleanup
    time.sleep(7)
    requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers
    )


@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_create_without_feeding_or_births(
        base_url, jwt_headers, test_zoo, created_species_id):
    """POST ganz ohne feeding_times/births → 201, beide Felder sind leer/null."""
    time.sleep(1)
    resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
        headers=jwt_headers,
        json={"species_id": created_species_id}
    )
    assert resp.status_code == 201, f"enclosure_species anlegen fehlgeschlagen: {resp.text}"
    es_id = resp.json()["id"]

    es = _find_es(base_url, jwt_headers, test_zoo, es_id)
    assert not es["feeding_times"]
    assert not es["births"]

    time.sleep(7)
    requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers
    )


###############################################################################
# ── PUT: feeding_times ersetzen (delete-all-reinsert) ───────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_put_replaces_feeding_times(
        base_url, jwt_headers, test_zoo, created_species_id):
    """PUT mit neuer feeding_times-Liste → alte Zeiten verschwinden komplett."""
    time.sleep(1)
    create_resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
        headers=jwt_headers,
        json={"species_id": created_species_id, "feeding_times": ["08:00", "12:00"]}
    )
    assert create_resp.status_code == 201
    es_id = create_resp.json()["id"]

    time.sleep(1)
    put_resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers,
        json={"feeding_times": ["18:00"]}
    )
    assert put_resp.status_code == 200, f"Update fehlgeschlagen: {put_resp.text}"

    es = _find_es(base_url, jwt_headers, test_zoo, es_id)
    assert es["feeding_times"] == ["18:00:00"], \
        f"Alte Fütterungszeiten sollten ersetzt, nicht ergänzt sein: {es['feeding_times']}"

    time.sleep(7)
    requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers
    )


@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_put_clear_feeding_times(
        base_url, jwt_headers, test_zoo, created_species_id):
    """PUT mit feeding_times: [] → alle Fütterungszeiten gelöscht."""
    time.sleep(1)
    create_resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
        headers=jwt_headers,
        json={"species_id": created_species_id, "feeding_times": ["08:00"]}
    )
    assert create_resp.status_code == 201
    es_id = create_resp.json()["id"]

    time.sleep(1)
    put_resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers,
        json={"feeding_times": []}
    )
    assert put_resp.status_code == 200, f"Update fehlgeschlagen: {put_resp.text}"

    es = _find_es(base_url, jwt_headers, test_zoo, es_id)
    assert not es["feeding_times"]

    time.sleep(7)
    requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers
    )


###############################################################################
# ── PUT: births ersetzen (delete-all-reinsert) ──────────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_put_replaces_births(
        base_url, jwt_headers, test_zoo, birth_test_species_id):
    """PUT mit neuer births-Liste → alte Geburten verschwinden komplett."""
    time.sleep(1)
    create_resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
        headers=jwt_headers,
        json={
            "species_id": birth_test_species_id,
            "births": [{"birth_date": "2026-01-10", "count": 1}],
        }
    )
    assert create_resp.status_code == 201
    es_id = create_resp.json()["id"]

    time.sleep(1)
    put_resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers,
        json={"births": [{"birth_date": "2026-06-20", "count": 3, "note": "Wurf"}]}
    )
    assert put_resp.status_code == 200, f"Update fehlgeschlagen: {put_resp.text}"

    es = _find_es(base_url, jwt_headers, test_zoo, es_id)
    assert len(es["births"]) == 1, \
        f"Alte Geburt sollte ersetzt, nicht ergänzt sein: {es['births']}"
    assert es["births"][0]["birth_date"] == "2026-06-20"
    assert es["births"][0]["count"] == 3
    assert es["births"][0]["note"] == "Wurf"

    time.sleep(7)
    requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers
    )


@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_put_clear_births(
        base_url, jwt_headers, test_zoo, birth_test_species_id):
    """PUT mit births: [] → alle Geburten gelöscht."""
    time.sleep(1)
    create_resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
        headers=jwt_headers,
        json={
            "species_id": birth_test_species_id,
            "births": [{"birth_date": "2026-01-10"}],
        }
    )
    assert create_resp.status_code == 201
    es_id = create_resp.json()["id"]

    time.sleep(1)
    put_resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers,
        json={"births": []}
    )
    assert put_resp.status_code == 200, f"Update fehlgeschlagen: {put_resp.text}"

    es = _find_es(base_url, jwt_headers, test_zoo, es_id)
    assert not es["births"]

    time.sleep(7)
    requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers
    )


@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_put_births_missing_birth_date(
        base_url, jwt_headers, test_zoo, created_enclosure_species_id):
    """PUT mit births-Eintrag ohne birth_date → 400, bestehende Daten bleiben unberührt."""
    time.sleep(1)
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{created_enclosure_species_id}",
        headers=jwt_headers,
        json={"births": [{"count": 5}]}
    )
    assert resp.status_code == 400, \
        f"births ohne birth_date sollte 400 geben, got {resp.status_code}: {resp.text}"


@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_put_does_not_touch_births_when_omitted(
        base_url, jwt_headers, test_zoo, created_enclosure_species_id):
    """PUT ohne births-Feld lässt bestehende Geburten unverändert."""
    time.sleep(1)
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{created_enclosure_species_id}",
        headers=jwt_headers,
        json={"note": "Nur die Notiz ändert sich"}
    )
    assert resp.status_code == 200, f"Update fehlgeschlagen: {resp.text}"

    es = _find_es(base_url, jwt_headers, test_zoo, created_enclosure_species_id)
    assert len(es["births"]) == 2, "births sollten unverändert bleiben, wenn nicht im Body"
    assert len(es["feeding_times"]) == 3, "feeding_times sollten unverändert bleiben, wenn nicht im Body"


###############################################################################
# ── PUT: species_id bleibt unveränderlich ───────────────────────────────────
###############################################################################

@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_put_rejects_species_id(
        base_url, jwt_headers, test_zoo, created_enclosure_species_id):
    """
    species_id ist nicht in ALLOWED → PUT mit species_id → 400.
    Wichtig für births: stellt sicher, dass die Annahme 'species_id ändert
    sich nie über PUT' weiterhin gilt, auf der das Auto-Befüllen von
    births.species_id aufbaut.
    """
    time.sleep(1)
    resp = requests.put(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{created_enclosure_species_id}",
        headers=jwt_headers,
        json={"species_id": 999999}
    )
    assert resp.status_code == 400


###############################################################################
# ── DELETE /api/v1/zoos/<zoo>/enclosure_species/<id> ────────────────────────
###############################################################################

def test_enclosure_species_delete_requires_auth(base_url, test_zoo):
    """DELETE ohne Auth → 401/403."""
    time.sleep(1)
    resp = requests.delete(f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/1")
    assert resp.status_code in (401, 403)


@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_delete_nonexistent(base_url, jwt_headers, test_zoo):
    """DELETE einer nicht existierenden enclosure_species → 404."""
    time.sleep(7)
    resp = requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/999999",
        headers=jwt_headers
    )
    assert resp.status_code == 404


@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_delete_removes_from_list(
        base_url, jwt_headers, test_zoo, created_species_id):
    """DELETE entfernt die enclosure_species sichtbar aus der Liste."""
    time.sleep(1)
    create_resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
        headers=jwt_headers,
        json={"species_id": created_species_id}
    )
    assert create_resp.status_code == 201
    es_id = create_resp.json()["id"]

    time.sleep(7)
    delete_resp = requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers
    )
    assert delete_resp.status_code == 200, f"Delete fehlgeschlagen: {delete_resp.text}"

    list_resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
                              headers=jwt_headers)
    ids = [e["id"] for e in list_resp.json()]
    assert es_id not in ids


@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_delete_is_not_double_deletable(
        base_url, jwt_headers, test_zoo, created_species_id):
    """Zweites DELETE auf dieselbe (bereits gelöschte) ID → 404, kein Crash."""
    time.sleep(1)
    create_resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
        headers=jwt_headers,
        json={"species_id": created_species_id}
    )
    assert create_resp.status_code == 201
    es_id = create_resp.json()["id"]

    time.sleep(7)
    first = requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers
    )
    assert first.status_code == 200

    time.sleep(7)
    second = requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers
    )
    assert second.status_code == 404


@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_delete_with_geo_point_succeeds(
        base_url, jwt_headers, test_zoo, created_species_id):
    """
    DELETE einer enclosure_species mit gesetzter GPS-Position darf nicht
    fehlschlagen — Regressionsschutz für die neue geo_points-Aufräum-Query
    (entity_type/entity_id ist polymorph, keine FK zur Absicherung).
    """
    time.sleep(1)
    create_resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
        headers=jwt_headers,
        json={
            "species_id": created_species_id,
            "latitude": 52.5145,
            "longitude": 13.3501,
        }
    )
    assert create_resp.status_code == 201
    es_id = create_resp.json()["id"]

    time.sleep(7)
    delete_resp = requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers
    )
    assert delete_resp.status_code == 200, f"Delete fehlgeschlagen: {delete_resp.text}"

    list_resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
                              headers=jwt_headers)
    ids = [e["id"] for e in list_resp.json()]
    assert es_id not in ids


@pytest.mark.jwt
@pytest.mark.write
@pytest.mark.media
def test_enclosure_species_delete_removes_media(
        base_url, jwt_headers, test_zoo, created_species_id, test_image_bytes):
    """
    DELETE entfernt zugehörige media-Einträge (entity_type='enclosure_species')
    inkl. der physischen Datei — sonst blieben sie als Orphans zurück, weil
    media keine FK-Constraint auf enclosure_species hat (polymorph).
    """
    time.sleep(1)
    create_resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
        headers=jwt_headers,
        json={"species_id": created_species_id}
    )
    assert create_resp.status_code == 201
    es_id = create_resp.json()["id"]

    upload_resp = requests.post(
        f"{base_url}/api/v1/media/enclosure_species/{es_id}",
        headers=jwt_headers,
        data={"zoo": test_zoo},
        files={"file": ("pytest.jpg", test_image_bytes, "image/jpeg")}
    )
    assert upload_resp.status_code == 201, f"Media-Upload fehlgeschlagen: {upload_resp.text}"

    # Vor dem Löschen: media ist sichtbar
    list_before = requests.get(
        f"{base_url}/api/v1/media/enclosure_species/{es_id}",
        headers=jwt_headers,
        params={"zoo": test_zoo}
    )
    assert list_before.status_code == 200
    assert len(list_before.json()) == 1

    time.sleep(7)
    delete_resp = requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers
    )
    assert delete_resp.status_code == 200, f"Delete fehlgeschlagen: {delete_resp.text}"

    # Nach dem Löschen: media-Eintrag ist verschwunden, kein Orphan
    list_after = requests.get(
        f"{base_url}/api/v1/media/enclosure_species/{es_id}",
        headers=jwt_headers,
        params={"zoo": test_zoo}
    )
    assert list_after.status_code == 200
    assert list_after.json() == [], \
        "media-Eintrag sollte nach Löschen der enclosure_species verschwunden sein"


@pytest.mark.jwt
@pytest.mark.write
def test_enclosure_species_delete_wrong_zoo_is_rejected(
        base_url, jwt_headers, test_zoo, created_species_id):
    """
    DELETE über einen falschen Zoo-Slug → 403/404, enclosure_species bleibt
    erhalten. Regressionstest für die Tenant-Isolation-Lücke: der alte
    Fallback-Zweig (keine enclosure_id/house_id gesetzt) prüfte den Zoo gar
    nicht und hätte fremde enclosure_species löschen können.
    """
    time.sleep(1)
    create_resp = requests.post(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
        headers=jwt_headers,
        json={"species_id": created_species_id}
    )
    assert create_resp.status_code == 201
    es_id = create_resp.json()["id"]

    time.sleep(7)
    delete_resp = requests.delete(
        f"{base_url}/api/v1/zoos/zoo_does_not_exist/enclosure_species/{es_id}",
        headers=jwt_headers
    )
    assert delete_resp.status_code in (403, 404), \
        f"Delete über falschen Zoo sollte fehlschlagen, got {delete_resp.status_code}"

    # Eintrag muss noch existieren
    list_resp = requests.get(f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species",
                              headers=jwt_headers)
    ids = [e["id"] for e in list_resp.json()]
    assert es_id in ids, \
        "enclosure_species sollte nach fehlgeschlagenem Cross-Tenant-Delete noch existieren"

    # Cleanup
    time.sleep(7)
    requests.delete(
        f"{base_url}/api/v1/zoos/{test_zoo}/enclosure_species/{es_id}",
        headers=jwt_headers
    )
