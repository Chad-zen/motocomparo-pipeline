-- Les codes promo, par marchand.
--
-- Repris du fonctionnement de la v1, constaté sur le site en production : un
-- code appartient à un MARCHAND, pas à un produit, et le lien « Voir chez X »
-- pointe vers la page promo du marchand lui-même — pas vers une plateforme
-- d'affiliation. La propriétaire l'explique : les flux des plateformes
-- n'étaient pas à jour, donc les codes sont relevés à la source.
--
-- La date de fin est OBLIGATOIRE, et c'est la décision qui compte ici. Un code
-- périmé affiché est pire que pas de code : le visiteur clique, le code est
-- refusé au panier, et il ne revient pas. Sans date de fin connue, on inscrit
-- une échéance courte et on la repousse — jamais l'inverse.

CREATE TABLE IF NOT EXISTS code_promo (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    merchant_id  smallint NOT NULL REFERENCES merchant(id),
    code         text NOT NULL,
    libelle      text NOT NULL,          -- « -14 % sur tout le site »
    url          text,                   -- la page promo DU MARCHAND
    debut_le     date NOT NULL DEFAULT current_date,
    fin_le       date NOT NULL,          -- jamais nul : voir plus haut
    cree_le      timestamptz NOT NULL DEFAULT now(),
    retire_le    timestamptz,            -- retrait manuel avant l'échéance
    -- le même code ne peut pas être saisi deux fois pour un marchand
    CONSTRAINT code_promo_uq UNIQUE (merchant_id, code),
    CONSTRAINT code_promo_dates CHECK (fin_le >= debut_le)
);

-- L'index ne couvre que les codes encore utiles : c'est la seule lecture que
-- fait le site, et elle a lieu sur chaque fiche produit.
CREATE INDEX IF NOT EXISTS code_promo_actifs_idx
    ON code_promo (merchant_id, fin_le)
    WHERE retire_le IS NULL;
