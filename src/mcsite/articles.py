"""Les articles de la rubrique « Guides & conseils » : fichiers, statut, données.

POURQUOI PAS UN BLOG À CÔTÉ DE /guides. Le site a déjà une rubrique
éditoriale, `/guides`, présente dans le menu, le tiroir mobile, le pied de
page et le plan du site. Ouvrir un `/blog` en parallèle aurait fait deux
portes pour le même genre de texte, deux index, deux fils d'Ariane — et le
jour où un article répond à une question des guides, personne ne saurait où
le ranger. Les articles vivent donc SOUS `/guides/<slug>`, et la page
`/guides` devient leur index (les quatre repères d'origine restent en
dessous, inchangés). Aucun lien nouveau dans les menus : ceux qui existent
mènent déjà à `/guides`, et la liste d'articles n'y apparaît que s'il en
existe au moins un de publié.

UN ARTICLE = UN FICHIER, dans `templates/articles/<slug>.html`. Un gabarit
Jinja plutôt que du Markdown : les guides existants sont écrits ainsi, la
propriétaire sait déjà les relire, et un article doit pouvoir poser un bloc
de données vivantes (prix du jour, plus bas prix relevé) au milieu du texte —
ce qu'un Markdown ne fait pas sans un second langage de balises. Pas de
dépendance de plus à installer sur le serveur non plus.

L'en-tête de chaque fichier est un commentaire Jinja, donc invisible au
rendu :

    {#---
    titre: Gants été ou hiver : comment choisir
    description: Une phrase pour Google, 150 caractères environ.
    date: 2026-10-15
    statut: brouillon
    rayon: gloves
    produits: slug-1, slug-2
    marques: ls2, scorpion
    illustration: gants-ete-ou-hiver.webp
    illustration_alt: Route de campagne mouillée sous un ciel d'automne.
    ---#}

L'ILLUSTRATION EST FACULTATIVE, ET SON ABSENCE NE CASSE RIEN. Le fichier
nommé par `illustration:` vit dans `static/guides/`. Tant qu'il n'y est pas
déposé, l'article se rend sans image : on peut écrire l'en-tête avant
d'avoir généré l'image, et l'image apparaît le jour où le fichier arrive,
sans toucher au texte. Un nom de fichier sans texte alternatif est refusé au
chargement : une image sans `alt` est un trou d'accessibilité, et c'est la
seule description qu'un moteur lit. Ces images sont des scènes d'ambiance
générées par IA, jamais un produit de marque (voir
`docs/blog/charte-editoriale.md`) ; la page le dit sous l'image.

LE BROUILLON NE SORT PAS. Un brouillon n'est listé nulle part, n'entre pas
dans le plan du site, et son adresse répond 404 — sauf si `BLOG_APERCU=1` est
posé dans `.env`, ce qui n'est le cas qu'en local. Même alors, la page porte
`noindex`. Un drapeau dans l'URL (`?apercu=1`) aurait été plus commode, mais
nginx garde les pages en cache sans tenir compte de qui les demande : la
première personne à l'ouvrir l'aurait servi à tout le monde.

UN TEXTE À TROUS NE SE PUBLIE PAS. Les passages qui demandent l'avis de
quelqu'un qui a porté le produit sont marqués `a_completer(...)` dans le
fichier. Tant qu'il en reste un, l'article est traité comme un brouillon,
même si son en-tête dit « publié » — c'est la règle du site (rien de publié
qui ne soit mesuré ou sourcé) appliquée par le code plutôt que par la
mémoire.
"""

from __future__ import annotations

import unicodedata
from html import unescape

import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from . import cache, queries

DOSSIER = Path(__file__).parent / "templates" / "articles"
# Les illustrations des articles, servies sous `/static/guides/<fichier>`.
ILLUSTRATIONS = Path(__file__).parent / "static" / "guides"

BROUILLON = "brouillon"
PUBLIE = "publié"
_STATUTS = {BROUILLON, PUBLIE, "publie"}

