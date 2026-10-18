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

import io
import json
import os
import time
import zipfile
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
    #: pour un flux à périmètre : combien de lignes par raison (ean_connu,
    #: rayon_tenu, hors_rayon, ean_invalide, sans_parent, deja_admis)
    raisons: dict | None = None


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


class FluxIncompletError(RuntimeError):
    """Colonnes obligatoires absentes : on n'importe pas un flux amputé."""


def _morceaux_du_zip(chemin: Path, taille: int = 1 << 20):
    """Le texte du premier fichier CSV d'une archive, par morceaux, sans le
    décompresser sur le disque."""
    with zipfile.ZipFile(chemin) as z:
        membres = [n for n in z.namelist() if n.lower().endswith(".csv")]
        if not membres:
            raise RuntimeError(f"{chemin.name}: aucune entrée .csv dans l'archive")
        with z.open(membres[0]) as brut:
            texte = io.TextIOWrapper(brut, encoding="utf-8", newline="")
            while morceau := texte.read(taille):
                yield morceau


def _marque(brut: str | None) -> str | None:
    from . import textnorm as tn

    code = tn.brand(brut)[0] if brut else ""
    return code or None


def _prix(brut: str | None) -> float | None:
    from . import textnorm as tn

    montant, _ = tn.price(brut)
    return float(montant) if montant else None


def _filtrer_perimetre(feed: FeedSpec, morceaux, fh, eans_connus: set[str],
                       deja_admis: set[str], on_progress=None,
                       prix_ref: dict[str, float] | None = None,
                       marques_ref: dict[str, frozenset[str]] | None = None) -> tuple[int, int, int, dict]:
    """Écrit dans `fh` l'en-tête réduit et les seules lignes du périmètre du flux.

    Les colonnes obligatoires sont vérifiées AVANT la première ligne écrite : un
    flux où `custom_1` (la taille) a disparu est refusé, pas importé sans taille.
    On ne garde que les colonnes que `feeds.py` sait lire (le flux Awin en compte
    86, on en lit 17) : `stg_feed_row` stocke chaque ligne en JSON.
    Rend (octets écrits, lignes lues, lignes gardées, comptes par raison)."""
    import csv
    import sys
    from collections import Counter

    from .normalize import _ci_get
    from .perimetre import decision

    csv.field_size_limit(sys.maxsize)
    lecteur = csv.reader(_lignes(morceaux), delimiter=feed.delimiter)
    entete = next(lecteur)
    presentes = {h.strip().lower() for h in entete}
    manquantes = [c for c in feed.colonnes_requises if c.lower() not in presentes]
    if manquantes:
        raise FluxIncompletError(
            f"{feed.code}: colonnes absentes du flux : {', '.join(manquantes)} — "
            "cocher ces cases sur la plateforme et regénérer l'URL")
    utiles = {n.lower() for noms in feed.columns.values() for n in noms}
    indices = [i for i, h in enumerate(entete) if h.strip().lower() in utiles]
    ecrivain = csv.writer(fh, delimiter=feed.delimiter, lineterminator="\n")
    ecrivain.writerow([entete[i] for i in indices])

    cols = feed.columns
    lues = gardees = 0
    raisons: Counter = Counter()
    for ligne in lecteur:
        lues += 1
        if len(ligne) != len(entete):
            raisons["colonnes_decalees"] += 1
            continue
        row = dict(zip(entete, ligne))
        sku = _ci_get(row, cols.get("merchant_ref", []))
        ok, raison = decision(
            feed.perimetre, ean=_ci_get(row, cols.get("gtin", [])),
            categorie=_ci_get(row, cols.get("category", [])),
            titre=_ci_get(row, cols.get("title", [])),
            parent=_ci_get(row, cols.get("item_group_id", [])), sku=sku,
            eans_connus=eans_connus, deja_admis=deja_admis,
            prix=_prix(_ci_get(row, cols.get("price", []))), prix_ref=prix_ref,
            marque=_marque(_ci_get(row, cols.get("brand", []))), marques_ref=marques_ref,
        )
        raisons[raison] += 1
        if ok:
            ecrivain.writerow([ligne[i] for i in indices])
            gardees += 1
        if on_progress is not None and lues % 25_000 == 0:
            on_progress(feed.code, fh.tell())
    return fh.tell(), lues, gardees, dict(raisons)


