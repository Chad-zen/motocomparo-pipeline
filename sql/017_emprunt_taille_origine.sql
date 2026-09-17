-- La PROVENANCE de la taille empruntée, et pas seulement sa valeur.
-- ============================================================================
--
-- Le problème, signalé par la propriétaire le 17/09/2026 sur la housse Ixon
-- Blanky : elle filtre sur la taille L, et le même marchand revient quatre
-- fois. La raison est que quatorze offres sur dix-huit s'affichent « taille non
-- communiquée » — et celles-là restent visibles quelle que soit la taille
-- choisie, ce qui est voulu.
--
-- Or leur taille EST connue. Les quatre marchands portent les mêmes
-- codes-barres que FC-Moto, qui déclare M, L, XL et 2XL dans son flux, et
-- `borrow_sizes()` a correctement relayé ces valeurs.
--
-- Ce qui les efface est une règle de `match.py`, elle-même bien fondée : hors
-- des rayons d'habillement, une taille ne compte que si le marchand l'a
-- DÉCLARÉE dans son flux. Mesuré le 13/09 : les selles portent une taille sur
-- 81 % de leurs offres et pas une seule n'était déclarée ; un Castrol 10W-50
-- s'est retrouvé rangé en « taille EU50 ». Ailleurs qu'en habillement, une
-- taille lue dans un titre ou une référence ne vaut rien.
--
-- Mais une taille EMPRUNTÉE PAR CODE-BARRES à un marchand qui la déclare dans
-- son flux n'est pas une supposition : c'est une déclaration relayée. La règle
-- la rejetait quand même, parce qu'elle regardait la provenance de la signature
-- de l'offre (`xmerchant_gtin`) sans pouvoir savoir d'où venait la valeur chez
-- le donneur. Cette colonne le lui apprend.
--
-- Portée mesurée avant écriture : 1 079 offres sur 325 fiches, toutes
-- comparables — c'est-à-dire exactement là où le filtre de taille sert.
--
-- `mpn` reste une inférence et n'obtient rien : `donor_source` ne vaut 'feed'
-- que si TOUS les donneurs le déclaraient dans leur flux.

ALTER TABLE offer_size_override
    ADD COLUMN IF NOT EXISTS donor_source text;

COMMENT ON COLUMN offer_size_override.donor_source IS
    'Provenance de la taille CHEZ LE DONNEUR : ''feed'' si tous les donneurs la '
    'déclaraient dans leur flux, ''mpn'' sinon. Seul ''feed'' vaut preuve hors '
    'des rayons d''habillement (voir _SIZE_OF_OFFER dans match.py).';
