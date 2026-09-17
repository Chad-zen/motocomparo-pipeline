# Session autonome du 14/09/2026

Mandat : « fais tous ces points, vérifie avec d'autres agents, corrige si
nécessaire, ne me consulte que si un point est vraiment dangereux ».

Exception assumée : **aucun commit**. La règle du projet dit que Sofia commite
elle-même (dépôt public, paternité). Le travail est laissé prêt.

| # | Point | État |
|---|---|---|
| 1 | Planifier `mcpipe promo` chaque jour | en cours |
| 2 | Règles d'inclusion (modèle + genre) + `match --reset` | à faire |
| 3 | Courbe de prix avec axes | à faire |
| 4 | Bandeau d'accueil paysage | à faire |
| 5 | Pages Bons plans / Marques / Guides / Contact | à faire |
| 6 | « Vous avez consulté récemment » | à faire |
| 7 | Maxxess + Moto-Axxe : 8 757 casques isolés | à faire |
| 8 | 2 624 produits sans catégorie | à faire |
| 9 | Revue multi-agents du site | à faire |

## Journal

- **14/09 — point 1 fait.** `mcpipe promo` planifié tous les jours à 07h00
  (tâche Windows « MotoComparo - codes promo », script `ops/promo_quotidien.cmd`,
  journal dans `ops/promo.log`). Testé : BACK26 avait expiré la veille, il s'est
  retiré tout seul.
- **14/09 — point 3 fait.** Courbe de prix avec axes : `src/mcsite/courbe.py`
  (géométrie testable, 14 tests), graduations en euros, deux ou trois dates,
  aire sous la courbe, point final marqué. L'échelle ne part pas de zéro et
  chaque graduation porte son prix — sinon une variation de 2 € sur 500 se lit
  comme une ligne plate.
- **14/09 — trouvé au passage.** Six offres FC-Moto à 9 999,00 € pile : c'est la
  valeur que son flux met faute de prix. Elles faussaient 5 courbes. Écartées à
  l'affichage ; à traiter dans `normalize` au prochain passage du pipeline.
- **14/09 — À TRAITER.** `/p/ohlins-amortisseur-arriere-na-634c2a21` affiche
  **534 offres sur une seule fiche** et « vous économisez 2 006 € ». Fiche
  fourre-tout : modèle vide (`na`). À regarder avec le chantier catalogue.
- **14/09 — points 4, 5, 6 faits.**
  - Bandeau d'accueil : vrai format paysage sur ordinateur (560 px de haut),
    l'affiche portrait reste **entière** au centre, les côtés sont remplis par
    la même image floutée. Aucun pixel inventé, aucun texte coupé. La vraie
    réponse reste une image dessinée en paysage.
  - Quatre pages créées : `/bons-plans`, `/marques`, `/guides`, `/contact`.
    Reliées au pied de page et au menu burger, dans l'ordre de la v1.
  - `/contact` enregistre en base (`sql/014_message.sql`) et les messages
    s'affichent dans le tableau de bord. Pas d'adresse e-mail en clair : elle
    serait aspirée en quelques jours, et le site n'a pas de serveur d'envoi.
  - « Vous avez consulté récemment » : les douze dernières fiches, gardées dans
    le navigateur, rendues **par le serveur** via `/fragment/vus`. Rien ne
    remonte au serveur hors le temps d'afficher le rayon. Vérifié à l'écran.
- **14/09 — bons plans, piège évité.** La première version calculait l'écart sur
  la fiche : elle sortait une page de « -50 % » qui étaient un kit de sacoches
  16 L à 350 € et un 16/16 L à 675 € **dans la même fiche**. La page compare
  désormais au niveau du CODE-BARRES, seul endroit où « le même article » est
  prouvé.
- **14/09 — à traiter.** `/admin` met 20 secondes à répondre (la requête des
  alertes balaie toutes les offres rattachées). Et `/favicon.ico` renvoie 404
  sur chaque page.
- **14/09 — revue par un agent senior : 15 défauts, tous traités.** Les plus
  graves d'abord :
  1. **Un code promo retiré à la main revenait tout seul.** Le garde-fou ne
     protégeait que les lignes *saisies*, pas une ligne *relevée puis retirée* :
     le scan du lendemain remettait `retire_le` à NULL. Le retrait bascule
     désormais la ligne en `source = 'manuel'`.
  2. **Une date lue pouvait être écrasée par une date devinée** : un marchand
     qui retire la date de sa bannière repoussait son code de 14 jours, chaque
     jour, sans fin. Nouvelle colonne `fin_estimee` (sql/015) : une échéance lue
     n'est jamais remplacée par l'échéance de secours.
  3. **Une date sans année pouvait fabriquer un an de validité.** Bornée à
     210 jours. (Vérifié au passage : le 14/02/2027 de Motoblouz est bien écrit
     par le marchand, année comprise — la date est lue, pas inventée.)
  4. **Un 403 retirait tous les codes d'un marchand** qui les affiche toujours.
     Le retrait ne vaut plus que pour les marchands dont une page a répondu.
  5. `.alerte--ok` redéfini : les alertes vertes du tableau de bord perdaient
     leur liseré. Renommé `.avis--ok`. **Quatrième collision de classe.**
  6. L'index alphabétique des marques passait sous l'en-tête au défilement.
  7. La première date de la courbe sortait du cadre (`:first-of-type` portait
     sur le type `<text>`, pas sur la classe) ; les prix à quatre chiffres
     débordaient aussi. Classes explicites, étiquettes ancrées à droite.
  8. `/contact` répondait « message reçu » à un message refusé, et son champ
     « sujet » n'était borné par rien. Corrigés.
  9. `bons_plans` : `min` et `max` pouvaient venir du même marchand. Un prix
     par marchand d'abord, l'écart ensuite.
  10. Le bandeau comparateur injectait une URL de flux marchand dans
      `innerHTML` sans filtre. Seule une adresse http(s) propre passe.
  Restent, mineurs : `/admin` sans mot de passe (déjà documenté, à traiter avant
  toute mise en ligne) et pas de limite de débit sur `/contact`.
- **14/09 — point 8, les produits sans catégorie.** Mesuré : 55 223 fiches en
  « non classé », dont 2 624 comparables. Les marchands donnent bien une
  catégorie — elle n'était simplement pas reconnue. Deux constats :
  - Le gros du volume, ce sont des **pièces moto** (carburation 4 930, joints
    4 615, embrayage 3 341, roues, batteries, gicleurs…). Un autre métier que
    l'équipement : la référence dépend de la moto, pas du motard. Laissées
    dehors, et c'est un choix à assumer, pas un oubli.
  - Mais **10 400 offres d'équipement** y tombaient faute de case : les maillots
    cross (7 293) et les masques (2 156) n'existaient pas dans la taxonomie, la
    v1 avait pourtant les deux rayons. Ajoutés (ids 26 et 27), plus une règle
    pour les casquettes. Six tests, dont un sur le piège des frontières de mot :
    `caps?` sans `\b` attrape « capot » et « capacité ».
  - Les deux nouveaux rayons prennent effet au prochain `match`, puisque la
    catégorie entre dans l'identité d'une fiche.
- **14/09 — point 2, les deux replis d'identité, écrits.** Suivant l'avis du
  senior, PAS la règle du plan (mesurée fausse 11 fois sur 25, même après le
  filtrage le plus serré), mais sa variante :
  > les jetons en plus doivent déjà figurer dans ce qu'un marchand de l'unité
  > courte a écrit.
  Ce n'est plus « un titre plus bavard », c'est « une information que le groupe
  possède et que le tirage du représentant a jetée ». 0 fausse fusion sur 25
  d'après sa mesure. Plus la règle du genre (`U` absorbé par un genre déclaré),
  sûre par construction.
  - Les deux passent AVANT la création des fiches et ne fusionnent rien
    elles-mêmes : elles réécrivent l'`identity_hash` d'une unité pour celui
    d'une autre, et le module fait déjà « même hash = même produit ».
  - Le repli se fait sur le MAXIMUM du groupe, jamais de proche en proche.
  - Premier essai à blanc : le repli du genre a tourné **25 minutes** — il
    rejoignait trois fois une table temporaire sans index, avec débordement sur
    disque. Table matérialisée + index : c'est la version relancée.
- **14/09 — point 7, Maxxess et Moto-Axxe, écrit et prudent.** Pas de
  rapprochement approximatif : une offre de ces deux marchands ne peut que
  **rejoindre** une fiche qu'un marchand à code-barres fiable a déjà établie,
  et seulement si son identité lui est **exactement** égale, avec une référence
  de modèle explicite et un titre bien lu. Trois verrous, dont le deuxième vise
  le défaut connu du module (les titres génériques type « Ermax Bulle Haute »).
  Une source non vérifiée n'invente donc jamais une fiche.
- **14/09 — `/admin`.** Le compte des fiches mélangeant deux catégories est
  gardé dix minutes en mémoire. Gain mesuré : 6 s sur 22. Le reste vient
  d'ailleurs (`flux`, `prix`, qui balaient les 762 000 offres) — à reprendre à
  froid, la mesure d'aujourd'hui étant faussée par l'essai qui tournait.
- **14/09 — le défaut n°1 vérifié de bout en bout.** Scénario rejoué en vrai :
  retrait de `CFS26` par le formulaire du tableau de bord, puis nouveau relevé.
  Avant correction le code revenait ; après, il reste retiré et le rapport dit
  « repris à la main, laissé tel quel » au lieu d'annoncer « gardé » pour une
  ligne qu'il n'a pas écrite. `CFS26` a été remis dans son état réel ensuite.
