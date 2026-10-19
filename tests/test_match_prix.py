"""La separation par le prix (19/10/2026) : un produit a 44 € ne partage plus la fiche d'un produit a 4 €.

Cas reel : La Becanerie vend « Protection de leviers Voca Racing rouge » deux fois sous le meme titre, une mousse
(4,05 €, avec code-barres) et de l'aluminium CNC (44,01 €, sans code-barres, autre groupe). Meme identite, donc meme
fiche. Deux relectures independantes ont demande ces tests : le seuil exact (3x hors habillement, 5x habillement),
le defaut qui aurait laisse les offres separees sans fiche (`hash_base`), la fiche collante, le frere deja rattache,
le garde-fou du plafond.

Tout est fabrique dans une transaction jamais validee : rien n'est ecrit dans la base.
"""

import itertools

import pytest

from mcpipe import match as m
from mcpipe.db import connect

A, B = 995, 996            # deux marchands d'essai, tous deux affiches
_n = itertools.count(1)
HABILLEMENT, PIECE = 6, 14  # blousons ; freinage


@pytest.fixture
def conn():
    try:
        c = connect()
    except Exception as exc:
        pytest.skip(f"base indisponible : {exc}")
    try:
        c.execute("INSERT INTO merchant (id, code, platform, gtin_trust, reliability_rank, affiche) VALUES "
                  "(%s, 'essai_a', 'effinity', 'trusted', 1, true), (%s, 'essai_b', 'effinity', 'trusted', 1, true)",
                  (A, B))
        yield c
    finally:
        c.rollback()
        c.close()


def _fiche(c, hash_, cat=PIECE):
    k = next(_n)
    return c.execute("INSERT INTO product (brand_code, category_id, model_display, identity_hash, slug) "
                     "VALUES ('essai', %s, 'essai', %s, %s) RETURNING id", (cat, hash_, f"slug-prix-{k}")).fetchone()[0]


def _offre(c, marchand, prix, *, produit=None, groupe=None, methode=None, gtin=None, cat=PIECE, vivante=True):
    k = next(_n)
    statut = "linked" if produit else "unresolved"
    oid = c.execute(
        "INSERT INTO raw_offer (merchant_id, merchant_sku, raw_title, deeplink, gtin, raw_item_group, price, is_live, "
        "linked_status, product_id, link_method, link_confidence) VALUES (%s, %s, 'essai', 'https://x.test', %s, %s, "
        "%s, %s, %s, %s, %s, %s) RETURNING id",
        (marchand, f"prix{k}", gtin, groupe, prix, vivante, statut, produit, methode, 0.75 if methode else None)
    ).fetchone()[0]
    c.execute("INSERT INTO offer_signature (raw_offer_id, brand_code, primary_colour, genre_age, is_pack, category_id, "
              "norm_txt, model_core_ref) VALUES (%s, 'essai', 'RD', 'U-A', false, %s, 'essai', 'ref1')", (oid, cat))
    return oid


def _unites(c):
    c.execute("CREATE TEMP TABLE _ig_unit (merchant_id smallint, raw_item_group text, identity_hash text, "
              "hash_base text, category_id smallint, n bigint, prix numeric) ON COMMIT DROP")
    c.execute("CREATE TEMP TABLE _ig_ref (h text, t text, m bigint, g text, prix numeric) ON COMMIT DROP")


def _unite(c, h, marchand, groupe, prix, *, cat=PIECE, n=1):
    c.execute("INSERT INTO _ig_unit VALUES (%s, %s, %s, %s, %s, %s, %s)", (marchand, groupe, h, h, cat, n, prix))
    c.execute("INSERT INTO _ig_ref VALUES (%s, 'i', %s, %s, %s)", (h, marchand, groupe, prix))


def _ref_fiche(c, h, prix):
    c.execute("INSERT INTO _ig_ref VALUES (%s, 'p', 1, NULL, %s)", (h, prix))


def _hash(c, marchand, groupe):
    return c.execute("SELECT identity_hash FROM _ig_unit WHERE merchant_id = %s AND raw_item_group = %s",
                     (marchand, groupe)).fetchone()[0]


# --- le seuil -----------------------------------------------------------------------------------


