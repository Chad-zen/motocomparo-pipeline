-- Les inscriptions à la lettre hebdomadaire.
--
-- Une adresse, une date, et rien d'autre : pas de nom, pas de suivi. Le jeton
-- de désinscription est tiré au hasard et figure dans chaque envoi, pour que se
-- désinscrire ne demande ni compte ni échange de courriel.
--
-- ⚠️ Cette table contient des DONNÉES PERSONNELLES. Elle ne doit pas recevoir
-- d'adresses tant que la page de confidentialité n'est pas écrite et publiée :
-- collecter une adresse sans dire ce qu'on en fait n'est pas acceptable, et
-- c'est à la propriétaire d'écrire ce texte, pas à l'assistant.

CREATE TABLE IF NOT EXISTS lettre_inscrit (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email       text NOT NULL,
    inscrit_le  timestamptz NOT NULL DEFAULT now(),
    -- une adresse ne s'inscrit qu'une fois ; se réinscrire ne crée pas de doublon
    CONSTRAINT lettre_email_uq UNIQUE (email),
    jeton       text NOT NULL DEFAULT encode(gen_random_bytes(16), 'hex'),
    desinscrit_le timestamptz
);

CREATE INDEX IF NOT EXISTS lettre_actifs_idx
    ON lettre_inscrit (inscrit_le) WHERE desinscrit_le IS NULL;
