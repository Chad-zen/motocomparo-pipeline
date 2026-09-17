-- Chercher dans le TITRE MARCHAND, ponctuation recollée.
-- ============================================================================
--
-- Constaté le 17/09/2026 : « Arai SZ-R » est introuvable. Deux raisons, et il
-- fallait les deux pour que ça échoue.
--
-- 1. **On cherchait dans `model_display`**, qui est un sac de jetons trié par
--    ordre alphabétique : le casque « Arai SZ-R VAS EVO » y devient « Evo R Sz
--    Vas ». Le nom que le marchand écrit, lui, vit dans `best_title`, et il est
--    renseigné pour les 311 698 fiches.
--
-- 2. **La ponctuation sépare.** Pour pg_trgm, « sz-r » est deux mots, « sz » et
--    « r » : quelqu'un qui tape « szr » ne rencontre ni l'un ni l'autre. On
--    retire donc les traits d'union, points et barres — sans toucher aux
--    espaces, sinon tous les mots se colleraient entre eux.
--
-- L'index porte exactement l'expression utilisée à la recherche. S'il en portait
-- une autre, PostgreSQL l'ignorerait en silence et balaierait 311 000 lignes à
-- chaque frappe — une lenteur qu'on ne verrait qu'en production.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE FUNCTION f_recherche(text)
    RETURNS text
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
-- Le nom est QUALIFIE : une expression d'index est evaluee avec un chemin
-- de recherche restreint, ou `f_unaccent` seul est introuvable. L'erreur ne
-- survient qu'a la creation de l'index, pas a celle de la fonction.
AS $$ SELECT translate(public.f_unaccent(lower($1)), '-._/''"()[]', '') $$;

COMMENT ON FUNCTION f_recherche(text) IS
    'Le texte tel qu''on le cherche : sans accent, en minuscules, ponctuation '
    'recollée (« SZ-R » devient « szr »). Les espaces sont conservés.';

CREATE INDEX IF NOT EXISTS product_stats_titre_trgm
    ON product_stats USING gin (f_recherche(best_title) gin_trgm_ops);
