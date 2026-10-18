"""Un marchand neuf ne met jamais en quarantaine les offres des autres (18/10/2026).

Le premier essai complet avec Motard Bleu a envoye 19 860 codes-barres en quarantaine, et avec eux
+7 557 offres Speedway, +10 813 Motoblouz, +2 520 FC-Moto. `_ECARTER_DESACCORDS` ecarte l'offre du
marchand neuf EN DESACCORD, seule ; ce test le prouve sur des offres fabriquees, dans une
transaction qui n'est jamais validee (rien n'est ecrit dans la base).
"""

import itertools

import pytest

from mcpipe import match as m
from mcpipe.db import connect

NEUF, ANCIEN = 997, 998
_cpt = itertools.count(1)


@pytest.fixture
def conn():
    try:
        c = connect()
    except Exception as exc:  # pas de base locale
        pytest.skip(f"base indisponible : {exc}")
    try:
        c.execute("INSERT INTO merchant (id, code, platform, gtin_trust, reliability_rank, affiche) "
                  "VALUES (%s, 'essai_neuf', 'awin', 'trusted', 3, false), "
                  "(%s, 'essai_ancien', 'effinity', 'trusted', 1, true)", (NEUF, ANCIEN))
        yield c
    finally:
        c.rollback()
        c.close()


def _offre(c, marchand, gtin, *, marque="ixon", couleur="BK", cat=6, genre="U-A", pack=False,
           annee=None, vivante=True):
    n = next(_cpt)
    oid = c.execute(
        "INSERT INTO raw_offer (merchant_id, merchant_sku, raw_title, deeplink, gtin, raw_gtin, is_live, linked_status) "
        "VALUES (%s, %s, 'essai', 'https://x.test', %s, %s, %s, 'unresolved') RETURNING id",
        (marchand, f"essai{n}", gtin, gtin, vivante)).fetchone()[0]
    c.execute(
        "INSERT INTO offer_signature (raw_offer_id, brand_code, primary_colour, genre_age, is_pack, "
        "model_year, category_id, norm_txt) VALUES (%s, %s, %s, %s, %s, %s, %s, 'essai')",
        (oid, marque, couleur, genre, pack, annee, cat))
    return oid


def _statut(c, oid):
    return c.execute("SELECT linked_status FROM raw_offer WHERE id = %s", (oid,)).fetchone()[0]


def _ecarter(c):
    c.execute(m.sql_ecarter_desaccords([NEUF]))


@pytest.mark.parametrize("champ, neuf, ancien", [
    ("marque", dict(marque="gprexhaust"), dict(marque="gpr")),
    ("rayon", dict(cat=1), dict(cat=31)),
    ("couleur", dict(couleur="BK"), dict(couleur="SI")),
    ("genre", dict(genre="F-A"), dict(genre="H-A")),
    ("age", dict(genre="U-E"), dict(genre="U-A")),
    ("lot", dict(pack=True), dict(pack=False)),
    ("annee", dict(annee=2024), dict(annee=2026)),
])
def test_le_desaccord_ecarte_l_offre_neuve_et_jamais_l_ancienne(conn, champ, neuf, ancien):
    gtin = f"9{next(_cpt):012d}"
    o_neuf = _offre(conn, NEUF, gtin, **neuf)
    o_ancien = _offre(conn, ANCIEN, gtin, **ancien)
    _ecarter(conn)
    assert _statut(conn, o_neuf) == "rejected", champ
    assert _statut(conn, o_ancien) == "unresolved", champ


@pytest.mark.parametrize("neuf, ancien", [
    (dict(couleur="BK"), dict(couleur="BK-RD")),         # inclusion : pas un desaccord
    (dict(couleur="BK|MAT"), dict(couleur="BK")),        # fini precise d'un seul cote
    (dict(couleur=None), dict(couleur="RD")),            # couleur absente : aucune preuve
    (dict(genre="U-A"), dict(genre="F-A")),              # genre inconnu : aucune preuve
    (dict(cat=25), dict(cat=6)),                         # « non classe » : aucune preuve
    (dict(annee=None), dict(annee=2026)),                # annee absente
])
def test_un_manque_de_preuve_n_est_pas_un_desaccord(conn, neuf, ancien):
    gtin = f"9{next(_cpt):012d}"
    o_neuf = _offre(conn, NEUF, gtin, **neuf)
    _offre(conn, ANCIEN, gtin, **ancien)
    _ecarter(conn)
    assert _statut(conn, o_neuf) == "unresolved"


def test_un_code_barres_inconnu_des_autres_ou_une_offre_retiree_ne_compte_pas(conn):
    seul = _offre(conn, NEUF, f"9{next(_cpt):012d}")
    gtin = f"9{next(_cpt):012d}"
    o_neuf = _offre(conn, NEUF, gtin, marque="gprexhaust")
    _offre(conn, ANCIEN, gtin, marque="gpr", vivante=False)    # retiree : n'est plus une preuve
    _ecarter(conn)
    assert _statut(conn, seul) == "unresolved"
    assert _statut(conn, o_neuf) == "unresolved"


def test_deux_offres_neuves_ne_s_ecartent_pas_entre_elles(conn):
    gtin = f"9{next(_cpt):012d}"
    a = _offre(conn, NEUF, gtin, marque="gpr")
    b = _offre(conn, NEUF, gtin, marque="autre")
    _ecarter(conn)
    assert (_statut(conn, a), _statut(conn, b)) == ("unresolved", "unresolved")


def test_seuls_les_marchands_declares_neufs_sont_examines():
    from mcpipe.feeds import FEEDS
    assert [c for c, f in FEEDS.items() if f.ecarte_desaccords] == ["motardbleu"]


# --- le second filet : un marchand neuf n'est jamais la cause d'une quarantaine -------------


def test_une_offre_neuve_sur_un_code_barres_en_conflit_est_ecartee_les_autres_non(conn):
    conn.execute("CREATE TEMP TABLE _gtin_unit (gtin text, conflict boolean) ON COMMIT DROP")
    g_conflit, g_sain, g_seul = (f"9{next(_cpt):012d}" for _ in range(3))
    neuf_c = _offre(conn, NEUF, g_conflit)
    ancien_c = _offre(conn, ANCIEN, g_conflit)
    neuf_s = _offre(conn, NEUF, g_sain)
    ancien_s = _offre(conn, ANCIEN, g_sain)
    ancien_seul = _offre(conn, ANCIEN, g_seul)           # conflit entre anciens : le leur, il reste
    conn.execute("INSERT INTO _gtin_unit VALUES (%s, true), (%s, false), (%s, true)",
                 (g_conflit, g_sain, g_seul))
    n = conn.execute(m.sql_ecarter_conflits_neufs([NEUF])).rowcount
    assert n == 1
    assert _statut(conn, neuf_c) == "rejected"
    assert _statut(conn, ancien_c) == "unresolved"       # l'ancien marchand n'est pas touche
    assert _statut(conn, neuf_s) == "unresolved"         # pas de conflit : rien a faire
    assert _statut(conn, ancien_s) == "unresolved"
    assert _statut(conn, ancien_seul) == "unresolved"    # l'examen ne vise que les marchands neufs


def test_le_second_filet_est_branche_dans_run_match():
    import inspect
    src = inspect.getsource(m.run_match)
    assert "sql_ecarter_conflits_neufs" in src
    assert src.index("_BUILD_GTIN_UNITS") < src.index("sql_ecarter_conflits_neufs") < src.index("CREATE INDEX ON _gtin_unit")
