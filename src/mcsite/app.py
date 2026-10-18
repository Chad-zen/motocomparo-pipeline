"""The site: routes, and nothing else.

Runs anywhere Python and PostgreSQL run — a laptop today, the VPS tomorrow. It
does not need WordPress, WooCommerce, or a copy of the catalogue: it reads the
pipeline's database directly, which is why there is no `publish` step between
the two and no window during which the site shows yesterday's data.
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager, contextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlencode

import psycopg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from psycopg_pool import ConnectionPool, PoolTimeout
from starlette.exceptions import HTTPException as StarletteHTTPException

from functools import lru_cache

from . import admin, cache, labels, partenaires, queries, seo, suggestions
from . import v1 as v1_mod
from . import articles as articles_mod
from . import courbe as courbe_mod

log = logging.getLogger("mcsite")

load_dotenv()

HERE = Path(__file__).parent
PER_PAGE = 24
# Au-delà, une page n'a plus de sens (le catalogue entier en fait ~13 000) et
# `?page=999999999999999999999` faisait déborder l'OFFSET après 53 s de
# requêtes. Les prix, eux, sont bornés à 100 000 € : `?prix_min=inf` levait
# une erreur 500 brute au rendu.
_PAGE_MAX = 15_000

pool: ConnectionPool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (check .env)")
    # small pool: this is a read-only site, and the box also runs the pipeline
    #
    # `timeout=5` : quand les six connexions sont prises, un visiteur attendait
    # 30 s puis recevait une erreur brute. Mieux vaut une page « réessayez »
    # tout de suite (voir `erreur_pool`). `statement_timeout` empêche une seule
    # requête de facettes emballée de garder une connexion vingt secondes.
    pool = ConnectionPool(
        url, min_size=1, max_size=6, timeout=5,
        kwargs={"autocommit": True, "options": "-c statement_timeout=15000"})
    pool.wait(timeout=10)
    yield
    pool.close()


# Pas de /docs, /redoc ni /openapi.json : ils listaient toutes les routes, dont
# celles du tableau de bord, à n'importe quel visiteur.
app = FastAPI(title="motocomparo v2", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["prix"] = labels.price
templates.env.filters["couleur"] = labels.colour
templates.env.filters["genre"] = labels.genre
templates.env.filters["marchand"] = labels.merchant
templates.env.filters["marque"] = labels.brand
templates.env.filters["caracteristique"] = queries._valeur_lisible
templates.env.filters["taille"] = labels.size_display
templates.env.globals["titre_produit"] = labels.product_title


from mcpipe import alertes as alertes_prix  # noqa: E402
from mcpipe import courriel  # noqa: E402
from mcpipe.category import CATEGORIES as _CATEGORIES  # noqa: E402

# 25 (« non classé ») n'apprend rien au visiteur : pas de libellé.
_LIBELLE_RAYON = {cid: libelle for cid, _p, _c, libelle in _CATEGORIES if cid != 25}


def _nom(row: Any) -> str:
    """The product name: one merchant's own title, verbatim.

    The owner's decision (2026-09-13): show what the merchants wrote, not a name
    rebuilt from it. Which merchant is her order too — Motoblouz, then Speedway,
    La Bécanerie, FC-Moto — and it is applied in `product_stats.best_title`.

    Nothing is stripped here. An earlier version removed the brand, the colour
    and the category noun; it read better on some pages and mangled others
    ("Cuir Swallow T7"), and a title the merchant wrote is at least a title a
    human wrote. `model_display` remains the fallback for a product with no
    usable title at all — it is a fingerprint, so it should show as rarely as
    possible.
    """
    titre = (row.get("best_title") or "").strip()
    # Une seule chose est retirée : une taille collée en fin de titre. Elle
    # annonce « M » sur une fiche qui en compare quatre, ce qui est faux avant
    # même que le visiteur lise le tableau. Voir `labels.sans_taille_finale` —
    # la règle est étroite exprès.
    if not titre:
        # Le repli seul donnait des cartes titrées « V24 » ou « 300i » : un
        # code modèle, sans dire s'il s'agit d'un casque ou d'un pot. Le rayon
        # le dit (audit du 30/09/2026).
        rayon = _LIBELLE_RAYON.get(row.get("category_id")) if hasattr(row, "get") else None
        return f"{row['model_display']} ({rayon})" if rayon else row["model_display"]
    # Deux retraits, et deux seulement. Chacun enlève une chose qui n'apprend
    # rien ou qui ment ; aucun ne touche au nom du produit lui-même.
    titre = labels.sans_queue_de_rayon(titre, row.get("brand_code") or "")
    return labels.sans_taille_finale(titre)


templates.env.globals["nom"] = _nom


def _a_completer(indice: str) -> str:
    """Pose un repère visible « À COMPLÉTER PAR LA PROPRIÉTAIRE » dans un
    article en chantier, avec l'indice de ce qui manque (un essai porté, une
    impression de confort…).

    Cherché comme TEXTE par `articles.lire` (voir `_TROU`) : tant qu'un
    article en contient un, il reste un brouillon même si son en-tête dit
    « publié », et un brouillon ne sort jamais du mode aperçu (`BLOG_APERCU`).
    Cette fonction ne rend donc en pratique que sur une page déjà fermée au
    public — elle peut se permettre d'être explicite.
    """
    from markupsafe import Markup, escape
    return Markup(f'<p class="alerte alerte--attention a-completer">'
                  f'À COMPLÉTER PAR LA PROPRIÉTAIRE — {escape(indice)}</p>')


templates.env.globals["a_completer"] = _a_completer


def _version_css() -> int:
    """Timestamp of the newest file in `static/`, appended to every asset URL.

    Without it a browser keeps the copy it already has, and a phone is the one
    place where clearing that cache by hand is genuinely awkward.

    It watches the whole directory, not one file. Tracking `style.css` alone
    meant editing `v1.css` left the number unchanged, so phones kept serving the
    stylesheet from before the logo had a size rule — and rendered a 595-pixel
    logo. A cache-buster that misses a file is worse than none, because the bug
    it produces looks like a design mistake.

    `rglob`, not `iterdir` — the docstring above already promised "the whole
    directory", but `iterdir` only lists `static/`'s DIRECT children, not
    `static/marchands/` or `static/polices/`. A logo re-cropped in place
    (29/09/2026, `motoblouz.webp`, trimmed of the transparent margin that made
    it render smaller than the other five) would have kept the same URL and
    the same cached copy on every phone that had already loaded it — the exact
    failure this function exists to prevent, just one directory level down
    from where it was being watched.
    """
    try:
        return max(
            int(f.stat().st_mtime)
            for f in (HERE / "static").rglob("*") if f.is_file()
        )
    except (OSError, ValueError):
        return 0


templates.env.globals["version_css"] = _version_css


_CSS_MINIFIE_CACHE: dict[str, tuple[float, str]] = {}


def _minifier_css(source: str) -> str:
    """Retire les commentaires et les espaces superflus, sans toucher au fichier
    source : celui-ci reste le seul lu et édité, celui-ci est le seul envoyé.

    Les commentaires de ce dépôt documentent des décisions au prix de
    kilooctets de prose — précieux à lire, coûteux à transmettre sur chaque
    page. Mesuré le 29/09/2026 (PageSpeed Insights, mobile, 67/100) : la
    version gzippée passe de 49,5 Ko à 16,6 Ko une fois retirés — l'essentiel
    du gain vient d'eux, pas des espaces, parce qu'un commentaire en prose
    compresse moins bien qu'une règle CSS répétitive.
    """
    sans_commentaires = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    compact = re.sub(r"\s+", " ", sans_commentaires)
    compact = re.sub(r"\s*([{};:,])\s*", r"\1", compact)
    compact = re.sub(r";}", "}", compact)
    return compact.strip()


@app.get("/css/style.min.css")
def style_minifie() -> Response:
    """Le CSS du site, sans ses commentaires — voir `_minifier_css`.

    Calculé EN MÉMOIRE à partir de `static/style.css` et mis en cache tant
    que le fichier n'a pas changé (même mesure que `version_css`, `st_mtime`) :
    rien n'est jamais écrit sur le disque, donc rien ne peut diverger entre
    une source éditée et une copie minifiée qu'on aurait oublié de refaire.

    Hors de `/static/`, exprès : ce chemin est monté en `StaticFiles` plus
    haut, qui répondrait 404 avant même d'atteindre cette route.
    """
    chemin = HERE / "static" / "style.css"
    mtime = chemin.stat().st_mtime
    entree = _CSS_MINIFIE_CACHE.get("style.css")
    if entree is None or entree[0] != mtime:
        entree = (mtime, _minifier_css(chemin.read_text(encoding="utf-8")))
        _CSS_MINIFIE_CACHE["style.css"] = entree
    return Response(
        entree[1], media_type="text/css",
        headers={"Cache-Control": "public, max-age=31536000, immutable"})


def _statique_existe(nom: str) -> bool:
    """`static/<nom>` est-il présent sur le disque ?

    Sert à ne proposer une image que si elle a été déposée. Un `<source>` qui
    pointe vers un fichier absent n'est pas un détail cosmétique : le navigateur
    choisit la source AVANT de la télécharger, et s'il retient celle-là, il
    n'affiche pas l'image de repli — il n'affiche rien du tout. L'affiche
    disparaîtrait de l'accueil, en desktop uniquement.

    Lu à chaque rendu, pas au démarrage : l'affiche paysage peut être déposée
    sans redémarrer le service, et la page d'accueil est de toute façon gardée
    en cache.
    """
    try:
        return (HERE / "static" / nom).is_file()
    except OSError:
        return False


templates.env.globals["statique_existe"] = _statique_existe


_LOGO_EXTENSIONS = ("svg", "webp", "png")


def _logo_marchand(code: str) -> str:
    """`static/marchands/<code>.<ext>` s'il existe, chemin relatif ou "".

    Reprend la boucle d'extensions écrite pour la bande de logos de l'accueil
    (`home_base.html`) au lieu de la copier une troisième fois dans `_fiche.html` —
    le bandeau « meilleur prix », le tableau des offres et les blocs code
    promo en avaient chacun besoin. Le fichier est pris TEL QUE le marchand le
    publie, sans conversion : trois de ces logos n'existent qu'en WebP.
    """
    for ext in _LOGO_EXTENSIONS:
        nom = f"marchands/{code}.{ext}"
        if _statique_existe(nom):
            return nom
    return ""


templates.env.globals["logo_marchand"] = _logo_marchand

# Largeur / hauteur de chaque logo marchand : sans `width` et `height`, le
# navigateur ne reserve pas la place et la page bouge quand l'image arrive
# (PageSpeed, 17/10/2026 : CLS 0,104 pour un seuil a 0,1). Mesures sur les
# fichiers de `static/marchands/` ; un marchand absent d'ici n'a pas de
# largeur declaree, rien ne casse.
_RATIO_LOGOS = {"fcmoto": 3.75, "motoblouz": 4.22, "speedway": 5.817,
                "motoaxxe": 8.824, "labecanerie": 5.437, "maxxess": 6.915}


def _logo_largeur(code: str, hauteur: int = 26) -> int:
    """Largeur en px d'un logo marchand affiche a `hauteur` px de haut, ou 0."""
    ratio = _RATIO_LOGOS.get(code)
    return round(hauteur * ratio) if ratio else 0


templates.env.globals["logo_largeur"] = _logo_largeur


def _remise_carte(it: dict) -> dict | None:
    """L'ecart en pourcentage entre le marchand le moins cher et le plus cher, pour
    une carte de la boutique, avec le palier de couleur de la fiche.

    MEME formule que la fiche produit (`round((1 - min / max) * 100)`) et memes
    seuils (`labels.SEUILS_REMISE`) : une carte qui annoncerait −30 % pendant que
    la fiche en dit −25 serait une promesse que la page suivante dement. Rien
    n'est annonce sous 1 % (« −0 % » a cote d'un prix, releve le 16/10/2026) ni
    pour une fiche qui n'a qu'un marchand : il n'y a alors rien a comparer.
    Le plafond de 50 % a ete retire le 17/10/2026, a la demande de Sofia.
    """
    bas, haut = it.get("cheapest"), it.get("dearest")
    if not bas or not haut or (it.get("merchant_count") or 0) < 2 or haut <= bas:
        return None
    pct = round((1 - bas / haut) * 100)
    if pct < 1:
        return None
    return {"pct": pct, "niveau": labels.niveau_remise(pct)}


templates.env.globals["remise_carte"] = _remise_carte


