"""Unit tests for `enrich`'s per-offer category decisions.

Pure and offline (no DB). They lock in the conservative rules: a coarse-bucket
offer is only reclassified on a confident, *different* read, and a helmet's
subtype is borrowed from a GTIN neighbour before the title is trusted — the
title being the signal that can name two types at once, or call the
adventure/trail family "enduro" where every other merchant says integral.
"""

from __future__ import annotations

from mcpipe.enrich import (
    decide_helmet_category,
    decide_override,
    helmet_subtype_from_title,
    is_helmet_accessory,
)

CASUAL = 23  # apparel_casual — FC-Moto's `tops` maps here
JACKET = 6
PANTS = 7
UNKNOWN = 25

HELMET = 1  # generic parent — must never be written or borrowed
INTEGRAL = 2
JET = 3
MODULAR = 4
CROSS = 5


# --- rule 1: coarse apparel buckets, read from the title -------------------


def test_real_jacket_title_is_reclassified():
    assert decide_override("Alpinestars Dice Veste textile moto", CASUAL) == JACKET
    assert decide_override("Blouson en cuir Ixon", CASUAL) == JACKET


def test_trousers_title_is_reclassified():
    assert decide_override("Pantalon textile moto Revit", CASUAL) == PANTS


def test_title_without_strong_keyword_is_left_alone():
    assert decide_override("Klim Mesa Falls Wool Chemise à manches longues", CASUAL) is None


def test_no_override_when_title_matches_current_mapping():
    assert decide_override("Tee-shirt Alpinestars", CASUAL) is None


def test_empty_title_is_safe():
    assert decide_override(None, CASUAL) is None
    assert decide_override("", CASUAL) is None


# --- helmet subtype read from a title --------------------------------------


def test_title_names_one_subtype():
    assert helmet_subtype_from_title("Casque jet Shark Nano") == JET
    assert helmet_subtype_from_title("Shot Lite Core Casque de motocross") == CROSS
    assert helmet_subtype_from_title("Casque modulable Nolan N100") == MODULAR
    assert helmet_subtype_from_title("Casque intégral AGV K6") == INTEGRAL


def test_title_naming_two_subtypes_is_ambiguous():
    # the real trap: a modular helmet described by its integral chin bar
    assert helmet_subtype_from_title("Casque modulable à mentonnière intégrale") is None


def test_title_without_subtype_says_nothing():
    assert helmet_subtype_from_title("HJC i91 Casque") is None
    assert helmet_subtype_from_title(None) is None


# --- rule 2: the helmet cascade --------------------------------------------


def test_non_moto_helmet_goes_to_unknown():
    google = "Sporting Goods > Outdoor Recreation > Cycling > Bicycle Helmets"
    assert decide_helmet_category("Casque jet", [JET], google) == UNKNOWN


def test_unanimous_neighbours_are_borrowed():
    assert decide_helmet_category("HJC i91 Casque", [JET, JET], None) == JET


def test_borrowing_outranks_the_title():
    # FC-Moto titles the adventure family "enduro/cross"; neighbours say
    # integral. Trusting the title here would contradict merges that work.
    assert decide_helmet_category("Klim X1 Alpha Barre Enduro", [INTEGRAL], None) == INTEGRAL


def test_neighbours_disagreeing_means_abstain():
    assert decide_helmet_category("HJC i91 Casque", [JET, MODULAR], None) is None


def test_generic_and_unknown_neighbours_are_not_lendable():
    # a neighbour that only says "helmet" or "unknown" carries no subtype:
    # it must neither be borrowed nor counted as agreement
    assert decide_helmet_category("Casque jet Shark Nano", [HELMET, UNKNOWN], None) == JET


def test_title_is_the_fallback_when_nobody_can_lend():
    assert decide_helmet_category("Casque modulable Nolan N100", [], None) == MODULAR


def test_no_lender_and_no_title_signal_leaves_it_alone():
    assert decide_helmet_category("HJC i91 Casque", [], None) is None


# --- spare parts sold inside the helmet bucket -----------------------------


def test_a_visor_is_an_accessory_not_a_helmet():
    # the helmet type in these titles says which helmet the part FITS
    assert is_helmet_accessory("Shark RS Jet Visière") is True
    assert is_helmet_accessory("AGV GT3-1 Sportmodular Pinlock Visière") is True
    assert is_helmet_accessory("Acerbis Flip FS-606 visière") is True
    assert is_helmet_accessory("Bandit JET Visière du casque") is True
    assert is_helmet_accessory("Bandit Bubble Visor pour Jet Helmet") is True
    assert is_helmet_accessory("Coiffe de casque BELL Moto 3") is True


def test_a_helmet_whose_model_name_contains_visor_is_not_an_accessory():
    # the real trap: "N20-2 Visor" is a model name, the item IS a jet helmet
    assert is_helmet_accessory("Nolan N20-2 Visor Dolce Vita Casque à réaction") is False
    assert is_helmet_accessory("Nolan N21 Visor 06 Verniciatura Speciale Casque jet") is False
    # a helmet merely mentioning its own screen stays a helmet
    assert is_helmet_accessory("Casque intégral Shoei avec écran solaire") is False


def test_accessories_outrank_borrowing():
    # whatever a neighbour calls it, a visor is not a helmet
    assert decide_helmet_category("Shark RS Jet Visière", [JET], None) == UNKNOWN


def test_flip_is_not_a_modular_keyword():
    # "Flip" is a product line here, it used to turn 27 visors into modulars
    assert helmet_subtype_from_title("Acerbis Flip FS-606") is None
