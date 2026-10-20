"""Le profil Motoin (Webgains), 19/10/2026 : colonnes, perimetre d'un CSV simple, prix promo JSON, rayons au pluriel."""

from __future__ import annotations

import csv
import io

import httpx
import pytest

from mcpipe import fetch as mod
from mcpipe.category import CATEGORIES, classify
from mcpipe.feeds import FEEDS
from mcpipe.normalize import _prix_promo
from mcpipe.perimetre import EQUIPEMENT_PILOTE, cle_gtin

NOMS = {c[0]: c[3] for c in CATEGORIES}


def ean13(douze: str) -> str:
    total = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(douze))
    return douze + str((10 - total % 10) % 10)


CONNU = ean13("366161575156")
NOUVEAU = ean13("366161575157")
LOISIR = ean13("366161575158")
INCONNU_SANS_RAYON = ean13("366161575159")

ENTETE = ["id", "gtin", "title", "brand", "link", "price", "sale_price", "product_category", "size",
          "item_group_id", "color", "mpn", "description", "image_link", "availability", "gender", "age_group"]


def _ligne(i, gtin, categorie, titre, parent="G1"):
    return [i, gtin, titre, "Alpinestars", f"https://webgains.test/{i}", "99.95 EUR",
            '{"FR":99.95,"DE":99.95}', categorie, "M", parent, "Noir", "MPN-PARTAGE", "desc",
            "https://img.test/a.jpg", "in stock", "male", "adult"]


LIGNES = [
    _ligne("A1", CONNU, "Vêtements>Vestes>Vestes en textile", "Alpinestars T-Missile, veste textile"),
    _ligne("A2", NOUVEAU, "Casques>Casques intégraux", "Shark Spartan, casque intégral"),
    _ligne("A3", LOISIR, "Habits loisirs>Pantalons", "Carhartt Rugged, pantalon de travail"),
    _ligne("A4", INCONNU_SANS_RAYON, "Bikes>Vélos", "Vélo de ville"),
    _ligne("A5", "3700611016437", "Vêtements>Gants>Gants de touring / chopper", "Held, gants"),   # cle fausse
]


