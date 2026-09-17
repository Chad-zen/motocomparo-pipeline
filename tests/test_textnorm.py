"""Checks on the text-normalization primitives used to build offer signatures."""

from decimal import Decimal

import pytest

from mcpipe import textnorm as tn
from mcpipe.textnorm import size_code


def test_norm_txt_folds_accents_and_roman_numerals():
    assert tn.norm_txt("Casque intégral Shoei GT-Air II") == "casque integral shoei gt air 2"
    assert tn.norm_txt("Blousón III") == "blouson 3"
    assert tn.norm_txt(None) == ""


def test_brand_known_vs_unknown():
    assert tn.brand("ALPINESTARS") == ("alpinestars", True)
    assert tn.brand("A-Stars") == ("alpinestars", True)
    assert tn.brand("Shoei") == ("shoei", True)
    code, known = tn.brand("Obscure Brand Co")
    assert known is False
    assert code == "obscurebrandco"


def test_colour_matte_and_gloss_are_distinct():
    matte, _, _ = tn.colour("noir mat")
    gloss, _, _ = tn.colour("noir brillant")
    assert matte == "BK|MAT"
    assert gloss == "BK|GLO"
    assert matte != gloss


def test_colour_multi_is_sorted_and_stable():
    a, _, _ = tn.colour("blanc / rouge / noir")
    b, _, _ = tn.colour("noir blanc rouge")
    assert a == b == "BK-RD-WH"


def test_colour_absent():
    assert tn.colour("") == ("", "", "")
    assert tn.colour("taille unique") == ("", "", "")


def test_genre_age_is_a_hard_partition():
    assert tn.genre_age("blouson femme alpinestars stella") == "F-A"
    assert tn.genre_age("bottes cross enfant gaerne") == "U-E"
    assert tn.genre_age("casque integral shoei") == "U-A"


def test_genre_age_uses_feed_fields_then_title_wins():
    # feed fills a gap the title doesn't cover
    assert tn.genre_age("blouson alpinestars", feed_gender="male") == "H-A"
    assert tn.genre_age("veste ixon", feed_gender="female", feed_age_group="adult") == "F-A"
    # child always beats adult, whichever side says it
    assert tn.genre_age("gants enfant", feed_age_group="adult") == "U-E"
    assert tn.genre_age("gants thor", feed_age_group="youth") == "U-E"
    # direct clash: the human-written title wins
    assert tn.genre_age("blouson femme", feed_gender="male") == "F-A"
    # feed junk (multi-locale blob) is ignored, not trusted
    assert tn.genre_age("casque hjc", feed_gender="bg_BG:Унисекс") == "U-A"


def test_valid_gtin():
    assert tn.valid_gtin("3660815165942") == "3660815165942"  # real EAN-13
    assert tn.valid_gtin("4028017539302") == "4028017539302"
    assert tn.valid_gtin("0") is None
    assert tn.valid_gtin("0000000000000") is None
    assert tn.valid_gtin("10554") is None  # too short
    assert tn.valid_gtin("3660815165941") is None  # bad check digit
    assert tn.valid_gtin("") is None
    assert tn.valid_gtin(None) is None


def test_model_ref_anchor():
    tokens, ref, strength = tn.model("Casque LS2 FF808 Stream II Noir", "ls2", "noir", "")
    assert ref == "ff808"
    assert strength == "strong"
    assert "stream" in tokens
    assert "ls2" not in tokens  # brand stripped
    assert "noir" not in tokens  # colour stripped


def test_model_strips_brand_aliases_not_just_canonical():
    tokens, _, _ = tn.model("Astars Mandate Oversized T-shirt", "alpinestars", "", "")
    assert "astars" not in tokens  # alias of the canonical brand, still stripped
    assert "mandate" in tokens


def test_model_ref_needs_a_co_occurring_token():
    # "Euro 3" must not become the identity anchor "euro3"
    _, ref, _ = tn.model("Echappement homologue Euro 3", "", "", "")
    assert ref == ""
    # a lone material code is not a model
    _, ref2, _ = tn.model("Gants D3O noir", "held", "noir", "")
    assert ref2 == ""


