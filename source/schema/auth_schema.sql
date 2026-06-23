--
-- PostgreSQL database dump
--

\restrict 02d7ggtVD5eogvbkpPEP8BvzUDdrSTacfhTqlGOCbI8ZDWLb7AGT4eVAkHl6phZ

-- Dumped from database version 18.4 (Debian 18.4-1.pgdg13+1)
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: auth; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA auth;


--
-- Name: citext; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public;


--
-- Name: EXTENSION citext; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION citext IS 'data type for case-insensitive character strings';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: api_keys; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.api_keys (
    id integer NOT NULL,
    api_key_hash character varying(64) NOT NULL,
    zoo_id integer,
    write_permission boolean DEFAULT false NOT NULL,
    device_id character varying(100),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_used_at timestamp with time zone,
    expires_at timestamp with time zone
);


--
-- Name: TABLE api_keys; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.api_keys IS 'Technische API-Keys für Clients/Zoo-Zugänge — getrennt von Personen-Accounts';


--
-- Name: COLUMN api_keys.api_key_hash; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.api_keys.api_key_hash IS 'SHA-256 — niemals Klartext speichern';


--
-- Name: api_keys_id_seq; Type: SEQUENCE; Schema: auth; Owner: -
--

CREATE SEQUENCE auth.api_keys_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: api_keys_id_seq; Type: SEQUENCE OWNED BY; Schema: auth; Owner: -
--

ALTER SEQUENCE auth.api_keys_id_seq OWNED BY auth.api_keys.id;


--
-- Name: app_tokens; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.app_tokens (
    id bigint NOT NULL,
    device_id text NOT NULL,
    token_hash text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    last_used_at timestamp with time zone,
    is_active boolean DEFAULT true NOT NULL
);


--
-- Name: TABLE app_tokens; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.app_tokens IS 'UUID-basierte App-Tokens für ZooGuide-App-Besucher — vollständig unberührt von Auth-Migration';


--
-- Name: app_tokens_id_seq; Type: SEQUENCE; Schema: auth; Owner: -
--

CREATE SEQUENCE auth.app_tokens_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: app_tokens_id_seq; Type: SEQUENCE OWNED BY; Schema: auth; Owner: -
--

ALTER SEQUENCE auth.app_tokens_id_seq OWNED BY auth.app_tokens.id;


