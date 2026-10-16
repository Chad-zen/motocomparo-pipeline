-- Quelles fiches n'ont ni matière, ni saison, ni homologation ?
--
-- Recalculé chaque nuit par `mcpipe couverture` (le calcul parcourt tout le
-- catalogue : trop long pour une page, le site coupe à 5 s). L'écran
-- « Caractéristiques » de l'administration lit ces deux tables et y écrit,
-- pour une fiche, la valeur que la propriétaire connaît (source `manuel`).
CREATE TABLE IF NOT EXISTS couverture_caracteristique (
    rayon        text PRIMARY KEY,
    produits     integer NOT NULL,
    saison       integer NOT NULL,
    matiere      integer NOT NULL,
    homologation integer NOT NULL,
    calcule_le   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fiche_incomplete (
    product_id  integer PRIMARY KEY,
    categorie   smallint NOT NULL,
    manque      text[] NOT NULL,
    marchands   smallint NOT NULL DEFAULT 0,
    calcule_le  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS fiche_incomplete_cat_idx ON fiche_incomplete (categorie, marchands DESC);
