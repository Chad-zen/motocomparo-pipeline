-- Airoh ST : un pinlock (34,90 EUR) et la visiere (44,90 / 54,95 EUR) sur une meme fiche.
--
-- Signale par la proprietaire le 22/10/2026 : « on compare un pinlock avec l'ecran ».
-- Fiche airoh-st-na-c3ceae95 (228432, rayon 30) :
--
--   * FC-Moto, GTIN 8029243229537 : « Airoh ST Pinlock Visiere »  34,90 EUR
--   * FC-Moto, GTIN 8029243229513 : « Airoh ST Visiere »          44,90 EUR
--   * Motoin,  GTIN 8029243229513 : « ... visiere, 85 % teinte »   54,95 EUR
--
-- Le pinlock est l'insert anti-buee, pas l'ecran. Deux GTIN differents d'UN MEME
-- marchand rattaches ensemble : l'identite ne retient pas le mot « pinlock ». Les
-- gardes de prix (3x / 5x) ne voient rien : l'ecart est de 57 %.
--
-- `match_override` isole le GTIN du pinlock ; l'offre detachee repart en
-- `unresolved` et reprend sa propre fiche a la prochaine passe de `match`.

INSERT INTO match_override (scope, merchant_id, key_value, is_split, note)
VALUES ('gtin', NULL, '8029243229537', true,
        'Airoh ST Pinlock (insert anti-buee) rattache a la visiere. Releve le 22/10/2026.')
ON CONFLICT DO NOTHING;

UPDATE raw_offer SET product_id = NULL, linked_status = 'unresolved',
    link_method = NULL, link_confidence = NULL
WHERE gtin = '8029243229537' AND linked_status = 'linked'
  AND product_id = (SELECT id FROM product WHERE slug = 'airoh-st-na-c3ceae95');
