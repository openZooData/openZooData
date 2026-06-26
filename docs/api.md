# OpenZooData API

> REST endpoints and example calls.

This document provides a high-level overview of the OpenZooData API.

For a detailed API overvierw please refer to 
[Detailed API Reference](docs/api_detail.md)

The API is split into:

- public read endpoints,
- feed and export endpoints,
- authenticated write endpoints,
- administrative endpoints.

---

## Base URL

Local development:

```text
http://127.0.0.1:5001
```

Public demo example:

```text
https://api.openzoodata.org
```

---

## Public Endpoints

### Health Check

```http
GET /status
```

Example:

```bash
curl https://api.openzoodata.org/status
```

Expected response:

```json
{
  "status": "ok"
}
```

---

### Network Feed

```http
GET /feed
```

Returns an RSS-style discovery feed for published zoo datasets.

```bash
curl https://api.openzoodata.org/feed
```

---

### Zoo-Specific Feed

```http
GET /feed/{zoo}
```

Example:

```bash
curl https://api.openzoodata.org/feed/zoo_osnabrueck
```

---

### SQLite Export

```http
GET /db/{zoo}
```

Example:

```bash
curl -O https://api.openzoodata.org/db/zoo_osnabrueck
```

---

## Species Endpoints

### Global Species

```http
GET /api/v1/species
```

Example:

```bash
curl https://api.openzoodata.org/api/v1/species
```

### Zoo Species

```http
GET /api/v1/zoos/{zoo}/species
```

Example:

```bash
curl https://api.openzoodata.org/api/v1/zoos/zoo_osnabrueck/species
```

### Search Species

If supported by the deployed version:

```bash
curl "https://api.openzoodata.org/api/v1/zoos/zoo_osnabrueck/species?search=Elefant"
```

---

## Zoo Endpoints

### List Zoos

```http
GET /api/v1/zoos
```

Example:

```bash
curl https://api.openzoodata.org/api/v1/zoos
```

---

## Enclosure Endpoints

### List Enclosures

```http
GET /api/v1/zoos/{zoo}/enclosures
```

Example:

```bash
curl https://api.openzoodata.org/api/v1/zoos/zoo_osnabrueck/enclosures
```

### Species Assignments

```http
GET /api/v1/zoos/{zoo}/enclosure_species
```

Example:

```bash
curl https://api.openzoodata.org/api/v1/zoos/zoo_osnabrueck/enclosure_species
```

---

## Birth Records

```http
GET /api/v1/zoos/{zoo}/births
```

Example:

```bash
curl https://api.openzoodata.org/api/v1/zoos/zoo_osnabrueck/births
```

---

## Feeding Times

```http
GET /api/v1/zoos/{zoo}/feeding_times
```

Example:

```bash
curl https://api.openzoodata.org/api/v1/zoos/zoo_osnabrueck/feeding_times
```

---

## Authentication

Protected endpoints require JWT authentication.

Typical request pattern:

```bash
curl https://api.openzoodata.org/api/v1/admin/zoos \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

## Admin Endpoints

Admin endpoints are intended for authenticated users with sufficient roles.

Examples:

| Endpoint | Purpose |
|---|---|
| `/api/v1/admin/zoos` | Zoo management |
| `/api/v1/admin/users` | User management |
| `/api/v1/admin/tenants` | Tenant management |
| `/api/v1/admin/test-fixtures/rbac` | Test fixture setup, if enabled |

These endpoints should not be exposed without authentication and authorization.

---

## Response Design Principles

API responses should be:

- JSON-based,
- stable within an API version,
- explicit about identifiers,
- clear about source zoo,
- clear about Wikidata and GBIF identifiers,
- suitable for mobile clients,
- suitable for dataset aggregation.

---

## Example Species Response

Illustrative example:

```json
{
  "id": 4,
  "wikidata_id": "Q140",
  "latin_name": "Panthera leo",
  "german_name": "Löwe",
  "gbif_taxon_key": 5219404,
  "iucn_status": "VU",
  "population_trend": "decreasing",
  "icon_path": "/media/species/Q140_Panthera_leo.png"
}
```

---

## API Versioning

Current endpoints are under:

```text
/api/v1/
```

Future versions should preserve backward compatibility where possible.

Recommended policy:

- breaking changes require a new API version,
- deprecated fields should remain available during transition,
- clients should not depend on undocumented fields,
- stable identifiers should remain stable.

---

## Error Handling

Recommended error shape:

```json
{
  "error": "Unauthorized"
}
```

Common status codes:

| Code | Meaning |
|---|---|
| `200` | Success |
| `400` | Invalid request |
| `401` | Missing or invalid authentication |
| `403` | Authenticated but not authorized |
| `404` | Not found |
| `429` | Rate limited |
| `500` | Server error |

---

## Notes for Evaluators

For challenge evaluation, prefer public read endpoints first:

```bash
curl https://api.openzoodata.org/status
curl https://api.openzoodata.org/feed
curl https://api.openzoodata.org/api/v1/zoos
curl https://api.openzoodata.org/api/v1/species
```

Authenticated write and admin endpoints require credentials.
