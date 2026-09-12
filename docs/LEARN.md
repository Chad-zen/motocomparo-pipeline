# Learning notes

Plain-language notes on how the project works — for me, to be able to explain it and
work on it directly. Grows as the project does.

Last updated: 2026-09-12 (end of phase 2).

## The mental model

A **pipeline** is a series of steps, each taking the output of the last:

```
fetch     → download the 6 CSV feeds to disk
load      → copy those CSVs into temporary ("staging") database tables
normalize → turn raw feed rows into clean `raw_offer` rows (one per merchant product)
signature → read each offer: its brand, colour, size, model words, men's/women's, year
categorize→ map each merchant's own shelf name onto our 25 categories
enrich    → fix categories the merchant got wrong or left too vague
match     → figure out which offers are the same real product → group them
verify    → re-check, independently, that no product mixes two different things
freshness → mark offers that vanished from a feed as gone; recompute cheapest price
publish   → write the finished catalog into the WordPress database
```

Each step is a command: `mcpipe fetch`, `mcpipe load`, etc. Running them one at a time
is how you debug. `mcpipe run` (not built yet) will do them all in order.

**Order matters in one non-obvious place:** `enrich` runs *before* `match`, not after.
It corrects each offer's category, and `match` reads those corrections when it decides
what groups with what.

## The one idea the whole project rests on

**A product is: brand × model × colour × men's/women's.**
**Size is never part of that — it's a variant.**

So a black Shoei helmet in S, M and L is **one** product page with three sizes, not
three pages. That single rule is what separates v2 from v1 (see `v1-retrospective.md`:
v1 published one page per barcode, so the same jacket appeared eight times).

*One caveat, because the code and the decision disagree today:* the code still counts
the **model year** as part of that identity, so a helmet listed as 2023 and the same one
listed as 2026 are two pages. The owner's rule says it should not — the same helmet
ships for years unchanged, the barcode is what identifies it, and the buyer takes the
cheapest (`product-decisions.md`). Measured: 199 review-queue groups and 349 duplicate
pages, small because only 2.5% of products carry a year at all. Fix noted in
`roadmap.md`, not applied yet — the year gate was itself put there to fix a real bug, so
it gets its own measured pass.

## The rule that decides every hard call

**A false merge costs 10 to 50× more than a missed merge.**

A false merge means two different items share one page — so the site shows a price that
doesn't belong to the product the visitor is looking at. That is the one thing a price
comparison site cannot do. A missed merge just means a product isn't compared yet:
disappointing, not damaging.

So whenever the pipeline is unsure, it **refuses to merge** and puts the case in a review
queue (`match_review_queue`) instead of guessing.

## The pieces

| thing | what it is | why |
|---|---|---|
| **Python** | the language the pipeline is written in | best tools for wrangling data |
| **PostgreSQL** | the database — on the PC today, on the VPS later | where every intermediate result lives; SQL does most of the real work |
| **`src/mcpipe/`** | the Python code, one file per step | |
| **`sql/`** | table definitions + transforms, numbered so they run in order | |
| **`tests/`** | automated checks that run in seconds | catch a broken change before it reaches the site |
| **`.env`** | secret settings (feed URLs, database password) — never committed | |
| **git / GitHub** | version history + the public home of the project | a recruiter reads the README and the code here |

## Where things run

- **The VPS** runs the pipeline: PostgreSQL, the calculations, the scheduling.
- **The shared host** keeps running the WordPress site: the design, the pages, SEO.
- WordPress only ever **receives the finished catalog**. It never computes it.

That split *is* the fix for what killed v1: a shared host cuts off any web request after
2-3 minutes, and a 375 MB feed cannot be parsed in that window. Moving the calculation
off the web request is the whole point.

## Where the project stands (end of phase 2)

| | |
|---|---|
| Offers taken in from 6 merchants | 763,570 |
| Distinct products after grouping | 244,378 |
| Products with **2+ merchants** (a real price comparison) | 24,664 |
| Products publishable (they have a colour) | 110,983 |
| Groups held in the review queue rather than guessed | 17,291 |
| Automated checks | 63 tests, `verify` at 0 violations |

Why only 24,664 comparable out of 244,378: merchants mostly sell **different** things.
Out of 426,843 validated barcodes, only 79,199 are shared by two merchants or more — and
those collapse into ~24,664 products once each product's sizes are grouped. The rest are
sold by a single merchant, so there is nothing to compare (they are still published, but
kept out of site navigation — see `product-decisions.md`).

Phases 0, 1 and 2 are done. Phase 3 (freshness + publish in shadow mode) is next.

## Everyday commands

```
mcpipe fetch            # download the feeds
mcpipe load             # into staging
mcpipe normalize        # into raw_offer
mcpipe signature        # read brand/colour/size/model from each offer
mcpipe enrich           # fix coarse merchant categories        (before match!)
mcpipe match --reset    # rebuild the grouping from scratch     (~10 min)
mcpipe verify           # independent re-check, must say 0 violations
```

Before committing anything:

```
.venv\Scripts\python -m pytest -q      # tests, must be all green
.venv\Scripts\python -m ruff check src tests   # code style
```

`psql` is not on the PATH; it lives at
`C:\Program Files\PostgreSQL\18\bin\psql.exe`.

## git, the 30-second version

- `git add <files>` — stage the files you changed
- `git commit -F <file>` — save a snapshot, with the message read from a file
- `git push` — send those snapshots to GitHub
- `git log --oneline` — see the history
- `git status -sb` — what's changed, and whether you're ahead of GitHub

Each commit is a checkpoint you can return to. The history *is* the story of the build.

## Three traps worth remembering

**One session owns the database at a time.** Two Claude sessions (or a session and
its own subagents) pointing at `mcpipe` will block each other — and if one of them
*writes*, the other's measurements are wrong without anyone noticing. Before any long
rebuild, check nobody else is connected:
`SELECT pid, application_name, state, query FROM pg_stat_activity WHERE datname='mcpipe'`.
Three seconds, and it would have saved two hours once.

**Never wrap a `psql` command in a `timeout`.** The client dies but the server keeps
running the query — and it keeps holding its locks. That once blocked a rebuild for two
hours. To diagnose: `SELECT pid, state, wait_event_type, now()-query_start, query FROM
pg_stat_activity`. A `Lock` in `wait_event_type` is the blocked one; the oldest query is
the culprit. `pg_cancel_backend(pid)` releases it.

**Don't run heavy queries while `match` is rebuilding.** It has to lock whole tables, and
anything else touching them makes it wait indefinitely.

## Questions I had (answers as we go)

- *Why not just fix the WordPress version?* → see `v1-retrospective.md`
- *Why Postgres and not the WordPress database directly?* → the WP database is on shared
  hosting (slow, size-limited, and the site reads from it constantly). Postgres is our
  workspace; WordPress only gets the final result.
- *Why does the pipeline refuse to merge things so often?* → see "the rule that decides
  every hard call" above. The review queue is a feature, not a backlog of failures.
- *Where are the business rules — the ones the code can't work out on its own?* →
  `product-decisions.md`. Matte and gloss are different products, a price older than 24h
  is not shown, nothing is ever removed from the site, and so on.
