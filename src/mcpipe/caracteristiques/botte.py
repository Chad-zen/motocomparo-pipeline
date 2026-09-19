"""Ce qu'on peut dire d'une botte ou d'une chaussure moto, à partir des flux.

POURQUOI CE FICHIER EXISTE. Même raison que pour les casques : le configurateur
a besoin de caractéristiques, et le catalogue n'en porte aucune. Le rayon
« Bottes & chaussures » (catégorie 9) compte 6 088 fiches, dont 6 030 portent au
moins une description marchande.

CE QU'ON A MESURÉ AVANT D'ÉCRIRE (18/09/2026), et c'est ce qui décide tout :

    source        fiches   description médiane
    motoblouz      1 867        724 signes
    fcmoto         3 385        154 signes
    speedway         734         78 signes
    labecanerie    2 057         86 signes
    maxxess          222        467 signes
    motoaxxe         230        439 signes

Motoblouz est encore la seule source vraiment bavarde, mais le rapport de force
n'est PAS celui des casques : FC-Moto couvre presque deux fois plus de fiches
que Motoblouz. Sa prose est courte et en listes à puces, mais d'une régularité
remarquable sur la seule chose qui compte vraiment ici :

    «  *  Chaussures de protection pour motocyclistes, EN 13634:2017 »

C'est une phrase de catalogue, écrite à l'identique sur des milliers de fiches.

Motoblouz, lui, écrit en sections nommées, toujours dans le même ordre :

    Matière: … Doublure: … Protections: … Les "+": … Sécurité et normes …

Cette structure est la clef de la MATIÈRE : elle dit de quelle PIÈCE chaque
matière parle, ce qu'aucune autre source ne fait.

CE QU'ON CHERCHE, ET DANS QUEL ORDRE. Les facettes que Motoblouz publie sur ce
rayon : matière (cuir / cuir et textile / synthétique / textile), catégorie
(bottes / demi-bottes / baskets moto / chaussettes), univers de pratique, genre,
Gore-Tex, et quatre options (imperméable, malléole, sélecteur, tibia). On s'y
cale, y compris sur son vocabulaire : un comparateur qui nomme ses filtres
autrement que les marchands qu'il compare se condamne à traduire.

On garde EN PLUS l'homologation EN 13634 et ses quatre indices, que Motoblouz
n'expose pas : c'est le premier critère de sécurité du rayon, et c'est
exactement là qu'un comparateur peut faire mieux que le marchand.

CE QU'ON NE TROUVERA PAS ICI, et il faut le dire une fois pour toutes :
L'UNIVERS DE PRATIQUE N'EST PAS DANS LES FLUX. On l'a cherché partout — titres,
descriptions, et la colonne `category` des six flux, qui porte la taxonomie du
marchand. Résultat de cette recherche, à garder :

    motoblouz    'Bottes et Baskets Moto Homme' (7 407) · 'Bottes Motocross'
                 (2 900) · 'Baskets' · 'Bottes' · 'Bottes et Demi bottes'
    labecanerie  'Équipement route > Botte moto > Botte route' · 'Équipement
                 Cross > Botte cross > Botte de cross' · 'Botte piste' · …
    maxxess      'Equipement du motard > Baskets et Bottes > Baskets moto'
    speedway     'Bottes et chaussures' — et rien d'autre

Aucun flux ne porte les huit valeurs (custom, enduro, roadster, scooter, sport,
supermotard, touring, trail). Ce qu'ils portent, c'est un partage ROUTE / CROSS,
et le genre. On lit donc l'univers dans la prose, avec une ancre d'usage, et on
l'annonce pour ce qu'il est : à peu près une fiche sur cinq, dont l'essentiel
est le cross lu dans le titre. Le reste tient en trois points de couverture.
Deviner les cinq sixièmes manquants à partir de la marque ou du prix aurait
donné un configurateur qui se trompe de profil ; il vaut mieux un axe honnête et
incomplet, qu'on complétera le jour où le marchand exposera sa facette.

(La colonne `category` est d'ailleurs hors de portée de ce module : `lire()` ne
reçoit que le titre et la description. La brancher demanderait de toucher
`__init__.py`, ce qui n'est pas de ce ressort.)

LA RÈGLE QUI GOUVERNE TOUT LE FICHIER
=====================================
En cas de doute, on rend `None`. Un `None` n'écrit aucune ligne en base. Une
caractéristique absente coûte un filtre moins précis ; une caractéristique
fausse coûte la confiance — et sur une botte, la caractéristique la plus
demandée est une donnée de sécurité. On ne devine jamais à partir du prix, de la
marque ni de la catégorie.

CE RAYON A UN PIÈGE QUE LE RAYON CASQUE N'AVAIT PAS : une botte est un assemblage
de huit pièces, et les marchands les décrivent TOUTES dans le même paragraphe.
Tige, semelle extérieure, semelle intérieure, doublure, renfort de malléole,
plaque de tibia, sélecteur, soufflet, guêtre. « Semelle en caoutchouc » ne dit
rien de la matière de la chaussure ; « doublure en cuir de vachette » non plus ;
et « tige en acier intégrée » parle d'une lame de renfort DANS LA SEMELLE.
Chaque motif de matière est donc testé contre la pièce dont il parle, et rend
`None` quand le texte ne le dit pas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Le vocabulaire de la PRÉPARATION, importé du rayon casque et non recopié.
#
# Il a coûté cher — cinq casques sur cinq annoncés « intercom fourni » alors que
# les cinq disaient « prédisposé à recevoir » — et il n'y a aucune raison qu'il
# diverge d'un rayon à l'autre. Une deuxième liste finirait par oublier un mot
# que la première connaît, et elle le ferait en silence.
#
# Le rayon botte a sa propre occurrence, trouvée en lisant :
#     « Patte arrière afin de faciliter l'enfilage Tige haute
#       Protège sélecteur DXR EN OPTION »
# Sans garde, cette botte-là annonce une protection de sélecteur qu'elle n'a pas.
from .casque import _PREPARE

# --- ce que le marchand écrit pour dire QU'IL N'Y EN A PAS ---------------------
#
# LE DÉFAUT QUI A COÛTÉ LE PLUS CHER DE CE FICHIER, et il n'était pas prévu :
# Motoblouz publie, sur une partie de son catalogue, une prose générée qui
# ANNONCE LES ABSENCES aussi explicitement que les présences, et dans les mêmes
# sections. Cinq phrases réelles, toutes relues dans l'échantillon :
#
#   « Imperméabilité et étanchéité — Construction imperméable […] ABSENCE DE
#     MEMBRANE GORE-TEX indiquée, vérifiez les limitations d'étanchéité »
#   « Version été AIR SANS MEMBRANE ÉTANCHE »                          (FC-Moto)
#   « Les + […] NON ÉTANCHE, ce qui signifie qu'il ne protège pas de la pluie »
#   « PRODUIT NON IMPERMÉABLE, éviter l'exposition prolongée à la pluie »
#   « Construction NON ÉTANCHE — Idéal pour les conditions sèches et estivales »
#   « PAS DE RENFORT TIBIAL intégré et sliders non remplaçables »
#
# La première est le cas d'école : la botte ressortait `gore_tex = True` sur la
# foi de la phrase qui dit qu'elle n'a pas de Gore-Tex. La dernière ressortait
# `protection_tibia = True`. Aucune ne se voyait dans un total : elles faisaient
# toutes MONTER la couverture.
#
# LA FENÊTRE EST COURTE, ET C'EST TOUT LE SUJET. Le même rayon écrit « sans »
# quinze fois par fiche pour dire l'inverse d'une absence :
#     « une protection ciblée SANS trop rigidifier la tige »
#     « une meilleure ventilation SANS compromettre la protection »
#     « porter les chaussures hors moto SANS sacrifier l'intégration des
#       protections »
# Une garde large aurait effacé ces protections-là, et aurait fait BAISSER la
# couverture — le seul type d'erreur qu'un total finit par trahir, mais après
# coup. On exige donc que la négation soit COLLÉE au mot qu'elle nie : elle, au
# plus un mot, puis le mot nié. « sans compromettre la protection » en compte
# deux, et passe.
_NEGATION = (r"(?:\bsans\b|\bnon\b|\bni\b|\baucune?\b|absence d[e']|"
             r"\bpas d[e']|d[ée]pourvue?s? d[e']|exemptes? d[e']|"
             r"d[ée]nu[ée]e?s? d[e'])")

# …et les mots qui, derrière « sans », n'annoncent aucune absence de pièce. Ce
# sont des tournures de vente — « sans couture », « sans infiltration », « sans
# compromis » — et elles sont assez fréquentes pour qu'une garde qui les ignore
# efface de vraies protections. « pour rouler par temps de pluie SANS
# INFILTRATION Protection et renforts Protections malléoles intégrées » est le
# cas exact : la botte a bel et bien ses protections de malléole.
_SANS_QUI_N_EST_PAS_UNE_ABSENCE = (
    r"(?:coutures?|soudures?|infiltrations?|compromis|efforts?|attaches?|"
    r"doutes?|contraintes?|difficult[ée]s?|entraves?|glissements?|lourdeurs?|"
    r"restrictions?|temps|cesse|rel[âa]che|pressions?|bavures?|limites?)")

# Les séparateurs qui ferment une affirmation chez les six marchands : le point
# et le deux-points de Motoblouz, l'astérisque de liste de FC-Moto. Une garde
# qui les franchit lit la phrase d'avant, qui parle d'autre chose — voir
# `_avant()`.
_FIN_DE_PROPOSITION = re.compile(r"[.:;*•!?]")

# --- les pièces d'une botte ---------------------------------------------------
#
# L'équivalent de `_PIECE_QUI_N_EST_PAS_LA_CALOTTE` du rayon casque, en beaucoup
# plus long : un casque a deux pièces en plastique, une botte en a huit.
#
# Trouvé en relisant l'échantillon, les quatre cas qui ont motivé chaque mot :
#   « Doublure entière en cuir de vachette »      -> ce n'est pas la chaussure
#   « Semelle intérieure amovible en PU »         -> ce n'est pas la chaussure
#   « Semelle intermédiaire avec tige ZPLATE »    -> « tige » = lame de torsion
#   « Coque de pied monobloc […] et tige en acier intégrée » -> idem
_PIECE_QUI_N_EST_PAS_LA_TIGE = (
    r"(?:doublure|semelle|assise plantaire|propret[ée]|insert|renfort|"
    r"protection|prot[èe]ge|protecteur|coque|talon|soufflet|gu[êe]tre|"
    r"languette|s[ée]lecteur|boucle|mollet|tibia|mall[ée]ole|cheville|"
    # L'INTÉRIEUR EST UNE PIÈCE, et il manquait. Trouvé en relisant l'Acerbis
    # X-TEAM ENFANT, une botte de cross en microfibre :
    #     « Guêtre et plis tibiaux en MICROFIBRE » … « Inserts structurés en
    #       TPU » … « INTÉRIEUR EN 3D MESH pour un confort supérieur »
    # Les deux premières mentions étaient bien écartées — guêtre, insert — et
    # la troisième ne l'était pas. La botte ressortait « textile » sur la foi
    # de sa doublure, ce qui est le piège du rayon dans sa forme la plus pure.
    # « Matière intérieure :100% polyester », le libellé du bloc Composition de
    # Motoblouz, tombe sous le même mot.
    r"int[ée]rieur|orteil|panneau|empi[èe]cement|face interne|collier|lacet|"
    r"chausson|"
    r"slider|plaque|patch|rembourrage|bouclier|sangle|rabat|patte)"
)

# --- accessoires du rayon -----------------------------------------------------
#
# La catégorie 9 ne contient pas que des bottes. Elle contient aussi les semelles
# de rechange, les sliders, les boucles détachées et les sur-bottes — vus dans
# l'échantillon :
#
#   « Semelle Alpinestars New Tech 7 Noir/Blanc- 9 »
#   « Sidi Atojo SRS Système d'extension Hyper »
#   « Boucle bottes Fox MOTION » / « Cheville Sidi Crossfire 2 Noir »
#   « Chaussons étanches Kenny pour bottes Evasion- 47 »
#
# Sans cette garde, « Chaussons étanches » devenait une botte imperméable. C'est
# le genre de faux positif qui FAIT MONTER la couverture, donc qui se lit comme
# une bonne nouvelle.
#
# Les CHAUSSETTES font exception : Motoblouz les expose comme une valeur de sa
# facette « catégorie », donc elles ont droit à leur ligne — et à rien d'autre.
_ACCESSOIRE = re.compile(
    r"\b(?:sliders?|chaussons?|sur.?bottes?|embauchoirs?|talonnettes?|cirage|"
    r"impr[ée]gnation|semelles?|lacets?|plaque|syst[èe]me d.extension|"
    r"boucle bottes?|cheville sidi|pare.?chaleur|sangles?|"
    # Trouvé en relisant : « Kochmann PROTECTION DE LEVIER DE VITESSES » est un
    # patin de sélecteur vendu seul, et il ressortait en botte de cuir.
    r"protections? de levier|prot[èe]ge.?s[ée]lecteur|"
    r"protections? de s[ée]lecteur|"
    # Trouvés en relisant les exclusions : le rayon vend aussi de quoi faire
    # sécher ses bottes. « Séchoir à bottes BikeTek noir », « Support de lavage
    # Motoblouz séchoir pour bottes ». Ils étaient écartés par `pour bottes`,
    # qui vient de disparaître ; il fallait les rattraper par leur nom.
    r"s[ée]choirs?|supports? de lavage)\b",
    re.I,
)
# LE PIÈGE N°4 DU RAYON CASQUE, EN PLEIN DANS CE FICHIER, et il ne se voyait
# nulle part parce qu'il faisait BAISSER la couverture au lieu de la monter.
#
# `resemel` était écrit sans limite de mot. Motoblouz publie ses sections
# collées, sans espace :
#     « …pour une durabilité supérieureSemelle avec motif de prise… »
#     « …un rabat interne en microfibreSemelle externe amovible… »
# La fin de « microfib-RE » suivie de « SEMEL-le » forme « reSemel », et le
# motif matchait. SOIXANTE-DIX-HUIT bottes réelles — des TECH 7, des TECH 10,
# des Sidi AGUEDA — étaient rendues VIDES, traitées comme des semelles de
# rechange. Aucun total ne le disait : la fiche existait, elle n'avait
# simplement aucune caractéristique.
#
# `pour bottes` était l'autre moitié du dégât, dans l'autre sens : la phrase de
# norme du rayon est « certifié CE selon la norme EN 13634 POUR BOTTES MOTO ».
# Elle décrit la botte, pas une pièce vendue pour une botte. On exige donc le
# vocabulaire de la compatibilité — « Compatible avec les bottes Instinct » —
# qui est le seul à dire qu'on parle d'un accessoire.
_RECHANGE = re.compile(
    r"pi[èe]ces? (?:de rechange|d[ée]tach[ée]es)|de rechange officielle|"
    r"\bresemel|"
    r"(?:compatibles?|adapt[ée]e?s?|con[çc]ue?s?|utilisables?|remplacements?)"
    r"[^.]{0,25}(?:avec|pour|aux?)[^.]{0,15}bottes\b",
    re.I,
)
_CHAUSSETTES = re.compile(r"\b(?:chaussettes?|socquettes?)\b", re.I)

# --- catégorie ----------------------------------------------------------------
#
# LE VOCABULAIRE EST CELUI DU MARCHAND, pas une échelle inventée : bottes,
# demi-bottes, baskets moto, chaussettes. « Demi-botte » et « bottine » sont des
# mots de métier qui veulent dire la même chose, et les marchands les emploient
# au sens propre.
#
# LU DANS LE TITRE, ET DANS LE TITRE SEUL. C'est une décision, pas une facilité :
# les titres de ce rayon sont d'une netteté rare (« Bottes cross … », « Baskets
# Moto … », « Demi-bottes … »), alors que les descriptions parlent d'« usage
# urbain » et de « look décontracté » à propos de n'importe quoi. Chercher la
# catégorie dans la description revenait à lire l'argumentaire au lieu du
# produit.
#
# L'ordre compte : « Demi-bottes » contient « bottes ».
_CATEGORIE = [
    ("chaussettes",  r"\b(?:chaussettes?|socquettes?)\b"),
    ("demi-bottes",  r"demi.?bottes?|\bbottines?\b"),
    ("bottes",       r"\bbottes?\b"),
    ("baskets moto", r"\bbaskets?\b|\bsneakers?\b|\bchaussures?\b"),
]

# --- univers de pratique ------------------------------------------------------
#
# LA CARACTÉRISTIQUE LA PLUS DEMANDÉE ET LA MOINS ÉCRITE. Voir l'en-tête : elle
# n'est dans aucune colonne de flux. Ce qui suit la lit dans la prose, et
# n'atteint qu'une fiche sur cinq — dont l'essentiel est le cross.
#
# DEUX RÉGIMES, parce que les mots n'ont pas tous le même risque.
#
#   Les mots SANS AMBIGUÏTÉ sont lus n'importe où dans le titre : « enduro »,
#   « supermotard », « roadster », « scooter », « touring », « custom »,
#   « motocross » ne désignent jamais autre chose qu'une pratique.
#
#   Les mots AMBIGUS ne sont lus qu'en tête de titre, derrière le nom du
#   produit — « Bottes trial … », « Bottes route … ». Trois pièges réels :
#       « Baskets Alpinestars META TRAIL »      -> un nom de modèle
#       « Inspirées du TRAIL RUNNING »          -> une autre discipline
#       « Semelle extérieure TOURING »          -> une pièce, pas un usage
#   Le premier est un faux positif silencieux : la chaussure est une basket
#   urbaine, et l'annoncer « trail » enverrait l'acheteur aventure sur un modèle
#   qui n'a pas de membrane.
#
# Dans la DESCRIPTION, aucun mot n'est lu sans une ancre d'usage explicite —
# « pour une utilisation Café racer, Custom et Cruiser », « permettant d'utiliser
# les bottes en Cross, Enduro ou Supermotard ». Sans ancre, « conduite sportive »
# et « quartiers sportifs » (sur des chaussettes) auraient fait basculer un
# sixième du rayon en « sport ».
#
# « cross » ne figure pas dans les huit valeurs du marchand. On le garde quand
# même : c'est le plus gros bloc du rayon (2 900 fiches chez Motoblouz sous
# 'Bottes Motocross'), et le taire aurait voulu dire ranger une botte de cross
# en « enduro » ou en rien.
_UNIVERS_SUR = [
    # PAS de « MX » : deux lettres entre limites de mot suffisent à attraper
    # « Sangle micrométrique Sidi ST/MX extra longue », qui est une pièce
    # détachée. C'est la leçon du « ABS » qui matchait « absorption ».
    ("cross",       r"motocross|\bcross\b"),
    ("enduro",      r"\benduro\b"),
    ("supermotard", r"\bsupermotard\b|\bsupermoto\b"),
    ("touring",     r"\btouring\b|grand tourisme"),
    ("roadster",    r"\broadster\b"),
    ("scooter",     r"\bscooter\b"),
    ("custom",      r"\bcustom\b|caf[ée].?racer|\bcruiser\b"),
]
_UNIVERS_AMBIGU = [
    ("trail",  r"\btrail\b(?! ?running)|\badventure\b|\baventure\b"),
    ("sport",  r"\bsportives?\b|\bracing\b|\bpiste\b|\bcircuit\b"),
]
# « Bottes trial Gaerne … », « Bottes route Forma … » : le mot suit le nom du
# produit, c'est là qu'il qualifie le produit et nulle part ailleurs.
_TETE_DE_TITRE = r"(?:bottes?|demi.?bottes?|chaussures?|baskets?|sneakers?)\s+(?:moto\s+)?"
_ANCRE_USAGE = (r"(?:utilisations?|usages?|pratiques?|con[çc]ues? pour|"
                r"destin[ée]e?s? [àa]|adapt[ée]e?s? (?:pour|[àa])|"
                r"id[ée]ale?s? pour|parfaites? pour|pens[ée]e?s? pour|"
                r"utiliser les bottes en)")

# --- genre --------------------------------------------------------------------
#
# Jamais déduit d'un nom de gamme. « Stella » est la ligne femme d'Alpinestars
# et « Lady » celle de plusieurs autres, mais « Stella » seul ne le dit pas à
# l'acheteur : on ne lit que ce qui est écrit en toutes lettres, plus « lady »
# et « women », que les marchands écrivent bel et bien dans les titres.
_GENRE = [
    ("mixte",  r"\bmixtes?\b|\bunisexes?\b"),
    ("femme",  r"\bfemmes?\b|\blady\b|\bladies\b|\bwom[ae]n\b|\bdames?\b|\bfille\b"),
    ("homme",  r"\bhommes?\b|\bmen\b|\bman\b|\bgar[çc]on\b"),
]

# --- matière ------------------------------------------------------------------
#
# PREMIER PLAN, et c'est la facette du marchand : cuir, cuir et textile,
# synthétique, textile. QUATRE VALEURS, pas cinq, pas une par pièce — Motoblouz
# donne UNE matière pour la chaussure entière, et le comparateur doit pouvoir
# être mis en regard.
#
# PIÈGE N°3, deux fois dans la même liste.
#
#   « cuir synthétique » N'EST PAS DU CUIR, et c'est l'inverse d'une nuance :
#     « Anatomiquement pré-formé en CUIR SYNTHÉTIQUE de haute qualité »
#     « réalisée en cuir synthétique de qualité supérieure renforcé PU »
#   Le motif synthétique passe donc AVANT le motif cuir, exactement comme le
#   composite passe avant le carbone chez les casques, et pour la même raison :
#   le mot cher est vrai et trompeur à la fois.
#
#   ET « cuir synthétique » N'EST PAS LA SEULE FORME. Trouvé en relisant, sur la
#   DXR CODE EVO SHORT :
#       « Matière: Tige en CUIR MICROFIBRE SYNTHÉTIQUE, matière solide et
#         durable » … « Composition: Matière extérieure :100% POLYURÉTHANE »
#   Le marchand donne la réponse deux lignes plus bas, et elle contredit ce que
#   l'extracteur lisait : il rendait « cuir », parce que « cuir » est écrit
#   avant « microfibre » et que l'ordre RENDU est celui du texte. Onze
#   occurrences du rayon sont dans ce cas : « cuir microfibre », « cuir PU et
#   microfibre », « Tige en cuir microfibre synthétique aussi résistant que du
#   cuir véritable ». Le mot « cuir » y est un ADJECTIF DE TEXTURE, pas une
#   matière, et il vaut cent euros de fiche.
#   On reconnaît donc le groupe entier — « cuir » suivi de ce qui le nie — au
#   lieu du seul « cuir synthétique ».
#
#   « microfibre » n'est pas du cuir non plus, même quand le marchand explique
#   qu'elle est « aussi résistante que le cuir naturel ». C'est un synthétique,
#   et c'est la matière de la moitié des bottes de cross du rayon.
#
# On ne garde PAS « cuir pleine fleur » comme valeur distincte, bien que les
# marchands l'écrivent : la facette du marchand dit « cuir », et le pleine fleur
# est un sous-genre. C'est le piège n°3 pris dans l'autre sens — rendre le genre
# quand on n'est pas sûr du sous-genre, et rendre le genre aussi quand on en est
# sûr mais que personne ne filtre dessus.
_FAMILLES = [
    ("synthétique", r"cuirs?[\s-]+(?:synth[ée]tiques?|artificiels?|micro.?fibres?|"
                    r"micro.?tech\w*|technomicro\w*|PU\b|polyur[ée]thanes?|"
                    r"[ée]cologiques?|v[ée]ganes?)|"
                    r"simili.?cuir|similicuir|"
                    r"\bsynth[ée]tiques?\b|microfibres?|micro.?fibres?|\bamara\b|"
                    r"\blorica\b|polyur[ée]thane|\bPU\b|\bTPU\b"),
    ("cuir",        r"\bcuirs?\b|vachette|nubuck|nabuk|\bdaim\b|su[ée]d[ée]e?\b|"
                    r"cuir de vache|\baniline\b|pleine fleur|plein grain|"
                    r"cuir bovin|vache\b"),
    ("textile",     r"\btextiles?\b|\bmesh\b|cordura|ripstop|polyester|\btissus?\b|"
                    r"\bnylon\b|\btoile\b|\bcanvas\b|\bmaille\b|\bdenim\b"),
]

# Les ancres qui désignent la TIGE et rien d'autre. Motoblouz et FC-Moto les
# écrivent toutes les deux, avec leurs mots à eux :
#   « Tige en cuir de vachette de qualité supérieure de 2,4 mm »   (fcmoto)
#   « Matériau extérieur principal : Microfibre »                  (fcmoto)
#   « Construction de la tige en microfibre avancée »              (motoblouz)
#   « Enveloppe principale en microfibre »                         (motoblouz)
# LE CUIR QU'ON CITE POUR DIRE QU'IL N'Y EN A PAS. Le rayon a une figure de
# style à lui, et elle est partout chez Bering et RST :
#     « Matière: En microfibre, matière synthétique, réputé pour être
#       AUSSI RÉSISTANT QUE LE CUIR »
#     « En microfibre, matière synthétique reconnue pour être aussi résistante
#       que le cuir naturel »
# Le mot « cuir » y est écrit, et il dit exactement le contraire de ce qu'une
# recherche de mot y lit. On efface donc la comparaison avant de chercher.
_CUIR_DE_COMPARAISON = re.compile(
    r"(?:aussi|plus|autant|moins)[^.]{0,40}?que (?:le |du )?cuir\w*(?: naturel)?|"
    r"comme (?:le |du )cuir\w*|comparable\w* au cuir|"
    r"(?:aspect|effet|toucher|imitation|look) cuir",
    re.I,
)

# Ce qui coupe un fragment de tige : la pièce suivante. « Tige en cuir pour un
# ajustement flexible et un confort * Doublure en maille » donnait « cuir et
# textile » alors que la maille est la DOUBLURE.
_FIN_DU_FRAGMENT = re.compile(_PIECE_QUI_N_EST_PAS_LA_TIGE, re.I)

_ANCRE_TIGE = re.compile(
    r"(?:tige|empeigne|mat[ée]riau ext[ée]rieur(?: principal)?|"
    r"mat[ée]riau principal|enveloppe principale|structure principale|"
    r"construction principale|partie sup[ée]rieure|\bhaut\b)"
    r"[^.]{0,25}?(?:\ben\b|:|\bprincipale?\b)",
    re.I,
)

# La section « Matière: » de Motoblouz, jusqu'à la section suivante. C'est le
# seul endroit du rayon où un marchand dit explicitement « ce qui suit décrit la
# matière extérieure ». Sa borne de fin est « Doublure: », et c'est elle qui
# empêche la doublure de passer pour la chaussure.
_SECTION_MATIERE = re.compile(
    r"Mati[èe]res?\s*:(.{0,400}?)(?:Doublure|Protections?|Les \"?\+|"
    r"Composition|S[ée]curit[ée]|Caract[ée]ristiques|$)",
    re.I | re.S,
)

# --- homologation EN 13634 ----------------------------------------------------
#
# Formes relevées dans l'échantillon, toutes réelles :
#   « EN 13634:2017 » « EN13634 » « prEN 13634:2017 » « FR 13634:2017 »
#   « EN 13634:2015 » « EN 13634:2010 » « certifiées CE selon la norme EN 13634 »
#
# Le nombre 13634 est sans ambiguïté possible dans une description de botte : on
# le cherche seul, avec ses limites de mot, et on ne tente pas de reconstituer
# les six façons de l'introduire.
#
# ET SURTOUT PAS `\b13634\b`. Les limites de mot sont le piège n°4 du rayon
# casque, ici dans sa version sournoise : dans « EN13634-2017 », écrit sans
# espace par O'Neal chez Motoblouz, il n'y a AUCUNE limite de mot entre le « N »
# et le « 1 ». La botte ressortait « CE » — la valeur générique — alors que le
# texte nommait la norme deux lignes plus bas. Un `\b` qui ne se déclenche pas
# ne fait pas d'erreur visible : il rend juste une réponse moins précise, ce
# qu'aucun total ne signale.
#
# On borne donc sur les CHIFFRES, pas sur les mots : une lettre peut coller, un
# chiffre non — « 913634 » ne doit pas passer pour la norme.
_EN13634 = re.compile(r"(?<![0-9])13634(?![0-9])")

# « Homologué CE » tout court est la valeur GÉNÉRIQUE, et ce n'est pas la même
# chose : la norme n'est pas nommée. On la garde — moins précise, vraie — comme
# `thermoplastique` avait été gardé face à `polycarbonate` chez les casques.
_CE = re.compile(
    r"(?:homologu[ée]e?s?|certifi[ée]e?s?|conformes?)[^.]{0,25}\bCE\b|"
    r"\bCE\b[^.]{0,15}(?:EPI|niveau)",
    re.I,
)

# …mais le CE d'une PROTECTION n'est pas le CE de la botte, et c'est le piège
# n°2 appliqué à l'homologation :
#     « Protections malléoles D3O HOMOLOGUÉES CE »
#     « Renfort Malléole homologué IPA »
#     « Tige en acier renforcé et certifié CE »
# Aucune de ces trois phrases ne dit que la CHAUSSURE est homologuée. Deux des
# trois bottes concernées le disaient ailleurs, avec le numéro de norme ; la
# troisième ne le disait pas, et elle rend donc `None`.
_CE_D_UNE_PIECE = re.compile(
    r"(?:mall[ée]ole|cheville|protections?|prot[èe]ge|renforts?|coque|"
    r"tige en acier|dorsale|insert)s?\b[^.]{0,30}$",
    re.I,
)

# Les quatre indices de l'EN 13634, dans l'ordre de la norme : hauteur de tige,
# résistance à l'abrasion, résistance à la coupure, rigidité transversale.
# Deux écritures, les deux relevées telles quelles :
#     « Homologuées CE EPI Niveau 1|1|1|1 »   « Homologuées niveau 1 | 1 | 2 | 1 »
#     « Modèle certifié CE, niveau 1111 WR IPA »
#     « Chaussures certifiées CE niveau 1 1 1 1 WR IPA »  <- trouvé en relisant
# La quatrième n'était pas prévue : quatre chiffres séparés par de simples
# espaces. Elle coûtait les quatre indices de l'Ixon Vyper, la seule botte de
# l'échantillon que trois marchands décrivaient à l'identique.
_INDICES = re.compile(
    r"niveaux?\s*:?\s*([12])\s*[|/.\-–]\s*([12])\s*[|/.\-–]\s*([12])\s*"
    r"[|/.\-–]\s*([12])\b|"
    r"niveaux?\s*:?\s*([12])\s([12])\s([12])\s([12])\b|"
    r"niveaux?\s*:?\s*([12])([12])([12])([12])\b",
    re.I,
)

# Un indice annoncé seul, et seulement quand la phrase nomme l'épreuve :
#     « résistance supérieure à l'abrasion niveau 2 et résistance supérieure
#       à la coupe niveau 2 »
#
# ATTENTION. « niveau » est un mot de camelote commerciale dans ce rayon :
# « hauts niveaux de respirabilité », « niveaux de flexibilité excellents ». Et
# « rigidité transversale » apparaît en clair dans une phrase qui ne parle pas
# du tout de la norme :
#     « Semelle intermédiaire avec tige ZPLATE, pour optimiser la flexibilité
#       sur l'avant et la RIGIDITÉ TRANSVERSALE »
# On n'accepte donc un indice isolé QUE pour l'abrasion et la coupure, les deux
# épreuves dont le nom n'est pas réutilisable en argument de vente.
_ABRASION_SEULE = re.compile(
    r"abrasion[^.]{0,25}niveau\s*([12])\b|niveau\s*([12])[^.]{0,25}abrasion", re.I)
_COUPURE_SEULE = re.compile(
    r"(?:coupure|coupe)[^.]{0,25}niveau\s*([12])\b|"
    r"niveau\s*([12])[^.]{0,25}(?:coupure|[àa] la coupe)\b", re.I)

# --- membrane et imperméabilité -----------------------------------------------
#
# PIÈGE N°3 encore, et le marchand le traite comme nous : il expose « Gore-Tex
# oui/non » ET « imperméable », parce que ce ne sont pas les mêmes bottes.
# `impermeable` est la valeur générique — vraie de toutes ces bottes — et
# `membrane` n'est renseignée que lorsque le texte NOMME la membrane.
_MEMBRANES = [
    ("gore-tex", r"gore.?tex|\bGTX\b"),
    ("drystar",  r"dry.?star"),
    ("hydratex", r"hydratex"),
    ("outdry",   r"out.?dry"),
    ("sympatex", r"sympatex"),
    ("hipora",   r"hipora"),
    ("aerotex",  r"aerotex"),
    ("aquatech", r"aquatech"),
    ("t-dry",    r"\bT.?DRY\b"),
    ("hdry",     r"\bH.?DRY\b"),
    ("waterstop", r"water.?stop"),
    ("rainseal", r"rain.?seal"),
]

# « étanche » l'adjectif, jamais « étanchéité » le nom — voir `_impermeable`.
_IMPERMEABLE = re.compile(
    r"imperm[ée]ables?|water.?proof|\b[ée]tanches?\b|membrane", re.I)

# …et une fermeture étanche n'est pas une botte étanche :
#     « Guêtre néoprène : crée une FERMETURE ÉTANCHE en haut de la botte »
#     « fermeture coulissante […] pour une excellente étanchéité en haut »
# La XP9-R est une botte de piste, elle n'a aucune membrane. Sans cette garde
# elle ressortait imperméable.
#
# Deuxième cas, trouvé à la relecture : « COL EN NÉOPRÈNE MICRO-INJECTÉ ÉTANCHE,
# anti-poussière et anti-insectes » sur la XPD XP6-S, une botte de piste sans la
# moindre membrane. Le col est étanche, la botte ne l'est pas. La fenêtre passe
# donc de vingt à trente-cinq signes : « micro-injecté » tient entre les deux.
#
# Troisième cas, trouvé à la relecture, et c'est LE piège du rayon appliqué à
# l'imperméabilité : le CHAUSSON est une pièce, et chez Forma il est même une
# pièce EN OPTION.
#     « Doublure: Doublure intérieure rembourrée POSSIBILITÉ D'INTÉGRER EN
#       OPTION un CHAUSSON amovible et remplaçable en Drytex, ÉTANCHE et
#       respirant (ref FM0128) »
# La botte ressortait imperméable. Elle ne l'est pas : elle peut le devenir
# contre un achat supplémentaire, ce qui est exactement ce que « prédisposé »
# veut dire, et exactement ce qu'un comparateur ne doit pas promettre. Deux
# gardes le rattrapent maintenant — la pièce ci-dessous, et la réserve « en
# option », que `_avant()` va désormais chercher assez loin pour la voir.
#
# La doublure, elle, N'EST PAS dans cette liste, et c'est délibéré : « Doublure:
# Membrane Drystar® imperméable et respirante » est la façon dont Motoblouz
# annonce l'imperméabilité de la botte entière. La membrane est toujours dans la
# doublure ; l'écarter reviendrait à ne plus rien lire.
_ETANCHE_D_UNE_PIECE = re.compile(
    r"(?:fermetures?|gu[êe]tres?|soufflets?|zip|coulissante?|n[ée]opr[èe]ne|"
    r"collier|\bcol\b|haut de la botte)\b[^.]{0,35}$|"
    r"chaussons?\b[^.]{0,55}$",
    re.I,
)

# --- protections --------------------------------------------------------------
#
# Les trois options du marchand : malléole, sélecteur, tibia. Chacune exige un
# ANCRE de protection devant ou derrière le nom de la pièce. Sans ancre,
# « liberté de mouvement au niveau de la cheville » et « adhérence de sélecteur »
# devenaient des protections.
_ANCRE_PROTECTION = (r"(?:prot(?:ection|ections|ecteur|ecteurs|[èe]ge)|"
                     r"renforts?|renforcements?|renforc[ée]e?s?|coussinets?|"
                     r"plaques?|coques?|inserts?|supports?|blindages?)")

_MALLEOLE = (rf"{_ANCRE_PROTECTION}[^.]{{0,45}}(?:mall[ée]ol|chevill)|"
             r"(?:mall[ée]ol|chevill)\w*[^.]{0,35}"
             r"(?:prot[ée]g|renforc|\bTPU\b|\bD3O\b|inject|homologu)")

_TIBIA = (rf"{_ANCRE_PROTECTION}[^.]{{0,40}}tibia|"
          r"tibias?[^.]{0,30}(?:prot[ée]g|renforc|inject|\bTPU\b)|"
          r"prot[èe]ge.?tibias?|shin guard")

# « Renfort de changement de vitesse », « Renforcement du levier de vitesse »,
# « Matière résistante au frottement du sélecteur », « Renfort sélecteur ».
# Mais PAS « adhérence de sélecteur », qui parle du grip sur le levier.
_SELECTEUR = (rf"{_ANCRE_PROTECTION}[^.]{{0,40}}"
              r"(?:s[ée]lecteur|levier de vitesse|changements? de vitesse|"
              r"passages? de vitesse)|"
              r"(?:mati[èe]re|zone|patch)[^.]{0,30}s[ée]lecteur")

# Gardée bien que le marchand ne la filtre pas : c'est la protection que
# l'acheteur de bottes cross regarde en premier.
_BOUT_DE_PIED = (rf"{_ANCRE_PROTECTION}[^.]{{0,40}}"
                 r"(?:orteils?|bout de pied|pointes?|avant.?pied|empeigne)|"
                 r"(?:orteils?|pointes?|bouts?)[^.]{0,25}renforc")

# --- semelle ------------------------------------------------------------------
#
# ANCRÉE SUR LE MOT « SEMELLE », et c'est tout le sujet : l'antidérapant d'une
# botte est souvent À L'INTÉRIEUR, et ne dit rien de l'adhérence au sol.
#     « Patch talon en microsuède ANTIDÉRAPANT pour stabiliser le pied
#       à l'intérieur de la chaussure »
#     « Insert ANTIDÉRAPANT sur l'intérieur de la botte »
# Ces deux-là sont des anti-glissement du PIED et du MOLLET contre la moto.
_SEMELLE_ANTIDERAPANTE = re.compile(
    r"semelles?[^.]{0,80}(?:anti.?d[ée]rapant|anti.?glisse)|"
    r"(?:anti.?d[ée]rapant\w*)[^.]{0,40}semelles?", re.I)

_SEMELLE_ANTI_HUILE = re.compile(
    r"semelles?[^.]{0,90}(?:anti.?huile|[àa] l.huile|aux huiles|"
    r"hydrocarbures?|\bessence\b|\bSRA\b|\bSRB\b|\bSRC\b)|"
    r"r[ée]sistante?s? aux hydrocarbures?", re.I)

# --- le reste -----------------------------------------------------------------
_VENTILATION = re.compile(
    r"ventilations?|a[ée]rations?|\ba[ée]r[ée]e?s?\b|\bventil[ée]e?s?\b|"
    r"entr[ée]es? d.air|prises? d.air|flux d.air|panneaux? perfor[ée]s?", re.I)

_REFLECHISSANT = re.compile(
    r"r[ée]fl[ée]chissant|r[ée]tro.?r[ée]fl[ée]|r[ée]flectif|r[ée]flexes?\b|"
    r"reflective|r[ée]flective", re.I)

# --- fermeture ----------------------------------------------------------------
#
# Motoblouz ne l'expose pas ; on la garde parce qu'elle est écrite partout et
# qu'elle distingue une botte de cross d'une basket.
#
# Une botte en a souvent DEUX — « Fermeture par lacet et zip médial », « zip et
# velcro », « Fermeture micrométrique Quick Release ET lacets en nylon ». On ne
# choisit donc pas : on rend tout ce qui est écrit, dans un ordre fixe, joint
# par des `+`. Choisir aurait voulu dire inventer une hiérarchie que le texte
# n'écrit pas.
#
# LE SCRATCH EXIGE UN CONTEXTE DE FERMETURE. Le velcro d'une botte est aussi
# souvent un rabat de protection qu'un serrage :
#     « Languette Velcro pour bloquer la tirette du zip, la gardant plate »
#     « rabat Velcro et microfibre couvrant le zip »
# Ni l'une ni l'autre n'est un système de fermeture.
#
# LES BOUCLES AUSSI. « Boucle arrière » est une patte d'enfilage, pas une
# boucle de serrage — vu tel quel sur les baskets XPD X-RADICAL, dont la seule
# fermeture est « lacets et velcro ».
_FERMETURE = [
    ("boucles micrométriques",
     r"micro.?m[ée]triqu\w*|cliquets?\b|ratchet|quick.?release|slide.?lock|"
     r"cr[ée]maill[èe]re"),
    ("boucles",
     r"boucles?[^.]{0,40}(?:m[ée]tall|polym[èe]re|composite|aluminium|acier|"
     r"r[ée]glabl|auto.?bloquant|de fermeture|de serrage)|"
     r"(?:fermetures?|serrages?)[^.]{0,30}boucles?|"
     r"\d\s*boucles?\b"),
    ("zip",
     r"\bzips?\b|fermetures? (?:[àa] )?glissi[èe]re|fermetures? [ée]clair|"
     r"\bYKK\b"),
    ("lacets",
     r"\blacets?\b|\bla[çc]age\b|[œoe]illets"),
    ("scratch",
     r"(?:fermetures?|serrages?|pattes?|sangles?|bandes?|syst[èe]me)"
     r"[^.]{0,30}(?:velcro|auto.?agrippant|scratch)|"
     r"(?:velcro|scratch|auto.?agrippant)[^.]{0,25}"
     r"(?:de fermeture|de serrage|de r[ée]glage)"),
]


@dataclass
class Botte:
    """Ce qu'on a su lire. `None` partout où on n'a pas su — jamais une valeur
    par défaut, qui se confondrait avec une lecture."""

    # Les facettes du marchand, dans son vocabulaire.
    matiere: str | None = None               # cuir / cuir et textile / synthétique / textile
    categorie: str | None = None             # bottes / demi-bottes / baskets moto / chaussettes
    univers: str | None = None               # cross / enduro / touring / trail / sport / …
    genre: str | None = None                 # homme / femme / mixte
    impermeable: bool | None = None
    gore_tex: bool | None = None
    protection_malleole: bool | None = None
    protection_selecteur: bool | None = None
    protection_tibia: bool | None = None
    # Ce que le marchand n'expose pas, et qu'un comparateur peut ajouter.
    homologation: str | None = None          # 'EN 13634' ou 'CE'
    indice_hauteur: int | None = None
    indice_abrasion: int | None = None
    indice_coupure: int | None = None
    indice_rigidite: int | None = None
    membrane: str | None = None              # nommée seulement ; sinon None
    coque_bout_de_pied: bool | None = None
    fermeture: str | None = None             # 'lacets', 'zip+scratch', …
    semelle_antiderapante: bool | None = None
    semelle_anti_huile: bool | None = None
    ventilation: bool | None = None
    reflechissants: bool | None = None
    sources: list[str] = field(default_factory=list)

    def renseignees(self) -> int:
        return sum(1 for champ in _CHAMPS if getattr(self, champ) is not None)


# Les champs fusionnables, dans l'ordre de la classe. `sources` n'en est pas un.
_CHAMPS = tuple(f for f in Botte.__dataclass_fields__ if f != "sources")


def _avant(texte: str, position: int, largeur: int = 60) -> str:
    """Ce que le marchand a écrit AVANT ce mot, dans la même proposition.

    On coupe à la dernière ponctuation forte, et c'est un correctif payé cher.
    La Sidi URBEX WATERPROOF disait :

        « Membrane imperméable et respirante ADAPTÉ À toutes les conditions
          Protections: PROTECTION DE CHEVILLE en D3O »

    Une fenêtre de quarante signes en amont y lisait « adapté à », qui est un
    mot de PRÉPARATION emprunté au rayon casque — « adapté pour recevoir un
    intercom ». La botte perdait sa protection de malléole sur la foi d'une
    phrase qui parlait de la membrane. Le deux-points de « Protections: » dit
    justement que ce qui précède est fini.

    La fenêtre s'élargit en échange de soixante signes, ce que le deux-points
    rend sans risque, et ce qu'il fallait pour attraper « Possibilité
    d'intégrer EN OPTION un chausson amovible et remplaçable en Drytex,
    ÉTANCHE » — cinquante-cinq signes entre la réserve et le mot.
    """
    fragment = texte[max(0, position - largeur):position]
    coupure = None
    for m in _FIN_DE_PROPOSITION.finditer(fragment):
        coupure = m.end()
    return fragment[coupure:] if coupure is not None else fragment


_MOT = r"[\w'’à-ÿ-]+\s*"


def _nie(texte: str, position: int) -> bool:
    """Le marchand dit-il, juste avant ce mot, qu'il n'y en a PAS ?

    La négation doit être collée : elle, au plus un mot, puis le mot nié. Voir
    `_NEGATION` pour le pourquoi — « sans compromettre la protection » ne doit
    pas effacer une protection.
    """
    avant = _avant(texte, position, 40)
    return bool(re.search(
        _NEGATION + r"\s*(?!" + _SANS_QUI_N_EST_PAS_UNE_ABSENCE + r"\b)"
        r"(?:" + _MOT + r")?$",
        avant, re.I))


def _nie_quelque_part(texte: str, debut: int, fin: int) -> bool:
    """La même question, posée devant CHAQUE mot du fragment [debut, fin[.

    Un motif de protection s'étend de son ancre à sa pièce — « protection
    latérale Pas de renfort tibial » —, et la négation peut tomber n'importe où
    entre les deux. On la cherche donc devant chaque mot, avec la même exigence
    d'adjacence : c'est la garde de `_nie`, appliquée autant de fois qu'il y a
    de mots, et pas une garde plus large.
    """
    if _nie(texte, debut):
        return True
    return any(_nie(texte, debut + m.start())
               for m in re.finditer(r"\S+", texte[debut:fin]))


def _reserve(texte: str, position: int) -> bool:
    """« prédisposé », « compatible », « en option » — juste avant ce mot.

    LA RÉSERVE AUSSI DOIT ÊTRE COLLÉE, et c'est une correction mesurée : sur
    tout le rayon, la garde de préparation placée en amont d'une protection
    s'est déclenchée CINQ fois, et les cinq étaient fausses.

        « Membrane imperméable et respirante ADAPTÉ À TOUTES LES CONDITIONS
          Protections: Protection de cheville en D3O »
        « Absence de sliders remplaçables impliquant qu'une usure du slider
          NÉCESSITE LE REMPLACEMENT DE LA PAIRE Protection et renforts
          Renfort malléole présent »

    « adapté à » et « nécessite » sont des mots de préparation dans le rayon
    casque — « adapté pour recevoir un intercom », « nécessite un boîtier ».
    Ici ce sont des phrases de vente, et elles effaçaient des protections
    réelles. On garde le vocabulaire commun, hérité du rayon casque, et on
    exige seulement qu'il touche le mot qu'il réserve : lui, au plus deux mots,
    puis le mot. « prééquipé pour recevoir un intercom » tient dedans ;
    « adapté à toutes les conditions » n'y tient pas.

    La réserve écrite DERRIÈRE — « Protège sélecteur DXR EN OPTION » — est
    cherchée à part par `_present`, dans sa fenêtre de trente signes.
    """
    avant = _avant(texte, position)
    return bool(re.search(_PREPARE + r"\w*\s*(?:" + _MOT + r"){0,2}$",
                          avant, re.I))


def _present(texte: str, motif: str) -> bool | None:
    """True si la chose est là, `None` si elle est niée, annoncée ou absente.

    On regarde ce qui précède le motif DANS SA PROPOSITION — « compatible
    avec », « prédisposé pour », « pas de » — ET les trente signes APRÈS, parce
    que ce rayon-ci écrit aussi la réserve derrière : « Protège sélecteur DXR
    EN OPTION ».

    ET ON PARCOURT TOUTES LES OCCURRENCES, au lieu de juger sur la première.
    Une première occurrence réservée ne dit rien des suivantes : « Protège
    sélecteur DXR en option » plus loin « Renfort au niveau du sélecteur »
    décrivent deux objets différents, et s'arrêter au premier revenait à croire
    le marchand sur son argument de vente plutôt que sur sa fiche technique.
    C'est le corollaire du défaut de négation : une garde qui ne regarde qu'une
    occurrence se trompe dans les deux sens.
    """
    for m in re.finditer(motif, texte, re.I):
        if _reserve(texte, m.start()):
            continue
        if re.search(_PREPARE, texte[m.end():m.end() + 30], re.I):
            continue          # « Protège sélecteur DXR EN OPTION »
        # La négation se cherche DANS le motif autant qu'avant lui, parce qu'un
        # motif de protection commence à son ANCRE et finit sur la PIÈCE, et
        # que la négation se glisse entre les deux :
        #     « …et protection latérale PAS DE renfort TIBIAL intégré »
        # L'ancre « protection » est à vingt-cinq signes de « tibial », donc
        # dans le motif ; la négation, elle, est juste devant « renfort ». Ne
        # regarder que le début du motif revenait à lire la phrase d'avant pour
        # conclure sur celle-ci.
        if _nie_quelque_part(texte, m.start(), m.end()):
            continue
        return True
    return None


def _familles_dans(fragment: str) -> list[str]:
    """Les familles de matière présentes, DANS L'ORDRE OÙ LE TEXTE LES ÉCRIT.

    L'ordre de `_FAMILLES` sert à trancher les recouvrements — « cuir
    synthétique » doit être lu comme synthétique, et non comme cuir — et on
    efface donc les occurrences reconnues au fur et à mesure, pour que le motif
    `cuir` ne repasse pas sur le « cuir » de « cuir synthétique ».

    Mais l'ordre RENDU est celui du texte, et c'est un correctif payé cher :
        « Matière: En MICROFIBRE, matière SYNTHÉTIQUE, réputé pour être
          aussi résistant que le CUIR »
    Cette basket-là ressortait « cuir », parce qu'une liste de priorités fixe
    faisait passer le cuir devant le synthétique quel que soit ce qui était
    écrit. Le marchand, lui, dit l'essentiel en premier.
    """
    fragment = _CUIR_DE_COMPARAISON.sub(" ", fragment)
    reste = fragment
    trouvees = []
    for nom, motif in _FAMILLES:
        m = re.search(motif, reste, re.I)
        if m:
            trouvees.append((m.start(), nom))
            # Effacé à longueur constante : les positions doivent rester
            # comparables d'une famille à l'autre.
            reste = re.sub(motif, lambda x: " " * len(x.group(0)), reste, flags=re.I)
    return [nom for _, nom in sorted(trouvees)]


def _jusqu_a_la_piece_suivante(fragment: str) -> str:
    """Coupe le fragment dès qu'une autre pièce est nommée."""
    m = _FIN_DU_FRAGMENT.search(fragment)
    return fragment[:m.start()] if m else fragment


def _matiere(t: str) -> str | None:
    """La matière de la CHAUSSURE, pas celle d'une de ses huit pièces.

    Trois passes, de la plus sûre à la moins sûre, et on s'arrête à la première
    qui répond :

      1. une ancre qui nomme la tige — « Tige en cuir de vachette », « Matériau
         extérieur principal : Microfibre » ;
      2. la section « Matière: » de Motoblouz, qui s'arrête avant « Doublure: » ;
      3. le texte entier, en écartant toute occurrence dont les quarante signes
         précédents parlent d'une autre pièce.

    La troisième sert aux marchands laconiques — « Demi bottes Oscar en cuir
    pleine fleur » tient en six mots — et c'est aussi la plus exposée : c'est
    elle qui porte la garde `_PIECE_QUI_N_EST_PAS_LA_TIGE`.

    LE MÉLANGE. « cuir et textile » n'est rendu que si les deux sont dans le
    MÊME fragment, celui qui décrit l'extérieur : « 72% de Polyester Denim
    renforcé, 28% de cuir Daim ». Un cuir dehors et un textile en doublure
    donnent « cuir », parce que c'est ce que le marchand écrirait.
    """
    fragments = []

    for m in _ANCRE_TIGE.finditer(t):
        avant = t[max(0, m.start() - 40):m.start()]
        if re.search(_PIECE_QUI_N_EST_PAS_LA_TIGE, avant, re.I):
            continue          # « Semelle intermédiaire avec tige ZPLATE »
        fragments.append(_jusqu_a_la_piece_suivante(t[m.end():m.end() + 90]))

    section = _SECTION_MATIERE.search(t)
    if section:
        fragments.append(section.group(1))

    for fragment in fragments:
        familles = _familles_dans(fragment)
        if familles:
            return _accorder(familles)

    # Dernier recours : le texte entier, occurrence par occurrence.
    for nom, motif in _FAMILLES:
        for m in re.finditer(motif, t, re.I):
            avant = t[max(0, m.start() - 40):m.start()]
            if re.search(_PIECE_QUI_N_EST_PAS_LA_TIGE, avant, re.I):
                continue      # « Doublure entière en cuir de vachette »
            # On repart du voisinage pour attraper un éventuel mélange annoncé
            # dans la même phrase.
            voisinage = (t[max(0, m.start() - 30):m.end()]
                         + _jusqu_a_la_piece_suivante(t[m.end():m.end() + 90]))
            return _accorder(_familles_dans(voisinage) or [nom])
    return None


def _accorder(familles: list[str]) -> str:
    """Les familles lues -> une des quatre valeurs du marchand.

    « cuir et textile » est la seule valeur mixte que le marchand expose : un
    cuir mélangé à du synthétique reste rangé sous la famille nommée en
    premier, faute d'une valeur pour le dire.
    """
    if "cuir" in familles and "textile" in familles:
        return "cuir et textile"
    return familles[0]


def _univers(titre: str, t: str) -> str | None:
    for nom, motif in _UNIVERS_SUR:
        if re.search(motif, titre, re.I):
            return nom
    for nom, motif in _UNIVERS_AMBIGU:
        if re.search(_TETE_DE_TITRE + r"(?:" + motif + r")", titre, re.I):
            return nom
    for nom, motif in _UNIVERS_SUR + _UNIVERS_AMBIGU:
        if re.search(_ANCRE_USAGE + r"[^.]{0,60}(?:" + motif + r")", t, re.I):
            return nom
    return None


def _homologation(t: str) -> str | None:
    """« EN 13634 » quand la norme est nommée, « CE » quand elle ne l'est pas.

    Et `None` quand le seul CE du texte est celui d'une PROTECTION : le
    protecteur de malléole a sa propre certification, qui ne dit rien de la
    chaussure qui le porte.
    """
    for m in _EN13634.finditer(t):
        if _nie(t, m.start()):
            continue          # « non certifié EN 13634 »
        return "EN 13634"
    for m in _CE.finditer(t):
        avant = t[max(0, m.start() - 45):m.start()]
        if _CE_D_UNE_PIECE.search(avant):
            continue
        if _nie(t, m.start()):
            continue
        return "CE"
    return None


def _impermeable(t: str) -> bool | None:
    """Imperméable, oui ou rien.

    On ne cherche QUE l'adjectif « étanche » : le nom « étanchéité » parle
    presque toujours du soufflet ou du haut de tige. Et on écarte l'occurrence
    dont les vingt signes précédents nomment une fermeture, une guêtre ou un
    soufflet — « crée une fermeture étanche en haut de la botte ».

    « hydrofuge » et « résistant à l'eau » ne figurent volontairement dans aucun
    motif : déperlant n'est pas imperméable, et la botte qui le dit le dit
    justement parce qu'elle n'a pas de membrane.
    """
    for m in _IMPERMEABLE.finditer(t):
        if _ETANCHE_D_UNE_PIECE.search(_avant(t, m.start())):
            continue
        if _reserve(t, m.start()):
            continue
        if _nie(t, m.start()):
            continue
        return True
    return None


def _membrane(t: str) -> str | None:
    """La membrane NOMMÉE, quand la botte en porte une.

    Les mêmes trois gardes que pour l'imperméabilité, et elles manquaient
    toutes les trois : le nom de la membrane était cherché à la volée, sans
    rien regarder autour. Une seule phrase de l'échantillon suffit à dire ce
    que ça coûtait :

        « Imperméabilité et étanchéité — Construction imperméable pour garder
          les pieds au sec — ABSENCE DE MEMBRANE GORE-TEX® INDIQUÉE, vérifiez
          les limitations d'étanchéité selon l'usage »

    Cette chaussure-là ressortait `membrane = 'gore-tex'` ET `gore_tex = True`.
    Le Gore-Tex est le nom qui justifie l'écart de prix du rayon, et il était
    posé sur la foi de la phrase qui dit qu'il n'y en a pas.
    """
    for nom, motif in _MEMBRANES:
        for m in re.finditer(motif, t, re.I):
            if _reserve(t, m.start()):
                continue
            if _nie(t, m.start()):
                continue
            return nom
    return None


def _fermeture(t: str) -> str | None:
    trouvees = [nom for nom, motif in _FERMETURE if re.search(motif, t, re.I)]
    # Une fermeture micrométrique EST une boucle : on ne compte pas deux fois.
    if "boucles micrométriques" in trouvees and "boucles" in trouvees:
        trouvees.remove("boucles")
    return "+".join(trouvees) or None


def _indices(t: str, b: Botte) -> None:
    m = _INDICES.search(t)
    if m:
        g = [x for x in m.groups() if x is not None]
        b.indice_hauteur, b.indice_abrasion, b.indice_coupure, b.indice_rigidite = (
            int(g[0]), int(g[1]), int(g[2]), int(g[3]))
        return
    # Les indices annoncés un par un, pour les deux seules épreuves dont le nom
    # ne sert pas d'argument de vente par ailleurs.
    m = _ABRASION_SEULE.search(t)
    if m:
        b.indice_abrasion = int(m.group(1) or m.group(2))
    m = _COUPURE_SEULE.search(t)
    if m:
        b.indice_coupure = int(m.group(1) or m.group(2))


def lire(titre: str, description: str) -> Botte:
    """Lit une botte dans le texte d'un marchand.

    La catégorie et le genre sont lus dans le TITRE seul, l'univers d'abord dans
    le titre puis dans la prose avec une ancre d'usage, et tout le reste dans le
    titre et la description concaténés — les marchands courts mettent
    « WATERPROOF » ou « GORE-TEX » dans le titre et rien dans le texte.
    """
    titre = " ".join((titre or "").split())
    t = " ".join((titre + " " + (description or "")).split())
    b = Botte()
    if not t:
        return b

    # Une semelle de rechange, un slider ou une boucle détachée ne sont pas une
    # botte. On rend une lecture VIDE plutôt qu'une botte imaginaire.
    if _ACCESSOIRE.search(titre) or _RECHANGE.search(t):
        return b

    # Les chaussettes sont une valeur de la facette « catégorie » du marchand,
    # et rien de plus : elles n'ont ni malléole, ni sélecteur, ni membrane, et
    # tout ce qu'on lirait dedans serait du vocabulaire de textile emprunté.
    if _CHAUSSETTES.search(titre):
        b.categorie = "chaussettes"
        return b

    for nom, motif in _CATEGORIE:
        if re.search(motif, titre, re.I):
            b.categorie = nom
            break

    b.univers = _univers(titre, t)

    for nom, motif in _GENRE:
        if re.search(motif, titre, re.I):
            b.genre = nom
            break

    b.matiere = _matiere(t)
    b.homologation = _homologation(t)
    _indices(t, b)

    b.protection_malleole = _present(t, _MALLEOLE)
    b.protection_tibia = _present(t, _TIBIA)
    b.protection_selecteur = _present(t, _SELECTEUR)
    b.coque_bout_de_pied = _present(t, _BOUT_DE_PIED)

    b.fermeture = _fermeture(t)
    b.impermeable = _impermeable(t)
    b.membrane = _membrane(t)
    if b.membrane == "gore-tex":
        b.gore_tex = True

    # Ces quatre-là n'ont pas de version « préparée » : une botte a des
    # aérations ou n'en a pas. On rend True, ou None — jamais False, qui
    # prétendrait que le texte AFFIRME l'absence quand il se tait.
    #
    # Mais il ne se tait PAS toujours, et c'est ce qu'on avait manqué : quand le
    # marchand écrit « pas de », « sans » ou « absence de » devant la chose,
    # il l'affirme bel et bien absente. On rend alors `None`, pas True — et pas
    # False non plus, parce qu'un `None` n'écrit aucune ligne en base là où un
    # False remplirait la facette d'une valeur que personne n'a demandée.
    for champ, motif in (("semelle_antiderapante", _SEMELLE_ANTIDERAPANTE),
                         ("semelle_anti_huile", _SEMELLE_ANTI_HUILE),
                         ("ventilation", _VENTILATION),
                         ("reflechissants", _REFLECHISSANT)):
        for m in motif.finditer(t):
            if _nie(t, m.start()):
                continue
            setattr(b, champ, True)
            break

    return b


def fusionner(lectures: list[Botte]) -> Botte:
    """Une fiche, plusieurs marchands : on réunit ce que chacun a su dire.

    La première valeur trouvée gagne, et l'ordre d'appel fait la priorité —
    l'appelant passe les marchands du plus bavard au moins bavard.

    L'HOMOLOGATION FAIT EXCEPTION, comme chez les casques, mais pas de la même
    façon. Un marchand qui écrit « EN 13634 » et un autre qui écrit « CE » ne se
    contredisent pas : le second est moins précis, pas faux. On garde donc la
    valeur la plus précise. En revanche, deux marchands qui donnent des INDICES
    différents pour la même botte se contredisent bel et bien, et on abandonne
    l'indice : deux sources qui se disputent une donnée de sécurité ne valent
    pas mieux qu'aucune source.
    """
    out = Botte()
    for l in lectures:
        for champ in _CHAMPS:
            if getattr(out, champ) is None and getattr(l, champ) is not None:
                setattr(out, champ, getattr(l, champ))

    if any(l.homologation == "EN 13634" for l in lectures):
        out.homologation = "EN 13634"

    for champ in ("indice_hauteur", "indice_abrasion", "indice_coupure",
                  "indice_rigidite"):
        valeurs = {getattr(l, champ) for l in lectures if getattr(l, champ) is not None}
        if len(valeurs) > 1:
            setattr(out, champ, None)

    return out
