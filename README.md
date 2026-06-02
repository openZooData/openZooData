# OpenZooData

![License](https://img.shields.io/badge/Code-AGPL--3.0-blue.svg)
![Data](https://img.shields.io/badge/Data-ODbL--1.0-green.svg)
![Docs](https://img.shields.io/badge/Docs-CC%20BY--SA%204.0-orange.svg)
![Powered by Wikidata](https://img.shields.io/badge/Powered%20by-Wikidata-006699.svg)

![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)  ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-required-blue.svg)

![Status](https://img.shields.io/badge/Status-Alpha-orange.svg)

Open infrastructure for zoo, animal, enclosure and visitor data.

Species are linked to Wikidata identifiers to provide stable,
multilingual and interoperable references across the open-data ecosystem.

➡️ See [Wikidata Integration](docs/wikidata.md)

## What is OpenZooData?

OpenZooData provides a self-hostable server platform for zoos to publish
structured data — species, enclosures, feeding times, maps — in open,
standardized formats. Data is distributed via RSS feeds and offline-capable
SQLite exports, designed for mobile-first and federated use.

## Prerequisites

Two PostgreSQL databases are required:

| Database | Default name | Purpose |
|---|---|---|
| Zoo database | `openZooData` | Species, enclosures, zoo data |
| Auth database | `openZooData_auth` | Users, tokens, roles |

Create them before starting the server:

```sql
CREATE DATABASE "openZooData";
CREATE DATABASE "openZooData_auth";
```

Then apply the schemas:

```bash
psql -d openZooData -f source/schema/zoo_schema.sql
psql -d openZooData_auth -f source/schema/auth_schema.sql
```

## Quick Start

```bash
git clone https://github.com/openZooData/openZooData
cd openZooData/source
cp env.example .env
# fill in .env — set PG_NAME=openZooData and AUTH_NAME=openZooData_auth
pip install -r requirements.txt
python app.py
```

## Key Endpoints

| Endpoint | Description |
|---|---|
| `/feed` | Zoo discovery feed (RSS) |
| `/feed/<zoo>` | Zoo-specific RSS feed |
| `/db/<zoo>` | SQLite export download |
| `/api/v1/species` | Species data |
| `/api/v1/zoos/<zoo>/enclosures` | Enclosure data |
| `/status` | Health check |

## Components

**Open Source (this repository)**
- Flask API server
- PostgreSQL schema
- RSS feed infrastructure
- SQLite export tooling
- Wikidata synchronization tools
- Community feedback system

**Proprietary (not included)**
- ZooGuide iOS App
- ZooCreator
- Analytics dashboards

## Licensing

| Component | License |
|---|---|
| Server Software | AGPLv3 |
| Zoo & Species Data | ODbL 1.0 |
| Documentation | CC BY-SA 4.0 |
| Name & Logos | Trademark Protected |

See [DATA_LICENSE.md](DATA_LICENSE.md) for full details including
interoperability requirements.

## Core Principles

- Open infrastructure
- Publicly accessible data
- Federation instead of vendor lock-in
- Reusable APIs and feeds
- Compatibility with Wikidata and Open Data ecosystems
- Separation of open infrastructure and proprietary client applications

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md) — report vulnerabilities to thorsten@codelab.cafe.
