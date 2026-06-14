--
-- PostgreSQL database dump
--


-- Dumped from database version 15.18 (Debian 15.18-0+deb12u1)
-- Dumped by pg_dump version 15.18 (Debian 15.18-0+deb12u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: community; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA IF NOT EXISTS community;


--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

-- *not* creating schema, since initdb creates it


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS '';


--
-- Name: zoo; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA IF NOT EXISTS zoo;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: change_proposals; Type: TABLE; Schema: community; Owner: -
--

CREATE TABLE community.change_proposals (
    id integer NOT NULL,
    zoo_id integer,
    proposed_by integer,
    contributor_id uuid,
    entity_type character varying(30),
    entity_id integer,
    proposed_data jsonb,
    status character varying(20) DEFAULT 'pending'::character varying,
    reviewed_by integer,
    review_note text,
    created_at timestamp with time zone DEFAULT now(),
    published_at timestamp with time zone,
    CONSTRAINT change_proposals_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'approved'::character varying, 'rejected'::character varying, 'published'::character varying])::text[])))
);


--
-- Name: change_proposals_id_seq; Type: SEQUENCE; Schema: community; Owner: -
--

CREATE SEQUENCE community.change_proposals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: change_proposals_id_seq; Type: SEQUENCE OWNED BY; Schema: community; Owner: -
--

ALTER SEQUENCE community.change_proposals_id_seq OWNED BY community.change_proposals.id;


--
-- Name: contributor_stats; Type: TABLE; Schema: community; Owner: -
--

CREATE TABLE community.contributor_stats (
    contributor_id uuid NOT NULL,
    proposals_total integer DEFAULT 0,
    proposals_accepted integer DEFAULT 0,
    points integer DEFAULT 0,
    first_seen timestamp with time zone DEFAULT now(),
    last_seen timestamp with time zone DEFAULT now()
);


--
-- Name: device_subscriptions; Type: TABLE; Schema: community; Owner: -
--

CREATE TABLE community.device_subscriptions (
    id integer NOT NULL,
    contributor_id uuid NOT NULL,
    device_token character varying(200) NOT NULL,
    platform character varying(10) DEFAULT 'ios'::character varying,
    zoo_id integer,
    notify_births boolean DEFAULT true,
    notify_events boolean DEFAULT false,
    notify_feeding boolean DEFAULT false,
    is_active boolean DEFAULT true,
    registered_at timestamp with time zone DEFAULT now(),
    last_seen timestamp with time zone DEFAULT now()
);


--
-- Name: device_subscriptions_id_seq; Type: SEQUENCE; Schema: community; Owner: -
--

CREATE SEQUENCE community.device_subscriptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: device_subscriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: community; Owner: -
--

ALTER SEQUENCE community.device_subscriptions_id_seq OWNED BY community.device_subscriptions.id;


--
-- Name: release_items; Type: TABLE; Schema: community; Owner: -
--

CREATE TABLE community.release_items (
    id integer NOT NULL,
    release_id integer NOT NULL,
    proposal_id integer NOT NULL
);


--
-- Name: release_items_id_seq; Type: SEQUENCE; Schema: community; Owner: -
--

CREATE SEQUENCE community.release_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: release_items_id_seq; Type: SEQUENCE OWNED BY; Schema: community; Owner: -
--

ALTER SEQUENCE community.release_items_id_seq OWNED BY community.release_items.id;


--
-- Name: releases; Type: TABLE; Schema: community; Owner: -
--

CREATE TABLE community.releases (
    id integer NOT NULL,
    zoo_id integer,
    version integer NOT NULL,
    status character varying(20) DEFAULT 'draft'::character varying,
    released_by integer,
    release_notes text,
    published_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT releases_status_check CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'published'::character varying])::text[])))
);


--
-- Name: releases_id_seq; Type: SEQUENCE; Schema: community; Owner: -
--

CREATE SEQUENCE community.releases_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: releases_id_seq; Type: SEQUENCE OWNED BY; Schema: community; Owner: -
--

ALTER SEQUENCE community.releases_id_seq OWNED BY community.releases.id;


