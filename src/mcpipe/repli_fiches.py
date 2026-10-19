"""Réunir les fiches d'un même casque que le nom du modèle a coupées en deux.

LE CAS SHOEI NEOTEC 3 (19/10/2026). Motoblouz écrit « NEOTEC 3 - FINITION BRILLANT »
sur ses six tailles ; Speedway et La Bécanerie écrivent « Neotec 3 ». Le nom d'une
fiche est tiré d'UNE seule offre par code-barres (match.py, `wording`) : la petite
taille a tiré Motoblouz (« 3 Finition Neotec »), les autres Speedway (« 3 Neotec »).
Deux empreintes, deux fiches, pour un seul casque.

`_FOLD_MODELE` (match.py) aurait réuni ces deux fiches, mais elle ne voit que les
unités d'un même passage de `match` ; ces fiches ont été créées à des passages
différents. Cette règle est la sienne, appliquée à des fiches EXISTANTES, avec des
garde-fous plus durs encore (relecture du 19/10/2026 par deux agents) :

* UNE LISTE BLANCHE de mots sans sens (`MOTS_SANS_SENS`), pas une liste noire : un mot
  en trop qui n'y figure pas (air, drystar, pro, evo, un nom de décor…) désigne peut-être
  un autre article, et la paire est écartée. On n'élargit la liste qu'après avoir lu
  les paires qu'elle ajouterait.
* la couleur COMPLÈTE doit être identique (mat et brillant sont deux produits),
  jamais « inconnue » ;
* la fiche courte n'a qu'UNE longue possible, et réciproquement : pas de chaîne, pas de
  pont entre deux variantes ;
* la preuve vient des CODES-BARRES : au moins un code-barres vivant de la fiche courte a
  déjà écrit le mot en trop (union des jetons de ses offres), et seules des offres de
  marchands à codes-barres fiables, rattachées par code-barres, comptent ;
* les prix médians ne s'écartent pas de plus de 1,5.

Rien ici n'écrit en base : `trouver_paires` est pur ; `fusion-repli` (cli.py) imprime le
rapport, et n'applique que les paires nommées, relues par une personne.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .consolider import marque_canonique

# Les rayons « casque » (1 à 5). Le rayon 30 (accessoires) n'en fait pas partie.
RAYONS = (1, 2, 3, 4, 5)

# Les mots qu'on accepte d'ignorer. « finition » : Motoblouz l'écrit devant brillant/mat,
# et la couleur COMPLÈTE est déjà comparée. Rien d'autre tant que personne n'a relu.
MOTS_SANS_SENS = frozenset({"finition"})

RAPPORT_PRIX_MAX = 1.5


@dataclass(frozen=True)
class FicheRepli:
    id: int
    marque: str
    rayon: int
    couleur: str
    genre: str
    annee: int | None
    jetons: frozenset[str]
    nb_offres: int
    prix_median: float
    # code-barres -> jetons écrits par les offres vivantes qui le portent
    codes_barres: dict[str, frozenset[str]] = field(default_factory=dict, hash=False, compare=False)
    # vrai si toutes les offres vivantes sont rattachées par code-barres chez un marchand fiable
    toutes_fiables: bool = True


def _sans_accent(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def mots_du_titre(titre: str | None) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", _sans_accent((titre or "").lower())))


def _cle(f: FicheRepli, alias: dict[str, str]) -> tuple:
    return (marque_canonique(f.marque, alias), f.rayon, (f.couleur or "").upper(),
            f.genre or "", f.annee)


def _couleur_ok(couleur: str) -> bool:
    return bool(couleur) and couleur.strip().lower() not in ("", "unknown")


def paire_possible(courte: FicheRepli, longue: FicheRepli, alias: dict[str, str],
                   mots: frozenset[str] = MOTS_SANS_SENS) -> bool:
    """La fiche courte et la longue sont-elles le même casque ? Toutes les conditions."""
    if courte.id == longue.id:
        return False
    if _cle(courte, alias) != _cle(longue, alias):
        return False
    # l'année fait partie de la clé : deux années absentes passent, une seule absente est refusée
    marque, rayon, couleur, _, _annee = _cle(courte, alias)
    if not marque or rayon not in RAYONS or not _couleur_ok(couleur):
        return False
    if not (courte.jetons < longue.jetons):
        return False
    en_plus = longue.jetons - courte.jetons
    if not en_plus or not en_plus <= mots:
        return False
    if not courte.toutes_fiables or not courte.codes_barres:
        return False
    # la preuve : la fiche courte a DEJA ecrit le mot en trop, sur au moins un de ses
    # codes-barres. Pas sur tous : une taille vendue par un seul marchand qui n'ecrit jamais
    # « finition » (Speedway, Shoei Neotec 3) ne contredit pas le mot, et exiger tous les
    # codes-barres aurait ecarte le cas meme qu'on corrige. C'est la LISTE BLANCHE qui garde
    # ici : un mot sans sens, deja ecrit par la fiche courte, ne distingue rien.
    if not any(en_plus <= jetons_vus for jetons_vus in courte.codes_barres.values()):
        return False
    if courte.prix_median <= 0 or longue.prix_median <= 0:
        return False
    haut, bas = max(courte.prix_median, longue.prix_median), min(courte.prix_median, longue.prix_median)
    return haut / bas <= RAPPORT_PRIX_MAX


def trouver_paires(fiches: list[FicheRepli], alias: dict[str, str],
                   mots: frozenset[str] = MOTS_SANS_SENS) -> list[tuple[FicheRepli, FicheRepli]]:
    """Les paires (courte, longue) sûres. Une fiche n'est dans AUCUNE paire si elle a
    plus d'un partenaire possible : on ne choisit pas entre deux variantes."""
    index: dict[tuple, dict[frozenset, list[FicheRepli]]] = {}
    for f in fiches:
        index.setdefault(_cle(f, alias), {}).setdefault(f.jetons, []).append(f)
    candidats: list[tuple[FicheRepli, FicheRepli]] = []
    for f in fiches:
        presents = sorted(f.jetons & mots)
        # on retire 1 ou 2 mots de la liste blanche : jamais plus
        retraits = [frozenset({m}) for m in presents]
        retraits += [frozenset({a, b}) for i, a in enumerate(presents) for b in presents[i + 1:]]
        for r in retraits:
            for courte in index.get(_cle(f, alias), {}).get(f.jetons - r, []):
                if paire_possible(courte, f, alias, mots):
                    candidats.append((courte, f))
    par_courte: dict[int, int] = {}
    par_longue: dict[int, int] = {}
    for c, l in candidats:
        par_courte[c.id] = par_courte.get(c.id, 0) + 1
        par_longue[l.id] = par_longue.get(l.id, 0) + 1
    # une fiche qui sert de courte ET de longue (chaîne A < B < C) est écartée aussi
    ids_courtes = {c.id for c, _ in candidats}
    ids_longues = {l.id for _, l in candidats}
    return [(c, l) for c, l in candidats
            if par_courte[c.id] == 1 and par_longue[l.id] == 1
            and c.id not in ids_longues and l.id not in ids_courtes]