@pytest.mark.parametrize("cat, prix, ref, separe", [
    (PIECE, 44.01, 4.05, True),         # le cas Voca : x10,9
    (PIECE, 12.00, 4.05, False),        # x2,96 : sous 3
    (PIECE, 12.20, 4.05, True),         # x3,01
    (PIECE, 1.00, 4.05, True),          # sens inverse : x4,05 moins cher
    (PIECE, 1.50, 4.05, False),         # x2,7 moins cher
    (HABILLEMENT, 19.90, 4.00, False),  # x4,97 : les soldes FC-Moto vont jusqu'a x3
    (HABILLEMENT, 20.00, 4.00, True),   # x5 pile
    (HABILLEMENT, 0.81, 4.00, False),   # x4,94 moins cher
    (HABILLEMENT, 0.80, 4.00, True),    # x5 moins cher
])
def test_le_seuil_de_separation(conn, cat, prix, ref, separe):
    _unites(conn)
    _unite(conn, "h1", A, "g1", prix, cat=cat)
    _ref_fiche(conn, "h1", ref)
    conn.execute(m._IG_SEPARER_PRIX)
    assert (_hash(conn, A, "g1") != "h1") is separe


def test_une_separation_donne_un_hash_deterministe(conn):
    # le lendemain, l'unite doit retrouver LA MEME fiche : le hash ne depend que de l'identite, du marchand, du groupe
    _unites(conn)
    _unite(conn, "h1", A, "g1", 44.0)
    _ref_fiche(conn, "h1", 4.0)
    conn.execute(m._IG_SEPARER_PRIX)
    attendu = conn.execute("SELECT md5('h1' || '|prix|' || %s || '|' || 'g1')", (A,)).fetchone()[0]
    assert _hash(conn, A, "g1") == attendu


# --- sans reference, ou deux unites qui s'opposent ----------------------------------------------------------------


def test_une_unite_seule_ou_sans_prix_n_est_jamais_separee(conn):
    _unites(conn)
    _unite(conn, "seul", A, "g1", 999.0)
    conn.execute("INSERT INTO _ig_unit VALUES (%s, 'g2', 'sansprix', 'sansprix', %s, 1, NULL)", (A, PIECE))
    _ref_fiche(conn, "sansprix", 4.0)
    conn.execute(m._IG_SEPARER_PRIX)
    assert _hash(conn, A, "g1") == "seul" and _hash(conn, A, "g2") == "sansprix"


def test_deux_unites_opposees_la_plus_fournie_garde_l_ancienne_fiche(conn):
    _unites(conn)
    _unite(conn, "h1", A, "mousse", 4.05, n=3)
    _unite(conn, "h1", A, "alu", 44.01, n=1)
    conn.execute(m._IG_SEPARER_PRIX)
    assert _hash(conn, A, "mousse") == "h1"          # garde l'adresse deja connue
    assert _hash(conn, A, "alu") != "h1"


def test_a_nombre_egal_la_moins_chere_reste(conn):
    _unites(conn)
    _unite(conn, "h1", A, "mousse", 4.05, n=2)
    _unite(conn, "h1", B, "alu", 44.01, n=2)
    conn.execute(m._IG_SEPARER_PRIX)
    assert _hash(conn, A, "mousse") == "h1" and _hash(conn, B, "alu") != "h1"


def test_avec_une_fiche_existante_toutes_les_unites_en_ecart_la_quittent(conn):
    _unites(conn)
    _unite(conn, "h1", A, "alu1", 44.0, n=5)
    _unite(conn, "h1", B, "alu2", 45.0, n=1)
    _ref_fiche(conn, "h1", 4.0)          # la fiche existante ne peut pas etre « gardee » par une unite item_group
    conn.execute(m._IG_SEPARER_PRIX)
    assert _hash(conn, A, "alu1") != "h1" and _hash(conn, B, "alu2") != "h1"


# --- le frere deja rattache, et la fiche collante -------------------------------------------------------------------


def test_un_frere_deja_rattache_a_la_fiche_d_origine_garde_le_groupe_entier(conn):
    # tient le passage de 4,9x a 5,1x d'une nuit a l'autre : la moitie du groupe est deja sur la fiche
    _unites(conn)
    fiche = _fiche(conn, "h1")
    _offre(conn, A, 4.0, produit=fiche, groupe="g1", methode="item_group")
    _unite(conn, "h1", A, "g1", 44.0)
    _ref_fiche(conn, "h1", 4.0)
    conn.execute(m._IG_SEPARER_PRIX)
    assert _hash(conn, A, "g1") == "h1"


def test_une_fiche_separee_la_veille_reste_separee(conn):
    _unites(conn)
    sep = conn.execute("SELECT md5('h1' || '|prix|' || %s || '|' || 'g1')", (A,)).fetchone()[0]
    _fiche(conn, sep)
    _unite(conn, "h1", A, "g1", 5.0)         # le prix est redevenu « normal »
    _ref_fiche(conn, "h1", 4.0)
    conn.execute(m._IG_SEPARER_PRIX)
    assert _hash(conn, A, "g1") == sep


