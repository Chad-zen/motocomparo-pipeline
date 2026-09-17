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
from datetime import date
from decimal import Decimal, InvalidOperation

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

# Last-resort colour words — see the `if not bases` branch of colour().
# French feminine forms the exact-token map above misses ("Bulle MRA Racing
# noire"). They resolve to codes that ALREADY exist, which is the whole reason
# they are safe.
#
# Deliberately NOT here: `bordeaux`, `camo`/`camouflage`, `turquoise`. They
# needed codes of their own (collapsing bordeaux into RD would merge a bordeaux
# jacket with a red one — a false merge), but a brand-new code is a word no
# other merchant uses, so it reads as a DISAGREEMENT on a barcode every other
# merchant already agrees on. Measured live: adding the three broke 74 working
# merges out of 78 lost — the same Segura Lady Garrisson is "rouge" at FC-Moto
# and "bordeaux" everywhere else; the same 100% Brisker gloves are "camo" at one
# and "camo/noir" at another. Colour naming is not standardised between
# merchants, so a colour word only pays off when the vocabulary is shared.
_COLOUR_FALLBACK: dict[str, str] = {
    "noire": "BK", "blanche": "WH", "verte": "GN", "grise": "GY",
    "bleue": "BL", "violette": "PU", "doree": "GD", "argentee": "SI",
}

# finish modifier -> code (a matte helmet is NOT a glossy helmet: kept separate
# — confirmed by the site owner: a buyer treats matte and gloss as two products)
_COLOUR_FINISH: dict[str, str] = {
    "mat": "MAT", "mate": "MAT", "matte": "MAT", "matt": "MAT", "opaco": "MAT",
    "brillant": "GLO", "gloss": "GLO", "glossy": "GLO", "lucido": "GLO", "shiny": "GLO",
    "fluo": "FLU", "fluorescent": "FLU", "hiviz": "FLU",
}

