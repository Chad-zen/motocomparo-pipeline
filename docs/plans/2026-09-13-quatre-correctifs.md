# Quatre correctifs, un seul réappariement

Date : 2026-09-13. Tous appliqués ensemble parce qu'ils ne se voient qu'après un
`match --reset`, et qu'un réappariement complet coûte ~25 minutes de base
verrouillée. Les grouper permet aussi une seule mesure avant/après.

Photo d'avant : `ops/avant_inclusion.json` — comparables 24 590, éclatement réel
1 553, fusion_ratio_gte_5 4 719, doublons 9 430, cohérence 0.

## 1. Règle d'inclusion sur les couleurs (`match.py`)

Le problème mesuré : 7 100 des 10 052 conflits de couleur ne sont pas des
désaccords, ce sont des **inclusions**. Un marchand écrit `noir`, l'autre
`noir-rouge` pour le même code-barres. Ce n'est pas deux produits différents,
c'est un marchand plus bavard que l'autre. La règle d'avant mettait les deux en
quarantaine : 14 677 offres bloquées pour rien.

La couleur sort du `HAVING` principal et passe dans une branche `UNION` qui
teste l'inclusion terme à terme (`string_to_array` + `@>`). Si l'un des deux
libellés contient l'autre, ce n'est pas un conflit. Le garde-fou parent-EAN
reste en place. La couleur retenue est la plus longue — la plus précise.

