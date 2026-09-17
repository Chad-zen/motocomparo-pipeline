"""The price chart's geometry — the part a reader draws conclusions from."""

from datetime import date

from mcsite.courbe import _euros, _jolis_paliers, graphique


def _pts(*couples):
    return [{"observed_on": d, "price": p} for d, p in couples]


# --- quand il n'y a rien à dessiner -------------------------------------------

def test_un_seul_releve_ne_fait_pas_une_courbe():
    assert graphique(_pts((date(2026, 9, 13), 120))) is None


def test_aucun_releve():
    assert graphique([]) is None


def test_les_prix_absents_ne_comptent_pas():
    pts = _pts((date(2026, 9, 12), 120)) + [{"observed_on": date(2026, 9, 13), "price": None}]
    assert graphique(pts) is None


# --- l'échelle ----------------------------------------------------------------

def test_le_trace_reste_dans_le_cadre():
    g = graphique(_pts((date(2026, 9, 10), 100), (date(2026, 9, 11), 180),
                       (date(2026, 9, 12), 140)), largeur=720, hauteur=220)
    xs = [float(m.split()[0]) for m in g.ligne.replace("M ", "").split(" L ")]
    ys = [float(m.split()[1]) for m in g.ligne.replace("M ", "").split(" L ")]
    assert min(xs) >= 0 and max(xs) <= 720
    assert min(ys) >= 0 and max(ys) <= 220
    # et il laisse la place aux étiquettes de prix, à droite
    assert max(xs) <= 720 - 40


def test_le_plus_cher_est_en_haut():
    g = graphique(_pts((date(2026, 9, 10), 100), (date(2026, 9, 11), 200)))
    ys = [float(m.split()[1]) for m in g.ligne.replace("M ", "").split(" L ")]
    assert ys[1] < ys[0]        # en SVG, y augmente vers le bas


def test_chaque_palier_est_dans_la_plage_observee():
    g = graphique(_pts((date(2026, 9, 10), 100), (date(2026, 9, 11), 180)))
    assert g.ticks_y
    for t in g.ticks_y:
        assert 0 <= t.pos <= 220


def test_un_prix_immobile_donne_une_ligne_plate_et_une_seule_etiquette():
    """Sur une échelle partant de zéro, 523,57 → 523,40 serait plat ; ici c'est
    l'inverse qu'il faut éviter — inventer une variation qui n'existe pas."""
    g = graphique(_pts((date(2026, 9, 12), 523.57), (date(2026, 9, 13), 523.57)))
    assert g.plat is True
    assert len(g.ticks_y) == 1
    ys = [float(m.split()[1]) for m in g.ligne.replace("M ", "").split(" L ")]
    assert ys[0] == ys[1]


# --- les étiquettes -----------------------------------------------------------

def test_les_paliers_sont_des_nombres_lisibles():
    """Le pas est arrondi, pas les étiquettes : sinon on lit « 523,5714 € »."""
    paliers = _jolis_paliers(100, 180, 4)
    assert all(abs(p / 20 - round(p / 20)) < 1e-9 for p in paliers), paliers


def test_les_paliers_ne_sortent_jamais_de_la_plage():
    paliers = _jolis_paliers(517.3, 524.9, 4)
    assert min(paliers) >= 517.3 and max(paliers) <= 524.9


def test_trois_dates_au_maximum():
    pts = _pts(*[(date(2026, 6, 1 + i), 100 + i) for i in range(25)])
    assert len(graphique(pts).ticks_x) <= 3


def test_deux_points_donnent_deux_dates():
    g = graphique(_pts((date(2026, 9, 12), 100), (date(2026, 9, 13), 110)))
    assert [t.label for t in g.ticks_x] == ["12/09", "13/09"]


def test_le_format_des_euros_est_francais():
    assert _euros(1234.5) == "1 234,50 €"
    assert _euros(9.9) == "9,90 €"


# --- l'aire -------------------------------------------------------------------

def test_l_aire_est_fermee_sous_la_courbe():
    g = graphique(_pts((date(2026, 9, 10), 100), (date(2026, 9, 11), 180)))
    assert g.aire.startswith("M ") and g.aire.endswith(" Z")


def test_le_dernier_point_est_celui_du_trace():
    g = graphique(_pts((date(2026, 9, 10), 100), (date(2026, 9, 11), 180)))
    fin = g.ligne.split(" L ")[-1].split()
    assert g.dernier == (float(fin[0]), float(fin[1]))


def test_une_etiquette_de_prix_a_quatre_chiffres_reste_dans_le_cadre():
    """Ancrée à droite contre le bord : « 1 000,00 € » sortait du viewBox."""
    g = graphique(_pts((date(2026, 9, 10), 429.95), (date(2026, 9, 11), 1299.95)),
                  largeur=720)
    assert g.x_prix <= 720
    # la grille s'arrête avant la zone des étiquettes
    assert g.fin_grille < g.x_prix - 40


def test_un_historique_immobile_tient_dans_une_boite_courte():
    """Un prix qui n'a pas bougé n'a pas besoin de 220 px de haut.

    Signalé par la propriétaire le 14/09/2026 : une ligne plate au milieu d'un
    grand cadre, la moitié basse remplie de gris, la moitié haute vide. Un aplat
    qui ne raconte rien est pire que pas de graphique.
    """
    from datetime import date

    pts = [{"observed_on": date(2026, 9, 12), "price": 523.57},
           {"observed_on": date(2026, 9, 13), "price": 523.57},
           {"observed_on": date(2026, 9, 14), "price": 523.57}]
    g = graphique(pts)
    assert g is not None
    assert g.plat is True
    assert g.hauteur < 120, "la boîte doit se réduire quand le prix est immobile"
    assert g.aire == "", "pas d'aplat sous une ligne plate"
    # la ligne reste au milieu de sa boîte, pas collée à un bord
    y = float(g.ligne.split()[2])
    assert abs(y - g.hauteur / 2) < g.hauteur * 0.15


def test_un_historique_qui_bouge_garde_son_aire_et_sa_hauteur():
    from datetime import date

    pts = [{"observed_on": date(2026, 9, 12), "price": 500.0},
           {"observed_on": date(2026, 9, 13), "price": 540.0},
           {"observed_on": date(2026, 9, 14), "price": 520.0}]
    g = graphique(pts)
    assert g is not None and g.plat is False
    assert g.hauteur == 220
    assert g.aire.endswith("Z")
