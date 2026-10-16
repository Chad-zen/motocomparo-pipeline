"""Importer des caractéristiques lues sur des pages marchands par un agent, après
vérification par un second agent.

Deux agents, deux rôles : l'un EXTRAIT (valeur + passage + adresse), l'autre
REVÉRIFIE à partir de la page elle-même. Rien n'entre en base sans les deux, et
un dernier contrôle, ici, refuse ce qui sort de la liste fermée du rayon ou dont
le passage ne contient aucun mot de la valeur. La valeur est écrite sous la
source `web` (derrière les saisies à la main, devant les lectures de
descriptions) et sa preuve est gardée dans `caracteristique_preuve`.
"""

from __future__ import annotations

import json
import re
import unicodedata

# Au moins un de ces mots doit figurer dans le passage cité pour la valeur.
MOTS_SAISON: dict[str, tuple[str, ...]] = {
    "ete": ("ete", "summer", "estival", "chaleur"),
    "mi-saison": ("mi-saison", "mi saison", "printemps", "automne", "demi-saison"),
    "hiver": ("hiver", "winter", "froid"),
    "toutes-saisons": ("toutes saisons", "toutes-saisons", "4 saisons", "quatre saisons",
                       "all season", "all-season", "4 seasons"),
}


def _sans_accent(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower())
                   if unicodedata.category(c) != "Mn")


def passage_soutient(champ: str, valeur: str, citation: str) -> bool:
    """Le passage cité contient-il un mot de la valeur ? (garde-fou, pas preuve)"""
    c = _sans_accent(citation)
    if not c.strip():
        return False
    if champ == "saison":
        return any(m in c for m in MOTS_SAISON.get(valeur, ()))
    if champ == "homologation":
        cles = {"AAA": "17092", "AA": "17092", "A": "17092", "B": "17092", "C": "17092",
                "EN 13594": "13594", "EN 13634": "13634", "CE": "ce",
                "22.06": "22", "22.05": "22"}
        cle = cles.get(valeur, _sans_accent(valeur))
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(cle), c))
    return _sans_accent(valeur).split()[0] in c          # matière : le mot lui-même


def preparer(extraction: list[dict], verification: list[dict],
             exclure: set[int] | None = None) -> tuple[list[dict], list[tuple]]:
    """Les valeurs à écrire, et celles refusées avec la raison."""
    exclure = exclure or set()
    confirmees = {(v["product_id"], v["champ"]): v for v in verification if v.get("confirme")}
    retenues, refusees = [], []
    for fiche in extraction:
        for champ, trouve in (fiche.get("trouve") or {}).items():
            if not trouve:
                continue
            pid, valeur = fiche["product_id"], trouve["valeur"]
            v = confirmees.get((pid, champ))
            if pid in exclure:
                refusees.append((pid, champ, "exclue à la main"))
            elif not v or v.get("valeur") != valeur:
                refusees.append((pid, champ, "non confirmée par le second agent"))
            elif not passage_soutient(champ, valeur, v.get("citation_exacte", "")):
                refusees.append((pid, champ, "le passage vérifié ne contient pas la valeur"))
            else:
                retenues.append({"product_id": pid, "champ": champ, "valeur": valeur,
                                 "url": trouve["url"], "citation": v["citation_exacte"][:400]})
    return retenues, refusees


def importer(chemin_extraction: str, chemin_verification: str,
             exclure: set[int] | None = None) -> dict[str, int]:
    from mcsite import admin

    from .db import connect

    extraction = json.load(open(chemin_extraction, encoding="utf-8"))
    verification = json.load(open(chemin_verification, encoding="utf-8"))
    retenues, refusees = preparer(extraction, verification, exclure)
    conn = connect()
    ecrites = 0
    try:
        for r in retenues:
            n = admin.enregistrer_caracteristiques(
                conn, r["product_id"], {r["champ"]: r["valeur"]}, source="web")
            if n:
                conn.execute(
                    "INSERT INTO caracteristique_preuve (product_id, nom, valeur, url, citation, verifie) "
                    "VALUES (%s, %s, %s, %s, %s, true) ON CONFLICT (product_id, nom) DO UPDATE "
                    "SET valeur = excluded.valeur, url = excluded.url, citation = excluded.citation, "
                    "verifie = true, cree_le = now()",
                    (r["product_id"], r["champ"], r["valeur"], r["url"], r["citation"]))
                ecrites += 1
        conn.commit()
    finally:
        conn.close()
    return {"retenues": len(retenues), "ecrites": ecrites, "refusees": len(refusees)}
