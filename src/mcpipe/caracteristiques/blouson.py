"""Ce qu'on peut dire d'un blouson, d'une veste ou d'une combinaison.

POURQUOI CE FICHIER EXISTE. Même raison que `casque.py` : le configurateur a
besoin de caractéristiques, et le catalogue n'en porte aucune. Le rayon compte
11 062 fiches en « Blousons & vestes » (catégorie 6) et 1 053 en
« Combinaisons » (catégorie 10).

CE QU'ON A MESURÉ AVANT D'ÉCRIRE (18/09/2026), sur les 12 020 fiches du rayon
qui portent au moins une description :

    source        offres   description médiane
    motoblouz      4 175        913 signes
    maxxess          476        563 signes
    motoaxxe         499        545 signes
    fcmoto         7 450        156 signes
    labecanerie    2 984        100 signes
    speedway       2 336         76 signes

Taux de mention, par marchand, sur ce qui compte :

    motif            motoblouz  maxxess  motoaxxe  fcmoto  labec.  speedway
    épaules / coudes       94 %     91 %      93 %    17 %     6 %       0 %
    dorsale                88 %     69 %      69 %     3 %     3 %       0 %
    « classe AA… »          8 %     61 %      58 %     3 %     0 %       0 %
    EN 17092               19 %     44 %      41 %     6 %     0 %       0 %
    membrane               41 %     47 %      47 %    19 %    10 %       0 %

Speedway écrit deux lignes de présentation commerciale et rien d'autre : il
n'apportera jamais une caractéristique. Maxxess et Motoaxxe écrivent court mais
DENSE — ils sont les meilleurs du rayon sur l'homologation, mieux que Motoblouz
qui écrit six fois plus. L'ordre de `fusionner()` s'en souvient.

CE QU'ON NE TROUVERA PAS ICI : aucun flux ne donne la colonne d'eau autrement
qu'en passant, ni le grammage de la doublure de façon systématique, ni le poids
du vêtement. Et aucun ne dit jamais qu'une caractéristique est ABSENTE : il se
tait. C'est pourquoi les booléens de ce fichier valent `True` ou `None`, jamais
`False` — voir `lire()`.

LA RÈGLE QUI GOUVERNE TOUT LE FICHIER
=====================================
En cas de doute, on rend `None`. Annoncer « dorsale fournie » sur un blouson
qui n'a qu'une poche vide n'est pas une imprécision de comparateur : c'est
envoyer quelqu'un rouler avec un dos nu qu'il croit protégé. Et c'est le défaut
NATUREL du rayon, parce que la dorsale y est presque toujours vendue à part.

Une caractéristique absente coûte un filtre moins précis ; une caractéristique
fausse coûte la confiance, et ici peut-être davantage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- les pièges de formulation ------------------------------------------------
#
# Recopié de `casque.py`, où il a coûté cher : quatre faux positifs y ont été
# trouvés en relisant l'échantillon, et LES QUATRE FAISAIENT MONTER LA
# COUVERTURE. Le vocabulaire est identique d'un rayon à l'autre parce que ce
# sont les mêmes six marchands qui écrivent.
#
# Ce qui CHANGE ici, et c'est la découverte du rayon : sur un casque, le mot de
# préparation précède la pièce (« prédisposé à recevoir un intercom »). Sur un
# blouson, la moitié des cas le SUIVENT :
#
#     « Poche pour protection dorsale EN OPTION »
#     « Poche dédiée pour protecteur dorsal avec protecteur dos R.I.S.C.
#        DISPONIBLE SÉPARÉMENT »
#     « Poche dédiée pour protection dorsale prévue et protection dorsale
#        NON FOURNIE »
#
# `casque.py` ne regarde que les quarante signes d'AVANT. Ici on regarde des
# deux côtés, sinon la garde ne voit rien et laisse passer « fournie ».
_PREPARE = (r"(?:pr[ée]dispos|pr[ée]{1,2}quip|pr[ée]par|compatible|"
            r"pr[êe]t (?:[àa]|pour)|ready|adapt[ée] (?:pour|[àa])|"
            r"peut recevoir|possibilit[ée] d|en option|non fourni|"
            r"n[ée]cessite|[àa] commander|vendu s[ée]par|"
            # ---- l'ajout propre au rayon : la POCHE. Un blouson sur trois chez
            # Motoblouz annonce « Poche pour protection dorsale » et rien de
            # plus. Une poche vide n'est pas une protection, et c'est
            # exactement la formule qui gonflait la couverture.
            r"poche[s]?[^.;]{0,25}(?:pour|[àa]|d[ée]di[ée]e?|pr[ée]vue?|"
            r"pouvant|pr[ée]par[ée]e?s?)|emplacement|logement|"
            r"pr[ée]vue?s? pour|pouvant accueillir|peut (?:accueillir|"
            r"[êe]tre [ée]quip)|velcro pour positionner|"
            # Relevé sur une veste Spidi : « arrangement pour la doublure thermo
            # FACULTATIVE et la doublure de H2Out ». Ni la doublure thermique ni
            # la membrane n'étaient dans le carton, et l'extracteur annonçait
            # les deux.
            r"facultati|arrangement pour|step.?in wear)"
            )

# Les mêmes marques de préparation, mais celles qui viennent APRÈS la pièce.
# Toutes relevées dans les descriptions du rayon, aucune inventée.
_OPTION_APRES = (r"(?:en option|optionnelle?s?|non fournie?s?|non incluse?s?|"
                 r"non livr[ée]e?s?|vendue?s? s[ée]par[ée]ment|"
                 r"disponibles? (?:s[ée]par[ée]ment|en option|ici en option)|"
                 r"s[ée]par[ée]ment|en suppl[ée]ment|[àa] commander)")

# --- EN 17092 : la caractéristique la plus utile du rayon ---------------------
#
# C'est la norme des VÊTEMENTS de moto, et sa classe résume à elle seule ce que
# le vêtement vaut en glissade : AAA (circuit) > AA (route) > A (urbain) >
# B (abrasion sans protections) > C (sur-couche porte-protections).
#
# Les marchands l'écrivent de deux façons, et c'est là qu'est le piège utile :
# soit la CLASSE en toutes lettres, soit seulement le NUMÉRO DE PARTIE de la
# norme, qui l'encode. Relevé tel quel dans les flux :
#
#     « Homologué CE EN 17092-4:2020, classe A »          partie 4 = classe A
#     « Combinaison certifiée selon EN 17092-3:2020 (AA) » partie 3 = classe AA
#     « classe de protection AA (EN 17092-3:2020) »        idem, ordre inverse
#     « Certifiée EN17092 classe A »                       pas de partie
#     « Référencé EN17092 A »                              pas de partie
#
# Les deux lectures se recoupent partout où on a pu les comparer, ce qui valide
# la table. Là où elles se contredisent, on ABANDONNE : deux affirmations qui se
# contredisent sur une donnée de sécurité ne valent pas mieux qu'aucune.
_PARTIE_VERS_CLASSE = {"2": "AAA", "3": "AA", "4": "A", "5": "B", "6": "C"}

# La partie de la norme. `(?![\d-])` empêche « 17092-4:2020 » de se faire lire
# comme une partie « 42 » si un marchand colle les chiffres.
_EN17092 = re.compile(r"\b(?:pr)?EN[\s.]?17092\b", re.I)
_EN17092_PARTIE = re.compile(r"\b(?:pr)?EN[\s.]?17092[\s]?[-–/][\s]?([2-6])(?![\d])", re.I)

# La classe écrite en toutes lettres. TROIS précautions :
#   - AAA avant AA avant A, sinon « AAA » se lit « A » ;
#   - on n'accepte que le mot « classe » / « class », JAMAIS « type » ni
#     « niveau » ni « catégorie ». « Type B-L2 » est un type de PROTECTION
#     (EN 1621), « niveau 1 » est son niveau d'absorption, et « catégorie II »
#     est la catégorie d'EPI — les trois se promènent dans la même phrase que
#     la classe du vêtement, et les confondre invente une homologation ;
#   - `\b` en fin, sans quoi « classe Affaires » deviendrait « classe A ».
_CLASSE_MOT = re.compile(
    r"\bclasse?s?\b(?:\s+de\s+protection)?[\s:\-]*\(?\s*(AAA|AA|A|B|C)\b", re.I)

# La classe accolée à la norme sans le mot « classe » : « Référencé EN17092 A ».
_CLASSE_COLLEE = re.compile(
    r"\b(?:pr)?EN[\s.]?17092(?:[\s]?[-–/][\s]?[2-6])?(?:\s*:?\s*20\d\d)?"
    r"[\s,:;()\-–]*\s*(AAA|AA|A|B|C)\b", re.I)

# --- matière de la coque ------------------------------------------------------
#
# LE DÉFAUT LE PLUS FRÉQUENT DU RAYON, et il est exactement celui que la visière
# était pour le casque : un blouson est fait de six matières, et le marchand les
# énumère toutes dans le même paragraphe.
#
#     « Matières: En cuir de Buffalo / 3D Air Mesh / Polyester 600D /
#        Membrane Hydratex amovible / DOUBLURE FIXE EN FILET »
#     « Matière ext. en Coton et fibre Kevlar / DOUBLURE FIXE EN FILET MESH »
#     « Matière: Tissu TexTech / DOUBLURE FIXE EN MESH »
#
# « Doublure 100 % polyester » ne dit rien de la coque, et « doublure fixe en
# mesh » encore moins : le mesh y est la doublure, pas le blouson. Sur les
# descriptions Motoblouz, le mot « mesh » appartient à la doublure une fois sur
# deux.
#
# On écarte donc toute occurrence dont les quarante-cinq signes précédents
# nomment une pièce qui n'est pas la coque.
_PIECE_QUI_N_EST_PAS_LA_COQUE = (
    r"(?:doublure|doublage|membrane|renfort|empi[èe]cement|insert|panneau[x]?\s+"
    r"(?:de\s+)?doublure|poche|col\b|poignet|sangle|patte|bande|velcro|"
    r"fermeture|[ée]clair|glissi[èe]re|\bzip|couture|curseur|logo|"
    r"[ée]tiquette|capuche|bas du dos|bord.?c[ôo]te|"
    # « Version tissu de son homologue EN CUIR » : le cuir est celui d'un AUTRE
    # modèle du catalogue. Vu sur un blouson Helstons en tissu.
    r"homologue|version|d[ée]clinaison|contrairement)"
)

# Le cuir, et rien que le cuir de la coque.
_CUIR = r"\bcuirs?\b|\bleather\b|peau de (?:vache|ch[èe]vre|buffle)|vachette|nubuck"

# LE CUIR SYNTHÉTIQUE N'EST PAS DU CUIR, et c'est le piège du genre et du
# sous-genre pris à l'envers : le mot est là, la matière n'y est pas. Relevé sur
# une combinaison Rev'it : « 3D Air Mesh, CUIR SYNTHÉTIQUE, NUBUCK ARTIFICIEL,
# cuir de vachette Monaco Performance ». Celle-là porte aussi du vrai cuir, mais
# rien ne garantit que la suivante en portera.
_CUIR_FAUX = (r"cuirs?\s+(?:synth[ée]tiques?|artificiels?|v[ée]g[ée]tal|PU\b|"
              r"[ée]cologiques?)|simili.?cuir|faux.?cuir|"
              r"nubucks?\s+artificiels?|\bskai\b")

# Le textile, tous noms confondus. La liste est volontairement large : ici, une
# erreur ne coûte presque rien, parce que « textile » est déjà la valeur
# générique. C'est le CUIR qu'il ne faut pas inventer.
_TEXTILE = (r"\btextiles?\b|polyester|polyamide|\bnylon\b|cordura|softshell|"
            r"\bmesh\b|maille|tissu|\bcoton\b|denim|ripstop|\bsergé\b|"
            r"fibretech|germadura|airguard|\btoile\b|polaire")

# « 3 % cuir véritable », « sangle velcro/cuir » : une garniture n'est pas une
# coque. Relevé sur un blouson Trilobite en denim, annoncé « cuir » par la
# première version.
_CUIR_GARNITURE = re.compile(r"\d{1,2}\s?%\s*(?:de\s*)?cuir", re.I)

# --- membrane et imperméabilité -----------------------------------------------
#
# Les noms propres de membranes relevés dans le rayon. On ne les devine pas :
# chacun a été lu dans une description.
_MEMBRANES = [
    ("gore-tex",   r"gore.?tex"),
    ("drystar",    r"drystar"),
    ("hydratex",   r"hydratex"),
    ("d-dry",      r"\bd.?dry\b"),
    ("h2out",      r"h2out|h2o.?out"),
    ("bwtech",     r"bwtech"),
    ("germatex",   r"germatex"),
    ("humax",      r"humax"),
    ("hipora",     r"hipora"),
    ("reissa",     r"reissa"),
    ("raintex",    r"raintex"),
    ("hydroscud",  r"hydroscud"),
    ("drymesh",    r"drymesh"),
    ("shelltech",  r"shelltech"),
    ("windscud",   r"windscud"),
    ("hydradri",   r"hydradri"),
]
_MEMBRANE = r"\bmembranes?\b|\blamin[ée]e?\b"

# UNE MEMBRANE GÉNÉRIQUE N'EST PAS DU GORE-TEX, et « déperlant » n'est pas
# « imperméable ». C'est le même piège que « thermoplastique n'est pas
# polycarbonate » sur le casque, à un rayon près.
#
#     « fini hydrofuge »                          -> PAS de membrane
#     « Revêtement hydrofuge durable Rain Defender » -> PAS de membrane
#     « En Softshell reconnu pour ses propriétés déperlantes » -> PAS de membrane
#
# Un traitement déperlant fait glisser l'averse cinq minutes ; il ne tient pas
# une heure d'autoroute sous la pluie. Aucun mot de cette famille n'entre donc
# dans `_IMPERMEABLE`.
# LE NOM ABSTRAIT ANNONCE LE SUJET, L'ADJECTIF DONNE LA RÉPONSE. « Étanchéité »
# et « imperméabilité » sont des INTITULÉS DE PARAGRAPHE chez les marchands, et
# le paragraphe qui suit dit parfois le contraire :
#
#     « Imperméabilité et étanchéité — Absence de membrane imperméable, la
#       destine prioritairement aux conditions sèches et chaudes. »
#
# Le blouson était annoncé imperméable sur la foi de son propre titre de
# section. La négation portait bien sur « imperméable », mais elle arrivait
# APRÈS, et la première occurrence non niée suffisait à conclure.
#
# On ne retient donc que les formes qui affirment quelque chose — « étanche »,
# « imperméable », « waterproof » — jamais la qualité nommée dans l'abstrait.
_IMPERMEABLE = r"imperm[ée]abl\w*|[ée]tanches?\b|waterproof"

# Et une POCHE imperméable ne rend pas le blouson imperméable, pas plus qu'une
# visière en polycarbonate ne faisait une calotte en polycarbonate. Relevé :
# « 4 poches extérieures imperméables », « Coutures thermo soudées »,
# « Fermeture à glissière imperméable sur le devant ».
_PIECE_QUI_N_EST_PAS_LE_VETEMENT = (
    r"(?:poche[s]?|portefeuille|fermeture|[ée]clair|glissi[èe]re|\bzip\w*|"
    r"couture[s]?|rabat|\bsac\b|pochette|compartiment)")

# --- doublure thermique -------------------------------------------------------
_THERMIQUE = (r"doublure[s]?[^.;]{0,30}(?:thermique|thermo|chaude|hivernale|"
              r"primaloft|isolante)|(?:thermique|thermo)[^.;]{0,20}amovible|"
              r"doublure[s]? (?:amovible|d[ée]montable)[^.;]{0,30}"
              r"(?:thermique|chaleur|chaude)")
_AMOVIBLE = r"amovible|d[ée]montable|d[ée]tachable|se retire|retirable|zipp[ée]e? et retir"

# --- saison -------------------------------------------------------------------
#
# Faible taux de mention, et DEUX pièges francs, tous deux des noms propres :
#
#   « Veste enduro Kenny BODYWARMER GRAPHIC HIVER 2025 » — « hiver » y est le
#   nom d'une COLLECTION, pas un climat d'usage.
#
#   « SUMMER Comfort System Lite ouvrant le long de la fermeture principale » —
#   sur une veste softshell « qui bloque le vent pour réduire la sensation de
#   froid ». « Summer » y est une marque déposée de Macna, et l'extracteur en
#   faisait un blouson d'été. Les mots anglais sont donc sortis de la liste :
#   dans un catalogue français, `summer` et `winter` sont presque toujours des
#   noms de technologies, jamais la saison d'usage.
_COLLECTION = re.compile(r"(?:automne|printemps)?[\s/-]*"
                         r"(?:hiver|[ée]t[ée])\s*[-/]?\s*20\d\d", re.I)
_SAISONS = [
    ("toutes-saisons", r"toutes? saisons?|4 saisons|quatre saisons|3 ?en ?1|"
                       r"3.in.1|toute l.ann[ée]e"),
    ("mi-saison",      r"mi.saison|demi.saison|saison[s]? interm[ée]diaires?"),
    ("hiver",          r"\bhivers?\b|hivernal|grand froid"),
    ("ete",            r"\b[ée]t[ée]\b|estival"),
]

# « ÉTÉ » EST AUSSI LE PARTICIPE PASSÉ D'« ÊTRE », et c'est le même piège que
# « ABS » dans « absorption » : la limite de mot est juste, le mot ne l'est pas.
#
#     « 100 % vegan-friendly. Aucune substance animale n'A ÉTÉ utilisée dans le
#        processus de fabrication »
#
# Deux blousons Ixon en cuir végane étaient annoncés « blouson d'été » sur la
# foi de cette phrase, qui parle de tannerie.
_ETE_VERBE = re.compile(r"\b(?:a|as|ont|avez|avons|ai|avait|avaient|aura|"
                        r"auront|ait|aient|avoir|ayant|[ée]t[ée])\s*$", re.I)

# Les deux bouts de l'usage. Un segment qui les nomme tous les deux ne choisit
# pas de saison, il décrit une polyvalence :
#
#     « Concept deux couches combinant VENTILATION ESTIVALE et protection
#        contre la PLUIE pour une utilisation élargie »
#     « pour ajouter de la CHALEUR sur les sorties FRAÎCHES et se défaire
#        facilement EN ÉTÉ »
#
# Les deux étaient annoncés « été ». Ce sont des blousons de mi-saison, et le
# marchand ne dit ni l'un ni l'autre : on se tait avec lui.
_POLE_CHAUD = r"chaud\w*|chaleur|estival\w*|\b[ée]t[ée]\b|canicul\w*"
_POLE_FRAIS = (r"froid\w*|fra[îi]ch?\w*|hivernal\w*|\bhivers?\b|\bpluie\b|"
               r"pluvieu\w*|intemp[ée]ries")

# --- le reste -----------------------------------------------------------------
_EPAULES = r"[ée]paules?|[ée]pauli[èe]res?|shoulder"
_COUDES = r"coudes?|coudi[èe]res?|elbow"
_DORSALE = r"dorsale?s?\b|protection de dos|prot[èe]ge.?dos|back.?protector"
# Un mot de protection doit se trouver près de la partie du corps, sinon
# « ajustement aux épaules » ou « empiècements élastiques aux coudes » — deux
# formules de coupe, pas de sécurité — feraient croire à une coque.
_MOT_PROTECTION = (r"protecti\w+|protecteurs?|prot[èe]ge|coques?|armures?|"
                   r"armatures?|1621|\bD3O\b|niveau\s?[12I]|homologu|certifi")

# --- Gore-Tex, et le troisième cas ---------------------------------------------
#
# Motoblouz filtre sur trois valeurs : non / oui / oui, laminé. Le laminé est
# une CONSTRUCTION, pas une membrane différente : la membrane est collée au
# tissu extérieur au lieu de flotter en doublure. Le blouson prend moins l'eau
# dans sa couche externe, il sèche plus vite, il coûte plus cher.
#
# Son contraire porte un nom dans le rayon, et il est écrit : le « Z-Liner »
# est justement la construction NON laminée, où la membrane est une doublure.
# « GORE-TEX Z-Liner » est donc du Gore-Tex simple, et le lire « laminé » aurait
# été le piège du genre et du sous-genre une fois de plus.
_LAMINE = r"lamin[ée]\w*|laminated|stratifi[ée]\w*"
_PAS_LAMINE = r"z.?liner|drop.?liner|doublure amovible"

# --- protection nuque ----------------------------------------------------------
#
# Relevé sur SIX fiches tirées au sort, et LES SIX disent la même chose :
# « Compatible neck brace », « Compatible avec une attelle cervicale », « Col
# amovible permettant d'accueillir un système de protection des cervicales ».
# Aucune ne livre la protection. On garde le champ parce qu'il répond à une
# vraie question — « puis-je mettre mon tour de cou avec ? » — mais il vaudra
# « prepare » à peu près partout, et c'est la vérité du rayon.
_NUQUE = (r"nuques?|cervicales?|neck.?brace|attelles? cervicales?|"
          r"protection du cou\b|tour de cou")

# --- genre ---------------------------------------------------------------------
#
# Le flux porte une colonne `gender`, mais `lire()` ne reçoit que le titre et la
# description : on lit donc le titre, où les marchands le mettent tous.
# « FEMME », « LADY », « pour dames », « STELLA » (la ligne femme d'un
# équipementier). Quand les deux genres sont nommés, c'est un mixte.
_GENRES = [
    ("enfant", r"\benfants?\b|\bkids?\b|\bjunior\b|\bchild|\bgar[çc]onnet|"
               r"\bb[ée]b[ée]s?\b|\byouth\b"),
    ("femme",  r"\bfemmes?\b|\bdames?\b|\blady\b|\bladies\b|\bwoman\b|"
               r"\bwomen\b|\bstella\b|f[ée]minine?"),
    ("homme",  r"\bhommes?\b|\bmens?\b|\bmasculin"),
]

# --- univers de pratique --------------------------------------------------------
#
# CE QU'ON A CHERCHÉ, ET CE QU'ON A TROUVÉ. Le configurateur en a besoin, et on
# est allé le chercher jusque dans la colonne `category` des six flux. Elle ne
# le porte pas : elle porte le TYPE d'article et la MATIÈRE, pas l'usage.
#
#     motoblouz    « Blouson Moto Textile », « Blouson Moto Cuir »,
#                  « Combinaison moto », « Veste Enduro », « Froid et Pluie »
#                  — dix valeurs en tout, aucune n'est un univers de pratique.
#     labecanerie  « Équipement route > Blouson moto > Blouson textile »
#     maxxess      « Equipement du motard > Blouson / veste / Combinaison >
#                    Blouson moto textile »
#     fcmoto       « tops », « suits ». Trois valeurs pour 29 931 offres.
#
# Le facettage du SITE Motoblouz n'est pas dans le FLUX Motoblouz. L'univers
# n'est donc lisible que dans la prose, et là il se cache derrière deux pièges :
#
#   1. LE NOM DE MODÈLE. « RST Roadster II », « IXS Sport RS-600 », « Alpinestars
#      Chrome Sport », « RST Blade Sport II ». Le mot est là, l'usage n'y est
#      pas — un blouson qui s'appelle Roadster n'est pas un blouson de roadster.
#   2. LE STYLE. « Coupe pensée pour la position sportive », « aux lignes
#      sportives », « style vintage ». On parle de la coupe, pas de la moto.
#
# On n'accepte donc que deux formes, toutes deux relevées telles quelles :
# l'univers ACCOLÉ au nom du vêtement (« blouson roadster », « Veste enduro »,
# « blouson de moto sportif ») ou une tournure d'usage explicite (« pensé pour
# un usage roadster », « adapté à la pratique sport et piste »).
#
# Et si deux univers sont nommés, on rend `None` : « Veste sport-touring » ne
# choisit pas, nous non plus.
_UNIVERS = [
    ("enduro",      r"enduros?|motocross|\bcross\b|tout.terrain"),
    ("trial",       r"trials?"),
    ("supermotard", r"supermotards?|supermoto"),
    ("trail",       r"trails?|adventure|aventure"),
    ("touring",     r"touring|grand tourisme|randonneu\w*"),
    ("roadster",    r"roadsters?|nakeds?"),
    ("custom",      r"customs?|vintage|caf[ée].?racer|r[ée]tro|heritage|bobber"),
    ("scooter",     r"scooters?|urbain\w*|citadin\w*"),
    ("sport",       r"sport\w*|racing|piste|circuit|comp[ée]tition"),
]
_VETEMENT = (r"(?:blousons?|vestes?|combinaisons?|sweats?|parkas?|"
             r"[ée]quipements?)\s+(?:de\s+)?(?:moto\s+|motos?\s+|textiles?\s+|"
             r"cuirs?\s+|homme\s+|femme\s+)?")
# « Veste SPORT-TOURING rétro en cuir » : deux univers en un mot. Le marchand
# n'a pas tranché entre le circuit et le grand tourisme — ce sont pourtant deux
# blousons différents, et deux cases différentes du configurateur.
_UNIVERS_COMPOSE = re.compile(
    r"\b(?:sport|touring|trail|roadster|custom|scooter|enduro|adventure)"
    r"\s?[-/]\s?"
    r"(?:sport|touring|trail|roadster|custom|scooter|enduro|adventure)\w*\b", re.I)
_USAGE = (r"(?:pour un usage|pens[ée]e?s? pour|con[çc]ue?s? pour|"
          r"destin[ée]e?s? (?:au|[àa] la|aux)|adapt[ée]e?s? (?:au|[àa] la|aux)|"
          r"id[ée]ale?s? pour (?:le|la|les)?|pratique|usage)\s+"
          r"(?:un |une |le |la |les |du |de la )?")

_VENTILATION = (r"ventilations?|a[ée]rations?|a[ée]r[ée]e?s?\b|zips? d.a[ée]ration|"
                r"panneaux? (?:en )?mesh|perfor[ée]|entr[ée]es? d.air|"
                r"sorties? d.air|flux d.air|\bair vent")
_SERRAGE = (r"serrages?|ajustements?|r[ée]glages?|ajustables?|r[ée]glables?|"
            r"pattes? de serrage|sangles? de r[ée]glage|cordon de serrage")
_REFLECHISSANT = (r"r[ée]fl[ée]chissant\w*|r[ée]tro.?r[ée]fl\w*|r[ée]flecteurs?|"
                  r"scotchlite|\b3M\b[^.;]{0,20}r[ée]fl")
# Le zip de liaison au pantalon. On exige les TROIS morceaux : un dispositif,
# une idée de raccord, et le pantalon — dans un mouchoir de poche. Sans le
# pantalon, on attrapait « Ce raccord vous permet de mettre à niveau votre
# blouson avec le gilet Connector » ; sans le dispositif, on attrapait
# « Nous vous conseillons d'associer cette veste au pantalon FREEWAY », qui est
# une vente croisée et rien d'autre.
_ZIP_LIAISON = (
    r"(?:zips?|fermetures?|[ée]clair|glissi[èe]re|pattes?|boucles?|passants?|"
    r"syst[èe]me|attaches?)[^.;]{0,40}"
    r"(?:raccord\w*|connexion|liaison|jonction|relier|raccorder|solidaris\w*)"
    r"[^.;]{0,40}pantalon"
    r"|(?:raccord\w*|connexion|liaison|jonction)[^.;]{0,30}"
    r"(?:blouson|veste)\s*[/-]\s*pantalon"
    r"|(?:relier|raccorder)[^.;]{0,30}(?:au|[àa] un|[àa] votre)\s+pantalon"
)


@dataclass
class Blouson:
    """Ce qu'on a su lire. `None` partout où on n'a pas su — jamais une valeur
    par défaut, qui se confondrait avec une mesure."""

    matiere_coque: str | None = None          # 'cuir' | 'cuir-textile' | 'textile'
    norme_en17092: bool | None = None         # certifié vêtement de moto
    classe_protection: str | None = None      # 'AAA' | 'AA' | 'A' | 'B' | 'C'
    protections_epaules: str | None = None    # 'fournies' | 'prepare'
    protections_coudes: str | None = None     # 'fournies' | 'prepare'
    # Trois états, pas deux, et c'est le facettage que la propriétaire utilise :
    # 'incluse' | 'option-poche' | 'option-predisposee'. Le quatrième état de
    # Motoblouz, « pas de poche », n'est PAS produit ici : aucun marchand
    # n'écrit qu'un blouson n'a pas de poche à dorsale, il se tait. Déduire
    # l'absence du silence serait inventer une donnée de sécurité.
    dorsale: str | None = None
    poche_dorsale: bool | None = None
    membrane: bool | None = None
    membrane_nom: str | None = None           # 'gore-tex', 'drystar'…
    gore_tex: str | None = None               # 'oui' | 'oui-lamine'
    impermeable: bool | None = None
    doublure_thermique: bool | None = None
    doublure_thermique_amovible: bool | None = None
    saison: str | None = None
    univers: str | None = None                # 'roadster', 'touring', 'trail'…
    genre: str | None = None                  # 'homme' | 'femme' | 'enfant' | 'mixte'
    ventilations: bool | None = None
    reglages_serrage: bool | None = None
    zip_liaison_pantalon: bool | None = None
    elements_reflechissants: bool | None = None
    sources: list[str] = field(default_factory=list)

    def renseignees(self) -> int:
        return sum(1 for c in _CHAMPS if getattr(self, c) is not None)


# L'ordre est celui de `fusionner()`. `sources` n'en fait pas partie : ce n'est
# pas une caractéristique du vêtement, c'est la trace de qui l'a dite.
_CHAMPS = (
    "matiere_coque", "norme_en17092", "classe_protection",
    "protections_epaules", "protections_coudes", "dorsale", "poche_dorsale",
    "membrane", "membrane_nom", "gore_tex", "impermeable",
    "doublure_thermique", "doublure_thermique_amovible", "saison",
    "univers", "genre",
    "ventilations", "reglages_serrage", "zip_liaison_pantalon",
    "elements_reflechissants",
)


# LA DÉCOUPE EN SEGMENTS, et c'est la correction qui a tout changé.
#
# La première version copiait `casque.py` : une fenêtre de quarante-cinq signes
# avant et soixante après. En relisant quinze extractions, trois des cinq
# défauts venaient de là, TOUS parce que la fenêtre débordait sur la phrase
# voisine, qui parle d'une autre pièce :
#
#   « Protections homologuées CE de niveau 2 aux coudes et aux épaules.
#      Poche prévue pour protection dorsale (en option). »
#        -> « épaules » prises pour préparées, à cause de la DORSALE d'après.
#
#   « Doublure de confort complète (corps et bras), fabriquée en coton »
#        -> « coton » pris pour la coque d'un blouson en cuir, parce que
#           « Doublure » était à cinquante-neuf signes, et la fenêtre en
#           faisait quarante-cinq.
#
# On découpe donc sur la ponctuation, et sur DEUX cas propres aux flux :
#   - les puces « * » de FC-Moto, qui séparent des affirmations sans point ;
#   - les phrases COLLÉES de Motoblouz, où l'espace manque : « Protections
#     épaules niveau 1Poche pour protection dorsale disponible en option ».
#     Sans cette coupure-là, la moitié des descriptions Motoblouz est une seule
#     phrase de mille signes, et toute garde de voisinage y est aveugle.
#
# Le deux-points NE coupE PAS entre deux chiffres : « EN 1621-2:2014, en
# option » doit rester d'un seul tenant, sans quoi on perd le « en option » et
# on annonce une dorsale fournie qui ne l'est pas.
_COUPURE = re.compile(
    r"[.;!?•·]|[*]|(?<!\d):(?!\d)|(?<=[a-zà-ÿ0-9\)])(?=[A-ZÀ-Þ][a-zà-ÿ])"
)


def _segments(texte: str) -> list[str]:
    return [s for s in _COUPURE.split(texte) if s and s.strip()]


def _segments_avec(texte: str, motif: str) -> list[str]:
    """Les segments où le motif apparaît. La liste vide veut dire « pas vu »."""
    return [s for s in _segments(texte) if re.search(motif, s, re.I)]


# « ABSENCE DE MEMBRANE IMPERMÉABLE », et l'extracteur annonçait imperméable.
#
# Trouvé sur une veste Macna dont la description dit, en toutes lettres :
# « Absence de membrane imperméable la destine prioritairement aux conditions
# sèches et chaudes, elle n'est pas adaptée aux pluies prolongées. » On
# annonçait « membrane : oui, imperméable : oui » sur un blouson dont le
# marchand écrit qu'il ne faut pas rouler sous la pluie avec.
#
# C'est le seul rayon où un marchand décrit ce qui MANQUE — les descriptions
# Macna sont rédigées et non listées — et c'est justement ce qui rendait le
# défaut invisible : il ne touche qu'une famille de fiches.
#
# Le négateur doit toucher le mot, sans rien entre les deux. « Sans
# compromettre l'étanchéité » et « sans retirer les protections » ne nient
# rien du tout, et il y en a plus dans le rayon que de vraies négations.
# Un seul mot peut s'intercaler, et seulement si c'est lui-même une pièce :
# « ABSENCE DE MEMBRANE imperméable », « PAS DE REVÊTEMENT thermique amovible ».
# « Sans MANCHES doublure fixe » ne nie pas la doublure, et « sans
# COMPROMETTRE l'étanchéité » l'affirme.
_NEGATION = re.compile(
    r"(?:absence d[e']|d[ée]pourvue?s? d[e']|pas d[e']|sans|aucune?)\s+"
    r"(?:(?:membranes?|doublures?|rev[êe]tements?|syst[èe]mes?|inserts?|"
    r"protections?|couches?)\s+)?$", re.I)


def _affirme(texte: str, motif: str) -> bool:
    """Vrai si le motif apparaît au moins une fois sans négateur accolé."""
    for m in re.finditer(motif, texte, re.I):
        if not _NEGATION.search(texte[max(0, m.start() - 24):m.start()]):
            return True
    return False


def _prepare_dans(segment: str) -> bool:
    return bool(re.search(_PREPARE, segment, re.I)
                or re.search(_OPTION_APRES, segment, re.I))


def _fourni_ou_prepare(texte: str, motif: str) -> str | None:
    """« Poche pour protection dorsale » n'est pas « dorsale incluse ».

    On est PESSIMISTE, et c'est délibéré : dès qu'UN segment porte à la fois la
    pièce et une marque de préparation, on rend « prepare ». `casque.py`
    regardait la première occurrence seulement, et seulement en amont ; le rayon
    blouson ne le permet pas, parce que la dorsale y est presque toujours vendue
    à part et que le marchand le dit en fin de phrase — « disponible ici en
    option », « vendues séparément », « non fournie ».

    Se tromper dans ce sens fait perdre un filtre. Se tromper dans l'autre fait
    rouler quelqu'un avec un dos nu qu'il croit protégé.
    """
    trouves = [s for s in _segments_avec(texte, motif) if _affirme(s, motif)]
    if not trouves:
        return None
    return "prepare" if any(_prepare_dans(s) for s in trouves) else "fourni"


# Toutes les pièces que le rayon protège. Sert à savoir DE QUI une marque de
# préparation parle — voir `_prepare_pour`.
_PIECES = (r"[ée]paules?|[ée]pauli[èe]res?|shoulders?|coudes?|coudi[èe]res?|"
           r"elbows?|dorsales?|protection de dos|prot[èe]ge.?dos|back.?protector|"
           r"hanches?|genoux|genouill[èe]res?|nuques?|cervicales?|"
           r"thorax|poitrine|sternum|tibias?")


def _prepare_pour(segment: str, motif_partie: str) -> bool:
    """La marque de préparation de ce segment parle-t-elle de NOTRE pièce ?

    LE DÉFAUT QUE CETTE FONCTION CORRIGE. Motoblouz colle ses phrases sans
    ponctuation : « Protections coudes D3O homologuées CE Protections épaules
    D3O homologuées CE Prédisposé à recevoir une protection dorsale ». Tout
    tient dans un seul segment. L'ancienne règle — un segment qui porte la
    pièce ET une marque de préparation vaut « prepare » — y lisait donc des
    coudes « préparés » sur un blouson dont le texte dit, en toutes lettres,
    qu'ils sont fournis et homologués. Seule la DORSALE y est en option.

    Les deux familles de marques ne se rattachent pas du même côté, et c'est
    ce qui permet de trancher :

      * « prédisposé à recevoir UNE DORSALE », « poche pour UNE DORSALE » :
        la préparation annonce ce qui SUIT ;
      * « épaules et coudes EN OPTION », « dorsale VENDUE SÉPARÉMENT » : elle
        qualifie ce qui PRÉCÈDE.

    On reste pessimiste quand la marque ne nomme aucune pièce : « livré sans
    protections » ne dit pas lesquelles, et se tromper dans ce sens fait
    perdre un filtre, tandis que se tromper dans l'autre fait rouler
    quelqu'un avec des coudes nus qu'il croit protégés.
    """
    for m in re.finditer(_PREPARE, segment, re.I):
        pieces = re.findall(f"(?:{_PIECES})", segment[m.end():m.end() + 90], re.I)
        if not pieces or any(re.search(motif_partie, p, re.I) for p in pieces):
            return True
    for m in re.finditer(_OPTION_APRES, segment, re.I):
        debut = max(0, m.start() - 90)
        pieces = re.findall(f"(?:{_PIECES})", segment[debut:m.start()], re.I)
        if not pieces or any(re.search(motif_partie, p, re.I) for p in pieces):
            return True
    return False


def _protection_du_corps(texte: str, motif_partie: str) -> str | None:
    """Une protection d'épaule, pas un empiècement d'épaule.

    « Empiècements élastiques aux épaules et aux coudes » et « Ajustements aux
    épaules » parlent de coupe, pas de sécurité. On exige donc un mot de
    protection dans le MÊME segment, puis on applique la garde
    « fourni / préparé » à ce segment-là seulement.
    """
    trouves = [s for s in _segments_avec(texte, motif_partie)
               if re.search(_MOT_PROTECTION, s, re.I)]
    if not trouves:
        return None
    return ("prepare" if any(_prepare_pour(s, motif_partie) for s in trouves)
            else "fournies")


def _matiere_coque(texte: str) -> str | None:
    """La matière de la COQUE, et d'elle seule.

    Le cuir et le textile sont cherchés séparément, et un segment qui nomme la
    doublure, un renfort, un empiècement ou la membrane AVANT la matière ne
    compte pas. Les deux ensemble donnent « cuir-textile », qui est ce que le
    marchand écrit lui-même (« blouson cuir/textile »).
    """
    morceaux = _segments(texte)

    def porte(motif: str, faux: str | None = None) -> bool:
        for s in morceaux:
            for m in re.finditer(motif, s, re.I):
                avant = s[:m.start()]
                if re.search(_PIECE_QUI_N_EST_PAS_LA_COQUE, avant, re.I):
                    break         # tout ce segment parle d'une autre pièce
                if faux and re.search(faux, s[max(0, m.start() - 12):m.end() + 16], re.I):
                    continue      # « cuir synthétique » : le mot sans la matière
                if _CUIR_GARNITURE.search(s[max(0, m.start() - 12):m.end()]):
                    continue      # « 3 % cuir véritable » : une garniture
                return True
        return False

    cuir, textile = porte(_CUIR, _CUIR_FAUX), porte(_TEXTILE)
    if cuir and textile:
        return "cuir-textile"
    if cuir:
        return "cuir"
    if textile:
        return "textile"
    return None


def _classe(texte: str) -> tuple[bool | None, str | None]:
    """La norme EN 17092 et sa classe, lues DEUX FOIS puis confrontées.

    Le numéro de partie encode la classe (partie 4 = classe A) et le marchand
    écrit souvent les deux. Quand les deux lectures se contredisent, on rend la
    norme sans la classe : « certifié EN 17092 » reste vrai, et c'est tout ce
    qu'on peut affirmer.

    Quand le texte ne donne QUE la norme, on ne devine pas de classe. Un
    vêtement « certifié EN 17092 » sans classe n'est pas un AA, comme un casque
    « thermoplastique » n'était pas un polycarbonate.
    """
    if not _EN17092.search(texte):
        # Une classe peut être annoncée sans que la norme soit nommée :
        # « Homologué CE, classe A ». Dans ce rayon, les classes AAA à C
        # n'appartiennent qu'à l'EN 17092 — mais on n'affirme pas la norme.
        m = _CLASSE_MOT.search(texte)
        return (None, m.group(1).upper() if m else None)

    par_partie = None
    m = _EN17092_PARTIE.search(texte)
    if m:
        par_partie = _PARTIE_VERS_CLASSE[m.group(1)]

    par_mot = None
    m = _CLASSE_MOT.search(texte) or _CLASSE_COLLEE.search(texte)
    if m:
        par_mot = m.group(1).upper()

    if par_partie and par_mot and par_partie != par_mot:
        return (True, None)       # deux affirmations, un désaccord : on renonce
    return (True, par_partie or par_mot)


def _membrane(texte: str) -> tuple[bool | None, str | None]:
    """Une membrane, et son nom SEULEMENT s'il est écrit.

    « Membrane imperméable et respirante » reste une membrane générique. On ne
    remonte pas au Gore-Tex parce que le blouson est cher ou la marque haut de
    gamme : le générique est moins précis, il est vrai.

    UNE MEMBRANE PEUT ÊTRE EN OPTION, et c'était un angle mort : « Prédisposition
    pour la doublure H2OUT optionnelle » faisait annoncer un blouson étanche
    H2Out qui ne l'est pas. Un segment qui ne parle que d'une membrane à
    commander ne compte donc pas.
    """
    def portee(motif: str) -> bool:
        return any(_affirme(s, motif)
                   for s in _segments_avec(texte, motif) if not _prepare_dans(s))

    for etiquette, motif in _MEMBRANES:
        if portee(motif):
            return (True, etiquette)
    if portee(_MEMBRANE):
        return (True, None)
    return (None, None)


def _impermeable(texte: str, membrane: bool | None) -> bool | None:
    """Imperméable, pas déperlant, et le vêtement, pas sa poche."""
    if membrane:
        return True
    for s in _segments_avec(texte, _IMPERMEABLE):
        if re.search(_PIECE_QUI_N_EST_PAS_LE_VETEMENT, s, re.I):
            continue          # « 4 poches extérieures imperméables »
        if _prepare_dans(s):
            continue          # « couches imperméables disponibles en option »
        if not _affirme(s, _IMPERMEABLE):
            continue          # « Absence de membrane imperméable »
        return True
    return None


def _dorsale(texte: str) -> tuple[str | None, bool | None]:
    """Les trois états qu'on sait lire, et le quatrième qu'on refuse d'inventer.

    Motoblouz compte 287 dorsales incluses contre 1 291 optionnelles. Un
    extracteur qui trouve beaucoup d'« incluse » est tombé dans le piège : dans
    ce rayon, la dorsale est une VENTE SÉPARÉE, et la description parle d'elle
    parce qu'elle vous la vendra, pas parce qu'elle est dedans.

    On distingue la poche fournie de la simple prédisposition sur le mot que le
    marchand emploie — « Poche pour protection dorsale en option » d'un côté,
    « Prédisposé à recevoir une protection dorsale » de l'autre.
    """
    trouves = [s for s in _segments_avec(texte, _DORSALE) if _affirme(s, _DORSALE)]
    if not trouves:
        return (None, None)
    poche = any(re.search(r"poche", s, re.I) for s in trouves) or None
    if not any(_prepare_dans(s) for s in trouves):
        return ("incluse", poche)
    avec_poche = any(_prepare_dans(s) and re.search(r"poche", s, re.I)
                     for s in trouves)
    return ("option-poche" if avec_poche else "option-predisposee", poche)


def _gore_tex(texte: str) -> str | None:
    """Gore-Tex, et le laminé seulement quand le mot est écrit à côté."""
    trouves = [s for s in _segments_avec(texte, r"gore.?tex")
               if not _prepare_dans(s) and _affirme(s, r"gore.?tex")]
    if not trouves:
        return None
    for s in trouves:
        if re.search(_LAMINE, s, re.I) and not re.search(_PAS_LAMINE, s, re.I):
            return "oui-lamine"
    return "oui"


def _univers(texte: str) -> str | None:
    """L'univers de pratique, quand le marchand le dit vraiment.

    Voir le commentaire de `_UNIVERS` : la colonne `category` des flux ne le
    porte pas, et dans la prose le mot est le plus souvent un nom de modèle ou
    une figure de style. Deux tournures seulement sont acceptées, et deux
    univers nommés valent `None`.
    """
    if _UNIVERS_COMPOSE.search(texte):
        return None
    trouves = []
    for nom, motif in _UNIVERS:
        accole = _VETEMENT + r"(?:" + motif + r")\b"
        usage = _USAGE + r"(?:" + motif + r")\b"
        if re.search(accole, texte, re.I) or re.search(usage, texte, re.I):
            trouves.append(nom)
    return trouves[0] if len(trouves) == 1 else None


def _genre(texte: str) -> str | None:
    """Homme, femme, enfant — ou « mixte » quand le marchand nomme les deux."""
    trouves = [nom for nom, motif in _GENRES if re.search(motif, texte, re.I)]
    if not trouves:
        return None
    if "enfant" in trouves:
        return "enfant"
    if len(trouves) > 1:
        return "mixte"           # « pour hommes et femmes »
    return trouves[0]


def _ete_vraiment(segment: str) -> bool:
    """« été » la saison, pas « été » le participe passé d'« être »."""
    for m in re.finditer(r"\b[ée]t[ée]\b|estival", segment, re.I):
        if not _ETE_VERBE.search(segment[max(0, m.start() - 16):m.start()]):
            return True
    return False


