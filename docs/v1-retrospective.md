# v1 retrospective

## What v1 was

A working price-comparison site built entirely inside WordPress + WooCommerce, with all
business logic in ~90 "Code Snippets" (PHP fragments stored in the database). It ingested
the same 5 merchant feeds, created a WooCommerce product per barcode seen at ≥2
merchants, and rendered price comparisons on each product page. It also did SEO work:
de-duplicating size variants into one canonical page with 301 redirects, hiding stale
offers, fixing indexation issues.

It ran. At its peak it had ~59k products and ~95k live offers, and ~23k pages indexed by
Google.

## Why WordPress first

- **No budget.** WordPress + a shared host + a theme was ~5 €/month, all in.
- **Speed to something live.** A recognizable site in days, not weeks.
- **First site.** I hadn't built one before; starting from a running storefront and
  changing it piece by piece was how I learned the domain — how the feeds are shaped,
  where merchants disagree, what "the same product" actually means across 5 catalogs.

Those were the right trade-offs for learning. They stopped being the right trade-offs
once the domain was clear.

## What broke, and why it was structural

| symptom | root cause |
|---|---|
| The 375 MB feed never finished importing | Feed parsing ran inside a PHP **web request**. The shared host kills requests at ~120–180 s. A 375 MB CSV can't be parsed in that window, and the partial-progress checkpointing was too coarse to resume cleanly. |
| The import froze for 3 days, twice | A single undefined function (`pc_assign_category`, lost in a refactor) made the publish step fatal. Every scheduled run crashed at the same point. **Nothing alerted** — it was found by noticing stale prices. |
| Scheduling was unreliable | WordPress cron, triggered by the host's cron, on shared hosting. Jittery, and it silently stopped making progress whenever the state machine deadlocked. |
| Small changes had large blast radius | ~90 snippets sharing global functions, option-row state, and transient locks. No tests. Changing one could break another with no signal until a user (me) hit the broken path. |

None of these are fixed by "write more careful PHP". They're consequences of running a
data pipeline inside a request-scoped CMS on shared hosting.

## What v2 changes

- Feed processing is a **standalone process** — no request timeout. A 375 MB file
  streams through in minutes.
- **PostgreSQL** as the system of record: real constraints, a review queue for
  ambiguous matches, price history, transactional publishes.
- **Explicit, ordered stages** with a CLI — each runnable and inspectable alone.
- **Alerting**: a dead-man switch per feed and a crash handler. A freeze is an email
  within the hour, not a discovery days later.
- **Tests**: feed-fixture regression tests so a merchant changing their format is
  caught before it publishes.
- WordPress keeps doing what it's good at — rendering pages and SEO — and receives only
  the finished catalog.

## What I'd keep from v1

The domain modelling was mostly right: the "1 page = model + colour, size is a variant"
target, the GTIN-trust split, the signature approach to normalization, the
canonical-merge + 301 mechanism for de-duplication. v2 reuses those ideas — it changes
where and how they run, not what they are.
