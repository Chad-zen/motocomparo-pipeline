"""Codes to French, for display only.

The pipeline stores codes because they compare reliably across six merchants in
four languages. A visitor reads words. This module is the one place that
translates, so no template ever hard-codes a label.
"""

from __future__ import annotations

import re

from mcpipe import textnorm as tn

_COLOUR: dict[str, str] = {
    "BK": "noir", "WH": "blanc", "RD": "rouge", "BL": "bleu", "YE": "jaune",
    "GN": "vert", "GY": "gris", "OR": "orange", "PK": "rose", "PU": "violet",
    "BR": "marron", "BG": "beige", "GD": "or", "SI": "argent", "TI": "titane",
    "BZ": "bronze", "CB": "carbone", "CHAM": "caméléon", "MULTI": "multicolore",
}

_FINISH: dict[str, str] = {"MAT": "mat", "GLO": "brillant", "FLU": "fluo"}

_GENRE: dict[str, str] = {
    "adult": "", "men": "homme", "women": "femme", "kids": "enfant",
    "unisex": "mixte",
}

# S < M < L reads naturally; "S 55/56" and "XXL" do not sort as text.
_SIZE_ORDER = "3XS 2XS XXS XS S M L XL XXL 2XL 3XL 4XL".split()


def colour(code: str | None) -> str:
    """'BK|MAT' -> 'noir mat'. 'BK-WH' -> 'noir et blanc'. Unknown -> ''."""
    if not code or code == "unknown":
        return ""
    base, _, finish = code.partition("|")
    words = [_COLOUR.get(p, p.lower()) for p in base.split("-") if p]
    if not words:
        return ""
    out = words[0] if len(words) == 1 else " et ".join([", ".join(words[:-1]), words[-1]])
    if finish in _FINISH:
        out = f"{out} {_FINISH[finish]}"
    return out


def genre(code: str | None) -> str:
    return _GENRE.get((code or "").lower(), "")


def size_key(code: str) -> tuple[int, str]:
    """Sort letter sizes in wearing order, then anything else alphabetically."""
    letters = code.strip().upper().split()[0] if code.strip() else ""
    if letters in _SIZE_ORDER:
        return (_SIZE_ORDER.index(letters), "")
    return (len(_SIZE_ORDER), code)


def price(value: object) -> str:
    """49.9 -> '49,90 €'. French sites use a comma; a dot reads as an error."""
    if value is None:
        return ""
    return f"{float(value):,.2f}".replace(",", " ").replace(".", ",") + " €"


def product_title(brand: str, model: str, colour_code: str | None) -> str:
    """What the page is called. Colour belongs in the name: it defines the page."""
    parts = [brand.upper(), model]
    if c := colour(colour_code):
        parts.append(f"— {c}")
    return " ".join(p for p in parts if p)


# The feeds spell merchants in lower-case slugs. A visitor is being sent to a
# real shop and should read its real name.
_MERCHANT: dict[str, str] = {
    "speedway": "Speedway",
    "labecanerie": "La Bécanerie",
    "motoblouz": "Motoblouz",
    "maxxess": "Maxxess",
    "motoaxxe": "Moto-Axxe",
    "fcmoto": "FC-Moto",
}


def merchant(code: str | None) -> str:
    return _MERCHANT.get((code or "").lower(), (code or "").title())


def size_display(code: str | None) -> str:
    """'S5556' and 'S 55/56' both show as 'S'. 'TU' shows as nothing at all.

    Head-circumference numbers mean nothing to a buyer (the owner's rule). The
    richer value stays in the database; only the display is trimmed.

    'TU' is not a size. `match.py` uses it as the bucket for offers whose size
    could not be read — 46% of all variants — so printing "taille unique" on a
    helmet would state as fact something the merchant never said. It becomes an
    empty string: the row shows a dash, stays visible under every size filter,
    and never becomes a filter button of its own.
    """
    if not code:
        return ""
    raw = code.strip().upper()
    if raw in {"TU", "UNI", "ONESIZE", "TAILLEUNIQUE", "1U"}:
        return ""
    head = raw.split()[0] if raw.split() else raw
    for letters in sorted(_SIZE_ORDER, key=len, reverse=True):
        if head.startswith(letters) and (len(head) == len(letters) or head[len(letters)].isdigit()):
            return letters
    return raw


# --------------------------------------------------------------------- naming

