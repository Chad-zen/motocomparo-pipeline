-- La preuve de chaque caractéristique lue sur le web : l'adresse de la page et le
-- passage qui l'établit, relu par un second agent. Sans elle, une valeur lue
-- sur une page marchande ne serait qu'une affirmation de plus.
CREATE TABLE IF NOT EXISTS caracteristique_preuve (
    product_id integer NOT NULL,
    nom        text NOT NULL,
    valeur     text NOT NULL,
    url        text NOT NULL,
    citation   text NOT NULL,
    verifie    boolean NOT NULL DEFAULT false,
    cree_le    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, nom)
);
