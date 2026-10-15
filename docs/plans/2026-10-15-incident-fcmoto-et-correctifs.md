# 14-15/10/2026 — incident disque FC-Moto, et correctifs du site

Trace de ce qui a été fait, pourquoi, et comment le défaire. Les commits portent
le détail ligne par ligne ; ce fichier dit l'enchaînement.

## 1. Incident : disque plein, prix figés

**Constat (14/10).** Le déploiement échoue : `No space left on device`. Disque à
100 % (48 Go).

**Cause.** Le flux FC-Moto du 14/10 pesait **7,2 Go / 6,8 millions de lignes**
(Motoblouz, le plus gros autre flux : 411 Mo). Vérifié : identifiants tous
uniques sur 500 000 lignes, aucun commit récent sur fetch/load/normalize — ce
n'est pas un bug chez nous, c'est le fichier reçu de Webgains/FC-Moto. Il a été
chargé tel quel : 2 292 025 offres FC-Moto en base contre 160 309 la veille,
base passée à 31 Go, sauvegarde du jour à 1,37 Go au lieu de ~370 Mo.

**Effet de bord découvert le 15/10.** La chaîne nocturne du 14/10 s'est arrêtée
avant `normalize` (disque plein) : **aucun prix rafraîchi depuis le 13/10** pour
les six marchands. Tout le site affichait « prix non rafraîchi ».

**Ce qui a été fait, dans l'ordre :**
1. Place libérée : cache nginx vidé, sauvegardes du 10 et du 11/10 supprimées,
   `feeds/fcmoto.csv` (7,2 Go, simple cache retéléchargeable) supprimé.
2. Sur décision de la propriétaire (« ne garder que les références listées
   hier ») : les offres FC-Moto (`raw_offer`, merchant_id 6) ont été remplacées
   par celles de la sauvegarde `mcpipe-2026-10-13.dump` (prise à 03h02, donc
   avant le flux anormal) — 2 292 025 lignes supprimées, 160 309 réinsérées,
   dans une transaction. Les autres marchands n'ont pas été touchés.
   - Copie de sécurité des lignes supprimées : `/tmp/fcmoto_aujourdhui_avant_revert.csv`
     sur le VPS (1,5 Go — à supprimer quand on est sûr de ne pas en avoir besoin).
   - Base temporaire de restauration `mcpipe_restore_tmp` : **encore présente**,
     à supprimer (`dropdb mcpipe_restore_tmp`).
3. `signature → enrich → relier-tailles → freshness → caracteristiques` relancés
   pour recalculer les fiches.
4. 15/10 : chaîne complète relancée pour les cinq autres marchands
   (`fetch --only <marchand>` un par un, puis la suite). FC-Moto volontairement
   exclu : son flux n'annonce pas sa taille (pas de Content-Length), impossible
   de savoir s'il est encore anormal sans le télécharger.

**⚠️ Reste ouvert.**
- FC-Moto reste figé sur ses prix du 12/10 (« prix non rafraîchi » sur ses
  lignes) tant qu'on ne l'a pas retéléchargé.
- La tâche planifiée `mcpipe-prix.timer` (04h13 UTC) va retélécharger FC-Moto
  la nuit suivante. Si le flux est toujours à ~7 Go, avec ~4,5 Go libres, le
  disque se remplit à nouveau et toute la chaîne s'arrête. **Décision à prendre
  avant** : exclure FC-Moto de la tâche, ou ajouter un garde-fou de taille dans
  `fetch.py`.
- Piège rencontré : ne jamais `source` le `.env` en bash (une valeur contient
  une espace — voir `07-planification.sh`). Passer par `mcpipe` (qui lit le
  `.env` lui-même) ou par `EnvironmentFile` de systemd.

## 2. Correctifs du site (commits du 14 et du 15/10)

