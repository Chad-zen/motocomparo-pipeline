-- Controle des ecarts de prix de plus de 50 % entre marchands, au sein d'une meme fiche.
--
-- Demande de la proprietaire, le 22/10/2026, apres la fiche Airoh ST (un pinlock a
-- 34,90 EUR compare a la visiere a 54,95 EUR : ecart de 57 %, sous les gardes 3x / 5x
-- de `match`). Sur 71 882 fiches comparees, 5 990 depassent 50 % : trop pour les
-- separer automatiquement (beaucoup sont de vraies soldes) ; elles sont donc
-- LISTEES chaque nuit, classees, et revues.
--
-- Ne contient que des chiffres et des titres de marchands : aucune donnee personnelle.

CREATE TABLE IF NOT EXISTS controle_ecart (
    product_id            integer PRIMARY KEY,
    ratio                 numeric(8, 2) NOT NULL,   -- prix le plus haut / prix le plus bas
    prix_bas              numeric(10, 2) NOT NULL,
    prix_haut             numeric(10, 2) NOT NULL,
    marchand_bas          text NOT NULL,
    marchand_haut         text NOT NULL,
    titre_bas             text,
    titre_haut            text,
    nb_marchands          smallint NOT NULL,
    nb_gtin               smallint NOT NULL,
    -- un MEME marchand porte deux codes-barres sur la fiche : deux articles, presque sur
    meme_marchand_2_gtin  boolean NOT NULL DEFAULT false,
    mots                  text,                     -- mots qui differencient les deux titres extremes
    niveau                text NOT NULL,            -- 'fort' | 'moyen' | 'faible'
    statut                text NOT NULL DEFAULT 'a_revoir',   -- 'a_revoir' | 'ok' | 'separe'
    vu_la_premiere_fois   date NOT NULL DEFAULT current_date,
    vu_le                 date NOT NULL DEFAULT current_date,
    revu_le               timestamptz,
    note                  text
);

CREATE INDEX IF NOT EXISTS controle_ecart_a_revoir_idx
    ON controle_ecart (statut, niveau, ratio DESC);