def survivant(courte: FicheRepli, longue: FicheRepli) -> int:
    """Celle qui porte le plus d'offres ; à égalité, la plus ancienne."""
    return sorted([courte, longue], key=lambda f: (-f.nb_offres, f.id))[0].id


# --- avec la base -------------------------------------------------------------

_FICHES = """
SELECT p.id, p.brand_code, p.category_id, coalesce(p.colour_code, ''), coalesce(p.genre_age, ''),
       p.model_year, coalesce(p.model_display, '')
FROM product p
WHERE p.status <> 'merged' AND p.category_id = ANY(%s) AND p.brand_code IS NOT NULL
  AND coalesce(p.model_core_ref, '') = ''
"""

_OFFRES = """
SELECT o.product_id, o.gtin, o.price, o.link_method, m.gtin_trust, sg.model_tokens
FROM raw_offer o
JOIN merchant m ON m.id = o.merchant_id
LEFT JOIN offer_signature sg ON sg.raw_offer_id = o.id
WHERE o.is_live AND o.price > 0 AND o.product_id = ANY(%s)
"""

_GROUPES_REFUSES = "SELECT produit_ids FROM fusion_proposee WHERE statut = 'refusee'"


def _mediane(xs: list[float]) -> float:
    xs = sorted(xs)
    n = len(xs)
    return 0.0 if not n else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2)


