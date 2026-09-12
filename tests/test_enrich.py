"""Unit tests for `enrich.decide_override` — the per-offer category decision.

Pure and offline (no DB): locks in the conservative rule that a coarse-bucket
offer is reclassified ONLY when its title yields a confident, different
category. A title with no strong keyword must be left untouched, so a wrong
label is never invented — the review queue keeping a group is the safe outcome.
"""

from __future__ import annotations

from mcpipe.enrich import decide_override

CASUAL = 23  # apparel_casual — FC-Moto's `tops` maps here
JACKET = 6
PANTS = 7


def test_real_jacket_title_is_reclassified():
    assert decide_override("Alpinestars Dice Veste textile moto", CASUAL) == JACKET
    assert decide_override("Blouson en cuir Ixon", CASUAL) == JACKET


def test_trousers_title_is_reclassified():
    assert decide_override("Pantalon textile moto Revit", CASUAL) == PANTS


def test_title_without_strong_keyword_is_left_alone():
    # a genuine casual shirt: no jacket/trousers/… keyword → no override,
    # stays whatever the feed said (here: casual)
    assert decide_override("Klim Mesa Falls Wool Chemise à manches longues", CASUAL) is None


def test_no_override_when_title_matches_current_mapping():
    # title classifies to casual too → nothing to change
    assert decide_override("Tee-shirt Alpinestars", CASUAL) is None


def test_empty_title_is_safe():
    assert decide_override(None, CASUAL) is None
    assert decide_override("", CASUAL) is None
