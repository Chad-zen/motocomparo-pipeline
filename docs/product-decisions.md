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

## 2026-09-17 — Bannières des marchands partenaires

Relevées chez **Effinity** (Speedway, La Bécanerie, Maxxess, Moto-Axxe) et
**Kwanko** (Motoblouz). FC-Moto est chez Webgains, qui ne propose pas de
bannière sur ce programme. Norauto en propose chez Effinity, mais ce n'est pas
un marchand du comparateur : annoncer un marchand qu'on ne compare pas
brouillerait la promesse du site. Écarté.

Toutes en 300×250, un seul format pour un seul emplacement — vérifié image par
image dans un vrai navigateur : les cinq répondent et font bien 300×250.

### Le choix qui demande une décision

Chaque régie fournit un code tout fait : un lien de clic **et** une image servie
par son propre serveur. Cette seconde partie est un pixel de mesure — la régie
voit passer chaque visiteur, sur chaque page, qu'il clique ou non. Kwanko
l'écrit lui-même à côté de son code :

> « En utilisant la version balise simple vous ne bénéficiez pas de la prise en
> charge automatique du consentement de vos visiteurs. L'ensemble des actions
> réalisées seront donc considérées comme non-consenties. »

Or la page « À propos » promet qu'il n'y a aucun cookie ni outil de mesure
d'audience. Employer le code tel quel rendait cette phrase fausse et imposait
une bannière de consentement — que le site n'a pas, et dont l'absence est un
argument.

**Retenu** : on garde le LIEN de suivi — il ne se déclenche qu'au clic,
exactement comme les boutons « Voir l'offre », déjà déclarés — et on prend
l'image **chez le marchand**, à l'adresse que la régie redirige de toute façon.
Une bannière Speedway devient alors, techniquement, une image servie par
Speedway : la même chose qu'une photo de produit, ce que la page déclarait déjà.

Les régies rémunèrent au clic et à la vente sur ces programmes, pas à
l'affichage : le revenu est inchangé. En revanche leurs conditions demandent en
général leur code tel quel — c'est une décision de la propriétaire, pas une
décision technique. `PUB_EMPREINTE_REGIE=1` bascule d'un seul réglage, et cinq
tests tiennent le défaut.

### Où elles sont posées, et où elles ne le sont pas

Sur les **pages de résultats** seulement, après la pagination et **avant** la
mention du classement — la dernière chose que lit le visiteur reste « aucun
marchand ne paie pour sa place », pas une publicité.

**Aucune bannière sur une fiche produit.** C'est là que le visiteur compare ;
une bannière d'un des marchands comparés, à côté du tableau des prix, laisserait
croire que ce marchand a payé son rang. Vérifié par un test.

La mention « PUBLICITÉ » est au-dessus de l'image, pas en dessous et pas en gris
pâle : elle doit être lue avant, pas découverte après. L'emplacement est
volontairement sobre — une publicité qui imite la page qui l'entoure est une
publicité trompeuse, et sur un comparateur c'est la confiance dans le classement
qu'elle détruit.

La rotation se fait dans le navigateur : nginx garde les pages une heure, un
tirage côté serveur figerait un marchand par page pour toute cette durée. Une
seule image part sur le réseau, celle qui est montrée.

La page « À propos » a été mise à jour dans le même mouvement : trois réserves
au lieu de deux, et un paragraphe qui explique en clair pourquoi nos bannières
ne suivent personne tant qu'on ne clique pas.

## 2026-09-17 — Aligner la typographie sur la v1

La propriétaire, captures à l'appui : « la v1 fait plus sérieux », « ce n'est
pas le même dégradé », « reprends-les toutes ». Relevé élément par élément à
1440 px sur les deux fiches en ligne, puis comparé. Tout ce qui suit est une
valeur **mesurée**, pas choisie.

### Ce que la comparaison a révélé

