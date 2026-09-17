"""Turn a price history into the geometry of a readable chart.

Why this is Python and not template arithmetic: a chart is only honest if its
axes are, and axes need decisions — where to put the ticks, how many, whether
the scale starts at zero. Those decisions belong somewhere they can be tested,
not inside a `{% for %}`.

Two of them are worth stating, because they change what the reader concludes:

1. **The scale does not start at zero.** A helmet that went from 523,57 € to
   523,40 € would be a flat line on a 0-based axis, and a flat line says "the
   price never moves" — which is the opposite of what this chart exists to
   show. It is framed on the range actually observed, and the axis labels say
   so at every tick, so nobody reads a 20-pixel rise as a collapse.

2. **A single observed price gets a flat line, not a chart.** With one value
   there is no variation to draw; the caller shows a sentence instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Tick:
    pos: float          # x or y in SVG units
    label: str


@dataclass(frozen=True)
class Graphique:
    largeur: int
    hauteur: int
    ligne: str                       # the "d" of the price path
    aire: str                        # the same path closed under the baseline
    ticks_y: list[Tick] = field(default_factory=list)
    ticks_x: list[Tick] = field(default_factory=list)
    dernier: tuple[float, float] = (0.0, 0.0)
    prix_min: float = 0.0
    prix_max: float = 0.0
    plat: bool = False               # the price never moved over the period
    # Les repères de dessin, exposés plutôt que recopiés dans le gabarit : ils
    # dépendent des marges ci-dessous, et deux valeurs recopiées à la main se
    # désaccordent en silence le jour où une marge change.
    fin_grille: float = 0.0          # où s'arrête une ligne de grille
    x_prix: float = 0.0              # où s'écrit une étiquette de prix
    y_dates: float = 0.0             # la ligne des dates


# Room for the labels: an axis label drawn outside the viewBox is an axis label
# nobody reads. These are the margins the drawing area is inset by.
_MARGE_G = 6      # left: the price labels sit inside, against the grid
_MARGE_D = 66     # right: where the price labels are written
# 66 et non 56 : « 1 234,50 € » à 11,5 px mesure environ 55 px, et une
# étiquette de quatre chiffres ancrée à gauche sortait du cadre. Elle est
# désormais ancrée à DROITE, contre le bord, et la grille s'arrête avant.
_MARGE_H = 14
_MARGE_B = 26     # bottom: the dates

# La hauteur d'un historique immobile. 96 laisse la place aux marges haute et
# basse plus une ligne au milieu, et rien de plus : il n'y a rien à montrer
# qu'un trait et son prix.
_HAUTEUR_PLATE = 96


def _jolis_paliers(bas: float, haut: float, combien: int = 4) -> list[float]:
    """Tick values a human would have chosen: 1, 2, 2.5 or 5 times a power of 10.

    A raw `(max-min)/4` gives labels like « 523,5714 € » — technically right and
    unreadable. The classic trick is to round the STEP, not the labels.
    """
    if haut <= bas:
        return [bas]
    brut = (haut - bas) / max(combien, 1)
    magnitude = 10 ** _floor_log10(brut)
    for facteur in (1, 2, 2.5, 5, 10):
        pas = facteur * magnitude
        if pas >= brut:
            break
    depart = (int(bas / pas)) * pas
    if depart < bas:
        depart += pas
    paliers: list[float] = []
    v = depart
    while v <= haut + pas * 0.001 and len(paliers) < 8:
        paliers.append(round(v, 6))
        v += pas
    return paliers or [bas, haut]


def _floor_log10(x: float) -> int:
    n = 0
    if x <= 0:
        return 0
    while x < 1:
        x *= 10
        n -= 1
    while x >= 10:
        x /= 10
        n += 1
    return n


def _euros(v: float) -> str:
    """« 1 234,50 € », espace insécable compris."""
    entier, _, dec = f"{v:,.2f}".replace(",", " ").replace(".", ",").partition(",")
    return f"{entier},{dec} €"


def _jour(d: Any) -> str:
    if isinstance(d, date):
        return f"{d.day:02d}/{d.month:02d}"
    return str(d)[-5:]


def graphique(points: list[dict[str, Any]], largeur: int = 720,
              hauteur: int = 220) -> Graphique | None:
    """Geometry for the price chart, or None when there is nothing to draw."""
    valeurs = [(p["observed_on"], float(p["price"])) for p in points
               if p.get("price") is not None]
    if len(valeurs) < 2:
        return None

    prix = [v for _, v in valeurs]
    bas, haut = min(prix), max(prix)
    plat = haut - bas < 0.005

    # A flat history still deserves its line — drawn through the middle, with
    # the single price written on the axis. Inventing a range would draw noise.
    #
    # Mais un prix immobile n'a pas besoin de 220 px de haut : la boîte se
    # réduit. Signalé par la propriétaire le 14/09/2026, capture à l'appui —
    # une ligne plate au milieu d'un grand cadre, la moitié basse remplie de
    # gris, la moitié haute vide. Le remplissage est d'ailleurs supprimé plus
    # bas : sous une ligne plate, un aplat ne dit rien qu'on ne lise déjà.
    if plat:
        bas, haut = bas - 1, haut + 1
        hauteur = _HAUTEUR_PLATE

    x0, x1 = _MARGE_G, largeur - _MARGE_D
    y0, y1 = _MARGE_H, hauteur - _MARGE_B
    n = len(valeurs) - 1

    def sx(i: int) -> float:
        return round(x0 + (x1 - x0) * i / n, 2)

    def sy(v: float) -> float:
        return round(y1 - (y1 - y0) * (v - bas) / (haut - bas), 2)

    pts = [(sx(i), sy(v)) for i, (_, v) in enumerate(valeurs)]
    ligne = "M " + " L ".join(f"{x} {y}" for x, y in pts)
    # Pas d'aire sous une ligne plate : elle remplirait la moitié du cadre d'un
    # gris qui n'apprend rien. Le gabarit ne dessine le chemin que s'il existe.
    aire = "" if plat else f"{ligne} L {pts[-1][0]} {y1} L {pts[0][0]} {y1} Z"

    ticks_y = [Tick(sy(v), _euros(v))
               for v in (_jolis_paliers(bas, haut) if not plat else [prix[0]])]

    # Dates: first, last, and the middle one when there is room. More than three
    # on a 720-wide chart and they collide.
    idx = [0, n] if n < 3 else [0, n // 2, n]
    ticks_x = [Tick(sx(i), _jour(valeurs[i][0])) for i in sorted(set(idx))]

    return Graphique(
        largeur=largeur, hauteur=hauteur, ligne=ligne, aire=aire,
        ticks_y=ticks_y, ticks_x=ticks_x, dernier=pts[-1],
        prix_min=min(prix), prix_max=max(prix), plat=plat,
        fin_grille=x1, x_prix=largeur - 4, y_dates=hauteur - 8,
    )
