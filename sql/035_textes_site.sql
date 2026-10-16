-- Les textes des pages rayon et marque, modifiables dans l'administration.
--
-- `cle` : « rayon:helmet », « marque:shoei ». Un champ vide = le texte
-- automatique de `mcsite/seo.py`, qui reste le repli. Rien n'est jamais perdu :
-- vider les champs d'une ligne rend la main au texte automatique.
CREATE TABLE IF NOT EXISTS texte_site (
    cle         text PRIMARY KEY,
    titre       text,
    description text,
    intro       text,
    modifie_le  timestamptz NOT NULL DEFAULT now()
);
