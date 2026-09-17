-- Les messages envoyés depuis la page Contact.
--
-- Pourquoi une table et pas une adresse e-mail affichée : une adresse en clair
-- sur une page publique est aspirée par les robots en quelques jours, et le
-- site n'a pas de serveur d'envoi. Les messages sont donc stockés ici et lus
-- dans le tableau de bord, où l'exploitante passe déjà tous les jours.
--
-- L'adresse de réponse est facultative : quelqu'un qui signale une erreur de
-- prix rend service même sans laisser son adresse, et l'exiger ferait perdre
-- le signalement.

CREATE TABLE IF NOT EXISTS message_contact (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sujet     text NOT NULL,
    corps     text NOT NULL,
    email     text,                    -- facultatif : voir plus haut
    page      text,                    -- d'où le visiteur écrivait
    recu_le   timestamptz NOT NULL DEFAULT now(),
    traite_le timestamptz,
    CONSTRAINT message_corps_non_vide CHECK (length(btrim(corps)) >= 10)
);

CREATE INDEX IF NOT EXISTS message_a_traiter_idx
    ON message_contact (recu_le DESC) WHERE traite_le IS NULL;
