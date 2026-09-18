-- Mettre un marchand de côté sans perdre ses données.
--
-- POURQUOI. Le 18/09/2026, le flux de La Bécanerie a été déclaré mort après une
-- contre-expertise qui a cherché à démontrer l'inverse :
--
--   * fichier de 178 803 398 octets IDENTIQUE À L'OCTET les 17 et 18/09, après
--     deux téléchargements complets de 170 Mo — les cinq autres flux ont varié
--     de +312 octets à −3,7 Mo sur la même nuit ;
--   * zéro prix modifié sur 222 927 offres depuis le 10/09, quand FC-Moto en
--     changeait 2 820 pour la seule nuit du 17 au 18 ;
--   * zéro offre entrée, zéro offre retirée depuis le 11/09 — les cinq autres
--     marchands renouvellent leur catalogue tous les jours ;
--   * deux prix vérifiés sur leur propre site : 71,00 € et 75,90 € là où leur
--     flux annonçait 42,90 € et 56,00 € ;
--   * cinq adresses produits sur douze redirigent vers une page de catégorie,
--     le produit ayant quitté leur catalogue sans quitter leur fichier.
--
-- Le pipeline, lui, a été disculpé : `load` fait un DELETE + COPY complet,
-- l'UPSERT de `normalize` écrit `price = EXCLUDED.price` sans condition, et
-- `price_history` s'écrit APRÈS la mise à jour des prix. La faute est en amont.
--
-- CE QUE CETTE COLONNE FAIT, ET CE QU'ELLE NE FAIT PAS
-- ====================================================
-- `affiche` ne coupe PAS l'ingestion : on continue à télécharger, à lire et à
-- historiser ce marchand. Le jour où son flux repart, ses prix sont déjà là et
-- il suffit de remettre le drapeau. Couper l'ingestion ferait perdre la
-- mesure qui permettra justement de savoir qu'il est reparti.
--
-- Elle ne supprime rien non plus : ses 222 927 offres restent en base.
--
-- ⚠️ À NE PAS CONFONDRE AVEC `merchant.active`, qui existait déjà et que
-- PERSONNE NE LIT — vérifié par recherche dans tout le code. Son sens n'a
-- jamais été écrit nulle part. On ne l'a donc pas détournée : deux drapeaux qui
-- se ressemblent et dont un seul a un sens documenté, c'est une erreur en
-- attente. `affiche` répond à une question précise : « le site montre-t-il ce
-- marchand ? »

ALTER TABLE merchant
    ADD COLUMN IF NOT EXISTS affiche boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN merchant.affiche IS
    'Le site montre-t-il ce marchand ? À false, ses offres sont ingérées et '
    'historisées comme avant, mais elles ne fixent aucun prix affiché, '
    'n''apparaissent sur aucune fiche et ne comptent pas dans le nombre de '
    'marchands comparés. Sert à écarter un flux devenu faux sans perdre la '
    'mesure qui dira qu''il est redevenu bon.';

-- ---------------------------------------------------------------------------
-- LA DÉCISION DU 18/09/2026, datée et réversible.
--
-- Elle est dans la migration plutôt que lancée à la main pour qu'une base
-- reconstruite de zéro ne réaffiche pas silencieusement un marchand écarté.
--
-- POUR LE REMETTRE, le jour où son flux repart :
--
--     UPDATE merchant SET affiche = true WHERE code = 'labecanerie';
--     SELECT refresh_product_stats();
--
-- Le signal à surveiller n'est pas le prix d'un produit mais le MOUVEMENT du
-- catalogue : des arrivées et des retraits. Un flux vivant en a tous les jours.
-- `mcpipe marchands-figes` le dit.
-- ---------------------------------------------------------------------------
UPDATE merchant SET affiche = false WHERE code = 'labecanerie';
