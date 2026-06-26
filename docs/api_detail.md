# OpenZooData API Detail

> Detailed REST API documentation for the current OpenZooData server code.

This document describes the API exposed by the Flask application under `source/app.py` and the registered route blueprints.

It is intended to be integrated into the official repository as:

```text
docs/api_detail.md
```

---

## Status of this document

This documentation reflects the API structure visible in the current codebase.

Some endpoint implementations are still in active development. Where the exact response shape depends on database content, the document describes the returned fields based on the SQL queries in the routes.

---

## Base URL

Local development:

```text
http://127.0.0.1:5001
```

Production example:

```text
https://api.openzoodata.org
```

All API paths in this document are relative to the base URL.

---

## Authentication overview

OpenZooData currently uses three access patterns:

| Access model | Used for | Header / Body |
|---|---|---|
| Public | Root, basic health, RSS feed list | none |
| App token | mobile app / SQLite / feedback | `Authorization: Bearer <app_token>` |
| Admin JWT | user/admin/zoo editing APIs | `Authorization: Bearer <access_token>` |
| Health key | detailed health check | `X-Health-Key: <health_key>` |

### App token

App tokens are issued to app installations, not to human users.

Typical flow:

```text
POST /api/v1/auth/app_register
POST /api/v1/auth/app_refresh
```

### Admin JWT

Admin users log in with email and password and receive:

- `access_token`
- `refresh_token`

Typical flow:

```text
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
```

### Role-based access

The code uses action-level checks such as:

| Permission action | Typical use |
|---|---|
| `read` | read zoo-specific data |
| `write` | create/update/delete zoo-specific data |
| `admin` | review feedback and administrative zoo operations |
| `publish` | publish/export zoo data |

Super-admin endpoints use `require_super_admin()`.

---

## Standard response conventions

### Successful create

Most create endpoints return:

```json
{
  "id": 123,
  "message": "Created"
}
```

HTTP status:

```text
201 Created
```

### Successful update

Most update endpoints return:

```json
{
  "message": "Updated"
}
```

HTTP status:

```text
200 OK
```

### Successful delete

Most delete endpoints return:

```json
{
  "message": "Deleted"
}
```

HTTP status:

```text
200 OK
```

### Common error shape

```json
{
  "error": "Error message"
}
```

### Common status codes

| Code | Meaning |
|---:|---|
| `200` | Success |
| `201` | Created |
| `304` | SQLite export not modified |
| `400` | Invalid input |
| `401` | Missing or invalid authentication |
| `403` | Unauthorized / insufficient permissions |
| `404` | Not found |
| `409` | Conflict |
| `429` | Rate limit exceeded |
| `500` | Internal server error |
| `503` | Health degraded |

---

## Rate limiting

The API uses Flask-Limiter. Limits are defined per route.

Common patterns:

| Limit | Used for |
|---|---|
| `60 per minute` | most read endpoints |
| `30 per minute` | most write/update endpoints |
| `10 per minute` | destructive or expensive endpoints |
| `5 per minute` | publish/export |
| `2 per minute` + daily limit | feedback submissions per token |

If a limit is exceeded, the API returns:

```json
{
  "error": "Rate limit exceeded. Please slow down."
}
```

HTTP status:

```text
429 Too Many Requests
```

---

# 1. Root and health

## `GET /`

Basic API root endpoint.

### Authentication

None.

### Response

```json
{
  "message": "openZooData API is running.",
  "status": "ok"
}
```

---

## `GET /status`

Basic health check for monitoring.

The endpoint checks both:

- Zoo PostgreSQL database
- Auth PostgreSQL database

### Authentication

None.

### Success response

```json
{
  "status": "ok"
}
```

Status:

```text
200 OK
```

### Degraded response

```json
{
  "status": "degraded"
}
```

Status:

```text
503 Service Unavailable
```

---

## `GET /status/details`

Detailed health check.

### Authentication

Requires:

```http
X-Health-Key: <health_key>
```

### Rate limit

```text
30 per minute
```

### Success response

```json
{
  "status": "ok",
  "checks": {
    "db_zoo": "ok",
    "db_auth": "ok",
    "sqlite_files": 3
  }
}
```

### Unauthorized response

```json
{
  "error": "Unauthorized"
}
```

Status:

```text
403 Forbidden
```

---

# 2. Admin authentication

## `POST /api/v1/auth/login`

Logs in an administrative user.

### Authentication

None.

### Rate limit

```text
60 per minute
```

### Request body

```json
{
  "email": "admin@example.org",
  "password": "YourPassword123!",
  "device_id": "optional-device-id"
}
```

### Required fields

| Field | Type | Required | Notes |
|---|---:|:---:|---|
| `email` | string | yes | normalized to lowercase |
| `password` | string | yes | checked against bcrypt hash |
| `device_id` | string | no | stored with refresh token |

### Success response

```json
{
  "access_token": "<jwt>",
  "refresh_token": "<refresh_token>",
  "display_name": "Admin User",
  "must_change_password": false
}
```

Status:

```text
200 OK
```

### Error responses

Missing credentials:

```json
{
  "error": "email and password required"
}
```

Invalid credentials, inactive user, locked user or inactive tenant:

```json
{
  "error": "Invalid credentials"
}
```

### Security behavior

