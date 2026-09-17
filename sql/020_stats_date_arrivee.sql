-- La date d'arrivée d'une fiche, portée par `product_stats`.
--
-- POURQUOI PAS `product.created_at`. Elle vaut le 14/09/2026 pour les 313 435
-- fiches : c'est le jour où la table a été reconstruite, pas une date de
-- nouveauté. Un tri « Nouveautés » branché dessus aurait rendu les fiches dans
-- un ordre arbitraire, avec l'air d'un tri juste — le genre de faux qui ne se
-- voit pas à l'écran.
--
-- La vraie date d'arrivée est celle de la première offre vue. Elle se calcule
-- déjà, fiche par fiche, pour la rangée « Nouveautés » de l'accueil ; mais un
-- TRI la demande pour toutes les fiches d'un rayon à la fois, et une
-- sous-requête corrélée sur 763 570 offres n'a pas sa place dans un ORDER BY
-- de page de résultats. Elle est donc agrégée une fois, là où le sont déjà le
-- nombre de marchands et le prix le plus bas.
--
-- ⚠️ La vue est RECRÉÉE, pas modifiée : `CREATE MATERIALIZED VIEW IF NOT
-- EXISTS` ne touche pas une vue existante, et il n'y a pas d'ALTER pour
-- ajouter une colonne à une vue matérialisée. La supprimer emporte ses index,
-- qui sont donc tous rétablis ici — y compris `product_stats_titre_trgm`, qui
-- vient de la migration 018 et que le site utilise à chaque frappe dans la
-- barre de recherche. L'oublier ne casse rien de visible : la recherche
-- balaierait simplement 311 000 lignes à chaque lettre.
--
-- ⚠️ Pendant la recréation, les pages de résultats n'ont plus de vue à lire.
-- Sur le VPS, à lancer hors des heures de visite — et jamais pendant la chaîne
-- quotidienne de 04:04, qui la rafraîchit.
--
-- ⚠️⚠️ ET SURTOUT : LE PROPRIÉTAIRE. Une vue recréée appartient à CELUI QUI LA
-- RECRÉE. Appliquée en `sudo -u postgres`, cette migration a rendu la vue
-- propriété de `postgres` alors que tout le reste du schéma appartient au rôle
-- de l'application — et le site entier est passé en 500 :
--
--     psycopg.errors.InsufficientPrivilege:
--     permission denied for materialized view product_stats
--
-- Sur toutes les pages, immédiatement, y compris l'accueil : `categories()`
-- lit cette vue. Aucune des 239 vérifications automatiques ne pouvait l'attraper,
-- parce qu'en local la migration est appliquée par le rôle qui possède déjà
-- tout. C'est un défaut qui n'existe QUE là où on déploie.
--
-- Le propriétaire est donc repris de `product`, table du pipeline qui appartient
-- toujours au bon rôle. Lu, jamais écrit en dur : le rôle ne porte pas le même
-- nom sur le poste de la propriétaire et sur le VPS.

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
WHERE o.linked_status = 'linked' AND o.is_live AND o.product_id IS NOT NULL
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