# `product.model_display` is the identity token bag: alphabetically sorted and
# stripped so that six merchants writing the same helmet six ways still land on
# one product. That is why it reads as "3 Blouson Hyperspeed It Rev". It is a
# fingerprint, not a name, and showing it was the mistake. The name below is
# rebuilt from a real merchant title instead, which keeps the word order.
#
# Nothing here touches matching: this is display only, and falls back to the
# token bag whenever cleaning would leave too little to read.

_NOISE: frozenset[str] = frozenset(
    """
    veste vestes blouson blousons gant gants pantalon pantalons botte bottes
    chaussure chaussures casque casques sacoche sacoches gilet gilets combinaison
    surcombinaison bottine bottines protection protections dorsale ceinture
    jacket jacke glove gloves pants boots helmet
    moto motard motos motorcycle scooter homme femme enfant adulte junior mixte
    unisexe unisex men women man lady ladies herren damen kinder
    de du des la le les pour en et avec sur a au aux the with
    taille tailles size pluie impermeable imperméable waterproof thermique hiver
    ete été toutes saisons nouveau nouvelle promo neuf
    route routier urbain ville sport touring clair fonce foncé
    """.split()
)

# One vocabulary, defined by the pipeline: a second list here would drift.
_COLOUR_WORDS = tn.colour_vocabulary()
_SIZE_WORDS = frozenset(s.lower() for s in _SIZE_ORDER) | {"tu", "unique"}


# A size left at the end of a name: "… WP 38", "… Skinny L30", "Swallow T7"
# (glove sizes ship as T5..T13 at some merchants). Never a displacement:
# "Honda 600 V Transalp" keeps its 600 because only the LAST token is cut.
_SIZE_TAIL = re.compile(r"(?:3[4-9]|4[0-9]|5[0-2])|[LWlw]\d{2}|[Tt]\d{1,2}")


def _norm_token(tok: str) -> str:
    return "".join(ch for ch in tok.lower() if ch.isalnum())


def display_name(
    raw_title: str | None,
    brand_code: str,
    colour_code: str | None,
    fallback: str,
) -> str:
    """Turn one merchant's title into the product's name.

    Drops the brand (the page shows it separately), the colour (same), sizes and
    the category noun, and keeps everything else in the order it was written.
    Returns `fallback` — the token bag — when what is left is too thin to be a
    name, because a short wrong name is worse than a clumsy right one.
    """
    if not raw_title:
        return fallback

    title = raw_title.strip()
    # Merchants pad the title with a category tail: "Ixon Stream - Veste de pluie
    # Ixon". Everything before the first " - " is the part they actually named.
    for sep in (" - ", " – ", " | "):
        if sep in title:
            title = title.split(sep)[0]
            break

    brand = _norm_token(brand_code)

    kept: list[str] = []
    for tok in title.replace("/", " ").replace(",", " ").split():
        clean = tok.strip("-–—.,;:()[]")
        n = _norm_token(clean)
        if not n:
            continue
        if len(n) >= 2 and brand and (n in brand or brand in n):
            continue  # "REV'IT", "Rev", "It", "SW-Motech", "Motech"
        if n in _NOISE or n in _SIZE_WORDS:
            continue
        # any colour word goes, not only this product's own: the page shows
        # the colour on its own line, and "Stream Noire Transparente" is not
        # a model name.
        if n in _COLOUR_WORDS or tn.norm_txt(clean) in _COLOUR_WORDS:
            continue
        kept.append(clean)

    # A trailing garment size that slipped through the feed's own size field:
    # "Forma Adv Tourer WP 38", "Rev'it Chino Terry Skinny L30". Leg lengths
    # are not variants at all (docs/product-decisions.md), and a shoe size is
    # a variant, never part of the name. Only ever trimmed at the very end, so
    # a displacement ("Honda 600 V Transalp") is untouched.
    while kept and _SIZE_TAIL.fullmatch(kept[-1]):
        kept.pop()

    if not kept or len("".join(kept)) < 3:
        return fallback

    out = []
    for w in kept:
        # leave acronyms and references alone (RPHA, FF820, WP); only fix words
        # a merchant shouted or typed in lower case
        out.append(w if (w[:1].isupper() and not w.isupper()) or any(c.isdigit() for c in w)
                   else w.capitalize() if w.islower() or w.isupper() and len(w) > 4 else w)
    return " ".join(out)