--
-- Name: audit_archive; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.audit_archive (
    id bigint NOT NULL,
    action character varying(100) NOT NULL,
    success boolean NOT NULL,
    error_code character varying(100),
    actor_user_id integer,
    actor_email character varying(255),
    actor_ip character varying(45),
    user_agent_hash character varying(64),
    tenant_id integer,
    zoo_id integer,
    target_type character varying(50),
    target_id integer,
    request_id character varying(64),
    correlation_id character varying(64),
    details jsonb,
    created_at timestamp with time zone NOT NULL,
    archived_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE audit_archive; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.audit_archive IS 'Archiv: Einträge aus audit_log nach 24 Monaten — bis 6 Jahre aufbewahren. Keine FKs (referenzierte Objekte könnten inzwischen gelöscht sein).';


--
-- Name: audit_log; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.audit_log (
    id bigint NOT NULL,
    action character varying(100) NOT NULL,
    success boolean DEFAULT true NOT NULL,
    error_code character varying(100),
    actor_user_id integer,
    actor_email character varying(255),
    actor_ip character varying(45),
    user_agent_hash character varying(64),
    tenant_id integer,
    zoo_id integer,
    target_type character varying(50),
    target_id integer,
    request_id character varying(64),
    correlation_id character varying(64),
    details jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT audit_log_action_check CHECK (((action)::text <> ''::text)),
    CONSTRAINT audit_log_target_type_check CHECK (((target_type)::text = ANY ((ARRAY['user'::character varying, 'tenant'::character varying, 'zoo'::character varying, 'species'::character varying, 'system'::character varying])::text[])))
);


--
-- Name: TABLE audit_log; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.audit_log IS 'Audit-Trail: 24 Monate online, danach Archiv bis 6 Jahre';


--
-- Name: COLUMN audit_log.action; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.audit_log.action IS 'z.B. login_success, user_created, publish_failed';


--
-- Name: COLUMN audit_log.actor_user_id; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.audit_log.actor_user_id IS 'NULL bei anonymen Aktionen (fehlgeschlagene Logins)';


--
-- Name: COLUMN audit_log.actor_ip; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.audit_log.actor_ip IS 'DSGVO: nach 30 Tagen anonymisieren (IPv4 letztes Oktett, IPv6 /48)';


--
-- Name: audit_log_id_seq; Type: SEQUENCE; Schema: auth; Owner: -
--

CREATE SEQUENCE auth.audit_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_log_id_seq; Type: SEQUENCE OWNED BY; Schema: auth; Owner: -
--

ALTER SEQUENCE auth.audit_log_id_seq OWNED BY auth.audit_log.id;


--
-- Name: external_keys; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.external_keys (
    id integer NOT NULL,
    key_value text NOT NULL,
    zoo_id integer,
    key_type character varying(50),
    expires_at date,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE external_keys; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.external_keys IS 'Externe Integrationsschlüssel (z.B. Wikidata, GBIF)';


--
-- Name: external_keys_id_seq; Type: SEQUENCE; Schema: auth; Owner: -
--

CREATE SEQUENCE auth.external_keys_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: external_keys_id_seq; Type: SEQUENCE OWNED BY; Schema: auth; Owner: -
--

ALTER SEQUENCE auth.external_keys_id_seq OWNED BY auth.external_keys.id;


--
-- Name: invites; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.invites (
    id bigint NOT NULL,
    user_id integer NOT NULL,
    invite_token_hash character varying(64) NOT NULL,
    invite_expires timestamp with time zone NOT NULL,
    invite_accepted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE invites; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.invites IS 'Invite-Token für neuen User-Onboarding (24h gültig)';


--
-- Name: COLUMN invites.invite_token_hash; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.invites.invite_token_hash IS 'SHA-256 — Klartext-Token nur in der E-Mail';


--
-- Name: COLUMN invites.invite_expires; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.invites.invite_expires IS 'Standard: NOW() + 24h (konfigurierbar via system_settings)';


--
-- Name: invites_id_seq; Type: SEQUENCE; Schema: auth; Owner: -
--

CREATE SEQUENCE auth.invites_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: invites_id_seq; Type: SEQUENCE OWNED BY; Schema: auth; Owner: -
--

ALTER SEQUENCE auth.invites_id_seq OWNED BY auth.invites.id;


--
-- Name: password_resets; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.password_resets (
    id bigint NOT NULL,
    user_id integer NOT NULL,
    reset_token_hash character varying(64) NOT NULL,
    reset_expires timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE password_resets; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.password_resets IS 'Passwort-Reset-Token (60 Minuten gültig)';


--
-- Name: COLUMN password_resets.reset_token_hash; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.password_resets.reset_token_hash IS 'SHA-256 — Klartext-Token nur in der E-Mail';


--
-- Name: COLUMN password_resets.reset_expires; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.password_resets.reset_expires IS 'Standard: NOW() + 60min (konfigurierbar via system_settings)';


--
-- Name: password_resets_id_seq; Type: SEQUENCE; Schema: auth; Owner: -
--

CREATE SEQUENCE auth.password_resets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: password_resets_id_seq; Type: SEQUENCE OWNED BY; Schema: auth; Owner: -
--

ALTER SEQUENCE auth.password_resets_id_seq OWNED BY auth.password_resets.id;


--
-- Name: refresh_tokens; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.refresh_tokens (
    id bigint NOT NULL,
    user_id integer NOT NULL,
    token_hash character varying(64) NOT NULL,
    device_id character varying(100),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    last_used timestamp with time zone
);


--
-- Name: TABLE refresh_tokens; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.refresh_tokens IS 'Refresh-Tokens für Admin/ZooCreator-User (NICHT App-Tokens)';


--
-- Name: COLUMN refresh_tokens.token_hash; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.refresh_tokens.token_hash IS 'SHA-256 des Klartext-Tokens — Klartext nie gespeichert';


--
-- Name: refresh_tokens_id_seq; Type: SEQUENCE; Schema: auth; Owner: -
--

CREATE SEQUENCE auth.refresh_tokens_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: refresh_tokens_id_seq; Type: SEQUENCE OWNED BY; Schema: auth; Owner: -
--

ALTER SEQUENCE auth.refresh_tokens_id_seq OWNED BY auth.refresh_tokens.id;


--
-- Name: revoked_tokens; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.revoked_tokens (
    jti character varying(64) NOT NULL,
    revoked_at timestamp with time zone DEFAULT now() NOT NULL,
    reason character varying(100),
    expires_at timestamp with time zone NOT NULL
);


--
-- Name: TABLE revoked_tokens; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.revoked_tokens IS 'JWT-Sperrliste (jti) — vorbereitet, Aktivierung in Phase 4';


--
-- Name: COLUMN revoked_tokens.jti; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.revoked_tokens.jti IS 'JWT-ID aus dem Token-Claim';


--
-- Name: COLUMN revoked_tokens.expires_at; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.revoked_tokens.expires_at IS 'Nach Token-Ablauf kann der Eintrag gelöscht werden';


--
-- Name: secrets; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.secrets (
    id integer NOT NULL,
    secret_hash character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE secrets; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.secrets IS 'Shared Secrets für API-Key-Ausstellung (getrennt von api_keys — kein FK bewusst)';


--
-- Name: secrets_id_seq; Type: SEQUENCE; Schema: auth; Owner: -
--

CREATE SEQUENCE auth.secrets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: secrets_id_seq; Type: SEQUENCE OWNED BY; Schema: auth; Owner: -
--

ALTER SEQUENCE auth.secrets_id_seq OWNED BY auth.secrets.id;


--
-- Name: species_proposals; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.species_proposals (
    id bigint NOT NULL,
    created_by_user_id integer,
    created_by_tenant_id integer,
    created_for_zoo_id integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    status character varying(30) DEFAULT 'pending'::character varying NOT NULL,
    validation_source character varying(20),
    validation_error text,
    reviewed_by_user_id integer,
    reviewed_at timestamp with time zone,
    review_comment text,
    wikidata_id character varying(20),
    latin_name character varying(200),
    german_name character varying(200),
    CONSTRAINT species_proposals_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'approved'::character varying, 'rejected'::character varying, 'needs_more_info'::character varying, 'external_check_failed'::character varying])::text[])))
);