Objection du senior (les EAN parents fausseraient l'inclusion) : mesurée fausse.
17 codes-barres concernés sur 426 782, zéro sur les casques.

## 2. Une couleur n'est jamais une taille (`textnorm.size_code`)

`NOIR` arrivait dans le champ taille de 6 456 offres Motoblouz et 417 La
Bécanerie, plus `BLEU` et `GRIP`. Conséquence : une fiche éclatée en fausses
variantes, et une offre qui ne peut pas se ranger avec ses vraies tailles.

Le mot est maintenant rejeté quelle que soit sa provenance — y compris quand il
vient du flux, parce qu'un flux qui écrit une couleur dans la colonne taille
n'est pas plus fiable qu'un titre.

## 3. Les longueurs de jambe ne créent plus de fausses tailles

`Short XL` et `XL` sont la même taille avec une coupe différente. Avant, la
fiche affichait `SHORTXL` à côté de `XL` comme deux variantes distinctes.
`_FIT_PREFIX_RE` retire le préfixe (`Short`, `Long`, `Court`) et garde la
taille. Vérifié : `('Short XL','feed') → ('XL','feed')`.

La coupe n'est pas perdue par négligence : elle n'est pas une taille, et le site
n'a aujourd'hui aucun endroit pour l'afficher. La reprendre comme attribut à
part est une tâche séparée.

## 4. Les pièces détachées sortent du rayon casques (`enrich.py`)

Speedway vend onze « Mentonnière HJC RPHA 90S … - Pièces détachées casque » à
90 €, assises au milieu de casques modulables à 455 €. La règle existante
demandait « pour casque » ou « de casque » pour que le mot « casque » d'un titre
ne suffise pas à en faire un casque — et « Pièces détachées casque » n'a ni l'un
ni l'autre.

`_IS_A_SPARE_PART` le dit directement. Vérifié qu'un vrai casque dont le nom de
modèle contient un mot d'accessoire (« Nolan N20-2 **Visor** Dolce Vita ») reste
un casque.

## Règle d'arrêt

Si la sur-fusion bouge (`fusion_ratio_gte_5`, `doublons`, `cohérence`), on
revient en arrière. Gagner des comparables en fusionnant des produits différents
coûte 10 à 50 fois plus cher que rater une fusion.

---

## Résultat, mesuré

`match --reset` : 2 844 s (47 min), 247 358 fiches, 423 886 variantes,
507 986 offres par code-barres, 103 237 par groupe d'articles.

| | avant | après | |
|---|---|---|---|
| **Fiches comparables (2 marchands+)** | 24 590 | **27 234** | **+2 644** |
| Fiches avec prix | 213 214 | 215 828 | +2 614 |
| Fusion suspecte ×5 | 4 719 | 4 732 | +13 |
| Fusion suspecte ×20 | 840 | 841 | +1 |
| Pire fiche (nb codes-barres) | 1 314 | 1 314 | 0 |
| Écart de prix ×10 | 75 | 75 | 0 |
| Incohérences | 0 | **0** | 0 |

**Gardé.** La règle d'arrêt portait sur la sur-fusion : elle n'a pas bougé
(+0,3 % sur l'indicateur principal, zéro sur les trois autres).

Casques après coup : 15 138 fiches, **3 256 comparables** (intégral 1 556,
jet 663, cross 480, modulable 468, non précisé 89).

## Ce que la mesure a appris en route

### `verify` appliquait encore l'ancienne règle

2 726 violations de couleur au premier passage — toutes des inclusions
(`['BK','BK|MAT']`, `['BK-SI','SI']`), aucune contradiction. Le catalogue allait
bien ; c'est le contrôleur qui n'avait pas été mis à jour avec la règle qu'il
contrôle. Corrigé : `verify._INVARIANTS` porte désormais une *tolérance*, et
celle de la couleur est la règle d'inclusion de `match.py`, écrite à
l'identique. Le test qui encodait l'ancienne règle (`BK` contre `BK-RD`) a été
réécrit sur une vraie contradiction (`BK` contre `WH`), et deux tests ajoutés :
l'inclusion est acceptée, et le pontage `BK` / `BK|MAT` / `BK|GLO` reste refusé.

Reste 6 fiches en violation réelle sur 247 358 — du pontage par une couleur
partielle. À traiter en revue, pas à masquer.

### L'indicateur de sur-fusion comptait un cas légitime

`fusion_doublons_marchand_taille` bondissait de +1 173. Attribution : 1 014 de
ces paires viennent des coupes de jambe. FC-Moto vend le pantalon Held Tridale
en `Short L` **et** `Long L` : une taille, deux coupes, deux articles réels. Le
correctif n° 3 ramène les deux à `L`, ce qui est juste, et l'indicateur y voyait
un doublon suspect.

L'indicateur exclut maintenant les coupes et les compte à part
(`tailles_coupes_jambe` : 436). Après correction, l'écart réel est **+128**.

## Dettes ouvertes, nommées

1. **436 paires de coupes s'afficheront mal** : « L » deux fois sur une fiche
   pantalon, sans mention de la coupe. Ce n'est pas une erreur de données, c'est
   un attribut manquant à l'affichage.
2. **La photo d'avant n'était pas ventilée par catégorie**, donc le gain propre
   aux casques n'est pas chiffrable a posteriori. `ops/mesure_catalogue.py`
   devrait relever les comparables par catégorie.
3. **`match` a coûté 47 min** contre ~30 avant. La règle d'inclusion déborde sur
   disque (`BuffileRead` pendant 26 min). Optimisable.

---

## Correctif n° 5 — un code-barres, une taille (affichage)

Trouvé en cliquant, après coup, sur `/p/helstons-gants-swallow-bk-f7e5f810`.

Quatre marchands vendent les mêmes gants Helstons Swallow sur les **mêmes quatre
codes-barres**, et nomment les tailles dans trois vocabulaires : `6 7 8 9`
(Motoblouz, FC-Moto), `T6 T7 T8 T9` (La Bécanerie), `XS S M L` (Speedway).

La page offrait **huit boutons de taille pour quatre tailles réelles**. Cliquer
« 6 » faisait disparaître Speedway ; cliquer « XS » faisait disparaître les trois
autres. La comparaison — la seule raison d'être du site — ne fonctionnait pas.

La règle est celle de la propriétaire : *le code-barres fait foi, on ne devine
jamais une taille*. Deux libellés sur un même code-barres sont donc une seule
taille, affichée `6 / XS`. Deux au maximum, dans l'ordre éditorial des marchands
(celui de `product_stats`, sql/009) : au-delà le bouton devient illisible.

Corrigé à l'affichage (`mcsite.labels.equivalences_tailles`) et non dans le
pipeline : chaque offre garde le libellé que son marchand a écrit, ce qui est la
vérité de la donnée. Seule la page les réunit. Aucun réappariement nécessaire.

**Garde-fou — les codes-barres parents.** Un marchand qui porte plusieurs
tailles sous un seul code-barres utilise un code couvrant une gamme : ce
code-barres ne prouve rien et il est ignoré entièrement. Sans cela, un seul code
parent fusionnerait `S`, `M` et `L` en un unique bouton — exactement l'inverse
du correctif. Quatre tests couvrent le cas nominal, le cas parent, la limite à
deux libellés et la taille isolée.

**Portée : 3 185 fiches** portent un même code-barres avec deux libellés de
taille différents.

---

## Un seul design — la v1, choisie

Les deux langages visuels cohabitaient depuis la veille, précisément pour que la
décision se prenne en regardant le même produit dans les deux. Décision prise le
2026-09-13 : **on garde la v1, l'autre est supprimé.**

Ce n'était pas un simple changement d'habillage : la route `/v1/c/{code}`
portait aussi la **colonne de filtres** (marque, tranche de prix, nombre de
marchands, tri) que `/c/{code}` n'avait pas. Supprimer la v1 telle quelle aurait
fait perdre les filtres — c'est donc son corps qui devient celui de `/c/{code}`.

- `base_v1.html`, `listing_v1.html`, `product_v1.html` deviennent `base.html`,
  `listing.html`, `product.html` ; les trois anciens sont remplacés.
- Les routes `/v1/c/{code}` et `/v1/p/{slug}` n'existent plus (404).
- Tous les liens internes en `/v1/...` sont réécrits, y compris dans `admin.html`.
- `v1.css` est replié à la fin de `style.css`, **dans le même ordre** qu'il était
  chargé, donc les mêmes règles gagnent les mêmes arbitrages. Une seule feuille
  de style : c'est aussi ce qui avait piégé le cache le jour du logo géant.
- La classe `.theme-v1` reste sur `<body>` : elle dit d'où viennent les valeurs,
  elle ne désigne plus un thème parmi deux.

`/recherche` partage le gabarit des catégories mais n'a pas de catégorie où
filtrer : elle passe `facettes=None` et la colonne s'efface, plutôt que d'avoir
un second gabarit à maintenir.

Vérifié après bascule : accueil, catégorie, catégorie filtrée, fiche, recherche
et tableau de bord répondent 200 ; les deux routes `/v1/` répondent 404 ; une
seule feuille de style est chargée ; la colonne de filtres est présente sur une
catégorie et absente sur la recherche.

---

## Le design v1, complété

La première reprise du design v1 n'avait porté que le cadre — bandeau de
confiance, en-tête, rail de catégories, grille de produits. La page d'accueil de
la v1 en production contient six blocs de plus, relevés sur le site lui-même :

1. **L'accroche** — « Comparez l'équipement moto au meilleur prix », la ligne de
   chiffres, deux boutons.
2. **Les rayons** — un par famille, avec un défilement horizontal. C'est ce qui
   donne à la page son allure de boutique plutôt que de catalogue.
3. **Comment ça marche** — trois étapes numérotées.
4. **Pourquoi MotoComparo** — le tableau comparatif.
5. **Questions fréquentes** — cinq questions dépliables.
6. **Le dernier appel** avant le pied de page.

Plus le **pied de page en colonnes** (marque, rayons, liens rapides,
informations), qui était réduit à deux lignes.

### Ce qui a été repris tel quel, et ce qui ne l'a pas été

Les textes sont ceux de la v1, à trois exceptions près, toutes pour la même
raison — **ne rien affirmer que le pipeline ne tienne** :

- Les chiffres de l'accroche sont **lus dans la base à chaque affichage**. La v1
  annonce « 25 000+ références » en dur ; un comparateur qui se trompe sur son
  propre volume se disqualifie sur la seule chose qu'on lui demande.
- La v1 cite trois marchands (« Motoblouz, La Bécanerie et Maxxess »). Il y en a
  six.
- La v1 dit « nos robots vérifient les prix plusieurs fois par jour ». Le
  pipeline tourne une fois par jour. La réponse dit ce qui est vrai, et ajoute
  la règle qui compte : un prix de plus de 24 heures n'est pas affiché.

### Formulaire d'inscription à la newsletter : non repris

La v1 en a un. Il n'est pas repris, faute d'endroit où envoyer l'adresse : un
champ e-mail qui ne mène nulle part collecte une donnée personnelle pour rien.
À rajouter le jour où il y a une liste derrière.

### Page « À propos » (`/infos`)

Créée pour que les liens du pied de page mènent quelque part. Elle dit les trois
choses qu'un comparateur doit dire pour être cru : les liens sont affiliés et
cela ne change pas le prix payé, un prix de plus de 24 h est retiré plutôt
qu'affiché, et le site ne demande ni compte ni adresse e-mail. Elle décrit aussi
la règle du code-barres et celle des tailles.

**Les textes juridiques restent à écrire par la propriétaire** — mentions
légales, conditions d'utilisation. Rien de tel n'a été inventé ici.

### Requête

`queries.rayons()` : une seule requête pour les neuf rayons (`ROW_NUMBER` par
famille), 0,18 s. Neuf requêtes séparées auraient donné neuf occasions à la plus
lente de fixer la vitesse de la page d'accueil.

### Vérifié

Accueil, à propos, catégorie, fiche, recherche et tableau de bord répondent 200.
Les six blocs sont présents, les 90 images des rayons se chargent, la page ne
déborde pas horizontalement (521 px de contenu pour 535 px de fenêtre) — seuls
les rayons défilent, dans leur propre cadre.

### Dette relevée au passage

`/admin` met **17 secondes** à répondre. Le tableau de bord compte tout le
catalogue à chaque affichage, sans pré-calcul. À traiter.

---

## Accueil refondue, menu, filtres mobiles, marques

### Le menu burger n'ouvrait rien

Il était dessiné, pas branché. Repris sur le schéma exact de la v1 (relevé dans
le HTML du site en production) : panneau sombre entrant par la gauche, en-tête
ambre « MENU / FERMER », voile cliquable, `Échap` pour fermer, page bloquée
derrière.

Un seul composant `.tiroir` sert deux usages — le menu et les filtres — donc
ouvrir l'un ferme l'autre sans code supplémentaire.

### Le filtre mobile était inutilisable

Au-dessous de 900 px, `.boutique` passait à une colonne et la colonne de filtres
se plaçait **au-dessus** de la grille : il fallait dépasser prix, marchands,
marques et catégories en entier avant de voir un seul produit. C'est le même
défaut que la v1 avait résolu avec son tiroir. Une barre « ☰ Filtres — N
résultats » l'ouvre maintenant.

### Cliquer une marque menait à une recherche texte

Le rail de marques pointait vers `/recherche?q=shoei` : une recherche plein
texte, qui répond avec ce qui contient le mot et n'offre aucun filtre une fois
arrivé. Une marque est un **filtre**, pas une requête. Nouvelle route `/m/{marque}` :
le même listing que les catégories, marque fixée, catégorie ouverte — donc prix,
nombre de marchands et catégories restent filtrables depuis là.

### Icônes de rayon

Vingt icônes SVG écrites à la main (`templates/_icones.html`), posées sur la
pastille dégradée de la v1. Une teinte par famille : ambre pour le casque
(catégorie phare), bleus profonds pour l'équipement du pilote, vert pour les
protections, gris acier pour la mécanique.

**Pourquoi pas des images générées** (la question a été posée) : une icône
d'interface fait 24 px de côté. Une image matricielle y arrive floue, pèse des
centaines de kilo-octets pour vingt rayons, ne peut pas prendre la couleur du
thème, et vingt images générées séparément n'ont pas le même style. L'effet
« soigné » vient de la régularité — même cadre, même épaisseur de trait, même
pastille — pas du détail de chaque dessin.

### La page d'accueil, inspirée d'idealo

Ce qui est repris d'idealo : **l'ordre**. Leur page s'ouvre sur une barre de
rayons puis immédiatement des produits avec un badge chiffré et le nombre
d'offres. La nôtre ouvrait sur un pavé sombre de 366 px — sur un téléphone il
fallait défiler pour comprendre qu'il s'agissait d'une boutique. Le pavé est
supprimé ; le mode d'emploi et les questions fréquentes descendent en bas, où on
les lit quand on en a besoin.

Ce qui n'est **pas** repris : leur badge de remise, calculé contre un prix de
référence que personne ne vérifie. Le nôtre (`queries.ecarts`) est l'écart entre
le marchand le moins cher et le plus cher **pour le même article, aujourd'hui**.
Rien n'est affirmé sur ce que le produit valait avant.

Trois garde-fous dans cette requête, chacun pour une raison mesurée :

- **plafond à un facteur deux** — au-delà, c'est bien plus souvent une fusion
  ratée qu'une affaire (`ops/mesure_catalogue.py` suit exactement cette forme
  sous `fusion_ecart_prix_x10`). Mettre nos pires fusions en tête d'accueil
  reviendrait à faire la publicité du défaut ;
- **un écart minimum de 25 EUR** — 50 % sur une chambre à air font 7 EUR, et une
  rangée de piécettes ne donne à personne l'envie de comparer ;
- **une ligne par modèle** — le même silencieux GPR en trois finitions est trois
  fiches et remplissait la rangée à lui seul.

### Collision de noms évitée

Les tuiles de rayon s'appelaient d'abord `.tuile`, nom déjà pris par les cases
du tableau de bord : `.tuile__n` y est en 23 px gras, et la redéfinir en 12 px
aurait cassé `/admin` sans que la page d'accueil montre quoi que ce soit
d'anormal. Renommées `.rayon-tuile`.

### Vérifié

Accueil, catégorie, marque, fiche, recherche, à propos et tableau de bord
répondent 200 ; `/m/inexistante` répond 404 ; les deux tiroirs s'ouvrent et se
ferment (mesuré sur le DOM, panneau à 330 px, voile actif) ; les vingt icônes
sont rendues.

---

## Vignettes photo, favoris, comparateur, thème sombre

### Photo dans les tuiles, dessin dans le menu

Première lecture, incomplète : n'ayant regardé que les pages d'accueil, j'avais
conclu que « Dafy n'a aucune icône de catégorie » et retiré les vingt dessins.
Les captures des **menus** de Speedway, Dafy et Motoblouz montrent le contraire —
les trois dessinent leurs rayons au trait. La règle réelle est un partage :

- **tuiles d'accueil → photo produit** (ce que font Motoblouz avec
  `Vignettes-picto_CASQUE.jpg` et Dafy partout) ;
