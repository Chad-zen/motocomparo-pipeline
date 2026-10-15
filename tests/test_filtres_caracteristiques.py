"""Matière, Homologation, Saison — les trois filtres du 15/10/2026.

Même piège que `test_site_tri.py` : un filtre qui existe dans `Filtres` mais
qu'un des trois gabarits de lien oublie perd son critère au premier clic
ailleurs dans le panneau — en silence, pas d'erreur, juste un filtre qui
« saute ». Ces vérifications lisent le code source plutôt que de cliquer,
pour les mêmes raisons que `test_site_tri.py` : elles tournent sans base.
"""

from __future__ import annotations

import os
import re

import pytest

from mcsite import queries

GABARIT = "src/mcsite/templates/listing.html"
APP = "src/mcsite/app.py"


def _macro(nom: str) -> str:
    s = open(GABARIT, encoding="utf-8").read()
    debut = s.index(f"{{% macro {nom}(")
    fin = s.index("{%- endmacro %}", debut)
    return s[debut:fin]


@pytest.mark.parametrize("macro", ["lien", "lien_rayon", "lien_marque"])
@pytest.mark.parametrize("param", list(queries.FILTRES_CARACTERISTIQUES))
def test_chaque_macro_de_lien_porte_les_trois_filtres(macro, param):
    """Les trois gabarits de lien doivent reporter `matiere`, `homologation`
    et `saison` — exactement le piège qui a fait sauter `couleur` puis `q`
    avant cette date (voir les commits de ce fichier)."""
    assert f"'{param}'" in _macro(macro), (
        f"{macro}() ne reporte pas le filtre « {param} »")


def test_les_quatre_routes_acceptent_les_trois_filtres():
    """`produits`, `/c/{code}`, `/m/{marque}` et `/recherche` construisent
    chacune un `Filtres(...)` : les trois nouveaux paramètres doivent être lus
    par les quatre, ou un clic dans le panneau perd le critère selon la page
    d'où l'on part."""
    s = open(APP, encoding="utf-8").read()
    appels = [m.end() for m in re.finditer(r"queries\.Filtres\(", s)]
    assert len(appels) == 4, f"{len(appels)} appels à Filtres(), 4 attendus"
    for debut in appels:
        # Parenthèses comptées une à une : l'appel contient lui-même des
        # appels imbriqués (`code_filtre(...)`), et le premier « ) » fermerait
        # sur l'un d'eux plutôt que sur `Filtres(...)`.
        profondeur, i = 1, debut
        while profondeur:
            i += 1
            profondeur += {"(": 1, ")": -1}.get(s[i], 0)
        bloc = s[debut:i]
        for param in queries.FILTRES_CARACTERISTIQUES:
            assert param in bloc, f"Filtres() à la position {debut} oublie « {param} »"


def test_le_robots_noindex_couvre_les_trois_filtres():
    """Une page filtrée par matière, homologation ou saison doit rester hors
    index, comme les autres filtres — sinon le catalogue entier s'indexe sous
    chaque combinaison (voir le commentaire du bloc `robots` dans le gabarit)."""
    s = open(GABARIT, encoding="utf-8").read()
    bloc = s[s.index("{% block robots %}"):s.index("{% endblock %}", s.index("{% block robots %}"))]
    for param in queries.FILTRES_CARACTERISTIQUES:
        assert f"f.{param}" in bloc, f"`robots` ne teste pas f.{param}"


def test_code_filtre_rejette_ce_qui_ne_vient_pas_du_site():
    """Les codes sont écrits par `_CARAC_SQL` : minuscules, chiffres, point et
    tiret. Une URL fabriquée à la main avec autre chose (espace, guillemet,
    balise) ne doit pas être recopiée telle quelle dans chaque lien du panneau."""
    assert queries.code_filtre("cuir") == "cuir"
    assert queries.code_filtre("ece-22.06") == "ece-22.06"
    assert queries.code_filtre("ECE-22.06") == "ece-22.06"
    assert queries.code_filtre("") is None
    assert queries.code_filtre(None) is None
    assert queries.code_filtre("<script>") is None
    assert queries.code_filtre("a b") is None
    assert queries.code_filtre("x" * 41) is None


def test_libelle_filtre_a_toujours_une_reponse():
    """Un code absent de `_LIBELLES_FILTRE` (un extracteur qui apprend une
    valeur nouvelle) doit quand même s'afficher, lisible, plutôt que de
    rester invisible en attendant qu'on pense à le nommer."""
    assert queries.libelle_filtre("matiere", "cuir") == "Cuir"
    assert queries.libelle_filtre("matiere", "neoprene") == "Neoprene"
    assert queries.libelle_filtre("saison", "toutes-saisons") == "Toutes saisons"


def test_actifs_affiche_les_trois_filtres():
    f = queries.Filtres(matiere="cuir", homologation="ece-22.06", saison="ete")
    cles = {a["cle"] for a in f.actifs()}
    assert {"matiere", "homologation", "saison"} <= cles


@pytest.mark.skipif(not os.environ.get("DATABASE_URL"),
                    reason="les facettes se calculent en base")
class TestFacettesEnBase:
    """Vérifications qui ouvrent une vraie connexion — la base locale peut
    être plus petite que la production, mais la FORME du résultat ne dépend
    pas du volume."""

    @pytest.fixture(scope="class")
    @staticmethod
    def conn():
        import psycopg
        with psycopg.connect(os.environ["DATABASE_URL"]) as c:
            yield c

    def test_facets_rend_les_trois_cles(self, conn):
        fa = queries.facets(conn, queries.Filtres(categories=[6]))  # blousons
        for param in queries.FILTRES_CARACTERISTIQUES:
            assert param in fa

    def test_une_valeur_choisie_ne_disparait_jamais_de_sa_propre_liste(self, conn):
        """Un filtre compté « sans lui-même » : choisir « cuir » ne doit pas
        faire disparaître « Cuir » de la liste des matières, sans quoi on ne
        peut plus revenir en arrière vers une autre matière sans tout effacer."""
        avec = queries.facets(conn, queries.Filtres(categories=[6], matiere="textile"))
        valeurs = {x["valeur"] for x in avec["matiere"]}
        assert "textile" in valeurs

    def test_filtrer_par_matiere_restreint_la_liste(self, conn):
        _, total_tout = queries.listing_filtre(
            conn, queries.Filtres(categories=[6]), 1, 0)
        _, total_cuir = queries.listing_filtre(
            conn, queries.Filtres(categories=[6], matiere="cuir"), 1, 0)
        assert 0 < total_cuir < total_tout

    def test_un_rayon_sans_extracteur_ne_montre_aucun_filtre(self, conn):
        """Les échappements (catégorie 12) : aucun extracteur de
        `mcpipe.caracteristiques` ne les lit. Les trois listes doivent être
        vides plutôt que de proposer un filtre qui ne couvre jamais rien."""
        fa = queries.facets(conn, queries.Filtres(categories=[12]))
        for param in queries.FILTRES_CARACTERISTIQUES:
            assert fa[param] == []
