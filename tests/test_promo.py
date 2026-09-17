"""The promo-code reader, on the shapes these five shop pages actually take.

Every "must not match" case below is a real false positive the v1 snippet hit
before its blacklist and its guards were added — they are the reason the rules
look the way they do, so they are the ones worth keeping under test.
"""

from datetime import date

from mcpipe.promo import (
    conditions,
    find_codes,
    label,
    to_text,
    window,
)

# --- reading the code ---------------------------------------------------------

def test_finds_a_plain_promo_code():
    hits = find_codes("Profitez de -20 % avec le code ROULEZ20 sur tout le site.")
    assert set(hits) == {"ROULEZ20"}
    assert hits["ROULEZ20"].score == 40


def test_code_postal_is_not_a_promo_code():
    """The classic one: « code postal » matches the weakest pattern."""
    assert find_codes("Renseignez votre CODE POSTAL pour trouver un magasin") == {}


def test_ordinary_capitalised_words_are_refused():
    for noise in ("CODE LIVRAISON", "CODE PROMO CADEAUX", "CODE CONDITIONS"):
        assert find_codes(noise) == {}, noise


def test_short_all_letter_token_is_a_word_not_a_code():
    assert find_codes("CODE SUPER") == {}
    # with a digit, four characters are enough to be a code
    assert "SUP15" in find_codes("CODE SUP15")


def test_a_code_the_page_says_is_inactive_is_skipped():
    assert find_codes("CODE HIVER30 - INACTIF depuis le 1er mars") == {}


def test_running_capitals_are_a_heading_not_a_code():
    """Weak pattern only: capitals that keep going are a title."""
    assert find_codes("CODE PROMOTION2 GANTS ET CASQUES") == {}


def test_welcome_and_newsletter_codes_are_left_out():
    """They need an account or a first order — not usable from a product page."""
    assert find_codes(
        "Inscrivez-vous à la newsletter et recevez le code BIENVENUE10"
    ) == {}
    assert find_codes(
        "Parrainage : offrez le code PARRAIN15 à un ami"
    ) == {}


def test_an_ended_offer_is_skipped():
    assert find_codes("OFFRE TERMINÉE — le code SOLDES24 n'est plus valable") == {}


def test_best_scored_reading_wins():
    txt = ("CODE RENTREE25 dans le menu. Plus bas : profitez-en avec le code "
           "RENTREE25 jusqu'au 30 novembre.")
    hits = find_codes(txt)
    assert hits["RENTREE25"].score == 40
    assert "30 novembre" in hits["RENTREE25"].context


# --- the dates ----------------------------------------------------------------

def test_numeric_range():
    assert window("Offre valable du 01/09/2026 au 30/09/2026") == (
        date(2026, 9, 1), date(2026, 9, 30))


def test_written_month_range_straddling_the_new_year():
    start, end = window("du 20 décembre au 5 janvier", today=date(2026, 12, 1))
    assert (start, end) == (date(2026, 12, 20), date(2027, 1, 5))


def test_jusqu_au_without_a_year_assumes_the_next_occurrence():
    assert window("Jusqu'au 30 septembre inclus", today=date(2026, 9, 13))[1] == \
        date(2026, 9, 30)
    # a date already behind us meant next year
    assert window("Jusqu'au 3 février", today=date(2026, 9, 13))[1] == \
        date(2027, 2, 3)


def test_an_impossible_date_is_not_a_date():
    assert window("jusqu'au 31/09/2026")[1] is None


def test_no_date_at_all():
    assert window("Code promo valable sur tout le site") == (None, None)


# --- the wording --------------------------------------------------------------

def test_label_reads_the_discount():
    assert label("-20 % sur tout", "ROULEZ20") == "-20 % avec le code ROULEZ20"
    assert label("15 % de remise", "X15") == "-15 % avec le code X15"
    assert label("10 € offerts", "DIX") == "10 € de remise avec le code DIX"


def test_label_falls_back_when_the_page_states_no_amount():
    assert label("offre spéciale", "MOTO") == "Code promo MOTO"


def test_conditions_keep_what_decides_the_discount():
    c = conditions("valable dès 79 € d'achat, hors soldes, non cumulable")
    assert c == "dès 79 € d'achat · hors soldes · non cumulable"


def test_no_conditions_stated():
    assert conditions("profitez-en vite") == ""


# --- the HTML -----------------------------------------------------------------

def test_scripts_are_stripped_before_reading():
    """A shop's JSON payloads are full of tokens that read like codes."""
    html = '<script>var x = "CODE PROMO FAUX123";</script><p>Bonjour</p>'
    txt = to_text(html)
    assert "FAUX123" not in txt
    assert "Bonjour" in txt


def test_block_ends_separate_words():
    assert to_text("<li>CODE</li><li>PROMO</li>") == "CODE PROMO"


def test_entities_are_decoded():
    assert "dès 79 €" in to_text("<p>d&egrave;s 79 &euro;</p>")


# --- the date belongs to the code, not to the page ----------------------------

SPEEDWAY = (
    "Code Promo PRINTEMPS Jusqu'à 15% de remise "
    "Offre valable jusqu'au : 2026-04-16 23:59:00 Avec le code PRINTEMPS9 "
    "Code Promo SORTIE DE GARAGE Préparez votre moto "
    "Offre valable jusqu'au : 2026-03-18 23:59:00 Avec le code SPEED15 "
    "Promo SAINT VALENTIN Offre valable jusqu'au : 2026-03-02 00:00:00"
)


def test_each_code_gets_its_own_date_not_the_first_on_the_page():
    """A promo page is a list of offers, each with its own end date.

    Reading the first date of the page — what the v1 did — gave every code the
    date of whichever offer was printed at the top, so a code expired in March
    still looked live in September.
    """
    hits = find_codes(SPEEDWAY)
    assert window(hits["SPEED15"].context, at=hits["SPEED15"].at)[1] == date(2026, 3, 18)
    p9 = hits["PRINTEMPS9"]
    assert window(p9.context, at=p9.at)[1] == date(2026, 4, 16)


def test_iso_end_date():
    assert window("Offre valable jusqu'au : 2026-03-18 23:59:00")[1] == date(2026, 3, 18)


def test_premier_du_mois_and_weekday_are_read():
    assert window("Offre valable du 1er Septembre au 13 Septembre 23h59",
                  today=date(2026, 9, 5)) == (date(2026, 9, 1), date(2026, 9, 13))
    assert window("valable du Mardi 23 Juin 2026 00h01 au Dimanche 14 Février 2027 23h59") \
        == (date(2026, 6, 23), date(2027, 2, 14))


# --- les garde-fous ajoutés après la revue -------------------------------------

def test_une_date_sans_annee_trop_loin_est_refusee():
    """Une bannière oubliée depuis dix mois ne doit pas fabriquer un an de validité."""
    # « jusqu'au 3 février » lu le 13 septembre : le report au 03/02/2027 tombe
    # dans l'horizon (143 jours) et reste accepté.
    assert window("Jusqu'au 3 février", today=date(2026, 9, 13))[1] == date(2027, 2, 3)
    # « jusqu'au 20 août » lu le 13 septembre : le report serait à 341 jours.
    assert window("Jusqu'au 20 août", today=date(2026, 9, 13))[1] is None


def test_une_date_avec_annee_reste_lue_telle_quelle():
    """Motoblouz écrit vraiment « au Dimanche 14 Février 2027 » : on le croit."""
    assert window("valable du Mardi 23 Juin 2026 00h01 au Dimanche 14 Février 2027 23h59") \
        == (date(2026, 6, 23), date(2027, 2, 14))
