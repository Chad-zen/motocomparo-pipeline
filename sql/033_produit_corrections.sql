-- Les corrections de fiche faites à la main dans l'administration.
--
-- Masquer une fiche la retire de toutes les listes, de la recherche et du plan du
-- site : elle prend le statut `merged` sans fiche d'arrivée, que tout le site
-- exclut déjà. On garde ici son ancien statut pour la réafficher, et son adresse
-- pour que la décision survive à un recalcul complet des fiches.
CREATE TABLE IF NOT EXISTS produit_masque (
    slug           text PRIMARY KEY,
    product_id     integer NOT NULL,
    ancien_statut  text NOT NULL,
    motif          text,
    cree_le        timestamptz NOT NULL DEFAULT now()
);

-- Changement de rayon : l'ancien et le nouveau, pour pouvoir revenir en arrière.
CREATE TABLE IF NOT EXISTS produit_rayon_corrige (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug           text NOT NULL,
    ancien_rayon   smallint NOT NULL,
    nouveau_rayon  smallint NOT NULL,
    cree_le        timestamptz NOT NULL DEFAULT now()
);