# --- le defaut bloquant : retrouver l'unite par l'identite d'ORIGINE ----------------------------------------------------


def test_une_unite_separee_retrouve_ses_offres_et_sa_fiche(conn):
    _unites(conn)
    oid = _offre(conn, A, 44.0, groupe="g1")
    h = conn.execute(
        "SELECT md5(coalesce(s.brand_code, '') || '|' || s.category_id::text || '|' || coalesce(s.primary_colour, '') "
        "|| '|' || coalesce(s.model_year::text, '') || '|' || coalesce(s.genre_age, '') || '|' || s.is_pack::int::text "
        "|| '|' || coalesce(s.model_core_ref, '') || ':' || coalesce(array_to_string(s.model_tokens, '-'), '')) "
        "FROM offer_signature s WHERE s.raw_offer_id = %s", (oid,)).fetchone()[0]
    nouveau = conn.execute("SELECT md5(%s || '|prix|' || %s || '|' || 'g1')", (h, A)).fetchone()[0]
    fiche = _fiche(conn, nouveau)
    conn.execute("INSERT INTO _ig_unit VALUES (%s, 'g1', %s, %s, %s, 1, 44.0)", (A, nouveau, h, PIECE))
    conn.execute(m._LINK_ITEM_GROUP_OFFERS)
    ligne = conn.execute("SELECT linked_status, product_id, link_method FROM raw_offer WHERE id = %s", (oid,)).fetchone()
    assert ligne == ("linked", fiche, "item_group")   # sans `hash_base`, elle restait « unresolved » en silence


# --- les vetements a code-barres, a 5x -----------------------------------------------------------------------------------


def _gtin(c, h, gtin, prix, cat, marchand=A):
    c.execute("CREATE TEMP TABLE IF NOT EXISTS _gtin_unit (gtin text, identity_hash text, category_id smallint, "
              "conflict boolean) ON COMMIT DROP")
    c.execute("INSERT INTO _gtin_unit VALUES (%s, %s, %s, false)", (gtin, h, cat))
    _offre(c, marchand, prix, gtin=gtin, cat=cat)


@pytest.mark.parametrize("cat, bas, haut, coupe", [
    (HABILLEMENT, 20.0, 120.0, True),    # x6 : Troy Lee, Bell
    (HABILLEMENT, 20.0, 100.0, True),    # x5 pile
    (HABILLEMENT, 20.0, 60.0, False),    # x3 : une solde FC-Moto, on ne coupe pas
    (PIECE, 20.0, 60.0, False),          # hors habillement : `_SPLIT_PRIX` (x2) s'en charge, pas cette regle
])
def test_les_vetements_a_code_barres_se_coupent_a_cinq(conn, cat, bas, haut, coupe):
    k = next(_n)
    _gtin(conn, f"hv{k}", f"9{k:012d}", bas, cat)
    _gtin(conn, f"hv{k}", f"9{k + 5000:012d}", haut, cat)
    conn.execute(m._SPLIT_PRIX_HABILLEMENT)
    distincts = conn.execute("SELECT count(DISTINCT identity_hash) FROM _gtin_unit").fetchone()[0]
    assert (distincts == 2) is coupe


# --- le detachement des offres deja mal rattachees ----------------------------------------------------------------------


def _isoler_du_reel(c):
    """La base locale contient de VRAIES offres mal rattachees : on les journalise d'avance, dans la transaction
    d'essai, pour que le detachement ne voie que les offres fabriquees (et que le plafond ne se declenche pas)."""
    c.execute(m._DETACHER_LOG)
    c.execute("INSERT INTO offre_detachee_prix (raw_offer_id) SELECT id FROM (" + m._DETACHER_CANDIDATS + ") q "
              "ON CONFLICT (raw_offer_id) DO NOTHING")


def _etat(c, oid):
    return c.execute("SELECT linked_status, product_id, link_method FROM raw_offer WHERE id = %s", (oid,)).fetchone()


def _lien_taille(c, oid, fiche):
    vid = c.execute("INSERT INTO variant (product_id, size_code) VALUES (%s, 'M') ON CONFLICT (product_id, size_code) "
                    "DO UPDATE SET size_code = 'M' RETURNING id", (fiche,)).fetchone()[0]
    c.execute("INSERT INTO offer_variant_link (raw_offer_id, variant_id) VALUES (%s, %s)", (oid, vid))


