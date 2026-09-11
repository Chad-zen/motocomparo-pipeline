-- ============================================================================
-- 004 — three columns the post-audit fixes need. Safe to run more than once.
--
--  raw_offer.gtin           validated GS1 barcode (raw_gtin stays verbatim);
--                           this is what `match` joins on.
--  raw_offer.raw_gender     feed gender/age, kept verbatim like the other raw_*
--  raw_offer.raw_age_group
--  offer_signature.brand_known  was the brand in the alias table? gates auto-merge
-- ============================================================================

ALTER TABLE raw_offer ADD COLUMN IF NOT EXISTS gtin          text;
ALTER TABLE raw_offer ADD COLUMN IF NOT EXISTS raw_gender    text;
ALTER TABLE raw_offer ADD COLUMN IF NOT EXISTS raw_age_group text;

-- match joins on the validated column, not the verbatim one
CREATE INDEX IF NOT EXISTS raw_offer_gtin_valid_idx ON raw_offer (gtin) WHERE gtin IS NOT NULL;

ALTER TABLE offer_signature ADD COLUMN IF NOT EXISTS brand_known boolean NOT NULL DEFAULT false;
