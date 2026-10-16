-- De quoi laisser la propriétaire décider des marques et des regroupements.
--
-- Aujourd'hui les alias de marque (« rg » = « rgracing ») sont écrits dans le
-- code (`textnorm._BRAND_ALIAS`) et les fiches qui se dédoublent pour un même
-- code-barres ne sont corrigées que par un recalcul complet. Chaque changement
-- passe par un développeur. Ces tables déplacent la décision dans l'écran
-- d'administration.

-- Un alias : le code de marque tel qu'un marchand l'écrit -> la marque qu'on
-- garde. `statut = 'refuse'` retient « ce ne sont PAS la même marque » : la
-- proposition ne revient plus.
CREATE TABLE IF NOT EXISTS marque_alias (
    alias      text PRIMARY KEY,
    marque     text NOT NULL,
    statut     text NOT NULL DEFAULT 'valide' CHECK (statut IN ('valide', 'refuse')),
    cree_le    timestamptz NOT NULL DEFAULT now(),
    CHECK (alias <> marque)
);

-- Un regroupement proposé : plusieurs fiches qui portent les mêmes codes-barres
-- et passent les garde-fous du rapprochement (marque, rayon, genre, année,
-- couleur, rapport de prix). `cle` rend le calcul rejouable sans doublon.
CREATE TABLE IF NOT EXISTS fusion_proposee (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cle         text NOT NULL UNIQUE,
    produit_ids integer[] NOT NULL,
    survivant   integer NOT NULL,
    nb_fiches   integer NOT NULL,
    nb_marchands integer NOT NULL,
    statut      text NOT NULL DEFAULT 'proposee'
                CHECK (statut IN ('proposee', 'validee', 'refusee', 'appliquee')),
    calcule_le  timestamptz NOT NULL DEFAULT now(),
    decide_le   timestamptz
);
CREATE INDEX IF NOT EXISTS fusion_proposee_statut_idx ON fusion_proposee (statut);

-- Quelques réglages que le site lit : (clé, valeur) texte.
CREATE TABLE IF NOT EXISTS reglage (
    cle    text PRIMARY KEY,
    valeur text NOT NULL,
    modifie_le timestamptz NOT NULL DEFAULT now()
);
