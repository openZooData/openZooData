-- =============================================================================
-- migrate_auth_v7.sql
-- Phase M2 (DDL) + Phase M3 (DML)
-- Plattform: openZooData
-- Datenbank: zooguide_auth (Schema: auth)
-- Erstellt:  Juni 2026
-- Grundlage: admin_auth_V7.md + migrate_auth_v7.md
--
-- Ausführung: copy-paste in Postico, Block für Block
-- Auth-DB und Zoo-DB bleiben getrennt; keine Cross-DB-FKs. zoo_id-Felder sind Integer-Referenzen auf die Zoo-DB und werden in Python geprüft.
--
-- Rollback (auskommentiert am Ende jedes Blocks)
-- =============================================================================


-- =============================================================================
-- PRE-FLIGHT — Extensions und Schema
-- Muss als erstes ausgeführt werden
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS citext;
CREATE SCHEMA IF NOT EXISTS auth;

-- =============================================================================
-- PHASE M2 — SCHEMA (DDL)
-- =============================================================================


-- -----------------------------------------------------------------------------
-- M2.1 — Bestehende auth.*-Legacy-Tabellen sichern
-- (5 Tabellen aus zoo_schema.sql — nie produktiv genutzt, aber sauber umbenennen)
-- -----------------------------------------------------------------------------

BEGIN;

ALTER TABLE IF EXISTS auth.user_zoo_roles RENAME TO user_zoo_roles_legacy;
ALTER TABLE IF EXISTS auth.users          RENAME TO users_legacy;
ALTER TABLE IF EXISTS auth.tenants        RENAME TO tenants_legacy;
ALTER TABLE IF EXISTS auth.api_keys       RENAME TO api_keys_legacy;
ALTER TABLE IF EXISTS auth.secrets        RENAME TO secrets_legacy;

COMMIT;

-- Rollback M2.1:
-- BEGIN;
-- ALTER TABLE IF EXISTS auth.user_zoo_roles_legacy RENAME TO user_zoo_roles;
-- ALTER TABLE IF EXISTS auth.users_legacy          RENAME TO users;
-- ALTER TABLE IF EXISTS auth.tenants_legacy        RENAME TO tenants;
-- ALTER TABLE IF EXISTS auth.api_keys_legacy       RENAME TO api_keys;
-- ALTER TABLE IF EXISTS auth.secrets_legacy        RENAME TO secrets;
-- COMMIT;


-- -----------------------------------------------------------------------------
-- M2.2 — Neue Tabellen anlegen (in Abhängigkeitsreihenfolge)
-- -----------------------------------------------------------------------------

BEGIN;


-- ── 1. auth.tenants ──────────────────────────────────────────────────────────

CREATE TABLE auth.tenants (
    id         SERIAL       PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    plan       VARCHAR(20)  NOT NULL DEFAULT 'free'
                            CHECK (plan IN ('free', 'basic', 'pro')),
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  auth.tenants           IS 'Zoo-Betreiber/Kunden — können mehrere Zoos haben';
COMMENT ON COLUMN auth.tenants.plan      IS 'free = Testzugang; basic = €149/mo; pro = €349/mo';
COMMENT ON COLUMN auth.tenants.is_active IS 'Soft-Delete. FALSE = kein Login für Tenant-User möglich';


-- ── 2. auth.tenant_zoos ──────────────────────────────────────────────────────

CREATE TABLE auth.tenant_zoos (
    tenant_id  INTEGER     NOT NULL REFERENCES auth.tenants(id) ON DELETE CASCADE,
    zoo_id     INTEGER     NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, zoo_id)
);

COMMENT ON TABLE  auth.tenant_zoos        IS 'n:m Zuordnung Tenant ↔ Zoo';
COMMENT ON COLUMN auth.tenant_zoos.zoo_id IS 'Zoo-ID aus separater Zoo-DB — keine Cross-DB-FK möglich';


-- ── 3. auth.users ─────────────────────────────────────────────────────────────

