"""La rubrique articles (`/guides/<slug>`) : lecture des fichiers, puis rendu.

Deux familles de vérifications. La première (toujours exécutée) relit les
VRAIS fichiers d'articles du dépôt — elle n'invente rien, elle vérifie que ce
qui est écrit obéit aux règles du module (un brouillon ne sort pas, un trou
« à compléter » empêche la publication). La seconde (sautée sans base) rend
les pages, dans l'esprit de `test_site_pages.py` : la leçon de ce fichier est
qu'un test qui n'ouvre pas la page ne vaut rien.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mcsite import articles

DOSSIER = Path(__file__).parent.parent / "src" / "mcsite" / "templates" / "articles"


def test_le_depot_ne_contient_aucun_article_publie_avec_un_trou():
    """La règle du site, imposée par le code : un passage `a_completer(...)`
    encore présent dégrade l'article en brouillon, quoi que dise son en-tête —
    jamais l'inverse."""
    for a in articles.tous(DOSSIER):
        if a.trous:
            assert not a.publie, (
                f"{a.slug} est marqué publié mais contient encore "
                f"{a.trous} passage(s) à compléter")


def test_les_trois_brouillons_existent_et_se_lisent():
    """Les trois articles écrits pour ce chantier : vérifie qu'ils chargent
    sans lever d'erreur de format et qu'ils sont bien à l'état brouillon,
    chacun marquant au moins un passage laissé à la propriétaire."""
    slugs = {a.slug: a for a in articles.tous(DOSSIER)}
    attendus = [
        "ls2-ff818-vs-scorpion-exo-530",
        "gants-ete-ou-hiver",
        "casque-jet-modulable-integral-norme",
    ]
    for slug in attendus:
        assert slug in slugs, f"article manquant : {slug}"
        a = slugs[slug]
        assert a.statut == articles.BROUILLON
        assert not a.publie
        assert a.trous >= 1, f"{slug} ne marque aucun passage à compléter"


def test_un_slug_inconnu_du_fichier_leve_une_erreur():
    """Le nom du fichier et le slug déclaré doivent être le même mot : sinon
    l'adresse `/guides/<slug>` ne correspondrait plus au fichier lu."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "exemple.html"
        chemin.write_text(
            "{#---\ntitre: Test\ndescription: Test\ndate: 2026-01-01\n"
            "statut: brouillon\nslug: autre-chose\n---#}\ncontenu",
            encoding="utf-8")
        with pytest.raises(ValueError):
            articles.lire(chemin)


def test_apercu_desactive_par_defaut(monkeypatch):
    monkeypatch.delenv("BLOG_APERCU", raising=False)
    assert not articles.apercu_actif()
    monkeypatch.setenv("BLOG_APERCU", "1")
    assert articles.apercu_actif()


pytestmark_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="rendre une page demande la base")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from mcsite.app import app
    with TestClient(app) as c:
        yield c


@pytestmark_db
def test_index_guides_ne_liste_aucun_brouillon(client):
    """Les trois brouillons de ce chantier ne doivent apparaître nulle part
    sur `/guides` — ni en lien, ni en titre — tant qu'ils ne sont pas
    publiés."""
    r = client.get("/guides")
    assert r.status_code == 200
    for slug in ("ls2-ff818-vs-scorpion-exo-530", "gants-ete-ou-hiver",
                "casque-jet-modulable-integral-norme"):
        assert f"/guides/{slug}" not in r.text


@pytestmark_db
def test_brouillon_est_un_404_sans_apercu(client, monkeypatch):
    monkeypatch.delenv("BLOG_APERCU", raising=False)
    r = client.get("/guides/ls2-ff818-vs-scorpion-exo-530")
    assert r.status_code == 404


@pytestmark_db
def test_brouillon_se_rend_en_apercu_avec_noindex_et_json_ld(client, monkeypatch):
    monkeypatch.setenv("BLOG_APERCU", "1")
    r = client.get("/guides/ls2-ff818-vs-scorpion-exo-530")
    assert r.status_code == 200
    assert '<meta name="robots" content="noindex, follow">' in r.text
    assert '"@type": "BlogPosting"' in r.text
    assert "BROUILLON" in r.text


@pytestmark_db
def test_le_bloc_de_donnees_du_duel_rend_un_tableau(client, monkeypatch):
    """Le bloc chiffré (prix, caractéristiques) de l'article « duel » doit
    produire un vrai tableau, pas une page vide faute de fiches trouvées."""
    monkeypatch.setenv("BLOG_APERCU", "1")
    r = client.get("/guides/ls2-ff818-vs-scorpion-exo-530")
    assert r.status_code == 200
    assert "article-comparaison" in r.text
    assert "Prix du jour" in r.text


@pytestmark_db
def test_un_article_inconnu_est_un_404(client):
    assert client.get("/guides/ce-slug-n-existe-pas").status_code == 404


@pytestmark_db
def test_un_brouillon_est_absent_du_sitemap(client, monkeypatch):
    monkeypatch.delenv("BLOG_APERCU", raising=False)
    from mcsite import cache
    cache.vider()
    r = client.get("/sitemap-1.xml")
    assert r.status_code == 200
    for slug in ("ls2-ff818-vs-scorpion-exo-530", "gants-ete-ou-hiver",
                "casque-jet-modulable-integral-norme"):
        assert f"/guides/{slug}" not in r.text
