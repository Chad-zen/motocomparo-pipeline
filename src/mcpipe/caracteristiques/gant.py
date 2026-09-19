"""Ce qu'on peut dire d'une paire de gants, à partir des flux qu'on reçoit déjà.

POURQUOI CE FICHIER EXISTE. Même raison que `casque.py` : le configurateur a
besoin de caractéristiques, et le catalogue n'en porte aucune. Sur le rayon
gants, ce qu'un acheteur regarde en premier n'est pas la couleur : c'est
l'homologation EN 13594, son niveau, et la mention KP qui dit que les
articulations sont protégées.

CE QU'ON A MESURÉ AVANT D'ÉCRIRE (18/09/2026), et c'est ce qui décide tout :

    source         fiches   description médiane
    motoblouz       2 867        562 signes
    fcmoto          5 127        148 signes
    labecanerie     3 994         94 signes
    motoaxxe          637        409 signes
    maxxess           586        444 signes
    speedway          414         75 signes

Motoblouz écrit quatre fois plus que FC-Moto, mais FC-Moto couvre deux fois
plus de fiches. Les deux comptent, et ils n'écrivent pas la même langue :
Motoblouz fait des rubriques collées (« Matière: ... Protections: ... »),
FC-Moto fait des listes à puces parfois mal traduites — on y lit « FR 13594 »
pour « EN 13594 », et des morceaux d'allemand non traduits.

LE PIÈGE DU RAYON, ET IL N'EST PAS LE MÊME QUE POUR LES CASQUES
===============================================================
Un casque a une calotte et un écran : deux pièces. Un gant en a six, et les
marchands parlent des six dans le même paragraphe — la PAUME, le DOS, les
DOIGTS, la MANCHETTE, les RENFORTS, la DOUBLURE. « Renfort de paume en cuir »
et « Paume en daim synthétique » se suivent dans la même phrase, sur la même
fiche : le renfort est en cuir, la paume ne l'est pas. Chaque matière est donc lue
POUR UNE PIÈCE NOMMÉE, jamais pour le gant entier, et une matière qui ne dit
pas de quelle pièce elle parle ne vaut rien : on rend `None`.

LA RÈGLE QUI GOUVERNE TOUT LE FICHIER
=====================================
En cas de doute, on rend `None`. Annoncer « EN 13594 niveau 2 » sur un gant
qui n'est pas homologué n'est pas une imprécision de comparateur : c'est une
information de sécurité fausse. Une caractéristique absente coûte un filtre
moins précis ; une caractéristique fausse coûte la confiance.

Et la couverture n'est pas un score. Les quatre défauts du rayon casque
FAISAIENT MONTER la couverture ; les cinq trouvés ici aussi.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- les pièges de formulation ------------------------------------------------
#
# Recopié de `casque.py` À L'IDENTIQUE, et volontairement : cette liste a coûté
# cher. Elle a été établie EN LISANT les descriptions, et sa première version
# ratait « PRÉDISPOSÉ » — le mot le plus employé du rayon casque — ainsi que
# « prêt POUR », n'ayant prévu que « prêt À ».
#
# Une garde qui ne connaît pas le vocabulaire qu'elle doit arrêter ne garde
# rien, et elle le fait en silence : la couverture monte, et c'est justement
# ce qui rassure à tort.
_PREPARE = (r"(?:pr[ée]dispos|pr[ée]{1,2}quip|pr[ée]par|compatible|"
            r"pr[êe]t (?:[àa]|pour)|ready|adapt[ée] (?:pour|[àa])|"
            r"peut recevoir|possibilit[ée] d|en option|non fourni|"
            r"n[ée]cessite|[àa] commander|vendu s[ée]par)"
            )

# La négation, qui est au gant ce que la préparation est au casque. Les
# descriptions longues de Motoblouz DISENT ce qui manque, et c'est un service
# rendu à l'acheteur qu'il ne faut pas retourner contre lui :
#   « Conçus SANS coque de phalanges afin de privilégier confort et liberté »
#   « ABSENCE DE protection scaphoïde, à prendre en compte si vous recherchez
#     une protection complète du poignet »
# Les lire comme des présences transformait deux gants dépourvus de protection
# en gants protégés. C'est le faux positif le plus grave du fichier, et il
# faisait monter la couverture comme les autres.
_NIE = r"(?:sans|absence d|d[ée]pourvu|ni\b|aucune?|pas de|non\b)"


# --- la fin de mot chez Motoblouz ---------------------------------------------
#
# Motoblouz colle ses rubriques sans espace ni ponctuation :
#   « Double serrage poignetMANCHETTE LONGUESoufflet aux articulations »
#   « Membrane étancheDOUBLURE thermique en Ouate idéale l'hiver »
# Un `\b` en fin de motif ÉCHOUE là-dessus : entre « longue » et « Soufflet »
# il n'y a pas de limite de mot, seulement une majuscule. « Manchette longue »
# n'était donc pas lue chez le marchand qui écrit le plus.
#
# `_F` remplace ce `\b` final : il refuse une minuscule ou un chiffre — donc
# « longueur » et « performances » restent refusés, exactement comme avec `\b`
# — mais il accepte la majuscule de la rubrique suivante.
#
# Il n'est JAMAIS employé après une abréviation. Après « PU », `\b` refuse
# « PUR » quand `_F` l'accepterait, et ce rayon est plein de sigles courts :
# TPU, TPR, PU, KP, CE, D3O, WP. Ceux-là gardent leur `\b`, des deux côtés.
#
# Le `(?-i:…)` n'est pas une coquetterie. Tous les motifs de ce fichier sont
# cherchés avec `re.I` — et `re.I` fait matcher « E » à une classe qui ne
# contient que « a-z ». Sans le drapeau désarmé, `_F` redevenait un `\b`
# ordinaire, silencieusement, et « Manchette mi-longueEmpreinte » repassait à
# la trappe : trente-cinq gants avaient perdu leur manchette sans qu'aucun
# message ne le dise. La casse est le sujet même de cette garde ; il faut donc
# la rallumer là où le reste du motif l'ignore.
_F = r"(?!(?-i:[a-zà-öø-ÿ])|[0-9])"

# Et le même problème existe à l'ENTRÉE du mot, parce que la rubrique précédente
# est collée elle aussi :
#   « Protection des phalanges en TPR injectéeRENFORT PAUME en SEESOFT »
# `\brenfort` échoue entre « injectée » et « Renfort ». `_D` accepte la
# majuscule qui commence une rubrique et refuse la minuscule qui continue un
# mot — il ne matchera donc jamais au milieu de « parenfort ».
#
# Il ne peut pas s'écrire comme le symétrique de `_F` : « le caractère d'avant
# n'est pas une minuscule » refuse justement le « eR » de « injectéeRenfort »,
# qui est le seul cas qu'on cherche à rattraper. Il faut l'écrire comme une
# alternative — soit une vraie limite de mot, soit une majuscule ici même.
_D = r"(?:(?<!\w)|(?=(?-i:[A-ZÀ-Þ])))"


def _nie_avant(texte: str, position: int, portee: int = 30) -> bool:
    """Le texte annonce-t-il l'ABSENCE de ce qu'on vient de trouver ?

    Trente signes, et la fin du segment seulement. La première version en
    regardait quarante-cinq sans se soucier de la ponctuation, et elle a nié
    une coque qui existait :

        « …manipuler vos écrans SANS retirer les gants
          Protections: COQUE RIGIDE AUX ARTICULATIONS… »

    Le « sans » appartenait à la phrase sur l'écran tactile, deux rubriques
    plus haut. Une garde qui déborde de sa phrase ne garde pas mieux : elle se
    met à mentir dans l'autre sens, et celui-là fait BAISSER la couverture —
    ce qui le rend, pour une fois, presque visible.

    « Absence de protection scaphoïde » tient en vingt-deux signes ; « Conçus
    sans coque » en six.
    """
    avant = texte[max(0, position - portee):position]
    avant = re.split(r"[.;:•]", avant)[-1]       # la fin du segment, et rien avant
    return bool(re.search(_NIE, avant, re.I))


# --- homologation -------------------------------------------------------------
#
# EN 13594:2015 est la norme des gants de moto. Elle s'écrit de sept façons dans
# les flux — « EN 13594:2015 », « EN13594 », « EN 13594-2015 », « EN 13594 :
# 2015 », « 13594 2015 », et chez FC-Moto « FR 13594 », qui est une traduction
# automatique de « EN » prise pour le nom d'une langue.
_EN13594 = re.compile(r"\b(?:EN|FR|NF)?[\s.\-:]?13[\s.]?594\b", re.I)

# « CE » sans la norme est une affirmation GÉNÉRIQUE, et c'est le piège du genre
# et du sous-genre : « thermoplastique » n'est pas « polycarbonate », « CE »
# n'est pas « EN 13594 ». Beaucoup de gants sont annoncés « Homologués CE » sans
# autre précision ; les compter comme EN 13594 leur prêterait une norme que le
# texte ne nomme pas. On rend donc la valeur générique, qui est moins précise et
# qui est vraie.
#
# « CE » est cherché SANS `re.I`, et c'est tout le sujet : en minuscules, « ce »
# est un des mots les plus fréquents du français. Une recherche insensible à la
# casse aurait homologué le rayon entier.
_CE = re.compile(r"\bCE\b")
_AUTOUR_DE_CE = r"homologu|certifi|conform|norme|approuv|\bEPI\b|13[\s.]?594|niveau|level"

# Le niveau (1 ou 2) et la mention KP. Les formes réelles :
#   « niveau 1 KP », « niveau 1KP », « Niveau 2 », « level 1 KP », « EPI 1KP »,
#   « Niveau de certification 1KP », « CE de niveau 1KP ».
_NIVEAU = re.compile(r"(?:niveaux?|level)\s*:?\s*([12])\b|\b([12])\s?KP\b", re.I)

# Les gants CHAUFFANTS ont eux aussi des niveaux, et ce ne sont pas les mêmes :
#   « Système chauffant: NIVEAU 1 : bleu / 32° / 8h d'autonomie
#     NIVEAU 2 : vert / 40°C / 4h d'autonomie … Homologués CE »
# Le « Homologués CE » de la fin de fiche suffisait à adosser « Niveau 2 » à
# une norme : le gant ressortait « CE niveau 2 », le niveau des gants racing,
# sur la foi d'un réglage de résistance chauffante. Un gant chauffant est
# presque toujours un gant d'hiver de niveau 1 — l'erreur allait donc dans le
# sens qui flatte la fiche, comme toutes les autres.
_NIVEAU_DE_CHAUFFE = r"chauff|autonomie|batteries?\b|temp[ée]rature|watt|\bheat"
_KP = re.compile(r"\b[12]?KP\b")   # sans re.I : « kp » minuscule n'existe pas en rayon

# Un niveau n'a de sens qu'ADOSSÉ à une homologation. Sans ça on ramasse des
# noms de produits : « Richa LEVEL 2 in 1 Gore-Tex gants de moto » est un
# modèle, pas un niveau de protection — et « Technologie Gore 2 en 1 » non plus.
#
# « CE » n'est PAS dans cette liste, et son absence est délibérée : elle est
# cherchée avec `re.I`, et en minuscules « ce » est un des mots les plus
# fréquents du français. Un `\bCE\b` glissé ici aurait adossé tous les niveaux
# du rayon à une norme imaginaire, et la garde n'aurait plus rien gardé — en
# silence, en faisant monter la couverture. Le « CE » des marchands est donc
# cherché à part, avec `_CE`, sensible à la casse.
_ADOSSE_A_UNE_NORME = r"13[\s.]?594|homologu|certifi|conform|norme|\bEPI\b|\bKP\b"

# ET il doit parler DU GANT, pas d'une de ses pièces. C'est le piège du rayon
# appliqué à la donnée la plus regardée de la fiche :
#   « Protections phalanges en Carbone homologuées CE NIVEAU 2 »
# La coque de phalanges est certifiée séparément, sous une autre norme, avec ses
# propres niveaux. Annoncer ce gant « EN 13594 niveau 2 » — le niveau le plus
# haut, celui des gants racing — sur la foi d'une coque, c'est exactement
# l'erreur que la couverture compte comme un succès.
# « protection » TOUT COURT n'est pas dans cette liste, et ça aussi a été
# mesuré : FC-Moto ouvre presque toutes ses fiches par « Gants de protection
# pour motards (EN 13594 Niveau 2) ». Compter ce mot-là comme une pièce jetait
# le niveau du GANT, annoncé dans la même parenthèse que la norme — quatre
# gants de niveau 2 retenus sur tout le rayon au lieu de quarante-neuf. Ce
# sont les parties du corps qui font la pièce, pas le mot « protection ».
_PIECE_QUI_N_EST_PAS_LE_GANT = (r"(?:phalange|articulation|m[ée]tacarp|jointure|"
                                r"prot[èe]ge[\s\-]?\w+|coques?|pads?|renforts?|"
                                r"slider|curseur|poing|doigts?|paume|manchette)")


# --- les matières, et la pièce dont elles parlent ------------------------------
#
# L'ordre est tout le sujet, comme pour la calotte des casques. « Cuir
# synthétique » PASSE AVANT « cuir », parce que « cuir synthétique » contient le
# mot « cuir » et qu'un gant en synthétique annoncé « cuir » vaut cent euros de
# plus qu'il ne vaut. Même piège, sens inverse : le sous-genre d'abord quand il
# CONTREDIT le genre, le genre d'abord quand il le contient.
_MATIERES = [
    ("cuir synthétique", r"cuir\s+(?:synth[ée]tique|artificiel)|simili[\s.\-]?cuir|"
                         r"kunstleder|clarino|amara\b|ax[\s.\-]?suede|synthetix|"
                         r"(?:su[èe]de|daim|cuir su[ée]d[ée])\s+synth[ée]tique|"
                         r"synth[ée]tique\s+(?:su[ée]d[ée]|embossé)|chamude"),
    ("cuir",             r"cuir" + _F + r"|peau de ch[èe]vre|pleine fleur|kangourou|"
                         r"agneau|vachette|peau de vache|buffle"),
    ("textile",          r"textile|tissus?" + _F + r"|maille" + _F + r"|mesh" + _F +
                         r"|nylon|polyester|"
                         r"softshell|spandex|lycra|n[ée]opr[èe]ne|cordura|"
                         r"jersey|denim|coton|polaire|toile" + _F + r"|tricot"),
    # Le fourre-tout, et il est nommé comme tel : « paume en matière
    # synthétique », « paume en microfibre ». On ne sait pas si c'est un
    # similicuir ou un tissu technique ; on dit ce que le texte dit.
    ("synthétique",      r"microfibre|mati[èe]re synth[ée]tique|synth[ée]tique" + _F +
                         r"|polyur[ée]thane|\bPU\b|\bPVC\b|superfabric|keprotec"),
]

# Les pièces dont on lit la matière. Chacune est cherchée COMME PIÈCE, et la
# matière est prise dans la fenêtre qui SUIT le nom de la pièce.
_PAUME = r"paumes?(?:\s+de\s+(?:la\s+)?main)?"
_DOS = (r"dos\s+de\s+(?:la\s+)?main|dos\s+de\s+la\s+main|dessus\s+de\s+(?:la\s+)?main|"
        r"\bdos\b|structure sup[ée]rieure|dessus\b")

# Les autres pièces : elles ferment la fenêtre de lecture. « Dos de la main en
# softshell, et paume renforcée en cuir de chèvre » — sans cette liste, le
# « cuir » de la paume serait attribué au dos.
_AUTRES_PIECES = (r"paume|dos de|dessus de|manchette|poignet|doigts?|pouce|index|"
                  r"auriculaire|annulaire|doublure|isolation|coque|phalange|"
                  r"articulation|slider|curseur|fourchette|tranche|protections?\b|"
                  r"membrane|renforts?\b")

# Ce qui, placé JUSTE AVANT le nom d'une pièce, dit qu'on parle d'un morceau
# rapporté et non de la pièce elle-même. La phrase qui a révélé le piège, chez
# un fabricant italien :
#   « Tissu en maille respirant RENFORT DE PAUME EN CUIR Paume en daim
#     synthétique »
# Le renfort est en cuir. La paume est en synthétique. Lue sans cette garde,
# la paume devenait « cuir » — une matière qu'elle n'a pas, sur la pièce qui
# fait le prix du gant.
_MORCEAU_RAPPORTE = (r"(?:renfort\w*|renforc\w*|renforcement|insert\w*|patch\w*|"
                     r"emp[iî][èe]cement\w*|empiecement\w*|slider|curseur|coques?|"
                     r"protections?|pads?|mousse\w*|grip|doublure\w*|isolation|"
                     r"impression|couture\w*|zone\w*|bande\w*)\s*"
                     r"(?:de\s+|d[eu]\s+|en\s+|sur\s+(?:la\s+|le\s+)?|au niveau de\s+"
                     r"(?:la\s+|le\s+)?|c[ôo]t[ée]\s+)?$")


def _matiere_de(texte: str, piece: str, fenetre: int = 70) -> str | None:
    """La matière D'UNE PIÈCE NOMMÉE, et d'elle seule.

    On cherche le nom de la pièce, on écarte les occurrences précédées d'un
    morceau rapporté (« renfort de paume… »), puis on lit la matière dans la
    fenêtre qui suit — tronquée dès qu'une AUTRE pièce est nommée, et dès la
    fin du segment.

    La matière retenue est la PREMIÈRE de la fenêtre, pas la première de la
    liste de vocabulaire : dans « dos en tissu stretch avec surpiqûres cuir »,
    le dos est en tissu.
    """
    for m in re.finditer(piece, texte, re.I):
        avant = texte[max(0, m.start() - 40):m.start()]
        if re.search(_MORCEAU_RAPPORTE, avant, re.I):
            continue
        suite = texte[m.end():m.end() + fenetre]
        # On coupe au premier séparateur de segment, puis à la pièce suivante.
        suite = re.split(r"[.;•]|\bet\s+(?:la\s+|le\s+|les\s+)?(?=" + _AUTRES_PIECES + ")",
                         suite, maxsplit=1, flags=re.I)[0]
        coupe = re.search(_AUTRES_PIECES, suite, re.I)
        if coupe and coupe.start() > 0:
            suite = suite[:coupe.start()]
        trouvees = []
        for rang, (nom, motif) in enumerate(_MATIERES):
            mm = re.search(motif, suite, re.I)
            if mm:
                trouvees.append((mm.start(), rang, nom))
        if trouvees:
            # Le tri porte sur (position, RANG DANS `_MATIERES`), et le rang
            # n'est pas décoratif : « Paume en CUIR SYNTHÉTIQUE avec renfort en
            # cuir de chèvre » donne deux détections à la MÊME position, et un
            # tri sur le seul nom les départageait par ordre alphabétique —
            # « cuir » avant « cuir synthétique ». La paume ressortait en cuir.
            # Un gant en synthétique annoncé cuir vaut cent euros de moins que
            # sa fiche.
            trouvees.sort()
            return trouvees[0][2]
    return None


# --- la coque d'articulations et sa matière ------------------------------------
#
# Une coque, sur un gant, est une coque de main — sauf quand le marchand dit le
# contraire, et il le dit : chez FC-Moto, une traduction de fiche blouson a
# laissé « COQUE DU TORSE » dans des descriptions de gants d'hiver. On ne va
# pas annoncer qu'un gant protège la poitrine.
#
# La première version exigeait le mot « phalanges » ou « articulations » à
# portée. Elle refusait « Coque de protection ASPECT CARBONE AU NIVEAU DES
# phalanges » — cinq mots, un de trop — et « Coque de ProtectionRenfort Paume »,
# où la rubrique suivante est collée au mot. Une garde trop serrée ne se
# trompe pas moins : elle se trompe moins souvent, et toujours dans le même
# sens. On inverse donc la charge : la coque compte, sauf si la partie du corps
# nommée juste après n'est pas la main.
_COQUE = re.compile(r"coques?" + _F + r"|coquilles?" + _F + r"|knuckle", re.I)
# Ce qui, nommé juste après la coque, dit qu'elle ne protège pas la main.
_COQUE_AILLEURS = re.compile(
    r"^\W{0,4}(?:de |du |d.|en |sur |au niveau d\w+ )?(?:la |le |les |l.)?"
    r"(?:torse|poitrine|dorsale|dos(?!sier)\b|genou|coude|[ée]paule|tibia|hanche|"
    r"thorax|sternum)", re.I)

# La matière de la coque, et le piège du genre et du sous-genre, en une phrase
# de marchand :
#   « Coque de protection ASPECT CARBONE au niveau des phalanges »
# « Aspect carbone » est une finition imprimée. Le carbone est ce qui justifie
# cent euros d'écart sur un gant racing ; l'annoncer sur un gant qui imite sa
# texture est la même sur-affirmation que « carbone » sur un casque composite.
# Quand la coque n'annonce aucune matière, on rend `None` : « coque de
# protection » est un genre, pas une matière.
_IMITATION = r"(?:aspect|effet|look|style|imitation|finition|d[ée]cor|motif)\s*$"
_MATIERES_COQUE = [
    ("carbone",         r"carbone?\b|carbon fib"),
    ("D3O",             r"\bD3O\b"),
    ("TPU",             r"\bTPU\b"),
    ("TPR",             r"\bTPR\b"),
    ("thermoplastique", r"thermoplastique|thermoform|thermoplastic"),
    ("PU",              r"\bPU\b|polyur[ée]thane"),
    ("plastique",       r"plastique\b|polym[èe]re"),
]


def _coque(t: str) -> tuple[bool | None, str | None]:
    """Coque d'articulations : présence, puis matière.

    Le `None` de présence et le `False` ne disent pas la même chose. `False`
    est réservé au gant dont le texte AFFIRME qu'il n'en a pas — « Conçus sans
    coque de phalanges » —, `None` au gant qui se tait.
    """
    m = None
    for candidat in _COQUE.finditer(t):
        if _COQUE_AILLEURS.match(t[candidat.end():candidat.end() + 30]):
            continue          # « coque du torse » : de la prose de blouson
        m = candidat
        break
    if m is None:
        return None, None
    if _nie_avant(t, m.start()):
        return False, None
    # La matière est cherchée autour de la coque : avant (« coque en carbone
    # sur les phalanges » a déjà donné la matière) comme après.
    zone = t[max(0, m.start() - 20):m.end() + 60]
    for nom, motif in _MATIERES_COQUE:
        mm = re.search(motif, zone, re.I)
        if not mm:
            continue
        if re.search(_IMITATION, zone[:mm.start()].rstrip()[-12:] + " ", re.I):
            continue          # « aspect carbone » : une finition, pas une matière
        if re.search(_IMITATION, zone[max(0, mm.start() - 12):mm.start()], re.I):
            continue
        return True, nom
    return True, None


# --- protections de la paume ---------------------------------------------------
#
# Le slider de paume est la pièce qui glisse au lieu d'accrocher ; le renfort de
# paume est la pièce qui s'use au lieu de percer. Ce ne sont pas les mêmes, et
# un gant peut avoir l'un sans l'autre.
#
# Les deux EXIGENT le mot « paume » à portée, et ce n'est pas du zèle :
#   « Protection de l'avant-bras grâce au CUFF SLIDER en TPR »
#   « SLIDER sur le dessus de la main »
# Un slider d'avant-bras et un slider de dos de main ne protègent pas la paume.
_SLIDER = re.compile(r"(?:sliders?|curseurs?)" + _F + r"|hypoth[ée]nar", re.I)
_SUR_LA_PAUME = re.compile(r"\bpaume|hypoth[ée]nar", re.I)
# Là où un slider peut se trouver ET qui n'est pas la paume. La phrase qui l'a
# imposé met les deux mots côte à côte :
#   « Renfort en cuir digital côté PAUME SLIDER SUR LE DESSUS DE LA MAIN »
# Une simple règle de proximité lisait « paume slider » et concluait. Il faut
# donc regarder OÙ le slider est posé, pas seulement ce qui l'entoure.
_AILLEURS_QUE_LA_PAUME = re.compile(
    r"dessus de (?:la )?main|dos de (?:la )?main|avant.bras|manchette|poignet|"
    r"doigts?|auriculaire|annulaire|pouce|index", re.I)


def _slider_paume(t: str) -> bool | None:
    """Un slider DE PAUME, et pas un autre.

    Un gant en porte jusqu'à trois : à la paume, au dos de la main, et à
    l'avant-bras (« Protection de l'avant-bras grâce au Cuff Slider en TPR »).
    Seul celui de la paume dit quelque chose de la chute : c'est la surface qui
    touche le bitume.

    On lit donc d'abord ce qui SUIT le slider — c'est là que le marchand dit où
    il est — et on ne se rabat sur ce qui précède que si la suite reste muette.
    """
    for m in _SLIDER.finditer(t):
        if m.group(0).lower().startswith("hypoth"):
            return not _nie_avant(t, m.start())
        apres = t[m.end():m.end() + 35]
        ailleurs = _AILLEURS_QUE_LA_PAUME.search(apres)
        paume = _SUR_LA_PAUME.search(apres)
        if paume and (not ailleurs or paume.start() < ailleurs.start()):
            return not _nie_avant(t, m.start())
        if ailleurs:
            continue          # le slider est posé ailleurs : ce n'en est pas un
        if _SUR_LA_PAUME.search(t[max(0, m.start() - 25):m.start()]):
            return not _nie_avant(t, m.start())
    return None
#
# Le renfort exige une PRÉPOSITION, et ce n'est pas de la grammaire pour la
# grammaire. Motoblouz colle ses rubriques sans ponctuation :
#   « Protection et RENFORTS PAUME en NANOFRONT® japonais offrant un grip… »
# « renforts » y est un titre de rubrique, « Paume » la ligne suivante, et le
# gant n'a aucun renfort de paume. Exiger « renfort DE / SUR / AU NIVEAU DE la
# paume » sépare la phrase du sommaire.
_RENFORT_PAUME = re.compile(
    _D + r"renfor\w*[^.;]{0,20}?\b(?:de|du|sur|dans|[àa])\s+(?:la\s+|le\s+)?"
    r"(?:niveau de (?:la )?)?paume|" + _D + r"paumes?(?:\s+\w+){0,2}\s+renforc"
    # « Renfort paume de main » : un SINGULIER collé au nom de la
    # pièce est une phrase. Le pluriel « renforts Paume » est un titre de
    # rubrique, et il reste dehors — c'est la seule chose qui distingue les
    # deux dans la prose sans ponctuation de Motoblouz.
    r"|" + _D + r"renfort\s+(?:de\s+(?:la\s+)?)?paume", re.I)

# Le scaphoïde est l'os du poignet qui casse en premier quand la main se pose.
# Rare (0,5 % des textes) et précieux — et le seul endroit du rayon où un
# marchand écrit noir sur blanc que la protection MANQUE.
_SCAPHOIDE = re.compile(r"scapho[iï]de?|scaphoid", re.I)

# --- manchette ----------------------------------------------------------------
#
# « mi-longue » AVANT « longue », sinon « manchette mi-longue » devient longue :
# c'est la même précaution d'ordre que partout ailleurs dans ce fichier.
# « Manchette en néoprène » ne dit RIEN de la longueur : `None`.
_MANCHETTE = [
    ("mi-longue", r"manchettes?[\s:,]*(?:est\s+)?(?:mi.longues?|moyennes?|semi.longues?)" + _F +
                  r"|mi.longues? manchettes?" + _F),
    ("longue",    r"manchettes?[\s:,]*(?:est\s+)?longues?" + _F + r"|longues? manchettes?" + _F +
                  r"|manchettes?[^.;]{0,25}" + _D + r"longues?" + _F + r"|crispin"),
    ("courte",    r"manchettes?[\s:,]*(?:est\s+)?courtes?" + _F + r"|courtes? manchettes?" + _F +
                  r"|manchettes?[^.;]{0,25}" + _D + r"courtes?" + _F),
]

# --- imperméabilité -----------------------------------------------------------
#
# « Déperlant » n'est pas « imperméable », et c'est le même piège que
# « prédisposé » / « fourni » : un traitement de surface n'est pas une membrane.
# La phrase qui l'a révélé, sur un gant d'ÉTÉ ajouré :
#   « En peau de chèvre teintée dans la masse IMPERMÉABILISÉE conjuguée au
#     microfibre »  — sur un gant d'ÉTÉ ajouré, dont le nom dit « AIR ».
# Un cuir imperméabilisé résiste dix minutes à la pluie. Le vendre comme un gant
# étanche, c'est promettre à l'acheteur une sortie d'hiver au sec.
_IMPERMEABLE = re.compile(
    r"imperm[ée]ables?" + _F + r"|[ée]tanch[ée]?e?s?" + _F + r"|waterproof|gore[\s.\-]?tex|"
    r"membrane[^.;]{0,30}(?:imperm|[ée]tanch|respirante)|\bWP\b|hipora|drystar|"
    r"h2out|hydratex|outdry|d[\s.\-]?dry\b|xdry", re.I)
# « hydro… » a été ESSAYÉ puis retiré : `\bhydro` attrape « hydrofuge », qui
# est justement le contraire de ce qu'on cherche, et il l'attrapait AVANT que
# `_PAS_IMPERMEABLE` ait son mot à dire.
_PAS_IMPERMEABLE = re.compile(
    r"d[ée]perlant|hydrofuge|imperm[ée]abilis|r[ée]sistant\w*\s+[àa] l.eau|"
    r"water[\s.\-]?repellent|d[ée]perlante", re.I)

# --- doublure thermique -------------------------------------------------------
#
# « Doublure » tout court ne veut RIEN dire de thermique. Sur un gant d'été :
#   « Doublure de confort en coton »
#   « Doublure intérieure 100% polyester »
#   « Doublure en tissu jersey, doux et confortable »
# Compter ces trois-là comme des doublures thermiques aurait fait passer des
# gants d'été pour des gants d'hiver — et la couverture aurait doublé.
_THERMIQUE = re.compile(
    r"primaloft|thinsulate|thermolite|ouat[ée]|molletonn|micro.?polaire|"
    r"isolation thermique|doublure thermique|isolant thermique|"
    r"doublure[^.;]{0,25}(?:polaire|chaude|thermique|hiver)|"
    r"(?:polaire|fourrure)[^.;]{0,25}doublure|duvet|"
    r"doublure[^.;]{0,25}fourrure|fourrure[^.;]{0,20}polaire|"
    r"isolation[^.;]{0,20}\d{2,3}\s?g", re.I)

# --- écran tactile ------------------------------------------------------------
#
# « Tactile » seul ne dit pas qu'on peut déverrouiller son téléphone :
#   « Doté du Sensor System pour une SENSIBILITÉ TACTILE optimale »
#   « INDICE TACTILE intelligent »
# Les deux parlent du ressenti au guidon, l'inverse exact du sujet. On exige
# donc qu'un écran, un smartphone ou un doigt soit nommé à portée.
_TACTILE = re.compile(
    r"[ée]crans?\s+tactiles?|tactiles?[^.;]{0,60}(?:[ée]cran|smartphone|"
    r"t[ée]l[ée]phone|gsm)|(?:[ée]cran|smartphone|t[ée]l[ée]phone)[^.;]{0,60}tactile|"
    r"(?:index|doigts?|pouce|embout\w*)\s+tactiles?|tactiles?\s+(?:[àa] l.index|au pouce)|"
    r"e[\s.\-]?touch|smart[\s.\-]?touch|touch[\s.\-]?screen|screen[\s.\-]?touch", re.I)

# --- saison -------------------------------------------------------------------
#
# Deux saisons dans le même texte, c'est zéro saison : « Gants d'hiver OU DE
# MI-SAISON pour les navetteurs urbains » ne permet de classer nulle
# part. On ne tranche pas à la place du marchand.
#
# « Été » se lit large, « été » se lit étroit, et c'est le même mot. Le
# participe passé d'« être » est partout — « ces gants ONT ÉTÉ conçus pour… » —
# donc la saison n'est reconnue que collée à « gants » ou précédée de « d' ».
# L'hiver n'a pas ce problème, et se laisse chercher plus loin dans la phrase :
# « Gants DE MOTO D'HIVER imperméables à l'eau chauffés » ne tenait pas dans un
# motif plus serré.
#
# « Gants chauffants » ne vaut PAS « hiver », bien qu'aucun d'eux ne se porte
# en juillet : le marchand en fait une catégorie à part, et la déduction
# appartient à celui qui affichera la fiche, pas à celui qui la lit.
_SAISONS = [
    ("mi-saison", r"mi[\s.\-]?saisons?" + _F),
    ("hiver",     r"gants?[^.;:•*|]{0,25}?\b(?:d.)?hivers?" + _F + r"|hivernaux?" + _F),
    ("été",       r"gants?\s+(?:moto\s+|de\s+moto\s+|cross\s+|enduro\s+|"
                  r"homme\s+|femme\s+)*[ée]t[ée]" + _F +
                  r"|gants?[^.;:•*|]{0,25}?\bd.[ée]t[ée]" + _F +
                  r"|saison\s+[ée]t[ée]" + _F),
]

# --- ventilation ---------------------------------------------------------------
#
# « Respirant » est EXCLU : c'est une propriété de membrane, qui se dit d'un
# gant d'hiver étanche. La ventilation, c'est un trou.
#
# Et « perfor » ne peut PAS s'écrire `perfor\w*`. La phrase qui l'a montré, sur
# un gant de cuir de cerf sans un seul trou :
#   « Coutures hautes PERFORMANCES pour une solidité maximale sur route »
# « performance » est un des mots les plus employés du rayon ; il faisait
# passer pour ventilés des gants d'hiver pleins. C'est le même accident que
# l'ABS des casques qui matchait « absorption », à ceci près qu'ici les limites
# de mot ne suffisent pas : il faut écrire la terminaison.
_VENTILATION = re.compile(
    r"ventil[ée]?\w*|a[ée]ration|a[ée]r[ée]e?s?" + _F + r"|perfor[ée]e?s?" + _F +
    r"|perforations?" + _F + r"|"
    r"prises? d.air|entr[ée]es? d.air|flux d.air|circulation de l.air|airflow|"
    r"air vent", re.I)


# --- la matière DU GANT, pas d'une de ses pièces -------------------------------
#
# Motoblouz ne propose que trois valeurs sur sa facette « Matière » : cuir,
# cuir et textile, textile. Une seule valeur POUR LE GANT ENTIER — et c'est
# exactement ce que le rayon rend difficile, puisque les descriptions parlent
# pièce par pièce.
#
# La règle est donc nette : on ne conclut sur le gant QUE si le texte parle du
# gant. « Paume en cuir de chèvre » ne dit rien de la matière du gant, même
# quand la paume est en cuir et que le gant en a l'air. Un gant dont la paume
# est en cuir et le dos en mesh n'est pas un gant en cuir : c'est le « cuir et
# textile » de la facette, et rien dans la phrase sur la paume ne le dit.
#
# On ne déduit pas non plus la matière du gant de la paume PLUS le dos : un
# gant a six pièces, en connaître deux ne fait pas un inventaire. Deux tiers
# d'un fait ne sont pas un fait.
_CUIR_GANT = r"cuir|peau de ch[èe]vre|pleine fleur|kangourou|agneau|vachette|buffle"
_TEXTILE_GANT = (r"textile|tissu|maille|mesh|nylon|polyester|softshell|spandex|"
                 r"lycra|n[ée]opr[èe]ne|cordura|denim|toile|synth[ée]tique")

# Les deux formes où un marchand parle du gant ENTIER. La première est un
# cadeau de La Bécanerie, qui met la matière dans le titre : « Gants
# cuir/textile Held Score 4.0 », « Gants textile Harisson Marshall ».
_MATIERE_TITRE = re.compile(
    r"gants?\s+(?:moto\s+|cross\s+|enduro\s+|[ée]t[ée]\s+|hiver\s+)*"
    r"(cuir\s*/\s*textile|textile\s*/\s*cuir|cuir|textile)" + _F, re.I)

# La seconde est la phrase : « Les Forest sont des gants ENTIÈREMENT EN CUIR de
# chèvre », « Gants d'été Old school EN TEXTILE mesh ET CUIR ».
#
# Le remplissage entre « gants » et « en » ne peut contenir ni « : » ni « * » :
# ce sont les séparateurs de rubrique, et sans eux « Gants Trilobite Faster:
# Matière: PAUME EN CUIR de cerf » donnerait un gant tout cuir sur la foi de sa
# seule paume. C'est le piège que la propriétaire a nommé, et il tient dans
# deux caractères de classe.
#
# Et le remplissage ne peut pas davantage contenir un NOM DE PIÈCE. La phrase
# qui l'a montré, en bas d'une fiche Motoblouz :
#   « Les "+": GANTS confortables avec PAUME EN CUIR avec coque de protection »
# Ni deux-points ni astérisque entre « Gants » et « en cuir » — la garde de
# ponctuation ne voyait rien — et pourtant la phrase parle de la paume. Le gant
# en question a le dos en softshell : il n'est pas en cuir, il est en cuir et
# textile. Le seul faux positif de matière de la relecture, et c'était
# exactement le piège annoncé.
_MATIERE_PHRASE = re.compile(
    r"gants?\b([^.;:•*|]{0,45}?)\b(?:enti[èe]rement\s+|tout\s+|toute\s+|100\s?%\s+)?"
    r"en\s+([^.;:•*|]{0,45})", re.I)
# On coupe la fenêtre dès que la phrase quitte l'inventaire des matières.
_FIN_INVENTAIRE = r"\b(?:qui|que|pour|avec|offrant|afin|gr[âa]ce|permet|assur)"


def _matiere_du_gant(t: str) -> str | None:
    """Cuir, textile, ou les deux — pour le GANT, ou `None`."""
    m = _MATIERE_TITRE.search(t)
    if m:
        dit = m.group(1).lower()
        if "/" in dit:
            return "cuir et textile"
        return "cuir" if dit.startswith("cuir") else "textile"

    for m in _MATIERE_PHRASE.finditer(t):
        if re.search(_AUTRES_PIECES, m.group(1), re.I):
            continue          # « gants confortables avec paume en cuir » : la paume
        segment = re.split(_FIN_INVENTAIRE, m.group(2), maxsplit=1, flags=re.I)[0]
        cuir = bool(re.search(_CUIR_GANT, segment, re.I))
        textile = bool(re.search(_TEXTILE_GANT, segment, re.I))
        if cuir and textile:
            return "cuir et textile"
        if cuir:
            return "cuir"
        if textile:
            return "textile"
    return None


# --- Gore-Tex ------------------------------------------------------------------
#
# Motoblouz en fait une facette à trois valeurs, et la troisième — « oui,
# laminé » — n'est pas un détail de vocabulaire : un Gore-Tex laminé est collé
# à la matière extérieure, un Gore-Tex à doublure flottante (le « Z-liner »)
# ne l'est pas, et les mains ne restent pas sèches de la même façon.
#
# On ne rend jamais « non » : aucun marchand n'écrit qu'un gant N'A PAS de
# Gore-Tex, et l'absence de la marque dans un texte de soixante-quinze signes
# chez Speedway ne prouve rien.
_GORETEX = re.compile(r"gore[\s.\-]?tex|goretex|\bGTX\b|gore[\s.\-]?grip", re.I)
_GORETEX_LAMINE = re.compile(
    r"(?:gore[\s.\-]?tex|goretex|\bGTX\b|gore[\s.\-]?grip)[^.;]{0,40}lamin"
    r"|lamin\w*[^.;]{0,40}(?:gore[\s.\-]?tex|goretex|\bGTX\b|gore[\s.\-]?grip)", re.I)
# « Gore-Tex Z-liner » est justement l'inverse du laminé : la membrane y pend
# entre deux couches. Le mot « laminé » apparaît parfois dans la même phrase,
# pour parler d'AUTRE CHOSE — « Protection des articulations en cuir laminé ».
_Z_LINER = re.compile(r"z[\s.\-]?liner", re.I)

# --- gants chauffants ----------------------------------------------------------
#
# Une catégorie à part chez Motoblouz, et un objet différent : il a des piles.
# Le piège est dans le rayon lui-même, qui contient les accessoires : « Câble
# pour VÊTEMENT CHAUFFANT Gerbing DE CONNEXION BATTERIE MOTO » n'est pas un
# gant chauffant, c'est un câble. On exige donc le mot « gant ».
_CHAUFFANT = re.compile(
    r"gants?[^.;:•*|]{0,35}?\bchauff(?:ants?|[ée]e?s?)" + _F +
    r"|chauffants?\s+\w{0,12}\s?gants?|gants?[^.;]{0,30}syst[èe]me chauffant"
    r"|niveaux? de chauffe|technologie chauffante", re.I)

# --- univers de pratique -------------------------------------------------------
#
# LA caractéristique que le configurateur attend, et celle que les flux donnent
# le moins bien. Elle n'est dans AUCUNE taxonomie marchande : la colonne
# `category` des six flux porte la saison et la route-ou-cross, jamais
# l'univers. Il faut donc la lire dans la prose, et la prose est piégée.
#
# LE PIÈGE EST LE NOM DE MARQUE. « Gants cross FLY RACING Patrol », « Moose
# RACING MX1 », « FIRST RACING Scan » : trois fabricants de cross dont le nom
# contient « Racing ». Les lire comme des gants sport aurait classé le rayon
# tout-terrain en racing — un contresens complet, et sur la caractéristique
# dont dépend le configurateur. Même piège avec « Ixon Pro CUSTOM », qui est un
# nom de modèle de gant d'hiver, avec « Furygan TD VINTAGE », et avec
# « Protection articulations ADVENTURE injectée », qui est un nom de pièce.
#
# D'où la forme exigée : le mot d'univers doit suivre « gant(s) » avec, entre
# les deux, RIEN D'AUTRE qu'une saison ou un genre. Un nom propre s'y glisse,
# et la détection tombe.
_REMPLISSAGE = r"(?:moto\s+|de\s+moto\s+|[ée]t[ée]\s+|hiver\s+|mi.saison\s+|homme\s+|femme\s+|pour\s+)*"
_UNIVERS = [
    ("scooter",  r"gants?\s+" + _REMPLISSAGE + r"scooters?\b|scooters?[^.;]{0,15}gants?\b"),
    ("trail",    r"gants?\s+" + _REMPLISSAGE + r"(?:trail|adventure)\b|"
                 r"pens[ée]\w*\s+pour\s+l.aventure|pour\s+le\s+trail\b|usage\s+trail\b"),
    ("enduro",   r"gants?\s+" + _REMPLISSAGE + r"(?:enduro|tout.terrain)\b|"
                 r"gants?\s+tout\s+terrain\b"),
    ("touring",  r"gants?\s+" + _REMPLISSAGE + r"touring\b|grand\s+tourisme|"
                 r"gants?\s+" + _REMPLISSAGE + r"de\s+voyage\b"),
    ("custom",   r"gants?\s+" + _REMPLISSAGE + r"customs?\b|"
                 r"(?:style|look|esprit|allure)\s+(?:vintage|custom|r[ée]tro|old.school)|"
                 r"gants?\s+" + _REMPLISSAGE + r"(?:vintage|r[ée]tro|old.school)\b"),
    ("sport",   r"gants?\s+" + _REMPLISSAGE + r"(?:racing|sports?|sportifs?|sportives?)\b|"
                 r"gants?\s+" + _REMPLISSAGE + r"de\s+(?:piste|circuit)\b|"
                 r"usage\s+(?:racing|sur\s+circuit)\b"),
    ("roadster", r"gants?\s+" + _REMPLISSAGE + r"(?:roadsters?|urbains?|city)\b|"
                 r"(?:usage|utilisation|conduite|roulage)\s+urbaine?\b|"
                 r"urbaine?s?\s+et\s+\w+\s*,?\s*(?:les\s+)?gants?\b|"
                 r"se\s+portent?\s+(?:id[ée]alement\s+)?en\s+ville\b|"
                 r"pour\s+(?:la\s+conduite\s+en\s+ville|un\s+usage\s+en\s+ville)"),
]

# Le cross n'est PAS un des sept univers de la facette, et le rayon en est plein
# — un texte sur cinq. La Bécanerie écrit la même phrase de vente sur tous ses
# gants tout-terrain :
#   « Gants CROSS Fly Racing Evo 2.0 … Paire de gants MX Fly Racing Evo 2.0.
#     GANTS RACING premium. »
# « Gants racing » y est une formule de catalogue, pas un univers : ce gant ne
# verra jamais un circuit. Plutôt que de le ranger en « sport » — ce qui aurait
# rempli la caractéristique la plus attendue du configurateur avec le rayon
# cross au complet — on rend `None` et on le dit. Le cross mérite sa propre
# valeur ; l'inventer ici serait la deviner.
_CROSS = re.compile(r"\bcross\b|motocross|\bMX\b|\bsupercross\b", re.I)

# --- genre ---------------------------------------------------------------------
#
# « Enfant » l'emporte, parce qu'un gant cross enfant est d'abord un gant
# d'enfant et que la taille le suit. Entre « homme » et « femme », en revanche,
# deux mentions dans le même texte ne font pas un gant mixte : elles font un
# texte qu'on n'a pas compris. `None`.
_GENRES = [
    ("enfant", r"\benfants?\b|\bkids?\b|junior|\byouth\b|\bb[ée]b[ée]\b"),
    ("femme",  r"\bfemmes?\b|\bdames?\b|\blady\b|\bladies\b|\bwom[ae]n\b|f[ée]minin"),
    ("homme",  r"\bhommes?\b|masculin"),
    ("mixte",  r"\bmixte\b|unisexe?\b"),
]


@dataclass
class Gant:
    """Ce qu'on a su lire. `None` partout où on n'a pas su — jamais une valeur
    par défaut, qui se confondrait avec une mesure."""

    # Les facettes que le marchand expose lui-même, et que la propriétaire a
    # demandées nommément. Elles passent devant.
    matiere: str | None = None               # 'cuir', 'cuir et textile', 'textile'
    saison: str | None = None                # 'été', 'mi-saison', 'hiver'
    impermeable: bool | None = None
    gore_tex: str | None = None              # 'oui' ou 'oui, laminé'
    chauffant: bool | None = None
    univers: str | None = None               # custom, enduro, roadster, scooter,
    #                                          sport, touring, trail
    genre: str | None = None                 # homme, femme, adulte, enfant, mixte

    # Ce que le marchand N'EXPOSE PAS et qu'un comparateur peut lire à sa
    # place : les deux premiers critères d'achat du rayon.
    homologation: str | None = None          # 'EN 13594' ou 'CE'
    niveau: str | None = None                # '1' ou '2'
    kp: bool | None = None                   # protection des articulations certifiée
    matiere_paume: str | None = None
    matiere_dos: str | None = None
    coque_articulations: bool | None = None  # False = le texte dit qu'il n'y en a pas
    matiere_coque: str | None = None
    slider_paume: bool | None = None
    renfort_paume: bool | None = None
    protection_scaphoide: bool | None = None
    manchette: str | None = None             # 'courte', 'mi-longue', 'longue'
    doublure_thermique: bool | None = None
    tactile: bool | None = None
    ventilation: bool | None = None
    sources: list[str] = field(default_factory=list)

    _CHAMPS = ("matiere", "saison", "impermeable", "gore_tex", "chauffant",
               "univers", "genre",
               "homologation", "niveau", "kp", "matiere_paume", "matiere_dos",
               "coque_articulations", "matiere_coque", "slider_paume",
               "renfort_paume", "protection_scaphoide", "manchette",
               "doublure_thermique", "tactile", "ventilation")

    def renseignees(self) -> int:
        return sum(1 for c in self._CHAMPS if getattr(self, c) is not None)


def _homologation(t: str) -> tuple[str | None, str | None, bool | None]:
    """Norme, niveau, KP — la donnée que l'acheteur regarde en premier.

    Trois décisions y sont prises, et chacune vient d'une phrase réelle :

    - « CE » seul reste « CE ». Le promouvoir en « EN 13594 » lui prêterait une
      norme que le texte ne nomme pas.
    - un niveau n'est retenu que s'il est ADOSSÉ à une homologation, sinon
      « Richa LEVEL 2 in 1 Gore-Tex » devient un gant de niveau 2.
    - un niveau attaché à une PIÈCE n'est pas le niveau du gant :
      « Protections phalanges en Carbone homologuées CE niveau 2 ».
    """
    norme = None
    if _EN13594.search(t):
        norme = "EN 13594"
    else:
        for m in _CE.finditer(t):
            autour = t[max(0, m.start() - 45):m.end() + 45]
            if re.search(_AUTOUR_DE_CE, autour, re.I):
                norme = "CE"
                break

    niveau = None
    for m in _NIVEAU.finditer(t):
        avant = t[max(0, m.start() - 60):m.start()]
        apres = t[m.end():m.end() + 30]
        zone = avant + " " + apres
        if re.search(_NIVEAU_DE_CHAUFFE, zone, re.I):
            continue          # un niveau de chauffe, pas un niveau de protection
        if not (re.search(_ADOSSE_A_UNE_NORME, zone, re.I) or _CE.search(zone)):
            continue
        # La pièce doit être cherchée TOUT PRÈS : « Protections phalanges …
        # homologuées CE niveau 2 » tient en trente signes, alors que
        # « Homologués CE, niveau 1 KP » n'en contient aucune.
        if re.search(_PIECE_QUI_N_EST_PAS_LE_GANT + r"[^.;]{0,30}$", avant, re.I):
            continue
        valeur = m.group(1) or m.group(2)
        if niveau is not None and niveau != valeur:
            return norme, None, True if _KP.search(t) else None
        niveau = valeur

    kp = True if _KP.search(t) else None
    return norme, niveau, kp


def lire(titre: str, description: str) -> Gant:
    """Lit une paire de gants dans le texte d'un marchand.

    Le titre est concaténé à la description, et ce n'est pas un détail sur ce
    rayon : La Bécanerie écrit quatre-vingt-quatorze signes de description et
    met la saison dans le titre — « Gants été cuir/textile femme … ». Chez
    FC-Moto, c'est l'imperméabilité qui n'est que dans le titre.
    """
    t = " ".join(((titre or "") + " " + (description or "")).split())
    g = Gant()
    if not t:
        return g

    g.matiere = _matiere_du_gant(t)

    if _GORETEX.search(t):
        g.gore_tex = "oui, laminé" if (_GORETEX_LAMINE.search(t)
                                       and not _Z_LINER.search(t)) else "oui"
    if _CHAUFFANT.search(t):
        g.chauffant = True

    univers = {nom for nom, motif in _UNIVERS if re.search(motif, t, re.I)}
    if len(univers) == 1 and not _CROSS.search(t):
        g.univers = univers.pop()

    for nom, motif in _GENRES:
        if re.search(motif, t, re.I):
            if nom == "enfant":
                g.genre = nom
                break
            # Entre homme, femme et mixte, une seule mention fait foi.
            autres = {n for n, mo in _GENRES[1:]
                      if n != "enfant" and re.search(mo, t, re.I)}
            g.genre = autres.pop() if len(autres) == 1 else None
            break

    g.homologation, g.niveau, g.kp = _homologation(t)

    g.matiere_paume = _matiere_de(t, _PAUME)
    g.matiere_dos = _matiere_de(t, _DOS)

    g.coque_articulations, g.matiere_coque = _coque(t)

    g.slider_paume = _slider_paume(t)

    for attribut, motif in (("renfort_paume", _RENFORT_PAUME),
                            ("protection_scaphoide", _SCAPHOIDE)):
        m = motif.search(t)
        if m:
            setattr(g, attribut, not _nie_avant(t, m.start()))

    for nom, motif in _MANCHETTE:
        if re.search(motif, t, re.I):
            g.manchette = nom
            break

    if _IMPERMEABLE.search(t):
        m = _IMPERMEABLE.search(t)
        if not _nie_avant(t, m.start()):
            g.impermeable = True
    if g.impermeable is None and _PAS_IMPERMEABLE.search(t):
        # Le texte parle d'eau sans promettre l'étanchéité. On ne rend pas
        # False — il n'affirme pas l'absence, il affirme AUTRE CHOSE.
        g.impermeable = None

    # Ces trois-là n'ont pas de valeur négative : un gant a des perforations ou
    # n'en a pas, et le texte ne dit jamais qu'il n'en a pas — il se tait. On
    # rend donc True, ou None, jamais False.
    if _THERMIQUE.search(t):
        g.doublure_thermique = True
    if _TACTILE.search(t):
        g.tactile = True
    if _VENTILATION.search(t):
        g.ventilation = True

    saisons = {nom for nom, motif in _SAISONS if re.search(motif, t, re.I)}
    if len(saisons) == 1:
        g.saison = saisons.pop()

    return g


def fusionner(lectures: list[Gant]) -> Gant:
    """Une fiche, plusieurs marchands : on réunit ce que chacun a su dire.

    La première valeur trouvée gagne, et l'ordre d'appel fait la priorité —
    l'appelant passe les marchands du plus disert au plus avare. Sur un
    désaccord franc entre deux marchands À PROPOS DE LA NORME OU DU NIVEAU, on
    ABANDONNE la valeur : deux sources qui se contredisent sur une donnée de
    sécurité ne valent pas mieux qu'aucune source.

    Les autres champs ne sont pas traités ainsi, et c'est volontaire : que
    Motoblouz décrive une paume en cuir quand FC-Moto n'en dit rien n'est pas
    un désaccord, c'est un silence.
    """
    out = Gant()
    normes = {l.homologation for l in lectures if l.homologation}
    niveaux = {l.niveau for l in lectures if l.niveau}
    matieres = {l.matiere for l in lectures if l.matiere}

    for l in lectures:
        for champ in Gant._CHAMPS:
            if champ in ("homologation", "niveau", "matiere"):
                continue
            if getattr(out, champ) is None and getattr(l, champ) is not None:
                setattr(out, champ, getattr(l, champ))

    # « EN 13594 » et « CE » ne se contredisent pas : le second est le genre du
    # premier. Un marchand précis et un marchand vague disent la même chose, et
    # c'est le précis qu'on garde.
    if "EN 13594" in normes:
        out.homologation = "EN 13594"
    elif len(normes) == 1:
        out.homologation = normes.pop()
    if len(niveaux) == 1:
        out.niveau = niveaux.pop()

    # « cuir et textile » n'est pas un désaccord avec « cuir » : c'est le
    # marchand qui a vu les deux matières et celui qui n'en a nommé qu'une. Le
    # plus complet gagne.
    #
    # En revanche, « cuir » contre « textile » sans personne pour dire les
    # deux, on ABANDONNE. La tentation est d'en conclure « cuir et textile » —
    # les deux marchands auraient chacun vu une moitié. Mais c'est une
    # déduction, pas une lecture, et elle se trompe exactement dans le cas où
    # l'un des deux marchands s'est trompé.
    if "cuir et textile" in matieres:
        out.matiere = "cuir et textile"
    elif len(matieres) == 1:
        out.matiere = matieres.pop()

    return out
