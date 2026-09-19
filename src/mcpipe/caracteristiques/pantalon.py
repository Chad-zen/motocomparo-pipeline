"""Ce qu'on peut dire d'un pantalon moto, a partir des flux qu'on recoit deja.

POURQUOI CE FICHIER EXISTE. Meme raison que `casque.py` : le configurateur a
besoin de caracteristiques, et le catalogue n'en porte aucune. Sur ce rayon-ci,
deux informations decident un achat a elles seules — le fait que les COQUES
soient dans le carton ou pas, et l'UNIVERS DE PRATIQUE, qui est l'axe du
configurateur par profil. Le reste est du confort.

CE QU'ON A MESURE AVANT D'ECRIRE, et c'est ce qui decide tout :

    source          fiches   description mediane
    motoblouz        2 478         690 signes
    fcmoto           5 493         163 signes
    speedway           984          77 signes
    labecanerie      1 810          87 signes
    maxxess            241         519 signes
    motoaxxe           243         493 signes

FC-Moto couvre le plus de fiches mais ecrit peu — en revanche il ecrit TOUJOURS
la meme chose, en liste a puces normalisee (« Vetements de protection pour
motocyclistes, classe de protection AA (EN 17092-3 :2020) », « Prepare pour les
protecteurs de hanche (non inclus) »). C'est la source la plus REGULIERE du
rayon, meme si ce n'est pas la plus bavarde. Motoblouz est la plus riche, mais
son HTML est aplati sans separateur : « ...aux genoux, ajustablesProtections
des hanches optionnellesPoche pour protection du coccyx optionnelle ». Tout le
travail de fenetrage de ce fichier vient de la.

LES FACETTES VISEES SONT CELLES DU MARCHAND, pas une liste inventee ici :
matiere grossiere et matiere nommee, matiere renforcee, saisonnalite, coupe,
Gore-Tex, protection genou et hanche, options, categorie, univers de pratique,
genre. Une seule est ajoutee : la CLASSE EN 17092, que le marchand n'expose pas
sur ce rayon-la alors qu'il l'expose sur les blousons. C'est precisement la que
le comparateur peut faire mieux que la boutique.

CE QU'ON NE TROUVERA PAS ICI, et il faut le dire une fois pour toutes :

  * L'UNIVERS DE PRATIQUE N'EST PAS DANS LA TAXONOMIE DES FLUX. On l'a
    cherche colonne par colonne. La colonne `category` de Motoblouz vaut
    « Pantalons » (12 829 lignes), « Pantalon Motocross » (4 568) ou
    « Pantalon Enduro » (22) — c'est la CATEGORIE, pas l'univers. Chez Maxxess
    et Moto-Axxe, `category`/`category_level2`/`category_level3` donnent
    « Equipement du motard / Pantalon et jeans / Jeans moto » ; chez La
    Becanerie « Equipement route / Pantalon moto / Jean ». Aucun des six flux
    ne porte custom / roadster / sport / touring / trail / scooter. Cet axe-la,
    le marchand le tient dans son PIM et ne l'exporte pas.
    On le lit donc DANS LA PROSE, et seulement quand le marchand le nomme a
    cote du mot « pantalon » — « son pantalon moto textile Touring le AST-1 »,
    « son pantalon moto Adventure les CONTINENT ». C'est peu, et c'est dit.
    (Et de toute facon `_lignes()` ne passe que le titre et la description a
    `lire()` : meme si la colonne portait l'univers, il faudrait ouvrir
    l'orchestrateur pour l'y amener. Ce n'est pas la decision de ce fichier.)

  * « MATIERE RENFORCEE : NON » N'EST PAS LISIBLE. Le marchand distingue
    « non » de « non communique » parce que son PIM porte les deux. Un texte de
    vente, lui, ne dit jamais « ce pantalon n'a aucun renfort » : il se tait.
    On rend donc 'oui' quand une fibre de renfort est nommee, 'non' sur la
    negation explicite — rarissime — et `None` sinon. `None` n'ecrit aucune
    ligne en base, ce qui EST « non communique ». La troisieme valeur existe,
    elle s'appelle l'absence.

LA REGLE QUI GOUVERNE TOUT LE FICHIER
=====================================
En cas de doute, on rend `None`. Annoncer « coques de hanches fournies » quand
elles sont en option, c'est promettre a l'acheteur une piece qu'il devra payer
en plus ; annoncer une classe AAA sur un vetement de classe A, c'est une
information de securite fausse. Une caracteristique absente coute un filtre
moins precis ; une caracteristique fausse coute la confiance.

C'est la meme regle que `casque.py`, pour la meme raison.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- les pieges de formulation ------------------------------------------------
#
# Recopie de `casque.py` — MOT POUR MOT pour la premiere moitie, parce que ce
# vocabulaire a coute cher a etablir sur le rayon casque et qu'il se transpose
# tel quel. La seconde moitie a ete ajoutee EN LISANT le rayon pantalon : ici,
# la piece optionnelle n'est pas un intercom, c'est la coque de hanche, et les
# marchands ont leur facon a eux de le dire.
#
#   « Poches pour protections de hanches CE ALPHA EN 1621-1 niveau 1 »
#   « Poches prevues pour ajouter des protections de hanches (en option) »
#   « Poche prevue pour protection de hanche disponible separement et non incluse »
#   « Prepare pour les protecteurs de hanche (non inclus) »
#
# « Poche(s) ... pour » est propre a ce rayon et ne figurait pas dans la garde
# du casque : une poche vide est le contraire d'une coque fournie, et c'est
# pourtant la formulation la plus courante de Motoblouz.
_PREPARE = (
    # --- la garde du rayon casque, telle quelle ---
    r"(?:pr[ée]dispos|pr[ée]{1,2}quip|pr[ée]par|compatible|"
    r"pr[êe]t (?:[àa]|pour)|ready|"
    # « ADAPTE A » N'EST PAS « ADAPTE A RECEVOIR », et la difference a ete
    # payee en relisant. Le rayon casque pouvait se permettre la formule nue ;
    # ici Motoblouz ecrit « Protections CE niveau 2 aux genoux et aux hanches »
    # juste apres « un niveau de protection global ADAPTE A LA ROUTE », et la
    # garde annoncait les deux coques en option alors qu'elles sont fournies.
    # Mesure : 17 fenetres de hanches et 28 de genoux etaient dans ce cas, et
    # toutes disaient l'inverse de ce que le marchand ecrit. On exige donc que
    # ce a quoi le vetement est adapte soit une PIECE A RECEVOIR, et non un
    # usage, une morphologie ou une route.
    r"adapt[ée]e?s? (?:pour|[àa])\s+(?:recevoir|accueillir|loger|"
    r"l.ajout|la pose|des? protect|les? protect)|"
    r"peut recevoir|possibilit[ée] d|en option|non fourni|"
    r"n[ée]cessite|[àa] commander|vendu[es]? s[ée]par|"
    # --- ce que le rayon pantalon ajoute ---
    #
    # LA POCHE SE DECRIT AVEC UN ADJECTIF AU MILIEU, et la premiere version ne
    # l'avait pas vu : elle exigeait « poche pour » ou « poche prevue pour »,
    # collees. Le rayon ecrit « Poches REGLABLES pour les protections genoux
    # amovibles ALPHA EN1621-1 » et « Poches POUVANT ACCUEILLIR des protections
    # hanches » — deux poches vides annoncees comme des coques fournies.
    r"poches?(?:\s+\w+){0,2}\s+(?:pour|pr[ée]vues?|pr[ée]dispos\w*|accueill|destin)|"
    r"pouvant (?:recevoir|accueillir|loger)|"
    r"emplacements? pour|logements? pour|"
    r"non inclus|non livr|optionnel|disponible s[ée]par|sans protection|"
    r"\(option|peuvent [êe]tre ajout)"
)

# Le contraire, et il faut le nommer aussi : sur ce rayon les deux marqueurs
# cohabitent DANS LA MEME PHRASE, et c'est le plus PROCHE qui dit la verite.
#
#   « Protections de hanches SEESMART RV33 CE-niveau 1 (en option) et inclut
#     des protections de genoux SEESMART CE-niveau 1 RV36 »
#
# Une garde qui se contente de chercher un motif de preparation quelque part
# autour annonce ici les DEUX coques en option, alors que les genoux sont dans
# le carton. On mesure donc la distance des deux marqueurs a l'ancre.
_FOURNI = r"(?:\(inclus|incluse|inclus\b|inclut|livr[ée]|fournie?s?\b|[ée]quip[ée])"


# --- homologation EN 17092 ----------------------------------------------------
#
# La norme decoupe les vetements en cinq classes, et chaque classe a SA PARTIE
# dans la norme. Les marchands ecrivent tantot la partie, tantot la lettre,
# souvent les deux :
#
#   EN 17092-2 -> AAA      « Entierement approuve CE AAA conformement a la
#   EN 17092-3 -> AA         norme EN17092-2 : 2020 »
#   EN 17092-4 -> A        « classe de protection AA (EN 17092-3 :2020) »
#   EN 17092-5 -> B        « Homologation CE EN17092 - A »
#   EN 17092-6 -> C        « Certifie EN17092 AAA »
#
# La partie -1 est le tronc commun (methodes d'essai) : elle ne designe AUCUNE
# classe, et la lire comme telle serait inventer une homologation.
_PARTIE_VERS_CLASSE = {"2": "AAA", "3": "AA", "4": "A", "5": "B", "6": "C"}
_EN_PARTIE = re.compile(r"17092\s*[-–:]\s*([2-6])(?!\d)")
_EN_LETTRE = re.compile(
    r"17092(?:\s*[-–]\s*[1-6])?\s*:?\s*(?:20\d\d)?[\s:,\-–]*\(?(AAA|AA|A|B|C)\)?(?![A-Za-z])"
)
# `class\w*` semblait inoffensif. Il ne l'est pas : le moteur BACKTRACKE, et sur
# « Pantalon cross O'Neal ELEMENT - CLASSIC - BLACK » il lit « CLASSI », puis
# prend le « C » final pour une classe de protection. La CLASSE C est la plus
# basse de la norme — celle des vetements qui ne resistent pas a l'abrasion.
# On l'annoncait sur des « Jean Moto Richa CLASSIC », un « Dainese CLASSIC
# LADY », un « Hebo TECH MONTESA CLASSIC ». « Classic » est un des noms de
# modele les plus courants du rayon : la faute etait systematique, et invisible
# — six fiches seulement, mais six sur six fausses, et toutes vers la classe qui
# fait fuir un acheteur.
# Le `\b` apres le groupe optionnel ferme la porte au retour arriere.
_CLASSE = re.compile(
    r"(?i:class(?:es?|ification)?)\b\s*(?i:de protection\s*)?:?\s*"
    r"\(?(AAA|AA|A|B|C)\)?(?![A-Za-z])"
)
_CE_CLASSE = re.compile(r"\bCE[\s,]+(AAA|AA)(?![A-Za-z])")
# « Pantalon homologue CE niveau A » : la lettre suit « niveau », ce qui est un
# abus de langage du marchand, mais un abus sans ambiguite tant qu'on exige le
# verbe d'homologation juste avant. Voir `_NIVEAU_N_EST_PAS_UNE_CLASSE`.
_HOMOLOGUE_NIVEAU = re.compile(
    r"(?i:homologu\w+|certifi\w+|approuv\w+)\s+(?i:CE\s+)?(?i:de\s+)?"
    r"(?i:niveau)\s+(AAA|AA|A|B|C)(?![A-Za-z])"
)

# LE PIEGE DES LETTRES, ET IL EST PARTOUT SUR CE RAYON.
#
# EN 1621-1 — la norme des COQUES — classe les protecteurs par TYPE A ou TYPE B
# (c'est leur surface de couverture) et par NIVEAU 1 ou 2. EN 17092 — la norme
# du VETEMENT — classe le pantalon en AAA/AA/A/B/C. Les deux se cotoient dans la
# meme phrase, avec les memes lettres :
#
#   « Protection Fanom SEK niveau I type A aux genoux, ajustables en hauteur
#     Protection Fanom Hip niveau I type B aux hanches »
#   « Genouilleres Armanox type 701, EN1621-1 type B, niveau 1 »
#
# Lire « type B » comme une classe de vetement ferait de ce pantalon un
# vetement de classe B — la classe des tenues sans resistance a l'abrasion.
# C'est exactement l'inverse de ce que dit la phrase. Aucune expression de ce
# fichier ne lit donc une lettre derriere « type ».
_NIVEAU_N_EST_PAS_UNE_CLASSE = r"type\s+[AB]\b"

# --- niveau des coques (EN 1621-1) --------------------------------------------
_NIVEAU_COQUE = re.compile(
    r"(?:niveau|level|niv\.)\s*(?:CE\s*)?[-\s]?(1|2|I{1,2})(?![\d\w])", re.I
)

# --- categorie ----------------------------------------------------------------
#
# Le vocabulaire est celui de la facette « Categorie » du marchand : jean moto,
# pantalon moto, surpantalon, legging, jambiere, jogging. Lu dans le TITRE
# d'abord, parce que c'est le seul champ que les six marchands remplissent de
# la meme facon. L'ordre compte : un sur-pantalon est aussi un pantalon, et un
# jean moto est aussi un pantalon.
#
# Le CUIR et le CROSS n'y sont PAS : le cuir est une matiere, le cross un
# univers de pratique. Les melanger dans un seul champ « type » — ce que faisait
# la premiere version de ce fichier — rendait le filtre inutilisable : on ne
# pouvait plus demander un jean de cuir, ni un pantalon cross en textile.
_CATEGORIE = [
    ("sur-pantalon", r"sur.?pantalon|surpantalon|pantalon de pluie|pantalon pluie|"
                     r"over.?(?:pant|trouser)"),
    ("jambiere",     r"jambi[èe]res?|\bchaps\b"),
    ("jogging",      r"\bjogging\b|sweat.?pant"),
    ("legging",      r"\bleggings?\b|\bjeggings?\b"),
    ("jean",         r"\bjeans?\b|\bdenim\b"),
    ("pantalon",     r"\bpantalons?\b|\bpants?\b|\btrousers?\b|\bhose\b"),
]

# --- univers de pratique ------------------------------------------------------
#
# LA CARACTERISTIQUE LA PLUS DEMANDEE, ET LA PLUS AVARE. Elle n'est dans aucune
# taxonomie de flux (voir l'en-tete du fichier) : il faut la lire dans la prose,
# et la prose ne la donne que par une tournure, celle de la phrase de
# presentation :
#
#   « ALPINESTARS vous propose son pantalon moto textile Touring le AST-1 V2 »
#   « REV'IT vous propose son pantalon moto Adventure homme les CONTINENT »
#   « Richa nous propose son pantalon moto Adventure, le Cyclone 2 Gore-Tex »
#   « un pantalon touring type Raid »
#
# On ANCRE donc sur le mot « pantalon » / « jean », et on ne lit l'univers que
# dans les quarante-cinq signes qui suivent. Hors de cette fenetre, les memes
# mots sont du decor de vente : « coupe sport », « look casual urbain »,
# « allure vintage » ne disent rien de l'usage de la machine.
#
# ET « RACING » EST UN NOM DE MARQUE. Fly Racing, Moose Racing, Answer Racing,
# Thor Racing font des pantalons de CROSS ; « Alpinestar Racing Rain » est un
# sur-pantalon de pluie. Le mot est dans le titre de plusieurs centaines de
# fiches tout-terrain, et le lire comme « sport » aurait envoye le rayon cross
# entier dans l'univers piste. Il est donc ABSENT du motif « sport », et c'est
# une perte assumee : quelques vrais pantalons racing ne seront pas classes.
#
# L'ordre compte doublement : le tout-terrain passe AVANT le sport, parce que
# « Pantalon tout-terrain Moose Racing Sahara » est l'un et pas l'autre.
_ANCRE_UNIVERS = r"(?:pantalons?|jeans?|jegging|legging|sur.?pantalon)"
_UNIVERS = [
    ("cross",    r"motocross|\bcross\b|tout.?terrain|off.?road\b|\bMX\b"),
    ("enduro",   r"\benduro\b"),
    ("trial",    r"\btrial\b"),
    ("trail",    r"\btrail\b|\badventure\b|\bADV\b|\braid\b"),
    ("touring",  r"\btouring\b|grand tourisme|\bvoyage\b"),
    ("scooter",  r"\bscooters?\b"),
    ("custom",   r"\bcustom\b|\bcruisers?\b|caf[ée].?racer|\bbobber\b"),
    ("sport",    r"\bpistes?\b|\bsupermotard\b|\bsuper.?sport\b"),
    ("roadster", r"\broadsters?\b|\burbaine?s?\b"),
]
# CE QUI A ETE RETIRE DE CES MOTIFS, ET POURQUOI — c'est la moitie du travail,
# et rien de tout cela ne se voyait dans un taux de couverture : chaque retrait
# FAIT BAISSER la couverture de l'univers, et chaque retrait est une correction.
#
#   « aventure » (francais)  : « Pantalon adapte aux AVENTURES URBAINES grace a
#                              ses poches multiples » — un jean de ville annonce
#                              en trail. Seul l'anglais « adventure » designe la
#                              categorie chez ces marques.
#   « street », « city »     : « Jean enfant Overlap STREET KID », « Jean Moto
#                              DXR HOWELL CITY », « Pantalon By City AIR III ».
#                              Trois noms de modele et une marque, zero usage.
#   « vintage »              : « Jean Rev'It Piston 3 SK L30 Bleu Clair
#                              VINTAGE » — c'est une COULEUR. Et « Carhartt
#                              Vintage Fit » est une coupe.
#   « sportif », « sportive »: qualifie la COUPE, pas la moto. « Pantalon de
#                              randonnee SPORTIF avec GORE-TEX Z-Liner » est un
#                              pantalon de voyage ; « ajustement sportif » est
#                              un sous-vetement de compression.
#   « circuit »              : « Jean Moto Trilobite PARADO CIRCUIT » se decrit
#                              lui-meme comme « style voyage, urbain et
#                              routier ». Nom de modele.
#   « racing »               : Fly Racing, Moose Racing, Answer Racing, Thor
#                              Racing font des pantalons de CROSS ; « Alpinestar
#                              Racing Rain » est un sur-pantalon de pluie. Le mot
#                              est dans plusieurs centaines de titres tout-
#                              terrain. Il n'a jamais figure dans ces motifs.
#
# Reste « piste », qui tient : « Pantalons sportifs en cuir pour la PISTE et la
# route » est bien un pantalon de circuit, et le mot n'est dans aucun nom de
# modele du rayon.

# --- genre --------------------------------------------------------------------
#
# « Mixte » passe en premier : « Genre mixte, adapte a une utilisation par les
# pilotes homme et femme » contient les trois mots, et seul le premier est vrai.
_GENRE = [
    ("mixte",  r"\bmixtes?\b|\bunisexe?\b"),
    ("enfant", r"\benfants?\b|\bkids?\b|\bjunior\b|\bgar[çc]on\b|\bfille\b|\byouth\b"),
    ("femme",  r"\bfemmes?\b|\blady\b|\bladies\b|\bdames?\b|\bwom[ae]n\b|f[ée]minin"),
    ("homme",  r"\bhommes?\b|\bmens?\b|\bmasculin\b|\bherren\b"),
]

# --- la matiere ---------------------------------------------------------------
#
# DEUXIEME PIEGE DU RAYON, transpose du casque ou « visiere en polycarbonate »
# faisait classer la calotte en polycarbonate. Un pantalon moto porte quatre ou
# cinq etoffes, et le marchand les cite toutes a la suite :
#
#   « Les panneaux interieurs en cuir de chevre aux genoux offrent une
#     sensation de qualite superieure »            <- ce n'est pas un pantalon cuir
#   « Etiquette en cuir de kangourou »             <- ce n'est pas un pantalon cuir
#   « Doublure interieure 100% polyester »         <- ne dit rien du tissu exterieur
#   « Renforts CORDURA 1500D sur les hanches »     <- ne dit rien du tissu exterieur
#   « Fessier renforce en polyamide 900 D »        <- ne dit rien du tissu exterieur
#
# Le cuir est le cas le plus couteux : c'est lui qui fait le prix.
#
# DEUX FACETTES, PAS UNE. Le marchand filtre sur une matiere GROSSIERE (denim,
# cuir, cuir et textile, textile) et sur une matiere NOMMEE (Armalith, denim
# Cordura, jean, Kevlar, textile). On rend les deux, et la nommee n'est remplie
# que si le texte NOMME vraiment : « denim renforce » n'est pas « Armalith »,
# et c'est le meme piege de genre et de sous-genre que « thermoplastique »
# n'est pas « polycarbonate » sur le rayon casque.
_MATIERE = [
    # Les marques d'abord : elles sont plus precises, et elles ne sont jamais
    # ambigues — personne n'ecrit « Armalith » pour dire « toile ».
    ("armalith",      r"armalith"),
    ("kevlar",        r"\bkevlar"),
    ("twaron",        r"\btwaron"),
    ("dyneema",       r"\bdyneema"),
    ("denim cordura", r"cordura\W{0,3}denim|denim\W{0,3}cordura"),
    # Le cuir SYNTHETIQUE n'est pas du cuir, et « Tissu exterieur : 600D Oxford,
    # [...] cuir synthetique » est une vraie phrase du rayon.
    ("cuir",       r"(?<!simili )\bcuirs?\b(?!\s*(?:synth|artificiel|PU\b|[ée]cologique))|\bleather\b"),
    ("denim",      r"\bdenims?\b|toile de coton"),
    ("cordura",    r"cordura"),
    ("softshell",  r"soft.?shell"),
    ("polyester",  r"polyester"),
    ("polyamide",  r"polyamide|\bnylon\b"),
]
# La matiere GROSSIERE, telle que le marchand la filtre.
_MATIERE_GROSSIERE = {
    "armalith": "denim", "kevlar": "textile", "twaron": "textile",
    "dyneema": "textile", "denim cordura": "denim", "cuir": "cuir",
    "denim": "denim", "cordura": "textile", "softshell": "textile",
    "polyester": "textile", "polyamide": "textile",
}
_PIECE_QUI_N_EST_PAS_LE_TISSU = (
    r"(?:doublure|doubl[ée]e?s?\b|renforts?|renforc|empi[èe]cement|panneaux?|"
    r"inserts?|patch|[ée]tiquette|superposition|double.couche|couche\b|"
    r"genoux?|genouill|fessier|si[èe]ge|assise|mollets?|entrejambe|tibia|"
    r"poches?|ceinture|passants?|ourlet|coutures?|rev[êe]tement|"
    r"membrane|maille|zones?\b|sliders?|protections?|combinaisons?|"
    r"bouclier|[ée]cussons?|logos?)"
)
# Motoblouz ecrit ses fiches par sections. Quand la section « Matiere » existe,
# on ne cherche le tissu principal QUE dedans : c'est la seule facon sure de ne
# pas prendre la doublure pour l'exterieur — et la doublure est presque toujours
# en polyester, alors que l'exterieur ne l'est presque jamais seul.
_SECTION_MATIERE = re.compile(
    r"Mati[èe]res?\s*:|Conception et mat[ée]riaux|Tissu ext[ée]rieur|"
    r"Mati[èe]re ext[ée]rieure",
    re.I,
)
_SECTION_SUIVANTE = re.compile(
    r"Doublures?\s*:|Protections?\s*:|Protection et renforts|Les\s*\"?\+|"
    r"Poches\s*:|S[ée]curit[ée] et normes|Imperm[ée]abilit[ée]|Ajustement et coupe|"
    r"Ventilation et respirabilit|Confort et ergonomie",
    re.I,
)

# --- matiere renforcee --------------------------------------------------------
#
# La facette du marchand a trois valeurs : oui, non, non communique. Un texte de
# vente n'ecrit jamais la deuxieme (voir l'en-tete). On exige une FIBRE NOMMEE,
# ou un renfort explicitement donne pour l'abrasion. « Coutures renforcees » ne
# compte pas : ce sont les fils, pas le tissu, et la formule est dans un tiers
# des fiches du rayon.
_RENFORT_OUI = re.compile(
    r"aramides?\b|\bkevlar|\btwaron|armalith|\bdyneema|\bcordura|\bPWR\b|"
    r"balistique|tri.?stretcher|\bhyscor\b|"
    r"renforc\w*[^.]{0,45}abrasion|renforts?[^.]{0,35}abrasion|"
    r"abrasion[^.]{0,25}renfor",
    re.I,
)
_RENFORT_NON = re.compile(r"sans renfort|non renforc[ée]|aucun renfort", re.I)

# --- renfort aramide ----------------------------------------------------------
#
# TROISIEME PIEGE, celui du genre et du sous-genre. Sur le casque, c'etait
# « thermoplastique » lu comme « polycarbonate ». Ici c'est la marque :
#
#   Kevlar (DuPont) et Twaron (Teijin) sont des para-aramides DE MARQUE.
#   « fibres d'aramide », « renforts aramides » ne disent pas laquelle.
#
# Le champ est donc un booleen : ce qui interesse l'acheteur est qu'il y ait de
# l'aramide, pas de qui. La marque, quand le texte l'ecrit, part dans
# `matiere_nommee` — ou elle est LUE, et non deduite.
#
# Le Dyneema (UHMWPE) et le Cordura (polyamide) NE SONT PAS des aramides, et ils
# figurent dans les memes phrases : « Denim TRI-STRETCHER PRO 5.0 (coton, nylon,
# polyester, Dyneema, elasthanne) ». Ils sont absents de ce motif expres.
_ARAMIDE = re.compile(r"aramides?\b|\bkevlar|\btwaron|para.?aramid", re.I)
# Et l'ETENDUE, qui est la vraie question : un jean a renforts aux genoux et aux
# hanches ne protege pas comme un jean double aramide sur toute la surface.
# Mesure sur l'echantillon : la grande majorite des mentions sont ZONEES.
_ARAMIDE_ZONES = (
    r"renforts?|inserts?|empi[èe]cement|panneaux?|au niveau|zones?\b|"
    r"genoux?|hanches?|si[èe]ge|fessier|[ée]paules?|stretch [àa] l|"
    r"localis|sur les|aux\b"
)
_ARAMIDE_COMPLETE = (
    r"toute la surface|int[ée]gralement|enti[èe]rement doubl|doublure compl[èe]te|"
    r"100\s?% aramide|monolayer|mono.?couche|monocouche|doublure aramide|"
    r"doubl[ée] aramide|sur l.ensemble"
)

# --- membrane et Gore-Tex -----------------------------------------------------
#
# TROISIEME PIEGE ENCORE, et sous sa forme la plus rentable pour le marchand :
# « membrane coupe-vent » n'est PAS une membrane impermeable, et
# « traitement exterieur impermeable » / « revetement hydrofuge » / « deperlant »
# sont des traitements de surface qui lachent sous la pluie soutenue.
#
#   « La doublure softshell en micropolaire chaude avec membrane coupe-vent et
#     traitement d'evacuation de l'humidite »      <- coupe-vent seulement
#   « Revetement hydrofuge, vous gardant au sec en cas de pluie FINE »
#
# On exige donc l'impermeabilite EXPLICITE dans la meme fenetre que la membrane.
# Et Gore-Tex est une marque : une membrane maison (BWTECH, XDRY, Solto-TEX,
# SinAqua, Drystar, D-Dry) est une membrane, pas un Gore-Tex. Valeur generique
# quand le texte ne nomme rien, comme « thermoplastique » sur le rayon casque.
#
# La facette du marchand distingue « oui » et « oui, lamine » : un Gore-Tex
# lamine sur le tissu exterieur n'a pas le meme comportement qu'un Z-Liner
# flottant a l'interieur. Le mot « lamine » est dans le texte quand c'est le cas.
_GORETEX = re.compile(r"gore.?tex", re.I)
_LAMINE = re.compile(r"lamin[ée]|laminat|\bstratifi[ée]|pro.?shell|3.?couches?|3l\b", re.I)
_ANCRE_MEMBRANE = re.compile(
    r"membranes?|doublure[^.]{0,40}(?:imperm[ée]abl|[ée]tanche)|laminat", re.I
)
_IMPERMEABLE = re.compile(r"imperm[ée]abl|[ée]tanch|waterproof", re.I)
# UN INTITULE DE PARAGRAPHE N'EST PAS UNE AFFIRMATION, et la negation arrive
# APRES. Defaut trouve hier sur les blousons, et il vaut ici mot pour mot :
#
#   « Adapte aux usages urbain et roadster pour des trajets quotidiens et
#     balades routieres NON IMPERMEABLE ET SANS MEMBRANE GORE-TEX, prevoir une
#     protection pluie separee pour roulages sous la pluie »
#
# Le mot « membrane » est la, le mot « Gore-Tex » est la, et le pantalon n'a ni
# l'un ni l'autre. Trois fiches sortaient « gore-tex » sur la foi de la phrase
# qui dit qu'elles ne le sont pas. Le repli de fin de `_membrane()` etait le
# plus coupable : il cherchait « gore-tex » dans TOUT le texte, sans jamais
# regarder ce qu'on en disait.
_PAS_DE_MEMBRANE = re.compile(
    r"(?:sans|aucune?|d[ée]pourvue?s?\s+de|exempte?s?\s+de|absence\s+de)\s+"
    r"(?:membrane|doublure\s+imperm|gore.?tex)|"
    r"(?:non|pas)\s+imperm[ée]abl|(?:non|pas)\s+[ée]tanche",
    re.I,
)

# --- doublure thermique -------------------------------------------------------
_THERMIQUE = re.compile(
    r"doublure[^.]{0,40}(?:thermique|polaire|chauffante|hiver)|"
    r"(?:thermique|chauffante)[^.]{0,25}amovible|couche chauffante|"
    r"doublure[^.]{0,20}thermo",
    re.I,
)
_AMOVIBLE = r"amovible|d[ée]tachable|d[ée]montable|retirable|2.?en.?1|2in1"
_FIXE = r"\bfixe\b|non amovible|cousue"

# --- saisonnalite -------------------------------------------------------------
#
# Motoblouz ecrit parfois la facette telle quelle — « Saisonnalite toutes
# saisons pour une utilisation polyvalente » — mais dix-huit fois seulement sur
# tout le rayon. Le reste se lit dans la prose ordinaire.
#
# « ETE » TOUT SEUL EST UN PIEGE DE LANGUE FRANCAISE : « ce pantalon a ETE
# concu pour... » est le participe passe du verbe etre, et il est dans une
# fiche sur deux. Le mot nu est donc absent du motif ; on exige « en ete »,
# « saison estivale », « temps chaud ».
_SAISON = [
    ("toutes saisons", r"toutes? (?:les )?saisons|\b4\s?saisons|quatre saisons|"
                       r"4.?seasons|all.?season|toute l.ann[ée]e"),
    ("mi-saison",      r"mi.?saison|demi.?saison|\bmi.saisons?\b|p[ée]riodes? temp[ée]r"),
    ("hiver",          r"\bhivers?\b|hivernal|\bwinter\b|temps froid|grand froid|"
                       r"saison froide|par temps frais"),
    ("ete",            r"\ben [ée]t[ée]\b|l.[ée]t[ée]\b|estival|temps chaud|"
                       r"saison chaude|\bsummer\b|fortes chaleurs|climat chaud"),
]

# --- coupe --------------------------------------------------------------------
#
# Le vocabulaire du marchand, dans son ordre de specificite : skinny avant slim
# (un skinny est un slim tres ajuste, et les deux mots cohabitent), tapered
# avant droite, loose avant regular.
_COUPE = [
    ("skinny",  r"\bskinny\b"),
    ("tapered", r"\btapered?\b|\btaper fit\b|coupe taper\b|fusel[ée]e?\b"),
    ("slim",    r"\bslim\b|coupe ajust[ée]e?\b|coupe cintr[ée]e?\b|pr[èe]s du corps"),
    ("loose",   r"\bloose\b|coupe ample|coupe large|\brelaxed\b|coupe d[ée]contract[ée]e?"),
    ("droite",  r"coupe droite|\bstraight\b"),
    ("regular", r"\bregular\b|coupe standard|coupe confort|coupe classique"),
]

# --- le reste -----------------------------------------------------------------
#
# « mesh » est volontairement absent de la ventilation : c'est le tissu de
# doublure de confort le plus courant du rayon (« Doublure de confort concue en
# mesh 3D »), et il ne dit rien des aerations.
_VENTILATION = re.compile(
    r"ventilation|a[ée]ration|a[ée]r[ée]e?s?\b|prises? d.air|entr[ée]es? d.air|"
    r"air.?vent|flux d.air|zips? d.a[ée]r|perforation",
    re.I,
)
# UNE NEGATION QUI ARRIVE AVANT, et il faut lire TOUTES les occurrences.
#
#   « Une fermeture eclair de connexion permet de relier le pantalon a une
#     veste compatible pour LIMITER LES ENTREES D'AIR et proteger le bas du
#     dos »
#   « Boucles de ceinture compatibles avec connexion blouson pour limiter les
#     entrees d'air en position de conduite »
#
# « entrees d'air » y designe ce que le vetement EMPECHE. Dix-huit fiches
# annoncaient une ventilation sur la phrase qui dit qu'on la bouche — et
# toutes les dix-huit etaient des pantalons de ville sans la moindre aeration.
# La garde doit balayer chaque occurrence : s'arreter a la premiere non niee
# suffirait, mais s'arreter a la PREMIERE tout court ne suffit pas.
_VENTILATION_NIEE = re.compile(
    r"(?:limiter|r[ée]duire|emp[êe]cher|bloquer|[ée]viter|sans|contre)"
    r"[^.]{0,25}$",
    re.I,
)
_ZIP_LIAISON = re.compile(
    r"zip[^.]{0,35}(?:raccord|liaison|connexion|jonction|blouson|veste)|"
    r"fermeture[^.]{0,35}(?:de )?(?:raccord|connexion|liaison)|"
    r"(?:raccorder|relier|connecter|attacher)[^.]{0,35}(?:blouson|veste)|"
    r"connecting zip|fixation blouson",
    re.I,
)
_REFLECHISSANT = re.compile(
    r"r[ée]fl[ée]chissant|r[ée]tro.?r[ée]fl|r[ée]flectif|reflective|scotchlite|"
    r"bandes? r[ée]fl|visibilit[ée] nocturne",
    re.I,
)
_SLIDER = re.compile(r"\bsliders?\b|patins? de genou", re.I)
# « genoux reglables en hauteur » : le point de reglage qui fait qu'une coque
# protege la rotule au lieu du tibia. Le motif tempere `((?!hanche).)` evite
# d'attribuer aux genoux un reglage annonce pour les hanches.
_REGLAGE_HAUTEUR = re.compile(
    r"(?:genoux?|genouill)\w*((?!hanche).){0,70}?(?:r[ée]glabl|ajustabl)\w*\s+en\s+hauteur|"
    r"(?:r[ée]glabl|ajustabl)\w*\s+en\s+hauteur((?!hanche).){0,45}?(?:genoux?|genouill)",
    re.I,
)

# --- ancres de coques ---------------------------------------------------------
#
# On ancre sur la PIECE DU CORPS, pas sur le mot « protection » : c'est la seule
# facon de ne pas attribuer aux genoux ce qui est dit des hanches, et
# reciproquement. Le coccyx et le tibia ne sont pas extraits, mais ils sont
# ancres quand meme : ils servent de BORNE aux fenetres des deux autres.
#
#   « ...aux genoux, ajustablesProtections des hanches optionnellesPoche pour
#     protection du coccyx optionnelle »
#
# Sans borne, la fenetre des genoux atteint « optionnelles » et annonce des
# genouilleres en option qui sont fournies. Motoblouz aplatit son HTML sans le
# moindre separateur : la borne EST le separateur.
_ANCRE_GENOU = (r"(?:protections?|protecteurs?|coques?|prot[èe]ge|plaques?)[^.]{0,40}genoux?|"
                r"genouill[èe]res?|prot[èe]ge.genoux?")
_ANCRE_HANCHE = (r"(?:protections?|protecteurs?|coques?|poches?|plaques?)[^.]{0,40}hanches?|"
                 r"hip\s+protect")
# LA BORNE DOIT COMMENCER OU COMMENCE LA PHRASE, PAS OU TOMBE LE MOT.
#
# Defaut trouve en relisant, et c'est la negation qui arrive APRES :
#
#   « Protections souples genoux et hanches SAS-TEC certifiees CE EN 1621-1
#     Poche pour protection du coccyx optionnelle »
#   « Protections aux hanches, certifiees CE EN 1621-1:2012 Predispose a
#     recevoir la protection coccyx »
#
# Les deux pantalons ont leurs coques de hanches dans le carton. Ancre sur le
# seul mot « coccyx », la borne laissait « Poche pour protection du » et
# « Predispose a recevoir la » DANS la fenetre des hanches, et les deux
# ressortaient « prepare ». La borne prend donc toute la phrase du coccyx,
# son verbe de preparation compris.
_ANCRE_AUTRE = (
    r"(?:pr[ée]dispos\w*|pr[ée]par\w*|compatible)[^.]{0,30}?"
    r"(?:coccyx|tibias?|[ée]paules?|coudes?|dorsales?)|"
    r"(?:protections?|protecteurs?|coques?|poches?|plaques?|prot[èe]ge)[^.]{0,40}?"
    r"(?:coccyx|tibias?|[ée]paules?|coudes?|dorsales?)|"
    r"coccyx|tibias?|[ée]paules?|coudes?|dorsale?s?|dos\b"
)
_ANCRES = re.compile(f"({_ANCRE_GENOU})|({_ANCRE_HANCHE})|({_ANCRE_AUTRE})", re.I)

# UNE POCHE EST VIDE. C'EST SA DEFINITION.
#
# LE defaut du rayon, et il ne se voyait dans aucun total : l'ancre des hanches
# accepte « poches? ... hanches? », et le silence autour d'elle valait
# « fourni ». 306 lectures de hanches sur 2 467 ont une POCHE pour ancre, et
# les voici telles que les marchands les ecrivent :
#
#   « Poches pouvant accueillir des protections hanches »        -> prepare
#   « Poches interieures sur les genoux et les hanches »         -> prepare
#   « Poches de protecteur sur les hanches »                     -> prepare
#   « Une poche supplementaire pour armure de hanche homologuee CE » -> prepare
#   « Poche interieure a la zone des hanches pour y ranger des cles » -> RIEN
#   « Deux poches cargo, deux poches hanches et une poche arriere »   -> RIEN
#
# Les six ressortaient « fournies ». Les deux dernieres ne parlent meme pas de
# protection : ce sont une poche a cles et des poches cargo, et l'extracteur en
# faisait des coques de hanches livrees avec le pantalon.
#
# Deux regles donc, et elles vont toutes les deux dans le sens de la prudence :
#   * une poche qui ne NOMME aucune protection ne dit rien — `None` ;
#   * une poche qui en nomme une est VIDE par defaut — il faut un « inclus »
#     explicite pour la remplir, et non l'inverse.
_ANCRE_EST_UNE_POCHE = re.compile(r"poch|logement|emplacement", re.I)
_POCHE_NOMME_UNE_PROTECTION = re.compile(
    r"protect|prot[èe]ge|coques?|armures?|genouill[èe]res?", re.I
)
# On coupe aussi aux vraies frontieres de phrase quand le marchand en met :
# FC-Moto ecrit en liste a puces, et chaque puce est une affirmation autonome.
_FRONTIERE = re.compile(r"[.;•\n]|\s\*\s")


@dataclass
class Pantalon:
    """Ce qu'on a su lire. `None` partout ou on n'a pas su — jamais une valeur
    par defaut, qui se confondrait avec une mesure."""

    categorie: str | None = None              # jean / pantalon / sur-pantalon / legging...
    univers: str | None = None                # touring / trail / sport / custom / cross...
    genre: str | None = None                  # homme / femme / enfant / mixte
    matiere: str | None = None                # facette grossiere : denim / cuir / textile...
    matiere_nommee: str | None = None         # facette fine, LUE : armalith / kevlar...
    matiere_renforcee: str | None = None      # 'oui' ou 'non' ; None = non communique
    renfort_aramide: bool | None = None
    etendue_aramide: str | None = None        # 'zones' ou 'complete'
    homologation: str | None = None           # EN 17092 : AAA / AA / A / B / C
    coques_genoux: str | None = None          # 'fourni' ou 'prepare'
    niveau_genoux: int | None = None          # EN 1621-1 : 1 ou 2
    coques_hanches: str | None = None         # 'fourni' ou 'prepare'
    niveau_hanches: int | None = None
    genouilleres_reglables: bool | None = None
    emplacement_slider: bool | None = None
    membrane: str | None = None               # 'gore-tex' / 'gore-tex lamine' / 'membrane'
    doublure_thermique: str | None = None     # 'amovible' / 'fixe' / 'presente'
    saison: str | None = None                 # toutes saisons / mi-saison / hiver / ete
    coupe: str | None = None                  # skinny / slim / tapered / loose / droite...
    ventilation: bool | None = None
    zip_liaison: bool | None = None
    reflechissant: bool | None = None
    sources: list[str] = field(default_factory=list)

    _CHAMPS = ("categorie", "univers", "genre", "matiere", "matiere_nommee",
               "matiere_renforcee", "renfort_aramide", "etendue_aramide",
               "homologation", "coques_genoux", "niveau_genoux",
               "coques_hanches", "niveau_hanches", "genouilleres_reglables",
               "emplacement_slider", "membrane", "doublure_thermique",
               "saison", "coupe", "ventilation", "zip_liaison", "reflechissant")

    def renseignees(self) -> int:
        return sum(1 for c in self._CHAMPS if getattr(self, c) is not None)


# --- les fenetres -------------------------------------------------------------

def _fenetre(t: str, debut: int, fin: int,
             avant: int = 60, apres: int = 60) -> tuple[str, int]:
    """La phrase AUTOUR d'une detection, bornee des deux cotes.

    Bornee par, dans l'ordre : les autres ancres de coques (parce que Motoblouz
    n'ecrit aucun separateur entre deux affirmations), puis les vraies frontieres
    de phrase (parce que FC-Moto en ecrit, et que chaque puce est autonome).

    Rend la fenetre ET la position de l'ancre dans la fenetre, parce que la
    garde qui suit a besoin de mesurer des distances.
    """
    g, d = max(0, debut - avant), min(len(t), fin + apres)

    for m in _ANCRES.finditer(t):
        if m.end() <= debut and m.start() != debut:
            g = max(g, m.end())
        elif m.start() >= fin:
            d = min(d, m.start())
            break

    gauche, droite = t[g:debut], t[fin:d]
    coupes = [m.end() for m in _FRONTIERE.finditer(gauche)]
    if coupes:
        gauche = gauche[coupes[-1]:]
    coupe = _FRONTIERE.search(droite)
    if coupe:
        droite = droite[:coupe.start()]
    return gauche + t[debut:fin] + droite, len(gauche)


def _prepare_ou_fourni(fen: str, position: int, defaut: str = "fourni") -> str:
    """« Prepare pour » n'est pas « fourni », et c'est LE piege du rayon.

    Transpose de `casque.py`, avec une difference qui a ete payee en relisant :
    ici les deux marqueurs cohabitent DANS LA MEME PHRASE, et c'est le PLUS
    PROCHE de l'ancre qui dit la verite.

        « Protections de hanches SEESMART RV33 CE-niveau 1 (en option) et
          inclut des protections de genoux SEESMART CE-niveau 1 RV36 »

    Une garde qui cherche « en option » n'importe ou dans la fenetre annonce
    ici les deux coques en option. Les genoux sont pourtant dans le carton :
    « inclut » est a onze signes de l'ancre, « en option » a trente-trois.

    Quand aucun des deux marqueurs n'est la, on rend `defaut`, qui vaut
    « fourni » : sur ce rayon, citer une genouillere sans reserve veut dire
    qu'elle est dans le carton, et les marchands ecrivent TOUJOURS la reserve
    quand il y en a une. Verifie en relisant 22 fenetres muettes tirees au
    sort : « Protections hanches homologuees CE niveau 1 », « Coques de
    protections hanches et genoux homologuees CE niveau 1 » — les 22 etaient
    bien fournies.

    L'appelant RENVERSE ce defaut quand l'ancre est une POCHE, parce qu'une
    poche est vide par definition. Voir `_ANCRE_EST_UNE_POCHE`.
    """
    def distance(motif: str) -> int | None:
        d = None
        for m in re.finditer(motif, fen, re.I):
            ecart = 0 if m.start() <= position <= m.end() else min(
                abs(m.start() - position), abs(m.end() - position))
            d = ecart if d is None else min(d, ecart)
        return d

    dp, df = distance(_PREPARE), distance(_FOURNI)
    if dp is None and df is None:
        return defaut
    if dp is None:
        return "fourni"
    if df is None:
        return "prepare"
    return "fourni" if df < dp else "prepare"


def _span_de_la_coque(t: str, debut: int, longueur: int = 95) -> str:
    """Du debut de l'ancre jusqu'a l'ancre suivante, et pas plus loin.

    Le NIVEAU se lit vers l'avant, jamais vers l'arriere, et il faut le dire :

        « Protections de genoux impacTec certifiees selon la norme
          EN 1621-1:2012 niveau 2 [...] Protections de hanches impacTec
          certifiees selon la norme EN 1621-1:2012 niveau 1 »

    Une fenetre symetrique autour de l'ancre « hanches » remonte jusqu'au
    « niveau 2 » des genoux et annonce des coques de hanches de niveau 2 que le
    marchand n'a jamais ecrites. Le niveau suit toujours la piece qu'il
    qualifie ; on ne lit donc que vers l'avant, jusqu'a la piece suivante.
    """
    fin = min(len(t), debut + longueur)
    for m in _ANCRES.finditer(t):
        if m.start() > debut:
            fin = min(fin, m.start())
            break
    bout = t[debut:fin]
    coupe = _FRONTIERE.search(bout)
    return bout[:coupe.start()] if coupe else bout


def _coques(t: str, ancre: str) -> tuple[str | None, int | None]:
    """L'etat d'une coque et son niveau EN 1621-1, lus dans SA fenetre a elle."""
    m = re.search(ancre, t, re.I)
    if not m:
        return None, None

    # L'ancre est-elle une POCHE ? Alors elle est vide jusqu'a preuve du
    # contraire — et si elle ne nomme aucune protection, elle ne parle pas de
    # coques du tout : c'est une poche a cles ou une poche cargo.
    if _ANCRE_EST_UNE_POCHE.search(m.group(0)):
        # On cherche la protection dans l'ancre ET dans les trente-cinq signes
        # qui la suivent : « Poches prevues aux genoux et aux hanches POUR
        # ACCUEILLIR DES PROTECTIONS amovibles » nomme la coque apres la piece,
        # et « Poche interieure a la zone des hanches POUR Y RANGER DES CLES »
        # n'en nomme aucune ni avant ni apres. Trente-cinq, parce qu'au-dela on
        # attrape la phrase suivante, qui parle d'autre chose.
        if not _POCHE_NOMME_UNE_PROTECTION.search(t[m.start():m.end() + 35]):
            return None, None
        defaut = "prepare"
    else:
        defaut = "fourni"

    fen, pos = _fenetre(t, m.start(), m.end())
    etat = _prepare_ou_fourni(fen, pos, defaut)

    niveau = None
    # LA LONGUEUR SE COMPTE DEPUIS LA PIECE, PAS DEPUIS LE MOT « PROTECTION ».
    #
    # L'ancre peut demarrer bien avant la piece qu'elle nomme : dans
    # « ...pour une PROTECTION localisee Protections de HANCHES impacTec
    # certifiees selon la norme EN 1621-1:2012 niveau 1 », elle demarre sur un
    # « protection » qui appartient a la phrase des genoux, et mange 43 des 95
    # signes de la fenetre. Le « niveau 1 » des hanches tombait juste apres la
    # borne, et se perdait en silence — niveau_hanches ne couvrait que 5,7 %
    # du rayon contre 12,2 % pour les genoux, alors que les marchands ecrivent
    # les deux dans la meme phrase. On donne donc a la fenetre les 95 signes
    # APRES l'ancre, quelle que soit la longueur de celle-ci.
    n = _NIVEAU_COQUE.search(_span_de_la_coque(t, m.start(),
                                               95 + m.end() - m.start()))
    if n:
        niveau = {"1": 1, "2": 2, "I": 1, "II": 2}.get(n.group(1).upper())
    return etat, niveau


# --- la matiere ---------------------------------------------------------------

def _zone_tissu(t: str) -> str:
    """La section « Matiere » quand elle existe, tout le texte sinon.

    Motoblouz ecrit « Matiere: ... Doublure: ... Protections: ... ». Restreindre
    la recherche du tissu principal a la premiere section est ce qui empeche de
    lire la doublure comme l'exterieur.
    """
    m = _SECTION_MATIERE.search(t)
    if not m:
        return t
    reste = t[m.end():]
    fin = _SECTION_SUIVANTE.search(reste)
    zone = reste[:fin.start()] if fin else reste
    return zone if zone.strip() else t


def _matieres_lues(zone: str, cuir_annonce: bool) -> list[str]:
    """Les matieres du tissu principal, dans l'ordre du texte de reference.

    On ecarte une occurrence dont les quarante-cinq signes precedents parlent
    d'une autre piece — doublure, renfort, empiecement, genou, fessier. Comme
    `_calotte()` dans `casque.py` ecarte la visiere, et pour la meme raison.

    LE CUIR A DROIT A UNE GARDE DE PLUS, et elle a ete ajoutee en relisant.
    La liste de pieces n'attrape pas tout, parce que les marchands citent le
    cuir au fil de la phrase :

        « Bouclier thermique en cuir extra long »            <- pantalon cross
        « materiel stretch et cuir de categorie superieure » <- pantalon cross
        « Version standard pour les combinaisons en cuir »   <- sliders de genoux

    Les trois annoncaient un pantalon de cuir, et le cuir double le prix d'une
    fiche. On exige donc que le cuir soit la matiere ANNONCEE : citee dans le
    titre, ou en tete de la section « Matiere » — « En cuir de vachette pleine
    fleur », « Cuir de vachette souple 1,1-1,3 mm ». Cite au milieu d'un
    paragraphe, c'est un empiecement, et on ne le lit pas.
    """
    trouvees: list[tuple[int, str]] = []
    for nom, motif in _MATIERE:
        for m in re.finditer(motif, zone, re.I):
            avant = zone[max(0, m.start() - 45):m.start()]
            if re.search(_PIECE_QUI_N_EST_PAS_LE_TISSU, avant, re.I):
                continue
            if nom == "cuir" and not cuir_annonce and m.start() > 60:
                continue
            trouvees.append((m.start(), nom))
            break
    trouvees.sort()
    return [nom for _, nom in trouvees]


# --- homologation -------------------------------------------------------------

def _homologation(t: str) -> str | None:
    """La classe EN 17092, ou rien.

    Quatre ecritures cohabitent en rayon et on les lit toutes ; mais quand deux
    d'entre elles se CONTREDISENT dans le meme texte, on abandonne. Deux
    affirmations opposees sur une donnee de securite ne valent pas mieux
    qu'aucune affirmation — c'est la regle que `fusionner()` applique entre deux
    marchands, appliquee ici entre deux phrases d'un meme marchand.
    """
    trouvees: set[str] = set()

    for m in _EN_PARTIE.finditer(t):
        trouvees.add(_PARTIE_VERS_CLASSE[m.group(1)])

    for motif in (_EN_LETTRE, _CLASSE, _CE_CLASSE, _HOMOLOGUE_NIVEAU):
        for m in motif.finditer(t):
            # « type A » / « type B » designent un PROTECTEUR EN 1621-1, jamais
            # une classe de vetement. Voir `_NIVEAU_N_EST_PAS_UNE_CLASSE`.
            avant = t[max(0, m.start(1) - 12):m.start(1) + 2]
            if re.search(_NIVEAU_N_EST_PAS_UNE_CLASSE, avant, re.I):
                continue
            trouvees.add(m.group(1).upper())

    return trouvees.pop() if len(trouvees) == 1 else None


# --- membrane -----------------------------------------------------------------

def _membrane(t: str) -> str | None:
    """Une membrane IMPERMEABLE, et nommee quand le texte la nomme.

    « Membrane coupe-vent » n'est pas une membrane impermeable, et c'est une
    vraie phrase du rayon. On exige donc l'impermeabilite dans la meme fenetre.
    Et une membrane maison n'est pas un Gore-Tex : valeur generique par defaut,
    comme « thermoplastique » sur le rayon casque.
    """
    generique = False
    for m in _ANCRE_MEMBRANE.finditer(t):
        fen = t[max(0, m.start() - 80):m.end() + 80]
        # La negation est dans la MEME fenetre que l'ancre, et elle prime.
        if _PAS_DE_MEMBRANE.search(fen):
            continue
        if _GORETEX.search(fen):
            return "gore-tex lamine" if _LAMINE.search(fen) else "gore-tex"
        if _IMPERMEABLE.search(fen):
            generique = True
    # Le repli sur tout le texte : il ne s'autorise que si le texte ne dit
    # nulle part le contraire. « Sans membrane Gore-Tex » est du Gore-Tex dans
    # une recherche de mot, et l'inverse d'un Gore-Tex dans une phrase.
    if _GORETEX.search(t) and not _PAS_DE_MEMBRANE.search(t):
        return "gore-tex"
    return "membrane" if generique else None


# --- univers ------------------------------------------------------------------

def _univers(t: str) -> str | None:
    """L'univers de pratique, et seulement quand il est ACCOLE au vetement.

    Hors de la fenetre qui suit « pantalon » ou « jean », les memes mots sont du
    decor de vente. Voir le commentaire de `_UNIVERS` : « racing » est un nom de
    marque sur ce rayon, pas un usage.
    """
    fenetres = [t[m.start():m.end() + 45] for m in re.finditer(_ANCRE_UNIVERS, t, re.I)]
    if not fenetres:
        return None
    for nom, motif in _UNIVERS:
        for fen in fenetres:
            if re.search(motif, fen, re.I):
                return nom
    return None


def _ventilation(t: str) -> bool:
    """Au moins une mention d'aeration qui ne soit pas celle qu'on bouche.

    On parcourt TOUTES les occurrences : une garde qui s'arrete a la premiere
    rate la phrase d'aeration quand le texte commence par celle du zip de
    raccordement, et inversement. Voir `_VENTILATION_NIEE`.
    """
    for m in _VENTILATION.finditer(t):
        if not _VENTILATION_NIEE.search(t[max(0, m.start() - 35):m.start()]):
            return True
    return False


def _premier(liste, texte: str) -> str | None:
    for nom, motif in liste:
        if re.search(motif, texte, re.I):
            return nom
    return None


# --- lecture ------------------------------------------------------------------

def lire(titre: str, description: str) -> Pantalon:
    """Lit un pantalon dans le texte d'un marchand.

    Le titre est concatene a la description : la moitie du rayon ne porte la
    categorie et le genre que dans le titre (« Sur-pantalon Held WET TOUR
    PANT », « Jean Moto Rev it SHELBY 2 LADIES »), et FC-Moto met parfois
    l'impermeabilite la et nulle part ailleurs.
    """
    t = " ".join(((titre or "") + " " + (description or "")).split())
    p = Pantalon()
    if not t:
        return p

    titre_seul = " ".join((titre or "").split())

    p.categorie = _premier(_CATEGORIE, titre_seul) or _premier(_CATEGORIE, t)
    p.genre = _premier(_GENRE, titre_seul) or _premier(_GENRE, t)
    p.univers = _univers(t)

    # --- matiere, sur ses deux facettes ---
    cuir_annonce = bool(re.search(r"\bcuirs?\b|\bleather\b", titre_seul, re.I))
    matieres = _matieres_lues(_zone_tissu(t), cuir_annonce)
    if matieres:
        p.matiere_nommee = matieres[0]
        grossieres = {_MATIERE_GROSSIERE[m] for m in matieres}
        if grossieres == {"cuir", "textile"} or grossieres == {"cuir", "denim"}:
            # La facette du marchand a cette valeur-la, et elle est utile :
            # un pantalon cuir a larges panneaux textiles ne se porte pas
            # comme un cuir integral.
            p.matiere = "cuir et textile"
        else:
            p.matiere = _MATIERE_GROSSIERE[matieres[0]]

    if _RENFORT_NON.search(t):
        p.matiere_renforcee = "non"
    elif _RENFORT_OUI.search(t):
        p.matiere_renforcee = "oui"

    p.homologation = _homologation(t)
    p.membrane = _membrane(t)

    m = _ARAMIDE.search(t)
    if m:
        p.renfort_aramide = True
        fen = t[max(0, m.start() - 70):m.end() + 70]
        if re.search(_ARAMIDE_COMPLETE, fen, re.I):
            p.etendue_aramide = "complete"
        elif re.search(_ARAMIDE_ZONES, fen, re.I):
            p.etendue_aramide = "zones"
        # Sinon : on sait qu'il y a de l'aramide, on ne sait pas ou. `None`.

    p.coques_genoux, p.niveau_genoux = _coques(t, _ANCRE_GENOU)
    p.coques_hanches, p.niveau_hanches = _coques(t, _ANCRE_HANCHE)

    m = _THERMIQUE.search(t)
    if m:
        fen = t[max(0, m.start() - 20):m.end() + 40]
        if re.search(_AMOVIBLE, fen, re.I):
            p.doublure_thermique = "amovible"
        elif re.search(_FIXE, fen, re.I):
            p.doublure_thermique = "fixe"
        else:
            p.doublure_thermique = "presente"

    # La saisonnalite, quand le marchand ecrit la facette telle quelle, gagne
    # sur la prose : « Saisonnalite toutes saisons » est une affirmation du PIM,
    # le reste est une tournure.
    facette = re.search(r"Saisonnalit[ée]\s*([^.]{0,30})", t, re.I)
    p.saison = _premier(_SAISON, facette.group(1)) if facette else None
    if p.saison is None:
        chaudes = [nom for nom, motif in _SAISON if re.search(motif, t, re.I)]
        # « hiver » ET « ete » dans le meme texte sans « toutes saisons » : le
        # marchand parle de deux configurations, pas d'une saison. On se tait.
        if chaudes[:1] and not ({"hiver", "ete"} <= set(chaudes)):
            p.saison = chaudes[0]

    p.coupe = _premier(_COUPE, t)

    if _REGLAGE_HAUTEUR.search(t):
        p.genouilleres_reglables = True
    if _SLIDER.search(t):
        p.emplacement_slider = True

    # Ces trois-la n'ont pas de version « preparee » : un pantalon a des
    # aerations ou n'en a pas. On rend donc True, ou None — jamais False, qui
    # pretendrait que le texte AFFIRME l'absence. Il ne l'affirme jamais ; il
    # se tait. Speedway se tait sur soixante-quinze signes.
    if _ventilation(t):
        p.ventilation = True
    if _ZIP_LIAISON.search(t):
        p.zip_liaison = True
    if _REFLECHISSANT.search(t):
        p.reflechissant = True

    return p


def fusionner(lectures: list[Pantalon]) -> Pantalon:
    """Une fiche, plusieurs marchands : on reunit ce que chacun a su dire.

    La premiere valeur trouvee gagne, et l'ordre d'appel fait la priorite —
    l'appelant passe les marchands du plus riche au plus pauvre. Sur un
    desaccord franc d'homologation, on ABANDONNE la valeur, exactement comme
    `casque.fusionner()` le fait pour l'ECE : deux sources qui se contredisent
    sur une donnee de securite ne valent pas mieux qu'aucune source.

    Le statut des coques obeit a la meme regle, et pour une raison de terrain :
    un marchand qui vend le pantalon « avec coques hanches » et un autre qui le
    vend « predispose » ne decrivent pas le meme carton. Promettre la piece est
    la faute la plus chere du rayon ; on prefere ne rien promettre.
    """
    out = Pantalon()
    arbitres = ("homologation", "coques_genoux", "coques_hanches")

    for champ in Pantalon._CHAMPS:
        if champ in arbitres:
            continue
        for l in lectures:
            if getattr(l, champ) is not None:
                setattr(out, champ, getattr(l, champ))
                break

    for champ in arbitres:
        valeurs = {getattr(l, champ) for l in lectures if getattr(l, champ) is not None}
        if len(valeurs) == 1:
            setattr(out, champ, valeurs.pop())

    return out