def _saison(texte: str) -> str | None:
    """Été, mi-saison, hiver — ou rien du tout si le texte en dit deux.

    « Membrane Raintex, idéale pour la mi-saison ET L'ÉTÉ » : le marchand n'a
    pas tranché, on ne tranche pas à sa place. « Toutes saisons » et « 3 en 1 »
    sont eux-mêmes une réponse, et ils priment.
    """
    t = _COLLECTION.sub(" ", texte)      # « HIVER 2025 » est un nom de collection
    trouvees = []
    for nom, motif in _SAISONS:
        for s in _segments_avec(t, motif):
            if nom in ("ete", "hiver") and (re.search(_POLE_CHAUD, s, re.I)
                                            and re.search(_POLE_FRAIS, s, re.I)):
                continue                 # le segment décrit une polyvalence
            if nom == "ete" and not _ete_vraiment(s):
                continue                 # « n'a ÉTÉ utilisée »
            trouvees.append(nom)
            break
    if not trouvees:
        return None
    if trouvees[0] == "toutes-saisons":
        return "toutes-saisons"
    return trouvees[0] if len(trouvees) == 1 else None


def lire(titre: str, description: str) -> Blouson:
    """Lit un blouson dans le texte d'un marchand.

    Le titre est concaténé à la description : chez Speedway et La Bécanerie, la
    matière et la saison ne sont QUE dans le titre (« Blouson cuir Furygan
    Vince V3 », « Blouson textile femme Hevik Scirocco »).
    """
    t = " ".join(((titre or "") + " " + (description or "")).split())
    b = Blouson()
    if not t:
        return b

    b.matiere_coque = _matiere_coque(t)
    b.norme_en17092, b.classe_protection = _classe(t)
    b.protections_epaules = _protection_du_corps(t, _EPAULES)
    b.protections_coudes = _protection_du_corps(t, _COUDES)
    b.dorsale, b.poche_dorsale = _dorsale(t)

    b.membrane, b.membrane_nom = _membrane(t)
    b.gore_tex = _gore_tex(t)
    b.impermeable = _impermeable(t, b.membrane)

    # La doublure thermique se vend aussi à part : « Prédisposition pour
    # doublure thermique », « Blouson isolant Max Liner Plus en option ». Les
    # segments qui ne parlent que de ça ne comptent pas.
    thermiques = [s for s in _segments_avec(t, _THERMIQUE)
                  if not _prepare_dans(s) and _affirme(s, _THERMIQUE)]
    if thermiques:
        b.doublure_thermique = True
        # Amovible ou non : seulement si le mot est dans le MÊME segment que la
        # doublure. Ailleurs, « amovible » parle des protections, qui le sont
        # presque toujours.
        if any(re.search(_AMOVIBLE, s, re.I) for s in thermiques):
            b.doublure_thermique_amovible = True

    b.saison = _saison(t)
    b.univers = _univers(t)
    b.genre = _genre(t)

    # Ces quatre-là n'ont pas de version « préparée » : un blouson a des
    # ventilations ou n'en a pas. On rend donc True, ou None — jamais False,
    # qui prétendrait que le texte AFFIRME l'absence. Il ne l'affirme jamais ;
    # il se tait, et le silence d'un marchand qui écrit soixante-seize signes
    # ne prouve rien.
    if _affirme(t, _VENTILATION):
        b.ventilations = True
    if _affirme(t, _SERRAGE):
        b.reglages_serrage = True
    if _affirme(t, _ZIP_LIAISON):
        b.zip_liaison_pantalon = True
    if _affirme(t, _REFLECHISSANT):
        b.elements_reflechissants = True

    return b