**La v1 compose toute sa fiche dans la police du système** — Segoe UI sous
Windows, San Francisco sur Mac. Source Sans 3 et Roboto n'y servent que le
bandeau et le menu. Nous faisions l'inverse : deux polices de rendu dans le
contenu, la police du système nulle part.

C'est l'écart qui se voit sans pouvoir se nommer. Une police système a des
formes plus fermées et un gris de page plus dense : à taille et graisse égales,
elle paraît plus assise. Une page composée dans la police du lecteur ressemble à
son système ; une page composée dans une police chargée ressemble à un gabarit.

**Le dégradé de l'en-tête allait dans l'autre sens.**

| | v1 | v2 (avant) |
|---|---|---|
| | `#1b2540 → #151d33 55% → #0f1524`, **vertical** | `#141a2b → #26355a`, **135°** |
| effet | s'assombrit vers le bas, le bandeau pèse | s'éclaircit vers le bas, le bandeau flotte |

### Les écarts corrigés, un par un

| élément | v1 | v2 avant |
|---|---|---|
| police de la fiche | système | Roboto / Source Sans 3 |
| prix principal | 34 px | **29 px** |
| « chez X » | blanc | gris-bleu |
| pastille de marque | fond clair `#eef1f9`, encre `#26355a` | **fond navy plein, texte blanc** |
| « Comparateur indépendant » | graisse 600 | 400 |
| garanties | `#4a5168` | noir de texte courant |
| nom du marchand | 15 px / 700 | 14 px |
| « en stock » | 11,5 px / 700, `#1a7f45` | 12 px / 400 |
| rang | 13 px | 12 px |
| bouton d'offre | 14 px / 800 | 13,5 px / 700 |
| logo | 24 px / 900 / −0,5 px, `#ffd000` | 21 px / 800 / −0,21 px, `#f8ca02` |

Deux remarques sur ces valeurs. La pastille de marque en navy plein disputait le
regard au titre : deux blocs sombres à deux centimètres l'un de l'autre, et le
nom du produit cessait d'être ce qu'on lit en premier. Nos jetons portaient
déjà les bonnes couleurs — une règle les écrasait.

Et le logo se trompait sur **trois** paramètres à la fois (taille, graisse,
teinte) : un tel écart ne se lit pas comme « une autre police », il se lit comme
« moins affirmé ». C'est la première chose qu'un visiteur regarde.

### Un défaut trouvé pendant la comparaison

Sur une fiche sans tailles — le top case Shad SH34 — « en stock » passait
**par-dessus** la pastille « Meilleur prix ». Une règle écrite pour combler le
vide laissé par la colonne des tailles s'appliquait au thème v1, où le marchand
occupe déjà toute la première ligne. Sa spécificité l'emportait, il ne suffisait
donc pas de la redéclarer ailleurs : il fallait l'empêcher de s'appliquer là.

## 2026-09-17 — Une barre de recherche qui propose des chemins

Demande : « je veux un outil intelligent, inspire-toi d'idealo et d'Amazon.
Quelqu'un qui tape Arai doit voir les catégories où Arai existe, et pouvoir
ouvrir un entonnoir dans cette même recherche. »

Le principe retenu : on ne devine pas ce que quelqu'un cherche, on lui montre
**ce qui existe**. Taper « arai » ne renvoie pas 147 produits en vrac — ça
répond :

```
ARAI, PAR RAYON
   Casques intégraux            94
   Casques cross                15
   Casques jet                  14
   Casques                      12
   Électronique & connectique   12
PRODUITS
   ARAI  Casque intégral Arai QUANTIC FROST      dès 567,34 €
   …
   Voir tous les résultats pour « arai »
```

Chaque ligne de l'entonnoir mène à `/c/<rayon>?marque=<marque>` : la marque ET
le rayon, en un clic, sans quitter la recherche. Vérifié lien par lien — cross
15, jet 14, électronique 12, exactement les nombres annoncés.

### Ce qui rend la chose tenable sur un VPS à un cœur

