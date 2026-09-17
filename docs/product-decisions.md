# Product decisions

Business rules that the code must honour but could never derive on its own.
Answers from the site owner, who sells this gear — recorded verbatim in intent,
so a later reader does not "fix" one of them by mistake. Each entry says what it
changes in the pipeline.

Last updated: 2026-09-12.

## Identity — what makes two listings the same product

**Matte and gloss are different products.** A buyer treats a matte black helmet
and a gloss black one as two different items, not one item in two finishes.
→ `textnorm._COLOUR_FINISH` keeping MAT/GLO apart is correct. Do not merge them.

**Model year does NOT define a product.** The same helmet ships for years with no
change; the barcode is what identifies it, and the buyer takes the cheapest. The
ECE 22.06 rule already removed the genuinely obsolete stock from sale, so an old
year is not a hazard.
→ `model_year` is currently a gated field in `match`, so a 2023 and a 2026
edition stay separate. That contradicts this rule and is likely the largest
single lever left for comparability. **Not changed yet**: the year gate was
itself the fix for a real bug (two Leatt GTINs, 2023 and 2026, collapsing onto
one product — see roadmap). Needs its own measured pass before touching.

**Leg-length fits (standard / long / court) are not real product variants.**
Rarely used in practice for trousers.
→ `textnorm` dropping them from the model name is correct. No change.

## Colour

**Read the real colour, not the tint word.** "Écran fumé gris" → grey.
"Visière iridium bleu" → blue. The tint word (fumé, iridium, transparent) only
names the colour when no real colour is present in the title.
→ Tint words may only ever be a LAST RESORT in `textnorm.colour`, never used
when a known colour was already found. Measured: ignoring this rule breaks ~31%
of the barcode groups it touches, because these words sit *alongside* a colour.

**"Clair" is not a colour.** In visor vocabulary the trade says *transparent*,
not *clair*; and 82% of titles containing "clair" use it as a shade of another
colour ("bleu clair", "fumé clair").
→ Stays in `_STOP`. Never add it as a colour word.

## Catalogue and display (phase 3)

**Single-merchant products are published, but kept out of site navigation.**
Reachable by direct URL only. This earns the SEO without putting a page that
cannot compare anything in front of a browsing visitor — and the day a second
merchant lists the item, it joins the navigation on its own.
→ `publish` needs a per-product "indexable but unlisted" state, not a filter
that drops them. ~220,000 of ~244,000 products are in this case.

**A price older than 24 hours is not shown.** Sending a buyer to a price that no
longer exists is the worst failure a comparison site can have.
→ That is the freshness window for `freshness`.

**Out-of-stock offers stay visible, marked "rupture de stock". Nothing is ever
removed from the site** — removing pages damages SEO.
→ `publish` must never delete a product page; stock is a displayed state.

**Shipping is researched per merchant and computed, but the displayed price
excludes it.** Both figures are kept: total delivered price, and price before
shipping. Preference is to display the price before shipping.
→ Needs a per-merchant shipping-terms table; not in the feeds.

**Sizes display as the plain letter: "S", never "S 55/56".** Head-circumference
numbers mean nothing to a buyer.
→ Display-side normalisation; `size_code` may keep the richer value internally
(FC-Moto ships "S5556"), but the site shows the letter.

**Cross and adventure/trail belong together for the buyer.** Someone shopping
for a cross helmet wants trail/adventure helmets in the same results — same
spirit. This is a *browsing* rule, not a matching rule: merchants disagree on
the label (FC-Moto titles them "enduro/cross", everyone else says integral), and
`enrich` deliberately follows the neighbours so the item still merges.
→ The site's "cross" listing must also draw in adventure/trail helmets. No
change to matching.

## Commercial priority

Where quality effort goes, in order:

1. **Helmets**
2. **Jackets**
3. **Gloves**
4. **Boots**
5. Parts — last.

## Competitor study (2026-09-12) — what a product page is

