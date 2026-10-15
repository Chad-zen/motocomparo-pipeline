"""Prépare les quatre fichiers du tableau de bord « Veille MotoComparo ».

Lancé depuis le poste (là où vit la clé SSH du VPS) :

    .venv/Scripts/python.exe ops/veille_tableau.py

Il exécute `ops/surveillance.py` sur le VPS, puis écrit dans `ops/veille/` :
`indicateurs.json` (une ligne), `alertes.json`, `marchands.json` et
`historique.json` (une ligne par jour, 90 jours, celle du jour remplacée si on
relance). Il ne publie rien : l'agent quotidien envoie ces fichiers au tableau
de bord. Le dossier est ignoré par git : on n'y met que des relevés.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DOSSIER = Path(__file__).resolve().parent / "veille"
CLE = Path.home() / ".ssh" / "motocomparo_vps"
# L'adresse du serveur n'a pas sa place dans un dépôt public — voir
# tests/test_depot_anonyme.py. Elle vient de `.env`, comme les autres secrets
# du projet (SOURCE_REVENDEUR_RACINE, FEED_*_URL...).
HOTE = os.environ.get("VPS_HOTE", "")
COMMANDE = (
    "systemd-run --wait --pipe --quiet "
    "--property=EnvironmentFile=/srv/motocomparo/.env "
    "/srv/motocomparo/venv/bin/python /srv/motocomparo/app/ops/surveillance.py"
)
CODES = {1: "speedway", 2: "labecanerie", 3: "motoblouz",
         4: "maxxess", 5: "motoaxxe", 6: "fcmoto"}
JOURS_GARDES = 90


def _releve() -> dict:
    sortie = subprocess.run(
        ["ssh", "-i", str(CLE), "-o", "BatchMode=yes", "-o", "ConnectTimeout=20",
         HOTE, COMMANDE],
        capture_output=True, timeout=600, check=False)
    if sortie.returncode != 0:
        raise SystemExit("relevé impossible : "
                         + sortie.stderr.decode("utf-8", "replace").strip()[-500:])
    return json.loads(sortie.stdout)


def _ecrire(nom: str, lignes: list[dict]) -> None:
    (DOSSIER / nom).write_text(json.dumps(lignes, ensure_ascii=False, indent=1),
                               encoding="utf-8")


def main() -> None:
    if not HOTE:
        raise SystemExit("VPS_HOTE n'est pas renseigné dans .env — voir .env.example")
    r = _releve()
    DOSSIER.mkdir(exist_ok=True)
    niveaux = [a["niveau"] for a in r["alertes"]]
    pages = r["pages"]

    _ecrire("indicateurs.json", [{
        "jour": r["jour"],
        "genere_le": r["genere_le"],
        "statut": r["statut"],
        "critiques": niveaux.count("critique"),
        "attentions": niveaux.count("attention"),
        "pages_ok": sum(1 for p in pages if p["code"] == 200),
        "pages_testees": len(pages),
        "page_plus_lente_s": max((p["secondes"] or 0) for p in pages) if pages else None,
        "disque_pct": r["disque_pct"],
        "disque_libre_go": r["disque_libre_go"],
        "base_go": r["base_go"],
        "chaine_resultat": r["chaine"]["resultat"],
        "chaine_fin": r["chaine"]["fin"],
        "erreurs_5xx_24h": r["erreurs_5xx_24h"],
        "sauvegarde": r["sauvegarde"],
        "fiches_total": r["fiches"]["total"],
        "fiches_avec_prix": r["fiches"]["avec_prix"],
        "messages_contact_24h": r["messages_contact_24h"],
    }])
    _ecrire("alertes.json", [
        {"niveau": a["niveau"], "sujet": a["sujet"], "message": a["message"]}
        for a in sorted(r["alertes"], key=lambda a: a["niveau"] != "critique")
    ])
    _ecrire("marchands.json", [
        {"marchand": m["nom"], "offres": m["offres"], "age_h": m["age_h"],
         "offres_veille": m["offres_veille"], "variation": m["variation"]}
        for m in r["marchands"]
    ])

    chemin_h = DOSSIER / "historique.json"
    try:
        historique = json.loads(chemin_h.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        historique = []
    jour = {"jour": r["jour"], "statut": r["statut"],
            "critiques": niveaux.count("critique"),
            "attentions": niveaux.count("attention"),
            "disque_pct": r["disque_pct"], "erreurs_5xx": r["erreurs_5xx_24h"]}
    for m in r["marchands"]:
        code = CODES.get(m["id"], str(m["id"]))
        jour[f"offres_{code}"] = m["offres"]
        jour[f"age_h_{code}"] = m["age_h"]
    historique = [h for h in historique if h["jour"] != r["jour"]] + [jour]
    historique = sorted(historique, key=lambda h: h["jour"])[-JOURS_GARDES:]
    _ecrire("historique.json", historique)

    print(json.dumps({"statut": r["statut"], "alertes": r["alertes"]}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
