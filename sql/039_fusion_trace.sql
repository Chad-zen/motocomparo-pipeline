-- L'etat d'avant chaque fusion de fiches (`consolider.appliquer`), de quoi la defaire.
--
-- POURQUOI. Le 19/10/2026, aucune fusion n'avait jamais ete appliquee en production, et `appliquer` ecrasait
-- `raw_offer.product_id` et `product.status` sans rien garder : une fausse fusion ne se defaisait pas. Avant de toucher
-- une fiche, `appliquer` ecrit ici ses offres (genre 'offre', ancien_product_id) et ses fiches (genre 'fiche', ancien
-- statut, ancienne marque, ancien merged_into). `consolider.defusionner(fusion_id)` relit cette table.
-- `consolider.appliquer` la cree si elle manque : cette migration ne fait que la documenter.

CREATE TABLE IF NOT EXISTS fusion_trace (
    fusion_id          bigint NOT NULL,
    genre              text   NOT NULL CHECK (genre IN ('offre', 'fiche')),
    ref_id             bigint NOT NULL,
    ancien_product_id  bigint,
    ancien_status      text,
    ancienne_marque    text,
    ancien_merged_into bigint,
    trace_le           timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (fusion_id, genre, ref_id)
);