# L'en-tête : `{#---` en toute première ligne, `---#}` pour fermer.
_ENTETE = re.compile(r"\A\s*\{#---\s*\n(.*?)\n---#\}", re.S)
# Un trou laissé pour la propriétaire. Cherché dans le TEXTE du fichier, pas
# au rendu : un article publié ne doit jamais avoir à être rendu pour qu'on
# sache s'il est complet.
_TROU = re.compile(r"\ba_completer\s*\(")
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# Un nom de fichier simple, sans dossier : l'en-tête ne doit pouvoir désigner
# qu'un fichier de `static/guides/`.
_IMAGE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\.(?:webp|jpg|jpeg|png)")

_log = logging.getLogger("mcsite.articles")


@dataclass(frozen=True)
class Article:
    slug: str
    titre: str
    description: str
    date: date
    statut: str
    gabarit: str                     # chemin relatif au dossier des gabarits
    maj: date | None = None
    rayon: str = ""
    produits: tuple[str, ...] = ()
    marques: tuple[str, ...] = ()
    trous: int = 0                   # passages `a_completer` restants
    illustration: str = ""           # nom de fichier dans `static/guides/`
    illustration_alt: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def publie(self) -> bool:
        """Publié ET complet. L'un sans l'autre reste un brouillon."""
        return self.statut == PUBLIE and self.trous == 0

    @property
    def illustration_url(self) -> str | None:
        """`/static/guides/<fichier>` si le fichier est déposé, sinon None.

        Regardé à chaque rendu, comme les articles eux-mêmes : une image
        déposée sur le serveur apparaît sans redémarrer le service, et un
        en-tête qui annonce une image pas encore générée ne produit pas
        d'image cassée.
        """
        if self.illustration and (ILLUSTRATIONS / self.illustration).is_file():
            return f"/static/guides/{self.illustration}"
        return None


def apercu_actif() -> bool:
    """Les brouillons ne s'ouvrent qu'avec `BLOG_APERCU=1` (développement)."""
    return os.environ.get("BLOG_APERCU", "").strip() == "1"


def _liste(valeur: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in valeur.split(",") if v.strip())


def lire(chemin: Path) -> Article:
    """Lit un fichier d'article. Lève `ValueError` si l'en-tête est faux :
    mieux vaut une erreur franche au chargement qu'un article publié sans
    date ou sous un mauvais slug."""
    texte = chemin.read_text(encoding="utf-8")
    m = _ENTETE.match(texte)
    if not m:
        raise ValueError(f"{chemin.name} : en-tête {{#--- ... ---#}} absent")
    champs: dict[str, str] = {}
    for ligne in m.group(1).splitlines():
        if not ligne.strip() or ligne.lstrip().startswith("#"):
            continue
        cle, sep, valeur = ligne.partition(":")
        if not sep:
            raise ValueError(f"{chemin.name} : ligne d'en-tête illisible {ligne!r}")
        champs[cle.strip().lower()] = valeur.strip()

    slug = chemin.stem
    if not _SLUG.fullmatch(slug):
        raise ValueError(f"{chemin.name} : le nom du fichier doit être un slug")
    if champs.get("slug", slug) != slug:
        raise ValueError(f"{chemin.name} : slug {champs['slug']!r} différent du nom du fichier")
    for obligatoire in ("titre", "description", "date", "statut"):
        if not champs.get(obligatoire):
            raise ValueError(f"{chemin.name} : champ « {obligatoire} » manquant")
    statut = champs["statut"].lower()
    if statut not in _STATUTS:
        raise ValueError(f"{chemin.name} : statut {statut!r} (brouillon ou publié)")
    statut = PUBLIE if statut in ("publié", "publie") else BROUILLON

    illustration = champs.get("illustration", "")
    illustration_alt = champs.get("illustration_alt", "")
    if illustration and not _IMAGE.fullmatch(illustration):
        raise ValueError(f"{chemin.name} : illustration {illustration!r} : un nom de "
                         "fichier simple attendu (minuscules, tirets, .webp/.jpg/.png)")
    if illustration and not illustration_alt:
        raise ValueError(f"{chemin.name} : illustration sans « illustration_alt »")

    corps = texte[m.end():]
    trous = len(_TROU.findall(corps))
    connus = {"slug", "titre", "description", "date", "maj", "statut",
              "rayon", "produits", "marques", "illustration", "illustration_alt"}
    article = Article(
        slug=slug,
        titre=champs["titre"],
        description=champs["description"],
        date=date.fromisoformat(champs["date"]),
        maj=date.fromisoformat(champs["maj"]) if champs.get("maj") else None,
        statut=statut,
        gabarit=f"articles/{chemin.name}",
        rayon=champs.get("rayon", ""),
        produits=_liste(champs.get("produits", "")),
        marques=_liste(champs.get("marques", "")),
        trous=trous,
        illustration=illustration,
        illustration_alt=illustration_alt,
        extra={k: v for k, v in champs.items() if k not in connus},
    )
    if statut == PUBLIE and trous:
        _log.warning("article %s marqué publié avec %d passage(s) à compléter : "
                     "traité comme brouillon", slug, trous)
    return article