The login route deliberately uses a generic `Invalid credentials` response to reduce user enumeration risk.

Failed logins increment `failed_login_count`. After the configured threshold, the account is locked for a configured time window.

---

## `POST /api/v1/auth/refresh`

Rotates a refresh token and returns a new access token and refresh token.

### Authentication

None.

The refresh token is supplied in the body.

### Rate limit

```text
30 per minute
```

### Request body

```json
{
  "refresh_token": "<refresh_token>"
}
```

### Success response

```json
{
  "access_token": "<new_jwt>",
  "refresh_token": "<new_refresh_token>"
}
```

### Error responses

Missing token:

```json
{
  "error": "refresh_token required"
}
```

Invalid, inactive or expired token:

```json
{
  "error": "Unauthorized"
}
```

### Security behavior

Refresh tokens are rotated. The old token is deactivated when used successfully.

---

## `POST /api/v1/auth/logout`

Logs out by deactivating the provided refresh token. If a valid access JWT is provided, its `jti` can be added to the revoked-token table.

### Authentication

Optional/partial JWT handling is used internally for audit and revocation.

### Rate limit

```text
30 per minute
```

### Request body

```json
{
  "refresh_token": "<refresh_token>"
}
```

### Success response

```json
{
  "message": "Logged out"
}
```

---

## `POST /api/v1/auth/register`

Creates a new admin / ZooCreator user and generates an invite.

### Authentication

Requires super admin.

### Rate limit

```text
10 per minute
```

### Request body

```json
{
  "email": "new.user@example.org",
  "display_name": "New User",
  "tenant_id": 1
}
```

### Required fields

| Field | Required | Notes |
|---|:---:|---|
| `email` | yes | must be syntactically valid |
| `display_name` | no | optional display name |
| `tenant_id` | no | validated when supplied |

### Success response

```json
{
  "id": 42,
  "message": "User created and invite generated",
  "invite_sent": false,
  "invite_url": "https://example.org/admin/invite/<token>"
}
```

Status:

```text
201 Created
```

### Conflict response

```json
{
  "error": "User already exists"
}
```

Status:

```text
409 Conflict
```

### Notes

If SMTP is not configured, the route may return the invite URL for staging/reference operation.

---

## `POST /api/v1/auth/invite/<token>`

Accepts an invite and sets the initial password.

### Authentication

None. The invite token in the URL is the authorization mechanism.

### Rate limit

```text
10 per minute
```

### Request body

```json
{
  "password": "NewStrongPassword123!"
}
```

### Validation

| Field | Rule |
|---|---|
| `password` | at least 12 characters |

### Success response

```json
{
  "message": "Invite accepted"
}
```

### Error responses

```json
{
  "error": "password must be at least 12 characters"
}
```

```json
{
  "error": "Invalid or expired invite"
}
```

---

# 3. App-token authentication

## `POST /api/v1/auth/app_register`

Registers an app installation and returns an app token.

### Authentication

None.

### Rate limit

```text
10 per minute
```

### Request body

