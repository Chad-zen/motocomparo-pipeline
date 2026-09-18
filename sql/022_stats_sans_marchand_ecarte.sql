-- `product_stats` cesse de compter les marchands mis de côté.
--
-- Suite de la migration 021, qui a créé `merchant.affiche`. Le drapeau ne
-- servait à rien tant que la vue continuait à agréger tout le monde : le site
-- lit `product_stats` pour le prix affiché, l'écart et le nombre de marchands.
--
-- CE QUE ÇA COÛTE, mesuré avant d'écrire (18/09/2026, en écartant
-- La Bécanerie) :
--
--     28 365 fiches comparables avant
--     21 944 le restent
--      6 421 disparaissent — elles n'avaient que lui et un autre
--      1 251 changent de prix affiché, et le prix MONTE dans 1 251 cas sur
--            1 251 : il était le moins cher partout où il comptait, et ce
--            prix était faux.
--
-- Les 6 421 fiches perdues reposaient sur une comparaison avec une source
-- morte. Ce n'étaient pas des comparaisons.
--
-- ⚠️ MÊMES PRÉCAUTIONS QUE LA MIGRATION 020, et pour la même raison : recréer
-- cette vue l'a fait changer de propriétaire le 17/09 et le site entier est
-- passé en 500. Le propriétaire est repris de `product` et vérifié plus bas.
-- Les index sont tous rétablis, y compris le trigramme de la recherche.

DROP MATERIALIZED VIEW IF EXISTS product_stats;

CREATE MATERIALIZED VIEW product_stats AS
SELECT o.product_id,
       count(DISTINCT o.merchant_id)::smallint                      AS merchant_count,
       count(*)::int                                                AS offer_count,
       min(o.price) FILTER (WHERE o.in_stock IS NOT FALSE)          AS cheapest,
       max(o.price)                                                 AS dearest,
       -- Le jour où cette fiche est apparue au catalogue : la première fois
       -- qu'une de ses offres a été vue. `::date` parce que l'heure ne veut
       -- rien dire ici — une fiche arrive le jour où le flux l'apporte.
       min(o.first_seen)::date                                      AS vu_le,
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
-- `m.affiche` : un marchand mis de côté n'entre plus dans AUCUN agrégat —
-- ni le prix le plus bas, ni le plus haut, ni le nombre de marchands
-- comparés, ni le titre retenu. Filtrer plus tard, à l'affichage, aurait
-- laissé un « 3 marchands » sur une fiche qui n'en montre que deux : le
-- genre d'incohérence qu'un visiteur remarque et qu'aucune erreur ne signale.
WHERE o.linked_status = 'linked' AND o.is_live AND o.product_id IS NOT NULL
  AND m.affiche
GROUP BY o.product_id;

-- the unique index is what allows REFRESH ... CONCURRENTLY (no read lock)
CREATE UNIQUE INDEX product_stats_pk ON product_stats (product_id);
CREATE INDEX product_stats_browse_idx ON product_stats (merchant_count, cheapest);
-- Rétabli depuis la migration 018. L'expression doit être EXACTEMENT celle que
-- la requête emploie, sinon PostgreSQL l'ignore en silence.
CREATE INDEX product_stats_titre_trgm
    ON product_stats USING gin (f_recherche(best_title) gin_trgm_ops);
-- Le tri « Nouveautés ».
CREATE INDEX product_stats_nouveaute_idx
    ON product_stats (vu_le DESC NULLS LAST, merchant_count DESC);

-- Le propriétaire, repris de `product` — voir l'avertissement en tête.
DO $$
DECLARE proprietaire text;
BEGIN
    SELECT pg_get_userbyid(relowner) INTO proprietaire
    FROM pg_class WHERE relname = 'product' AND relkind = 'r';
    IF proprietaire IS NULL THEN
        RAISE EXCEPTION 'table product introuvable : propriétaire indéterminable';
    END IF;
    EXECUTE format('ALTER MATERIALIZED VIEW product_stats OWNER TO %I', proprietaire);
    EXECUTE format('ALTER FUNCTION refresh_product_stats() OWNER TO %I', proprietaire);
END $$;

-- Et on vérifie, plutôt que de supposer : la migration échoue bruyamment ici
-- si la vue n'appartient pas au même rôle que la table dont elle dérive.
DO $$
BEGIN
    IF (SELECT pg_get_userbyid(relowner) FROM pg_class WHERE relname = 'product_stats')
       IS DISTINCT FROM
       (SELECT pg_get_userbyid(relowner) FROM pg_class
        WHERE relname = 'product' AND relkind = 'r')
    THEN
        RAISE EXCEPTION 'product_stats n''appartient pas au rôle de product';
    END IF;
END $$;

ANALYZE product_stats;
