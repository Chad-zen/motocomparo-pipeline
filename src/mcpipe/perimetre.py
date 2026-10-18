"""Quelles lignes d'un flux entrent, AVANT qu'elles ne touchent la base.

Un nouveau marchand n'arrive pas avec tout son catalogue : le flux de Motard Bleu
compte 130 143 lignes, dont 43 113 « non classées » (rétroviseurs, filtres à air,
clignotants…) et des milliers de pièces dans des rayons où les fausses fusions
sont les plus fréquentes. Le périmètre dit ce qu'on laisse entrer, et il le dit
au téléchargement : une ligne écartée ne passe jamais par `stg_feed_row`.

Décidé le 18/10/2026, après deux revues indépendantes du plan :

* « Seulement les rayons qu'on tient déjà » (la propriétaire), et d'abord
  l'ÉQUIPEMENT DU PILOTE. Les pièces viendront dans un second lot, quand
  `mcpipe verify` sera propre : 37 239 lignes de pièces seraient entrées par le
  seul rayon, 24 213 sans code-barres connu ni parent, c'est-à-dire sans moyen de
  les rapprocher d'une fiche existante.
* Une ligne entre si le code-barres est valide ET :
    1. il existe déjà chez un autre marchand vivant (le produit est connu : on
       n'ajoute qu'un prix, ça ne peut pas créer une fiche), OU
    2. la ligne a DÉJÀ été admise par un passage précédent (voir ci-dessous), OU
    3. c'est de l'équipement du pilote ET la ligne a un `parent_product_id` (sans
       parent, rien ne dit à quelle fiche elle appartient : 873 clés d'identité
       mêlaient quatre codes-barres ou plus pour une seule taille).

* LE PÉRIMÈTRE EST MONOTONE. La règle 1 dépend de l'état des AUTRES marchands : si
  Motoblouz perd des offres une nuit, les lignes de Motard Bleu retenues par leur
  code-barres sortiraient du flux filtré, et le disjoncteur de retrait de
  `normalize` (20 %) s'enclencherait ; `--force` deviendrait routinier. Une ligne
  déjà en base pour ce marchand (règle 2) reste donc admise tant qu'elle figure dans
  le flux.
"""

from __future__ import annotations

from . import textnorm as tn
from .category import classify

# Casques (et leurs sous-types), blousons, pantalons, gants, bottes, combinaisons,
# protections du pilote, masques, maillots cross, pièces et accessoires de casque.
# `classify` ne rend jamais 28 ni 29 : c'est `enrich` qui sépare les protections.
EQUIPEMENT_PILOTE: frozenset[int] = frozenset({1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 26, 27, 30})

PERIMETRES: dict[str, frozenset[int]] = {"equipement_pilote": EQUIPEMENT_PILOTE}


def cle_gtin(brut: str | None) -> str | None:
    """Le code-barres comparable : valide, sans zéros de tête. None sinon.

    Les autres flux écrivent un EAN-13 là où celui-ci écrit un UPC-A (12 chiffres) :
    les zéros de tête n'y changent pas le produit."""
    g = tn.valid_gtin(brut)
    return g.lstrip("0") if g else None


# LE GARDE-FOU DE PRIX, A LA PORTE. Pour un code-barres que d'autres marchands
# vendent deja, un prix quatre fois plus haut ou quatre fois plus bas que leur
# MEDIANE n'est pas une affaire, c'est presque toujours un code-barres reutilise
# pour un autre article (20,82 € contre 336,90 € sur le flux de Motard Bleu) ou un
# prix saisi de travers. L'offre est ecartee SEULE : la fiche des autres marchands
# n'est pas touchee, contrairement au seuil de 5x de `match` qui met le code-barres
# entier en quarantaine (mesure sur ce flux : 19 fiches saines y seraient tombees).
# Sur 67 876 codes-barres communs, 283 sortent par le bas et 21 par le haut.
RATIO_PRIX_MIN = 0.25
RATIO_PRIX_MAX = 4.0


def decision(
    perimetre: str,
    *,
    ean: str | None,
    categorie: str | None,
    titre: str | None,
    parent: str | None,
    sku: str | None,
    eans_connus: set[str],
    deja_admis: set[str],
    prix: float | None = None,
    prix_ref: dict[str, float] | None = None,
    marque: str | None = None,
    marques_ref: dict[str, frozenset[str]] | None = None,
) -> tuple[bool, str]:
    """(gardée ?, raison) — la raison sert aux comptes du journal et aux tests."""
    gtin = cle_gtin(ean)
    if gtin is None:
        return False, "ean_invalide"
    # LA MARQUE EN DESACCORD. Un code-barres que d'autres marchands vendent sous la
    # marque X et que celui-ci vend sous la marque Y n'est pas le meme article, ou un
    # nom de marque que le dictionnaire ne sait pas encore lire. Dans les deux cas
    # `match` mettrait le code-barres ENTIER en quarantaine, donc les offres des
    # AUTRES marchands avec (11 137 codes-barres au premier essai complet). On
    # ecarte l'offre de ce flux, seule.
    connues = (marques_ref or {}).get(gtin)
    if marque and connues and marque not in connues:
        return False, "marque_en_desaccord"
    ref = (prix_ref or {}).get(gtin)
    if ref and prix and not (RATIO_PRIX_MIN <= prix / ref <= RATIO_PRIX_MAX):
        return False, "prix_aberrant"
    if gtin in eans_connus:
        return True, "ean_connu"
    if sku and sku in deja_admis:
        return True, "deja_admis"
    rayons = PERIMETRES[perimetre]
    if classify(categorie, titre) not in rayons:
        return False, "hors_rayon"
    if not (parent or "").strip():
        return False, "sans_parent"
    return True, "rayon_tenu"