def fusionner(lectures: list[Blouson]) -> Blouson:
    """Une fiche, plusieurs marchands : on réunit ce que chacun a su dire.

    La première valeur trouvée gagne, et l'ordre d'appel fait la priorité —
    l'appelant passe les marchands par richesse de description décroissante.

    DEUX EXCEPTIONS, et elles vont dans le même sens que tout le fichier :

    - la CLASSE EN 17092 est abandonnée si deux marchands ne disent pas la
      même chose. C'est la règle que `casque.py` applique à l'homologation ECE,
      pour la même raison : sur une donnée de sécurité, deux sources qui se
      contredisent ne valent pas mieux qu'aucune source.

    - la DORSALE est pessimiste. Si un marchand dit « incluse » et un autre
      « poche prévue, protection en option », on garde l'option. Le marchand qui
      écrit le plus long n'est pas forcément celui qui a raison, et le coût des
      deux erreurs n'est pas le même.

    La NORME EN 17092 survit à un désaccord de classe : « certifié EN 17092 »
    reste vrai même quand les marchands ne s'accordent pas sur AA ou A. C'est
    la quatrième valeur du facettage, et elle a sa place.
    """
    out = Blouson()
    for lecture in lectures:
        for champ in _CHAMPS:
            if getattr(out, champ) is None and getattr(lecture, champ) is not None:
                setattr(out, champ, getattr(lecture, champ))

    classes = {l.classe_protection for l in lectures if l.classe_protection}
    out.classe_protection = classes.pop() if len(classes) == 1 else None

    optionnelles = [l.dorsale for l in lectures
                    if l.dorsale and l.dorsale != "incluse"]
    if optionnelles:
        out.dorsale = optionnelles[0]

    return out