--
-- Name: TABLE species_proposals; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.species_proposals IS 'Moderierter Species-Vorschlag-Workflow';


--
-- Name: COLUMN species_proposals.created_by_user_id; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.species_proposals.created_by_user_id IS 'FK mit SET NULL — Vorschlag bleibt auch wenn User gelöscht';


--
-- Name: COLUMN species_proposals.status; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.species_proposals.status IS 'pending|approved|rejected|needs_more_info|external_check_failed';


--
-- Name: COLUMN species_proposals.validation_source; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.species_proposals.validation_source IS 'wikidata | gbif | iucn';


--
-- Name: species_proposals_id_seq; Type: SEQUENCE; Schema: auth; Owner: -
--

CREATE SEQUENCE auth.species_proposals_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: species_proposals_id_seq; Type: SEQUENCE OWNED BY; Schema: auth; Owner: -
--

ALTER SEQUENCE auth.species_proposals_id_seq OWNED BY auth.species_proposals.id;


--
-- Name: system_settings; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.system_settings (
    key character varying(100) NOT NULL,
    value text NOT NULL,
    value_type character varying(20) NOT NULL,
    updated_by integer,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT system_settings_value_type_check CHECK (((value_type)::text = ANY ((ARRAY['int'::character varying, 'bool'::character varying, 'string'::character varying, 'time'::character varying, 'date'::character varying, 'weekday'::character varying])::text[])))
);