def test_model_strips_glued_emission_norm():
    # "Euro3" glued as one word in the title (common on parts feeds)
    title = "Cylindre D.40 Polini Evolution Alu Derbi Euro3 50 cc"
    tokens, ref, _ = tn.model(title, "polini", "", "")
    assert ref != "euro3"
    assert "euro3" not in tokens


def test_size_code_sources():
    assert tn.size_code("XL", None, None, None) == ("XL", "feed")
    assert tn.size_code("", None, "https://x/produit?taille-m", None) == ("M", "url")
    assert tn.size_code("", "Bottes Gaerne SG12 noir- 44", None, None) == ("EU44", "title")
    assert tn.size_code("", None, None, None) == ("", "")


def test_size_code_mpn_fallback_needs_a_boundary():
    # a bare word ending in a size letter is NOT a size
    assert tn.size_code("", None, None, "BRAKECONTROL") == ("", "")
    assert tn.size_code("", None, None, "SUPERSMALL") == ("", "")
    # a delimited or digit-glued size suffix still works
    assert tn.size_code("", None, None, "168075199-XL") == ("XL", "mpn")
    assert tn.size_code("", None, None, "168075199XL") == ("XL", "mpn")


def test_size_code_5xl_6xl():
    assert tn.size_code("5XL", None, None, None) == ("5XL", "feed")
    assert tn.size_code("XXXXXXL", None, None, None) == ("6XL", "feed")


def test_size_code_compound_value_is_kept_not_discarded():
    """A raw size the parser can't fully canonicalize (a range, a combined
    size, an out-of-table number) must still come back as something
    non-empty and DISTINCT from a different such value — `match.py` treats
    an empty size_code as "one size" and merges every offer that has one
    into a single variant, so silently discarding a real (if messy) size
    used to merge genuinely different sizes together (found live: waist
    28/30/32/34, boot sizes 6-13, "S (55/56)", "S/M" were all collapsing
    into the same 'TU' variant)."""
    waist, _ = tn.size_code("28/30/32/34", None, None, None)
    boot, _ = tn.size_code("9", None, None, None)
    combo, _ = tn.size_code("S/M", None, None, None)
    assert waist and boot and combo
    assert len({waist, boot, combo}) == 3  # all distinct, none silently empty


def test_size_code_pure_punctuation_still_returns_empty():
    assert tn.size_code("---", None, None, None) == ("", "")


def test_size_never_leaks_into_model():
    tokens, _, _ = tn.model("Gants Furygan Jet noir- M", "furygan", "noir", "M")
    assert "m" not in tokens


def test_model_tokens_deduplicated():
    """A merchant title that repeats itself (real feed example: "Pantalon
    REV'IT Stratum Gore-Tex Standard Noir Gris - Pantalon moto REV'IT")
    must not duplicate every token — that leaked into model_display/slug as
    "It It Pantalon Pantalon Rev Rev Standard"."""
    tokens, _, _ = tn.model(
        "Pantalon REV'IT Stratum Gore-Tex Standard Noir Gris - Pantalon moto REV'IT",
        "revit", "noir gris", None,
    )
    assert len(tokens) == len(set(tokens))


def test_leg_length_never_leaks_into_model():
    """Leg-length fit words are a sizing choice, not model identity — left
    in, "Held Arese ST GTX Standard" and "...Long" hash as different
    products instead of two lengths of the same real item."""
    standard, _, _ = tn.model("Pantalon Held Arese ST GTX Standard noir", "held", "noir", None)
    long_, _, _ = tn.model("Pantalon Held Arese ST GTX Long noir", "held", "noir", None)
    king, _, _ = tn.model("Pantalon Held Arese ST GTX King Size noir", "held", "noir", None)
    assert standard == long_ == king


def test_pack_detection():
    assert tn.is_pack("pack casque gants")
    assert tn.is_pack("lot de 2 disques de frein")
    assert tn.is_pack("casque shoei intercom sena offert")  # gift + device
    # "kit" alone is not a pack — "kit chaine" / "kit piston" are single products
    assert not tn.is_pack("kit chaine ek 520")
    assert not tn.is_pack("kit piston vertex")
    assert not tn.is_pack("casque integral shoei gt air 2")


def test_model_year():
    assert tn.model_year("bottes cross 2024 gaerne") == 2024
    assert tn.model_year("casque shoei nxr2") is None
    assert tn.model_year("norme euro 2027 echappement") == 2027
    assert tn.model_year("casque 2031 special") is None  # out of range


