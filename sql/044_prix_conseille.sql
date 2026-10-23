-- Le prix public conseille de chaque fiche (23/10/2026), releve dans les prix barres des flux par
-- `mcpipe prix-conseille` (voir src/mcpipe/prix_conseille.py : regle a deux paliers, sources et garde-fous).
-- palier 1 : au moins deux marchands d'accord a 1 % ; palier 2 : Speedway seul, qui l'etiquette « prix public conseille ».
CREATE TABLE IF NOT EXISTS prix_conseille (
    product_id  bigint PRIMARY KEY,
    prix        numeric(10, 2) NOT NULL,
    palier      smallint NOT NULL,
    sources     text NOT NULL,
    calcule_le  timestamptz NOT NULL DEFAULT now()
);