--
-- Name: TABLE system_settings; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.system_settings IS 'Globale Konfigurationsparameter — Auflösung: Zoo > Tenant > Global > Code-Default';


--
-- Name: COLUMN system_settings.value_type; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.system_settings.value_type IS 'int | bool | string | time | date | weekday';


--
-- Name: tenant_settings; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.tenant_settings (
    tenant_id integer NOT NULL,
    key character varying(100) NOT NULL,
    value text NOT NULL,
    value_type character varying(20) NOT NULL,
    updated_by integer,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT tenant_settings_value_type_check CHECK (((value_type)::text = ANY ((ARRAY['int'::character varying, 'bool'::character varying, 'string'::character varying, 'time'::character varying, 'date'::character varying, 'weekday'::character varying])::text[])))
);


--
-- Name: TABLE tenant_settings; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.tenant_settings IS 'Tenant-spezifische Settings — überschreiben system_settings';


--
-- Name: tenant_zoos; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.tenant_zoos (
    tenant_id integer NOT NULL,
    zoo_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE tenant_zoos; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.tenant_zoos IS 'n:m Zuordnung Tenant ↔ Zoo';


--
-- Name: COLUMN tenant_zoos.zoo_id; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.tenant_zoos.zoo_id IS 'Zoo-ID aus separater Zoo-DB — keine Cross-DB-FK möglich';


--
-- Name: tenants; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.tenants (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    plan character varying(20) DEFAULT 'free'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT tenants_plan_check CHECK (((plan)::text = ANY ((ARRAY['free'::character varying, 'basic'::character varying, 'pro'::character varying])::text[])))
);


--
-- Name: TABLE tenants; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.tenants IS 'Zoo-Betreiber/Kunden — können mehrere Zoos haben';


--
-- Name: COLUMN tenants.plan; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.tenants.plan IS 'free = Testzugang; basic = €149/mo; pro = €349/mo';


--
-- Name: COLUMN tenants.is_active; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.tenants.is_active IS 'Soft-Delete. FALSE = kein Login für Tenant-User möglich';


--
-- Name: tenants_id_seq; Type: SEQUENCE; Schema: auth; Owner: -
--

CREATE SEQUENCE auth.tenants_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tenants_id_seq; Type: SEQUENCE OWNED BY; Schema: auth; Owner: -
--

ALTER SEQUENCE auth.tenants_id_seq OWNED BY auth.tenants.id;


--
-- Name: user_global_roles; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.user_global_roles (
    user_id integer NOT NULL,
    role character varying(20) NOT NULL,
    CONSTRAINT user_global_roles_role_check CHECK (((role)::text = ANY ((ARRAY['super_admin'::character varying, 'moderator'::character varying])::text[])))
);


--
-- Name: TABLE user_global_roles; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.user_global_roles IS 'Globale Rollen (Mehrfachrollen möglich): super_admin, moderator';


--
-- Name: COLUMN user_global_roles.role; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.user_global_roles.role IS 'super_admin = plattformweiter Vollzugriff; moderator = Species-Moderation';


--
-- Name: user_tenant_roles; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.user_tenant_roles (
    user_id integer NOT NULL,
    tenant_id integer NOT NULL,
    role character varying(20) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT user_tenant_roles_role_check CHECK (((role)::text = 'tenant_admin'::text))
);


--
-- Name: TABLE user_tenant_roles; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.user_tenant_roles IS 'Tenant-Rolle: tenant_admin — verwaltet alle Zoos seines Tenants';


--
-- Name: COLUMN user_tenant_roles.is_active; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.user_tenant_roles.is_active IS 'Einzeln deaktivierbar ohne Löschen';


--
-- Name: user_zoo_roles; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.user_zoo_roles (
    user_id integer NOT NULL,
    zoo_id integer NOT NULL,
    role character varying(20) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    CONSTRAINT user_zoo_roles_role_check CHECK (((role)::text = ANY ((ARRAY['zoo_admin'::character varying, 'editor'::character varying, 'viewer'::character varying])::text[])))
);


--
-- Name: TABLE user_zoo_roles; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.user_zoo_roles IS 'Zoo-spezifische Rollen: zoo_admin (bearbeiten+publish+vergeben), editor, viewer';


--
-- Name: COLUMN user_zoo_roles.zoo_id; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.user_zoo_roles.zoo_id IS 'Zoo-ID aus separater Zoo-DB — App-Level-Validierung';


--
-- Name: COLUMN user_zoo_roles.role; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.user_zoo_roles.role IS 'zoo_admin: write+publish+vergabe; editor: write only; viewer: read only';


--
-- Name: COLUMN user_zoo_roles.is_active; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.user_zoo_roles.is_active IS 'Einzeln deaktivierbar ohne Löschen';


--
-- Name: users; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.users (
    id integer NOT NULL,
    tenant_id integer,
    email public.citext NOT NULL,
    password_hash character varying(255) NOT NULL,
    display_name character varying(255),
    is_active boolean DEFAULT true NOT NULL,
    must_change_password boolean DEFAULT false NOT NULL,
    failed_login_count smallint DEFAULT 0 NOT NULL,
    locked_until timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_login_at timestamp with time zone
);


--
-- Name: TABLE users; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.users IS 'Alle Zoo-Mitarbeiter und Admins (NICHT App-Besucher)';


--
-- Name: COLUMN users.tenant_id; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.users.tenant_id IS 'NULL = super_admin (plattformweit, kein Tenant)';


--
-- Name: COLUMN users.email; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.users.email IS 'CITEXT — case-insensitive unique';


--
-- Name: COLUMN users.must_change_password; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.users.must_change_password IS 'TRUE nach Invite — Pflicht beim ersten Login';


--
-- Name: COLUMN users.failed_login_count; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.users.failed_login_count IS 'Für Account-Lockout';


--
-- Name: COLUMN users.locked_until; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON COLUMN auth.users.locked_until IS 'NULL = nicht gesperrt';


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: auth; Owner: -
--

CREATE SEQUENCE auth.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: auth; Owner: -
--

ALTER SEQUENCE auth.users_id_seq OWNED BY auth.users.id;


--
-- Name: zoo_settings; Type: TABLE; Schema: auth; Owner: -
--

CREATE TABLE auth.zoo_settings (
    zoo_id integer NOT NULL,
    key character varying(100) NOT NULL,
    value text NOT NULL,
    value_type character varying(20) NOT NULL,
    updated_by integer,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT zoo_settings_value_type_check CHECK (((value_type)::text = ANY ((ARRAY['int'::character varying, 'bool'::character varying, 'string'::character varying, 'time'::character varying, 'date'::character varying, 'weekday'::character varying])::text[])))
);


--
-- Name: TABLE zoo_settings; Type: COMMENT; Schema: auth; Owner: -
--

COMMENT ON TABLE auth.zoo_settings IS 'Zoo-spezifische Settings — überschreiben tenant_settings und system_settings. zoo_id verweist logisch auf separate Zoo-DB.';


--
-- Name: api_keys id; Type: DEFAULT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.api_keys ALTER COLUMN id SET DEFAULT nextval('auth.api_keys_id_seq'::regclass);


--
-- Name: app_tokens id; Type: DEFAULT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.app_tokens ALTER COLUMN id SET DEFAULT nextval('auth.app_tokens_id_seq'::regclass);


--
-- Name: audit_log id; Type: DEFAULT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.audit_log ALTER COLUMN id SET DEFAULT nextval('auth.audit_log_id_seq'::regclass);


--
-- Name: external_keys id; Type: DEFAULT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.external_keys ALTER COLUMN id SET DEFAULT nextval('auth.external_keys_id_seq'::regclass);


--
-- Name: invites id; Type: DEFAULT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.invites ALTER COLUMN id SET DEFAULT nextval('auth.invites_id_seq'::regclass);


--
-- Name: password_resets id; Type: DEFAULT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.password_resets ALTER COLUMN id SET DEFAULT nextval('auth.password_resets_id_seq'::regclass);


--
-- Name: refresh_tokens id; Type: DEFAULT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.refresh_tokens ALTER COLUMN id SET DEFAULT nextval('auth.refresh_tokens_id_seq'::regclass);


--
-- Name: secrets id; Type: DEFAULT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.secrets ALTER COLUMN id SET DEFAULT nextval('auth.secrets_id_seq'::regclass);


--
-- Name: species_proposals id; Type: DEFAULT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.species_proposals ALTER COLUMN id SET DEFAULT nextval('auth.species_proposals_id_seq'::regclass);


--
-- Name: tenants id; Type: DEFAULT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.tenants ALTER COLUMN id SET DEFAULT nextval('auth.tenants_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.users ALTER COLUMN id SET DEFAULT nextval('auth.users_id_seq'::regclass);


--
-- Name: api_keys api_keys_api_key_hash_key; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.api_keys
    ADD CONSTRAINT api_keys_api_key_hash_key UNIQUE (api_key_hash);


--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);


--
-- Name: app_tokens app_tokens_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.app_tokens
    ADD CONSTRAINT app_tokens_pkey PRIMARY KEY (id);


--
-- Name: app_tokens app_tokens_token_hash_key; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.app_tokens
    ADD CONSTRAINT app_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id);


