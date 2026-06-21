# Changelog

All notable changes to OpenZooData will be documented here.

## [Unreleased]

### Added
- `enclosure_species` as the central link between a species and its location
  in the zoo (enclosure and/or house), replacing the previous direct
  `enclosure`-only relationship
- Feeding times and birth records (`births`) attached to `enclosure_species`,
  exposed as nested arrays on the parent resource
- Birth records persist permanently as historical data — a species can no
  longer be deleted via the API once a birth has been recorded for it (`409`)
- GPS positions and photos can now be attached directly to an
  `enclosure_species` entry (in addition to enclosures, houses, and species)
- `GET /api/v1/zoos/<zoo>/enclosure_species/<id>` to fetch a single
  species-in-enclosure entry directly, without re-fetching the full list
- Dedicated CRUD endpoints for feeding times and birth records
  (`/enclosure_species/<id>/feeding_times`, `/enclosure_species/<id>/births`),
  alongside the existing nested-array approach on `enclosure_species` itself
  — both remain supported in parallel
- Zoo-wide listing of all feeding times and birth records
  (`/zoos/<zoo>/feeding_times`, `/zoos/<zoo>/births`), independent of any
  single species-in-enclosure entry, with an optional `species_id` filter
- CORS (`Access-Control-Allow-Origin: *`) on the public, unauthenticated
  `/feed` and `/feed/<zoo>` endpoints, so third-party tools and browser-based
  feed readers can consume them directly without a server-side proxy
- `icon_media_id` and `map_overlay_1_id` … `map_overlay_5_id` on `zoo.zoos`
  (direct foreign-key columns into `zoo.media`, mirroring the existing
  `species.icon_media_id` convention), resolved on read as
  `icon_media_path` / `map_overlay_1_path` … `map_overlay_5_path` on both
  `GET /api/v1/zoos/<zoo>` and `GET /api/v1/admin/zoos/<zoo>`. The existing
  `icon_url`/`map_overlay` single-value fields are unchanged and remain
  part of the response alongside the new fields

### Fixed
- Tenant isolation gap in enclosure deletion: a fallback code path could
  delete an `enclosure_species` row without verifying it belonged to the
  caller's zoo
- Deleting an enclosure or `enclosure_species` entry now correctly cleans up
  its associated photos and GPS positions (these are stored polymorphically
  and are not covered by foreign-key cascades)
- Several admin role-management endpoints (revoking a zoo/tenant/global role,
  granting a tenant or global role) were unreachable due to missing route
  registrations — fixed
- Species could be created by users with read-only (`viewer`) access; write
  access is now correctly enforced
- The SQLite export pipeline referenced a stale column name for feeding
  times, births, and GPS positions, causing zoo publishing to fail; also
  fixed an export query that silently skipped `enclosure_species` entries
  attached only to a house rather than an outdoor enclosure
- Various missing imports across admin endpoints (audit logging, password
  reset email delivery, role-constant validation) that could surface as
  `500` errors on otherwise-valid requests
- Stale internal documentation/test data referencing the previous feedback
  type taxonomy and column names

### Initial public release
- Flask-based API with Blueprint structure
- PostgreSQL zoo and auth database support
- JWT and App Token authentication
- SQLite export delivery with ETag/gzip support
- Public RSS feed infrastructure
- Wikidata synchronization tooling
- Feedback and community contribution system
- Database schema for zoo, species, enclosures, and auth
- Interoperability requirements (RSS feed as discovery endpoint)