La ventilation marque × rayon est **précalculée et gardée en mémoire** : 711
lignes, 217 marques, 70 Ko, 157 ms une fois par jour. Tout le filtrage se fait
ensuite en Python, donc en zéro milliseconde.

L'alternative — une requête par frappe — coûtait **130 ms de balayage à chaque
lettre**, parce que `f_unaccent(brand_code)` interdit l'index et force un
parcours des 313 000 fiches. Taper « alpinestars » aurait lancé douze balayages
complets. Mesuré avant d'écrire une ligne d'interface.

Les produits, eux, ne peuvent pas se précalculer : ils viennent de la base,
servis par l'index de trigrammes posé le 14/09, et mis en cache par texte tapé.
Réponses observées : 3 à 120 ms après la première frappe.

### La recherche se fait MOT À MOT

Une seule condition sur la chaîne entière ne trouvait rien pour « ixon bl » :
`model_display` est un sac de jetons trié alphabétiquement, si bien que « Ixon
Blanky » y devient « Blanky ixon » et que la marque ne précède jamais le
modèle. Chaque mot devient sa propre condition — l'ordre cesse de compter, et
l'index sert chacune d'elles.

### Trois règles de classement, et pourquoi

- **L'entonnoir passe avant tout le reste.** C'est la proposition qui fait
  gagner le plus de temps : elle répond à la fois « quelle marque » et « quel
  rayon ». Sous la liste des produits, elle serait invisible.
- **Les rayons vont du plus fourni au moins fourni.** Un entonnoir qui commence
  par le rayon le plus maigre fait perdre le temps qu'il est censé faire gagner.
- **Le début du mot pèse plus que le milieu.** « ara » cherche Arai, pas
  Marauder. Les deux sont proposés, dans cet ordre — et l'entonnoir ne s'ouvre
  QUE sur une correspondance de début : l'ouvrir sur une marque qu'on ne fait
  que traverser supposerait qu'on la cherchait.

### Ce qui ne se voit pas

Trois choses comptent plus que l'affichage, et aucune ne se remarque quand elle
marche :

1. **On attend que la frappe se calme** (160 ms). Sans cela « alpinestars »
   lance onze requêtes dont dix sont périmées avant d'arriver.
2. **La requête précédente est annulée.** Sinon la réponse de « ara » peut
   arriver APRÈS celle de « arai » et réécrire la liste avec des résultats plus
   anciens — un défaut qui n'apparaît qu'en connexion lente, c'est-à-dire chez
   les visiteurs qu'on sert déjà le plus mal.
3. **Tout se fait au clavier** (flèches, Entrée, Échap), avec le motif
   `combobox` complet. Une liste qu'on ne peut parcourir qu'à la souris n'existe
   pas pour une partie des visiteurs.

### Les vignettes

Signalé par la propriétaire : la liste montrait des noms sans images. Sur un
comparateur d'équipement, l'image fait autant que le texte — « Casque intégral
Arai CONCEPT-XE » ne dit ni la couleur ni la forme, et trois lignes du même
modèle se ressemblent toutes tant qu'on ne les voit pas.

Un carré fixe de 42 px, fond clair, `object-fit: contain`. Fixe, parce que les
photos des marchands n'ont ni la même taille ni le même cadrage : sans cadre,
chaque ligne prendrait une hauteur différente et la liste cesserait d'être
balayable. `contain` et non `cover`, parce que recadrer un casque détouré coupe
la mentonnière ou la visière — c'est-à-dire ce qui permet de le reconnaître.
Vérifié : les six lignes produit font exactement 60 px.

Une image qui ne se charge pas retire sa vignette au lieu de laisser un carré
vide ; le nom suffit à choisir.

### Un défaut attrapé au test

Les liens de l'entonnoir partaient avec la marque en MAJUSCULES. Le filtre des
listes compare à `brand_code` sans tenir compte de la casse nulle part : la page
répondait **200 avec zéro produit**. C'est la pire forme de panne — elle
ressemble à un rayon vide, pas à une erreur, et personne ne la signale.

