"""Charge les fiches enrichies (texte par modele de casque) dans `fiche_enrichie`.

Le texte est ecrit a part (agent redacteur, faits sources) et arrive en JSON : une liste
d'objets, un par modele. Ce module ne redige rien : il range, et il dit le motif qui relie
un modele a ses fiches (le titre d'une fiche contient le modele).
"""

from __future__ import annotations

import json
from pathlib import Path

from .db import connect

# modele -> motif cherche dans le titre de la fiche (insensible a la casse).
# Arai (22/10/2026) : « Tour » seul (2 fiches) est un Tour-X5 ecrit court.
MOTIFS: dict[tuple[str, str], str] = {
    # Dans PostgreSQL la limite de mot s'ecrit barre-inverse + y ; barre-inverse + b y est un retour
    # arriere, et le motif ne trouvait alors rien (constate le 22/10/2026).
    # RX-7V EVO seulement : l'ancien RX-7V (norme 22.05) n'a pas le meme texte.
    ("arai", "RX-7V EVO"): r"rx-?7v[- ]?evo",
    ("arai", "TOUR-X5"): r"tour[- ]?x ?5",
    ("arai", "QUANTIC"): r"quantic",
    ("arai", "SZ-R"): r"sz-?r\y",
    ("arai", "MX-V"): r"mx-?v\y",
    ("arai", "CONCEPT-X"): r"concept[- ]?x",
    ("arai", "FREEWAY"): r"freeway",
}


# Ce que la MARQUE est, commun a tous ses modeles. Chaque fait est source ; ce qui n'est pas
# confirme n'y figure pas. Arai (22/10/2026) : fondation et usines d'Omiya donnees par la
# chronologie de l'entreprise ; « tous les casques Arai sont encore faits a la main au Japon »
# vient d'un essai de la presse (heise.de, RX-7V EVO), et la page du distributeur britannique
# dit « produit au Japon ». Le site d'assemblage precis par modele n'est PAS confirme.
MARQUES_INFO: dict[str, dict] = {
    "arai": {
        "fondation": 1926,
        "fondateur": "Hirotake Arai",
        "pays": "Japon",
        "lieu": "Omiya (Saitama)",
        "assemblage": "À la main",
        "familiale": True,
        "sources": {
            "fondation": "Arai, chronologie de l'entreprise (whyarai.co.uk) ; amcn.com.au",
            "pays": "Arai UK (whyarai.co.uk, page RX-7V EVO) ; heise.de",
            "lieu": "Arai, chronologie de l'entreprise : usine d'Omiya-ku, Saitama (whyarai.co.uk)",
            "assemblage": "heise.de, essai du RX-7V EVO : casques Arai encore faits à la main au Japon",
            "familiale": "Arai, chronologie : Michio Arai, fils du fondateur, président (whyarai.co.uk)",
        },
    },
}


# Profil du pilote, de 0 (urbain) a 100 (sportif), 50 = enduro / trail. C'est un CLASSEMENT
# EDITORIAL de MotoComparo, tire des usages decrits par le constructeur et la presse (champ
# `profil_type.usages` de chaque fiche) : il n'est pas mesure, et la page le dit.
PROFILS: dict[tuple[str, str], int] = {
    ("arai", "RX-7V EVO"): 95,    # route sportive, roulage rapide, circuit
    ("arai", "QUANTIC"): 75,      # route, trajets longs, maintien plus relache
    ("arai", "TOUR-X5"): 50,      # trail et aventure
    ("arai", "MX-V"): 50,         # motocross, enduro
    ("arai", "CONCEPT-X"): 25,    # roadster, neo-retro, balades
    ("arai", "SZ-R"): 12,         # jet : ville, balades
    ("arai", "FREEWAY"): 6,       # jet classique : ville, custom, cafe racer
}


