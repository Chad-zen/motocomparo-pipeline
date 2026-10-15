# Calendrier éditorial — 19 octobre au 11 décembre 2026

Seize articles, deux par semaine : **le mardi** un article de fond, **le
vendredi** un format plus court ou d'actualité. Les formats (A à E), les
règles d'honnêteté, les blocs de données et le style d'image sont définis
dans `docs/blog/charte-editoriale.md`.

Saison : automne et début d'hiver (pluie, froid, jours courts), Black Friday
le **vendredi 27 novembre 2026**, cadeaux de Noël à partir de fin novembre.

Avant d'écrire un article :
- vérifier en local que les blocs prévus renvoient des chiffres (un rayon
  peu renseigné sur une caractéristique donne un tableau vide : changer de
  caractéristique plutôt que publier un tableau creux) ;
- pour les duels, vérifier que les deux fiches ont toujours au moins quatre
  marchands ;
- pour les articles qui s'appuient sur l'historique des prix (n° 11 et 12),
  vérifier la profondeur de `price_history` en production : le bloc
  `prix_bas` ne doit pas promettre 90 jours s'il n'en existe que 30.

Chaque prompt d'illustration est prêt à coller dans Meta AI. Il contient
déjà le style commun. Format demandé : 16:9, exporté en WebP 1600 × 900,
nommé `<slug>.webp`.

---

## Vue d'ensemble

| Sem. | Date | Titre de travail | Format | Rayon |
|---|---|---|---|---|
| 1 | mar. 20/10 | Blouson moto hiver : membrane, doublure et classe EN 17092 | A | jacket |
| 1 | ven. 23/10 | Rouler sous la pluie : l'équipement imperméable, du casque aux bottes | D | plusieurs |
| 2 | mar. 27/10 | Pantalon moto homologué : classes A, AA, AAA et coques de genoux | B | pants |
| 2 | ven. 30/10 | Gants chauffants moto : ce qu'il faut savoir avant d'acheter | A | gloves |
| 3 | mar. 03/11 | Bottes moto hiver : la norme EN 13634 et l'imperméabilité | B | boots |
| 3 | ven. 06/11 | Buée sur la visière : Pinlock fourni, préparé ou absent | A | helmet |
| 4 | mar. 10/11 | Dorsale moto : intégrée, en option ou à acheter à part | B | jacket, protection.pilote |
| 4 | ven. 13/11 | LS2 OF600 ou Scorpion Exo-City II : deux jets urbains comparés | C | helmet.jet |
| 5 | mar. 17/11 | Casque ECE 22.05 : peut-on encore l'acheter et le porter ? | B | helmet |
| 5 | ven. 20/11 | Taille de blouson et de pantalon moto : mesurer avant de commander | A | jacket, pants |
| 6 | mar. 24/11 | Black Friday moto : reconnaître une vraie baisse de prix | E | tous |
| 6 | ven. 27/11 | Casque intégral à petit prix : ce que le prix change, et ce qu'il ne change pas | E | helmet.integral |
| 7 | mar. 01/12 | Offrir un équipement moto : taille, homologation et échange | A | plusieurs |
| 7 | ven. 04/12 | Intercom moto : casque « préparé » ou « fourni », ce que ça veut dire | A | helmet, electronics |
| 8 | mar. 08/12 | Bagagerie moto : sacoche de réservoir, de selle ou top case | A | luggage |
| 8 | ven. 11/12 | Idées de cadeaux moto par budget, prix du jour à l'appui | E | plusieurs |

---

## Semaine 1

### 1. Blouson moto hiver : membrane, doublure et classe EN 17092
- **Date** : mardi 20 octobre 2026 — slug `blouson-moto-hiver-comment-choisir`
- **Format** : A, guide de choix
- **Requête visée** : « blouson moto hiver », « blouson moto hiver imperméable », « blouson moto homologué AA »
- **Pourquoi un comparateur répond mieux** : les guides de Dafy et Motoblouz
  listent des critères sans chiffres. Nous pouvons dire combien de blousons
  comparables déclarent une membrane, une doublure amovible ou une classe
  AA, et à quel prix médian, aujourd'hui.