- **menu → dessin au trait**, et les trois font les mêmes quatre choix :
  aucune pastille de couleur derrière, une icône **large** (~48 px, pas 22),
  **une seule** couleur — la leur —, l'objet vu de **trois quarts**. Plus un
  chevron à droite et un libellé en capitales.

C'est la présentation autant que le dessin qui rendait la première série laide :
à 22 px dans une pastille dégradée, un trait fin devient du bruit.

Les tuiles d'accueil gardent donc la photo du produit le plus comparé du
rayon. À 40 pixels, la photo d'un casque dit
« casque » mieux que n'importe quel dessin, et ce catalogue en contient 400 000.

Un piège en route : un rayon parent ne contient que les articles dont le
sous-type n'a pas pu être lu, donc sa réserve d'images n'est pas représentative
— « Casques » avait sorti un **pare-soleil**. Le parent prend désormais l'image
de son plus gros enfant.

### Favoris et comparateur

Les deux actions sur chaque visuel, comme en v1, plus le **bandeau du bas à
quatre emplacements** (les vides en pointillés, un ✕ rouge sur les pleins,
« Tout retirer », « Comparer (n) »), et deux pages `/favoris` et `/comparer`.

Tout vit dans le navigateur : le site n'a ni compte ni adresse e-mail, donc une
liste de côté ne peut vivre nulle part ailleurs. Chaque lecture et chaque
écriture est protégée par un `try` — en navigation privée `localStorage` lève
une erreur, et une liste de favoris ne doit jamais empêcher le site de
fonctionner.

