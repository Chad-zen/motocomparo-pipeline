"""Une offre neuve dont le code-barres est deja porte par UNE fiche rejoint cette fiche (20/10/2026).

Les tests tournent sur les VRAIES tables (raw_offer, offer_signature, product, category) dans une
transaction annulee : masquer ces tables par des tables TEMP ferait perdre les index et le plan reels.
Seules `_gtin_unit` et `_hash_avant_decoupes` sont creees (ce sont deja des tables temporaires).
"""

from __future__ import annotations

import itertools

import pytest

from mcpipe import match as m
from mcpipe.db import connect

_ids = itertools.count(9_000_000_000)


@pytest.fixture
def cur():
    try:
        conn = connect()
    except Exception as exc:  # pas de base locale
        pytest.skip(f"base indisponible : {exc}")
    cur = conn.cursor()
    cur.execute("""CREATE TEMP TABLE _gtin_unit (
        gtin text, brand_code text, primary_colour text, model_year smallint, genre_age text,
        is_pack boolean, model_core_ref text, model_tokens text[], category_id smallint,
        jetons_vus text[], conflict boolean, identity_hash text)""")
    cur.execute("CREATE TEMP TABLE _hash_avant_decoupes (gtin text, identity_hash text)")
    yield cur
    conn.rollback()
    conn.close()


def _fiche(cur, hash_, *, brand="shark", cat=2, merged_into=None, status="draft"):
    cur.execute("""INSERT INTO product (brand_code, category_id, model_display, identity_hash, slug, status, merged_into)
                   VALUES (%s, %s, 'Modele', %s, %s, %s, %s) RETURNING id""",
                (brand, cat, hash_, f"t-{hash_}", status, merged_into))
    return cur.fetchone()[0]


def _offre(cur, gtin, *, marchand=1, statut="unresolved", produit=None, methode=None, prix=100.0,
           brand="shark", cat=2, couleur="BK", genre="U-A", annee=None, pack=False, vivante=True):
    sku = f"sku{next(_ids)}"
    cur.execute("""INSERT INTO raw_offer (merchant_id, merchant_sku, raw_title, deeplink, gtin, price, is_live,
                       linked_status, product_id, link_method)
                   VALUES (%s, %s, 'titre', 'http://x', %s, %s, %s, %s, %s, %s) RETURNING id""",
                (marchand, sku, gtin, prix, vivante, statut, produit, methode))
    oid = cur.fetchone()[0]
    cur.execute("""INSERT INTO offer_signature (raw_offer_id, brand_code, category_id, primary_colour, genre_age,
                       model_year, is_pack, norm_txt) VALUES (%s, %s, %s, %s, %s, %s, %s, 'x')""",
                (oid, brand, cat, couleur, genre, annee, pack))
    return oid


def _unite(cur, gtin, hash_propre, *, conflict=False, avant=None):
    cur.execute("INSERT INTO _gtin_unit (gtin, conflict, identity_hash) VALUES (%s, %s, %s)", (gtin, conflict, hash_propre))
    cur.execute("INSERT INTO _hash_avant_decoupes VALUES (%s, %s)", (gtin, avant or hash_propre))


def _hash_unite(cur, gtin):
    cur.execute("SELECT identity_hash FROM _gtin_unit WHERE gtin = %s", (gtin,))
    return cur.fetchone()[0]


def _cas_simple(cur, gtin="T000000000001", **offre_neuve):
    p = _fiche(cur, "H_CIBLE")
    # l'offre deja rattachee a un genre et une annee connus : sinon « inconnu » ne contredit rien
    _offre(cur, gtin, marchand=2, statut="linked", produit=p, methode="gtin", genre="H-A", annee=2019)
    _offre(cur, gtin, marchand=1, **offre_neuve)
    _unite(cur, gtin, "H_PROPRE")
    return p