- **Données vivantes** : `repartition('jacket', 'classe_protection')`,
  `repartition('jacket', 'doublure_thermique')`,
  `repartition('jacket', 'membrane')` (au plus trois blocs).
- **Liens internes** : `/c/jacket?saison=hiver`, `/c/jacket?homologation=classe-aa`,
  `/guides#guide-normes`, futur article dorsale (n° 7), article pluie (n° 2).
- **Points à sourcer** : EN 17092 (classes AAA, AA, A, B, C) ; distinction
  membrane / déperlant ; compatibilité airbag seulement si la fiche le déclare.
- **Prompt Meta AI** :
  > A motorcyclist seen from behind, standing next to a parked motorcycle on a quiet country road in late autumn, wearing a plain dark textile riding jacket with the collar closed, cold morning mist over the fields, bare trees, wet asphalt. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

### 2. Rouler sous la pluie : l'équipement imperméable, du casque aux bottes
- **Date** : vendredi 23 octobre 2026 — slug `equipement-moto-pluie`
- **Format** : D, dossier de saison
- **Requête visée** : « équipement moto pluie », « rouler à moto sous la pluie équipement », « tenue de pluie moto »
- **Pourquoi un comparateur répond mieux** : une seule page qui couvre les
  cinq pièces, avec pour chacune le nombre de modèles comparables qui
  déclarent une membrane ou l'imperméabilité, et le lien vers le rayon filtré.
- **Données vivantes** : `repartition('gloves', 'saison')` ou
  `repartition('boots', 'membrane')`, `repartition('helmet', 'pinlock')`.
  Une phrase par rayon peut citer le total via un bloc, jamais à la main.
- **Liens internes** : `/c/jacket`, `/c/pants`, `/c/gloves?saison=hiver`,
  `/c/boots`, `/guides/gants-ete-ou-hiver`, article buée (n° 6).
- **Points à sourcer** : conseils de conduite sous la pluie → renvoi vers la
  Sécurité routière (securite-routiere.gouv.fr), pas de conseil de pilotage
  rédigé par nous.
- **Prompt Meta AI** :
  > A motorcycle parked under a small shelter during heavy autumn rain, rain streaks visible against a dim grey sky, puddles reflecting a warm street lamp, a plain matte helmet resting on the seat with water droplets on it. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

## Semaine 2

### 3. Pantalon moto homologué : classes A, AA, AAA et coques de genoux
- **Date** : mardi 27 octobre 2026 — slug `pantalon-moto-homologue-classes`
- **Format** : B, la norme expliquée
- **Requête visée** : « pantalon moto homologué », « pantalon moto classe AA », « jean moto homologué »
- **Pourquoi un comparateur répond mieux** : les marchands mélangent
  « homologué », « CE », « avec protections ». Nous montrons ce que déclarent
  réellement les fiches, par classe et par niveau de coque (EN 1621-1 niveau
  1 ou 2), avec le prix médian de chaque groupe.
- **Données vivantes** : `repartition('pants', 'homologation')` (libellé à
  remplacer par « Classe EN 17092 »), `repartition('pants', 'niveau_genoux')`.
- **Liens internes** : `/c/pants?homologation=classe-aa`, `/c/pants`,
  `/guides#guide-normes`, article blouson hiver (n° 1).
- **Points à sourcer** : EN 17092-2 à -6 (classes), EN 1621-1 (coques).
  Le jean « moto » : classe A ou AA seulement si l'étiquette le dit.
- **Prompt Meta AI** :
  > Close-up of a rider's knee and lower leg in plain dark textile riding trousers, crouching beside a motorcycle wheel in a workshop, a removable knee armour pad lying on the concrete floor next to a folded measuring tape. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