Deux détails qui ne se voient que quand ils manquent :

- les boutons sont **à l'intérieur** du lien de la carte, donc chacun annule la
  navigation lui-même : sans cela, cliquer le cœur ouvrirait la fiche ;
- chaque entrée retient l'identifiant **et** la vignette, pour que le bandeau se
  dessine sans interroger le serveur, y compris sur une page qui ne contient
  aucun des produits retenus.

Les pages `/favoris` et `/comparer` font un aller-retour : le script remet les
identifiants dans l'URL et recharge. Le serveur produit alors les mêmes cartes
que partout ailleurs — pas de second rendu en JavaScript à maintenir — et
l'adresse obtenue est partageable.

### La fiche produit, reprise de la v1

Badge « N offres comparées » sur le visuel, pastille de marque, titre,
**« Réf. <code-barres> »**, la signature « Comparateur indépendant », puis le
bloc **Meilleur prix** sur fond nuit avec le bouton comparateur en rond ambre et
« Voir l'offre → » pleine largeur, suivi des quatre promesses.

Deux choix de fond :

- La référence affichée est le **code-barres**, et les deux marchands à GTIN
  synthétique en sont exclus : le leur, c'est nous qui l'avons fabriqué, il
  n'identifie rien pour personne d'autre.
- Les cinq étoiles ne sont **pas** une note de produit — personne n'a testé ce
  casque ici. Le libellé dit « Comparateur indépendant » en toutes lettres pour
  qu'aucun visiteur ne lise « 5 étoiles pour ce casque ».

### Thème clair / sombre

Bouton dans l'en-tête, choix retenu par le navigateur, et **sans choix on suit
le réglage du système**. Le thème est posé avant le premier rendu : appliqué
après chargement, la page apparaîtrait une fraction de seconde en clair.

Deux défauts trouvés en le vérifiant, tous deux invisibles à l'œil sur une seule
page :