def tous(dossier: Path | None = None) -> list[Article]:
    """Tous les articles, brouillons compris, du plus récent au plus ancien.

    Relu à chaque appel : trois fichiers de quelques kilo-octets coûtent moins
    qu'un cache à invalider, et un article déposé sur le serveur apparaît sans
    redémarrer le service.
    """
    d = dossier or DOSSIER
    if not d.is_dir():
        return []
    articles = []
    for chemin in sorted(d.glob("*.html")):
        if chemin.name.startswith("_"):
            continue
        articles.append(lire(chemin))
    return sorted(articles, key=lambda a: (a.date, a.slug), reverse=True)


def publies(dossier: Path | None = None) -> list[Article]:
    return [a for a in tous(dossier) if a.publie]


def trouver(slug: str, dossier: Path | None = None) -> Article | None:
    """L'article à servir pour ce slug, ou None (→ 404).

    Un brouillon n'est rendu qu'en mode aperçu ; ailleurs, il n'existe pas.
    """
    for a in tous(dossier):
        if a.slug == slug:
            if a.publie or apercu_actif():
                return a
            return None
    return None


# --- les blocs de données ---------------------------------------------------
#
# Ce qu'un article a le droit d'affirmer en chiffres vient d'ici, et nulle
# part ailleurs : les prix et caractéristiques DU JOUR, lus dans la même base
# que les fiches. Aucun chiffre n'est recopié à la main dans le texte d'un
# article — il serait faux dès le lendemain.
#
# Chaque bloc est mis en cache comme les autres pages (`cache.au_chaud`) : un
# article lu mille fois ne relance pas mille fois la même requête.

# Les caractéristiques montrées par défaut dans un tableau de casques. Choisies
# parce qu'elles se lisent sur une étiquette ou une fiche technique, pas parce
# qu'elles flattent un modèle.
CARACS_CASQUE = ("homologation", "calotte", "poids_g", "ecran_solaire",
                 "pinlock", "boucle", "interieur_amovible", "note_securite")


