"""Les adresses de l'ancien site (v1, WordPress/WooCommerce), et où les envoyer.

Google les connaît encore : en deux semaines (relevé du 15/10/2026), environ
28 000 demandes sur `/shop/…`, 24 000 sur `/product/…`, 4 800 sur
`/product-category/…`, toutes en 404. Chaque 404 apprend à Google que la page
est morte, et le référencement acquis par la v1 s'en va avec. Une redirection
permanente (301) le transmet à la page qui la remplace.

Il n'existe AUCUNE table « ancienne adresse -> nouvelle fiche » : la base de la
v1 n'est pas ici. La correspondance se lit donc dans l'adresse elle-même
(`/product/casque-modulable-hjc-f100-gris-nardo-m/`), avec une règle de
prudence : une fiche n'est visée que si la marque est écrite EN TOUTES LETTRES
et que la ressemblance est forte. Sinon, la page de la marque, ou le rayon que
désigne le premier mot de produit, ou le catalogue. Rediriger vers une fiche
« à peu près » serait pire qu'utile : Google traite une redirection hors sujet
comme une page morte déguisée, et le visiteur ne trouve pas ce qu'il cherchait.
"""

from __future__ import annotations

import re
from urllib.parse import unquote

from . import suggestions

# Mesuré le 15/10/2026 sur 40 anciennes fiches demandées par Googlebot : les
# bonnes fiches commencent à 0,67 (Ixon IX-Airbag U04, Bardahl nettoyant
# carburateur, Acerbis MX Pro Socks…) ; à 0,56-0,57, un modèle voisin (écran
# Roof RO15 -> RO35, écran Scott Prospect -> film anti-buée). La coupure passe
# entre les deux.
SEUIL_FICHE = 0.60

# Rayon d'un mot de produit, MESURÉ dans le catalogue et non deviné : pour
# chaque mot, le rayon où tombent la plupart des fiches qui le portent (75 %
# et plus). D'où quelques surprises fidèles aux données : les écrans de casque
# sont rangés en électronique, les pneus en entretien.
_MOTS_RAYON = {
    "ecran": "electronics", "pinlock": "electronics", "intercom": "electronics",
    "gps": "electronics", "retroviseur": "electronics",
    "bulle": "bodywork", "carenage": "bodywork", "phare": "bodywork",
    "casquette": "apparel_casual", "sweat": "apparel_casual", "cagoule": "apparel_casual",
    "housse": "seat", "selle": "seat",
    "outil": "maintenance", "batterie": "maintenance", "chargeur": "maintenance",
    "nettoyant": "maintenance", "pneu": "maintenance", "gicleur": "maintenance",
    "carburateur": "maintenance", "bequille": "maintenance", "graisse": "maintenance",
    "cable": "maintenance",
    "filtre": "engine", "huile": "engine", "piston": "engine", "cylindre": "engine",
    "support": "luggage", "sacoche": "luggage", "valise": "luggage", "sac": "luggage",
    "bagagerie": "luggage",
    "plaquette": "brakes", "disque": "brakes", "frein": "brakes",
    "amortisseur": "suspension", "fourche": "suspension",
    "chaine": "transmission", "pignon": "transmission", "couronne": "transmission",
    "variateur": "transmission", "courroie": "transmission",
    "masque": "goggles", "lunette": "goggles",
    "echappement": "exhaust", "silencieux": "exhaust", "pot": "exhaust",
    "dorsale": "protection.pilote", "genouillere": "protection.pilote",
    "airbag": "protection.pilote",
    "maillot": "jersey", "combinaison": "suit", "combi": "suit",
    "veste": "jacket", "blouson": "jacket", "pantalon": "pants", "gant": "gloves",
    "botte": "boots", "basket": "boots", "chaussure": "boots", "chaussette": "boots",
    "compteur": "accessories",
}
_SOUS_CASQUE = {"modulable": "helmet.modular", "jet": "helmet.jet",
                "integral": "helmet.integral", "cross": "helmet.cross",
                "mx": "helmet.cross"}

# Les catégories WooCommerce de la v1, telles que Google les demande.
_RAYONS_V1 = {
    "accessoires": "accessories", "accessoires-de-la-moto": "accessories",
    "securite": "accessories",
    "casques": "helmet", "casque": "helmet", "casque-moto": "helmet",
    "blousons": "jacket", "pantalons": "pants", "gants": "gloves", "bottes": "boots",
    "protections": "protection", "entretien": "maintenance", "outillage": "maintenance",
    "bagagerie": "luggage", "sportswear": "apparel_casual", "high-tech": "electronics",
    "cross-tt-enduro": "jersey", "tout-terrain": "jersey",
}

RAYONS_V1_CONNUS = frozenset(_RAYONS_V1)

# Le filtre `mc_type` de la boutique v1.
_TYPES_V1 = {
    "ecran": "electronics", "bottes": "boots", "casquette": "apparel_casual",
    "protect": "protection", "gants": "gloves", "blouson": "jacket",
    "pantalon": "pants", "housse": "seat", "casque_crs": "helmet.cross",
    "souvet": "apparel_casual", "bagage": "luggage", "outil": "maintenance",
    "casque_jet": "helmet.jet", "carenage": "bodywork", "casque_int": "helmet.integral",
    "combi": "suit", "transmi": "transmission", "casque": "helmet", "huile": "engine",
    "filtre": "engine", "eclair": "bodywork", "casque_mod": "helmet.modular",
    "antivol": "accessories", "bulle": "bodywork", "frein": "brakes",
    "support": "luggage", "batterie": "maintenance", "nettoy": "maintenance",
    "echap": "exhaust",
}

