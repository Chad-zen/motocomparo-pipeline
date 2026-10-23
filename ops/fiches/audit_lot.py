"""Controle d'un lot de textes de fiches AVANT de le charger.

usage : python ops/fiches/audit_lot.py scratch/nouveaux          (un dossier <marque>/fiches_enrichies.json par marque)

Cherche, dans tout ce qui s'affiche : un nom de marchand ou de concurrent, une phrase d'absence (« non testé »),
un prix, un superlatif, un motif de fiche mal ecrit (`\\\\y`), des points forts courts hors format, une accroche
trop longue, une matiere de coque contredite par une phrase du texte. Les motifs d'anonymat propres a la
proprietaire sont lus dans `.anonymat` (non versionne), jamais ecrits ici.
Sortie : le nombre de modeles controles et la liste des alertes. Code de sortie 1 s'il y en a.
"""

from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RACINE / "src"))
sys.stdout.reconfigure(encoding="utf8")
from mcsite import analyse  # noqa: E402

MARCHANDS = ["dafy", "motoblouz", r"fc-?moto", "speedway", r"b[ée]canerie", "maxxess", r"moto-?axxe", "motoin",
             r"motard ?bleu", "revendeur"]
if (RACINE / ".anonymat").exists():
    MARCHANDS += [l.strip() for l in (RACINE / ".anonymat").read_text(encoding="utf-8").splitlines()
                  if l.strip() and not l.startswith("#")]
MARCHANDS_SOURCES = re.compile("|".join(m for m in MARCHANDS if m != "revendeur"), re.I)   # « revendeur » est le mot neutre des sources
MARCHANDS = re.compile("|".join(MARCHANDS), re.I)
ABSENCE = re.compile(r"non test|aucun|pas pu|non pr[ée]cis|non trouv|n'a pas|pas de |introuvable|nous nous en tenons|"
                     r"non renseign|non confirm|inconnu|incertain", re.I)
PRIX = re.compile(r"€|euros?\b|\d\s?eur\b|(?<!grand )\bprix\b", re.I)
SUPER = re.compile(r"meilleur casque|le plus s[ûu]r|n°\s?1|num[ée]ro 1|le meilleur", re.I)
NOMS = {1: "thermoplastique", 2: "fibre de verre", 3: "composite", 4: "carbone"}
PAT = {4: r"carbone|carbon", 3: r"composite", 2: r"fibre de verre|fibreglass", 1: r"thermoplast|polycarbonate"}


def main(dossier: str) -> int:
    alertes: list[tuple[str, str, str, str]] = []
    nb = 0
    for f in sorted(glob.glob(str(Path(dossier) / "*/fiches_enrichies.json"))):
        marque = Path(f).parent.name
        info = Path(f).with_name("marque_info.json")
        if info.is_file() and MARCHANDS_SOURCES.search(info.read_text(encoding="utf8")):
            alertes.append((marque, "-", "MARCHAND dans marque_info", ""))
        for m in json.loads(Path(f).read_text(encoding="utf8")):
            nb += 1
            mod = m["modele"]
            pub = {"accroche": m.get("accroche", ""), "description": m.get("description", "")}
            for i, s in enumerate(m.get("points_forts_courts", [])):
                pub[f"court{i}"] = s
            for t in m.get("fiche_technique", []):
                pub[f"tech:{t['nom']}"] = t["valeur"]
            for k, v in pub.items():
                for nom, motif in (("MARCHAND", MARCHANDS), ("ABSENCE", ABSENCE), ("PRIX", PRIX), ("SUPERLATIF", SUPER)):
                    if motif.search(v):
                        alertes.append((marque, mod, f"{nom} {k}", v[:100]))
            for coll in ("points_forts", "fiche_technique"):
                for x in m.get(coll, []):
                    if MARCHANDS_SOURCES.search(x.get("source", "")):
                        alertes.append((marque, mod, f"MARCHAND source {coll}", x.get("source", "")[:80]))
            courts = m.get("points_forts_courts", [])
            if len(courts) != 4 or any(len(c) > 45 for c in courts):
                alertes.append((marque, mod, "COURTS", str([len(c) for c in courts])))
            if len(m.get("accroche", "")) > 150:
                alertes.append((marque, mod, "ACCROCHE longue", str(len(m["accroche"]))))
            if not (0 <= int(m.get("profil_position", -1)) <= 100):
                alertes.append((marque, mod, "PROFIL", str(m.get("profil_position"))))
            if "\\\\" in m.get("motif", ""):
                alertes.append((marque, mod, "MOTIF double barre", m["motif"]))
            coque = [t["valeur"] for t in m.get("fiche_technique", []) if t["nom"].lower().startswith("coque")]
            cran = analyse._cran_coque(coque[0]) if coque else None
            if cran:
                for k, v in pub.items():
                    if k.startswith("tech"):
                        continue
                    for ph in re.split(r"(?<=[.!?])\s+", v):
                        autre = [c for c, p in PAT.items() if c != cran and re.search(p, ph, re.I)]
                        if autre and not re.search(PAT[cran], ph, re.I):
                            alertes.append((marque, mod, f"MATIERE [{NOMS[cran]}] {k}", ph[:100]))
    print(nb, "modeles controles,", len(alertes), "alertes")
    for a in alertes:
        print("  ", a)
    return 1 if alertes else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "scratch/nouveaux"))
