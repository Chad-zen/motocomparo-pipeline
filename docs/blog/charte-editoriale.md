# Charte éditoriale — rubrique « Guides & conseils »

Rédigée le 16/10/2026. S'applique à tout article publié sous `/guides/<slug>`
(fichiers `src/mcsite/templates/articles/<slug>.html`, moteur
`src/mcsite/articles.py`). Le calendrier des huit premières semaines est dans
`docs/blog/calendrier.md`.

---

## 1. Pourquoi cette rubrique existe

MotoComparo ne vend rien. Il relève chaque jour les prix d'environ six
marchands (Speedway, La Bécanerie, Motoblouz, Maxxess, Moto-Axxe, FC-Moto) et
les caractéristiques qu'ils publient. Les liens vers les marchands sont
affiliés, et le site le dit.

Les guides des concurrents (étude du 16/10/2026, résumée en annexe) ont trois
défauts récurrents :

- **ils sont écrits par un vendeur** et poussent ses propres fiches ;
- **leurs prix sont figés** (« autour de 150 € », « moins de 240 € »), sans
  date de relevé, et faux quelques semaines plus tard ;
- **leurs avis sont invérifiables** : « testé à 5 °C », « la rédaction a
  élu », notes sur 10 sans grille, normes périmées (ECE 22.05 présentée comme
  en vigueur sur un guide d'achat de 2026).

Notre rubrique fait l'inverse. Chaque article répond à une question précise,
s'appuie sur les chiffres **du jour** tirés de notre catalogue et sur des
sources publiques citées, et dit clairement ce qu'il ne sait pas.

## 2. Le lecteur

- Un motard ou une motarde qui **va acheter** dans les jours ou les semaines
  qui viennent : un premier équipement, un remplacement, un cadeau.
- Il a déjà une question en tête (« gants hiver ou mi-saison ? », « un 22.05
  est-il encore autorisé ? ») et il la tape dans Google.
- Il n'est pas forcément mécanicien ni passionné de technique : il veut une
  réponse claire, puis les moyens de la vérifier.
- Il se méfie des « top 5 » de vendeurs. Notre seul argument est d'être
  vérifiable.

## 3. Les règles d'honnêteté (non négociables)

1. **Aucun essai inventé.** Le site n'a pas de banc d'essai et personne n'a
   porté les produits. Interdits : « nous l'avons essayé », « à l'usage »,
   « on a aimé », « confortable », « silencieux », toute impression de port,
   tout avis d'utilisateur reformulé comme s'il était le nôtre, toute mesure
   que nous n'avons pas faite.
2. **Ce qu'on sait, on le montre ; ce qu'on ne sait pas, on le dit.** Une
   caractéristique absente d'une fiche marchande n'est pas une absence
   constatée : on l'écrit ainsi (« la fiche ne le mentionne pas »).
3. **Aucun prix écrit à la main.** Un prix, un écart de prix, un nombre de
   marchands, un nombre de fiches vient des blocs de données vivants (§ 7).
   Le texte peut dire « le moins cher des deux aujourd'hui » seulement si
   cette phrase est calculée par le gabarit.
4. **Pas de classement sans critère public.** Pas de « meilleur casque » ni
   de « notre préféré ». Si un article ordonne des produits, c'est selon un
   critère affiché et vérifiable (prix du jour, note SHARP, nombre de
   marchands).
5. **Sources citées pour tout fait technique ou légal** : texte de loi
   (Légifrance), norme (ECE 22.06, EN 17092, EN 13594, EN 13634, EN 1621-1/-2),
   programme SHARP (sharp.dft.gov.uk), notice ou site du fabricant. Si une
   source n'est pas trouvable, la phrase disparaît.
6. **Le trou plutôt que l'invention.** Un passage qui demanderait un essai
   reste marqué `{{ a_completer("...") }}` : l'article ne peut alors pas être
   publié (le code l'en empêche, voir `articles.py`).
7. **Pas de ton commercial.** Pas de « incontournable », « must-have »,
   « pépite », « bon plan à saisir », ni de point d'exclamation.

## 4. Le style

- Des **phrases complètes**, correctement conjuguées, au présent. Ni style
  télégraphique, ni bavardage.
- **Factuel et clair** : une idée par phrase, un sujet par paragraphe
  (3 à 5 lignes).
- On vouvoie le lecteur. On écrit « MotoComparo » ou « le site », jamais
  « nous avons testé ».
- **Le jargon est expliqué une fois**, à sa première apparition, entre
  parenthèses ou en une phrase : « boucle micrométrique (une boucle à crans
  qui se ferme d'une main) », « KP (protection des articulations testée) ».
- Chiffres et unités : espace insécable avant « € », « % », « : », « ; »
  (`&nbsp;` dans le gabarit). Guillemets français « … ».
- Les noms de produits sont écrits comme le fabricant les écrit
  (« LS2 FF818 Storm III »), pas comme le flux marchand (« Ff818 »).

## 5. Les cinq formats

Chaque article appartient à un format. La structure est fixe ; seuls les
intertitres changent de mots.

Tous les formats commencent par **« La réponse courte »** : un encadré
`<div class="article__reponse">` de 3 à 5 phrases qui répond à la question
du titre avant toute explication. Le lecteur pressé doit pouvoir s'arrêter
là. Ils finissent tous par **« Pour aller plus loin »** (liens internes,
§ 8).

### A. Le guide de choix (« … : comment choisir »)
Pour une question d'achat générale sur un rayon.
1. La réponse courte
2. Ce que la loi ou la norme impose (si applicable), avec la source
3. Ce que déclarent les fiches du catalogue (1 à 3 blocs `repartition`)
4. Les critères qui changent le choix, un par intertitre ou en liste
5. Avant d'acheter (taille, entretien, pièges)
6. Pour comparer les prix (liens filtrés vers `/c/...`)
7. Pour aller plus loin

Longueur : **900 à 1 400 mots** hors tableaux.

### B. La norme expliquée (« que dit la norme … ? »)
Pour une norme, une étiquette, une obligation légale.
1. La réponse courte
2. Ce que la norme teste, et ce qu'elle ne teste pas
3. Comment le lire sur l'étiquette (lettres, chiffres, pictogramme)
4. Ce qu'on trouve sur le site (comptage par valeur, premier prix)
5. Les idées reçues, corrigées une par une (si utile)
6. Pour aller plus loin

Longueur : **700 à 1 100 mots**.

### C. Le duel (« X ou Y : lequel choisir ? »)
Deux modèles (trois au plus) vendus par **au moins quatre marchands**
chacun, dans le même rayon et la même gamme de prix.
1. La réponse courte, avec la phrase de prix **calculée** (qui est le moins
   cher aujourd'hui, de combien)
2. Le comparatif chiffré (`donnees.comparaison`)
3. Ce que montrent les fiches (points communs, différences déclarées)
4. Ce que les fiches ne disent pas (forme, bruit, confort : ce qui demande
   un essai, dit honnêtement)
5. Comment trancher (étapes concrètes)
6. Pour aller plus loin (fiches `/p/`, marques `/m/`, rayon `/c/`)

Longueur : **700 à 1 000 mots**. Ne jamais désigner de « gagnant ».

### D. Le dossier de saison (« rouler sous la pluie », « l'équipement d'hiver »)
Une situation de conduite qui touche plusieurs rayons.
1. La réponse courte (la liste minimale d'équipement)
2. Une section par pièce d'équipement (casque, blouson, pantalon, gants,
   bottes), chacune avec son critère décisif et un lien vers le rayon filtré
3. Un bloc de données par pièce, au plus (sinon la page devient un tableur)
4. Ce que l'équipement ne règle pas (conduite, visibilité), en renvoyant à
   une source publique (Sécurité routière)
5. Pour aller plus loin

Longueur : **1 200 à 1 800 mots**.

### E. Le guide de prix (« reconnaître une vraie promotion », « à moins de 100 € »)
Ce que seul un comparateur peut écrire : prix du jour, plus bas prix relevé,
écarts entre marchands.
1. La réponse courte
2. La méthode (comment lire un prix barré, l'historique, les frais de port)
3. Les chiffres du jour (blocs `prix_bas`, `repartition`, comparaison)
4. Les pièges (taille absente, millésime, rupture de stock)
5. Pour aller plus loin (`/bons-plans`, alertes de prix)

Longueur : **700 à 1 200 mots**.

## 6. Titre, description, slug

- **Titre (`titre:`)** : 45 à 65 caractères. Il reprend la requête telle
  qu'on la tape (« gants moto hiver », « casque 22.05 ») et promet une
  réponse, pas un superlatif. Le site ajoute « — MotoComparo » après.
  Pas d'année dans le titre sauf si le sujet en dépend (Black Friday).
- **Description (`description:`)** : 120 à 160 caractères. Une phrase qui
  dit ce que la page apprend et ce qu'elle a de propre (chiffres du
  catalogue, comparaison entre marchands). **Aucun prix ni aucun nombre
  susceptible de changer** (la description n'est pas recalculée).
- **Slug** : le nom du fichier, en minuscules et tirets, 3 à 7 mots, sans
  date. Il ne change plus après publication.
- **Un seul H1** (le titre, posé par la page). Les intertitres du corps sont
  des `<h2>`, et `<h3>` au besoin. Un intertitre dit ce que contient la
  section (« Ce que la loi impose »), pas une accroche.
- `date:` = date de publication. Toute mise à jour de fond ajoute
  `maj: AAAA-MM-JJ`.

Le test `test_les_trois_premiers_articles_sont_publies_et_complets` vérifie
les longueurs de titre et de description des trois premiers articles ;
ajouter tout nouvel article publié à la liste `PUBLIES` du test.

## 7. Les blocs de données vivants

Ils se calculent à l'ouverture de la page et sont mis en cache comme le
reste du site. Aucun chiffre du texte ne doit les dupliquer.

| Besoin | Appel dans le gabarit | Affichage |
|---|---|---|
| Deux à quatre fiches côte à côte : prix du jour, nombre de marchands, plus bas prix sur 30 jours, caractéristiques | `{% set c = donnees.comparaison(['slug-1', 'slug-2']) %}` puis `{% include "_article_comparaison.html" %}` | tableau + lien vers `/comparatif/...` |
| Combien de fiches déclarent chaque valeur d'une caractéristique, prix médian et plus bas | `{% set rep = donnees.repartition('gloves', 'saison') %}` puis `{% include "_article_repartition.html" %}` | tableau + part des fiches renseignées |
| Plus bas prix relevé d'une fiche sur N jours | `{% set b = donnees.prix_bas('slug', 90) %}` | à mettre en phrase dans le gabarit |
| Nombre de fiches et premier prix par sous-rayon | `nav` (déjà dans la page), voir `casque-jet-modulable-integral-norme.html` | tableau |

Règles d'usage :

- **Une phrase qui cite un chiffre est calculée** (`{% if %}` dans le
  gabarit) ou n'existe pas. Exemple : la réponse courte du duel LS2 /
  Scorpion.
- **Toujours prévoir le cas vide** : une fiche peut disparaître, un prix
  peut manquer. Les gabarits de blocs le gèrent déjà ; une phrase calculée
  doit avoir son `{% else %}` ou rester silencieuse.
- **Trois blocs `repartition` au plus par article.** Au-delà, l'article
  devient un tableur.
- **Lire la répartition honnêtement** : elle compte ce que les marchands
  *déclarent*. Le gabarit l'écrit sous chaque tableau ; le texte ne doit
  pas dire « 80 % des gants sont … » mais « parmi les fiches qui le
  précisent ».
- Un libellé inadapté au rayon se remplace dans l'article :
  `{% set rep = dict(donnees.repartition(...), libelle='Homologation') %}`.
- Les caractéristiques disponibles (et leur rayon) se listent par la requête
  sur `product_caracteristique` ; les plus fournies : `saison`,
  `impermeable`, `membrane`, `homologation`, `classe_protection`,
  `niveau_genoux`, `dorsale`, `doublure_thermique`, `chauffant`, `kp`,
  `manchette`, `calotte`, `pinlock`, `ecran_solaire`, `intercom`,
  `note_securite` (SHARP), `poids_g`.

## 8. Les liens internes

Chaque article contient au minimum :

- **1 lien vers le rayon** concerné (`/c/<code>`), et de préférence vers le
  rayon filtré qui répond à la question (`/c/gloves?saison=hiver`,
  `/c/jacket?homologation=classe-aa`). Filtres disponibles : `saison`,
  `homologation`, `matiere`, `marque`, `prix_min`, `prix_max`.
- **1 lien vers un autre guide** (`/guides/<slug>`) ou un repère de la page
  `/guides` (`#guide-taille-casque`, `#guide-ece2206`, `#guide-normes`,
  `#guide-comparer-prix`).
- Pour un duel : les fiches (`/p/<slug>`), les marques (`/m/<code>`) et le
  comparateur (posé par le bloc).
- **Maillage retour** : à la publication d'un article, ajouter un lien vers
  lui dans un ou deux articles existants du même rayon.

Les ancres sont descriptives (« les gants d'hiver comparés »), jamais
« cliquez ici ». Les liens externes (Légifrance, SHARP, fabricant) portent
`rel="noopener"` ; aucun lien direct vers un marchand dans le texte (les
liens affiliés vivent sur les fiches).

## 9. Citer les sources

- Dans le texte, au plus près de l'affirmation : « (article R431-1-2 du Code
  de la route) », « selon le programme SHARP (sharp.dft.gov.uk) ».
- Un lien quand la source est en ligne et stable ; sinon la référence
  exacte (numéro de norme, date du décret).
- Les données du site sont présentées comme telles : « dans notre
  catalogue », « les fiches marchandes déclarent ».
- Ne jamais citer un concurrent comme source d'un fait technique.

## 10. Les illustrations

### Ce qu'on illustre, et ce qu'on n'illustre pas
- **Une illustration par article**, en tête, générée par la propriétaire
  avec Meta AI à partir du prompt fourni dans le calendrier.
- **Des scènes, des ambiances, des concepts** : une route mouillée, des
  mains gantées sur une poignée, un mètre de couturière, une étagère
  d'atelier.
- **Jamais un produit de marque réel**, ni une imitation : un faux « LS2 »
  généré tromperait le lecteur. Les photos de produits réels sont celles des
  marchands, déjà sur les fiches.
- Équipement visible = **uni, mat, sans logo ni inscription**. Si Meta AI
  ajoute un pseudo-logo, des lettres ou un motif qui rappelle une marque,
  l'image est refusée et régénérée.
- Pas de visage reconnaissable (motard de dos, casque fermé, visière
  fumée, ou cadrage sur les mains).
- Pas de texte dans l'image : le titre est déjà dans la page.

### Le style commun (à coller à la fin de chaque prompt)

> Editorial documentary photograph, natural soft light, muted palette of
> slate grey, olive green and ochre with a single burnt-orange accent, fine
> film grain, shallow depth of field, landscape 16:9, generous negative space
> on one side. Any motorcycle gear is plain matte with no logos. No text, no
> letters, no logos, no brand names, no readable labels, no recognisable
> faces.

Ce style donne une unité à la rubrique : même lumière, même palette, même
grain. On ne mélange pas avec de l'illustration dessinée ou de la 3D.

### Format du fichier
- **1600 × 900 px** (16:9), **WebP**, qualité 80, moins de 250 Ko.
- Nom = le slug de l'article : `<slug>.webp`.
- Déposé dans `src/mcsite/static/guides/`.

### Dans l'en-tête de l'article
```
illustration: <slug>.webp
illustration_alt: Une phrase qui décrit la scène, pas le sujet de l'article.
```
- Le texte alternatif décrit **ce qu'on voit** (« Mains gantées posées sur
  la poignée d'une moto, route mouillée en arrière-plan »), 80 à 140
  caractères, sans « image de » ni mot-clé ajouté pour Google.
- Sans fichier déposé, l'article s'affiche simplement sans image : on peut
  remplir l'en-tête avant de générer l'image.
- La page ajoute d'elle-même la légende « Illustration d'ambiance générée
  par IA », sert l'image comme image de partage (`og:image`) et la déclare
  dans les données structurées.

## 11. Rythme

Deux articles par semaine, **le mardi et le vendredi**. Le mardi pour un
guide de fond (formats A, B, D), le vendredi pour un format plus court
(C, E) ou d'actualité saisonnière. Un article écrit d'avance reste
`statut: brouillon` jusqu'à sa date.

## 12. Liste de vérification avant publication

Contenu
- [ ] La question du titre a une réponse dans l'encadré « La réponse
      courte ».
- [ ] Aucune phrase ne prétend un essai, un port, une mesure ou un avis
      personnel. Relire en cherchant : *essayé, testé, porté, à l'usage,
      confortable, silencieux, on a aimé, notre préféré, meilleur*.
- [ ] Aucun prix, écart ou nombre de marchands écrit à la main
      (chercher `€` et les chiffres dans le fichier : chacun doit venir d'un
      bloc ou être une date, une norme, un article de loi).
- [ ] Chaque fait technique ou légal a sa source.
- [ ] Le jargon est expliqué à sa première apparition.
- [ ] Aucun `a_completer(...)` restant.

Référencement
- [ ] Titre 45–65 caractères, description 120–160 caractères, sans prix.
- [ ] Intertitres en `<h2>`/`<h3>`, un sujet chacun.
- [ ] Au moins un lien rayon, un lien guide, et les fiches pour un duel.
- [ ] Un lien vers ce nouvel article ajouté dans un article existant.

Image
- [ ] Image sans logo, sans lettre, sans visage, au style commun.
- [ ] `<slug>.webp` 1600 × 900 dans `static/guides/`, `illustration_alt`
      rempli.

Technique
- [ ] Rendu vérifié en local avec `BLOG_APERCU=1` : les blocs affichent
      des chiffres, pas « Aucune fiche… ».
- [ ] Le slug est ajouté à `PUBLIES` dans `tests/test_site_articles.py`,
      et `pytest -q tests/test_site_articles.py` passe.
- [ ] `statut: publié`, `date:` du jour.

---

## Annexe — ce que font les concurrents (étude du 16/10/2026)

| Site | Formats | Ce qui marche | Ce qui manque |
|---|---|---|---|
| Motoblouz, #EnjoyTheRide (`/enjoytheride/guides-achat`) | 28 guides « Bien choisir… », « top 5 » annuels, essais produits | couverture large, guides saisonniers (hiver, pluie), essais longs signés avec conditions d'usage | sélection non expliquée, prix absents ou non datés, aucune source externe, dates contradictoires, lien commercial non déclaré sur les « top » |
| Speedway, guide d'achat casque | guide long (2 200–2 500 mots), H2/H3 par type et critère | structure exhaustive, maillage vers les rayons | ECE 22.05 présentée comme norme en vigueur, ni date ni auteur, conditions de livraison contradictoires, bannières promo |
| Dafy, « Comment choisir son blouson moto hiver » | guide court (~600 mots), 4 H2 « doit être… » | lisible, centré sur la décision | chiffres non sourcés, pas de date, conseils vagues (« essayez-le »), ton vendeur |
| Le Repaire des Motards, « bien choisir ses gants » | dossier long (~3 000 mots), auteur nommé, photos | vrai savoir pratique, défauts courants, repères de prix | 2020 sans mise à jour visible, EN 13594 jamais citée, prix périmés |
| Meilleurtest (comparatifs « 9 analysés, 4 retenus ») | top N avec notes sur 10, FAQ, liens Amazon affiliés | gabarit SEO efficace, date affichée | « tests » sans protocole, 5 produits sur 9 jamais nommés, incohérences entre fiches, prix statiques |
| Que Choisir, guide casques | guide indépendant, sources liées (étude Mutuelle des Motards / Fondation Maif) | confiance, idées reçues corrigées | pas de lien vers les prix, pas de données de marché |

Les manques que MotoComparo comble :
1. **Le prix du jour, chez plusieurs marchands, dans le texte** — personne
   ne le fait ; tous figent un prix ou n'en donnent pas.
2. **Le plus bas prix relevé** (historique) pour juger une promotion —
   seuls les comparateurs généralistes l'ont, et sans article autour.
3. **Le comptage du marché** : combien de modèles comparables déclarent
   une membrane, une classe AA, une note SHARP, à quel prix médian.
4. **L'honnêteté vérifiable** : sources liées, « ce que la fiche ne dit
   pas », aucune prétention d'essai.

---

## 10. La forme cible (23/10/2026, d'après un article de référence demandé par la propriétaire)

Les cinq formats (§ 5) gardent leur logique, mais **chaque article prend désormais la forme d'un article de fond**,
long, sourcé, que l'on peut survoler ou lire en entier. Le moteur (`articles.py`, `article.html`) fournit lui-même :
le **temps de lecture**, la **date de mise à jour**, le **sommaire** « Dans cet article » (un lien par `<h2>`, ancres
automatiques), les **données structurées** (`BlogPosting`, et `FAQPage` si l'article a une FAQ), le bloc
**« À lire aussi »** (trois autres articles) et un **appel sobre vers le rayon** (jamais vers un marchand).
L'auteur écrit, dans le fichier, les éléments suivants, dans cet ordre :

1. **« À retenir »** — l'encadré `<div class="article__reponse">` existant, mais en **quatre puces** (`<ul>`) qui
   donnent l'essentiel : la réponse à la question du titre, puis les trois critères qui comptent. Pas de paragraphe.
2. **Une introduction** de 3 à 5 phrases : à qui s'adresse l'article, ce qu'on y trouve, d'où viennent les chiffres.
3. **Six à huit sections `<h2>`** (réparties en `<h3>` au besoin), qui suivent une progression : définition ou
   règle → ce qu'elle change pour le lecteur → ce que montre le catalogue → comment choisir → pièges.
4. **Un tableau comparatif** alimenté par un bloc de données vivantes (§ 7). Jamais de chiffre écrit à la main.
5. **Un à deux encadrés « Bon à savoir »** : `<aside class="article__bon-a-savoir"><p><b>Bon à savoir.</b> …</p></aside>`.
   Un fait court, utile, sourcé (une règle, un piège, une erreur courante).
6. **Un exemple chiffré** quand il en existe un vérifiable (calculé par le gabarit, jamais écrit).
7. **Des liens internes** vers les rayons filtrés, les autres articles et les fiches (§ 8), au moins six.
8. **Une FAQ de cinq questions** (les questions que les gens tapent vraiment), au format exact :

   ```html
   <section class="article__faq">
     <h2>Questions fréquentes</h2>
     <details class="faq"><summary>La question, avec son point d'interrogation ?</summary>
       <p>La réponse en deux à quatre phrases, sourcée comme le reste du texte.</p></details>
     … (cinq au total)
   </section>
   ```
   Le moteur lit ces blocs pour produire les données structurées `FAQPage` : la forme est donc obligatoire.
9. **Une section « Sources »** en dernier : `<section class="article__sources"><h2>Sources</h2><ol><li><a href="…">Titre de la page</a>, organisme, date de consultation</li>…</ol></section>`.
   Une liste de toutes les sources citées dans le texte (loi, norme, organisme, fabricant), jamais un site marchand.
10. **« Pour aller plus loin »** n'est plus une section : elle est remplacée par « À lire aussi » (automatique).

**Longueur :** 1 500 à 2 300 mots hors tableaux, FAQ et sources (le format C, le duel, reste à 1 200 à 1 800).
**Ton :** pédagogique et direct, phrases courtes, jargon expliqué une fois, vouvoiement.
**Confiance :** la page porte déjà la mention sur les prix relevés et l'absence d'essai ; le texte ne promet rien
d'autre. Aucun avis, aucune note, aucune impression de port.

### La mise en page (23/10/2026)

La page reprend la mise en page de l'article de référence : durée de lecture et date au-dessus d'un grand titre,
signature de l'équipe, grande image arrondie (l'illustration si elle est déposée, sinon un bandeau au pictogramme du
rayon), carte « À retenir » avec son icône, cartes « Bon à savoir », FAQ en cartes dépliantes, et le **sommaire en
barre fixe en bas de l'écran** (il s'ouvre vers le haut). Rien de cela ne demande de balisage particulier, hors la
convention de la FAQ (§ 10, point 8).

**Pour que le texte tienne cette mise en page :** des paragraphes courts (deux à quatre phrases) ; la réponse dans
la première phrase de chaque section ; les termes clés en gras à leur première apparition ; une liste à puces dès
que l'on énumère des critères ; pas de bloc de texte de plus de six lignes sur un téléphone.
