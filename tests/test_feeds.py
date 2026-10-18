"""Sanity checks on the feed configuration itself."""

from mcpipe.feeds import FEEDS


def test_feeds_defined():
    assert set(FEEDS) == {
        "speedway",
        "labecanerie",
        "motoblouz",
        "maxxess",
        "motoaxxe",
        "fcmoto",
        "motardbleu",
    }


def test_merchant_ids_are_unique():
    ids = [f.merchant_id for f in FEEDS.values()]
    assert len(ids) == len(set(ids))


def test_gtin_trust_split():
    trusted = {c for c, f in FEEDS.items() if f.gtin_trust == "trusted"}
    synthetic = {c for c, f in FEEDS.items() if f.gtin_trust == "synthetic"}
    assert trusted == {"speedway", "labecanerie", "motoblouz", "fcmoto", "motardbleu"}
    assert synthetic == {"maxxess", "motoaxxe"}


def test_only_fcmoto_needs_a_token():
    assert FEEDS["fcmoto"].auth_token_env == "FEED_FCMOTO_TOKEN"
    assert all(f.auth_token_env is None for c, f in FEEDS.items() if c != "fcmoto")


def test_every_feed_maps_gtin_and_title():
    for code, f in FEEDS.items():
        assert "gtin" in f.columns, code
        assert "title" in f.columns, code
        assert "price" in f.columns, code


def test_delimiter_matches_platform():
    expected = {"effinity": ";", "netaffiliation": "|", "webgains": ",", "awin": ","}
    for f in FEEDS.values():
        assert f.delimiter == expected[f.platform]


def test_motard_bleu_est_masque_et_lit_la_taille_dans_custom_1():
    f = FEEDS["motardbleu"]
    assert f.affiche_au_depart is False          # pas sur le site avant validation
    assert f.columns["size"] == ["custom_1"]
    assert f.columns["gtin"] == ["ean"]           # product_GTIN est vide chez Awin
    assert f.columns["link"] == ["aw_deep_link"]  # le lien tracke, pas merchant_deep_link
    assert "rrp_price" not in sum(f.columns.values(), [])  # un prix conseille n'est pas une remise
    assert f.compression == "zip"
    assert "custom_1" in f.colonnes_requises and "ean" in f.colonnes_requises


def test_les_autres_marchands_restent_affiches_des_leur_creation():
    assert all(f.affiche_au_depart for c, f in FEEDS.items() if c != "motardbleu")
