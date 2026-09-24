"""The site: routes, and nothing else.

Runs anywhere Python and PostgreSQL run — a laptop today, the VPS tomorrow. It
does not need WordPress, WooCommerce, or a copy of the catalogue: it reads the
pipeline's database directly, which is why there is no `publish` step between
the two and no window during which the site shows yesterday's data.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus

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
from psycopg_pool import ConnectionPool
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import admin, cache, labels, partenaires, queries, suggestions
from . import courbe as courbe_mod

load_dotenv()

HERE = Path(__file__).parent
PER_PAGE = 24

pool: ConnectionPool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set (check .env)")
    # small pool: this is a read-only site, and the box also runs the pipeline
    pool = ConnectionPool(url, min_size=1, max_size=6, kwargs={"autocommit": True})
    pool.wait(timeout=10)
    yield
    pool.close()


app = FastAPI(title="motocomparo v2", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["prix"] = labels.price
templates.env.filters["couleur"] = labels.colour
templates.env.filters["genre"] = labels.genre
templates.env.filters["marchand"] = labels.merchant
templates.env.filters["taille"] = labels.size_display
templates.env.globals["titre_produit"] = labels.product_title


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
        return row["model_display"]
    # Deux retraits, et deux seulement. Chacun enlève une chose qui n'apprend
    # rien ou qui ment ; aucun ne touche au nom du produit lui-même.
    titre = labels.sans_queue_de_rayon(titre, row.get("brand_code") or "")
    return labels.sans_taille_finale(titre)


templates.env.globals["nom"] = _nom


def _version_css() -> int:
    """Timestamp of the newest file in `static/`, appended to every asset URL.

    Without it a browser keeps the copy it already has, and a phone is the one
    place where clearing that cache by hand is genuinely awkward.

    It watches the whole directory, not one file. Tracking `style.css` alone
    meant editing `v1.css` left the number unchanged, so phones kept serving the
    stylesheet from before the logo had a size rule — and rendered a 595-pixel
    logo. A cache-buster that misses a file is worse than none, because the bug
    it produces looks like a design mistake.
    """
    try:
        return max(
            int(f.stat().st_mtime) for f in (HERE / "static").iterdir() if f.is_file()
        )
    except (OSError, ValueError):
        return 0


templates.env.globals["version_css"] = _version_css


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
            "bandeaux_larges": partenaires.bandeaux("large"), **extra}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    # Tout l'accueil est le MÊME pour chaque visiteur et ne change qu'au passage
    # du pipeline. Mesuré le 2026-09-14 : 2,4 s de requêtes par visite, dont
    # 1,77 s pour `categories()` — une requête que le cache de navigation
    # détenait déjà et que cette page relançait pour rien.
    def _bloc() -> dict:
        with pool.connection() as conn:  # type: ignore[union-attr]
            # the shelves ARE the home page (the v1 shape), so the old flat grid
            # of 12 products is gone rather than kept above them: two answers to
            # the same question stacked on one page is how a home page stops
            # reading.
            familles = [c for c in _rayons() if c["n"]][:9]
            # Les casques, avec leurs sous-rayons — `ids` porte le parent ET ses
            # enfants, sinon « Nouveautés casque » ne verrait que les 79 casques
            # dont aucun sous-type n'a pu être lu, et non le rayon entier.
            casques = queries.find_category(_rayons(), "helmet")
            return {
                "totals": queries.totals(conn),
                "rayons": queries.rayons(conn, familles, 10),
                "ecarts": queries.ecarts(conn, 12),
                "nouveautes": queries.nouveautes(
                    conn, casques["ids"] if casques else [], 12),
                "nouveautes_rayon": casques,
                "baisses": queries.baisses(conn, 12),
                "affiche": queries.affiche(conn),
                "vitrine": queries.vitrine(conn),
            }

    bloc = cache.au_chaud("accueil", _bloc)
    return templates.TemplateResponse(
        request, "home.html", _ctx(request, **bloc))


def _releve_jour(conn) -> str:
    """La date du dernier relevé de prix, pour la mention des pages de résultats."""
    r = conn.execute(
        "SELECT max(last_seen)::date FROM raw_offer WHERE is_live").fetchone()
    return r[0].strftime("%d/%m/%Y") if r and r[0] else ""


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
            return items, total, queries.facets(conn, f), _releve_jour(conn)

    items, total, facettes, releve = cache.au_chaud(f"liste|{f}|{page}", _page)
    return templates.TemplateResponse(
        request, "listing.html",
        _ctx(request, titre=titre, code=code, items=items, total=total,
             page=page, pages=max(1, -(-total // PER_PAGE)), base=base,
             courante=courante, facettes=facettes, f=f, releve_jour=releve),
    )


@app.get("/produits", response_class=HTMLResponse)
def produits(
    request: Request,
    page: int = Query(1, ge=1),
    marque: str | None = None,
    prix_min: float | None = None,
    prix_max: float | None = None,
    taille: str | None = None,
    couleur: str | None = None,
    marchands: int = Query(2, ge=2, le=6),
    tri: str = "pertinence",
):
    """The whole catalogue, every department at once — where the home banner
    leads. No category is fixed, so the visitor narrows down from the whole
    shelf instead of having to pick a department before seeing anything."""
    f = queries.Filtres(marque=marque, prix_min=prix_min, prix_max=prix_max,
                        taille=taille, couleur=couleur, marchands=marchands, tri=tri)
    return _liste(request, "Tous les produits", "/produits", f, page)


@app.get("/c/{code}", response_class=HTMLResponse)
def category(
    request: Request,
    code: str,
    page: int = Query(1, ge=1),
    marque: str | None = None,
    prix_min: float | None = None,
    prix_max: float | None = None,
    taille: str | None = None,
    couleur: str | None = None,
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
    f = queries.Filtres(categories=courante["ids"], marque=marque,
                        prix_min=prix_min, prix_max=prix_max, taille=taille,
                        couleur=couleur, marchands=marchands, tri=tri)
    return _liste(request, courante["label_fr"], f"/c/{code}", f, page,
                  code=code, courante=courante)


@app.get("/m/{marque}", response_class=HTMLResponse)
def marque_page(
    request: Request,
    marque: str,
    page: int = Query(1, ge=1),
    prix_min: float | None = None,
    prix_max: float | None = None,
    taille: str | None = None,
    couleur: str | None = None,
    marchands: int = Query(2, ge=2, le=6),
    tri: str = "pertinence",
):
    """Everything one brand makes, across every category.

    A brand is a filter, not a text query: the rail used to send the visitor to
    `/recherche?q=shoei`, which answers with whatever contains the word and
    offers nothing to narrow once you land.
    """
    f = queries.Filtres(marque=marque, prix_min=prix_min, prix_max=prix_max,
                        taille=taille, couleur=couleur, marchands=marchands, tri=tri)
    with pool.connection() as conn:  # type: ignore[union-attr]
        _, total = queries.listing_filtre(conn, f, 1, 0)
    if not total and page == 1:
        raise HTTPException(404, "Marque inconnue")
    return _liste(request, marque.upper(), f"/m/{marque}", f, page)


@app.get("/p/{slug}", response_class=HTMLResponse)
def product(request: Request, slug: str):
    with pool.connection() as conn:  # type: ignore[union-attr]
        p = queries.product(conn, slug)
        if p is None:
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
    # the barcode, shown as the reference: it is the one identifier every
    # merchant on the page agrees on, which is exactly what makes it worth
    # printing. Merchants with a synthetic GTIN are skipped — theirs is ours.
    reference = next((o["gtin"] for o in rows
                      if o["gtin"] and o["merchant"] not in ("maxxess", "motoaxxe")), None)
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
             donnees_structurees=[
                 _donnees_structurees(request, p, rows, image, reference),
                 _fil_structure(request, p),
             ]),
    )


def _donnees_structurees(
    request: Request,
    p: dict[str, Any],
    rows: list[dict[str, Any]],
    image: str | None,
    reference: str | None,
) -> dict[str, Any]:
    """Le produit et sa fourchette de prix, décrits pour les moteurs.

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
    marque = (p.get("brand_code") or "").upper()

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
    return produit


