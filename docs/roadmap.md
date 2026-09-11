# Roadmap

Phased so each step is independently useful and reversible. Effort = focused days.

| phase | goal | effort | done? |
|---|---|---|---|
| **0** | Repo + schema + local Postgres running; feed URLs collected | 2–3 d | **done** |
| **1** | `fetch → load → normalize` working on all 5 real feeds | 4–6 d | **done** |
| **2** | `signature` → `match` (GTIN + item_group + base-SKU) → `enrich` | 5–8 d | in progress |
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
- [x] core schema (`sql/001-004`)
- [x] feed definitions (`src/mcpipe/feeds.py`), column maps verified against the 6 live headers
- [x] `.env` filled with real feed URLs — all 6 return HTTP 200
- [x] PostgreSQL 18 running locally, `mcpipe` database created, schema applied
- [x] `mcpipe feeds` → 6/6 configured
- [x] `mcpipe fetch` — all 6 feeds download (motoblouz 376 MB in 94 s, streamed;
      truncated-download guard compares bytes received to `Content-Length`)
- [x] `mcpipe load` — 763k feed rows → `stg_feed_row` (JSONB) via COPY
- [x] `mcpipe normalize` — 763k staged rows → 763k `raw_offer` records.
      Stable key per merchant: feed `id` (Speedway, La Bécanerie), `internal
      reference` (Motoblouz), `mpn` (FC-Moto), `md5(merchant product URL)` for
      the id-recycling pair (Maxxess, Moto-Axxe). `raw_gtin` stored verbatim
      for trusted merchants; the separate `gtin` column holds only
      checksum-validated barcodes — that's what `match` will join on
      (529,979 of 538,549 raw values passed; the rest were placeholders like
      `'0'` or too short). A retirement circuit-breaker aborts the run
      (`--force` to override) if it would silently retire >20% of a
      merchant's live offers — the guard against a truncated feed being
      read as "everything disappeared".

### Phase 2 progress

- [x] `mcpipe signature` — normalize every offer into `offer_signature`
      (brand code + known-brand flag, colour code, model tokens + alnum
      anchor, size, genre/age, year, pack flag). Genre/age combines the
      feed's own `gender`/`age_group` (whitelisted) with title parsing — the
      title wins on a direct clash. No matching yet; `category_id`,
      `identity_hash` and `base_sku` stay NULL (owned by `match`).
- [x] **6th merchant: FC-Moto** (Webgains — a 3rd feed platform). 147k rows,
      real GTINs (98% valid EAN), best-filled feed (colour 90%, size 94%,
      item_group 94%). Keyed on `mpn`. Adds a 2nd merchant to ~35k
      previously mono-merchant products. Feed needs a bearer token
      (`FEED_FCMOTO_TOKEN`); the endpoint does not enforce it yet.
- [ ] `mcpipe match` — GTIN cascade → item_group → base-SKU
- [ ] `mcpipe enrich` — colour cascade, category

Signature coverage across all 763,570 offers: brand 100% (57% a known alias),
colour 51%, size 31%, model anchor 17%, gendered (not `U-A`) 26%,
is_pack 0.2% (was 12% before fixing the "kit" false-positive).

### Notes for phase 2

- Speedway's feed leaves `color` / `size` / `item_group_id` / `mpn`
  completely empty — colour/size are recovered from the title/URL by
  `signature` (73% / 51% for Speedway specifically).
- Motoblouz (Netaffiliation) has no colour or `item_group_id` column at all
  — this is the "colour cascade" problem; its no-GTIN rows (~30%) will need
  to match on brand + mpn (stage 4) instead.
- `base_sku` is deferred to `match`: only Motoblouz needs it, and it must be
  a guarded blocking key (still requires size/colour agreement), not an
  auto-merge key on its own.
- La Bécanerie's `item_group_id` groups all colourways of a model together
  (not model+colour) — `match`'s item_group stage must still split on
  `primary_colour`.
- The cross-merchant GTIN stage needs a same-brand/same-category guard
  before auto-merging (recycled or mistyped EANs exist).
