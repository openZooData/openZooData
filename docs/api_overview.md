# openZooData — API Endpoints V2

Stand: Juni 2026 · Basis-URL: `https://api.openzoodata.org`  
Lokal: `http://localhost:5001`

**Auth-Schema:**

- `—` = kein Token nötig
- `App-Token` = iOS End-User App Token
- `JWT` = Bearer JWT (Zoo-Admin oder super_admin)
- `JWT read` = JWT mit read-Berechtigung auf diesen Zoo
- `JWT write` = JWT mit write-Berechtigung auf diesen Zoo
- `JWT write (global)` = JWT mit write-Berechtigung (zoo_admin/editor) auf irgendeinem Zoo, oder tenant_admin/super_admin — für Endpoints ohne Zoo-Kontext
- `JWT publish` = JWT mit publish-Berechtigung auf diesen Zoo
- `JWT super_admin` = JWT mit globaler super_admin-Rolle

-----

## System

|Method|Endpoint         |Auth          |Beschreibung                              |
|------|-----------------|--------------|------------------------------------------|
|GET   |`/`              |—             |Root                                      |
|GET   |`/status`        |—             |Health-Check                              |
|GET   |`/status/details`|`X-Health-Key`|Detaillierter Status (DBs, SQLite-Dateien)|

-----

## Auth

|Method|Endpoint                             |Auth           |Beschreibung                         |
|------|-------------------------------------|---------------|-------------------------------------|
|POST  |`/api/v1/auth/app_register`          |—              |App-Token registrieren (iOS End-User)|
|POST  |`/api/v1/auth/app_refresh`           |—              |App-Token erneuern                   |
|POST  |`/api/v1/auth/login`                 |—              |JWT Login (60/min)                   |
|POST  |`/api/v1/auth/refresh`               |—              |JWT erneuern                         |
|POST  |`/api/v1/auth/logout`                |JWT            |Logout                               |
|POST  |`/api/v1/auth/register`              |JWT super_admin|User einladen                        |
|POST  |`/api/v1/auth/invite/<token>`        |—              |Einladung annehmen + Passwort setzen |
|POST  |`/api/v1/auth/password-reset/request`|—              |Passwort-Reset anfordern             |
|POST  |`/api/v1/auth/password-reset/confirm`|—              |Passwort-Reset bestätigen            |

-----

## Zoos

|Method|Endpoint            |Auth    |Beschreibung                |
|------|--------------------|--------|----------------------------|
|GET   |`/api/v1/zoos`      |JWT     |Alle aktiven Zoos           |
|GET   |`/api/v1/zoos/<zoo>`|JWT read|Zoo-Details + Öffnungszeiten|

-----

## Enclosures (Tiergehege)

|Method|Endpoint                            |Auth     |Beschreibung             |
|------|------------------------------------|---------|-------------------------|
|GET   |`/api/v1/zoos/<zoo>/enclosures`     |JWT read |Alle Gehege inkl. Species|
|POST  |`/api/v1/zoos/<zoo>/enclosures`     |JWT write|Gehege anlegen           |
|PUT   |`/api/v1/zoos/<zoo>/enclosures/<id>`|JWT write|Gehege bearbeiten        |
|DELETE|`/api/v1/zoos/<zoo>/enclosures/<id>`|JWT write|Gehege löschen           |

-----

## Houses (Tierhäuser)

|Method|Endpoint                        |Auth     |Beschreibung                   |
|------|--------------------------------|---------|-------------------------------|
|GET   |`/api/v1/zoos/<zoo>/houses`     |JWT read |Alle Häuser inkl. Gehege-Anzahl|
|GET   |`/api/v1/zoos/<zoo>/houses/<id>`|JWT read |Haus-Details inkl. Gehege      |
|POST  |`/api/v1/zoos/<zoo>/houses`     |JWT write|Haus anlegen                   |
|PUT   |`/api/v1/zoos/<zoo>/houses/<id>`|JWT write|Haus bearbeiten                |
|DELETE|`/api/v1/zoos/<zoo>/houses/<id>`|JWT write|Haus löschen (CASCADE)         |

