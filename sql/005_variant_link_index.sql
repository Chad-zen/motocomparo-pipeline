-- ============================================================================
-- 005 — index the FK column `match`'s reset routine was missing.
--
-- offer_variant_link's only index was its PK (raw_offer_id, variant_id) —
-- variant_id isn't the leading column, so a DELETE FROM variant had no usable
-- index for the ON DELETE CASCADE check and fell back to a full scan of
-- offer_variant_link per row deleted. Safe to run more than once.
-- ============================================================================

CREATE INDEX IF NOT EXISTS offer_variant_link_variant_idx ON offer_variant_link (variant_id);
