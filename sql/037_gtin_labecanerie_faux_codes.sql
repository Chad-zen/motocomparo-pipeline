-- Cinq codes-barres que La Becanerie rattache a un autre article que celui des
-- autres marchands. Releves le 17/10/2026 en cherchant, parmi les fiches
-- affichees, celles dont deux marchands ont des prix a plus de 5 fois l'un de
-- l'autre : 7 fiches sur 28 655, dont les cinq ci-dessous viennent de cette seule
-- source.
--
--   * 4512048446819 : « Coiffe de casque Shoei Hornet ADV » (35,30 EUR) sur la
--     fiche de l'intercom Sena SRL3 (369 EUR, Speedway). Signale par la
--     proprietaire le meme jour : « produits n'ont rien a voir ».
--   * 4050300525068 et 4008321100948 : ampoules Osram vendues par BOITE DE 10
--     (9,00 et 29,40 EUR) contre l'ampoule a l'unite (1,30 et 3,24 EUR).
--   * 3284660129685 : serre-cable Magura, 2,00 EUR contre 20,30 EUR.
--   * 8436542173490 : joint de silencieux Yasuni, 14,00 contre 1,50 EUR.
--
-- Le disjoncteur de `match.py` (prix 5x) ne regarde que les offres encore non
-- resolues : ces liens datent d'avant lui et personne ne les relisait.
-- `match_override` isole SEULEMENT l'offre La Becanerie ; les autres marchands
-- restent ensemble. L'offre detachee repart en `unresolved` et reprend sa
-- propre fiche a la prochaine passe de `match`.

INSERT INTO match_override (scope, merchant_id, key_value, is_split, note)
SELECT 'gtin', (SELECT id FROM merchant WHERE code = 'labecanerie'), g.gtin, true, g.note
FROM (VALUES
    ('4512048446819', 'Coiffe Shoei Hornet ADV (La Becanerie) vs intercom Sena SRL3 (Speedway). Releve le 17/10/2026.'),
    ('4050300525068', 'Ampoule Osram T4W : boite de 10 (La Becanerie) vs a l''unite. Releve le 17/10/2026.'),
    ('4008321100948', 'Ampoule Osram W16W : lot de 10 (La Becanerie) vs a l''unite. Releve le 17/10/2026.'),
    ('3284660129685', 'Serre-cable Magura : prix a 10x entre La Becanerie et Motoblouz. Releve le 17/10/2026.'),
    ('8436542173490', 'Joint de silencieux Yasuni : a l''unite (La Becanerie) vs lot. Releve le 17/10/2026.')
) AS g(gtin, note)
ON CONFLICT (scope, merchant_id, key_value) DO NOTHING;

UPDATE raw_offer SET product_id = NULL, linked_status = 'unresolved',
    link_method = NULL, link_confidence = NULL
WHERE merchant_id = (SELECT id FROM merchant WHERE code = 'labecanerie')
  AND gtin IN ('4512048446819', '4050300525068', '4008321100948', '3284660129685', '8436542173490')
  AND linked_status = 'linked';
