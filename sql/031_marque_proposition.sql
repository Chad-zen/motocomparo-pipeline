-- Les paires de marques écrites différemment pour un même code-barres, calculées
-- chaque nuit par `mcpipe consolider` plutôt qu'à l'ouverture de l'écran : la
-- recherche balaie toutes les offres (plus de 5 s), le site coupe à 5 s.
CREATE TABLE IF NOT EXISTS marque_proposition (
    a            text NOT NULL,
    b            text NOT NULL,
    codes_barres integer NOT NULL,
    fiches_a     integer NOT NULL DEFAULT 0,
    fiches_b     integer NOT NULL DEFAULT 0,
    titre_a      text,
    titre_b      text,
    calcule_le   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (a, b)
);
