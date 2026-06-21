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

➡️ See [Wikidata Integration](docs/wikidata_integration.md)

---

## What is OpenZooData?

OpenZooData provides a self-hostable server platform for zoos to publish
structured data — species, enclosures, feeding times, maps — in open,
standardized formats. Data is distributed via RSS feeds and offline-capable
SQLite exports, designed for mobile-first and federated use.

---

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

---

## Quick Start

```bash
git clone https://github.com/openZooData/openZooData
cd openZooData/source
cp env.example .env
# fill in .env — set PG_NAME=openZooData and AUTH_NAME=openZooData_auth
pip install -r requirements.txt
python app.py
```

### First Super-Admin

After starting the server for the first time, create the initial super_admin
user directly in the auth database:

```bash
# Generate a bcrypt password hash
python3 -c "import bcrypt; print(bcrypt.hashpw('YourPassword123!'.encode(), bcrypt.gensalt()).decode())"
```

```sql
-- In the auth database:
BEGIN;
INSERT INTO auth.users (email, password_hash, is_active, must_change_password)
VALUES ('your@email.com', '$2b$12$...hash...', TRUE, FALSE)
RETURNING id;

INSERT INTO auth.user_global_roles (user_id, role)
VALUES (<id>, 'super_admin');
COMMIT;
```

---

## Key Endpoints

| Endpoint | Description |
|---|---|
| `/feed` | Zoo discovery feed (RSS) |
| `/feed/<zoo>` | Zoo-specific RSS feed |
| `/db/<zoo>` | SQLite export download |
| `/api/v1/species` | Species data |
| `/api/v1/zoos/<zoo>/enclosures` | Enclosure data |
| `/api/v1/zoos/<zoo>/enclosure_species` | Species-in-enclosure links (feeding times, births, GPS, photos) |
| `/api/v1/admin/zoos` | Admin: zoo management |
| `/api/v1/admin/users` | Admin: user management |
| `/status` | Health check |

---

## Repository Structure

```
openZooData/
├── .github/
│   └── workflows/
│       └── test.yml          ← GitHub Actions (static checks + live smoke)
├── source/                   ← Server code (deployed)
│   ├── app.py
│   ├── routes/
│   ├── helpers/
│   ├── schema/
│   └── ...
├── tests/                    ← API test suite
│   ├── .env                  ← NOT in Git (create from .env.example)
│   ├── .env.example
│   ├── conftest.py
│   ├── pytest.ini
│   ├── requirements-dev.txt
│   ├── test_api.py
│   ├── test_enclosure_species.py
│   ├── test_feed.py
│   ├── test_feedback_api.py
│   ├── test_rbac.py
│   ├── test_security.py
│   └── test_z_cleanup.py
├── docs/
├── .gitignore
└── README.md
```

---

## Running the Tests

### Setup

```bash
cp tests/.env.example tests/.env
# Fill in tests/.env with real values
pip install -r tests/requirements-dev.txt
```

### Safe Smoke Tests (no side effects, no auth required)

```bash
pytest tests/ -v -m "not slow and not write and not feedback and not requires_data and not media and not jwt"
```

### All tests except slow rate-limit tests

```bash
pytest tests/ -v -m "not slow"
```

### Security tests only

```bash
pytest tests/test_security.py -v
```

### Full run including cleanup (requires test data)

```bash
pytest tests/ -v
```

### Test Markers

| Marker | Meaning | Runs automatically |
|---|---|---|
| *(none)* | Fast, read-only, no auth | ✅ always |
| `jwt` | Requires JWT login | ❌ manual only |
| `write` | Writes data to the server | ❌ manual only |
| `media` | Media upload/download | ❌ manual only |
| `feedback` | Feedback system tests | ❌ manual only |
| `requires_data` | Requires SQLite/feed data | ❌ manual only |
| `slow` | Contains sleeps or long exports | ❌ manual only |
| `rbac` | RBAC and tenant isolation tests | ❌ manual only |
| `security` | Security-specific tests | ✅ in smoke run |

### CI/CD

| Trigger | What runs |
|---|---|
| `git push` / PR | Static checks: syntax + collection (no live API) |
| `git pull` on server | Safe smoke via post-merge hook |
| `workflow_dispatch` | Live API smoke against deployed server |

---

## Components

**Open Source (this repository)**
- Flask API server
- PostgreSQL schema
- RSS feed infrastructure
- SQLite export tooling
- Wikidata synchronization tools
- Community feedback system
- Admin endpoints (zoo, tenant, user management)

**Proprietary (not included)**
- ZooGuide iOS App
- ZooCreator
- Analytics dashboards

---

## Licensing

| Component | License |
|---|---|
| Server Software | AGPLv3 |
| Zoo & Species Data | ODbL 1.0 |
| Documentation | CC BY-SA 4.0 |
| Name & Logos | Trademark Protected |

See [DATA_LICENSE.md](DATA_LICENSE.md) for full details including
interoperability requirements.

---

## Core Principles

- Open infrastructure
- Publicly accessible data
- Federation instead of vendor lock-in
- Reusable APIs and feeds
- Compatibility with Wikidata and Open Data ecosystems
- Separation of open infrastructure and proprietary client applications

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md) — report vulnerabilities to thorsten@codelab.cafe.