Checked against two merchants and one comparison site, because the two do not
model the catalogue the same way and only one of them is our business.

**Dafy-Moto and Motoblouz — merchants — put one page per MODEL.** Colour and
size are both selectors; the URL does not change when you switch colour
(Motoblouz's RPHA 12 keeps the same page and the same reference HJ1093 across
grey, titanium, blue/black, metallic blue). Comfortable for a shop that owns its
own stock.

**idealo — a comparison site — puts one page per COLOURWAY**, which is what v2
does. Their page is titled "HJC RPHA 12 Solid black"; the colour is part of the
product name and appears again as an attribute ("Couleur: Noir").

The difference is not taste, it is the job. A merchant sells its own stock, so
grouping colourways is convenient. A comparison site puts several merchants side
by side on *the same article* — if colour were only a selector, the page would
be comparing one merchant's grey against another's blue and the price would mean
nothing. Measured on our own data: the RPHA 12 titanium semi-matte is 328,27 € at
Speedway, 390,90 € at Motoblouz, 459,90 € at FC-Moto. That comparison is only
honest because colour defines the page.

**→ Keep colour in the product identity. Do not follow the merchants here.**

### What idealo's page contains, and how it maps to what we have

| idealo | us |
|---|---|
| Colour in the product name + as an attribute | `product.colour_code`, already there |
| Size as a filter, one offer row per size | `variant` + `offer_variant_link`, already there |
| Price history graph (3 months / 6 months / 1 year) | `price_history`, first 763,550 rows written 2026-09-12 |
| A **Prix / Prix total** toggle (before / including shipping) | not built — needs a per-merchant shipping table, the feeds do not carry it |
| Offer name carries the size ("…Noir Metal **M**") | we have `size_code` per offer |
| "Ce produit peut contenir des offres en différentes tailles" — an honest caveat | worth reusing verbatim |
| Price alert (email) | out of scope, needs accounts |