--
-- Name: external_keys external_keys_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.external_keys
    ADD CONSTRAINT external_keys_pkey PRIMARY KEY (id);


--
-- Name: invites invites_invite_token_hash_key; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.invites
    ADD CONSTRAINT invites_invite_token_hash_key UNIQUE (invite_token_hash);


--
-- Name: invites invites_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.invites
    ADD CONSTRAINT invites_pkey PRIMARY KEY (id);


--
-- Name: password_resets password_resets_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.password_resets
    ADD CONSTRAINT password_resets_pkey PRIMARY KEY (id);


--
-- Name: password_resets password_resets_reset_token_hash_key; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.password_resets
    ADD CONSTRAINT password_resets_reset_token_hash_key UNIQUE (reset_token_hash);


--
-- Name: refresh_tokens refresh_tokens_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.refresh_tokens
    ADD CONSTRAINT refresh_tokens_pkey PRIMARY KEY (id);


--
-- Name: refresh_tokens refresh_tokens_token_hash_key; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.refresh_tokens
    ADD CONSTRAINT refresh_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: revoked_tokens revoked_tokens_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.revoked_tokens
    ADD CONSTRAINT revoked_tokens_pkey PRIMARY KEY (jti);


--
-- Name: secrets secrets_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.secrets
    ADD CONSTRAINT secrets_pkey PRIMARY KEY (id);


