"""À quelle fréquence les marchands republient-ils vraiment leurs flux ?

La question décide du nombre de relevés de prix par jour. La relancer plus
souvent que le marchand ne publie ne rafraîchit rien et coûte 925 Mo de
téléchargement à chaque fois ; la relancer moins souvent affiche des prix que
le marchand a déjà changés.

On ne peut pas y répondre d'une seule lecture : `Last-Modified` dit la DERNIÈRE
publication, pas la cadence. Ce script relève cette date à intervalle régulier
et note chaque changement. Au bout d'une journée, le fichier donne la réponse.

Requête `HEAD` uniquement : on demande les en-têtes, jamais le fichier. Aucun
lien d'affiliation n'est suivi, aucune bande passante marchande consommée.

    python ops/cadence_flux.py            # échantillonne 24 h, toutes les 15 min
    python ops/cadence_flux.py 6 10       # 6 h, toutes les 10 min
    python ops/cadence_flux.py --resume   # lit le journal et conclut
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime

RACINE = os.path.join(os.path.dirname(__file__), "..")
JOURNAL = os.path.join(RACINE, "ops", "cadence_flux.log")
CODES = ["speedway", "labecanerie", "motoblouz", "maxxess", "motoaxxe", "fcmoto"]

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]


def _entetes(url: str) -> tuple[str | None, str | None]:
    """(Last-Modified, ETag) — ou (None, None) si le serveur n'en donne pas."""
    r = subprocess.run(
        ["curl", "-sSI", "-L", "--max-time", "40", "-A", "Mozilla/5.0", url],
        capture_output=True, text=True, timeout=60)
    lm = re.search(r"(?im)^last-modified:\s*(.+)$", r.stdout)
    et = re.search(r"(?im)^etag:\s*(.+)$", r.stdout)
    return (lm.group(1).strip() if lm else None,
            et.group(1).strip() if et else None)


def echantillonne(heures: float, minutes: int) -> None:
    from dotenv import dotenv_values
    env = dotenv_values(os.path.join(RACINE, ".env"))
    urls = {c: env.get(f"FEED_{c.upper()}_URL") for c in CODES}

    fin = time.time() + heures * 3600
    connu: dict[str, str] = {}
    print(f"relevé toutes les {minutes} min pendant {heures} h -> {JOURNAL}", flush=True)

    while time.time() < fin:
        maintenant = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        with open(JOURNAL, "a", encoding="utf-8") as f:
            for code, url in urls.items():
                if not url:
                    continue
                try:
                    lm, et = _entetes(url)
                except Exception as exc:
                    f.write(f"{maintenant}\t{code}\tERREUR\t{type(exc).__name__}\n")
                    continue
                # L'ETag sert de repli quand le serveur n'annonce pas de date
                # (FC-Moto) : il change quand le fichier change, c'est tout ce
                # qu'on demande ici.
                signe = lm or et or "inconnu"
                if connu.get(code) != signe:
                    marque = "NOUVEAU" if code in connu else "depart"
                    f.write(f"{maintenant}\t{code}\t{marque}\t{signe}\n")
                    print(f"  {maintenant}  {code:<14} {marque:<8} {signe}", flush=True)
                    connu[code] = signe
        time.sleep(minutes * 60)

    conclut()


def conclut() -> None:
    if not os.path.exists(JOURNAL):
        print("aucun relevé pour l'instant.")
        return
    par_code: dict[str, list[str]] = {}
    with open(JOURNAL, encoding="utf-8") as journal:
        for ligne in journal:
            champs = ligne.rstrip("\n").split("\t")
            if len(champs) == 4 and champs[2] in ("NOUVEAU", "depart"):
                par_code.setdefault(champs[1], []).append(champs[0])
    print(f"\n{'marchand':<14} {'republications observées':>24}   première -> dernière")
    print("-" * 74)
    for code in CODES:
        dates = par_code.get(code, [])
        n = max(0, len(dates) - 1)  # le « depart » n'est pas une republication
        borne = f"{dates[0]} -> {dates[-1]}" if dates else "—"
        print(f"{code:<14} {n:>24}   {borne}")
    print("\nUne republication observée = une occasion de rafraîchir les prix.")


if __name__ == "__main__":
    if "--resume" in sys.argv:
        conclut()
    else:
        h = float(sys.argv[1]) if len(sys.argv) > 1 else 24.0
        m = int(sys.argv[2]) if len(sys.argv) > 2 else 15
        echantillonne(h, m)