def test_base_sku_is_deferred_but_conservative():
    # base_sku is not populated by `signature` yet (match owns it); keep the
    # function honest for when match uses it
    assert tn.base_sku("168075199XS") == "168075199"  # digit-glued letter size
    assert tn.base_sku("168075199-M") == "168075199"  # delimited size
    assert tn.base_sku("ABC123") == "ABC123"          # trailing digits, no delimiter
    assert tn.base_sku("A08-12D1-A02-07") == "A08-12D1-A02-07"  # -07 not a plausible size
    assert tn.base_sku("BRACKET-44") == "BRACKET"     # -44 is in EU size range (a known limit)
    assert tn.base_sku(None) == ""


# --- last-resort colour words (see textnorm._COLOUR_FALLBACK) --------------


def test_feminine_colour_is_read_when_nothing_else_matches():
    # "noir" was known, "noire" was not — 936 equipment offers lost their colour
    assert tn.colour("Bulle MRA Racing noire Honda CBR")[1] == "BK"
    assert tn.colour("Saute vent Puig Sport Noire")[1] == "BK"


def test_colour_words_no_other_merchant_uses_are_left_out():
    # bordeaux / camo needed codes of their own (bordeaux is not red), but a new
    # code is a word nobody else uses: live, the three of them broke 74 working
    # merges — "rouge" at one merchant, "bordeaux" at the next, same barcode
    assert tn.colour("Blouson Femme Bering Lady Scoop Bordeaux")[0] == ""
    assert tn.colour("Blouson textile Macna Redox urban camo")[0] == ""


def test_fallback_never_fires_when_a_real_colour_is_present():
    # the whole point: an offer already resolving to BK must stay BK, so its
    # barcode twin (also BK) is not quarantined over a string mismatch
    assert tn.colour("Blouson noir et blanche")[0] == "BK"
    assert tn.colour("Ecran fume gris")[1] == "GY"


def test_clair_is_never_a_colour():
    # trade vocabulary says "transparent"; "clair" is a shade of another colour
    assert tn.colour("Bulle Bullster Double courbure Fume clair")[0] == ""


# --- price and availability ------------------------------------------------


def test_price_formats_across_the_six_feeds():
    assert tn.price("64.99 EUR") == (Decimal("64.99"), "EUR")   # FC-Moto
    assert tn.price("79.00") == (Decimal("79.00"), None)        # Effinity
    assert tn.price("132.00") == (Decimal("132.00"), None)      # Motoblouz
    assert tn.price("156,53") == (Decimal("156.53"), None)      # comma decimal


def test_price_handles_thousands_separators():
    assert tn.price("1 299,00")[0] == Decimal("1299.00")
    assert tn.price("1.299,00")[0] == Decimal("1299.00")
    assert tn.price("1,299.00")[0] == Decimal("1299.00")


def test_no_price_rather_than_a_wrong_one():
    # an offer with no price is simply not comparable; a wrong price is the one
    # thing a price-comparison site must never show
    assert tn.price(None) == (None, None)
    assert tn.price("") == (None, None)
    assert tn.price("sur demande") == (None, None)
    assert tn.price("0.00") == (None, None)
    assert tn.price("-5.00") == (None, None)


def test_availability_vocabulary_of_each_merchant():
    for word in ("in stock", "in_stock", "en stock", "1"):
        assert tn.in_stock(word) is True
    for word in ("out of stock", "0"):
        assert tn.in_stock(word) is False


def test_flux_tendu_counts_as_available():
    # Motoblouz's just-in-time wording — 86% of its catalogue. The owner's rule:
    # it is available (docs/product-decisions.md)
    assert tn.in_stock("flux tendu") is True


def test_unknown_availability_is_not_out_of_stock():
    # None must stay distinct from False, so "the merchant said nothing" is
    # never displayed to a visitor as "out of stock"
    assert tn.in_stock(None) is None
    assert tn.in_stock("") is None
    assert tn.in_stock("nous consulter") is None


