"""Text normalization: messy merchant strings -> clean, comparable fields.

Every function here is pure (no I/O, no DB). `signature` calls them once per
offer and stores the result; `match` compares the stored results, never the raw
text. Ported from the v1 PHP signature snippet the review agents wrote.

The dictionaries are deliberately data, not logic — extend the lists, don't
touch the functions.
"""

from __future__ import annotations

import re
import unicodedata

# --------------------------------------------------------------------------
# dictionaries
# --------------------------------------------------------------------------

# cleaned brand form (lowercase, alnum only)  ->  canonical brand code.
# A hit here means "known brand" — the flag gates auto-merge in `match`.
_BRAND_ALIAS: dict[str, str] = {
    # helmets
    "hjc": "hjc", "hjcrpha": "hjc",
    "shoei": "shoei", "shark": "shark",
    "scorpion": "scorpion", "scorpionexo": "scorpion",
    "airoh": "airoh", "ls2": "ls2", "nexx": "nexx", "arai": "arai",
    "nolan": "nolan", "nolangroup": "nolan", "xlite": "xlite", "grex": "grex",
    "astone": "astone", "bell": "bell",
    "agv": "agv", "schuberth": "schuberth", "suomy": "suomy", "caberg": "caberg",
    "roof": "roof", "kyt": "kyt", "premier": "premier", "momodesign": "momodesign",
    "mt": "mt", "mthelmets": "mt", "mthelmet": "mt",
    "6d": "6d", "6dhelmets": "6d",
    "lazer": "lazer", "shiro": "shiro", "just1": "just1", "leatt": "leatt",
    "trendy": "trendy", "marko": "marko", "stormer": "stormer", "nox": "nox",
    "qwart": "qwart", "kokpit": "kokpit", "tnt": "tnt", "tnthelmets": "tnt",
    # off-road / apparel
    "alpinestars": "alpinestars", "astars": "alpinestars", "alpine": "alpinestars",
    "shot": "shot", "shotbyfreegun": "shot", "freegunbyshot": "shot", "freegun": "shot",
    "oneal": "oneal", "oneindustries": "oneindustries",
    "acerbis": "acerbis", "acerbisottano": "acerbis",
    "kenny": "kenny", "pullin": "pullin", "answer": "answer",
    "troyleedesigns": "troyleedesigns", "tld": "troyleedesigns",
    "fox": "fox", "foxracing": "fox",
    "flyracing": "flyracing", "fly": "flyracing",
    "thor": "thor", "scott": "scott", "ufo": "ufo", "hebo": "hebo",
    "dxr": "dxr", "firstracing": "firstracing", "kiniredbull": "kiniredbull",
    "revit": "revit", "revitsport": "revit",
    "held": "held", "ixon": "ixon", "furygan": "furygan", "bering": "bering",
    "segura": "segura", "dainese": "dainese", "spidi": "spidi", "rst": "rst",
    "harisson": "harisson", "helstons": "helstons", "johndoe": "johndoe",
    "blauer": "blauer", "hevik": "hevik", "gms": "gms", "ixs": "ixs",
    "klim": "klim", "fxr": "fxr", "macna": "macna", "richa": "richa",
    "tucanourbano": "tucanourbano", "vquattro": "vquattro",
    # accessories / parts / luggage
    "givi": "givi", "kappa": "kappa", "shad": "shad", "bagster": "bagster",
    "sena": "sena", "cardo": "cardo", "midland": "midland",
    "puig": "puig", "ermax": "ermax", "barracuda": "barracuda",
    "hepcobecker": "hepcobecker", "sw": "swmotech", "swmotech": "swmotech",
    "rgracing": "rgracing", "chaft": "chaft", "doppler": "doppler",
    "tecnium": "tecnium", "bihr": "bihr", "gpr": "gpr", "tpz": "tpz",
    "mooseracing": "mooseracing", "moose": "mooseracing",
    "allballs": "allballs", "allballsracing": "allballs",
    "motoaxxe": "maxxe", "maxxe": "maxxe",
}

