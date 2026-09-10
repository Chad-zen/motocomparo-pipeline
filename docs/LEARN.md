# Learning notes

Plain-language notes on how the project works — for me, to be able to explain it and
work on it directly. Grows as the project does.

## The mental model

A **pipeline** is a series of steps, each taking the output of the last:

```
fetch    → download the 5 CSV feeds to disk
load     → copy those CSVs into temporary ("staging") database tables
normalize→ turn raw feed rows into clean `raw_offer` rows (one per merchant product)
match    → figure out which raw_offers are the same real product → group them
enrich   → fill in colour / size / category
freshness→ mark offers that vanished from a feed as gone; recompute cheapest price
publish  → write the finished catalog into the WordPress database
```

Each step is a command: `mcpipe fetch`, `mcpipe load`, etc. `mcpipe run` does them all
in order. Running them one at a time is how you debug.

## The pieces

| thing | what it is | why |
|---|---|---|
| **Python** | the language the pipeline is written in | best tools for wrangling data |
| **PostgreSQL** | a database that runs on your PC (or the VPS later) | it's where every intermediate result lives; SQL is how most of the real work is done |
| **`src/mcpipe/`** | the Python code, one file per step | |
| **`sql/`** | database table definitions + SQL transforms, numbered so they run in order | |
| **`tests/`** | automated checks that run in seconds | catch a broken change before it reaches the site |
| **`.env`** | secret settings (feed URLs, database password) — never committed to git | |
| **git / GitHub** | version history + the public home of the project | a recruiter reads the README and the code here |

## git, the 30-second version

- `git add .` — stage the files you changed
- `git commit -m "message"` — save a snapshot with a note
- `git push` — send those snapshots to GitHub
- `git log --oneline` — see the history

Each commit is a checkpoint you can return to. The history *is* the story of the build.

## Setup checklist (do this once, together, next session)

1. Install PostgreSQL 16 (native Windows installer) **or** Docker Desktop.
2. `python -m venv .venv` then `.venv\Scripts\activate`
3. `pip install -e ".[dev]"`
4. `copy .env.example .env` and fill in the feed URLs (from the v1 WordPress config)
5. Create the database tables: `psql "%DATABASE_URL%" -f sql/001_schema.sql`
6. `mcpipe feeds` — should list the 5 feeds as "configured"
7. Create an empty repo on github.com, then `git remote add origin <url>` and `git push`

## Questions I had (answers as we go)

- *Why not just fix the WordPress version?* → see `v1-retrospective.md`
- *Why Postgres and not the WordPress database directly?* → the WP database is on shared
  hosting (slow, size-limited, and the site reads from it constantly). Postgres is our
  workspace; WordPress only gets the final result.
