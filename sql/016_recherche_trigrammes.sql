-- La recherche : rendre le texte indexable.
--
-- `unaccent(model_display) ILIKE '%mot%'` ne peut utiliser AUCUN index : le
-- joker en tête interdit un parcours d'arbre, et `unaccent` est déclarée STABLE
-- — donc inutilisable dans une expression indexée. PostgreSQL balaie les
-- 313 000 fiches, pour chaque mot cherché, dans CHACUNE des cinq requêtes du
-- panneau de filtres.
--
-- Mesuré le 2026-09-14 : 1,1 s pour la liste, 4,6 s pour les facettes, 11,5 s
-- pour la page complète au premier appel.
--
-- Deux pièces :
--   1. `f_unaccent` — la même fonction, déclarée IMMUTABLE. C'est exact ici :
--      le dictionnaire `unaccent` ne change pas en cours de route. PostgreSQL
--      refuse d'indexer sans cette promesse, et c'est la manière recommandée
--      de la lui faire.
--   2. Un index GIN de trigrammes. Il découpe le texte en groupes de trois
--      lettres, ce qui rend « %ixon% » cherchable comme une clé.

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE OR REPLACE FUNCTION f_unaccent(text)
RETURNS text
LANGUAGE sql
IMMUTABLE PARALLEL SAFE STRICT
AS $$ SELECT public.unaccent('public.unaccent', $1) $$;

-- Le texte cherché est la marque ET le modèle réunis : un visiteur qui tape
-- « ixon madden » cherche dans les deux sans le savoir, et deux index séparés
-- obligeraient le planificateur à les combiner.
CREATE INDEX IF NOT EXISTS product_recherche_trgm
    ON product USING gin (
        f_unaccent(coalesce(model_display, '') || ' ' || coalesce(brand_code, ''))
        gin_trgm_ops
    );