# Les quatre points forts COURTS affiches en haut de la fiche, a la place des promesses generales
# (« prix releves chaque jour »...). Ce sont des reformulations de `points_forts`, chacune tiree
# d'un fait source de la fiche ; aucun fait n'est ajoute ici.
FORTS_COURTS: dict[tuple[str, str], list[str]] = {
    ("arai", "RX-7V EVO"): ["5 étoiles au test de choc SHARP", "Ventilation jugée excellente en essai",
                            "Coque assemblée à la main au Japon", "Pinlock anti-buée fourni"],
    ("arai", "TOUR-X5"): ["4 étoiles au test de choc SHARP", "Peak démontable : rue, trail ou lunettes",
                          "Ventilation jugée excellente en essai", "Pinlock 120 XLT fourni"],
    ("arai", "QUANTIC"): ["4 étoiles au test de choc SHARP", "Maintien plus relâché, pensé pour la route",
                          "Ajustement salué, même sur têtes larges", "Pinlock fourni, visière anti-rayures"],
    ("arai", "SZ-R"): ["Norme ECE 22.06 (version EVO)", "Visière VAS-Z à double pivot",
                       "Conçu pour lunettes et haut-parleurs", "Pinlock fourni, visière teintée en option"],
    ("arai", "MX-V"): ["Ajustement noté 5/5 après 2 ans d'usage", "Ventilation jugée bonne, durabilité saluée",
                       "Norme ECE 22.06", "Doublure Dry-Cool, extracteur démontable"],
    ("arai", "CONCEPT-X"): ["4 étoiles au test de choc SHARP", "Ajustement très confortable, sans point dur",
                            "Plutôt silencieux selon l'essai", "Bonne ventilation pour l'été"],
    ("arai", "FREEWAY"): ["Coque en super fibre, légère", "Intérieur lavable, joues remplaçables",
                          "Fermeture double anneau en D", "Peak amovible sur certaines versions"],
}


def _coque_mixte(fiche: dict) -> bool:
    """La ligne « Coque » annonce deux matieres (« fibre de verre, versions carbone ») : voir `mcsite.analyse`."""
    from mcsite.analyse import coque_mixte

    return coque_mixte(fiche)


def _code_coque(fiche: dict) -> str | None:
    """Le code de filtre (thermoplastique, fibre, composite, carbone) de la ligne « Coque » de la fiche."""
    from mcsite.analyse import _CODE_COQUE, _cran_coque

    for ligne in fiche.get("fiche_technique") or []:
        if ligne.get("nom", "").lower().startswith("coque"):
            cran = _cran_coque(ligne.get("valeur", ""))
            return _CODE_COQUE.get(cran) if cran else None
    return None


