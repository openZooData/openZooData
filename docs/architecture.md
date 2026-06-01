# Architecture Overview

## Technology Stack

| Component | Technology |
|---|---|
| API Framework | Flask |
| Rate Limiting | flask-limiter |
| Main Database | PostgreSQL |
| Authentication | JWT + App Tokens |
| Reverse Proxy | nginx / Apache |
| Export Format | SQLite (.sqlite.gz) |
| Open Feed Format | RSS 2.0 |

## High-Level Architecture

The OpenZooData server is implemented as a modular Flask application
using Blueprints for functional separation.

The platform currently consists of:

- Public zoo APIs
- Species APIs
- Enclosure APIs
- Authentication services
- SQLite export services
- RSS/Manifest feeds
- Media and feedback routes
- Wikidata synchronization tooling

## Blueprint Structure

| Blueprint | Purpose |
|---|---|
| auth_bp | JWT authentication |
| app_auth_bp | Device/app authentication |
| species_bp | Species endpoints |
| enclosures_bp | Enclosure endpoints |
| domains_bp | Domain/category endpoints |
| sqlite_bp | SQLite export delivery |
| publish_bp | Publishing/export functionality |
| media_bp | Media delivery |
| feedback_bp | Visitor feedback |
| feed_bp | Public RSS feed infrastructure |

## Database Separation

The system uses two PostgreSQL databases:

### Zoo Database

Main structured zoo data:

- zoos
- species
- enclosures
- geo_points
- feeding_times
- translations
- domains

### Auth Database

Separate PostgreSQL authentication database:

- users
- roles
- refresh tokens
- app tokens

## Deployment Philosophy

The architecture is designed for:

- Separation of public and private services
- Open data distribution
- Offline-capable clients
- Future federation support
- Community interoperability