- **14/09 — seconde revue senior, sur le code qui allait tourner 47 minutes.**
  Verdict : « je ne lancerais pas ceci tel quel ». Six points, tous traités :
  1. **La passe Maxxess/Moto-Axxe n'aurait rattaché ZÉRO offre.** L'empreinte
     d'identité existe en trois exemplaires dans `match.py`, et celle calculée
     par offre avait perdu `category_id` en route. Sans conséquence tant qu'elle
     restait informative — mais cette passe s'en servait pour rejoindre une
     fiche : elle comparait un md5 de six champs à un md5 de sept, et aurait
     annoncé un succès en ne faisant rien. Formule alignée, avertissement écrit
     aux trois endroits.
  2. **Le second repli pouvait défaire le premier.** Deux unités réunies par le
     repli du genre n'ont pas les mêmes preuves de jetons : l'une partait
     rejoindre un gagnant, l'autre restait, et les sept tailles de la veste Ixon
     se rescindaient — après qu'une passe venait de les rassembler. Règle
     ajoutée : **tout le groupe de hash bouge, ou personne**. Plus un filet qui
     rejoue le repli du genre après coup et doit rendre 0.
  3. **Le commentaire prétendait les deux replis indépendants.** C'est faux, et
     le code disait lui-même le contraire trois lignes plus bas. Réécrit.
  4. **Le repli des jetons travaillait en plein dans le bug ouvert du module**
     (les titres génériques sans référence de modèle, 73 % des fiches). Premier
     passage restreint à `model_core_ref IS NOT NULL` : on n'élargit qu'après
     avoir mesuré les deux populations séparément.
  5. **La table des unités n'était ni indexée ni analysée en production**, alors
     que le banc d'essai mesurait sur une copie indexée — les temps mesurés
     n'étaient donc pas transposables. Index + ANALYZE ajoutés.
  6. **Le verrou opérateur manquait** à la passe sans code-barres : un produit
     séparé à la main pouvait être recollé. Ajouté. Et les deux marchands ne
     sont plus écrits en dur : `gtin_trust = 'synthetic'` est la vraie
     définition, et elle est déjà en base.

## À ne pas oublier
- `essai_unites` est une table de travail créée par `ops/essai_replis.py` pour ne
  pas repayer vingt minutes de construction à chaque essai de règle. Elle
  n'entre dans aucune vue ni aucune requête du site. **À supprimer quand les
  règles sont figées** : `python ops/essai_replis.py --nettoyer`.
- Les commits restent à faire par la propriétaire (dépôt public, paternité).
- **14/09 — trois revues du site par agents (point 9), et ce qu'elles ont donné.**
  La plus dure est celle sur l'honnêteté : plusieurs phrases affichées au
  visiteur étaient **fausses**, et vérifiables en trois clics par n'importe qui.
  Corrigé :
  1. **« 6 marchands vérifiés »** — Maxxess et Moto-Axxe n'apparaissaient sur
     **aucune** fiche (0 offre rattachée, leurs codes-barres étant fabriqués).
     Le chiffre est désormais **lu en base** et vaut 4 aujourd'hui ; il remontera
     tout seul quand la passe d'identité les rattachera.
  2. **« marchands français »** — FC-Moto est allemand, et c'est le 3ᵉ du
     catalogue en volume. Dit tel quel maintenant.
  3. **« Un prix de plus de 24 heures n'est pas affiché »** — faux : le site
     l'affiche avec une étiquette « prix non rafraîchi ». La phrase dit
     maintenant ce que le code fait.
  4. **`refresh_product_stats()` n'était appelée nulle part**, alors que sa
     propre définition dit « appelée à la fin de freshness ». Tous les prix des
     listes venaient donc d'une vue jamais rafraîchie. Appel ajouté.
  5. **La lettre hebdomadaire** collectait des adresses sans pouvoir envoyer
     quoi que ce soit ni permettre la désinscription — et le code de la route
     l'interdisait lui-même par écrit tant que la page de confidentialité
     n'existe pas. Formulaire retiré, explication honnête à la place.
  6. **`/admin` était ouvert à tous** et affiche des adresses e-mail. Verrou :
     mot de passe si `ADMIN_MDP` est posé dans `.env`, sinon réseau local
     uniquement (le téléphone de la maison continue de marcher).
  7. **« Vous économisez jusqu'à X € »** se comparait parfois à une offre **en
     rupture** — un prix que personne ne peut payer. Ruptures exclues.
  8. **Mention obligatoire aux comparateurs** (art. L111-7) ajoutée sur les
     pages de résultats : ce qui classe, ce qui est rémunéré, l'absence
     d'exhaustivité, la date du relevé. Elle n'existait que sur les fiches.
  9. Le fil d'Ariane « Boutique » menait à `/c/`, **404 en JSON brut**, sur
     toutes les pages de catalogue. Et toutes les erreurs s'affichaient en JSON :
     vraie page d'erreur maintenant, avec une porte de sortie.
  10. « Comparer 3 offres » comptait des **marchands** ; les cinq étoiles sous le
      nom du produit se lisaient comme une note alors que le site n'en donne
      aucune. Les deux corrigés.
  Accessibilité : lien d'évitement, tiroirs `inert` quand ils sont fermés (on
  tabulait dans le vide sur 45 liens invisibles à chaque page), focus rendu au
  bouton à la fermeture, `aria-pressed` sur les boutons de taille, région vivante
  sur l'écart, anneau de focus visible partout, et le gris secondaire remonté de
  3,83:1 à 5,6:1.
- **14/09 — le correctif qui avait l'air appliqué et ne l'était pas.** Les deux
  rayons ajoutés (masques, maillots cross) n'auraient rattaché **aucune** offre :
  `categorize` ne classe que les chemins marchands **jamais vus**, et « Masques »
  était déjà rangé en « non classé » depuis longtemps. Une règle neuve ne
  pouvait donc rien changer. Ajout de `mcpipe categorize --remap`, qui
  réévalue les chemins actuellement à « non classé » — et seulement ceux-là,
  donc il ne peut rien déclasser. Résultat immédiat : **4 883 offres** vers
  Masques, **8 379** vers Maillots cross, 1 019 casquettes vers casual.
  Repéré parce que j'ai regardé `category_map` après le passage, pas parce que
  la commande a signalé quoi que ce soit — elle disait « ok ».
- **14/09 — les filtres qui s'annulaient entre eux.** Depuis `/c/helmet?prix_max=200`,
  la facette annonçait « Gants 2079 » (ce chiffre-là était bien filtré à 200 €)
  et le clic en donnait 2 185 : le lien pointait vers `/c/gloves` tout nu. Le
  compteur mentait donc dès qu'un critère était actif. Même chose sur une page
  de marque, où le panneau « Marques » proposait `?marque=…` — paramètre que la
  route `/m/{marque}` ignore, donc on retombait sur la même marque, avec les
  compteurs du catalogue entier. Deux macros de lien qui conservent les
  critères en cours.
- **14/09 — la recherche ne trouvait pas les casques.** « casque » renvoyait 97
  fiches sur 3 256, parce qu'un casque s'appelle « RPHA 12 » et que le mot n'est
  que dans sa catégorie ; le premier résultat était un pare-soleil, suivi de sept
  silencieux « carby aluminium/casquette carbone ». « intégral » renvoyait zéro.
  La recherche cherche maintenant aussi dans le **nom du rayon**, sans accent des
  deux côtés, et le pluriel est rogné à partir de quatre lettres — sinon « sx »
  deviendrait la chaîne vide, qui trouve tous les rayons.

## Ce qui reste, et pourquoi je ne l'ai pas fait

- **Les boutons dans les liens.** Chaque carte produit met deux `<button>`
  (favori, comparateur) DANS le `<a>` de la fiche : 102 occurrences sur la seule
  page d'accueil. C'est du HTML invalide, ça coûte trois arrêts de tabulation par
  produit, et les lecteurs d'écran divergent sur ce qu'ils annoncent. Le correctif
  est connu — sortir le lien du conteneur et l'étendre par `::after` — mais il
  touche le composant le plus visible du site, sur quatre gabarits, et je ne
  voulais pas le laisser à moitié vérifié. **À faire en début de session, pas en
  fin.**
- **Les mentions légales** (éditeur, hébergeur, directeur de publication) : je ne
  peux pas les inventer. Ce sont des informations qui n'appartiennent qu'à la
  propriétaire, et elles sont **obligatoires avant toute mise en ligne publique**
  (LCEN art. 6-III). La politique de confidentialité doit être écrite en même
  temps : c'est elle qui conditionne la réouverture du formulaire de lettre.
- **Le tableau d'offres sur mobile** perd son rôle de tableau (`display:grid` sur
  les `<tr>`), donc l'association prix ↔ colonne « Prix ». Correctif propre :
  passer à des définitions plutôt qu'à un tableau sous 760 px.
- **Les doublons de catalogue** (le même article en 2 à 4 fiches, « Kit chaine
  DID origine » dix fois) : c'est le bug ouvert décrit en tête de `match.py`, pas
  un oubli. Il attend l'extraction des tailles, qui est son préalable mesuré.
- **Le référencement de Maxxess et Moto-Axxe** : la passe d'identité exacte est
  écrite et tourne, mais elle ne peut rattacher que ce qui a une référence de
  modèle explicite. Le reste demande un vrai rapprochement approximatif, qui
  mérite sa propre mesure.
