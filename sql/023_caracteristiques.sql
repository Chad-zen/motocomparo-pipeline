-- Les caractéristiques lues dans les descriptions marchandes.
--
-- POURQUOI UNE TABLE, ET PAS DES COLONNES SUR `product`
-- ====================================================
-- Un casque a une calotte et une boucle ; un blouson a une membrane et des
-- coques ; un pneu a un indice de charge. Mettre tout ça en colonnes sur
-- `product` donnerait une table de soixante colonnes vides à quatre-vingt-dix
-- pour cent, et une migration à chaque rayon qu'on attaque.
--
-- Une ligne par (fiche, caractéristique) coûte une jointure et ne coûte rien
-- d'autre. On ajoute un rayon sans toucher au schéma.
--
-- POURQUOI `source` ET `confiance`
-- ================================
-- Parce qu'une caractéristique lue dans une phrase de vente n'a pas le même
-- statut qu'une valeur déclarée dans un champ dédié, et que le site doit
-- pouvoir faire la différence. `borrow_sizes()` a appris cette leçon au projet
-- avec les tailles : une valeur sans sa provenance finit par être traitée
-- comme une preuve.
--
-- CE QU'ON N'Y MET PAS : une valeur devinée. L'extracteur rend `None` en cas de
-- doute, et un `None` ne produit aucune ligne ici. Une caractéristique absente
-- coûte un filtre moins précis ; une caractéristique fausse coûte la confiance.

CREATE TABLE IF NOT EXISTS product_caracteristique (
    product_id  integer NOT NULL REFERENCES product(id) ON DELETE CASCADE,
    nom         text    NOT NULL,
    valeur      text    NOT NULL,
    source      text    NOT NULL,
    confiance   text    NOT NULL DEFAULT 'lue',
    calcule_le  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (product_id, nom)
);

COMMENT ON TABLE product_caracteristique IS
    'Ce qu''on a su lire des descriptions marchandes, une ligne par fiche et '
    'par caractéristique. Jamais une valeur devinée : l''extracteur s''abstient '
    'plutôt que de supposer.';

COMMENT ON COLUMN product_caracteristique.source IS
    'Le marchand dont le texte a fourni la valeur. Sert à remonter à la phrase '
    'd''origine quand une valeur est contestée — et elle le sera.';

COMMENT ON COLUMN product_caracteristique.confiance IS
    '''lue'' : trouvée telle quelle dans un texte marchand. ''deduite'' : '
    'établie par recoupement. Le site n''affiche aujourd''hui que ''lue''.';

-- Chercher « tous les casques en carbone » est la requête du configurateur.
-- Sans cet index, elle balaie la table entière à chaque filtre coché.
CREATE INDEX IF NOT EXISTS product_caracteristique_nom_valeur_idx
    ON product_caracteristique (nom, valeur);

ANALYZE product_caracteristique;