## 2026-09-17 — La recherche : pertinence, casse, fautes de frappe

Trois reproches de la propriétaire, tous fondés : « je tape Ara, il me propose
des vestes Ixon », « ne sois pas sensible à la casse », « quelqu'un qui tape
arei szr ou arai zzr doit tomber sur Arai SZ-R ».

### Pourquoi « Ara » sortait des Ixon

On cherchait par **sous-chaîne**. « ara » se trouve au milieu d'« OSTARA »
(veste Ixon), d'« araignée » (filet SW-Motech) et de « KARAKUM » (gants
Dainese) : trois mots qu'aucun visiteur ne cherchait, traités comme des
correspondances pleines.

Remplacé par `strict_word_similarity` de pg_trgm — « ce mot ressemble-t-il à un
**mot entier** de ce texte ». La pollution disparaît entièrement.

### Pourquoi « SZ-R » était introuvable

Deux causes, et il fallait les deux pour que ça échoue.

1. **On cherchait dans `model_display`**, un sac de jetons trié par ordre
   alphabétique : « Arai SZ-R VAS EVO » y devient « Evo R Sz Vas », que personne
   ne tape. Le nom écrit par le marchand vit dans `best_title`, renseigné pour
   les 311 698 fiches.
2. **La ponctuation sépare.** Pour pg_trgm « sz-r » est deux mots, « sz » et
   « r » : « szr » ne rencontre ni l'un ni l'autre.

Migration 018 : `f_recherche()` recolle la ponctuation (« SZ-R » → « szr ») et
un index GIN de trigrammes porte **exactement** cette expression — une autre
serait ignorée en silence et chaque frappe balaierait 311 000 lignes.

### Les fautes de frappe : deux mesures, pas une

Les trigrammes sont aveugles sur les mots courts. Mesuré :

| | ressemblance |
|---|---|
| « szr » vs « sz-r » recollé | **1,00** |
| « zzr » vs « szr » | **0,14** |
| « arei » vs « arai » | **0,25** |

Aucun seuil ne peut à la fois accepter 0,14 et refuser le bruit. La solution
tient en deux temps :

1. **La marque est reconnue en mémoire**, sur les 217 noms déjà en cache, par
   distance d'édition — exacte, puis par préfixe, puis à une faute près. Les
   inversions de lettres comptent pour UNE faute : « shoie » pour « shoei » est
   l'erreur la plus courante au clavier, et sans cela elle en coûterait deux.
   La correction ne s'applique qu'aux mots d'au moins quatre lettres : à trois,
   une lettre d'écart change de marque plus souvent qu'elle ne corrige.
2. **La marque une fois connue**, on ne cherche plus que dans son catalogue —
   quelques centaines de fiches — et on y classe par ressemblance **sans
   seuil**. C'est ce qui permet à « zzr » d'arriver premier parmi 147 Arai avec
   seulement 0,14.

Vérifié de bout en bout : « arei szr » **et** « arai zzr » rendent tous deux
« Casque jet Arai SZ-R VAS EVO » en tête, en 80 à 100 ms.

### Le meilleur résultat, à part

La moitié des recherches vise un produit précis. Quand on l'a trouvé, le noyer
au milieu de cinq lignes identiques oblige à relire pour le reconnaître. Il est
donc sorti de la liste, posé sur un fond différent, avec une photo de 62 px, le
nombre de marchands et le prix de départ.

Trois marques pour une seule idée — position, fond, taille. Une seule ne
suffirait pas : un fond seul se prend pour une bande, une taille seule pour du
hasard.

### Les vignettes

Un carré fixe de 42 px (62 pour le meilleur), `object-fit: contain`. Fixe, parce
que les photos des marchands n'ont ni la même taille ni le même cadrage : sans
cadre, chaque ligne prendrait une hauteur différente et la liste cesserait
d'être balayable. `contain` et non `cover`, parce que recadrer un casque
détouré coupe la mentonnière ou la visière — ce qui permet de le reconnaître.

