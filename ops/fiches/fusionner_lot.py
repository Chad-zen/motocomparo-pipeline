"""Ajoute un lot de textes (scratch/nouveaux/<marque>/) aux fiches versionnees (contenu/fiches_enrichies/<marque>/).

usage : python ops/fiches/fusionner_lot.py scratch/nouveaux

Un modele deja present (meme nom) est REMPLACE par la version du lot ; les autres sont ajoutes. `marque_info.json` du
lot n'ecrase celui de la marque que s'il n'existe pas encore. Ne charge rien en base : voir docs/fiches/passe-hebdomadaire.md.
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent.parent
CONTENU = RACINE / "contenu" / "fiches_enrichies"


def main(dossier: str) -> None:
    ajoutes = remplaces = 0
    for f in sorted(glob.glob(str(Path(dossier) / "*/fiches_enrichies.json"))):
        marque = Path(f).parent.name
        lot = json.loads(Path(f).read_text(encoding="utf8"))
        cible = CONTENU / marque
        cible.mkdir(parents=True, exist_ok=True)
        fichier = cible / "fiches_enrichies.json"
        actuel = json.loads(fichier.read_text(encoding="utf8")) if fichier.is_file() else []
        par_nom = {m["modele"]: m for m in actuel}
        for m in lot:
            if m["modele"] in par_nom:
                remplaces += 1
            else:
                ajoutes += 1
            par_nom[m["modele"]] = m
        fichier.write_text(json.dumps(list(par_nom.values()), ensure_ascii=False, indent=1), encoding="utf8")
        info = Path(f).with_name("marque_info.json")
        if info.is_file() and not (cible / "marque_info.json").is_file():
            (cible / "marque_info.json").write_text(info.read_text(encoding="utf8"), encoding="utf8")
    print(f"{ajoutes} modeles ajoutes, {remplaces} remplaces")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "scratch/nouveaux")
