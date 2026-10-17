"""Ranger parmi les pieces et accessoires les fiches casque qui n'en sont pas.

`enrich` corrige la categorie des OFFRES qui arrivent ; `match` n'en fait rien
pour les fiches qui existent deja (une offre rattachee n'est plus revue). Les
pages casque integral et casque cross portaient donc des coussinets de joue, des
pare-soleil, des pics et des lentilles de lunettes (17/10/2026). Cette passe
range ces fiches en categorie 30 -- « Pieces et accessoires casque » -- quand
TOUTES leurs offres vivantes sont des pieces : une fiche mixte (un casque et sa
piece sous le meme code-barres) n'est pas touchee.

Sans `appliquer`, elle compte et montre des exemples, rien n'est ecrit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .category import categorize, classify
from .db import connect
from .enrich import is_helmet_accessory

_RAYONS_CASQUE = (1, 2, 3, 4, 5)
_ACCESSOIRE = 30

_SQL = """
SELECT p.id, o.id, o.raw_title, o.raw_category
FROM product p
JOIN raw_offer o ON o.product_id = p.id AND o.linked_status = 'linked' AND o.is_live
WHERE p.category_id = ANY(%s) AND p.status <> 'merged'
"""


@dataclass
class Resultat:
    fiches_casque: int = 0
    a_ranger: int = 0
    mixtes: int = 0
    rangees: int = 0
    exemples: list[str] = field(default_factory=list)


def est_une_piece(titre: str | None, categorie_marchand: str | None) -> bool:
    """Une offre est une piece de casque si son titre le dit, ou si le chemin de
    categorie du marchand, lu avec les regles d'aujourd'hui, la range en 30."""
    return is_helmet_accessory(titre) or classify(categorie_marchand) == _ACCESSOIRE


def ranger_accessoires_casque(appliquer: bool = False) -> Resultat:
    # Les chemins deja ranges en casque sont relus avec les regles actuelles :
    # « Casquette de casque cross » y restait depuis avant la regle des pieces.
    if appliquer:
        categorize(remap_categories=set(_RAYONS_CASQUE))
    res = Resultat()
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_SQL, (list(_RAYONS_CASQUE),))
            par_fiche: dict[int, list[tuple[int, str, bool]]] = {}
            for pid, oid, titre, cat in cur.fetchall():
                par_fiche.setdefault(pid, []).append((oid, titre, est_une_piece(titre, cat)))
            res.fiches_casque = len(par_fiche)
            a_ranger: list[int] = []
            offres: list[int] = []
            for pid, lignes in par_fiche.items():
                nb = sum(1 for _oid, _t, piece in lignes if piece)
                if nb == len(lignes):
                    a_ranger.append(pid)
                    offres += [oid for oid, _t, _p in lignes]
                    if len(res.exemples) < 12:
                        res.exemples.append(lignes[0][1])
                elif nb:
                    res.mixtes += 1
            res.a_ranger = len(a_ranger)
            if appliquer and a_ranger:
                cur.execute("UPDATE product SET category_id = %s WHERE id = ANY(%s)",
                            (_ACCESSOIRE, a_ranger))
                res.rangees = cur.rowcount
                cur.execute("UPDATE offer_signature SET category_id = %s WHERE raw_offer_id = ANY(%s)",
                            (_ACCESSOIRE, offres))
        if appliquer:
            conn.commit()
        else:
            conn.rollback()
        return res
    finally:
        conn.close()
