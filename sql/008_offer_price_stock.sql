-- Current price and availability on each offer.
--
-- These were never extracted: `normalize` was deliberately scoped to identity
-- (who is this product), and the price (what does it cost) was left for phase 3.
-- Every one of the 6 feeds carries both — `feeds.py` already maps the columns.
--
-- Same raw/clean convention the barcode columns use: keep what the merchant
-- actually sent next to our reading of it, so a parsing mistake is always
-- diagnosable after the fact instead of silently lost.
--
-- `price_history` (sql/001) stays the append-only record of what was observed
-- on a given day; these columns are "what it costs right now".

ALTER TABLE raw_offer
    ADD COLUMN IF NOT EXISTS raw_price        text,           -- verbatim, e.g. '64.99 EUR'
    ADD COLUMN IF NOT EXISTS price            numeric(10, 2), -- parsed
    ADD COLUMN IF NOT EXISTS currency         text,           -- ISO code when stated
    ADD COLUMN IF NOT EXISTS raw_availability text,           -- verbatim, e.g. 'flux tendu'
    ADD COLUMN IF NOT EXISTS in_stock         boolean;        -- NULL = merchant did not say

-- publish and freshness both start from "live offers of this product, cheapest
-- first"; without this that is a sequential scan of 763k rows per product.
CREATE INDEX IF NOT EXISTS raw_offer_product_price_idx
    ON raw_offer (product_id, price)
    WHERE linked_status = 'linked' AND price IS NOT NULL;
