"""Le filtre « offres connues seulement » du téléchargement — voir `fetch._filtrer_connues`."""

import csv
import io

from mcpipe.feeds import FEEDS
from mcpipe.fetch import _filtrer_connues

_FLUX = (
    'id,mpn,gtin,title,description\n'
    'h1,MPN-A,111,Casque A,"ligne 1\nligne 2, avec virgule"\n'
    'h2,,222,Casque B,court\n'
    'h3,,,Casque C,inconnu\n'
)


def _morceaux(texte, taille=7):
    # coupé n'importe où, y compris au milieu d'un champ entre guillemets
    return [texte[i:i + taille] for i in range(0, len(texte), taille)]


def test_ne_garde_que_les_cles_connues():
    fh = io.StringIO()
    # clé FC-Moto : mpn, sinon gtin, sinon id
    _, lues, gardees = _filtrer_connues(FEEDS["fcmoto"], _morceaux(_FLUX), fh, {"MPN-A", "222"})
    assert (lues, gardees) == (3, 2)
    lignes = list(csv.reader(io.StringIO(fh.getvalue())))
    assert lignes[0] == ["id", "mpn", "gtin", "title", "description"]
    assert [l[0] for l in lignes[1:]] == ["h1", "h2"]
    assert lignes[1][4] == "ligne 1\nligne 2, avec virgule"
