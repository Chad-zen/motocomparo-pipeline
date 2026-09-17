"""Rien de personnel ne doit entrer dans ce dépôt public.

POURQUOI CE FICHIER EXISTE. Le 17/09/2026, un commit a emporté le nom de
famille de la propriétaire en clair, dans un commentaire expliquant une panne,
sur un dépôt public et volontairement anonymisé. Un balayage avait pourtant été
lancé avant de commiter — il cherchait les termes dont je me souvenais, pas la
règle que j'appliquais. Une vérification écrite de mémoire ne vérifie rien.

POURQUOI LES MOTIFS NE SONT PAS ÉCRITS ICI. Ils DÉCRIVENT ce qu'on cache : les
écrire dans le dépôt publierait exactement ce que le test protège. Ils vivent
donc dans `.anonymat`, à la racine, non versionné — un motif d'expression
régulière par ligne, les lignes vides et celles commençant par `#` ignorées.

Sans ce fichier, la vérification est IGNORÉE et le dit. C'est un choix assumé :
elle sert au moment du commit, sur la machine de la propriétaire, pas dans une
forge qui n'a rien à savoir de ce qu'elle protège.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
LISTE = RACINE / ".anonymat"

# Ce fichier-ci parle des motifs : il les contiendrait tous en clair.
EXCLUS = {"tests/test_depot_anonyme.py", ".anonymat"}


def _motifs() -> list[str]:
    return [l.strip() for l in LISTE.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]


def _versionnes() -> list[str]:
    sortie = subprocess.run(["git", "ls-files"], cwd=RACINE,
                            capture_output=True, text=True, check=True)
    return [f for f in sortie.stdout.split("\n") if f and f not in EXCLUS]


@pytest.mark.skipif(not LISTE.exists(),
                    reason="`.anonymat` absent : la liste des motifs est locale, "
                           "non versionnée (voir le docstring)")
def test_aucune_donnee_personnelle_dans_les_fichiers_versionnes():
    motifs = [re.compile(m, re.I) for m in _motifs()]
    assert motifs, ".anonymat est vide"

    fautes: list[str] = []
    for chemin in _versionnes():
        f = RACINE / chemin
        try:
            texte = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, ligne in enumerate(texte.splitlines(), 1):
            for m in motifs:
                if m.search(ligne):
                    # Le motif n'est PAS répété dans le message : il finirait
                    # dans une sortie de test, un journal d'intégration continue,
                    # un rapport — c'est-à-dire publié par l'outil censé l'éviter.
                    fautes.append(f"{chemin}:{i}")
                    break
    assert not fautes, (
        "donnée personnelle dans un dépôt public, aux emplacements suivants — "
        "le motif n'est volontairement pas répété ici : " + ", ".join(fautes))
