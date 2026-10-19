"""Un rapport, en lecture seule, qui note chaque regroupement de fiches proposé.

POURQUOI (19/10/2026). `consolider` propose des regroupements, la propriétaire les
valide un par un : 527 en attente. Elle a remarqué que dans un vrai doublon les
tailles se COMPLÈTENT et que les codes-barres se SUIVENT (Furygan Brooks : une fiche
S, M, L, 4XL, l'autre XL et 2XL). Mais deux COLORIS d'un même modèle donnent aussi des
tailles complémentaires et des codes-barres voisins : la règle seule ne suffit pas, et
le contre-exemple est la Falco Starboy 4 (semelle blanche / tout noir).

CE QUE FAIT CE MODULE : il ne fusionne RIEN et n'écrit RIEN en base. Pour chaque
groupe, il compare ses fiches deux à deux sur des signaux indépendants et rend un
verdict avec ses raisons, pour qu'une personne relise un échantillon et mesure le
taux d'erreur AVANT qu'on automatise quoi que ce soit.

VERDICTS, du plus sûr au moins sûr :
  sur       aucun veto, couleur complète connue et identique, prix à 1,5× au plus, et
            un code-barres partagé OU une même référence fabricant (`base_sku`)
  probable  aucun veto, couleur complète identique, prix à 1,5× au plus, tailles qui
            se complètent ET codes-barres du même bloc et à quelques unités les uns
            des autres
  douteux   aucun veto, mais un des signaux manque (couleur inconnue d'un côté...)
  refuser   au moins un veto

VETOS (jamais assouplis) : une même taille avec deux codes-barres différents d'une fiche
à l'autre ; une couleur COMPLÈTE différente (« BK|MAT » et « BK|GLO » sont deux
produits) ; un genre ou un âge différent, une année différente ; des prix à plus de 3×.

L'image n'est PAS un signal ici : deux marchands photographient presque toujours un même
article différemment, et deux coloris du même modèle se ressemblent. Elle ne pourrait
servir que de veto, et pas avant qu'on ait mesuré sa fiabilité.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .db import connect

# Deux codes-barres de taille « voisins » : mêmes 12 premiers chiffres à `ECART_EAN`
# unités près (le 13e est la clé de contrôle). Furygan Brooks : 343598037277,
# …278, …279, …281, …283.
ECART_EAN = 20
RAPPORT_PRIX_DOUTEUX = 1.5
RAPPORT_PRIX_VETO = 3.0


@dataclass
class FicheSignaux:
    id: int
    slug: str
    couleur: str                       # colour_code COMPLET (« BK|MAT »), « » si inconnu
    genre: str                         # genre_age (« H-A »)
    annee: int | None
    tailles: dict[str, set[str]] = field(default_factory=dict)   # taille -> EAN
    refs: set[str] = field(default_factory=set)                  # base_sku non vides
    prix: list[float] = field(default_factory=list)


@dataclass
class Verdict:
    note: str                          # sur | probable | douteux | refuser
    raisons: list[str]


def _couleur_connue(c: str) -> bool:
    return bool(c) and c.lower() != "unknown"


def _sexe_age(genre: str) -> tuple[str, str]:
    g = genre or "U-A"
    return g.split("-")[0], g.split("-")[-1]


def _eans_proches(a: str, b: str) -> bool:
    """Même bloc (9 premiers chiffres) et à `ECART_EAN` unités près sur les 12 premiers."""
    if len(a) < 12 or len(b) < 12 or a[:9] != b[:9] or not (a[:12] + b[:12]).isdigit():
        return False
    return abs(int(a[:12]) - int(b[:12])) <= ECART_EAN


def evaluer(fiches: list[FicheSignaux]) -> Verdict:
    """Note un groupe. Pure : aucune base, testable seule."""
    raisons: list[str] = []
    vetos: list[str] = []

    # -- les vetos --------------------------------------------------------
    couleurs = {f.couleur for f in fiches if _couleur_connue(f.couleur)}
    inconnue = any(not _couleur_connue(f.couleur) for f in fiches)
    if len(couleurs) > 1:
        vetos.append("couleurs différentes : " + " / ".join(sorted(couleurs)))

    sexes = {_sexe_age(f.genre)[0] for f in fiches} - {"U"}
    ages = {_sexe_age(f.genre)[1] for f in fiches}
    if len(sexes) > 1:
        vetos.append("genres différents : " + " / ".join(sorted(sexes)))
    if len(ages) > 1:
        vetos.append("âges différents (adulte/enfant)")
    annees = {f.annee for f in fiches if f.annee}
    if len(annees) > 1:
        vetos.append("années différentes : " + " / ".join(str(a) for a in sorted(annees)))

    tailles: dict[str, dict[int, set[str]]] = {}
    for f in fiches:
        for t, eans in f.tailles.items():
            tailles.setdefault(t, {})[f.id] = set(eans)
    en_double = [t for t, par_fiche in tailles.items() if len(par_fiche) > 1]
    conflits = []
    for t in en_double:
        tous = set().union(*tailles[t].values())
        if len(tous) > 1:
            conflits.append(t)
    if conflits:
        vetos.append("même taille, codes-barres différents : " + ", ".join(sorted(conflits)))

    mediane_par_fiche = [statistics.median(f.prix) for f in fiches if f.prix]
    rapport = (max(mediane_par_fiche) / min(mediane_par_fiche)
               if len(mediane_par_fiche) > 1 and min(mediane_par_fiche) > 0 else 1.0)
    if rapport > RAPPORT_PRIX_VETO:
        vetos.append(f"prix médians à {rapport:.1f}×")

    if vetos:
        return Verdict("refuser", vetos)

    # -- les signaux positifs ------------------------------------------------
    eans_par_fiche = [set().union(*f.tailles.values()) if f.tailles else set() for f in fiches]
    # un code-barres vu sur deux fiches au moins
    vus: dict[str, int] = {}
    for eans in eans_par_fiche:
        for e in eans:
            vus[e] = vus.get(e, 0) + 1
    code_partage = any(n > 1 for n in vus.values())
    refs = [f.refs for f in fiches]
    ref_commune = all(refs) and bool(set.intersection(*refs))
    complementaires = not en_double and all(f.tailles for f in fiches)
    proches = False
    if complementaires:
        proches = all(
            any(_eans_proches(a, b) for a in eans_par_fiche[i] for j in range(len(fiches))
                if j != i for b in eans_par_fiche[j])
            for i in range(len(fiches)))

    if code_partage:
        raisons.append("un code-barres partagé par deux fiches")
    if ref_commune:
        raisons.append("même référence fabricant")
    if complementaires:
        raisons.append("tailles qui se complètent")
    if proches:
        raisons.append("codes-barres voisins")
    couleur_ok = len(couleurs) == 1 and not inconnue
    if couleur_ok:
        raisons.append(f"couleur identique ({next(iter(couleurs))})")
    elif inconnue:
        raisons.append("couleur inconnue sur au moins une fiche")
    prix_ok = rapport <= RAPPORT_PRIX_DOUTEUX
    raisons.append(f"prix médians à {rapport:.2f}×" + ("" if prix_ok else " (> 1,5)"))

    if couleur_ok and prix_ok and (code_partage or ref_commune):
        return Verdict("sur", raisons)
    if couleur_ok and prix_ok and complementaires and proches:
        return Verdict("probable", raisons)
    return Verdict("douteux", raisons)


# --- avec la base (lecture seule) ----------------------------------------------

_GROUPES = "SELECT id, cle, produit_ids FROM fusion_proposee WHERE statut = ANY(%s) ORDER BY id"

_FICHES = """
SELECT p.id, p.slug, coalesce(p.colour_code, ''), coalesce(p.genre_age, 'U-A'), p.model_year
FROM product p WHERE p.id = ANY(%s)
"""

_TAILLES = """
SELECT v.product_id, v.size_code, o.gtin
FROM variant v
JOIN offer_variant_link l ON l.variant_id = v.id
JOIN raw_offer o ON o.id = l.raw_offer_id AND o.is_live AND o.gtin ~ '^[0-9]{12,14}$'
WHERE v.product_id = ANY(%s) AND v.size_code <> 'TU'
"""

_REFS_ET_PRIX = """
SELECT o.product_id, coalesce(s.base_sku, ''), o.price
FROM raw_offer o LEFT JOIN offer_signature s ON s.raw_offer_id = o.id
WHERE o.product_id = ANY(%s) AND o.is_live
"""


def noter(statuts: tuple[str, ...] = ("proposee",)) -> list[dict]:
    """Note chaque groupe de `fusion_proposee` dans ces statuts. N'écrit RIEN."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_GROUPES, (list(statuts),))
            groupes = cur.fetchall()
            ids = sorted({p for _, _, pids in groupes for p in pids})
            cur.execute(_FICHES, (ids,))
            fiches = {r[0]: FicheSignaux(r[0], r[1], r[2], r[3], r[4]) for r in cur.fetchall()}
            cur.execute(_TAILLES, (ids,))
            for pid, taille, gtin in cur.fetchall():
                fiches[pid].tailles.setdefault(taille, set()).add(gtin)
            cur.execute(_REFS_ET_PRIX, (ids,))
            for pid, ref, prix in cur.fetchall():
                if ref:
                    fiches[pid].refs.add(ref)
                if prix is not None:
                    fiches[pid].prix.append(float(prix))
        sortie = []
        for fid, cle, pids in groupes:
            fs = [fiches[p] for p in pids if p in fiches]
            v = evaluer(fs) if len(fs) > 1 else Verdict("douteux", ["une seule fiche lisible"])
            sortie.append({"id": fid, "cle": cle, "note": v.note, "raisons": v.raisons,
                           "fiches": [f.slug for f in fs]})
        return sortie
    finally:
        conn.close()
