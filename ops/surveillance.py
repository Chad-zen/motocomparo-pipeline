"""Relevé quotidien de l'état du site — un JSON sur la sortie standard.

Lancé sur le VPS, en root, avec l'environnement du site :

    systemd-run --wait --pipe --quiet \\
        --property=EnvironmentFile=/srv/motocomparo/.env \\
        /srv/motocomparo/venv/bin/python /srv/motocomparo/app/ops/surveillance.py

Il ne corrige rien et n'écrit nulle part ailleurs que dans son propre fichier
d'état (`ETAT_VEILLE`, pour comparer à la veille). Les alertes sont calculées
ICI, avec des seuils écrits en dur, et non laissées à l'appréciation de l'agent
qui recopie le résultat dans le tableau de bord : le même état donne toujours
les mêmes alertes.

Né de l'incident du 14/10/2026 : un flux FC-Moto passé de 160 000 à 6,8
millions de lignes a rempli le disque, la chaîne nocturne s'est arrêtée, et les
prix sont restés figés deux jours sans que personne ne le voie. Chacune des
alertes ci-dessous aurait levé ce cas le matin même.
"""

from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request

import psycopg

SITE = "https://motocomparo.com"
SAUVEGARDES = "/srv/motocomparo/sauvegardes"
FLUX = "/srv/motocomparo/feeds"
JOURNAL_NGINX = "/var/log/nginx/motocomparo.access.log"
ETAT_VEILLE = "/srv/motocomparo/surveillance-veille.json"

MARCHANDS = {1: "Speedway", 2: "La Bécanerie", 3: "Motoblouz",
             4: "Maxxess", 5: "Moto-Axxe", 6: "FC-Moto"}

# Seuils. Une fenêtre de 26 h et non 24 : la chaîne démarre à heure variable
# (RandomizedDelaySec) et dure jusqu'à deux heures.
FRAICHEUR_MAX_H = 26
DISQUE_ATTENTION, DISQUE_CRITIQUE = 85, 92
VARIATION_OFFRES = 0.30
REPONSE_LENTE_S = 3.0
ERREURS_5XX_MAX = 20


def _alerte(alertes, niveau, sujet, message):
    alertes.append({"niveau": niveau, "sujet": sujet, "message": message})


def _page(chemin: str) -> dict:
    t0 = time.time()
    try:
        req = urllib.request.Request(SITE + chemin, headers={"User-Agent": "motocomparo-veille"})
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:  # noqa: BLE001 — injoignable : c'est l'information
        return {"chemin": chemin, "code": None, "secondes": None, "erreur": str(e)[:200]}
    return {"chemin": chemin, "code": code, "secondes": round(time.time() - t0, 2)}


def _erreurs_5xx_24h() -> int:
    limite = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
    # Ancré en début de ligne : une requête malformée (crochets, guillemets
    # échappés) ne doit pas faire lire une date au mauvais endroit.
    motif = re.compile(r'^\S+ \S+ \S+ \[([^\]]+)\] "(?:[^"\\]|\\.)*" (\d{3}) ')
    n = 0
    for chemin in (JOURNAL_NGINX, JOURNAL_NGINX + ".1"):
        if not os.path.exists(chemin):
            continue
        with open(chemin, errors="replace") as fh:
            for ligne in fh:
                m = motif.match(ligne)
                if not m or not m.group(2).startswith("5"):
                    continue
                try:
                    quand = dt.datetime.strptime(m.group(1), "%d/%b/%Y:%H:%M:%S %z")
                except ValueError:
                    continue
                if quand >= limite:
                    n += 1
    return n


def _chaine_nocturne() -> dict:
    sortie = subprocess.run(
        ["systemctl", "show", "mcpipe-prix", "-p", "Result",
         "-p", "ExecMainExitTimestamp", "-p", "ExecMainStatus"],
        capture_output=True, text=True, check=False).stdout
    champs = dict(l.split("=", 1) for l in sortie.splitlines() if "=" in l)
    return {"resultat": champs.get("Result", ""),
            "fin": champs.get("ExecMainExitTimestamp", ""),
            "code_sortie": champs.get("ExecMainStatus", "")}


