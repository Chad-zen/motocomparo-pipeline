"""Le tri des pages de résultats.

Deux défauts que seule une lecture du code révèle : un tri qui existe dans la
requête mais qu'aucun lien ne permet d'atteindre, et un tri sans départage, qui
rend une pagination incohérente sans jamais lever d'erreur.
"""

from __future__ import annotations

import re

SOURCE = "src/mcsite/queries.py"
GABARIT = "src/mcsite/templates/listing.html"


def _bloc_ordres() -> str:
    s = open(SOURCE, encoding="utf-8").read()
    debut = s.index("    ordres = {")
    return s[debut:s.index("    ordre = ordres.get", debut)]


def _cles_du_code() -> set[str]:
    return set(re.findall(r'^\s*"([a-z_]+)":\s*"', _bloc_ordres(), re.M))


def _cles_du_gabarit() -> set[str]:
    s = open(GABARIT, encoding="utf-8").read()
    bloc = s[s.index("{% set libelles = {"):]
    return set(re.findall(r"'([a-z_]+)':\s*'", bloc[:bloc.index("} %}")]))


def test_le_tri_par_nouveautes_existe():
    assert "nouveautes" in _cles_du_code()
    assert "nouveautes" in _cles_du_gabarit()


def test_le_tri_lit_la_date_d_arrivee_et_non_created_at():
    """`product.created_at` vaut le jour de reconstruction de la table pour les
    313 435 fiches. Un tri branché dessus rendrait un ordre arbitraire avec
    l'air d'un tri juste. La date lue est `vu_le` : la première offre vue."""
    # Les commentaires sont retirés d'abord : celui du code CITE `created_at`
    # comme contre-exemple, et le test se serait accroché à son explication.
    # C'est la deuxième fois aujourd'hui qu'un test lit un commentaire au lieu
    # du code — la leçon est écrite ici pour qu'elle reste.
    bloc = re.sub(r"#.*", "", _bloc_ordres())
    assert "s.vu_le" in bloc
    assert "created_at" not in bloc


def test_chaque_tri_du_code_est_atteignable():
    """Un tri que le sélecteur ne propose pas n'existe pour personne ; un
    libellé sans tri derrière retombe en silence sur « Pertinence », et le
    visiteur croit avoir trié."""
    assert _cles_du_code() == _cles_du_gabarit()


def test_chaque_tri_est_departage():
    """Sans clé finale, deux fiches à égalité sortent dans un ordre libre que
    PostgreSQL n'a aucune raison de tenir d'une requête à l'autre. Avec
    LIMIT/OFFSET, c'est une fiche vue deux fois page 3 et jamais page 4 — et
    le tri par nouveautés met 310 770 fiches à égalité."""
    s = open(SOURCE, encoding="utf-8").read()
    ligne = next(l for l in s.splitlines() if "ordres.get(f.tri" in l)
    assert 'p.slug' in ligne, ligne