Three things worth copying: the size inside each offer's name, that honest
caveat sentence, and offering the shipping toggle rather than imposing one view
(the owner's preference stays "before shipping" as the default).

### Scope for the first shadow publish (decided 2026-09-12)

Publish with what the pipeline already holds; look at the result; enrich after.
The point of shadow mode is to decide on the evidence, not in advance.

- **Shipping is deferred.** No feed carries it, so it needs a hand-maintained
  per-merchant table (free-shipping threshold, weight or basket bands) that
  someone has to keep current. Worth doing, not worth delaying the first look.
  Until then the site shows the product price only, which is the owner's
  preferred default anyway.
- **Offer display name: ours, with the merchant's title kept underneath.**
  idealo shows the raw merchant title — honest but redundant ("Casque HJC RPHA
  12 Uni Métal Noir - Casque Intégral HJC Noir Metal M"). We have the parts to
  write a clean one ("HJC RPHA 12 — Titane mat — Taille M") and the raw title
  stays visible in smaller type, so nothing is hidden from the buyer.
- **Product attributes: only what we actually have** — type, colour, sizes,
  gender. Materials and weight are not in any feed; extracting them from
  descriptions is its own project and is not a prerequisite to looking at the
  catalogue.

## 2026-09-17 — La ligne d'offre sur mobile : le rôle plutôt que le rang

Sur mobile, le tableau des offres s'empile en carte. La mise en page était calée
sur la POSITION des cellules (`td:nth-child(2)`, `(3)`, `(4)`…). Or la colonne
des tailles n'existe que sur les fiches qui en ont une : dès qu'elle manquait,
tout se décalait d'un cran — le libellé « taille » se posait sur la
disponibilité (« taille en stock »), le prix passait en petit dans le coin et le
bouton prenait la ligne du prix. Les cellules portent désormais un nom
(`offres__marchand`, `offres__taille`, `offres__dispo`, `offres__prix`,
`offres__action`) et la mise en page vise ces noms. Un nom ne se décale pas.

Deux conséquences voulues :

- **Le libellé « taille » ne s'écrit plus quand il n'y a pas de taille.** Une
  cellule qui ne porte que le repère « i » n'annonce rien : « taille » suivi de
  rien n'apprend rien à personne.
- **Nouvelle ligne de décision** (demande du 17/09) : le prix en gros à gauche,
  la taille et le stock en pastilles à hauteur du prix, le bouton en pleine
  largeur dessous. C'est une seule réponse — à combien, en quelle taille, et
  est-ce disponible — et elle se lit maintenant d'un seul regard au lieu de
  trois lignes à recomposer soi-même.

### Le trait qui sépare deux offres (17/09, suite)

Retour de la propriétaire : « les tirets se ressemblent, on ne distingue plus
les offres ». Constat : le trait **entre deux offres** (`--line`, `#e3e6ec`,
1 px) et le filet **interne** sous le nom du marchand (`--ligne-carte`,
`#e8eaf1`, 1 px) avaient la même épaisseur et presque la même teinte. Deux
traits identiques pour deux rôles opposés : l'un est une frontière, l'autre une
simple ponctuation. L'œil ne pouvait pas les départager.

Corrigé en leur donnant des rôles visibles :

- nouveau jeton `--ligne-offre: #c7cedc`, nettement plus foncé que `--line` ;
- sur mobile, la frontière entre deux offres passe à **2 px** de cette teinte ;
- sur grand écran elle reste à 1 px mais prend la teinte foncée (le tableau a
  déjà ses colonnes pour structurer, l'épaisseur y serait lourde) ;
- le filet interne s'éclaircit à `#eef1f6`.

### Distinguer les offres : la structure, pas la couleur (17/09)

Trois essais successifs pour séparer les offres — trait plus épais, une ligne
sur deux en gris, puis en bleu, puis en bandeau sur le seul nom du marchand —
tous rejetés par la propriétaire, le dernier qualifié de « catastrophique ».
Ils avaient un défaut commun : ils coloriaient le **fond** pour suggérer une
frontière, alors que le problème était qu'une offre ne se lisait pas comme un
**objet**. On ne répare pas un manque de structure avec une teinte.

Design retenu, sur mobile : le tableau devient un fond clair (`#eef1f7`) et
chaque offre une **carte blanche détachée** — quatre bords à elle, coins
arrondis 12 px, ombre légère, 10 px de vide entre deux cartes. Il n'y a plus
rien à faire croire : il y a réellement du vide entre deux offres.

La meilleure offre garde son fond ambre pâle et prend en plus un **bord ambre**.
Maintenant que chaque offre a un bord, le seul qui soit coloré se voit avant
qu'on ait lu quoi que ce soit — c'est devenu le signal principal, l'ombre
ambrée n'étant qu'un renfort.

La classe `est-paire` reste posée par le gabarit et tenue à jour par le script
(elle suit les lignes visibles, pas celles du HTML) au cas où une alternance
redevienne utile ; plus aucune règle ne s'y accroche.

**Reste à trancher :** en grand écran, les offres restent un vrai tableau, avec
le seul trait de séparation foncé (`--ligne-offre`, `#c7cedc`). Les colonnes y
structurent déjà la lecture ; à valider sur écran large avant publication.

## 2026-09-17 — Étagères qui bouclent, et ce que la fiche déclare aux moteurs

### Les suggestions défilent sans fin, sans charger quoi que ce soit

Demande : « scroll illimité avec un nombre de produits limités ». La sélection
reste celle qu'on a choisie — six suggestions de la même marque, huit dans la
même gamme de prix — mais l'étagère ne bute plus sur un bord.

Mécanique (`static/etagere.js`, partagée par `.proches__grille` et
`.rayon__piste` : une seule mécanique dans le site, pas deux qui divergeraient).
On duplique la série ; quand le défilement a parcouru une série entière, on le
ramène en arrière d'exactement cette longueur. Les pixels sous le doigt sont
identiques avant et après le saut : c'est un tapis roulant, pas un chargement.

Trois pièges traités :

- **La gouttière du dernier élément.** `scrollWidth` ne la compte pas. Sans
  l'ajouter, chaque tour perdrait 12 px et l'étagère dériverait.
- **Une série plus étroite que l'écran.** Le saut remplacerait alors une portion
  visible par une autre et se verrait. On répète la série jusqu'à couvrir la
  fenêtre avant d'en faire l'unité de bouclage.
- **L'étagère des « déjà vus »** de l'accueil est insérée après le chargement
  (elle est cherchée en JavaScript). Une veille `MutationObserver` la rattrape ;
  sans elle, c'était la seule à ne pas boucler — et c'est la plus regardée.

Les copies sont `aria-hidden`, sorties du parcours clavier et marquées
`data-copie` : un lecteur d'écran ne doit traverser la sélection qu'une fois.

*Non vérifié de mon côté :* le volet du navigateur de travail ne distribue pas
d'événement de défilement quand il est masqué, donc la boucle elle-même n'a pas
pu être éprouvée en machine. À valider au doigt.

### Données structurées (schema.org)

Les fiches n'en avaient aucune. Pour un comparateur c'est le manque le plus
coûteux : avec elles, le résultat Google porte la fourchette de prix, le nombre
de marchands et la disponibilité — la promesse du site, lisible avant le clic.

Deux absences volontaires, toutes deux testées (`tests/test_site_fiche.py`) :

- **Aucune note, aucun avis.** Les cinq étoiles de la fiche disent
  « comparateur indépendant » ; elles ne notent pas le produit. Les déclarer
  comme une note ferait retirer le site des résultats enrichis, à juste titre.
- **Aucun code-barres inventé.** Maxxess et Moto-Axxe reçoivent un GTIN
  synthétique fabriqué par le pipeline ; le publier comme identifiant officiel
  serait une fausse déclaration.

Le prix bas annoncé exclut les articles en rupture — annoncer « à partir de
43 € » sur un article que personne ne peut acheter est exactement le reproche
que le guide du site adresse aux autres.

### `/favicon.ico`

Répondait 404 sous chaque visite : le navigateur réclame cette adresse quoi
qu'on déclare dans l'entête. Redirection permanente vers `favicon.svg`. Un 404
qu'on s'explique est un 404 qu'on finit par ne plus lire, y compris le jour où
il en cache un vrai.

### La passe SEO, vérifiée sur le site qui tourne (17/09)

Tout ce qui suit a été contrôlé sur les pages réellement servies, pas seulement
dans les gabarits.

**Plan du site.** 28 751 adresses en deux fichiers (20 000 + 8 751), index
`/sitemap.xml`, un numéro hors plage renvoie bien 404. Seules les fiches à deux
marchands ou plus y figurent : les 280 000 autres restent accessibles, mais les
proposer à l'indexation noierait celles qui font l'intérêt du site.

**`robots.txt` — un ordre contradictoire retiré.** Les filtres restent fermés
(ils se combinent sans fin et épuisent le budget de parcours). La **pagination**,
elle, a été rouverte : les pages 2 et suivantes portent `noindex, follow`, et
interdire leur parcours rendait cette consigne illisible — un robot à qui on
interdit la page ne peut pas y lire le `noindex`, et le `follow` ne sert plus à
rien. Interdire ET marquer `noindex` sont deux ordres qui s'annulent.

**Canoniques.** `/c/helmet?page=2` et `/c/helmet?marque=SHOEI` renvoient tous
deux au rayon nu, avec `noindex, follow`. Vérifié page par page.

**Descriptions.** Cinq pages — bons plans, marques, guides, à propos, contact —
répétaient mot pour mot la description du site. Chacune a la sienne, toutes
entre 99 et 156 caractères, c'est-à-dire sous la limite d'affichage de Google.

**Données structurées hors fiches.** L'accueil déclare `WebSite` (avec sa
`SearchAction`, qui seule permet un champ de recherche dans le résultat Google)
et `Organization` — ce dernier évite qu'une page de marque passe pour le site
officiel de la marque, confusion facile sur un comparateur. Les rayons et les
pages de marque déclarent leur fil d'Ariane, pointant vers l'adresse SANS
filtre pour ne pas contredire le `canonical`.

Aucun `sameAs` déclaré : des réseaux sociaux vides ou inventés valent moins que
rien.

## 2026-09-17 — Le filtre de taille ne filtrait rien hors habillement

Signalé par la propriétaire : sur la housse Ixon Blanky, filtrer sur la taille L
laissait le même marchand revenir quatre fois.

**Ce qui se passait.** Quatorze offres sur dix-huit s'affichaient « taille non
communiquée », et celles-là restent visibles quelle que soit la taille choisie —
c'est voulu, le marchand vend bien l'article. Mais leur taille était connue :
les quatre marchands portent exactement les mêmes codes-barres que FC-Moto, qui
déclare M, L, XL et 2XL dans son flux, et `borrow_sizes()` avait correctement
relayé ces valeurs.

Ce qui les effaçait est une règle de `match.py`, elle-même bien fondée : hors
des rayons d'habillement, une taille ne compte que si le marchand l'a **déclarée
dans son flux**. Mesuré le 13/09 : les selles portent une taille sur 81 % de
leurs offres et pas une seule n'était déclarée ; un Castrol 10W-50 s'était
retrouvé rangé en « taille EU50 ». Ailleurs qu'en habillement, une taille lue
dans un titre ou une référence ne vaut rien.

**La faille, étroite.** Une taille empruntée par code-barres à un marchand qui
la déclare dans son flux n'est pas une inférence de plus : c'est la même
déclaration, relayée par l'identifiant sur lequel tous les marchands sont
d'accord. La règle la rejetait quand même, parce qu'elle lisait la provenance de
la signature (`xmerchant_gtin`) sans pouvoir savoir d'où venait la valeur chez le
donneur.

**Corrigé** : `offer_size_override.donor_source` (migration 017) retient cette
provenance, et ne vaut `'feed'` que si **tous** les donneurs la déclaraient —
un seul donneur `mpn` suffit à faire retomber la valeur dans les suppositions.
`_SIZE_OF_OFFER` accorde l'exception à ce seul cas.

**Portée, mesurée avant et après** : 1 079 offres sur 325 fiches, toutes
comparables. Après recalcul : 1 062 offres gagnent une taille sur 372 fiches,
**aucune n'en perd**, 2 changent.

### `mcpipe relier-tailles`

Appliquer ce correctif aurait demandé un `match --reset` : cinquante minutes,
site éteint, tout le catalogue reconstruit pour changer une colonne. Or les deux
instructions qui construisent les tailles — `_CREATE_VARIANTS` et
`_LINK_VARIANTS` — ne dépendent que de `raw_offer.product_id`, de la signature
et des tailles empruntées, dont aucune n'est touchée par l'appariement.

La commande rejoue **ces mêmes instructions**, précédées du retrait des liens
devenus faux (sans quoi `ON CONFLICT DO NOTHING` laisserait l'offre rattachée à
deux tailles) et suivies de l'`ANALYZE` de rigueur. **38 secondes.**

### Un piège de mesure, noté parce qu'il a failli me tromper

Ma première simulation annonçait « 20 079 offres dont la taille change » et
donnait à croire qu'un `match` abîmerait le catalogue : les tailles de casques
FC-Moto (`S (55/56)`) devenaient `S5556`. C'était ma simulation qui était
fausse — j'y avais remplacé `_SIZE_OF_OFFER` par un `coalesce` simplifié, alors
que `_CANONICAL_SIZE` replie précisément ces formes en `S`. Refaite en
important l'expression réelle du module : 2 changements, pas 20 079. **Une
simulation qui simplifie ce qu'elle teste ne teste plus rien.**

## 2026-09-17 — Mettre la réduction en avant

Demande de la propriétaire : « je ne mets pas assez en avant la réduction ».
Sous le meilleur prix, la fiche affiche désormais le **prix le plus cher
pratiqué aujourd'hui pour le même article**, barré, et l'écart en pourcentage
dans une pastille dont la couleur dit l'ampleur.

Trois paliers, ses valeurs, définies une seule fois dans
`labels.SEUILS_REMISE` : moins de 20 % sobre, de 20 à 35 % orange, au-delà de
35 % rouge. Le gabarit les rend une première fois et le script de la fiche les
**relit** (`data-seuils`) au lieu de les redéfinir : deux copies de la même
règle finissent par diverger, et c'est la couleur — donc la promesse faite au
visiteur — qui se tromperait. Verrouillé aux bornes exactes par cinq tests.

Répartition mesurée sur le catalogue : 73 % des fiches comparables sont sobres,
20 % oranges, 6 % rouges. La couleur garde donc sa valeur d'alerte : si les
trois quarts du catalogue étaient rouges, elle ne dirait plus rien.

**Un écart corrigé au test.** Le premier jet calculait le pourcentage sur les
seules offres de taille connue. En taille L, la page annonçait donc 43,50 € en
grand, barrait 78,30 € et titrait « −16 % » — trois chiffres dont deux venaient
d'un lot et le troisième d'un autre. Les trois sortent maintenant des lignes
**réellement affichées** sous le bloc : le visiteur peut retrouver les deux
bornes en descendant d'un écran.

**Le prix reste blanc, sans teinte ni contour.** Deux essais le 17/09 — prix
entièrement coloré, puis prix blanc à contour coloré — tous deux écartés par la
propriétaire. La couleur porte le message depuis l'encadré ; le prix, lui, n'a
qu'un travail : se lire. La teinte du palier est définie **une fois** sur le
bloc et lue par l'encadré, sur le bloc et non sur la pastille parce que le
script la remet à jour à chaque choix de taille.

**L'encadré est à angles droits** : arrondi, il ressemblait aux étiquettes
« en stock » du tableau, qui ne sont que des états. Ici c'est un chiffre, et un
chiffre se pose dans un cadre.

**Le premier palier n'est pas noir.** La demande disait « noir normal » ; ce
bloc est sur fond bleu nuit, un noir y serait invisible. Gris clair neutre :
même rôle, présent sans rien crier.

### Sur le prix public conseillé

Ce qui est barré n'est **pas** un PPC : c'est une mesure faite par le site entre
marchands réels. Le choix est autant juridique qu'éditorial — depuis la
directive Omnibus, un prix de référence affiché à côté d'une réduction doit être
le prix le plus bas pratiqué dans les trente jours précédents. Un écart entre
marchands, lui, est un fait vérifiable ligne par ligne dans le tableau juste en
dessous.

Un prix de référence existe pourtant dans les flux, et n'est aujourd'hui pas
lu (mesuré le 17/09 sur les fichiers du jour) :

| marchand | colonne | couverture |
|---|---|---|
| Motoblouz | `crossed price` | 100 % des lignes, supérieur au prix sur 57 % |
| Speedway | `price_norebate` | 100 %, supérieur sur 84 % |
| FC-Moto | `price` (vs `sale_price`) | déjà lu, mais seul le prix payé est gardé |
| La Bécanerie | `price_norebate` | 1,6 % seulement |
| Maxxess, Moto-Axxe | — | aucune |

`crossed_price` est même déjà déclaré dans le schéma NetAffiliation
(`feeds.py`) mais `normalize` ne le lit jamais. L'ajouter demande une colonne
sur `raw_offer`, la lecture dans `normalize`, puis un `load` + `normalize`
complet des six flux (environ 900 Mo). Décision en attente : à quatre marchands
sur six, dont deux à couverture nulle, un « PPC » afficherait un prix barré sur
certaines fiches et rien sur d'autres.
