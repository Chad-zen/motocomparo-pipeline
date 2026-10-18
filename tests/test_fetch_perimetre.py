"""Le téléchargement d'un flux Awin en archive, filtré à son périmètre (18/10/2026).

Le flux de Motard Bleu pèse 37 Mo en zip, 223 Mo une fois ouvert, 130 143 lignes. On
ne laisse entrer que l'équipement du pilote ; `perimetre.py` en donne la règle, ce
fichier vérifie que la règle s'applique bien AU TÉLÉCHARGEMENT, que les colonnes
obligatoires sont contrôlées avant tout remplacement, et que rien ne traîne sur le
disque après coup.
"""

from __future__ import annotations

import csv
import io
import zipfile

import httpx
import pytest

from mcpipe import fetch as mod
from mcpipe.feeds import FEEDS
from mcpipe.fetch import FluxIncompletError
from mcpipe.perimetre import cle_gtin, decision


def ean13(douze: str) -> str:
    """Un EAN-13 à clé de contrôle valide à partir de ses douze premiers chiffres."""
    total = sum(int(c) * (3 if i % 2 else 1) for i, c in enumerate(douze))
    return douze + str((10 - total % 10) % 10)


KNOWN = ean13("366161575156")       # déjà chez un autre marchand
NEW = ean13("366161575157")         # inconnu, dans un rayon tenu, avec un parent
NO_PARENT = ean13("366161575158")   # inconnu, rayon tenu, sans parent
PIECE = ean13("366161575159")       # inconnu, hors rayon (« non classé »)
KNOWN_PIECE = ean13("366161575160")  # connu, mais dans un rayon qu'on ne charge pas encore
ADMIS = ean13("366161575161")       # déjà admis par un passage précédent
INVALID = "3700611016437"           # clé de contrôle fausse, vu dans le flux réel

ENTETE = ["aw_deep_link", "product_name", "merchant_product_id", "merchant_image_url",
          "description", "merchant_category", "search_price", "currency", "ean", "mpn",
          "parent_product_id", "in_stock", "brand_name", "colour", "custom_1", "custom_2",
          "custom_3", "rrp_price", "delivery_cost"]


def _ligne(sku, ean, categorie, parent="P1", titre="Blouson moto Ixon Arma", taille="M"):
    return [f"https://awin.test/{sku}", titre, sku, "https://img.test/a.jpg", "desc",
            categorie, "99.99", "EUR", ean, "MPN1", parent, "1", "Ixon", "Noir", taille,
            "Unisex", "Adulte", "129.99", "7.49"]


LIGNES = [
    _ligne("S1", KNOWN, "Moto > Blouson moto > Adulte > Homme"),
    _ligne("S2", NEW, "Moto > Casque moto intégral > Adulte > Mixte", titre="Casque Shark"),
    _ligne("S3", NO_PARENT, "Moto > Gants moto été > Adulte > Homme", parent="", titre="Gants"),
    _ligne("S4", PIECE, "Moto > Rétroviseur moto", titre="Rétroviseur"),
    _ligne("S5", KNOWN_PIECE, "Moto > Rétroviseur moto", titre="Rétroviseur"),
    _ligne("S6", ADMIS, "Moto > Rétroviseur moto", titre="Rétroviseur"),
    _ligne("S7", INVALID, "Moto > Blouson moto > Adulte > Homme"),
    _ligne("S8", "", "Moto > Blouson moto > Adulte > Homme"),
]