# words dropped from the model name: generic, category, gender, certification,
# year, marketing, colour and size tokens. `standard`/`long`/`court`/`king
# size`/`regular` are leg-length fit variants (boots, pants) — a real fitting
# choice like size, not a different product; left in, they became distinct
# `model_tokens` and produced 4 separate products for one real item (Held
# Arese ST GTX: standard/long/king size/court all sharing one item_group_id
# at every merchant), the same false-split class the size/colour stripping
# just above already exists to prevent.
# ATTENTION : cette chaîne est découpée par `.split()`. Un commentaire écrit
# À L'INTÉRIEUR y entrerait mot par mot — « mais », « pas », « donnait » —
# et ces mots seraient alors retirés de vrais noms de produits. Commenter
# au-dessus, jamais dedans.
#
# « taille / tailles » ajoutés le 14/09/2026 : « size » y était mais pas sa
# traduction, et « Housse Moto Ixon Blanky (Taille M) » donnait les jetons
# [blanky, housse, taille] — d'où une adresse de fiche en « -housse-taille- »
# et 224 fiches portant un mot d'identité qui n'identifie rien.
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
    xs s m l xl xxl xxxl 2xl 3xl 4xl 5xl 6xl tu tailleunique
    h2o d3o d30 waterproof gore tex membrane protection homologation
    standard long court king size regular normal
    taille tailles
    """.split()
)

_MODEL_REF_RE = re.compile(r"\b([a-z]{1,5}\d{1,4}[a-z]?|\d{2,4}[a-z]{1,3})\b")
# Le tiret doit être DÉTACHÉ. Un vrai suffixe de taille est séparé — « Stoner
# - XL », « Skwal - 59 », « Couronne JT 853 - 520 » ; une génération de modèle
# est collée — « BNS TECH-2 », « Tissu-MESH », « GT-Air ». Signalé par la
# propriétaire le 14/09/2026 : une protection cervicale Alpinestars affichait
# « taille 2 » à côté des XS/M et L/XL que six autres marchands déclarent.
#
# Mesuré sur la base : sur 50 666 tailles lues dans un titre, 39 216 viennent
# d'un tiret collé — donc des générations — contre 11 103 d'un tiret détaché,
# qui sont de vraies caractéristiques (pas de chaîne, nombre de rayons).
_SIZE_TITLE_RE = re.compile(r"-\s+([a-z0-9]{1,4})\s*$", re.I)
_SIZE_URL_RE = re.compile(r"taille[-/ ]([a-z0-9]{1,4})", re.I)
# an mpn size suffix must be set off by a delimiter or preceded by a digit
# (168075199XS) — a bare "...L" at the end of an unbroken token is not a size
# A manufacturer reference often ends in the size. Letter sizes were handled
# from the start; `T6`..`T13` were not, and they are how French merchants write
# a glove size. Live example, the Helstons Swallow: FC-Moto and La Bécanerie both
# ship `20190067-NO-T6`, read it, and show size 6 — Motoblouz ships the very same
# reference and showed "size not stated", because nothing looked for `-T6`.
#
# Only the `T` form is added. A bare number at the end of a reference is NOT
# taken as a size: it is just as often a colour code or a version, and 29,593
# offers carry one. Reading those needs a per-category range (gloves 6-11, boots
# 36-48, nothing elsewhere) and is a separate, measured piece of work — inventing
# sizes is the mistake this pipeline spent 2026-09-13 undoing.
_SIZE_MPN_RE = re.compile(
    r"(?:[-_ /]|(?<=\d))(xxs|xs|s|m|l|xl|xxl|xxxl|2xl|3xl|4xl|tu|t\d{1,2})$", re.I
)
# A leg-length word glued to a letter size: "Short XL", "M court", "LONGM".
# `size_code` has already stripped spaces by the time this runs, so both orders
# have to be matched. The size is what survives; the cut is dropped.
_FIT_PREFIX_RE = re.compile(
    r"(?:SHORT|LONG|COURT|REGULAR|STANDARD|KING)(?P<taille>XXS|XS|S|M|L|XL|XXL|[2-6]XL)"
    r"|(?P<taille2>XXS|XS|S|M|L|XL|XXL|[2-6]XL)(?:SHORT|LONG|COURT|REGULAR|STANDARD|KING)",
    re.I,
)


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

_SIZE_LETTER_RE = re.compile(r"^(XXS|XS|S|M|L|XL|2XL|3XL|4XL|5XL|6XL|TU)$")
_SIZE_ALPHA_MAP = {
    "XXL": "2XL", "XXXL": "3XL", "XXXXL": "4XL", "XXXXXL": "5XL", "XXXXXXL": "6XL",
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
        # Last resort only, never alongside a known colour. Running these words
        # in the pass above would ADD a colour to offers that already resolve to
        # one — "noir/blanche" would turn BK into BK-WH while its barcode twin
        # stays BK, and the conflict gate compares whole strings, so the pair
        # would be quarantined although both agree. Measured: ~36 barcode groups
        # lost that way, for no gain. The same rule is why tint words (fumé,
        # iridium, transparent) are absent here: "écran fumé gris" is grey, and
        # the trade says a clear visor is *transparent*, never *clair* — which
        # is why `clair` sits in _STOP (82% of its uses are a shade of another
        # colour: "bleu clair"). See docs/product-decisions.md.
        for t in toks:
            if t in _COLOUR_FALLBACK:
                code = _COLOUR_FALLBACK[t]
                if code not in bases:
                    bases.append(code)
                if not first:
                    first = code
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
    # a compound/range value we don't otherwise recognize (feed sends "28/30/
    # 32/34", "S/M", "S (55/56)", "US-28", a boot size outside the two known
    # 2-digit ranges, ...) — every one of these still IS a real, distinct
    # size. Discarding it to "" used to make `match.py` collapse it into the
    # shared 'TU' ("one size") bucket alongside every other unparsed size —
    # merging genuinely different sizes as if they were the same variant.
    # Keeping the cleaned original, even unprettified, is always safer:
    # worst case it is an ugly size label; the old behaviour was a silent
    # false merge, the exact class of bug this project treats as
    # unacceptable everywhere else.
    # A colour is never a size, whatever field it came from. Reading a size out
    # of a title picks up whatever
    # word sits where a size usually sits, and on 2026-09-13 that meant 6,456
    # Motoblouz offers filed under size "NOIR", 417 more at La Bécanerie, and
    # "BLEU" and "GRIP" besides. Each one is a variant nobody can buy, and it
    # splits a product that should have had one.
    if c.lower() in _COLOUR_BASE or c.lower() in _COLOUR_FALLBACK:
        return "", ""

    # Leg length is a fit, not a size: "Short XL" and "XL" are the same size in
    # two cuts, and the owner's rule (docs/product-decisions.md) is that leg
    # lengths are not real variants — they were already stripped from the model
    # name for exactly this reason, but survived here and created SHORTXL beside
    # XL. FC-Moto ships "Short XL", "Long M", "M court".
    if m := _FIT_PREFIX_RE.fullmatch(c):
        return (m.group("taille") or m.group("taille2")).upper(), src

    # Une taille lue dans un TITRE est le signal le plus faible dont on dispose :
    # on prend le mot qui occupe la place où une taille se trouve d'habitude, et
    # rien ne garantit que c'en soit une. Mesuré le 2026-09-14 : 57 135 offres
    # tiraient leur taille du titre, et sur les rayons habillement les valeurs
    # les plus fréquentes étaient PURE, MONO, TECH, AIR, DRY, TEX, CITY, GT,
    # RAID, YUMA — des mots de modèle et d'argumentaire. MESH avait ainsi donné
    # une « taille MESH » sur un blouson Helstons, à côté des S/M/L/XL que cinq
    # autres marchands déclaraient proprement.
    #
    # Interdire MESH, puis CUIR, puis GORETEX, serait une liste sans fin. La
    # règle tenable est l'inverse : depuis cette source-là, on n'accepte QUE ce
    # qui a la forme d'une taille. Les formes reconnues ont déjà été rendues
    # plus haut (lettres, tours de tête en CM, pointures EU, coupes) ; tout ce
    # qui arrive ici est un mot libre, et un mot libre n'est jamais une taille.
    #
    # Les autres sources gardent leur liberté : `feed` est déclaré par le
    # marchand, `url` et `mpn` occupent une position structurée. Seul le titre
    # est de la prose.
    # ... mais seulement quand le candidat est un MOT. La frontière n'est pas
    # arbitraire, elle est mesurée : sur les rayons habillement, le bruit est
    # alphabétique (PURE, MONO, TECH, AIR, DRY, TEX, CITY, GT, RAID, YUMA,
    # MESH), tandis que ce qu'il faut préserver sur les pièces est numérique —
    # 520, 525, 530 sont des pas de chaîne, 14 à 20 des nombres de dents. Ce
    # sont de vraies caractéristiques, et les confondre mélangerait deux chaînes
    # différentes.
    #
    # La propriétaire a tranché le 14/09/2026 : corriger l'habillement, laisser
    # les pièces à leur propre chantier. `category_id` n'existe pas encore à
    # l'heure des signatures — c'est `match` qui le pose — donc on ne peut pas
    # filtrer par rayon ici. Le test « contient un chiffre » sépare les deux
    # populations sans avoir besoin du rayon.
    if src == "title" and not any(ch.isdigit() for ch in c):
        return "", ""

    return (c[:24], src) if c else ("", "")


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

    # dedupe (order-preserving) — a merchant title that repeats its own name
    # (seen live: "Pantalon REV'IT Stratum ... - Pantalon moto REV'IT") would
    # otherwise duplicate every one of its words in `model_tokens`, leaking
    # into `model_display`/`slug` as "It It Pantalon Pantalon Rev Rev ..."
    kept = list(dict.fromkeys(w for w in t.split() if w and w not in _STOP))
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


# --- price and availability -------------------------------------------------

# Feeds state the price four ways: '64.99 EUR' (FC-Moto), '79.00' (Effinity),
# '132.00' (Motoblouz) and the occasional comma decimal. Thousands separators
# appear on big-ticket items ('1 299,00'). The currency, when stated, is a
# trailing ISO code.
_PRICE_RE = re.compile(
    r"^\s*(?P<amount>[0-9][0-9\s., ']*)\s*(?P<cur>[A-Z]{3}|€|EUR)?\s*$", re.I
)

# what each merchant's availability column says. 'flux tendu' is Motoblouz's
# just-in-time wording — 86% of its catalogue, and the owner's rule is that it
# counts as available (docs/product-decisions.md). Speedway states 1/0.
_IN_STOCK_WORDS = {
    "in stock", "in_stock", "instock", "en stock", "enstock",
    "flux tendu", "fluxtendu", "available", "disponible", "1", "true", "yes",
}
_OUT_OF_STOCK_WORDS = {
    "out of stock", "out_of_stock", "outofstock", "rupture", "epuise",
    "indisponible", "unavailable", "0", "false", "no",
}


def price(raw: str | None) -> tuple[Decimal | None, str | None]:
    """(amount, currency) from a feed's price field, or (None, None).

    Returns None rather than guessing when the field is absent, zero or
    unparseable: an offer with no price is simply not comparable, whereas a
    wrong price is the one thing a price-comparison site must never show.
    """
    if not raw:
        return None, None
    m = _PRICE_RE.match(raw)
    if not m:
        return None, None

    amount = m.group("amount")
    # strip thousands separators (space, NBSP, apostrophe), then settle the
    # decimal mark: whichever of '.' or ',' comes last is the decimal one.
    amount = re.sub(r"[\s ']", "", amount)
    if "," in amount and "." in amount:
        if amount.rfind(",") > amount.rfind("."):
            amount = amount.replace(".", "").replace(",", ".")
        else:
            amount = amount.replace(",", "")
    elif "," in amount:
        amount = amount.replace(",", ".")

    try:
        value = Decimal(amount).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None, None
    if value <= 0:
        return None, None

    cur = m.group("cur")
    if cur:
        cur = "EUR" if cur in {"€", "EUR", "eur"} else cur.upper()
    return value, cur


def in_stock(raw: str | None) -> bool | None:
    """True / False / None from a feed's availability field.

    None means the merchant said nothing usable — deliberately distinct from
    False, so "we don't know" is never displayed as "out of stock".
    """
    if raw is None:
        return None
    token = re.sub(r"[\s _-]+", " ", raw.strip().lower())
    token = unicodedata.normalize("NFKD", token).encode("ascii", "ignore").decode()
    if not token:
        return None
    if token in _IN_STOCK_WORDS:
        return True
    if token in _OUT_OF_STOCK_WORDS:
        return False
    return None


def colour_vocabulary() -> frozenset[str]:
    """Every word this module recognises as a colour, tint or finish.

    Exposed so the storefront strips exactly the words the pipeline treats as
    colour, instead of keeping a second list that would drift out of step.
    Feminine forms are included: a title says "noire", a feed says "noir".
    """
    words = set(_COLOUR_BASE) | set(_COLOUR_FALLBACK) | set(_COLOUR_FINISH)
    words |= {w + "e" for w in words if not w.endswith("e")}
    words |= {w + "s" for w in list(words)}
    words |= {"transparent", "transparente", "fume", "fumee", "iridium", "irise"}
    return frozenset(words)


def sale_is_live(window: str | None, today: date | None = None) -> bool:
    """Is a promotional price in force right now?

    Google Shopping's `sale_price_effective_date` is two ISO timestamps joined by
    a slash: a promo can be announced days ahead, and publishing it early would
    quote a price the merchant is not charging yet.

    An empty or unreadable window means "no window given", which every feed here
    uses to mean "the promo is on" — FC-Moto leaves it blank on all 45,015 of
    its sale prices. Unreadable is deliberately treated the same way rather than
    as a refusal: the promo price is already gated on being lower than the
    reference price, so the failure mode is quoting a real discount, not an
    invented one.
    """
    if not window or "/" not in window:
        return True
    debut, _, fin = window.partition("/")
    jour = today or date.today()
    for borne, avant in ((debut, True), (fin, False)):
        texte = borne.strip()[:10]
        if not texte:
            continue
        try:
            limite = date.fromisoformat(texte)
        except ValueError:
            continue
        if avant and jour < limite:
            return False
        if not avant and jour > limite:
            return False
    return True
