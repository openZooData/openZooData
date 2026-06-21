# RSS Feed System

OpenZooData includes a public RSS-based feed infrastructure.

## Goals

The feed system is intended to support:

- public zoo discovery
- synchronization
- federation
- update notifications
- mirroring
- decentralized infrastructure

## Endpoints

| Endpoint | Description |
|---|---|
| /feed | List available zoo feeds |
| /feed/<zoo> | Zoo-specific RSS feed |

## Feed Format

Current implementation:

- RSS 2.0
- custom zoo namespace
- SQLite export references
- changelog support
- data versioning
- CORS-enabled (both endpoints are public and unauthenticated, and can be
  fetched directly from a browser context — e.g. third-party feed readers
  or dashboards)

## Long-Term Vision

The feed system is planned to become the foundation for:

- federated zoo servers
- public mirrors
- automated synchronization
- open ecosystem discovery
