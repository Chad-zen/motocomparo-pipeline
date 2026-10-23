"""La rubrique articles (`/guides/<slug>`) : lecture des fichiers, puis rendu.

Deux familles de vérifications. La première (toujours exécutée) relit les
VRAIS fichiers d'articles du dépôt — elle n'invente rien, elle vérifie que ce
qui est écrit obéit aux règles du module (un brouillon ne sort pas, un trou
« à compléter » empêche la publication). La seconde (sautée sans base) rend
les pages, dans l'esprit de `test_site_pages.py` : la leçon de ce fichier est
qu'un test qui n'ouvre pas la page ne vaut rien.

LE COMPORTEMENT D'UN BROUILLON EST TESTÉ SUR UN BROUILLON DE TEST. Les trois
premiers articles du dépôt sont publiés depuis le 16/10/2026 ; un test qui
s'appuierait sur l'un d'eux pour vérifier qu'un brouillon reste caché
casserait à chaque publication. La fixture `dossier_de_test` fabrique donc un
dossier temporaire (les trois vrais articles recopiés, plus un brouillon) et
y pointe le module, le temps du test.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from mcsite import articles

DOSSIER = Path(__file__).parent.parent / "src" / "mcsite" / "templates" / "articles"

PUBLIES = (
    "ls2-ff818-vs-scorpion-exo-530",
    "gants-ete-ou-hiver",
    "casque-jet-modulable-integral-norme",
)
BROUILLON = "brouillon-de-test"
_TEXTE_BROUILLON = (
    "{#---\ntitre: Brouillon de test\ndescription: Un article jamais publié.\n"
    "date: 2026-10-01\nstatut: brouillon\n---#}\n"
    "<p>Texte du brouillon de test.</p>\n")


def _ecrire(dossier: Path, nom: str, entete: str, corps: str = "<p>x</p>") -> Path:
    chemin = dossier / f"{nom}.html"
    chemin.write_text("{#---\n" + entete + "\n---#}\n" + corps, encoding="utf-8")
    return chemin


_ENTETE_MIN = "titre: Test\ndescription: Test\ndate: 2026-01-01\nstatut: publié"


# --- les fichiers ------------------------------------------------------------

def test_le_depot_ne_contient_aucun_article_publie_avec_un_trou():
    """La règle du site, imposée par le code : un passage `a_completer(...)`
    encore présent dégrade l'article en brouillon, quoi que dise son en-tête —
    jamais l'inverse."""
    for a in articles.tous(DOSSIER):
        if a.trous:
            assert not a.publie, (
                f"{a.slug} est marqué publié mais contient encore "
                f"{a.trous} passage(s) à compléter")


def test_les_trois_premiers_articles_sont_publies_et_complets():
    slugs = {a.slug: a for a in articles.tous(DOSSIER)}
    for slug in PUBLIES:
        assert slug in slugs, f"article manquant : {slug}"
        a = slugs[slug]
        assert a.statut == articles.PUBLIE, slug
        assert a.trous == 0, f"{slug} contient encore un passage à compléter"
        assert a.publie
        # La charte : un titre et une description à la taille de Google.
        assert len(a.titre) <= 70, f"{slug} : titre de {len(a.titre)} caractères"
        assert 110 <= len(a.description) <= 165, (
            f"{slug} : description de {len(a.description)} caractères")


def test_un_slug_inconnu_du_fichier_leve_une_erreur(tmp_path):
    """Le nom du fichier et le slug déclaré doivent être le même mot : sinon
    l'adresse `/guides/<slug>` ne correspondrait plus au fichier lu."""
    chemin = _ecrire(tmp_path, "exemple", _ENTETE_MIN + "\nslug: autre-chose")
    with pytest.raises(ValueError):
        articles.lire(chemin)


def test_apercu_desactive_par_defaut(monkeypatch):
    monkeypatch.delenv("BLOG_APERCU", raising=False)
    assert not articles.apercu_actif()
    monkeypatch.setenv("BLOG_APERCU", "1")
    assert articles.apercu_actif()


# --- l'illustration ------------------------------------------------------------

def test_sans_illustration_rien_a_afficher(tmp_path):
    a = articles.lire(_ecrire(tmp_path, "sans-image", _ENTETE_MIN))
    assert a.illustration == ""
    assert a.illustration_url is None


