"""L'analyseur des fiches SHARP, et surtout : son silence quand il casse.

CE QUI EST VRAIMENT EN JEU ICI. Un analyseur de page HTML tombe en panne le jour
où le site d'en face change son thème, et il tombe en panne EN SILENCE : il rend
des fiches vides au lieu de lever une erreur. On réécrit alors 585 lignes de
néant par-dessus les bonnes, et personne ne le voit avant qu'un visiteur ne
demande pourquoi plus aucun casque n'a de note.

Ce projet a déjà payé cette leçon ailleurs : la clé de jointure des
caractéristiques était fausse pour trois marchands sur six, 113 967 offres sans
description, et 277 vérifications au vert. D'où `_exiger`, et d'où la moitié des
tests ci-dessous.

Les fragments HTML sont ceux de la vraie page, réduits — jamais inventés : un
test bâti sur du HTML imaginaire ne prouve que l'imagination de son auteur.
"""

from __future__ import annotations

import pytest

from mcpipe.sources import sharp


# Le tableau de la fiche AGV K7, relevé le 19/09/2026. Les tabulations et les
# retours chariot sont ceux du site : l'analyseur doit les traverser.
PAGE = """
<table class="table table-condensed">
<tbody>
\t\t<tr>
\t\t\t<th>Helmet rating</th>
\t\t\t<td><img src="/wp-content/themes/sharp2017/img/star-rating/rating-star-5.gif"></td>
\t\t</tr>
\t\t<tr><th>Model</th><td>K7</td></tr>
\t\t<tr><th>Manufacturer</th><td>AGV</td></tr>
\t\t<tr><th>Helmet weight</th><td>1.6kg</td></tr>
\t\t<tr><th>RRP</th><td>&pound;389.00</td></tr>
\t\t<tr><th>Helmet sizes</th><td>XS S M L XL XXL</td></tr>
\t\t<tr><th>Helmet type</th><td>Full face</td></tr>
\t\t<tr><th>Retention system</th><td>Quick release buckle</td></tr>
\t\t<tr><th>Materials</th><td>Composite Fibre</td></tr>
\t\t<tr><th>Standard</th><td>UN ECE REG 22.06</td></tr>
\t\t<tr>
\t\t\t<th>Manufacturer's Website</th>
\t\t<td>
\t\t\t<a target="_blank" href="http://www.agv.com/gb/en/full-face/k7/">
\t\t\twww.agv.com/gb/en/full-face/k7/\t\t</a>
\t\t\t</td>
\t\t</tr>
\t\t<tr><th>Test date</th><td>April 2026</td></tr>
</tbody>
</table>
<div class="col-md-6 col-sm-12 helmet-features">\r
<h3>Helmet features</h3>\r
<table class="table table-condensed table-bordered table-striped">\r
\t\t<tr>\r
\t\t\t<td><img class="center-block" src="/img/helmet-features/anti-fog-visor.png" alt="anti fog visor" /></td>\r
\t\t\t<td><strong>Anti fog visor</strong></td>\r
\t\t</tr>\r
\t\t<tr>\r
\t\t\t<td><img class="center-block" src="/img/helmet-features/sun-visor.png" alt="sun visor" /></td>\r
\t\t\t<td><strong>Dropdown sun-visor</strong></td>\r
\t\t</tr>\r
</table>\r
</div>
<h3>Cookies</h3>
<table class="cookielawinfo-row-cat-table">
\t<tr><td>_ga</td><td>1 year</td></tr>
\t<tr><td>CONSENT</td><td>2 years</td></tr>
</table>
"""


@pytest.fixture(scope="module")
def fiche():
    return sharp.lire("agv-k7", PAGE)


# --- le relevé lui-même -------------------------------------------------------

def test_les_champs_du_tableau_sont_lus(fiche):
    assert fiche.marque == "AGV"
    assert fiche.modele == "K7"
    assert fiche.etoiles == 5
    assert fiche.type_casque == "Full face"
    assert fiche.retention == "Quick release buckle"
    assert fiche.materiaux == "Composite Fibre"
    assert fiche.norme == "UN ECE REG 22.06"
    assert fiche.date_test == "April 2026"


def test_le_poids_est_ramene_au_gramme(fiche):
    """SHARP écrit « 1.6kg » ici et « 1450 g » ailleurs. Mélanger les deux dans
    une colonne donne un tri où 1,6 passe avant 1450 — un classement « du plus
    léger » qui met les casques lourds en tête, sans qu'aucune valeur soit
    fausse prise isolément."""
    assert fiche.poids_g == 1600
    assert sharp._poids_en_grammes("1450 g") == 1450
    assert sharp._poids_en_grammes("1,55 kg") == 1550
    assert sharp._poids_en_grammes("non communique") is None


