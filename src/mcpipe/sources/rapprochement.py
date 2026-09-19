"""Coller la bonne mesure SHARP sur la bonne fiche.

SHARP écrit « AGV / K7 ». Le marchand écrit « Casque intégral AGV K-7 Mono Noir
Mat ». Il faut relier les deux, et c'est la partie fragile de toute l'affaire —
bien plus que le relevé, qui est exact.

LE DANGER N'EST PAS DE RATER UN RAPPROCHEMENT, C'EST D'EN FAIRE UN FAUX.
Une fiche sans note affiche simplement moins de choses. Une fiche qui porte les
cinq étoiles du voisin ment à quelqu'un qui achète un casque pour sa tête. Les
deux coûtent le même effort à produire et ne se ressemblent pas du tout.

CE QUI EST ICI, ET CE QUI EST DANS `correspondance.py`. La reconnaissance d'un
modèle dans un titre — jetons, garde de prolongement, garde d'accessoire — est
commune à toute source externe : le revendeur a affronté exactement les
mêmes pièges. Ce fichier ne garde que ce qui est SPÉCIFIQUE à SHARP : ses
colonnes, ses noms de caractéristiques, et la garde de FORME (jet/cross jamais
testés) qui dépend de ce que SHARP, précisément, sait tester.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..db import connect
from .correspondance import TROP_COMMUN as _TROP_COMMUN
from .correspondance import choisir as choisir
from .correspondance import contient as _contient
from .correspondance import est_un_casque as est_un_casque
from .correspondance import est_une_suite as _est_une_suite
from .correspondance import jetons as _jetons
from .correspondance import marque as _marque

# Les rayons casque : parent, intégral, jet, cross, modulable.
CATEGORIES_CASQUE = (1, 2, 3, 4, 5)

# Ce que SHARP publie, et sous quel nom on le range dans `product_caracteristique`.
# Seulement ce qui est MESURÉ ou RELEVÉ par le laboratoire — le prix conseillé
# britannique n'a rien à faire sur une fiche française, et les tailles testées
# ne sont pas les tailles vendues ici.
#
# `poids_g` GARDE LE NOM DU FLUX, à dessein : avant la migration 025, SHARP
# écrivait sous « poids » pour ne pas écraser le « poids_g » du flux au même
# product_id — deux noms pour la même idée, uniquement pour ne pas se
# percuter. La clé porte maintenant la source ; les deux lignes coexistent
# sans conflit, et rien n'empêche plus de leur donner le même nom. Une future
# page produit qui chercherait « le poids » n'a plus qu'un seul nom à chercher,
# quelle que soit la source qui a répondu.
_A_RETENIR = {
    "etoiles": "note_securite",
    "poids_g": "poids_g",
}

# CE QUE SHARP TESTE, ET CE QU'IL NE TESTE PAS.
#
# Sur 585 fiches : 442 intégraux, 142 modulables, et RIEN D'AUTRE. Pas un seul
# jet, pas un seul cross. Ce n'est pas un trou dans leur catalogue, c'est le
# périmètre du programme.
#
# La conséquence est une garde bien plus solide qu'une liste de mots : une fiche
# rangée en « casque jet » ou en « casque cross » qui reçoit une note SHARP est
# fausse PAR CONSTRUCTION, quelle que soit la ressemblance des noms. Le « Shark
# Skwal Jet » en est l'exemple : SHARP a testé le Skwal, qui est un intégral, et
# le jet du même nom héritait de sa note.
#
# L'inverse est vrai aussi : un modulable ne prend pas la note d'un intégral.
# Les constructeurs réemploient leurs noms d'une forme à l'autre, et ce sont
# deux structures différentes — c'est précisément la mentonnière qui change.
_TYPE_SHARP_VERS_CATEGORIE = {
    "full face": 2,                    # casques intégraux
    "system (modular/flip-up)": 4,     # casques modulables
}
# Les catégories où SHARP n'a, par définition, rien à dire.
_JAMAIS_TESTE = (3, 5)                 # jet, cross


def type_compatible(categorie_id: int, type_sharp: str | None) -> bool:
    """La forme du casque relevée par SHARP et la nôtre disent-elles la même chose ?

    Le rayon parent (`helmet`, id 1) passe : c'est la catégorie des fiches dont
    on n'a pas su dire la forme, et lui refuser la note reviendrait à punir une
    fiche mal rangée plutôt qu'un rapprochement douteux.
    """
    if categorie_id in _JAMAIS_TESTE:
        return False
    attendue = _TYPE_SHARP_VERS_CATEGORIE.get((type_sharp or "").strip().lower())
    if attendue is None:
        return False       # « Non-protective lower faceguard » et compagnie
    return categorie_id == attendue or categorie_id == 1


@dataclass
class Candidat:
    """Un modèle SHARP, prêt à être recherché dans un titre.

    Pas partagé avec `correspondance.py` : chaque source a sa propre forme de
    données (SHARP porte `type_casque`, le revendeur porte tout autre chose), et ce
    conteneur est trop petit pour justifier une hiérarchie de classes. Ce qui
    EST partagé, et c'est ce qui comptait, c'est l'algorithme de reconnaissance
    — `contient`, `choisir`, la garde de prolongement, la garde d'accessoire.
    """
    slug: str
    marque: str
    modele: str
    jetons: list[str]
    valeurs: dict[str, str]
    type_casque: str | None = None


def _candidats(conn) -> dict[str, list[Candidat]]:
    """marque -> modèles SHARP, du plus long au plus court."""
    par_marque: dict[str, list[Candidat]] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT slug, marque, modele, etoiles, poids_g, type_casque "
                    "FROM source_sharp")
        for slug, marque, modele, etoiles, poids_g, type_casque in cur:
            jt = _jetons(modele or "")
            if not jt or set(jt) <= _TROP_COMMUN:
                continue
            valeurs = {}
            if etoiles is not None:
                valeurs[_A_RETENIR["etoiles"]] = str(etoiles)
            if poids_g is not None:
                valeurs[_A_RETENIR["poids_g"]] = str(poids_g)
            if not valeurs:
                continue
            par_marque.setdefault(_marque(marque), []).append(
                Candidat(slug, marque, modele, jt, valeurs, type_casque))
    for liste in par_marque.values():
        liste.sort(key=lambda c: len(c.jetons), reverse=True)
    return par_marque


def rapprocher(trace=print) -> tuple[int, int, int, int, int]:
    """Écrit les mesures SHARP sur les fiches casque qu'on sait identifier.

    Rend (fiches rapprochées, valeurs écrites, écartées pour ambiguïté,
    écartées parce que ce n'est pas un casque, écartées pour la forme).
    Rejouable : l'écriture n'efface que ce qui vient de SHARP.
    """
    conn = connect()
    try:
        par_marque = _candidats(conn)
        if not par_marque:
            raise RuntimeError(
                "aucun modèle SHARP en base : lancer `mcpipe sharp` d'abord")
        trace(f"{sum(len(v) for v in par_marque.values())} modèles SHARP, "
              f"{len(par_marque)} marques")

        with conn.cursor() as cur:
            cur.execute("""
                SELECT p.id, p.brand_code, s.best_title, p.category_id
                FROM product p JOIN product_stats s ON s.product_id = p.id
                WHERE p.category_id = ANY(%s) AND p.status <> 'merged'
                  AND s.best_title IS NOT NULL
            """, (list(CATEGORIES_CASQUE),))
            fiches = cur.fetchall()

        rapprochees = valeurs_ecrites = ambigues = accessoires = formes = 0
        with conn.cursor() as cur:
            cur.execute("DELETE FROM product_caracteristique WHERE source = 'sharp'")
            for pid, marque, titre, categorie in fiches:
                if not est_un_casque(titre):
                    accessoires += 1
                    continue
                candidats = par_marque.get(_marque(marque or ""))
                if not candidats:
                    continue
                jetons_titre = _jetons(titre)
                trouves = [c for c in candidats if _contient(jetons_titre, c.jetons)]
                if not trouves:
                    continue
                choisi = choisir(titre, candidats)
                if choisi is None:
                    ambigues += 1
                    continue
                if not type_compatible(categorie, choisi.type_casque):
                    formes += 1
                    continue
                for nom, valeur in choisi.valeurs.items():
                    cur.execute("""
                        INSERT INTO product_caracteristique
                            (product_id, nom, valeur, source, confiance)
                        VALUES (%s, %s, %s, 'sharp', 'mesuree')
                        ON CONFLICT (product_id, nom, source) DO UPDATE SET
                            valeur = EXCLUDED.valeur, source = EXCLUDED.source,
                            confiance = EXCLUDED.confiance, calcule_le = now()
                    """, (pid, nom, valeur))
                    valeurs_ecrites += 1
                rapprochees += 1
        conn.commit()
        return rapprochees, valeurs_ecrites, ambigues, accessoires, formes
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