### 4. Gants chauffants moto : ce qu'il faut savoir avant d'acheter
- **Date** : vendredi 30 octobre 2026 — slug `gants-chauffants-moto`
- **Format** : A, guide de choix
- **Requête visée** : « gants chauffants moto », « gants chauffants moto batterie ou 12V », « gants chauffants homologués »
- **Pourquoi un comparateur répond mieux** : les comparatifs existants
  « testent » sans protocole. Nous comptons les gants chauffants comparables,
  leur prix médian face aux gants d'hiver non chauffants, et rappelons qu'ils
  doivent eux aussi être homologués EN 13594.
- **Données vivantes** : `repartition('gloves', 'chauffant')`,
  `repartition('gloves', 'saison')` (pour comparer le prix médian « hiver »).
- **Liens internes** : `/c/gloves?saison=hiver`, `/guides/gants-ete-ou-hiver`,
  `/c/electronics`.
- **Points à sourcer** : obligation des gants homologués (R431-1-2) ;
  alimentation batterie ou 12 V d'après les fiches et notices ; aucune
  promesse d'autonomie qui ne vienne pas du fabricant.
- **Prompt Meta AI** :
  > Two hands in plain black winter riding gloves holding a steaming metal cup at a roadside stop on a frosty morning, a motorcycle handlebar softly blurred in the background, low winter sun. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

## Semaine 3

### 5. Bottes moto hiver : la norme EN 13634 et l'imperméabilité
- **Date** : mardi 3 novembre 2026 — slug `bottes-moto-hiver-norme-en-13634`
- **Format** : B, la norme expliquée
- **Requête visée** : « bottes moto hiver », « bottes moto imperméables », « norme EN 13634 »
- **Pourquoi un comparateur répond mieux** : l'étiquette EN 13634 porte
  quatre chiffres (hauteur, abrasion, coupure, rigidité transversale) que
  personne n'explique simplement. Nous les expliquons et montrons combien de
  fiches citent la norme, une membrane, et à quel prix.
- **Données vivantes** : `repartition('boots', 'homologation')`,
  `repartition('boots', 'membrane')`.
- **Liens internes** : `/c/boots`, article pluie (n° 2), `/guides#guide-normes`.
- **Points à sourcer** : EN 13634:2017 (signification des quatre chiffres,
  niveaux 1 et 2).
- **Prompt Meta AI** :
  > Low-angle shot of a pair of plain black leather riding boots standing in a shallow puddle on a cobbled street at dusk, fallen leaves around them, water droplets beading on the leather, a motorcycle footpeg just visible at the edge of the frame. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

### 6. Buée sur la visière : Pinlock fourni, préparé ou absent
- **Date** : vendredi 6 novembre 2026 — slug `buee-visiere-casque-pinlock`
- **Format** : A, guide de choix (court)
- **Requête visée** : « buée visière casque moto », « pinlock c'est quoi », « casque avec pinlock fourni »
- **Pourquoi un comparateur répond mieux** : « préparé Pinlock » et
  « Pinlock fourni » ne coûtent pas la même chose. Nous comptons les casques
  de chaque cas et leur prix médian, pour que le lecteur sache s'il doit
  ajouter l'achat de l'insert.
- **Données vivantes** : `repartition('helmet', 'pinlock')`.
- **Liens internes** : `/c/helmet.integral`, `/c/helmet.modular`,
  `/guides/casque-jet-modulable-integral-norme`, article pluie (n° 2).
- **Points à sourcer** : principe de l'écran double (site du fabricant de
  l'insert, sans en faire la promotion) ; aucun produit anti-buée recommandé.
- **Prompt Meta AI** :
  > Extreme close-up of a clear helmet visor partly fogged by condensation on a cold morning, droplets of mist on the outside, a blurred wet road and soft headlights behind it, the helmet itself plain matte grey. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