-----

## Enclosure Species (Tier-Zuordnungen) ✨ neu

Verknüpft eine Tierart (Species) mit einem Ort im Zoo — optional einem
Enclosure (Freigehege) und/oder einem House (Tierhaus). Zentraler
Knotenpunkt für Fütterungszeiten, Geburten, GPS-Position (`geo_points`) und
Foto (`media`).

|Method|Endpoint                                  |Auth     |Beschreibung                                      |
|------|-------------------------------------------|---------|---------------------------------------------------|
|GET   |`/api/v1/zoos/<zoo>/enclosure_species`     |JWT read |Alle Tier-Zuordnungen inkl. `feeding_times`, `births`|
|GET   |`/api/v1/zoos/<zoo>/enclosure_species/<id>`|JWT read |Einzelne Zuordnung (z.B. Refresh nach POST/PUT)   |
|POST  |`/api/v1/zoos/<zoo>/enclosure_species`     |JWT write|Zuordnung anlegen                                 |
|PUT   |`/api/v1/zoos/<zoo>/enclosure_species/<id>`|JWT write|Zuordnung bearbeiten                              |
|DELETE|`/api/v1/zoos/<zoo>/enclosure_species/<id>`|JWT write|Zuordnung löschen (inkl. `media`/`geo_points`)    |

**Query-Parameter für GET:**

- `?enclosure_id=<id>` — Filter nach Gehege
- `?house_id=<id>` — Filter nach Tierhaus
- `?domain_id=<id>` — Filter nach Domain (Enclosure, House oder enclosure_species selbst)

**Zwei Wege für `feeding_times`/`births`:** entweder verschachtelt über
`enclosure_species` (POST/PUT, delete-all-reinsert-Semantik, siehe unten),
oder über die eigenständigen Sub-Resource-Endpoints weiter unten — beide
Wege funktionieren parallel und schreiben in dieselben Tabellen.
`enclosure_species_id` (und bei `births` zusätzlich `species_id`/`zoo_id`)
kommen in beiden Fällen immer aus dem URL-/Parent-Kontext — der Client
schickt sie nie mit.

POST/PUT-Body (Auszug, verschachtelter Weg):

```json
{
  "species_id": 42,
  "enclosure_id": 7,
  "feeding_times": ["09:00", "15:30"],
  "births": [
    {"birth_date": "2026-03-01", "count": 2, "note": "Zwillinge", "is_public": true}
  ]
}
```

- `feeding_times`: Liste von Uhrzeiten (`"HH:MM"`)
- `births`: Liste von Objekten, `birth_date` Pflicht, `count` (Default `1`), `note`, `is_public` (Default `true`)
- PUT ersetzt eine mitgeschickte Liste komplett (delete-all-reinsert); `[]` löscht alle Einträge, ein fehlendes Feld lässt bestehende Einträge unverändert
- `species_id` ist über PUT nicht änderbar (400 bei Versuch)

**DELETE-Verhalten (beim Löschen der enclosure_species selbst):**

|Tabelle      |Verhalten                                              |
|-------------|--------------------------------------------------------|
|feeding_times|automatisch mitgelöscht (`ON DELETE CASCADE`)            |
|births       |bleibt erhalten, `enclosure_species_id` wird `NULL` (historisches Faktum)|
|geo_points   |wird explizit gelöscht (polymorph, keine FK möglich)     |
|media        |wird explizit gelöscht inkl. physischer Datei (polymorph, keine FK möglich)|

-----

### Feeding Times (eigenständige CRUD-Endpoints) ✨ neu