def test_l_unite_rejoint_la_fiche_du_code_barres(cur):
    _cas_simple(cur)
    offres, refus, ecartees = m.rattacher_a_la_fiche_existante(cur)
    assert (offres, refus) == (1, 0)
    assert _hash_unite(cur, "T000000000001") == "H_CIBLE"
    cur.execute("SELECT count(*) FROM rattachement_existant_log WHERE gtin = 'T000000000001'")
    assert cur.fetchone()[0] == 1                    # journalise


def test_second_passage_ne_fait_rien(cur):
    _cas_simple(cur)
    m.rattacher_a_la_fiche_existante(cur)
    cur.execute("UPDATE raw_offer SET linked_status = 'linked', product_id = (SELECT id FROM product WHERE identity_hash='H_CIBLE'),"
                " link_method = 'gtin' WHERE gtin = 'T000000000001'")
    assert m.rattacher_a_la_fiche_existante(cur)[0] == 0


@pytest.mark.parametrize("champ, valeur", [
    ("brand", "arai"), ("couleur", "RD"), ("genre", "F-A"), ("genre", "H-E"), ("annee", 2020), ("pack", True),
    ("cat", 6), ("prix", 600.0),
])
def test_un_desaccord_empeche_le_rattachement(cur, champ, valeur):
    _cas_simple(cur, **{champ: valeur})
    assert m.rattacher_a_la_fiche_existante(cur)[0] == 0
    assert _hash_unite(cur, "T000000000001") == "H_PROPRE"


def test_parent_et_enfant_de_rayon_sont_compatibles(cur):
    _cas_simple(cur, cat=1)          # 1 = Casques, parent de 2 (integraux) porte par l'offre deja rattachee
    assert m.rattacher_a_la_fiche_existante(cur)[0] == 1


def test_mat_et_brillant_restent_deux_produits(cur):
    p = _fiche(cur, "H_CIBLE")
    _offre(cur, "T000000000001", marchand=2, statut="linked", produit=p, methode="gtin", couleur="BK|MAT")
    _offre(cur, "T000000000001", marchand=1, couleur="BK|GLO")
    _unite(cur, "T000000000001", "H_PROPRE")
    assert m.rattacher_a_la_fiche_existante(cur)[0] == 0


def test_la_couleur_incluse_est_compatible(cur):
    p = _fiche(cur, "H_CIBLE")
    _offre(cur, "T000000000001", marchand=2, statut="linked", produit=p, methode="gtin", couleur="BK-RD")
    _offre(cur, "T000000000001", marchand=1, couleur="BK")
    _unite(cur, "T000000000001", "H_PROPRE")
    assert m.rattacher_a_la_fiche_existante(cur)[0] == 1


def test_un_code_barres_deja_eclate_sur_deux_fiches_n_est_pas_touche(cur):
    p1, p2 = _fiche(cur, "H1"), _fiche(cur, "H2")
    _offre(cur, "T000000000001", marchand=2, statut="linked", produit=p1, methode="gtin")
    _offre(cur, "T000000000001", marchand=3, statut="linked", produit=p2, methode="gtin")
    _offre(cur, "T000000000001", marchand=1)
    _unite(cur, "T000000000001", "H_PROPRE")
    assert m.rattacher_a_la_fiche_existante(cur)[0] == 0


def test_une_fiche_fusionnee_envoie_vers_la_survivante(cur):
    survivante = _fiche(cur, "H_SURVIVANTE")
    absorbee = _fiche(cur, "H_ABSORBEE", status="merged", merged_into=survivante)
    _offre(cur, "T000000000001", marchand=2, statut="linked", produit=absorbee, methode="gtin")
    _offre(cur, "T000000000001", marchand=1)
    _unite(cur, "T000000000001", "H_PROPRE")
    assert m.rattacher_a_la_fiche_existante(cur)[0] == 1
    assert _hash_unite(cur, "T000000000001") == "H_SURVIVANTE"


