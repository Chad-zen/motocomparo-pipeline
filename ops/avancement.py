"""Où en est le pipeline, en une ligne lisible.

`match` est une poignée de très grosses requêtes SQL : il n'affiche rien entre
le début et la fin, et il n'existe aucun moyen de demander à PostgreSQL « à quel
pourcentage en est cette requête » — la fonctionnalité n'existe pas pour un
SELECT. Ce que ce script montre est donc honnête sur ce qu'il sait :

  - l'étape en cours, lue dans le journal du lancement ;
  - le temps écoulé sur cette étape ;
  - une barre calée sur la durée HABITUELLE de l'étape, pas sur son avancement
    réel — elle peut donc dépasser 100 %, et c'est normal ;
  - une preuve de vie : si le compteur d'entrées/sorties bouge, la base
    travaille ; s'il ne bouge plus, elle est bloquée et il faut regarder.

    python ops/avancement.py <fichier-journal>
"""

from __future__ import annotations

import os
import pathlib
import sys
import time

# la console Windows est en cp1252 : sans ceci, un accent fait planter l'affichage
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

_ENV = pathlib.Path(__file__).resolve().parent.parent / ".env"
if _ENV.exists():
    for _l in _ENV.read_text(encoding="utf-8").splitlines():
        if "=" in _l and not _l.strip().startswith("#"):
            _k, _, _v = _l.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from mcpipe.db import connect  # noqa: E402

# (marqueur cherché dans le journal, nom lisible, durée habituelle en secondes)
ETAPES = [
    ("=== signature ===",      "Signatures",        520),
    ("=== enrich ===",         "Enrichissement",    240),
    ("=== match --reset ===",  "Appariement",      2400),
    ("=== verify ===",         "Vérification",      120),
    ("=== freshness ===",      "Prix & fraîcheur",  180),
    ("=== product_stats ===",  "Vue d'affichage",    60),
]


def _pouls() -> tuple[int, str]:
    """Combien la base a lu depuis son démarrage, et ce qu'elle attend."""
    with connect() as c:
        io = list(c.execute("""
            SELECT blks_read + blks_hit + temp_bytes / 8192
            FROM pg_stat_database WHERE datname = current_database()
        """))[0][0]
        act = list(c.execute("""
            SELECT coalesce(wait_event, 'calcul'),
                   round(extract(epoch from now() - query_start))::int
            FROM pg_stat_activity
            WHERE datname = current_database() AND pid <> pg_backend_pid()
              AND state = 'active' LIMIT 1
        """))
    return int(io), (f"{act[0][0]} depuis {act[0][1] // 60} min" if act else "au repos")


def barre(fraction: float, largeur: int = 34) -> str:
    plein = min(largeur, int(fraction * largeur))
    depasse = ">" if fraction > 1 else ""
    return "[" + "#" * plein + "." * (largeur - plein) + "]" + depasse


def etape_en_cours(journal: pathlib.Path) -> tuple[int, float]:
    """Index de l'étape en cours et secondes écoulées dessus."""
    texte = journal.read_text(encoding="utf-8", errors="replace")
    if "=== FIN ===" in texte:
        return len(ETAPES), 0.0
    index = 0
    for i, (marqueur, _, _) in enumerate(ETAPES):
        if marqueur in texte:
            index = i
    # le fichier est réécrit à chaque ligne : sa date de modification est celle
    # de la dernière ligne écrite, donc du début de l'étape en cours
    return index, time.time() - journal.stat().st_mtime


def main() -> None:
    journal = pathlib.Path(sys.argv[1])
    i, ecoule = etape_en_cours(journal)
    if i >= len(ETAPES):
        print("Chaîne terminée.")
        return

    _, nom, habituel = ETAPES[i]
    fini = sum(e[2] for e in ETAPES[:i])
    total = sum(e[2] for e in ETAPES)
    reste = max(0, total - fini - ecoule)

    io_a, _ = _pouls()
    time.sleep(6)
    io_b, attente = _pouls()
    vivant = "la base travaille" if io_b > io_a else "AUCUNE ACTIVITÉ — à vérifier"

    print(f"Étape {i + 1}/{len(ETAPES)} — {nom}")
    print(f"  {barre(ecoule / habituel)}  {ecoule / 60:.0f} min écoulées "
          f"(habituellement ~{habituel // 60} min)")
    print(f"  {barre((fini + ecoule) / total)}  chaîne complète, "
          f"reste ~{reste / 60:.0f} min")
    print(f"  {vivant} — {attente}")


if __name__ == "__main__":
    main()
