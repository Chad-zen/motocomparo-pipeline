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
  tous les EAN au clic ; le bloc « Codes-barres par taille » reste en plus.
- **Voile de chargement** : badge rond seul, fond transparent, sans pastille.
- Repéré par le premier relevé, non traité : Googlebot reçoit des erreurs 500
  sur d'anciennes adresses de la v1 (`/shop/…`, `/product/…`) ; la base fait
  34,7 Go après la suppression de 2,1 M de lignes (place non rendue au disque
  tant qu'un `VACUUM FULL` n'est pas passé — à planifier, il demande de
  l'espace libre et bloque la table).
- Catégorie choisie : seule sa branche reste affichée dans le panneau
  « Catégories » (plus les onze autres rayons sous la ligne active) — un lien
  « ← Toutes les catégories » ramène en arrière en gardant le mot tapé.
- Chaque filtre (Catégories, Marques, Couleur, Taille) replié à 10 lignes
  (12 pastilles pour Taille), un bouton « Voir les N autres » déplie sur
  place. **Essai raté et corrigé le jour même** : une première version faisait
  défiler la liste DANS le filtre, imbriquée dans le tiroir mobile qui défile
  lui-même — « le scroll est bugué, c'est une galère » — remplacée par le
  bouton, sans aucun défilement interne.
- Bannière Maxxess périmée (« jusqu'au 12 octobre », vue en ligne le 15)
  retirée ; nouveau champ `expire_le` dans `partenaires.py` pour qu'un
  partenaire sorte de lui-même de la rotation une fois sa date dépassée.
- La tâche `veille-motocomparo` (8h) vérifie désormais aussi, chaque jour, les
  bannières affichées sur l'accueil et une page de liste : zoom + lecture de
  toute date visible, alerte critique si dépassée. Jamais corrigé
  automatiquement.

## 4. Audit SEO externe, et les trois chantiers menés en parallèle (15/10)

Une IA tierce (sans accès au site, qui le dit elle-même) a produit un audit à
partir d'une seule capture d'écran. Vérifié point par point sur le vrai site :
la moitié des manques annoncés existaient déjà (comparateur, guides, mentions
légales, bande de catégories…). Deux vrais manques retenus et corrigés
**avant** de lancer les chantiers :
- `/m/<marque>` portait `noindex` (la marque comptait comme un filtre sur sa
  propre page) → levé ; 161 pages marques (≥ 5 fiches comparables) ajoutées au
  plan du site.
- La FAQ de l'accueil (5 questions) n'avait pas de balisage `FAQPage` → ajouté,
  tiré de la MÊME liste que la section visible (jamais deux sources qui
  pourraient diverger).

**Trois chantiers lancés en agents séparés** (worktrees isolés, aucun ne
pousse ni ne déploie — relu, testé et fusionné par la session principale) :

1. **Filtres Matière / Homologation / Saison** sur les 4 pages de liste.
   Lisent exclusivement `product_caracteristique` (ce que les extracteurs ont
   trouvé dans un texte marchand), jamais déduits. Un filtre masqué sous 15 %
   de couverture du rayon (ex. Saison absente sur Casques : 0 %). Aucune
   migration — index `(nom, valeur)` déjà posé (migration 023).
2. **Le blog**, sous `/guides` (pas de section à part — une seule porte
   éditoriale, voir l'en-tête de `src/mcsite/articles.py`). Un article =
   `templates/articles/<slug>.html`, en-tête Jinja en commentaire
   (`titre, description, date, statut, rayon, produits, marques`). Un
   `a_completer(...)` resté dans le texte transforme l'article en brouillon
   même si `statut: publié` — la règle du site (rien de publié qui ne soit
   mesuré) appliquée par le code, pas laissée à la mémoire. Trois brouillons
   écrits (duel LS2/Scorpion, gants été/hiver, casque jet/modulable/intégral
   et la norme) — chacun attend un retour d'usage réel de la propriétaire,
   repéré par ce marqueur.
3. **L'alerte de baisse de prix** (le plus gros morceau — voir section 5).

**Ce que la relecture a dû corriger avant de fusionner** (aucun n'était une
erreur des agents, plutôt l'angle mort de travailler sur trois branches en
parallèle) :
- Conflit sur `listing.html` entre les filtres caractéristiques et les
  correctifs de catégorie du même jour — résolu à la main.
- `ops/veille_tableau.py` (écrit le jour même) avait l'IP du VPS en clair,
  jamais testé contre `test_depot_anonyme.py` avant la fusion complète de la
  suite → `VPS_HOTE` déplacé dans `.env` / `.env.example`.
- Config nginx d'un agent posée au bon endroit du dépôt
  (`ops/deploiement/nginx/motocomparo-server.conf`) mais qui correspond en
  réalité à un FRAGMENT inclus sur le serveur
  (`/etc/nginx/snippets/motocomparo-server.conf`), pas au fichier
  `sites-available/motocomparo` complet (SSL, Certbot) — vérifié avant de
  copier, sauvegarde des deux fichiers live faite avant remplacement.

**Déploiement serveur, dans l'ordre :** migration `sql/028_alerte_prix.sql`
appliquée en tant que `mcpipe` → nginx (snippet + http.conf) testé
(`nginx -t`) puis rechargé → `07-planification.sh` relancé pour ajouter
`mcpipe alertes` à la chaîne nocturne (`/usr/local/bin/mcpipe-prix`) →
`systemctl restart mcsite`. Un 500 ponctuel sur l'accueil juste après
(`statement timeout` sur une requête déjà existante, page froide) — résolu de
lui-même à la requête suivante, sans rapport avec les fusions.

## 5. L'alerte de baisse de prix — et sa boîte mail

**La fonctionnalité.** Double opt-in RGPD complet : formulaire sur la fiche →
e-mail de confirmation (jeton) → rien d'actif avant le clic. Alerte confirmée
active 6 mois puis effacée automatiquement ; demande non confirmée effacée
sous 7 jours ; lien de désinscription en un clic dans chaque e-mail ; plafonds
anti-abus (20 alertes/adresse, 5 demandes/24h, 3 renvois max). Table
`alerte_prix` (migration 028) : slug du produit et non son id (survit à un
`mcpipe match --reset`, qui vide `product` avec `RESTART IDENTITY`).
`mcpipe alertes` tourne chaque nuit après `freshness`, sans jamais faire
échouer la chaîne. **Le formulaire reste invisible sur tout le site tant que
`SMTP_PASS` est vide** (`mcpipe.courriel.configure()`).

**La boîte mail.** La propriétaire a créé elle-même `hello@motocomparo.com`
chez Hostinger (le mot de passe n'a jamais transité par l'assistant — règle
dure, jamais de mot de passe tapé ni manipulé, même sur demande explicite).
`.env` du serveur : `SMTP_USER=hello@motocomparo.com`, `SMTP_PASS=` (tapé par
elle), `CONTACT_NOTIF_TO=contact@motocomparo.com` (sinon les messages du
formulaire de contact partaient dans `hello@`, une boîte qu'elle ne lirait pas
par réflexe). Testé en conditions réelles par la propriétaire le 15/10 :
l'e-mail de confirmation part bien.

**Le texte, repris TROIS fois le même jour** — chaque passage corrige le
précédent, à retenir pour la suite :
1. Premier jet (les deux agents) : fonctionnel mais « écrit par un
   développeur ». Un consultant rédacteur (agent) l'a repris une première
   fois, dans le ton déjà établi ailleurs sur le site (direct, honnête, jamais
   commercial — voir les extraits cités dans le prompt de l'agent si besoin de
   le refaire).
2. « Ce qui manque c'est du visuel » : ajout d'une bannière fournie par la
   propriétaire (casque/gants/blouson/flèche/étiquette, or sur fond nuit) —
   sur la page `/alertes/*` en tête + une carte produit (photo/nom/prix) sur
   les états utiles, et dans l'e-mail en HTML (alternative au texte, jamais à
   sa place). **Point de vigilance réglé explicitement** : l'image de l'e-mail
   est JOINTE au message (Content-ID, `mcpipe.courriel.cid_banniere`), jamais
   chargée à une adresse distante — sinon elle aurait fonctionné comme un
   pixel de suivi d'ouverture, l'inverse de ce que `/infos#donnees` promet.
3. Reprise du ton, deux allers-retours :
   - D'abord vers un registre trop sec, en fragments sans verbe
     (« Adresse e-mail invalide. Réessai depuis la fiche produit. ») — demandé
     explicitement par la propriétaire après avoir jugé le premier jet trop
     bavard.
   - Puis corrigé une seconde fois : « tu écris comme un robot, accorde au
     moins tes phrases » — retour à des phrases complètes et correctement
     conjuguées (« Sans confirmation sous 7 jours, la demande sera effacée
     automatiquement et aucune alerte ne sera envoyée. »), toujours sans
     bavardage « nous/vous ». **Ce dernier registre est la référence** pour
     tout texte futur sur cette fonctionnalité : phrase complète, ton
     factuel et impersonnel, jamais de fragment en style étiquette.

**Reste ouvert / à surveiller :**
- Aucun vrai e-mail de BAISSE DE PRIX envoyé en conditions (seule la
  confirmation a été testée réellement) — à vérifier au premier passage de
  `mcpipe alertes` qui trouve une alerte confirmée avec une offre fraîche.
- Seuils anti-abus et durée de vie (6 mois) : à ajuster si besoin, aucun retour
  d'usage encore.
- Logo en SVG (demandé en passant par la propriétaire) : pas encore fait, le
  fichier vectoriel source manque.

## 6. Indexation, tailles des bottes, et des filtres enfin rapides (15/10, après-midi)

**Indexation Google.** Propriété `https://motocomparo.com/` validée dans
Search Console (compte de la propriétaire, méthode fichier HTML servi par la
route `/google91d87112b2771314.html` — à ne jamais supprimer). Le sitemap
déclaré jusque-là était `/sitemap_index.xml`, qui n'existe pas (« impossible
de récupérer » depuis le 07/09) : `/sitemap.xml` soumis, lu sans erreur.
Réindexation de l'accueil demandée. GTM ne sert pas à l'indexation.

**Tailles des bottes.** Le filtre Taille des bottes montrait « 8, 11, 34, 2,
M » et jamais une pointure : la regex des facettes (pensée pour vêtements et
gants) prenait les résidus de flux à 1-2 chiffres et ratait `EU36`..`EU52`.
Corrigé dans `facets()` pour le seul rayon bottes (`f725576`).

**Multi-sélection.** Marque et taille se cochent à plusieurs (`= ANY(...)`,
union des valeurs) ; `/m/{marque}` reste une page à marque unique (`36fead6`).

**Pourquoi les filtres étaient si lents — quatre causes empilées :**
1. Robots d'IA. PerplexityBot refusé sur les pages à paramètres (`31859b3`),
   puis, passé aux fiches, plafonné avec ClaudeBot, Bytespider, GPTBot…
   à 30 pages/min PAR FAMILLE toutes adresses confondues (`8112002`) : la
   limite par adresse ne voyait rien, IP tournantes. Charge 5 -> ~1,5.
2. Rechargement complet à chaque clic. Désormais la case se coche à
   l'instant, les coches marque/taille rapprochées partent en une seule
   demande (450 ms), seuls liste et compteurs sont remplacés, tiroir ouvert
   conservé, Précédent/Suivant gérés, repli sans JS intact (`3fae3fe`).
   Référence : Motoblouz (appli Nuxt) et Speedway (PrestaShop + ElasticShop)
   ne rechargent jamais la page.
3. **Bug trouvé en route : sur ordinateur, la colonne de filtres était
   inerte** (non cliquable) — le script du tiroir ne reconnaissait une
   colonne qu'en `static`, elle est en `sticky`. Un tiroir = `fixed` (`3fae3fe`).
4. Plans de requête désastreux en production : « bottes ET sidi » estimé à
   11 fiches (568 réelles), la sous-requête Matière recalculée par fiche —
   10 s, puis 500 au-delà de 15 s dès deux marques. Statistique étendue
   (rayon, marque) via `sql/029` (appliquée en tant que `mcpipe`) + CTE
   `MATERIALIZED` pour Matière/Homologation/Saison (`9765f2b`). Mesuré en
   production : 10-25 s / erreur 500 -> 1,3 à 2,4 s par combinaison neuve,
   résultats identiques sur 18 cas comparés.

Fausse piste écartée : un index sur `product(category_id)` changeait le plan
sans gain (et ralentissait le filtre taille) — retiré, non déployé.

**Reste ouvert :** les ~9 requêtes de facettes coûtent encore 0,1-0,2 s
chacune (1,3-2,4 s par combinaison jamais vue, instantané ensuite grâce aux
caches). Le prochain levier serait d'en réduire le nombre — chantier à mener
avec mesures avant/après, une fusion naïve ayant déjà été essayée et
abandonnée (commentaire dans `queries.py`).

## 7. Fin de journée : filtres, fiche, bandeau cookies (15/10, soir)

- **Colonne de filtres ordinateur** : tient dans l'écran et défile seule ;
  on n'a plus à descendre toute la page pour atteindre Couleur (`14e4d48`).
- **Fiche produit** : l'encadré photo occupe toute la hauteur de la colonne
  prix/tailles, plus de blanc dessous (`90e4ef0`).
- **Filtre « N marchands et + »** retiré du panneau et sa requête avec ; le
  paramètre reste lu pour les anciens liens (`90e4ef0`).
- **Rubriques repliables comme chez Speedway** : Taille, Couleur, Prix… sont
  des accordéons. Ouvertes d'office : Catégories, Marques, et toute rubrique
  avec un choix actif ; les gestes du visiteur sont retenus pour l'onglet
  (`3b3d9dd`). Fausse route d'abord : un bouton « Fermer les filtres » global
  (`ace8d0d`, `9973e8f`) — ce n'était pas la demande, retiré sans trace.
- **Bandeau cookies** d'après la maquette de la propriétaire (cookies casqués
  « M » et « C ») : carte compacte en bas d'écran, sans voile ; « Tout
  refuser » et « Accepter et fermer » de même taille (contour discret sur le
  refus) ; texte de la maquette sans ce qui serait faux (pas de
  personnalisation, pas d'écran de réglages) ; « Continuer sans accepter »
  retiré à sa demande ; plus de cadre de focus jaune à l'ouverture
  (`9c402b7` → `a1b5180`). Tests de consentement verts : refus d'abord,
  Google chargé à l'accord seulement, choix 6 mois, « Gérer les cookies ».

**Reste ouvert à la fin du 15/10 :**
- Blog : la rubrique `/guides` est en ligne, mais les 3 brouillons ne sont
  pas publiés (passages « essai réel » à fournir par la propriétaire, ou à
  réécrire sans prétendre à un essai).
- Alertes de prix : aucun e-mail de BAISSE encore observé en production.
- Facettes : 1,3 à 2,4 s par combinaison neuve ; le prochain levier est d'en
  réduire le nombre de requêtes (chantier mesuré, pas improvisé).
- Logo vectoriel (SVG) : fichier source manquant.
- Anciennes adresses v1 (`/shop/…`, `/product/…`) : répondent 404, encore
  explorées par Google — des redirections 301 récupéreraient ce trafic.
- Base : `VACUUM FULL` à planifier ; restes de l'incident FC-Moto toujours
  sur le VPS (base `mcpipe_restore_tmp`, ~1,7 Go de CSV dans `/tmp`,
  disque à 71 %).
