"""La clé qui relie une ligne de flux à une fiche — et le silence de sa panne.

CE QUE CE FICHIER GARDE. Les caractéristiques se lisent dans les descriptions,
qui n'existent que dans les fichiers de flux. Pour savoir de quelle fiche parle
une ligne de flux, il faut recalculer la référence marchande EXACTEMENT comme
`normalize` l'a écrite en base. Une deuxième façon de la calculer, écrite à
côté, finit toujours par diverger.

ELLE A DIVERGÉ. Le module cherchait la référence dans la colonne `id`, en repli
sur `internal reference`. C'était juste pour quatre marchands sur six :

  * FC-Moto range la sienne dans `mpn` (repli `gtin`, puis `id`) — sa colonne
    `id` est un hachage dont la stabilité n'est pas établie. Sur les blousons :
    27 330 offres liées, UNE description retrouvée.
  * Maxxess et Moto-Axxe changent d'identifiant à chaque rafraîchissement, donc
    `normalize` fabrique la sienne à partir de l'URL cible (`u:<md5>`). Aucune
    valeur de `id` ne pouvait y correspondre : zéro description, les deux.

3 433 casques et 4 157 blousons n'avaient pas de description sans que rien ne le
dise. C'est le genre de panne qui ne lève aucune erreur et ne laisse aucune
trace : les fiches retrouvées étaient bien renseignées, et les autres avaient
l'air de fiches sans texte.

D'OÙ UN TEST SUR LE TAUX, PAS SUR UN CAS. Un test qui vérifierait une fiche
précise serait passé au vert tout du long — il y en avait des milliers de
justes. Ce qu'il fallait mesurer, c'est qu'AUCUN MARCHAND ne tombe à zéro.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import pytest

from mcpipe.caracteristiques import _dossier_flux, _lignes, _references
from mcpipe.db import connect
from mcpipe.feeds import FEEDS

csv.field_size_limit(10 ** 7)

# Les rayons qu'on sait lire aujourd'hui, réunis : le test doit rester vrai
# quand un rayon s'ajoute, pas être réécrit à chaque fois.
_CATEGORIES_LUES = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)

# Un marchand peut légitimement être peu présent dans un rayon, ou décrire
# pauvrement. Il ne peut pas être à zéro pour cent alors qu'il a des milliers
# d'offres liées : ça, c'est une clé qui ne tombe pas en face.
_PLANCHER = 0.20
_ASSEZ_D_OFFRES = 200

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL") or not Path(_dossier_flux()).is_dir(),
    reason="demande la base et les fichiers de flux du jour")


@pytest.fixture(scope="module")
def jointure() -> dict[str, tuple[int, int]]:
    """marchand -> (offres liées, offres dont la ligne de flux a été retrouvée)."""
    conn = connect()
    try:
        refs = _references(conn, _CATEGORIES_LUES)
    finally:
        conn.close()

    lies: dict[str, int] = {}
    for (code, _sku) in refs:
        lies[code] = lies.get(code, 0) + 1

    trouves: dict[str, int] = {}
    for code, feed in FEEDS.items():
        chemin = _dossier_flux() / f"{code}.csv"
        if not chemin.exists():
            continue
        vus = {sku for sku, _t, _d in _lignes(feed, chemin)
               if (code, sku) in refs}
        trouves[code] = len(vus)
    return {c: (lies.get(c, 0), trouves.get(c, 0)) for c in FEEDS}


def test_aucun_marchand_ne_perd_ses_descriptions(jointure):
    """Le test qui manquait. Avec l'ancienne clé : FC-Moto 0,004 %, Maxxess 0 %,
    Moto-Axxe 0 % — et 277 vérifications au vert."""
    muets = {c: (n_lies, n_trouves)
             for c, (n_lies, n_trouves) in jointure.items()
             if n_lies >= _ASSEZ_D_OFFRES and n_trouves / n_lies < _PLANCHER}
    assert not muets, (
        "des marchands n'ont presque aucune ligne de flux retrouvée — la "
        f"référence ne tombe plus en face de celle de `normalize` : {muets}")


def test_la_reference_est_celle_du_pipeline(jointure):
    """La garde de fond : si un jour quelqu'un réécrit la clé ici plutôt que de
    réutiliser `_merchant_sku`, les deux marchands à identifiant synthétique
    repartiront à zéro sans bruit. Ils sont petits — 500 fiches chacun — donc
    invisibles dans un total ; ils sont nommés ici pour cette raison."""
    for code in ("maxxess", "motoaxxe"):
        n_lies, n_trouves = jointure[code]
        if n_lies < _ASSEZ_D_OFFRES:
            pytest.skip(f"{code} n'a pas assez d'offres liées dans cette base")
        assert n_trouves > 0, (
            f"{code} : {n_lies} offres liées et aucune ligne de flux retrouvée. "
            "Sa référence est fabriquée à partir de l'URL cible, elle ne peut "
            "pas se lire dans une colonne du flux.")
