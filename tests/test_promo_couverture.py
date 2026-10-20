"""Chaque marchand du pipeline a une page de codes promo a lire, ou une raison ecrite de ne pas en avoir (20/10/2026).

Le 20/10/2026, Motard Bleu et Motoin etaient dans `FEEDS` (et Motoin affiche sur le site) sans figurer dans
`promo.PAGES` : le releve quotidien ne les lisait jamais, sans qu'aucune erreur ne le signale.
"""

from mcpipe.feeds import FEEDS
from mcpipe.promo import PAGES

# Marchands volontairement absents de PAGES, avec la raison. Toute autre absence est un oubli.
SANS_RELEVE = {
    # La Becanerie est derriere Cloudflare (HTTP 403) : ses codes se saisissent a la main (`source = 'manuel'`).
    "labecanerie": "Cloudflare refuse la machine ; codes saisis a la main dans /admin/code-promo",
}


def test_tout_marchand_est_releve_ou_a_une_raison():
    oublies = sorted(c for c in FEEDS if c not in PAGES and c not in SANS_RELEVE)
    assert not oublies, f"marchands jamais lus pour leurs codes promo : {oublies}"


def test_motard_bleu_et_motoin_sont_lus():
    assert PAGES["motardbleu"][0].endswith("/codes-promo")
    assert PAGES["motoin"] == ("https://www.motoin.de/",)


def test_les_pages_sont_des_urls_https_du_marchand():
    for code, urls in PAGES.items():
        assert urls and all(u.startswith("https://") for u in urls), code
