"""Stage — read the merchants' own promo pages and keep `code_promo` current.

This is a port of the v1 WordPress snippet "MC Codes Promo v1", which ran daily
on the old site. Its history matters, because it explains the design:

  * The snippet first pulled codes from the affiliate platforms' APIs (Effinity,
    Kwanko). That code is still in the v1 file but is **no longer called** — the
    platforms served last month's codes. The scheduled job ends up calling one
    single function, `mc_promo_scan_sites()`.
  * What replaced it reads the merchant's OWN public promo page — the same page
    a customer would open — strips the HTML to plain text, and looks for a code
    in that text.

So a code is only ever as good as what the merchant publishes about it, and the
whole difficulty is telling a real code from the uppercase noise on a shop page
("LIVRAISON", "NOUVEAUTE", "CGV"). The v1 answered that with a scored pattern
list plus a blacklist, and both are reproduced here as measured, not improved:
the blacklist in particular is the residue of a year of false positives on these
exact six sites.

Scope, deliberately: only the merchant's public promo pages, once a day. Never an
affiliate deeplink — following those at any volume is click fraud and closes the
account.
"""

from __future__ import annotations

import html as _html
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta

import httpx

from .db import connect

# --- where to look -----------------------------------------------------------
#
# Taken from the v1 snippet, merchant by merchant. The first URL of each list is
# the dedicated promo page; the home page follows as a fallback, because several
# of these shops announce the month's code in a banner and nowhere else.
#
# FC-Moto is absent: it was absent from the v1 too (a German site with no French
# promo page). Adding one here is all it takes for it to be scanned.
PAGES: dict[str, tuple[str, ...]] = {
    "motoblouz": (
        "https://www.motoblouz.com/code-promo-motoblouz.html",
        "https://www.motoblouz.com/",
    ),
    # La Bécanerie sits behind Cloudflare, which refuses this machine outright —
    # even its robots.txt comes back 403. That is a protection the shop chose,
    # so it is not worked around: its codes are typed in the admin screen
    # instead (`source = 'manuel'`, which no scan ever overwrites). Worth
    # retrying from the server the pipeline will run on: the v1 read this page
    # fine from the Hostinger machine, so the block may be on this IP only.
    "labecanerie": (
        "https://www.la-becanerie.com/code-promo.html",
        "https://www.la-becanerie.com/offre-en-cours.html",
        "https://www.la-becanerie.com/",
    ),
    "maxxess": (
        "https://www.maxxess.fr/blog/code-promo-maxxess/",
        "https://www.maxxess.fr/",
    ),
    "motoaxxe": (
        # the v1's URL (/blog/code-promo-moto-axxe/) now 404s — the shop moved
        # its offers to /bons-plans/, still linked from its own home page.
        "https://www.moto-axxe.fr/bons-plans/",
        "https://www.moto-axxe.fr/",
    ),
    "speedway": (
        "https://www.speedway.fr/code-promo",
        "https://www.speedway.fr/",
    ),
}

# A code with no readable end date is kept on a short leash: two weeks, pushed
# back at every scan that still finds it on the page. A code that disappears
# therefore stops being served within a fortnight even if nothing else notices.
DEFAULT_WINDOW = timedelta(days=14)

# Aucune date lue n'est acceptée au-delà de cet horizon. Un « jusqu'au 3 février »
# sans année, lu sur une bannière oubliée depuis dix mois, devient sinon une date
# à onze mois : le code paraît vivant pour un an. Au-delà de six mois on préfère
# ne pas savoir — l'échéance courte reprend la main, et elle est révisée chaque
# jour. (Vérifié : la seule date longue observée, le 14/02/2027 de Motoblouz, est
# écrite telle quelle par le marchand avec son année, donc lue et non devinée.)
HORIZON_MAX = timedelta(days=210)

_TIMEOUT = httpx.Timeout(connect=10.0, read=25.0, write=10.0, pool=10.0)

# A shop that serves a bot-detection page serves no promo code either. The v1
# sent a full browser header set; same here, minus the client hints that only
# make sense from a real Chrome.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}

