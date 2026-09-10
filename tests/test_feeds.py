"""Sanity checks on the feed configuration itself."""

from mcpipe.feeds import FEEDS


def test_five_feeds_defined():
    assert set(FEEDS) == {
        "speedway",
        "labecanerie",
        "motoblouz",
        "maxxess",
        "motoaxxe",
    }


def test_gtin_trust_split():
    trusted = {c for c, f in FEEDS.items() if f.gtin_trust == "trusted"}
    synthetic = {c for c, f in FEEDS.items() if f.gtin_trust == "synthetic"}
    assert trusted == {"speedway", "labecanerie", "motoblouz"}
    assert synthetic == {"maxxess", "motoaxxe"}


def test_every_feed_maps_gtin_and_title():
    for code, f in FEEDS.items():
        assert "gtin" in f.columns, code
        assert "title" in f.columns, code
        assert "price" in f.columns, code


def test_delimiter_matches_platform():
    for f in FEEDS.values():
        expected = ";" if f.platform == "effinity" else "|"
        assert f.delimiter == expected
