"""Le filtre Taille ne porte que sur l'équipement du motard (16/10/2026).

Vu sur /m/swmotech?taille=S : 78 pièces (valises, repose-pieds) proposées en
taille S, lue dans des références de pièces. Un échappement n'a pas de taille.
"""

from __future__ import annotations

from mcsite import queries


def test_les_rayons_a_tailles_sont_ceux_de_l_equipement():
    r = set(queries._RAYONS_A_TAILLES)
    assert {"jacket", "gloves", "pants", "boots", "helmet.integral",
            "protection.pilote"} <= r
    for piece in ("exhaust", "luggage", "brakes", "engine", "transmission",
                  "bodywork", "unknown", "maintenance", "electronics",
                  "protection.moto"):
        assert piece not in r


def test_filtre_et_pastilles_portent_la_meme_restriction():
    import inspect
    assert queries._IN_RAYONS_A_TAILLES in queries._OU
    assert "_IN_RAYONS_A_TAILLES" in inspect.getsource(queries.facets)


def test_les_tailles_se_rangent_du_plus_petit_au_plus_grand():
    """Lettres de XS à 5XL, puis les nombres, puis le reste (16/10/2026)."""
    from mcsite import labels
    vu = ["XL", "S", "13", "EU45", "2XL", "5", "M", "XS", "10", "4-5ANS",
          "L", "9", "3XL", "XXL", "6"]
    assert sorted(vu, key=labels.ordre_taille) == [
        "XS", "S", "M", "L", "XL", "2XL", "XXL", "3XL",
        "5", "6", "9", "10", "13", "4-5ANS", "EU45"]


def test_une_variante_sans_offre_est_elaguee_chaque_nuit():
    """Une règle de taille corrigée ne laisse plus d'ancienne pastille."""
    from mcpipe import match
    assert "NOT EXISTS" in match._ELAGUER_VARIANTES
    assert "offer_variant_link" in match._ELAGUER_VARIANTES


def test_les_pastilles_de_lettres_n_acceptent_que_de_vraies_tailles():
    """« 5S », « 6M », « 6XS » passaient le motif [2-6]?X{0,3}[SML] (16/10/2026)."""
    import re
    motif = re.compile(r"^([2-4]XS|[2-6]XL|X{1,3}[SL]|[SML])$")
    for ok in ("S", "M", "L", "XS", "XL", "XXL", "XXXL", "2XS", "2XL", "3XL", "5XL", "6XL", "3XS", "4XS"):
        assert motif.match(ok), ok
    for faux in ("5S", "6M", "6XS", "4M", "XM", "X", "SS", "XXXXL"):
        assert not motif.match(faux), faux


def test_toutes_les_pastilles_de_taille_sont_proposees():
    """Plus de plafond à 24 : « Tous les produits » perdait 5XL, 2XS, EU50."""
    import inspect
    src = inspect.getsource(queries.facets)
    assert "LIMIT 24" not in src


def test_une_pointure_eu_declaree_est_empruntee_au_meme_code_barres():
    """Bering/Segura T0..T6 dans le titre, 36..46 dans le flux FC-Moto."""
    from mcpipe import enrich
    assert "^EU[0-9]{2}$" in enrich._BORROW_SIZE


def test_une_taille_de_reference_cede_devant_une_taille_declaree():
    from mcpipe import enrich
    assert "s.size_source = 'mpn' AND a.origine = 'feed'" in enrich._BORROW_SIZE


def test_une_taille_declaree_par_les_flux_l_emporte_sur_une_taille_lue():
    from mcpipe import match
    assert "ovr.donor_source = 'feed'" in match._DECLARED_SIZE
    assert match._DECLARED_SIZE.index("ovr.size_code END") < match._DECLARED_SIZE.index("nullif")


def test_filtre_et_pastilles_ne_gardent_que_les_tailles_achetables():
    """17/10/2026 : /c/gloves?taille=S montrait des gants dont le S n'est plus en
    stock nulle part -- le filtre voulait seulement qu'une variante S existe."""
    import inspect
    assert queries._VARIANTE_ACHETABLE in queries._OU
    assert "_VARIANTE_ACHETABLE" in inspect.getsource(queries.facets)
    for condition in ("o.is_live", "o.in_stock IS NOT FALSE", "o.price > 0", "mm.affiche"):
        assert condition in queries._VARIANTE_ACHETABLE, condition


def test_chaque_gant_liste_en_s_a_un_s_en_stock():
    """Sur les donnees reelles : aucune fiche listee en taille S sans offre S achetable."""
    import os

    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        _verifier_gants_en_s(conn)


def _verifier_gants_en_s(conn):
    cats = queries.categories(conn)
    gants = queries.find_category(cats, "gloves")
    f = queries.Filtres(categories=gants["ids"], taille=["S"], marchands=2, tri="prix")
    fiches, _n = queries.listing_filtre(conn, f, 60, 0)
    assert fiches, "aucun gant en S : le test ne prouve rien"
    slugs = [x["slug"] for x in fiches]
    sans = conn.execute(f"""
        SELECT p.slug FROM product p WHERE p.slug = ANY(%s) AND NOT EXISTS (
            SELECT 1 FROM variant v WHERE v.product_id = p.id
              AND {queries._taille_norm('v.size_code')} = 'S' AND {queries._VARIANTE_ACHETABLE})
    """, (slugs,)).fetchall()
    assert not sans, f"{len(sans)} fiche(s) sans S achetable : {sans[:3]}"