| Problème signalé | Cause | Correctif |
|---|---|---|
| Favicon : ancien logo | fichier SVG texte d'origine | nouveau badge MC, puis PNG 16/32/48 + `favicon.ico` générés depuis la source (le SVG était flou à 16 px) |
| « %None » sans réduction | `{{ remise }}` imprimait `None` (fiche à un seul marchand) | `remise or 0` |
| Meilleur prix figé sur FC-Moto (Arai Frost, taille S) | le bandeau « chez X » et « Voir l'offre » ne suivaient pas la taille choisie, et le badge pouvait tomber sur une offre en rupture | le script suit la première ligne visible non rompue et met à jour logo, nom et lien |
| Un EAN tapé dans la recherche ne trouve rien | la recherche compare des mots du titre, jamais le code-barres | un code de 8 à 14 chiffres saute directement sur la fiche (`queries.slug_par_gtin`) |
| Taper « Honda » puis choisir un rayon efface « Honda » | le lien de rayon ne portait pas `q`, et `/c/{code}` ne le lisait pas | corrigé des deux côtés |
| La « Réf. » affichée « sort de nulle part » | un EAN par taille ; on affichait celui de la première offre, donc d'une taille au hasard — et on le déclarait à Google comme `gtin13` du produit entier | voir ci-dessous |

### Codes-barres et SEO (15/10)
Avis d'un consultant SEO (agent, de mémoire de la doc Google, **non vérifié en
ligne**) :
- retirer un `gtin13` pris au hasard ne nuit pas — il est recommandé, pas
  requis, et l'actuel était faux ;
- en revanche, masquer les codes-barres serait une perte : les recherches par
  EAN existent.

Donc :
- près du titre : l'EAN n'est affiché que s'il est unique, sinon celui de la
  taille choisie ;
- nouveau bloc « Codes-barres par taille », rendu par le serveur, tous les EAN
  en clair ;
- données structurées : `ProductGroup` (`variesBy` size) + une variante par
  taille avec son `gtin13` et sa fourchette de prix ; un produit à EAN unique
  reste un simple `Product`.

**À faire après déploiement :** passer une fiche multi-tailles dans le test des
résultats enrichis de Google, puis surveiller la Search Console (rapport
« Extraits de produits ») sur quelques semaines.

## 3. Suites du 15/10

- **FC-Moto, produits connus seulement** (`FeedSpec.connus_seulement`, commit
  « fetch: FC-Moto filtre aux offres deja connues »). Le flux est lu et trié au
  fil du téléchargement, jamais écrit en entier : ~160 000 lignes gardées sur
  6,8 millions. Aucun nouveau produit FC-Moto n'entre tant que le réglage est
  vrai — à retirer quand le flux redevient normal. Premier passage lancé le
  15/10 à 00h UTC (`systemd-run --unit=fcmoto-rattrapage`, journal :
  `journalctl -u fcmoto-rattrapage`).
- **Tableau de bord « Veille MotoComparo »** (artefact claude.ai
  `PozDFC7k3JPuWPX8CDYe51`). Relevé : `ops/surveillance.py` (sur le VPS,
  alertes à seuils fixes) → `ops/veille_tableau.py` (sur le poste, 4 fichiers
  dans `ops/veille/`) → tâche planifiée locale `veille-motocomparo`, chaque jour
  à 8h, qui envoie les fichiers et notifie si une alerte est critique. Lecture
  seule. La tâche ne tourne que si l'application Claude est ouverte (sinon au
  prochain lancement).
- **Réf. déroulante** sur la fiche : EAN de la plus petite taille, liste de
  tous les EAN au clic ; remplace le bloc « Codes-barres par taille ».
- **Voile de chargement** : badge rond seul, fond transparent, sans pastille.
- Repéré par le premier relevé, non traité : Googlebot reçoit des erreurs 500
  sur d'anciennes adresses de la v1 (`/shop/…`, `/product/…`) ; la base fait
  34,7 Go après la suppression de 2,1 M de lignes (place non rendue au disque
  tant qu'un `VACUUM FULL` n'est pas passé — à planifier, il demande de
  l'espace libre et bloque la table).