--
-- Name: species_proposals species_proposals_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.species_proposals
    ADD CONSTRAINT species_proposals_pkey PRIMARY KEY (id);


--
-- Name: system_settings system_settings_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.system_settings
    ADD CONSTRAINT system_settings_pkey PRIMARY KEY (key);


--
-- Name: tenant_settings tenant_settings_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.tenant_settings
    ADD CONSTRAINT tenant_settings_pkey PRIMARY KEY (tenant_id, key);


--
-- Name: tenant_zoos tenant_zoos_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.tenant_zoos
    ADD CONSTRAINT tenant_zoos_pkey PRIMARY KEY (tenant_id, zoo_id);


--
-- Name: tenants tenants_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);


--
-- Name: user_global_roles user_global_roles_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.user_global_roles
    ADD CONSTRAINT user_global_roles_pkey PRIMARY KEY (user_id, role);


--
-- Name: user_tenant_roles user_tenant_roles_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.user_tenant_roles
    ADD CONSTRAINT user_tenant_roles_pkey PRIMARY KEY (user_id, tenant_id, role);


--
-- Name: user_zoo_roles user_zoo_roles_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.user_zoo_roles
    ADD CONSTRAINT user_zoo_roles_pkey PRIMARY KEY (user_id, zoo_id, role);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: zoo_settings zoo_settings_pkey; Type: CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.zoo_settings
    ADD CONSTRAINT zoo_settings_pkey PRIMARY KEY (zoo_id, key);


