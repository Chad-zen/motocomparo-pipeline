"""Ce qu'on peut dire d'un casque, à partir des flux qu'on reçoit déjà.

POURQUOI CE FICHIER EXISTE. La propriétaire veut un configurateur d'équipement
— budget, usage, et on propose un panier. Un configurateur a besoin de
caractéristiques, et le catalogue n'en portait aucune : un titre, une marque,
une couleur, une taille, un prix. Rien sur ce qui fait la différence entre deux
casques à 200 € d'écart.

CE QU'ON A MESURÉ AVANT D'ÉCRIRE (18/09/2026), et c'est ce qui décide tout :

    source        casques   description médiane
    motoblouz      22 819        1 049 signes
    fcmoto         22 727          157 signes
    labecanerie    21 343          127 signes

Motoblouz écrit huit fois plus que les autres, et c'est la seule source qui
tienne. Taux de mention DANS ses descriptions :

    boucle 89 %      ventilation 83 %      calotte 83 %      Pinlock 56 %
    écran solaire 50 %   intercom 39 %   poids 34 %   homologation ECE 26 %
    intérieur amovible 21 %

Et la couverture par FICHE, une fois les offres fusionnées :

    3 132 fiches casque à deux marchands ou plus
    2 720 (87 pour cent) sont vendues par Motoblouz
    3 076 (98 pour cent) par Motoblouz OU FC-Moto

C'est donc jouable. La propriétaire soupçonnait une source pauvre : elle l'est
pour La Bécanerie, elle ne l'est pas pour les casques pris chez Motoblouz.

CE QU'ON NE TROUVERA PAS ICI, et il faut le dire une fois pour toutes : aucun
flux ne porte de note SHARP, de mesure de bruit, ni de résultat de test
indépendant. Si le configurateur doit un jour les afficher, ça viendra
d'ailleurs.

LA RÈGLE QUI GOUVERNE TOUT LE FICHIER
=====================================
En cas de doute, on rend `None`. Annoncer qu'un casque est homologué ECE 22.06
quand il ne l'est pas n'est pas une imprécision de comparateur : c'est une
information de sécurité fausse. Une caractéristique absente coûte un filtre
moins précis ; une caractéristique fausse coûte la confiance, et peut-être
davantage.

C'est la même règle que `borrow_sizes()` applique aux tailles, pour la même
raison — sauf qu'ici l'enjeu n'est plus le confort.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- les pièges de formulation ------------------------------------------------
#
# Les trois quarts du travail sont là. Un marchand écrit « prééquipé pour
# intercom » et « intercom intégré » dans la même phrase de vente, et seul le
# second veut dire que le boîtier est dans la boîte. Chaque motif de PRÉPARATION
# est donc testé AVANT son motif de présence, et il gagne.
# Liste etablie EN LISANT les descriptions, pas de memoire. La premiere
# version ratait « PREDISPOSE », le mot le plus employe du rayon :
# l'extracteur annoncait « intercom fourni » sur cinq casques sur cinq alors
# que les cinq disaient « predispose a recevoir ». Elle ratait aussi
# « pret POUR », n'ayant prevu que « pret A ».
#
# Une garde qui ne connait pas le vocabulaire qu'elle doit arreter ne garde
# rien, et elle le fait en silence : la couverture monte, et c'est justement
# ce qui rassure a tort.
_PREPARE = (r"(?:pr[ée]dispos|pr[ée]{1,2}quip|pr[ée]par|compatible|"
            r"pr[êe]t (?:[àa]|pour)|ready|adapt[ée] (?:pour|[àa])|"
            r"peut recevoir|possibilit[ée] d|en option|non fourni|"
            r"n[ée]cessite|[àa] commander|vendu s[ée]par)"
)

# --- homologation -------------------------------------------------------------
#
# ECE 22.06 remplace 22.05 depuis 2024. Les deux coexistent en rayon, et l'écart
# compte pour l'acheteur : un 22.05 ne sera plus fabriqué. Les marchands
# l'écrivent de six façons — « ECE 22.06 », « ECE R22-06 », « 22-06 »,
# « ECE22.06 », « norme 22.06 », « ECE 22/06 ».
_ECE = re.compile(r"ECE[\s.\-/]?R?[\s.\-/]?22[\s.\-/]?0?([56])\b|(?<![\d.])22[\s.\-/]0([56])\b", re.I)

# --- calotte ------------------------------------------------------------------
#
# Ce qui fait le prix ET le poids. L'ordre compte : « fibre de carbone » doit
# être lu comme carbone, pas comme fibre de verre, donc carbone passe en premier.
# « thermoplastique » N'EST PAS « polycarbonate », et les confondre etait une
# sur-affirmation. Le polycarbonate est un thermoplastique parmi d'autres ;
# beaucoup de casques annoncent une « resine thermoplastique » ou un melange
# maison — l'ADT de KYT et de Suomy — qui n'en est pas. Trois cas sur sept de
# l'echantillon etaient dans ce cas.
#
# On rend donc ce que le texte dit, et rien de plus : « thermoplastique »
# devient une valeur en soi. Elle est moins precise, elle est vraie.
_CALOTTE = [
    ("carbone",         r"(?:fibre de )?carbone?\b|carbon fib|full.?carbon"),
    ("composite",       r"tri.?composite|multi.?composite|composite|fibre[s]? compos"),
    ("fibre",           r"fibre de verre|fiberglass|fibre[s]? organique"),
    ("polycarbonate",   r"polycarbonate|\bPC ?/ ?ABS\b|\bABS\b"),
    ("thermoplastique", r"thermoplastique|thermoplastic|injection thermo"),
]


# --- boucle -------------------------------------------------------------------
_BOUCLE = [
    ("double-D",      r"double[\s.\-]?d\b|d[\s.\-]?ring|anneaux? en d"),
    ("micrométrique", r"micro.?m[ée]trique|ratchet|cr[ée]maill[èe]re|quick.?release"),
]

# --- le reste -----------------------------------------------------------------
_PINLOCK = r"pinlock"
_SOLAIRE = r"[ée]cran solaire|pare.?soleil|sun.?visor|visi[èe]re solaire|[ée]cran interne"
_INTERCOM = r"intercom|bluetooth|kit main.?libres?|\bSENA\b|\bCardo\b|syst[èe]me de communication"
_AMOVIBLE = r"int[ée]rieur[^.]{0,30}(?:amovible|d[ée]montable|lavable)|coiffe[^.]{0,20}amovible|mousses? amovibles?"
_VENTIL = r"ventilation|a[ée]ration|extracteur|entr[ée]e[s]? d.air|prises? d.air"

# Le poids : on exige l'unité ET un ordre de grandeur crédible. Un casque pèse
# entre 900 et 2 000 g ; « 1 200 » seul dans une phrase peut être une référence,
# une contenance ou une cylindrée.
_POIDS = re.compile(r"(\d{3,4})\s?(?:g|gr|grammes)\b", re.I)


@dataclass
class Casque:
    """Ce qu'on a su lire. `None` partout où on n'a pas su — jamais une valeur
    par défaut, qui se confondrait avec une mesure."""

    homologation: str | None = None       # '22.06' ou '22.05'
    calotte: str | None = None
    poids_g: int | None = None
    pinlock: str | None = None            # 'fourni' ou 'prepare'
    ecran_solaire: bool | None = None
    ventilation: bool | None = None
    interieur_amovible: bool | None = None
    intercom: str | None = None           # 'integre' ou 'prepare'
    boucle: str | None = None
    sources: list[str] = field(default_factory=list)

    def renseignees(self) -> int:
        return sum(1 for v in (self.homologation, self.calotte, self.poids_g,
                               self.pinlock, self.ecran_solaire, self.ventilation,
                               self.interieur_amovible, self.intercom, self.boucle)
                   if v is not None)


# Un casque porte DEUX pièces en plastique, et les marchands parlent des deux
# dans le même paragraphe : la calotte et l'écran. « Visière en polycarbonate »
# est vrai de presque tous les casques du marché, y compris ceux dont la coque
# est en carbone.
#
# Trouvé en relisant l'échantillon : un KYT R2R dont la coque est en ADT était
# annoncé « polycarbonate », sur la foi de sa visière. La couverture ne montre
# jamais ce genre d'erreur — elle la compte comme un succès.
_PIECE_QUI_N_EST_PAS_LA_CALOTTE = r"(?:visi[èe]re|[ée]cran|bulle|mentonni[èe]re)"


def _calotte(t: str) -> str | None:
    """La matière de la COQUE, et d'elle seule.

    On écarte une occurrence dont les quarante signes précédents parlent de
    l'écran. Quarante, comme pour `_prepare_ou_fourni` : « Visière en
    polycarbonate, résistante aux rayures » tient dedans.
    """
    for nom, motif in _CALOTTE:
        for m in re.finditer(motif, t, re.I):
            avant = t[max(0, m.start() - 40):m.start()]
            if re.search(_PIECE_QUI_N_EST_PAS_LA_CALOTTE, avant, re.I):
                continue          # c'est l'ecran, on passe a l'occurrence suivante
            return nom
    return None


def _prepare_ou_fourni(texte: str, motif: str) -> str | None:
    """« prééquipé pour » n'est pas « fourni », et c'est LE piège du rayon.

    On cherche le mot dans sa phrase, puis on regarde les quarante signes qui
    le précèdent. Quarante parce que « prééquipé pour recevoir un système
    d'intercom » tient dedans, et qu'au-delà on attrape la phrase d'avant, qui
    parle d'autre chose.
    """
    m = re.search(motif, texte, re.I)
    if not m:
        return None
    avant = texte[max(0, m.start() - 40):m.start()]
    return "prepare" if re.search(_PREPARE, avant, re.I) else "fourni"


def lire(titre: str, description: str) -> Casque:
    """Lit un casque dans le texte d'un marchand.

    Le titre est concaténé à la description : les marchands mettent parfois
    l'homologation dans le titre et rien dans le texte.
    """
    t = " ".join(((titre or "") + " " + (description or "")).split())
    c = Casque()
    if not t:
        return c

    m = _ECE.search(t)
    if m:
        c.homologation = "22.0" + (m.group(1) or m.group(2))

    c.calotte = _calotte(t)

    for nom, motif in _BOUCLE:
        if re.search(motif, t, re.I):
            c.boucle = nom
            break

    # On prend le poids le plus PROBABLE, pas le premier venu : une description
    # cite parfois le poids de l'écran ou de l'emballage. Entre 900 et 2000 g,
    # c'est un casque ; en dehors, c'est autre chose.
    poids = [int(g) for g in _POIDS.findall(t) if 900 <= int(g) <= 2000]
    if poids:
        c.poids_g = min(poids)

    c.pinlock = _prepare_ou_fourni(t, _PINLOCK)
    c.intercom = _prepare_ou_fourni(t, _INTERCOM)

    # Ces trois-là n'ont pas de version « préparée » : un casque a des aérations
    # ou n'en a pas. On rend donc True, ou None — jamais False, qui prétendrait
    # que le texte AFFIRME l'absence. Il ne l'affirme jamais ; il se tait.
    if re.search(_VENTIL, t, re.I):
        c.ventilation = True
    if re.search(_SOLAIRE, t, re.I):
        c.ecran_solaire = True
    if re.search(_AMOVIBLE, t, re.I):
        c.interieur_amovible = True

    return c


def fusionner(lectures: list[Casque]) -> Casque:
    """Une fiche, plusieurs marchands : on réunit ce que chacun a su dire.

    La première valeur trouvée gagne, et l'ordre d'appel fait la priorité —
    l'appelant passe Motoblouz en premier, parce que c'est lui qui écrit. Sur
    un désaccord franc d'homologation entre deux marchands, on ABANDONNE la
    valeur : deux sources qui se contredisent sur une donnée de sécurité ne
    valent pas mieux qu'aucune source.
    """
    out = Casque()
    homologations = {l.homologation for l in lectures if l.homologation}
    for l in lectures:
        for champ in ("calotte", "poids_g", "pinlock", "ecran_solaire",
                      "ventilation", "interieur_amovible", "intercom", "boucle"):
            if getattr(out, champ) is None and getattr(l, champ) is not None:
                setattr(out, champ, getattr(l, champ))
    if len(homologations) == 1:
        out.homologation = homologations.pop()
    return out