# --- what a code looks like --------------------------------------------------
#
# Scored: a code introduced by "avec le code" is worth far more than a bare
# "CODE XYZ", because the second also matches "CODE POSTAL". When the same code
# is seen twice, the best-scored reading wins — it carries the better context,
# and the context is what the date and the wording are read from.
_PATTERNS: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"\bCODE\s+([A-Z][A-Z0-9]{3,19})\s*[-–—]?\s*ACTIF\b", re.I), 50),
    (re.compile(r"\bAVEC\s+LE\s+CODE\s*(?:PROMO)?\s*:?\s*([A-Z][A-Z0-9]{3,19})\b", re.I), 40),
    (re.compile(r"\bCODE\s+PROMO\s*:?\s*([A-Z][A-Z0-9]{3,19})\b", re.I), 30),
    (re.compile(r"\bCODE\s*:\s*([A-Z][A-Z0-9]{3,19})\b", re.I), 25),
    (re.compile(
        r"\b(?:saisis|saisissez|utilise|utilisez|entrez|renseignez)\s+le\s+code"
        r"\s*:?\s*([A-Z][A-Z0-9]{3,19})\b", re.I), 25),
    (re.compile(r"\bCODE\s+([A-Z][A-Z0-9]{3,19})\b"), 10),
)

# Ordinary French words that a shop writes in capitals next to the word "code".
# Every entry here was a false positive on one of these five sites.
_BLACKLIST = frozenset("""
PROMO PROMOS PROMOTION PROMOTIONS PROMOTIONNEL PROMOTIONNELS CODES CODE
REDUC REDUCTION REDUCTIONS REMISE REMISES ACTIF ACTIVE INACTIF VALABLE
CLIENT CLIENTS POSTAL POSTALE CADEAU CADEAUX ACHAT ACHATS PANIER COMMANDE
LIVRAISON GRATUIT GRATUITE OFFERT OFFERTS OFFRE OFFRES SOLDES DESTOCKAGE
MOTO MOTOS CASQUE CASQUES BLOUSON GANTS BOTTES EQUIPEMENT EQUIPEMENTS
MERCI AVEC SANS TOUT TOUTE TOUTES TOUS VOTRE NOTRE DANS POUR LORS
ETRE BIEN PLUS SEUL SEULE FOIS JOUR JOURS SEMAINE MOIS ANNEE SAISON
MAGASIN MAGASINS SERVICE CONTACT NEWSLETTER SUIVANT SUIVANTS SUIVANTE
DETAIL DETAILS CONDITION CONDITIONS UTILISATION BARRE BARRES TVA CGV
FRAIS TOTAL PRIX EUROS PARTIR CUMULABLE MARQUE MARQUES SELECTION
""".split())

_VALID = re.compile(r"^[A-Z][A-Z0-9]{3,19}$")

_MONTHS = {
    "janvier": 1, "janv": 1, "fevrier": 2, "fev": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "juil": 7, "aout": 8, "septembre": 9,
    "sept": 9, "octobre": 10, "oct": 10, "novembre": 11, "nov": 11,
    "decembre": 12, "dec": 12,
}


@dataclass
class Hit:
    """One code read on one page, with the text that surrounded it."""

    code: str
    score: int
    context: str       # ~900 characters around the code: dates, conditions
    near: str          # ~260 characters: what gets shown as the description
    url: str
    at: int = 0        # where the code sits inside `context` — see `window`


@dataclass
class StoreReport:
    merchant: str
    pages: list[str] = field(default_factory=list)   # "url -> HTTP 200 (48 231 car.)"
    kept: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)


# --- text ---------------------------------------------------------------------

