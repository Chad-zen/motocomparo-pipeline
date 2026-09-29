"""A small, coarse category taxonomy, and a keyword classifier for the
merchants' free-text `raw_category` paths.

`product.category_id` is NOT NULL, so `match` cannot insert a single row until
this runs. The taxonomy is deliberately shallow (~25 categories) — good enough
to keep EPI categories (helmets) separate from parts, which is all `match`
needs for its category-based guardrails. Getting *every* raw path right is
`enrich`'s job later; this just has to not be wrong in a way that causes a
false merge.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from . import textnorm as tn
from .db import connect

# (id, parent_id, code, label_fr) — ids are fixed and referenced by CATEGORY_RULES
CATEGORIES: list[tuple[int, int | None, str, str]] = [
    (1, None, "helmet", "Casques"),
    (2, 1, "helmet.integral", "Casques intégraux"),
    (3, 1, "helmet.jet", "Casques jet"),
    (4, 1, "helmet.modular", "Casques modulables"),
    (5, 1, "helmet.cross", "Casques cross"),
    (6, None, "jacket", "Blousons & vestes"),
    (7, None, "pants", "Pantalons"),
    (8, None, "gloves", "Gants"),
    (9, None, "boots", "Bottes & chaussures"),
    (10, None, "suit", "Combinaisons"),
    (11, None, "protection", "Protections"),
    (12, None, "exhaust", "Échappements"),
    (13, None, "transmission", "Transmission"),
    (14, None, "brakes", "Freinage"),
    (15, None, "engine", "Moteur"),
    (16, None, "suspension", "Suspension"),
    (17, None, "tyres", "Pneus"),
    (18, None, "bodywork", "Carénage & carrosserie"),
    (19, None, "electronics", "Électronique & connectique"),
    (20, None, "luggage", "Bagagerie"),
    (21, None, "seat", "Selles"),
    (22, None, "maintenance", "Entretien"),
    (23, None, "apparel_casual", "Vêtements casual / lifestyle"),
    (24, None, "accessories", "Accessoires"),
    (25, None, "unknown", "Non classé"),
    # Ajoutés le 14/09/2026, après avoir mesuré ce qui tombait dans « non
    # classé » : 10 400 offres d'ÉQUIPEMENT que la taxonomie n'avait tout
    # simplement pas de case pour recevoir. La v1 avait les deux rayons.
    (26, None, "goggles", "Masques & lunettes"),
    (27, None, "jersey", "Maillots cross"),
    # Ajoutés le 14/09/2026. Le rayon 11 « Protections » était un fourre-tout de
    # 44 350 offres qui mélangeait ce qui protège le PILOTE (dorsales, gilets,
    # cervicales) et ce qui protège la MOTO (pare-carters, sabots moteur,
    # protège-réservoir). Conséquence visible : sur la fiche d'une protection
    # cervicale Alpinestars, l'étagère « dans la même gamme de prix » proposait
    # un pare-carter SW-Motech et une protection moteur R&G — même prix, même
    # rayon, aucun rapport. Aucun filtre ne pouvait les séparer tant qu'ils
    # portaient le même numéro.
    (28, 11, "protection.pilote", "Protections du pilote"),
    (29, 11, "protection.moto", "Protections de la moto"),
    # Ajouté le 29/09/2026, après avoir mesuré ce que contenait la catégorie 1
    # générique : des centaines d'écrans, pinlocks, mousses de joues et
    # mentonnières détachées, rangés comme des casques faute d'un rayon pour
    # les recevoir — signalé par la propriétaire sur deux fiches précises
    # (un écran solaire O'Neal, un pinlock HJC), généralisé après coup.
    (30, 1, "helmet.accessory", "Pièces & accessoires casque"),
]

_UNKNOWN_ID = 25

# ordered: first regex to match a normalized raw_category (or title, as a
# fallback) wins — specific subtypes are listed before their parent category
#
# L'ACCESSOIRE PASSE AVANT TOUT LE RESTE DU RAYON CASQUE, sous-types compris.
# Mesuré le 29/09/2026 : 2 300 fiches dans la catégorie 1 (« Casques »
# générique), dont plusieurs centaines n'étaient pas des casques du tout —
# écrans, pinlocks, mousses de joues, mentonnières détachées, calottes. Le
# marchand écrit presque toujours "casque" quelque part dans le chemin d'une
# pièce détachée de casque ("Pièces Détachées Casque", "Casque moto > Pinlock
# et anti-buée", "Visière et accessoire > ... > Visière de casque"), donc
# l'ancienne règle générique (`\bcasque\b`, ligne plus bas) les avalait — et
# une règle de SOUS-TYPE placée avant elle aurait fait pareil pour un "écran
# teinté pour casque intégral". D'où sa position : tout en tête, avant même
# les sous-types.
_RULES: list[tuple[re.Pattern, int]] = [
    (re.compile(
        r"\bcasque\b.*(visiere|visor|ecran|pinlock|mentonniere|coiffe|mousse"
        r"|bavette|spoiler|joues|calotte)"
        r"|(?:visiere|visor|ecran|pinlock|mentonniere|calotte).*\bcasque\b"
        r"|pieces? detach.*casque|casque.*pieces? detach"
    ), 30),
    (re.compile(r"\bcasque\b.*(integral|integrale)|full ?face|\bhelmets?\b"), 2),
    (re.compile(r"\bcasque\b.*(jet|demi.?jet|bol)"), 3),
    (re.compile(r"\bcasque\b.*(modulable|flip|modular)"), 4),
    (re.compile(r"\bcasque\b.*cross|cross.*\bcasque\b"), 5),
    (re.compile(r"\bcasque\b|\bhelmet\b"), 1),
    # Avant les vêtements : « maillot cross » n'est ni un blouson ni un
    # tee-shirt, et « masque » n'était attrapé par aucune règle. 7 293 et
    # 2 156 offres respectivement, toutes en « non classé » jusqu'ici.
    (re.compile(r"\bmaillots?\b.*\b(cross|motocross|mx)\b"
                r"|\b(cross|motocross|mx)\b.*\bmaillots?\b"), 27),
    (re.compile(r"\bmasques?\b|\bgoggles?\b|\blunettes?\b"), 26),
    # Les frontières de mot ne sont pas décoratives : `caps?` sans elles
    # attrape « capot » et « capacité ». Le négatif exclut la « casquette de
    # phare » : une pièce de carénage (le carénage avant qui coiffe le phare),
    # pas un couvre-chef — trouvée dans la même mesure du 29/09/2026, sous
    # "Carénage > Carénage > Casquette de phare".
    (re.compile(r"\bcasquettes?\b(?!\s+de\s+phare)|\bcaps\b|\bbonnets?\b"), 23),
    (re.compile(r"\bblouson\b|\bveste\b|\bjacket\b(?!.*helmet)"), 6),
    (re.compile(r"\bpantalon\b|\bjean\b|\bpants\b"), 7),
    (re.compile(r"\bgants?\b|\bgloves?\b"), 8),
    (re.compile(r"\bbottes?\b|\bchaussures?\b|\bbaskets?\b|\bboots?\b"), 9),
    (re.compile(r"\bcombinaison\b|\bsuits?\b"), 10),
    (re.compile(
        r"\bprotection\b|\bdorsale\b|\bplastron\b|genouill|\bcoude\b|\bairbag\b|\bprotector\b"
    ), 11),
    (re.compile(r"\bechappement\b|\bsilencieux\b|\bexhaust\b"), 12),
    (re.compile(r"\btransmission\b|\bchaine\b|\bcouronne\b|\bpignon\b"), 13),
    (re.compile(r"\bfreinage\b|\bfrein\b|\bdisque\b|\bplaquette\b|\bdurite\b|\bbrake\b"), 14),
    (re.compile(r"\bmoteur\b|\bpiston\b|\bculasse\b|\bvilebrequin\b|\bcarter\b|\bengine\b"), 15),
    (re.compile(r"\bsuspension\b|\bamortisseur\b|\bfourche\b"), 16),
    (re.compile(r"\bpneu\b|\btyre\b|\btire\b"), 17),
    (re.compile(r"\bcarenage\b|\bcarrosserie\b|\bplaque\b|\bbodywork\b|\bfairing\b"), 18),
    (re.compile(
        r"\bintercom\b|\bgps\b|\btelephone\b|\belectronique\b|\bmultimedia\b|\bcommunication\b"
    ), 19),
    (re.compile(r"\bbagagerie\b|\bsacoche\b|top ?case|\bvalise\b|\bbags?\b"), 20),
    (re.compile(r"\bselle\b|\bseats?\b"), 21),
    (re.compile(r"\bentretien\b|\blubrifiant\b|\bnettoyant\b|\bmaintenance\b"), 22),
    (re.compile(r"\bsportswear\b|tee.?shirt|\bpolo\b|\bstreetwear\b|\btops?\b"), 23),
]


@dataclass
class CategorizeResult:
    categories_seeded: int
    paths_mapped: int
    seconds: float


def classify(raw_category: str | None, title: str | None = None) -> int:
    """Best-guess category id for one merchant category path (or title, as a
    fallback when the path is empty). Never fails — returns the catch-all."""
    blob = tn.norm_txt(raw_category) or tn.norm_txt(title)
    if blob:
        for pattern, cat_id in _RULES:
            if pattern.search(blob):
                return cat_id
    return _UNKNOWN_ID


def categorize(
    remap_unknown: bool = False, remap_categories: set[int] | None = None
) -> CategorizeResult:
    """Seed `category`, then map every merchant `raw_category` path seen in
    `raw_offer` into `category_map` (cached, so `match` is a plain join).

    `remap_unknown` re-runs the rules over the paths currently mapped to the
    catch-all. C'est le complément indispensable d'une règle ajoutée : sans lui,
    un chemin déjà rangé en « non classé » y reste pour toujours, puisque la
    requête ci-dessous ne regarde que les chemins JAMAIS vus. Deux rayons ont
    ainsi été créés (masques, maillots cross) sans qu'une seule offre les
    rejoigne — le genre de correctif qui a l'air appliqué et ne l'est pas.

    `remap_categories` généralise l'idée à N'IMPORTE QUELLE catégorie, pas
    seulement 25 : ajouté le 29/09/2026 pour rejouer les chemins actuellement
    en catégorie 1 (« Casques ») après la règle qui en a sorti les accessoires
    (visières, pinlocks…) vers la 30. `remap_unknown=True` reste équivalent à
    `remap_categories={25}` — les deux se combinent si les deux sont passés.

    Chaque option ne touche QUE les chemins actuellement dans les catégories
    visées : un chemin déjà rangé ailleurs n'est jamais réévalué, donc rien
    ici ne peut déclasser un chemin correctement trié par une règle plus
    récente que celle qui l'a rangé la première fois.
    """
    cibles = set(remap_categories or set())
    if remap_unknown:
        cibles.add(_UNKNOWN_ID)
    t0 = time.time()
    conn = connect()
    try:
        with conn.cursor() as cur:
            for cid, parent, code, label in CATEGORIES:
                cur.execute(
                    """
                    INSERT INTO category (id, parent_id, code, label_fr)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        parent_id = EXCLUDED.parent_id,
                        code = EXCLUDED.code,
                        label_fr = EXCLUDED.label_fr
                    """,
                    (cid, parent, code, label),
                )
            seeded = len(CATEGORIES)

            cur.execute(
                """
                SELECT DISTINCT o.merchant_id, o.raw_category
                FROM raw_offer o
                LEFT JOIN category_map cm
                    ON cm.merchant_id = o.merchant_id AND cm.raw_path = o.raw_category
                WHERE o.raw_category IS NOT NULL AND cm.id IS NULL
                """
            )
            pairs = cur.fetchall()

            if cibles:
                cur.execute(
                    """
                    SELECT DISTINCT cm.merchant_id, cm.raw_path
                    FROM category_map cm WHERE cm.category_id = ANY(%s)
                    """,
                    (list(cibles),),
                )
                pairs += cur.fetchall()
            for merchant_id, raw_category in pairs:
                cat_id = classify(raw_category)
                cur.execute(
                    """
                    INSERT INTO category_map (merchant_id, raw_path, category_id, confidence)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (merchant_id, raw_path) DO UPDATE SET
                        category_id = EXCLUDED.category_id, confidence = EXCLUDED.confidence
                    """,
                    (merchant_id, raw_category, cat_id, 0.60 if cat_id != _UNKNOWN_ID else 0.10),
                )
        conn.commit()
        return CategorizeResult(seeded, len(pairs), time.time() - t0)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
