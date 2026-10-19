"""Un seul calcul a la fois par cle : les visiteurs suivants attendent la valeur."""

import threading
import time

from mcsite import cache


def test_deux_visiteurs_sur_cache_froid_ne_calculent_qu_une_fois():
    cache.vider() if hasattr(cache, "vider") else cache._boite.clear()
    appels = []

    def lent():
        appels.append(1)
        time.sleep(0.3)
        return "valeur"

    sorties = []
    fils = [threading.Thread(target=lambda: sorties.append(cache.au_chaud("k-verrou", lent, ttl=60)))
            for _ in range(5)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    assert len(appels) == 1
    assert sorties == ["valeur"] * 5


def test_un_echec_ne_bloque_pas_les_suivants_et_n_est_pas_garde():
    cache._boite.clear()

    def casse():
        raise RuntimeError("delai depasse")

    try:
        cache.au_chaud("k-echec", casse, ttl=60)
    except RuntimeError:
        pass
    assert cache.au_chaud("k-echec", lambda: "ok", ttl=60) == "ok"


def test_cles_differentes_ne_s_attendent_pas():
    cache._boite.clear()
    debut = time.monotonic()
    t = threading.Thread(target=lambda: cache.au_chaud("k-a", lambda: time.sleep(0.4) or 1, ttl=60))
    t.start()
    time.sleep(0.05)
    assert cache.au_chaud("k-b", lambda: 2, ttl=60) == 2
    assert time.monotonic() - debut < 0.35
    t.join()
