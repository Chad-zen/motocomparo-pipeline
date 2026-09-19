"""Reconnaître un modèle de casque dans un titre marchand — commun à toutes les
sources externes.

Ce module a été extrait de `rapprochement.py` (le premier écrit, pour SHARP) au
moment où une deuxième source — un revendeur — s'est trouvée devant
EXACTEMENT les mêmes pièges : le même modèle prolongé qui vole la note d'une
version plus ancienne, la même pièce détachée qui porte le nom d'un vrai
casque, la même marque écrite différemment d'une source à l'autre.

Deux façons de reconnaître un modèle finissent toujours par diverger. Il n'y en
a plus qu'une, et les deux sources la partagent — voir `rapprochement.py`
(SHARP) et `rapprochement_revendeur.py`.
"""

from __future__ import annotations

import re
import unicodedata

_SEPARATEURS = re.compile(r"[^a-z0-9]+")
_LETTRES_CHIFFRES = re.compile(r"[a-z]+|[0-9]+")


def jetons(texte: str) -> list[str]:
    """« Exo-R1 Evo » -> ['exo', 'r', '1', 'evo'].

    Les chiffres sont séparés des lettres pour que « K7 » et « K-7 » donnent la
    même chose : les marchands ponctuent au hasard et le fabricant lui-même
    change d'avis d'une gamme à l'autre.
    """
    sans_accent = unicodedata.normalize("NFKD", texte.lower())
    sans_accent = "".join(c for c in sans_accent if not unicodedata.combining(c))
    mots = _SEPARATEURS.sub(" ", sans_accent).split()
    return [m for mot in mots for m in _LETTRES_CHIFFRES.findall(mot)]


def marque(texte: str) -> str:
    """La marque, ramenée à la forme des `brand_code` de la base."""
    return "".join(jetons(texte))


# Des mots qui apparaissent dans les titres marchands sans rien dire du modèle.
# Ils ne sont PAS retirés du titre — un modèle peut légitimement s'appeler
# « Sport » — mais un modèle réduit à ces seuls mots est refusé, parce qu'il
# correspondrait à la moitié du catalogue.
TROP_COMMUN = {
    "casque", "helmet", "moto", "integral", "jet", "cross", "modulable",
    "sport", "touring", "carbon", "carbone", "solid", "mono", "noir", "black",
    "blanc", "white", "mat", "matt", "gloss", "evo", "air", "pro", "plus",
}

# CE QUI, JUSTE APRÈS LE MODÈLE, SIGNALE UN AUTRE MODÈLE.
#
# « Le plus long gagne » ne protège que des modèles que LA SOURCE CONNAÎT. Le
# vrai danger est ailleurs : le titre nomme une version que la source n'a
# jamais recensée, et le rapprochement retombe sur l'ancienne. Relevé côté
# SHARP, sur un échantillon de vingt, à la troisième relecture :
#
#     HJC C91N          prenait la note du C91
#     Shark D-Skwal 3   celle du D-Skwal
#     Shark Skwal Cup   celle du Skwal
#     Arai RX-7V Evo    celle du RX-7V
#     Caberg Drift Evo II   celle du Drift Evo
#
# Aucun de ces cinq n'était au catalogue SHARP. Le rapprochement ne pouvait
# donc PAS se trancher par comparaison entre candidats : il n'y avait qu'un
# candidat, et il était faux. Le même défaut guette le revendeur, dont le
# catalogue est certes plus large, mais jamais exhaustif.
#
# Ce qui les trahit, c'est le jeton qui suit : un chiffre, un chiffre romain,
# une lettre seule, ou un des mots dont les constructeurs se servent pour
# désigner une évolution. Une déclinaison de COULEUR, elle, s'appelle
# « Supra », « Blank », « Raceshop », « Nepos » — des noms qui ne ressemblent à
# rien de cette liste.
#
# On perd des rapprochements justes au passage : un casque dont le coloris
# s'appellerait « Max » sera écarté. C'est le sens de l'échange — une fiche
# muette contre une note fausse.
SUITE_DE_MODELE = {
    "evo", "evolution", "cup", "gt", "rs", "rr", "sv", "sr", "sp", "pro",
    "plus", "carbon", "carbone", "max", "mini", "ii", "iii", "iv", "bis",
    "mips", "ece", "tech",
}


