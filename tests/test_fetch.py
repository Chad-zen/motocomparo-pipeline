"""La revalidation conditionnelle : ne pas retélécharger ce qui n'a pas changé.

Les six flux pèsent 925 Mo. Mesuré le 2026-09-14, cinq marchands sur six
répondent `304` quand on leur joint l'empreinte de la copie qu'on a déjà :
656 Mo et trois minutes évités à chaque passage où rien n'a bougé.

Ce fichier existe parce que la panne serait silencieuse. Si l'en-tête cesse
d'être envoyé, rien ne casse : le pipeline retéléchargera simplement 925 Mo à
chaque fois, et personne ne s'en apercevra avant la facture de bande passante.
"""

from __future__ import annotations

import json

import httpx
import pytest

from mcpipe import fetch as mod
from mcpipe.feeds import FeedSpec


class _Reponse:
    """Le minimum d'une réponse httpx en flux, utilisable comme gestionnaire."""

    def __init__(self, statut: int, corps: bytes = b"", entetes: dict | None = None):
        self.status_code = statut
        self._corps = corps
        self.headers = httpx.Headers(entetes or {})
        self.num_bytes_downloaded = len(corps)
        self.ferme = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def close(self):
        self.ferme = True

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erreur", request=None, response=None)
        return self

    def iter_bytes(self, chunk_size: int = 0):
        yield self._corps


@pytest.fixture
def flux():
    return FeedSpec(code="essai", merchant_id=99, platform="effinity",
                    delimiter=",", gtin_trust="trusted", reliability_rank=9)


def _branche(monkeypatch, reponse: _Reponse, vues: list[dict]):
    def faux_stream(_methode, _url, **kw):
        vues.append(dict(kw.get("headers") or {}))
        return reponse

    monkeypatch.setattr(mod.httpx, "stream", faux_stream)
    monkeypatch.setattr(FeedSpec, "url", property(lambda self: "https://exemple.test/f.csv"))


def test_un_304_garde_le_fichier_et_ne_compte_aucun_octet(tmp_path, monkeypatch, flux):
    """Le cas qui fait tout l'intérêt : le serveur dit « rien de neuf »."""
    (tmp_path / "essai.csv").write_bytes(b"x" * 5_000)
    (tmp_path / "essai.http.json").write_text(
        json.dumps({"etag": '"abc"', "last-modified": "Mon, 14 Sep 2026 00:00:00 GMT"}),
        encoding="utf-8")

    vues: list[dict] = []
    _branche(monkeypatch, _Reponse(304), vues)
    res = mod.fetch_feed(flux, tmp_path, max_age_seconds=0)

    assert res.unchanged is True
    assert res.from_cache is True
    # L'empreinte a bien été posée dans la question, sinon le serveur n'aurait
    # aucun moyen de répondre 304.
    assert vues[0]["If-None-Match"] == '"abc"'
    assert vues[0]["If-Modified-Since"] == "Mon, 14 Sep 2026 00:00:00 GMT"
    # Et la copie est intacte : un 304 ne doit jamais effacer ce qu'on a.
    assert (tmp_path / "essai.csv").read_bytes() == b"x" * 5_000


def test_un_200_remplace_le_fichier_et_enregistre_la_nouvelle_empreinte(
        tmp_path, monkeypatch, flux):
    (tmp_path / "essai.csv").write_bytes(b"vieux" * 1_000)
    vues: list[dict] = []
    _branche(monkeypatch,
             _Reponse(200, b"neuf" * 2_000, {"etag": '"def"'}), vues)

    res = mod.fetch_feed(flux, tmp_path, max_age_seconds=0)

    assert res.unchanged is False
    assert (tmp_path / "essai.csv").read_bytes() == b"neuf" * 2_000
    assert mod._lire_empreinte(tmp_path, "essai") == {"etag": '"def"'}


def test_sans_copie_locale_on_ne_pose_pas_la_question(tmp_path, monkeypatch, flux):
    """Demander « as-tu changé ? » sans rien avoir vaudrait un 304 sur du vide."""
    vues: list[dict] = []
    _branche(monkeypatch, _Reponse(200, b"a" * 3_000), vues)

    mod.fetch_feed(flux, tmp_path, max_age_seconds=0)

    assert "If-None-Match" not in vues[0]
    assert "If-Modified-Since" not in vues[0]


def test_fresh_force_un_vrai_telechargement(tmp_path, monkeypatch, flux):
    """`--fresh` (max_age_seconds=None) doit court-circuiter la revalidation."""
    (tmp_path / "essai.csv").write_bytes(b"x" * 5_000)
    (tmp_path / "essai.http.json").write_text(json.dumps({"etag": '"abc"'}),
                                              encoding="utf-8")
    vues: list[dict] = []
    _branche(monkeypatch, _Reponse(200, b"b" * 4_000), vues)

    mod.fetch_feed(flux, tmp_path, max_age_seconds=None)

    assert "If-None-Match" not in vues[0]


def test_une_empreinte_illisible_ne_fait_pas_tomber_le_flux(tmp_path, monkeypatch, flux):
    """Un fichier d'empreinte corrompu doit valoir « je ne sais pas », pas une panne."""
    (tmp_path / "essai.csv").write_bytes(b"x" * 5_000)
    (tmp_path / "essai.http.json").write_text("{ ceci n'est pas du json",
                                              encoding="utf-8")
    vues: list[dict] = []
    _branche(monkeypatch, _Reponse(200, b"c" * 3_000), vues)

    res = mod.fetch_feed(flux, tmp_path, max_age_seconds=0)

    assert res.unchanged is False
    assert "If-None-Match" not in vues[0]