def _fil_structure(request: Request, p: dict[str, Any]) -> dict[str, Any]:
    """Le fil d'Ariane déjà affiché en haut de la fiche, redit aux moteurs.

    Il est écrit ici à partir des mêmes valeurs que le gabarit : deux sources
    pour un seul fil finiraient par se contredire, et c'est la version cachée
    qui mentirait sans que personne le voie.
    """
    racine = f"{request.url.scheme}://{request.url.netloc}"
    etapes = [("Accueil", "/")]
    if p.get("category_code"):
        etapes.append((p.get("category_label") or p["category_code"],
                       f"/c/{p['category_code']}"))
    etapes.append((_nom(p), f"/p/{p['slug']}"))
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
_RESEAU_LOCAL = ("127.", "::1", "10.", "192.168.", "172.16.", "172.17.",
                 "172.18.", "172.19.", "172.2", "172.30.", "172.31.", "localhost")


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
            headers={"WWW-Authenticate": 'Basic realm="MotoComparo"'},
        )

    hote = request.client.host if request.client else ""
    if any(hote.startswith(p) for p in _RESEAU_LOCAL):
        return None
    return PlainTextResponse(
        "Le tableau de bord n'est accessible que depuis le réseau local. "
        "Pour l'ouvrir ailleurs, renseignez ADMIN_MDP dans .env.",
        status_code=403,
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
    return templates.TemplateResponse(request, "admin.html", _ctx(request, **contexte))


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

    d = parse_qs((await request.body()).decode("utf-8", "replace"))
    prendre = lambda k: (d.get(k, [""])[0] or "").strip()  # noqa: E731
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
    return RedirectResponse("/admin#promos", status_code=303)


@app.get("/favoris", response_class=HTMLResponse)
def favoris(request: Request, p: str = ""):
    """The shortlist. Empty until the page's own script fills the URL from the
    browser's store — see `templates/liste.html` for why that hop exists."""
    slugs = [x for x in p.split(",") if x][:40]
    with pool.connection() as conn:  # type: ignore[union-attr]
        items = queries.par_slugs(conn, slugs)
    return templates.TemplateResponse(
        request, "liste.html",
        _ctx(request, titre="Mes favoris", cle="favoris", items=items,
             vide="Vous n'avez encore rien mis de côté.",
             aide="Le cœur sur une image met le produit ici. La liste reste sur "
                  "cet appareil : le site ne vous demande aucun compte."),
    )


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
    for it in items:
        it["indice"] = queries.indice_protection(
            it["caracteristiques"], it.get("category_code") or "")
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
    for it in items:
        it["indice"] = queries.indice_protection(
            it["caracteristiques"], it.get("category_code") or "")
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
    """
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
    """Tailles et normes — des faits vérifiables, pas des conseils de vendeur."""
    return templates.TemplateResponse(request, "guides.html", _ctx(request))


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


@app.post("/contact")
async def contact_envoi(request: Request):
    """Enregistre le message. Pas d'e-mail affiché, pas d'envoi SMTP.

    Une adresse en clair sur une page publique est aspirée en quelques jours, et
    le site n'a pas de serveur d'envoi : les messages sont stockés et relus dans
    le tableau de bord. `parse_qs` plutôt que `Form()` pour ne pas dépendre de
    python-multipart, absent de l'environnement.
    """
    d = parse_qs((await request.body()).decode("utf-8", "replace"))
    prendre = lambda k: (d.get(k, [""])[0] or "").strip()  # noqa: E731
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
    with pool.connection() as conn:  # type: ignore[union-attr]
        conn.execute(
            "INSERT INTO message_contact (sujet, corps, email, page) "
            "VALUES (%s, %s, nullif(%s, ''), %s)",
            (sujet, corps[:4000], prendre("email")[:190],
             request.headers.get("referer", "")[:300]),
        )
    return RedirectResponse("/contact?envoye=1", status_code=303)


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

    def _produits() -> list[dict[str, Any]]:
        with pool.connection() as conn:  # type: ignore[union-attr]
            # Huit et non six : trois partent en grand format, il doit rester
            # de quoi remplir « Autres produits ».
            if marque:
                return queries.produits_dans_la_marque(conn, marque, restants, 8)
            return queries.produits_suggeres(conn, tapes, 8)

    trouves = cache.au_chaud(f"suggestions|{texte.lower()}", _produits, ttl=300)

    return JSONResponse(
        suggestions.construire(texte, matrice, plats, trouves, _nom,
                               marque, restants),
        headers={"Cache-Control": "no-store"},
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Le navigateur réclame `/favicon.ico` quoi qu'on déclare dans l'entête.

    L'entête annonce bien `favicon.svg`, mais tout navigateur demande d'abord
    cette adresse-là, à la racine, sans lire la page — et la journalisation du
    site portait un 404 sous CHAQUE visite. Un 404 qu'on s'explique est un 404
    qu'on finit par ne plus lire, y compris le jour où il en cache un vrai.

    Redirection permanente plutôt que copie d'un fichier `.ico` : une seule
    image à tenir à jour, et le navigateur ne redemande plus.
    """
    return RedirectResponse("/static/favicon.svg", status_code=301)


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots(request: Request) -> str:
    """Ce qu'un robot a le droit de parcourir.

    On ferme ce qui n'a aucun sens pour un moteur : le comparateur et les
    favoris vivent dans le navigateur du visiteur et seraient vides ; `/admin`
    n'est pas public ; `/fragment` rend des morceaux de page sans en-tête.
    """
    base = f"{request.url.scheme}://{request.url.netloc}"
    return "\n".join([
        "User-agent: *",
        "Disallow: /admin",
        "Disallow: /comparer",
        "Disallow: /favoris",
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
        fixes = ["/", "/produits", "/bons-plans", "/marques", "/guides",
                 "/infos", "/contact"]
        return (fixes
                + [f"/c/{r[0]}" for r in rayons]
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
    page: int = Query(1, ge=1),
    marque: str | None = None,
    prix_min: float | None = None,
    prix_max: float | None = None,
    taille: str | None = None,
    couleur: str | None = None,
    marchands: int = Query(2, ge=2, le=6),
    tri: str = "pertinence",
):
    """Search results, filterable like every other listing.

    It used to be a page apart — no filter panel, no counts, no sort — so a
    search for "arai sz" returned forty helmets and left the visitor with
    nothing to narrow them down. The typed words are now a filter like any
    other, which also means they survive every click inside the panel.
    """
    f = queries.Filtres(texte=q.strip() or None, marque=marque,
                        prix_min=prix_min, prix_max=prix_max, taille=taille,
                        couleur=couleur, marchands=marchands, tri=tri)
    titre = f"Recherche : {q}" if q.strip() else "Recherche"
    return _liste(request, titre, f"/recherche?q={quote_plus(q)}", f, page)

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


@app.exception_handler(RequestValidationError)
async def erreur_validation(request: Request, exc: RequestValidationError):
    return _page_erreur(request, 422, "Adresse incorrecte")
