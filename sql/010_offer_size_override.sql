-- Per-offer size correction, borrowed from another merchant selling the same
-- barcode. Written by `mcpipe enrich`, read by `match` when it builds variants.
--
-- Why this exists: four of the six merchants never send a size column. The
-- pipeline recovers one from the manufacturer reference when it is there
-- (Motoblouz `HAN = 100101026-9001-M`), but the Arai SZ-R ships as
-- `HAN = 8009013011` and nothing in that feed distinguishes its four offers
-- except the barcode. They all collapse into the shared `TU` bucket, the page
-- then shows the same merchant four times with no size, and the price spread it
-- prints is a comparison between an unknown size and a known one.
--
-- A GTIN identifies one article in one size. So the size is not unknown — it is
-- written next door, on the same barcode, by a merchant who does declare it.
--
-- NOT truncated between runs, unlike `offer_category_override`. A borrowed size
-- depends on a donor still being live; if that donor leaves the feed, dropping
-- the value would move the offer back to `TU`, change its variant and move the
-- per-size price, with no merchant data having changed. The row therefore
-- sticks, and `confirmed_at` records the last run that could still prove it.
--
-- No FK to `product`, so `reset_match_state()` never touches it.

CREATE TABLE IF NOT EXISTS offer_size_override (
    raw_offer_id bigint PRIMARY KEY REFERENCES raw_offer(id) ON DELETE CASCADE,
    size_code    text NOT NULL,
    -- which rule decided, so a suspect correction can be traced back
    source       text NOT NULL,
    -- how many merchants agreed, and which: an audit trail for a borrowed value
    donor_count  smallint NOT NULL,
    donor_codes  text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    confirmed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS offer_size_override_source_idx ON offer_size_override (source);
