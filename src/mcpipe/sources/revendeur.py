"""Le relevé des fiches du revendeur.

Ce revendeur n'est pas un organisme public : ce n'est pas SHARP.
Ce qu'on en garde est du même ordre qu'une fiche technique — matière, nombre de
coques, fermeture — jamais leur texte de vente, jamais leurs notes éditoriales
(confort, bruit : des avis, pas des faits). SHARP dit si un casque protège ;
le revendeur dit de quoi il est fait. Les deux se complètent, sans se répéter, et
tous les deux se sourcent : `product_caracteristique.source` garde la trace.

DEUX CHOSES QU'ON N'A PAS EN ÉCRIVANT CE MODULE, ET QU'ON AVAIT AVEC SHARP :

  1. PAS DE LISTE FINIE UNIQUE. Le catalogue se parcourt par les cinq pages de
     catégorie du rayon casque (intégraux, modulables, jet, off-road, racing),
     chacune paginée. « Racing » recoupe largement « intégraux » : les URL sont
     dédoublonnées au passage.

  2. PAS DE CHAMP « MODÈLE » PROPRE. Une page par coloris, jamais de fiche
     canonique. Le tableau technique auto-généré (`#product-attribute-specs-table`,
     structure Magento, vue une fois puis vérifiée deux fois — elle ne bouge pas
     d'une page à l'autre) donne la marque, mais jamais le modèle seul. Le
     rapprochement (`rapprochement_revendeur.py`) compare donc les fiches par
     leurs MOTS, débarrassés de la couleur des deux côtés à la fois — voir ce
     module pour le détail.

CE QUI EST FIABLE, ET CE QUI NE L'EST PAS. Le tableau technique est généré,
donc régulier ; on le lit tel quel, avec une table de correspondance vers le
vocabulaire déjà en place pour les flux marchands (mêmes valeurs de calotte,
même écriture de boucle — pour qu'une page produit n'ait jamais à savoir de
quelle source vient une caractéristique). Le POIDS et l'HOMOLOGATION, eux,
sont écrits en PROSE dans le texte de présentation : on les y lit avec la
même prudence qu'une description marchande, jamais recopiés tels quels.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field

import httpx

from ..db import connect
from .correspondance import est_un_casque

# L'ADRESSE DU REVENDEUR VIT DANS L'ENVIRONNEMENT, PAS DANS LE DÉPÔT.
# Le code de collecte est public — c'est un portfolio — mais la cible n'a pas à
# l'être : elle se lit dans `.env`, comme les adresses de flux marchands. Sans
# elle le module s'arrête net et le dit, plutôt que d'interroger une URL vide.
RACINE = os.environ.get("SOURCE_REVENDEUR_RACINE", "").rstrip("/")
PLAN_DE_SITE = f"{RACINE}/pub/sitemaps/sitemap_fr.xml"

ENTETES = {
    "User-Agent": ("motocomparo/1.0 (comparateur de prix d'equipement moto ; "
                   "contact@motocomparo.com)"),
    "Accept": "text/html",
}

# Un revendeur, pas un organisme public : on ralentit encore plus qu'avec SHARP.
PAUSE = 0.6

# LA LISTE VIENT DU PLAN DE SITE, PAS DES PAGES DE CATÉGORIE — ET C'EST UN
# CHANGEMENT DE PLAN, PAS LE DESSIN D'ORIGINE.
#
# Un premier essai listait les cinq catégories du rayon (intégraux, jet,
# modulables, off-road, racing) par leur grille paginée, en ciblant la classe
# `product-item-link` pour éviter le méga-menu des marques (un tout premier
# essai, encore plus naïf, cherchait n'importe quel lien `.html` et attrapait
# « agv.html », « abus.html »… identiques sur chaque page). Même corrigé, ça
# n'a rendu que 12 fiches par catégorie, toujours les 12 mêmes, quel que soit
# `?p=N` demandé : le CDN du site sert une page mise en cache pour toute
# pagination, sans session de navigateur complète pour la débloquer — vérifié
# dans les en-têtes de réponse (`x-magento-cache-debug: HIT`, contenu
# identique sur `?p=2`). Ce n'est pas un blocage (200, `robots.txt` autorise
# tout), mais une protection anti-bot qui aurait plafonné le relevé à 60
# fiches sur un catalogue de plusieurs milliers.
#
# Les PAGES PRODUIT, elles, n'ont pas ce défaut : chaque URL est son propre
# cache, légitime. Le plan de site en donne la liste complète — 4 246 fiches,
# toutes catégories confondues (casques, gants, bottes...). Pas question de
# toutes les lire pour n'en garder qu'une partie : le NOM DE FICHIER de
# l'image, dans le plan de site lui-même, porte déjà le mot « casque » en
# plusieurs langues (SEO oblige) — « hjc-rpha-11-joker-full-face-helmet-helm-
# casque-kask-casco.jpg ». Un filtre sur ce seul nom de fichier, sans charger
# une seule page, ramène 4 246 URL à 1 846 — vérifié sur un tirage aléatoire de
# vingt, tous des casques, aucun gant ni blouson.
#
# ⚠️ LE MOT « HELMET » EST DANS LE NOM DE DOMAINE LUI-MÊME : un premier filtre
# cherchait ces mots dans l'URL DE
# L'IMAGE ENTIÈRE, et matchait donc CHAQUE image du site, casque ou pas — 3 414
# « casques » sur 4 246 fiches, avec des pantalons Rukka et des gants Dainese
# dedans. Le filtre ne porte que sur le dernier segment de l'URL (le nom de
# fichier), jamais sur l'URL complète.
_MOT_CASQUE = re.compile(r"helmet|casque|-helm-|-kask-|-casco-", re.I)


def adresses(client: httpx.Client) -> list[str]:
    """Les URL produit du plan de site dont le nom de fichier d'image dit
    « casque » — sans charger une seule page produit."""
    if not RACINE:
        raise RuntimeError(
            "SOURCE_REVENDEUR_RACINE n'est pas défini : l'adresse du revendeur "
            "se lit dans l'environnement, pas dans le dépôt. Voir `.env.example`.")
    plan = client.get(PLAN_DE_SITE).text
    urls = []
    for bloc in plan.split("<url>")[1:]:
        m_loc = re.search(r"<loc>([^<]+)</loc>", bloc)
        m_img = re.search(r"<image:loc>([^<]+)</image:loc>", bloc)
        if not m_loc or not m_img:
            continue
        fichier = m_img.group(1).rsplit("/", 1)[-1]
        if _MOT_CASQUE.search(fichier):
            urls.append(m_loc.group(1))
    return urls

# --- le tableau technique, généré, régulier ------------------------------------

_LIGNE_TABLE = re.compile(
    r'<th[^>]*class="col label"[^>]*>(.*?)</th>\s*'
    r'<td[^>]*class="col data"[^>]*>(.*?)</td>', re.I | re.S)
_BALISE = re.compile(r"<[^>]+>")


def _texte(brut: str) -> str:
    import html
    return html.unescape(_BALISE.sub(" ", brut)).replace("\xa0", " ").strip()


# Leurs mots vers les nôtres — les MÊMES valeurs que `caracteristiques/casque.py`,
# pour qu'une page produit n'ait jamais à connaître deux vocabulaires.
_MATIERE_VERS_CALOTTE = {
    "fibre de verre": "fibre", "fiberglass": "fibre",
    "fibre de carbone": "carbone", "carbon": "carbone", "carbone": "carbone",
    "polycarbonate": "polycarbonate", "abs": "polycarbonate",
    "composite": "composite", "hybride": "composite",
    "thermoplastique": "thermoplastique",
}
_FERMETURE_VERS_BOUCLE = {
    "double-d": "double-D", "double d": "double-D", "d-ring": "double-D",
    "micrométrique": "micrométrique", "micrometrique": "micrométrique",
    "ratchet": "micrométrique",
}


def _matiere(brut: str) -> str | None:
    return _MATIERE_VERS_CALOTTE.get(brut.strip().lower())


def _fermeture(brut: str) -> str | None:
    return _FERMETURE_VERS_BOUCLE.get(brut.strip().lower())


# --- poids et homologation : en PROSE, donc gardés comme une description ------
#
# Même garde que le rayon casque : l'unité ET un ordre de grandeur crédible.
# Leurs fiches mélangent les deux écritures selon la page — « 1459 gram » et
# « 1429 grams » vus tous les deux dans l'échantillon, jamais « grammes ».
_POIDS = re.compile(r"(\d{3,4})\s?gr?ammes?\b|(\d{3,4})\s?grams?\b", re.I)
_ECE = re.compile(r"ECE[\s.\-/]?R?[\s.\-/]?22[\s.\-/]?0?([56])\b", re.I)


def _poids_en_prose(texte: str) -> int | None:
    m = _POIDS.search(texte)
    if not m:
        return None
    g = int(m.group(1) or m.group(2))
    return g if 900 <= g <= 2500 else None    # un casque pèse dans cette fourchette


def _homologation_en_prose(texte: str) -> str | None:
    m = _ECE.search(texte)
    return f"22.0{m.group(1)}" if m else None


@dataclass
class Fiche:
    url: str
    marque: str = ""
    modele: str = ""            # le meilleur nom qu'on en tire — voir `lire()`
    type_annonce: str = ""      # laissé vide : voir la note au-dessus d'`adresses()`
    nombre_coques: int | None = None
    fermeture: str | None = None
    matiere: str | None = None
    fonctionnalites: list[str] = field(default_factory=list)
    poids_g: int | None = None
    homologation: str | None = None


def lire(url: str, page: str, type_annonce: str = "") -> Fiche | None:
    """Une page produit -> une fiche, ou `None` si ce n'est pas un casque.

    Testable seule, sans réseau : `page` est le HTML déjà en main.
    """
    # LE TITRE TRANCHE D'ABORD. Le rayon liste aussi des écrans, des
    # mentonnières, des pare-soleil — le même défaut que sur SHARP, avec les
    # mêmes mots. `est_un_casque` regarde la position du mot « casque », pas sa
    # seule présence.
    #
    # LU DANS `<title>`, PAS DANS UN `<h1>`. Le thème de la boutique ne rend
    # jamais de `<h1>` textuel sur une fiche produit — la vérification l'a
    # montré, une vraie page en main, pas une supposition. `<title>` porte le
    # même nom, suivi d'un slogan commercial : « HJC RPHA 11 Joker +
    # Livraison & Retour Gratuits! | 24% SALE! ». On coupe au premier « + » ou
    # « | », qui n'apparaissent jamais dans un nom de casque.
    m = re.search(r"<title>(.*?)</title>", page, re.I | re.S)
    titre = _texte(m.group(1)) if m else ""
    titre = re.split(r"\s[+|]\s", titre)[0].strip()
    if not titre or not est_un_casque(titre):
        return None

    f = Fiche(url=url, type_annonce=type_annonce, modele=titre)
    for libelle, valeur in _LIGNE_TABLE.findall(page):
        cle = _texte(libelle).lower()
        v = _texte(valeur)
        if not v:
            continue
        if cle == "marque":
            f.marque = v
        elif cle in ("nombre de coques", "shell sizes"):
            if v.isdigit():
                f.nombre_coques = int(v)
        elif cle in ("fermeture du casque", "helmet closure"):
            f.fermeture = _fermeture(v)
        elif cle in ("matériel", "material"):
            f.matiere = _matiere(v)
        elif cle == "caractéristiques" or cle == "features":
            f.fonctionnalites = [x.strip() for x in v.split(",") if x.strip()]

    if not f.marque:
        return None     # sans marque, aucun rapprochement n'est possible

    corps_texte = _texte(page)
    f.poids_g = _poids_en_prose(corps_texte)
    f.homologation = _homologation_en_prose(corps_texte)
    return f


def _exiger(fiches: list[Fiche]) -> None:
    """La même garde que pour SHARP : un analyseur muet ressemble à un site
    vide, et ce projet a déjà payé cette leçon avec la clé de jointure des
    flux — 113 967 offres sans description, 277 vérifications au vert."""
    if not fiches:
        raise RuntimeError("aucune fiche relevée : les pages de catégorie sont-elles vides ?")
    avec_marque = sum(1 for f in fiches if f.marque)
    avec_matiere_ou_coques = sum(1 for f in fiches if f.matiere or f.nombre_coques)
    for quoi, combien in (("une marque", avec_marque),
                          ("une matière ou un nombre de coques", avec_matiere_ou_coques)):
        if combien < len(fiches) * 0.5:
            raise RuntimeError(
                f"seulement {combien} fiches sur {len(fiches)} ont {quoi} — "
                "la page du revendeur a changé de structure, l'analyseur est à revoir")


def relever(limite: int | None = None, trace=print) -> list[Fiche]:
    fiches: list[Fiche] = []
    with httpx.Client(headers=ENTETES, timeout=30, follow_redirects=True) as client:
        urls = adresses(client)
        if limite:
            urls = urls[:limite]
        trace(f"{len(urls)} fiches à lire")
        for i, url in enumerate(urls, 1):
            try:
                page = client.get(url).text
                f = lire(url, page)
            except httpx.HTTPError as e:
                trace(f"  !! {url} : {type(e).__name__} {e}")
                continue
            if f is not None:
                fiches.append(f)
            if i % 200 == 0:
                trace(f"  {i}/{len(urls)}")
            time.sleep(PAUSE)
    _exiger(fiches)
    return fiches


_INSERTION = """
INSERT INTO source_revendeur (url, marque, modele, type_annonce, nombre_coques,
    fermeture, matiere, fonctionnalites, poids_g, homologation, releve_le)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
ON CONFLICT (url) DO UPDATE SET
    marque = EXCLUDED.marque, modele = EXCLUDED.modele,
    type_annonce = EXCLUDED.type_annonce, nombre_coques = EXCLUDED.nombre_coques,
    fermeture = EXCLUDED.fermeture, matiere = EXCLUDED.matiere,
    fonctionnalites = EXCLUDED.fonctionnalites, poids_g = EXCLUDED.poids_g,
    homologation = EXCLUDED.homologation, releve_le = now()
"""


def enregistrer(fiches: list[Fiche]) -> int:
    conn = connect()
    try:
        with conn.cursor() as cur:
            for f in fiches:
                cur.execute(_INSERTION, (
                    f.url, f.marque, f.modele, f.type_annonce, f.nombre_coques,
                    f.fermeture, f.matiere, f.fonctionnalites, f.poids_g,
                    f.homologation))
        conn.commit()
        return len(fiches)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