CREATE TABLE auth.users (
    id                  SERIAL       PRIMARY KEY,
    tenant_id           INTEGER      REFERENCES auth.tenants(id) ON DELETE RESTRICT,
                                     -- NULL erlaubt für super_admin
    email               CITEXT       NOT NULL UNIQUE,
    password_hash       VARCHAR(255) NOT NULL,
    display_name        VARCHAR(255),
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    must_change_password BOOLEAN     NOT NULL DEFAULT FALSE,
    failed_login_count  SMALLINT     NOT NULL DEFAULT 0,
    locked_until        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_login_at       TIMESTAMPTZ
);

COMMENT ON TABLE  auth.users                      IS 'Alle Zoo-Mitarbeiter und Admins (NICHT App-Besucher)';
COMMENT ON COLUMN auth.users.tenant_id            IS 'NULL = super_admin (plattformweit, kein Tenant)';
COMMENT ON COLUMN auth.users.email                IS 'CITEXT — case-insensitive unique';
COMMENT ON COLUMN auth.users.must_change_password IS 'TRUE nach Invite — Pflicht beim ersten Login';
COMMENT ON COLUMN auth.users.failed_login_count   IS 'Für Account-Lockout';
COMMENT ON COLUMN auth.users.locked_until         IS 'NULL = nicht gesperrt';


-- ── 4. auth.user_global_roles ────────────────────────────────────────────────

CREATE TABLE auth.user_global_roles (
    user_id INTEGER     NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role    VARCHAR(20) NOT NULL CHECK (role IN ('super_admin', 'moderator')),
    PRIMARY KEY (user_id, role)
);

COMMENT ON TABLE  auth.user_global_roles      IS 'Globale Rollen (Mehrfachrollen möglich): super_admin, moderator';
COMMENT ON COLUMN auth.user_global_roles.role IS 'super_admin = plattformweiter Vollzugriff; moderator = Species-Moderation';


-- ── 5. auth.user_tenant_roles ────────────────────────────────────────────────

CREATE TABLE auth.user_tenant_roles (
    user_id   INTEGER     NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id INTEGER     NOT NULL REFERENCES auth.tenants(id) ON DELETE CASCADE,
    role      VARCHAR(20) NOT NULL CHECK (role IN ('tenant_admin')),
    is_active BOOLEAN     NOT NULL DEFAULT TRUE,
    PRIMARY KEY (user_id, tenant_id, role)
);

COMMENT ON TABLE  auth.user_tenant_roles           IS 'Tenant-Rolle: tenant_admin — verwaltet alle Zoos seines Tenants';
COMMENT ON COLUMN auth.user_tenant_roles.is_active IS 'Einzeln deaktivierbar ohne Löschen';


-- ── 6. auth.user_zoo_roles ───────────────────────────────────────────────────

CREATE TABLE auth.user_zoo_roles (
    user_id   INTEGER     NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    zoo_id    INTEGER     NOT NULL,
                          -- Zoo-ID aus separater Zoo-DB — App-Level-Validierung
    role      VARCHAR(20) NOT NULL CHECK (role IN ('zoo_admin', 'editor', 'viewer')),
    is_active BOOLEAN     NOT NULL DEFAULT TRUE,
    PRIMARY KEY (user_id, zoo_id, role)
);

COMMENT ON TABLE  auth.user_zoo_roles           IS 'Zoo-spezifische Rollen: zoo_admin (bearbeiten+publish+vergeben), editor, viewer';
COMMENT ON COLUMN auth.user_zoo_roles.role      IS 'zoo_admin: write+publish+vergabe; editor: write only; viewer: read only';
COMMENT ON COLUMN auth.user_zoo_roles.is_active IS 'Einzeln deaktivierbar ohne Löschen';
COMMENT ON COLUMN auth.user_zoo_roles.zoo_id    IS 'Zoo-ID aus separater Zoo-DB — App-Level-Validierung';


-- ── 7. auth.refresh_tokens ───────────────────────────────────────────────────

CREATE TABLE auth.refresh_tokens (
    id          BIGSERIAL    PRIMARY KEY,
    user_id     INTEGER      NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(64)  NOT NULL UNIQUE,
    device_id   VARCHAR(100),
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ  NOT NULL,
    last_used   TIMESTAMPTZ
);