def _csv() -> bytes:
    sortie = io.StringIO()
    w = csv.writer(sortie, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(ENTETE)
    w.writerows(LIGNES)
    return sortie.getvalue().encode("utf-8")


class _Reponse:
    def __init__(self, corps: bytes):
        self.status_code = 200
        self._corps = corps
        self.headers = httpx.Headers({})
        self.num_bytes_downloaded = len(corps)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def close(self):
        pass

    def raise_for_status(self):
        return self

    def iter_bytes(self, chunk_size: int = 0):
        for i in range(0, len(self._corps), 64):
            yield self._corps[i:i + 64]

    def iter_text(self, chunk_size: int = 0):
        texte = self._corps.decode("utf-8")
        for i in range(0, len(texte), 64):
            yield texte[i:i + 64]


@pytest.fixture
def motoin(monkeypatch):
    monkeypatch.setenv("FEED_MOTOIN_URL", "http://127.0.0.1:1/feed.csv")
    monkeypatch.setattr(mod, "_MIN_BYTES", 100)
    return FEEDS["motoin"]


def _telecharger(monkeypatch, tmp_path, spec, **kw):
    monkeypatch.setattr(mod.httpx, "stream", lambda *a, **k: _Reponse(_csv()))
    return mod.fetch_feed(spec, tmp_path, max_age_seconds=None, **kw)


def _lire(chemin):
    return list(csv.DictReader(chemin.open(encoding="utf-8", newline="")))


# --- le profil ----------------------------------------------------------------

def test_la_reference_de_l_offre_est_l_id_jamais_le_mpn():
    cols = FEEDS["motoin"].columns
    assert cols["merchant_ref"] == ["id"]            # `mpn` est partage entre les tailles d'un article
    assert "mpn" not in cols                          # et n'est pas lu (marchand `trusted`)


def test_le_rayon_vient_de_product_category_et_le_marchand_est_masque():
    f = FEEDS["motoin"]
    assert f.columns["category"][0] == "product_category"
    assert f.affiche_au_depart is False and f.ecarte_desaccords is True
    assert f.perimetre == "equipement_pilote" and f.platform == "webgains"
    assert len({x.merchant_id for x in FEEDS.values()}) == len(FEEDS)    # pas de numero en double


# --- le perimetre s'applique aussi a un CSV simple ------------------------------

def test_un_csv_simple_est_filtre_au_telechargement(tmp_path, monkeypatch, motoin):
    res = _telecharger(monkeypatch, tmp_path, motoin, eans_connus={cle_gtin(CONNU)}, connues=set())
    gardees = {r["id"] for r in _lire(res.path)}
    assert gardees == {"A1", "A2"}          # connu + casque neuf avec parent ; loisir, velo, cle fausse : dehors
    assert res.filtre == (5, 2)
    assert res.raisons["hors_rayon"] == 2 and res.raisons["ean_invalide"] == 1


def test_des_offres_deja_admises_ne_ferment_pas_la_porte_aux_produits_nouveaux(tmp_path, monkeypatch, motoin):
    # avec `connues` non vide, l'ancienne branche « seulement les offres connues » (FC-Moto) prenait
    # la place du perimetre des la 2e nuit : le casque neuf A2 n'entrait plus jamais
    res = _telecharger(monkeypatch, tmp_path, motoin, eans_connus={cle_gtin(CONNU)}, connues={"A1"})
    assert {r["id"] for r in _lire(res.path)} == {"A1", "A2"}


# --- le prix promotionnel en JSON par pays --------------------------------------

def test_le_prix_promo_est_celui_de_la_france():
    assert _prix_promo('{"AD":31.95,"FR":29.5,"DE":31.95}') == "29.5 EUR"


def test_un_prix_promo_illisible_ou_sans_france_est_ignore():
    assert _prix_promo('{"DE":31.95}') is None
    assert _prix_promo("{pas du json") is None
    assert _prix_promo('{"FR":0}') is None
    assert _prix_promo('{"FR":"abc"}') is None


def test_un_prix_promo_ordinaire_passe_tel_quel():
    assert _prix_promo("311.99 EUR") == "311.99 EUR"
    assert _prix_promo(None) is None and _prix_promo("") == ""


# --- les rayons au pluriel -------------------------------------------------------

@pytest.mark.parametrize("chemin, rayon", [
    ("Casques>Casques intégraux", "Casques intégraux"),
    ("Casques>Casques jets", "Casques jet"),
    ("Casques>Casques Cross / Enduro", "Casques cross"),
    ("Casques>Casques modulables", "Casques modulables"),
    ("Vêtements>Vestes>Vestes en textile", "Blousons & vestes"),
    ("Vêtements>Vestes>Vestes en cuir", "Blousons & vestes"),
    ("Vêtements>Pantalons>Pantalons textile", "Pantalons"),
    ("Vêtements>Pantalons>Jeans", "Pantalons"),
    ("Vêtements>Combinaisons>Combinaisons en cuir", "Combinaisons"),
    ("Casques>Accessoires", "Pièces & accessoires casque"),
])
def test_les_chemins_de_motoin_trouvent_leur_rayon(chemin, rayon):
    assert NOMS[classify(chemin, "titre sans importance")] == rayon


@pytest.mark.parametrize("chemin", ["Habits loisirs>Pantalons", "Habits loisirs>Vestes",
                                     "Habits loisirs>Chaussures / Bottes"])
def test_les_habits_loisirs_restent_hors_du_perimetre(chemin):
    assert classify(chemin, "Carhartt") not in EQUIPEMENT_PILOTE
    assert NOMS[classify(chemin, "Carhartt")] == "Vêtements casual / lifestyle"
