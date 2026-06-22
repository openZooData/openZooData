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

**Medien-Felder in der Zoo-Detail-Antwort:** `icon_media_id` und
`map_overlay_1_id` … `map_overlay_5_id` sind direkte FK-Spalten auf
`zoo.zoos`, jeweils aufgelöst zu `icon_media_path` / `map_overlay_1_path`
… `map_overlay_5_path` (Pfad aus `storage_path || filename`, `null` falls
noch nicht verknüpft). Die alten Einzelwert-Felder `icon_url` (für den
RSS-Feed) und `map_overlay` bleiben unverändert zusätzlich Teil der Antwort
— kein Merge, der Client entscheidet selbst welche Quelle er verwendet.

`time_open` / `time_close` sind einfache Zeitfelder direkt auf `zoo.zoos`
(eine einzige, globale Öffnungszeit ohne Wochentag-Differenzierung),
editierbar über `PUT /api/v1/admin/zoos/<zoo>`. Daneben gibt es die
detaillierten wochentag-basierten Öffnungszeiten über `zoo.zoo_opening_hours`
— siehe Abschnitt [Öffnungszeiten](#öffnungszeiten).

Verknüpfen ausschließlich manuell per SQL (kein API-Endpoint):

```sql
UPDATE zoo.zoos SET icon_media_id   = <media.id> WHERE slug = '<zoo>';
UPDATE zoo.zoos SET map_overlay_1_id = <media.id> WHERE slug = '<zoo>';
```

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

## Enclosure Species (Tier-Zuordnungen)

Verknüpft eine Tierart (Species) mit einem Ort im Zoo — optional einem
Enclosure (Freigehege) und/oder einem House (Tierhaus). Zentraler
Knotenpunkt für Fütterungszeiten, Geburten, GPS-Position (`geo_points`) und
Foto (`media`).

|Method|Endpoint                                   |Auth     |Beschreibung                                        |
|------|-------------------------------------------|---------|----------------------------------------------------|
|GET   |`/api/v1/zoos/<zoo>/enclosure_species`     |JWT read |Alle Tier-Zuordnungen inkl. `feeding_times`, `births`|
|GET   |`/api/v1/zoos/<zoo>/enclosure_species/<id>`|JWT read |Einzelne Zuordnung                                  |
|POST  |`/api/v1/zoos/<zoo>/enclosure_species`     |JWT write|Zuordnung anlegen                                   |
|PUT   |`/api/v1/zoos/<zoo>/enclosure_species/<id>`|JWT write|Zuordnung bearbeiten                                |
|DELETE|`/api/v1/zoos/<zoo>/enclosure_species/<id>`|JWT write|Zuordnung löschen (inkl. `media`/`geo_points`)      |

**Query-Parameter für GET:** `?enclosure_id=`, `?house_id=`, `?domain_id=`

**Zwei Wege für `feeding_times`/`births`:** entweder verschachtelt über
`enclosure_species` (POST/PUT, delete-all-reinsert-Semantik), oder über
die eigenständigen Sub-Resource-Endpoints weiter unten — beide Wege
funktionieren parallel. `enclosure_species_id` (und bei `births` zusätzlich
`species_id`/`zoo_id`) kommen immer aus dem URL-/Parent-Kontext, nie vom
Client.

**DELETE-Verhalten (beim Löschen der enclosure_species selbst):**

|Tabelle      |Verhalten                                                        |
|-------------|------------------------------------------------------------------|
|feeding_times|automatisch mitgelöscht (`ON DELETE CASCADE`)                      |
|births       |bleibt erhalten, `enclosure_species_id` → `NULL` (historisch)     |
|geo_points   |wird explizit gelöscht (polymorph, keine FK möglich)              |
|media        |wird explizit gelöscht inkl. physischer Datei                     |

-----

### Feeding Times (eigenständige CRUD-Endpoints)

|Method|Endpoint                                                        |Auth     |Beschreibung                             |
|------|----------------------------------------------------------------|---------|-----------------------------------------|
|GET   |`/api/v1/zoos/<zoo>/feeding_times`                              |JWT read |Alle im Zoo, optional `?species_id=<id>` |
|GET   |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times`    |JWT read |Liste                                    |
|GET   |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times/<id>`|JWT read |Einzeln                                  |
|POST  |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times`    |JWT write|Anlegen                                  |
|PUT   |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times/<id>`|JWT write|Bearbeiten                               |
|DELETE|`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times/<id>`|JWT write|Löschen                                  |

POST/PUT-Body: `feeding_time` (Pflicht bei POST, `"HH:MM"`), `day_of_week` (0=Mo…6=So), `note`, `is_public` (Default `true`).

-----

### Births (eigenständige CRUD-Endpoints)

|Method|Endpoint                                                  |Auth     |Beschreibung                             |
|------|----------------------------------------------------------|---------|-----------------------------------------|
|GET   |`/api/v1/zoos/<zoo>/births`                               |JWT read |Alle im Zoo, optional `?species_id=<id>` |
|GET   |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/births`     |JWT read |Liste                                    |
|GET   |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/births/<id>`|JWT read |Einzeln                                  |
|POST  |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/births`     |JWT write|Anlegen                                  |
|PUT   |`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/births/<id>`|JWT write|Bearbeiten                               |
|DELETE|`/api/v1/zoos/<zoo>/enclosure_species/<es_id>/births/<id>`|JWT write|Löschen                                  |

POST/PUT-Body: `birth_date` (Pflicht bei POST, `"YYYY-MM-DD"`), `count` (Default `1`), `note`, `is_public` (Default `true`). `species_id`/`zoo_id` kommen serverseitig aus der `enclosure_species`, nie vom Client. `GET /api/v1/zoos/<zoo>/births` nutzt die eigene `zoo_id`-Spalte — births überleben auch dann, wenn ihre `enclosure_species` gelöscht wurde (`enclosure_species_id = NULL`).

-----

## Domains

|Method|Endpoint                             |Auth     |Beschreibung    |
|------|-------------------------------------|---------|----------------|
|GET   |`/api/v1/zoos/<zoo>/domains`         |JWT read |Alle Domains    |
|GET   |`/api/v1/zoos/<zoo>/domains/<id>`    |JWT read |Domain-Details  |
|POST  |`/api/v1/zoos/<zoo>/domains`         |JWT write|Domain anlegen  |
|PUT   |`/api/v1/zoos/<zoo>/domains/<id>`    |JWT write|Domain bearbeiten|
|DELETE|`/api/v1/zoos/<zoo>/domains/<id>`    |JWT write|Domain löschen  |

-----

## Locations (Infrastruktur-POIs)

|Method|Endpoint                            |Auth     |Beschreibung                |
|------|------------------------------------|---------|----------------------------|
|GET   |`/api/v1/zoos/<zoo>/locations`      |JWT read |Alle POIs                   |
|GET   |`/api/v1/zoos/<zoo>/locations/<id>` |JWT read |POI-Details + Öffnungszeiten|
|POST  |`/api/v1/zoos/<zoo>/locations`      |JWT write|POI anlegen                 |
|PUT   |`/api/v1/zoos/<zoo>/locations/<id>` |JWT write|POI bearbeiten              |
|DELETE|`/api/v1/zoos/<zoo>/locations/<id>` |JWT write|POI löschen (inkl. Media)   |

Beim Anlegen (`POST`) wird automatisch ein `zoo.media`-Eintrag für das Icon
angelegt, sofern `location_type_id` gesetzt ist:
`storage_path = zoo/<zoo_slug>/locations/`, `filename = <location_type.icon>.png`.
`icon_media_id` wird direkt auf `zoo.locations` gesetzt. Beim Löschen wird
der Media-DB-Eintrag mitgelöscht, die Datei bleibt auf Disk.

Öffnungszeiten werden als `opening_hours[]`-Array in `GET /locations/<id>`
mitgeliefert und über die Sub-Resource
`/locations/<id>/opening_hours` (CRUD) verwaltet — siehe
Abschnitt [Öffnungszeiten](#öffnungszeiten).

**Erlaubte Felder für PUT:**
`name`, `name_display`, `description`, `location_type`, `location_type_id`,
`sort_order`, `domain_id`, `url`, `description_long`, `latitude`, `longitude`.
`time_open`/`time_close` existieren auf Locations **nicht** — Öffnungszeiten
laufen über die Sub-Resource `.../opening_hours`.

-----

## Location Types

|Method|Endpoint                                        |Auth     |Beschreibung              |
|------|------------------------------------------------|---------|--------------------------|
|GET   |`/api/v1/location-types`                        |JWT read |Alle Typen                |
|GET   |`/api/v1/location-types/<id>`                   |JWT read |Typ-Details               |
|POST  |`/api/v1/location-types`                        |JWT write|Typ anlegen               |
|PUT   |`/api/v1/location-types/<id>`                   |JWT write|Typ bearbeiten            |
|DELETE|`/api/v1/location-types/<id>`                   |JWT write|Typ löschen               |

-----

## Species

|Method|Endpoint                   |Auth              |Beschreibung              |
|------|---------------------------|------------------|--------------------------|
|GET   |`/api/v1/species`          |JWT               |Alle validen Species      |
|GET   |`/api/v1/species/<id>`     |JWT               |Species-Details           |
|POST  |`/api/v1/species`          |JWT write (global)|Species anlegen           |
|PUT   |`/api/v1/species/<id>`     |JWT super_admin   |Species bearbeiten        |
|DELETE|`/api/v1/species/<id>`     |JWT super_admin   |Species löschen           |

**POST — automatische Wikidata-Anreicherung:** beim Anlegen wird synchron
(`blocking`) ein SPARQL-Call gegen Wikidata abgesetzt. Abgerufen werden:
latin_name (P225), Taxonomie (P171/P105: Kingdom, Phylum, Class, Order,
Family, Genus), IUCN-Status (P141), Populationstrend (P2241), IUCN-Taxon-ID
(P627), GBIF Taxon Key (P846). Alle Felder werden direkt in `zoo.species`
gespeichert. Ist kein Wikidata-Call möglich (kein `wikidata_id` angegeben
oder SPARQL-Fehler), wird trotzdem eine Species angelegt, nur ohne
angereicherte Daten.

**POST — automatischer Media-Eintrag:** nach dem Species-INSERT wird
automatisch ein `zoo.media`-Eintrag für das Icon angelegt und `icon_media_id`
direkt gesetzt:
`storage_path = species/`, `filename = <wikidata_id>_<latin_name>.png`
(Leerzeichen → Unterstrich). Nur wenn `wikidata_id` vorhanden ist.

**DELETE:** schlägt mit `409` fehl, wenn noch `enclosure_species` oder
`births` verknüpft sind. Media-DB-Eintrag wird mitgelöscht, Datei bleibt
auf Disk.

Media-Pfad-Ausnahme bei Datei-Auslieferung: Species-Icons liegen unter
`media/species/` (physischer Pfad), aber `storage_path` in der DB ist
`species/` (ohne `media/`-Prefix).

-----

## Media

|Method|Endpoint                           |Auth              |Beschreibung                   |
|------|-----------------------------------|------------------|-------------------------------|
|POST  |`/api/v1/media/<entity_type>/<id>` |JWT write (global)|Datei hochladen (multipart)    |
|GET   |`/api/v1/media/<entity_type>/<id>` |JWT read          |Media-Einträge einer Entity    |
|DELETE|`/api/v1/media/<id>`               |JWT write (global)|Media-Eintrag löschen          |
|GET   |`/media/<path>`                    |App-Token oder JWT|Datei ausliefern               |

`entity_type`: `species`, `enclosure_species`, `location`, `house`, `zoo`, `domain`

-----

## Zoo Species

|Method|Endpoint                        |Auth    |Beschreibung                        |
|------|--------------------------------|--------|------------------------------------|
|GET   |`/api/v1/zoos/<zoo>/species`    |JWT read|Species des Zoos (aus enclosure_species)|

-----

## Öffnungszeiten

Öffnungszeiten existieren an drei Stellen im System, alle mit identischer
Struktur (separate Zeile pro Wochentag, optional Gültigkeitszeitraum).
Jede Entität kann mehrere Einträge pro Wochentag haben (z.B. Sommer- vs.
Winterzeit über `valid_from`/`valid_until` unterschieden).

|Tabelle                 |Zugehörig zu|Endpoints                                          |
|------------------------|------------|---------------------------------------------------|
|`zoo.zoo_opening_hours` |Zoo         |`/api/v1/zoos/<zoo>/opening_hours`                 |
|`zoo.opening_hours`     |Location-POI|`/api/v1/zoos/<zoo>/locations/<id>/opening_hours`  |
|`zoo.house_opening_hours`|Tierhaus   |`/api/v1/zoos/<zoo>/houses/<id>/opening_hours`     |

### Zoo-Öffnungszeiten

|Method|Endpoint                                   |Auth     |Beschreibung|
|------|-------------------------------------------|---------|------------|
|GET   |`/api/v1/zoos/<zoo>/opening_hours`         |JWT read |Liste       |
|GET   |`/api/v1/zoos/<zoo>/opening_hours/<id>`    |JWT read |Einzeln     |
|POST  |`/api/v1/zoos/<zoo>/opening_hours`         |JWT write|Anlegen     |
|PUT   |`/api/v1/zoos/<zoo>/opening_hours/<id>`    |JWT write|Bearbeiten  |
|DELETE|`/api/v1/zoos/<zoo>/opening_hours/<id>`    |JWT write|Löschen     |

### Location-Öffnungszeiten

|Method|Endpoint                                                        |Auth     |Beschreibung|
|------|----------------------------------------------------------------|---------|------------|
|GET   |`/api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours`           |JWT read |Liste       |
|GET   |`/api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours/<id>`      |JWT read |Einzeln     |
|POST  |`/api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours`           |JWT write|Anlegen     |
|PUT   |`/api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours/<id>`      |JWT write|Bearbeiten  |
|DELETE|`/api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours/<id>`      |JWT write|Löschen     |

### House-Öffnungszeiten

|Method|Endpoint                                                           |Auth     |Beschreibung|
|------|-------------------------------------------------------------------|---------|------------|
|GET   |`/api/v1/zoos/<zoo>/houses/<house_id>/opening_hours`               |JWT read |Liste       |
|GET   |`/api/v1/zoos/<zoo>/houses/<house_id>/opening_hours/<id>`          |JWT read |Einzeln     |
|POST  |`/api/v1/zoos/<zoo>/houses/<house_id>/opening_hours`               |JWT write|Anlegen     |
|PUT   |`/api/v1/zoos/<zoo>/houses/<house_id>/opening_hours/<id>`          |JWT write|Bearbeiten  |
|DELETE|`/api/v1/zoos/<zoo>/houses/<house_id>/opening_hours/<id>`          |JWT write|Löschen     |

**POST/PUT-Body** (alle drei identisch):

```json
{
  "day_of_week": "monday",
  "open_time":   "09:00",
  "close_time":  "18:00",
  "valid_from":  "2026-04-01",
  "valid_until": "2026-10-31",
  "label":       "Sommerzeit"
}
```

- `day_of_week`: Pflicht bei POST. Erlaubte Werte: `monday`, `tuesday`, `wednesday`, `thursday`, `friday`, `saturday`, `sunday`. `null` = täglich gültig.
- `open_time` / `close_time`: `"HH:MM"` — beim Lesen kommt `"HH:MM:SS"` zurück (PostgreSQL `time`-Typ)
- `valid_from` / `valid_until`: `"YYYY-MM-DD"` oder `null` (= immer gültig)
- `label`: optionaler Beschriftungstext, z.B. `"Sommerzeit"`, `"Feiertage"`

**Wichtig für den iOS-Agent:** `time_open`/`time_close` sind separate Felder
direkt auf `zoo.zoos` (eine einzige globale Öffnungszeit ohne Wochentag),
editierbar über `PUT /api/v1/admin/zoos/<zoo>`. Diese Felder existieren
**nicht** auf Locations oder Houses — `PUT /locations/<id>` und
`PUT /houses/<id>` lehnen `time_open`/`time_close` mit `400 Unknown fields`
ab. Öffnungszeiten für Locations und Houses immer über die Sub-Resource
`.../opening_hours` verwalten.

`GET /api/v1/zoos/<zoo>/locations/<id>` und
`GET /api/v1/zoos/<zoo>/houses/<id>` liefern die Öffnungszeiten bereits als
verschachteltes `opening_hours[]`-Array mit — separate Calls auf die
Sub-Resource sind nur für Write-Operationen nötig.

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

CORS (`Access-Control-Allow-Origin: *`) auf beiden Feed-Endpoints.

-----

## Admin — Zoos

|Method|Endpoint                  |Auth                          |Beschreibung    |
|------|--------------------------|------------------------------|----------------|
|GET   |`/api/v1/admin/zoos`      |JWT super_admin               |Zoo-Liste       |
|GET   |`/api/v1/admin/zoos/<zoo>`|JWT super_admin / tenant_admin|Zoo-Details     |
|POST  |`/api/v1/admin/zoos`      |JWT super_admin               |Zoo anlegen     |
|PUT   |`/api/v1/admin/zoos/<zoo>`|JWT super_admin / tenant_admin|Zoo bearbeiten  |
|DELETE|`/api/v1/admin/zoos/<zoo>`|JWT super_admin               |Zoo deaktivieren|

`GET /api/v1/admin/zoos/<zoo>` liefert dieselben Medien-Felder
(`icon_media_path`, `map_overlay_1_path` … `map_overlay_5_path`,
`icon_url`, `map_overlay`) wie der app-seitige Endpoint.

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

|Gruppe           |Endpoints|Hinweis                                    |
|-----------------|---------|-------------------------------------------|
|System           |3        |                                           |
|Auth             |9        |                                           |
|Zoos             |2        |icon_media_path + map_overlay_1..5_path    |
|Enclosures       |4        |                                           |
|Houses           |5        |                                           |
|Enclosure Species|5        |                                           |
|Feeding Times    |6        |inkl. zoo-weiter Liste                     |
|Births           |6        |inkl. zoo-weiter Liste                     |
|Öffnungszeiten   |15       |Zoo + Locations + Houses, je 5 Endpoints   |
|Domains          |5        |                                           |
|Locations        |5        |Auto-Media-Eintrag beim Anlegen            |
|Location Types   |5        |                                           |
|Species          |5        |Auto-Wikidata + Auto-Media-Eintrag         |
|Zoo Species      |1        |                                           |
|Media            |4        |                                           |
|Feedback         |6        |                                           |
|Publish          |1        |                                           |
|SQLite           |1        |                                           |
|RSS-Feed         |2        |CORS                                       |
|Admin Zoos       |5        |                                           |
|Admin Tenants    |7        |                                           |
|Admin Users      |4        |                                           |
|Admin Rollen     |6        |                                           |
|Admin System     |7        |                                           |
|**Gesamt**       |**119**  |                                           |
