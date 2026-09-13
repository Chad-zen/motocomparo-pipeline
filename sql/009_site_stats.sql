-- Per-product aggregates the site reads on every listing page.
--
-- Counting merchants per product means scanning the 763k linked offers; doing
-- that on every page view would make the site feel exactly as slow as v1. It is
-- computed once, after a pipeline run, and read as a plain table afterwards.
--
-- Refresh: SELECT refresh_product_stats();  (called at the end of `freshness`)

CREATE MATERIALIZED VIEW IF NOT EXISTS product_stats AS
SELECT o.product_id,
       count(DISTINCT o.merchant_id)::smallint                      AS merchant_count,
       count(*)::int                                                AS offer_count,
       min(o.price) FILTER (WHERE o.in_stock IS NOT FALSE)          AS cheapest,
       max(o.price)                                                 AS dearest,
       (array_agg(o.image_url ORDER BY o.merchant_id)
            FILTER (WHERE o.image_url IS NOT NULL AND o.image_url <> ''))[1] AS image_url,
       -- The title shown on the site, taken verbatim from one merchant.
       --
       -- `product.model_display` is the identity token bag: sorted, stripped and
       -- order-free on purpose, which is what makes matching work and what makes
       -- it unreadable ("3 Blouson Hyperspeed It Rev"). It is a fingerprint, not
       -- a name, and it must never reach a page.
       --
       -- The order below is the owner's, and it is editorial rather than
       -- technical: Motoblouz first, then Speedway, La Bécanerie, FC-Moto. The
       -- two synthetic-GTIN merchants come last — their catalogues are the least
       -- carefully written and they are only a fallback.
       (array_agg(o.raw_title ORDER BY
            CASE m.code
                WHEN 'motoblouz'   THEN 1
                WHEN 'speedway'    THEN 2
                WHEN 'labecanerie' THEN 3
                WHEN 'fcmoto'      THEN 4
                WHEN 'maxxess'     THEN 5
                ELSE 6
            END)
            FILTER (WHERE o.raw_title IS NOT NULL AND o.raw_title <> ''))[1] AS best_title
FROM raw_offer o
JOIN merchant m ON m.id = o.merchant_id
WHERE o.linked_status = 'linked' AND o.is_live AND o.product_id IS NOT NULL
GROUP BY o.product_id;

-- the unique index is what allows REFRESH ... CONCURRENTLY (no read lock)
CREATE UNIQUE INDEX IF NOT EXISTS product_stats_pk ON product_stats (product_id);
CREATE INDEX IF NOT EXISTS product_stats_browse_idx ON product_stats (merchant_count, cheapest);

CREATE OR REPLACE FUNCTION refresh_product_stats() RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY product_stats;
EXCEPTION WHEN OTHERS THEN
    -- CONCURRENTLY refuses on a never-populated view; fall back once
    REFRESH MATERIALIZED VIEW product_stats;
END;
$$ LANGUAGE plpgsql;