```json
{
  "device_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Validation

`device_id` must be a UUID.

### Success response

```json
{
  "app_token": "<token>",
  "expires_at": "2026-09-24T12:00:00+00:00"
}
```

Status:

```text
201 Created
```

### Notes

The endpoint is idempotent for the app installation concept. Active old tokens for the same device are deactivated before a new token is issued.

---

## `POST /api/v1/auth/app_refresh`

Refreshes an app token when it is close to expiry.

### Authentication

None; token is supplied in the body.

### Rate limit

```text
30 per minute
```

### Request body

```json
{
  "app_token": "<current_app_token>",
  "device_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Success response — not refreshed

If the token is still valid and not close to expiry:

```json
{
  "app_token": "<same_app_token>",
  "expires_at": "2026-09-24T12:00:00+00:00",
  "refreshed": false
}
```

### Success response — refreshed

```json
{
  "app_token": "<new_app_token>",
  "expires_at": "2026-09-24T12:00:00+00:00",
  "refreshed": true
}
```

### Error responses

```json
{
  "error": "app_token and device_id required"
}
```

```json
{
  "error": "device_id must be a valid UUID"
}
```

```json
{
  "error": "Token invalid or expired — re-register"
}
```

---

# 4. Feeds and offline exports

## `GET /feed`

Lists all public zoo feeds on this server.

### Authentication

None.

### Rate limit

```text
10 per minute
```

### Response

```json
[
  {
    "slug": "zoo_osnabrueck",
    "name": "Zoo Osnabrück",
    "version": 12,
    "feed_url": "https://api.openzoodata.org/feed/zoo_osnabrueck"
  }
]
```

---

## `GET /feed/<zoo>`

Returns an RSS 2.0 feed for one zoo.

### Authentication

None.

### Rate limit

```text
30 per minute
```

### Path parameters

| Parameter | Description |
|---|---|
| `zoo` | Zoo slug, validated by `is_valid_slug()` |

### Response type

```http
Content-Type: application/rss+xml; charset=utf-8
```

### Headers

| Header | Description |
|---|---|
| `Cache-Control` | `public, max-age=300` |
| `X-Zoo-Version` | current zoo data version |

### Error responses

Invalid slug:

```json
{
  "error": "Invalid zoo identifier"
}
```

Zoo not found:

```json
{
  "error": "Zoo not found"
}
```

---

## `GET /db/<zoo>`

Downloads the gzip-compressed SQLite export for a zoo.

### Authentication

Requires app token.

```http
Authorization: Bearer <app_token>
```

### Rate limit

```text
10 per minute
```

### Path parameters

| Parameter | Description |
|---|---|
| `zoo` | Zoo slug |

### Conditional requests

The endpoint supports `If-None-Match` based on the zoo `data_version`.

Example:

```http
If-None-Match: "12"
```

If unchanged:

```text
304 Not Modified
```

### Success response

Binary file download:

```text
<zoo>.sqlite.gz
```

### Headers

| Header | Description |
|---|---|
| `ETag` | current data version |
| `Cache-Control` | `no-cache` |
| `Content-Type` | `application/octet-stream` |

### Error responses

```json
{
  "error": "Invalid zoo identifier"
}
```

```json
{
  "error": "Not found"
}
```

---

## `POST /api/v1/zoos/<zoo>/publish`

Starts the SQLite export/publish process for a zoo.

### Authentication

Requires zoo access with `publish` action.

Typically allowed:

- `super_admin`
- `tenant_admin`
- `zoo_admin`

### Rate limit

```text
5 per minute
```

### Behavior

The route:

1. validates the zoo slug,
2. checks publish permission,
3. verifies that the zoo exists,
4. acquires a PostgreSQL advisory lock,
5. runs the SQLite export script,
6. increments `zoo.zoos.data_version` after successful export,
7. sends publish-failure notifications when configured,
8. always attempts to release the advisory lock.

### Success response

```json
{
  "message": "Export für zoo_osnabrueck erfolgreich",
  "data_version": 13,
  "duration_ms": 1842
}
```

### Conflict response

If another export is already running:

```json
{
  "error": "Export bereits aktiv für diesen Zoo. Bitte warten."
}
```

Status:

```text
409 Conflict
```

### Failure response

```json
{
  "error": "Export fehlgeschlagen",
  "details": "Administratoren wurden benachrichtigt."
}
```

---

# 5. Zoo endpoints

## `GET /api/v1/zoos`

Lists active, non-archived zoos.

### Authentication

Requires authenticated user.

### Rate limit

```text
60 per minute
```

### Returned fields

The query returns:

| Field |
|---|
| `id` |
| `slug` |
| `name` |
| `city` |
| `country` |
| `url` |
| `description` |
| `top_left_latitude` |
| `top_left_longitude` |
| `bottom_right_latitude` |
| `bottom_right_longitude` |
| `map_overlay` |
| `data_version` |
| `easy_language` |
| `number_animals` |
| `icon_url` |
| `latitude` |
| `longitude` |

### Example response

```json
[
  {
    "id": 1,
    "slug": "zoo_osnabrueck",
    "name": "Zoo Osnabrück",
    "city": "Osnabrück",
    "country": "DE",
    "data_version": 12
  }
]
```

---

## `GET /api/v1/zoos/<zoo>`

Returns details for one zoo, including opening hours.

### Authentication

Requires zoo access with `read`.

### Rate limit

```text
60 per minute
```

### Returned fields

Includes base zoo fields plus:

| Field |
|---|
| `email` |
| `time_open` |
| `time_close` |
| `icon_media_path` |
| `map_overlay_1_path` |
| `map_overlay_2_path` |
| `map_overlay_3_path` |
| `map_overlay_4_path` |
| `map_overlay_5_path` |
| `opening_hours` |

### Error responses

```json
{
  "error": "Invalid zoo identifier"
}
```

```json
{
  "error": "Zoo not found"
}
```

---

# 6. Global species endpoints

## `GET /api/v1/species`

Lists valid global species.

### Authentication

Requires authenticated user.

### Rate limit

```text
60 per minute
```

### Query parameters

| Parameter | Type | Default | Notes |
|---|---:|---:|---|
| `search` | string | empty | searches German and Latin name |
| `limit` | integer | `500` | max `1000` |
| `offset` | integer | `0` | pagination offset |

### Returned fields

| Field |
|---|
| `id` |
| `wikidata_id` |
| `german_name` |
| `latin_name` |
| `iucn_status_id` |
| `iucn_id` |
| `gbif_taxon_key` |
| `iucn_population_trend_id` |
| `id_valid` |
| `icon_path` |

### Example request

```bash
curl "$BASE/api/v1/species?search=Elefant&limit=20" \
  -H "Authorization: Bearer $TOKEN"
```

---

## `GET /api/v1/species/<species_id>`

Returns one global species record.

### Authentication

Requires authenticated user.

### Rate limit

```text
60 per minute
```

### Notes

The details endpoint is implemented in the global species blueprint. It is intended to return the species record and related enriched data where available.

---

## `POST /api/v1/species`

Creates a new global species.

### Authentication

Requires authenticated user and write access. The code supports super-admin and write-authorized zoo users.

### Rate limit

```text
30 per minute
```

### Request body

```json
{
  "german_name": "Löwe",
  "latin_name": "Panthera leo",
  "wikidata_id": "Q140",
  "zoo_slug": "zoo_osnabrueck"
}
```

### Required fields

| Field | Required | Notes |
|---|:---:|---|
| `german_name` | yes | local German name |
| `wikidata_id` | yes | required for direct creation |
| `latin_name` | no | scientific name |
| `zoo_slug` | required for non-super-admin | used for permission check |

### Validation

If `wikidata_id` is missing:

```json
{
  "error": "wikidata_id required. Without a validated Wikidata ID, submit a proposal instead."
}
```

### Success response

```json
{
  "id": 4,
  "german_name": "Löwe",
  "latin_name": "Panthera leo",
  "wikidata_id": "Q140",
  "id_valid": true
}
```

Status:

```text
201 Created
```

---

## `PUT /api/v1/species/<species_id>`

Updates a global species record.

### Authentication

Requires super admin.

### Notes

Used for global species corrections.

---

## `DELETE /api/v1/species/<species_id>`

Deletes a global species.

### Authentication

Requires super admin.

### Rate limit

```text
10 per minute
```

### Constraint

A species cannot be deleted if it is still used by one or more `enclosure_species` records.

### Conflict response

```json
{
  "error": "Species wird noch in 3 Gehege(n) verwendet"
}
```

Status:

```text
409 Conflict
```

---

# 7. Zoo-specific species endpoints

## `GET /api/v1/zoos/<zoo>/species`

Lists species assigned to a specific zoo.

### Authentication

Requires zoo access with `read`.

### Query parameters

Implementation may support search/filter parameters depending on route version.

### Notes

This endpoint is distinct from global `/api/v1/species`. It returns the zoo-specific set of species, usually derived from `zoo.enclosure_species` joined to global `zoo.species`.

---

# 8. Enclosure species endpoints

`enclosure_species` is the central zoo-specific animal-presence object.

It represents:

```text
species + zoo-specific assignment + optional enclosure + optional house + optional map position
```

It is not the same as the global species record.

---

## `GET /api/v1/zoos/<zoo>/enclosure_species`

Lists all `enclosure_species` records for a zoo.

### Authentication

Requires zoo access with `read`.

### Rate limit

```text
60 per minute
```

### Query parameters

| Parameter | Type | Notes |
|---|---:|---|
| `enclosure_id` | integer | filter by enclosure |
| `house_id` | integer | filter by house |
| `domain_id` | integer | filter by domain |

### Returned fields

| Field |
|---|
| `id` |
| `species_id` |
| `enclosure_id` |
| `house_id` |
| `note` |
| `count_adult` |
| `count_juvenile` |
| `counted_at` |
| `domain_id` |
| `german_name` |
| `latin_name` |
| `wikidata_id` |
| `iucn_status_id` |
| `iucn_id` |
| `gbif_taxon_key` |
| `enclosure_name` |
| `enclosure_sort_order` |
| `enclosure_domain_id` |
| `house_name` |
| `house_domain_id` |
| `latitude` |
| `longitude` |
| `species_icon_path` |
| `image_path` |
| `feeding_times` |
| `births` |

---

## `GET /api/v1/zoos/<zoo>/enclosure_species/<es_id>`

Returns one `enclosure_species` record.

### Authentication

Requires zoo access with `read`.

### Rate limit

```text
60 per minute
```

---

## `POST /api/v1/zoos/<zoo>/enclosure_species`

Creates a new `enclosure_species` assignment.

### Authentication

Requires zoo access with `write`.

### Rate limit

```text
30 per minute
```

### Request body

```json
{
  "species_id": 4,
  "enclosure_id": 12,
  "house_id": null,
  "domain_id": 3,
  "note": "Visible near the main path",
  "count_adult": 2,
  "count_juvenile": 1,
  "latitude": 52.2723,
  "longitude": 8.0471,
  "feeding_times": ["14:00", "16:00"]
}
```

### Required fields

| Field | Required |
|---|:---:|
| `species_id` | yes |

### Notes

- `enclosure_id` is optional.
- `house_id` is optional.
- Coordinates are rounded by the server.
- Feeding times can be supplied as nested values.
- Related `births` may also be supported in the route implementation.

---

## `PUT /api/v1/zoos/<zoo>/enclosure_species/<es_id>`

Updates an `enclosure_species` assignment.

### Authentication

Requires zoo access with `write`.

### Rate limit

```text
30 per minute
```

### Common allowed fields

| Field |
|---|
| `enclosure_id` |
| `house_id` |
| `domain_id` |
| `note` |
| `count_adult` |
| `count_juvenile` |
| `latitude` |
| `longitude` |
| `feeding_times` |
| `births` |

Unknown fields return `400`.

---

## `DELETE /api/v1/zoos/<zoo>/enclosure_species/<es_id>`

Deletes an `enclosure_species` assignment.

### Authentication

Requires zoo access with `write`.

### Rate limit

```text
10 per minute
```

### Notes

Where supported, related historical `births` are intended to remain as historical facts, with their direct enclosure-species reference cleared rather than losing the historical record.

---

## Legacy alias: `/api/v1/zoos/<zoo>/enclosures`

The codebase also contains an older `enclosures.py` route that exposes similar `enclosure_species` CRUD operations under:

```text
/api/v1/zoos/<zoo>/enclosures
/api/v1/zoos/<zoo>/enclosures/<es_id>
```

Use `/enclosure_species` for new clients because it matches the actual data model more clearly.

---

# 9. Enclosure container endpoints

The repository contains dedicated enclosure-container routes in addition to the older `/enclosures` alias.

Enclosures are physical open-air or grouped locations. They are containers that can hold one or more `enclosure_species`.

Typical route group:

```text
/api/v1/zoos/<zoo>/enclosure
```

and/or dedicated collection routes depending on branch version.

For current integrations, prefer checking the deployed route map or using the documented `/enclosure_species` endpoint for animal-presence data.

---

# 10. Houses

A house is an indoor or covered zoo-specific container.

---

## `GET /api/v1/zoos/<zoo>/houses`

Lists houses for a zoo.

### Authentication

Requires zoo access with `read`.

### Rate limit

```text
60 per minute
```

### Returned fields

| Field |
|---|
| `id` |
| `name` |
| `description` |
| `history` |
| `sponsor` |
| `notes` |
| `domain_id` |
| `domain_name` |
| `enclosure_count` |
| `latitude` |
| `longitude` |
| `image_path` |

---

## `GET /api/v1/zoos/<zoo>/houses/<house_id>`

Returns one house with related enclosures and directly assigned species.

### Authentication

Requires zoo access with `read`.

### Response structure

```json
{
  "id": 1,
  "name": "Tropical House",
  "description": "...",
  "enclosures": [],
  "species": []
}
```

---

## `POST /api/v1/zoos/<zoo>/houses`

Creates a house.

### Authentication

Requires zoo access with `write`.

### Rate limit

```text
30 per minute
```

### Request body

```json
{
  "name": "Tropical House",
  "description": "Indoor tropical habitat",
  "history": null,
  "sponsor": null,
  "notes": null,
  "domain_id": 3,
  "latitude": 52.2723,
  "longitude": 8.0471
}
```

### Required fields

| Field | Required |
|---|:---:|
| `name` | yes |

---

## `PUT /api/v1/zoos/<zoo>/houses/<house_id>`

Updates a house.

### Authentication

Requires zoo access with `write`.

### Allowed fields

| Field |
|---|
| `name` |
| `description` |
| `history` |
| `sponsor` |
| `notes` |
| `domain_id` |
| `latitude` |
| `longitude` |

---

## `DELETE /api/v1/zoos/<zoo>/houses/<house_id>`

Deletes a house.

### Authentication

Requires zoo access with `write`.

### Rate limit

```text
10 per minute
```

---

# 11. Domains

Domains group zoo content, map areas or infrastructure categories.

---

## `GET /api/v1/zoos/<zoo>/domains`

Lists global and zoo-specific domains.

### Authentication

Requires zoo access with `read`.

### Rate limit

```text
60 per minute
```

### Returned fields

| Field |
|---|
| `id` |
| `name` |
| `is_infrastructure` |
| `sort_order` |
| `color_red` |
| `color_green` |
| `color_blue` |
| `color_alpha` |
| `zoo_id` |

---

## `GET /api/v1/zoos/<zoo>/domains/<domain_id>`

Returns one domain.

### Authentication

Requires zoo access with `read`.

---

## `POST /api/v1/zoos/<zoo>/domains`

Creates a zoo-specific domain.

### Authentication

Requires zoo access with `write`.

### Request body

```json
{
  "name": "Mammals",
  "is_infrastructure": false,
  "sort_order": 10,
  "color_red": 128,
  "color_green": 128,
  "color_blue": 128,
  "color_alpha": 1.0
}
```

### Required fields

| Field | Required |
|---|:---:|
| `name` | yes |

---

## `PUT /api/v1/zoos/<zoo>/domains/<domain_id>`

Updates a zoo-specific domain.

### Authentication

Requires zoo access with `write`.

### Allowed fields

| Field |
|---|
| `name` |
| `is_infrastructure` |
| `sort_order` |
| `color_red` |
| `color_green` |
| `color_blue` |
| `color_alpha` |

---

## `DELETE /api/v1/zoos/<zoo>/domains/<domain_id>`

Deletes a zoo-specific domain.

### Authentication

Requires zoo access with `write`.

---

# 12. Locations and location types

Locations are infrastructure POIs such as toilets, shops, playgrounds, restaurants or service points.

---

## `GET /api/v1/location-types`

Lists all location types.

### Authentication

Requires authenticated user.

### Rate limit

```text
60 per minute
```

### Returned fields

| Field |
|---|
| `id` |
| `slug` |
| `name` |
| `icon` |
| `sort_order` |

---

## `GET /api/v1/location-types/<type_id>`

Returns one location type.

### Authentication

Requires authenticated user.

---

## `POST /api/v1/location-types`

Creates a location type.

### Authentication

Requires super admin.

### Request body

```json
{
  "slug": "toilet",
  "name": "Toilet",
  "icon": "toilet",
  "sort_order": 10
}
```

### Required fields

| Field | Required |
|---|:---:|
| `slug` | yes |
| `name` | yes |

---

## `PUT /api/v1/location-types/<type_id>`

Updates a location type.

### Authentication

Requires super admin.

### Allowed fields

| Field |
|---|
| `slug` |
| `name` |
| `icon` |
| `sort_order` |

---

## `DELETE /api/v1/location-types/<type_id>`

Deletes a location type.

### Authentication

Requires super admin.

### Constraint

Deletion fails when locations still use the type.

---

## Zoo location endpoints

The codebase contains a dedicated `locations.py` blueprint under `source/routes/zoo_routes/`.

Typical route group:

```text
/api/v1/zoos/<zoo>/locations
/api/v1/zoos/<zoo>/locations/<location_id>
```

Expected behavior follows the same pattern:

| Method | Purpose | Permission |
|---|---|---|
| `GET` collection | list POIs | `read` |
| `GET` item | read one POI | `read` |
| `POST` | create POI | `write` |
| `PUT` | update POI | `write` |
| `DELETE` | delete POI | `write` |

---

# 13. Feeding times

Feeding times are attached to `enclosure_species`, not directly to global species.

---

## `GET /api/v1/zoos/<zoo>/feeding_times`

Lists all feeding times in a zoo.

### Authentication

Requires zoo access with `read`.

### Rate limit

```text
60 per minute
```

### Query parameters

| Parameter | Type | Notes |
|---|---:|---|
| `species_id` | integer | optional filter |

### Returned fields

| Field |
|---|
| `id` |
| `enclosure_species_id` |
| `feeding_time` |
| `day_of_week` |
| `note` |
| `is_public` |
| `species_id` |
| `german_name` |
| `latin_name` |
| `enclosure_name` |
| `house_name` |

---

## `GET /api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times`

Lists feeding times for one `enclosure_species`.

### Authentication

Requires zoo access with `read`.

---

## `GET /api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times/<ft_id>`

Returns one feeding time.

### Authentication

Requires zoo access with `read`.

---

## `POST /api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times`

Creates a feeding time.

### Authentication

Requires zoo access with `write`.

### Request body

```json
{
  "feeding_time": "14:00",
  "day_of_week": null,
  "note": "Public feeding",
  "is_public": true
}
```

### Required fields

| Field | Required |
|---|:---:|
| `feeding_time` | yes |

### Notes

`day_of_week` is optional. In this route, it is stored as supplied by the client.

---

## `PUT /api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times/<ft_id>`

Updates a feeding time.

### Authentication

Requires zoo access with `write`.

### Allowed fields

| Field |
|---|
| `feeding_time` |
| `day_of_week` |
| `note` |
| `is_public` |

---

## `DELETE /api/v1/zoos/<zoo>/enclosure_species/<es_id>/feeding_times/<ft_id>`

Deletes a feeding time.

### Authentication

Requires zoo access with `write`.

---

# 14. Births

Birth records are attached to `enclosure_species`, but they also store `species_id` and `zoo_id` server-side for historical querying.

---

## `GET /api/v1/zoos/<zoo>/births`

Lists all births in a zoo.

### Authentication

Requires zoo access with `read`.

### Rate limit

```text
60 per minute
```

### Query parameters

| Parameter | Type | Notes |
|---|---:|---|
| `species_id` | integer | optional filter |

### Returned fields

| Field |
|---|
| `id` |
| `enclosure_species_id` |
| `species_id` |
| `zoo_id` |
| `birth_date` |
| `count` |
| `note` |
| `is_public` |
| `german_name` |
| `latin_name` |
| `enclosure_name` |
| `house_name` |

---

## `GET /api/v1/zoos/<zoo>/enclosure_species/<es_id>/births`

Lists births for one `enclosure_species`.

### Authentication

Requires zoo access with `read`.

---

## `GET /api/v1/zoos/<zoo>/enclosure_species/<es_id>/births/<birth_id>`

Returns one birth record.

### Authentication

Requires zoo access with `read`.

---

## `POST /api/v1/zoos/<zoo>/enclosure_species/<es_id>/births`

Creates a birth record.

### Authentication

Requires zoo access with `write`.

### Request body

```json
{
  "birth_date": "2026-06-26",
  "count": 1,
  "note": "First visible in public enclosure",
  "is_public": true
}
```

### Required fields

| Field | Required |
|---|:---:|
| `birth_date` | yes |

### Server-derived fields

The server derives these from `enclosure_species`:

| Field |
|---|
| `species_id` |
| `zoo_id` |

---

## `PUT /api/v1/zoos/<zoo>/enclosure_species/<es_id>/births/<birth_id>`

Updates a birth record.

### Authentication

Requires zoo access with `write`.

### Allowed fields

| Field |
|---|
| `birth_date` |
| `count` |
| `note` |
| `is_public` |

The route rejects unknown fields, including direct changes to `species_id`, `zoo_id` or `enclosure_species_id`.

---

## `DELETE /api/v1/zoos/<zoo>/enclosure_species/<es_id>/births/<birth_id>`

Deletes a birth record.

### Authentication

Requires zoo access with `write`.

### Notes

This is a direct delete for correcting a wrong birth entry. It is distinct from deleting an `enclosure_species` assignment, where births can be preserved as historical records.

---

# 15. Opening hours

OpenZooData has separate opening-hour tables for:

| Scope | Route prefix | Table |
|---|---|---|
| Zoo | `/api/v1/zoos/<zoo>/opening_hours` | `zoo.zoo_opening_hours` |
| Location | `/api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours` | `zoo.opening_hours` |
| House | `/api/v1/zoos/<zoo>/houses/<house_id>/opening_hours` | `zoo.house_opening_hours` |

---

## Shared opening-hour fields

| Field | Type | Notes |
|---|---|---|
| `day_of_week` | string or null | one of `monday` … `sunday`, or null for daily |
| `open_time` | string | `HH:MM` |
| `close_time` | string | `HH:MM` |
| `valid_from` | string or null | `YYYY-MM-DD` |
| `valid_until` | string or null | `YYYY-MM-DD` |
| `label` | string or null | e.g. summer season |

Valid `day_of_week` values:

```text
monday
tuesday
wednesday
thursday
friday
saturday
sunday
```

---

## Zoo opening hours

### Routes

| Method | Path | Permission |
|---|---|---|
| `GET` | `/api/v1/zoos/<zoo>/opening_hours` | `read` |
| `GET` | `/api/v1/zoos/<zoo>/opening_hours/<oh_id>` | `read` |
| `POST` | `/api/v1/zoos/<zoo>/opening_hours` | `write` |
| `PUT` | `/api/v1/zoos/<zoo>/opening_hours/<oh_id>` | `write` |
| `DELETE` | `/api/v1/zoos/<zoo>/opening_hours/<oh_id>` | `write` |

### Create request body

```json
{
  "day_of_week": "monday",
  "open_time": "09:00",
  "close_time": "18:00",
  "valid_from": "2026-04-01",
  "valid_until": "2026-10-31",
  "label": "Summer season"
}
```

---

## Location opening hours

### Routes

| Method | Path | Permission |
|---|---|---|
| `GET` | `/api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours` | `read` |
| `GET` | `/api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours/<oh_id>` | `read` |
| `POST` | `/api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours` | `write` |
| `PUT` | `/api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours/<oh_id>` | `write` |
| `DELETE` | `/api/v1/zoos/<zoo>/locations/<loc_id>/opening_hours/<oh_id>` | `write` |

---

## House opening hours

### Routes

| Method | Path | Permission |
|---|---|---|
| `GET` | `/api/v1/zoos/<zoo>/houses/<house_id>/opening_hours` | `read` |
| `GET` | `/api/v1/zoos/<zoo>/houses/<house_id>/opening_hours/<oh_id>` | `read` |
| `POST` | `/api/v1/zoos/<zoo>/houses/<house_id>/opening_hours` | `write` |
| `PUT` | `/api/v1/zoos/<zoo>/houses/<house_id>/opening_hours/<oh_id>` | `write` |
| `DELETE` | `/api/v1/zoos/<zoo>/houses/<house_id>/opening_hours/<oh_id>` | `write` |

---

# 16. Feedback API

The feedback API is intended for community/user feedback from app clients and review workflows by zoo admins.

---

## `GET /api/v1/feedback-types`

Lists active feedback types and report reasons.

### Authentication

Requires app token.

### Rate limit

```text
30 per minute
```

### Response

```json
[
  {
    "id": 1,
    "slug": "feeding_time_correction",
    "label_de": "Fütterungszeit korrigieren",
    "entity_type": "enclosure_species",
    "requires_admin_review": true,
    "report_reasons": []
  }
]
```

### Cache

The route sets:

```http
Cache-Control: public, max-age=3600
```

---

## `POST /api/v1/zoos/<zoo>/feedback`

Creates feedback from an app client.

### Authentication

Requires app token.

### Rate limits

```text
60 per minute
2 per minute per token
60 per day per token
```

### Request body

Base fields:

```json
{
  "feedback_type_id": 1,
  "contributor_id": "anonymous-client-uuid"
}
```

Additional fields depend on `feedback_type_id`.

### Feedback value fields

| Field | Purpose |
|---|---|
| `enclosure_species_id` | target animal-presence record |
| `value_time` | proposed time |
| `value_latitude` | proposed latitude |
| `value_longitude` | proposed longitude |
| `value_wikidata_id` | proposed Wikidata ID |
| `value_species_id` | proposed species |
| `value_date` | proposed date |
| `value_count` | proposed count |
| `value_enrichment_text_id` | text item reference |
| `value_report_reason_id` | report reason |
| `value_language` | language code |

### Success response

```json
{
  "id": 123,
  "status": "pending",
  "created_at": "2026-06-26T12:00:00+00:00"
}
```

Status:

```text
201 Created
```

### Conflict response

```json
{
  "error": "Already rated"
}
```

---

## `GET /api/v1/zoos/<zoo>/feedback`

Lists clustered feedback for admin review.

### Authentication

Requires zoo access with `admin`.

### Rate limit

```text
60 per minute
```

### Query parameters

| Parameter | Type | Default | Notes |
|---|---:|---:|---|
| `status` | string | `pending` | `pending`, `accepted`, `rejected` |
| `limit` | integer | `50` | max `200` |
| `offset` | integer | `0` | pagination offset |

### Response

```json
{
  "total": 3,
  "clusters": [
    {
      "feedback_ids": [1, 2],
      "feedback_type_id": 1,
      "feedback_type_slug": "feeding_time_correction",
      "reporter_count": 2,
      "first_reported": "2026-06-26T12:00:00",
      "last_reported": "2026-06-26T12:05:00"
    }
  ]
}
```

---

## `GET /api/v1/zoos/<zoo>/feedback/<feedback_id>`

Returns one feedback item.

### Authentication

Requires zoo access with `admin`.

---

## `PUT /api/v1/zoos/<zoo>/feedback/<feedback_id>/accept`

Marks one or more feedback items as accepted.

### Authentication

Requires zoo access with `admin`.

### Rate limit

```text
30 per minute
```

### Request body

```json
{
  "comment": "Verified by zoo staff",
  "also_ids": [124, 125]
}
```

### Success response

```json
{
  "message": "Accepted",
  "updated_count": 3
}
```

---

## `PUT /api/v1/zoos/<zoo>/feedback/<feedback_id>/reject`

Marks one or more feedback items as rejected.

### Authentication

Requires zoo access with `admin`.

### Request body

```json
{
  "comment": "Incorrect report",
  "also_ids": [124, 125]
}
```

### Success response

```json
{
  "message": "Rejected",
  "updated_count": 3
}
```

---

# 17. Media API

The codebase registers `media_bp` and `media_bundle_bp`.

---

## Media routes

Media endpoints handle file upload/download and media records for zoo entities.

The route implementation is in:

```text
source/routes/media.py
```

The server configuration sets:

```text
MAX_CONTENT_LENGTH = 12 MB
```

SVG upload is intentionally excluded in the media route comments for security reasons.

Expected behavior:

| Method | Purpose | Permission |
|---|---|---|
| `GET` | serve media file | read or public depending on endpoint |
| `POST` | upload media | zoo write access |
| `DELETE` | delete media | zoo write access |

---

## `GET /media-bundle/<zoo>` or equivalent media bundle route

The app registers `media_bundle_bp`.

The media bundle route is intended to support offline/client synchronization of media metadata and assets.

Recommended documentation after route verification:

| Field | Meaning |
|---|---|
| `url` | bundle or file URL |
| `etag` | media version / cache validator |
| `zoo` | zoo slug |

---

# 18. QR routes

The app registers `qr_bp`.

The QR route is used by the QR-code helper page and/or zoo-feed subscription workflow.

Implementation file:

```text
source/routes/qr.py
```

Recommended integration target:

```text
html/zoo-qr-codes.html
```

---

# 19. Admin API

The admin API is split into several blueprints under:

```text
source/routes/admin_routes/
```

Registered admin blueprints:

| Blueprint file | Purpose |
|---|---|
| `zoos.py` | admin zoo management |
| `tenants.py` | tenant management |
| `users.py` | user management |
| `roles.py` | role assignment |
| `system.py` | system settings |
| `fixtures.py` | test fixtures |

All admin endpoints require administrative JWT-based authorization.

---

## Common admin concepts

### User roles

The codebase uses role concepts such as:

| Role | Scope |
|---|---|
| `super_admin` | global |
| `tenant_admin` | tenant |
| `zoo_admin` | zoo |
| `zoo_viewer` | zoo |
| `moderator` | zoo / moderation |
| editor/write roles | zoo editing workflows |

### Tenant model

Tenants group users and zoos.

A zoo can be assigned to a tenant. Tenant admins can manage data within the permitted tenant/zoo scope.

### Settings hierarchy

The code uses settings with a hierarchy similar to:

```text
zoo setting → tenant setting → global setting → default
```

This is visible in the publish error notification setting.

---

## `source/routes/admin_routes/fixtures.py`

The fixtures blueprint is intended for tests, especially RBAC fixtures.

Typical endpoint:

```text
/api/v1/admin/test-fixtures/rbac
```

This endpoint should not be enabled or exposed in production unless explicitly intended.

---

# 20. Security headers and global error handling

The Flask app sets these security headers after each request:

| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |

Unhandled exceptions are logged and returned as:

```json
{
  "error": "Internal server error"
}
```

HTTP status:

```text
500 Internal Server Error
```

---

# 21. Recommended curl examples

## Login

```bash
BASE="https://api.openzoodata.org"

curl -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.org",
    "password": "YourPassword123!"
  }'
```

---

## Store JWT

```bash
TOKEN="paste-access-token-here"
```

---

## List zoos

```bash
curl "$BASE/api/v1/zoos" \
  -H "Authorization: Bearer $TOKEN"
```

---

## List zoo species

```bash
curl "$BASE/api/v1/zoos/zoo_osnabrueck/enclosure_species" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Register app installation

```bash
curl -X POST "$BASE/api/v1/auth/app_register" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

---

## Download SQLite bundle

```bash
APP_TOKEN="paste-app-token-here"

curl -L "$BASE/db/zoo_osnabrueck" \
  -H "Authorization: Bearer $APP_TOKEN" \
  -o zoo_osnabrueck.sqlite.gz
```

---

## Submit feedback

```bash
curl -X POST "$BASE/api/v1/zoos/zoo_osnabrueck/feedback" \
  -H "Authorization: Bearer $APP_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "feedback_type_id": 1,
    "contributor_id": "anonymous-client-uuid",
    "enclosure_species_id": 123,
    "value_time": "14:00"
  }'
```

---

# 22. Integration notes for official repository

Recommended file path:

```text
docs/api_detail.md
```

Recommended README link:

```markdown
- [Detailed API Reference](docs/api_detail.md)
```

Recommended follow-up improvements:

- Generate an OpenAPI specification from the Flask route map.
- Add route-level examples from a seeded demo database.
- Add test-backed request/response examples.
- Add authentication examples for each role.
- Add a table that maps each endpoint to its source file and pytest coverage.
- Add public vs. protected endpoint classification.
- Add production deployment notes for reverse proxy path handling.
