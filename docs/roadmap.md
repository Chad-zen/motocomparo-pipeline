# Roadmap

Phased so each step is independently useful and reversible. Effort = focused days.

| phase | goal | effort | done? |
|---|---|---|---|
| **0** | Repo + schema + local Postgres running; feed URLs collected | 2–3 d | in progress |
| **1** | `fetch → load → normalize` working on all 5 real feeds | 4–6 d | |
| **2** | `match` (GTIN + item_group + base-SKU stages) + `enrich` | 5–8 d | |
| **3** | `freshness` + price history; `publish` in **shadow** mode | 4–6 d | |
| **4** | Diff shadow output vs the live catalog until it's explained | 3–5 d | |
| **5** | Fuzzy stage for Maxxess / Moto-Axxe *(optional — can ship without)* | 3–5 d | |
| **6** | Cutover: `publish` live, retire the v1 import | 2–3 d | |
| **7** | VPS + systemd timers + healthchecks alerting | 2 d | |

**~3.5–4.5 weeks** without the fuzzy stage, **~5–7 weeks** with it. The recommendation
is to ship phases 0–4 + 6–7 first (covers 3 of 5 merchants and essentially all live
offers), then add phase 5 as a fast-follow.

## Current status

- [x] repo skeleton, package layout, CLI stub
- [x] core schema (`sql/001_schema.sql`)
- [x] feed definitions (`src/mcpipe/feeds.py`), column maps verified against the 5 live headers
- [x] `.env` filled with real feed URLs — all 5 return HTTP 200
- [ ] local PostgreSQL running, schema applied
- [ ] `mcpipe fetch` implemented
