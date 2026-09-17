"""Les pièges de `queries.py` qu'on ne voit qu'à l'exécution.

Trois fois dans la même journée — le 17/09/2026 — un `%` écrit dans un
COMMENTAIRE SQL a fait échouer une requête. psycopg lit la chaîne entière, pas
seulement le code : un « 18 % » ou un `{% if %}` dans une explication devient un
paramètre incomplet, et la page rend 500. L'erreur ne parle jamais du
commentaire, elle parle d'un « incomplete placeholder », et on cherche ailleurs.

Trois fois, ce n'est plus de la distraction : c'est un piège du langage, et un
piège se garde.
"""

from __future__ import annotations

import re

SOURCE = "src/mcsite/queries.py"


def _commentaires_sql() -> list[tuple[int, str]]:
    """Les lignes de commentaire SQL (`--`) à l'intérieur des requêtes.

    Un `--` en début de ligne dans ce fichier est toujours du SQL : les
    commentaires Python y commencent par `#`.
    """
    lignes = open(SOURCE, encoding="utf-8").read().splitlines()
    return [(i, l) for i, l in enumerate(lignes, 1) if l.strip().startswith("--")]


def test_aucun_pourcent_isole_dans_un_commentaire_sql():
    """`%s` est un paramètre, `%%` un pourcent littéral. Tout autre `%` casse la
    requête — y compris dans une phrase française parfaitement innocente."""
    fautifs = [(i, l.strip()) for i, l in _commentaires_sql()
               if re.search(r"%(?![%s])", l)]
    assert not fautifs, "\n".join(f"  ligne {i} : {l}" for i, l in fautifs)


# NOTE. Une seconde vérification a été tentée ici — compter les `%s` d'une
# requête et les comparer au nombre d'arguments fournis — puis RETIRÉE. Elle
# analysait du Python à coups d'expressions régulières et rendait un faux
# positif sur `brands()`, une requête pourtant juste.
#
# Un test auquel on ne peut pas se fier coûte plus qu'il ne rapporte : on finit
# par le contourner, puis par ignorer ses semblables. Le décompte des
# paramètres est de toute façon attrapé à la première visite par
# `tests/test_site_pages.py`, qui ouvre vraiment les pages.