--
-- Name: idx_auth_ak_zoo_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_ak_zoo_id ON auth.api_keys USING btree (zoo_id);


--
-- Name: idx_auth_al_action; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_al_action ON auth.audit_log USING btree (action);


--
-- Name: idx_auth_al_actor_ip; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_al_actor_ip ON auth.audit_log USING btree (actor_ip) WHERE (actor_ip IS NOT NULL);


--
-- Name: idx_auth_al_actor_user_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_al_actor_user_id ON auth.audit_log USING btree (actor_user_id);


--
-- Name: idx_auth_al_created_at; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_al_created_at ON auth.audit_log USING btree (created_at);


--
-- Name: idx_auth_al_tenant_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_al_tenant_id ON auth.audit_log USING btree (tenant_id);


--
-- Name: idx_auth_al_zoo_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_al_zoo_id ON auth.audit_log USING btree (zoo_id);


--
-- Name: idx_auth_at_device_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_at_device_id ON auth.app_tokens USING btree (device_id);


--
-- Name: idx_auth_at_token_hash; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_at_token_hash ON auth.app_tokens USING btree (token_hash);


--
-- Name: idx_auth_inv_expires; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_inv_expires ON auth.invites USING btree (invite_expires) WHERE (invite_accepted_at IS NULL);


--
-- Name: idx_auth_inv_token_hash; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_inv_token_hash ON auth.invites USING btree (invite_token_hash);


--
-- Name: idx_auth_inv_user_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_inv_user_id ON auth.invites USING btree (user_id);


--
-- Name: idx_auth_pr_expires; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_pr_expires ON auth.password_resets USING btree (reset_expires) WHERE (used_at IS NULL);


--
-- Name: idx_auth_pr_token_hash; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_pr_token_hash ON auth.password_resets USING btree (reset_token_hash);


--
-- Name: idx_auth_pr_user_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_pr_user_id ON auth.password_resets USING btree (user_id);


--
-- Name: idx_auth_rt_token_hash; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_rt_token_hash ON auth.refresh_tokens USING btree (token_hash);


--
-- Name: idx_auth_rt_user_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_rt_user_id ON auth.refresh_tokens USING btree (user_id);


--
-- Name: idx_auth_rv_expires_at; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_rv_expires_at ON auth.revoked_tokens USING btree (expires_at);


--
-- Name: idx_auth_sp_created_by; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_sp_created_by ON auth.species_proposals USING btree (created_by_user_id);


--
-- Name: idx_auth_sp_status; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_sp_status ON auth.species_proposals USING btree (status);


--
-- Name: idx_auth_sp_zoo_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_sp_zoo_id ON auth.species_proposals USING btree (created_for_zoo_id);


--
-- Name: idx_auth_tz_tenant_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_tz_tenant_id ON auth.tenant_zoos USING btree (tenant_id);


--
-- Name: idx_auth_tz_zoo_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_tz_zoo_id ON auth.tenant_zoos USING btree (zoo_id);


--
-- Name: idx_auth_ugr_user_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_ugr_user_id ON auth.user_global_roles USING btree (user_id);


--
-- Name: idx_auth_users_email; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_users_email ON auth.users USING btree (email);


--
-- Name: idx_auth_users_is_active; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_users_is_active ON auth.users USING btree (is_active);


--
-- Name: idx_auth_users_tenant_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_users_tenant_id ON auth.users USING btree (tenant_id);


--
-- Name: idx_auth_utr_active; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_utr_active ON auth.user_tenant_roles USING btree (tenant_id, is_active);


--
-- Name: idx_auth_utr_tenant_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_utr_tenant_id ON auth.user_tenant_roles USING btree (tenant_id);