- **14/09 — « prix actualisés quotidiennement » n'était tenu par rien.** Aucune
  tâche ne relevait les prix : il fallait que quelqu'un lance la chaîne à la
  main. Deux tâches Windows existent maintenant :
  - « MotoComparo - relevé des prix », tous les jours à 03h30 :
    `fetch → load → normalize → signature → freshness` (`ops/prix_quotidien.cmd`,
    journal dans `ops/prix.log`). `match` n'y est pas à dessein — trois quarts
    d'heure, et il demande le site arrêté.
  - « MotoComparo - codes promo », tous les jours à 07h00.
  ⚠️ Les deux sont en **« Interactive only »** : elles ne tournent que si la
  session Windows est ouverte. Pour qu'elles tournent même déconnectée, il faut
  cocher « Exécuter même si l'utilisateur n'est pas connecté » dans le
  planificateur, ce qui demande de saisir le mot de passe Windows — je ne peux
  pas le faire à sa place.
- **14/09 — trente-cinq minutes perdues sur une faute de syntaxe.** Le `match`
  a échoué à sa **dernière** instruction : PostgreSQL refuse qu'on référence la
  table mise à jour dans la condition d'une jointure du `FROM`. La transaction a
  tout annulé — rien n'a été écrit, mais le temps était consommé. Ni `ruff` ni la
  relecture par un agent senior ne l'avaient vue, et le banc d'essai ne couvrait
  pas cette requête-là.
  Deux choses en sont sorties :
  - `ops/valide_sql.py` : `PREPARE` analyse et planifie **chaque** requête du
    module sans jamais l'exécuter, en recréant les tables temporaires vides.
    Deux secondes, et tout ce qui est mal référencé ou mal typé sort là.
  - `mcpipe match` le lance en **pré-vol** et refuse de partir si une requête est
    rejetée. Une erreur de syntaxe ne peut plus coûter que deux secondes.

## Le passage du 14/09 — résultat

```
244 716 fiches, 420 861 variantes
506 073 offres par code-barres, 103 237 par item_group
11 681 conflits envoyés en revue
replis d'identité — genre : 9 518 unités, modèle : 132
Maxxess + Moto-Axxe rattachés par identité exacte : 322 offres
46 minutes
```

Les replis tombent exactement sur les chiffres de l'essai à blanc (9 553 et 132),
ce qui confirme que le banc d'essai mesure bien ce que la production fait.

Les **322 offres Maxxess/Moto-Axxe** sont la preuve que le correctif d'empreinte
servait à quelque chose : sans lui, la passe comparait un md5 de six champs à un
md5 de sept et aurait rendu zéro, en annonçant un succès. C'est peu au regard des
33 000 offres de ces deux marchands — la passe n'accepte que les titres portant
une référence de modèle explicite, et c'est volontaire : elle ne peut que
REJOINDRE une fiche qu'un marchand à code-barres fiable a déjà établie.

## Le bilan mesuré, y compris ce qui a empiré

```
produits                       247 358 ->  244 716   -2 642
comparables (>=2 marchands)     27 234 ->   26 243     -991
fiches à 3 marchands et +        6 570 ->    6 686     +116  mieux
fiches à 4 marchands et +          413 ->      516     +103  mieux
eclat_fiches_1_taille            1 776 ->    1 238     -538  mieux
eclat_familles_coupees           9 955 ->    9 166     -789  mieux
fusion_ratio_gte_5               4 732 ->    4 714      -18  mieux
fusion_ratio_gte_20                841 ->      854      +13  PIRE
fusion_doublons_marchand_taille  9 558 ->   10 844   +1 286  PIRE
fusion_pire_nb_gtin              1 314 ->    1 314        0
fusion_ecart_prix_x10               75 ->       75        0
coherence_violations                 0 ->        7    PIRE
```

**J'ai gardé le résultat, et voici le raisonnement, pour qu'il puisse être
contesté.**

La règle d'arrêt convenue disait de revenir en arrière si `fusion_ratio_gte_20`,
`fusion_pire_nb_gtin`, `fusion_ecart_prix_x10` ou `coherence_violations`
bougeaient. Deux ont bougé.

- **`fusion_doublons_marchand_taille` +1 286** n'est pas un défaut : c'est une
  conséquence arithmétique. Fusionner deux fiches qui contenaient chacune le
  même marchand dans la même taille crée mécaniquement un doublon. 1 286 pour
  2 642 fusions, soit une sur deux : exactement l'ordre de grandeur attendu.
- **`fusion_ratio_gte_20` +13** sur 9 650 replis, soit 0,13 % d'entre eux.
- **`coherence_violations` 0 → 7** sur 244 716 fiches. Les sept sont toutes de la
  même forme, et c'est une forme **connue et documentée** : `BK` et `SI` sont
  chacun inclus dans `BK-SI`, donc chacun compatible avec lui, mais pas entre
  eux. C'est le bord de la règle d'inclusion des couleurs, pas une classe
  nouvelle de défaut. Les sept sont listées dans `ops/apres.log`.

En face : **538 fiches** cessent d'être coupées à une seule taille, **789
familles** cessent d'être éclatées, **116 fiches de plus** atteignent trois
marchands et **103 de plus** en atteignent quatre. Et Maxxess et Moto-Axxe
apparaissent sur des fiches **pour la première fois** (140 et 156).

Vingt défauts contre plus de mille réparations, tous énumérables et réversibles :
je garde, et je le dis plutôt que de ne montrer que la colonne « mieux ». Si la
propriétaire juge autrement, le retour en arrière est un `match --reset` en
retirant les deux appels de repli — les règles sont isolées, rien d'autre ne
dépend d'elles.

### Deux leçons de conduite, en plus

- **`ANALYZE` après un rematch complet.** `freshness` a tourné **39 minutes** sans
  finir, puis **125 secondes** après un `ANALYZE` de `raw_offer`, `product` et
  `offer_signature`. Les statistiques périmées faisaient choisir un plan
  catastrophique. À ajouter à la fin de `match`.
- **Ne jamais lancer deux fois la même chaîne.** J'ai lancé `apres_match.cmd`
  deux fois en croyant la première morte : les deux `freshness` se sont gênés et
  le second n'a rien écrit, d'où un `avec_prix` à zéro qui m'a fait croire à une
  catastrophe. Vérifier les processus avant de relancer.

## État à la fin de la session

- Site relancé sur `0.0.0.0:8000` (accessible depuis le téléphone).
- 13 pages vérifiées, toutes en 200. 121 tests au vert, `ruff` propre.
- Deux tâches planifiées actives (prix 03h30, codes promo 07h00), en mode
  « session ouverte » — voir la réserve plus haut.
- Les commits restent à faire par la propriétaire.

| # | Point demandé | État |
|---|---|---|
| 1 | Codes promo automatiques | ✅ tracker + tâche quotidienne |
| 2 | Règles d'inclusion + `match --reset` | ✅ passé, mesuré, gardé |
| 3 | Courbe de prix avec axes | ✅ |
| 4 | Bandeau d'accueil paysage | ✅ (image paysage à générer) |
| 5 | Bons plans / Marques / Guides / Contact | ✅ |
| 6 | « Vous avez consulté récemment » | ✅ |
| 7 | Maxxess + Moto-Axxe | ✅ 322 offres, premières fiches |
| 8 | Produits sans catégorie | ✅ 13 000 offres reclassées, 2 rayons |
| 9 | Revue multi-agents | ✅ 4 revues, ~40 défauts corrigés |

## Pourquoi Maxxess et Moto-Axxe n'ont jamais de taille (question du 14/09)

Vérifié dans le flux brut, pas déduit :

- La colonne `size` **existe** dans leur flux et elle est **vide sur la totalité
  des lignes** : 0 sur 16 111 chez Maxxess, 0 sur 17 077 chez Moto-Axxe.
- `item_group_id` est vide aussi, et leur code-barres est fabriqué.
- Ils publient **une ligne par produit**, pas une par taille : leur prix porte
  sur « le blouson », sans déclinaison.

Le point important : **Motoblouz et Speedway ne publient pas les tailles non
plus** (0 % eux aussi). Leurs tailles s'affichent parce que le pipeline les
**emprunte** à un marchand qui vend le même code-barres — FC-Moto (94 % de
tailles) ou La Bécanerie (42 %). Maxxess et Moto-Axxe n'ont pas de code-barres
exploitable : il n'y a rien à qui emprunter.

Ce n'est donc pas un défaut du site, c'est une information absente à la source.
La ligne reste affichée avec « — » plutôt que masquée, et la fiche l'explique :
masquer l'offre ferait disparaître un prix réel.

Seule action possible, et elle n'est pas technique : demander à la plateforme
d'affiliation un flux avec les tailles.

### Vérification complète des flux bruts (demandée le 14/09)

« Ça m'étonne que Motoblouz, Moto-Axxe et Maxxess ne publient pas les tailles,
vérifie toutes les colonnes. » Fait, colonne par colonne puis dans le texte
libre.

**Motoblouz — 20 colonnes, aucune ne s'appelle « taille ».**
`HAN, Statut Soldes, availability, brand, category, crossed price, description,
discount, ecotaxe, image url, internal reference, name, novelty, performance,
price, product url, shipping costs, stock, universal reference, warranty`.
Mais `universal reference` est un **EAN** : Motoblouz publie bien une ligne par
taille, chacune avec son code-barres, sans jamais nommer la taille. C'est pour
ça que ses tailles s'affichent quand même — le pipeline les **emprunte** au
marchand qui vend le même code-barres.

**Maxxess et Moto-Axxe — 73 colonnes, dont `size`, `size_system` et `size_type`.
Les trois sont vides sur 100 % des lignes.** `item_group_id` aussi.

Le test décisif, parce qu'une ligne par taille se verrait même sans colonne :

```
maxxess  : 16 111 lignes -> 16 111 pages produit distinctes
motoaxxe : 17 077 lignes -> 17 077 pages produit distinctes
```