def test_illustration_annoncee_mais_pas_deposee(tmp_path, monkeypatch):
    """L'en-tête peut annoncer l'image avant qu'elle soit générée : tant que
    le fichier n'est pas dans `static/guides/`, pas d'image (donc pas d'image
    cassée)."""
    monkeypatch.setattr(articles, "ILLUSTRATIONS", tmp_path / "guides")
    a = articles.lire(_ecrire(
        tmp_path, "avec-image",
        _ENTETE_MIN + "\nillustration: avec-image.webp\nillustration_alt: Une route."))
    assert a.illustration == "avec-image.webp"
    assert a.illustration_alt == "Une route."
    assert a.illustration_url is None
    assert "illustration" not in a.extra


def test_illustration_deposee(tmp_path, monkeypatch):
    images = tmp_path / "guides"
    images.mkdir()
    (images / "avec-image.webp").write_bytes(b"RIFF")
    monkeypatch.setattr(articles, "ILLUSTRATIONS", images)
    a = articles.lire(_ecrire(
        tmp_path, "avec-image",
        _ENTETE_MIN + "\nillustration: avec-image.webp\nillustration_alt: Une route."))
    assert a.illustration_url == "/static/guides/avec-image.webp"


@pytest.mark.parametrize("nom", ["../app.py", "sous/dossier.webp", "Image.WEBP",
                                 "image.gif", "image"])
def test_illustration_au_nom_douteux_refusee(tmp_path, nom):
    chemin = _ecrire(tmp_path, "douteux",
                     _ENTETE_MIN + f"\nillustration: {nom}\nillustration_alt: x")
    with pytest.raises(ValueError):
        articles.lire(chemin)


def test_illustration_sans_texte_alternatif_refusee(tmp_path):
    chemin = _ecrire(tmp_path, "sans-alt", _ENTETE_MIN + "\nillustration: sans-alt.webp")
    with pytest.raises(ValueError):
        articles.lire(chemin)


# --- le rendu (base requise) ---------------------------------------------------

pytestmark_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="rendre une page demande la base")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from mcsite.app import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def dossier_de_test(tmp_path, monkeypatch):
    """Un dossier d'articles temporaire : les vrais articles recopiés, plus
    un brouillon. Le module lit `articles.DOSSIER` à chaque appel, et le
    gabarit du brouillon est rendu par un chargeur Jinja ajouté devant celui
    du site — rien n'est écrit dans le dépôt. Le cache est vidé avant et
    après, pour qu'un plan du site calculé ici ne serve pas au test suivant."""
    from jinja2 import ChoiceLoader, FileSystemLoader

    from mcsite import cache
    from mcsite.app import templates

    racine = tmp_path / "gabarits"
    dossier = racine / "articles"
    dossier.mkdir(parents=True)
    for slug in PUBLIES:
        shutil.copy(DOSSIER / f"{slug}.html", dossier / f"{slug}.html")
    (dossier / f"{BROUILLON}.html").write_text(_TEXTE_BROUILLON, encoding="utf-8")

    monkeypatch.setattr(articles, "DOSSIER", dossier)
    monkeypatch.setattr(templates.env, "loader",
                        ChoiceLoader([templates.env.loader, FileSystemLoader(racine)]))
    cache.vider()
    yield dossier
    cache.vider()


@pytestmark_db
def test_index_guides_liste_les_publies_et_pas_le_brouillon(client, dossier_de_test):
    r = client.get("/guides")
    assert r.status_code == 200
    for slug in PUBLIES:
        assert f"/guides/{slug}" in r.text
    assert f"/guides/{BROUILLON}" not in r.text


@pytestmark_db
def test_brouillon_est_un_404_sans_apercu(client, dossier_de_test, monkeypatch):
    monkeypatch.delenv("BLOG_APERCU", raising=False)
    assert client.get(f"/guides/{BROUILLON}").status_code == 404


@pytestmark_db
def test_brouillon_se_rend_en_apercu_avec_noindex_et_json_ld(
        client, dossier_de_test, monkeypatch):
    monkeypatch.setenv("BLOG_APERCU", "1")
    r = client.get(f"/guides/{BROUILLON}")
    assert r.status_code == 200
    assert '<meta name="robots" content="noindex, follow">' in r.text
    assert '"@type": "BlogPosting"' in r.text
    assert "BROUILLON" in r.text
    assert "Texte du brouillon de test." in r.text