## Semaine 4

### 7. Dorsale moto : intégrée, en option ou à acheter à part
- **Date** : mardi 10 novembre 2026 — slug `dorsale-moto-integree-ou-separee`
- **Format** : B, la norme expliquée
- **Requête visée** : « dorsale moto », « dorsale moto niveau 2 », « blouson moto avec dorsale incluse »
- **Pourquoi un comparateur répond mieux** : un blouson « avec poche
  dorsale » n'a pas de dorsale. Nous montrons combien de blousons la
  fournissent, combien la prévoient seulement, et le prix d'une dorsale
  vendue seule — le vrai prix du blouson complet.
- **Données vivantes** : `repartition('jacket', 'dorsale')` (valeurs
  incluse / option-poche / option-prédisposée) ; tableau `nav` ou
  `repartition` sur `protection.pilote` pour le prix d'une dorsale seule.
- **Liens internes** : `/c/protection.pilote`, `/c/jacket`,
  `/guides#guide-normes`, article blouson hiver (n° 1).
- **Points à sourcer** : EN 1621-2 (niveaux 1 et 2), EN 1621-1 pour les
  coques de membres.
- **Prompt Meta AI** :
  > A plain dark motorcycle jacket laid open on a wooden workbench, inside lining visible, a separate plain grey back protector placed beside it, a pair of scissors and a tape measure nearby, soft window light from the side. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

### 8. LS2 OF600 ou Scorpion Exo-City II : deux jets urbains comparés
- **Date** : vendredi 13 novembre 2026 — slug `ls2-of600-vs-scorpion-exo-city-2`
- **Format** : C, duel
- **Fiches** (relevées le 16/10/2026, cinq marchands chacune) :
  `ls2-of600-bk-mat-17c0fb99`, `scorpion-2-city-exo-sheer-bk-br-mat-098c73e4`.
  Vérifier les noms commerciaux exacts sur les sites des fabricants avant
  rédaction ; changer de coloris si une fiche passe sous quatre marchands.
- **Requête visée** : « LS2 OF600 avis », « Scorpion Exo City 2 », « casque jet pas cher ville »
- **Pourquoi un comparateur répond mieux** : prix du jour chez cinq
  marchands, plus bas prix relevé, caractéristiques côte à côte ; aucun
  verdict inventé, la décision renvoyée à l'essai.
- **Données vivantes** : `comparaison([...])` + phrase de prix calculée
  (modèle : `ls2-ff818-vs-scorpion-exo-530.html`).
- **Liens internes** : `/p/<les deux slugs>`, `/m/ls2`, `/m/scorpion`,
  `/c/helmet.jet`, `/guides/casque-jet-modulable-integral-norme`.
- **Points à sourcer** : homologation (étiquette J ou P/J), poids annoncé
  par le fabricant s'il est publié.
- **Prompt Meta AI** :
  > A city street in the early evening after rain, a scooter-style motorcycle parked at the kerb with a plain matte open-face helmet hanging from the mirror, shop windows glowing softly, reflections on the wet pavement. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

## Semaine 5

### 9. Casque ECE 22.05 : peut-on encore l'acheter et le porter ?
- **Date** : mardi 17 novembre 2026 — slug `casque-ece-22-05-encore-autorise`
- **Format** : B, la norme expliquée
- **Requête visée** : « casque 22.05 encore autorisé », « casque 22.05 ou 22.06 », « fin de vente casque 22.05 »
- **Pourquoi un comparateur répond mieux** : des guides de vendeurs
  présentent encore la 22.05 comme norme en vigueur. Nous montrons combien
  de fiches comparables portent encore « 22.05 » dans leur description, et
  rappelons la règle de vente et d'usage.
- **Données vivantes** : `repartition('helmet', 'homologation')`.
- **Liens internes** : `/guides#guide-ece2206`, `/c/helmet`,
  `/guides/casque-jet-modulable-integral-norme`.
