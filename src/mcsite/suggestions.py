"""Ce que la barre de recherche propose pendant qu'on tape.

L'idée, reprise d'idealo et d'Amazon : on ne devine pas ce que quelqu'un
cherche, on lui montre les chemins qui existent. Taper « arai » ne doit pas
seulement mener à une liste de 147 produits — ça doit dire « Arai, il y en a
dans Casques, et trois dans Accessoires », et laisser choisir.

C'est l'entonnoir : une marque, puis le rayon, sans quitter la recherche.

CE QUI VIENT DE LA MÉMOIRE ET CE QUI VIENT DE LA BASE
=====================================================

La ventilation marque × rayon — 711 lignes, 217 marques, 70 Ko — ne change
qu'au passage du pipeline, une fois par jour. Elle est calculée d'un coup et
gardée au chaud ; tout le filtrage se fait ensuite en mémoire, donc en zéro
milliseconde. Les produits, eux, ne peuvent pas se précalculer : ils viennent de
la base à chaque requête, servis par l'index de trigrammes.

Mesuré le 17/09/2026 : une requête par frappe sur la marque coûtait 130 ms de
base, parce que `f_unaccent(brand_code)` interdit l'index et force un balayage
des 313 000 fiches. Taper « alpinestars » lançait douze balayages complets. Sur
un VPS à un cœur, la barre de recherche aurait mis le site à genoux à elle
seule.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from . import labels

# En dessous de deux caractères, tout correspond : la liste proposée serait
# l'alphabet des marques, ce qui n'aide personne et interroge la base pour rien.
MINIMUM = 2

# La ponctuation est RECOLLÉE, pas remplacée par une espace — exactement comme
# `f_recherche()` le fait côté base (migration 018). « sz-r » devient « szr »
# des deux côtés.
#
# C'est une symétrie, et elle n'a pas le droit d'être approximative : soignée en
# base et oubliée ici, « sz-r » se découpait en « sz » et « r », deux mots que
# le texte indexé ne contient plus. Quelqu'un qui tape le nom AVEC son tiret —
# c'est-à-dire correctement — ne trouvait rien.
_COLLES = re.compile(r"""[-._/'"()\[\]]+""")
_SEPARATEURS = re.compile(r"[^a-z0-9]+")


def sans_accent(texte: str) -> str:
    """« Bécanerie » et « becanerie » doivent se rencontrer."""
    return "".join(
        c for c in unicodedata.normalize("NFD", (texte or "").lower())
        if unicodedata.category(c) != "Mn"
    )


def mots(texte: str) -> list[str]:
    """Les mots cherchés, écrits comme le texte dans lequel on les cherche."""
    colle = _COLLES.sub("", sans_accent(texte))
    return [m for m in _SEPARATEURS.split(colle) if m]


def _distance(a: str, b: str, plafond: int) -> int:
    """Distance de Levenshtein, abandonnée dès qu'elle dépasse le plafond.

    Écrite ici plutôt qu'installée : elle tourne sur 217 noms de marque de dix
    lettres, ce qui se compte en microsecondes, et une dépendance de plus sur un
    serveur à un cœur se paie à chaque déploiement.

    C'est la bonne mesure pour une faute de frappe, là où les trigrammes sont
    aveugles : « arei » et « arai » ne partagent que 0,25 de trigrammes — bien
    trop peu pour franchir un seuil — mais une seule lettre les sépare.

    Les inversions de lettres comptent pour UNE faute (Damerau) : « shoie » pour
    « shoei » est la faute la plus courante au clavier, et sans cela elle en
    coûterait deux.
    """
    if abs(len(a) - len(b)) > plafond:
        return plafond + 1
    avant_precedent: list[int] = []
    precedent = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        courant = [i]
        for j, cb in enumerate(b, 1):
            cout = min(precedent[j] + 1,
                       courant[j - 1] + 1,
                       precedent[j - 1] + (ca != cb))
            # L'INVERSION DE DEUX LETTRES compte pour une faute, pas deux.
            # « shoie » pour « shoei », « arai » pour « arla » : c'est la faute
            # de frappe la plus courante au clavier, et sans cette ligne elle
            # coûte deux points — donc elle n'est jamais rattrapée.
            if (i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb):
                cout = min(cout, avant_precedent[j - 2] + 1)
            courant.append(cout)
        if min(courant) > plafond:
            return plafond + 1
        avant_precedent, precedent = precedent, courant
    return precedent[-1]


def reconnaitre_marque(mots_tapes: list[str],
                       noms: list[str]) -> tuple[str | None, list[str]]:
    """Trouve la marque dans ce qui est tapé, et rend le reste.

    Trois passes, de la plus sûre à la plus indulgente :

    1. le mot EST une marque — « arai » ;
    2. le mot commence une marque — « alpin » pour Alpinestars ;
    3. le mot est à une faute près d'une marque — « arei » pour « arai ».

    La troisième descend jusqu'à trois lettres, mais exige d'être **certaine** :
    une seule marque à une faute près. C'est la garde qui compte, bien plus que
    la longueur — « aai » ne ressemble qu'à « arai », on corrige ; un mot de
    trois lettres proche de deux marques resterait ambigu, on s'abstient.

    La version d'avant refusait tout mot de moins de quatre lettres, et « aai »
    — un « r » oublié — ne trouvait donc rien du tout.

    Reconnaître la marque change tout le reste : on ne cherche plus dans 313 000
    fiches mais dans les quelques centaines de cette marque, et on peut donc y
    classer par ressemblance SANS seuil — c'est ce qui permet à « zzr » de
    trouver « SZ-R ».
    """
    connus = set(noms)
    for i, mot in enumerate(mots_tapes):
        if mot in connus:
            return mot, mots_tapes[:i] + mots_tapes[i + 1:]

    for i, mot in enumerate(mots_tapes):
        if len(mot) >= 3:
            debuts = sorted((n for n in noms if n.startswith(mot)), key=len)
            if debuts:
                return debuts[0], mots_tapes[:i] + mots_tapes[i + 1:]

    seul = len(mots_tapes) == 1
    for i, mot in enumerate(mots_tapes):
        # Un mot COURT et SEUL n'est pas corrigé. « sz-r » tapé tout seul est un
        # nom de modèle, pas une marque mal orthographiée — et il se trouve
        # qu'il n'est qu'à une lettre de la marque SGR. Corrigé, il envoyait
        # chez SGR quelqu'un qui cherchait un casque Arai.
        #
        # Accompagné — « aai sz-r » — le doute tombe : un mot court à côté d'un
        # nom de modèle est bien la marque, et c'est là qu'on rattrape la lettre
        # oubliée.
        if len(mot) < 3 or (len(mot) < 4 and seul):
            continue
        proches = [n for n in noms
                   if abs(len(n) - len(mot)) <= 1 and _distance(mot, n, 1) <= 1]
        # UNE SEULE candidate, sinon on se tait. Corriger vers l'une de deux
        # marques possibles, c'est choisir à la place de quelqu'un qui n'a rien
        # demandé — et le renvoyer chez un concurrent de ce qu'il cherchait.
        if len(proches) == 1:
            return proches[0], mots_tapes[:i] + mots_tapes[i + 1:]

    return None, mots_tapes


def _marques(matrice: list[dict[str, Any]], q: str) -> list[dict[str, Any]]:
    """Les marques dont le nom COMMENCE par ce qui est tapé, puis les autres.

    Le début du mot pèse plus lourd que le milieu : quelqu'un qui tape « ara »
    cherche Arai, pas « Barracuda ». Les deux sont proposés, dans cet ordre.
    """
    total: dict[str, int] = {}
    for ligne in matrice:
        total[ligne["marque"]] = total.get(ligne["marque"], 0) + ligne["n"]

    debut, dedans = [], []
    for marque, n in total.items():
        sans = sans_accent(marque)
        if sans.startswith(q):
            debut.append((marque, n))
        elif q in sans:
            dedans.append((marque, n))
    debut.sort(key=lambda t: -t[1])
    dedans.sort(key=lambda t: -t[1])
    return [{"marque": m, "n": n} for m, n in (debut + dedans)]


def _entonnoir(matrice: list[dict[str, Any]], marque: str) -> list[dict[str, Any]]:
    """Les rayons où cette marque existe, du plus fourni au moins fourni."""
    lignes = [dict(x) for x in matrice if x["marque"] == marque]
    lignes.sort(key=lambda x: -x["n"])
    return lignes


def construire(texte: str, matrice: list[dict[str, Any]],
               rayons: list[dict[str, Any]],
               produits: list[dict[str, Any]],
               nom, marque_reconnue: str | None = None,
               mots_restants: list[str] | None = None) -> dict[str, Any]:
    """Assemble la réponse. Aucune requête ici : tout est déjà là.

    `nom` est la fonction qui fabrique le nom affichable d'une fiche — la même
    que celle des pages, pour qu'un produit ne s'appelle pas autrement dans la
    liste déroulante que sur sa propre page.
    """
    q = sans_accent(texte).strip()
    if len(q) < MINIMUM:
        return {"marque_seule": None, "meilleurs": [], "marque_reconnue": None,
                "marques": [], "entonnoir": [], "rayons": [], "produits": []}

    trouvees = _marques(matrice, q)

    # L'entonnoir ne s'ouvre que sur la MEILLEURE marque, et seulement si elle
    # est franche : proposer « X dans Casques » pour quatre marques à la fois
    # remplirait la liste de chemins qu'on n'a pas demandés.
    #
    # `marque_reconnue` l'emporte quand elle existe : c'est elle qui a survécu à
    # la faute de frappe. Quelqu'un qui tape « arei szr » n'a aucune marque dont
    # le nom commence par « arei szr » — sans cette priorité, l'entonnoir
    # resterait fermé alors qu'on sait très bien qu'il cherche Arai.
    entonnoir: list[dict[str, Any]] = []
    premiere = marque_reconnue
    if not premiere and trouvees and sans_accent(trouvees[0]["marque"]).startswith(q):
        premiere = trouvees[0]["marque"]
    if premiere:
        entonnoir = _entonnoir(matrice, premiere)
        for e in entonnoir:
            e["marque"] = premiere

    vus = set()
    rayons_trouves = []
    for r in rayons:
        if q in sans_accent(r.get("label_fr") or "") and r["id"] not in vus:
            vus.add(r["id"])
            rayons_trouves.append({"id": r["id"], "code": r["code"],
                                   "label": r["label_fr"]})

    liste = _produits(produits, nom)

    # QUELQU'UN QUI TAPE UNE MARQUE, ET RIEN D'AUTRE, VEUT LA MARQUE.
    #
    # « arai » seul ne désigne aucun casque en particulier : mettre trois Arai
    # en grand revient à en choisir trois au hasard parmi 147 et à les présenter
    # comme la réponse. Ce qu'il veut, c'est entrer chez Arai — par la porte
    # principale ou par un rayon.
    #
    # Dès qu'un mot accompagne la marque — « arai szr » — il cherche un produit,
    # et les mises en avant reprennent leur sens.
    marque_seule = None
    if marque_reconnue and not (mots_restants or []):
        total = sum(x["n"] for x in matrice if x["marque"] == marque_reconnue)
        marque_seule = {
            "marque": marque_reconnue,
            "n": total,
            # Une photo prise sur la fiche la plus comparée de la marque : un
            # nom de marque seul, dans une liste qui montre des produits
            # partout ailleurs, fait un trou.
            "image": liste[0]["image"] if liste else None,
        }
    # LES MEILLEURS RÉSULTATS, mis à part et montrés en grand — trois, pas un.
    #
    # Un seul supposait qu'on sait lequel est le bon. Or « arai szr » rend six
    # SZ-R qui ne diffèrent que par la finition, et « shoei neotec » un Neotec 2
    # et un Neotec 3 : désigner un vainqueur, c'est cacher les deux autres
    # réponses également valables. Trois laissent le choix sans noyer.
    #
    # Trois et pas cinq : au-delà, la liste des chemins — marques, rayons —
    # passe sous la ligne de flottaison, et c'est elle qui fait l'intérêt de
    # cette barre de recherche.
    meilleurs = [] if marque_seule else liste[:3]

    return {
        "marque_seule": marque_seule,
        "meilleurs": meilleurs,
        "marque_reconnue": marque_reconnue,
        "marques": trouvees[:5],
        "entonnoir": entonnoir[:5],
        "rayons": rayons_trouves[:4],
        "produits": liste if marque_seule else liste[3:],
    }


def _couleur(code: str | None) -> str:
    """Le nom de la couleur, ou rien.

    Sans elle, chercher « arai szr » proposait trois fois « Casque jet Arai SZ-R
    VAS EVO - SOLID » : trois coloris distincts, trois lignes jumelles, et aucun
    moyen de les départager autrement qu'en ouvrant les trois. La couleur est
    souvent la seule chose qui sépare deux fiches d'un même modèle.
    """
    if not code or code == "unknown":
        return ""
    return labels.colour(code)


def _produits(produits: list[dict[str, Any]], nom) -> list[dict[str, Any]]:
    """Les fiches, telles que la liste doit les rendre."""
    return [
        {
            "slug": p["slug"],
            "nom": nom(p),
            "couleur": _couleur(p.get("colour_code")),
            "marque": (p.get("brand_code") or "").upper(),
            "prix": float(p["cheapest"]) if p.get("cheapest") is not None else None,
            "marchands": p.get("merchant_count"),
            "image": p.get("image_url"),
        }
        for p in produits
    ]