1. `.theme-v1` est posée sur `<body>` et redéfinit `--bg` et `--ink`. Plus
   profonde que `:root`, elle gagnait sur les jetons sombres : la page restait
   claire alors que l'attribut était bien posé. Chaque bloc vise désormais la
   racine **et** le corps.
2. Les pastilles (tailles, marques) avaient un fond `#fafbfc` écrit en dur, qui
   restait blanc en sombre avec du texte clair par-dessus. Nouveau jeton
   `--puce`.

Contrôlé par mesure, pas à l'œil : un script parcourt chaque élément visible de
la page et compare la luminance du fond à celle du texte. Dix éléments
illisibles avant correction (le rail des marques), **zéro après**, sur la fiche
et sur une page de catégorie.

---

## L'affiche d'accueil

Les tuiles de rayon sont retirées : les rayons figurent déjà dans le rail sous
l'en-tête **et** dans le menu. Trois fois la même liste sur un écran de
téléphone, c'est deux de trop.

À leur place, une affiche dans l'esprit des « opérations » des marchands (Dafy
et son *OPÉRATION FLASH*) — avec la différence qui est tout l'argument du site :
**leur promotion est décidée par eux, la nôtre est un constat.** Le casque
nommé, ses deux prix et l'écart entre les deux sont relus dans la base à chaque
affichage (`queries.affiche`). Au moment de l'écriture : Schuberth C5 Carbon
Glossy, 1 019,32 EUR ici, 1 499,00 EUR ailleurs, **479,68 EUR d'écart** chez
trois marchands.

Mêmes deux garde-fous que la rangée des écarts, pour les mêmes raisons : pas
au-delà d'un facteur deux (ce serait une fusion ratée, pas une affaire), et
trois marchands plutôt que deux — l'affirmation est plus difficile à balayer.

**Dessinée en CSS et en SVG, pas exportée en image.** Une image d'affiche
pèserait quelques centaines de kilo-octets, serait floue sur un écran dense, et
le jour où le texte change il faudrait la refaire. Ici les traits de vitesse et
les étincelles sont du SVG, le relief des lettres un décalage ambre en
`text-shadow`, et le texte est du vrai texte — lisible par un moteur de
recherche et par un lecteur d'écran.

### Deux défauts corrigés en vérifiant

1. **Collision de noms, à nouveau.** La phrase d'accroche utilisait `.bandeau`,
   classe déjà prise par un bandeau bleu nuit : le texte sortait bleu foncé sur
   bleu foncé, visible sur la capture de la propriétaire. Disparue avec les
   tuiles, mais c'est la deuxième collision de la soirée (après `.tuile`) —
   les noms de classe de ce fichier méritent un préfixe.
2. **La photo fantôme passait derrière le relevé de prix** sur mobile et rendait
   le prix barré illisible. Elle descend dans le coin bas droit, et le relevé
   prend un fond opaque : c'est le seul endroit chiffré de l'affiche.

Contrôle de lisibilité repassé sur les deux thèmes : **zéro élément illisible**.
Un faux positif relevé au passage, `.rail`, qui a un fond nuit mais héritait
d'une couleur de texte sombre — aucun texte direct dedans aujourd'hui, donc rien
de cassé, mais le premier mot qu'on y ajouterait aurait été invisible. Fermé.

---

## L'affiche fournie, pleine largeur

L'affiche est maintenant l'image fournie par la propriétaire
(`static/affiche-accueil.jpg`), en pleine largeur, cliquable vers **`/produits`**
— nouvelle route qui liste le catalogue entier, filtres prix / marchands /
marques / catégories actifs. Le listing de catégorie sans catégorie fixée : le
visiteur part de tout le rayon et réduit, au lieu de devoir choisir un
département avant de voir quoi que ce soit.

### Pleine largeur, proprement

Elle est posée dans un bloc `pleine_largeur` **hors de `.conteneur`**, plutôt
que par l'astuce habituelle `width: 100vw; margin-left: 50%`. Raison : sur un
écran d'ordinateur, `100vw` compte la barre de défilement, et la page déborde
de quelques pixels vers la droite — un défaut qu'on ne voit jamais sur le poste
où on l'écrit.

### Ce que la mesure a dit sur la qualité

L'image fait **1 139 × 1 503**. Sur un téléphone, la bannière occupe 375 points
de large × 3 pixels par point = **1 125 pixels nécessaires**. On est à 1,01× le
minimum : aucune marge, et c'est pour cela qu'elle paraît molle. Ce n'est pas
l'affichage qui la dégrade, c'est le fichier qui n'a pas plus de détail.
Agrandir n'ajouterait rien — seulement du flou, en plus lourd.

**Ce qu'il faudrait :**

| | dimensions | pourquoi |
|---|---|---|
| Version portrait (téléphone) | **1 200 × 1 600** | 375 pt × 3 = 1 125 px, plus la marge |
| Version paysage (ordinateur) | **2 560 × 1 100** | pleine largeur sur écran dense |

### Le cadrage sur ordinateur, corrigé

Premier essai en 21/9 : le cadre coupait les deux premières lignes, on ne lisait
plus que « MOTO ». Le cadre s'allonge (`min(660px, 52vw)`) et le cadrage remonte
(`object-position: center 7%`) pour garder les trois lignes.

C'est un pis-aller assumé : **une affiche portrait ne peut pas remplir un écran
d'ordinateur sans qu'on lui coupe quelque chose.** Le vrai remède est une
deuxième image en paysage, servie au-dessus de 900 px.

### Poids

877 Ko. Sur un téléphone en 4G, une à deux secondes avant que la page soit
présentable. À compresser dès qu'une version de meilleure définition arrive :
150 à 200 Ko sont atteignables sans perte visible.