def test_une_fiche_fourre_tout_n_accepte_plus_rien(cur):
    p = _fiche(cur, "H_CIBLE")
    for i in range(m.TAILLE_MAX_CIBLE + 1):
        _offre(cur, f"T9{i:011d}", marchand=2, statut="linked", produit=p, methode="gtin")
    _offre(cur, "T000000000001", marchand=1)
    _unite(cur, "T000000000001", "H_PROPRE")
    assert m.rattacher_a_la_fiche_existante(cur)[0] == 0


def test_une_unite_en_conflit_ou_separee_par_une_decoupe_ne_revient_pas(cur):
    _cas_simple(cur, gtin="T000000000001")
    cur.execute("UPDATE _gtin_unit SET conflict = true WHERE gtin = 'T000000000001'")
    assert m.rattacher_a_la_fiche_existante(cur)[0] == 0
    # une decoupe a change l'empreinte depuis l'instantane : l'unite n'est pas reprise
    p = _fiche(cur, "H_CIBLE2")
    _offre(cur, "T000000000002", marchand=2, statut="linked", produit=p, methode="gtin")
    _offre(cur, "T000000000002", marchand=1)
    _unite(cur, "T000000000002", "H_APRES_DECOUPE", avant="H_AVANT_DECOUPE")
    assert m.rattacher_a_la_fiche_existante(cur)[0] == 0
    assert _hash_unite(cur, "T000000000002") == "H_APRES_DECOUPE"


def test_une_coupure_posee_a_la_main_l_ecarte(cur):
    _cas_simple(cur)
    cur.execute("INSERT INTO match_override (scope, key_value, is_split) VALUES ('gtin', 'T000000000001', true)")
    assert m.rattacher_a_la_fiche_existante(cur)[0] == 0


def test_seules_les_offres_rattachees_par_code_barres_servent_de_cible(cur):
    p = _fiche(cur, "H_CIBLE")
    _offre(cur, "T000000000001", marchand=2, statut="linked", produit=p, methode="item_group")
    _offre(cur, "T000000000001", marchand=1)
    _unite(cur, "T000000000001", "H_PROPRE")
    assert m.rattacher_a_la_fiche_existante(cur)[0] == 0


def test_le_prix_d_un_marchand_masque_compte_aussi(cur):
    # Motoin est `affiche = false` : son prix ne doit pas disparaitre du garde-fou
    cur.execute("UPDATE merchant SET affiche = false WHERE id = 1")
    _cas_simple(cur, prix=900.0)
    assert m.rattacher_a_la_fiche_existante(cur)[0] == 0


def test_le_plafond_est_tout_ou_rien_et_ne_leve_pas(cur, monkeypatch):
    monkeypatch.setenv("MCPIPE_RATTACHER_MAX", "1")
    p = _fiche(cur, "H_CIBLE")
    for i in range(3):
        g = f"T00000000010{i}"
        _offre(cur, g, marchand=2, statut="linked", produit=p, methode="gtin")
        _offre(cur, g, marchand=1)
        _unite(cur, g, f"H_PROPRE{i}")
    offres, refus, _ = m.rattacher_a_la_fiche_existante(cur)
    assert (offres, refus) == (0, 3)
    assert all(_hash_unite(cur, f"T00000000010{i}") == f"H_PROPRE{i}" for i in range(3))
    cur.execute("SELECT count(*) FROM rattachement_existant_log WHERE gtin LIKE 'T00000000010%'")
    assert cur.fetchone()[0] == 0                    # rien n'est journalise quand rien n'est ecrit


def test_le_passage_est_apres_les_decoupes_et_avant_la_creation_des_fiches():
    import inspect
    src = inspect.getsource(m.run_match)
    assert src.index("_SPLIT_PRIX_HABILLEMENT") < src.index("rattacher_a_la_fiche_existante(cur)") \
        < src.index("_CREATE_PRODUCTS_FROM_GTIN")
    assert src.index("_HASH_AVANT_DECOUPES") < src.index("_SPLIT_PIECES")