@pytestmark_db
@pytest.mark.parametrize("slug", PUBLIES)
def test_un_article_publie_se_rend_sans_apercu(client, slug, monkeypatch):
    """Les vrais fichiers, rendus comme en production : 200, indexable, pas
    de bandeau brouillon, pas de trou, la réponse courte en tête."""
    monkeypatch.delenv("BLOG_APERCU", raising=False)
    r = client.get(f"/guides/{slug}")
    assert r.status_code == 200
    assert "noindex" not in r.text
    assert "BROUILLON" not in r.text
    assert "a-completer" not in r.text
    assert "article__reponse" in r.text
    assert '"@type": "BlogPosting"' in r.text


@pytestmark_db
def test_le_bloc_de_donnees_du_duel_rend_un_tableau(client, monkeypatch):
    """Le bloc chiffré (prix, caractéristiques) de l'article « duel » doit
    produire un vrai tableau, pas une page vide faute de fiches trouvées."""
    monkeypatch.delenv("BLOG_APERCU", raising=False)
    r = client.get("/guides/ls2-ff818-vs-scorpion-exo-530")
    assert r.status_code == 200
    assert "article-comparaison" in r.text
    assert "Prix du jour" in r.text


@pytestmark_db
def test_sans_fichier_image_pas_de_figure(client, monkeypatch, tmp_path):
    """Les trois articles annoncent une illustration ; tant qu'elle n'est
    pas déposée, la page se rend sans figure et garde l'image de partage du
    site."""
    monkeypatch.setattr(articles, "ILLUSTRATIONS", tmp_path)
    r = client.get("/guides/gants-ete-ou-hiver")
    assert r.status_code == 200
    assert "article__illustration" not in r.text
    assert "/static/og-accueil.jpg" in r.text


@pytestmark_db
def test_avec_fichier_image_la_figure_et_le_partage(client, monkeypatch, tmp_path):
    a = articles.trouver("gants-ete-ou-hiver")
    (tmp_path / a.illustration).write_bytes(b"RIFF")
    monkeypatch.setattr(articles, "ILLUSTRATIONS", tmp_path)
    r = client.get("/guides/gants-ete-ou-hiver")
    assert r.status_code == 200
    assert 'class="article__illustration"' in r.text
    assert f'src="/static/guides/{a.illustration}"' in r.text
    assert "générée par IA" in r.text
    assert f'property="og:image" content="http://testserver/static/guides/{a.illustration}"' in r.text
    assert '"image": "http://testserver/static/guides/' in r.text


@pytestmark_db
def test_un_article_inconnu_est_un_404(client):
    assert client.get("/guides/ce-slug-n-existe-pas").status_code == 404


@pytestmark_db
def test_le_plan_du_site_contient_les_publies_et_pas_le_brouillon(
        client, dossier_de_test, monkeypatch):
    """Un seul calcul du plan du site pour les deux vérifications : c'est
    le test le plus lent du fichier."""
    monkeypatch.delenv("BLOG_APERCU", raising=False)
    r = client.get("/sitemap-1.xml")
    assert r.status_code == 200
    for slug in PUBLIES:
        assert f"/guides/{slug}</loc>" in r.text
    assert f"/guides/{BROUILLON}" not in r.text


def test_la_mise_en_forme_pose_les_ancres_le_sommaire_le_temps_de_lecture_et_la_faq():
    """La forme d'un article (23/10/2026) : sommaire, minutes de lecture, FAQ lue pour les donnees structurees."""
    from mcsite.articles import mise_en_forme

    html = ("<h2>Ce que la loi impose</h2><p>" + "mot " * 440 + "</p><h3>Détail</h3>"
            "<h2>Ce que la loi impose</h2><h2>Avant d'acheter</h2>"
            '<details class="faq"><summary>Peut-on rouler sans gants ?</summary><p>Non, les gants sont obligatoires.</p></details>')
    corps, sommaire, minutes, faq = mise_en_forme(html)
    assert [t for _, t in sommaire] == ["Ce que la loi impose", "Ce que la loi impose", "Avant d'acheter"]
    ancres = [a for a, _ in sommaire]
    assert len(set(ancres)) == 3, "deux intertitres identiques doivent avoir deux ancres differentes"
    assert all(f'id="{a}"' in corps for a in ancres)
    assert minutes == 2
    assert faq == [{"q": "Peut-on rouler sans gants ?", "r": "Non, les gants sont obligatoires."}]