### Plusieurs mises en avant, et une marque tapée seule

Deux corrections demandées dans la foulée.

**Trois mises en avant, pas une.** Un seul « meilleur résultat » supposait qu'on
sache lequel est le bon. Or « arai szr » rend six SZ-R qui ne diffèrent que par
la finition : désigner un vainqueur, c'est cacher deux réponses aussi justes que
lui. Trois et pas cinq — au-delà, l'entonnoir passe sous la ligne de flottaison,
et c'est lui qui fait l'intérêt de cette barre.

**La couleur départage.** Sans elle, la liste montrait trois fois « Casque jet
Arai SZ-R VAS EVO - SOLID » : trois coloris, trois lignes jumelles, aucun moyen
de choisir sans ouvrir les trois. Elle est souvent la seule chose qui sépare
deux fiches d'un même modèle.

**Une marque tapée seule propose la MARQUE.** « arai » ne désigne aucun casque
en particulier : mettre trois Arai en grand revenait à en choisir trois au
hasard parmi 147 et à les présenter comme la réponse. La liste ouvre maintenant
sur « ARAI — voir les 147 produits comparés », photo empruntée à la fiche la
plus comparée de la marque, puis l'entonnoir par rayon, puis quelques produits.
Dès qu'un mot accompagne la marque, les mises en avant reprennent leur sens.

Un détail attrapé au test : les codes couleur sont stockés en MAJUSCULES.
Écrit en minuscules, `colour()` retombe sur le code lui-même — le test serait
passé en affichant « bk ».

### La symétrie de normalisation, oubliée d'un côté

Signalé par la propriétaire : « arai sz-r » ne rendait rien.

La cause est une asymétrie que j'avais créée moi-même. Côté base, `f_recherche()`
**recolle** la ponctuation : « SZ-R » y devient « szr ». Côté saisie, je
**découpais** dessus : « sz-r » devenait deux mots, « sz » et « r », que le texte
indexé ne contient plus. Quelqu'un qui tapait le nom **avec son tiret**,
c'est-à-dire correctement, ne trouvait rien.

Une symétrie soignée d'un côté et oubliée de l'autre ne sert à rien. Les deux
normalisations sont désormais les mêmes, et un test les compare.

### Corriger une lettre oubliée sans envoyer chez le concurrent

« aai sz-r » — un « r » oublié — ne trouvait rien non plus : ma garde refusait
de corriger les mots de moins de quatre lettres. En la descendant à trois, un
nouveau défaut est apparu immédiatement : **« sz-r » tapé seul devenait la
marque SGR**, dont il n'est qu'à une lettre. Quelqu'un qui cherchait un casque
Arai se retrouvait chez un autre fabricant.

Deux gardes, et il faut les deux :

- **une seule candidate**, sinon on se tait — corriger vers l'une de deux
  marques possibles, c'est choisir à la place de quelqu'un qui n'a rien demandé ;
- **un mot court et SEUL n'est pas corrigé** — tapé seul, « sz-r » est un nom de
  modèle ; accompagné, « aai sz-r », c'est une marque, et le doute tombe.

Vérifié sur neuf formulations : `arai sz-r`, `aai sz-r`, `sz-r`, `szr`,
`arei szr`, `shoei gt-air`, `arai`, `shoie`, `ara` — toutes tombent juste, en
3 à 208 ms.

## 17/09/2026 — Trois rangées pour l'accueil, et ce que les données savent

Demande de la propriétaire : « d'abord mettre en avant les réductions
importantes **mais pas celles qui sont le plus élevées, varie les baisses**.
Ensuite les nouveautés en casque. Celui qui a le plus baissé cette semaine. »

Trois signaux, et ils ne sont pas également disponibles. Mesuré avant d'écrire
quoi que ce soit :

