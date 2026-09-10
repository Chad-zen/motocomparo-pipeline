-- ============================================================================
-- mcpipe core schema  (PostgreSQL 18)
--
-- Grain: one `product` = brand x model x model_year x colourway x genre.
-- Size is a `variant`, never part of product identity.
-- Merchant listings are `raw_offer` rows, linked to one or more variants.
--
-- Safe to run more than once (every object is IF NOT EXISTS).
-- Run with:  psql "$DATABASE_URL" -f sql/001_schema.sql
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- trigram similarity for fuzzy matching
CREATE EXTENSION IF NOT EXISTS unaccent;   -- accent folding

-- ---------------------------------------------------------------------------
-- reference
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS merchant (
    id               smallint PRIMARY KEY,
    code             text NOT NULL UNIQUE,          -- 'speedway', 'motoblouz', ...
    platform         text NOT NULL,                 -- 'effinity' | 'netaffiliation'
    gtin_trust       text NOT NULL CHECK (gtin_trust IN ('trusted', 'synthetic')),
    reliability_rank smallint NOT NULL,             -- 1 = most trusted
    active           boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS category (
    id        smallint PRIMARY KEY,
    parent_id smallint REFERENCES category(id),
    code      text NOT NULL UNIQUE,   -- 'helmet.integral', 'helmet.jet', 'jacket', ...
    label_fr  text NOT NULL
);

-- merchant's raw (l1 > l2 > l3) category path -> our internal category
CREATE TABLE IF NOT EXISTS category_map (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    merchant_id   smallint NOT NULL REFERENCES merchant(id),
    raw_path      text NOT NULL,                    -- 'Casques>Casques integraux>...'
    category_id   smallint REFERENCES category(id),
    confidence    numeric(3, 2) NOT NULL DEFAULT 1.00,
    UNIQUE (merchant_id, raw_path)
);

-- ---------------------------------------------------------------------------
-- ingestion bookkeeping
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS feed_run (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    merchant_id    smallint NOT NULL REFERENCES merchant(id),
    started_at     timestamptz NOT NULL DEFAULT now(),
    finished_at    timestamptz,
    status         text NOT NULL DEFAULT 'running'  -- running | ok | failed
                       CHECK (status IN ('running', 'ok', 'failed')),
    row_count      integer,
    gtin_drift     numeric(4, 3),   -- fraction of GTINs unseen vs previous run
    note           text
);
CREATE INDEX IF NOT EXISTS feed_run_merchant_idx ON feed_run (merchant_id, started_at DESC);

-- ---------------------------------------------------------------------------
-- canonical products  (created before raw_offer so raw_offer can point at it)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS product (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    brand_code     text NOT NULL,
    category_id    smallint NOT NULL REFERENCES category(id),
    model_core_ref text,                              -- stable anchor: 'rpha12', 'ff807'
    model_display  text NOT NULL,
    colour_code    text NOT NULL DEFAULT 'unknown',   -- 'unknown' blocks publish
    model_year     smallint,
    genre_age      text NOT NULL DEFAULT 'adult',
    identity_hash  text NOT NULL,
    slug           text NOT NULL UNIQUE,              -- frozen at creation, never recomputed
    status         text NOT NULL DEFAULT 'draft'
                       CHECK (status IN ('draft', 'published', 'stale', 'merged')),
    merged_into    bigint REFERENCES product(id),
    min_price      numeric(10, 2),
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT product_identity_uq UNIQUE (identity_hash)
);
CREATE INDEX IF NOT EXISTS product_lookup_idx ON product (brand_code, category_id, model_core_ref)
    WHERE model_core_ref IS NOT NULL;

-- every identity_hash a product has ever had -> lets re-normalization re-attach
-- instead of forking a new product (keeps URLs stable)
CREATE TABLE IF NOT EXISTS product_identity_alias (
    identity_hash text PRIMARY KEY,
    product_id    bigint NOT NULL REFERENCES product(id),
    reason        text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- raw offers  (persistent, one row per merchant SKU, upserted every run)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS raw_offer (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    merchant_id     smallint NOT NULL REFERENCES merchant(id),
    merchant_sku    text NOT NULL,          -- feed's stable id, or md5(deeplink) when it has none
    raw_gtin        text,                   -- kept for trusted merchants; ignored for synthetic
    raw_title       text NOT NULL,
    raw_brand       text,
    raw_color       text,
    raw_size        text,
    raw_mpn         text,
    raw_item_group  text,
    raw_category    text,
    deeplink        text NOT NULL,
    image_url       text,
    first_seen      timestamptz NOT NULL DEFAULT now(),
    last_seen       timestamptz NOT NULL DEFAULT now(),
    is_live         boolean NOT NULL DEFAULT true,
    linked_status   text NOT NULL DEFAULT 'unresolved'
                        CHECK (linked_status IN ('unresolved', 'linked', 'quarantined', 'rejected')),
    product_id      bigint REFERENCES product(id),
    link_method     text,                  -- 'gtin_exact' | 'item_group' | 'base_sku' | 'fuzzy' | 'operator'
    link_confidence numeric(4, 3),
    UNIQUE (merchant_id, merchant_sku)
);
CREATE INDEX IF NOT EXISTS raw_offer_gtin_idx    ON raw_offer (raw_gtin) WHERE raw_gtin IS NOT NULL;
CREATE INDEX IF NOT EXISTS raw_offer_status_idx  ON raw_offer (linked_status);
CREATE INDEX IF NOT EXISTS raw_offer_product_idx ON raw_offer (product_id) WHERE linked_status = 'linked';
CREATE INDEX IF NOT EXISTS raw_offer_title_trgm  ON raw_offer USING gin (raw_title gin_trgm_ops);

-- one computed signature per raw_offer (successor of v1's wp_mc_psig)
CREATE TABLE IF NOT EXISTS offer_signature (
    raw_offer_id     bigint PRIMARY KEY REFERENCES raw_offer(id) ON DELETE CASCADE,
    brand_code       text,
    model_core_ref   text,            -- stable anchor token: 'rpha12', 'ff807'
    model_tokens     text[] NOT NULL DEFAULT '{}',
    model_strength   text CHECK (model_strength IN ('strong', 'medium', 'weak', 'empty')),
    primary_colour   text,
    colour_conf      numeric(3, 2) NOT NULL DEFAULT 0,
    colour_source    text,            -- 'feed' | 'xmerchant_gtin' | 'title' | 'base_sku' | 'none'
    size_code        text,
    size_source      text,
    genre_age        text,
    model_year       smallint,        -- NULL = unspecified
    base_sku         text,            -- mpn minus trailing size token (Motoblouz)
    category_id      smallint REFERENCES category(id),
    identity_hash    text,            -- md5 of the stable identity tuple, see docs
    norm_txt         text NOT NULL,
    computed_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS offer_signature_identity_idx ON offer_signature (identity_hash);
CREATE INDEX IF NOT EXISTS offer_signature_basesku_idx  ON offer_signature (base_sku) WHERE base_sku IS NOT NULL;

-- ---------------------------------------------------------------------------
-- variants (sizes) + the offer<->variant link
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS variant (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id bigint NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    size_code  text NOT NULL,
    UNIQUE (product_id, size_code)
);

CREATE TABLE IF NOT EXISTS offer_variant_link (
    raw_offer_id bigint NOT NULL REFERENCES raw_offer(id) ON DELETE CASCADE,
    variant_id   bigint NOT NULL REFERENCES variant(id) ON DELETE CASCADE,
    PRIMARY KEY (raw_offer_id, variant_id)
);

-- ---------------------------------------------------------------------------
-- price history  (append-only, one row per observed price change)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS price_history (
    raw_offer_id bigint NOT NULL REFERENCES raw_offer(id) ON DELETE CASCADE,
    observed_on  date NOT NULL,
    price        numeric(10, 2) NOT NULL,
    in_stock     boolean,
    PRIMARY KEY (raw_offer_id, observed_on)
);

-- ---------------------------------------------------------------------------
-- decisions:  ambiguous matches go here, never guessed
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS match_review_queue (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind                  text NOT NULL,          -- 'base_sku_weak_colour', 'fuzzy_candidate', ...
    review_key            text NOT NULL,
    raw_offer_ids         bigint[] NOT NULL,
    candidate_product_ids bigint[] NOT NULL DEFAULT '{}',
    signals               jsonb NOT NULL,         -- the scores that led here
    priority              smallint NOT NULL DEFAULT 5,
    status                text NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending', 'resolved', 'skipped')),
    verdict               jsonb,
    resolved_at           timestamptz,
    UNIQUE (kind, review_key)
);
CREATE INDEX IF NOT EXISTS match_review_pending_idx ON match_review_queue (status, priority);

-- operator decisions that must survive every future feed run
CREATE TABLE IF NOT EXISTS match_override (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scope            text NOT NULL CHECK (scope IN ('sku', 'gtin', 'base_sku', 'identity_hash')),
    merchant_id      smallint REFERENCES merchant(id),
    key_value        text NOT NULL,
    force_product_id bigint REFERENCES product(id),
    is_split         boolean NOT NULL DEFAULT false,  -- true = these must never merge
    note             text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (scope, merchant_id, key_value)
);
