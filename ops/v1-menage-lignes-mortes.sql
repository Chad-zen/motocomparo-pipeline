-- ============================================================================
-- MENAGE DES LIGNES MORTES DE LA v1  (wp_pc_catalog)
--
-- A EXECUTER A LA MAIN DANS phpMyAdmin, PAR SOFIA, ETAPE PAR ETAPE.
-- Ne pas tout coller d'un coup. Chaque bloc se lit avant de passer au suivant.
--
-- CONTEXTE : Maxxess et Moto-Axxe emettent des code-barres qui changent a
-- chaque export. La v1 les empile depuis des annees. Estimation de depart :
-- ~870 000 lignes mortes sur 1,32 million, pour <900 offres vivantes.
--
-- PREREQUIS ABSOLUS (dans cet ordre, aucun n'est optionnel) :
--   1. L'inventaire v1 est EXPORTE ET GELE (adresse / code-barres / trafic /
--      position Google). Tant que ce n'est pas fait, ne rien supprimer.
--   2. Une sauvegarde de la table existe et a ete TELECHARGEE (bloc 2).
--   3. On a verifie qu'aucun snippet ni plugin actif ne lit ces lignes.
--      Symptome d'une erreur ici : des erreurs 500 sur des pages publiques,
--      vues par Google.
--
-- RAPPEL : depuis l'achat du VPS, ce menage n'est plus un prealable a quoi
-- que ce soit. C'est de l'hygiene. En cas de doute : ne pas le faire.
-- ============================================================================


-- ---------------------------------------------------------------------------
-- BLOC 1 - MESURER (lecture seule, aucun risque)
-- ---------------------------------------------------------------------------

-- 1a. Combien de lignes par marchand, et a quand remonte la derniere vue ?
--     C'est ce qui prouve (ou infirme) les ~870 000 lignes mortes.
SELECT store,
       COUNT(*)                                   AS lignes,
       MIN(last_seen)                             AS plus_ancienne,
       MAX(last_seen)                             AS plus_recente,
       SUM(last_seen < NOW() - INTERVAL 30 DAY)   AS mortes_30j,
       SUM(last_seen < NOW() - INTERVAL 90 DAY)   AS mortes_90j
FROM wp_pc_catalog
GROUP BY store
ORDER BY lignes DESC;

-- 1b. Ce que pesent reellement les tables, et la place que ca liberera.
SELECT table_name,
       table_rows,
       ROUND((data_length + index_length) / 1024 / 1024)     AS taille_mo,
       ROUND(data_free / 1024 / 1024)                        AS deja_libre_mo
FROM information_schema.TABLES
WHERE table_schema = DATABASE()
ORDER BY (data_length + index_length) DESC
LIMIT 25;

-- 1c. Combien de fiches WooCommerce aujourd'hui, et le poids des attributs.
--     (Ce chiffre decide si les 244 000 fiches v2 peuvent etre des articles
--      WordPress ou non. Rien a voir avec le menage, mais c'est la meme visite.)
SELECT (SELECT COUNT(*) FROM wp_posts WHERE post_type = 'product') AS fiches,
       (SELECT COUNT(*) FROM wp_postmeta)                          AS lignes_attributs;


-- ---------------------------------------------------------------------------
-- BLOC 2 - SAUVEGARDER  (a faire AVANT toute suppression)
-- ---------------------------------------------------------------------------
-- Dans phpMyAdmin : onglet "Exporter", choisir UNIQUEMENT wp_pc_catalog,
-- format SQL, compression gzip, puis TELECHARGER le fichier sur le PC.
--
-- Ne pas se contenter d'une copie dans la base : elle occuperait la place
-- qu'on essaie justement de liberer, et elle disparaitrait avec la base.
--
-- Verifier que le fichier telecharge n'est pas vide avant de continuer.


-- ---------------------------------------------------------------------------
-- BLOC 3 - REPETITION A BLANC (lecture seule)
-- ---------------------------------------------------------------------------
-- Compter EXACTEMENT ce que le bloc 4 supprimerait. Ce nombre doit
-- correspondre a ce qu'on attend. S'il surprend : on s'arrete.

SELECT COUNT(*) AS a_supprimer
FROM wp_pc_catalog
WHERE store IN ('maxxess', 'motoaxxe')          -- << VERIFIER CES NOMS AU BLOC 1a
  AND last_seen < NOW() - INTERVAL 30 DAY;

-- Et ce qui RESTERAIT vivant pour ces deux marchands (attendu : <900) :
SELECT store, COUNT(*) AS restant
FROM wp_pc_catalog
WHERE store IN ('maxxess', 'motoaxxe')
  AND last_seen >= NOW() - INTERVAL 30 DAY
GROUP BY store;


-- ---------------------------------------------------------------------------
-- BLOC 4 - SUPPRIMER, PAR PETITS PAQUETS
-- ---------------------------------------------------------------------------
-- Par paquets de 5 000 : un hebergement mutualise coupe les requetes longues,
-- et une suppression de 870 000 lignes d'un coup verrouillerait la table
-- pendant que des visiteurs sont sur le site.
--
-- Relancer cette requete jusqu'a ce que phpMyAdmin affiche "0 ligne affectee".
-- Compter environ 175 passages. C'est long et c'est normal.

DELETE FROM wp_pc_catalog
WHERE store IN ('maxxess', 'motoaxxe')
  AND last_seen < NOW() - INTERVAL 30 DAY
LIMIT 5000;

-- Apres chaque serie de passages, ouvrir le site dans un onglet et verifier
-- qu'une page produit s'affiche normalement. Au moindre 500 : arreter et
-- restaurer la sauvegarde du bloc 2.


-- ---------------------------------------------------------------------------
-- BLOC 5 - RECUPERER LA PLACE
-- ---------------------------------------------------------------------------
-- ATTENTION - LE PIEGE : supprimer des lignes ne rend PAS la place. MySQL la
-- garde en reserve dans le fichier de la table. Pour la rendre au disque il
-- faut reconstruire la table -- et pendant la reconstruction MySQL a besoin
-- d'AUTANT DE PLACE LIBRE que la taille de la table.
--
-- Donc : si la base est encore quasi pleine, CETTE REQUETE ECHOUERA.
-- Verifier d'abord avec le bloc 1b que "deja_libre_mo" couvre "taille_mo".
--
-- Si ce n'est pas le cas : ne pas insister, demander a Hostinger, ou
-- simplement laisser la place en reserve (elle sera reutilisee par la table
-- elle-meme, ce qui n'est pas un probleme).

OPTIMIZE TABLE wp_pc_catalog;

-- Puis re-mesurer avec le bloc 1b.
