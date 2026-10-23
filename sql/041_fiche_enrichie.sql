-- Fiches enrichies : le texte « vendeur » d'un MODELE de casque, valable pour tous ses coloris.
--
-- Demande de la proprietaire (22/10/2026) : chaque fiche doit aider a decider -- points
-- forts, points a ameliorer, profil type, fiche technique -- avec des faits SOURCES.
-- Premier lot : sept modeles Arai.
--
-- Une ligne par modele, pas par fiche : un RX-7V EVO existe en 36 coloris au catalogue, un
-- seul texte les sert tous. `motif` est une expression reguliere (insensible a la casse)
-- cherchee dans le titre de la fiche, pour la marque `brand_code`.
--
-- Le contenu est un JSON : accroche, description, profil_type, points_forts,
-- points_a_ameliorer, fiche_technique, securite, a_savoir. Chaque fait porte sa preuve
-- (sharp / fabricant / presse / flux) et sa source ; `alertes_qualite` reste pour l'equipe
-- et n'est jamais affiche.

CREATE TABLE IF NOT EXISTS fiche_enrichie (
    brand_code  text NOT NULL,
    modele      text NOT NULL,
    motif       text NOT NULL,
    contenu     jsonb NOT NULL,
    source      text NOT NULL DEFAULT 'redige',
    redige_le   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (brand_code, modele)
);