# base colour token -> 2-letter code
_COLOUR_BASE: dict[str, str] = {
    "noir": "BK", "black": "BK", "nero": "BK", "schwarz": "BK",
    "blanc": "WH", "white": "WH", "bianco": "WH", "weiss": "WH", "perle": "WH",
    "rouge": "RD", "red": "RD", "rosso": "RD",
    "bleu": "BL", "blue": "BL", "blu": "BL", "navy": "BL", "azur": "BL",
    "jaune": "YE", "yellow": "YE", "giallo": "YE", "gelb": "YE",
    "vert": "GN", "green": "GN", "verde": "GN", "kaki": "GN", "khaki": "GN",
    "army": "GN", "olive": "GN",
    "gris": "GY", "grey": "GY", "gray": "GY", "grigio": "GY", "anthracite": "GY",
    "nardo": "GY", "gunmetal": "GY",
    "orange": "OR",
    "rose": "PK", "pink": "PK",
    "violet": "PU", "purple": "PU", "lila": "PU",
    "marron": "BR", "brown": "BR", "chocolat": "BR", "cognac": "BR",
    "beige": "BG", "sable": "BG", "sand": "BG", "ivoire": "BG",
    "or": "GD", "gold": "GD", "dore": "GD", "oro": "GD",
    "argent": "SI", "silver": "SI", "chrome": "SI", "alu": "SI", "aluminium": "SI",
    "titane": "TI", "titanium": "TI", "titan": "TI",
    "bronze": "BZ",
    "carbone": "CB", "carbon": "CB", "carbonio": "CB",
    "cameleon": "CHAM", "chameleon": "CHAM", "irise": "CHAM",
    "multicolore": "MULTI", "multicolor": "MULTI", "multi": "MULTI",
}

# finish modifier -> code (a matte helmet is NOT a glossy helmet: kept separate)
_COLOUR_FINISH: dict[str, str] = {
    "mat": "MAT", "mate": "MAT", "matte": "MAT", "matt": "MAT", "opaco": "MAT",
    "brillant": "GLO", "gloss": "GLO", "glossy": "GLO", "lucido": "GLO", "shiny": "GLO",
    "fluo": "FLU", "fluorescent": "FLU", "hiviz": "FLU",
}

# words dropped from the model name: generic, category, gender, certification,
# year, marketing, colour and size tokens
_STOP: frozenset[str] = frozenset(
    """
    casque helmet casco moto motard motorcycle scooter pour de du le la les the with avec et a
    integral integrale modulable jet demijet cross crossover trial enduro adventure routier route
    urbain ville homme femme adulte enfant junior kid kids child youth mixte unisex uni lady ladies
    men women man herren damen kinder ece euro euro1 euro2 euro3 euro4 euro5 euro6
    2206 2205 dot homologue homologuee certifie certified
    norme promo soldes destockage nouveau nouvelle new edition collection serie
    2018 2019 2020 2021 2022 2023 2024 2025 2026 2027 2028 2029 2030
    double ecran solaire pinlock bluetooth intercom pack offert sun visor visiere
    noir black blanc white rouge red bleu blue navy jaune yellow vert green army olive gris grey
    gray gunmetal nardo anthracite orange rose pink violet purple teal marron brown beige sable or
    gold
    argent silver titane titanium titan carbone carbon mat matte brillant gloss fluo perle kaki
    clair fonce multicolore
    xs s m l xl xxl xxxl 2xl 3xl 4xl tu tailleunique
    h2o d3o d30 waterproof gore tex membrane protection homologation
    """.split()
)

_MODEL_REF_RE = re.compile(r"\b([a-z]{1,5}\d{1,4}[a-z]?|\d{2,4}[a-z]{1,3})\b")
_SIZE_TITLE_RE = re.compile(r"-\s*([a-z0-9]{1,4})\s*$", re.I)
_SIZE_URL_RE = re.compile(r"taille[-/ ]([a-z0-9]{1,4})", re.I)
# an mpn size suffix must be set off by a delimiter or preceded by a digit
# (168075199XS) — a bare "...L" at the end of an unbroken token is not a size
_SIZE_MPN_RE = re.compile(r"(?:[-_ /]|(?<=\d))(xxs|xs|s|m|l|xl|xxl|xxxl|2xl|3xl|4xl|tu)$", re.I)
_YEAR_RE = re.compile(r"\b(20(?:1[89]|2[0-9]))\b")
# a genuine multi-item pack, not "kit chaine" / "kit piston" (single products).
# runs on norm_txt output, so "+" is already gone — hence the gift+device pair.
_PACK_RE = re.compile(r"\b(pack|bundle|combo|multipack)\b|\blot de\b")
_PACK_GIFT_RE = re.compile(r"\boffert\b")
_PACK_DEVICE_RE = re.compile(r"\b(intercom|bluetooth|cardo|sena|masque|ecran|sacoche)\b")
_FEMALE_RE = re.compile(r"\b(femme|women|woman|lady|ladies|donna|wmn|damen|mesdames|stella)\b")
_MALE_RE = re.compile(r"\b(homme|men|man|herren|uomo)\b")
_CHILD_RE = re.compile(r"\b(enfant|kid|kids|kinder|junior|jr|youth|child|bimbo|cadet|baby)\b")