def charger(conn, alias: dict[str, str]) -> list[FicheRepli]:
    with conn.cursor() as cur:
        cur.execute(_FICHES, (list(RAYONS),))
        base = {r[0]: r for r in cur.fetchall()}
        cur.execute(_OFFRES, (list(base),))
        offres = cur.fetchall()
    prix: dict[int, list[float]] = {}
    cb: dict[int, dict[str, set[str]]] = {}
    fiables: dict[int, bool] = {}
    for pid, gtin, price, methode, confiance, jetons in offres:
        prix.setdefault(pid, []).append(float(price))
        ok = methode == "gtin" and confiance == "trusted" and gtin
        fiables[pid] = fiables.get(pid, True) and bool(ok)
        if ok:
            cb.setdefault(pid, {}).setdefault(gtin, set()).update(jetons or [])
    sortie = []
    for pid, (_, marque, rayon, couleur, genre, annee, nom) in base.items():
        if pid not in prix:
            continue
        sortie.append(FicheRepli(
            pid, marque, rayon, couleur, genre, annee, frozenset(nom.lower().split()),
            len(prix[pid]), _mediane(prix[pid]),
            {g: frozenset(j) for g, j in cb.get(pid, {}).items()}, fiables.get(pid, False)))
    return sortie


def paires_de_la_base(conn, alias: dict[str, str],
                      mots: frozenset[str] = MOTS_SANS_SENS) -> list[tuple[FicheRepli, FicheRepli]]:
    """Les paires sûres, moins celles que la propriétaire a déjà refusées."""
    paires = trouver_paires(charger(conn, alias), alias, mots)
    with conn.cursor() as cur:
        cur.execute(_GROUPES_REFUSES)
        refusees = [set(ids) for (ids,) in cur.fetchall()]
    return [(c, l) for c, l in paires
            if not any({c.id, l.id} <= g for g in refusees)]


def appliquer_paires(conn, demandees: list[tuple[int, int]]) -> dict[str, int]:
    """Fusionne les paires nommées (courte, longue), et elles seules.

    Chaque paire est re-vérifiée sur les données du moment : une paire qui ne passe
    plus la règle est refusée avec une erreur, jamais fusionnée « quand même ». Les
    groupes sont écrits `validee` dans `fusion_proposee` (clé « repli:… », jamais
    touchés par le proposer de la nuit, qui ne supprime que les `proposee`), puis
    appliqués par `consolider.appliquer(cles=…)`, qui trace l'état d'avant.
    """
    import hashlib

    from . import consolider as c

    alias = c.charger_alias(conn)
    sures = {(a.id, b.id): (a, b) for a, b in paires_de_la_base(conn, alias)}
    cles = []
    for courte, longue in demandees:
        if (courte, longue) not in sures:
            raise ValueError(f"paire {courte}:{longue} absente de la liste sure : rien n'est fusionne")
    for courte, longue in demandees:
        a, b = sures[(courte, longue)]
        ids = sorted([a.id, b.id])
        cle = hashlib.md5(("repli:" + ",".join(map(str, ids))).encode()).hexdigest()
        with conn.cursor() as cur:
            cur.execute("SELECT count(DISTINCT merchant_id) FROM raw_offer "
                        "WHERE product_id = ANY(%s) AND is_live", (ids,))
            marchands = cur.fetchone()[0]
            cur.execute("""
                INSERT INTO fusion_proposee (cle, produit_ids, survivant, nb_fiches, nb_marchands, statut, decide_le)
                VALUES (%s, %s, %s, 2, %s, 'validee', now())
                ON CONFLICT (cle) DO UPDATE SET statut = 'validee', decide_le = now()
                WHERE fusion_proposee.statut IN ('proposee', 'validee')""",
                        (cle, ids, survivant(a, b), marchands))
        cles.append(cle)
    conn.commit()
    return c.appliquer(cles=cles)