|Method|Endpoint                                                       |Auth     |Beschreibung   |
|------|----------------------------------------------------------------|---------|---------------|
|GET   |`/api/v1/zoos/<zoo>/feeding_times`                               |JWT read |Alle im Zoo, optional `?species_id=<id>`|
|GET   |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times`     |JWT read |Liste          |
|GET   |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times/<id>`|JWT read |Einzeln        |
|POST  |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times`     |JWT write|Anlegen        |
|PUT   |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times/<id>`|JWT write|Bearbeiten     |
|DELETE|`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times/<id>`|JWT write|Löschen        |

POST/PUT-Body: `feeding_time` (Pflicht bei POST, `"HH:MM"`), `day_of_week`
(optional, 0=Mo…6=So, leer = täglich), `note` (optional), `is_public`
(optional, Default `true`). PUT akzeptiert nur diese vier Felder — Versuch,
`enclosure_species_id` o.ä. zu ändern, gibt `400`.

-----

### Births (eigenständige CRUD-Endpoints) ✨ neu

|Method|Endpoint                                                 |Auth     |Beschreibung   |
|------|-----------------------------------------------------------|---------|---------------|
|GET   |`/api/v1/zoos/<zoo>/births`                               |JWT read |Alle im Zoo, optional `?species_id=<id>`|
|GET   |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/births`     |JWT read |Liste          |
|GET   |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/births/<id>`|JWT read |Einzeln        |
|POST  |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/births`     |JWT write|Anlegen        |
|PUT   |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/births/<id>`|JWT write|Bearbeiten     |
|DELETE|`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/births/<id>`|JWT write|Löschen        |

POST/PUT-Body: `birth_date` (Pflicht bei POST, `"YYYY-MM-DD"`), `count`
(optional, Default `1`), `note` (optional), `is_public` (optional, Default
`true`). `species_id`/`zoo_id` werden serverseitig aus der
`enclosure_species` übernommen — auch wenn der Client sie mitschickt,
werden sie ignoriert. PUT akzeptiert nur `birth_date`/`count`/`note`/
`is_public` — `400` bei anderen Feldern.

> Anders als beim kaskadierenden Löschen über die enclosure_species selbst
> (dort: `enclosure_species_id` → `NULL`, historisches Faktum bleibt
> erhalten) löscht `DELETE .../births/<id>` die Zeile tatsächlich — gedacht
> für die direkte Korrektur einer einzelnen Fehleingabe.

`GET /api/v1/zoos/<zoo>/births` nutzt die eigene `zoo_id`-Spalte von
`births` direkt (kein Join über `enclosure_species` nötig) — births deren
`enclosure_species` inzwischen gelöscht wurde (`enclosure_species_id` ist
dann `NULL`) tauchen hier weiterhin auf.

-----

## Domains (Zoo-Bereiche)

|Method|Endpoint                         |Auth     |Beschreibung                          |
|------|---------------------------------|---------|--------------------------------------|
|GET   |`/api/v1/zoos/<zoo>/domains`     |JWT read |Alle Domains (zoo-spezifisch + global)|
|GET   |`/api/v1/zoos/<zoo>/domains/<id>`|JWT read |Einzelne Domain                       |
|POST  |`/api/v1/zoos/<zoo>/domains`     |JWT write|Domain anlegen                        |
|PUT   |`/api/v1/zoos/<zoo>/domains/<id>`|JWT write|Domain bearbeiten                     |
|DELETE|`/api/v1/zoos/<zoo>/domains/<id>`|JWT write|Domain löschen                        |

-----

## Locations (Infrastruktur-POIs)

Toiletten, Restaurants, Spielplätze, Eingänge, etc.

|Method|Endpoint                           |Auth     |Beschreibung                    |
|------|-----------------------------------|---------|--------------------------------|
|GET   |`/api/v1/zoos/<zoo>/locations`     |JWT read |Alle Infrastruktur-POIs         |
|GET   |`/api/v1/zoos/<zoo>/locations/<id>`|JWT read |POI-Details inkl. Öffnungszeiten|
|POST  |`/api/v1/zoos/<zoo>/locations`     |JWT write|POI anlegen                     |
|PUT   |`/api/v1/zoos/<zoo>/locations/<id>`|JWT write|POI bearbeiten                  |
|DELETE|`/api/v1/zoos/<zoo>/locations/<id>`|JWT write|POI löschen                     |