COMMENT ON TABLE  auth.refresh_tokens            IS 'Refresh-Tokens für Admin/ZooCreator-User (NICHT App-Tokens)';
COMMENT ON COLUMN auth.refresh_tokens.token_hash IS 'SHA-256 des Klartext-Tokens — Klartext nie gespeichert';


-- ── 8. auth.app_tokens ───────────────────────────────────────────────────────

CREATE TABLE auth.app_tokens (
    id          BIGSERIAL   PRIMARY KEY,
    device_id   TEXT        NOT NULL,
    token_hash  TEXT        NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE auth.app_tokens IS 'UUID-basierte App-Tokens für ZooGuide-App-Besucher — vollständig unberührt von Auth-Migration';


-- ── 9. auth.api_keys ─────────────────────────────────────────────────────────

CREATE TABLE auth.api_keys (
    id               SERIAL       PRIMARY KEY,
    api_key_hash     VARCHAR(64)  NOT NULL UNIQUE,
    zoo_id           INTEGER,
    write_permission BOOLEAN      NOT NULL DEFAULT FALSE,
    device_id        VARCHAR(100),
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_used_at     TIMESTAMPTZ,
    expires_at       TIMESTAMPTZ
);

COMMENT ON TABLE  auth.api_keys              IS 'Technische API-Keys für Clients/Zoo-Zugänge — getrennt von Personen-Accounts';
COMMENT ON COLUMN auth.api_keys.api_key_hash IS 'SHA-256 — niemals Klartext speichern';


-- ── 10. auth.secrets ─────────────────────────────────────────────────────────

CREATE TABLE auth.secrets (
    id          SERIAL      PRIMARY KEY,
    secret_hash VARCHAR(255) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE auth.secrets IS 'Shared Secrets für API-Key-Ausstellung (getrennt von api_keys — kein FK bewusst)';


-- ── 11. auth.external_keys ───────────────────────────────────────────────────

CREATE TABLE auth.external_keys (
    id        SERIAL      PRIMARY KEY,
    key_value TEXT        NOT NULL,
    zoo_id    INTEGER,
    key_type  VARCHAR(50),
    expires_at DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE auth.external_keys IS 'Externe Integrationsschlüssel (z.B. Wikidata, GBIF)';


-- ── 12. auth.invites ─────────────────────────────────────────────────────────

CREATE TABLE auth.invites (
    id                 BIGSERIAL    PRIMARY KEY,
    user_id            INTEGER      NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    invite_token_hash  VARCHAR(64)  NOT NULL UNIQUE,
    invite_expires     TIMESTAMPTZ  NOT NULL,
    invite_accepted_at TIMESTAMPTZ,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  auth.invites                    IS 'Invite-Token für neuen User-Onboarding (24h gültig)';
COMMENT ON COLUMN auth.invites.invite_token_hash  IS 'SHA-256 — Klartext-Token nur in der E-Mail';
COMMENT ON COLUMN auth.invites.invite_expires     IS 'Standard: NOW() + 24h (konfigurierbar via system_settings)';


-- ── 13. auth.password_resets ─────────────────────────────────────────────────

CREATE TABLE auth.password_resets (
    id               BIGSERIAL    PRIMARY KEY,
    user_id          INTEGER      NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    reset_token_hash VARCHAR(64)  NOT NULL UNIQUE,
    reset_expires    TIMESTAMPTZ  NOT NULL,
    used_at          TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  auth.password_resets                IS 'Passwort-Reset-Token (60 Minuten gültig)';
COMMENT ON COLUMN auth.password_resets.reset_token_hash IS 'SHA-256 — Klartext-Token nur in der E-Mail';
COMMENT ON COLUMN auth.password_resets.reset_expires    IS 'Standard: NOW() + 60min (konfigurierbar via system_settings)';


-- ── 14. auth.revoked_tokens ──────────────────────────────────────────────────

CREATE TABLE auth.revoked_tokens (
    jti        VARCHAR(64)  PRIMARY KEY,
    revoked_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    reason     VARCHAR(100),
    expires_at TIMESTAMPTZ  NOT NULL
);

COMMENT ON TABLE  auth.revoked_tokens           IS 'JWT-Sperrliste (jti) — vorbereitet, Aktivierung in Phase 4';
COMMENT ON COLUMN auth.revoked_tokens.jti       IS 'JWT-ID aus dem Token-Claim';
COMMENT ON COLUMN auth.revoked_tokens.expires_at IS 'Nach Token-Ablauf kann der Eintrag gelöscht werden';


-- ── 15. auth.audit_log ───────────────────────────────────────────────────────

CREATE TABLE auth.audit_log (
    id             BIGSERIAL    PRIMARY KEY,
    action         VARCHAR(100) NOT NULL CHECK (action <> ''),
    success        BOOLEAN      NOT NULL DEFAULT TRUE,
    error_code     VARCHAR(100),
    actor_user_id  INTEGER      REFERENCES auth.users(id) ON DELETE SET NULL,
    actor_email    VARCHAR(255),
    actor_ip       VARCHAR(45),
    user_agent_hash VARCHAR(64),
    tenant_id      INTEGER      REFERENCES auth.tenants(id) ON DELETE SET NULL,
    zoo_id         INTEGER,
    target_type    VARCHAR(50)  CHECK (target_type IN ('user','tenant','zoo','species','system')),
    target_id      INTEGER,
    request_id     VARCHAR(64),
    correlation_id VARCHAR(64),
    details        JSONB,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  auth.audit_log              IS 'Audit-Trail: 24 Monate online, danach Archiv bis 6 Jahre';
COMMENT ON COLUMN auth.audit_log.actor_ip     IS 'DSGVO: nach 30 Tagen anonymisieren (IPv4 letztes Oktett, IPv6 /48)';
COMMENT ON COLUMN auth.audit_log.actor_user_id IS 'NULL bei anonymen Aktionen (fehlgeschlagene Logins)';
COMMENT ON COLUMN auth.audit_log.action       IS 'z.B. login_success, user_created, publish_failed';


-- ── 16. auth.audit_archive ───────────────────────────────────────────────────

CREATE TABLE auth.audit_archive (
    id             BIGINT       NOT NULL,
    action         VARCHAR(100) NOT NULL,
    success        BOOLEAN      NOT NULL,
    error_code     VARCHAR(100),
    actor_user_id  INTEGER,
    actor_email    VARCHAR(255),
    actor_ip       VARCHAR(45),
    user_agent_hash VARCHAR(64),
    tenant_id      INTEGER,
    zoo_id         INTEGER,
    target_type    VARCHAR(50),
    target_id      INTEGER,
    request_id     VARCHAR(64),
    correlation_id VARCHAR(64),
    details        JSONB,
    created_at     TIMESTAMPTZ  NOT NULL,
    archived_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE auth.audit_archive IS 'Archiv: Einträge aus audit_log nach 24 Monaten — bis 6 Jahre aufbewahren. Keine FKs (referenzierte Objekte könnten inzwischen gelöscht sein).';


-- ── 17. auth.system_settings ─────────────────────────────────────────────────

CREATE TABLE auth.system_settings (
    key        VARCHAR(100) PRIMARY KEY,
    value      TEXT         NOT NULL,
    value_type VARCHAR(20)  NOT NULL
               CHECK (value_type IN ('int', 'bool', 'string', 'time', 'date', 'weekday')),
    updated_by INTEGER      REFERENCES auth.users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  auth.system_settings            IS 'Globale Konfigurationsparameter — Auflösung: Zoo > Tenant > Global > Code-Default';
COMMENT ON COLUMN auth.system_settings.value_type IS 'int | bool | string | time | date | weekday';


-- ── 18. auth.tenant_settings ─────────────────────────────────────────────────

CREATE TABLE auth.tenant_settings (
    tenant_id  INTEGER      NOT NULL REFERENCES auth.tenants(id) ON DELETE CASCADE,
    key        VARCHAR(100) NOT NULL,
    value      TEXT         NOT NULL,
    value_type VARCHAR(20)  NOT NULL
               CHECK (value_type IN ('int', 'bool', 'string', 'time', 'date', 'weekday')),
    updated_by INTEGER      REFERENCES auth.users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, key)
);

COMMENT ON TABLE auth.tenant_settings IS 'Tenant-spezifische Settings — überschreiben system_settings';


-- ── 19. auth.zoo_settings ────────────────────────────────────────────────────

CREATE TABLE auth.zoo_settings (
    zoo_id     INTEGER      NOT NULL,
    key        VARCHAR(100) NOT NULL,
    value      TEXT         NOT NULL,
    value_type VARCHAR(20)  NOT NULL
               CHECK (value_type IN ('int', 'bool', 'string', 'time', 'date', 'weekday')),
    updated_by INTEGER      REFERENCES auth.users(id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (zoo_id, key)
);

COMMENT ON TABLE auth.zoo_settings IS 'Zoo-spezifische Settings — überschreiben tenant_settings und system_settings. zoo_id verweist logisch auf separate Zoo-DB.';


-- ── 20. auth.species_proposals ───────────────────────────────────────────────

CREATE TABLE auth.species_proposals (
    id                   BIGSERIAL    PRIMARY KEY,
    created_by_user_id   INTEGER      REFERENCES auth.users(id) ON DELETE SET NULL,
    created_by_tenant_id INTEGER      REFERENCES auth.tenants(id) ON DELETE SET NULL,
    created_for_zoo_id   INTEGER,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    status               VARCHAR(30)  NOT NULL DEFAULT 'pending'
                         CHECK (status IN (
                             'pending',
                             'approved',
                             'rejected',
                             'needs_more_info',
                             'external_check_failed'
                         )),
    validation_source    VARCHAR(20),
    validation_error     TEXT,
    reviewed_by_user_id  INTEGER      REFERENCES auth.users(id) ON DELETE SET NULL,
    reviewed_at          TIMESTAMPTZ,
    review_comment       TEXT,
    wikidata_id          VARCHAR(20),
    latin_name           VARCHAR(200),
    german_name          VARCHAR(200)
);

COMMENT ON TABLE  auth.species_proposals                    IS 'Moderierter Species-Vorschlag-Workflow';
COMMENT ON COLUMN auth.species_proposals.status             IS 'pending|approved|rejected|needs_more_info|external_check_failed';
COMMENT ON COLUMN auth.species_proposals.validation_source  IS 'wikidata | gbif | iucn';
COMMENT ON COLUMN auth.species_proposals.created_by_user_id IS 'FK mit SET NULL — Vorschlag bleibt auch wenn User gelöscht';

-- ── 21. Cross-DB-Hinweis ─────────────────────────────────────────────────
-- Zoo-DB und Auth-DB sind getrennt. Deshalb werden keine FKs auf zoo.* oder
-- aus zoo.* auf auth.* erzeugt. Felder wie zoo_id oder uploaded_by werden
-- auf Applikationsebene validiert.

-- =============================================================================
-- INDIZES
-- =============================================================================

-- auth.users
CREATE INDEX idx_auth_users_tenant_id     ON auth.users (tenant_id);
CREATE INDEX idx_auth_users_email         ON auth.users (email);
CREATE INDEX idx_auth_users_is_active     ON auth.users (is_active);

-- auth.user_global_roles
CREATE INDEX idx_auth_ugr_user_id         ON auth.user_global_roles (user_id);

-- auth.user_tenant_roles
CREATE INDEX idx_auth_utr_user_id         ON auth.user_tenant_roles (user_id);
CREATE INDEX idx_auth_utr_tenant_id       ON auth.user_tenant_roles (tenant_id);
CREATE INDEX idx_auth_utr_active          ON auth.user_tenant_roles (tenant_id, is_active);

-- auth.user_zoo_roles
CREATE INDEX idx_auth_uzr_user_id         ON auth.user_zoo_roles (user_id);
CREATE INDEX idx_auth_uzr_zoo_id          ON auth.user_zoo_roles (zoo_id);
CREATE INDEX idx_auth_uzr_active          ON auth.user_zoo_roles (zoo_id, is_active);

-- auth.refresh_tokens
CREATE INDEX idx_auth_rt_user_id          ON auth.refresh_tokens (user_id);
CREATE INDEX idx_auth_rt_token_hash       ON auth.refresh_tokens (token_hash);

-- auth.app_tokens
CREATE INDEX idx_auth_at_device_id        ON auth.app_tokens (device_id);
CREATE INDEX idx_auth_at_token_hash       ON auth.app_tokens (token_hash);

-- auth.api_keys
CREATE INDEX idx_auth_ak_zoo_id           ON auth.api_keys (zoo_id);

-- auth.invites
CREATE INDEX idx_auth_inv_user_id         ON auth.invites (user_id);
CREATE INDEX idx_auth_inv_token_hash      ON auth.invites (invite_token_hash);
CREATE INDEX idx_auth_inv_expires         ON auth.invites (invite_expires)
    WHERE invite_accepted_at IS NULL;

-- auth.password_resets
CREATE INDEX idx_auth_pr_user_id          ON auth.password_resets (user_id);
CREATE INDEX idx_auth_pr_token_hash       ON auth.password_resets (reset_token_hash);
CREATE INDEX idx_auth_pr_expires          ON auth.password_resets (reset_expires)
    WHERE used_at IS NULL;

-- auth.revoked_tokens
CREATE INDEX idx_auth_rv_expires_at       ON auth.revoked_tokens (expires_at);

-- auth.audit_log
CREATE INDEX idx_auth_al_created_at       ON auth.audit_log (created_at);
CREATE INDEX idx_auth_al_actor_user_id    ON auth.audit_log (actor_user_id);
CREATE INDEX idx_auth_al_tenant_id        ON auth.audit_log (tenant_id);
CREATE INDEX idx_auth_al_zoo_id           ON auth.audit_log (zoo_id);
CREATE INDEX idx_auth_al_action           ON auth.audit_log (action);
CREATE INDEX idx_auth_al_actor_ip         ON auth.audit_log (actor_ip)
    WHERE actor_ip IS NOT NULL;

-- auth.tenant_zoos
CREATE INDEX idx_auth_tz_tenant_id        ON auth.tenant_zoos (tenant_id);
CREATE INDEX idx_auth_tz_zoo_id           ON auth.tenant_zoos (zoo_id);

-- auth.species_proposals
CREATE INDEX idx_auth_sp_status           ON auth.species_proposals (status);
CREATE INDEX idx_auth_sp_created_by       ON auth.species_proposals (created_by_user_id);
CREATE INDEX idx_auth_sp_zoo_id           ON auth.species_proposals (created_for_zoo_id);

COMMIT;

-- Rollback M2.2 (alle neuen Tabellen entfernen):
-- BEGIN;
-- DROP TABLE IF EXISTS auth.species_proposals    CASCADE;
-- DROP TABLE IF EXISTS auth.zoo_settings         CASCADE;
-- DROP TABLE IF EXISTS auth.tenant_settings      CASCADE;
-- DROP TABLE IF EXISTS auth.system_settings      CASCADE;
-- DROP TABLE IF EXISTS auth.audit_archive        CASCADE;
-- DROP TABLE IF EXISTS auth.audit_log            CASCADE;
-- DROP TABLE IF EXISTS auth.revoked_tokens       CASCADE;
-- DROP TABLE IF EXISTS auth.password_resets      CASCADE;
-- DROP TABLE IF EXISTS auth.invites              CASCADE;
-- DROP TABLE IF EXISTS auth.external_keys        CASCADE;
-- DROP TABLE IF EXISTS auth.secrets              CASCADE;
-- DROP TABLE IF EXISTS auth.api_keys             CASCADE;
-- DROP TABLE IF EXISTS auth.app_tokens           CASCADE;
-- DROP TABLE IF EXISTS auth.refresh_tokens       CASCADE;
-- DROP TABLE IF EXISTS auth.user_zoo_roles       CASCADE;
-- DROP TABLE IF EXISTS auth.user_tenant_roles    CASCADE;
-- DROP TABLE IF EXISTS auth.user_global_roles    CASCADE;
-- DROP TABLE IF EXISTS auth.users               CASCADE;
-- DROP TABLE IF EXISTS auth.tenant_zoos          CASCADE;
-- DROP TABLE IF EXISTS auth.tenants              CASCADE;
-- COMMIT;


-- =============================================================================
-- PHASE M3 — INITIALDATEN (DML)
-- =============================================================================


-- -----------------------------------------------------------------------------
-- M3.1 — System-Settings Defaults
-- -----------------------------------------------------------------------------

BEGIN;

INSERT INTO auth.system_settings (key, value, value_type) VALUES
    ('admin_access_token_minutes',   '480',   'int'),
    ('admin_refresh_token_days',     '30',    'int'),
    ('admin_invite_token_minutes',   '1440',  'int'),    -- 24h
    ('admin_password_reset_minutes', '60',    'int'),
    ('audit_online_months',          '24',    'int'),
    ('audit_archive_years',          '6',     'int'),
    ('audit_ip_anonymize_days',      '30',    'int'),
    ('technical_log_retention_days', '90',    'int'),
    ('publish_log_retention_months', '24',    'int'),
    ('publish_notification_enabled', 'true',  'bool'),
    ('publish_error_email_enabled',  'true',  'bool');

COMMIT;

-- Rollback M3.1:
-- BEGIN;
-- DELETE FROM auth.system_settings;
-- COMMIT;


-- -----------------------------------------------------------------------------
-- M3.2 — Legacy-Tabellen aufräumen
-- (nach erfolgreicher Validierung — nicht sofort nach M2)
-- Erst ausführen wenn alle Smoke-Tests bestanden haben.
-- -----------------------------------------------------------------------------

-- WARTEN: Erst nach 2 Wochen stabilem Betrieb ausführen!

-- BEGIN;
-- DROP TABLE IF EXISTS auth.user_zoo_roles_legacy CASCADE;
-- DROP TABLE IF EXISTS auth.users_legacy          CASCADE;
-- DROP TABLE IF EXISTS auth.tenants_legacy        CASCADE;
-- DROP TABLE IF EXISTS auth.api_keys_legacy       CASCADE;
-- DROP TABLE IF EXISTS auth.secrets_legacy        CASCADE;
-- COMMIT;


-- =============================================================================
-- VERIFIKATION — nach M2 + M3 ausführen, vor Code-Umschaltung
-- =============================================================================

-- 1. Alle 20 neuen Tabellen vorhanden?
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'auth'
  AND table_name NOT LIKE '%_legacy'
ORDER BY table_name;
-- Erwartetes Ergebnis: 20 Zeilen

-- 2. System-Settings korrekt?
SELECT key, value, value_type FROM auth.system_settings ORDER BY key;
-- Erwartetes Ergebnis: 11 Zeilen

-- 3. Legacy-Tabellen noch vorhanden (soll noch da sein)?
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'auth'
  AND table_name LIKE '%_legacy'
ORDER BY table_name;
-- Erwartetes Ergebnis: 5 Zeilen (api_keys_legacy, secrets_legacy,
--   tenants_legacy, user_zoo_roles_legacy, users_legacy)

-- 4. Constraints korrekt?
SELECT conname, contype
FROM pg_constraint
WHERE connamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'auth')
ORDER BY conname;

-- 5. Foreign Keys prüfen (nur innerhalb der Auth-DB; keine Cross-DB-FKs auf zoo.*)
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_schema AS foreign_schema,
    ccu.table_name   AS foreign_table
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
    ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'auth'
ORDER BY tc.table_name, kcu.column_name;
-- Erwartetes Ergebnis: nur FKs innerhalb auth.* sichtbar; zoo_id-Felder haben bewusst keine FK

-- =============================================================================
-- NÄCHSTER SCHRITT nach Freigabe:
-- db.py + helpers/authz.py + helpers/audit.py + routes/auth.py
-- =============================================================================