def _csv(entete=ENTETE, lignes=LIGNES) -> bytes:
    sortie = io.StringIO()
    w = csv.writer(sortie, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(entete)
    w.writerows(lignes)
    return sortie.getvalue().encode("utf-8")


def _zip(contenu: bytes, nom="flux.csv") -> bytes:
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(nom, contenu)
    return tampon.getvalue()


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
        # coupé en morceaux : une archive reçue par paquets ne doit rien changer
        for i in range(0, len(self._corps), 64):
            yield self._corps[i:i + 64]


@pytest.fixture
def mb(monkeypatch):
    monkeypatch.setenv("FEED_MOTARDBLEU_URL", "https://productdata.awin.com/datafeed/download/apikey/CLE/x/")
    # les archives d'essai pesent quelques centaines d'octets, pas un mega
    monkeypatch.setattr(mod, "_MIN_BYTES", 100)
    return FEEDS["motardbleu"]


def _telecharger(monkeypatch, tmp_path, mb, corps, **kw):
    monkeypatch.setattr(mod.httpx, "stream", lambda *a, **k: _Reponse(corps))
    return mod.fetch_feed(mb, tmp_path, max_age_seconds=None, **kw)


def _lire(chemin):
    return list(csv.DictReader(chemin.open(encoding="utf-8", newline="")))


def test_le_perimetre_s_applique_au_telechargement(tmp_path, monkeypatch, mb):
    res = _telecharger(monkeypatch, tmp_path, mb, _zip(_csv()),
                       eans_connus={cle_gtin(KNOWN), cle_gtin(KNOWN_PIECE)}, connues={"S6"})
    gardees = {r["merchant_product_id"] for r in _lire(res.path)}
    assert gardees == {"S1", "S2", "S5", "S6"}
    assert res.filtre == (8, 4)
    assert res.raisons == {"ean_connu": 2, "rayon_tenu": 1, "sans_parent": 1,
                           "hors_rayon": 1, "deja_admis": 1, "ean_invalide": 2}


def test_on_ne_garde_que_les_colonnes_que_feeds_py_sait_lire(tmp_path, monkeypatch, mb):
    res = _telecharger(monkeypatch, tmp_path, mb, _zip(_csv()), eans_connus={cle_gtin(KNOWN)})
    colonnes = set(_lire(res.path)[0])
    assert {"ean", "custom_1", "aw_deep_link", "search_price"} <= colonnes
    assert "rrp_price" not in colonnes          # prix conseille : jamais lu
    assert "delivery_cost" not in colonnes


def test_les_champs_a_virgule_et_a_saut_de_ligne_survivent(tmp_path, monkeypatch, mb):
    lignes = [_ligne("S1", KNOWN, "Moto > Blouson moto > Adulte > Homme", titre="Blouson, hiver\nligne 2")]
    res = _telecharger(monkeypatch, tmp_path, mb, _zip(_csv(lignes=lignes)), eans_connus={cle_gtin(KNOWN)})
    assert _lire(res.path)[0]["product_name"] == "Blouson, hiver\nligne 2"


def test_l_archive_et_le_part_ne_trainent_pas(tmp_path, monkeypatch, mb):
    _telecharger(monkeypatch, tmp_path, mb, _zip(_csv()), eans_connus={cle_gtin(KNOWN)})
    assert sorted(p.name for p in tmp_path.iterdir()) == ["motardbleu.csv"]


def test_une_colonne_obligatoire_absente_refuse_le_flux_et_garde_l_ancienne_copie(tmp_path, monkeypatch, mb):
    ancien = tmp_path / "motardbleu.csv"
    ancien.write_text("a" * 2000, encoding="utf-8")
    sans_taille = [c for c in ENTETE if c != "custom_1"]
    lignes = [[v for c, v in zip(ENTETE, l) if c != "custom_1"] for l in LIGNES]
    with pytest.raises(FluxIncompletError, match="custom_1"):
        _telecharger(monkeypatch, tmp_path, mb, _zip(_csv(sans_taille, lignes)),
                     eans_connus={cle_gtin(KNOWN)})
    assert ancien.read_text(encoding="utf-8") == "a" * 2000
    assert sorted(p.name for p in tmp_path.iterdir()) == ["motardbleu.csv"]


def test_un_perimetre_sans_eans_connus_est_une_erreur_pas_un_chargement_complet(tmp_path, monkeypatch, mb):
    with pytest.raises(ValueError, match="eans_connus"):
        _telecharger(monkeypatch, tmp_path, mb, _zip(_csv()))


def test_une_archive_sans_csv_est_refusee(tmp_path, monkeypatch, mb):
    with pytest.raises(RuntimeError, match="aucune entrée .csv"):
        _telecharger(monkeypatch, tmp_path, mb, _zip(_csv(), nom="lisez-moi.txt"), eans_connus=set())
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_une_page_d_erreur_n_est_pas_un_flux(tmp_path, monkeypatch, mb):
    with pytest.raises(RuntimeError, match="looks like an error page"):
        _telecharger(monkeypatch, tmp_path, mb, b"<html>erreur</html>", eans_connus=set())


# --- la règle elle-même ------------------------------------------------------


def _d(**kw):
    base = dict(ean=NEW, categorie="Moto > Casque moto intégral > Adulte > Mixte", titre="Casque",
                parent="P", sku="X", eans_connus=set(), deja_admis=set())
    base.update(kw)
    return decision("equipement_pilote", **base)


def test_un_ean_dont_la_cle_est_fausse_n_est_jamais_connu():
    assert _d(ean=INVALID, eans_connus={INVALID}) == (False, "ean_invalide")


def test_un_upc_et_son_ean_a_zero_de_tete_sont_le_meme_code():
    # 036000291452 est un UPC-A valide ; 0036000291452 est le meme code ecrit en EAN-13
    assert cle_gtin("036000291452") == cle_gtin("0036000291452") == "36000291452"


def test_un_produit_connu_entre_meme_hors_rayon():
    assert _d(ean=KNOWN, categorie="Moto > Rétroviseur moto", eans_connus={cle_gtin(KNOWN)}) == (True, "ean_connu")


def test_une_offre_deja_admise_le_reste_meme_si_l_autre_marchand_la_perd():
    # le perimetre est monotone : l'EAN n'est plus chez personne, la ligne reste
    assert _d(categorie="Moto > Rétroviseur moto", sku="S6", deja_admis={"S6"}) == (True, "deja_admis")


def test_un_nouveau_produit_sans_parent_n_entre_pas():
    assert _d(parent="") == (False, "sans_parent")
    assert _d(parent="   ") == (False, "sans_parent")


def test_une_piece_inconnue_n_entre_pas():
    assert _d(categorie="Moto > Rétroviseur moto") == (False, "hors_rayon")
    assert _d(categorie="Moto > Silencieux moto > Adulte > Mixte") == (False, "hors_rayon")


def test_un_nouveau_produit_d_equipement_avec_parent_entre():
    assert _d() == (True, "rayon_tenu")


# --- le garde-fou de prix a la porte -----------------------------------------


@pytest.mark.parametrize("prix, ref, garde", [
    (68.0, 68.0, True),       # le meme prix
    (17.1, 68.0, True),       # 0,2515 x la mediane : limite basse, gardee
    (16.9, 68.0, False),      # 0,2485 x : ecartee
    (271.0, 68.0, True),      # 3,99 x
    (273.0, 68.0, False),     # 4,01 x
    (20.82, 336.90, False),   # 0,062 x : un code-barres reutilise (cas reel du flux)
])
def test_le_prix_hors_du_quart_a_quatre_fois_la_mediane_est_ecarte(prix, ref, garde):
    ok, raison = _d(ean=KNOWN, eans_connus={cle_gtin(KNOWN)}, prix=prix, prix_ref={cle_gtin(KNOWN): ref})
    assert ok is garde
    assert garde or raison == "prix_aberrant"


def test_sans_prix_de_reference_le_garde_fou_ne_joue_pas():
    assert _d(ean=NEW, prix=5000.0, prix_ref={})[0] is True


def test_le_garde_fou_joue_meme_pour_une_offre_deja_admise():
    ok, raison = _d(ean=ADMIS, categorie="Moto > Rétroviseur moto", sku="S6", deja_admis={"S6"},
                    prix=1000.0, prix_ref={cle_gtin(ADMIS): 10.0})
    assert (ok, raison) == (False, "prix_aberrant")


def test_le_garde_fou_s_applique_au_telechargement(tmp_path, monkeypatch, mb):
    ref = {cle_gtin(KNOWN): 399.0}   # notre prix : 399 ; le flux dit 99,99 (0,2506x : limite, gardee)
    res = _telecharger(monkeypatch, tmp_path, mb, _zip(_csv()), eans_connus={cle_gtin(KNOWN)}, prix_ref=ref)
    assert "S1" in {r["merchant_product_id"] for r in _lire(res.path)}      # limite basse, gardee
    ref = {cle_gtin(KNOWN): 450.0}   # 0,2222x : ecartee
    res = _telecharger(monkeypatch, tmp_path, mb, _zip(_csv()), eans_connus={cle_gtin(KNOWN)}, prix_ref=ref)
    assert "S1" not in {r["merchant_product_id"] for r in _lire(res.path)}
    assert res.raisons["prix_aberrant"] == 1


# --- la marque en desaccord ---------------------------------------------------


def test_une_marque_en_desaccord_ecarte_l_offre_seule():
    ref = {cle_gtin(KNOWN): frozenset({"gpr"})}
    assert _d(ean=KNOWN, eans_connus={cle_gtin(KNOWN)}, marque="gprexhaust", marques_ref=ref) == (False, "marque_en_desaccord")
    assert _d(ean=KNOWN, eans_connus={cle_gtin(KNOWN)}, marque="gpr", marques_ref=ref) == (True, "ean_connu")


def test_si_les_autres_marchands_se_partagent_il_suffit_d_en_etre():
    # « ng » et « ngbrake » coexistent chez les autres : une offre « ng » n'est pas en desaccord
    ref = {cle_gtin(KNOWN): frozenset({"ng", "ngbrake"})}
    assert _d(ean=KNOWN, eans_connus={cle_gtin(KNOWN)}, marque="ng", marques_ref=ref)[0] is True
    assert _d(ean=KNOWN, eans_connus={cle_gtin(KNOWN)}, marque="ngbrakedisc", marques_ref=ref)[0] is False


def test_sans_marque_de_reference_ou_sans_marque_le_garde_fou_ne_joue_pas():
    assert _d(ean=NEW, marque="gprexhaust", marques_ref={})[0] is True
    assert _d(ean=KNOWN, eans_connus={cle_gtin(KNOWN)}, marque=None,
              marques_ref={cle_gtin(KNOWN): frozenset({"gpr"})})[0] is True


def test_la_marque_en_desaccord_s_applique_au_telechargement(tmp_path, monkeypatch, mb):
    ref = {cle_gtin(KNOWN): frozenset({"gpr"})}    # le flux dit « Ixon »
    res = _telecharger(monkeypatch, tmp_path, mb, _zip(_csv()), eans_connus={cle_gtin(KNOWN)}, marques_ref=ref)
    assert "S1" not in {r["merchant_product_id"] for r in _lire(res.path)}
    assert res.raisons["marque_en_desaccord"] == 1