def _flatten(s: str) -> str:
    """Accent-free lowercase, punctuation reduced to spaces — for date matching."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Za-z0-9 %./:-]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def to_text(html: str) -> str:
    """HTML -> readable text, block ends turned into spaces.

    Scripts and styles go first: a shop's JSON payloads are full of uppercase
    tokens that read exactly like promo codes.
    """
    html = re.sub(r"<(script|style|noscript|svg)\b[^>]*>.*?</\1>", " ", html,
                  flags=re.I | re.S)
    html = re.sub(r"<br\s*/?>", " | ", html, flags=re.I)
    html = re.sub(r"</(p|div|li|td|th|h[1-6]|span|a)>", " | ", html, flags=re.I)
    txt = re.sub(r"<[^>]+>", " ", html)
    txt = _html.unescape(txt)
    txt = txt.replace("\xa0", " ").replace("|", " ")
    return re.sub(r"\s+", " ", txt).strip()


def fetch_text(url: str, client: httpx.Client | None = None) -> tuple[str, str]:
    """Download one page. Returns `(text, message)`; text is '' on failure.

    A failure is reported, never raised: one shop being down must not stop the
    other four from being read.
    """
    own = client is None
    client = client or httpx.Client(timeout=_TIMEOUT, follow_redirects=True,
                                    headers=_HEADERS)
    try:
        r = client.get(url)
        if r.status_code >= 400 or not r.text:
            return "", f"HTTP {r.status_code}"
        txt = to_text(r.text)
        return txt, f"HTTP {r.status_code} ({len(txt):,} car.)".replace(",", " ")
    except httpx.HTTPError as exc:
        return "", f"ERR {type(exc).__name__}"
    finally:
        if own:
            client.close()


# --- reading a code out of the text -------------------------------------------

def find_codes(text: str, url: str = "") -> dict[str, Hit]:
    """Every plausible promo code in one page's text, best reading per code."""
    found: dict[str, Hit] = {}
    for pattern, score in _PATTERNS:
        for m in pattern.finditer(text):
            code = m.group(1).strip()
            off = m.start(1)
            if not _VALID.match(code) or code in _BLACKLIST:
                continue
            # A short all-letter token is a word, not a code. With a digit in it
            # ("SPEED15"), four characters are enough.
            if not any(c.isdigit() for c in code) and len(code) < 6:
                continue
            if code.isdigit():
                continue
            # "CODE PROMO XYZ INACTIF" — the page says so itself.
            if "INACTIF" in text[off:off + 40].upper():
                continue
            # On the weak patterns only: if the capitals keep running after the
            # match, we are inside a heading, not reading a code.
            if score < 40:
                tail = text[off + len(code):off + len(code) + 20]
                if re.match(r"^\s+[A-ZÀ-Ý]", tail):
                    continue
            context = text[max(0, off - 260):off + 640]
            if re.search(r"OFFRE\s+TERMIN", context, re.I):
                continue
            near = text[max(0, off - 90):off + 170]
            # Welcome / newsletter / referral codes are not comparison-shopping
            # offers: they need an account or a first order, so showing them on
            # a product page is a promise we cannot keep.
            if re.search(r"newsletter|inscription|inscris|inscrivant|parrainage"
                         r"|parrain|bienvenue|premi[eè]re commande", near, re.I):
                continue
            if code not in found or found[code].score < score:
                found[code] = Hit(code, score, context, near, url,
                                  at=off - max(0, off - 260))
    return found


# Weekday and "1er" sit between "du" and the day number on real pages:
# "du Mardi 23 Juin 2026", "du 1er septembre". Both are noise to skip over.
_WD = r"(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)?\s*"
_D = r"(\d{1,2})(?:er)?"
_UNTIL = r"jusqu.{0,4}au\b\s*:?\s*"

_WHEN: tuple[tuple[re.Pattern[str], str], ...] = (
    # A full range first: it states both ends and needs no assumption.
    (re.compile(rf"du\s+{_WD}(\d{{1,2}})[/.-](\d{{1,2}})[/.-](\d{{2,4}})"
                rf".{{0,20}}?au\s+{_WD}(\d{{1,2}})[/.-](\d{{1,2}})[/.-](\d{{2,4}})"), "range_num"),
    (re.compile(rf"du\s+{_WD}{_D}\s+([a-z]{{3,9}})(?:\s+(\d{{4}}))?"
                rf".{{0,40}}?\bau\s+{_WD}{_D}\s+([a-z]{{3,9}})(?:\s+(\d{{4}}))?"), "range_txt"),
    # Then an end date alone. The ISO form is Speedway's: "jusqu'au : 2026-03-18".
    (re.compile(rf"{_UNTIL}(\d{{4}})-(\d{{1,2}})-(\d{{1,2}})"), "until_iso"),
    (re.compile(rf"{_UNTIL}(\d{{1,2}})[/.-](\d{{1,2}})[/.-](\d{{2,4}})"), "until_num"),
    (re.compile(rf"{_UNTIL}{_WD}{_D}\s+([a-z]{{3,9}})(?:\s+(\d{{4}}))?"), "until_txt"),
)


