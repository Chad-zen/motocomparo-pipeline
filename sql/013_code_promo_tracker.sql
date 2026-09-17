-- Le relevé automatique des codes promo, repris de la v1.
--
-- La v1 avait essayé les plateformes d'affiliation (Effinity, Kwanko) : le code
-- y était le plus souvent celui du mois précédent. L'extrait « MC Codes Promo
-- v1 » a donc fini par lire les pages promo PUBLIQUES des marchands eux-mêmes,
-- une fois par jour, et c'est ce mécanisme-là qu'on rejoue ici.
--
-- Trois colonnes suffisent à le distinguer d'une saisie à la main :
--
--   source      'site' = relevé chez le marchand, 'manuel' = saisi à l'admin.
--               Un relevé ne doit jamais écraser une saisie : la propriétaire
--               qui corrige un libellé à la main a raison contre l'automate.
--   vu_le       la dernière fois que le code était encore sur la page. C'est
--               lui qui permet de retirer tout seul un code disparu, sans
--               attendre son échéance.
--   conditions  « dès 79 € d'achat · hors soldes », relevé dans le voisinage
--               du code. Affiché sous le libellé.
--
-- `contexte` garde les ~900 caractères qui entouraient le code sur la page. Ce
-- n'est pas affiché : c'est ce qu'on relit quand un code se révèle faux, pour
-- comprendre ce que le lecteur a cru voir.

ALTER TABLE code_promo
    ADD COLUMN IF NOT EXISTS source     text NOT NULL DEFAULT 'manuel',
    ADD COLUMN IF NOT EXISTS vu_le      timestamptz,
    ADD COLUMN IF NOT EXISTS conditions text,
    ADD COLUMN IF NOT EXISTS contexte   text;

ALTER TABLE code_promo DROP CONSTRAINT IF EXISTS code_promo_source;
ALTER TABLE code_promo
    ADD CONSTRAINT code_promo_source CHECK (source IN ('manuel', 'site'));

-- Un code relevé sans date de fin lisible sur la page reçoit une échéance
-- courte, repoussée à chaque relevé tant qu'il est encore affiché. L'index
-- reste celui de la 012 : il ne couvre que les codes encore servis.
CREATE INDEX IF NOT EXISTS code_promo_source_idx ON code_promo (source, vu_le);
