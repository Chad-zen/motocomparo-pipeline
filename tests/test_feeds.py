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
    }


def test_merchant_ids_are_unique():
    ids = [f.merchant_id for f in FEEDS.values()]
    assert len(ids) == len(set(ids))


def test_gtin_trust_split():
    trusted = {c for c, f in FEEDS.items() if f.gtin_trust == "trusted"}
    synthetic = {c for c, f in FEEDS.items() if f.gtin_trust == "synthetic"}
    assert trusted == {"speedway", "labecanerie", "motoblouz", "fcmoto"}
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
    expected = {"effinity": ";", "netaffiliation": "|", "webgains": ","}
    for f in FEEDS.values():
        assert f.delimiter == expected[f.platform]
