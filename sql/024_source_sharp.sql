-- SHARP : la seule source de ce projet qui MESURE au lieu de décrire.
--
-- POURQUOI CELLE-CI, ET PAS UNE AUTRE
-- ===================================
-- Tout ce que le site sait aujourd'hui vient des marchands, qui décrivent ce
-- qu'ils vendent. SHARP est le programme d'essais du ministère des transports
-- britannique : il achète les casques, les détruit sur 32 scénarios de choc, et
-- publie une note de 1 à 5 étoiles avec le POIDS PESÉ.
--
-- C'est la différence entre « casque léger et sûr » écrit par le vendeur et
-- « 1,6 kg, 5 étoiles » relevé par un laboratoire. Aucun de nos six marchands
-- ne porte cette donnée, et c'est précisément ce qui peut faire d'un
-- comparateur autre chose qu'une liste de prix.
--
-- LICENCE. Le site porte le logo Open Government Licence : réutilisation
-- autorisée, attribution obligatoire. `source` vaut donc 'sharp' partout, et
-- toute page qui affiche une de ces valeurs doit nommer SHARP à côté. Ce n'est
-- pas une politesse, c'est la condition de la licence.
--
-- POURQUOI UNE TABLE À PART, ET PAS DIRECTEMENT `product_caracteristique`
-- ======================================================================
-- Parce que le RAPPROCHEMENT est un problème séparé du RELEVÉ, et bien plus
-- fragile. SHARP écrit « K7 », le marchand écrit « Casque intégral AGV K-7
-- Mono Noir Mat taille L ». Le relevé, lui, est exact et se refait en dix
-- minutes. En les séparant, on peut rejouer le rapprochement autant de fois
-- qu'il faut sans retourner chercher les 585 pages — et on garde sous les yeux
-- ce que SHARP a dit, mot pour mot, quand une valeur est contestée.

CREATE TABLE IF NOT EXISTS source_sharp (
    slug              text PRIMARY KEY,   -- le segment d'URL, ex. 'agv-k7'
    marque            text NOT NULL,
    modele            text NOT NULL,
    etoiles           smallint,           -- 1 à 5 ; NULL si la page n'en montre pas
    poids_g           integer,            -- pesé par le laboratoire, pas annoncé
    prix_gbp          numeric(10, 2),     -- prix conseillé au Royaume-Uni
    tailles           text,
    type_casque       text,               -- Full face, Flip front, Open face...
    retention         text,               -- type de boucle
    materiaux         text,               -- matière de calotte, telle qu'écrite
    norme             text,
    site_constructeur text,               -- la passerelle vers la source suivante
    date_test         text,
    options           text[] NOT NULL DEFAULT '{}',
    releve_le         timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE source_sharp IS
    'Relevé brut des fiches SHARP (Department for Transport, Open Government '
    'Licence). Jamais rapproché ici : le rapprochement avec nos fiches est une '
    'étape séparée, rejouable sans retélécharger.';

COMMENT ON COLUMN source_sharp.poids_g IS
    'Le poids PESÉ par le laboratoire. C''est la valeur la plus difficile à '
    'obtenir du rayon : les marchands l''annoncent rarement, et quand ils '
    'l''annoncent c''est le chiffre du fabricant pour la plus petite coque.';

COMMENT ON COLUMN source_sharp.site_constructeur IS
    'L''adresse du modèle chez son fabricant, donnée par SHARP. Elle ouvre la '
    'source suivante sans avoir à deviner l''URL.';

CREATE INDEX IF NOT EXISTS source_sharp_marque_idx ON source_sharp (marque);

ANALYZE source_sharp;
