"""Les indicateurs d'une fiche enrichie : la fiche technique, lue d'un coup d'oeil.

Chaque indicateur est tire d'une ligne SOURCEE de la fiche technique du modele ; une valeur
absente ne produit pas d'indicateur (sauf les quatre essentiels, affiches « non renseigne »,
parce que ne pas savoir le poids d'un casque est une information). Rien n'est devine.

Types : `etoiles` (note SHARP), `jauge` (poids sur une echelle), `badge` (norme), `oui` /
`non` (presence d'un equipement), `texte` (une valeur courte), `inconnu`.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

# Echelle de la jauge de poids : un integral pese entre 1,1 et 1,9 kg. Ce n'est pas une note
# de qualite : un casque leger n'est pas « meilleur », il est plus leger.
POIDS_MIN, POIDS_MAX = 1100, 1900


def _ligne(tech: list[dict[str, Any]], *motifs: str) -> dict[str, Any] | None:
    for m in motifs:
        for t in tech:
            if re.search(m, t.get("nom", ""), re.I):
                return t
    return None


def _nombre(texte: str) -> int | None:
    m = re.search(r"(\d[\d   ]{2,6})\s*g\b", texte or "")
    return int(re.sub(r"\D", "", m.group(1))) if m else None


def _court(texte: str, n: int = 46) -> str:
    t = re.split(r"[;(]|, | : ", texte or "")[0].strip()
    if len(t) <= n:
        return t
    coupe = t[: n - 1]
    return (coupe.rsplit(" ", 1)[0] if " " in coupe else coupe).rstrip(" ,;") + "…"


def indicateurs(contenu: dict[str, Any]) -> list[dict[str, Any]]:
    tech = contenu.get("fiche_technique") or []
    sec = contenu.get("securite") or None
    out: list[dict[str, Any]] = []

    # 1. Note SHARP
    if sec and sec.get("sharp_etoiles"):
        out.append({"cle": "sharp", "titre": "Test de choc SHARP", "type": "etoiles",
                    "etoiles": int(sec["sharp_etoiles"]), "valeur": f"{sec['sharp_etoiles']} / 5",
                    "detail": f"Ministère des transports britannique · {sec.get('date_test', '')}".strip(" ·")})
    # 2. Poids
    l = _ligne(tech, r"^poids")
    g = _nombre(l["valeur"]) if l else None
    if g:
        pese = bool(re.search(r"pes[ée]e|SHARP", l["valeur"], re.I)) and "annonc" not in l["nom"].lower()
        pct = max(0, min(100, round((g - POIDS_MIN) / (POIDS_MAX - POIDS_MIN) * 100)))
        out.append({"cle": "poids", "titre": "Poids", "type": "jauge", "pct": pct,
                    "valeur": f"{g:,}".replace(",", " ") + " g",
                    "detail": ("Pesé en test" if pese else "Annoncé par le constructeur")
                              + (" · avec peak" if "peak" in l["valeur"].lower() else ""),
                    "bornes": ("1,1 kg", "1,9 kg")})

    # 3. Norme
    n = _ligne(tech, r"^norme|homolog")
    v = (n or {}).get("valeur", "") or (sec or {}).get("norme", "")
    m = re.search(r"22[.\-]?0?([56])", v or "")
    if m:
        recente = m.group(1) == "6"
        out.append({"cle": "norme", "titre": "Homologation", "type": "badge",
                    "valeur": f"ECE 22.0{m.group(1)}", "ok": recente,
                    "detail": "Norme en vigueur" if recente else "Ancienne norme"})

    # 4. Coque : le sigle du constructeur (PB-SNC², PB-cLc2) ne dit rien au visiteur. On met le
    # MATERIAU en gros et le nom de la technologie en petit. SNC² est la coque haut de gamme
    # d'Arai ; cLc est son composite de fibres (presse : Rider, 2019 ; Arai annonce la meme
    # protection, la difference porte sur les materiaux, donc le poids).
    l = _ligne(tech, r"^coque")
    if l:
        v = l["valeur"]
        m = re.search(r"PB[ -]?(?:e-)?(?:SNC[²2]?|cLc2?)", v, re.I)
        sigle = re.sub(r"^PB[ -]?(?=e-)", "PB ", m.group(0)) if m else ""
        sigle = re.sub(r"^PB[ ](?!e-)", "PB-", sigle)
        if re.search(r"SNC", v, re.I):
            out.append({"cle": "coque", "titre": "Coque", "type": "texte", "valeur": "Super fibre",
                        "detail": f"Technologie Arai {sigle} · haut de gamme" if sigle else "Haut de gamme Arai"})
        elif re.search(r"cLc", v, re.I):
            out.append({"cle": "coque", "titre": "Coque", "type": "texte", "valeur": "Composite de fibres",
                        "detail": f"Technologie Arai {sigle}" if sigle else ""})
        else:
            out.append({"cle": "coque", "titre": "Coque", "type": "texte", "valeur": _court(v), "detail": ""})

    # Identite de la marque : lieu, assemblage, anciennete. Une case par fait SOURCE.
    mi = contenu.get("marque_info") or {}
    if mi.get("pays"):
        out.append({"cle": "fabrication", "titre": "Fabriqué au", "type": "texte", "valeur": mi["pays"],
                    "detail": mi.get("lieu", "")})
    if mi.get("assemblage"):
        out.append({"cle": "assemblage", "titre": "Assemblage", "type": "oui", "valeur": mi["assemblage"],
                    "detail": ""})
    if mi.get("fondation"):
        age = date.today().year - int(mi["fondation"])
        out.append({"cle": "fondation", "titre": "Marque fondée en", "type": "texte",
                    "valeur": str(mi["fondation"]),
                    "detail": (f"Il y a {age} ans" + (" · entreprise familiale" if mi.get("familiale") else ""))})

    # Equipements : presents seulement s'ils sont sources
    l = _ligne(tech, r"^pinlock")
    if l and not re.search(r"non|aucun|pas de", l["valeur"], re.I):
        out.append({"cle": "pinlock", "titre": "Pinlock anti-buée", "type": "oui",
                    "valeur": "Fourni" if re.search(r"fourni", l["valeur"], re.I) else "Préparé", "detail": ""})
    l = _ligne(tech, r"^pare-?soleil")
    if l and not re.match(r"\s*(non|aucun)", l["valeur"], re.I):
        out.append({"cle": "pare_soleil", "titre": "Pare-soleil intégré", "type": "oui",
                    "valeur": "Oui", "detail": ""})
    l = _ligne(tech, r"^doublure|int[ée]rieur")
    if l and re.search(r"amovible|lavable", l["valeur"], re.I):
        out.append({"cle": "doublure", "titre": "Doublure amovible", "type": "oui",
                    "valeur": "Oui, lavable" if re.search(r"lavable", l["valeur"], re.I) else "Oui", "detail": ""})
    l = _ligne(tech, r"^audio|intercom")
    if l:
        out.append({"cle": "audio", "titre": "Prêt pour interphone", "type": "oui",
                    "valeur": "Logements prévus", "detail": ""})
    l = _ligne(tech, r"^ventilation")
    if l:
        out.append({"cle": "ventilation", "titre": "Ventilation", "type": "texte",
                    "valeur": _court(l["valeur"], 40), "detail": ""})
    l = _ligne(tech, r"^fermeture")
    if l:
        out.append({"cle": "fermeture", "titre": "Fermeture", "type": "texte",
                    "valeur": "Double anneau en D" if re.search(r"double", l["valeur"], re.I)
                    else _court(l["valeur"], 30), "detail": ""})
    l = _ligne(tech, r"^tailles")
    if l:
        m = re.search(r"\b(XXS|XS|S|M|L|XL|XXL|3XL|4XL)\b\s*(?:à|-|–)\s*\b(XS|S|M|L|XL|XXL|3XL|4XL)\b", l["valeur"])
        out.append({"cle": "tailles", "titre": "Tailles", "type": "texte",
                    "valeur": f"{m.group(1)} → {m.group(2)}" if m else _court(l["valeur"], 24),
                    "detail": ""})
    l = _ligne(tech, r"^garantie")
    if l:
        out.append({"cle": "garantie", "titre": "Garantie constructeur", "type": "texte",
                    "valeur": _court(l["valeur"], 20), "detail": ""})
    return out


def profil(contenu: dict[str, Any]) -> dict[str, Any] | None:
    """Le curseur « pour quel pilote ? » : urbain (0), enduro / trail (50), sportif (100).

    Un classement editorial de MotoComparo d'apres les usages decrits par le constructeur et la
    presse. Sans position, pas de curseur : on n'en invente pas un.
    """
    pc = contenu.get("profil_curseur") or {}
    pos = pc.get("position")
    if pos is None:
        return None
    pos = max(0, min(100, int(pos)))
    libelle = ("Urbain" if pos < 20 else "Urbain et routier" if pos < 40 else "Enduro / trail" if pos < 60
               else "Routier sportif" if pos < 85 else "Sportif")
    usages = (contenu.get("profil_type") or {}).get("usages") or []
    return {"position": pos, "libelle": libelle, "usages": usages[:3]}


CRANS_COQUE = ("Thermoplastique", "Fibre de verre", "Composite", "Carbone")

_PHRASES_COQUE = {
    1: "Un plastique moulé (polycarbonate, ABS) : la coque la plus abordable, mais un peu plus lourde.",
    2: "Des couches de fibre de verre : une coque rigide et durable, courante en milieu de gamme.",
    3: "Un mélange de fibres (verre, aramide, carbone) : plus légère et plus résistante que la fibre de verre seule.",
    4: "La plus légère et la plus rigide des coques, mais aussi la plus chère.",
}


_FAMILLES_COQUE = (r"(?<!poly)carbon", r"composite|hybrid|hybride", r"verre|fibreglass|fiberglass|\bfibre\b",
                   r"thermoplast|polycarbon|\babs\b|plastique")


def _cran_coque(texte: str) -> int | None:
    v = (texte or "").lower()
    # « Fibre de verre (HPFC), versions carbone » et « Thermoplastique avec elements en carbone 6K » :
    # la matiere de la coque est la premiere ; les versions et elements en carbone sont des options.
    # (23/10/2026 : ces fiches LS2 sortaient au cran carbone, et dans le filtre « carbone ».)
    v = re.sub(r"\b(?:versions?|[ée]l[ée]ments?|inserts?)\b[^,;()]*", "", v)
    # « Carbone ou fibre de verre » : deux matieres selon la version, donc aucune de sure
    if re.search(r"\bou\b", v) and sum(bool(re.search(f, v)) for f in _FAMILLES_COQUE) >= 2:
        return None
    # « polycarbonate » CONTIENT « carbon » : sans le garde, un casque en plastique passait au cran carbone
    carbone = re.search(r"(?<!poly)carbon", v)
    if carbone and not re.search(r"composite|hybrid|hybride", v):
        return 4
    if re.search(r"composite|hybrid|hybride|snc|clc|super fibre|multi|aramid|kevlar", v) or carbone:
        return 3
    if re.search(r"verre|fibreglass|fiberglass|\bfibre\b", v):
        return 2
    if re.search(r"thermoplast|polycarbon|\babs\b|plastique", v):
        return 1
    return None


_COQUE_MIXTE = re.compile(r"versions?\s+carbon|carbone\s+sur\s+les\s+versions|carbone\s+ou\s|\bou\s+(?:fibre|carbone)", re.I)
_MOT_COQUE = re.compile(r"coque|hpfc|fibre|composite|carbon", re.I)


def coque_mixte(contenu: dict[str, Any] | None) -> bool:
    """Le texte du MODELE annonce deux matieres de coque (« fibre de verre, versions carbone »)."""
    for l in (contenu or {}).get("fiche_technique") or []:
        if re.match(r"\s*coque", l.get("nom", ""), re.I) and _COQUE_MIXTE.search(l.get("valeur", "")):
            return True
    return False


def contenu_selon_titre(contenu: dict[str, Any] | None, titre: str | None) -> dict[str, Any] | None:
    """Un modele vendu en deux matieres (LS2 OF603 : fibre de verre, et une version « Carbon ») : le texte est ecrit pour
    TOUS les coloris, il ne peut pas dire la matiere de la version « Carbon ». Sur une fiche dont le titre porte
    « carbon », on retire donc ce que le texte affirme de la coque : la ligne technique, les points forts courts et les
    phrases qui la decrivent. Les sources des revendeurs se contredisent sur cette version (fibre de carbone pour l'un,
    melange de fibre de verre pour l'autre) : mieux vaut ne rien dire que dire faux (24/10/2026).
    """
    if not contenu or not coque_mixte(contenu) or not re.search(r"carbon", titre or "", re.I):
        return contenu
    sortie = dict(contenu)
    sortie["coque_incertaine"] = True       # `aligner_caracteristiques` retire alors la matiere declaree par les marchands
    sortie["fiche_technique"] = [l for l in contenu.get("fiche_technique") or []
                                 if not re.match(r"\s*coque", l.get("nom", ""), re.I)]
    sortie["points_forts_courts"] = [c for c in contenu.get("points_forts_courts") or [] if not _MOT_COQUE.search(c)]
    for champ in ("accroche", "description"):
        phrases = re.split(r"(?<=[.!?])\s+", contenu.get(champ) or "")
        sortie[champ] = " ".join(p for p in phrases if not _MOT_COQUE.search(p))
    return sortie


def coque_curseur(caracteristiques: list[dict[str, Any]] | None, contenu: dict[str, Any] | None = None
                  ) -> dict[str, Any] | None:
    """Le curseur « matiere de la coque » : thermoplastique, fibre de verre, composite, carbone.

    La matiere dit surtout le POIDS et le PRIX, pas le niveau de securite (tous les casques
    homologues passent les memes essais) : l'echelle va de « entree de gamme » a « premium ».
    Source, par ordre : la fiche technique verifiee du modele, puis la caracteristique `calotte`
    (deja classee par fiabilite de source). Pas de matiere connue, pas de curseur.
    """
    cran, techno = None, ""
    if contenu:
        for l in contenu.get("fiche_technique") or []:
            if re.match(r"\s*coque", l.get("nom", ""), re.I):
                cran = _cran_coque(l.get("valeur", ""))
                m = re.search(r"technologie Arai ([^),]+)", l.get("valeur", ""))
                techno = m.group(1).strip() if m else ""
                break
    if cran is None:
        for c in caracteristiques or []:
            if c.get("nom") == "calotte":
                cran = _cran_coque(str(c.get("valeur", "")))
                break
    if cran is None:
        return None
    return {"cran": cran, "crans": list(CRANS_COQUE), "libelle": CRANS_COQUE[cran - 1],
            "phrase": _PHRASES_COQUE[cran], "technologie": techno}


# Position du curseur « pour quel pilote ? » quand aucun texte n'a ete ecrit pour le modele : le TYPE
# de casque, rien d'autre. C'est un repere grossier, et la page le dit.
_PROFIL_PAR_TYPE = {"helmet.jet": 12, "helmet.modular": 30, "helmet.integral": 68, "helmet.cross": 50, "helmet": 55}


def analyse_auto(caracteristiques: list[dict[str, Any]] | None, categorie_code: str | None) -> dict[str, Any] | None:
    """L'analyse d'un casque SANS texte ecrit : indicateurs et points forts tires des seules
    caracteristiques relevees (SHARP, revendeur, marchands). Aucun texte n'est invente : une case
    n'existe que si la valeur est connue, et il faut au moins trois cases pour qu'il y ait une
    analyse. `caracteristiques()` rend les booleens en « Oui » : les deux ecritures sont lues.
    """
    c = {str(x.get("nom")): str(x.get("valeur")) for x in caracteristiques or []}
    source = {str(x.get("nom")): str(x.get("source")) for x in caracteristiques or []}
    oui = lambda cle: c.get(cle) in ("True", "Oui")
    tech: list[dict[str, str]] = []
    forts: list[str] = []

    etoiles = int(c["note_securite"]) if c.get("note_securite", "").isdigit() else None
    homolog = re.search(r"22[.\-]?0?([56])", c.get("homologation", ""))
    poids = int(c["poids_g"]) if c.get("poids_g", "").isdigit() else None
    if poids and 700 <= poids <= 2200:
        if source.get("poids_g") == "sharp":
            tech.append({"nom": "Poids", "valeur": f"{poids} g (pesée SHARP)"})
        else:
            tech.append({"nom": "Poids annoncé", "valeur": f"{poids} g"})
    if homolog:
        tech.append({"nom": "Norme", "valeur": f"ECE 22.0{homolog.group(1)}"})
    if c.get("pinlock") in ("fourni", "prepare"):
        tech.append({"nom": "Pinlock", "valeur": "Pinlock fourni" if c["pinlock"] == "fourni" else "Pinlock préparé"})
    if oui("ecran_solaire"):
        tech.append({"nom": "Pare-soleil", "valeur": "Intégré"})
    if oui("interieur_amovible"):
        tech.append({"nom": "Doublure", "valeur": "Amovible"})
    if c.get("intercom") == "prepare":
        tech.append({"nom": "Audio", "valeur": "Logements prévus"})
    if c.get("boucle") in ("double-D", "micrométrique"):
        tech.append({"nom": "Fermeture", "valeur": "Double anneau en D" if c["boucle"] == "double-D" else "Micrométrique"})

    # points forts courts, dans l'ordre de ce qui donne le plus envie ; seulement des faits releves
    if etoiles and etoiles >= 4:
        forts.append(f"{etoiles} étoiles au test de choc SHARP")
    if oui("ecran_solaire"):
        forts.append("Écran solaire intégré")
    if c.get("pinlock") == "fourni":
        forts.append("Pinlock anti-buée fourni")
    elif c.get("pinlock") == "prepare":
        forts.append("Prêt pour le Pinlock anti-buée")
    if c.get("calotte") == "carbone":
        forts.append("Coque en fibre de carbone")
    elif c.get("calotte") == "composite":
        forts.append("Coque composite, plus légère")
    if c.get("intercom") == "prepare":
        forts.append("Prêt pour un interphone")
    if oui("interieur_amovible"):
        forts.append("Intérieur amovible")
    if poids and 700 <= poids <= 1350:
        forts.append(f"Léger : {poids} g" + (" à la pesée" if source.get("poids_g") == "sharp" else " annoncés"))
    if homolog and homolog.group(1) == "6":
        forts.append("Homologué ECE 22.06, la norme actuelle")
    if c.get("boucle") == "micrométrique":
        forts.append("Fermeture micrométrique")

    contenu: dict[str, Any] = {"fiche_technique": tech}
    if etoiles:
        contenu["securite"] = {"sharp_etoiles": etoiles, "date_test": ""}
    indic = indicateurs(contenu)
    indic = [i for i in indic if i["type"] != "inconnu"]
    if len(indic) < 3:
        return None
    pos = _PROFIL_PAR_TYPE.get(categorie_code or "")
    prof = profil({"profil_curseur": {"position": pos}}) if pos is not None else None
    if prof:
        prof["auto"] = True
    return {"auto": True, "indicateurs": indic, "profil": prof,
            "points_forts_courts": forts[:4] if len(forts) >= 3 else None}


_CODE_COQUE = {1: "thermoplastique", 2: "fibre", 3: "composite", 4: "carbone"}


def aligner_caracteristiques(caracteristiques: list[dict[str, Any]], contenu: dict[str, Any] | None
                             ) -> list[dict[str, Any]]:
    """Le tableau « Caracteristiques » dit la MEME chose que les indicateurs de la fiche.

    Sans cela, une page affichait « Composite » sur le curseur de coque et « Carbone » dans le
    tableau (700 fiches sur 2 220, constate le 23/10/2026), ou 1 500 g dans la case du poids et
    1 600 g plus bas. Quand un texte verifie existe pour le modele, ses valeurs REMPLACENT celles
    des flux pour les memes caracteristiques : une page, une seule voix.
    """
    if not contenu:
        return caracteristiques
    if contenu.get("coque_incertaine"):
        # une version « Carbon » d'un modele a deux matieres : ni le texte du modele ni les marchands ne tranchent
        caracteristiques = [c for c in caracteristiques if c["nom"] != "calotte"]
    ind = {i["cle"]: i for i in indicateurs(contenu)}
    tech = contenu.get("fiche_technique") or []
    neuves: dict[str, tuple[str, str]] = {}     # nom -> (valeur, source)

    cran = None
    for l in tech:
        if re.match(r"\s*coque", l.get("nom", ""), re.I):
            cran = _cran_coque(l.get("valeur", ""))
    if cran:
        neuves["calotte"] = (_CODE_COQUE[cran], "manuel")
    if "poids" in ind and ind["poids"]["type"] == "jauge":
        g = _nombre(ind["poids"]["valeur"] + "")
        if g:
            neuves["poids_g"] = (str(g), "sharp" if ind["poids"]["detail"].startswith("Pesé") else "manuel")
    if "norme" in ind and ind["norme"]["type"] == "badge":
        neuves["homologation"] = (ind["norme"]["valeur"].replace("ECE ", ""), "manuel")
    if "sharp" in ind and ind["sharp"]["type"] == "etoiles":
        neuves["note_securite"] = (str(ind["sharp"]["etoiles"]), "sharp")
    if "fermeture" in ind:
        neuves["boucle"] = ("double-D" if "anneau" in ind["fermeture"]["valeur"].lower() else "micrométrique", "manuel")
    if "pinlock" in ind and ind["pinlock"]["type"] == "oui":
        neuves["pinlock"] = ("fourni" if ind["pinlock"]["valeur"] == "Fourni" else "prepare", "manuel")
    if "pare_soleil" in ind:
        neuves["ecran_solaire"] = ("Oui", "manuel")
    if "doublure" in ind:
        neuves["interieur_amovible"] = ("Oui", "manuel")
    if "audio" in ind:
        neuves["intercom"] = ("prepare", "manuel")

    sortie = [dict(c) for c in caracteristiques]
    deja = {c["nom"] for c in sortie}
    for nom, (valeur, source) in neuves.items():
        for c in sortie:
            if c["nom"] == nom:
                c["valeur"], c["source"] = valeur, source
        if nom not in deja:
            from . import queries as q          # import tardif : queries importe deja analyse
            sortie.append({"nom": nom, "libelle": q._LIBELLES.get(nom) or nom.replace("_", " ").capitalize(), "valeur": valeur,
                           "source": source, "confiance": "lue"})
    return sortie
