"""Le titre, la description et le court texte d'ouverture des rayons et marques.

Audit du 16/10/2026 : les pages rayons s'appelaient « Casques — MotoComparo »
(21 caractères) avec une description de 75 caractères et aucun texte. Ce sont
pourtant elles qui doivent répondre à « casque moto pas cher » ou « gants moto
hiver » : un titre qui ne dit ni « moto » ni « prix » ne se place sur rien.

RÈGLE D'ÉCRITURE : rien qu'on ne puisse vérifier. Pas de « les meilleurs
prix du web », pas de norme citée de mémoire ; le nombre de produits et de
marchands est calculé, le reste décrit ce que le rayon contient.
"""

from __future__ import annotations

from typing import Any

# code -> (nom pour le titre, phrase d'ouverture). Le nom porte « moto » quand
# le libellé du rayon ne le dit pas : « Casques » seul est aussi un casque de vélo.
_RAYONS: dict[str, tuple[str, str]] = {
    "helmet": ("Casques moto",
               "Casques intégraux, jet, modulables et cross"),
    "helmet.integral": ("Casques moto intégraux",
                        "Casques intégraux, mentonnière fixe, pour la route, le sport et le quotidien"),
    "helmet.jet": ("Casques moto jet",
                   "Casques jet, ouverts sur le bas du visage, pour la ville et les trajets courts"),
    "helmet.modular": ("Casques moto modulables",
                       "Casques modulables à mentonnière relevable, pour la route et les longs trajets"),
    "helmet.cross": ("Casques moto cross",
                     "Casques cross et enduro, à visière et à porter avec un masque"),
    "helmet.accessory": ("Écrans et pièces de casque moto",
                         "Écrans, Pinlock, mousses, intercoms et pièces détachées de casque"),
    "jacket": ("Blousons et vestes moto",
               "Blousons et vestes moto en cuir, textile ou denim, été, mi-saison et hiver"),
    "gloves": ("Gants moto",
               "Gants moto été, mi-saison, hiver et chauffants, en cuir ou textile"),
    "pants": ("Pantalons et jeans moto",
              "Pantalons moto, jeans renforcés et surpantalons"),
    "boots": ("Bottes et chaussures moto",
              "Bottes, bottines et baskets moto, route, sport et tout-terrain"),
    "suit": ("Combinaisons moto",
             "Combinaisons cuir, textile et de pluie"),
    "protection": ("Protections moto",
                   "Dorsales, airbags, genouillères et protections de la moto"),
    "protection.pilote": ("Protections du motard",
                          "Dorsales, gilets airbag, plastrons, genouillères et coudières"),
    "protection.moto": ("Protections de la moto",
                        "Protège-carters, tampons de protection, crash bars et protections de réservoir"),
    "goggles": ("Masques et lunettes moto",
                "Masques cross, lunettes et écrans de masque"),
    "jersey": ("Maillots moto cross",
               "Maillots cross et enduro"),
    "luggage": ("Bagagerie moto",
                "Sacoches, sacs de réservoir, top cases et supports"),
    "exhaust": ("Échappements moto",
                "Silencieux, lignes complètes et accessoires d'échappement"),
    "bodywork": ("Carénage et carrosserie moto",
                 "Bulles, garde-boue, rétroviseurs et pièces de carrosserie"),
    "transmission": ("Transmission moto",
                     "Kits chaîne, pignons, couronnes et chaînes"),
    "electronics": ("Électronique moto",
                    "Intercoms, supports de téléphone, prises et éclairage"),
    "brakes": ("Freinage moto",
               "Plaquettes, disques, durites et liquide de frein"),
    "tyres": ("Pneus moto", "Pneus moto route, sport, trail et tout-terrain"),
    "engine": ("Pièces moteur moto", "Filtres, bougies, joints et pièces moteur"),
    "suspension": ("Suspensions moto", "Amortisseurs, ressorts et pièces de fourche"),
    "seat": ("Selles moto", "Selles et housses de selle"),
    "maintenance": ("Entretien moto",
                    "Huiles, nettoyants, lubrifiants de chaîne et outillage"),
    "accessories": ("Accessoires moto", "Accessoires pour la moto et le motard"),
    "apparel_casual": ("Vêtements casual moto", "Sweats, t-shirts, casquettes et vêtements de tous les jours"),
}


def _nombre(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def rayon(code: str, libelle: str, total: int, marchands: int) -> dict[str, Any]:
    nom, phrase = _RAYONS.get(code, (libelle, libelle))
    return {
        "titre": f"{nom} : comparez les prix chez {marchands} marchands",
        "description": (f"{phrase} : {_nombre(total)} produits comparés chez "
                        f"{marchands} marchands, prix relevés chaque jour. "
                        "Trouvez le moins cher, taille par taille."),
        "intro": (f"{phrase}. {_nombre(total)} produits comparés entre "
                  f"{marchands} marchands, prix mis à jour chaque jour : "
                  "choisissez votre taille, le site affiche qui la vend le "
                  "moins cher."),
    }


def marque(nom: str, total: int, marchands: int,
           rayons: list[str]) -> dict[str, Any]:
    # Les trois rayons les plus fournis de la marque, lus en base : « casques,
    # gants et blousons » dit davantage qu'un nom de marque seul.
    liste = [r.lower() for r in rayons[:3]]
    rayons_txt = (", ".join(liste[:-1]) + " et " + liste[-1]) if len(liste) > 1 else (liste[0] if liste else "")
    return {
        "titre": f"{nom} : prix comparés chez {marchands} marchands",
        "description": (f"{_nombre(total)} produits {nom} comparés chez {marchands} "
                        f"marchands{(' : ' + rayons_txt) if rayons_txt else ''}. "
                        "Prix relevés chaque jour, le moins cher pour chaque taille."),
        "intro": (f"{_nombre(total)} produits {nom} comparés chez {marchands} marchands"
                  f"{(', surtout en ' + rayons_txt) if rayons_txt else ''}. "
                  "Les prix sont relevés chaque jour."),
    }