_LETTER_SIZES = "XXS|XS|S|M|L|XL|XXL|XXXL|2XL|3XL|4XL"
# trailing size on an mpn: a letter size glued onto a digit (168075199XS), or a
# size / plausible numeric size (EU 34-52, helmet cm 53-65) after a delimiter
_BASE_SKU_TAIL_RE = re.compile(
    rf"(?<=\d)({_LETTER_SIZES})$|[-_ ]({_LETTER_SIZES}|TU|3[4-9]|4[0-9]|5[0-9]|6[0-5])$", re.I
)

_SIZE_LETTER_RE = re.compile(r"^(XXS|XS|S|M|L|XL|2XL|3XL|4XL|TU)$")
_SIZE_ALPHA_MAP = {
    "XXL": "2XL", "XXXL": "3XL", "XXXXL": "4XL",
    "TAILLEUNIQUE": "TU", "ONESIZE": "TU", "UNI": "TU",
}


# --------------------------------------------------------------------------
# functions
# --------------------------------------------------------------------------


def norm_txt(s: str | None) -> str:
    """Fold accents, lowercase, roman numerals II/III -> 2/3, keep [a-z0-9 ]."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"\biii\b", "3", s)
    s = re.sub(r"\bii\b", "2", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def brand(raw: str | None) -> tuple[str, bool]:
    """(canonical brand code, is_known). Unknown brands still return a usable
    normalized code, but the flag gates auto-merge later."""
    key = re.sub(r"[^a-z0-9]", "", norm_txt(raw))
    if key in _BRAND_ALIAS:
        return _BRAND_ALIAS[key], True
    return key, False


def colour(raw: str | None) -> tuple[str, str, str]:
    """(canonical e.g. 'BK-RD|MAT', first base bucket e.g. 'BK', source-agnostic).

    Returns ('', '', '') when no colour token is present.
    """
    toks = norm_txt(raw).split()
    if not toks:
        return "", "", ""
    bases: list[str] = []
    finishes: list[str] = []
    first = ""
    for t in toks:
        if t in _COLOUR_BASE:
            code = _COLOUR_BASE[t]
            if code not in bases:
                bases.append(code)
            if not first:
                first = code
        elif t in _COLOUR_FINISH:
            code = _COLOUR_FINISH[t]
            if code not in finishes:
                finishes.append(code)
    if not bases:
        return "", "", ""
    canon = "-".join(sorted(bases))
    if finishes:
        canon += "|" + "-".join(sorted(finishes))
    return canon, first, canon


# feed gender / age_group are GMC free text — whitelist, never trust raw
_FEED_GENDER = {
    "male": "H", "homme": "H", "men": "H", "man": "H", "herren": "H", "uomo": "H",
    "mannlich": "H", "hombre": "H",
    "female": "F", "femme": "F", "women": "F", "woman": "F", "damen": "F", "donna": "F",
    "weiblich": "F", "mujer": "F",
    "unisex": "U", "unisexe": "U", "uni": "U", "mixte": "U",
}
_FEED_AGE = {
    "adult": "A", "adulte": "A", "adults": "A", "adulti": "A",
    "kids": "E", "kid": "E", "enfant": "E", "child": "E", "children": "E", "junior": "E",
    "youth": "E", "newborn": "E", "infant": "E", "toddler": "E", "baby": "E", "kinder": "E",
}


def genre_age(blob: str, feed_gender: str | None = None,
              feed_age_group: str | None = None) -> str:
    """'U-A' unisex-adult, 'F-A', 'H-E', ... — a hard partition, never crossed.

    Combines the title signal with the feed's own gender/age fields. Rule: take
    the more specific value; on a direct F-vs-H clash the title wins (a human
    wrote 'femme'); child always beats adult.
    """
    title_g = "F" if _FEMALE_RE.search(blob) else ("H" if _MALE_RE.search(blob) else None)
    title_child = _CHILD_RE.search(blob) is not None
    feed_g = _FEED_GENDER.get(norm_txt(feed_gender)) if feed_gender else None
    feed_a = _FEED_AGE.get(norm_txt(feed_age_group)) if feed_age_group else None

    # title wins when it has a signal (incl. a direct F-vs-H clash), feed fills gaps
    g = title_g or feed_g or "U"
    a = "E" if (title_child or feed_a == "E") else (feed_a or "A")
    return f"{g}-{a}"


def model_year(blob: str) -> int | None:
    m = _YEAR_RE.search(blob)
    return int(m.group(1)) if m else None


def is_pack(blob: str) -> bool:
    """True only for a real multi-item bundle. `blob` is norm_txt output."""
    if _PACK_RE.search(blob):
        return True
    return bool(_PACK_GIFT_RE.search(blob) and _PACK_DEVICE_RE.search(blob))


def valid_gtin(s: str | None) -> str | None:
    """Return the GTIN if it is a real GS1 barcode (8/12/13/14 digits, valid
    check digit, not a zero/placeholder), else None."""
    if not s:
        return None
    g = s.strip()
    if not g.isdigit() or len(g) not in (8, 12, 13, 14) or set(g) == {"0"}:
        return None
    digits = [int(c) for c in g]
    check = digits.pop()
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return g if (10 - total % 10) % 10 == check else None


def size_code(raw_size: str | None, title: str | None, link: str | None,
              mpn: str | None) -> tuple[str, str]:
    """(normalized size, source). Size lives on the offer, never in product identity."""
    cand, src = (raw_size or "").strip(), "feed"
    if not cand and link:
        m = _SIZE_URL_RE.search(link)
        if m:
            cand, src = m.group(1), "url"
    if not cand and title:
        m = _SIZE_TITLE_RE.search(title)
        if m:
            cand, src = m.group(1), "title"
    if not cand and mpn:
        m = _SIZE_MPN_RE.search(mpn)
        if m:
            cand, src = m.group(1), "mpn"
    if not cand:
        return "", ""

    c = re.sub(r"[^a-z0-9]", "", cand, flags=re.I).upper()
    c = _SIZE_ALPHA_MAP.get(c, c)
    if _SIZE_LETTER_RE.match(c):
        return c, src
    if re.fullmatch(r"5[3-9]|6[0-5]", c):
        return c + "CM", src
    if re.fullmatch(r"3[5-9]|4[0-9]|5[0-2]", c):
        return "EU" + c, src
    return "", ""


def model(title: str | None, brand_code: str, colour_raw: str | None,
          size_raw: str | None) -> tuple[list[str], str, str]:
    """(sorted distinctive tokens, model_core_ref e.g. 'ff807', strength).

    strength: 'strong' (has an alnum ref), 'medium' (>=2 tokens), 'weak' (1),
    'empty' (0).
    """
    t = norm_txt(title)
    # strip the brand and every alias that resolves to the same canonical code
    brand_forms = {norm_txt(brand_code)} | {
        a for a, canon in _BRAND_ALIAS.items() if canon == brand_code
    }
    for bf in brand_forms:
        if bf:
            t = re.sub(rf"\b{re.escape(bf)}\b", " ", t)
    for w in norm_txt(f"{colour_raw or ''} {size_raw or ''}").split():
        if len(w) > 1:
            t = re.sub(rf"\b{re.escape(w)}\b", " ", t)

    kept = [w for w in t.split() if w and w not in _STOP]
    # anchor: an alnum ref built from the KEPT tokens (so "gt air 2" -> "gtair2"
    # but "euro 3" never appears — "euro" is a stopword). Only trust it as an
    # identity anchor when there is at least one other distinctive token.
    refs = _MODEL_REF_RE.findall("".join(kept) + " " + " ".join(kept))
    non_ref = [w for w in kept if w not in refs]
    core_ref = refs[0] if (refs and non_ref) else ""

    if core_ref:
        strength = "strong"
    elif len(kept) >= 2:
        strength = "medium"
    elif len(kept) == 1:
        strength = "weak"
    else:
        strength = "empty"

    return sorted(kept), core_ref, strength


def base_sku(mpn: str | None) -> str:
    """mpn with a trailing size token stripped — the Motoblouz colour hypothesis."""
    if not mpn:
        return ""
    m = mpn.strip()
    stripped = _BASE_SKU_TAIL_RE.sub("", m)
    return stripped if stripped and stripped != m else m
