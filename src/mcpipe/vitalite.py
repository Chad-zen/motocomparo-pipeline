"""Un flux marchand est-il vivant, ou seulement ponctuel ?

POURQUOI CE FICHIER EXISTE. Le 18/09/2026, on a découvert qu'un marchand
servait depuis huit jours un fichier rigoureusement identique — même taille à
l'octet, mêmes prix, mêmes produits — pendant que sa plateforme d'affiliation
le régénérait consciencieusement chaque nuit et que notre chaîne le
retéléchargeait intégralement, 170 Mo sur le fil.

Rien n'avait signalé quoi que ce soit. Aucune exception, aucun avertissement,
aucune ligne rouge dans les journaux. Le téléchargement disait « ok », le
chargement disait « ok », et le site affichait des prix vieux de huit jours
avec le même aplomb que les autres.

C'est le défaut le plus coûteux d'un comparateur : il ne casse rien, il ne
lève rien, et il détruit la seule chose qui fasse la valeur du site. Il a été
trouvé parce que la propriétaire a cliqué sur un lien mort, pas parce qu'on
l'avait vu venir.

CE QU'ON MESURE, ET POURQUOI PAS LE PRIX
========================================
Le réflexe serait de surveiller les prix. C'est insuffisant : un marchand peut
très bien ne changer aucun prix pendant une semaine calme, et ce serait normal.

Le signal qui ne trompe pas, c'est le MOUVEMENT DU CATALOGUE — des références
qui entrent, des références qui sortent. Un catalogue de plusieurs dizaines de
milliers d'articles en a tous les jours : une rupture, un réassort, une fin de
série. Mesuré le 18/09 sur les six marchands :

    motoblouz    308 853 offres    3 401 retirées    7 561 entrées
    fcmoto       151 386             4 760           3 879
    speedway      61 731             2 647           3 068
    motoaxxe      17 177               109              85
    maxxess       16 169                93              80
    labecanerie  222 927                 0               0   <- le mort

Même les deux plus petits marchands bougent de quatre-vingts références. Zéro
entrée ET zéro sortie sur 222 927 offres, c'est arithmétiquement impossible
pour un catalogue vivant.

On regarde donc trois choses ensemble, et c'est leur CONJONCTION qui accuse :
aucune arrivée, aucun retrait, aucun prix modifié. Un seul de ces trois à zéro
ne prouve rien.
"""

from __future__ import annotations

from dataclasses import dataclass

from .db import connect

# Combien de jours sans le moindre mouvement avant de s'alarmer.
#
# Trois, et pas un. Deux serait trop court : un flux peut sauter une nuit sur
# un incident réseau chez la plateforme, et deux relevés identiques ne sont
# alors qu'un relevé manqué. Sept serait trop long — c'est déjà une semaine de
# prix faux servis aux visiteurs.
JOURS_AVANT_ALERTE = 3


@dataclass
class Vitalite:
    code: str
    offres: int
    retirees: int
    arrivees: int
    prix_changes: int
    dernier_mouvement: str | None
    affiche: bool

    @property
    def fige(self) -> bool:
        """Les trois à zéro. Un seul ne veut rien dire."""
        return self.retirees == 0 and self.arrivees == 0 and self.prix_changes == 0


_SQL = """
WITH mouvement AS (
    SELECT o.merchant_id,
           count(*)                                                  AS offres,
           count(*) FILTER (WHERE NOT o.is_live)                      AS retirees,
           count(*) FILTER (WHERE o.first_seen >= now() - %(f)s::interval) AS arrivees,
           max(o.first_seen)::date                                    AS derniere_arrivee
    FROM raw_offer o
    GROUP BY o.merchant_id
),
-- Les prix qui ont bougé entre les DEUX DERNIERS relevés disponibles, et non
-- entre aujourd'hui et une date fixe : l'historique a des trous — les 15 et 16
-- septembre n'ont rien collecté — et une fenêtre en dur compterait ces trous
-- comme des immobilités.
bornes AS (
    SELECT max(observed_on) AS fin,
           max(observed_on) FILTER (
               WHERE observed_on < (SELECT max(observed_on) FROM price_history)
           ) AS debut
    FROM price_history
),
changes AS (
    SELECT o.merchant_id, count(*) AS prix_changes
    FROM bornes b
    JOIN price_history a ON a.observed_on = b.debut
    JOIN price_history z ON z.observed_on = b.fin AND z.raw_offer_id = a.raw_offer_id
    JOIN raw_offer o ON o.id = a.raw_offer_id
    WHERE a.price IS DISTINCT FROM z.price
    GROUP BY o.merchant_id
)
SELECT m.code, m.affiche,
       mo.offres, mo.retirees, mo.arrivees,
       coalesce(c.prix_changes, 0) AS prix_changes,
       mo.derniere_arrivee::text
FROM merchant m
JOIN mouvement mo ON mo.merchant_id = m.id
LEFT JOIN changes c ON c.merchant_id = m.id
ORDER BY (mo.retirees + mo.arrivees + coalesce(c.prix_changes, 0))
"""


def mesurer(jours: int = JOURS_AVANT_ALERTE) -> list[Vitalite]:
    """L'état de chaque flux, du plus figé au plus vivant."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(_SQL, {"f": f"{jours} days"})
            return [Vitalite(code=r[0], affiche=r[1], offres=r[2], retirees=r[3],
                             arrivees=r[4], prix_changes=r[5], dernier_mouvement=r[6])
                    for r in cur.fetchall()]
    finally:
        conn.close()
