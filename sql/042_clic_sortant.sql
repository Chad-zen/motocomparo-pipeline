-- Les clics vers les marchands, comptes par le site lui-meme (23/10/2026).
--
-- Chaque bouton « Voir l'offre » passe par /aller/<offre> : le site note le clic puis redirige vers le lien
-- d'affiliation du marchand. L'adresse affichee au visiteur est une adresse motocomparo.com, et un lien
-- d'affiliation qui change se corrige a un seul endroit.
--
-- Aucune donnee personnelle : ni adresse IP, ni navigateur, ni identifiant de visiteur. Une ligne =
-- une offre cliquee a un instant donne.

CREATE TABLE IF NOT EXISTS clic_sortant (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    offre_id    bigint NOT NULL,
    product_id  bigint,
    merchant_id smallint,
    au          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS clic_sortant_au_idx ON clic_sortant (au);
CREATE INDEX IF NOT EXISTS clic_sortant_produit_idx ON clic_sortant (product_id, au);
