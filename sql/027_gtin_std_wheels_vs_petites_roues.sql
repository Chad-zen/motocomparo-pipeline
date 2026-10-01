-- Collision de code-barres : KTM 85 SX « grandes roues » (STD) contre
-- « petites roues » (P.R), un seul GTIN pour deux kits chaîne différents.
--
-- Signalée par la propriétaire le 01/10/2026, un lien de fiche à l'appui.
-- Vérifié sur les trois sites marchands avant de corriger :
--
--   * Motoblouz (réf. DE00528A / 107105121) : « KTM 85 85 SX STD WHEELS
--     17/14 » — le kit grandes roues.
--   * Speedway (réf. MOR107105151) et La Bécanerie (réf. 405DID-3112) :
--     « KTM 85 SX P.R » / « petites roues 03-> », même pignon (14), même
--     couronne (46), même pas (428), 120 maillons.
--
-- Les deux kits diffèrent réellement (démultiplication et longueur de
-- chaîne liées à la taille de roue), mais partagent le GTIN 8434290144663
-- dans les trois flux — une erreur du fabricant ou d'un des marchands en
-- amont, pas une faute du pipeline. L'écart de prix (71 à 121 €, ratio
-- 1,7) est resté sous le seuil de 5x du disjoncteur de `match.py`, donc
-- invisible pour lui.
--
-- `match_override` isole SEULEMENT l'offre Motoblouz : Speedway et La
-- Bécanerie s'accordent entre eux et restent fusionnés.

INSERT INTO match_override (scope, merchant_id, key_value, is_split, note)
VALUES (
    'gtin',
    (SELECT id FROM merchant WHERE code = 'motoblouz'),
    '8434290144663',
    true,
    'KTM 85 SX STD WHEELS (Motoblouz) vs P.R/petites roues (Speedway, '
    'La Bécanerie) — même GTIN, deux kits chaîne différents. Vérifié sur '
    'les trois sites le 01/10/2026.'
)
ON CONFLICT (scope, merchant_id, key_value) DO NOTHING;

-- Détache l'offre déjà fusionnée à tort : `match` (sans --reset) la
-- retrouvera 'unresolved' et, grâce à l'override ci-dessus, ne la
-- remariera plus au produit des deux autres marchands.
UPDATE raw_offer SET product_id = NULL, linked_status = 'unresolved',
    link_method = NULL, link_confidence = NULL
WHERE merchant_id = (SELECT id FROM merchant WHERE code = 'motoblouz')
  AND merchant_sku = '1212535';