- **Points à sourcer** : règlement ONU n° 22, série 06 (dates d'application
  et de fin de vente des casques 22.05) ; distinction vente / usage.
- **Prompt Meta AI** :
  > An older plain white motorcycle helmet with visible scuffs resting on a shelf next to a newer plain matte grey helmet, in a quiet garage, warm late-afternoon light through a dusty window, a calendar-free bare wall behind. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

### 10. Taille de blouson et de pantalon moto : mesurer avant de commander
- **Date** : vendredi 20 novembre 2026 — slug `taille-blouson-pantalon-moto`
- **Format** : A, guide de choix
- **Requête visée** : « taille blouson moto », « guide des tailles équipement moto », « blouson moto taille grand ou petit »
- **Pourquoi un comparateur répond mieux** : avant Black Friday, une
  commande à la mauvaise taille coûte un retour. Nous expliquons les
  mesures (poitrine, tour de taille, entrejambe, bras) et le placement des
  coques, sans prétendre connaître la coupe de chaque marque — renvoi au
  guide de chaque fabricant.
- **Données vivantes** : pas de répartition utile ; à défaut, le tableau
  `nav` du rayon blousons (nombre de fiches par sous-rayon) ou aucun bloc.
  Si l'article n'a pas de donnée propre, il doit apporter une méthode de
  mesure claire et illustrée (schéma texte).
- **Liens internes** : `/guides#guide-taille-casque`,
  `/guides#guide-comparer-prix` (la taille avant le prix), `/c/jacket`,
  `/c/pants`.
- **Points à sourcer** : la position des coques sur l'articulation et leur
  réglage (notices des fabricants) ; guides des tailles des fabricants.
  Aucune correspondance de tailles entre marques écrite par nous.
- **Prompt Meta AI** :
  > A tailor's measuring tape draped over the shoulders of a plain dark motorcycle jacket hanging on a wooden hanger against a light plaster wall, a notebook and pencil on a small table below, soft daylight. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

## Semaine 6

### 11. Black Friday moto : reconnaître une vraie baisse de prix
- **Date** : mardi 24 novembre 2026 — slug `black-friday-equipement-moto-vraie-promo`
- **Format** : E, guide de prix
- **Requête visée** : « black friday équipement moto », « black friday casque moto », « promo moto vraie ou fausse »
- **Pourquoi un comparateur répond mieux** : c'est l'article que seul un
  comparateur peut écrire. Un prix barré compare à un prix conseillé ;
  nous comparons au plus bas prix relevé chez plusieurs marchands. Exemples
  calculés sur deux ou trois fiches très suivies.
- **Données vivantes** : `prix_bas('<slug>', 90)` sur trois fiches à fort
  nombre de marchands (choisies la veille), phrase calculée « le prix du jour
  est / n'est pas sous le plus bas relevé ».
- **Liens internes** : `/bons-plans`, alertes de prix (`/alertes/demande`
  depuis une fiche), `/guides#guide-comparer-prix`.
- **Points à sourcer** : règle française d'annonce de réduction (prix de
  référence = prix le plus bas des 30 derniers jours, article L112-1-1 du
  Code de la consommation) — à vérifier sur Légifrance avant de l'écrire.
- **Prompt Meta AI** :
  > A dimly lit motorcycle gear shop interior after closing time, rows of plain unbranded jackets on rails and plain helmets on shelves, a single warm lamp over an empty counter with a paper receipt roll, quiet evening atmosphere. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

