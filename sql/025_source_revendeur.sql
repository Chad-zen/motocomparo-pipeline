-- Les fiches techniques d'un revendeur, en complement de SHARP.
--
-- POURQUOI CETTE SOURCE, ALORS QUE CE N'EST PAS UN ORGANISME PUBLIC
-- ===================================================================
-- SHARP dit si un casque protège : une mesure de laboratoire, sur 585 modèles,
-- jamais un jet ni un cross. Le revendeur dit de quoi il est fait : matière
-- de calotte, nombre de coques, type de fermeture — sur plus de 4 000 fiches,
-- tous rayons. Les deux se complètent, aucun ne remplace l'autre.
--
-- CE QU'ON EN GARDE, ET CE QU'ON N'EN GARDE PAS. Un tableau de caractéristiques
-- généré automatiquement par leur boutique (marque, modèle, nombre de coques,
-- fermeture, matière, fonctionnalités) — c'est FACTUEL, comparable à une fiche
-- technique. Le poids et l'homologation, eux, sont écrits en prose dans un
-- texte de présentation : on les extrait avec la même prudence qu'une
-- description marchande, jamais recopiés tels quels. Ce qu'on ne reprend
-- JAMAIS : leurs notes éditoriales (confort, bruit — des avis, pas des faits)
-- ni leur texte de vente.
--
-- LE CHANGEMENT DE CLE SUR `product_caracteristique`. Elle valait
-- (product_id, nom) : une seule ligne par caractéristique, quelle que soit sa
-- provenance. Deux sources déjà en place se recouvraient en silence sur le
-- poids — `poids_g` côté flux, `poids` côté SHARP, deux noms pour ne pas se
-- percuter, ce qui n'est qu'un contournement. Une troisième source qui
-- écrirait aussi un poids referait la même impasse, ou pire : écraserait
-- purement et simplement une valeur MESURÉE par une valeur ANNONCÉE, selon
-- l'ordre d'exécution des commandes ce jour-là — un défaut qui ne se voit que
-- le jour où les deux sources sont en désaccord.
--
-- La clé devient (product_id, nom, source) : chaque source garde sa ligne. Le
-- choix de laquelle afficher — la mesure avant l'annonce, l'annonce avant le
-- silence — appartient à la page qui LIT, jamais à l'écriture qui écraserait
-- une preuve avec une opinion.

ALTER TABLE product_caracteristique DROP CONSTRAINT product_caracteristique_pkey;
ALTER TABLE product_caracteristique ADD PRIMARY KEY (product_id, nom, source);

COMMENT ON TABLE product_caracteristique IS
    'Ce qu''on a su lire, une ligne par fiche, caractéristique ET SOURCE : deux '
    'sources qui se contredisent restent visibles toutes les deux, plutôt que '
    'la dernière écrite qui écraserait l''autre en silence.';

CREATE TABLE IF NOT EXISTS source_revendeur (
    url               text PRIMARY KEY,
    marque            text NOT NULL,
    modele            text NOT NULL,
    type_annonce      text,               -- le rayon où la fiche a été trouvée chez eux
    nombre_coques     smallint,
    fermeture         text,
    matiere           text,
    fonctionnalites   text[] NOT NULL DEFAULT '{}',
    poids_g           integer,            -- lu en prose : voir sources/revendeur.py
    homologation      text,               -- lu en prose : voir sources/revendeur.py
    releve_le         timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE source_revendeur IS
    'Relevé brut des fiches du revendeur. Jamais rapproché ici : voir '
    'sources/rapprochement_revendeur.py, séparé pour les mêmes raisons que '
    'pour SHARP — le relevé est fiable, le rapprochement se règle plusieurs fois.';

CREATE INDEX IF NOT EXISTS source_revendeur_marque_idx ON source_revendeur (marque);

ANALYZE product_caracteristique;
ANALYZE source_revendeur;