@lru_cache(maxsize=4)
def _polices_en_ligne(mtime: float) -> str:
    """`polices.css` sans commentaires ni espaces, pour l'ecrire dans le <head>.

    Le fichier etait une feuille de plus a recuperer avant de pouvoir choisir
    une police : PageSpeed comptait 580 ms de requetes bloquantes. En ligne, il
    n'y a plus d'aller-retour. Relu quand le fichier change (`mtime`).
    """
    css = (HERE / "static" / "polices.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return re.sub(r"\s+", " ", css).replace(" {", "{").replace("{ ", "{").replace("; ", ";").strip()


def _polices_css_en_ligne() -> str:
    return _polices_en_ligne((HERE / "static" / "polices.css").stat().st_mtime)


templates.env.globals["polices_en_ligne"] = _polices_css_en_ligne


def _rayons() -> list[dict[str, Any]]:
    """Le menu des rayons, pris dans le cache de navigation.

    `queries.categories()` coûte 1,77 s (mesuré le 2026-09-14) : c'est la
    requête la plus chère du site. Elle était appelée trois fois par page —
    une fois par `_ctx` pour le menu, une fois par l'accueil, une fois par la
    route de rayon — alors qu'elle rend exactement la même chose aux trois.
    Une seule porte, donc, et le cache derrière.
    """
    def _nav() -> tuple:
        with pool.connection() as conn:  # type: ignore[union-attr]
            return (queries.categories(conn), queries.brands(conn),
                    queries.marchands_actifs(conn))

    return cache.au_chaud("nav", _nav)[0]


def _ctx(request: Request, **extra: Any) -> dict[str, Any]:
    # Le mobilier de navigation est le MÊME pour tout le monde et ne bouge
    # qu'après un passage du pipeline. Le recalculer par visiteur coûtait
    # 7 à 12 s par page une fois le catalogue passé à 312 000 fiches
    # (mesuré le 2026-09-14). Voir `cache.py`.
    def _nav() -> tuple:
        with pool.connection() as conn:  # type: ignore[union-attr]
            return (queries.categories(conn), queries.brands(conn),
                    queries.marchands_actifs(conn))

    nav, marques, marchands = cache.au_chaud("nav", _nav)
    # `marchands` est lu, pas écrit en dur : le bandeau annonçait « 6 marchands
    # vérifiés » alors que deux d'entre eux n'apparaissaient sur aucune fiche.
    # Les bannières sont mises à disposition de TOUS les gabarits, mais posées
    # seulement là où un gabarit les demande explicitement. Aucune fiche produit
    # n'en affiche : voir le commentaire de `_pub.html`.
    return {"request": request, "nav": nav, "marques": marques,
            "marchands_actifs": marchands,
            "bandeaux": partenaires.bandeaux(),
            "bandeaux_larges": partenaires.bandeaux("large"),
            # Vides tant que les comptes n'existent pas : le gabarit n'écrit
            # alors ni script Google ni bandeau de consentement.
            "gtm_id": _GTM_ID, "ga4_id": _GA4_ID, "crisp_id": _CRISP_ID,
            "mesure_active": _MESURE_ACTIVE,
            # Les alertes de prix n'existent pour le visiteur que si un e-mail
            # peut partir : sans SMTP complet (SMTP_PASS vide en production au
            # 15/10/2026), ni formulaire sur les fiches, ni ligne dans /infos.
            "alertes_ouvertes": courriel.configure(),
            **extra}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """L'accueil : curseur de budget, bons plans par rayon, nouveautes, baisses.

    Tout est le MEME pour chaque visiteur et ne change qu'au passage du
    pipeline : le bloc est garde au chaud (voir `cache.py`). Mesure le
    2026-09-14 : 2,4 s de requetes par visite avant ce cache.
    """
    return _page_accueil(request, "home_blocs.html", **_baisses_accueil())


_RAYONS_PHARES = ("helmet", "jacket", "gloves", "boots", "pants", "protection")

# L'accueil ne change qu'au passage du pipeline, qui redemarre le site et le
# rechauffe aussitot (`rechauffer.sh`) : on le garde donc au chaud toute la
# journee. A froid il coute ~20 s (mesure le 17/10/2026 : 4 ecarts, 4 histogrammes,
# 5 nouveautes, les baisses) -- un visiteur ne doit jamais payer ca. Sans cache
# (SITE_CACHE_TTL=0, en developpement) il reste sans cache.
_TTL_ACCUEIL = 86400 if cache.duree() > 0 else 0

# Les quatre onglets des bons plans de l'accueil.
_ONGLETS_ACCUEIL = (("helmet", "Casques"), ("jacket", "Blousons"),
                    ("gloves", "Gants"), ("boots", "Bottes"))


# (code, onglet, « ton prochain … ») pour le curseur de budget
_BUDGETS_ACCUEIL = (("helmet", "Casque", "ton prochain casque"),
                    ("jacket", "Blouson", "ton prochain blouson"),
                    ("gloves", "Gants", "tes prochains gants"),
                    ("boots", "Bottes", "tes prochaines bottes"))


# Rayons mélangés dans « Nouveautés » de l'accueil de test, et taille de la rangée.
_RAYONS_NOUVEAUTES = ("helmet", "jacket", "gloves", "boots", "pants")
_NOUVEAUTES_TOTAL = 18
_NOUVEAUTES_PAR_MARQUE = 2


def _nouveautes_variees(conn) -> list[dict]:
    """Des nouveautés de tous les rayons, pas plus de deux par marque.

    Uniquement des fiches COMPARÉES (2 marchands ou plus). Jusqu'au 18/10/2026
    la rangée se complétait avec des fiches à un seul marchand pour rester
    pleine : 14 cartes sur 18 étaient « 1 marchand » sur un site de comparaison.
    Choix de la propriétaire : une rangée plus courte vaut mieux qu'une rangée
    qui ne compare rien. Les rayons passent à tour de rôle pour que la rangée ne
    soit pas faite de dix paires de bottes d'une même marque.
    """
    par_rayon = []
    for code in _RAYONS_NOUVEAUTES:
        rayon = queries.find_category(_rayons(), code)
        if not rayon:
            continue
        # UN seul appel par rayon : chacun coute 1,6 s (mesure le 17/10/2026).
        par_rayon.append(
            queries.nouveautes(conn, _ids_equipement(rayon), 40, min_marchands=2))
    retenues, par_marque = [], {}
    rang = 0
    while len(retenues) < _NOUVEAUTES_TOTAL and any(rang < len(l) for l in par_rayon):
        for liste in par_rayon:
            if rang < len(liste) and len(retenues) < _NOUVEAUTES_TOTAL:
                it = liste[rang]
                if par_marque.get(it["brand_code"], 0) < _NOUVEAUTES_PAR_MARQUE:
                    par_marque[it["brand_code"]] = par_marque.get(it["brand_code"], 0) + 1
                    retenues.append(it)
        rang += 1
    return retenues


def _ids_equipement(rayon: dict) -> list[int]:
    """Les categories d'un rayon SANS ses pieces et accessoires (`*.accessory`).

    La courbe de budget, les bons plans et les nouveautes de l'accueil parlent de
    ce qu'on achete pour rouler : un visiteur qui cherche « combien pour mon
    prochain casque » ne veut pas voir une visiere a 16 EUR dans la courbe (« un
    casque a moins de 27 euros, ca n'existe pas », 17/10/2026). Les categories
    d'accessoires restent des enfants du rayon pour la navigation ; elles ne
    comptent simplement pas ici.
    """
    pieces = {e["id"] for e in rayon.get("enfants", []) if e["code"].endswith(".accessory")}
    return [i for i in rayon["ids"] if i not in pieces]


def _section_accueil(cle: str, fabrique, defaut):
    """Un bloc de l'accueil, garde au chaud, et qui ne peut pas faire tomber la page.

    Le 17/10/2026, au premier demarrage en production, la requete des baisses a
    depasse le delai de 5 s des requetes du site (le reechauffement en lancait
    d'autres au meme moment, sur un seul coeur) : l'accueil entier rendait un
    500. Un bloc trop lent doit s'afficher VIDE, pas emporter la page ; et ce
    vide n'est pas garde -- `au_chaud` ne memorise rien quand la fabrique leve --
    donc le visiteur suivant retente le calcul.
    """
    try:
        return cache.au_chaud(cle, fabrique, ttl=_TTL_ACCUEIL)
    except (psycopg.errors.QueryCanceled, PoolTimeout):
        log.warning("accueil : le bloc %s est trop lent, affiche vide", cle)
        return defaut


@contextmanager
def _longue_requete(conn):
    """Delai de 30 s pour les blocs de l'accueil, le temps de leur transaction.

    Ils sont calcules UNE fois par jour puis gardes 24 h, et non par visiteur :
    le delai de 5 s des requetes du site est fait pour les pages qu'on calcule a
    chaque visite. En production (un coeur) la requete des baisses ne tient pas
    dans 5 s, et un bloc qui n'aboutit jamais est recalcule a chaque visite
    sans jamais etre garde (17/10/2026).
    """
    with conn.transaction():
        conn.execute("SET LOCAL statement_timeout = '30s'")
        yield


def _onglets_accueil() -> list:
    with pool.connection() as conn, _longue_requete(conn):  # type: ignore[union-attr]
        onglets = []
        for code, titre in _ONGLETS_ACCUEIL:
            rayon = queries.find_category(_rayons(), code)
            items = (queries.ecarts(conn, 6, min_marchands=2, ids=_ids_equipement(rayon))
                     if rayon else [])
            if items:
                onglets.append({"code": code, "titre": titre, "produits": items})
        return onglets


def _budget_accueil() -> list:
    with pool.connection() as conn, _longue_requete(conn):  # type: ignore[union-attr]
        budget = []
        for code, _titre, phrase in _BUDGETS_ACCUEIL:
            rayon = queries.find_category(_rayons(), code)
            h = queries.histo_prix(conn, _ids_equipement(rayon)) if rayon else None
            if h and h["max"]:
                budget.append({"code": code, "phrase": phrase, "label": rayon["label_fr"], **h})
        return budget


def _baisses_accueil() -> dict:
    def _baisses() -> list:
        with pool.connection() as conn, _longue_requete(conn):  # type: ignore[union-attr]
            return queries.baisses(conn, 12, min_marchands=2)

    return {"baisses": _section_accueil("accueil_baisses_v3", _baisses, [])}


def _nouveautes_accueil() -> list:
    def _nouveautes() -> list:
        with pool.connection() as conn, _longue_requete(conn):  # type: ignore[union-attr]
            return _nouveautes_variees(conn)

    return _section_accueil("accueil_nouveautes_v1", _nouveautes, [])


def _page_accueil(request: Request, gabarit: str, **extra: Any):
    bloc = {"onglets": _section_accueil("accueil_onglets_v1", _onglets_accueil, []),
            "budget": _section_accueil("accueil_budget_v1", _budget_accueil, []),
            "nouveautes": _nouveautes_accueil()}
    phares = {c: i for i, c in enumerate(_RAYONS_PHARES)}
    nav_accueil = sorted(_rayons(), key=lambda r: (phares.get(r["code"], 99), -r["n"]))
    return templates.TemplateResponse(
        request, gabarit,
        _ctx(request, **bloc, **extra, nav=nav_accueil, articles=articles_mod.publies()[:3]))


def _releve_jour() -> str:
    """La date du dernier relevé de prix, pour la mention des pages de résultats.

    Gardée au chaud sous sa propre clé : ce `max()` parcourt toute `raw_offer`
    (1,26 Go), et il tournait jusqu'ici à chaque combinaison de filtres pas
    encore en cache. La date ne change qu'une fois par jour.
    """
    def _calcul() -> str:
        with pool.connection() as conn:  # type: ignore[union-attr]
            r = conn.execute(
                "SELECT max(last_seen)::date FROM raw_offer WHERE is_live").fetchone()
        return r[0].strftime("%d/%m/%Y") if r and r[0] else ""

    return cache.au_chaud("releve_jour", _calcul)


def _liste(request, titre, base, f, page, code="", courante=None):
    """Render a listing.

    The three listings — a category, a brand, the whole catalogue — differ only
    by their title, their URL and which filter is fixed. Everything else was
    written three times and had already drifted once.
    """
    # Mesuré le 2026-09-14 sur une recherche : la liste coûte 1,1 s et le
    # PANNEAU DE FILTRES 4,6 s — il lance cinq requêtes qui rebalaient chacune
    # le catalogue avec le même filtre texte. Le refondre est un chantier ; le
    # garder au chaud est immédiat, et deux visiteurs qui ouvrent le même rayon
    # voient exactement la même chose.
    #
    # La clé est la combinaison de filtres ET la page : deux pages d'un même
    # rayon n'ont pas le même contenu. `cache.py` plafonne le nombre d'entrées,
    # sans quoi un robot essayant mille fourchettes de prix ferait gonfler la
    # mémoire indéfiniment.
    def _page() -> tuple:
        with pool.connection() as conn:  # type: ignore[union-attr]
            items, total = queries.listing_filtre(
                conn, f, PER_PAGE, (page - 1) * PER_PAGE)
            return items, total, queries.facets(conn, f)

    items, total, facettes = cache.au_chaud(f"liste|{f}|{page}", _page)
    releve = _releve_jour()
    return templates.TemplateResponse(
        request, "listing.html",
        _ctx(request, titre=titre, code=code, items=items, total=total,
             page=page, pages=max(1, -(-total // PER_PAGE)), base=base,
             courante=courante, facettes=facettes, f=f, releve_jour=releve,
             seo=_seo_liste(base, code, courante, f, page, total)),
    )


def _marques_par_rayon() -> list[dict[str, Any]]:
    """La ventilation marque x rayon (711 lignes), gardée au chaud."""
    def _calcul() -> list[dict[str, Any]]:
        with pool.connection() as conn:  # type: ignore[union-attr]
            return queries.marques_par_rayon(conn)
    return cache.au_chaud("marques-par-rayon", _calcul)


def _seo_liste(base, code, courante, f, page, total) -> dict[str, Any] | None:
    """Titre, description et texte d'ouverture d'un rayon ou d'une marque nus.

    Seulement sans filtre, en page 1 et au tri par défaut : ce sont les pages
    indexées. Une page filtrée garde son titre court — elle est en `noindex`.
    """
    marque_fixee = base.startswith("/m/")
    filtres = [a for a in f.actifs() if not (marque_fixee and a["cle"] == "marque")]
    if filtres or page > 1 or f.tri != "pertinence" or not total:
        return None
    _rayons()   # garde « nav » au chaud : la ligne suivante ne fait que le lire
    marchands = len(cache.au_chaud("nav", lambda: (None, None, []))[2] or [])
    def _saisis() -> dict[str, dict[str, Any]]:
        with pool.connection() as conn:  # type: ignore[union-attr]
            return admin.textes_saisis(conn)

    # Une minute de mémoire : un texte saisi dans l'administration se voit vite.
    saisis = cache.au_chaud("textes-saisis", _saisis, ttl=60)
    if code and courante:
        return seo.avec_textes_saisis(
            seo.rayon(code, courante["label_fr"], total, marchands), saisis.get(f"rayon:{code}"))
    if marque_fixee and f.marque:
        lignes = sorted((x for x in _marques_par_rayon()
                         if x["marque"] == f.marque[0].lower()), key=lambda x: -x["n"])
        return seo.avec_textes_saisis(
            seo.marque(labels.brand(f.marque[0]), total, marchands,
                       [x["rayon"] for x in lignes]),
            saisis.get(f"marque:{f.marque[0].lower()}"))
    return None


@app.get("/produits", response_class=HTMLResponse)
def produits(
    request: Request,
    page: int = Query(1, ge=1, le=_PAGE_MAX),
    marque: list[str] = Query([]),
    prix_min: float | None = Query(None, ge=0, le=100_000),
    prix_max: float | None = Query(None, ge=0, le=100_000),
    taille: list[str] = Query([]),
    couleur: str | None = None,
    matiere: str | None = None,
    homologation: str | None = None,
    saison: str | None = None,
    genre: str | None = None,
    marchands: int = Query(2, ge=2, le=6),
    tri: str = "pertinence",
):
    """The whole catalogue, every department at once — where the home banner
    leads. No category is fixed, so the visitor narrows down from the whole
    shelf instead of having to pick a department before seeing anything."""
    f = queries.Filtres(marque=marque, prix_min=prix_min, prix_max=prix_max,
                        taille=taille, couleur=queries.couleur_simple(couleur),
                        matiere=queries.code_filtre(matiere),
                        homologation=queries.code_filtre(homologation),
                        saison=queries.code_filtre(saison),
                        genre=queries.code_filtre(genre),
                        marchands=marchands, tri=tri)
    return _liste(request, "Tous les produits", "/produits", f, page)


@app.get("/c/{code}", response_class=HTMLResponse)
def category(
    request: Request,
    code: str,
    q: str = "",
    page: int = Query(1, ge=1, le=_PAGE_MAX),
    marque: list[str] = Query([]),
    prix_min: float | None = Query(None, ge=0, le=100_000),
    prix_max: float | None = Query(None, ge=0, le=100_000),
    taille: list[str] = Query([]),
    couleur: str | None = None,
    matiere: str | None = None,
    homologation: str | None = None,
    saison: str | None = None,
    genre: str | None = None,
    marchands: int = Query(2, ge=2, le=6),
    tri: str = "pertinence",
):
    """A category listing, with its filter panel."""
    # Plus besoin d'ouvrir une connexion ici : le menu vient du cache.
    courante = queries.find_category(_rayons(), code)
    if courante is None:
        raise HTTPException(404, "Catégorie inconnue")
    # a parent searches itself and its children: clicking "Casques" must return
    # every helmet, not only those with no readable subtype
    #
    # `q` : sans lui, taper « Honda » puis cliquer un rayon dans le panneau
    # de facettes perdait le mot tapé — `lien_rayon` dans listing.html porte
    # maintenant le même paramètre, mais la route doit aussi savoir le lire.
    # Signalé par la propriétaire (14/10/2026).
    # Les pieces et accessoires d'un rayon (`helmet.accessory`) restent des enfants
    # pour la navigation, mais « Casques » ne les liste plus : ils faussaient le
    # curseur de budget de l'accueil, dont le lien menait ici (17/10/2026).
    f = queries.Filtres(categories=_ids_equipement(courante), texte=q.strip() or None,
                        marque=marque, prix_min=prix_min, prix_max=prix_max,
                        taille=taille, couleur=queries.couleur_simple(couleur),
                        matiere=queries.code_filtre(matiere),
                        homologation=queries.code_filtre(homologation),
                        saison=queries.code_filtre(saison),
                        genre=queries.code_filtre(genre),
                        marchands=marchands,
                        tri=tri)
    return _liste(request, courante["label_fr"], f"/c/{code}", f, page,
                  code=code, courante=courante)


@app.get("/m/{marque}", response_class=HTMLResponse)
def marque_page(
    request: Request,
    marque: str,
    page: int = Query(1, ge=1, le=_PAGE_MAX),
    prix_min: float | None = Query(None, ge=0, le=100_000),
    prix_max: float | None = Query(None, ge=0, le=100_000),
    taille: list[str] = Query([]),
    couleur: str | None = None,
    matiere: str | None = None,
    homologation: str | None = None,
    saison: str | None = None,
    genre: str | None = None,
    marchands: int = Query(2, ge=2, le=6),
    tri: str = "pertinence",
):
    """Everything one brand makes, across every category.

    A brand is a filter, not a text query: the rail used to send the visitor to
    `/recherche?q=shoei`, which answers with whatever contains the word and
    offers nothing to narrow once you land.
    """
    f = queries.Filtres(marque=[marque], prix_min=prix_min, prix_max=prix_max,
                        taille=taille, couleur=queries.couleur_simple(couleur),
                        matiere=queries.code_filtre(matiere),
                        homologation=queries.code_filtre(homologation),
                        saison=queries.code_filtre(saison),
                        genre=queries.code_filtre(genre),
                        marchands=marchands, tri=tri)
    with pool.connection() as conn:  # type: ignore[union-attr]
        _, total = queries.listing_filtre(conn, f, 1, 0)
    if not total and page == 1:
        raise HTTPException(404, "Marque inconnue")
    return _liste(request, labels.brand(marque), f"/m/{marque}", f, page)


@app.get("/p/{slug}", response_class=HTMLResponse)
def product(request: Request, slug: str):
    with pool.connection() as conn:  # type: ignore[union-attr]
        p = queries.product(conn, slug)
        if p is None:
            raise HTTPException(404, "Produit inconnu")
        # Une fiche regroupée avec une autre (`mcpipe consolider`) garde son
        # adresse : elle renvoie, en 301, vers la fiche qui l'a absorbée. Sans
        # cela, chaque regroupement perdait une page déjà connue de Google.
        # Une fiche MASQUÉE à la main (`merged` sans fiche d'arrivée) n'existe plus
        # pour le visiteur : 404, comme une adresse inconnue.
        if p["status"] == "merged":
            cible = (conn.execute("SELECT slug FROM product WHERE id = %s",
                                  (p["merged_into"],)).fetchone()
                     if p.get("merged_into") else None)
            if cible:
                return RedirectResponse(f"/p/{cible[0]}", status_code=301)
            raise HTTPException(404, "Produit inconnu")
        rows = queries.offers(conn, p["id"])
        courbe = queries.price_curve(conn, p["id"])
        graphe = courbe_mod.graphique(courbe)
        similaires = queries.similaires(conn, p, 6)
        meme_gamme = queries.meme_gamme(conn, p, 8)
        promos = queries.codes_promo(conn, sorted({o['merchant'] for o in rows}))
        caracteristiques = queries.caracteristiques(conn, p["id"])
    # Les points de la courbe, posés DANS la page plutôt que servis par une
    # seconde requête : la v1 allait les chercher en JSON après coup, ce qui
    # ajoutait un aller-retour et faisait apparaître la courbe en retard.
    points = [{"time": c["observed_on"].isoformat(),
               "value": float(c["price"]),
               "store": labels.merchant(c.get("merchant"))}
              for c in courbe if c.get("price") is not None]
    # in stock first, then cheapest; an offer with no price goes last
    rows.sort(key=lambda o: (o["in_stock"] is False, o["price"] is None, o["price"] or 0))
    # the sizes offered are whatever the offers actually carry, nothing else
    # filter on the DISPLAYED size: 'TU' is the pipeline's "size unreadable"
    # bucket and renders empty, so it must not become a button of its own.
    # `6` at FC-Moto and `XS` at Speedway on the same barcode are one size, not
    # two: merged into a single `XS / 6` before anything is displayed, so the
    # buttons and the rows agree and a filter never hides half the merchants.
    fusion = labels.equivalences_tailles(rows)
    for o in rows:
        o["taille"] = fusion.get(labels.size_display(o["size_code"]), "")
    tailles = sorted({o["taille"] for o in rows if o["taille"]}, key=labels.size_key)
    image = p["image_url"] or next((o["image_url"] for o in rows if o["image_url"]), None)
    # the cheapest offer that a visitor can actually buy today — `rows` is
    # already sorted in stock first, then by price
    meilleure = next((o for o in rows if o["price"] is not None), None)
    # Le code-barres affiché. UN EAN PAR TAILLE : l'Arai Frost en porte cinq.
    # L'ancien code prenait celui de la première offre du tableau, donc d'une
    # taille au hasard — « un code qui sort de je ne sais où », selon la
    # propriétaire (15/10/2026). Près du titre : seulement s'il est unique, ou
    # celui de la taille choisie (script de la fiche). Tous les codes restent
    # écrits en clair dans « Codes-barres par taille » : une recherche Google
    # sur un EAN doit pouvoir tomber sur cette page, quelle que soit la taille.
    # Maxxess et Moto-Axxe sont écartés : leur GTIN est synthétique.
    for o in rows:
        o["ean"] = (o["gtin"] if o["gtin"]
                    and o["merchant"] not in ("maxxess", "motoaxxe") else "")
    eans = {o["ean"] for o in rows if o["ean"]}
    reference = next(iter(eans)) if len(eans) == 1 else None
    # La taille d'un code se lit sur les offres qui la déclarent ; un code vu
    # seulement chez des marchands muets sur la taille reste sans taille.
    codes_tailles = []
    for ean in eans:
        vues = {o["taille"] for o in rows if o["ean"] == ean and o["taille"]}
        codes_tailles.append({"ean": ean, "taille": vues.pop() if len(vues) == 1 else ""})
    codes_tailles.sort(key=lambda c: (not c["taille"], labels.size_key(c["taille"]), c["ean"]))
    # What comparing is worth here, in euros. Computed across every live offer;
    # the page's own script narrows it to the chosen size, because comparing an
    # XS against an XL is not comparing.
    # Les offres en RUPTURE sont exclues : l'écart était calculé sur toutes les
    # lignes, et le prix le plus cher était parfois celui d'un article
    # indisponible. La page annonçait « vous économisez 54,40 € » en se comparant
    # à un prix que personne ne pouvait payer — alors que le guide du site dit
    # lui-même qu'« un prix bas sur un article en rupture n'est pas un prix ».
    prix = [o["price"] for o in rows
            if o["price"] is not None and o["in_stock"] is not False]
    economie = (max(prix) - min(prix)) if len(prix) > 1 else None
    # Le prix le plus cher qu'un visiteur pourrait payer aujourd'hui pour le
    # même article, et l'écart en pourcentage. C'est CE chiffre qu'on barre —
    # pas un prix conseillé par un fabricant, ni un prix barré fourni par un
    # marchand : une mesure faite par le site entre marchands réels, vérifiable
    # ligne par ligne dans le tableau juste en dessous.
    plus_cher = max(prix) if len(prix) > 1 else None
    remise = (
        round((1 - min(prix) / max(prix)) * 100)
        if plus_cher and max(prix) > 0 and max(prix) > min(prix)
        else None
    )
    # when the prices were last read from the merchants
    vus = [o["last_seen"] for o in rows if o["last_seen"]]
    releve = max(vus).strftime("%d/%m/%Y à %H:%M") if vus else None
    return templates.TemplateResponse(
        request, "product.html",
        _ctx(request, p=p, offres=_grouper(rows), tailles=tailles, courbe=courbe, graphe=graphe,
             points=points,
             image=image, nb_offres=len(rows), meilleure=meilleure,
             reference=reference, economie=economie, releve=releve,
             plus_cher=plus_cher, remise=remise,
             niveau_remise=labels.niveau_remise(remise),
             seuils_remise=labels.SEUILS_REMISE,
             similaires=similaires, meme_gamme=meme_gamme, promos=promos,
             caracteristiques=caracteristiques,
             codes_tailles=codes_tailles if len(codes_tailles) > 1 else [],
             donnees_structurees=[
                 _donnees_structurees(request, p, rows, image, reference,
                                      codes_tailles),
                 _fil_structure(request, p),
             ]),
    )


def _donnees_structurees(
    request: Request,
    p: dict[str, Any],
    rows: list[dict[str, Any]],
    image: str | None,
    reference: str | None,
    codes_tailles: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Le produit et sa fourchette de prix, décrits pour les moteurs.

    Plusieurs tailles, chacune avec son EAN : un `ProductGroup` (variesBy
    size) et une variante par taille, portant SON code-barres et SA
    fourchette de prix. L'ancien balisage posait le `gtin13` d'une seule
    taille, prise au hasard, sur un produit qui les couvre toutes — une
    donnée fausse. Avis d'un consultant SEO, 15/10/2026.

    Une fiche de comparateur sans ces données n'est qu'un texte dans les
    résultats de recherche. Avec elles, le résultat porte la fourchette de
    prix, le nombre de marchands et la disponibilité — la promesse du site,
    lisible avant le clic.

    Deux choses volontairement absentes :

    - **Aucune note, aucun avis.** Les cinq étoiles de la fiche disent
      « comparateur indépendant » ; elles ne notent pas le produit. Les
      déclarer comme une note ferait retirer le site des résultats enrichis,
      et ce serait mérité.
    - **Aucun code-barres inventé.** Maxxess et Moto-Axxe reçoivent un GTIN
      synthétique fabriqué par le pipeline : le publier comme identifiant
      officiel du produit serait une fausse déclaration. `reference` les
      écarte déjà, on s'appuie sur elle.

    Les offres en rupture comptent dans la fourchette mais pas dans le prix
    bas : annoncer « à partir de 43 € » sur un article que personne ne peut
    acheter est exactement le reproche que le guide du site adresse aux
    autres.
    """
    racine = f"{request.url.scheme}://{request.url.netloc}"
    nom = _nom(p)
    marque = labels.brand(p.get("brand_code"))

    achetables = [o["price"] for o in rows
                  if o["price"] is not None and o["in_stock"] is not False]
    tous = [o["price"] for o in rows if o["price"] is not None]

    produit: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": nom,
        "url": f"{racine}/p/{p['slug']}",
    }
    if marque:
        produit["brand"] = {"@type": "Brand", "name": marque}
    if image:
        produit["image"] = image
    if reference:
        # 13 chiffres : un EAN. Le déclarer comme tel vaut mieux que `sku`,
        # c'est l'identifiant que les moteurs recoupent entre marchands.
        produit["gtin13" if len(reference) == 13 else "sku"] = reference
    if p.get("colour_code") and p["colour_code"] != "unknown":
        produit["color"] = labels.colour(p["colour_code"])

    if tous:
        bas = min(achetables) if achetables else min(tous)
        produit["offers"] = {
            "@type": "AggregateOffer",
            "priceCurrency": "EUR",
            "lowPrice": f"{bas:.2f}",
            "highPrice": f"{max(tous):.2f}",
            "offerCount": len(rows),
            "availability": (
                "https://schema.org/InStock" if achetables
                else "https://schema.org/OutOfStock"
            ),
        }

    variantes = []
    for c in codes_tailles or []:
        if not c["taille"]:
            continue
        lignes = [o for o in rows if o["ean"] == c["ean"] and o["price"] is not None]
        if not lignes:
            continue
        dispo = [o["price"] for o in lignes if o["in_stock"] is not False]
        prix_v = [o["price"] for o in lignes]
        variantes.append({
            "@type": "Product",
            "name": f"{nom} — taille {c['taille']}",
            "size": c["taille"],
            "gtin13" if len(c["ean"]) == 13 else "sku": c["ean"],
            "offers": {
                "@type": "AggregateOffer",
                "priceCurrency": "EUR",
                "lowPrice": f"{min(dispo or prix_v):.2f}",
                "highPrice": f"{max(prix_v):.2f}",
                "offerCount": len(lignes),
                "availability": ("https://schema.org/InStock" if dispo
                                 else "https://schema.org/OutOfStock"),
            },
        })
    if len(variantes) > 1:
        groupe = {k: v for k, v in produit.items() if k != "offers"}
        groupe.update({
            "@type": "ProductGroup",
            "productGroupID": p["slug"],
            "variesBy": "https://schema.org/size",
            "hasVariant": variantes,
        })
        return groupe
    return produit


def _fil_structure(request: Request, p: dict[str, Any]) -> dict[str, Any]:
    """Le fil d'Ariane déjà affiché en haut de la fiche, redit aux moteurs.

    Il est écrit ici à partir des mêmes valeurs que le gabarit : deux sources
    pour un seul fil finiraient par se contredire, et c'est la version cachée
    qui mentirait sans que personne le voie.
    """
    etapes = [("Accueil", "/")]
    if p.get("category_code"):
        etapes.append((p.get("category_label") or p["category_code"],
                       f"/c/{p['category_code']}"))
    etapes.append((_nom(p), f"/p/{p['slug']}"))
    return _fil(request, etapes)


def _fil(request: Request, etapes: list[tuple[str, str]]) -> dict[str, Any]:
    """Un `BreadcrumbList` à partir des étapes (libellé, chemin) déjà affichées.

    Sorti de `_fil_structure` pour servir aussi aux articles : un seul endroit
    qui sait écrire un fil d'Ariane pour les moteurs.
    """
    racine = f"{request.url.scheme}://{request.url.netloc}"
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": nom, "item": racine + chemin}
            for i, (nom, chemin) in enumerate(etapes, start=1)
        ],
    }


def _grouper(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse a merchant's sizeless offers at the same price into one row.

    Motoblouz lists the Arai SZ-R four times — XS, S, M and L — and never says
    which. On the page that reads as the same offer repeated four times, which
    looks like a bug and hides that they are four real, different articles. They
    become one row saying so, with the other links kept: dropping them would
    remove real offers from the comparison.

    Only ever groups offers that are genuinely indistinguishable to a visitor:
    same merchant, same price, same stock state, and no size on either side.
    """
    groupes: list[dict[str, Any]] = []
    index: dict[tuple, dict[str, Any]] = {}
    for o in rows:
        if o["taille"]:
            groupes.append({**o, "autres": []})
            continue
        cle = (o["merchant"], o["price"], o["in_stock"])
        if cle in index:
            index[cle]["autres"].append(o["deeplink"])
        else:
            tete = {**o, "autres": []}
            index[cle] = tete
            groupes.append(tete)
    return groupes



# --- qui peut ouvrir le tableau de bord --------------------------------------
#
# `/admin` affiche les messages reçus et les adresses e-mail qui les
# accompagnent : le jour où le site prend une adresse publique, c'est une fuite
# de données personnelles ouverte à tous. Le fichier `admin.py` le disait déjà
# en avertissement ; il manquait le verrou.
#
# Deux niveaux, dans cet ordre :
#   1. si `ADMIN_MDP` est renseigné dans `.env`, un mot de passe est exigé ;
#   2. sinon, seules les adresses du réseau local sont acceptées — ce qui laisse
#      le téléphone de la maison fonctionner comme avant, et ferme la porte
#      partout ailleurs.
# Le mot de passe n'est écrit nulle part dans le dépôt : il se pose dans `.env`.
#
# Le réseau local se teste avec `ipaddress`, jamais par préfixe de texte :
# l'ancien préfixe « 172.2 » couvrait aussi 172.2.x.x et 172.200 à 172.255,
# des plages publiques louables chez des hébergeurs.
#
# Aucune page admin ne doit entrer dans le cache nginx, dont la clé ignore
# l'adresse et l'en-tête Authorization : la première page servie à une
# personne autorisée l'aurait été à tout le monde pendant une heure.
_SANS_CACHE = {"Cache-Control": "no-store, private"}


def _reseau_local(hote: str) -> bool:
    import ipaddress

    if hote == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(hote)
    except ValueError:
        return False
    return ip.is_loopback or (ip.is_private and not ip.is_link_local)


def _admin_autorise(request: Request) -> Response | None:
    """None si l'accès est permis, sinon la réponse à renvoyer."""
    mdp = os.environ.get("ADMIN_MDP", "").strip()
    if mdp:
        entete = request.headers.get("authorization", "")
        if entete.startswith("Basic "):
            import base64
            import hmac

            try:
                donne = base64.b64decode(entete[6:]).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001 — en-tête malformé = refus
                donne = ""
            # comparaison à temps constant : sinon le temps de réponse dit au
            # visiteur combien de caractères il a devinés.
            if hmac.compare_digest(donne.split(":", 1)[-1], mdp):
                return None
        return Response(
            "Accès réservé.", status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="MotoComparo"', **_SANS_CACHE},
        )

    hote = request.client.host if request.client else ""
    if _reseau_local(hote):
        return None
    return PlainTextResponse(
        "Le tableau de bord n'est accessible que depuis le réseau local. "
        "Pour l'ouvrir ailleurs, renseignez ADMIN_MDP dans .env.",
        status_code=403, headers=_SANS_CACHE,
    )


@app.get("/admin", response_class=HTMLResponse)
def tableau_de_bord(request: Request):
    """The site's own admin screen — the price of leaving WordPress.

    Read-only apart from the promo codes, which are entered here because they
    are the one thing in this catalogue no feed provides — see `/admin/code-promo`.
    It answers the questions the owner would otherwise need a developer and a
    SQL prompt for.
    """
    refus = _admin_autorise(request)
    if refus is not None:
        return refus

    import time as _t

    with pool.connection() as conn:  # type: ignore[union-attr]
        contexte = {
            "flux": admin.flux(conn),
            "cat": admin.catalogue(conn),
            "p": admin.prix(conn),
            "alertes": admin.alertes(conn),
            "marques_top": admin.top_marques(conn),
            "revue": admin.revue(conn),
            "promos": admin.codes_promo(conn),
            "messages": admin.messages(conn),
            "marchands": admin.marchands(conn),
            "maintenant": _t.strftime("%d/%m/%Y %H:%M"),
        }
    return templates.TemplateResponse(request, "admin.html", _ctx(request, **contexte),
                                      headers=_SANS_CACHE)


@app.post("/admin/code-promo")
async def admin_code_promo(request: Request):
    """Add or withdraw a promo code.

    The end date is required by the table, not by politeness: a code shown after
    it expired sends the visitor to a checkout that refuses it, and they do not
    come back. Withdrawing is a date, never a deletion — knowing which code ran
    when is worth keeping.
    """
    refus = _admin_autorise(request)
    if refus is not None:
        return refus

    # Une page tierce ouverte par l'administratrice ne doit pas pouvoir poster
    # ici à sa place (le navigateur renverrait les identifiants Basic).
    origine = request.headers.get("origin") or ""
    if origine and not origine.startswith(("https://motocomparo.com",
                                           "http://127.0.0.1", "http://localhost")):
        return PlainTextResponse("Origine refusée.", status_code=403,
                                 headers=_SANS_CACHE)

    d = parse_qs((await request.body()).decode("utf-8", "replace"))
    prendre = lambda k: (d.get(k, [""])[0] or "").strip()  # noqa: E731
    # le lien du code s'affiche sur les fiches : https ou rien
    if prendre("url") and not prendre("url").startswith("https://"):
        d["url"] = [""]
    with pool.connection() as conn:  # type: ignore[union-attr]
        if prendre("retirer").isdigit():
            # `source = 'manuel'` en même temps que la date : sans ça, le relevé
            # du lendemain retrouvait le code sur la page du marchand, entrait
            # dans son `ON CONFLICT DO UPDATE` (qui ne protège que les lignes
            # déjà `manuel`) et remettait `retire_le` à NULL. Le code retiré
            # revenait tout seul, et c'était le chemin le plus court pour qu'un
            # code faux réapparaisse sur une fiche.
            conn.execute(
                "UPDATE code_promo SET retire_le = now(), source = 'manuel' "
                "WHERE id = %s", (int(prendre("retirer")),))
        elif (prendre("code") and prendre("fin_le")
              and prendre("merchant_id").isdigit()):
            conn.execute("""
                INSERT INTO code_promo (merchant_id, code, libelle, url, fin_le)
                VALUES (%s, %s, %s, nullif(%s, ''), %s)
                ON CONFLICT (merchant_id, code) DO UPDATE
                   SET libelle = excluded.libelle, url = excluded.url,
                       fin_le = excluded.fin_le, retire_le = NULL
            """, (int(prendre("merchant_id")), prendre("code").upper(),
                  prendre("libelle"), prendre("url"), prendre("fin_le")))
    return RedirectResponse("/admin#promos", status_code=303, headers=_SANS_CACHE)


# --- l'administration : regroupements de fiches et alias de marque ----------
#
# La propriétaire décide ici ; le pipeline de nuit applique (`mcpipe consolider
# --appliquer`, et la lecture des alias par `signature`). Rien ne modifie une
# fiche sur-le-champ : une erreur de clic se rattrape avant la nuit.

async def _admin_formulaire(request: Request):
    """(champs, None) si la requête est permise, sinon (None, réponse de refus)."""
    refus = _admin_autorise(request)
    if refus is not None:
        return None, refus
    origine = request.headers.get("origin") or ""
    if origine and not origine.startswith(("https://motocomparo.com",
                                           "http://127.0.0.1", "http://localhost")):
        return None, PlainTextResponse("Origine refusée.", status_code=403,
                                       headers=_SANS_CACHE)
    d = parse_qs((await request.body()).decode("utf-8", "replace"))
    return {k: (v[0] or "").strip() for k, v in d.items()}, None


@app.get("/admin/regroupements", response_class=HTMLResponse)
def admin_regroupements(request: Request):
    refus = _admin_autorise(request)
    if refus is not None:
        return refus
    with pool.connection() as conn:  # type: ignore[union-attr]
        contexte = {"compte": admin.regroupements_compte(conn),
                    "groupes": admin.regroupements_echantillon(conn)}
    return templates.TemplateResponse(request, "admin_regroupements.html",
                                      _ctx(request, **contexte), headers=_SANS_CACHE)


@app.post("/admin/regroupements/decider")
async def admin_regroupements_decider(request: Request):
    champs, refus = await _admin_formulaire(request)
    if refus is not None:
        return refus
    decision = {"valider": "validee", "refuser": "refusee"}.get(champs.get("decision", ""))
    if decision and champs.get("id", "").isdigit():
        with pool.connection() as conn:  # type: ignore[union-attr]
            conn.execute("UPDATE fusion_proposee SET statut = %s, decide_le = now() "
                         "WHERE id = %s AND statut = 'proposee'",
                         (decision, int(champs["id"])))
    return RedirectResponse("/admin/regroupements", status_code=303, headers=_SANS_CACHE)


@app.post("/admin/regroupements/tout-valider")
async def admin_regroupements_tout_valider(request: Request):
    champs, refus = await _admin_formulaire(request)
    if refus is not None:
        return refus
    with pool.connection() as conn:  # type: ignore[union-attr]
        conn.execute("UPDATE fusion_proposee SET statut = 'validee', decide_le = now() "
                     "WHERE statut = 'proposee'")
    return RedirectResponse("/admin/regroupements", status_code=303, headers=_SANS_CACHE)


@app.post("/admin/regroupements/auto")
async def admin_regroupements_auto(request: Request):
    champs, refus = await _admin_formulaire(request)
    if refus is not None:
        return refus
    valeur = "oui" if champs.get("valeur") == "oui" else "non"
    with pool.connection() as conn:  # type: ignore[union-attr]
        conn.execute("INSERT INTO reglage (cle, valeur) VALUES ('fusion_auto', %s) "
                     "ON CONFLICT (cle) DO UPDATE SET valeur = excluded.valeur, "
                     "modifie_le = now()", (valeur,))
    return RedirectResponse("/admin/regroupements", status_code=303, headers=_SANS_CACHE)


@app.get("/admin/marques", response_class=HTMLResponse)
def admin_marques(request: Request):
    refus = _admin_autorise(request)
    if refus is not None:
        return refus
    with pool.connection() as conn:  # type: ignore[union-attr]
        contexte = {"alias": admin.marques_alias(conn),
                    "propositions": cache.au_chaud("admin|marques-propositions",
                                                   lambda: admin.marques_propositions(conn),
                                                   ttl=0)}
    return templates.TemplateResponse(request, "admin_marques.html",
                                      _ctx(request, **contexte), headers=_SANS_CACHE)


_CODE_MARQUE = re.compile(r"^[a-z0-9]{1,40}$")


@app.post("/admin/marques/alias")
async def admin_marques_alias(request: Request):
    champs, refus = await _admin_formulaire(request)
    if refus is not None:
        return refus
    alias = champs.get("alias", "").lower()
    marque = champs.get("marque", "").lower()
    statut = "refuse" if champs.get("statut") == "refuse" else "valide"
    if _CODE_MARQUE.match(alias) and _CODE_MARQUE.match(marque) and alias != marque:
        with pool.connection() as conn:  # type: ignore[union-attr]
            conn.execute("INSERT INTO marque_alias (alias, marque, statut) VALUES (%s, %s, %s) "
                         "ON CONFLICT (alias) DO UPDATE SET marque = excluded.marque, "
                         "statut = excluded.statut", (alias, marque, statut))
    return RedirectResponse("/admin/marques", status_code=303, headers=_SANS_CACHE)


@app.post("/admin/marques/supprimer")
async def admin_marques_supprimer(request: Request):
    champs, refus = await _admin_formulaire(request)
    if refus is not None:
        return refus
    if champs.get("alias"):
        with pool.connection() as conn:  # type: ignore[union-attr]
            conn.execute("DELETE FROM marque_alias WHERE alias = %s", (champs["alias"],))
    return RedirectResponse("/admin/marques", status_code=303, headers=_SANS_CACHE)


@app.get("/admin/caracteristiques", response_class=HTMLResponse)
def admin_caracteristiques(request: Request, rayon: int = 0, manque: str = "",
                           page: int = Query(1, ge=1, le=400)):
    refus = _admin_autorise(request)
    if refus is not None:
        return refus
    with pool.connection() as conn:  # type: ignore[union-attr]
        lignes, total = admin.incompletes(conn, rayon or None, manque or None, page)
        contexte = {"couverture": admin.couverture_par_rayon(conn),
                    "rayons": admin.incompletes_rayons(conn),
                    "lignes": lignes, "total": total, "page": page,
                    "pages": max(1, -(-total // 25)), "rayon": rayon, "manque": manque}
    return templates.TemplateResponse(request, "admin_caracteristiques.html",
                                      _ctx(request, **contexte), headers=_SANS_CACHE)


@app.post("/admin/caracteristiques/enregistrer")
async def admin_caracteristiques_enregistrer(request: Request):
    champs, refus = await _admin_formulaire(request)
    if refus is not None:
        return refus
    if champs.get("product_id", "").isdigit():
        with pool.connection() as conn:  # type: ignore[union-attr]
            admin.enregistrer_caracteristiques(
                conn, int(champs["product_id"]),
                {k: champs.get(k, "") for k in ("saison", "matiere", "homologation")})
    retour = champs.get("retour", "")
    if not retour.startswith("/admin/caracteristiques"):
        retour = "/admin/caracteristiques"
    return RedirectResponse(retour, status_code=303, headers=_SANS_CACHE)


@app.get("/admin/produits", response_class=HTMLResponse)
def admin_produits(request: Request, q: str = ""):
    refus = _admin_autorise(request)
    if refus is not None:
        return refus
    with pool.connection() as conn:  # type: ignore[union-attr]
        contexte = {"q": q, "trouves": admin.produits_trouves(conn, q) if q.strip() else [],
                    "rayons": admin.rayons_choix(conn), "masques": admin.produits_masques(conn)}
    return templates.TemplateResponse(request, "admin_produits.html",
                                      _ctx(request, **contexte), headers=_SANS_CACHE)


@app.post("/admin/produits/action")
async def admin_produits_action(request: Request):
    champs, refus = await _admin_formulaire(request)
    if refus is not None:
        return refus
    action = champs.get("action", "")
    with pool.connection() as conn:  # type: ignore[union-attr]
        if action == "masquer" and champs.get("product_id", "").isdigit():
            admin.masquer(conn, int(champs["product_id"]), champs.get("motif", ""))
        elif action == "reafficher" and champs.get("slug"):
            admin.reafficher(conn, champs["slug"])
        elif (action == "rayon" and champs.get("product_id", "").isdigit()
              and champs.get("rayon", "").isdigit()):
            admin.changer_rayon(conn, int(champs["product_id"]), int(champs["rayon"]))
    # le site garde ses listes trois heures : une correction doit se voir tout de suite
    cache.vider()
    retour = champs.get("retour", "")
    if not retour.startswith("/admin/produits"):
        retour = "/admin/produits"
    return RedirectResponse(retour, status_code=303, headers=_SANS_CACHE)


@app.get("/admin/calculs", response_class=HTMLResponse)
def admin_calculs(request: Request):
    refus = _admin_autorise(request)
    if refus is not None:
        return refus
    with pool.connection() as conn:  # type: ignore[union-attr]
        contexte = {"calculs": admin.calculs(conn), "historique": admin.calculs_historique(conn)}
    return templates.TemplateResponse(request, "admin_calculs.html",
                                      _ctx(request, **contexte), headers=_SANS_CACHE)


@app.post("/admin/calculs/lancer")
async def admin_calculs_lancer(request: Request):
    champs, refus = await _admin_formulaire(request)
    if refus is not None:
        return refus
    if champs.get("tache") == "cache":
        cache.vider()           # instantané : pas de file d'attente
    else:
        with pool.connection() as conn:  # type: ignore[union-attr]
            admin.demander_calcul(conn, champs.get("tache", ""))
    return RedirectResponse("/admin/calculs", status_code=303, headers=_SANS_CACHE)


@app.get("/admin/textes", response_class=HTMLResponse)
def admin_textes(request: Request, marque: str = ""):
    refus = _admin_autorise(request)
    if refus is not None:
        return refus
    with pool.connection() as conn:  # type: ignore[union-attr]
        contexte = {"rayons": admin.textes_rayons(conn), "marque": marque.strip().lower(),
                    "marques_saisies": [v for k, v in admin.textes_saisis(conn).items()
                                        if k.startswith("marque:")]}
    return templates.TemplateResponse(request, "admin_textes.html",
                                      _ctx(request, **contexte), headers=_SANS_CACHE)


@app.post("/admin/textes/enregistrer")
async def admin_textes_enregistrer(request: Request):
    champs, refus = await _admin_formulaire(request)
    if refus is not None:
        return refus
    with pool.connection() as conn:  # type: ignore[union-attr]
        admin.enregistrer_texte(conn, champs.get("cle", ""), champs.get("titre", ""),
                                champs.get("description", ""), champs.get("intro", ""))
    cache.vider()
    return RedirectResponse("/admin/textes", status_code=303, headers=_SANS_CACHE)


@app.get("/favoris")
def favoris():
    """Les favoris ont rejoint le comparatif (17/10/2026) : une seule liste, une
    seule page. L'ancienne adresse y renvoie, pour les liens deja partages."""
    return RedirectResponse("/comparer", status_code=301)


def _noter(items: list[dict[str, Any]]) -> None:
    """Pose la note MotoComparo sur chaque fiche comparée, en place.

    Rien à interroger ici : la note ne dépend que des caractéristiques déjà
    chargées avec la fiche. Le prix n'y entre pas — voir `_POIDS_QUALITE`.
    """
    for it in items:
        it["indice"] = queries.note_globale(
            it["caracteristiques"], it.get("category_code") or "")


@app.get("/comparer", response_class=HTMLResponse)
def comparer(request: Request, p: str = ""):
    """Prix, protection et technologies des fiches choisies, côte à côte.

    Plafonné à huit colonnes — pas les quarante des favoris. Au-delà, un
    tableau ne se lit plus : chaque caractéristique en ligne, chaque produit
    en colonne, et la largeur d'écran est ce qu'elle est.
    """
    slugs = [x for x in p.split(",") if x][:8]
    with pool.connection() as conn:  # type: ignore[union-attr]
        items = queries.par_slugs(conn, slugs)
        for it in items:
            it["caracteristiques"] = queries.caracteristiques(conn, it["product_id"])
    _noter(items)
    lignes = queries.tableau_comparaison(items)
    sections = queries.sections_comparaison(lignes)
    # Comparer un casque à une botte ne dit rien : le tableau reste affiché
    # (retirer une fiche silencieusement serait plus surprenant qu'un
    # avertissement), mais la page le signale plutôt que de laisser croire
    # que les rayons se répondent.
    memes_rayons = len({it["category_id"] for it in items}) <= 1
    return templates.TemplateResponse(
        request, "comparer.html",
        _ctx(request, titre="Mon comparateur", cle="comparer", items=items,
             lignes=lignes, sections=sections, memes_rayons=memes_rayons, mode="perso",
             lien_partage=("/comparatif/" + ",".join(it["slug"] for it in items)
                           if len(items) >= 2 else None),
             vide="Aucun produit dans le comparateur.",
             aide="Le bouton ⇄ sur une image ajoute le produit ici."),
    )


@app.get("/comparatif/{slugs}", response_class=HTMLResponse)
def comparatif(request: Request, slugs: str):
    """La comparaison publique et partageable — une ADRESSE, pas une liste
    posée dans le navigateur de quelqu'un.

    `/comparer` sert la même table, mais vécue depuis les favoris de la
    personne qui la regarde : son lien ne veut rien dire pour un tiers, et
    aucun moteur ne peut l'indexer, puisque la page part vide sans le
    `localStorage` qui la remplit. Cette route-ci porte les fiches dans
    l'URL elle-même — deux casques ou trois blousons, écrits dans l'adresse —
    partageable telle quelle et ouverte à l'indexation, comme les pages
    « vs » d'un comparateur de téléphones.
    """
    slugs_list = [s for s in slugs.split(",") if s][:8]
    if len(slugs_list) < 2:
        raise HTTPException(404, "Il faut au moins deux fiches à comparer")
    with pool.connection() as conn:  # type: ignore[union-attr]
        items = queries.par_slugs(conn, slugs_list)
        for it in items:
            it["caracteristiques"] = queries.caracteristiques(conn, it["product_id"])
    if len(items) < 2:
        raise HTTPException(404, "Fiches introuvables ou insuffisantes pour comparer")
    _noter(items)
    lignes = queries.tableau_comparaison(items)
    sections = queries.sections_comparaison(lignes)
    memes_rayons = len({it["category_id"] for it in items}) <= 1
    titre = " vs ".join(_nom(it) for it in items)
    return templates.TemplateResponse(
        request, "comparatif.html",
        _ctx(request, titre=titre, items=items, lignes=lignes, sections=sections,
             memes_rayons=memes_rayons, mode="partage",
             slugs=[it["slug"] for it in items]),
    )


@app.post("/lettre")
async def lettre(request: Request):
    """Sign up for the weekly letter.

    An address and a date, nothing else — no name, no tracking. Signing up twice
    is not an error and creates no duplicate (`ON CONFLICT DO NOTHING`), and an
    address that had unsubscribed is reactivated rather than refused.

    ⚠️ This writes PERSONAL DATA. It must not be opened to the public until the
    privacy page is written and published: collecting an address without saying
    what becomes of it is not acceptable, and that text is the owner's to write.

    Fermée tant que la lettre n'existe pas : aucune page n'a de formulaire qui
    y mène, mais la route acceptait n'importe quel envoi fabriqué à la main.
    Passer `LETTRE_OUVERTE=1` dans `.env` le jour du lancement.
    """
    if os.environ.get("LETTRE_OUVERTE", "") != "1":
        raise StarletteHTTPException(status_code=404)
    # Le corps est décodé à la main. FastAPI comme Starlette réclament
    # `python-multipart` dès qu'on touche à un formulaire, même sans fichier :
    # une dépendance de plus à installer et à tenir à jour sur le serveur, pour
    # lire un champ de texte. `parse_qs` est dans la bibliothèque standard.
    corps = (await request.body()).decode("utf-8", "replace")
    champs = parse_qs(corps)
    adresse = (champs.get("email", [""])[0]).strip().lower()[:254]
    if "@" in adresse:
        with pool.connection() as conn:  # type: ignore[union-attr]
            conn.execute("""
                INSERT INTO lettre_inscrit (email) VALUES (%s)
                ON CONFLICT (email) DO UPDATE SET desinscrit_le = NULL
            """, (adresse,))
    # 303 and not 302: the browser must follow with a GET, otherwise a refresh
    # replays the POST and the visitor signs up again
    return RedirectResponse("/infos#lettre", status_code=303)


@app.get("/fragment/vus", response_class=HTMLResponse)
def fragment_vus(request: Request, ids: str = ""):
    """Les fiches déjà consultées, rendues par le serveur, injectées par la page.

    La liste vit dans le navigateur : le site n'a ni compte ni cookie, et rien
    de ce qui est consulté ne remonte au serveur autrement que dans cette URL,
    le temps d'une requête. Le rendu reste celui du serveur — les cartes sont
    donc identiques à celles des rayons, sans second chemin de rendu.

    Renvoie une chaîne vide quand il n'y a rien à montrer : la page n'affiche
    alors aucun cadre, plutôt qu'un rayon vide.
    """
    slugs = [s for s in ids.split(",") if s][:12]
    if not slugs:
        return HTMLResponse("")
    with pool.connection() as conn:  # type: ignore[union-attr]
        items = queries.par_slugs(conn, slugs)
    if not items:
        return HTMLResponse("")
    # `_ctx` n'est pas utilisé ici : il interroge la base pour le menu et les
    # marques, dont ce fragment n'affiche rien. C'étaient deux requêtes de plus
    # à chaque chargement de l'accueil, pour rien.
    return templates.TemplateResponse(
        request, "_rayon_vus.html", {"request": request, "items": items})


@app.get("/bons-plans", response_class=HTMLResponse)
def bons_plans(request: Request):
    """« Meilleurs prix du moment » — la page de la v1, mesurée honnêtement.

    L'écart est calculé entre marchands vendant le MÊME code-barres. Une
    première version le calculait sur la fiche : elle sortait une page entière
    de « -50 % » qui étaient en réalité deux articles différents rangés dans la
    même fiche (un kit de sacoches 16 L à 350 € et un 16/16 L à 675 €). Un
    comparateur qui met ses propres ratés en vitrine ne survit pas à un lecteur
    attentif.
    """
    # Une agrégation sur tout le catalogue, identique pour tous les visiteurs
    # et qui ne bouge qu'au passage du pipeline : 17 s par visite sans cache.
    def _items():
        with pool.connection() as conn:  # type: ignore[union-attr]
            return queries.bons_plans(conn, 48)

    items = cache.au_chaud("bons_plans", _items)
    return templates.TemplateResponse(
        request, "bons-plans.html", _ctx(request, items=items))


@app.get("/marques", response_class=HTMLResponse)
def marques(request: Request):
    """L'index alphabétique de toutes les marques comparables."""
    def _items():
        with pool.connection() as conn:  # type: ignore[union-attr]
            return queries.toutes_marques(conn)

    items = cache.au_chaud("toutes_marques", _items)
    lettres = sorted({(m["brand_code"] or "?")[0].lower() for m in items})
    return templates.TemplateResponse(
        request, "marques.html", _ctx(request, items=items, lettres=lettres))


@app.get("/guides", response_class=HTMLResponse)
def guides(request: Request):
    """Tailles et normes — des faits vérifiables, pas des conseils de vendeur.

    C'est aussi l'index des articles : une seule rubrique éditoriale, pas un
    blog à côté (voir l'en-tête de `articles.py`). Seuls les articles publiés
    y sont listés ; sans aucun, la page reste exactement celle d'avant.
    """
    return templates.TemplateResponse(
        request, "guides.html", _ctx(request, articles=articles_mod.publies()))


_DONNEES_ARTICLE = articles_mod.Donnees(lambda: pool)


@app.get("/guides/{slug}", response_class=HTMLResponse)
def article(request: Request, slug: str):
    """Un article. Un brouillon répond 404 hors aperçu (`BLOG_APERCU=1`)."""
    a = articles_mod.trouver(slug)
    if a is None:
        raise HTTPException(404, "Article introuvable")
    racine = f"{request.url.scheme}://{request.url.netloc}"
    url = f"{racine}/guides/{a.slug}"
    # `BlogPosting` plutôt qu'`Article` : c'est le type que Google attend
    # pour un texte daté d'une rubrique de conseils. Auteur et éditeur sont
    # le site lui-même — aucune personne n'est nommée, aucun avis n'est
    # déclaré : il n'y en a pas.
    posting: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": a.titre,
        "description": a.description,
        "datePublished": a.date.isoformat(),
        "dateModified": (a.maj or a.date).isoformat(),
        "inLanguage": "fr-FR",
        "mainEntityOfPage": {"@type": "WebPage", "@id": url},
        "url": url,
        "author": {"@type": "Organization", "name": "MotoComparo", "url": racine + "/"},
        "publisher": {"@type": "Organization", "name": "MotoComparo",
                      "logo": {"@type": "ImageObject",
                               "url": racine + "/static/logo_mc.png"}},
    }
    if a.illustration_url:
        posting["image"] = racine + a.illustration_url
    if a.marques:
        posting["about"] = [{"@type": "Brand", "name": labels.brand(m)}
                            for m in a.marques]
    fil = _fil(request, [("Accueil", "/"), ("Guides & conseils", "/guides"),
                         (a.titre, f"/guides/{a.slug}")])
    return templates.TemplateResponse(
        request, "article.html",
        _ctx(request, article=a, donnees=_DONNEES_ARTICLE,
             donnees_structurees=[posting, fil]))


# --- la mesure d'audience, et son interrupteur -------------------------------
#
# L'IDENTIFIANT VIT DANS `.env`, ET SON ABSENCE EST UN ÉTAT NORMAL. Tant qu'il
# n'est pas renseigné, AUCUN script Google n'est écrit dans la page : pas de
# balise vide, pas de requête vers un conteneur inexistant, et le bandeau de
# consentement ne s'affiche pas non plus — il n'aurait rien à faire consentir.
# Le site reste alors exactement ce qu'il était, et la phrase de la page
# Confidentialité qui le dit reste vraie.
#
# C'est aussi ce qui permet de livrer le code avant que le conteneur existe :
# la propriétaire colle l'identifiant le jour où elle le crée, sans toucher au
# dépôt — qui est public, et où un identifiant de mesure n'a rien à faire.
# DEUX INTERRUPTEURS INDÉPENDANTS, et c'est voulu. Google Tag Manager est un
# outil de plus à apprendre ; Google Analytics seul se branche en collant un
# identifiant. On peut donc commencer par GA4 seul, ajouter GTM le jour où un
# besoin l'exige (une balise publicitaire, un suivi de conversion), ou n'avoir
# que GTM et déclarer GA4 dedans. Les trois combinaisons fonctionnent, et
# aucune ne demande de retoucher le code.
#
# ⚠️ NE PAS DÉCLARER GA4 DES DEUX CÔTÉS. Si `GA4_ID` est renseigné ici ET
# qu'une balise GA4 existe dans le conteneur GTM, chaque page est comptée deux
# fois. Le garde ci-dessous ne peut pas le voir — le contenu du conteneur n'est
# pas lisible d'ici — donc c'est écrit là où on le lira : dans `.env.example`.
_GTM_ID = os.environ.get("GTM_ID", "").strip()
_GA4_ID = os.environ.get("GA4_ID", "").strip()
# Le chat d'assistance Crisp : un identifiant de site (UUID), public par nature
# (il figure dans le code que Crisp fournit). Chargé dès l'ouverture de toute
# page, indépendamment du bandeau de cookies : décision de la propriétaire
# (16/10/2026). La page de confidentialité le dit.
_CRISP_ID = os.environ.get("CRISP_WEBSITE_ID", "").strip().lower()

# Des identifiants, et rien d'autre. Ces champs finissent dans une balise
# `<script>` : une valeur fantaisiste venue d'un `.env` mal recopié y serait
# injectée telle quelle. Les formats sont fixes et connus, on s'y tient.
# ⚠️ Les variables de cette boucle sont préfixées `_cfg_` pour une raison
# concrète : la première version les appelait `_nom`, `_valeur`… et une boucle
# au niveau du module laisse ses variables derrière elle. `_nom` était déjà
# LA FONCTION qui compose le nom d'un produit, trois cents lignes plus haut ;
# elle s'est retrouvée remplacée par la chaîne « GA4_ID », et treize
# vérifications sont tombées sur `'str' object is not callable`.
for _cfg_nom, _cfg_valeur, _cfg_motif, _cfg_exemple in (
        ("GTM_ID", _GTM_ID, r"GTM-[A-Z0-9]{4,10}", "GTM-XXXXXXX"),
        ("GA4_ID", _GA4_ID, r"G-[A-Z0-9]{4,12}", "G-XXXXXXXXXX"),
        ("CRISP_WEBSITE_ID", _CRISP_ID,
         r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
         "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")):
    if _cfg_valeur and not re.fullmatch(_cfg_motif, _cfg_valeur):
        raise RuntimeError(
            f"{_cfg_nom} ne ressemble pas à un identifiant : {_cfg_valeur!r}. "
            f"Format attendu : {_cfg_exemple}. Laisser vide pour désactiver.")

# Le bandeau de consentement n'a de raison d'être que s'il y a quelque chose à
# faire consentir. Sans identifiant, il ne s'affiche pas — et la phrase de la
# page Confidentialité qui promet l'absence de mesure reste vraie.
_MESURE_ACTIVE = bool(_GTM_ID or _GA4_ID)


# Mentions légales : l'éditeur et le directeur de la publication ne peuvent pas
# être devinés, et une mention légale à moitié remplie vaut moins qu'une ligne
# absente. Ils viennent donc de `.env` et la page ne les affiche que s'ils sont
# renseignés. L'hébergeur a une valeur par défaut parce qu'elle est factuelle :
# le VPS de production est chez Hostinger (docs/infrastructure.md).
_MENTIONS = {
    "editeur": os.environ.get("MENTIONS_EDITEUR", "").strip(),
    "directeur": os.environ.get("MENTIONS_DIRECTEUR", "").strip(),
    # L'adresse publique du site, elle, a une valeur par defaut : ce n'est pas
    # une donnee a deviner mais la boite aux lettres du service, et une page de
    # mentions legales sans moyen de contact ne remplit pas son office. La v1
    # ecrivait `privacy@` ; la proprietaire a demande le 17/09/2026 que tout
    # passe par `contact@`, une seule adresse a relever.
    "contact": os.environ.get(
        "MENTIONS_CONTACT", "contact@motocomparo.com").strip(),
    "hebergeur": os.environ.get(
        "MENTIONS_HEBERGEUR",
        "Hostinger International Ltd, 61 Lordou Vironos, 6023 Larnaca, Chypre "
        "— serveurs situés en France.").strip(),
}


# Les seuls sujets acceptés. Ailleurs qu'ici, la valeur vient du navigateur.
SUJETS_CONTACT = frozenset({"erreur-prix", "erreur-fiche", "marchand", "autre"})


@app.get("/contact", response_class=HTMLResponse)
def contact(request: Request, envoye: int = 0):
    return templates.TemplateResponse(
        request, "contact.html", _ctx(request, envoye=envoye))


def _notifier_contact(sujet: str, corps: str, email: str, page: str) -> None:
    """Prévient par e-mail qu'un message est arrivé — en plus de l'écrire en
    base, jamais à sa place : `/admin` reste la source, cette notification
    peut échouer sans rien perdre.

    Désactivée tant que `SMTP_HOST` est vide dans `.env` (c'est le cas par
    défaut) : pas de serveur d'envoi configuré, pas de tentative, aucune
    erreur. Une seule boîte sert à tout — envoi et réception — via Hostinger
    Mail, SSL implicite sur le port 465.

    Jamais laissée faire échouer l'enregistrement du message : un problème
    réseau ou des identifiants faux ne doivent coûter qu'une notification
    manquée, pas le message lui-même, déjà écrit en base avant cet appel.
    """
    # L'envoi lui-même vit dans `mcpipe.courriel`, partagé avec les alertes de
    # prix ; il se tait sans configuration et n'émet jamais d'exception.
    if not courriel.configure():
        return
    dest = os.environ.get("CONTACT_NOTIF_TO", "").strip() or courriel.expediteur()
    libelles = {
        "erreur-prix": "Un prix qui ne correspond pas",
        "erreur-fiche": "Une fiche mal rangée ou en double",
        "marchand": "Je suis un marchand",
        "autre": "Autre",
    }
    # Délai court (8 s par défaut) et volontaire : un serveur SMTP qui ne
    # répond pas ne doit pas faire attendre le visiteur sur sa confirmation.
    # `repondre_a` : répondre à CE message répond directement au visiteur,
    # sans passer par la boîte de contact — seulement s'il a laissé une adresse.
    courriel.envoyer(
        dest, f"[Contact MotoComparo] {libelles.get(sujet, sujet)}",
        f"{corps}\n\n---\n"
        f"E-mail laissé : {email or '(aucun)'}\n"
        f"Page : {page or '(inconnue)'}\n"
        f"Lu et répondu depuis /admin sur le site.",
        repondre_a=email)


def _origine_refusee(request: Request) -> bool:
    """Un formulaire posté depuis un autre site n'a rien à faire ici. L'absence
    d'Origin (vieux navigateurs, logiciels de messagerie) reste acceptée."""
    origine = request.headers.get("origin")
    return bool(origine and origine not in ("https://motocomparo.com",
                                            "https://www.motocomparo.com")
                and not _reseau_local(request.client.host if request.client else ""))


@app.post("/contact")
async def contact_envoi(request: Request):
    """Enregistre le message, puis tente de prévenir par e-mail.

    Une adresse en clair sur une page publique est aspirée en quelques jours :
    le message est donc TOUJOURS écrit en base et relu depuis le tableau de
    bord, que la notification par e-mail (`_notifier_contact`) réussisse ou
    non. `parse_qs` plutôt que `Form()` pour ne pas dépendre de
    python-multipart, absent de l'environnement.
    """
    if _origine_refusee(request):
        return PlainTextResponse("Origine refusée.", status_code=403)

    brut = await request.body()
    if len(brut) > 16_000:
        return RedirectResponse("/contact?envoye=2", status_code=303)
    d = parse_qs(brut.decode("utf-8", "replace"))
    prendre = lambda k: (d.get(k, [""])[0] or "").strip()  # noqa: E731
    if prendre("site_web"):
        # champ piège rempli : un robot. On lui répond comme à un humain pour
        # ne pas lui apprendre ce qui l'a trahi.
        return RedirectResponse("/contact?envoye=1", status_code=303)
    corps = prendre("corps")
    if len(corps) < 10:
        # Le `minlength` du gabarit n'engage que le navigateur ; un envoi refusé
        # doit se dire, pas répondre « bien reçu » à ce qu'on a jeté.
        return RedirectResponse("/contact?envoye=2", status_code=303)

    # Le <select> n'engage lui aussi que le navigateur : un envoi fabriqué à la
    # main peut porter n'importe quel sujet, de la taille du corps de requête.
    # La liste close est la seule borne qui tienne.
    sujet = prendre("sujet")
    if sujet not in SUJETS_CONTACT:
        sujet = "autre"
    email_visiteur = prendre("email")[:190]
    page_origine = request.headers.get("referer", "")[:300]
    with pool.connection() as conn:  # type: ignore[union-attr]
        conn.execute(
            "INSERT INTO message_contact (sujet, corps, email, page) "
            "VALUES (%s, %s, nullif(%s, ''), %s)",
            (sujet, corps[:4000], email_visiteur, page_origine),
        )
        # La durée promise sous le formulaire : 12 mois après réception.
        # Faite ici, à chaque nouveau message, plutôt que par un minuteur de
        # plus — une requête sur une table de quelques lignes.
        conn.execute("DELETE FROM message_contact "
                     "WHERE recu_le < now() - interval '12 months'")
    # APRÈS le commit implicite de l'INSERT (connexion en autocommit) : le
    # message est déjà écrit en base, quoi qu'il arrive à la notification.
    _notifier_contact(sujet, corps[:4000], email_visiteur, page_origine)
    return RedirectResponse("/contact?envoye=1", status_code=303)


# --- les alertes de baisse de prix -------------------------------------------
#
# Les règles (ce qu'est une baisse, les plafonds, les durées) sont dans
# `mcpipe/alertes.py`, lues aussi par l'envoi de nuit. Ici : le formulaire de la
# fiche et les pages où mènent les liens des e-mails.
#
# Les pages qui portent un jeton ne chargent JAMAIS la mesure d'audience
# (`mesure_active=False`) et demandent qu'aucun référent ne parte : l'adresse
# complète, jeton compris, finirait sinon chez Google. `no-store` : nginx ne
# les met pas en cache (il respecte cet en-tête), aucune ne doit être resservie
# à un autre visiteur.

_EMAIL_RE = re.compile(r"[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s.]{2,24}")


def _page_alerte(request: Request, etat: str, **extra: Any) -> HTMLResponse:
    # La carte produit (photo, nom, prix) : seulement sur cette PAGE, jamais
    # dans l'e-mail — une image distante dans un e-mail est un pixel de suivi
    # d'ouverture, exactement ce que `/infos#donnees` promet de ne pas faire.
    # Repérée par la propriétaire comme manquante (15/10/2026) : la page,
    # elle, n'a pas cette contrainte.
    produit = None
    slug = extra.get("slug")
    if slug:
        with pool.connection() as conn:  # type: ignore[union-attr]
            produit = queries.product(conn, slug)
    return templates.TemplateResponse(
        request, "alerte.html",
        _ctx(request, etat=etat, mesure_active=False, produit=produit,
             duree_vie=alertes_prix.DUREE_VIE_TEXTE,
             attente=alertes_prix.ATTENTE_TEXTE, **extra),
        headers=_SANS_CACHE)


def _prix_saisi(texte: str) -> Decimal | None | bool:
    """« 89,90 € » → Decimal('89.90'). Vide → None. Illisible ou hors bornes →
    False : on le dit au visiteur plutôt que d'ignorer son seuil en silence."""
    texte = texte.replace("€", "").replace(" ", "").replace(" ", "").replace(",", ".")
    if not texte:
        return None
    try:
        v = Decimal(texte).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return False
    return v if Decimal("0") < v <= Decimal("100000") else False


@app.post("/alertes")
async def alerte_demande(request: Request):
    """Le formulaire « Prévenez-moi si le prix baisse » de la fiche.

    Mêmes protections que le contact : Origin, corps borné, champ piège
    `site_web`, `parse_qs` (pas de python-multipart). La réponse est la MÊME
    que l'adresse soit nouvelle, déjà inscrite ou au plafond — voir
    `alertes_prix.enregistrer_demande`.

    404 tant que l'envoi d'e-mails n'est pas configuré : le formulaire n'est
    alors affiché nulle part, et un envoi fabriqué à la main n'enregistrerait
    qu'une adresse à qui l'on ne pourrait jamais écrire.
    """
    if not courriel.configure():
        raise StarletteHTTPException(status_code=404)
    if _origine_refusee(request):
        return PlainTextResponse("Origine refusée.", status_code=403)
    brut = await request.body()
    if len(brut) > 4_000:
        return _page_alerte(request, "refus")
    d = parse_qs(brut.decode("utf-8", "replace"))
    prendre = lambda k: (d.get(k, [""])[0] or "").strip()  # noqa: E731
    slug = prendre("produit")[:200]
    if prendre("site_web"):
        # Un robot : la réponse d'un humain, pour ne rien lui apprendre.
        return RedirectResponse(f"/alertes/demande?p={quote_plus(slug)}", status_code=303)
    email = prendre("email").lower()[:254]
    if not _EMAIL_RE.fullmatch(email):
        return _page_alerte(request, "adresse", slug=slug)
    prix_cible = _prix_saisi(prendre("prix_cible"))
    if prix_cible is False:
        return _page_alerte(request, "prix", slug=slug)
    taille = prendre("taille")[:60] or None

    with pool.connection() as conn:  # type: ignore[union-attr]
        p = queries.product(conn, slug)
        if p is None:
            raise HTTPException(404, "Produit inconnu")
        # La taille doit être l'un des boutons de la fiche, calculés comme la
        # fiche les calcule : un libellé inventé ne correspondrait jamais à
        # rien et l'alerte resterait muette six mois.
        if taille:
            rows = queries.offers(conn, p["id"])
            fusion = labels.equivalences_tailles(rows)
            permises = {fusion.get(labels.size_display(o["size_code"]), "") for o in rows}
            if taille not in permises - {""}:
                return _page_alerte(request, "refus", slug=slug)
        # Le prix de référence est relu ici, en base, jamais pris dans le
        # formulaire : c'est lui qui décide de ce qu'est « une baisse ».
        offres = alertes_prix.offres_achetables(conn, [slug])[slug]
        o = alertes_prix.meilleure(offres, taille)
        reference = o["price"] if o else None
        # Un seuil déjà atteint aujourd'hui n'apprendrait rien demain : il
        # devient « toute baisse sous le prix du jour ».
        if prix_cible is not None and reference is not None and prix_cible >= reference:
            prix_cible = None
        # Les effacements promis, faits aussi ici : une table de quelques
        # lignes, pas besoin d'attendre la nuit.
        alertes_prix.purger(conn)
        jeton = alertes_prix.enregistrer_demande(
            conn, email=email, slug=slug, taille=taille,
            prix_cible=prix_cible, prix_reference=reference)

    if jeton:
        sujet, corps, html = alertes_prix.courriel_confirmation(
            titre=_nom(p), taille=taille, prix_cible=prix_cible,
            prix_actuel=reference, jeton=jeton)
        if not courriel.envoyer(email, sujet, corps, html=html):
            # Rien n'est parti : on ne garde pas une adresse à laquelle on n'a
            # pas pu écrire, et on le dit — sans rien révéler de l'adresse.
            with pool.connection() as conn:  # type: ignore[union-attr]
                conn.execute("DELETE FROM alerte_prix WHERE jeton = %s "
                             "AND confirme_le IS NULL AND envois = 1", (jeton,))
            return _page_alerte(request, "envoi", slug=slug)
    return RedirectResponse(f"/alertes/demande?p={quote_plus(slug)}", status_code=303)


@app.get("/alertes/demande", response_class=HTMLResponse)
def alerte_demandee(request: Request, p: str = ""):
    return _page_alerte(request, "demande", slug=p[:200])


def _jeton(valeur: str) -> str:
    # `token_urlsafe(32)` fait 43 caractères ; tout le reste est rejeté avant
    # d'atteindre la base.
    v = (valeur or "").strip()
    return v if re.fullmatch(r"[A-Za-z0-9_-]{20,100}", v) else ""


async def _jeton_poste(request: Request) -> str:
    brut = await request.body()
    if len(brut) > 1_000:
        return ""
    return _jeton(parse_qs(brut.decode("utf-8", "replace")).get("jeton", [""])[0])


@app.get("/alertes/confirmer", response_class=HTMLResponse)
def alerte_confirmer_page(request: Request, jeton: str = ""):
    """Le lien de l'e-mail de confirmation mène à un BOUTON, pas à la
    confirmation elle-même : les filtres anti-spam ouvrent les liens des
    e-mails pour les inspecter, et confirmeraient l'alerte à la place de la
    personne — le double opt-in ne prouverait plus rien."""
    jeton = _jeton(jeton)
    a = None
    if jeton:
        with pool.connection() as conn:  # type: ignore[union-attr]
            a = conn.execute(
                "SELECT produit_slug, confirme_le IS NOT NULL AS active FROM alerte_prix "
                "WHERE jeton = %s AND (confirme_le IS NOT NULL OR cree_le > now() - "
                f"interval '{alertes_prix.ATTENTE_CONFIRMATION}')", (jeton,)).fetchone()
    if a is None:
        return _page_alerte(request, "inconnu")
    if a[1]:
        return _page_alerte(request, "active", slug=a[0], jeton=jeton)
    return _page_alerte(request, "a-confirmer", slug=a[0], jeton=jeton)


@app.post("/alertes/confirmer", response_class=HTMLResponse)
async def alerte_confirmer(request: Request):
    if _origine_refusee(request):
        return PlainTextResponse("Origine refusée.", status_code=403)
    jeton = await _jeton_poste(request)
    a = None
    if jeton:
        with pool.connection() as conn:  # type: ignore[union-attr]
            a = conn.execute(
                "UPDATE alerte_prix SET confirme_le = coalesce(confirme_le, now()) "
                "WHERE jeton = %s AND (confirme_le IS NOT NULL OR cree_le > now() - "
                f"interval '{alertes_prix.ATTENTE_CONFIRMATION}') "
                "RETURNING produit_slug", (jeton,)).fetchone()
    if a is None:
        return _page_alerte(request, "inconnu")
    return _page_alerte(request, "active", slug=a[0], jeton=jeton)


def _arreter(jeton: str) -> str | None:
    if not jeton:
        return None
    with pool.connection() as conn:  # type: ignore[union-attr]
        a = conn.execute("DELETE FROM alerte_prix WHERE jeton = %s RETURNING produit_slug",
                         (jeton,)).fetchone()
    return a[0] if a else None


@app.get("/alertes/arreter", response_class=HTMLResponse)
def alerte_arreter_lien(request: Request, jeton: str = ""):
    """Désinscription en UN clic, comme promis dans chaque e-mail : le lien
    suffit, sans bouton à confirmer. L'alerte est EFFACÉE, pas désactivée."""
    slug = _arreter(_jeton(jeton))
    return _page_alerte(request, "arretee" if slug else "inconnu", slug=slug or "")


@app.post("/alertes/arreter")
async def alerte_arreter(request: Request):
    """Le « se désabonner » des logiciels de messagerie (RFC 8058) : un POST
    envoyé par le serveur de Gmail ou d'Outlook, sans Origin, avec le jeton
    dans l'adresse. Accepté aussi depuis la page, jeton dans le corps."""
    if _origine_refusee(request):
        return PlainTextResponse("Origine refusée.", status_code=403)
    jeton = _jeton(request.query_params.get("jeton", "")) or await _jeton_poste(request)
    slug = _arreter(jeton)
    return _page_alerte(request, "arretee" if slug else "inconnu", slug=slug or "")


@app.get("/alertes/tout-supprimer", response_class=HTMLResponse)
def alerte_tout_supprimer_page(request: Request, jeton: str = ""):
    """Effacer TOUTES les alertes d'une adresse passe par un bouton : un
    filtre anti-spam qui ouvre le lien ne doit pas tout effacer à la place
    de la personne."""
    jeton = _jeton(jeton)
    n = 0
    if jeton:
        with pool.connection() as conn:  # type: ignore[union-attr]
            n = conn.execute(
                "SELECT count(*) FROM alerte_prix WHERE email = "
                "(SELECT email FROM alerte_prix WHERE jeton = %s)", (jeton,)).fetchone()[0]
    if not n:
        return _page_alerte(request, "inconnu")
    return _page_alerte(request, "tout-confirmer", jeton=jeton, nombre=n)


@app.post("/alertes/tout-supprimer", response_class=HTMLResponse)
async def alerte_tout_supprimer(request: Request):
    if _origine_refusee(request):
        return PlainTextResponse("Origine refusée.", status_code=403)
    jeton = await _jeton_poste(request)
    n = 0
    if jeton:
        with pool.connection() as conn:  # type: ignore[union-attr]
            n = conn.execute(
                "DELETE FROM alerte_prix WHERE email = "
                "(SELECT email FROM alerte_prix WHERE jeton = %s)", (jeton,)).rowcount
    return _page_alerte(request, "tout-efface" if n else "inconnu", nombre=n)


# --- ce qui rend le site trouvable ------------------------------------------
#
# Absent jusqu'au 15/09/2026. Un comparateur qu'aucun moteur ne sait parcourir
# n'a pas de raison d'exister : c'est par la recherche que ses visiteurs
# arrivent, fiche par fiche.

@app.get("/api/suggestions")
def api_suggestions(request: Request, q: str = "") -> Response:
    """Ce que la barre de recherche propose pendant la frappe.

    Deux sources, et c'est tout l'intérêt du découpage :

    - la ventilation **marque × rayon** est précalculée et gardée au chaud
      (711 lignes, 70 Ko) : le filtrage s'y fait en mémoire, sans toucher la
      base. Une requête par frappe coûtait 130 ms de balayage, parce que
      `f_unaccent(brand_code)` interdit l'index ;
    - les **produits** viennent de la base, mais servis par l'index de
      trigrammes et mis en cache par texte tapé — deux visiteurs qui cherchent
      « shoei » ne la font travailler qu'une fois.

    `no-store` : la liste dépend de ce qu'on est en train de taper, elle n'a
    aucune raison d'être gardée par nginx ni par le navigateur.
    """
    texte = (q or "").strip()[:60]
    if len(suggestions.sans_accent(texte)) < suggestions.MINIMUM:
        return JSONResponse({"marques": [], "entonnoir": [], "rayons": [],
                             "produits": []},
                            headers={"Cache-Control": "no-store"})

    def _matiere() -> tuple:
        with pool.connection() as conn:  # type: ignore[union-attr]
            return queries.marques_par_rayon(conn), queries.categories(conn)

    matrice, arbre = cache.au_chaud("suggestions|matiere", _matiere)

    # `categories()` rend un arbre : on l'aplatit pour chercher aussi dans les
    # sous-rayons (« Casques intégraux » autant que « Casques »).
    plats: list[dict[str, Any]] = []
    for parent in arbre:
        plats.append(parent)
        plats.extend(parent.get("enfants") or [])

    # LA MARQUE D'ABORD. La reconnaître change tout ce qui suit : on ne cherche
    # plus dans 313 000 fiches mais dans les quelques centaines de cette marque,
    # et on peut donc y classer par ressemblance SANS seuil. C'est ce qui permet
    # à « arai zzr » de trouver le SZ-R, dont « zzr » n'est qu'à 0,14 de
    # ressemblance — bien trop peu pour franchir un seuil, largement assez pour
    # arriver premier parmi 147 Arai.
    noms = sorted({ligne["marque"] for ligne in matrice})
    tapes = suggestions.mots(texte)
    marque, restants = suggestions.reconnaitre_marque(tapes, noms)

    # PUIS LE RAYON ET SES FILTRES : « gant hiver » est le rayon Gants, saison
    # hiver — une liste qui existe déjà, avec son compte. On y cherche les
    # produits au lieu de chercher les mots dans les titres.
    lu = suggestions.comprendre(restants)
    noeud = queries.find_category(arbre, lu["rayon"]) if lu["rayon"] else None
    ids_par_code = {r["code"]: r["id"] for r in plats}
    accessoires = {ids_par_code[c] for c in _RAYONS_ACCESSOIRES if c in ids_par_code}

    def _dans_le_rayon(conn) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
        filtres = dict(lu["filtres"])
        restes = list(lu["restants"])
        for essai in range(2):
            f = queries.Filtres(categories=noeud["ids"],
                                marque=[marque] if marque else None,
                                texte=" ".join(restes) or None,
                                matiere=filtres.get("matiere"),
                                homologation=filtres.get("homologation"),
                                saison=filtres.get("saison"),
                                genre=filtres.get("genre"))
            # Gardé par COMBINAISON et non par texte tapé : « gant hiver »,
            # « gants hiver » et « Gant Hiver » sont la même liste, et son
            # compte coûte 0,6 à 1,5 s à froid en production (16/10/2026).
            fiches, n = cache.au_chaud(f"suggestions-rayon|{f}",
                                       lambda: queries.listing_filtre(conn, f, 40, 0),
                                       ttl=3600)
            if n or not filtres:
                break
            # Un filtre que le rayon n'a pas (« casque cuir ») : le mot
            # redevient un mot cherché, plutôt qu'une liste vide.
            restes += list(filtres.values())
            filtres = {}
        if not n:
            return None
        morceaux = [noeud["label_fr"]]
        morceaux += [queries.GENRES[v] if p == "genre" else queries.libelle_filtre(p, v)
                     for p, v in filtres.items()]
        if marque:
            morceaux.append(marque.upper())
        params = {**({"marque": marque} if marque else {}), **filtres}
        if restes:
            params["q"] = " ".join(restes)
        url = f"/c/{noeud['code']}" + (f"?{urlencode(params)}" if params else "")
        compris = {"code": noeud["code"], "label": " · ".join(morceaux),
                   "filtres": filtres, "url": url, "n": n}
        return fiches, compris

    def _produits() -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        with pool.connection() as conn:  # type: ignore[union-attr]
            if noeud:
                dedans = _dans_le_rayon(conn)
                if dedans:
                    fiches, compris = dedans
                    if not marque:
                        fiches = suggestions.varier(fiches)
                    return suggestions.regrouper(fiches, 8), compris
            # Vingt-quatre, regroupées ensuite en huit : trois partent en grand
            # format, il doit rester de quoi remplir « Autres produits ».
            # Rayon compris mais vide (« casque bluetooth » : aucun casque ne
            # s'appelle ainsi) : on cherche les mots qui restent, sans le mot
            # du rayon — c'est un intercom qu'on veut, pas un casque.
            hors_rayon = (lu["restants"] + list(lu["filtres"].values())) if noeud else []
            if marque:
                fiches = queries.produits_dans_la_marque(conn, marque, restants, 24)
            else:
                fiches = queries.produits_suggeres(conn, hors_rayon or tapes, 24)
            # L'ACCESSOIRE APRÈS LE PRODUIT. « shoei neotec » mettait une
            # bavette et trois écrans devant le casque : à ressemblance égale,
            # le nom du modèle est dans les deux titres. Pénalité d'un
            # demi-mot seulement : qui tape « ecran » est déjà conduit au
            # rayon des pièces de casque par `comprendre`.
            fiches.sort(key=lambda p: -(float(p.get("score") or 0) - (
                0.5 if (p.get("category_id") in accessoires
                        or suggestions.est_accessoire(p.get("best_title"))) else 0)))
            if not marque:
                fiches = suggestions.varier(fiches)
            return suggestions.regrouper(fiches, 8), None

    trouves, compris = cache.au_chaud(f"suggestions|{texte.lower()}", _produits, ttl=300)

    return JSONResponse(
        suggestions.construire(texte, matrice, plats, trouves, _nom,
                               marque, restants, compris),
        headers={"Cache-Control": "no-store"},
    )


# Les rayons dont un produit accompagne un autre : passés après les produits
# principaux dans les suggestions, à ressemblance égale.
_RAYONS_ACCESSOIRES = ("helmet.accessory", "accessories", "maintenance")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Le navigateur réclame `/favicon.ico` quoi qu'on déclare dans l'entête.

    L'entête annonce bien `favicon.svg`, mais tout navigateur demande d'abord
    cette adresse-là, à la racine, sans lire la page — et la journalisation du
    site portait un 404 sous CHAQUE visite. Un 404 qu'on s'explique est un 404
    qu'on finit par ne plus lire, y compris le jour où il en cache un vrai.

    Redirection permanente vers le vrai `.ico` servi par ailleurs dans
    `/static` : le navigateur ne redemande plus après la première fois.
    """
    return RedirectResponse("/static/favicon.ico", status_code=301)


@app.get("/google91d87112b2771314.html", response_class=PlainTextResponse)
def verification_google() -> str:
    """Preuve de propriete pour Google Search Console.

    Ne pas supprimer : Google revalide periodiquement ce fichier pour
    conserver le statut de proprietaire confirme.
    """
    return "google-site-verification: google91d87112b2771314.html"


# --- les adresses de l'ancien site (v1) -------------------------------------
# Voir `v1.py` : 301 vers ce qui les remplace, 410 pour la mécanique WordPress.

def _marques_v1() -> tuple[set[str], set[str]]:
    """Toutes les marques, et celles qui ont une page (`/m/…` sinon 404)."""
    def _calcul() -> tuple[set[str], set[str]]:
        with pool.connection() as conn:  # type: ignore[union-attr]
            toutes = {r[0] for r in conn.execute(
                "SELECT DISTINCT brand_code FROM product "
                "WHERE brand_code <> '' AND status <> 'merged'")}
            listees = {r[0] for r in conn.execute(
                "SELECT DISTINCT p.brand_code FROM product p "
                "JOIN product_stats s ON s.product_id = p.id "
                "WHERE s.merchant_count >= 2 AND s.cheapest IS NOT NULL "
                "AND p.status <> 'merged' AND p.brand_code <> ''")}
        return toutes, listees
    return cache.au_chaud("v1-marques", _calcul, ttl=6 * 3600)


def _candidates_v1(marque: str, texte: str) -> list[tuple[str, float, str]]:
    """Les fiches vivantes de la marque qui ressemblent le plus à l'ancienne adresse."""
    with pool.connection() as conn:  # type: ignore[union-attr]
        rows = conn.execute("""
            SELECT p.slug, similarity(f_recherche(s.best_title), %(t)s), s.best_title
            FROM product p JOIN product_stats s ON s.product_id = p.id
            WHERE p.brand_code = %(m)s AND p.status <> 'merged'
              AND s.cheapest IS NOT NULL AND s.best_title IS NOT NULL
            ORDER BY 2 DESC LIMIT 5""", {"m": marque, "t": texte}).fetchall()
    return [(r[0], float(r[1]), r[2]) for r in rows]


# Une ancienne adresse donne toujours la même cible dans la journée : gardée
# à part, hors de `cache.py`, dont les 400 places servent aux listes et que
# 4 500 anciennes fiches videraient.
@lru_cache(maxsize=8192)
def _cible_fiche_v1(chemin: str) -> str:
    toutes, listees = _marques_v1()
    return v1_mod.cible_fiche_v1(chemin, toutes, listees, _candidates_v1)


@app.get("/product/{chemin:path}")
def v1_fiche(chemin: str):
    return RedirectResponse(_cible_fiche_v1(chemin), status_code=301)


@app.get("/product-category/{chemin:path}")
def v1_rayon(chemin: str):
    return RedirectResponse(v1_mod.cible_rayon_v1(chemin), status_code=301)


@app.get("/shop")
@app.get("/shop/{chemin:path}")
def v1_boutique(request: Request, chemin: str = ""):
    # Trois formes dans les journaux : `/shop/?mc_type=…` (filtres),
    # `/shop/gants/` (un rayon) et `/shop/blousons/veste-de-pluie-…/` (une
    # fiche rangée sous son rayon).
    morceaux = [m for m in chemin.strip("/").split("/")
                if m and m != "page" and not m.isdigit()]
    if len(morceaux) >= 2:
        return RedirectResponse(_cible_fiche_v1(morceaux[-1]), status_code=301)
    if len(morceaux) == 1 and morceaux[0] in v1_mod.RAYONS_V1_CONNUS:
        return RedirectResponse(v1_mod.cible_rayon_v1(morceaux[0]), status_code=301)
    cible = v1_mod.cible_boutique_v1(dict(request.query_params), _marques_v1()[1])
    return RedirectResponse(cible, status_code=301)


# Les articles du blog v1 (`/2026/08/05/rouler-en-securite…/`) : la rubrique
# qui les remplace.
@app.get("/2025/{chemin:path}")
@app.get("/2026/{chemin:path}")
def v1_article(chemin: str):
    return RedirectResponse("/guides", status_code=301)


def _redirection_fixe(cible: str):
    def route():
        return RedirectResponse(cible, status_code=301)
    return route


for _ancienne, _cible in v1_mod.REDIRECTIONS_FIXES.items():
    # Les deux écritures : sans la seconde, `/about/` passait d'abord par la
    # redirection automatique vers `/about`, soit deux sauts au lieu d'un.
    for _forme in (_ancienne, _ancienne + "/"):
        if not _forme.endswith(".xml/"):
            app.add_api_route(_forme, _redirection_fixe(_cible), methods=["GET"])


# La mécanique de WordPress (`wp-cron.php`, `xmlrpc.php`, `wp-json`, les flux,
# le compte client) n'a jamais été une page : 410 « disparu pour de bon », que
# Google retire plus vite qu'un 404 et cesse de redemander.
def _disparu():
    return PlainTextResponse("Cette adresse de l'ancien site n'existe plus.", status_code=410)


for _motif in ("/wp-{reste:path}", "/xmlrpc.php", "/feed", "/feed/",
               "/comments/feed", "/comments/feed/", "/my-account",
               "/my-account/{reste:path}",
               # Les plans du site de WordPress/Yoast : Googlebot en redemande
               # encore (product-sitemap84.xml, le 16/10/2026). Le nôtre est
               # /sitemap.xml, annoncé dans robots.txt.
               "/sitemap_index.xml", "/{type}-sitemap.xml",
               "/{type}-sitemap{n}.xml", "/{type}-sitemap{n}.xml/"):
    app.add_api_route(_motif, _disparu, methods=["GET", "POST"])


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots(request: Request) -> str:
    """Ce qu'un robot a le droit de parcourir.

    On ferme ce qui n'a aucun sens pour un moteur : le comparateur et les
    favoris vivent dans le navigateur du visiteur et seraient vides ; `/admin`
    n'est pas public ; `/fragment` rend des morceaux de page sans en-tête.
    """
    base = f"{request.url.scheme}://{request.url.netloc}"
    return "\n".join([
        # Le robot d'entraînement de Meta explorait les filtres sans fin et
        # saturait le serveur (audit du 30/09/2026). nginx le refuse aussi.
        "User-agent: meta-externalagent",
        "Disallow: /",
        "",
        "User-agent: *",
        "Disallow: /admin",
        "Disallow: /comparer",
        "Disallow: /fragment/",
        # Les FILTRES sont fermés : ils se combinent sans fin, et un robot qui
        # explore mille fourchettes de prix n'a plus le temps de voir les
        # fiches. Aucune fiche n'est perdue pour autant — toutes celles qui ont
        # au moins deux marchands sont dans le plan du site.
        "Disallow: /*?marque=",
        "Disallow: /*?prix_min=",
        "Disallow: /*?prix_max=",
        "Disallow: /*?taille=",
        "Disallow: /*?couleur=",
        # Les anciennes adresses de la v1 restent ouvertes MÊME avec ces
        # paramètres (`/product/…/?taille=171924`) : elles ne rendent qu'une
        # redirection, et Google ne peut la suivre que s'il a le droit de la
        # demander. 72 anciennes fiches étaient bloquées ainsi (Search
        # Console, 15/10/2026). Règle plus longue que les Disallow ci-dessus :
        # chez Google, la plus longue l'emporte.
        "Allow: /product/*?taille=",
        "Allow: /shop/*?taille=",
        "Allow: /product-category/*?taille=",
        # La PAGINATION, elle, reste ouverte, et c'est volontaire. Les pages 2
        # et suivantes portent `noindex, follow` : « ne range pas cette page
        # dans l'index, mais suis les liens qu'elle contient ». Les fermer ici
        # rendrait cette consigne illisible — un robot à qui on interdit de
        # parcourir la page ne peut pas y lire le `noindex`, et le `follow` ne
        # sert plus à rien. C'est l'erreur classique : interdire ET marquer
        # `noindex` sont deux ordres qui s'annulent.
        "",
        f"Sitemap: {base}/sitemap.xml",
        "",
    ])


# 20 000 adresses par fichier : la limite du format est 50 000, on garde de la
# marge pour que le catalogue puisse grossir sans changer la structure.
_PAR_SITEMAP = 20_000


def _urls_sitemap() -> list[str]:
    """Les adresses à proposer aux moteurs.

    **Seules les fiches réellement comparables y figurent** — deux marchands au
    moins. Les 280 000 autres restent accessibles par leur adresse (décision de
    la propriétaire : publier ce qui a un vrai lien), mais les proposer à
    l'indexation noierait les 28 000 qui font l'intérêt du site sous des pages à
    un seul marchand, où il n'y a rien à comparer.
    """
    def _calcul() -> list[str]:
        with pool.connection() as conn:  # type: ignore[union-attr]
            rows = conn.execute("""
                SELECT p.slug FROM product p
                JOIN product_stats s ON s.product_id = p.id
                WHERE p.status <> 'merged' AND s.merchant_count >= 2
                  AND s.cheapest IS NOT NULL
                ORDER BY s.merchant_count DESC, s.product_id
            """).fetchall()
            rayons = conn.execute(
                "SELECT code FROM category WHERE id <> %s ORDER BY code",
                (queries.UNCLASSIFIED_ID,)).fetchall()
            # Les pages marques manquaient au plan (15/10/2026). Même règle
            # que les fiches : seulement les marques qui ont de quoi comparer —
            # cinq fiches à deux marchands au moins. Une page « Marque X » à
            # une seule fiche comparable n'apporte rien à qui la trouve.
            marques = conn.execute("""
                SELECT p.brand_code FROM product p
                JOIN product_stats s ON s.product_id = p.id
                WHERE p.status <> 'merged' AND s.merchant_count >= 2
                  AND s.cheapest IS NOT NULL AND p.brand_code <> 'unknown'
                GROUP BY p.brand_code HAVING count(*) >= 5
                ORDER BY count(*) DESC
            """).fetchall()
        fixes = ["/", "/produits", "/bons-plans", "/marques", "/guides",
                 "/infos", "/contact"]
        # Les articles PUBLIÉS seulement : un brouillon répond 404 en
        # production, le proposer aux moteurs serait leur donner une erreur.
        fixes += [f"/guides/{a.slug}" for a in articles_mod.publies()]
        return (fixes
                + [f"/c/{r[0]}" for r in rayons]
                + [f"/m/{r[0]}" for r in marques]
                + [f"/p/{r[0]}" for r in rows])

    return cache.au_chaud("sitemap", _calcul, ttl=6 * 3600)


@app.get("/sitemap.xml")
def sitemap_index(request: Request) -> Response:
    """L'index : la liste des fichiers, pas les adresses elles-mêmes."""
    base = f"{request.url.scheme}://{request.url.netloc}"
    n = max(1, -(-len(_urls_sitemap()) // _PAR_SITEMAP))
    jour = date.today().isoformat()
    corps = "".join(
        f"<sitemap><loc>{base}/sitemap-{i}.xml</loc>"
        f"<lastmod>{jour}</lastmod></sitemap>"
        for i in range(1, n + 1))
    return Response(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{corps}</sitemapindex>",
        media_type="application/xml")


@app.get("/sitemap-{numero}.xml")
def sitemap_page(request: Request, numero: int) -> Response:
    # un numéro négatif lisait une tranche depuis la FIN : un doublon valide
    if numero < 1:
        raise HTTPException(404, "Ce fichier de plan n'existe pas")
    urls = _urls_sitemap()
    debut = (numero - 1) * _PAR_SITEMAP
    lot = urls[debut:debut + _PAR_SITEMAP]
    if not lot:
        raise HTTPException(404, "Ce fichier de plan n'existe pas")
    base = f"{request.url.scheme}://{request.url.netloc}"
    jour = date.today().isoformat()
    corps = "".join(
        f"<url><loc>{base}{u}</loc><lastmod>{jour}</lastmod></url>" for u in lot)
    return Response(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{corps}</urlset>",
        media_type="application/xml")


@app.get("/infos", response_class=HTMLResponse)
def infos(request: Request):
    """What the site does, and how, in the visitor's words.

    A comparison site lives on being believed, and three things have to be said
    plainly for that: the links are affiliated, a price older than 24 hours is
    withheld rather than shown, and no account or tracking is involved. The page
    states only what the code actually does — nothing here is a promise the
    pipeline does not keep.
    """
    return templates.TemplateResponse(request, "infos.html",
                                      _ctx(request, mentions=_MENTIONS))


@app.get("/recherche", response_class=HTMLResponse)
def search(
    request: Request,
    q: str = "",
    page: int = Query(1, ge=1, le=_PAGE_MAX),
    marque: list[str] = Query([]),
    prix_min: float | None = Query(None, ge=0, le=100_000),
    prix_max: float | None = Query(None, ge=0, le=100_000),
    taille: list[str] = Query([]),
    couleur: str | None = None,
    matiere: str | None = None,
    homologation: str | None = None,
    saison: str | None = None,
    genre: str | None = None,
    marchands: int = Query(2, ge=2, le=6),
    tri: str = "pertinence",
):
    """Search results, filterable like every other listing.

    It used to be a page apart — no filter panel, no counts, no sort — so a
    search for "arai sz" returned forty helmets and left the visitor with
    nothing to narrow them down. The typed words are now a filter like any
    other, which also means they survive every click inside the panel.
    """
    # Un code-barres (EAN-8 à GTIN-14, chiffres uniquement) ne ressemble
    # jamais à un titre marchand : la recherche texte ci-dessous ne le
    # trouve jamais, même collé mot pour mot sur la bonne fiche. On le
    # cherche donc directement par code-barres, et on saute tout droit à la
    # fiche s'il y en a une — pas de page de résultats à un seul élément.
    code = q.strip()
    if code.isdigit() and 8 <= len(code) <= 14:
        with pool.connection() as conn:  # type: ignore[union-attr]
            slug = queries.slug_par_gtin(conn, code)
        if slug:
            return RedirectResponse(f"/p/{slug}", status_code=302)

    # UNE MARQUE OU UN RAYON TAPÉS, ET RIEN D'AUTRE : on y va directement.
    # « shoei » + Entrée coûtait 9,3 s à froid (liste ET panneau de filtres
    # recalculés sur un filtre texte), pour montrer moins bien ce que
    # /m/shoei montre déjà, avec son titre et ses filtres (16/10/2026). Même
    # lecture que les suggestions : « gant hiver » mène à Gants, saison hiver.
    # Seulement depuis la barre (q seul) : un filtre déjà posé dans le
    # panneau de la recherche ne doit pas être perdu.
    if set(request.query_params) == {"q"} and code:
        cible = _cible_recherche(code)
        if cible:
            return RedirectResponse(cible, status_code=302)

    f = queries.Filtres(texte=q.strip() or None, marque=marque,
                        prix_min=prix_min, prix_max=prix_max, taille=taille,
                        couleur=queries.couleur_simple(couleur),
                        matiere=queries.code_filtre(matiere),
                        homologation=queries.code_filtre(homologation),
                        saison=queries.code_filtre(saison),
                        genre=queries.code_filtre(genre),
                        marchands=marchands, tri=tri)
    titre = f"Recherche : {q}" if q.strip() else "Recherche"
    return _liste(request, titre, f"/recherche?q={quote_plus(q)}", f, page)

def _cible_recherche(texte: str) -> str | None:
    """La page de marque ou de rayon que désigne entièrement `texte`, ou rien."""
    matrice = _marques_par_rayon()
    noms = sorted({x["marque"] for x in matrice})
    marque, restants = suggestions.reconnaitre_marque(suggestions.mots(texte), noms)
    lu = suggestions.comprendre(restants)
    if lu["restants"]:
        return None
    if not lu["rayon"]:
        return f"/m/{marque}" if marque else None
    noeud = queries.find_category(_rayons(), lu["rayon"])
    if not noeud:
        return None
    params = {**({"marque": marque} if marque else {}), **lu["filtres"]}
    return f"/c/{noeud['code']}" + (f"?{urlencode(params)}" if params else "")


# --- ce que voit un visiteur quand quelque chose n'existe pas ----------------
#
# Par défaut, FastAPI renvoie du JSON : `{"detail":"Produit inconnu"}` sur fond
# blanc, sans logo, sans menu, sans porte de sortie. Et `?page=0` renvoyait un
# pavé technique en anglais. Ces deux écrans étaient atteignables depuis un lien
# du site lui-même.
_EXPLICATIONS = {
    404: "Cette page n'existe pas ou n'existe plus. Un produit disparaît quand"
         " plus aucun marchand ne le publie.",
    422: "L'adresse contient une valeur que nous ne savons pas lire — un numéro"
         " de page ou un prix, probablement.",
    500: "Quelque chose s'est mal passé de notre côté. Ce n'est pas vous.",
    503: "Beaucoup de visites en même temps : réessayez dans quelques secondes.",
}


def _page_erreur(request: Request, code: int, titre: str) -> HTMLResponse:
    explication = _EXPLICATIONS.get(code, _EXPLICATIONS[500])
    return templates.TemplateResponse(
        request, "erreur.html",
        _ctx(request, code=code, titre=titre, explication=explication),
        status_code=code,
    )


@app.exception_handler(StarletteHTTPException)
async def erreur_http(request: Request, exc: StarletteHTTPException):
    titres = {404: "Page introuvable", 405: "Action impossible"}
    return _page_erreur(request, exc.status_code if exc.status_code in (404, 405) else 500,
                        titres.get(exc.status_code, "Erreur"))


@app.exception_handler(PoolTimeout)
async def erreur_pool(request: Request, exc: PoolTimeout):
    """Toutes les connexions sont prises : une page claire en 5 s plutôt qu'une
    erreur brute de 21 octets au bout de 30 s. `Retry-After` et `no-store` pour
    que ni un robot ni nginx ne gardent cette réponse pour la vraie page."""
    try:
        reponse = _page_erreur(request, 503, "Site momentanément chargé")
    except PoolTimeout:
        # le menu n'était pas en cache et demandait lui aussi une connexion
        reponse = HTMLResponse(
            "<!doctype html><meta charset=utf-8><title>MotoComparo</title>"
            "<p>Le site est momentanément chargé. Réessayez dans quelques "
            "secondes.</p>", status_code=503)
    reponse.headers["Retry-After"] = "30"
    reponse.headers["Cache-Control"] = "no-store"
    return reponse


@app.exception_handler(Exception)
async def erreur_imprevue(request: Request, exc: Exception):
    """Toute erreur non prévue rend la page d'erreur du site, jamais la page
    texte brute de Starlette. L'erreur reste dans le journal."""
    import logging
    logging.getLogger("mcsite").exception("erreur non prévue sur %s", request.url.path)
    try:
        reponse = _page_erreur(request, 500, "Erreur")
    except Exception:  # noqa: BLE001
        reponse = PlainTextResponse("Erreur du site. Réessayez plus tard.", status_code=500)
    reponse.headers["Cache-Control"] = "no-store"
    return reponse


@app.exception_handler(RequestValidationError)
async def erreur_validation(request: Request, exc: RequestValidationError):
    return _page_erreur(request, 422, "Adresse incorrecte")