| Signal | Ce que la base peut en dire |
|---|---|
| Réductions variées | disponible tout de suite |
| Nouveautés casque | `product.created_at` vaut **le 14/09 pour les 313 435 fiches** : c'est le jour de reconstruction de la table. Inutilisable. |
| Plus forte baisse | `price_history` n'a que **quatre jours** : 12, 13, 14 et 17 septembre. |

### La date qu'il ne fallait pas lire

Une rangée « Nouveautés » branchée sur `created_at` aurait montré douze fiches
prises au hasard dans tout le catalogue, avec l'air d'une rangée juste. C'est la
forme de bug la plus coûteuse : **rien ne se voit à l'écran**.

La vraie date d'arrivée est celle de la première offre vue, `first_seen`. Reste
à écarter le versement initial — 763 570 offres le même jour. Le seuil n'est pas
écrit en dur, il se **lit** : est nouveau ce qui est apparu après le
`min(first_seen)` de la table. Une base repartie de zéro n'aura rien à corriger.

La rangée est donc courte — 37 casques le 17/09 — et grandit à chaque collecte.
Mieux vaut une rangée courte et vraie qu'une rangée pleine et inventée.

### La comparaison qu'il ne fallait pas faire

Pour « ce qui a baissé », le réflexe est de comparer le prix mini d'il y a une
semaine à celui d'aujourd'hui. Ces deux minimums ne portent pas sur la même
population : **un marchand moins cher qui arrive ferait baisser le second sans
qu'aucun prix n'ait bougé**, et la rangée annoncerait une baisse qui n'a pas eu
lieu. On compare donc une offre à elle-même, par son identifiant, et seulement
celle qui porte le prix affiché aujourd'hui.

Ce que les chiffres disent alors (fenêtre 12→17) : les baisses se massent sur
des rapports **ronds** — 0,90, 0,85, 0,80, 0,70. Ce sont des opérations
commerciales, pas du bruit. Mais elles sont très inégalement réparties :

| Marchand | Offres suivies | Baisses | Rapport moyen |
|---|---:|---:|---:|
| FC-Moto | 143 523 | 112 149 | 0,83 |
| Moto-Axxe | 16 994 | 8 362 | 0,92 |
| Maxxess | 16 007 | 9 288 | 0,92 |
| Speedway | 56 297 | 20 346 | 1,00 |
| Motoblouz | 298 530 | 4 449 | 1,00 |
| La Bécanerie | 222 907 | **0** | 1,00 |

Classée au pourcentage, la rangée montrait douze articles FC-Moto : la promotion
d'un marchand, présentée comme l'actualité du catalogue. Deux corrections, dont
la seconde a demandé un aveu :

1. un **tour de rôle** entre marchands — le meilleur de chacun, puis le
   deuxième ;
2. un **plafond dur** de trois par marchand. Le tour de rôle seul ne suffisait
   pas : dès que les autres étaient à court de candidats, la queue se remplissait
   du seul qui en avait encore. La rangée a le droit d'être plus courte que
   douze ; elle n'a pas le droit d'être le catalogue d'un marchand.

**Une limite qui attire au lieu d'écarter n'est pas une limite.** Posée d'abord
aux sept dixièmes, ma garde anti-aberration s'est retrouvée à *sélectionner* :
FC-Moto y venait buter et la rangée s'ouvrait sur « −70 % » quatre fois de
suite. Ramenée un peu au-dessus de la moitié, et doublée d'un plancher en euros
— un écran de casque qui passe de 15,00 € à 4,53 € affiche un beau pourcentage
et ne mérite pas la page d'accueil — elle redevient une garde.

### Varier sans descendre

La rangée des écarts est désormais rangée par tranche de dix points et se sert
dans chacune à tour de rôle. Deux détails :

- la **bande basse est écartée**. Le seuil historique (`dearest ≥ cheapest×1,15`)
  laisse passer des −13, et la page d'accueil s'ouvrait sur « −14 % ». Varier ne
  veut pas dire descendre.