### 12. Casque intégral à petit prix : ce que le prix change, et ce qu'il ne change pas
- **Date** : vendredi 27 novembre 2026 (Black Friday) — slug `casque-integral-pas-cher-ce-que-le-prix-change`
- **Format** : E, guide de prix
- **Requête visée** : « casque intégral pas cher », « casque moto pas cher homologué », « casque intégral moins de 150 euros »
- **Pourquoi un comparateur répond mieux** : la matière de la calotte, la
  note SHARP et le poids déclaré se croisent avec le prix médian de chaque
  groupe ; le lecteur voit ce qu'il paie en plus (carbone, fibre) et ce qui
  ne bouge pas (la norme). Que Choisir rappelle, étude à l'appui, que le
  prix ne dit pas le niveau de protection : on le cite.
- **Données vivantes** : `repartition('helmet.integral', 'calotte')`,
  `repartition('helmet.integral', 'note_securite')`.
- **Liens internes** : `/c/helmet.integral?prix_max=150`,
  `/guides/ls2-ff818-vs-scorpion-exo-530`, article Black Friday (n° 11).
- **Points à sourcer** : étude citée par Que Choisir (Mutuelle des Motards,
  Fondation Maif, Université de Strasbourg) ; SHARP.
- **Prompt Meta AI** :
  > Three plain matte full-face motorcycle helmets in different neutral colours lined up on a long wooden shelf, each a slightly different shape, soft side light, a price-tag-free minimalist display, workshop atmosphere. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

## Semaine 7

### 13. Offrir un équipement moto : taille, homologation et échange
- **Date** : mardi 1er décembre 2026 — slug `offrir-equipement-moto-cadeau`
- **Format** : A, guide de choix
- **Requête visée** : « offrir un casque moto », « cadeau motard équipement », « offrir gants moto taille »
- **Pourquoi un comparateur répond mieux** : la question n'est pas « quoi »
  mais « comment ne pas se tromper » : ce qu'on peut offrir sans connaître
  la taille (bagagerie, entretien, électronique), ce qu'il vaut mieux faire
  essayer (casque), et l'écart de prix entre marchands sur le même produit.
- **Données vivantes** : tableau `nav` (nombre de fiches et premier prix
  par rayon : luggage, maintenance, electronics, gloves).
- **Liens internes** : `/c/luggage`, `/c/maintenance`, `/c/electronics`,
  `/guides#guide-taille-casque`, article tailles (n° 10).
- **Points à sourcer** : droit de rétractation de 14 jours pour un achat en
  ligne (Code de la consommation, art. L221-18) ; les délais propres à
  chaque marchand ne sont pas recopiés (ils changent).
- **Prompt Meta AI** :
  > A wrapped gift box in plain brown kraft paper with a simple string bow placed on the seat of a parked motorcycle in a garage decorated with a single string of warm fairy lights, winter evening, cosy atmosphere. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

### 14. Intercom moto : casque « préparé » ou « fourni », ce que ça veut dire
- **Date** : vendredi 4 décembre 2026 — slug `intercom-moto-casque-prepare-ou-fourni`
- **Format** : A, guide de choix (court)
- **Requête visée** : « intercom moto », « casque moto compatible intercom », « casque préparé intercom »
- **Pourquoi un comparateur répond mieux** : « préparé » signifie un
  emplacement, pas un appareil. Nous comptons les casques de chaque cas,
  leur prix médian, et renvoyons vers le rayon électronique pour le prix
  d'un intercom seul.
- **Données vivantes** : `repartition('helmet', 'intercom')` ; tableau `nav`
  pour `electronics`.
- **Liens internes** : `/c/electronics`, `/c/helmet.modular`,
  `/guides/casque-jet-modulable-integral-norme`, article cadeaux (n° 13).
- **Points à sourcer** : règle sur les écouteurs au volant (article R412-6-1
  du Code de la route, exception des systèmes intégrés au casque) — à
  vérifier sur Légifrance.
- **Prompt Meta AI** :
  > Two motorcyclists seen from behind riding side by side on a winding country road at golden hour in late autumn, plain matte helmets, a small plain communication unit on the side of one helmet, hills and hedgerows in soft haze. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

## Semaine 8