# La v1 a mal encodé ses accents : « écran » est devenu « a » suivi d'un
# caractère de contrôle (`a%C2%89cran`). On rend le « e », de loin la voyelle
# accentuée la plus fréquente en français.
_ACCENT_CASSE = re.compile("a[\u0080-\u009f]")


def normaliser(texte: str) -> str:
    """Un texte réduit à ses mots, comme le reste de la recherche les écrit."""
    texte = _ACCENT_CASSE.sub("e", texte)
    texte = re.sub(r"[^a-z0-9]+", " ", suggestions.sans_accent(texte).lower())
    return " ".join(suggestions.mots(texte))


def phrase(chemin: str) -> str:
    """Les mots d'une ancienne adresse de fiche, prêts à être cherchés."""
    dernier = chemin.strip().strip("/").split("/")[-1]
    return normaliser(unquote(dernier, errors="replace"))


def marque_ecrite(mots: list[str], marques: set[str]) -> str | None:
    """La marque, seulement si elle est écrite EN TOUTES LETTRES.

    Pas la reconnaissance indulgente de la recherche (début de mot, faute de
    frappe) : dans une adresse, « vis » devenait la marque Visiodry et « 100 »
    la marque 100%. « quad lock » ou « o neal », en deux mots, se recollent.
    """
    for i, mot in enumerate(mots):
        if len(mot) >= 3 and not mot.isdigit() and mot in marques:
            return mot
        if i + 1 < len(mots):
            colle = mot + mots[i + 1]
            if colle in marques and len(colle) >= 4:
                return colle
    return None


def rayon_des_mots(mots: list[str]) -> str | None:
    """Le rayon que désigne le PREMIER mot de produit de l'adresse.

    Le premier, parce qu'une ancienne adresse commence par ce qu'est l'article :
    « écran … pour casque » est un écran, pas un casque.
    """
    for i, mot in enumerate(mots):
        seul = mot[:-1] if len(mot) > 3 and mot.endswith("s") else mot
        if seul == "casque":
            for suivant in mots[i + 1:i + 3]:
                if suivant in _SOUS_CASQUE:
                    return _SOUS_CASQUE[suivant]
            return "helmet"
        if seul in _MOTS_RAYON:
            return _MOTS_RAYON[seul]
    return None


def cible_rayon_v1(chemin: str) -> str:
    """`/product-category/casques/integral/page/3/` -> le rayon qui le remplace."""
    morceaux = [m for m in chemin.strip("/").split("/") if m and m != "page" and not m.isdigit()]
    if not morceaux:
        return "/produits"
    code = _RAYONS_V1.get(morceaux[0])
    if code == "helmet" and len(morceaux) > 1:
        code = _SOUS_CASQUE.get(morceaux[1].split("-")[0], code)
    return f"/c/{code}" if code else "/produits"


def cible_boutique_v1(params: dict[str, str], marques_listees: set[str]) -> str:
    """`/shop/?mc_brand=Shad&mc_type=bagage` -> la page qui y répond aujourd'hui.

    `product_cat=protections` (pagination de la boutique v1) vaut le rayon.
    """
    code = (_TYPES_V1.get((params.get("mc_type") or "").strip().lower())
            or _RAYONS_V1.get((params.get("product_cat") or "").strip().lower()))
    nom = re.sub(r"[^a-z0-9]", "", suggestions.sans_accent(params.get("mc_brand") or "").lower())
    marque = nom if nom in marques_listees else None
    if code and marque:
        return f"/c/{code}?marque={marque}"
    if marque:
        return f"/m/{marque}"
    if code:
        return f"/c/{code}"
    return "/produits"


def references(mots: list[str]) -> set[str]:
    """Les références de modèle : lettres ET chiffres mêlés (f100, ro15, u04)."""
    return {m for m in mots if re.search(r"[a-z]", m) and re.search(r"\d", m)}


def cible_fiche_v1(chemin: str, marques: set[str], marques_listees: set[str],
                   candidates) -> str:
    """Une ancienne fiche -> la nouvelle fiche, ou ce qui s'en approche le plus.

    `candidates(marque, phrase)` rend les fiches les plus ressemblantes de la
    marque, `(slug, score, titre)`, meilleure d'abord : la base reste hors de
    ce module.

    LA RÉFÉRENCE DE MODÈLE DOIT ÊTRE LA MÊME. Les mots génériques gonflent la
    ressemblance : « casque modulable hjc f100 gris » trouvait un HJC i91 gris
    au-dessus du seuil — même marque, même type, mauvais casque. Quand
    l'ancienne adresse porte une référence (f100), la fiche visée doit la
    porter aussi, sinon on s'en tient à la page de la marque.
    """
    texte = phrase(chemin)
    mots = texte.split()
    marque = marque_ecrite(mots, marques)
    if marque:
        refs = references(mots)
        for slug, score, titre in candidates(marque, texte) or []:
            if score < SEUIL_FICHE:
                break
            if refs and not refs & set(normaliser(titre or "").split()):
                continue
            return f"/p/{slug}"
        if marque in marques_listees:
            return f"/m/{marque}"
    rayon = rayon_des_mots(mots)
    return f"/c/{rayon}" if rayon else "/produits"


# Les pages de l'ancien site sans équivalent produit.
REDIRECTIONS_FIXES = {
    "/blog": "/guides", "/about": "/infos", "/about-us": "/infos",
    "/terms": "/infos", "/terms-conditions": "/infos",
    "/privacy-policy": "/infos#donnees", "/privacy-policy-2": "/infos#donnees",
    "/favorites": "/comparer", "/compare-products": "/comparer",
    "/comparateur": "/comparer",
    "/sitemap_index.xml": "/sitemap.xml", "/wp-sitemap.xml": "/sitemap.xml",
}