def window(context: str, today: date | None = None,
           at: int | None = None) -> tuple[date | None, date | None]:
    """`(start, end)` for the code sitting at `at` in `context`; either may be None.

    The nearest date wins, and that is the whole point. A promo page is a LIST:
    Speedway's carries a dozen past operations, each written
    "… valable jusqu'au : 2026-03-18 … Avec le code SPEED15". Reading the first
    date in the page — what the v1 did — hands every code the date of whichever
    offer happens to be printed at the top, and a code whose own date has passed
    then looks live. Measured on that page today: every one of its dates is in
    the past, so the honest answer is that Speedway has no current code, and the
    v1 was showing a March code in September.

    `at` defaults to the middle, where `find_codes` puts the code.
    """
    today = today or date.today()
    # Offsets must be comparable, so the anchor is measured in the same
    # flattened text the patterns are matched against.
    anchor = len(_flatten(context[:at])) if at is not None else len(_flatten(context)) // 2
    f = _flatten(context)

    best: tuple[int, int, date | None, date | None] | None = None
    for rank, (pattern, kind) in enumerate(_WHEN):
        for m in pattern.finditer(f):
            pair = _read_when(m, kind, today)
            if pair is None or (pair[0] is None and pair[1] is None):
                continue
            key = (abs(m.start() - anchor), rank, *pair)
            if best is None or key[:2] < best[:2]:
                best = key  # type: ignore[assignment]
    return (best[2], best[3]) if best else (None, None)


def _read_when(m: re.Match[str], kind: str, today: date
               ) -> tuple[date | None, date | None] | None:
    if kind == "range_num":
        y1, y2 = int(m[3]), int(m[6])
        y1 += 2000 if y1 < 100 else 0
        y2 += 2000 if y2 < 100 else 0
        return _safe(y1, int(m[2]), int(m[1])), _safe(y2, int(m[5]), int(m[4]))

    if kind == "range_txt":
        m1, m2 = _MONTHS.get(m[2], 0), _MONTHS.get(m[5], 0)
        if not (m1 and m2):
            return None
        start = _safe(int(m[3]) if m[3] else today.year, m1, int(m[1]))
        end = _safe(int(m[6]) if m[6] else (int(m[3]) if m[3] else today.year),
                    m2, int(m[4]))
        # "du 20 décembre au 5 janvier" straddles the new year.
        if start and end and end < start and not m[6]:
            end = _safe(end.year + 1, m2, int(m[4]))
        return start, end

    if kind == "until_iso":
        return None, _safe(int(m[1]), int(m[2]), int(m[3]))

    if kind == "until_num":
        y = int(m[3])
        y += 2000 if y < 100 else 0
        return None, _safe(y, int(m[2]), int(m[1]))

    if kind == "until_txt":
        mo = _MONTHS.get(m[2], 0)
        if not mo:
            return None
        if m[3]:
            return None, _safe(int(m[3]), mo, int(m[1]))
        end = _safe(today.year, mo, int(m[1]))
        # No year written: a date already behind us meant the next one — mais
        # seulement si le résultat reste dans un horizon plausible, sinon on
        # aurait fabriqué une validité d'un an à partir d'une page périmée.
        if end and end < today:
            report = _safe(today.year + 1, mo, int(m[1]))
            end = report if report and report <= today + HORIZON_MAX else None
        return None, end

    return None