### 15. Bagagerie moto : sacoche de réservoir, de selle ou top case
- **Date** : mardi 8 décembre 2026 — slug `bagagerie-moto-comment-choisir`
- **Format** : A, guide de choix
- **Requête visée** : « sacoche moto », « sacoche réservoir ou top case », « bagagerie moto étanche »
- **Pourquoi un comparateur répond mieux** : le rayon bagagerie est l'un
  des plus fournis du catalogue ; nous donnons le nombre de modèles et le
  premier prix par type, et les critères de compatibilité (fixation,
  support) qu'aucune fiche ne résume.
- **Données vivantes** : tableau `nav` du rayon `luggage` ; une
  `repartition('luggage', ...)` seulement si une caractéristique est
  suffisamment renseignée (à vérifier : aucune ne l'est le 16/10/2026).
- **Liens internes** : `/c/luggage`, article cadeaux (n° 13 et 16).
- **Points à sourcer** : compatibilité de fixation → notice du fabricant.
- **Prompt Meta AI** :
  > A touring motorcycle parked at a mountain pass viewpoint in early winter, plain dark soft saddlebags and a plain tank bag fitted, a thermos and folded map on the seat, distant snowy peaks, crisp clear air. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

### 16. Idées de cadeaux moto par budget, prix du jour à l'appui
- **Date** : vendredi 11 décembre 2026 — slug `idees-cadeaux-moto-par-budget`
- **Format** : E, guide de prix
- **Requête visée** : « cadeau motard », « idée cadeau moto moins de 50 euros », « cadeau moto noël »
- **Pourquoi un comparateur répond mieux** : les listes de cadeaux des
  marchands ne montrent que leurs produits. Nous classons par budget à
  partir des premiers prix du jour par rayon, avec des liens vers les rayons
  filtrés par prix (`prix_max`). Aucune « sélection coup de cœur » : les
  critères sont affichés (budget, sans taille à connaître, vendu par
  plusieurs marchands).
- **Données vivantes** : tableau `nav` ; liens `/c/<rayon>?prix_max=50`,
  `?prix_max=100` ; éventuellement `comparaison` de deux produits sans taille
  (ex. une sacoche) choisis la veille.
- **Liens internes** : article « Offrir un équipement » (n° 13),
  `/bons-plans`, `/c/luggage`, `/c/maintenance`, `/c/electronics`.
- **Points à sourcer** : délais de livraison avant Noël → ne pas les
  recopier ; renvoyer à la page de chaque marchand.
- **Prompt Meta AI** :
  > Flat lay on a dark wooden table of small unbranded motorcycle-related gifts: a plain neck warmer, a small tool roll, a pair of plain gloves, a folded paper map and a thermos, scattered pine sprigs and a few warm fairy lights, viewed from above. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

---

## Illustrations des trois articles déjà publiés

### `ls2-ff818-vs-scorpion-exo-530.webp`
> A tailor's measuring tape wrapped around the head of a person seen from behind, short hair, in a motorcycle workshop at dusk, a plain matte helmet out of focus on a workbench in the background, warm light from a single lamp. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

### `gants-ete-ou-hiver.webp`
> Close-up of two hands in plain black riding gloves resting on the handlebar grips of a motorcycle, wet country road and scattered autumn leaves softly blurred in the background, light drizzle, overcast late-afternoon light. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.

### `casque-jet-modulable-integral-norme.webp`
> Three plain matte motorcycle helmets on a wooden workshop shelf, left to right: an open-face helmet, a modular helmet with its chin bar raised, and a full-face helmet, all unbranded in neutral grey, olive and black, soft side light from a window. Editorial documentary photograph, natural soft light, muted palette of slate grey, olive green and ochre with a single burnt-orange accent, fine film grain, shallow depth of field, landscape 16:9, generous negative space on one side. Any motorcycle gear is plain matte with no logos. No text, no letters, no logos, no brand names, no readable labels, no recognisable faces.
