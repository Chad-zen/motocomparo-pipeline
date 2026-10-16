"""Fiches sans caractéristiques, et saisie à la main (16/10/2026)."""

from __future__ import annotations

from mcpipe import couverture
from mcsite import admin, queries


def test_les_champs_saisissables_suivent_le_rayon():
    assert set(admin.choix_pour(2)) == {"matiere", "homologation"}          # casque intégral
    assert set(admin.choix_pour(8)) == {"saison", "matiere", "homologation"}  # gants
    assert set(admin.choix_pour(9)) == {"matiere", "homologation"}          # bottes : pas de saison
    assert admin.choix_pour(18) == {}                                       # carrosserie


def test_chaque_valeur_saisie_est_ecrite_sous_le_nom_que_lit_le_filtre():
    """Si le nom stocké n'est pas celui du filtre, la saisie ne s'affiche jamais."""
    sql = queries._CARAC_SQL["matiere"]
    for categorie, nom in ((2, "calotte"), (6, "matiere_coque"), (8, "matiere"),
                           (7, "matiere"), (9, "matiere")):
        assert admin.choix_pour(categorie)["matiere"]["nom"] == nom
        assert f"'{nom}'" in sql
    assert admin.choix_pour(6)["homologation"]["nom"] == "classe_protection"
    assert admin.choix_pour(8)["saison"]["nom"] == "saison"


def test_la_source_manuelle_passe_avant_toutes_les_autres():
    p = queries._SOURCE_PRIORITE
    assert p["manuel"] == min(p.values())


def test_le_calcul_de_couverture_ne_compte_que_ce_qui_a_un_sens():
    assert 8 in couverture.APPLICABLE["saison"] and 1 not in couverture.APPLICABLE["saison"]
    assert 9 not in couverture.APPLICABLE["saison"]
    assert set(couverture.APPLICABLE["matiere"]) >= {1, 6, 7, 8, 9}


def test_les_valeurs_proposees_sont_celles_que_les_filtres_savent_nommer():
    ok = set(queries._LIBELLES_FILTRE["saison"]) | {"ete"}
    assert {v for v, _ in admin.SAISONS} <= ok | {"mi-saison", "toutes-saisons"}


# --- corrections de fiche à la main : masquer, rayon (16/10/2026) --------------

def test_une_fiche_masquee_n_existe_plus_pour_le_visiteur():
    """`merged` sans fiche d'arrivée : 404 ; avec une fiche d'arrivée : 301."""
    import inspect

    from mcsite import app
    src = inspect.getsource(app.product)
    assert 'p["status"] == "merged"' in src
    assert "raise HTTPException(404" in src and "status_code=301" in src


def test_masquer_garde_l_ancien_statut_pour_reafficher():
    import inspect

    src = inspect.getsource(admin.masquer) + inspect.getsource(admin.reafficher)
    assert "ancien_statut" in src and "status = 'merged', merged_into = NULL" in src


def test_le_calcul_de_nuit_ne_reveille_pas_une_fiche_masquee():
    """freshness ne touche que draft / published / stale."""
    import inspect

    from mcpipe import freshness
    src = inspect.getsource(freshness)
    assert "p.status IN ('draft', 'published')" in src and "p.status = 'stale'" in src