### L'accueil dégagée

Trois retraits demandés, tous pour la même raison : ce qui se trouve entre
l'en-tête et l'affiche repousse l'affiche sous la ligne de flottaison.

- **Le rail des catégories** et **le rail des marques** ne s'affichent plus sur
  l'accueil — `request.url.path != "/"` — et restent partout ailleurs, où ils
  servent à naviguer depuis une page de contenu. Les deux restent dans le menu,
  intact, qui est l'endroit où on va les chercher quand on les veut.
- **« 100 % gratuit, sans inscription »** quitte la ligne de confiance, qui
  garde les deux mentions vérifiables : la fraîcheur des prix et le nombre de
  marchands. L'information n'est pas perdue, elle est dite là où elle se
  démontre — page « À propos » et questions fréquentes.

L'affiche est désormais le premier élément sous l'en-tête, entièrement visible
sans défiler.


### L'affiche, version finale

Fichiers en place : `affiche-portrait.webp` (1 086 × 1 448, **134 Ko**) servi via
`<picture>`, et `affiche-portrait.jpg` (246 Ko) en secours pour les navigateurs
sans WebP. L'ancienne pesait **877 Ko** et portait les artefacts de plusieurs
réenregistrements successifs : six fois et demie plus légère, et plus propre.

**Le calcul qui a évité une fausse bonne idée.** Une première optimisation
proposait `banner-800.webp` (800 × 1066) et `banner-480.webp` servi aux mobiles
sous `media="(max-width: 600px)"`. Le format était juste, les dimensions non :
un téléphone de 375 points de large affiche **3 pixels par point**, soit 1 125
pixels réels. Le fichier de 800 aurait été étiré ×1,4 et celui de 480 ×2,3 —
plus flou que l'original qu'on cherchait à améliorer.

C'est le piège classique de `media` en largeur CSS : il raisonne en points et
ignore la densité de l'écran. La conversion a donc été refaite **à la taille
native, sans redimensionner** : changement de format seul, aucun pixel perdu.

Mesuré en place : le WebP est bien celui qui est servi, 1 086 pixels disponibles
pour 1 125 nécessaires sur un écran 3×, soit 3 % sous l'idéal — imperceptible,
là où le fichier précédent était à 29 % au-dessus du nécessaire en poids pour
une définition à peine meilleure.

**Reste ouvert** : la version paysage pour les écrans larges. Tant qu'elle
n'existe pas, le cadrage sur ordinateur garde le titre et coupe le bas de
l'affiche — un pis-aller assumé, pas une solution.

### L'en-tête, sur deux lignes

Disposition relevée chez Speedway, à la demande de la propriétaire :

```
  [ logo MotoComparo ]                          [ ⇄ ]  [ ♡ ]
  [ ☰ ]  [ Rechercher casques, blousons, gants, bottes…        ]
```

Le gain n'est pas décoratif. Sur un téléphone, la recherche coincée entre le
logo et les icônes faisait **140 px utiles** ; sur sa propre ligne à côté du
menu, elle en fait plus du double et le texte d'invite tient enfin en entier.

Sur écran large tout revient sur une seule ligne — logo, menu, recherche
étirée, raccourcis. Réalisé avec `display: contents` sur les deux boîtes de
regroupement : elles s'effacent, leurs enfants deviennent enfants directs de
l'en-tête, et `order` peut alors les replacer. Premier essai sans cela : la
règle ne faisait rien, les raccourcis n'étant pas dans le même conteneur que la
recherche. Vérifié en place à 1 280 px — logo 63, menu 279, recherche 343→1 083,
raccourcis 1 101, aucun débordement.

### Le thème sombre retiré en entier

Le bouton de bascule est retiré à la demande de la propriétaire. Premier
réflexe : garder `prefers-color-scheme` pour que le site suive le réglage du
système. **Erreur, et elle s'est vue tout de suite** — son téléphone est réglé
en sombre, donc le site s'affichait en sombre, et sans bouton il n'y avait plus
aucun moyen d'en sortir.

Suivre le réglage du système n'a de sens que si l'on garde une porte de sortie.
Sans bouton, c'est une décision prise à la place du visiteur. Les jetons sombres
sont donc supprimés, pas laissés inertes : une règle qui ne s'applique jamais
finit par s'appliquer un jour, au pire moment. L'historique les conserve si le
thème revient un jour avec son bouton.

Une ligne de plus, qui n'a rien d'évident : `color-scheme: light` sur `:root`.
Sans elle, le navigateur d'un appareil en mode sombre repeint de lui-même ce
qu'il contrôle — champs de saisie, listes déroulantes, barres de défilement — et
on obtient un champ de recherche noir au milieu d'une page claire. Vérifié en
émulant un système en sombre : fond de page clair, champ de recherche blanc,
cartes blanches.

### Un seul haut de page sur tout le site

Les deux rails — catégories et marques — étaient retirés de l'accueil seulement.
Ils le sont maintenant **partout** : le haut du site doit être le même d'un bout
à l'autre, sinon chaque page a l'air d'appartenir à un autre site.

Ce qui coiffe désormais toutes les pages : la ligne de confiance, puis la marque
avec ses deux raccourcis, puis le menu et la recherche. Rien d'autre. Les rayons
et les marques vivent dans le menu, qui est fait pour ça.

### Le bouton Filtrer, mécanisme de la v1

Remplacé : la barre « ☰ Filtres » posée en haut de liste, qu'on voyait une fois
au début et plus jamais ensuite — il fallait remonter toute la page pour changer
un filtre.

