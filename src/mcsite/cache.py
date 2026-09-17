"""Garder au chaud ce qui ne change qu'une fois par jour.

Trois requêtes tournaient à CHAQUE page : le menu des rayons, la liste des
marques et le compte de fiches par marchand. Ce sont des agrégations sur tout
le catalogue — 312 000 fiches — dont le résultat est identique pour tous les
visiteurs et ne bouge qu'après un passage du pipeline, c'est-à-dire une fois
par jour.

Mesuré le 2026-09-14, après que le catalogue soit passé de 244 000 à 312 000
fiches : la page d'accueil mettait 12 s, la recherche 16 s, les bons plans 17 s.
Rien n'était en panne — le site refaisait simplement, pour chaque visiteur, un
calcul dont il connaissait déjà la réponse.

Volontairement minuscule : un dictionnaire et un verrou. Pas de Redis, pas de
dépendance, rien à faire tourner sur le VPS. Ce qui coûte cher ici, ce n'est pas
d'aller chercher une valeur, c'est de la recalculer.

`SITE_CACHE_TTL` (secondes, défaut 600) règle la durée ; `0` désactive
entièrement le cache — c'est ce qu'on veut en développement, quand on relance le
pipeline et qu'on veut voir le résultat tout de suite.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from typing import Any

_verrou = threading.Lock()
_boite: dict[str, tuple[float, Any]] = {}


def duree() -> float:
    try:
        return float(os.environ.get("SITE_CACHE_TTL", "600"))
    except ValueError:
        return 600.0


def au_chaud(cle: str, fabrique: Callable[[], Any], ttl: float | None = None) -> Any:
    """Renvoie la valeur en cache, ou la calcule et la garde.

    `fabrique` est appelée HORS du verrou. Deux requêtes simultanées sur une
    entrée froide peuvent donc la calculer toutes les deux — on l'accepte :
    tenir le verrou pendant une requête de quinze secondes mettrait toutes les
    autres pages en file derrière elle, ce qui est exactement le mal qu'on
    soigne. Le doublon coûte un calcul, le verrou coûterait le site.
    """
    vie = duree() if ttl is None else ttl
    if vie <= 0:
        return fabrique()

    maintenant = time.monotonic()
    with _verrou:
        entree = _boite.get(cle)
        if entree is not None and maintenant - entree[0] < vie:
            return entree[1]

    valeur = fabrique()
    with _verrou:
        _boite[cle] = (time.monotonic(), valeur)
        _elaguer()
    return valeur


# Les pages de résultats se mettent en cache par COMBINAISON de filtres, et une
# combinaison est une chaîne libre : sans plafond, un robot qui essaie mille
# fourchettes de prix ferait grossir ce dictionnaire sans fin. On garde les
# entrées les plus récemment ÉCRITES — pas les plus lues : ce qui vaut ici,
# c'est la fraîcheur, et une entrée relue ne rajeunit pas.
_PLAFOND = 400


def _elaguer() -> None:
    """Ramène la boîte sous le plafond. À appeler en tenant le verrou."""
    if len(_boite) <= _PLAFOND:
        return
    trop = len(_boite) - _PLAFOND
    for cle, _ in sorted(_boite.items(), key=lambda kv: kv[1][0])[:trop]:
        _boite.pop(cle, None)


def vider() -> int:
    """Oublie tout. À appeler après un passage du pipeline, sinon le site
    continue d'afficher les comptes d'avant pendant la durée du cache."""
    with _verrou:
        n = len(_boite)
        _boite.clear()
    return n
