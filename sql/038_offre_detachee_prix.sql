-- Les offres que `match` a detachees d'une fiche parce que leur prix n'avait aucun rapport avec les autres.
--
-- POURQUOI. Le 19/10/2026, une offre La Becanerie a 44 € (une protection de levier en aluminium) se trouvait sur
-- la fiche d'une protection en mousse a 4 €, rattachee par item_group parce que les deux portent le meme titre.
-- `match` detache desormais, a chaque passage, les offres rattachees par item_group dont le prix s'ecarte de 3x
-- (5x pour l'habillement) de la mediane des autres offres vivantes de leur fiche (`_DETACHER_CANDIDATS`).
--
-- Cette table est le JOURNAL de ces detachements : de quoi les annuler a la main (ancienne fiche, ancien mode de
-- rattachement, ancienne confiance) et de quoi ne jamais detacher deux fois la meme offre (aller-retour). La fonction
-- `match.detacher_ecarts_de_prix` la cree si elle manque : cette migration ne fait que la documenter.

CREATE TABLE IF NOT EXISTS offre_detachee_prix (
    raw_offer_id       bigint PRIMARY KEY,
    ancien_product_id  bigint,
    ancien_link_method text,
    ancienne_confiance numeric,
    prix               numeric,
    mediane_autres     numeric,
    detache_le         timestamptz NOT NULL DEFAULT now()
);
