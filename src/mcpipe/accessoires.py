"""Ranger parmi les accessoires les fiches qui ne sont pas ce que leur rayon annonce.

`enrich` corrige la categorie des OFFRES qui arrivent ; `match` n'en fait rien
pour les fiches qui existent deja (une offre rattachee n'est plus revue). Les
pages casque integral et casque cross portaient donc des coussinets de joue, des
pare-soleil, des pics et des lentilles de lunettes ; les bottes, des chaussettes
et des sangles ; les gants, des sous-gants (17/10/2026). Et la courbe de budget
de l'accueil, lue sur ces memes rayons, en etait faussee.

Cette passe range ces fiches -- en « Pieces et accessoires casque » (30) pour le
casque, en « Accessoires » (24) pour les vetements -- quand TOUTES leurs offres
vivantes sont des pieces : une fiche mixte (un casque et sa piece sous le meme
code-barres) n'est pas touchee.

Sans `appliquer`, elle compte et montre des exemples, rien n'est ecrit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import textnorm as tn
from .category import categorize, classify
from .db import connect
from .enrich import is_helmet_accessory

_RAYONS_CASQUE = (1, 2, 3, 4, 5)
_ACCESSOIRE_CASQUE = 30
_ACCESSOIRES = 24

# Par rayon de vetement : des mots de piece qui valent TOUJOURS (`fort`), des mots
# qui valent seulement quand le titre ne nomme pas le vetement lui-meme (`faible`
# + `vetement`) : « Sangle et boucle Alpinestars Tech 10 » est une piece, « Bottes
# a boucle » une botte. Lu sur les 16 fiches les moins cheres de chaque rayon
# (17/10/2026) : chaussettes et sangles chez les bottes, sous-gants chez les gants.
# Les vestes de pluie a 17 EUR, elles, sont de vrais blousons : rien ne les touche.
_REGLES: dict[int, dict[str, re.Pattern]] = {
    9: {  # bottes & chaussures
        "fort": re.compile(r"\bchaussettes?\b|\bsliders?\b|\bsemelles?\b|\bcirage\b|\bnettoyant\b"
                           r"|\bgraisse\b|\bimpermeabilisant\b|\bpieces? detachees?\b|\bde remplacement\b"),
        "faible": re.compile(r"\bsangles?\b|\bboucles?\b|\blacets?\b|\bembouts?\b|\bkit\b|\bsac\b"),
        "vetement": re.compile(r"\b(?:bottes?|bottines?|chaussures?|baskets?|boots?|sneakers?|brodequins?)\b"),
    },
    8: {  # gants
        "fort": re.compile(r"\bsous ?gants?\b|\bsliders?\b|\bnettoyant\b|\bgraisse\b|\bimpermeabilisant\b"
                           r"|\bpieces? detachees?\b|\bde remplacement\b"),
        "faible": re.compile(r"\bkit\b|\bsac\b|\bdoublures?\b|\bprotege ?poignets?\b|\bpatins?\b"),
        "vetement": re.compile(r"\b(?:gants?|mitaines?|moufles?|gloves?)\b"),
    },
    6: {  # blousons & vestes
        "fort": re.compile(r"\bnettoyant\b|\bimpermeabilisant\b|\bgraisse\b"
                           r"|\bpieces? detachees?\b|\bde remplacement\b"),
        "faible": re.compile(r"\bdorsales?\b|\bdoublures?\b|\bprotections?\b|\becussons?\b|\bpatch(?:es)?\b"
                             r"|\bsangles?\b|\bkit\b|\bbretelles?\b|\bceintures?\b|\bsac\b|\bpoches?\b"
                             r"|\bfermetures?\b"),
        "vetement": re.compile(r"\b(?:vestes?|blousons?|jackets?|manteaux?|parkas?|gilets?|coupe ?vent|k ?way"
                               r"|poncho|combinaisons?|surchemises?|chemises?|pulls?|sweats?|hoodies?)\b"),
    },
    7: {  # pantalons
        "fort": re.compile(r"\bnettoyant\b|\bimpermeabilisant\b|\bpieces? detachees?\b"
                           r"|\bde remplacement\b"),
        "faible": re.compile(r"\bdoublures?\b|\bceintures?\b|\bbretelles?\b|\bgenouilleres?\b|\bsliders?\b"
                             r"|\bkit\b|\bsac\b"),
        "vetement": re.compile(r"\b(?:pantalons?|jeans?|pants?|leggings?|shorts?|bermudas?|surpantalons?"
                               r"|salopettes?|combinaisons?|treillis|cargo|cuissards?|bibs?)\b"),
    },
}
# `spray` n'est PAS un mot de piece : « Veste de pluie Macna SPRAY » est une veste
# (la gamme s'appelle ainsi), vu a la premiere relecture. Les produits d'entretien se
# disent « nettoyant », « graisse », « impermeabilisant ».
_RAYONS_VETEMENT = tuple(_REGLES)

_SQL = """
SELECT p.id, p.category_id, o.id, o.raw_title, o.raw_category, s.cheapest
FROM product p
JOIN raw_offer o ON o.product_id = p.id AND o.linked_status = 'linked' AND o.is_live
LEFT JOIN product_stats s ON s.product_id = p.id
WHERE p.category_id = ANY(%s) AND p.status <> 'merged'
"""


@dataclass
class Rayon:
    fiches: int = 0
    a_ranger: int = 0
    mixtes: int = 0
    rangees: int = 0
    exemples: list[str] = field(default_factory=list)
    # les plus CHERS : une vraie piece coute peu, un vetement pris pour une piece
    # ressort ici
    plus_chers: list[str] = field(default_factory=list)


@dataclass
class Resultat:
    rayons: dict[str, Rayon] = field(default_factory=dict)

    # compatibilite avec la premiere version (casque seul)
    @property
    def fiches_casque(self) -> int:
        return self.rayons.get("casque", Rayon()).fiches

    @property
    def a_ranger(self) -> int:
        return sum(r.a_ranger for r in self.rayons.values())

    @property
    def rangees(self) -> int:
        return sum(r.rangees for r in self.rayons.values())


def est_une_piece(titre: str | None, categorie_marchand: str | None) -> bool:
    """Offre d'un casque : une piece si son titre le dit, ou si le chemin de
    categorie du marchand, lu avec les regles d'aujourd'hui, la range en 30."""
    return is_helmet_accessory(titre) or classify(categorie_marchand) == _ACCESSOIRE_CASQUE


def est_un_accessoire_vetement(rayon: int, titre: str | None) -> bool:
    regles = _REGLES.get(rayon)
    blob = tn.norm_txt(titre)
    if not regles or not blob:
        return False
    if regles["fort"].search(blob):
        return True
    return bool(regles["faible"].search(blob)) and not regles["vetement"].search(blob)


def ranger_accessoires(appliquer: bool = False) -> Resultat:
    # Les chemins deja ranges en casque sont relus avec les regles actuelles :
    # « Casquette de casque cross » y restait depuis avant la regle des pieces.
    if appliquer:
        categorize(remap_categories=set(_RAYONS_CASQUE))
    res = Resultat()
    nom_rayon = {**{c: "casque" for c in _RAYONS_CASQUE}, 9: "bottes", 8: "gants", 6: "blousons", 7: "pantalons"}
    for nom in dict.fromkeys(nom_rayon.values()):
        res.rayons[nom] = Rayon()
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_SQL, (list(_RAYONS_CASQUE) + list(_RAYONS_VETEMENT),))
            par_fiche: dict[int, dict] = {}
            for pid, cat, oid, titre, chemin, cheapest in cur.fetchall():
                fiche = par_fiche.setdefault(pid, {"cat": cat, "lignes": [], "prix": float(cheapest or 0)})
                if cat in _RAYONS_CASQUE:
                    piece = est_une_piece(titre, chemin)
                else:
                    piece = est_un_accessoire_vetement(cat, titre)
                fiche["lignes"].append((oid, titre, piece))
            deplacer: dict[int, list[int]] = {_ACCESSOIRE_CASQUE: [], _ACCESSOIRES: []}
            offres: dict[int, list[int]] = {_ACCESSOIRE_CASQUE: [], _ACCESSOIRES: []}
            par_rayon: dict[str, list[tuple[float, str]]] = {n: [] for n in res.rayons}
            for pid, fiche in par_fiche.items():
                r = res.rayons[nom_rayon[fiche["cat"]]]
                r.fiches += 1
                nb = sum(1 for _o, _t, piece in fiche["lignes"] if piece)
                if nb == len(fiche["lignes"]):
                    cible = _ACCESSOIRE_CASQUE if fiche["cat"] in _RAYONS_CASQUE else _ACCESSOIRES
                    deplacer[cible].append(pid)
                    offres[cible] += [o for o, _t, _p in fiche["lignes"]]
                    r.a_ranger += 1
                    par_rayon[nom_rayon[fiche["cat"]]].append((fiche["prix"], fiche["lignes"][0][1]))
                    if len(r.exemples) < 12:
                        r.exemples.append(fiche["lignes"][0][1])
                elif nb:
                    r.mixtes += 1
            for nom, lignes in par_rayon.items():
                res.rayons[nom].plus_chers = [f"{p:.0f} EUR  {t}" for p, t in sorted(lignes, reverse=True)[:12]]
            if appliquer:
                for cible, ids in deplacer.items():
                    if not ids:
                        continue
                    cur.execute("UPDATE product SET category_id = %s WHERE id = ANY(%s)", (cible, ids))
                    cur.execute("UPDATE offer_signature SET category_id = %s WHERE raw_offer_id = ANY(%s)",
                                (cible, offres[cible]))
                # compte des fiches rangees, par rayon d'origine
                for cible, ids in deplacer.items():
                    for pid in ids:
                        res.rayons[nom_rayon[par_fiche[pid]["cat"]]].rangees += 1
        if appliquer:
            conn.commit()
        else:
            conn.rollback()
        return res
    finally:
        conn.close()


# nom d'origine, gardee pour l'appel du planificateur
ranger_accessoires_casque = ranger_accessoires
