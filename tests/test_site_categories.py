"""La bande de raccourcis posée sous l'affiche.

Le défaut qu'on ne verrait pas : un rayon apparaît en base — le pipeline en a
classé assez pour qu'il dépasse les autres — et son picto n'existe pas. La case
reste cliquable, elle affiche juste un losange. Personne ne le remarque, parce
que personne ne relit une page qui « marche ».
"""

from __future__ import annotations

import os
import re

import psycopg
import pytest

from mcsite import queries

GABARIT = "src/mcsite/templates/_categories.html"


def _codes_dessines() -> set[str]:
    """Les codes pour lesquels un trait est dessiné, lus dans le gabarit."""
    texte = open(GABARIT, encoding="utf-8").read()
    bloc = texte[texte.index("{% set traits"):texte.index("} %}")]
    return set(re.findall(r"^\s*'([a-z_]+)':", bloc, re.M))


def test_chaque_picto_a_un_trace():
    codes = _codes_dessines()
    assert len(codes) >= 12, codes


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"),
                    reason="la liste des rayons se lit en base")
def test_les_rayons_montres_ont_tous_leur_picto():
    """La bande n'affiche que les douze premiers rayons, mais le classement
    change : un rayon qui grossit y entre sans prévenir. On exige donc le picto
    pour les vingt premiers, pas pour les douze affichés aujourd'hui."""
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        rayons = [r["code"] for r in queries.categories(c)][:20]
    manquants = [r for r in rayons if r not in _codes_dessines()]
    assert not manquants, f"rayons sans picto : {manquants}"


def test_les_libelles_viennent_de_la_base():
    """La maquette proposait « Helmes » et « Mancliqes ». Les noms affichés sont
    ceux de la base, jamais réécrits dans le gabarit."""
    texte = open(GABARIT, encoding="utf-8").read()
    assert "r.label_fr" in texte
    # Les commentaires Jinja sont retirés d'abord : celui du gabarit CITE ces
    # noms comme contre-exemples, et le test se serait accroché à sa propre
    # explication.
    rendu = re.sub(r"\{#.*?#\}", "", texte, flags=re.S)
    for invente in ("Helmes", "Mancliqes", "Jackets", "Aventure"):
        assert invente not in rendu


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"),
                    reason="l'ordre des rayons se lit en base")
def test_casque_blouson_gants_ouvrent_la_marche():
    """Décision éditoriale de la propriétaire, 18/09/2026.

    Classés au nombre de fiches, les trois premiers rayons étaient Bagagerie,
    Blousons et Casques : le catalogue le plus gros passait devant, pas le
    besoin le plus courant. Personne n'arrive sur un comparateur d'équipement
    moto en cherchant d'abord un top-case.

    Ce test tient l'ordre parce qu'il est INVISIBLE dans le code appelant : la
    bande de raccourcis, la mosaïque, le menu et les étagères lisent tous la
    même liste, et un tri remis au nombre de fiches ne casserait rien — il
    changerait seulement la première chose que voit un visiteur.
    """
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        codes = [r["code"] for r in queries.categories(c)]
    assert codes[:3] == ["helmet", "jacket", "gloves"], codes[:6]


def test_le_reste_suit_le_nombre_de_fiches():
    """Au-delà des trois premiers, aucune raison éditoriale ne tranche : le
    nombre de fiches reste le bon critère."""
    import os as _os
    if not _os.environ.get("DATABASE_URL"):
        pytest.skip("base absente")
    import psycopg
    with psycopg.connect(_os.environ["DATABASE_URL"]) as c:
        suite = [r["n"] for r in queries.categories(c)[3:]]
    assert suite == sorted(suite, reverse=True), suite[:6]