Repris de la v1 : une **pastille flottante en bas d'écran**, fixe, et un panneau
qui **monte depuis le bas**. Le pouce est en bas du téléphone ; c'est là que le
bouton doit être, et c'est de là que le panneau doit venir.

Le panneau s'arrête à 114 px du haut plutôt que de couvrir l'écran : la bande de
liste qui reste visible dit au visiteur qu'il est toujours sur sa page. En-tête
« Filtres » avec une croix, pastille « N produits », puis prix, marchands,
marques et catégories.

Deux détails qui ne se voient que sur un vrai téléphone :
`bottom: calc(18px + env(safe-area-inset-bottom))` place la pastille au-dessus
de la barre de gestes, et `padding-bottom` sur la liste empêche la pastille de
masquer le dernier produit.

Le même composant `.tiroir` sert le menu (qui entre par la gauche) et les
filtres (qui montent du bas) : une seule mécanique d'ouverture, deux habillages.

### Les catégories avaient disparu des filtres

Le HTML était pourtant bien produit. La cause était la mise en page : `.tiroir`
est une **colonne flexible**, et le panneau du bas a une hauteur maximale — ses
sections se faisaient donc comprimer pour y tenir, et la dernière, les
catégories, disparaissait purement et simplement.

Le panneau passe en bloc qui défile (`display: block; overflow-y: auto`) : chaque
section garde sa taille et on descend jusqu'en bas. Plus deux détails :
`overscroll-behavior: contain` pour que le défilement ne fuie pas sur la page
derrière, et un en-tête collant pour garder « Filtres » et sa croix visibles
pendant qu'on parcourt la liste.

Vérifié : quatre sections (prix, marchands, marques, catégories), 1 704 px de
contenu dans 698 px visibles, et les sous-catégories s'ouvrent sous leur mère —
sur « Casques », on trouve bien intégraux 1 556, jet 663, cross 480, modulables
468.

### Les filtres, réordonnés et complétés

Ordre demandé, et il suit une logique : on choisit d'abord **ce** qu'on cherche,
puis ce qui le restreint.

1. **Catégories** et sous-catégories
2. **Marques**
3. **Prix** — une jauge de 0 au prix le plus élevé
4. **Taille** (nouveau)
5. **Couleur** (nouveau)
6. **Marchands** — en dernier : c'est une exigence sur la comparaison, pas sur
   le produit

**Les filtres en cours sont en haut**, chacun avec sa croix, plus « Tout
effacer ». C'est le seul endroit d'où l'on voit d'un coup d'œil pourquoi une
liste est si courte, et le seul d'où l'on défait une sélection sans rouvrir la
section où on l'avait prise. Vérifié : retirer la marque garde le prix et la
taille — chaque croix ne défait que son propre filtre.

La jauge remplace les cinq tranches fixes : ses bornes sont celles du rayon
affiché. Proposer « 400 € et + » sur un rayon de gants n'aidait personne.

#### Ce que le remaniement a permis de corriger au passage

Les filtres voyageaient en **huit arguments positionnels** répétés dans trois
routes — une inversion entre deux d'entre eux n'aurait produit aucune erreur,
juste une mauvaise liste. Ils tiennent maintenant dans un objet `Filtres`, et
les trois listings (un rayon, une marque, tout le catalogue) partagent une seule
fonction : ils ne différaient que par leur titre, leur URL et le filtre fixé, et
le reste avait déjà divergé une fois.

**Chaque facette est comptée avec son propre critère levé.** Compter les marques
alors qu'une marque est déjà choisie répondrait « 1 marque, 40 produits » — vrai
et inutile. En le levant, la réponse devient « si vous passiez à Shoei, vous
auriez 312 », qui est la question que le visiteur se pose en ouvrant la liste.

### Un seul bouton de tri

Les quatre bulles tenaient sur deux lignes au téléphone, poussaient le premier
produit hors de l'écran et affichaient en permanence trois options qu'on ne
prendrait pas. Remplacées par un contrôle unique — « Trier par : Pertinence » —
qui se déplie.

Bâti sur `<details>` plutôt que sur un menu natif : il prend les couleurs du
site, se ferme avec Échap, et ne demande pas une ligne de script. Et sa forme est
celle de MotoComparo — fond nuit, valeur en ambre — pas le rectangle gris du
modèle de départ.

### La recherche devient une liste comme les autres

Elle n'avait pas de bouton Filtrer, parce qu'elle n'était pas un listing : pas
de panneau, pas de compteurs, pas de tri. Chercher « Arai sz » rendait vingt-six
casques et ne laissait rien pour les réduire.

Les mots tapés sont maintenant **un filtre comme les autres** : ils entrent dans
la même clause `WHERE`, apparaissent en premier parmi les filtres actifs
(« « Arai sz » ✕ »), et survivent à chaque clic dans le panneau. La recherche
hérite du coup du panneau complet, des compteurs et du tri, sans une ligne de
code en plus.

Un ET et non un OU entre les mots : « arai sz » ne doit pas ramener tout Arai.

#### Le piège que l'objet devait éviter, et que j'ai déclenché

`texte` a été inséré **en deuxième position** de `Filtres`, alors que les routes
passaient encore leurs filtres dans l'ordre. La marque atterrissait donc dans le
champ texte : trois listings sont tombés en erreur d'un coup — et c'est une
chance, car un décalage entre deux champs du même type aurait rendu des
résultats faux, sans rien signaler.

Corrigé à la racine plutôt qu'au cas par cas : `Filtres` est désormais
`kw_only`. Un champ peut être ajouté n'importe où sans toucher un seul appelant,
et passer un filtre par rang ne compile plus.

