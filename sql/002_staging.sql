-- ============================================================================
-- staging: the raw feed, landed as-is, one JSONB object per line.
--
-- We don't declare a column per merchant field (Effinity feeds carry 73, most
-- of them junk). We keep the whole row and let `normalize` pick what it needs.
-- Truncated per merchant at the start of each load.
-- ============================================================================

CREATE TABLE IF NOT EXISTS stg_feed_row (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    feed_run_id  bigint NOT NULL REFERENCES feed_run(id),
    merchant_id  smallint NOT NULL REFERENCES merchant(id),
    row          jsonb NOT NULL,
    loaded_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS stg_feed_row_merchant_idx ON stg_feed_row (merchant_id);