# --- une taille lue dans un titre doit ressembler à une taille ----------------
#
# `_SIZE_TITLE_RE` prend ce qui suit le dernier tiret d'un titre. Le plus souvent
# c'est bien une taille ; parfois c'est la matière ou un mot d'argumentaire.
# Mesuré le 2026-09-14 : 57 135 offres tiraient leur taille du titre, et sur les
# rayons habillement les valeurs les plus fréquentes étaient PURE, MONO, TECH,
# AIR, DRY, TEX, CITY, GT, RAID, YUMA. Le cas signalé par la propriétaire : un
# blouson Helstons affichait une « taille MESH » à côté des S/M/L/XL que cinq
# autres marchands déclaraient proprement.
#
# La règle retenue est une liste blanche, pas une liste noire : depuis cette
# source, on n'accepte que ce qui a la forme d'une taille. Interdire les
# matières une par une n'aurait jamais de fin.

@pytest.mark.parametrize("titre", [
    "HELSTONS Blouson STONER EVO AIR GIRL Tissu-MESH",
    "Blouson Ixon Pulsion-PURE",
    "Veste Rev It Neptune-TECH",
    "Blouson Furygan-AIR",
    "Pantalon Ixon-DRY",
])
def test_un_mot_libre_du_titre_n_est_pas_une_taille(titre):
    assert size_code(None, titre, None, None) == ("", "")


@pytest.mark.parametrize("titre,attendu", [
    ("Blouson Helstons Stoner - XL", "XL"),
    ("Gants Alpinestars SP X 3 - M", "M"),
    ("Blouson femme - TU", "TU"),
    ("Casque Shark Skwal - 59", "59CM"),      # tour de tête
    ("Bottes Falco Pyro - 44", "EU44"),       # pointure
])
def test_une_vraie_taille_du_titre_est_gardee(titre, attendu):
    assert size_code(None, titre, None, None) == (attendu, "title")


@pytest.mark.parametrize("titre,attendu", [
    ("Chaine DID VX3 Or - 520", "520"),    # pas de chaîne
    ("Couronne JT acier - 45", "EU45"),    # nombre de dents (lu comme pointure)
])
def test_une_valeur_numerique_du_titre_est_gardee(titre, attendu):
    """Les pièces sont un chantier à part (décision de la propriétaire, 14/09).

    520, 525 et 530 sont des pas de chaîne, 14 à 20 des nombres de dents : de
    vraies caractéristiques. Les supprimer confondrait deux chaînes différentes.
    Le filtre ne vise que les MOTS, pas les nombres.
    """
    assert size_code(None, titre, None, None)[0] == attendu


def test_les_autres_sources_gardent_leur_liberte():
    """Le flux est déclaré par le marchand, l'URL et la référence occupent une
    position structurée. Seul le titre est de la prose : lui seul est filtré."""
    assert size_code("S/M", None, None, None) == ("SM", "feed")
    assert size_code(None, None, "https://x/produit-taille-xl", None)[1] == "url"


# --- le tiret doit être détaché ----------------------------------------------
#
# Un vrai suffixe de taille est séparé du nom ; une génération de modèle y est
# collée. Signalé par la propriétaire le 14/09/2026 : une protection cervicale
# Alpinestars affichait « taille 2 », lue dans « BNS TECH-2 », à côté des XS/M
# et L/XL que six autres marchands déclarent proprement.
#
# Mesuré : sur 50 666 tailles lues dans un titre, 39 216 venaient d'un tiret
# collé — des générations — contre 11 103 d'un tiret détaché, qui sont de
# vraies caractéristiques (pas de chaîne, nombre de rayons, épaisseur de joint).

@pytest.mark.parametrize("titre", [
    "ALPINESTARS Neck Brace BNS TECH-2",        # génération, pas une taille
    "Casque Shoei GT-Air 2",
    "HELSTONS Blouson STONER EVO AIR Tissu-MESH",
])
def test_un_tiret_colle_est_une_generation_pas_une_taille(titre):
    assert size_code(None, titre, None, None) == ("", "")


@pytest.mark.parametrize("titre,attendu", [
    ("Blouson Helstons Stoner - XL", "XL"),
    ("Casque Shark Skwal - 59", "59CM"),
    ("Couronne JT. acier standard 2022 - 525", "525"),
])
def test_un_tiret_detache_porte_une_vraie_valeur(titre, attendu):
    assert size_code(None, titre, None, None)[0] == attendu