def test_un_poids_mal_ponctue_ne_fait_pas_tomber_le_releve():
    """SHARP écrit « 1.35.kg » sur au moins une de ses 585 fiches. Une classe de
    caractères gourmande avalait le point final, `float("1.35.")` levait une
    ValueError, et le relevé s'arrêtait net à la 121ᵉ page — en emportant les
    120 déjà lues, puisque l'enregistrement n'a lieu qu'à la fin."""
    assert sharp._poids_en_grammes("1.35.kg") == 1350
    assert sharp._poids_en_grammes("1.6kg.") == 1600


def test_le_prix_perd_son_symbole(fiche):
    assert fiche.prix_gbp == 389.00


def test_le_site_du_constructeur_est_le_texte_pas_la_balise(fiche):
    """C'est la passerelle vers la source suivante : la fiche technique du
    fabricant. Une balise `<a>` mal nettoyée la rendrait inutilisable."""
    assert fiche.site_constructeur == "www.agv.com/gb/en/full-face/k7/"


# --- les pièges de la page ----------------------------------------------------

def test_les_equipements_viennent_du_bon_tableau(fiche):
    """Le pied de page porte QUATRE tableaux de cookies, faits eux aussi de
    lignes à deux cellules. Une première écriture les cherchait dans toute la
    page : le casque se retrouvait équipé de « _ga » et de « CONSENT »."""
    assert fiche.options == ["Anti fog visor", "Dropdown sun-visor"]
    assert not any("_ga" in o or "CONSENT" in o for o in fiche.options)


def test_un_pictogramme_ne_masque_pas_le_libelle():
    """La première cellule de ce tableau porte une IMAGE, pas du vide. Une
    écriture qui attendait une cellule vide devant ne remontait jamais aucune
    option — et ne levait, bien sûr, aucune erreur."""
    assert sharp.lire("x", PAGE).options


# --- la panne silencieuse -----------------------------------------------------

def test_une_page_vide_ne_produit_pas_une_fiche_credible():
    vide = sharp.lire("x", "<html><body>Service temporairement indisponible</body></html>")
    assert vide.etoiles is None and vide.poids_g is None and vide.modele == ""


def test_le_releve_refuse_de_s_enregistrer_s_il_est_muet():
    """LE test qui compte. Si SHARP change son thème, l'analyseur rendra des
    fiches vides sans lever d'erreur, et on écrasera 585 bonnes lignes par du
    néant. `_exiger` arrête le relevé avant la base."""
    muettes = [sharp.Fiche(slug=f"x{i}") for i in range(20)]
    with pytest.raises(RuntimeError, match="de structure"):
        sharp._exiger(muettes)


def test_le_releve_refuse_une_liste_vide():
    with pytest.raises(RuntimeError, match="plan de site"):
        sharp._exiger([])


def test_une_donnee_qui_manque_legitimement_ne_bloque_pas_tout():
    """Le seuil est à la moitié, et c'est voulu : de vieilles fiches n'ont
    réellement ni poids ni prix conseillé. Un seuil strict ferait échouer un
    relevé parfaitement bon sur une absence légitime."""
    bonnes = [sharp.Fiche(slug=f"x{i}", modele="M", etoiles=4, poids_g=1500)
              for i in range(18)]
    bonnes += [sharp.Fiche(slug="vieux1", modele="V"), sharp.Fiche(slug="vieux2", modele="V")]
    sharp._exiger(bonnes)      # ne doit rien lever


# --- la liste des fiches ------------------------------------------------------

def test_la_page_de_liste_n_est_pas_prise_pour_un_casque():
    """Le plan de site s'ouvre sur `/helmets/`, qui est la page de liste. Relevée
    comme une fiche, elle aurait ajouté un casque sans marque ni modèle."""
    class FauxClient:
        def get(self, url):
            class R:
                text = ("<urlset><url><loc>https://sharp.dft.gov.uk/helmets/</loc></url>"
                        "<url><loc>https://sharp.dft.gov.uk/helmets/agv-k7/</loc></url>"
                        "</urlset>")
            return R()

    assert sharp.adresses(FauxClient()) == ["https://sharp.dft.gov.uk/helmets/agv-k7/"]
