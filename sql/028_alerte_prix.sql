-- Les alertes de baisse de prix : « prévenez-moi si le prix baisse ».
--
-- ⚠️ Cette table contient des DONNÉES PERSONNELLES (une adresse e-mail). Le
-- strict nécessaire et rien d'autre : l'adresse, la fiche, la taille, le prix
-- visé, des dates et un jeton. Pas de nom, pas d'adresse IP, pas de suivi
-- d'ouverture. La page /infos#donnees décrit ce traitement.
--
-- Cycle de vie, tenu par le code (site et `mcpipe alertes`) :
--   1. le formulaire écrit une ligne EN ATTENTE (`confirme_le` vide) et envoie
--      un e-mail de confirmation ; rien d'autre ne part avant la confirmation ;
--   2. une ligne en attente depuis plus de 7 jours est EFFACÉE ;
--   3. une alerte confirmée vit 6 mois après sa confirmation, puis est EFFACÉE ;
--   4. se désinscrire EFFACE la ligne — on ne garde pas trace d'une alerte
--      arrêtée, elle n'aurait plus d'usage.
--
-- La fiche est désignée par son SLUG et non par `product.id`, et sans clé
-- étrangère. Deux raisons, mesurées dans le code :
--   - `mcpipe match --reset` vide `product` avec RESTART IDENTITY : un id
--     renverrait alors vers UN AUTRE produit, et l'alerte préviendrait d'une
--     baisse sur un article que personne n'a demandé ;
--   - une clé étrangère ferait refuser ce TRUNCATE (cf. product_caracteristique).
-- Le slug, lui, est dérivé de l'identity_hash et gelé à la création
-- (sql/001) : il survit à un nouveau rapprochement.
--
-- À appliquer en tant que `mcpipe` (propriétaire des tables), pas `postgres`.

CREATE TABLE IF NOT EXISTS alerte_prix (
    id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email                 text NOT NULL,          -- en minuscules
    produit_slug          text NOT NULL,
    taille                text,                   -- libellé affiché (« M », « XS / 6 »), NULL = toutes
    prix_cible            numeric(10,2),          -- NULL = toute baisse sous prix_reference
    prix_reference        numeric(10,2),          -- le meilleur prix au moment de la demande
    dernier_prix_notifie  numeric(10,2),          -- on ne réécrit que sur une baisse SUPPLÉMENTAIRE
    jeton                 text NOT NULL,          -- confirmer, arrêter, tout effacer
    -- E-mails de confirmation déjà partis pour cette demande : plafonné, pour
    -- que le formulaire ne serve pas à bombarder la boîte d'un tiers.
    envois                smallint NOT NULL DEFAULT 1,
    cree_le               timestamptz NOT NULL DEFAULT now(),
    confirme_le           timestamptz,
    notifie_le            timestamptz,
    CONSTRAINT alerte_jeton_uq UNIQUE (jeton),
    CONSTRAINT alerte_email_court CHECK (length(email) BETWEEN 3 AND 254),
    CONSTRAINT alerte_cible_positive CHECK (prix_cible IS NULL OR prix_cible > 0)
);

-- Une adresse ne suit qu'une fois la même fiche dans la même taille :
-- redemander met à jour, ne duplique pas.
CREATE UNIQUE INDEX IF NOT EXISTS alerte_unique_idx
    ON alerte_prix (email, produit_slug, coalesce(taille, ''));

-- Le plafond par adresse et l'effacement « toutes mes alertes ».
CREATE INDEX IF NOT EXISTS alerte_email_idx ON alerte_prix (email);

-- Le passage de nuit ne lit que les alertes confirmées.
CREATE INDEX IF NOT EXISTS alerte_actives_idx
    ON alerte_prix (produit_slug) WHERE confirme_le IS NOT NULL;
