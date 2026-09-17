-- Deux index pour les rangées « Nouveautés » et « Ça a baissé » de l'accueil.
--
-- Sans eux, les deux requêtes mettaient 5,1 s et 7,2 s (mesuré le 17/09/2026) :
-- l'accueil entier serait passé à 14 s à chaque expiration de son cache — pas
-- pour le visiteur, qui lit une page gardée, mais pour le malchanceux qui
-- arrive juste après. Aucune des deux colonnes n'était indexée.
--
--   * `first_seen` : la rangée « Nouveautés » cherche les offres apparues
--     APRÈS le versement initial. Elles sont 10 187 sur 763 570, soit 1,3 % —
--     exactement la forme qu'un index sert, et que le parcours complet ignore.
--
--   * `observed_on` : `price_history` a sa clé primaire sur
--     (raw_offer_id, observed_on), dans cet ordre. Une requête qui ne connaît
--     que le jour ne peut pas s'en servir : la colonne de tête manque. D'où un
--     parcours des 2,3 millions de lignes pour en retenir un jour.
--
-- Les deux sont créés en CONCURRENTLY sur le VPS — voir la note plus bas.

CREATE INDEX IF NOT EXISTS raw_offer_first_seen_idx
    ON raw_offer (first_seen);

CREATE INDEX IF NOT EXISTS price_history_observed_on_idx
    ON price_history (observed_on);

-- ⚠️ Sur le VPS, la base est servie pendant la migration et un CREATE INDEX
-- ordinaire pose un verrou qui bloque les écritures de la chaîne quotidienne.
-- Y appliquer plutôt, hors transaction :
--
--     CREATE INDEX CONCURRENTLY raw_offer_first_seen_idx ON raw_offer (first_seen);
--     CREATE INDEX CONCURRENTLY price_history_observed_on_idx ON price_history (observed_on);
--     ANALYZE raw_offer;
--     ANALYZE price_history;
--
-- L'ANALYZE n'est pas décoratif : trois pannes du 14/09 venaient de
-- statistiques périmées après une réécriture de masse.
ANALYZE raw_offer;
ANALYZE price_history;
