"""Stage 1 — download each configured merchant feed to disk.

Streamed: bytes are written straight to a file as they arrive, so a 375 MB feed
never sits in memory. The download goes to `<code>.csv.part` and is renamed to
`<code>.csv` only once it completes — a killed download never leaves a truncated
file that a later stage would try to parse.

**On ne retélécharge pas un fichier qui n'a pas changé.** Les six flux pèsent
925 Mo ensemble, et un marchand qui n'a rien republié renvoie exactement les
mêmes octets. On demande donc d'abord : « as-tu changé depuis ma copie ? », en
joignant l'empreinte (`ETag`) et la date de la copie qu'on a déjà. Le serveur
répond `304` sans corps, et la question aura coûté un kilo-octet.

Mesuré le 2026-09-14 : cinq marchands sur six répondent `304` — Speedway, La
Bécanerie, Motoblouz, Maxxess, Moto-Axxe, soit 655 Mo évités à chaque passage
où rien n'a bougé. FC-Moto (270 Mo) n'annonce ni date ni empreinte : lui seul
est retéléchargé à l'aveugle, et aucune question ne peut y changer quoi que ce
soit.

L'empreinte est gardée à côté du fichier, dans `<code>.http.json`. Elle n'est
écrite qu'après un téléchargement réussi : une copie posée à la main n'a pas
d'empreinte, donc elle est revalidée normalement plutôt que crue sur parole.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from .feeds import FeedSpec

# feeds are big; be patient on the body, quick to give up on a dead connection
_TIMEOUT = httpx.Timeout(connect=15.0, read=120.0, write=30.0, pool=15.0)
_MIN_BYTES = 1_000  # anything smaller than this is an error page, not a feed


@dataclass
class FetchResult:
    feed: str
    path: Path
    bytes: int
    seconds: float
    from_cache: bool = False
    #: le serveur a répondu « rien de neuf » (304). Distinct de `from_cache`,
    #: qui veut seulement dire « ma copie est récente, je n'ai pas demandé ».
    unchanged: bool = False
    #: (lignes lues, lignes gardées) quand le flux a été filtré aux offres connues
    filtre: tuple[int, int] | None = None


def _meta_path(dest_dir: Path, code: str) -> Path:
    return dest_dir / f"{code}.http.json"


def _lire_empreinte(dest_dir: Path, code: str) -> dict[str, str]:
    try:
        with _meta_path(dest_dir, code).open(encoding="utf-8") as fh:
            donnees = json.load(fh)
        return donnees if isinstance(donnees, dict) else {}
    except (OSError, ValueError):
        return {}  # absente ou illisible : on revalide, c'est tout


def _ecrire_empreinte(dest_dir: Path, code: str, entetes: httpx.Headers) -> None:
    empreinte = {c: entetes[c] for c in ("etag", "last-modified") if c in entetes}
    if not empreinte:
        _meta_path(dest_dir, code).unlink(missing_ok=True)
        return
    with _meta_path(dest_dir, code).open("w", encoding="utf-8") as fh:
        json.dump(empreinte, fh)


def _lignes(morceaux):
    """Les lignes d'un texte reçu par morceaux, fin de ligne comprise.

    Coupé sur `\\n` seulement : `csv` recolle lui-même un champ entre
    guillemets qui contient un saut de ligne (les descriptions FC-Moto en ont).
    """
    reste = ""
    for m in morceaux:
        reste += m
        parts = reste.split("\n")
        reste = parts.pop()
        for p in parts:
            yield p + "\n"
    if reste:
        yield reste


def _filtrer_connues(feed: FeedSpec, morceaux, fh, connues: set[str],
                     on_progress=None) -> tuple[int, int, int]:
    """Écrit dans `fh` l'en-tête et les seules lignes dont la clé est connue.

    Le flux n'est jamais écrit en entier : c'est tout l'intérêt — le 14/10/2026,
    FC-Moto a envoyé 7,2 Go, plus que le disque libre. La clé est calculée par
    `normalize._merchant_sku`, la même qui identifie l'offre en base : le
    filtre et la base ne peuvent pas diverger.
    Rend (octets écrits, lignes lues, lignes gardées).
    """
    import csv
    import sys

    from .normalize import _merchant_sku

    csv.field_size_limit(sys.maxsize)
    lecteur = csv.reader(_lignes(morceaux), delimiter=feed.delimiter)
    ecrivain = csv.writer(fh, delimiter=feed.delimiter, lineterminator="\n")
    entete = next(lecteur)
    ecrivain.writerow(entete)
    lues = gardees = 0
    for ligne in lecteur:
        lues += 1
        if _merchant_sku(feed, dict(zip(entete, ligne)), "") in connues:
            ecrivain.writerow(ligne)
            gardees += 1
        if on_progress is not None and lues % 250_000 == 0:
            on_progress(feed.code, fh.tell())
    return fh.tell(), lues, gardees


def fetch_feed(
    feed: FeedSpec,
    dest_dir: Path,
    *,
    max_age_seconds: float | None = 3 * 3600,
    on_progress=None,
    connues: set[str] | None = None,
) -> FetchResult:
    """Download one feed. Reuses an existing file younger than `max_age_seconds`
    (set to None to always re-download).

    `connues` : si fourni (et non vide), seules les offres dont la clé y figure
    sont écrites — voir `_filtrer_connues`."""
    if feed.url is None:
        raise ValueError(f"feed {feed.code!r} has no URL configured")

    dest_dir.mkdir(parents=True, exist_ok=True)
    final = dest_dir / f"{feed.code}.csv"
    part = dest_dir / f"{feed.code}.csv.part"

    if (
        max_age_seconds is not None
        and final.exists()
        and final.stat().st_size >= _MIN_BYTES
        and (time.time() - final.stat().st_mtime) < max_age_seconds
    ):
        return FetchResult(feed.code, final, final.stat().st_size, 0.0, from_cache=True)

    headers = {}
    if feed.auth_token:
        headers["Authorization"] = f"Bearer {feed.auth_token}"

    # La question polie. Posée seulement si on a bien un fichier complet à
    # revalider — et jamais sous `--fresh`, dont le rôle est justement de
    # forcer un vrai téléchargement.
    revalide = (
        max_age_seconds is not None
        and final.exists()
        and final.stat().st_size >= _MIN_BYTES
    )
    if revalide:
        empreinte = _lire_empreinte(dest_dir, feed.code)
        if etag := empreinte.get("etag"):
            headers["If-None-Match"] = etag
        if date := empreinte.get("last-modified"):
            headers["If-Modified-Since"] = date

    t0 = time.time()
    written = 0
    part.unlink(missing_ok=True)
    with httpx.stream(
        "GET", feed.url, timeout=_TIMEOUT, follow_redirects=True, headers=headers
    ) as r:
        if r.status_code == 304:
            # Rien de neuf : le corps n'a même pas été envoyé. On garde la copie
            # et on la redate, pour que le garde-fou par l'âge reparte de zéro.
            r.close()
            taille = final.stat().st_size
            os.utime(final, None)
            return FetchResult(feed.code, final, taille, time.time() - t0,
                               from_cache=True, unchanged=True)
        r.raise_for_status()
        if connues:
            with part.open("w", encoding="utf-8", newline="") as fh:
                written, lues, gardees = _filtrer_connues(
                    feed, r.iter_text(chunk_size=1 << 20), fh, connues, on_progress)
            filtre = (lues, gardees)
        else:
            filtre = None
            with part.open("wb") as fh:
                for chunk in r.iter_bytes(chunk_size=1 << 20):  # 1 MiB
                    fh.write(chunk)
                    written += len(chunk)
                    if on_progress is not None:
                        on_progress(feed.code, written)

        # a stream that stops short of the advertised length is a truncated
        # download, not a complete feed. `num_bytes_downloaded` is the count
        # over the wire, comparable to Content-Length (both pre-decompression).
        # Absent on chunked / gzipped-without-length responses — skip then.
        entetes = r.headers
        declared = r.headers.get("content-length")
        if declared and r.num_bytes_downloaded < int(declared):
            part.unlink(missing_ok=True)
            raise RuntimeError(
                f"{feed.code}: truncated download — got {r.num_bytes_downloaded:,} "
                f"of {int(declared):,} bytes"
            )

    if written < _MIN_BYTES:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"{feed.code}: got only {written} bytes — looks like an error page")

    os.replace(part, final)  # atomic on the same filesystem
    # L'empreinte n'est écrite qu'ici : après un fichier complet, validé, en
    # place. Une empreinte écrite plus tôt ferait sauter le prochain
    # téléchargement au nom d'une copie qui n'existe pas.
    _ecrire_empreinte(dest_dir, feed.code, entetes)
    return FetchResult(feed.code, final, written, time.time() - t0, filtre=filtre)
