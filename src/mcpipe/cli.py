"""Command-line entry point.

Each pipeline stage is its own subcommand so it can be run and inspected in
isolation. `mcpipe run` chains them in order.

    mcpipe fetch          download the merchant feeds
    mcpipe load           CSV -> Postgres staging
    mcpipe normalize      staging -> raw_offer
    mcpipe match          cluster offers into products
    mcpipe enrich         colour / size / category
    mcpipe freshness      expire unseen offers, recompute prices
    mcpipe publish        build + swap the storefront tables (mode-gated)
    mcpipe run            all of the above, in order

Most stages are not implemented yet — this is the skeleton. See docs/roadmap.md.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

from . import __version__
from .feeds import FEEDS, configured_feeds, masquer_secrets

load_dotenv()  # read .env into the environment before anything looks at it

app = typer.Typer(add_completion=False, help="motocomparo data pipeline")
console = Console()


def _feeds_dir() -> Path:
    return Path(os.environ.get("FEEDS_DIR", "./feeds"))


def _mb(n: int) -> str:
    return f"{n / 1_048_576:.1f} MB"


@app.command()
def version() -> None:
    """Print the version."""
    console.print(f"mcpipe {__version__}")


@app.command()
def feeds() -> None:
    """List the merchant feeds and whether each one is configured."""
    for f in FEEDS.values():
        state = "[green]configured[/]" if f.url else "[yellow]no URL[/]"
        console.print(
            f"  {f.code:<12} {f.platform:<14} gtin={f.gtin_trust:<10} {state}"
        )
    n = len(configured_feeds())
    console.print(f"\n{n}/{len(FEEDS)} feed(s) configured.")


@app.command()
def fetch(
    only: str = typer.Option(None, help="fetch just this one feed (e.g. 'speedway')"),
    fresh: bool = typer.Option(False, "--fresh", help="re-download even if a recent copy exists"),
) -> None:
    """Download each configured feed to the feeds directory."""
    from .fetch import fetch_feed

    feeds = configured_feeds()
    if only:
        feeds = [f for f in feeds if f.code == only]
        if not feeds:
            console.print(f"[red]no configured feed named {only!r}[/]")
            raise typer.Exit(1)
    if not feeds:
        console.print("[yellow]no feeds configured — set FEED_*_URL in .env[/]")
        raise typer.Exit(1)

    dest = _feeds_dir()
    max_age = None if fresh else 3 * 3600
    total_bytes = 0
    economise = 0

    for f in feeds:
        console.print(f"[bold]{f.code}[/] ...", end=" ")
        mark = [0]

        def progress(_code: str, written: int, *, mark: list[int] = mark) -> None:
            if written - mark[0] >= 25 * 1_048_576:
                mark[0] = written
                console.print(_mb(written), end=" ")

        connues = None
        if f.connus_seulement:
            from .db import connect
            with connect() as conn:
                connues = {r[0] for r in conn.execute(
                    "SELECT merchant_sku FROM raw_offer WHERE merchant_id = %s",
                    (f.merchant_id,))}
            # Base vide : filtrer ne garderait rien. On télécharge tout, et on
            # le dit, plutôt que de vider le marchand en silence.
            if not connues:
                console.print("[yellow]aucune offre connue, filtre ignoré[/]", end=" ")
        eans_connus = None
        prix_ref = None
        marques_ref = None
        if f.perimetre:
            from .db import connect
            from .perimetre import cle_gtin
            with connect() as conn:
                # les codes-barres des AUTRES marchands, vivants seulement
                eans_connus = {k for (g,) in conn.execute(
                    "SELECT DISTINCT raw_gtin FROM raw_offer WHERE merchant_id <> %s"
                    " AND is_live AND raw_gtin IS NOT NULL", (f.merchant_id,))
                    if (k := cle_gtin(g))}
                # leur prix median par code-barres, pour le garde-fou de prix
                prix_ref = {}
                for g, med in conn.execute(
                        "SELECT ro.raw_gtin, percentile_cont(0.5) WITHIN GROUP (ORDER BY ph.price)"
                        " FROM raw_offer ro JOIN LATERAL ("
                        "   SELECT price FROM price_history WHERE raw_offer_id = ro.id"
                        "   AND in_stock ORDER BY observed_on DESC LIMIT 1) ph ON true"
                        " WHERE ro.merchant_id <> %s AND ro.is_live AND ro.raw_gtin IS NOT NULL"
                        " AND ph.price > 0 GROUP BY ro.raw_gtin", (f.merchant_id,)):
                    if (k := cle_gtin(g)):
                        prix_ref[k] = float(med)
                # les marques sous lesquelles les autres marchands vendent chaque
                # code-barres, pour ecarter une offre en desaccord (`perimetre.decision`)
                marques_ref = {}
                for g, marques in conn.execute(
                        "SELECT o.gtin, array_agg(DISTINCT sg.brand_code)"
                        " FROM raw_offer o JOIN offer_signature sg ON sg.raw_offer_id = o.id"
                        " WHERE o.merchant_id <> %s AND o.is_live AND o.gtin IS NOT NULL"
                        " AND sg.brand_code IS NOT NULL AND sg.brand_code <> '' GROUP BY o.gtin",
                        (f.merchant_id,)):
                    if (k := cle_gtin(g)):
                        marques_ref[k] = frozenset(marques)
                # le perimetre est monotone : une offre deja admise le reste
                connues = {r[0] for r in conn.execute(
                    "SELECT merchant_sku FROM raw_offer WHERE merchant_id = %s",
                    (f.merchant_id,))}
            console.print(f"[dim]{len(eans_connus):,} codes-barres connus, "
                          f"{len(connues):,} offres déjà admises[/]", end=" ")
        try:
            res = fetch_feed(f, dest, max_age_seconds=max_age, on_progress=progress,
                             connues=connues, eans_connus=eans_connus,
                             prix_ref=prix_ref if f.perimetre else None,
                             marques_ref=marques_ref if f.perimetre else None)
        except Exception as exc:  # noqa: BLE001 — report and keep going
            console.print(f"[red]FAILED[/] {masquer_secrets(exc)}")
            continue

        # Ce qui est compté, c'est ce qui a VRAIMENT transité. Un flux revalidé
        # en 304 pèse zéro : le confondre avec un téléchargement ferait croire
        # qu'on tire 925 Mo à chaque passage, et le total ne servirait plus à
        # rien — c'est justement ce total qu'on cherche à faire baisser.
        if res.unchanged:
            economise += res.bytes
            console.print(f"[dim]inchangé[/] — 304, {_mb(res.bytes)} évités")
        elif res.from_cache:
            console.print(f"[dim]cached[/] ({_mb(res.bytes)})")
        else:
            total_bytes += res.bytes
            console.print(f"[green]ok[/] {_mb(res.bytes)} in {res.seconds:.0f}s")
            if res.filtre:
                lues, gardees = res.filtre
                console.print(f"  périmètre : {gardees:,} gardées"
                              f" sur {lues:,} lues")
            if res.raisons:
                console.print("  par raison : " + ", ".join(
                    f"{k} {v:,}" for k, v in sorted(res.raisons.items(), key=lambda x: -x[1])))

    console.print(f"\n{_mb(total_bytes)} téléchargés dans {dest}/")
    if economise:
        console.print(f"[dim]{_mb(economise)} évités : les marchands ont confirmé"
                      f" que leur fichier n'avait pas changé.[/]")


@app.command()
def load(
    only: str = typer.Option(None, help="load just this one feed"),
) -> None:
    """Load the downloaded feed CSVs into the `stg_feed_row` staging table."""
    from .load import load_feed

    feeds = configured_feeds()
    if only:
        feeds = [f for f in feeds if f.code == only]
        if not feeds:
            console.print(f"[red]no configured feed named {only!r}[/]")
            raise typer.Exit(1)

    dest = _feeds_dir()
    total = 0
    for f in feeds:
        console.print(f"[bold]{f.code}[/] ...", end=" ")
        try:
            res = load_feed(f, dest / f"{f.code}.csv")
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]FAILED[/] {masquer_secrets(exc)}")
            continue
        total += res.rows
        console.print(f"[green]ok[/] {res.rows:,} rows in {res.seconds:.0f}s")

    console.print(f"\n{total:,} rows staged.")


@app.command()
def normalize(
    only: str = typer.Option(None, help="normalize just this one feed"),
    force: bool = typer.Option(
        False, "--force", help="override the retirement circuit-breaker"
    ),
) -> None:
    """Map staged feed rows into typed `raw_offer` records (upsert + freshness)."""
    from .normalize import normalize_feed

    feeds = configured_feeds()
    if only:
        feeds = [f for f in feeds if f.code == only]
        if not feeds:
            console.print(f"[red]no configured feed named {only!r}[/]")
            raise typer.Exit(1)

    for f in feeds:
        console.print(f"[bold]{f.code}[/] ...", end=" ")
        try:
            res = normalize_feed(f, force=force)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]FAILED[/] {masquer_secrets(exc)}")
            continue
        extra = f", {res.gtin_rejected:,} bad GTINs dropped" if res.gtin_rejected else ""
        if res.hors_perimetre:
            extra += f", {res.hors_perimetre:,} hors périmètre écartées"
        console.print(
            f"[green]ok[/] {res.upserted:,} offers, {res.retired:,} retired{extra}"
            f" in {res.seconds:.0f}s"
        )


@app.command()
def signature(
    only: str = typer.Option(None, help="signature for just this one feed"),
) -> None:
    """Compute one normalized `offer_signature` per raw offer (no matching yet)."""
    from .feeds import FEEDS
    from .signature import compute_signatures

    mid = None
    if only:
        if only not in FEEDS:
            console.print(f"[red]no feed named {only!r}[/]")
            raise typer.Exit(1)
        mid = FEEDS[only].merchant_id

    console.print("computing signatures ...", end=" ")
    res = compute_signatures(mid)
    console.print(f"[green]ok[/] {res.rows:,} signatures in {res.seconds:.0f}s")


@app.command()
def categorize(
    remap: bool = typer.Option(
        False, "--remap",
        help="re-run the rules over the paths currently filed as 'unknown'",
    ),
    remap_ids: str = typer.Option(
        "", "--remap-ids",
        help="re-run the rules over paths currently in these category ids, "
             "comma-separated (e.g. --remap-ids 1 after a rule change that "
             "pulls offers OUT of the generic helmet bucket)",
    ),
) -> None:
    """Seed the category taxonomy and classify every merchant category path.

    `--remap` est à lancer après avoir ajouté une règle : sans lui, un chemin
    déjà rangé en « non classé » y reste, et la règle neuve ne sert à rien.
    `--remap-ids` fait la même chose pour n'importe quelle autre catégorie
    déjà peuplée — utilisé le 29/09/2026 pour ressortir les accessoires
    casque de la catégorie 1 après leur avoir donné la 30.
    """
    from .category import categorize as run_categorize

    ids = {int(x) for x in remap_ids.split(",") if x.strip()}
    console.print("categorizing ...", end=" ")
    res = run_categorize(remap_unknown=remap, remap_categories=ids)
    console.print(
        f"[green]ok[/] {res.categories_seeded} categories, "
        f"{res.paths_mapped:,} new paths mapped in {res.seconds:.0f}s"
    )


@app.command()
def match(
    reset: bool = typer.Option(
        False, "--reset", help="undo a previous match run first (dev/re-run only)"
    ),
    sans_mpn: bool = typer.Option(
        False, "--sans-mpn",
        help="laisser de côté la passe préfixe Maxxess/Moto-Axxe "
             "(à rejouer ensuite par ops/appliquer_mpn.py)",
    ),
) -> None:
    """Cluster raw offers into products (GTIN + item_group_id, v1 scope)."""
    from .category import categorize as run_categorize
    from .match import reset_match_state, run_match

    if reset:
        console.print("resetting previous match state ...", end=" ")
        reset_match_state()
        console.print("[green]ok[/]")

    console.print("categorizing ...", end=" ")
    cres = run_categorize()
    console.print(f"[green]ok[/] {cres.paths_mapped:,} paths mapped")

    # Pré-vol : PostgreSQL analyse chaque requête sans l'exécuter. Une faute de
    # syntaxe dans la DERNIÈRE instruction d'un `match` coûte trois quarts
    # d'heure, puisque la transaction annule tout — c'est arrivé le 14/09/2026,
    # sur une jointure que PostgreSQL refuse dans un UPDATE. Deux secondes ici
    # valent mieux que quarante minutes plus loin.
    console.print("vérification des requêtes ...", end=" ")
    import subprocess

    pre = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[2] / "ops" / "valide_sql.py")],
        capture_output=True, text=True,
    )
    if pre.returncode != 0:
        console.print("[red]refusé[/]")
        console.print(pre.stdout[-2000:])
        raise typer.Exit(1)
    console.print("[green]ok[/]")

    console.print("matching ...", end=" ")
    if sans_mpn:
        console.print("[yellow]passe préfixe Maxxess/Moto-Axxe laissée de côté[/] "
                      "— à rejouer ensuite : python ops/appliquer_mpn.py")
    res = run_match(avec_mpn=not sans_mpn)
    console.print(
        f"[green]ok[/] {res.products_created:,} products, {res.variants_created:,} variants — "
        f"{res.offers_linked_gtin:,} offers via GTIN, {res.offers_linked_item_group:,} via "
        f"item_group, {res.gtin_conflicts} GTIN conflicts sent to review in {res.seconds:.0f}s"
    )
    console.print(
        f"  replis d'identité — genre : {res.replis_genre:,} unité(s), "
        f"modèle : {res.replis_modele:,} unité(s)"
    )
    if res.replis_genre_2:
        console.print(
            f"  [yellow]attention : le repli du genre n'est pas stable "
            f"({res.replis_genre_2:,} unité(s) au second passage)[/]"
        )
    console.print(
        f"  Maxxess + Moto-Axxe rattachés par identité exacte : "
        f"{res.offers_linked_identite:,} offre(s) par identité exacte, "
        f"{res.offers_linked_mpn:,} par référence fabricant"
    )
    console.print(
        f"  pièces séparées d'une fiche fourre-tout : "
        f"{res.pieces_decoupees:,} unité(s)"
    )
    if res.offres_ecartees:
        console.print(
            f"  offres d'un marchand neuf écartées (en désaccord avec les autres) : "
            f"{res.offres_ecartees:,}"
        )
    if res.groupes_separes or res.offres_detachees:
        console.print(
            f"  prix sans rapport : {res.groupes_separes:,} groupe(s) séparé(s) de leur fiche, "
            f"{res.offres_detachees:,} offre(s) déjà mal rattachée(s) détachée(s) puis reclassée(s)"
        )
    if res.detachement_refuse:
        console.print(
            f"[yellow]  {res.detachement_refuse:,} offre(s) à détacher : au-delà du plafond, "
            f"rien n'a été détaché — à examiner à la main[/]"
        )

    # Troisieme filet pour les marchands neufs : voir `match._ECARTER_VIOLATIONS_NEUFS`.
    try:
        from .match import ecarter_violations_des_marchands_neufs

        fiches, offres = ecarter_violations_des_marchands_neufs()
        if offres:
            console.print(
                f"  fiches en violation touchant un marchand neuf : {fiches:,} ; "
                f"ses offres en sont retirees : {offres:,}")
    except Exception as exc:  # noqa: BLE001 — le match est fait, on le dit
        console.print(f"[yellow]nettoyage des violations des marchands neufs : echec ({exc})[/]")

    # Advisory only: never let a verify-side bug or a real violation turn a
    # successful match run into a failure the user can't unblock. `mcpipe
    # verify` is the command that actually exits non-zero.
    try:
        from .verify import check_match_invariants

        violations = check_match_invariants()
        if violations:
            vivantes = sum(1 for v in violations if v.vivante)
            console.print(
                f"[yellow]verify: {len(violations)} invariant violation(s) found "
                f"({vivantes} sur offres vivantes) — run `mcpipe verify` for details[/]"
            )
        else:
            console.print("verify: [green]0 invariant violations[/]")
    except Exception as exc:  # noqa: BLE001 — reporting only, must not fail the run
        console.print(f"[yellow]verify: skipped ({exc})[/]")


@app.command("ecarter-violations")
def ecarter_violations() -> None:
    """Retire des fiches en violation les offres des marchands neufs (voir `match`).

    A lancer sur une base deja appariee, sans refaire le `match` ; suivre de
    `relier-tailles` puis `freshness`."""
    from .match import ecarter_violations_des_marchands_neufs

    console.print("fiches en violation touchant un marchand neuf ...", end=" ")
    fiches, offres = ecarter_violations_des_marchands_neufs()
    console.print(f"[green]ok[/] {fiches:,} fiche(s), {offres:,} offre(s) retiree(s)")


@app.command("relier-tailles")
def relier_tailles() -> None:
    """Recalculer les tailles rattachées aux fiches, sans refaire l'appariement.

    À lancer après un `enrich` qui a changé des tailles — un emprunt par
    code-barres, une règle corrigée — quand les fiches, elles, n'ont pas bougé.
    Quelques secondes au lieu des cinquante minutes d'un `match --reset`, et ce
    sont les mêmes instructions.
    """
    from .match import relink_sizes

    console.print("recalcul des tailles rattachées ...", end=" ")
    r = relink_sizes()
    console.print(
        f"[green]ok[/] {r['delies']:,} lien(s) périmé(s) retiré(s), "
        f"{r['variantes_creees']:,} variante(s) créée(s), "
        f"{r['liens_crees']:,} lien(s) posé(s), "
        f"{r['variantes_elaguees']:,} variante(s) sans offre élaguée(s)"
    )


@app.command()
def verify() -> None:
    """Re-check that no `product` mixes category/colour/genre/pack/year/brand
    across its linked offers — a standing regression net for `match`, run
    independently of any specific run."""
    from .verify import check_match_invariants

    console.print("verifying match invariants ...", end=" ")
    violations = check_match_invariants()
    if not violations:
        console.print("[green]ok[/] 0 violations")
        return

    vivantes = [v for v in violations if v.vivante]
    console.print(
        f"[red]{len(violations)} violation(s)[/] dont {len(vivantes)} sur offres "
        f"vivantes ({len(violations) - len(vivantes)} latentes : offres retirées "
        f"encore liées)"
    )
    by_field: dict[str, list[int]] = {}
    for v in violations:
        n = by_field.setdefault(v.field, [0, 0])
        n[0] += 1
        n[1] += v.vivante
    for field, (n, nv) in sorted(by_field.items(), key=lambda kv: -kv[1][0]):
        console.print(f"  {field}: {n} (vivantes {nv})")
    # les vivantes d'abord : ce sont elles que le site affiche
    for v in sorted(violations, key=lambda v: not v.vivante)[:10]:
        console.print(
            f"  product {v.product_id} / {v.field}: {v.distinct_values} "
            f"(offers {v.example_offer_ids[:5]})"
            + ("" if v.vivante else " [latente]")
        )
    raise typer.Exit(1)


@app.command()
def enrich() -> None:
    """Correct coarse feed categories from the title (FC-Moto `tops` -> jacket, ...).

    Rebuilds `offer_category_override`; run BEFORE `match` so the corrected
    categories flow into clustering. Colour/size cascades come later.
    """
    from .enrich import enrich_categories

    console.print("enriching categories from titles ...", end=" ")
    res = enrich_categories()
    from .category import CATEGORIES

    labels = {cid: code for cid, _p, code, _l in CATEGORIES}
    console.print(
        f"[green]ok[/] {res.overrides_written:,} overrides from "
        f"{res.candidates_scanned:,} candidates in {res.seconds:.0f}s"
    )
    for cid, n in sorted(res.by_target.items(), key=lambda kv: -kv[1]):
        console.print(f"  -> {labels.get(cid, cid)}: {n:,}")
    console.print("[dim]by rule: " + ", ".join(
        f"{rule} {n:,}" for rule, n in sorted(res.by_rule.items(), key=lambda kv: -kv[1])
    ) + "[/]")

    # Same idea one field over: read what a neighbour already knows. A merchant
    # that does not send a size is not hiding it — another merchant selling the
    # very same barcode has written it down. Must run before `match`, which
    # builds the variants.
    # Le fourre-tout « Protections » découpé : ce qui protège le pilote, ce qui
    # protège la moto, et ce qui n'était pas une protection du tout.
    from .enrich import split_protections

    console.print("découpe du rayon « Protections » ...", end=" ")
    par_rayon = split_protections()
    noms = {28: "pilote", 29: "moto", 18: "carénage", 24: "accessoires"}
    console.print(f"[green]ok[/] {sum(par_rayon.values()):,} offre(s) rangée(s)")
    for cid, n in sorted(par_rayon.items(), key=lambda kv: -kv[1]):
        console.print(f"  -> {noms.get(cid, cid)}: {n:,}")

    # Accorder les marchands d'un même code-barres : sans cette passe, trois
    # façons d'écrire « protection cervicale » donnent trois rayons, et le
    # pipeline détache la fiche. Voir enrich.py.
    from .enrich import accorder_protections_par_gtin

    console.print("accord des marchands sur un même code-barres ...", end=" ")
    rallies = accorder_protections_par_gtin()
    console.print(f"[green]ok[/] {rallies:,} offre(s) ralliée(s)")

    from .enrich import borrow_sizes

    console.print("borrowing missing sizes from the same barcode ...", end=" ")
    borrowed = borrow_sizes()
    console.print(f"[green]ok[/] {borrowed:,} offers given a size")
    console.print("[dim]now run `mcpipe match --reset` to apply.[/]")


@app.command()
def caracteristiques() -> None:
    """Relit les descriptions du jour et remplit les caracteristiques.

    A lancer APRES `match` : l'etape travaille par FICHE, et une fiche reunit
    les textes de plusieurs marchands. Elle lit les fichiers de flux sur le
    disque — les descriptions ne sont pas en base, voir la note du module.
    """
    from .caracteristiques import calculer

    console.print("lecture des descriptions ...", end=" ")
    fiches, lignes = calculer()
    console.print("[green]ok[/]")
    console.print(f"  fiches renseignees : {fiches:,}")
    console.print(f"  caracteristiques ecrites : {lignes:,}")
    if fiches:
        console.print(f"  moyenne : {lignes / fiches:.2f} par fiche")


@app.command()
def sharp(
    limite: int = typer.Option(0, help="ne relever que les N premieres fiches"),
) -> None:
    """Releve les fiches SHARP : note de securite et POIDS PESE des casques.

    SHARP est le programme d'essais du ministere des transports britannique. Il
    achete les casques, les detruit sur 32 scenarios de choc, et publie une note
    de 1 a 5 etoiles avec le poids mesure. Aucun de nos six marchands ne porte
    cette donnee.

    585 fiches a une demi-seconde : compter cinq minutes. Le relevé se refait
    une fois par mois, pas une fois par jour — rien ne bouge plus vite que les
    essais eux-memes.

    Cette commande RELEVE seulement. Le rapprochement avec nos fiches produit
    est une etape separee : voir `sql/024_source_sharp.sql`.
    """
    from .sources import sharp as src

    fiches = src.relever(limite=limite or None, trace=console.print)
    n = src.enregistrer(fiches)
    notes = sum(1 for f in fiches if f.etoiles)
    poids = sum(1 for f in fiches if f.poids_g)
    console.print(f"[green]ok[/] {n:,} fiches enregistrees")
    console.print(f"  avec une note : {notes:,}")
    console.print(f"  avec un poids pese : {poids:,}")
    console.print("[dim]donnees SHARP / Department for Transport, "
                  "Open Government Licence — l'attribution est obligatoire.[/]")


@app.command("sharp-rapprocher")
def sharp_rapprocher() -> None:
    """Colle les mesures SHARP sur les fiches casque qu'on sait identifier.

    Separe du releve, et rejouable sans retourner chercher les 585 pages : le
    releve est exact, le rapprochement est approximatif et se reglera plusieurs
    fois.

    La regle tient en une phrase : on prefere une fiche muette a une fiche qui
    porte la note d'un autre modele. Les egalites ne sont pas tranchees.
    """
    from .sources.rapprochement import rapprocher

    fiches, valeurs, ambigues, accessoires, formes = rapprocher(
        trace=console.print)
    console.print(f"[green]ok[/] {fiches:,} fiches rapprochees, "
                  f"{valeurs:,} valeurs ecrites")
    if ambigues:
        console.print(f"  [yellow]{ambigues:,} fiches ecartees[/] : plusieurs "
                      "modeles SHARP collaient au meme titre")
    if accessoires:
        console.print(f"  [yellow]{accessoires:,} fiches ecartees[/] : coiffes, "
                      "ecrans, mentonnieres — des pieces, pas des casques")
    if formes:
        console.print(f"  [yellow]{formes:,} fiches ecartees[/] : SHARP ne teste "
                      "ni les jets ni les cross, et un modulable n'est pas un "
                      "integral")


@app.command()
def revendeur(
    limite: int = typer.Option(0, help="ne relever que les N premieres fiches"),
) -> None:
    """Releve les fiches du revendeur : matiere, coques, fermeture, poids.

    Un revendeur, pas un organisme public — ce n'est pas SHARP. Ce qu'on en
    garde est factuel (tableau technique genere par leur boutique) ou lu avec
    la meme prudence qu'une description marchande (poids, homologation, en
    prose). Jamais leur texte de vente, jamais leurs notes editoriales.

    Parcourt les cinq pages de categorie du rayon casque, paginees. Compter
    plusieurs dizaines de minutes : c'est un site plus grand que SHARP, et on
    y va plus doucement.
    """
    from .sources import revendeur as src

    fiches = src.relever(limite=limite or None, trace=console.print)
    n = src.enregistrer(fiches)
    matiere = sum(1 for f in fiches if f.matiere)
    poids = sum(1 for f in fiches if f.poids_g)
    homolog = sum(1 for f in fiches if f.homologation)
    console.print(f"[green]ok[/] {n:,} fiches enregistrees")
    console.print(f"  avec une matiere : {matiere:,}")
    console.print(f"  avec un poids (lu en prose) : {poids:,}")
    console.print(f"  avec une homologation (lue en prose) : {homolog:,}")


@app.command("revendeur-rapprocher")
def revendeur_rapprocher() -> None:
    """Colle les caracteristiques du revendeur sur les fiches casque qu'on identifie.

    Le revendeur n'a pas de modele propre : une page par coloris. Le rapprochement
    compare donc les deux titres apres avoir retire la couleur des DEUX cotes,
    avec le meme vocabulaire de couleur que le pipeline — voir
    sources/rapprochement_revendeur.py.
    """
    from .sources.rapprochement_revendeur import rapprocher

    fiches, valeurs, ambigues, accessoires = rapprocher(trace=console.print)
    console.print(f"[green]ok[/] {fiches:,} fiches rapprochees, "
                  f"{valeurs:,} valeurs ecrites")
    if ambigues:
        console.print(f"  [yellow]{ambigues:,} fiches ecartees[/] : plusieurs "
                      "fiches du revendeur collaient au meme titre")
    if accessoires:
        console.print(f"  [yellow]{accessoires:,} fiches ecartees[/] : ce "
                      "n'etait pas un casque")


@app.command("marchands-figes")
def marchands_figes(
    jours: int = typer.Option(3, help="fenetre d'observation, en jours"),
) -> None:
    """Quels flux ne bougent plus ?

    Un flux mort ne leve aucune erreur : il se telecharge, se charge et
    s'affiche comme les autres, avec des prix perimes. On le repere au
    MOUVEMENT du catalogue — arrivees et retraits — parce qu'un marchand peut
    legitimement ne changer aucun prix pendant une semaine calme, mais pas
    cesser d'avoir la moindre rupture ni le moindre reassort.
    """
    from .vitalite import mesurer

    lignes = mesurer(jours)
    console.print(f"mouvement du catalogue sur {jours} jours")
    console.print()
    console.print(f"  {'marchand':<14}{'offres':>10}{'retirees':>10}"
                  f"{'arrivees':>10}{'prix':>8}   etat")
    alerte = 0
    for v in lignes:
        if v.fige and not v.affiche:
            # Deja traite : ce n'est plus une alerte, c'est un constat. Le
            # compter comme alerte ferait clignoter en rouge une decision
            # deja prise, et on finirait par ne plus regarder le rouge.
            etat, couleur = "fige, deja ecarte", "yellow"
        elif v.fige:
            etat, couleur = "FIGE", "red"
            alerte += 1
        elif not v.affiche:
            etat, couleur = "ecarte, reparti", "yellow"
        else:
            etat, couleur = "vivant", "green"
        console.print(f"  {v.code:<14}{v.offres:>10,}{v.retirees:>10,}"
                      f"{v.arrivees:>10,}{v.prix_changes:>8,}   "
                      f"[{couleur}]{etat}[/]")
    console.print()
    for v in lignes:
        if v.fige and v.affiche:
            console.print(f"  [red]{v.code} est fige ET affiche sur le site.[/] "
                          f"Derniere arrivee : {v.dernier_mouvement}.")
        elif not v.fige and not v.affiche:
            console.print(f"  [green]{v.code} bouge de nouveau[/] et reste ecarte.")
            console.print("  Pour le remettre :")
            console.print(f"      UPDATE merchant SET affiche = true "
                          f"WHERE code = '{v.code}';")
            console.print("      SELECT refresh_product_stats();")
    if not alerte:
        console.print("  aucun flux fige.")


@app.command()
def freshness() -> None:
    """Expire stale offers, append today's prices, recompute each product's
    headline price. Run after `match`; safe to re-run."""
    from .freshness import FRESHNESS_WINDOW, run_freshness

    console.print(f"applying freshness (window: {FRESHNESS_WINDOW}) ...", end=" ")
    res = run_freshness()
    console.print(f"[green]ok[/] in {res.seconds:.0f}s")
    console.print(f"  offers fresh: {res.offers_fresh:,}   expired: {res.offers_expired:,}")
    console.print(f"  price history rows written: {res.history_rows:,}")
    console.print(
        f"  headline prices set: {res.prices_set:,}   cleared: {res.prices_cleared:,}"
    )
    console.print(
        f"  products marked stale: {res.products_stale:,}   revived: {res.products_revived:,}"
    )


@app.command()
def alertes() -> None:
    """Préviennent par e-mail les alertes de prix atteintes. Après `freshness`.

    Efface d'abord les demandes non confirmées (7 jours) et les alertes
    échues (6 mois). Sans SMTP configuré, n'envoie rien et sort sans erreur ;
    une panne d'envoi non plus ne fait pas échouer la chaîne de nuit.
    """
    from .alertes import run_alertes

    res = run_alertes()
    console.print(f"alertes : {res.effacees} effacée(s) (non confirmées ou échues)")
    if not res.smtp:
        console.print("  [yellow]SMTP non configuré[/] : aucun e-mail envoyé")
        return
    console.print(f"  examinées : {res.examinees}   envoyées : {res.envoyees}   "
                  f"échecs d'envoi : {res.echecs}   ({res.seconds:.0f}s)")
    if res.echecs:
        console.print("  [yellow]des e-mails ne sont pas partis[/] : ils seront "
                      "retentés la nuit prochaine (rien n'a été marqué envoyé)")


@app.command()
def promo() -> None:
    """Read the merchants' own promo pages and refresh `code_promo`.

    Independent of the catalogue stages: it touches no offer and no product, so
    it can run while the site is up, and on its own schedule (the v1 ran it once
    a day). Codes that vanished from the merchant's page are withdrawn, not
    deleted; codes typed by hand in the admin screen are never touched.
    """
    from .promo import scan

    console.print("reading the merchants' promo pages ...\n")
    reports = scan()
    total = 0
    for r in reports:
        console.print(f"[bold]{r.merchant}[/]")
        for line in r.pages:
            console.print(f"    [dim]{line}[/]")
        for line in r.kept:
            console.print(f"    [green]{line}[/]")
            total += 1
        for line in r.ignored:
            console.print(f"    [yellow]{line}[/]")
        if not r.kept:
            console.print("    [dim]aucun code détecté[/]")
    console.print(f"\n[green]ok[/] {total} code(s) en cours")


@app.command()
def publish() -> None:
    """Build wp_pc_*_next and swap. Gated by PUBLISH_MODE. [not implemented]"""
    raise typer.Exit(_todo("publish"))


@app.command()
def run() -> None:
    """Run every stage in order. [not implemented]"""
    raise typer.Exit(_todo("run"))


def _todo(stage: str) -> int:
    console.print(f"[yellow]`{stage}` is not implemented yet.[/] See docs/roadmap.md")
    return 1


if __name__ == "__main__":
    app()


@app.command()
def consolider(
    proposer: bool = typer.Option(True, "--proposer/--pas-proposer",
                                  help="calculer les groupes de fiches a regrouper"),
    appliquer: bool = typer.Option(False, "--appliquer",
                                   help="fusionner les groupes valides (et les proposes si fusion_auto=oui)"),
) -> None:
    """Regrouper les fiches qui se dedoublent pour un meme code-barres.

    `--proposer` (defaut) ne modifie rien : il ecrit les groupes dans
    `fusion_proposee`, que la proprietaire valide dans l'ecran d'administration.
    `--appliquer` fusionne ce qui est valide. A lancer AVANT `relier-tailles` et
    `freshness`, qui recreent les variantes et recalculent les prix.
    """
    from . import consolider as c

    if proposer:
        r = c.proposer()
        console.print(
            f"[green]ok[/] {r['gtins_eclates']:,} codes-barres eclates sur plusieurs "
            f"fiches, {r['groupes']:,} groupes, {r['retenus']:,} retenus "
            f"({r['ecartes_trop_gros']:,} ecartes car trop gros), "
            f"{r['nouveaux']:,} nouveaux")
    if appliquer:
        r = c.appliquer()
        console.print(f"[green]ok[/] {r['groupes']:,} groupes appliques, "
                      f"{r['fiches_fusionnees']:,} fiches fusionnees")


@app.command()
def couverture() -> None:
    """Recalcule quelles fiches n'ont pas de matiere, de saison ou d'homologation.

    Alimente l'ecran « Caracteristiques » de l'administration. A lancer apres
    `caracteristiques`.
    """
    from .couverture import recalculer

    r = recalculer()
    console.print(f"[green]ok[/] {r['fiches_incompletes']:,} fiches comparables "
                  f"avec au moins une caracteristique manquante")


@app.command()
def taches() -> None:
    """Execute la plus ancienne demande de calcul faite dans l'administration.

    Lance chaque minute par un minuteur systeme ; une seule tache a la fois, et
    jamais pendant le releve de nuit.
    """
    from .taches import executer_une

    console.print(executer_une())


@app.command("importer-web")
def importer_web(
    extraction: str = typer.Argument(..., help="JSON de l'agent qui extrait"),
    verification: str = typer.Argument(..., help="JSON de l'agent qui reverifie"),
    exclure: str = typer.Option("", help="product_id a ecarter, separes par des virgules"),
) -> None:
    """Ecrit les caracteristiques lues sur le web ET confirmees par un second agent."""
    from .importer_web import importer

    ids = {int(x) for x in exclure.split(",") if x.strip().isdigit()}
    r = importer(extraction, verification, ids)
    console.print(f"[green]ok[/] {r['retenues']} valeurs retenues, {r['ecrites']} ecrites, "
                  f"{r['refusees']} refusees")


@app.command("accessoires-casque")
def accessoires_casque(
    appliquer: bool = typer.Option(False, "--appliquer", help="ecrire ; sans cela, on compte seulement"),
) -> None:
    """Range en accessoires les fiches casque, bottes, gants, blousons et pantalons qui n'en sont pas."""
    from .accessoires import ranger_accessoires

    res = ranger_accessoires(appliquer)
    for nom, r in res.rayons.items():
        console.print(f"[bold]{nom}[/] : {r.fiches:,} fiches examinees, {r.a_ranger:,} ne sont que des pieces, "
                      f"{r.mixtes:,} melangent pieces et vrais produits (laissees)")
        for titre in r.exemples[:6]:
            console.print(f"    - {titre}")
        if r.plus_chers:
            console.print("    les plus chers (a relire : une piece coute peu) :")
            for ligne in r.plus_chers[:6]:
                console.print(f"    - {ligne}")
    if appliquer:
        console.print(f"[green]ok[/] {res.rangees:,} fiches rangees")
    else:
        console.print("[dim]rien d'ecrit : relancer avec --appliquer[/]")
