# SQLite Export System

OpenZooData supports offline-capable SQLite exports for mobile clients.

## Endpoint

GET /db/<zoo>

## Features

- gzip-compressed SQLite delivery
- ETag support
- version-based caching
- offline synchronization
- app-token authentication

## Client Workflow

1. Client authenticates using app token
2. Client downloads zoo SQLite export
3. ETag is compared against current data_version
4. 304 Not Modified supported

## Goal

The export system is designed to:

- minimize bandwidth usage
- support offline operation
- allow mobile-first architectures
- simplify synchronization
