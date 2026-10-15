-- Apprendre au planificateur que la marque et le rayon sont liés.
--
-- Postgres estime « rayon = bottes ET marque = sidi » en multipliant les deux
-- fréquences, comme si elles étaient indépendantes : 11 fiches attendues, 568
-- en réalité — Sidi ne fait presque que des bottes. Sur cette estimation, il
-- recalculait la sous-requête Matière (20 000 lignes) une fois PAR fiche
-- retenue au lieu d'une seule fois : 2,5 millions de lectures, 10 s pour une
-- seule facette, puis le délai de 15 s dépassé et une erreur 500 dès qu'on
-- cochait deux marques (relevé en production le 15/10/2026).
--
-- Une statistique étendue sur le couple ne change aucune requête ni aucun
-- résultat : elle corrige l'estimation, et donc le plan. Elle est tenue à
-- jour par l'ANALYZE automatique comme les autres. Retrait : DROP STATISTICS.

CREATE STATISTICS IF NOT EXISTS product_categorie_marque_stats
    (dependencies, ndistinct, mcv) ON category_id, brand_code FROM product;

ANALYZE product;