class Donnees:
    """Les requêtes qu'un article peut appeler depuis son gabarit.

    Reçoit une fonction qui rend le pool de connexions plutôt que le pool
    lui-même : dans `app.py`, le pool n'existe qu'une fois le serveur démarré.
    """

    def __init__(self, pool: Callable[[], Any]):
        self._pool = pool

    def _requete(self, cle: str, fabrique: Callable[[Any], Any]) -> Any:
        def _calcul() -> Any:
            with self._pool().connection() as conn:
                return fabrique(conn)
        return cache.au_chaud(f"article|{cle}", _calcul)

    def comparaison(self, slugs: list[str], caracs: tuple[str, ...] | list[str] = CARACS_CASQUE,
                    jours: int = 30) -> dict[str, Any]:
        """Deux à quatre fiches côte à côte : prix du jour, fourchette, nombre
        de marchands, plus bas prix relevé sur `jours` jours, et les
        caractéristiques demandées.

        Réutilise `queries.par_slugs` et `queries.caracteristiques`, les
        mêmes que `/comparatif/{slugs}` : le bloc de l'article est une version
        courte de ce comparateur, et il y renvoie pour le tableau complet (la
        note MotoComparo, toutes les lignes). Le tableau complet n'est pas
        inclus tel quel : il dépend d'un script de page pour replier ses
        sections, et au milieu d'un texte il prendrait tout l'écran.
        """
        slugs = [s for s in slugs if s][:4]
        caracs = tuple(caracs)

        def _f(conn: Any) -> dict[str, Any]:
            items = queries.par_slugs(conn, slugs)
            for it in items:
                cs = {c["nom"]: c for c in queries.caracteristiques(conn, it["product_id"])}
                it["caracs"] = cs
                it["plus_bas"] = _plus_bas(queries.price_curve(conn, it["product_id"], jours))
            lignes = []
            for nom in caracs:
                valeurs = {it["slug"]: it["caracs"].get(nom) for it in items}
                if not any(valeurs.values()):
                    continue
                libelle = next(v["libelle"] for v in valeurs.values() if v)
                lignes.append({"nom": nom, "libelle": libelle, "valeurs": valeurs})
            # `fiches`, pas `items` : Jinja lit un dict par attribut, et
            # `c.items` aurait trouvé la MÉTHODE `dict.items` avant la clé —
            # le gabarit aurait bouclé sur une fonction, pas sur la liste.
            return {"fiches": items, "lignes": lignes, "jours": jours,
                    "manquants": [s for s in slugs
                                  if s not in {it["slug"] for it in items}]}

        return self._requete(f"comparaison|{','.join(slugs)}|{','.join(caracs)}|{jours}", _f)

    def prix_bas(self, slug: str, jours: int = 30) -> dict[str, Any] | None:
        """Le plus bas prix relevé sur une fiche ces `jours` derniers jours, avec
        la date et le marchand. Lu dans `price_history` par `queries.price_curve`
        — la même courbe que celle de la fiche."""
        def _f(conn: Any) -> dict[str, Any] | None:
            p = queries.product(conn, slug)
            if p is None:
                return None
            bas = _plus_bas(queries.price_curve(conn, p["id"], jours))
            return {"p": p, "bas": bas, "jours": jours}
        return self._requete(f"prix_bas|{slug}|{jours}", _f)

    def repartition(self, rayon: str, nom: str, valeurs: list[str] | None = None) -> dict[str, Any]:
        """Combien de fiches comparables d'un rayon déclarent chaque valeur
        d'une caractéristique, et à quel prix médian.

        « Comparables » : la règle des fiches du plan du site, deux marchands
        au moins et un prix connu. Le rayon inclut ses sous-rayons. Rend aussi
        le total du rayon, pour qu'un article puisse dire honnêtement combien
        de fiches NE renseignent PAS la caractéristique.
        """
        def _f(conn: Any) -> dict[str, Any]:
            lignes = conn.execute("""
                WITH fiches AS (
                    SELECT p.id, s.cheapest
                    FROM product p
                    JOIN product_stats s ON s.product_id = p.id
                    JOIN category c ON c.id = p.category_id
                    LEFT JOIN category pa ON pa.id = c.parent_id
                    WHERE (c.code = %(r)s OR pa.code = %(r)s)
                      AND p.status <> 'merged'
                      AND s.merchant_count >= 2 AND s.cheapest IS NOT NULL
                )
                SELECT pc.valeur, count(DISTINCT f.id) AS n,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY f.cheapest) AS mediane,
                       min(f.cheapest) AS mini
                FROM fiches f
                JOIN product_caracteristique pc ON pc.product_id = f.id AND pc.nom = %(n)s
                GROUP BY pc.valeur
                ORDER BY n DESC
            """, {"r": rayon, "n": nom}).fetchall()
            total = conn.execute("""
                SELECT count(*) FROM product p
                JOIN product_stats s ON s.product_id = p.id
                JOIN category c ON c.id = p.category_id
                LEFT JOIN category pa ON pa.id = c.parent_id
                WHERE (c.code = %(r)s OR pa.code = %(r)s) AND p.status <> 'merged'
                  AND s.merchant_count >= 2 AND s.cheapest IS NOT NULL
            """, {"r": rayon}).fetchone()[0]
            rangs = [{"valeur": v, "n": n, "mediane": med, "mini": mini}
                     for v, n, med, mini in lignes
                     if valeurs is None or v in valeurs]
            return {"rayon": rayon, "nom": nom, "lignes": rangs, "total": total,
                    "renseignees": sum(r["n"] for r in rangs),
                    "libelle": queries._LIBELLES.get(nom)
                    or nom.replace("_", " ").capitalize()}
        return self._requete(f"repartition|{rayon}|{nom}|{valeurs}", _f)


