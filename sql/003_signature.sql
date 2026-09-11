-- ============================================================================
-- 003 — offer_signature: one extra column the review agents' step 1 needs.
--
-- `is_pack` (pack / lot / bundle vs a single item) is a hard matching boundary:
-- a pack is never merged with the unit. Kept on the signature so `match` reads
-- it without re-parsing the title.
--
-- Safe to run more than once.
-- ============================================================================

ALTER TABLE offer_signature ADD COLUMN IF NOT EXISTS is_pack boolean NOT NULL DEFAULT false;