- le tirage est **arbitraire mais stable sur la journée**, `hashtext(slug ||
  date)`. Un `random()` ferait sauter la rangée à chaque expiration du cache,
  sous les yeux du visiteur qui revient ; figée, elle ne montrerait jamais que
  les mêmes douze fiches.

Ce tirage a révélé un défaut ancien : les `DISTINCT ON` n'avaient **aucun
départage**, et le coloris retenu changeait d'une visite à l'autre. Invisible
tant que la rangée classait au pourcentage, il éclate dès qu'un hachage du slug
entre dans le tri. `p.slug` clôt maintenant les trois tris.

### Le prix en temps

Les deux nouvelles requêtes coûtaient **5,1 s et 7,2 s**. Deux causes, toutes
deux d'ordre :

- aucune des deux colonnes utiles n'était indexée (`raw_offer.first_seen`,
  `price_history.observed_on` — cette dernière est en *deuxième* position de la
  clé primaire, donc inutilisable seule). Migration `019`.
- les requêtes partaient du grand ensemble. Réécrites pour partir du petit —
  les 10 187 offres arrivées après le versement, les offres dont le prix a
  bougé — avant de rejoindre les fiches.

Résultat : **0,16 s / 1,03 s / 2,03 s**, et l'accueil complet passe de 2,4 s à
5,2 s à froid, 7 ms en cache.

## 17/09/2026, soir — Deux pannes totales, et le test qui manquait

### La panne

La migration 020 recrée `product_stats` — il n'existe pas d'ALTER pour ajouter
une colonne à une vue matérialisée. Appliquée sur le VPS en `sudo -u postgres`,
elle a rendu la vue propriété de `postgres`, alors que tout le schéma appartient
au rôle de l'application. Résultat, **toutes les pages en 500** :

```
psycopg.errors.InsufficientPrivilege:
permission denied for materialized view product_stats
```

Y compris l'accueil : `categories()` lit cette vue. Réparé en rendant la vue à
son propriétaire. La migration reprend désormais le propriétaire de `product`,
puis **vérifie** qu'il a bien été appliqué et échoue bruyamment sinon.

C'est un défaut qui n'existe QUE là où on déploie : en local, la migration est
appliquée par le rôle qui possède déjà tout.

### La seconde, une heure plus tard

En câblant l'affiche paysage, j'ai ajouté `statique_existe()` au gabarit et
oublié de le déclarer. L'accueil a rendu 500 — et **les 239 vérifications sont
passées au vert.**

C'est le constat de la journée. Aucune ne RENDAIT une page. Elles examinaient
des requêtes, des règles, des fichiers, des invariants — tout sauf le résultat.
Deux pannes totales en une journée, aucune attrapée, faute du test le plus bête
qui soit : ouvrir la page et regarder le code de retour.

`tests/test_site_pages.py` rend maintenant seize adresses, une fiche produit
tirée de l'accueil, et vérifie que les fichiers d'affiche référencés existent
vraiment — parce qu'un `<source>` retenu mais introuvable n'affiche pas l'image
de repli, il n'affiche rien.

### La fuite, et d'où elle venait

Le commit `e69da0a` de ce matin — que j'avais préparé — contenait le nom de
famille de la propriétaire en clair, dans un commentaire de
`ops/deploiement/07-planification.sh`, sur un dépôt PUBLIC et volontairement
anonymisé. Retiré.

Mon balayage d'avant-commit cherchait un prénom, un fournisseur de messagerie,
l'adresse IP, le mot « password ».
Il ne cherchait pas le nom de famille. **Une vérification qui cherche les termes
dont on se souvient, au lieu de la règle qu'on applique, ne vérifie rien.**

### L'accueil : douze carrousels, c'était onze de trop

Demande de la propriétaire : « trop répétitive, c'est moche de dingue, il manque
des IMAGES, il y en a 11 c'est trop ». Le compte lui donnait raison : trois
étagères éditoriales plus neuf étagères de rayon, toutes bâties sur la même
carte, au même rythme, avec les mêmes boutons.