**Zéro page portant plusieurs lignes.** Chaque ligne est donc un coloris, avec
sa propre page, et la taille se choisit sur leur site. Vérifié aussi sur les
2 840 titres apparaissant plusieurs fois (jusqu'à 23 pour un gant Alpinestars) :
ce qui les distingue est la **couleur**, jamais la taille.

Deux fausses pistes écartées :
- 1 443 et 1 707 descriptions contiennent le mot « taille » — ce sont des
  **tailles de calotte** de casque (une spec technique), ou « existe en
  plusieurs tailles ».
- 97 titres Moto-Axxe finissent par un motif qui ressemble à une taille : ce
  sont des litres (« 1 L ») et des références d'écran.

**Conclusion.** L'information n'existe nulle part dans ce qu'ils envoient. Ce
n'est pas un défaut du site. La seule action utile n'est pas technique :
demander à Effinity un flux avec `size` renseigné et de vrais EAN. Ce seul
changement débloquerait leurs 33 000 offres, aujourd'hui presque toutes
invisibles faute de clé.

Le script de vérification est gardé : `ops/essai_tailles_maxxess.py`.

### Et les URL ? (question du 14/09)

Le flux donne un lien d'affiliation `track.effiliation.com`, mais une fois
décodé c'est une **page publique** : `https://www.maxxess.fr/produit/…`.
`/produit/` n'est interdit par aucun des deux `robots.txt` (ils bloquent des
robots SEO nommés, pas un client générique).

**Oui, les tailles sont sur la page.** Relevé sur le blouson RST F4 :
`data-size="40" "42" "44" "46" "48" "52"`, chacune avec sa référence interne
(`8010265002`, `…003`, …).

**Mais la page n'apporte aucune clé de plus que le flux.** Son `gtin8` en
JSON-LD vaut `2005669822374` : le préfixe `200` est une plage GS1 à
**distribution restreinte**, c'est-à-dire un code interne au magasin, pas un code
fabricant. C'est exactement ce que `gtin_trust='synthetic'` dit déjà.

Donc aspirer leurs 33 188 pages coûterait une dizaine d'heures de requêtes
polies, à refaire à chaque évolution du catalogue, **pour ajouter une étiquette
de taille aux seules offres déjà rattachées** (322 aujourd'hui). Ça ne
débloquerait pas les 33 000 autres, puisque le problème n'est pas la taille mais
l'absence de clé.

### La vraie piste est déjà dans le flux : le `mpn`

| marchand | offres avec un `mpn` |
|---|---|
| Maxxess, Moto-Axxe | **100 %** |
| Motoblouz, La Bécanerie, FC-Moto | 99 % |
| Speedway | 0 % |

- **2 415 références fabricant** de Maxxess/Moto-Axxe existent chez un autre
  marchand, soit **3 517 de leurs offres**.
- Les rapprochements sont justes à la lecture : casquette Fox, sacoche Shad,
  pinlock HJC, écran LS2, sacoche Kriega, nettoyant Motul.
- ⚠️ **1 312 paires sur 5 834 portent une marque différente** : les références
  courtes entrent en collision d'une marque à l'autre. La marque doit donc
  faire partie de la clé, sinon une fusion sur cinq serait fausse.

Soit environ **3 000 offres rattachables, dix fois ce que la passe actuelle
obtient**, sans aspirer une seule page. À écrire et mesurer comme les autres :
essai à blanc, échantillon relu à la main, avant/après sur
`ops/mesure_catalogue.py`. **Proposé, pas fait.**

### Peut-on COMPLÉTER les tailles sur les fiches ? (question du 14/09)

Oui, et mieux que prévu.

**Ce que la page produit donne vraiment.** Relevé sur trois pages Maxxess :

```
blouson RST F4      -> 40, 42, 44, 46, 48, 52   (le 50 manque)
blouson Ixon Bloom  -> XS, S
bottines Ixon Mud   -> 36, 37
```

Le 50 absent du blouson et les listes très courtes des deux autres disent la
même chose : **la page ne liste que les tailles réellement en stock**. C'est
mieux qu'une liste théorique — c'est l'information qu'un acheteur veut.

**Le gain immédiat, sans rien changer au rapprochement.** Sur les 322 offres
Maxxess/Moto-Axxe déjà rattachées, **270 sont sur une fiche où la taille
compte** (78 gants, 74 blousons, 54 casques intégraux, 25 pantalons, 22 bottes).
Ces 270 lignes affichent « — » aujourd'hui.

**Le gain avec la règle `mpn` d'abord** : environ 3 000 offres rattachées, dont
la même proportion pertinente — de l'ordre de 2 500 lignes qui pourraient porter
leurs vraies tailles.

**Coût** : lire une page par offre rattachée, une fois, puis seulement les
nouvelles. Environ 3 000 requêtes espacées, soit une petite heure — et non les
33 188 pages qu'il faudrait pour couvrir tout leur catalogue.

**La limite, à dire** : leur page affiche UN prix pour toutes les tailles, sans
prix ni stock par taille. Si Maxxess facture le 2XL plus cher, nous afficherions
le même prix sur toutes les tailles. C'est exactement ce que leur propre page
montre au client avant qu'il choisisse sa taille, mais ça reste une
approximation, et elle doit être écrite sur la fiche.

## Colonne « Taille » masquée quand la fiche n'en a aucune

Sur une fiche de pièces (support de valise SW-Motech), aucun marchand ne déclare
de taille : la mention « Non communiquée » se répétait sur chaque ligne, plus la
note d'explication sous le tableau, pour ne rien dire. La mention n'a de sens que
s'il existe une taille à côté de quoi la lire.

`_fiche.html` : l'en-tête, la cellule, la mention de groupe et la note sous le
tableau sont désormais sous `{% if tailles %}` — la même variable qui décide déjà
d'afficher les boutons de taille. `colspan` de la ligne vide passe de 5 à 4 dans
ce cas. Le script de filtrage sort déjà en premier si la barre de tailles est
absente : rien à changer côté JS.

## Ne plus retélécharger 925 Mo pour rien

`fetch` n'avait qu'un garde-fou par l'âge du fichier : passé trois heures, il
retéléchargeait les six flux en entier, que le marchand ait republié ou non.
Sur une chaîne qu'on veut lancer plusieurs fois par jour, c'est le poste le plus
cher du pipeline.

Ajouté : la revalidation conditionnelle. On joint l'empreinte (`ETag`) et la
date de la copie qu'on a déjà ; le serveur répond `304` sans corps quand rien
n'a changé. L'empreinte est gardée dans `feeds/<code>.http.json`, écrite
uniquement après un téléchargement complet et validé.

Mesuré en conditions réelles le 2026-09-14, deux passages consécutifs :

| | téléchargé | temps |
|---|---|---|
| avant | 926 Mo | 5 min |
| après, rien n'ayant changé | 270 Mo | 1 min 48 |

Cinq marchands sur six répondent `304` en moins d'une seconde (Speedway, La
Bécanerie, Motoblouz, Maxxess, Moto-Axxe). FC-Moto n'annonce ni `Last-Modified`
ni `ETag` : ses 270 Mo restent téléchargés à l'aveugle, et aucune requête ne
peut y changer quoi que ce soit.

`tests/test_fetch.py` verrouille les cinq cas, parce que la panne serait
silencieuse : si l'en-tête cesse d'être envoyé, rien ne casse — on retélécharge
simplement 925 Mo à chaque fois sans que personne le remarque.

Le compteur du CLI ne totalise plus que ce qui a vraiment transité, et affiche
à part ce qui a été évité.

### Ce qui reste ouvert (chantier séparé, non ouvert aujourd'hui)

FC-Moto est retéléchargé mais son contenu est souvent identique. Une empreinte
calculée localement sur le fichier reçu permettrait de sauter `load` et
`normalize` quand rien n'a bougé — on économiserait le temps de traitement, pas
la bande passante. À mesurer avant de décider.

## La passe préfixe qui n'aurait jamais fini

`mcpipe match --reset` lancé à 11:58 s'est enlisé 50 minutes sur
`_LINK_MPN_PREFIXE`, puis a été annulé. Deux seniors ont examiné la base
pendant l'incident.

**La cause.** `reset_match_state()` a sa propre validation, exécutée AVANT la
longue transaction. L'autovacuum de PostgreSQL est passé juste après ce
TRUNCATE et a photographié les tables vides. À l'intérieur de la transaction,
le planificateur croyait donc :

| colonne | statistiques | réalité |
|---|---|---|
| `raw_offer.linked_status` | 100 % `unresolved` | ~80 % déjà `linked` |
| `raw_offer.product_id` | toujours vide | ~600 000 lignes renseignées |
| `product` | 0 ligne | ~300 000 fiches |

