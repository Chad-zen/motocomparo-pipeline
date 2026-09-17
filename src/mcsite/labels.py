"""Codes to French, for display only.

The pipeline stores codes because they compare reliably across six merchants in
four languages. A visitor reads words. This module is the one place that
translates, so no template ever hard-codes a label.
"""

from __future__ import annotations

import re
import unicodedata

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
    """49.9 -> '49,90 €'. French sites use a comma; a dot reads as an error.

    Les deux espaces sont INSÉCABLES, et ce n'est pas de la typographie : avec
    des espaces ordinaires, le navigateur a le droit de couper avant le « € ».
    Il le faisait — sur une carte étroite, « dès 126,99 » restait sur la ligne
    et le « € » tombait seul en dessous. Mesuré : le bloc prix passait de 19,5 à
    39 px de haut, sur 46 cartes de la page d'accueil.

    Corrigé ici plutôt que classe par classe : un prix écrit à un endroit qu'on
    a oublié de styler reste protégé.
    """
    if value is None:
        return ""
    return (f"{float(value):,.2f}"
            .replace(",", " ")      # milliers : espace fine insécable
            .replace(".", ",")
            + " €")                 # avant l'euro : espace insécable


# Une taille COLLÉE EN FIN de titre marchand : « Housse moto Ixon BLANKY - M »,
# « Housse Moto Ixon Blanky (Taille M) ». Le titre annonce alors UNE taille sur
# une fiche qui en compare quatre — il ment au visiteur avant même qu'il lise le
# tableau. Signalé par la propriétaire le 14/09/2026.
#
# Volontairement étroit. La règle d'affichage du projet est « le titre du
# marchand, tel quel » (décision du 13/09) : une version antérieure qui retirait
# la marque, la couleur et le nom de rayon lisait mieux sur certaines pages et
# en abîmait d'autres — « Cuir Swallow T7 ». On n'enlève donc QUE ce qui suit un
# tiret ou une parenthèse en toute fin, et seulement si c'est une taille
# reconnue. « Cuir Swallow T7 » n'a pas de séparateur : il n'est pas touché.
_TAILLE_FINALE = re.compile(
    r"\s*[-–—(]\s*(?:taille\s*)?"
    r"(?:3XS|2XS|XXS|XS|S|M|L|XL|XXL|[2-6]XL|TU)\s*\)?\s*$",
    re.IGNORECASE,
)


def sans_taille_finale(titre: str) -> str:
    """Retire une taille terminale d'un titre marchand. Ne touche à rien d'autre.

    Rend le titre inchangé si l'amputation laissait moins de trois caractères :
    un titre vide est pire qu'un titre qui annonce une taille.
    """
    coupe = _TAILLE_FINALE.sub("", titre).strip(" -–—(")
    return coupe if len(coupe) >= 3 else titre


_SEPARATEURS = (" - ", " – ", " — ", " | ")


def sans_queue_de_rayon(titre: str, brand_code: str) -> str:
    """Retire la queue « nom de rayon + marque » que certains marchands collent.

        Casque Cross Alpinestars SM3 Falcon Rouge - Casque Cross ALPINESTARS
        Bottes TCX Infinity 3 Gore-Tex Noir - Bottes et chaussures TCX

    La condition est la RÉPÉTITION DE LA MARQUE dans la queue, et c'est elle qui
    rend la règle sûre. Couper à tous les tirets perdrait de vraies
    informations — « Casque Scorpion EXO-RACE AIR - SOLID », où SOLID est le
    coloris — et c'est précisément l'erreur qui avait fait rejeter le
    reconstructeur de noms le 13/09. Une queue qui réécrit la marque, elle,
    n'apprend jamais rien : le nom de la marque est déjà affiché à côté.

    Mesuré sur les 28 716 fiches comparables le 14/09/2026 : 1 538 titres
    concernés (5 %), et 24 coupes tirées au hasard relues une par une — 24
    queues de rayon, aucune perte.

    Deux garde-fous : on ne coupe qu'au DERNIER séparateur, et jamais si le
    titre restant tombe sous huit caractères.
    """
    marque = _sans_signes(brand_code)
    if len(marque) < 3:
        return titre
    for sep in _SEPARATEURS:
        i = titre.rfind(sep)
        if i > 0 and marque in _sans_signes(titre[i + len(sep):]):
            court = titre[:i].strip()
            if len(court) >= 8:
                return court
    return titre