def fetch_feed(
    feed: FeedSpec,
    dest_dir: Path,
    *,
    max_age_seconds: float | None = 3 * 3600,
    on_progress=None,
    connues: set[str] | None = None,
    eans_connus: set[str] | None = None,
    prix_ref: dict[str, float] | None = None,
    marques_ref: dict[str, frozenset[str]] | None = None,
) -> FetchResult:
    """Download one feed. Reuses an existing file younger than `max_age_seconds`
    (set to None to always re-download).

    `connues` : si fourni (et non vide), seules les offres dont la clé y figure
    sont écrites — voir `_filtrer_connues`.

    `eans_connus` : pour un flux à `perimetre`, les codes-barres déjà présents chez
    les AUTRES marchands (voir `perimetre.py`). `connues`, lui, sert alors de liste
    des offres déjà admises de CE marchand."""
    if feed.url is None:
        raise ValueError(f"feed {feed.code!r} has no URL configured")
    if feed.perimetre and eans_connus is None:
        raise ValueError(f"feed {feed.code!r}: `eans_connus` est obligatoire avec un périmètre")

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
    zip_part: Path | None = None
    raisons: dict | None = None
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
        if feed.compression == "zip":
            # L'archive arrive entière sur le disque (une archive ne se lit pas à la
            # volée), puis est filtrée plus bas, une fois la taille vérifiée.
            filtre = None
            zip_part = dest_dir / f"{feed.code}.zip.part"
            zip_part.unlink(missing_ok=True)
            with zip_part.open("wb") as fh:
                for chunk in r.iter_bytes(chunk_size=1 << 20):  # 1 MiB
                    fh.write(chunk)
                    written += len(chunk)
                    if on_progress is not None:
                        on_progress(feed.code, written)
        elif connues:
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
        if zip_part is not None:
            zip_part.unlink(missing_ok=True)
        raise RuntimeError(f"{feed.code}: got only {written} bytes — looks like an error page")

    if zip_part is not None:
        # Le contrôle des colonnes se fait ici, avant que `<code>.csv` ne soit
        # remplacé : un flux refusé laisse la copie précédente intacte.
        morceaux = _morceaux_du_zip(zip_part)
        try:
            with part.open("w", encoding="utf-8", newline="") as fh:
                if feed.perimetre:
                    written, lues, gardees, raisons = _filtrer_perimetre(
                        feed, morceaux, fh, eans_connus or set(),
                        connues or set(), on_progress, prix_ref, marques_ref)
                    filtre = (lues, gardees)
                else:
                    for morceau in morceaux:
                        fh.write(morceau)
                    written = fh.tell()
        except BaseException:
            part.unlink(missing_ok=True)
            raise
        finally:
            # fermer le generateur AVANT de supprimer l'archive : sur Windows un
            # fichier encore ouvert ne se supprime pas (une erreur en cours de
            # lecture le laisse ouvert)
            morceaux.close()
            zip_part.unlink(missing_ok=True)
        if written < _MIN_BYTES:
            part.unlink(missing_ok=True)
            raise RuntimeError(f"{feed.code}: le périmètre n'a laissé que {written} octets")

    os.replace(part, final)  # atomic on the same filesystem
    # L'empreinte n'est écrite qu'ici : après un fichier complet, validé, en
    # place. Une empreinte écrite plus tôt ferait sauter le prochain
    # téléchargement au nom d'une copie qui n'existe pas.
    _ecrire_empreinte(dest_dir, feed.code, entetes)
    return FetchResult(feed.code, final, written, time.time() - t0, filtre=filtre,
                       raisons=raisons)