def test_le_cas_voca_l_offre_a_44_euros_quitte_la_fiche_a_4_euros(conn):
    _isoler_du_reel(conn)
    fiche = _fiche(conn, "hv")
    mousse = _offre(conn, A, 4.05, produit=fiche, gtin="9000000000017", methode="gtin")
    alu = _offre(conn, A, 44.01, produit=fiche, groupe="g2", methode="item_group")
    _lien_taille(conn, alu, fiche)
    with conn.cursor() as cur:
        detachees, refusees = m.detacher_ecarts_de_prix(cur)
    assert (detachees, refusees) == (1, 0)
    assert _etat(conn, alu) == ("unresolved", None, None)
    assert _etat(conn, mousse) == ("linked", fiche, "gtin")        # un code-barres est une preuve : jamais touche
    assert conn.execute("SELECT count(*) FROM offer_variant_link WHERE raw_offer_id = %s", (alu,)).fetchone()[0] == 0
    assert conn.execute("SELECT ancien_product_id FROM offre_detachee_prix WHERE raw_offer_id = %s", (alu,)).fetchone()[0] == fiche


def test_une_offre_detachee_une_fois_ne_l_est_plus(conn):
    _isoler_du_reel(conn)
    fiche = _fiche(conn, "hv")
    _offre(conn, A, 4.05, produit=fiche, gtin="9000000000024", methode="gtin")
    alu = _offre(conn, A, 44.01, produit=fiche, groupe="g2", methode="item_group")
    with conn.cursor() as cur:
        assert m.detacher_ecarts_de_prix(cur) == (1, 0)
    conn.execute("UPDATE raw_offer SET linked_status='linked', product_id=%s, link_method='item_group' WHERE id=%s", (fiche, alu))
    with conn.cursor() as cur:
        assert m.detacher_ecarts_de_prix(cur) == (0, 0)     # pas d'aller-retour
    assert _etat(conn, alu)[0] == "linked"


@pytest.mark.parametrize("cat, prix, detache", [
    (PIECE, 12.20, True), (PIECE, 12.00, False),
    (HABILLEMENT, 20.0, True), (HABILLEMENT, 19.9, False),
])
def test_le_detachement_suit_le_meme_seuil_que_la_separation(conn, cat, prix, detache):
    _isoler_du_reel(conn)
    fiche = _fiche(conn, "hv", cat)
    _offre(conn, A, 4.05 if cat == PIECE else 4.0, produit=fiche, gtin="9000000000031", methode="gtin", cat=cat)
    alu = _offre(conn, B, prix, produit=fiche, groupe="g2", methode="item_group", cat=cat)
    with conn.cursor() as cur:
        m.detacher_ecarts_de_prix(cur)
    assert (_etat(conn, alu)[0] == "unresolved") is detache


def test_les_liens_d_operateur_et_les_offres_retirees_ne_sont_jamais_detaches(conn):
    _isoler_du_reel(conn)
    fiche = _fiche(conn, "hv")
    _offre(conn, A, 4.05, produit=fiche, gtin="9000000000048", methode="gtin")
    voulu = _offre(conn, A, 44.0, produit=fiche, groupe="g2", methode="operator")
    retiree = _offre(conn, B, 44.0, produit=fiche, groupe="g3", methode="item_group", vivante=False)
    with conn.cursor() as cur:
        assert m.detacher_ecarts_de_prix(cur) == (0, 0)
    assert _etat(conn, voulu)[0] == "linked" and _etat(conn, retiree)[0] == "linked"


def test_au_dela_du_plafond_rien_n_est_detache_et_on_le_dit(conn, monkeypatch):
    _isoler_du_reel(conn)
    fiche = _fiche(conn, "hv")
    _offre(conn, A, 4.05, produit=fiche, gtin="9000000000055", methode="gtin")
    alu = _offre(conn, B, 44.0, produit=fiche, groupe="g2", methode="item_group")
    monkeypatch.setattr(m, "DETACHER_MAX_OFFRES", 0)
    with conn.cursor() as cur:
        assert m.detacher_ecarts_de_prix(cur) == (0, 1)
    assert _etat(conn, alu)[0] == "linked"                   # un flux casse ne defait pas des milliers de fiches


def test_le_detachement_et_la_separation_sont_branches_dans_run_match():
    import inspect
    src = inspect.getsource(m.run_match)
    assert src.index("detacher_ecarts_de_prix") < src.index("_COMPUTE_OFFER_IDENTITY")
    assert src.index("_BUILD_ITEM_GROUP_UNITS") < src.index("_IG_REF") < src.index("_IG_SEPARER_PRIX") \
        < src.index("_CREATE_PRODUCTS_FROM_ITEM_GROUP")
    assert src.index("_SPLIT_PRIX)") < src.index("_SPLIT_PRIX_HABILLEMENT")