def est_une_suite(jeton: str) -> bool:
    """Le jeton prolonge-t-il le nom du modèle, plutôt que de le décorer ?"""
    return jeton.isdigit() or len(jeton) == 1 or jeton in SUITE_DE_MODELE


def contient(titre: list[str], modele: list[str]) -> bool:
    """`modele` apparaît-il dans `titre` SANS y être prolongé ?

    Le modèle doit s'y trouver tel quel, et ce qui le suit ne doit pas en faire
    un autre modèle. Toutes les positions sont essayées : il suffit qu'UNE
    seule soit propre, parce qu'un titre peut répéter le nom du casque
    (« Casque Shark Skwal i3 — ... — Casque Shark »).
    """
    if not modele or len(modele) > len(titre):
        return False
    for i in range(len(titre) - len(modele) + 1):
        if titre[i:i + len(modele)] != modele:
            continue
        apres = i + len(modele)
        if apres >= len(titre) or not est_une_suite(titre[apres]):
            return True
    return False


def choisir(titre: str, candidats: list) -> object | None:
    """Le modèle que ce titre désigne parmi les candidats d'UNE marque, ou rien.

    `candidats` est une liste d'objets qui portent au moins un attribut
    `.jetons` — chaque source définit son propre conteneur (`Candidat` dans
    `rapprochement.py` et dans `rapprochement_revendeur.py`), trop différents
    l'un de l'autre pour partager une classe. Seul l'algorithme se partage.

    Rien, aussi, quand deux modèles de même longueur correspondent : c'est le
    cas où un rapprochement automatique se trompe une fois sur deux, et une
    fiche muette vaut mieux qu'un tirage au sort.
    """
    jetons_titre = jetons(titre)
    trouves = [c for c in candidats if contient(jetons_titre, c.jetons)]
    if not trouves:
        return None
    plus_long = len(trouves[0].jetons)
    meilleurs = [c for c in trouves if len(c.jetons) == plus_long]
    return meilleurs[0] if len(meilleurs) == 1 else None


# CE QUI SE VEND DANS LE RAYON CASQUE SANS ÊTRE UN CASQUE.
#
# Le rayon ne contient pas que des casques : il contient aussi de quoi les
# réparer. Coiffes, mousses de joues, mentonnières, écrans, pare-soleil — et
# tous portent le nom du modèle auquel ils vont, forcément. Le défaut est
# apparu deux fois, identique, sur les deux sources : « Mentonnière HJC RPHA
# 90S » et « Scorpion Exo-Tech Visor » se présentaient toutes les deux comme
# des casques.
_ACCESSOIRE = re.compile(
    r"pi[eè]ces? d[eé]tach|coiffe|mousses?|mentonni[èe]re|pare.?soleil|"
    r"visi[èe]re|\bvisors?\b|[ée]cran|bulle|support|fixation|adaptateur|"
    r"sac de casque|housse|antibu[ée]e|pinlock|sangle|jugulaire|"
    r"a[ée]rations? de rechange|aileron|becquet|spoiler|d[ée]flecteur|"
    r"cache.?nez|bavette|molette|m[ée]canisme|platine|\bvis\b|plaquettes?|"
    r"coussinets?|viseur|kit int[ée]rieur|garniture|couronne|"
    r"\bcheek ?pads?\b|\bliners?\b|\bshield\b", re.I)
_CASQUE = re.compile(r"\bcasques?\b|\bhelmets?\b", re.I)


def est_un_casque(titre: str) -> bool:
    """Le titre désigne-t-il un casque, ou une pièce qui va dessus ?

    LA POSITION TRANCHE, PAS LA PRÉSENCE. « Casque intégral Shark SKWAL i3 —
    MAYFER + ÉCRAN IRIDIUM » est un vrai casque, livré avec un écran ; une
    exclusion sur le seul mot « écran » l'aurait écarté avec les pièces
    détachées. Ce qui distingue les deux, c'est l'ordre : dans une pièce de
    rechange, le nom de la pièce arrive AVANT le mot « casque », parce que
    c'est elle qu'on vend.
    """
    accessoire = _ACCESSOIRE.search(titre)
    if not accessoire:
        return True
    casque = _CASQUE.search(titre)
    return casque is not None and casque.start() < accessoire.start()
