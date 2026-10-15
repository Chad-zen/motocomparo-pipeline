"""Le suivi quotidien de l'indexation Google — lecture seule.

Lancé depuis le poste (là où vit la clé SSH du VPS), par la veille du matin :

    .venv/Scripts/python.exe ops/veille_indexation.py
    .venv/Scripts/python.exe ops/veille_indexation.py --console indexees=33200 non_indexees=46200 ...

Il lit sur le VPS le journal nginx de la VEILLE (`motocomparo.access.log.1`,
une journée complète) et en tire ce que Googlebot a demandé et reçu : pages
lues, anciennes adresses v1 encore en 404 (doivent tomber à ~0 depuis les
redirections du 15/10/2026), redirections v1 suivies, erreurs serveur, lectures
du plan du site. `--console` y ajoute les chiffres relevés dans Search Console
(rapport « Pages »), que ce script ne peut pas lire lui-même.

Écrit `ops/veille/indexation.json` (une ligne par jour, 90 jours, celle du jour
remplacée si on relance) et imprime en dernière ligne un JSON
{jour, releve, ecarts, alertes}. Ne modifie rien sur le serveur.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DOSSIER = Path(__file__).resolve().parent / "veille"
FICHIER = DOSSIER / "indexation.json"
CLE = Path.home() / ".ssh" / "motocomparo_vps"
HOTE = os.environ.get("VPS_HOTE", "")
JOURS_GARDES = 90

# Une ligne « clé=valeur » par mesure, calculée sur le serveur.
COMMANDE = r"""
F=/var/log/nginx/motocomparo.access.log.1
G=$(grep -i 'googlebot' "$F")
v1='"(GET|HEAD) /(product|shop|product-category)/'
echo "debut=$(head -1 "$F" | cut -d' ' -f4 | tr -d '[')"
echo "fin=$(tail -1 "$F" | cut -d' ' -f4 | tr -d '[')"
echo "googlebot=$(printf '%s\n' "$G" | grep -c .)"
echo "googlebot_200=$(printf '%s\n' "$G" | awk '$9==200' | grep -c .)"
echo "googlebot_404=$(printf '%s\n' "$G" | awk '$9==404' | grep -c .)"
echo "googlebot_5xx=$(printf '%s\n' "$G" | awk '$9>=500' | grep -c .)"
echo "v1_404=$(printf '%s\n' "$G" | awk '$9==404' | grep -cE "$v1")"
echo "v1_301=$(printf '%s\n' "$G" | awk '$9==301' | grep -cE "$v1")"
echo "sitemap=$(printf '%s\n' "$G" | grep -cE '"GET /sitemap')"
"""

CONSOLE = ("indexees", "non_indexees", "introuvables", "erreurs_5xx_console",
           "detectees_non_indexees", "explorees_non_indexees")


def _releve() -> dict:
    sortie = subprocess.run(
        ["ssh", "-i", str(CLE), "-o", "BatchMode=yes", "-o", "ConnectTimeout=20",
         HOTE, COMMANDE],
        capture_output=True, timeout=300, check=False)
    if sortie.returncode != 0:
        raise SystemExit("relevé impossible : "
                         + sortie.stderr.decode("utf-8", "replace").strip()[-500:])
    mesures: dict = {}
    for ligne in sortie.stdout.decode("utf-8", "replace").splitlines():
        if "=" in ligne:
            cle, valeur = ligne.split("=", 1)
            mesures[cle] = int(valeur) if valeur.isdigit() else valeur
    return mesures


def _console(args: list[str]) -> dict:
    if "--console" not in args:
        return {}
    valeurs = {}
    for paire in args[args.index("--console") + 1:]:
        cle, _, valeur = paire.partition("=")
        if cle in CONSOLE and valeur.replace(" ", "").isdigit():
            valeurs[cle] = int(valeur.replace(" ", ""))
    return valeurs


def _alertes(r: dict) -> list[dict]:
    """Des seuils fixes, pour que l'agent n'ait rien à interpréter."""
    out = []
    if r.get("googlebot_5xx", 0) > 20:
        out.append({"niveau": "attention",
                    "message": f"Googlebot a reçu {r['googlebot_5xx']} erreurs serveur (5xx) en 24 h"})
    if r.get("v1_404", 0) > 50:
        out.append({"niveau": "attention",
                    "message": f"{r['v1_404']} anciennes adresses v1 encore en 404 pour Googlebot "
                               "— les redirections ne couvrent pas tout"})
    if r.get("googlebot", 0) < 100:
        out.append({"niveau": "attention",
                    "message": f"Googlebot n'a demandé que {r.get('googlebot', 0)} pages en 24 h"})
    return out


def main() -> None:
    if not HOTE:
        raise SystemExit("VPS_HOTE n'est pas renseigné dans .env — voir .env.example")
    releve = {"jour": date.today().isoformat(), **_releve(), **_console(sys.argv[1:])}

    DOSSIER.mkdir(exist_ok=True)
    historique = json.loads(FICHIER.read_text(encoding="utf-8")) if FICHIER.exists() else []
    historique = [h for h in historique if h.get("jour") != releve["jour"]]
    precedent = historique[-1] if historique else {}
    historique = (historique + [releve])[-JOURS_GARDES:]
    FICHIER.write_text(json.dumps(historique, ensure_ascii=False, indent=1), encoding="utf-8")

    ecarts = {cle: releve[cle] - precedent[cle] for cle in releve
              if isinstance(releve[cle], int) and isinstance(precedent.get(cle), int)}
    print(json.dumps({"jour": releve["jour"], "releve": releve, "depuis": precedent.get("jour"),
                      "ecarts": ecarts, "alertes": _alertes(releve)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