Les neuf rangées de rayon deviennent une **mosaïque en grandes images** : une
vraie photo de produit par rayon, son nombre de fiches, son prix d'entrée. La
première tuile est deux fois plus grande — sans elle, la mosaïque serait à son
tour un damier régulier, et on aurait remplacé une monotonie par une autre.

De douze carrousels à **trois**. Aucune requête de plus : `categories()` portait
déjà la photo et le prix d'entrée.

### La bannière qui déposait des cookies

Voir `partenaires.py`. L'image Motoblouz pointait vers `pkw.motoblouz.com`, le
domaine de suivi de Kwanko : quatre cookies, 60 jours, **à l'affichage**, chez
un visiteur qui n'avait rien cliqué — alors que la page « À propos » promet
l'inverse. Mon commentaire d'origine disait « il n'y a pas de tiers
supplémentaire » : vrai sur la forme, faux sur le fond. La question n'était pas
de savoir s'il y a un tiers, mais si un cookie part sans clic.

Motoblouz sort de la rotation d'images, et seulement d'elle : son lien de clic
reste, et le revenu se fait au clic et à la vente, pas à l'affichage.

## 17/09/2026, tard — Les cartes de l'accueil, et une règle qui en coûte une autre

Réglages demandés par la propriétaire, capture à l'appui :

- **la MARQUE en gras et en capitales**, le **titre en graisse normale**, le
  **prix de la même taille et de la même graisse que la marque** ;
- le **prix barré collé au prix**, et non renvoyé à l'autre bout de la carte ;
- **plus de « X € d'écart sur cette fiche »** ni de « vu pour la première fois
  le … » : « le client n'est pas con non plus » ;
- la pastille **« Nouveau » sur les trois premières cartes seulement** ;
- **aucune fiche à moins de trois marchands** sur l'accueil.

Les quatre premiers sont des retraits, et ils vont dans le même sens : une carte
de 208 px annonçait la remise **trois fois** — en pastille, en prix barré, et en
toutes lettres. Deux ancres fortes (marque, prix) et un titre discret entre les
deux se parcourent plus vite qu'un gros chiffre entouré de redites. Poser le
prix à la même taille que la marque est l'inverse de l'habitude, et c'est mieux
vu : une carte sert à **reconnaître** l'article, la fiche à en comparer le prix.

### La règle des trois marchands en annule une autre

Mesuré avant d'appliquer, et c'est heureux :

| Rangée | à ≥2 marchands | à ≥3 marchands |
|---|---:|---:|
| Là où comparer rapporte le plus | 5 777 candidats | 2 389 |
| Nouveautés casque | 40 fiches | **0** |

Une fiche qui vient d'arriver est chez **un** marchand par construction ; il
faut des semaines pour que trois la listent. La règle est donc appliquée partout
— c'est la consigne — et elle **fait disparaître la rangée « Nouveautés
casque »** demandée le matin même. Le gabarit ne rend la section que si elle a
quelque chose à montrer : mieux vaut une rangée absente qu'une rangée qui
enfreint la règle du site. La décision de garder l'une ou l'autre appartient à
la propriétaire, qui a été prévenue avec les chiffres.

### Trois fois le même piège

Un `%` écrit dans un **commentaire SQL** a fait échouer une requête trois fois
dans la journée : psycopg lit la chaîne entière, pas seulement le code, et
« 18 % » ou `{% if %}` dans une explication devient un paramètre incomplet.
L'erreur ne parle jamais du commentaire — elle dit « incomplete placeholder »,
et on cherche ailleurs. Trois fois, ce n'est plus de la distraction : c'est un
piège du langage, et `tests/test_requetes_sql.py` le garde maintenant.

Un second test a été écrit puis **retiré** : il comptait les paramètres d'une
requête en analysant du Python à coups d'expressions régulières, et rendait un
faux positif sur une requête juste. Un test auquel on ne peut pas se fier coûte
plus qu'il ne rapporte — on finit par le contourner, puis par ignorer ses
semblables.
