# Roadmap

> Development status and future direction.

OpenZooData is currently in alpha. The core concept is implemented, but the project is still evolving toward a stable self-hosted open infrastructure platform.

---

## Guiding Vision

OpenZooData aims to become the open publishing infrastructure for zoological biodiversity data.

The project should enable zoos to:

- publish selected biodiversity data openly,
- remain the authoritative owner of their own data,
- connect species records to GBIF and Wikidata,
- provide offline data bundles for visitor and research applications,
- participate in a federated biodiversity data network.

---

## Implemented

### Server Infrastructure

- [x] Flask API server
- [x] PostgreSQL-backed zoo database
- [x] Separate auth database
- [x] Environment-based configuration
- [x] Gunicorn-compatible deployment
- [x] Health check endpoint
- [x] Detailed health check endpoint

### Data Model

- [x] Zoos
- [x] Species
- [x] Enclosures
- [x] Houses
- [x] Enclosure-species assignments
- [x] Geo points
- [x] Feeding times
- [x] Birth records
- [x] Translations
- [x] Media records

### Publishing

- [x] REST API
- [x] RSS discovery feed
- [x] Zoo-specific feed
- [x] SQLite export
- [x] Public read endpoints

### Biodiversity Integration

- [x] Wikidata identifiers
- [x] GBIF taxon key support
- [x] Taxonomic enrichment workflow
- [x] Species media enrichment
- [x] Conservation status fields

### Security and Administration

- [x] JWT authentication
- [x] Role-based access control
- [x] Multi-tenant structure
- [x] Super admin role
- [x] Tenant admin role
- [x] Zoo admin role
- [x] Viewer role
- [x] Moderator role
- [x] Security tests

### Testing

- [x] API tests
- [x] Feed tests
- [x] Security tests
- [x] RBAC tests
- [x] CI workflow
- [x] Smoke tests

---

## In Progress

- [ ] Improved README and challenge documentation
- [ ] Architecture documentation
- [ ] Federation documentation
- [ ] GBIF integration documentation
- [ ] Public demo endpoint documentation
- [ ] Screenshot-based repository presentation
- [ ] Translation enrichment workflow
- [ ] Better setup instructions
- [ ] More stable local development setup
- [ ] Public API example responses

---

## Planned

### Deployment

- [ ] Dockerfile
- [ ] Docker Compose setup
- [ ] Production deployment guide
- [ ] systemd service example
- [ ] backup and restore guide
- [ ] monitoring guide

### Biodiversity Data

- [ ] Darwin Core Archive export
- [ ] dataset metadata
- [ ] ex-situ presence modeling
- [ ] GBIF-compatible publication strategy
- [ ] taxonomic validation reports
- [ ] improved species matching workflow

### Federation

- [ ] public registry of OpenZooData nodes
- [ ] feed validator
- [ ] dataset versioning
- [ ] federation status dashboard
- [ ] signed feed metadata
- [ ] aggregator reference implementation

### API

- [ ] stable API versioning policy
- [ ] OpenAPI specification
- [ ] generated API documentation
- [ ] pagination policy
- [ ] standardized error format
- [ ] stronger public read/write separation

### Clients

- [ ] Android client support
- [ ] generic OpenMapData-compatible clients
- [ ] improved offline bundle compatibility
- [ ] client SDKs

### Administration

- [ ] improved invite workflow
- [ ] audit log UI
- [ ] better role management
- [ ] tenant-level settings
- [ ] zoo-level settings
- [ ] publication approval workflow

---

## Challenge-Focused Priorities

For the GBIF Ebbe Nielsen Challenge, the most important remaining tasks are:

- [ ] Make the README visually and conceptually strong.
- [ ] Add architecture diagrams.
- [ ] Add screenshots.
- [ ] Document GBIF relevance clearly.
- [ ] Provide public demo endpoints.
- [ ] Show example API responses.
- [ ] Explain what was built during the challenge period.
- [ ] Clarify future Darwin Core / GBIF export direction.
- [ ] Keep GitHub Actions green.
- [ ] Tag a release for the submitted version.

---

## Release Milestones

### v0.1 — Public Alpha

Goal: make the project understandable and testable.

- public README,
- basic setup guide,
- public demo endpoints,
- core REST API,
- basic federation feed,
- SQLite export,
- Wikidata and GBIF enrichment.

### v0.2 — Self-Hosting Preview

Goal: make it easier for other institutions to install.

- Docker Compose,
- improved setup scripts,
- seed data,
- deployment guide,
- backup instructions,
- OpenAPI draft.

### v0.3 — Federation Preview

Goal: demonstrate multiple independently hosted nodes.

- registry format,
- feed validation,
- aggregator prototype,
- dataset metadata,
- versioning.

### v1.0 — Stable Publishing Infrastructure

Goal: stable API and production-ready self-hosting.

- stable API version,
- stable schema migrations,
- documented security model,
- production deployment docs,
- release artifacts,
- stable federation format.

---

## Long-Term Vision

OpenZooData should become a reusable open infrastructure layer for zoological biodiversity data.

Potential long-term outcomes:

- zoos publish interoperable open datasets,
- researchers can discover ex-situ species data,
- visitors can access GBIF-linked biodiversity information,
- institutions can self-host without losing control,
- aggregators can build directories without becoming data owners,
- GBIF and Wikidata links become standard parts of zoo biodiversity publishing.
