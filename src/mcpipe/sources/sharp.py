"""Le relevé des fiches SHARP.

SHARP est le programme d'essais de casques du ministère des transports
britannique. Il achète les casques au détail, les détruit sur 32 scénarios de
choc et publie, pour chacun, une note de 1 à 5 étoiles et un POIDS PESÉ.

585 fiches, une par modèle, listées dans le plan de site du domaine — donc pas
de pagination à dérouler, pas de bouton « voir plus » à cliquer, et surtout pas
de liste devinée. `robots.txt` n'interdit que `/wp-json/` et `/?rest_route=` ;
les fiches elles-mêmes sont ouvertes.

CE QUI EST ÉCRIT ICI ET CE QUI NE L'EST PAS. Ce module RELÈVE, il ne rapproche
pas. Il ne sait rien de nos fiches produit et n'écrit rien dans
`product_caracteristique`. La raison est dans `sql/024_source_sharp.sql` : le
relevé est exact et se refait en quelques minutes, le rapprochement est
approximatif et se rejouera souvent.

POURQUOI PAS D'ANALYSEUR HTML. Le projet n'en embarque aucun, et la page se lit
en deux expressions : un tableau de paires libellé/valeur, et le nom de fichier
de l'image d'étoiles. Ajouter une dépendance pour ça ne se justifie pas.
En revanche un analyseur qui ne trouve rien doit CRIER : voir `_exiger`.
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass, field

import httpx

from ..db import connect

RACINE = "https://sharp.dft.gov.uk"
PLAN_DE_SITE = f"{RACINE}/helmet-sitemap.xml"

# On se présente. Un relevé qui se cache d'un site public n'a pas sa place dans
# un dépôt qu'on montre, et l'adresse permet au ministère de nous joindre si le
# rythme le gêne.
ENTETES = {
    "User-Agent": ("motocomparo/1.0 (comparateur de prix d'equipement moto ; "
                   "contact@motocomparo.com)"),
    "Accept": "text/html",
}

# 585 pages. À une demi-seconde, le relevé complet prend cinq minutes et ne pèse
# rien pour le serveur d'en face. Il n'y a aucune raison d'aller plus vite : ce
# relevé se refait une fois par mois, pas une fois par heure.
PAUSE = 0.5

_LIGNE = re.compile(
    r"<tr[^>]*>\s*<t[hd][^>]*>(.*?)</t[hd]>\s*<t[hd][^>]*>(.*?)</t[hd]>",
    re.I | re.S)
_ETOILES = re.compile(r"rating-star-(\d)\.gif", re.I)
_BALISE = re.compile(r"<[^>]+>")
# LE NOMBRE S'ARRÊTE AU DERNIER CHIFFRE. Une classe `[\d.,]+` est gourmande et
# avale la ponctuation qui suit : SHARP écrit « 1.35.kg » sur au moins une fiche,
# et `float("1.35.")` a fait tomber le relevé à la 121ᵉ page sur 585.
_POIDS = re.compile(r"(\d+(?:[.,]\d+)?)\s*\.?\s*(kg|g)\b", re.I)
_PRIX = re.compile(r"\d+(?:[.,]\d+)?")
# Les équipements du casque vivent dans un second tableau, sous un bloc
# `helmet-features`. On le délimite avant de le lire, au lieu de chercher ses
# lignes dans toute la page : le pied de page porte quatre tableaux de cookies
# qui, eux aussi, sont faits de lignes à deux cellules.
_BLOC_OPTIONS = re.compile(r'class="[^"]*helmet-features[^"]*"(.*?)</table>',
                           re.I | re.S)
# Dans ce tableau, la première cellule porte un PICTOGRAMME et la seconde le
# libellé en gras. Une première écriture attendait une cellule vide devant, et
# ne remontait donc jamais rien — sans erreur, évidemment.
_OPTION = re.compile(r"<strong[^>]*>(.*?)</strong>", re.I | re.S)

# Les libellés du tableau, tels que SHARP les écrit, vers nos colonnes.
_CHAMPS = {
    "model": "modele",
    "manufacturer": "marque",
    "helmet weight": "poids_g",
    "rrp": "prix_gbp",
    "helmet sizes": "tailles",
    "helmet type": "type_casque",
    "retention system": "retention",
    "materials": "materiaux",
    "standard": "norme",
    "manufacturer's website": "site_constructeur",
    "test date": "date_test",
}


@dataclass
class Fiche:
    slug: str
    marque: str = ""
    modele: str = ""
    etoiles: int | None = None
    poids_g: int | None = None
    prix_gbp: float | None = None
    tailles: str | None = None
    type_casque: str | None = None
    retention: str | None = None
    materiaux: str | None = None
    norme: str | None = None
    site_constructeur: str | None = None
    date_test: str | None = None
    options: list[str] = field(default_factory=list)


def _texte(brut: str) -> str:
    return html.unescape(_BALISE.sub(" ", brut)).replace("\xa0", " ").strip()


def _poids_en_grammes(valeur: str) -> int | None:
    """« 1.6kg » et « 1450 g » désignent la même chose ; la base n'en garde qu'une.

    Tout est ramené au gramme parce qu'un casque se compare au gramme près et
    qu'un mélange de kilos et de grammes dans une colonne finit toujours par
    produire un tri absurde — un 1,6 classé avant un 1450.
    """
    m = _POIDS.search(valeur)
    if not m:
        return None
    nombre = float(m.group(1).replace(",", "."))
    return round(nombre * 1000) if m.group(2).lower() == "kg" else round(nombre)


def _prix(valeur: str) -> float | None:
    m = _PRIX.search(valeur.replace(",", ""))
    return float(m.group(0)) if m else None


def lire(slug: str, page: str) -> Fiche:
    """Une page SHARP -> une fiche. Ne touche pas au réseau : testable seule."""
    f = Fiche(slug=slug)
    for libelle, valeur in _LIGNE.findall(page):
        cle = _texte(libelle).lower().rstrip(":")
        champ = _CHAMPS.get(cle)
        if not champ:
            continue
        v = _texte(valeur)
        if not v:
            continue
        if champ == "poids_g":
            f.poids_g = _poids_en_grammes(v)
        elif champ == "prix_gbp":
            f.prix_gbp = _prix(v)
        else:
            setattr(f, champ, v)

    m = _ETOILES.search(page)
    if m:
        f.etoiles = int(m.group(1))

    bloc = _BLOC_OPTIONS.search(page)
    if bloc:
        for cellule in _OPTION.findall(bloc.group(1)):
            option = _texte(cellule)
            if option and option not in f.options:
                f.options.append(option)
    return f


def _exiger(fiches: list[Fiche]) -> None:
    """Un analyseur muet ressemble à un site vide — c'est LE défaut du projet.

    La clé de jointure des caractéristiques est tombée en panne pour trois
    marchands sans lever la moindre erreur : les valeurs manquantes avaient
    l'air de valeurs absentes, et 277 vérifications sont restées au vert. On ne
    recommence pas. Si la page change de structure, le relevé s'arrête ICI, au
    lieu d'écrire 585 lignes vides par-dessus les bonnes.

    Le seuil est à la moitié, pas à cent pour cent : certaines fiches
    anciennes n'ont réellement ni poids ni prix, et un seuil strict ferait
    échouer le relevé sur une donnée qui manque légitimement.
    """
    if not fiches:
        raise RuntimeError("aucune fiche relevée : le plan de site est-il vide ?")
    controles = (
        ("une note", sum(1 for f in fiches if f.etoiles)),
        ("un poids", sum(1 for f in fiches if f.poids_g)),
        ("un modèle", sum(1 for f in fiches if f.modele)),
    )
    for quoi, combien in controles:
        if combien < len(fiches) * 0.5:
            raise RuntimeError(
                f"seulement {combien} fiches sur {len(fiches)} ont {quoi} — "
                "la page SHARP a changé de structure, l'analyseur est à revoir")


def adresses(client: httpx.Client) -> list[str]:
    plan = client.get(PLAN_DE_SITE).text
    urls = re.findall(r"<loc>([^<]+)</loc>", plan)
    # La première entrée du plan est la page de liste, pas un casque.
    return [u for u in urls if u.rstrip("/").rsplit("/", 1)[-1] != "helmets"]


def relever(limite: int | None = None, trace=print) -> list[Fiche]:
    fiches: list[Fiche] = []
    with httpx.Client(headers=ENTETES, timeout=30, follow_redirects=True) as client:
        urls = adresses(client)
        if limite:
            urls = urls[:limite]
        trace(f"{len(urls)} fiches a relever")
        for i, url in enumerate(urls, 1):
            slug = url.rstrip("/").rsplit("/", 1)[-1]
            # UNE FICHE ABÎMÉE NE DOIT PAS EMPORTER LES AUTRES. Le premier
            # relevé s'est arrêté net à la 121ᵉ page sur un poids mal écrit, et
            # les 120 déjà lues sont parties avec — l'enregistrement n'a lieu
            # qu'à la fin. On note la page fautive et on continue ; `_exiger`
            # reste là pour refuser un relevé massivement muet.
            try:
                fiches.append(lire(slug, client.get(url).text))
            except (httpx.HTTPError, ValueError, AttributeError) as e:
                trace(f"  !! {slug} : {type(e).__name__} {e}")
                continue
            if i % 50 == 0:
                trace(f"  {i}/{len(urls)}")
            time.sleep(PAUSE)
    _exiger(fiches)
    return fiches


_INSERTION = """
INSERT INTO source_sharp (slug, marque, modele, etoiles, poids_g, prix_gbp,
    tailles, type_casque, retention, materiaux, norme, site_constructeur,
    date_test, options, releve_le)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
ON CONFLICT (slug) DO UPDATE SET
    marque = EXCLUDED.marque, modele = EXCLUDED.modele,
    etoiles = EXCLUDED.etoiles, poids_g = EXCLUDED.poids_g,
    prix_gbp = EXCLUDED.prix_gbp, tailles = EXCLUDED.tailles,
    type_casque = EXCLUDED.type_casque, retention = EXCLUDED.retention,
    materiaux = EXCLUDED.materiaux, norme = EXCLUDED.norme,
    site_constructeur = EXCLUDED.site_constructeur,
    date_test = EXCLUDED.date_test, options = EXCLUDED.options,
    releve_le = now()
"""


def enregistrer(fiches: list[Fiche]) -> int:
    conn = connect()
    try:
        with conn.cursor() as cur:
            for f in fiches:
                cur.execute(_INSERTION, (
                    f.slug, f.marque, f.modele, f.etoiles, f.poids_g, f.prix_gbp,
                    f.tailles, f.type_casque, f.retention, f.materiaux, f.norme,
                    f.site_constructeur, f.date_test, f.options))
        conn.commit()
        return len(fiches)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
