-- Per-offer category correction, written by `mcpipe enrich`.
--
-- Why a dedicated table and not a bigger `category_map`: `category_map` is a
-- (merchant, raw_path) cache — one row per feed category, shared by every
-- offer under it. The coarse-bucket problem is the opposite: offers sharing
-- ONE feed category (e.g. FC-Moto `tops`) need DIFFERENT real categories, read
-- from each offer's own title. That is a per-offer decision, so it needs a
-- per-offer store. `match._COMPUTE_OFFER_IDENTITY` reads this first, ahead of
-- `category_map`, so a correction here flows into every merge decision.
--
-- Derived data: `enrich` truncates and rebuilds it. It has no FK pointing at
-- `product`, so `reset_match_state()` never touches it and it survives a
-- `match --reset`.

CREATE TABLE IF NOT EXISTS offer_category_override (
    raw_offer_id bigint PRIMARY KEY REFERENCES raw_offer(id) ON DELETE CASCADE,
    category_id  smallint NOT NULL REFERENCES category(id),
    source       text NOT NULL,          -- 'title_reclass'
    confidence   numeric(3, 2) NOT NULL DEFAULT 0,
    created_at   timestamptz NOT NULL DEFAULT now()
);