-----

## Location Types (Infrastruktur-Typen) ✨ neu

Vordefinierte Typen für Infrastruktur-POIs (Toilette, Restaurant, Spielplatz, …).  
Lesen: alle JWT-User. Schreiben: nur super_admin.

|Method|Endpoint                     |Auth           |Beschreibung          |
|------|-----------------------------|---------------|----------------------|
|GET   |`/api/v1/location-types`     |JWT            |Alle Location-Typen   |
|GET   |`/api/v1/location-types/<id>`|JWT            |Einzelner Location-Typ|
|POST  |`/api/v1/location-types`     |JWT super_admin|Typ anlegen           |
|PUT   |`/api/v1/location-types/<id>`|JWT super_admin|Typ bearbeiten        |
|DELETE|`/api/v1/location-types/<id>`|JWT super_admin|Typ löschen           |


> DELETE schlägt mit `409` fehl wenn noch Locations diesen Typ verwenden.

-----

## Species (Tierarten)

|Method|Endpoint                    |Auth     |Beschreibung                        |
|------|----------------------------|---------|------------------------------------|
|GET   |`/api/v1/species?search=<q>`|JWT      |Globale Suche (deutsch + lateinisch)|
|POST  |`/api/v1/species`           |JWT write (global)|Tierart anlegen                     |
|DELETE|`/api/v1/species/<id>`      |JWT super_admin|Tierart löschen (`409` falls noch `enclosure_species`/`births` verknüpft)|
|GET   |`/api/v1/zoos/<zoo>/species`|JWT read |Artenliste pro Zoo                  |

**Query-Parameter für `/api/v1/zoos/<zoo>/species`:**

- `?search=Löwe` — Suche in deutschem oder lateinischem Namen
- `?domain_id=3` — Filter nach Domain

-----

## Media (Bilder)

|Method|Endpoint                                      |Auth     |Beschreibung                |
|------|----------------------------------------------|---------|----------------------------|
|GET   |`/api/v1/media/<entity_type>/<id>`            |JWT      |Media-Liste für eine Entität|
|POST  |`/api/v1/media/<entity_type>/<id>`            |JWT write|Bild hochladen              |
|DELETE|`/api/v1/media/<id>?zoo=<slug>`               |JWT write|Bild löschen                |
|GET   |`/api/v1/files/<zoo>/<entity_type>/<filename>`|JWT read |Bild abrufen                |

**Erlaubte `entity_type`-Werte:**
`zoo`, `species`, `enclosure`, `enclosure_species`, `house`, `location`, `domain`

> `species` ist zoo-übergreifend (global) — der gespeicherte Pfad hat hier
> kein `<zoo>`-Segment, sondern die Form `species/<filename>`.

**Erlaubte Formate:** JPEG, PNG, WebP · **Max. Größe:** 10 MB · SVG verboten  
**Dateiendung** wird strikt an MIME-Typ gebunden (Fix Juni 2026).

-----

## Feedback

|Method|Endpoint                                 |Auth     |Beschreibung              |
|------|-----------------------------------------|---------|--------------------------|
|GET   |`/api/v1/feedback-types`                 |App-Token|Feedback-Typen            |
|POST  |`/api/v1/zoos/<zoo>/feedback`            |App-Token|Feedback einreichen       |
|GET   |`/api/v1/zoos/<zoo>/feedback`            |JWT write|Feedback-Queue (Zoo-Admin)|
|GET   |`/api/v1/zoos/<zoo>/feedback/<id>`       |JWT write|Einzelnes Feedback        |
|PUT   |`/api/v1/zoos/<zoo>/feedback/<id>/accept`|JWT write|Akzeptieren               |
|PUT   |`/api/v1/zoos/<zoo>/feedback/<id>/reject`|JWT write|Ablehnen                  |

