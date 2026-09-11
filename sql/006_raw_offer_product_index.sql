-- ============================================================================
-- 006 — a non-partial index on raw_offer.product_id.
--
-- The existing `raw_offer_product_idx` is partial (`WHERE linked_status =
-- 'linked'`), so it cannot be used for the FK-check scan a plain
-- `DELETE FROM product` needs (that check has no linked_status predicate —
-- it must confirm no raw_offer row references the product id, across every
-- status). Without a usable index, that FK check falls back to a full scan
-- of raw_offer per deleted product row — the same class of bug fixed in
-- sql/005, this time on `product`'s other referencing table.
-- Safe to run more than once.
-- ============================================================================

CREATE INDEX IF NOT EXISTS raw_offer_product_id_idx ON raw_offer (product_id);