### La fiche alignée sur la v1, aux valeurs mesurées

La propriétaire trouvait la v2 « fausse ». Relevé sur les deux pages plutôt
qu'estimé à l'œil : **la palette était déjà identique** (`#0f1524`, `#f5b301`,
`#f7f8fa`). L'écart était ailleurs.

**Le bloc « Meilleur prix » : un dégradé, pas un aplat.** La v1 va de `#141a2b`
à `#26355a` en 135° ; le nôtre était un aplat sombre, d'où l'impression d'un
rectangle collé sur la page. C'est la différence qui sautait aux yeux entre les
deux captures.

Valeurs relevées et appliquées :

| | v1 | v2 avant | v2 après |
|---|---|---|---|
| Fond du bloc | dégradé `#141a2b`→`#26355a` | aplat `#0f1524` | ✅ |
| Titre produit | 21 px / 800 | 28 px / 700 | ✅ |
| Prix | 29 px | 32–38 px | ✅ |
| « chez X » | 13 px, normal | 16 px, italique | ✅ |
| Bouton | rayon 10 px, 15 px, halo ambre | pilule 24 px, 13,5 px | ✅ |
| Rond comparateur | blanc cerclé d'ambre | disque ambre plein | ✅ |
| Libellé « Meilleur prix » | 11 px, interlettrage 1,2 px | — | ✅ |

#### Trois valeurs que le premier passage n'a pas prises

Elles étaient écrasées par des règles **plus précises** situées ailleurs :
`.theme-v1 .fiche__tete h1` battait `.fiche__tete h1`, `.theme-v1 .bouton`
battait `.meilleur__voir`, et une requête `max-width: 640px` remettait le prix à
32 px — précisément à la largeur où la v1 le mesure à 29.

Corrigé en modifiant les règles d'origine plutôt qu'en empilant une définition
de plus : une seule vérité par valeur. Le symptôme est instructif — à écrire une
feuille de style par ajouts successifs, on finit par ne plus savoir laquelle
gagne.

### Les blocs de contenu ajoutés

- **A** « Vous économisez jusqu'à 130,89 € » — bandeau vert, calculé sur les
  offres vivantes
- **B** « Comparer les 3 offres · Mis à jour le 13/09/2026 à 16:43 »
- **C** offres numérotées 1, 2, 3 avec la pastille « Meilleur prix » sur la
  première
- **D** les mentions sur les prix et la commission
- **E** les quatre garanties avec leur sous-titre (Prix vérifiés / Marchands
  français / Aucun surcoût / Sans inscription)

Restent les lots validés mais non faits : **G** les produits associés, et **F**
les codes promo, qui demandent une table et une saisie dans le tableau de bord.

**Bug corrigé au passage** : « ↔ voir cette fiche dans l'autre design » pointait
encore vers les routes `/v1/` supprimées.

### La fiche redensifiée

La propriétaire comparait les deux captures : « on dirait une version Wish ».
L'écart ne portait plus sur les couleurs, désormais identiques, mais sur la
**densité**. La v1 met en deux colonnes ce que nous empilions ; elle tient en un
écran là où nous en prenions trois.

Quatre empilements rattrapés :

1. **Le visuel reste à gauche sur téléphone.** La v1 garde ses deux colonnes à
   375 px. Empilé, le casque prenait toute la largeur et repoussait le prix —
   l'information principale — sous la ligne de flottaison.
2. **Le bloc prix sur une rangée** : prix à gauche, rond et bouton à droite.
   Chez la v1 il fait 164 px de haut ; le nôtre en faisait plus du double.
3. **Les quatre garanties en 2 × 2** au lieu de quatre lignes.
4. **L'en-tête du tableau des offres disparaît sur mobile.** « MARCHAND /
   TAILLE / DISPONIBILITÉ / PRIX » en capitales grises faisait tableur ; la v1
   n'a pas d'en-tête et pose l'information dans la ligne.

Et un signal ajouté : **seule la meilleure offre porte un bouton plein**, les
suivantes sont en contour. Quand tous les boutons crient aussi fort, aucun ne
dit lequel est le moins cher — c'est pourtant la seule chose que la page ait à
dire.

#### Trois essais avant que la grille tienne

Instructif, parce que chaque échec avait une cause précise et invisible :

- `@media (max-width: 380px)` pour empiler : un téléphone courant fait **375**,
  il tombait donc du mauvais côté et s'empilait quand même. Descendu à 340.
- `minmax(120px, 38%)` pour la colonne image : elle s'est effondrée à 120 px,
  la colonne de droite réclamant toute la place.
- `44% 1fr` : la colonne de droite **refuse de descendre sous la largeur
  minimale de son contenu** — comportement par défaut des grilles — et écrasait
  l'image à 69 px. Il faut `minmax(0, 1fr)` et `min-width: 0` sur les enfants.

La forme finale sépare les rôles : image et identité côte à côte en haut, tout
le reste en pleine largeur dessous. À 375 px, une colonne de droite fait 160 px,
où le prix, l'économie et les garanties partaient chacun sur quatre lignes.

### Produits associés

`queries.similaires()` — mêmes critères que la v1, dans cet ordre : la marque,
puis l'écart de prix relatif, puis le nombre de marchands. Même département
exigé, jamais la seule marque : Arai fabrique aussi des visières, et en proposer
une sous un casque se lit comme une erreur.

Une ligne par **modèle** et non par coloris : le même casque cross en deux
couleurs occupait deux cases côte à côte, ce qui gâche deux des six places et se
lit comme un défaut.