**Feedback-Typen:**

|ID|Slug                  |Pflichtfelder                                                |
|--|----------------------|--------------------------------------------------------------|
|1 |`feeding_time`        |`enclosure_species_id`, `value_time`                         |
|2 |`position`            |`enclosure_species_id`, `value_latitude`, `value_longitude`  |
|3 |`new_species_wikidata`|`enclosure_species_id`, `value_wikidata_id`                  |
|4 |`new_species_existing`|`enclosure_species_id`, `value_species_id`                   |
|5 |`species_birthday`    |`enclosure_species_id`, `value_species_id`, `value_date`     |
|6 |`count_adult`         |`enclosure_species_id`, `value_species_id`, `value_count`    |
|7 |`count_juvenile`      |`enclosure_species_id`, `value_species_id`, `value_count`    |
|8 |`text_incorrect`      |`value_enrichment_text_id`                                   |
|9 |`text_helpful`        |`value_enrichment_text_id`                                   |
|10|`text_excellent`      |`value_enrichment_text_id`                                   |

Rate-Limit: 2/min, 60/Tag pro Gerät.

-----

## Publish

|Method|Endpoint                    |Auth       |Beschreibung         |
|------|----------------------------|-----------|---------------------|
|POST  |`/api/v1/zoos/<zoo>/publish`|JWT publish|SQLite neu generieren|

Gibt `409` wenn bereits ein Export für diesen Zoo läuft.

-----

## SQLite-Download

|Method|Endpoint   |Auth              |Beschreibung       |
|------|-----------|------------------|-------------------|
|GET   |`/db/<zoo>`|App-Token oder JWT|SQLite-Datei (gzip)|

-----

## RSS-Feed

|Method|Endpoint     |Auth|Beschreibung          |
|------|-------------|----|----------------------|
|GET   |`/feed`      |—   |Zoo-Verzeichnis (JSON)|
|GET   |`/feed/<zoo>`|—   |Zoo-Feed (RSS 2.0)    |

-----

## Admin — Zoos

|Method|Endpoint                  |Auth                          |Beschreibung    |
|------|--------------------------|------------------------------|----------------|
|GET   |`/api/v1/admin/zoos`      |JWT super_admin               |Zoo-Liste       |
|GET   |`/api/v1/admin/zoos/<zoo>`|JWT super_admin / tenant_admin|Zoo-Details     |
|POST  |`/api/v1/admin/zoos`      |JWT super_admin               |Zoo anlegen     |
|PUT   |`/api/v1/admin/zoos/<zoo>`|JWT super_admin / tenant_admin|Zoo bearbeiten  |
|DELETE|`/api/v1/admin/zoos/<zoo>`|JWT super_admin               |Zoo deaktivieren|

-----

## Admin — Tenants

|Method|Endpoint                               |Auth                          |Beschreibung       |
|------|---------------------------------------|------------------------------|-------------------|
|GET   |`/api/v1/admin/tenants`                |JWT super_admin               |Tenant-Liste       |
|GET   |`/api/v1/admin/tenants/<id>`           |JWT super_admin / tenant_admin|Tenant-Details     |
|POST  |`/api/v1/admin/tenants`                |JWT super_admin               |Tenant anlegen     |
|PUT   |`/api/v1/admin/tenants/<id>`           |JWT super_admin               |Tenant bearbeiten  |
|DELETE|`/api/v1/admin/tenants/<id>`           |JWT super_admin               |Tenant deaktivieren|
|POST  |`/api/v1/admin/tenants/<id>/zoos`      |JWT super_admin               |Zoo Tenant zuordnen|
|DELETE|`/api/v1/admin/tenants/<id>/zoos/<zoo>`|JWT super_admin               |Zuordnung entfernen|

