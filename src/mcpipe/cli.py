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
from .feeds import FEEDS, configured_feeds

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

        try:
            res = fetch_feed(f, dest, max_age_seconds=max_age, on_progress=progress)
        except Exception as exc:  # noqa: BLE001 — report and keep going
            console.print(f"[red]FAILED[/] {exc}")
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
            console.print(f"[red]FAILED[/] {exc}")
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
            console.print(f"[red]FAILED[/] {exc}")
            continue
        extra = f", {res.gtin_rejected:,} bad GTINs dropped" if res.gtin_rejected else ""
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
) -> None:
    """Seed the category taxonomy and classify every merchant category path.

    `--remap` est à lancer après avoir ajouté une règle : sans lui, un chemin
    déjà rangé en « non classé » y reste, et la règle neuve ne sert à rien.
    """
    from .category import categorize as run_categorize

    console.print("categorizing ...", end=" ")
    res = run_categorize(remap_unknown=remap)
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

    # Advisory only: never let a verify-side bug or a real violation turn a
    # successful match run into a failure the user can't unblock. `mcpipe
    # verify` is the command that actually exits non-zero.
    try:
        from .verify import check_match_invariants

        violations = check_match_invariants()
        if violations:
            console.print(
                f"[yellow]verify: {len(violations)} invariant violation(s) found "
                f"— run `mcpipe verify` for details[/]"
            )
        else:
            console.print("verify: [green]0 invariant violations[/]")
    except Exception as exc:  # noqa: BLE001 — reporting only, must not fail the run
        console.print(f"[yellow]verify: skipped ({exc})[/]")


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
        f"{r['liens_crees']:,} lien(s) posé(s)"
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

    console.print(f"[red]{len(violations)} violation(s)[/]")
    by_field: dict[str, int] = {}
    for v in violations:
        by_field[v.field] = by_field.get(v.field, 0) + 1
    for field, n in sorted(by_field.items(), key=lambda kv: -kv[1]):
        console.print(f"  {field}: {n}")
    for v in violations[:10]:
        console.print(
            f"  product {v.product_id} / {v.field}: {v.distinct_values} "
            f"(offers {v.example_offer_ids[:5]})"
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
