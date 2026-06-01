# API Overview

## Base Endpoints

| Endpoint | Description |
|---|---|
| /status | Health endpoint |
| /api/v1/species | Species search and management |
| /api/v1/zoos/<zoo>/enclosures | Enclosure data |
| /db/<zoo> | SQLite export download |
| /feed/<zoo> | Public RSS feed |


## Authentication Modes

### JWT Authentication

Used for:
- administrative APIs
- write operations
- protected data management

Roles:
- super_admin
- zoo_admin

### App Tokens

Used for:
- mobile app authentication
- SQLite downloads
- feedback systems
- public client services

App tokens are device-based and anonymous.

## Rate Limiting

The API uses flask-limiter for endpoint protection.

Typical limits:

- 60 requests/minute for reads
- 10–30 requests/minute for writes

## Error Handling

Standard JSON error responses:

```json
{
  "error": "description"
}
```