-----

## Admin — Users

|Method|Endpoint                  |Auth           |Beschreibung              |
|------|--------------------------|---------------|--------------------------|
|GET   |`/api/v1/admin/users`     |JWT super_admin|User-Liste (`?tenant_id=`)|
|GET   |`/api/v1/admin/users/<id>`|JWT super_admin|User-Details + Rollen     |
|PUT   |`/api/v1/admin/users/<id>`|JWT super_admin|User bearbeiten           |
|DELETE|`/api/v1/admin/users/<id>`|JWT super_admin|User deaktivieren         |

-----

## Admin — Rollen

|Method|Endpoint                                         |Auth                          |Beschreibung           |
|------|-------------------------------------------------|------------------------------|-----------------------|
|POST  |`/api/v1/admin/users/<id>/roles/zoo`             |JWT super_admin / tenant_admin|Zoo-Rolle vergeben     |
|DELETE|`/api/v1/admin/users/<id>/roles/zoo/<zoo>/<role>`|JWT super_admin / tenant_admin|Zoo-Rolle entziehen    |
|POST  |`/api/v1/admin/users/<id>/roles/tenant`          |JWT super_admin               |Tenant-Rolle vergeben  |
|DELETE|`/api/v1/admin/users/<id>/roles/tenant/<tid>`    |JWT super_admin               |Tenant-Rolle entziehen |
|POST  |`/api/v1/admin/users/<id>/roles/global`          |JWT super_admin               |Globale Rolle vergeben |
|DELETE|`/api/v1/admin/users/<id>/roles/global/<role>`   |JWT super_admin               |Globale Rolle entziehen|

**Zoo-Rollen:** `viewer` · `editor` · `zoo_admin`  
**Tenant-Rollen:** `tenant_admin`  
**Globale Rollen:** `super_admin` · `moderator`

-----

## Admin — System

|Method|Endpoint                              |Auth                       |Beschreibung          |
|------|--------------------------------------|---------------------------|----------------------|
|GET   |`/api/v1/admin/settings`              |JWT super_admin            |System-Settings       |
|PUT   |`/api/v1/admin/settings/<key>`        |JWT super_admin            |Setting ändern        |
|GET   |`/api/v1/admin/audit`                 |JWT super_admin            |Audit-Log             |
|GET   |`/api/v1/admin/proposals`             |JWT super_admin / moderator|Species-Proposals     |
|PUT   |`/api/v1/admin/proposals/<id>/approve`|JWT super_admin / moderator|Proposal genehmigen   |
|PUT   |`/api/v1/admin/proposals/<id>/reject` |JWT super_admin / moderator|Proposal ablehnen     |
|DELETE|`/api/v1/admin/test-fixtures/rbac`    |JWT super_admin            |RBAC-Testdaten löschen|

-----

## Zusammenfassung

|Gruppe        |Endpoints|Änderung                       |
|--------------|---------|-------------------------------|
|System        |3        |                               |
|Auth          |9        |                               |
|Zoos          |2        |                               |
|Enclosures    |4        |                               |
|Houses        |5        |                               |
|Enclosure Species|5     |✨ +1 GET-Single                |
|Feeding Times |6        |✨ neu                          |
|Births        |6        |✨ neu                          |
|Domains       |5        |✨ +4 (POST/PUT/DELETE + GET id)|
|Locations     |5        |✨ neu                          |
|Location Types|5        |✨ neu                          |
|Species       |4        |                               |
|Media         |4        |✨ +domain entity_type          |
|Feedback      |6        |                               |
|Publish       |1        |                               |
|SQLite        |1        |                               |
|RSS-Feed      |2        |                               |
|Admin Zoos    |5        |                               |
|Admin Tenants |7        |                               |
|Admin Users   |4        |                               |
|Admin Rollen  |6        |                               |
|Admin System  |7        |                               |
|**Gesamt**    |**102**  |**+22 gegenüber V1**            |