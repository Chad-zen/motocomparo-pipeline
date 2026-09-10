# motocomparo-pipeline

A data pipeline that ingests motorcycle-gear product feeds from 5 merchants, normalizes
and de-duplicates roughly a million merchant SKUs into a clean product catalog, and
publishes it to a storefront.

**Status:** early build (v2 rewrite). See [docs/roadmap.md](docs/roadmap.md).

---

## The problem

`motocomparo.com` is a French motorcycle-gear price-comparison site. Five merchants each
expose a product feed (CSV, 20 MB to 375 MB). The same physical product — say a *Shoei
Glamster helmet, black, size M* — appears:

- in several feeds, under different titles, sometimes different (or wrong) barcodes;
- once per size, so one helmet colourway is 6–8 near-identical rows;
- with colour/size present in some feeds and completely absent in others.

The job of this pipeline: turn that mess into **one catalog entry per (model + colour)**,
with sizes as variants and every merchant attached as an offer, refreshed daily, with a
price history — and hand it to the website without breaking it.

Hard parts, and how they're handled: [docs/architecture.md](docs/architecture.md).

## Context — why there is a "v1" and a "v2"

v1 was a prototype built directly inside the site's WordPress/WooCommerce install (all
logic in ~90 PHP snippets). It was the fast, zero-budget way to get something live while
learning the domain — first site I'd built. It worked, but it hit real limits:

- feed ingestion ran inside PHP web requests → the 375 MB feed never finished parsing
  before the host killed the request;
- scheduling depended on WordPress cron on shared hosting → the pipeline stalled silently
  for days;
- ~90 interdependent snippets with hand-rolled state machines and locks → one missing
  function froze everything.

Once the domain was clear, the limits of that approach were obvious. This repository is
the redesign: **the data pipeline as a standalone service**, with a real relational
database, a streaming feed parser, proper scheduling and monitoring. The storefront
(WordPress) stays; only the engine behind it changes.

Honest one-page retrospective: [docs/v1-retrospective.md](docs/v1-retrospective.md).

---

## Architecture at a glance

```
merchant feeds (5 × CSV)
        │  fetch      stream to disk, verify size/columns
        ▼
   staging tables    COPY into Postgres, 10k-row batches
        │  normalize  one row per merchant SKU, parse price, fold text
        ▼
   raw_offer
        │  match      GTIN → item_group_id → base-SKU+attrs → fuzzy
        ▼            (ambiguous cases → review queue, never guessed)
   product / variant / offer_variant_link
        │  enrich     colour, size, category (feed → title → cross-merchant vote)
        │  freshness  expire unseen offers, recompute min price, append price_history
        ▼
   publish           build wp_pc_*_next in the WP database, atomic RENAME swap
```

- **Language:** Python 3.12+
- **Store:** PostgreSQL 18 (system of record; the WordPress MySQL only receives the
  final published tables)
- **Schedule:** systemd timers on a small VPS (dev: run by hand)
- **Transforms:** plain SQL files, run in order

## Repository layout

```
src/mcpipe/        the pipeline package
  config.py        settings (env-driven)
  feeds.py         the 5 merchant feeds: URL, format, column mapping
  fetch.py         download a feed to disk (streaming, resumable)
  load.py          CSV → Postgres staging
  normalize.py     staging → raw_offer
  match/           the matching stages
  enrich.py        colour / size / category derivation
  freshness.py     expire, recompute prices, price history
  publish.py       build + swap the WordPress tables
  cli.py           `mcpipe fetch | load | normalize | match | ... | run`
sql/               schema + transforms, numbered, run in order
tests/             pytest; feed-fixture regression tests
docs/              architecture, roadmap, v1 retrospective, learning notes
feeds_samples/     small anonymized feed samples for tests (no secrets)
```

## Running it locally

Prerequisites: Python 3.12+, and PostgreSQL 18 (native install or Docker).

```bash
cp .env.example .env          # then edit .env
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -e ".[dev]"
mcpipe --help
```

Full setup walkthrough (written for someone new to this): [docs/LEARN.md](docs/LEARN.md).

## License

MIT — see [LICENSE](LICENSE).