--
-- Name: births; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.births (
    id integer NOT NULL,
    zoo_id integer NOT NULL,
    enclosure_id integer,
    species_id integer NOT NULL,
    birth_date date NOT NULL,
    count smallint DEFAULT 1,
    note text,
    is_public boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: births_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.births_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: births_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.births_id_seq OWNED BY zoo.births.id;


--
-- Name: domains; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.domains (
    id integer NOT NULL,
    zoo_id integer,
    name character varying(200) NOT NULL,
    sort_order integer DEFAULT 0,
    is_infrastructure boolean DEFAULT false,
    color_red smallint DEFAULT 128,
    color_green smallint DEFAULT 128,
    color_blue smallint DEFAULT 128,
    color_alpha numeric(3,1) DEFAULT 1.0
);


--
-- Name: domains_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.domains_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: domains_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.domains_id_seq OWNED BY zoo.domains.id;


--
-- Name: enclosure_species; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.enclosure_species (
    enclosure_id integer,
    species_id integer NOT NULL,
    note text,
    count_adult smallint,
    count_juvenile smallint,
    counted_at timestamp with time zone,
    id integer NOT NULL,
    house_id integer
);


--
-- Name: enclosure_species_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.enclosure_species_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: enclosure_species_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.enclosure_species_id_seq OWNED BY zoo.enclosure_species.id;


--
-- Name: enclosures; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.enclosures (
    id integer NOT NULL,
    zoo_id integer NOT NULL,
    house_id integer,
    name character varying(200),
    sort_order integer DEFAULT 0,
    domain_id integer,
    osm_relation_id bigint,
    history text,
    sponsor text,
    notes text,
    image_media_id integer
);


--
-- Name: enclosures_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.enclosures_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: enclosures_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.enclosures_id_seq OWNED BY zoo.enclosures.id;


--
-- Name: feedback; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.feedback (
    id integer NOT NULL,
    zoo_id integer NOT NULL,
    feedback_type_id smallint NOT NULL,
    contributor_id uuid NOT NULL,
    status character varying(20),
    review_comment text,
    reviewed_at timestamp with time zone,
    reviewed_by character varying(100),
    enclosure_id integer,
    value_time time without time zone,
    value_latitude double precision,
    value_longitude double precision,
    value_wikidata_id character varying(20),
    value_species_id integer,
    value_date date,
    value_count smallint,
    value_enrichment_text_id integer,
    value_report_reason_id smallint,
    value_language character varying(10),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT feedback_status_check CHECK (((status IS NULL) OR ((status)::text = ANY ((ARRAY['pending'::character varying, 'accepted'::character varying, 'rejected'::character varying])::text[]))))
);


--
-- Name: TABLE feedback; Type: COMMENT; Schema: zoo; Owner: -
--

COMMENT ON TABLE zoo.feedback IS 'Community-Feedback: Änderungsvorschläge (Admin-Review) + Textbewertungen (kein Review)';


--
-- Name: COLUMN feedback.contributor_id; Type: COMMENT; Schema: zoo; Owner: -
--

COMMENT ON COLUMN zoo.feedback.contributor_id IS 'UUID aus iOS Keychain — kein Personenbezug, DSGVO-konform';


--
-- Name: COLUMN feedback.status; Type: COMMENT; Schema: zoo; Owner: -
--

COMMENT ON COLUMN zoo.feedback.status IS 'NULL für Typ 9/10 (kein Review nötig). pending|accepted|rejected für Typ 1–8.';


--
-- Name: COLUMN feedback.value_wikidata_id; Type: COMMENT; Schema: zoo; Owner: -
--

COMMENT ON COLUMN zoo.feedback.value_wikidata_id IS 'Nur Typ 3: Wikidata-ID z.B. "Q140" für Löwe';


--
-- Name: COLUMN feedback.value_language; Type: COMMENT; Schema: zoo; Owner: -
--

COMMENT ON COLUMN zoo.feedback.value_language IS 'Nur Typ 8: Sprache des gemeldeten Textes, z.B. "de", "en"';


--
-- Name: feedback_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.feedback_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: feedback_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.feedback_id_seq OWNED BY zoo.feedback.id;


--
-- Name: feedback_report_reasons; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.feedback_report_reasons (
    id smallint NOT NULL,
    slug character varying(50) NOT NULL,
    label_de character varying(100) NOT NULL
);


--
-- Name: feedback_types; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.feedback_types (
    id smallint NOT NULL,
    slug character varying(50) NOT NULL,
    label_de character varying(100) NOT NULL,
    entity_type character varying(20) NOT NULL,
    requires_admin_review boolean DEFAULT true NOT NULL,
    is_active boolean DEFAULT true NOT NULL
);


--
-- Name: feeding_times; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.feeding_times (
    id integer NOT NULL,
    enclosure_id integer NOT NULL,
    species_id integer,
    feeding_time time without time zone NOT NULL,
    day_of_week smallint,
    note text,
    is_public boolean DEFAULT true
);


--
-- Name: feeding_times_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.feeding_times_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: feeding_times_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.feeding_times_id_seq OWNED BY zoo.feeding_times.id;


--
-- Name: geo_points; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.geo_points (
    id integer NOT NULL,
    entity_type character varying(30) NOT NULL,
    entity_id integer NOT NULL,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    translation_id integer,
    sort_order integer DEFAULT 0
);


--
-- Name: geo_points_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.geo_points_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: geo_points_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.geo_points_id_seq OWNED BY zoo.geo_points.id;


--
-- Name: house_opening_hours; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.house_opening_hours (
    id integer NOT NULL,
    house_id integer NOT NULL,
    day_of_week character varying(20) NOT NULL,
    open_time time without time zone,
    close_time time without time zone,
    valid_from date,
    valid_until date,
    label character varying(100)
);


--
-- Name: house_opening_hours_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.house_opening_hours_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: house_opening_hours_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.house_opening_hours_id_seq OWNED BY zoo.house_opening_hours.id;


--
-- Name: houses; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.houses (
    id integer NOT NULL,
    zoo_id integer NOT NULL,
    name character varying(200) NOT NULL,
    description text,
    history text,
    sponsor text,
    notes text,
    domain_id integer,
    image_media_id integer
);


--
-- Name: houses_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.houses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: houses_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.houses_id_seq OWNED BY zoo.houses.id;


--
-- Name: iucn_status; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.iucn_status (
    id integer NOT NULL,
    wikidata_id character varying(20) NOT NULL,
    code character varying(5) NOT NULL,
    name character varying(100) NOT NULL
);


--
-- Name: iucn_status_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.iucn_status_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: iucn_status_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.iucn_status_id_seq OWNED BY zoo.iucn_status.id;


--
-- Name: iucn_trend; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.iucn_trend (
    id integer NOT NULL,
    wikidata_id character varying(20) NOT NULL,
    name character varying(100) NOT NULL
);


--
-- Name: iucn_trend_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.iucn_trend_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: iucn_trend_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.iucn_trend_id_seq OWNED BY zoo.iucn_trend.id;


--
-- Name: location_species; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.location_species (
    location_id integer NOT NULL,
    species_id integer NOT NULL,
    note text
);


--
-- Name: location_types; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.location_types (
    id integer NOT NULL,
    slug character varying(50) NOT NULL,
    name character varying(100) NOT NULL,
    icon character varying(100),
    sort_order integer DEFAULT 0,
    icon_media_id integer
);


--
-- Name: location_types_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.location_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: location_types_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.location_types_id_seq OWNED BY zoo.location_types.id;


--
-- Name: locations; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.locations (
    id integer NOT NULL,
    zoo_id integer NOT NULL,
    name character varying(200) NOT NULL,
    name_display character varying(200),
    description text,
    location_type character varying(50),
    sort_order integer DEFAULT 0,
    domain_id integer,
    url character varying(255),
    description_long text,
    location_type_id integer,
    icon_media_id integer,
    image_media_id integer
);


--
-- Name: locations_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.locations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: locations_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.locations_id_seq OWNED BY zoo.locations.id;


--
-- Name: media; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.media (
    id integer NOT NULL,
    zoo_id integer,
    filename character varying(200) NOT NULL,
    storage_path character varying(500) NOT NULL,
    mime_type character varying(50),
    file_size integer,
    uploaded_at timestamp with time zone DEFAULT now(),
    uploaded_by integer,
    entity_type character varying(30),
    entity_id integer,
    sort_order integer DEFAULT 0,
    label character varying(100),
    wikidata_id character varying(20)
);


--
-- Name: media_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.media_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: media_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.media_id_seq OWNED BY zoo.media.id;


--
-- Name: opening_hours; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.opening_hours (
    id integer NOT NULL,
    location_id integer NOT NULL,
    day_of_week character varying(20) NOT NULL,
    open_time time without time zone,
    close_time time without time zone,
    valid_from date,
    valid_until date,
    label character varying(100)
);


--
-- Name: opening_hours_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.opening_hours_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: opening_hours_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.opening_hours_id_seq OWNED BY zoo.opening_hours.id;


--
-- Name: species; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.species (
    id integer NOT NULL,
    wikidata_id character varying(20),
    latin_name character varying(200),
    german_name character varying(200) NOT NULL,
    tax_kingdom_id character varying(20),
    tax_phylum_id character varying(20),
    tax_class_id character varying(20),
    tax_order_id character varying(20),
    tax_family_id character varying(20),
    tax_genus_id character varying(20),
    wiki_fetched_at timestamp with time zone,
    iucn_status_id character varying(20),
    iucn_population_trend_id character varying(20),
    iucn_fetched_at timestamp with time zone,
    gbif_taxon_key integer,
    id_valid boolean DEFAULT false,
    translations_valid boolean DEFAULT false,
    iucn_id character varying(20),
    icon_media_id integer
);


--
-- Name: species_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.species_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: species_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.species_id_seq OWNED BY zoo.species.id;


--
-- Name: species_texts; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.species_texts (
    id integer NOT NULL,
    species_id integer NOT NULL,
    field character varying(50) NOT NULL,
    de text,
    en text,
    es text,
    fr text,
    it text,
    nl text,
    pl text,
    pt text,
    ru text,
    tr text,
    uk text,
    zh_hans text,
    generated_at timestamp with time zone,
    helpful_count integer DEFAULT 0 NOT NULL,
    excellent_count integer DEFAULT 0 NOT NULL
);


--
-- Name: species_texts_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.species_texts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: species_texts_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.species_texts_id_seq OWNED BY zoo.species_texts.id;


--
-- Name: taxonomy; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.taxonomy (
    id integer NOT NULL,
    wikidata_id character varying(20) NOT NULL,
    rank character varying(20) NOT NULL,
    name character varying(200) NOT NULL
);


--
-- Name: taxonomy_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.taxonomy_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: taxonomy_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.taxonomy_id_seq OWNED BY zoo.taxonomy.id;


--
-- Name: translations; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.translations (
    entity_type character varying(30) NOT NULL,
    entity_id integer NOT NULL,
    de text,
    en text,
    es text,
    fr text,
    it text,
    nl text,
    pl text,
    pt text,
    ru text,
    tr text,
    uk text,
    zh_hans text,
    field character varying(50) DEFAULT 'name'::character varying NOT NULL,
    he text,
    ar text,
    ja text
);


--
-- Name: zoo_opening_hours; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.zoo_opening_hours (
    id integer NOT NULL,
    zoo_id integer NOT NULL,
    day_of_week character varying(20) NOT NULL,
    open_time time without time zone,
    close_time time without time zone,
    valid_from date,
    valid_until date,
    label character varying(100)
);


--
-- Name: zoo_opening_hours_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.zoo_opening_hours_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zoo_opening_hours_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.zoo_opening_hours_id_seq OWNED BY zoo.zoo_opening_hours.id;


--
-- Name: zoos; Type: TABLE; Schema: zoo; Owner: -
--

CREATE TABLE zoo.zoos (
    id integer NOT NULL,
    slug character varying(50) NOT NULL,
    name character varying(100) NOT NULL,
    url character varying(255),
    description text,
    email character varying(255),
    top_left_latitude double precision,
    top_left_longitude double precision,
    bottom_right_latitude double precision,
    bottom_right_longitude double precision,
    map_overlay character varying(100),
    data_version integer DEFAULT 0,
    media_version integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true,
    easy_language boolean DEFAULT false,
    number_animals integer,
    city text,
    country text DEFAULT 'DE'::text,
    icon_url character varying(255),
    latitude double precision,
    longitude double precision,
    time_open time without time zone,
    time_close time without time zone,
    archived_at timestamp with time zone
);


--
-- Name: zoos_id_seq; Type: SEQUENCE; Schema: zoo; Owner: -
--

CREATE SEQUENCE zoo.zoos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: zoos_id_seq; Type: SEQUENCE OWNED BY; Schema: zoo; Owner: -
--

ALTER SEQUENCE zoo.zoos_id_seq OWNED BY zoo.zoos.id;


--
-- Name: change_proposals id; Type: DEFAULT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.change_proposals ALTER COLUMN id SET DEFAULT nextval('community.change_proposals_id_seq'::regclass);


--
-- Name: device_subscriptions id; Type: DEFAULT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.device_subscriptions ALTER COLUMN id SET DEFAULT nextval('community.device_subscriptions_id_seq'::regclass);


--
-- Name: release_items id; Type: DEFAULT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.release_items ALTER COLUMN id SET DEFAULT nextval('community.release_items_id_seq'::regclass);


--
-- Name: releases id; Type: DEFAULT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.releases ALTER COLUMN id SET DEFAULT nextval('community.releases_id_seq'::regclass);


--
-- Name: births id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.births ALTER COLUMN id SET DEFAULT nextval('zoo.births_id_seq'::regclass);


--
-- Name: domains id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.domains ALTER COLUMN id SET DEFAULT nextval('zoo.domains_id_seq'::regclass);


--
-- Name: enclosure_species id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.enclosure_species ALTER COLUMN id SET DEFAULT nextval('zoo.enclosure_species_id_seq'::regclass);


--
-- Name: enclosures id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.enclosures ALTER COLUMN id SET DEFAULT nextval('zoo.enclosures_id_seq'::regclass);


--
-- Name: feedback id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feedback ALTER COLUMN id SET DEFAULT nextval('zoo.feedback_id_seq'::regclass);


--
-- Name: feeding_times id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feeding_times ALTER COLUMN id SET DEFAULT nextval('zoo.feeding_times_id_seq'::regclass);


--
-- Name: geo_points id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.geo_points ALTER COLUMN id SET DEFAULT nextval('zoo.geo_points_id_seq'::regclass);


--
-- Name: house_opening_hours id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.house_opening_hours ALTER COLUMN id SET DEFAULT nextval('zoo.house_opening_hours_id_seq'::regclass);


--
-- Name: houses id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.houses ALTER COLUMN id SET DEFAULT nextval('zoo.houses_id_seq'::regclass);


--
-- Name: iucn_status id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.iucn_status ALTER COLUMN id SET DEFAULT nextval('zoo.iucn_status_id_seq'::regclass);


--
-- Name: iucn_trend id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.iucn_trend ALTER COLUMN id SET DEFAULT nextval('zoo.iucn_trend_id_seq'::regclass);


--
-- Name: location_types id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.location_types ALTER COLUMN id SET DEFAULT nextval('zoo.location_types_id_seq'::regclass);


--
-- Name: locations id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.locations ALTER COLUMN id SET DEFAULT nextval('zoo.locations_id_seq'::regclass);


--
-- Name: media id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.media ALTER COLUMN id SET DEFAULT nextval('zoo.media_id_seq'::regclass);


--
-- Name: opening_hours id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.opening_hours ALTER COLUMN id SET DEFAULT nextval('zoo.opening_hours_id_seq'::regclass);


--
-- Name: species id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.species ALTER COLUMN id SET DEFAULT nextval('zoo.species_id_seq'::regclass);


--
-- Name: species_texts id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.species_texts ALTER COLUMN id SET DEFAULT nextval('zoo.species_texts_id_seq'::regclass);


--
-- Name: taxonomy id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.taxonomy ALTER COLUMN id SET DEFAULT nextval('zoo.taxonomy_id_seq'::regclass);


--
-- Name: zoo_opening_hours id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.zoo_opening_hours ALTER COLUMN id SET DEFAULT nextval('zoo.zoo_opening_hours_id_seq'::regclass);


--
-- Name: zoos id; Type: DEFAULT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.zoos ALTER COLUMN id SET DEFAULT nextval('zoo.zoos_id_seq'::regclass);


--
-- Name: change_proposals change_proposals_pkey; Type: CONSTRAINT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.change_proposals
    ADD CONSTRAINT change_proposals_pkey PRIMARY KEY (id);


--
-- Name: contributor_stats contributor_stats_pkey; Type: CONSTRAINT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.contributor_stats
    ADD CONSTRAINT contributor_stats_pkey PRIMARY KEY (contributor_id);


--
-- Name: device_subscriptions device_subscriptions_device_token_key; Type: CONSTRAINT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.device_subscriptions
    ADD CONSTRAINT device_subscriptions_device_token_key UNIQUE (device_token);


--
-- Name: device_subscriptions device_subscriptions_pkey; Type: CONSTRAINT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.device_subscriptions
    ADD CONSTRAINT device_subscriptions_pkey PRIMARY KEY (id);


--
-- Name: release_items release_items_pkey; Type: CONSTRAINT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.release_items
    ADD CONSTRAINT release_items_pkey PRIMARY KEY (id);


--
-- Name: releases releases_pkey; Type: CONSTRAINT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.releases
    ADD CONSTRAINT releases_pkey PRIMARY KEY (id);


--
-- Name: releases releases_zoo_id_version_key; Type: CONSTRAINT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.releases
    ADD CONSTRAINT releases_zoo_id_version_key UNIQUE (zoo_id, version);


--
-- Name: births births_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.births
    ADD CONSTRAINT births_pkey PRIMARY KEY (id);


--
-- Name: domains domains_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.domains
    ADD CONSTRAINT domains_pkey PRIMARY KEY (id);


--
-- Name: enclosure_species enclosure_species_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.enclosure_species
    ADD CONSTRAINT enclosure_species_pkey PRIMARY KEY (enclosure_id, species_id);


--
-- Name: enclosures enclosures_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.enclosures
    ADD CONSTRAINT enclosures_pkey PRIMARY KEY (id);


--
-- Name: feedback feedback_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feedback
    ADD CONSTRAINT feedback_pkey PRIMARY KEY (id);


--
-- Name: feedback_report_reasons feedback_report_reasons_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feedback_report_reasons
    ADD CONSTRAINT feedback_report_reasons_pkey PRIMARY KEY (id);


--
-- Name: feedback_report_reasons feedback_report_reasons_slug_key; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feedback_report_reasons
    ADD CONSTRAINT feedback_report_reasons_slug_key UNIQUE (slug);


--
-- Name: feedback_types feedback_types_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feedback_types
    ADD CONSTRAINT feedback_types_pkey PRIMARY KEY (id);


--
-- Name: feedback_types feedback_types_slug_key; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feedback_types
    ADD CONSTRAINT feedback_types_slug_key UNIQUE (slug);


--
-- Name: feeding_times feeding_times_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feeding_times
    ADD CONSTRAINT feeding_times_pkey PRIMARY KEY (id);


--
-- Name: geo_points geo_points_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.geo_points
    ADD CONSTRAINT geo_points_pkey PRIMARY KEY (id);


--
-- Name: house_opening_hours house_opening_hours_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.house_opening_hours
    ADD CONSTRAINT house_opening_hours_pkey PRIMARY KEY (id);


--
-- Name: houses houses_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.houses
    ADD CONSTRAINT houses_pkey PRIMARY KEY (id);


--
-- Name: iucn_status iucn_status_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.iucn_status
    ADD CONSTRAINT iucn_status_pkey PRIMARY KEY (id);


--
-- Name: iucn_status iucn_status_wikidata_id_key; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.iucn_status
    ADD CONSTRAINT iucn_status_wikidata_id_key UNIQUE (wikidata_id);


--
-- Name: iucn_trend iucn_trend_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.iucn_trend
    ADD CONSTRAINT iucn_trend_pkey PRIMARY KEY (id);


--
-- Name: iucn_trend iucn_trend_wikidata_id_key; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.iucn_trend
    ADD CONSTRAINT iucn_trend_wikidata_id_key UNIQUE (wikidata_id);


--
-- Name: location_species location_species_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.location_species
    ADD CONSTRAINT location_species_pkey PRIMARY KEY (location_id, species_id);


--
-- Name: location_types location_types_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.location_types
    ADD CONSTRAINT location_types_pkey PRIMARY KEY (id);


--
-- Name: location_types location_types_slug_key; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.location_types
    ADD CONSTRAINT location_types_slug_key UNIQUE (slug);


--
-- Name: locations locations_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.locations
    ADD CONSTRAINT locations_pkey PRIMARY KEY (id);


--
-- Name: media media_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.media
    ADD CONSTRAINT media_pkey PRIMARY KEY (id);


--
-- Name: opening_hours opening_hours_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.opening_hours
    ADD CONSTRAINT opening_hours_pkey PRIMARY KEY (id);


--
-- Name: species species_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.species
    ADD CONSTRAINT species_pkey PRIMARY KEY (id);


--
-- Name: species_texts species_texts_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.species_texts
    ADD CONSTRAINT species_texts_pkey PRIMARY KEY (id);


--
-- Name: species_texts species_texts_species_id_field_key; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.species_texts
    ADD CONSTRAINT species_texts_species_id_field_key UNIQUE (species_id, field);


--
-- Name: taxonomy taxonomy_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.taxonomy
    ADD CONSTRAINT taxonomy_pkey PRIMARY KEY (id);


--
-- Name: taxonomy taxonomy_wikidata_id_key; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.taxonomy
    ADD CONSTRAINT taxonomy_wikidata_id_key UNIQUE (wikidata_id);


--
-- Name: translations translations_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.translations
    ADD CONSTRAINT translations_pkey PRIMARY KEY (entity_type, entity_id, field);


--
-- Name: zoo_opening_hours zoo_opening_hours_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.zoo_opening_hours
    ADD CONSTRAINT zoo_opening_hours_pkey PRIMARY KEY (id);


--
-- Name: zoos zoos_pkey; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.zoos
    ADD CONSTRAINT zoos_pkey PRIMARY KEY (id);


--
-- Name: zoos zoos_slug_key; Type: CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.zoos
    ADD CONSTRAINT zoos_slug_key UNIQUE (slug);


--
-- Name: idx_device_sub_contributor; Type: INDEX; Schema: community; Owner: -
--

CREATE INDEX idx_device_sub_contributor ON community.device_subscriptions USING btree (contributor_id);


--
-- Name: idx_device_sub_zoo; Type: INDEX; Schema: community; Owner: -
--

CREATE INDEX idx_device_sub_zoo ON community.device_subscriptions USING btree (zoo_id);


--
-- Name: idx_proposals_contributor; Type: INDEX; Schema: community; Owner: -
--

CREATE INDEX idx_proposals_contributor ON community.change_proposals USING btree (contributor_id);


--
-- Name: idx_proposals_zoo_status; Type: INDEX; Schema: community; Owner: -
--

CREATE INDEX idx_proposals_zoo_status ON community.change_proposals USING btree (zoo_id, status);


--
-- Name: idx_release_items_release; Type: INDEX; Schema: community; Owner: -
--

CREATE INDEX idx_release_items_release ON community.release_items USING btree (release_id);


--
-- Name: idx_releases_zoo; Type: INDEX; Schema: community; Owner: -
--

CREATE INDEX idx_releases_zoo ON community.releases USING btree (zoo_id);


--
-- Name: idx_births_species_id; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_births_species_id ON zoo.births USING btree (species_id);


--
-- Name: idx_births_zoo_id; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_births_zoo_id ON zoo.births USING btree (zoo_id);


--
-- Name: idx_domains_global_name; Type: INDEX; Schema: zoo; Owner: -
--

CREATE UNIQUE INDEX idx_domains_global_name ON zoo.domains USING btree (name) WHERE (zoo_id IS NULL);


--
-- Name: idx_domains_zoo_id; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_domains_zoo_id ON zoo.domains USING btree (zoo_id);


--
-- Name: idx_domains_zoo_name; Type: INDEX; Schema: zoo; Owner: -
--

CREATE UNIQUE INDEX idx_domains_zoo_name ON zoo.domains USING btree (zoo_id, name) WHERE (zoo_id IS NOT NULL);


--
-- Name: idx_enclosures_zoo_id; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_enclosures_zoo_id ON zoo.enclosures USING btree (zoo_id);


--
-- Name: idx_feedback_contributor; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_feedback_contributor ON zoo.feedback USING btree (contributor_id);


--
-- Name: idx_feedback_created_at; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_feedback_created_at ON zoo.feedback USING btree (created_at DESC);


--
-- Name: idx_feedback_enclosure; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_feedback_enclosure ON zoo.feedback USING btree (enclosure_id) WHERE (enclosure_id IS NOT NULL);


--
-- Name: idx_feedback_text_aggregation; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_feedback_text_aggregation ON zoo.feedback USING btree (feedback_type_id, value_enrichment_text_id) WHERE (feedback_type_id = ANY (ARRAY[9, 10]));


--
-- Name: idx_feedback_text_rating_unique; Type: INDEX; Schema: zoo; Owner: -
--

CREATE UNIQUE INDEX idx_feedback_text_rating_unique ON zoo.feedback USING btree (feedback_type_id, value_enrichment_text_id, contributor_id) WHERE (feedback_type_id = ANY (ARRAY[9, 10]));


--
-- Name: idx_feedback_zoo_status; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_feedback_zoo_status ON zoo.feedback USING btree (zoo_id, status) WHERE ((status)::text = 'pending'::text);


--
-- Name: idx_geo_points_entity; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_geo_points_entity ON zoo.geo_points USING btree (entity_type, entity_id);


--
-- Name: idx_house_opening_hours_unique; Type: INDEX; Schema: zoo; Owner: -
--

CREATE UNIQUE INDEX idx_house_opening_hours_unique ON zoo.house_opening_hours USING btree (house_id, day_of_week);


--
-- Name: idx_locations_zoo_id; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_locations_zoo_id ON zoo.locations USING btree (zoo_id);


--
-- Name: idx_media_entity; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_media_entity ON zoo.media USING btree (entity_type, entity_id);


--
-- Name: idx_media_wikidata_id; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_media_wikidata_id ON zoo.media USING btree (wikidata_id) WHERE (wikidata_id IS NOT NULL);


--
-- Name: idx_media_zoo_id; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_media_zoo_id ON zoo.media USING btree (zoo_id);


--
-- Name: idx_opening_hours_loc_id; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_opening_hours_loc_id ON zoo.opening_hours USING btree (location_id);


--
-- Name: idx_opening_hours_unique; Type: INDEX; Schema: zoo; Owner: -
--

CREATE UNIQUE INDEX idx_opening_hours_unique ON zoo.opening_hours USING btree (location_id, day_of_week);


--
-- Name: idx_species_latin_name; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_species_latin_name ON zoo.species USING btree (latin_name) WHERE (latin_name IS NOT NULL);


--
-- Name: idx_species_texts_field; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_species_texts_field ON zoo.species_texts USING btree (field);


--
-- Name: idx_species_texts_species; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_species_texts_species ON zoo.species_texts USING btree (species_id);


--
-- Name: idx_species_wikidata_id; Type: INDEX; Schema: zoo; Owner: -
--

CREATE INDEX idx_species_wikidata_id ON zoo.species USING btree (wikidata_id) WHERE (wikidata_id IS NOT NULL);


--
-- Name: idx_species_wikidata_id_unique; Type: INDEX; Schema: zoo; Owner: -
--

CREATE UNIQUE INDEX idx_species_wikidata_id_unique ON zoo.species USING btree (wikidata_id) WHERE (wikidata_id IS NOT NULL);


--
-- Name: change_proposals change_proposals_zoo_id_fkey; Type: FK CONSTRAINT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.change_proposals
    ADD CONSTRAINT change_proposals_zoo_id_fkey FOREIGN KEY (zoo_id) REFERENCES zoo.zoos(id) ON DELETE CASCADE;


--
-- Name: device_subscriptions device_subscriptions_zoo_id_fkey; Type: FK CONSTRAINT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.device_subscriptions
    ADD CONSTRAINT device_subscriptions_zoo_id_fkey FOREIGN KEY (zoo_id) REFERENCES zoo.zoos(id) ON DELETE CASCADE;


--
-- Name: release_items release_items_proposal_id_fkey; Type: FK CONSTRAINT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.release_items
    ADD CONSTRAINT release_items_proposal_id_fkey FOREIGN KEY (proposal_id) REFERENCES community.change_proposals(id) ON DELETE CASCADE;


--
-- Name: release_items release_items_release_id_fkey; Type: FK CONSTRAINT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.release_items
    ADD CONSTRAINT release_items_release_id_fkey FOREIGN KEY (release_id) REFERENCES community.releases(id) ON DELETE CASCADE;


--
-- Name: releases releases_zoo_id_fkey; Type: FK CONSTRAINT; Schema: community; Owner: -
--

ALTER TABLE ONLY community.releases
    ADD CONSTRAINT releases_zoo_id_fkey FOREIGN KEY (zoo_id) REFERENCES zoo.zoos(id) ON DELETE CASCADE;


--
-- Name: births births_enclosure_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.births
    ADD CONSTRAINT births_enclosure_id_fkey FOREIGN KEY (enclosure_id) REFERENCES zoo.enclosures(id) ON DELETE SET NULL;


--
-- Name: births births_species_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.births
    ADD CONSTRAINT births_species_id_fkey FOREIGN KEY (species_id) REFERENCES zoo.species(id);


--
-- Name: births births_zoo_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.births
    ADD CONSTRAINT births_zoo_id_fkey FOREIGN KEY (zoo_id) REFERENCES zoo.zoos(id) ON DELETE CASCADE;


--
-- Name: domains domains_zoo_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.domains
    ADD CONSTRAINT domains_zoo_id_fkey FOREIGN KEY (zoo_id) REFERENCES zoo.zoos(id) ON DELETE CASCADE;


--
-- Name: enclosure_species enclosure_species_enclosure_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.enclosure_species
    ADD CONSTRAINT enclosure_species_enclosure_id_fkey FOREIGN KEY (enclosure_id) REFERENCES zoo.enclosures(id) ON DELETE CASCADE;

ALTER TABLE ONLY zoo.enclosure_species
    ADD CONSTRAINT enclosure_species_house_id_fkey FOREIGN KEY (house_id) REFERENCES zoo.houses(id) ON DELETE SET NULL;


--
-- Name: enclosure_species enclosure_species_species_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.enclosure_species
    ADD CONSTRAINT enclosure_species_species_id_fkey FOREIGN KEY (species_id) REFERENCES zoo.species(id) ON DELETE CASCADE;


--
-- Name: enclosures enclosures_domain_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.enclosures
    ADD CONSTRAINT enclosures_domain_id_fkey FOREIGN KEY (domain_id) REFERENCES zoo.domains(id) ON DELETE SET NULL;


--
-- Name: enclosures enclosures_house_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.enclosures
    ADD CONSTRAINT enclosures_house_id_fkey FOREIGN KEY (house_id) REFERENCES zoo.houses(id) ON DELETE SET NULL;


--
-- Name: enclosures enclosures_zoo_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.enclosures
    ADD CONSTRAINT enclosures_zoo_id_fkey FOREIGN KEY (zoo_id) REFERENCES zoo.zoos(id) ON DELETE CASCADE;


--
-- Name: feedback feedback_enclosure_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feedback
    ADD CONSTRAINT feedback_enclosure_id_fkey FOREIGN KEY (enclosure_id) REFERENCES zoo.enclosures(id) ON DELETE SET NULL;


--
-- Name: feedback feedback_feedback_type_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feedback
    ADD CONSTRAINT feedback_feedback_type_id_fkey FOREIGN KEY (feedback_type_id) REFERENCES zoo.feedback_types(id);


--
-- Name: feedback feedback_value_enrichment_text_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feedback
    ADD CONSTRAINT feedback_value_enrichment_text_id_fkey FOREIGN KEY (value_enrichment_text_id) REFERENCES zoo.species_texts(id) ON DELETE SET NULL;


--
-- Name: feedback feedback_value_report_reason_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feedback
    ADD CONSTRAINT feedback_value_report_reason_id_fkey FOREIGN KEY (value_report_reason_id) REFERENCES zoo.feedback_report_reasons(id);


--
-- Name: feedback feedback_value_species_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feedback
    ADD CONSTRAINT feedback_value_species_id_fkey FOREIGN KEY (value_species_id) REFERENCES zoo.species(id) ON DELETE SET NULL;


--
-- Name: feedback feedback_zoo_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feedback
    ADD CONSTRAINT feedback_zoo_id_fkey FOREIGN KEY (zoo_id) REFERENCES zoo.zoos(id) ON DELETE CASCADE;


--
-- Name: feeding_times feeding_times_enclosure_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feeding_times
    ADD CONSTRAINT feeding_times_enclosure_id_fkey FOREIGN KEY (enclosure_id) REFERENCES zoo.enclosures(id) ON DELETE CASCADE;


--
-- Name: feeding_times feeding_times_species_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.feeding_times
    ADD CONSTRAINT feeding_times_species_id_fkey FOREIGN KEY (species_id) REFERENCES zoo.species(id) ON DELETE SET NULL;


--
-- Name: house_opening_hours house_opening_hours_house_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.house_opening_hours
    ADD CONSTRAINT house_opening_hours_house_id_fkey FOREIGN KEY (house_id) REFERENCES zoo.houses(id) ON DELETE CASCADE;


--
-- Name: houses houses_zoo_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.houses
    ADD CONSTRAINT houses_zoo_id_fkey FOREIGN KEY (zoo_id) REFERENCES zoo.zoos(id) ON DELETE CASCADE;

ALTER TABLE ONLY zoo.houses
    ADD CONSTRAINT houses_domain_id_fkey FOREIGN KEY (domain_id) REFERENCES zoo.domains(id) ON DELETE SET NULL;


--
-- Name: location_species location_species_location_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.location_species
    ADD CONSTRAINT location_species_location_id_fkey FOREIGN KEY (location_id) REFERENCES zoo.locations(id) ON DELETE CASCADE;


--
-- Name: location_species location_species_species_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.location_species
    ADD CONSTRAINT location_species_species_id_fkey FOREIGN KEY (species_id) REFERENCES zoo.species(id) ON DELETE CASCADE;


--
-- Name: locations locations_domain_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.locations
    ADD CONSTRAINT locations_domain_id_fkey FOREIGN KEY (domain_id) REFERENCES zoo.domains(id) ON DELETE SET NULL;


--
-- Name: locations locations_location_type_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.locations
    ADD CONSTRAINT locations_location_type_id_fkey FOREIGN KEY (location_type_id) REFERENCES zoo.location_types(id);


--
-- Name: locations locations_zoo_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.locations
    ADD CONSTRAINT locations_zoo_id_fkey FOREIGN KEY (zoo_id) REFERENCES zoo.zoos(id) ON DELETE CASCADE;


--
-- Name: media media_zoo_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.media
    ADD CONSTRAINT media_zoo_id_fkey FOREIGN KEY (zoo_id) REFERENCES zoo.zoos(id) ON DELETE SET NULL;


--
-- Name: opening_hours opening_hours_location_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.opening_hours
    ADD CONSTRAINT opening_hours_location_id_fkey FOREIGN KEY (location_id) REFERENCES zoo.locations(id) ON DELETE CASCADE;


--
-- Name: species_texts species_texts_species_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.species_texts
    ADD CONSTRAINT species_texts_species_id_fkey FOREIGN KEY (species_id) REFERENCES zoo.species(id) ON DELETE CASCADE;


--
-- Name: zoo_opening_hours zoo_opening_hours_zoo_id_fkey; Type: FK CONSTRAINT; Schema: zoo; Owner: -
--

ALTER TABLE ONLY zoo.zoo_opening_hours
    ADD CONSTRAINT zoo_opening_hours_zoo_id_fkey FOREIGN KEY (zoo_id) REFERENCES zoo.zoos(id) ON DELETE CASCADE;


-- ============================================================================
-- Seed-Daten: Pflichteinträge für den Betrieb
-- ============================================================================

-- ── Feedback-Typen ───────────────────────────────────────────────────────────

INSERT INTO zoo.feedback_types
    (id, slug, label_de, entity_type, requires_admin_review, is_active)
VALUES
    (1,  'feeding_time',         'Fütterungszeit melden',          'enclosure', TRUE,  TRUE),
    (2,  'position',             'Position korrigieren',           'enclosure', TRUE,  TRUE),
    (3,  'new_species_wikidata', 'Neues Tier (Wikidata)',           'enclosure', TRUE,  TRUE),
    (4,  'species_missing',      'Tier nicht mehr vorhanden',      'enclosure', TRUE,  TRUE),
    (5,  'enclosure_name',       'Gehegename korrigieren',         'enclosure', TRUE,  TRUE),
    (6,  'zoo_info',             'Zoo-Information korrigieren',    'zoo',       TRUE,  TRUE),
    (7,  'opening_hours',        'Öffnungszeiten korrigieren',     'zoo',       TRUE,  TRUE),
    (8,  'report',               'Inhalt melden',                  'enclosure', TRUE,  TRUE),
    (9,  'text_helpful',         'Text hilfreich',                 'species',   FALSE, TRUE),
    (10, 'text_not_helpful',     'Text nicht hilfreich',           'species',   FALSE, TRUE)
ON CONFLICT (id) DO NOTHING;

SELECT setval(
    pg_get_serial_sequence('zoo.feedback_types', 'id'),
    GREATEST((SELECT MAX(id) FROM zoo.feedback_types), 10)
);

-- ── Feedback-Report-Reasons (für Typ 8 "report") ─────────────────────────────

INSERT INTO zoo.feedback_report_reasons
    (id, slug, label_de)
VALUES
    (1, 'incorrect_info', 'Falsche Information'),
    (2, 'offensive',      'Anstößiger Inhalt'),
    (3, 'outdated',       'Veraltete Information'),
    (4, 'other',          'Sonstiges')
ON CONFLICT (id) DO NOTHING;

SELECT setval(
    pg_get_serial_sequence('zoo.feedback_report_reasons', 'id'),
    GREATEST((SELECT MAX(id) FROM zoo.feedback_report_reasons), 4)
);

--
-- PostgreSQL database dump complete
--

--
-- Data for location_types
--

INSERT INTO zoo.location_types (slug, name, icon, sort_order) VALUES
  ('wc',                  'WC',                   'restroom',       1),
  ('wickelraum',          'Wickelraum',            'baby-carriage',  2),
  ('spielplatz',          'Spielplatz',            'playground',     3),
  ('restaurant',          'Restaurant',            'fork-knife',     4),
  ('kiosk',               'Kiosk',                 'coffee',         5),
  ('eis',                 'Eis',                   'ice-cream',      6),
  ('shop',                'Shop',                  'shopping-bag',   7),
  ('eingang',             'Eingang',               'door-enter',     8),
  ('ausgang',             'Ausgang',               'door-exit',      9),
  ('backstube',           'Backstube',             'bread',          10),
  ('museum',              'Museum',                'building',       11),
  ('attraktion',          'Attraktion',            'star',           12),
  ('service',             'Service',               'tool',           13),
  ('aussichtsplattform',  'Aussichtsplattform',    'binoculars',     15),
  ('behindertentoilette', 'Behindertentoilette',   'accessible',     3),
  ('sonstiges',           'Sonstiges',             'dots',           99);

CREATE UNIQUE INDEX uq_geo_points_entity ON zoo.geo_points (entity_type, entity_id);

-- Media FK constraints (migration Juni 2026)
ALTER TABLE ONLY zoo.species
    ADD CONSTRAINT species_icon_media_id_fkey FOREIGN KEY (icon_media_id) REFERENCES zoo.media(id) ON DELETE SET NULL;

ALTER TABLE ONLY zoo.location_types
    ADD CONSTRAINT location_types_icon_media_id_fkey FOREIGN KEY (icon_media_id) REFERENCES zoo.media(id) ON DELETE SET NULL;

ALTER TABLE ONLY zoo.locations
    ADD CONSTRAINT locations_icon_media_id_fkey FOREIGN KEY (icon_media_id) REFERENCES zoo.media(id) ON DELETE SET NULL;

ALTER TABLE ONLY zoo.locations
    ADD CONSTRAINT locations_image_media_id_fkey FOREIGN KEY (image_media_id) REFERENCES zoo.media(id) ON DELETE SET NULL;

ALTER TABLE ONLY zoo.enclosures
    ADD CONSTRAINT enclosures_image_media_id_fkey FOREIGN KEY (image_media_id) REFERENCES zoo.media(id) ON DELETE SET NULL;

ALTER TABLE ONLY zoo.houses
    ADD CONSTRAINT houses_image_media_id_fkey FOREIGN KEY (image_media_id) REFERENCES zoo.media(id) ON DELETE SET NULL;

CREATE INDEX idx_species_icon_media ON zoo.species (icon_media_id) WHERE icon_media_id IS NOT NULL;
CREATE INDEX idx_locations_icon_media ON zoo.locations (icon_media_id) WHERE icon_media_id IS NOT NULL;
CREATE INDEX idx_locations_image_media ON zoo.locations (image_media_id) WHERE image_media_id IS NOT NULL;
CREATE INDEX idx_enclosures_image_media ON zoo.enclosures (image_media_id) WHERE image_media_id IS NOT NULL;
CREATE INDEX idx_houses_image_media ON zoo.houses (image_media_id) WHERE image_media_id IS NOT NULL;
