"""Exécuter les calculs demandés depuis l'écran « Calculs » de l'administration.

LISTE BLANCHE. Une demande ne désigne jamais une commande : elle désigne une
clé de `TACHES`, et c'est ici — pas dans le formulaire — que la commande est
écrite. Un formulaire détourné ne peut donc faire exécuter que ce qui est listé.

UNE TÂCHE À LA FOIS, ET PAS PENDANT LE RELEVÉ DE NUIT : deux calculs qui
réécrivent les mêmes tables se gêneraient, et le VPS n'a qu'un cœur.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from dataclasses import dataclass

from .db import connect


@dataclass(frozen=True)
class Tache:
    libelle: str
    aide: str
    etapes: tuple[tuple[str, ...], ...]      # commandes `mcpipe`, dans l'ordre
    duree: str
    redemarre_site: bool = True              # le site garde ses listes 3 h


TACHES: dict[str, Tache] = {
    "tailles": Tache(
        "Recalculer les tailles",
        "Rattache chaque offre à la bonne taille, retire les tailles que plus personne ne vend.",
        (("relier-tailles",),), "environ 1 minute"),
    "prix": Tache(
        "Recalculer les prix affichés",
        "Refait le meilleur prix de chaque fiche et l'historique du jour.",
        (("freshness",),), "environ 5 minutes"),
    "caracteristiques": Tache(
        "Recalculer matière, saison, homologation",
        "Relit les descriptions des marchands et réapplique tes saisies à la main.",
        (("caracteristiques",), ("couverture",)), "environ 10 minutes"),
    "regroupements": Tache(
        "Chercher les fiches à regrouper",
        "Met à jour les propositions de « Regroupements » et de « Marques ». Ne modifie aucune fiche.",
        (("consolider",),), "environ 3 minutes", redemarre_site=False),
    "appliquer-regroupements": Tache(
        "Appliquer les regroupements validés",
        "Fusionne les fiches que tu as validées, puis refait les tailles et les prix.",
        (("consolider", "--pas-proposer", "--appliquer"), ("relier-tailles",), ("freshness",)),
        "environ 8 minutes"),
}


def demander(tache: str) -> int | None:
    """Enregistre une demande ; None si la tâche est inconnue ou déjà en attente."""
    if tache not in TACHES:
        return None
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM tache_demandee WHERE tache = %s "
                        "AND statut IN ('demandee', 'en_cours')", (tache,))
            if cur.fetchone():
                return None
            cur.execute("INSERT INTO tache_demandee (tache) VALUES (%s) RETURNING id", (tache,))
            n = cur.fetchone()[0]
        conn.commit()
        return n
    finally:
        conn.close()


def _releve_de_nuit_en_cours() -> bool:
    try:
        r = subprocess.run(["systemctl", "is-active", "--quiet", "mcpipe-prix.service"])
    except FileNotFoundError:        # pas de systemd (poste de développement)
        return False
    return r.returncode == 0


def executer_une() -> str:
    """Exécute la plus ancienne demande, s'il y en a une. Rend ce qui s'est passé."""
    if _releve_de_nuit_en_cours():
        return "relevé de nuit en cours : on attend"
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM tache_demandee WHERE statut = 'en_cours'")
            if cur.fetchone():
                return "une tâche tourne déjà"
            cur.execute("SELECT id, tache FROM tache_demandee WHERE statut = 'demandee' "
                        "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED")
            ligne = cur.fetchone()
            if not ligne:
                return "rien à faire"
            tid, cle = ligne
            cur.execute("UPDATE tache_demandee SET statut = 'en_cours', debut_le = now() "
                        "WHERE id = %s", (tid,))
        conn.commit()

        tache = TACHES.get(cle)
        sortie, ok = [], tache is not None
        if tache is None:
            sortie.append(f"tâche inconnue : {cle}")
        else:
            for etape in tache.etapes:
                cmd = ["nice", "-n", "10", shutil.which("mcpipe") or sys.argv[0], *etape]
                t0 = time.time()
                r = subprocess.run(cmd, capture_output=True, text=True)
                sortie.append(f"$ mcpipe {' '.join(etape)}  ({time.time() - t0:.0f} s)")
                sortie.append((r.stdout or "").strip()[-600:])
                if r.returncode != 0:
                    sortie.append((r.stderr or "").strip()[-600:])
                    ok = False
                    break
        with conn.cursor() as cur:
            cur.execute("UPDATE tache_demandee SET statut = %s, fin_le = now(), sortie = %s "
                        "WHERE id = %s", ("terminee" if ok else "echec",
                                          "\n".join(sortie)[-3000:], tid))
        conn.commit()
        if ok and tache and tache.redemarre_site:
            # le site garde ses listes trois heures : un drapeau, lu par l'unité
            # système qui a le droit de redémarrer le site
            try:
                open("/srv/motocomparo/.redemarrer-site", "w").close()
            except OSError:          # poste de développement : pas de site à redémarrer
                pass
        return f"{cle} : {'terminée' if ok else 'ÉCHEC'}"
    finally:
        conn.close()
