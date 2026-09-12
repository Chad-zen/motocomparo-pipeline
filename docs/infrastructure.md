# Infrastructure — what is actually there

Measured 2026-09-13, read-only, from hPanel and from each site's WordPress
"Site Health → Info" page. Everything here was checked, not assumed: an earlier
version of these notes had the two databases the wrong way round and drew the
wrong conclusion from it.

## The two WordPress installs

There are **two** complete WordPress sites, not one.

| | production | staging |
|---|---|---|
| Address | `motocomparo.com` | `staging.motocomparo.com` |
| Database | **`u660903589_8sMNw`** | **`u660903589_4MFbB`** |
| Database size / quota | 2981 / 3072 MB (**97%**) | 3028 / 3072 MB (98.6%) |
| Database created | 2025-12-31 | **2026-09-05** |
| Table prefix | `wp_` | `wp_` |

Same theme (ReHub), same 18 active plugins, same 70 WPCode snippets, same
`MC Flux` v1 plugin. The staging is a full copy made on 2026-09-05.

⚠️ **`4MFbB` is the staging database, not production.** Notes written before
2026-09-13 call it "the main one" — they are wrong. A phpMyAdmin session opened
from the `4MFbB` row is looking at staging, and its MySQL user
(`u660903589_B6jms`) cannot see the production database at all. To reach
production, open phpMyAdmin from the **`8sMNw`** row (user `u660903589_msxBG`).

## Disk is not a constraint. The per-database quota is.

| resource | used | limit | |
|---|---|---|---|
| Disk | 10.95 GB | 50 GB | 22% |
| Inodes (files) | 69,485 | 600,000 | 12% |
| Memory (avg) | 62 MB | 3072 MB | |
| CPU (avg) | 10% | 100% | |

So the plan is **Business Web Hosting**, and there is plenty of disk. The only
wall is that **each MySQL database is capped at 3072 MB**, and both live ones are
within ~50-90 MB of that cap.

Note: each site's WordPress reports a much larger "total installation size"
(13.07 GB for production, 7.55 GB for staging). Those figures overlap — hPanel's
10.95 GB is the authority. There is no hidden pile of leftover feed files; that
hypothesis was raised on 2026-09-13 and disproved the same day.

## A third database exists and is nearly empty

`u660903589_X5EYI` — 7 MB used, unattributed to any site, created 2026-01-02,
user `u660903589_lRakW`. It carries its **own 3072 MB quota**.

The v2 catalogue is estimated at 500-600 MB. It would fit there with room to
spare, without deleting anything from production.

**Open question, not yet tested:** whether WordPress can read tables in a second
database. The MySQL host is the same (`127.0.0.1`), so cross-database queries are
possible in principle, but each Hostinger database has its own user and the
production user would need a grant on `X5EYI`. To be verified before relying on
it.

## The VPS

Provisioned 2026-09-13. This is where the v2 pipeline — and, as decided the same
day, the v2 site itself — will run.

| | |
|---|---|
| Host name | `srv1976533.hstgr.cloud` |
| Plan | Hostinger KVM 1 (annual, paid; payment ref H_50669617) |
| Location | France |
| OS | Ubuntu 24.04 LTS, plain — no control panel |
| Extras | none: no malware scanner, no Docker manager (both declined to keep RAM for PostgreSQL; both can be added later from the VPS dashboard) |
| Expires | 2027-09-12 |
| IP address | *to be filled in once provisioning completes* |

Why 24.04 and not the 26.04 LTS offered as default: 24.04 is the mature LTS that
PostgreSQL's own apt repository and most tooling target. 26.04 was five months old
at the time of the decision. The OS can be reinstalled from hPanel if that proves
wrong.

Why a plain image and not one with a control panel: those install a web server and
a MySQL of their own, neither of which this project needs, and they take the memory
PostgreSQL wants on an entry-level plan.

## What this changes

1. **Cleaning the ~870,000 dead `wp_pc_catalog` rows is no longer a prerequisite
   for anything.** It was only ever about freeing space, and space has three
   other answers now (the VPS, the empty database, the 50 GB disk). The runbook
   stays in `ops/v1-menage-lignes-mortes.sql` for the day it is wanted — and
   note it must be pointed at `8sMNw`, not the database it was written against.
2. **There IS a staging environment.** Earlier notes said there was none and
   that every display snippet therefore had to be tested in production. That was
   wrong, and it removes the main risk hanging over the publish phase: the v2
   display can be built and broken on `staging.motocomparo.com` without a
   visitor or Google ever seeing it.
3. The publish target decision (`docs/architecture.md`: build `wp_pc_*_next` in
   the WordPress database, then an atomic swap) was **already made** and is not
   blocked by space. What remains genuinely undecided is whether a v2 product
   page is a WooCommerce post or a page rendered from our own tables — that is a
   question about `wp_posts` / `wp_postmeta` growth, not about disk.