def releve() -> dict:
    alertes: list[dict] = []
    maintenant = dt.datetime.now(dt.timezone.utc)

    # --- le site, vu comme un visiteur ---------------------------------------
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        fiche = conn.execute(
            "SELECT p.slug FROM product p JOIN product_stats s ON s.product_id = p.id "
            "WHERE s.merchant_count >= 3 ORDER BY s.merchant_count DESC, p.slug LIMIT 1"
        ).fetchone()
        pages = [_page("/"), _page("/recherche?q=casque")]
        if fiche:
            pages.append(_page(f"/p/{fiche[0]}"))
        for p in pages:
            if p["code"] != 200:
                _alerte(alertes, "critique", "site",
                        f"{p['chemin']} répond {p['code'] or p.get('erreur')}")
            elif p["secondes"] > REPONSE_LENTE_S:
                _alerte(alertes, "attention", "site",
                        f"{p['chemin']} a mis {p['secondes']} s à répondre")

        # --- les prix : fraîcheur et volume par marchand ----------------------
        lignes = conn.execute("""
            SELECT merchant_id,
                   count(*) FILTER (WHERE is_live)                         AS vivantes,
                   extract(epoch FROM now() - max(last_seen)) / 3600       AS age_h
            FROM raw_offer GROUP BY merchant_id ORDER BY merchant_id
        """).fetchall()
        fiches = conn.execute(
            "SELECT count(*), count(*) FILTER (WHERE cheapest IS NOT NULL) FROM product_stats"
        ).fetchone()
        messages_24h = conn.execute(
            "SELECT count(*) FROM message_contact WHERE recu_le > now() - interval '24 hours'"
        ).fetchone()[0]
        taille_base = conn.execute(
            "SELECT pg_database_size(current_database())").fetchone()[0]

    # Relancé deux fois le même jour, le relevé se compare toujours à la VEILLE,
    # jamais à lui-même : le fichier garde le jour qu'il décrit et le précédent.
    jour = f"{maintenant:%Y-%m-%d}"
    try:
        with open(ETAT_VEILLE, encoding="utf-8") as fh:
            etat = json.load(fh)
    except (OSError, ValueError):
        etat = {}
    reference = etat.get("precedent", {}) if etat.get("jour") == jour else etat.get("offres", {})
    offres_veille = {int(k): v for k, v in reference.items()}

    marchands = []
    for mid, vivantes, age_h in lignes:
        nom = MARCHANDS.get(mid, str(mid))
        age = round(float(age_h), 1) if age_h is not None else None
        avant = offres_veille.get(mid)
        variation = (vivantes - avant) / avant if avant else None
        marchands.append({"id": mid, "nom": nom, "offres": vivantes, "age_h": age,
                          "offres_veille": avant,
                          "variation": round(variation, 3) if variation is not None else None})
        if age is None or age > FRAICHEUR_MAX_H:
            _alerte(alertes, "critique", "prix",
                    f"{nom} : prix non rafraîchis depuis {age} h")
        if variation is not None and abs(variation) > VARIATION_OFFRES:
            _alerte(alertes, "attention", "flux",
                    f"{nom} : {avant:,} → {vivantes:,} offres en un jour "
                    f"({variation:+.0%})".replace(",", " "))

    # --- la machine ------------------------------------------------------------
    disque = shutil.disk_usage("/")
    disque_pct = round(disque.used / disque.total * 100, 1)
    if disque_pct >= DISQUE_CRITIQUE:
        _alerte(alertes, "critique", "disque", f"disque plein à {disque_pct} %")
    elif disque_pct >= DISQUE_ATTENTION:
        _alerte(alertes, "attention", "disque", f"disque plein à {disque_pct} %")

    chaine = _chaine_nocturne()
    if chaine["resultat"] not in ("success", ""):
        _alerte(alertes, "critique", "chaine",
                f"la chaîne de relevé des prix a échoué ({chaine['resultat']}, "
                f"code {chaine['code_sortie']}, fin {chaine['fin']})")

    site_actif = subprocess.run(["systemctl", "is-active", "mcsite"],
                                capture_output=True, text=True, check=False).stdout.strip()
    if site_actif != "active":
        _alerte(alertes, "critique", "site", f"le service mcsite est « {site_actif} »")

    erreurs = _erreurs_5xx_24h()
    if erreurs > ERREURS_5XX_MAX:
        _alerte(alertes, "attention", "site", f"{erreurs} erreurs serveur (5xx) en 24 h")

    dumps = sorted(glob.glob(f"{SAUVEGARDES}/mcpipe-*.dump"))
    derniere = os.path.basename(dumps[-1]) if dumps else None
    if derniere != f"mcpipe-{maintenant:%Y-%m-%d}.dump":
        _alerte(alertes, "attention", "sauvegarde",
                f"pas de sauvegarde datée d'aujourd'hui (dernière : {derniere})")

    flux = {os.path.basename(f): round(os.path.getsize(f) / 1_048_576, 1)
            for f in sorted(glob.glob(f"{FLUX}/*.csv"))}

    with open(ETAT_VEILLE, "w", encoding="utf-8") as fh:
        json.dump({"jour": jour, "precedent": reference,
                   "offres": {m["id"]: m["offres"] for m in marchands}}, fh)

    niveaux = {a["niveau"] for a in alertes}
    statut = "critique" if "critique" in niveaux else ("attention" if niveaux else "ok")
    return {
        "genere_le": maintenant.isoformat(timespec="seconds"),
        "jour": jour,
        "statut": statut,
        "alertes": alertes,
        "pages": pages,
        "marchands": marchands,
        "fiches": {"total": fiches[0], "avec_prix": fiches[1]},
        "disque_pct": disque_pct,
        "disque_libre_go": round(disque.free / 1e9, 1),
        "base_go": round(taille_base / 1e9, 1),
        "chaine": chaine,
        "erreurs_5xx_24h": erreurs,
        "sauvegarde": derniere,
        "flux_mo": flux,
        "messages_contact_24h": messages_24h,
    }


if __name__ == "__main__":
    print(json.dumps(releve()))