def _sans_signes(s: str) -> str:
    """Minuscules, sans accents, sans espaces ni tirets — pour comparer
    « SW-Motech », « sw motech » et « swmotech » comme un seul mot."""
    plat = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in plat
                   if unicodedata.category(c) != "Mn" and c.isalnum())


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


# The owner's merchant order, the same one `product_stats` uses to pick a title
# (sql/009). Editorial, not technical: it decides which wording a visitor reads
# first when several are equally true.
MARCHANDS_ORDRE = {
    "motoblouz": 1, "speedway": 2, "labecanerie": 3,
    "fcmoto": 4, "maxxess": 5,
}


def equivalences_tailles(rows: list[dict]) -> dict[str, str]:
    """Size labels the barcode proves are the same size, merged into one.

    Four merchants sell the same Helstons Swallow gloves on the same four
    barcodes, and name the sizes `6 7 8 9`, `T6 T7 T8 T9` and `XS S M L`. The
    page offered eight filter buttons for four real sizes: clicking `6` hid
    Speedway, clicking `XS` hid everyone else, and the comparison — the only
    thing the site is for — stopped working.

    The barcode is the authority (the owner's rule: sizes are never decided by
    guessing, only by what another merchant says about the same barcode). Two
    labels on one barcode are therefore one size, shown as `XS / 6`.

    Returns {label: merged label}; a label nothing merges with maps to itself.

    Two guards:

    - **Parent barcodes.** A merchant carrying several sizes under one barcode
      is using a code that covers a range, so that barcode proves nothing about
      sizes and is skipped entirely. Without this, one parent code would fuse
      `S`, `M` and `L` into a single button — the exact opposite of the fix.
    - **Two labels at most**, in merchant order, per the owner's rule: beyond
      two the button stops being readable and the extra wordings add nothing.
    """
    par_gtin: dict[str, dict[str, set[str]]] = {}
    priorite: dict[str, int] = {}

    for o in rows:
        etiquette = size_display(o.get("size_code"))
        if not etiquette:
            continue
        rang = MARCHANDS_ORDRE.get(o.get("merchant", ""), 9)
        priorite[etiquette] = min(priorite.get(etiquette, 99), rang)
        if gtin := o.get("gtin"):
            par_gtin.setdefault(gtin, {}).setdefault(o["merchant"], set()).add(etiquette)

    parent: dict[str, str] = {e: e for e in priorite}

    def racine(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for par_marchand in par_gtin.values():
        if any(len(v) > 1 for v in par_marchand.values()):
            continue  # code-barres parent : ne prouve rien
        etiquettes = sorted({e for v in par_marchand.values() for e in v})
        for autre in etiquettes[1:]:
            a, b = racine(etiquettes[0]), racine(autre)
            if a != b:
                parent[b] = a

    classes: dict[str, set[str]] = {}
    for e in parent:
        classes.setdefault(racine(e), set()).add(e)

    fusion: dict[str, str] = {}
    for membres in classes.values():
        ordonne = sorted(membres, key=lambda e: (priorite[e], size_key(e)))
        etiquette = " / ".join(ordonne[:2])
        fusion.update(dict.fromkeys(membres, etiquette))
    return fusion


# --- le niveau d'une remise -------------------------------------------------
#
# Demandé par la propriétaire le 17/09/2026 : montrer d'un coup d'œil qu'une
# affaire est bonne. Trois paliers, ses valeurs :
#
#   0 – 20 %   sobre    l'écart existe, il n'est pas remarquable
#   20 – 35 %  orange   l'écart mérite d'être vu
#   plus de 35 % rouge  l'écart est le vrai sujet de la page
#
# Ces bornes sont écrites ICI et nulle part ailleurs. La page les rend une
# première fois côté serveur, puis le script les recalcule à chaque choix de
# taille : deux copies de la même règle finiraient par diverger, et c'est la
# couleur — donc la promesse faite au visiteur — qui se tromperait.
SEUILS_REMISE = (20, 35)


def niveau_remise(pourcentage: float | None) -> str:
    """« sobre », « orange » ou « rouge » selon l'ampleur de l'écart."""
    if pourcentage is None:
        return ""
    bas, haut = SEUILS_REMISE
    if pourcentage > haut:
        return "rouge"
    if pourcentage >= bas:
        return "orange"
    return "sobre"
