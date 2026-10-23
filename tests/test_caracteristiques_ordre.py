"""Un marchand dont le flux est lu doit aussi compter dans la fusion des descriptions (24/10/2026)."""

from mcpipe.caracteristiques import _ORDRE
from mcpipe.feeds import FEEDS


def test_tout_marchand_de_flux_figure_dans_l_ordre_de_fusion():
    """Sinon ses descriptions sont lues puis ecartees en silence : les gants chauffants Gerbing, vendus par Motard
    Bleu et Motoin, n'avaient qu'une caracteristique (la saison, deduite du rayon)."""
    manquants = set(FEEDS) - set(_ORDRE)
    assert not manquants, f"marchands lus mais jamais fusionnes : {sorted(manquants)}"


def test_l_ordre_ne_cite_aucun_marchand_inconnu():
    assert set(_ORDRE) <= set(FEEDS)