def charger(chemin: str, marque: str = "arai", marque_info: str | None = None) -> list[tuple[str, int]]:
    """Charge les fiches enrichies d'un fichier JSON ; rend (modele, nombre de fiches touchees).

    Chaque objet porte `modele` et peut porter `motif` (expression reguliere PostgreSQL cherchee dans
    le titre : `\\y` est la limite de mot), `profil_position` (0 urbain, 50 trail, 100 sportif) et
    `points_forts_courts` (quatre phrases courtes). Ces trois champs, pour Arai, ont aussi une valeur
    de repli dans ce module. L'identite de la marque vient de `marque_info` (un JSON) ou, pour Arai,
    de `MARQUES_INFO`.
    """
    lignes = json.loads(Path(chemin).read_text(encoding="utf-8"))
    info = MARQUES_INFO.get(marque)
    if marque_info:
        info = json.loads(Path(marque_info).read_text(encoding="utf-8"))
    rendu: list[tuple[str, int]] = []
    conn = connect()
    try:
        with conn.cursor() as cur:
            for fiche in lignes:
                modele = fiche["modele"]
                motif = fiche.get("motif") or MOTIFS.get((marque, modele))
                if not motif:
                    continue
                contenu = {k: v for k, v in fiche.items() if k not in {"nb_fiches", "motif", "profil_position"}}
                position = fiche.get("profil_position", PROFILS.get((marque, modele)))
                if position is not None:
                    contenu["profil_curseur"] = {"position": int(position)}
                courts = fiche.get("points_forts_courts") or FORTS_COURTS.get((marque, modele))
                if courts:
                    contenu["points_forts_courts"] = courts
                if info:
                    contenu["marque_info"] = info
                cur.execute(
                    """
                    INSERT INTO fiche_enrichie (brand_code, modele, motif, contenu)
                    VALUES (%s, %s, %s, %s::jsonb)
                    ON CONFLICT (brand_code, modele) DO UPDATE
                    SET motif = EXCLUDED.motif, contenu = EXCLUDED.contenu, redige_le = now()
                    """,
                    (marque, modele, motif, json.dumps(contenu, ensure_ascii=False)),
                )
                cur.execute(
                    """
                    SELECT count(*) FROM product p JOIN product_stats s ON s.product_id = p.id
                    WHERE p.brand_code = %s AND p.category_id IN (1, 2, 3, 4, 5) AND s.best_title ~* %s
                    """,
                    (marque, motif),
                )
                rendu.append((modele, cur.fetchone()[0]))
                # La matiere de coque VERIFIEE du modele devient la valeur `manuel` de ces fiches : le filtre
                # « matiere de coque » lit la base, la fiche lit le texte verifie ; sans cela ils se
                # contredisaient (LS2 FF808 : « carbone » dans le flux, thermoplastique en realite).
                code = _code_coque(fiche)
                mixte = _coque_mixte(fiche)
                if mixte:
                    # un modele a deux matieres : le titre tranche, « carbon » dans le titre = coque carbone (Sofia, 29/10/2026)
                    cur.execute(
                        """
                        INSERT INTO product_caracteristique (product_id, nom, valeur, source, confiance)
                        SELECT p.id, 'calotte', 'carbone', 'manuel', 'lue'
                        FROM product p JOIN product_stats s ON s.product_id = p.id
                        WHERE p.brand_code = %s AND p.category_id IN (1, 2, 3, 4, 5) AND s.best_title ~* %s
                          AND s.best_title ~* 'carbon'
                        ON CONFLICT (product_id, nom, source) DO UPDATE
                        SET valeur = EXCLUDED.valeur, calcule_le = now()
                        """,
                        (marque, motif),
                    )
                if not code:
                    # matiere indeterminee (« carbone ou fibre de verre » selon la version) : aucune valeur
                    # `manuel` ne doit rester d'un passage precedent
                    cur.execute(
                        """
                        DELETE FROM product_caracteristique pc USING product p, product_stats s
                        WHERE pc.product_id = p.id AND s.product_id = p.id AND pc.nom = 'calotte'
                          AND pc.source = 'manuel' AND p.brand_code = %s AND s.best_title ~* %s
                          AND NOT (%s AND s.best_title ~* 'carbon')
                        """,
                        (marque, motif, mixte),
                    )
                if code:
                    cur.execute(
                        """
                        INSERT INTO product_caracteristique (product_id, nom, valeur, source, confiance)
                        SELECT p.id, 'calotte', %s, 'manuel', 'lue'
                        FROM product p JOIN product_stats s ON s.product_id = p.id
                        WHERE p.brand_code = %s AND p.category_id IN (1, 2, 3, 4, 5) AND s.best_title ~* %s
                          AND NOT (%s AND s.best_title ~* 'carbon')
                        ON CONFLICT (product_id, nom, source) DO UPDATE
                        SET valeur = EXCLUDED.valeur, calcule_le = now()
                        """,
                        (code, marque, motif, mixte),
                    )
        conn.commit()
        return rendu
    finally:
        conn.close()


def charger_dossier(dossier: str) -> list[tuple[str, str, int]]:
    """Charge `<dossier>/<marque>/fiches_enrichies.json` (et `marque_info.json` s'il existe) pour
    chaque marque. Rend (marque, modele, nombre de fiches touchees)."""
    rendu: list[tuple[str, str, int]] = []
    for sous in sorted(Path(dossier).iterdir()):
        fichier = sous / "fiches_enrichies.json"
        if not fichier.is_file():
            continue
        info = sous / "marque_info.json"
        for modele, n in charger(str(fichier), sous.name, str(info) if info.is_file() else None):
            rendu.append((sous.name, modele, n))
    return rendu
