"""The 5 merchant feeds: where to get each one, its format, and how its columns
map onto our internal fields.

This is deliberately data, not code. Adding or fixing a merchant should be an edit
here, never a change to the parser.

Three feed platforms:

  * Effinity      — ';'-delimited CSV, rich columns (colour, size, mpn, item_group_id).
                    Merchants: Speedway, La Bécanerie, Maxxess, Moto-Axxe.
  * Netaffiliation — '|'-delimited CSV, sparse (no colour, no size, no item_group_id).
                    Merchant: Motoblouz.
  * Webgains      — ','-delimited CSV, Google Shopping schema, the best-filled feed
                    (colour 90%, size 94%, mpn 99%, item_group_id 94%). Needs a
                    bearer token. Merchant: FC-Moto.

GTIN trust: Speedway / La Bécanerie / Motoblouz emit real, stable barcodes — safe to
join on. Maxxess / Moto-Axxe emit synthetic sequential ids that change every refresh —
`gtin_trust="synthetic"`, never used as a key (see docs/architecture.md).

Header quirks verified against the live feeds (2026-09-10):
  * every header field is wrapped in double quotes — the parser strips them;
  * column matching is case-insensitive (Motoblouz's part-number column is `HAN`);
  * Effinity feeds carry 73 columns, Netaffiliation 20 — we read only the ones below.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class FeedSpec:
    code: str                       # 'speedway', 'labecanerie', ...
    merchant_id: int                # stable id, also the PK in the `merchant` table
    platform: str                   # 'effinity' | 'netaffiliation'
    delimiter: str
    gtin_trust: str                 # 'trusted' | 'synthetic'
    reliability_rank: int           # 1 = most trusted, used to break attribute ties
    # internal field  ->  list of acceptable column names in the feed header
    columns: dict[str, list[str]] = field(default_factory=dict)
    # env var holding a bearer token, when the feed endpoint requires one
    auth_token_env: str | None = None
    # Ne garder, au téléchargement, que les offres déjà connues en base — voir
    # `fetch._filtrer_connues`. Aucune offre nouvelle n'entre tant que c'est vrai.
    connus_seulement: bool = False
    # Flux livre en archive (`zip`) : Awin n'offre que gzip ou zip, jamais « rien ».
    compression: str | None = None
    # Perimetre applique AU TELECHARGEMENT, avant que la moindre ligne n'entre en
    # base — voir `fetch._filtrer_perimetre`. None = tout garder.
    perimetre: str | None = None
    # Colonnes sans lesquelles le flux n'est pas importable. Si l'une manque (un
    # marchand renomme, un utilisateur decoche une case sur la plateforme), on
    # s'arrete plutot que d'importer sans taille ni code-barres.
    colonnes_requises: tuple[str, ...] = ()
    # Le marchand est-il montre sur le site des sa creation en base ? Faux pour un
    # nouveau marchand tant qu'il n'a pas ete valide (`merchant.affiche`, sql/021).
    affiche_au_depart: bool = True
    # Ses offres EN DESACCORD avec celles des autres marchands sur un meme code-barres
    # (marque, rayon, couleur, genre/age, lot, annee) sont ecartees (`rejected`) avant le
    # `match`, au lieu de mettre le code-barres entier en quarantaine — voir
    # `match._ECARTER_DESACCORDS`. Pour un marchand neuf et non eprouve.
    ecarte_desaccords: bool = False

    @property
    def url(self) -> str | None:
        return os.environ.get(f"FEED_{self.code.upper()}_URL") or None

    @property
    def auth_token(self) -> str | None:
        return os.environ.get(self.auth_token_env) if self.auth_token_env else None


_EFFINITY_COLUMNS = {
    "merchant_ref":   ["id"],
    "gtin":           ["gtin"],
    "title":          ["title"],
    "brand":          ["brand"],
    "color":          ["color"],
    "gender":         ["gender"],
    "age_group":      ["age_group"],
    "size":           ["size"],
    "mpn":            ["mpn"],
    "item_group_id":  ["item_group_id"],
    "description":    ["description"],
    "category":       ["category"],
    "category_l2":    ["category_level2"],
    "category_l3":    ["category_level3"],
    "link":           ["link"],
    "image":          ["image_link"],
    "price":          ["price"],
    "currency":       ["currency"],
    "availability":   ["availability"],
    "stock":          ["stock"],
}

_NETAFFILIATION_COLUMNS = {
    "gtin":           ["universal reference"],
    "title":          ["name"],
    "brand":          ["brand"],
    "mpn":            ["HAN"],
    "merchant_ref":   ["internal reference"],
    "category":       ["category"],
    "description":    ["description"],
    "link":           ["product url"],
    "image":          ["image url"],
    "price":          ["price"],
    "crossed_price":  ["crossed price"],
    "availability":   ["availability"],
    "stock":          ["stock"],
}

# Webgains ships a Google-Shopping-style schema (44 columns). `price` is the
# reference price and `sale_price` the promotional one; `normalize` prefers the
# promo when it is lower and in force, because that is what the buyer pays.
# Mapping it was reversed on 2026-09-13: leaving it out quoted the REV'IT
# Stealth 2 at 389.99 when FC-Moto was selling it at 311.99, making the cheapest
# merchant on the page look like the dearest. 45,015 of FC-Moto's offers carry a
# sale price and not one carries an effective-date window.
# merchant_ref falls back mpn -> gtin -> id (the `id` hash's stability is unproven).
_WEBGAINS_COLUMNS = {
    "gtin":           ["gtin"],
    "sale_price":       ["sale_price"],
    "sale_price_window": ["sale_price_effective_date"],
    "title":          ["title"],
    "brand":          ["brand"],
    "color":          ["color"],
    "gender":         ["gender"],
    "age_group":      ["age_group"],
    "size":           ["size"],
    "mpn":            ["mpn"],
    "item_group_id":  ["item_group_id"],
    "merchant_ref":   ["mpn", "gtin", "id"],
    "description":    ["description"],
    "category":       ["product_type", "google_product_category_text"],
    "link":           ["link"],
    "image":          ["image_link"],
    "price":          ["price"],
    "availability":   ["availability"],
}

# Motoin (Webgains, 19/10/2026) : meme schema Google-Shopping que FC-Moto, trois differences MESUREES
# sur les 74 449 lignes du flux (voir tests/test_feeds.py) :
#  * `merchant_ref` = `id` SEUL. `mpn` est partage entre les tailles d'un meme article
#    (293 valeurs sur 1 635 lignes, ex. « 20160002 M » porte cinq tailles) : repli `mpn` puis
#    `gtin` de FC-Moto en ferait UNE offre. `id` est unique sur 74 449 lignes.
#  * `mpn` n'est PAS lu (meme raison que Motard Bleu) : marchand `trusted`, `match._LINK_MPN_PREFIXE`
#    s'en serait servi comme cible.
#  * `category` = `product_category` (« Vetements>Vestes>Vestes en textile », « Habits loisirs>… »),
#    pas `product_type` (« Clothing », « Casual ») qui est trop grossier pour le perimetre.
#  * `sale_price` est un objet JSON PAR PAYS (`{"FR":31.95,"DE":31.95,…}`), egal au prix pour la France
#    sur 74 449 lignes sur 74 449 : lu par `normalize._prix_promo`, jamais comme un montant brut.
_MOTOIN_COLUMNS = {
    "gtin":           ["gtin"],
    "sale_price":     ["sale_price"],
    "title":          ["title"],
    "brand":          ["brand"],
    "color":          ["color"],
    "gender":         ["gender"],
    "age_group":      ["age_group"],
    "size":           ["size"],
    "item_group_id":  ["item_group_id"],
    "merchant_ref":   ["id"],
    "description":    ["description"],
    "category":       ["product_category", "google_product_category_text"],
    "link":           ["link"],
    "image":          ["image_link"],
    "price":          ["price"],
    "availability":   ["availability"],
}

# Awin (Le Motard Bleu, 18/10/2026). Le flux est ce que l'utilisateur coche sur
# « Create-a-Feed » : seules les colonnes cochees existent. La TAILLE n'est pas une
# colonne a part, elle est dans `custom_1` (S, M, L, XL, 2XL... et « TU » pour une
# taille unique), le genre dans `custom_2` (Unisex / Male / Female), l'age dans
# `custom_3` (Adulte / Junior / Baby, rempli a 61 %). `product_GTIN` est VIDE : le
# code-barres est dans `ean`. Le lien tracke est `aw_deep_link` ; `merchant_deep_link`
# ne rapporterait aucune commission. `rrp_price` est un prix conseille, jamais un
# ancien prix : il n'est pas lu, il ne doit jamais s'afficher comme une remise.
# `mpn` n'est PAS lu : 4 806 valeurs sont partagees entre variantes (22 111 lignes),
# dont 149 entre rayons differents (une housse Bagster et un tube Brazoline), et
# Motard Bleu etant `trusted`, `match._LINK_MPN_PREFIXE` s'en serait servi comme cible.
_AWIN_COLUMNS = {
    "merchant_ref":   ["merchant_product_id"],
    "gtin":           ["ean"],
    "title":          ["product_name"],
    "brand":          ["brand_name"],
    "color":          ["colour"],
    "size":           ["custom_1"],
    "gender":         ["custom_2"],
    "age_group":      ["custom_3"],
    "item_group_id":  ["parent_product_id"],
    "description":    ["description"],
    "category":       ["merchant_category"],
    "link":           ["aw_deep_link"],
    "image":          ["merchant_image_url"],
    "price":          ["search_price"],
    "currency":       ["currency"],
    "availability":   ["in_stock"],
}


FEEDS: dict[str, FeedSpec] = {
    "speedway": FeedSpec(
        code="speedway", merchant_id=1, platform="effinity", delimiter=";",
        gtin_trust="trusted", reliability_rank=1, columns=_EFFINITY_COLUMNS,
    ),
    "labecanerie": FeedSpec(
        code="labecanerie", merchant_id=2, platform="effinity", delimiter=";",
        gtin_trust="trusted", reliability_rank=1, columns=_EFFINITY_COLUMNS,
    ),
    "motoblouz": FeedSpec(
        code="motoblouz", merchant_id=3, platform="netaffiliation", delimiter="|",
        gtin_trust="trusted", reliability_rank=2, columns=_NETAFFILIATION_COLUMNS,
    ),
    "maxxess": FeedSpec(
        code="maxxess", merchant_id=4, platform="effinity", delimiter=";",
        gtin_trust="synthetic", reliability_rank=3, columns=_EFFINITY_COLUMNS,
    ),
    "motoaxxe": FeedSpec(
        code="motoaxxe", merchant_id=5, platform="effinity", delimiter=";",
        gtin_trust="synthetic", reliability_rank=3, columns=_EFFINITY_COLUMNS,
    ),
    "fcmoto": FeedSpec(
        code="fcmoto", merchant_id=6, platform="webgains", delimiter=",",
        gtin_trust="trusted", reliability_rank=2, columns=_WEBGAINS_COLUMNS,
        auth_token_env="FEED_FCMOTO_TOKEN",
        # Le 14/10/2026 le flux est passé de 160 000 à 6,8 millions de lignes
        # (7,2 Go) et a rempli le disque du VPS. Décision de la propriétaire :
        # ne mettre à jour que les produits FC-Moto déjà connus. À retirer
        # quand le flux redevient normal — de nouveaux produits entreront alors.
        connus_seulement=True,
    ),
    # Le Motard Bleu : 130 143 lignes, 223 Mo une fois le zip ouvert. On ne charge
    # que l'equipement du pilote (voir `perimetre`) ; les pieces viendront apres, une
    # fois `mcpipe verify` propre. Masque du site tant qu'il n'est pas valide.
    "motardbleu": FeedSpec(
        code="motardbleu", merchant_id=7, platform="awin", delimiter=",",
        gtin_trust="trusted", reliability_rank=3, columns=_AWIN_COLUMNS,
        compression="zip", perimetre="equipement_pilote",
        colonnes_requises=("merchant_product_id", "ean", "product_name", "brand_name",
                           "aw_deep_link", "search_price", "merchant_category", "custom_1"),
        affiche_au_depart=False,
        ecarte_desaccords=True,
    ),
    # Motoin (motoin.de via Webgains) : 74 449 lignes, 280 Mo, 96,5 % de codes-barres tous valides,
    # 71 % deja vendus chez nous, prix a 1,00 de la mediane des autres marchands. Meme perimetre que
    # Motard Bleu (l'equipement du pilote, pas le loisir ni les velos). Masque du site tant qu'il n'est
    # pas valide. TOUT est « in stock » : aucune rupture ne sera jamais detectee par ce flux.
    "motoin": FeedSpec(
        code="motoin", merchant_id=8, platform="webgains", delimiter=",",
        gtin_trust="trusted", reliability_rank=3, columns=_MOTOIN_COLUMNS,
        perimetre="equipement_pilote",
        colonnes_requises=("id", "gtin", "title", "brand", "link", "price", "product_category", "size"),
        affiche_au_depart=False,
        ecarte_desaccords=True,
    ),
}


# LA CLE D'UN FLUX EST UN SECRET (18/10/2026). L'URL du flux Awin porte la cle API
# dans son chemin (`/apikey/<32 caracteres>/`), et `httpx` recopie l'URL entiere dans
# le message de ses erreurs : une coupure reseau l'aurait ecrite dans le journal de
# la chaine de nuit (`07-planification.sh` redirige la sortie vers des fichiers).
# Tout message d'erreur de flux passe par ici avant d'etre affiche ou journalise.
_CLE_AWIN = re.compile(r"(apikey/)[^/\s'\"]+", re.IGNORECASE)
_PARAM_SECRET = re.compile(r"([?&](?:token|key|apikey|api_key|secret)=)[^&\s'\"]+", re.IGNORECASE)


def masquer_secrets(texte: object) -> str:
    """Le texte d'une erreur, sans l'URL d'un flux ni son jeton.

    Remplace les URL et jetons connus de l'environnement (`FEED_*_URL`,
    `FEED_*_TOKEN`) puis les formes courantes (`apikey/...`, `?token=...`)."""
    out = str(texte)
    for nom, valeur in os.environ.items():
        if nom.startswith("FEED_") and (nom.endswith("_URL") or nom.endswith("_TOKEN")) and valeur:
            out = out.replace(valeur, f"<{nom}>")
    out = _CLE_AWIN.sub(r"\1***", out)
    return _PARAM_SECRET.sub(r"\1***", out)


def configured_feeds() -> list[FeedSpec]:
    """Feeds that have a URL set in the environment."""
    return [f for f in FEEDS.values() if f.url]