def _plus_bas(courbe: list[dict[str, Any]]) -> dict[str, Any] | None:
    """La ligne la moins chère d'une courbe `queries.price_curve` ; à prix
    égal, la plus récente — c'est celle qui a encore une chance d'être vraie."""
    lignes = [c for c in courbe if c.get("price") is not None]
    if not lignes:
        return None
    return min(lignes, key=lambda c: (c["price"], -c["observed_on"].toordinal()))


# --- la forme d'un article : sommaire, temps de lecture, questions fréquentes ----------------------------------------
#
# Calculées sur le HTML déjà rendu, pas sur le fichier source : un bloc de données vivantes (tableau comparatif) fait
# partie de la page que le lecteur lit, donc du temps de lecture. Aucun de ces éléments ne demande de balisage à
# l'auteur sauf la FAQ, qui suit une convention (voir `docs/blog/charte-editoriale.md`, § « La forme cible »).

_H2 = re.compile(r"<h2(?P<attrs>[^>]*)>(?P<texte>.*?)</h2>", re.S)
_H3 = re.compile(r"<h3(?P<attrs>[^>]*)>(?P<texte>.*?)</h3>", re.S)
_FAQ = re.compile(r'<details class="faq"[^>]*>\s*<summary[^>]*>(?P<q>.*?)</summary>(?P<r>.*?)</details>', re.S)
_BALISES = re.compile(r"<[^>]+>")
MOTS_PAR_MINUTE = 220


def _texte(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(_BALISES.sub(" ", html))).strip()


def _ancre(texte: str, deja: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", texte.lower()).encode("ascii", "ignore").decode())
    base = base.strip("-")[:60] or "section"
    ancre, n = base, 2
    while ancre in deja:
        ancre, n = f"{base}-{n}", n + 1
    deja.add(ancre)
    return ancre


def mise_en_forme(html: str) -> tuple[str, list[tuple[str, str]], int, list[dict[str, str]]]:
    """(corps avec ancres sur les intertitres, sommaire [(ancre, titre)], minutes de lecture, FAQ [{q, r}])."""
    deja: set[str] = set()
    sommaire: list[tuple[str, str]] = []

    def _poser(m: re.Match, dans_sommaire: bool) -> str:
        attrs = m.group("attrs")
        titre = _texte(m.group("texte"))
        if 'id="' in attrs:
            ancre = re.search(r'id="([^"]+)"', attrs).group(1)
            deja.add(ancre)
        else:
            ancre = _ancre(titre, deja)
            attrs = f'{attrs} id="{ancre}"'
        if dans_sommaire:
            sommaire.append((ancre, titre))
        niveau = "h2" if dans_sommaire else "h3"
        return f"<{niveau}{attrs}>{m.group('texte')}</{niveau}>"

    corps = _H2.sub(lambda m: _poser(m, True), html)
    corps = _H3.sub(lambda m: _poser(m, False), corps)
    minutes = max(1, round(len(_texte(html).split()) / MOTS_PAR_MINUTE))
    faq = [{"q": _texte(m.group("q")), "r": _texte(m.group("r"))} for m in _FAQ.finditer(html)]
    return corps, sommaire, minutes, faq