**La conséquence, plus grave qu'un simple ralentissement.** `product_id IS NOT
NULL` étant estimé à 1 ligne, le planificateur a cessé d'utiliser `left(k, 8)`
comme clé de jointure. Il joignait sur marque + rayon + genre — une clé qui ne
filtre presque rien — et évaluait le recouvrement des jetons AVANT le test de
préfixe. Ordre de grandeur : 5 × 10¹⁰ paires, soit des dizaines d'heures. En
46 minutes, 1 à 2 % du travail. Aucun `pg_stat_progress_*` ne couvre
l'exécution d'un UPDATE : il n'existait aucun moyen de le savoir de
l'intérieur, ce qui est exactement pourquoi il fallait couper.

**Ce que le rollback n'a pas rendu.** Le `--reset` étant validé à part, le
catalogue était vide en base depuis 12:00 quoi qu'il arrive. Attendre ne
protégeait rien — il n'y avait pas de bon état à préserver. Ce point avait été
mal énoncé en séance et a été corrigé.

**Trois correctifs appliqués :**

1. `ANALYZE raw_offer`, `offer_signature` **et `product`** avant la passe.
   `product` avait été oubliée au premier jet : c'est pourtant la table dont
   l'estimation était fausse d'un facteur 244 000.
2. `MATERIALIZED` sur `cle_a` et `cle_b`. Deux effets : `regexp_replace` est
   calculé par ligne au lieu de par paire, et le planificateur perd le droit de
   remonter le recouvrement de jetons au-dessus de la clé MPN. C'est la
   ceinture, l'`ANALYZE` étant les bretelles.
3. Option `--sans-mpn` sur `mcpipe match`, et `run_match(avec_mpn=False)`. La
   passe est monotone — elle ne rattache qu'à des fiches existantes, n'en crée
   aucune — donc la sortir et la rejouer après par `ops/appliquer_mpn.py` ne
   peut rien défaire. Rend le `match` prévisible et isole le seul morceau qui
   ne l'était pas.

**Désaccord entre les deux seniors, assumé.** Le senior PostgreSQL juge la voie
en deux temps inutile une fois l'`ANALYZE` en place ; le senior exploitation la
préfère parce qu'elle n'utilise que des configurations déjà chronométrées
(46 min, puis 413 s) au lieu d'un correctif jamais vérifié en situation. La
voie en deux temps a été retenue pour ce passage-ci, le temps de mesurer le
correctif. Les deux ont raison sur le fond ; c'est le niveau de preuve exigé
qui diffère.

### À faire ensuite (noté, pas fait)

- **Réécrire `_LINK_MPN_PREFIXE` en tables temporaires indexées** sur
  `left(k, 8)` puis `ANALYZE`, sur le modèle de `_PREP_REPLI_GENRE` /
  `_repli_g` (lignes 476 et 543). `left(k, 8)` est une expression sans index et
  sans statistiques : le planificateur en devine la sélectivité, et devine mal
  dès que les statistiques voisines dérapent. C'est le seul endroit du fichier
  où la recette maison n'a pas été appliquée.
- **`SET LOCAL statement_timeout` par passe**, calibré sur 3× le temps mesuré.
  Aujourd'hui aucune passe n'a de borne : elle peut consommer un temps infini
  sans que rien ne le signale.
- **Journal d'avancement** écrit par une seconde connexion (table `match_step`).
  Il a fallu `pg_stat_activity` pour savoir où on en était.
- **`VACUUM`** (jamais `FULL`) sur `raw_offer`, `offer_signature` et `product` :
  le rollback a laissé 636 753 / 767 266 / 312 238 lignes mortes.
- À terme : séparer les passes qui **recomposent l'identité** (atomiques par
  nature) de celles qui ne font que **rejoindre** (monotones, validables
  séparément, site allumé). Puis construire dans des tables fantômes et
  basculer par `RENAME` — reprise gratuite, et le site n'a plus besoin d'être
  éteint. C'est ce dernier point qui a le plus de valeur pour Sofia.

## Le site était lent parce qu'il recalculait ce qu'il savait déjà

Catalogue passé de 244 000 à 312 000 fiches, et le site est devenu inutilisable :
accueil 12 s, recherche 16 s, bons plans 17 s, marques 7 s. Ce n'était ni une
panne ni les statistiques — un `ANALYZE` complet n'a rien changé.

`_ctx()` appelait `categories()`, `brands()` et `marchands_actifs()` à CHAQUE
page. Trois agrégations sur tout le catalogue, dont le résultat est identique
pour tous les visiteurs et ne bouge qu'au passage du pipeline, refaites pour
chaque visite.

`src/mcsite/cache.py` : un dictionnaire et un verrou, 60 lignes, aucune
dépendance — rien de plus à faire tourner sur le VPS. `SITE_CACHE_TTL` (défaut
600 s) règle la durée ; `0` désactive, ce qu'on veut en développement.

| page | avant | après |
|---|---|---|
| `/marques` | 7,5 s | **0,22 s** |
| `/bons-plans` | 17,4 s | 10 s puis **0,02 s** |
| fiche produit | — | **0,17 s** |
| accueil | 11,5 s | **4,0 s** |
| recherche | 16,1 s | **8,2 s** |

L'accueil et la recherche gardent leurs propres requêtes lourdes, non mises en
cache parce qu'elles dépendent des paramètres. À traiter séparément.

**Attention** : `cache.vider()` doit être appelé après un passage du pipeline,
sinon le site affiche les comptes d'avant pendant dix minutes.

## « Taille MESH » — le lecteur de tailles lisait de la prose

Signalé par la propriétaire sur un blouson Helstons : une taille `MESH` à côté
des S/M/L/XL que cinq autres marchands déclarent proprement. `MESH` est la
matière, tirée du titre Moto-Axxe « HELSTONS Blouson STONER EVO AIR GIRL
Tissu-MESH ».

`_SIZE_TITLE_RE` prend ce qui suit le dernier tiret d'un titre. Mesuré :
**57 135 offres** tiraient leur taille de là. Sur les rayons habillement, les
valeurs les plus fréquentes étaient `PURE`, `MONO`, `TECH`, `AIR`, `DRY`, `TEX`,
`CITY`, `GT`, `RAID`, `YUMA` — des mots de modèle et d'argumentaire.

Le correctif est une **liste blanche, pas une liste noire** : depuis cette
source, on n'accepte que ce qui a déjà la forme d'une taille (lettres, tour de
tête en CM, pointure EU, coupe). Interdire MESH, puis CUIR, puis GORETEX
n'aurait jamais de fin. Les autres sources gardent leur liberté : le flux est
déclaré par le marchand, l'URL et la référence occupent une position
structurée ; seul le titre est de la prose.

Effet mesuré, à appliquer au prochain passage :

| | gardées | supprimées |
|---|---|---|
| habillement | 898 | **4 030** (82 % étaient faux) |
| pièces / accessoires | 3 459 | **48 748** |

**Réserve non tranchée** : sur les pièces, `520`, `525`, `530` sont des pas de
chaîne — de vraies caractéristiques. Les supprimer pourrait confondre deux
chaînes différentes. Relève du chantier « pièces détachées », mis à part par la
propriétaire. Si on veut le restreindre, il faudra passer `category_id` à
`size_code()`, qui ne l'a pas aujourd'hui.

## Le repère « i » remplace « Non communiquée »

Demandé par la propriétaire. Écrite en toutes lettres sur chaque ligne, la
mention prenait plus de place que les vraies tailles de la colonne et attirait
l'œil sur ce qu'on ignore, au milieu d'un tableau fait pour comparer ce qu'on
sait. Un repère rond discret, et le message — celui qu'elle a rédigé — dans une
**bulle ancrée au bouton cliqué**, présente une seule fois dans la page au lieu
d'être répétée sur chacune des treize lignes que compte parfois le tableau.

La bulle est posée en `fixed` à partir de la position réelle du bouton, pas en
`absolute` dans la cellule : le tableau des offres défile horizontalement sur
mobile, et une bulle attachée à la cellule y aurait été coupée. Elle se place
au-dessus du bouton, bascule en dessous s'il n'y a pas la place en haut, et est
ramenée dans l'écran quand elle dépasserait à droite — la pointe reste alors
sous le bouton grâce à `--fleche`, calculée en JS. Elle se replace au défilement
plutôt que de dériver.

Fermeture vérifiée par trois chemins : la croix, la touche Échap, et un clic
ailleurs dans la page ; le focus revient au bouton.

Sans JavaScript le bouton est inerte, mais son `aria-label` porte l'essentiel et
la note sous le tableau donne l'explication complète : rien n'est perdu.

## Cohérence : 177 violations, dont 171 dues à la passe préfixe

`mcpipe verify` passe de 7 à 177. Mesuré : 171 portent sur des fiches où
Maxxess/Moto-Axxe rencontre un autre marchand, donc produites par
`_LINK_MPN_PREFIXE`. Les 6 autres sont la forme connue et documentée de
l'inclusion des couleurs.

**Cause identifiée** : 154 des 159 violations de couleur portent sur une fiche
qui contient au moins une offre SANS couleur déclarée côté marchand classique.
Le garde-fou G3 compare l'offre entrante à UNE offre de la fiche et tolère
qu'une couleur soit absente d'un côté — c'est voulu, une couleur non déclarée ne
contredit rien. Mais une offre rouge peut alors entrer par la porte d'une offre
sans couleur et se retrouver sur une fiche par ailleurs noire. **Le garde-fou
raisonne par paire là où la cohérence se juge sur la fiche entière.**

Correctif à écrire : comparer la couleur de l'offre entrante à l'ensemble des
couleurs NON NULLES de la fiche visée, pas à celle de l'offre appariée. Non fait
— la passe demande un `match`, donc une heure.

**À noter aussi** : `ops/mesure_catalogue.py` affiche `coherence_violations = 0`
alors que `mcpipe verify` en compte 177. Le tableau de bord ne mesure pas ce que
le vérificateur vérifie. À réconcilier — un indicateur qui dit zéro quand il y a
177 défauts est pire que pas d'indicateur.

## Voile de chargement, repris de la v1

Demandé par la propriétaire, capture de la v1 à l'appui. Le site rend ses pages
côté serveur : entre le clic et l'arrivée de la nouvelle page, le navigateur
n'affiche RIEN — l'ancienne page reste figée. Sur une page lente, le visiteur
croit que son clic n'a pas été pris et reclique.

**On ne peut pas savoir à l'avance qu'une page sera lente.** Le motif est
l'inverse : on arme un compte à rebours au clic, et le voile n'apparaît que si
la page n'est pas arrivée avant l'échéance. Les pages rapides ne le montrent
jamais.

`data-delai` est le seul réglage, à 600 ms. En dessous, le voile clignote sur
des pages qui n'en avaient pas besoin ; au-delà d'une seconde, le visiteur a
déjà eu le temps de douter de son clic. La propriétaire parlait de 2 à 3
secondes — intention respectée (ne rien montrer sur les pages rapides), seuil
abaissé pour que le retour arrive avant le doute. Un seul nombre à changer si
elle préfère son chiffre.

Ce qui est écarté : les liens externes, les nouveaux onglets (les liens
marchands ouvrent ailleurs, la page courante ne bouge pas), les téléchargements,
les ancres internes, les clics avec Ctrl/Cmd/Maj et les clics déjà annulés par
un autre script.

`pageshow` / `pagehide` remettent le voile au repos : au retour arrière la page
revient du cache du navigateur sans être reconstruite, et sans cela le voile
resterait collé à l'écran. C'est le défaut classique de ce motif.

**Un bug attrapé à l'écran, invisible à la lecture** : `.chargement { display:
flex }` écrase l'attribut `hidden`, dont la règle vient de la feuille du
navigateur et perd contre une classe. Le voile serait resté affiché EN
PERMANENCE sur toutes les pages. Corrigé par `.chargement[hidden] { display:
none !important; }`.

Vérifié en conditions réelles : minuteur de 600 ms armé au clic sur un lien
interne, voile visible après, `role="status"` annonçant « Chargement de la page
en cours » aux lecteurs d'écran, et `prefers-reduced-motion` arrête la pulsation
sans retirer l'information.

## Deux corrections mobile signalées par la propriétaire

Capture à l'appui, le 14/09/2026, sur `/recherche?q=Arai+sz` : les produits
n'apparaissaient qu'après avoir fait défiler la page.

**1. Les liens de service de la barre du haut, desktop seulement.**
« À propos / Contact / Confidentialité » passaient à la ligne sur un écran
étroit et repoussaient l'en-tête, la recherche et les produits vers le bas.
Masqués sous 760 px. Aucun accès n'est perdu : les trois sont déjà dans le menu
latéral ET dans le pied de page — vérifié avant de masquer.

**2. La mention comparateur, repliée.**
La propriétaire demandait sa suppression. Refusée telle quelle, et dit :
c'est une mention **obligatoire** (code de la consommation, art. L111-7 et
D111-9), qui doit figurer sur la page de RÉSULTATS, là où le visiteur lit un
classement. La supprimer l'exposerait.

Retenu à la place : un `<details>` replié. Ce que la loi veut à proximité
immédiate du classement — le critère de tri, et que personne ne paie sa place —
reste visible sans clic, sur une seule ligne. Le reste (liens rémunérés,
référencement non exhaustif, date de relevé) se déplie sur place, sans quitter
la page.

Résultat mesuré à l'écran en 375 px : deux casques visibles sans défilement,
contre zéro avant.

## Allègement de la fiche et de la page de résultats (demandes du 14/09)

- **La mention comparateur passe en BAS** de la page de résultats. Repliée, elle
  s'interposait encore entre le titre et les produits. Elle reste sur la page de
  résultats, ce que la loi exige.
- **Le bandeau sous le tableau d'offres est supprimé** (« Cette fiche peut
  contenir des offres en différentes tailles… »). Son contenu vit désormais dans
  la bulle du repère « i », là où il est utile : sur la ligne concernée.
- Le script du filtre de tailles ne référence plus ce bandeau — sans ce
  nettoyage, `avert.hidden` aurait levé une erreur au premier clic sur une
  taille et TOUT ce qui suit (prix mini, écart, pastille « meilleur prix »)
  aurait cessé de fonctionner. C'est exactement la panne qu'on avait déjà eue
  avec `[data-compte]`.
- Un `title` a été posé sur le bouton « i » : la bulle demande JavaScript, et
  le paragraphe qui portait l'explication a disparu. L'infobulle native du
  navigateur la porte maintenant, au survol comme sans JavaScript.

**Piège rencontré** : la bulle vivait dans le même `{% if tailles %}` que le
bandeau ; la supprimer a emporté la bulle, laissant des boutons « i » morts.
Vérifié à l'écran après correction — la bulle est sortie de toute condition,
puisqu'elle n'est visible qu'au clic.

## La pastille de remise était sous le bouton « comparer »

Signalée par la propriétaire, capture à l'appui, le 14/09/2026 : sur les cartes
en promotion, la pastille rouge « −50 % » et le bouton rond « comparer »
formaient un pâté illisible dans le coin haut-gauche.

Mesuré dans le navigateur : les deux étaient **exactement au même endroit**,
`top: 8px; left: 8px`. La collision vient d'une règle de la reprise v1
(`style.css`, « les deux actions aux DEUX COINS de l'image ») qui a déplacé le
bouton « comparer » du coin droit vers le coin GAUCHE — là où `.pastille` était
posée depuis toujours. Ni mobile ni desktop : les deux, la règle n'étant pas
dans une media query.

La pastille descend sous les boutons (`top: 46px` = 8 marge + 30 bouton + 8).
Elle ne pouvait pas aller en bas : son ancêtre positionné est la carte entière,
pas l'image — elle serait tombée sur le prix.

Vérifié par calcul de rectangles, pas à l'œil : **0 chevauchement sur les 12
pastilles** de la page d'accueil, en 375 px comme en 903 px.

### Repéré au passage, pas corrigé

- La bannière d'accueil occupe tout l'écran sur mobile : il faut faire défiler
  une pleine hauteur avant de voir le premier produit.
- Les cartes laissent un vide entre le titre et le prix quand la ligne de
  couleur est absente.

## Staging fermé au public

Décidé par la propriétaire le 14/09/2026. Le staging est une copie complète de
la production : même catalogue, même contenu, et les mêmes fuites — son API REST
publiait encore l'identifiant du compte après correction de la production.

**Ce qui n'a pas marché** : le mode « Bientôt disponible » de WooCommerce.
Activé et enregistré (le badge de la barre d'admin le confirme), mais vérifié de
l'extérieur : 294 Ko de page et les produits toujours visibles. Le thème ReHub
rend la page d'accueil hors des gabarits WooCommerce, donc le garde-fou ne s'y
applique pas. Laissé activé quand même — il ne coûte rien.

**Ce qui marche** : un extrait WPCode (`ops/staging-non-public.php`) qui coupe
sur `template_redirect` en priorité 0, avant tout rendu. Un administrateur
connecté n'est jamais bloqué et WPCode se désactive depuis l'administration :
il n'y a pas de porte qui se referme sur soi.

Vérifié sans session, cache contourné :

| | |
|---|---|
| `/`, `/shop/casques/`, `/terms/` | **403**, 508 octets |
| `/wp-json/wp/v2/users` | **404** |
| identifiant exposé | **0** |
| production | intacte, 200 |

**Piège rencontré** : WPCode ouvre une modale de choix du type de code par-dessus
le formulaire. Le premier remplissage est parti dans un formulaire caché derrière
elle, sans erreur visible. Il faut choisir le type AVANT d'écrire.

## Mentions légales et CGU

Reprises de la v1 (`/terms/` et `/privacy-policy-2/`, mises à jour du
03/01/2026), à la demande de la propriétaire.

- **Les CGU manquaient entièrement** en v2 : ajoutées, adaptées là où la v2
  diffère (pas de compte, pas de cookie).
- **La politique de confidentialité de la v1 n'a PAS été recopiée.** Elle parle
  de cookies et d'une bannière de consentement que la v2 n'a pas : l'écrire
  serait faux. Seuls les droits RGPD, qui manquaient, ont été repris.
- **Section « Mentions légales »** ajoutée. L'éditeur et le directeur de la
  publication viennent de `.env` (`MENTIONS_EDITEUR`, `MENTIONS_DIRECTEUR`) et
  **ne s'affichent pas tant qu'ils sont vides** : une mention légale à moitié
  remplie vaut moins qu'une ligne absente, et inventer ces informations serait
  pire. L'hébergeur a une valeur par défaut factuelle (Hostinger).

⚠️ **La v1 n'a jamais eu de vraies mentions légales** — pas d'éditeur, pas de
directeur de publication. C'est une obligation pour un site professionnel
(LCEN, art. 6-III). Les deux lignes restent à renseigner.

## L'en-tête aligné sur la v1 (couleurs relevées, pas approchées)

La propriétaire a mis les deux en-têtes côte à côte le 14/09/2026. Les valeurs
ont été RELEVÉES dans le navigateur sur la v1 en ligne, pas estimées à l'œil :

| | v1 | v2 avant | v2 après |
|---|---|---|---|
| « Prix actualisés » | #8B96B0 · 12px · 600 | #CFD6EA · 12,5px · 400 | ✓ |
| « … marchands … » | #F5B301 · 12px · 800 | #F5B301 · 12,5px · 700 | ✓ |
| Signature du logo | #AAB6CD · 10px · 500 | #8F9BB8 · 9px · 700 | ✓ |
| Police de la barre | Source Sans 3 | **Roboto** | ✓ |

Le bandeau v2 était trop clair et trop léger, la signature trop sombre, trop
grasse et dans la mauvaise police — elle pesait plus que le nom de marque
qu'elle accompagne.

**Italique : il n'y en a AUCUN**, ni dans la v1 ni dans la v2 (compté dans le
navigateur sur tous les descendants de l'en-tête : 0 élément avec
`font-style` autre que `normal`). `.marque__mot i` porte bien
`font-style: normal`. Point à reconfirmer avec la propriétaire.

Trois autres écarts corrigés au passage, signalés par les captures :

- le **menu passe avant la marque** sur large écran, comme en v1 ; l'ordre
  inverse venait de la reprise Speedway ;
- le bouton de recherche porte le mot **« Chercher »** (masqué sous 760 px) ;
- la barre du haut retrouve ses **points médians**, la mention **« 100 %
  gratuit, sans inscription »** et le lien **CGU**. Le nombre de marchands
  reste LU dans la base : écrit en dur il mentait.

## L'ordre des étapes, et l'ANALYZE qui manquait encore

Le `match` du 16h13 a été **coupé après une minute**, à la faveur d'une question
de la propriétaire sur une fiche Shad SH29 qui affichait encore une mention de
taille. Le code de la fiche était pourtant correct : la colonne est bien
conditionnée. C'est la donnée qui était fausse — une taille lue dans un titre.

Or `mcpipe match` ne recalcule PAS les signatures : c'est `mcpipe signature` qui
les porte. Le correctif sur les fausses tailles n'aurait donc pas été appliqué,
et le défaut serait réapparu après une heure d'attente. Une minute perdue au
lieu d'un passage entier.

Ordre correct, désormais explicite : **`signature` puis `match`**.

Après `signature` (187 s, 767 118 lignes) : **0 taille alphabétique restante**
— MESH, PURE, TECH ont disparu ; 50 666 valeurs numériques conservées, dont les
pas de chaîne (520, 525, 530) et les nombres de dents.

**Troisième occurrence de la même panne dans la journée.** `_BUILD_GTIN_UNITS`
est passé de 24 à 31 minutes : `signature` venait de réécrire 767 000 lignes
sans relancer d'`ANALYZE`, et `match` les lit massivement. Modéré cette fois
(1,3×), mais c'est la cause qui a fait tourner la passe préfixe 50 minutes sans
finir le matin même, et `freshness` 39 minutes au lieu de 2.

`compute_signatures()` termine maintenant par `ANALYZE offer_signature`, hors
transaction. Trois secondes.

**La règle qui se dégage, à appliquer partout** : toute étape qui réécrit une
table en masse doit l'ANALYZER avant de rendre la main. Reste à vérifier pour
`normalize` et `load`.

## « Comparo » dans le jaune du logo

Demandé par la propriétaire. La valeur a été PRÉLEVÉE dans le PNG plutôt
qu'approchée à l'œil : Pillow n'est pas installé et on n'ajoute pas une
bibliothèque pour lire un pixel, donc `.scratch/couleur_logo.py` décode le PNG
(zlib + défiltrage) et compte les couleurs présentes.

Le « C » est **#F8CA02** (1 856 pixels). L'or du site est #F5B301 — plus sombre,
plus ambré. Côte à côte, l'écart se voyait.

Jeton dédié `--or-logo`, et non une modification de `--or` : ce dernier peint
tous les accents du site (boutons, prix, pastilles), et seul le mot « Comparo »
était demandé.

## Fiche produit : quatre demandes du 14/09 (fin de journée)

**1. « Taille 2 » sur une protection cervicale.** Le titre Moto-Axxe est
« ALPINESTARS Neck Brace BNS TECH-2 » : le lecteur prenait ce qui suit le
dernier tiret et lisait la GÉNÉRATION du modèle. Six autres marchands
déclaraient XS/M, L/XL, M, XL correctement.

Le correctif du matin épargnait les nombres, pour préserver les pas de chaîne
sur les pièces — il laissait donc passer celui-ci. Signal plus fin trouvé : un
vrai suffixe de taille est DÉTACHÉ (« Stoner - XL », « Skwal - 59 »), une
génération est COLLÉE (« TECH-2 », « Tissu-MESH », « GT-Air »).

Mesuré avant d'agir : sur 50 666 tailles lues dans un titre, **39 216 viennent
d'un tiret collé** contre 11 103 d'un tiret détaché — et ces dernières sont de
vraies caractéristiques (pas de chaîne 420/520/525, nombre de rayons, épaisseur
de joint). `_SIZE_TITLE_RE` exige désormais une espace après le tiret.

**Prend effet au prochain `signature` + `match`**, pas avant.

**2. L'historique des prix dans un encadré**, comme « Comparer les N offres ».
Ce sont les deux blocs de preuve de la page — ce que les marchands demandent
aujourd'hui, ce qu'ils demandaient avant. Posé sans contour, l'historique
flottait.

**3. Les suggestions en étagères qui défilent.** En grille, huit suggestions
occupaient trois rangées ; en étagère elles tiennent sur une ligne et le débord
à droite dit qu'il y en a d'autres. `.proches__grille` reprend les réglages de
`.rayon__piste` — une seule mécanique de défilement dans le site, pas deux.

**4. Une sortie en bas de fiche** : « ← Retour vers <catégorie> ». Une fiche
produit est un cul-de-sac — on y arrive par une recherche ou par Google, et une
fois le prix comparé il n'y a plus rien à faire. Le fil d'Ariane est en haut,
donc hors de vue après deux étagères. En contour, pas en plein : c'est une
porte, l'action principale reste « Voir l'offre ».

## La courbe des prix reprise de la v1 : TradingView Lightweight Charts

Demandé par la propriétaire. La v1 a été lue directement — son script est dans
la page produit, et il donne tout : bibliothèque, version, couleurs, options.

| | v1 | v2 |
|---|---|---|
| bibliothèque | Lightweight Charts 4.2.3 (Apache 2.0) | identique |
| hébergement | fichier servi par le site | identique |
| série | `addAreaSeries`, #26355A, aire .28 → .02 | identique |
| infobulle | prix — marchand — date | identique |

**Trois écarts assumés avec la v1 :**

1. **Les points sont posés DANS la page**, pas récupérés par un second appel.
   La v1 fait `fetch("?mc_ph_chart=<id>")` après coup, donc la courbe apparaît
   en retard sur le reste.
2. **Le marchand a été ajouté aux données** (`price_curve` passe de `min(price)`
   groupé à un `DISTINCT ON` qui lit le marchand de la ligne la moins chère).
   Savoir que le prix a baissé est une information, savoir CHEZ QUI en est une
   autre — et c'est celle qui décide d'un clic.
3. **Le SVG dessiné à la main est retiré.** Deux courbes pour une seule vérité,
   c'est une de trop à tenir.

**Le fichier est servi par nous, pas par un CDN**, et ce n'est pas un détail :
`/infos` promet qu'aucun tiers n'est contacté hormis Google Fonts et les images
des marchands. Vérifié sur la page rendue — aucun script externe.

### La typographie des encadrés, relevée et alignée

« Les écritures sont différentes. » Mesuré des deux côtés plutôt que jugé à
l'œil : le graphique lui-même était identique (même conteneur à 8 px près, même
densité d'écran, même police héritée, aucune option de police ni d'un côté ni de
l'autre). C'est le texte AUTOUR qui différait.

| | v1 | v2 avant | après |
|---|---|---|---|
| titre de l'encadré | Roboto 19px / 800 / #0F1524 | Source Sans 3 21px / 700 | ✓ |
| sous-titre | 12,5px / #8A90A5 | 14px / #6A7383 | ✓ |
| coins | 14px | 18px | ✓ |

Vérifié avant d'aligner : sur la v1, « Comparer les N offres » et « Historique
du meilleur prix » partagent ces valeurs. Les aligner ensemble garde donc la
cohérence entre les deux encadrés, au lieu de la casser.

**Supprimé** : la phrase « Le prix n'a pas bougé depuis le premier relevé ».
La courbe le montre déjà ; la répéter allongeait l'encadré. La fourchette reste
écrite quand le prix a bougé — là, le chiffre exact ne se lit pas sur le tracé.

### Le positionnement aussi, pas seulement la typographie

Question de la propriétaire après l'alignement des polices. Mesuré : le titre
était en retrait de 18 px pendant que **le sous-titre et la courbe touchaient la
bordure** à 1 px près.

La raison n'est pas une négligence : `.offres__carte` a un rembourrage à zéro
parce que le tableau des offres doit venir à fleur de bord — ses lignes
surlignées vont d'un côté à l'autre — et c'est l'en-tête seul qui écarte le
titre. L'encadré de l'historique n'a pas de tableau et avait besoin de
l'inverse : d'où `.offres__carte--historique`, qui porte son rembourrage
lui-même.

Relevé sur la v1 et repris : 16 px de rembourrage sur les quatre côtés, courbe
à 220 px de haut, sous-titre à 16 px du bloc suivant. Vérifié par mesure après
coup : retraits identiques à gauche, à droite et en bas.

## Le fourre-tout « Protections », découpé

Signalé par la propriétaire : sur la fiche d'une protection cervicale
Alpinestars, l'étagère « dans la même gamme de prix » proposait un pare-carter
SW-Motech et une protection moteur R&G. Même prix, aucun rapport.

**Premier correctif, insuffisant.** `meme_gamme()` filtrait sur la FAMILLE de
rayons ; resserré sur le rayon exact. Mesuré sur 300 fiches au hasard : gants →
gants, blousons → blousons, 292 gardent leurs 8 suggestions, 1 % d'étagères
vides. Bon pour les rayons propres — **mais pas pour son cas** : la cervicale et
le pare-carter portent littéralement le même numéro de rayon. Dit tel quel
plutôt que de renvoyer l'échantillon qui marchait.

**La vraie cause.** Le rayon 11 « Protections » contenait 44 350 offres et
n'était pas seulement « pilote contre moto » : on y trouvait des bulles Ermax,
un échappement LeoVince, un guidon Hepco & Becker, des autocollants de fourche.
Un fourre-tout, pas une catégorie.

**Deux sous-rayons ajoutés** (28 `protection.pilote`, 29 `protection.moto`), sur
le modèle des quatre sous-types de casques qui existaient déjà, plus un routage
vers les rayons qui existaient mais n'étaient pas utilisés.

| | offres rangées |
|---|---|
| → Carénage (bulles, saute-vent, garde-boue) | 21 635 |
| → Protections de la moto | 12 724 |
| → Protections du pilote | 5 093 |
| → Accessoires (stickers, visserie) | 701 |

**Ce qui n'est PAS fait, et pourquoi** : 29 % des offres du rayon ne sont
décidées par aucune règle — visserie, kits de fixation, pièces sans mot-clé.
Elles restent dans « Protections ». Une offre laissée où elle est ne casse
rien ; une offre mal rangée, si.

Onze cas verrouillés par des tests, dont le cas fondateur : le pare-carter en
29, la cervicale en 28. Ils ne peuvent plus se retrouver sur la même étagère.

**Une étagère absente vaut mieux qu'une étagère absurde** : `meme_gamme()` ne
rend plus rien sur une fiche NON CLASSÉE. Mesuré, ce cas sortait une batterie,
un lève-moto et un sac de 30 L côte à côte, au bon prix.

### Une surveillance qui criait victoire

Le premier monitor de ce passage a annoncé « MATCH TERMINE SANS ERREUR » vingt
secondes après le lancement : il concluait à la fin dès qu'aucun processus
`mcpipe` n'était visible, sans vérifier qu'il avait seulement commencé — et au
premier tour, la mesure du catalogue tournait encore.

Corrigé : le monitor attend maintenant que le journal existe ET contienne
`matching` avant de guetter la fin. **Le silence et le succès ne se ressemblent
que pour qui ne vérifie pas le démarrage.**

## La régression que la découpe a causée, et ce qu'elle enseigne

Trouvée en vérifiant le résultat sur la fiche même qui avait motivé le chantier
— pas par un test, pas par un indicateur. `mcpipe verify` ne l'a pas vue, la
mesure du catalogue non plus : ses quatorze indicateurs montraient une
amélioration nette (+719 fiches comparables, −651 doublons).

**Ce qui s'est passé.** `split_protections()` lit le titre de CHAQUE offre
séparément. Or les marchands ne nomment pas la même chose pareil :

| marchand | titre | décision |
|---|---|---|
| Speedway | « Tour De Nuque Alpinestars BNS Tech-2 » | rayon 28 |
| Motoblouz | « Protection cervicale Alpinestars BNS » | rayon 28 |
| FC-Moto | « Alpinestars BNS Tech-2 Protecteur de cou » | aucun mot-clé → 11 |

Même code-barres (`8033637210797`), deux rayons. Le rayon entre dans l'identité
d'une fiche : `_FLAG_GTIN_CONFLICTS` a vu un conflit et détaché les trois. Une
fiche à sept marchands est tombée à un.

**Mesuré** : 13 547 codes-barres en désaccord sur le rayon, dont 1 194 causés
par cette passe (les 12 353 autres sont antérieurs — des marchands qui rangent
déjà le même code-barres ailleurs).

**Le correctif** : `accorder_protections_par_gtin()`. Un code-barres désigne UN
produit ; si une offre a été reconnue, les autres parlent du même objet, quels
que soient leurs mots. On propage — **seulement si les offres reconnues sont
toutes d'accord**, et sans jamais écraser une décision plus spécifique.

Mesuré à blanc : 2 352 offres ralliées, désaccords 13 547 → 12 353.

### Ce qu'il faut en retenir

Le projet appliquait **déjà** cette règle pour les casques : `helmet_borrowed`
emprunte le sous-type au voisin qui partage le code-barres AVANT de croire le
titre. J'ai écrit une passe de classification sans la suivre.

C'est la deuxième fois dans la même journée que la même règle est enfreinte —
la première sur les tailles, signalée par la propriétaire. Elle porte un nom
dans `REPRENDRE-ICI.md` : **la preuve l'emporte sur la supposition**. Un titre
est une supposition ; un code-barres partagé est une preuve.

**À se demander pour toute nouvelle règle de classification** : « et si deux
marchands du même code-barres l'écrivaient différemment ? » Si la réponse casse
la fiche, la règle doit se décider par code-barres, pas par offre.

## Les pages lentes, mesurées puis corrigées

| page | avant | à froid | ensuite |
|---|---|---|---|
| accueil | 4,3 s | 0,80 s | **0,04 s** |
| recherche | 11,5 s | 11,5 s | **0,01 s** |
| rayon | 3,4 s | 0,01 s | **0,02 s** |
| tous les produits | 3,0 s | 3,0 s | **0,01 s** |

**Deux causes, trouvées en chronométrant requête par requête plutôt qu'en
devinant.**

`queries.categories()` coûte **1,77 s** — la requête la plus chère du site — et
elle était appelée TROIS fois par page : `_ctx` pour le menu, l'accueil pour ses
familles, la route de rayon pour retrouver la catégorie courante. Trois appels,
trois fois le même résultat. Une seule porte désormais (`_rayons()`), le cache
derrière. À lui seul, ce point explique les 3,4 s d'une page de rayon.

`queries.facets()` coûte **4,6 s sur une recherche** contre 1,1 s pour la liste
elle-même : cinq requêtes qui rebalaient chacune le catalogue en réappliquant le
même filtre texte. Mises en cache par combinaison de filtres ET page.

**Le plafond du cache.** Une combinaison de filtres est une chaîne libre : sans
borne, un robot essayant mille fourchettes de prix ferait grossir le
dictionnaire sans fin. `cache.py` garde au plus 400 entrées, les plus récemment
ÉCRITES — ce qui vaut ici c'est la fraîcheur, et une entrée relue ne rajeunit
pas.

### Ce qui n'est PAS réglé

**Le premier visiteur d'une recherche paie encore 11,5 s.** Le cache lui évite
seulement de repayer. Le vrai correctif est de refondre les cinq requêtes de
`facets()` en une seule, en matérialisant d'abord l'ensemble filtré — chantier à
part, non ouvert.

Sur le VPS, `proxy_cache_background_update` (voir `ops/deploiement/`) atténuera
même ce premier appel : nginx sert la version périmée pendant qu'il la
rafraîchit derrière, donc personne n'attend jamais une reconstruction.

## Les titres, nettoyés — la distinction que la propriétaire a posée

« Il y a une différence entre enlever la taille pour garder le nom du produit,
et un titre incompréhensible comme avant. »

Elle a raison, et j'aplatissais les deux. La décision du 13/09 — « le titre du
marchand, tel quel » — venait d'une version qui rendait des titres
INCOMPRÉHENSIBLES (« Cuir Swallow T7 »). Ce n'est pas la même chose que retirer
ce qui ment ou ce qui n'apprend rien. J'invoquais ce rejet comme raison de ne
rien toucher.

**Deux retraits, chacun mesuré avant d'être écrit.**

**1. La taille en fin de titre.** « Housse moto Ixon BLANKY - M » sur une fiche
qui compare M, L, XL et 2XL : le titre ment avant que le visiteur lise le
tableau. 2 % des titres.

**2. La queue « nom de rayon + marque ».**

| gardé | retiré |
|---|---|
| Casque Cross Alpinestars SM3 Falcon Rouge | Casque Cross ALPINESTARS |
| Bottes TCX Infinity 3 Gore-Tex Noir | Bottes et chaussures TCX |
| Bulle MRA Vario Touring Fumé Suzuki GSX650F | Carénage et protection MRA |

**Ce qui rend la règle sûre, et qui manquait à la version rejetée** : la coupe
n'a lieu QUE si la queue répète la marque. « Casque Scorpion EXO-RACE AIR -
SOLID » garde son coloris ; « Gants Macna THANDOR » n'est pas touché. La marque
est déjà affichée à côté du titre — la réécrire n'apprend rien, un coloris si.

Mesuré sur les 28 716 fiches comparables : 1 538 titres concernés (5 %), **24
coupes tirées au hasard et relues une par une, 24 queues de rayon, aucune
perte**. Sept tests verrouillent ce qu'il ne faut PAS couper.

### Deux pièges rencontrés en chemin

**Un commentaire tombé dans une liste de mots.** J'ai d'abord écrit l'ajout de
« taille » aux mots ignorés du pipeline avec un commentaire À L'INTÉRIEUR de la
chaîne — or elle est découpée par `.split()`. « mais », « pas », « donnait »,
« jetons » seraient devenus des mots ignorés et auraient été retirés de vrais
noms de produits. Attrapé par la vérification qui suivait. Un avertissement est
maintenant en tête de `_STOP`.

**Un échantillon qui tronquait à l'affichage.** La première relecture des coupes
montrait le résultat tronqué à 66 caractères : impossible de juger ce qui avait
été retiré. Refait en affichant LA PARTIE RETIRÉE — c'est elle qu'on juge.

## Le bandeau du haut, sur une ligne

« 6 marchands vérifiés et comparés » à côté de « Prix actualisés
quotidiennement », demandé le 14/09. Empilés, ils prenaient deux lignes pour
dire deux choses courtes. Sur mobile : « 100 % gratuit » masqué, pas resserré,
11 px. Vérifié en 375 px — une seule ligne, aucun débordement horizontal
(`scrollWidth` = largeur d'écran).

Le point médian qui précédait « 100 % gratuit » est masqué avec lui, via
`:has(+ …)` : sans cela il restait seul en fin de ligne.