--
-- Name: idx_auth_utr_user_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_utr_user_id ON auth.user_tenant_roles USING btree (user_id);


--
-- Name: idx_auth_uzr_active; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_uzr_active ON auth.user_zoo_roles USING btree (zoo_id, is_active);


--
-- Name: idx_auth_uzr_user_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_uzr_user_id ON auth.user_zoo_roles USING btree (user_id);


--
-- Name: idx_auth_uzr_zoo_id; Type: INDEX; Schema: auth; Owner: -
--

CREATE INDEX idx_auth_uzr_zoo_id ON auth.user_zoo_roles USING btree (zoo_id);


--
-- Name: audit_log audit_log_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.audit_log
    ADD CONSTRAINT audit_log_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES auth.users(id) ON DELETE SET NULL;


--
-- Name: audit_log audit_log_tenant_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.audit_log
    ADD CONSTRAINT audit_log_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES auth.tenants(id) ON DELETE SET NULL;


--
-- Name: invites invites_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.invites
    ADD CONSTRAINT invites_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: password_resets password_resets_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.password_resets
    ADD CONSTRAINT password_resets_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: refresh_tokens refresh_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.refresh_tokens
    ADD CONSTRAINT refresh_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: species_proposals species_proposals_created_by_tenant_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.species_proposals
    ADD CONSTRAINT species_proposals_created_by_tenant_id_fkey FOREIGN KEY (created_by_tenant_id) REFERENCES auth.tenants(id) ON DELETE SET NULL;


--
-- Name: species_proposals species_proposals_created_by_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.species_proposals
    ADD CONSTRAINT species_proposals_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES auth.users(id) ON DELETE SET NULL;


--
-- Name: species_proposals species_proposals_reviewed_by_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.species_proposals
    ADD CONSTRAINT species_proposals_reviewed_by_user_id_fkey FOREIGN KEY (reviewed_by_user_id) REFERENCES auth.users(id) ON DELETE SET NULL;


--
-- Name: system_settings system_settings_updated_by_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.system_settings
    ADD CONSTRAINT system_settings_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES auth.users(id) ON DELETE SET NULL;


--
-- Name: tenant_settings tenant_settings_tenant_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.tenant_settings
    ADD CONSTRAINT tenant_settings_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES auth.tenants(id) ON DELETE CASCADE;


--
-- Name: tenant_settings tenant_settings_updated_by_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.tenant_settings
    ADD CONSTRAINT tenant_settings_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES auth.users(id) ON DELETE SET NULL;


--
-- Name: tenant_zoos tenant_zoos_tenant_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.tenant_zoos
    ADD CONSTRAINT tenant_zoos_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES auth.tenants(id) ON DELETE CASCADE;


--
-- Name: user_global_roles user_global_roles_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.user_global_roles
    ADD CONSTRAINT user_global_roles_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: user_tenant_roles user_tenant_roles_tenant_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.user_tenant_roles
    ADD CONSTRAINT user_tenant_roles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES auth.tenants(id) ON DELETE CASCADE;


--
-- Name: user_tenant_roles user_tenant_roles_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.user_tenant_roles
    ADD CONSTRAINT user_tenant_roles_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: user_zoo_roles user_zoo_roles_user_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.user_zoo_roles
    ADD CONSTRAINT user_zoo_roles_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;


--
-- Name: users users_tenant_id_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.users
    ADD CONSTRAINT users_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES auth.tenants(id) ON DELETE RESTRICT;


--
-- Name: zoo_settings zoo_settings_updated_by_fkey; Type: FK CONSTRAINT; Schema: auth; Owner: -
--

ALTER TABLE ONLY auth.zoo_settings
    ADD CONSTRAINT zoo_settings_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES auth.users(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict 02d7ggtVD5eogvbkpPEP8BvzUDdrSTacfhTqlGOCbI8ZDWLb7AGT4eVAkHl6phZ