def _safe(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:      # "31 septembre" happens on real pages
        return None


def label(context: str, code: str) -> str:
    """« -20 % avec le code ROULEZ20 » — the discount if the page states one."""
    value = ""
    m = re.search(r"-\s?(\d{1,2})\s?%", context)
    if m:
        value = f"-{m[1]} %"
    else:
        m = re.search(r"(\d{1,2})\s?%\s?(?:de\s+)?(?:remise|r[ée]duction)", context, re.I)
        if m:
            value = f"-{m[1]} %"
        else:
            m = re.search(r"(\d{1,3})\s?(?:€|EUR)\s+(?:offerts?|de\s+remise"
                          r"|de\s+r[ée]duction)", context, re.I)
            if m:
                value = f"{m[1]} € de remise"
    return f"{value} avec le code {code}" if value else f"Code promo {code}"


def conditions(context: str) -> str:
    """« dès 79 € d'achat · hors soldes · non cumulable ».

    The three that actually decide whether the visitor gets the discount. A code
    shown without its minimum order is a code refused at checkout.
    """
    out: list[str] = []
    m = re.search(r"(?:dès|à\s+partir\s+de|minimum(?:\s+d'achat)?(?:\s+de)?"
                  r"|commande\s+minimum(?:\s+de)?)\s*(\d+(?:[.,]\d+)?)\s*(?:€|EUR)",
                  context, re.I)
    if m:
        out.append(f"dès {m[1].replace('.', ',')} € d'achat")
    m = re.search(r"hors\s+(soldes|promos?|promotions?|articles?\s+déjà\s+remisés?)",
                  context, re.I)
    if m:
        out.append(f"hors {m[1].lower()}")
    if re.search(r"non\s+cumulable", context, re.I):
        out.append("non cumulable")
    return " · ".join(out)


# --- the scan itself ----------------------------------------------------------

def scan(pages: dict[str, tuple[str, ...]] | None = None) -> list[StoreReport]:
    """Read every merchant page, write what was found, retire what vanished.

    Only rows with `source = 'site'` are ever touched: a code the owner typed in
    the admin screen outranks the automate, always. Codes no longer found are
    withdrawn (`retire_le`), never deleted — which code ran when is worth
    keeping.
    """
    pages = pages or PAGES
    reports: list[StoreReport] = []
    today = date.today()

    with connect() as conn:
        ids = {row[0]: row[1] for row in
               conn.execute("SELECT code, id FROM merchant")}
        seen_ids: list[int] = []
        lus: list[int] = []          # marchands dont au moins une page a répondu

        with httpx.Client(timeout=_TIMEOUT, follow_redirects=True,
                          headers=_HEADERS) as client:
            for merchant, urls in pages.items():
                rep = StoreReport(merchant)
                if merchant not in ids:
                    rep.ignored.append("marchand inconnu en base")
                    reports.append(rep)
                    continue

                best: dict[str, Hit] = {}
                lisible = False
                for url in urls:
                    text, msg = fetch_text(url, client)
                    rep.pages.append(f"{re.sub(r'^https?://', '', url)} -> {msg}")
                    if not text:
                        continue
                    lisible = True
                    for code, hit in find_codes(text, url).items():
                        if code not in best or best[code].score < hit.score:
                            best[code] = hit

                for code, hit in best.items():
                    start, end = window(hit.context, today, hit.at)
                    if end and end < today:
                        rep.ignored.append(f"{code} (expiré le {end:%d/%m/%Y})")
                        continue
                    row_id = _upsert(conn, ids[merchant], code, hit, start, end, today)
                    if row_id is None:
                        # `_upsert` ne renvoie rien quand la ligne est passée en
                        # `manuel` : le code est bien sur la page, mais il a été
                        # repris à la main et l'automate n'y touche plus. Le dire,
                        # plutôt que d'annoncer « gardé » pour une ligne qu'on n'a
                        # pas écrite.
                        rep.ignored.append(f"{code} (repris à la main, laissé tel quel)")
                        continue
                    if row_id:
                        seen_ids.append(row_id)
                    rep.kept.append(
                        f"{code}" + (f" (jusqu'au {end:%d/%m/%Y})" if end else
                                     f" (échéance courte au {(today + DEFAULT_WINDOW):%d/%m/%Y})")
                    )
                if lisible:
                    lus.append(ids[merchant])
                else:
                    rep.ignored.append("aucune page lisible — codes conservés")
                reports.append(rep)

        _retire_missing(conn, seen_ids, lus)
        conn.commit()
    return reports


def _upsert(conn, merchant_id: int, code: str, hit: Hit,
            start: date | None, end: date | None, today: date) -> int | None:
    """Insert or refresh one scanned code. Returns its id.

    Deux garde-fous, et les deux ont été écrits après coup, chacun pour une
    façon précise dont un code faux atteignait une fiche :

    1. `WHERE source = 'site'` — une ligne saisie ou reprise à la main n'est
       jamais réécrite par l'automate. Retirer un code à l'admin le bascule en
       `manuel` (voir `/admin/code-promo`), sans quoi le relevé du lendemain
       remettait `retire_le` à NULL et le code revenait.
    2. `fin_estimee` — une échéance LUE sur la page n'est jamais remplacée par
       l'échéance de secours de quatorze jours. Sans ça, un marchand qui retire
       la date de sa bannière repoussait son code d'un jour chaque jour, et le
       code ne mourait plus.
    """
    row = conn.execute("""
        INSERT INTO code_promo (merchant_id, code, libelle, url, source,
                                debut_le, fin_le, fin_estimee, conditions,
                                contexte, vu_le, retire_le)
        VALUES (%(m)s, %(c)s, %(lib)s, %(url)s, 'site',
                coalesce(%(deb)s, current_date), %(fin)s, %(estimee)s,
                nullif(%(cond)s, ''), %(ctx)s, now(), NULL)
        ON CONFLICT (merchant_id, code) DO UPDATE
           -- the start never moves forward: a code first seen without its
           -- start date, then read again once the page states it, should
           -- learn the real one — not today's.
           SET debut_le   = least(code_promo.debut_le, excluded.debut_le),
               libelle    = excluded.libelle,
               url        = excluded.url,
               -- une date devinée ne remplace jamais une date lue
               fin_le     = CASE WHEN excluded.fin_estimee AND NOT code_promo.fin_estimee
                                 THEN code_promo.fin_le ELSE excluded.fin_le END,
               fin_estimee = CASE WHEN excluded.fin_estimee AND NOT code_promo.fin_estimee
                                  THEN false ELSE excluded.fin_estimee END,
               conditions = excluded.conditions,
               contexte   = excluded.contexte,
               vu_le      = now(),
               retire_le  = NULL
         WHERE code_promo.source = 'site'
        RETURNING id
    """, {
        "m": merchant_id, "c": code,
        "lib": label(hit.context, code), "url": hit.url,
        "deb": start, "fin": end or (today + DEFAULT_WINDOW),
        "estimee": end is None,
        "cond": conditions(hit.context), "ctx": hit.context[:1000],
    }).fetchone()
    return row[0] if row else None


def _retire_missing(conn, seen_ids: list[int], marchands_lus: list[int]) -> int:
    """Withdraw every scanned code that was not on the pages this time.

    A merchant who ends an operation simply removes the banner: nothing says
    "expired", the code just stops being mentioned. Disappearing from the page
    is therefore the only end-of-life signal most of these codes ever get.

    D'où `marchands_lus` : le retrait ne vaut que pour les marchands dont au
    moins une page a répondu. Sans cette restriction, un 403 ou un délai
    d'attente — La Bécanerie en renvoie trois par relevé — retirait tous les
    codes d'un marchand qui les affiche toujours. « Je n'ai pas pu lire » n'est
    pas « ce n'est plus là ».
    """
    if not marchands_lus:
        return 0
    return conn.execute("""
        UPDATE code_promo SET retire_le = now()
        WHERE source = 'site' AND retire_le IS NULL
          AND merchant_id = ANY(%s)
          AND NOT (id = ANY(%s))
    """, (marchands_lus, seen_ids or [0])).rowcount
