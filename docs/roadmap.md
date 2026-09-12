# Roadmap

Phased so each step is independently useful and reversible. Effort = focused days.

| phase | goal | effort | done? |
|---|---|---|---|
| **0** | Repo + schema + local Postgres running; feed URLs collected | 2–3 d | **done** |
| **1** | `fetch → load → normalize` working on all 5 real feeds | 4–6 d | **done** |
| **2** | `signature` → `match` (GTIN + item_group + base-SKU) → `enrich` | 5–8 d | **done** |
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
- [x] `mcpipe categorize` — seeds a 25-category taxonomy and classifies every
      merchant `raw_category` path by keyword (`src/mcpipe/category.py`).
      Coarse on purpose (16% of offers land in the "unknown" catch-all) —
      good enough to keep EPI categories (helmets) separate from parts,
      which is all `match` needs; `enrich` can refine it later without
      affecting matching, since category is part of `identity_hash` (see
      below) but reclassifying is handled by `product_identity_alias`.
- [x] `mcpipe match` — GTIN + `item_group_id`, v1 scope (`base_sku`/Motoblouz
      and the fuzzy stage for Maxxess/Moto-Axxe are deferred, as planned). A
      *unit* is a validated GTIN (spans merchants) or one merchant's
      `(item_group_id, identity_hash)` pair. A unit's `identity_hash` mixes
      two kinds of fields on purpose: **gated** fields (brand, category,
      colour, year, genre/age, pack) are taken independently per field, safe
      because the conflict check guarantees at most one distinct non-null
      value per field across the group; **wording** fields (model anchor,
      title tokens) still come from one best-parsed offer, since merchants
      word the same product differently (see retro). Units that reduce to
      the same hash are the same `product`, regardless of which one found it
      first. A GTIN group is quarantined into `match_review_queue`, never
      merged, when members genuinely disagree on colour / genre / pack /
      year / category / **brand**.
      Result: **540,823 offers linked** (437,611 via GTIN, 103,212 via
      item_group) into **236,766 products** / 359,108 `variant` rows;
      **38,374 GTIN groups quarantined** in review (17,291 after `enrich`, see below);
      **~124,000 stay `unresolved`** (no GTIN + no item_group, or
      Maxxess/Moto-Axxe — waiting on `base_sku`/fuzzy). **Verified two ways:
      `mcpipe verify` (see below) reports 0 invariant violations across the
      whole live DB, and 3 specific historical bug cases were re-checked by
      hand against the live data and confirmed fixed.**
- [x] `mcpipe verify` — a standing, automated invariant check
      (`src/mcpipe/verify.py`), run automatically at the end of every
      `mcpipe match` and available on demand. Re-derives, straight from
      linked `raw_offer`/`offer_signature` rows, whether any `product` mixes
      category / colour / genre / pack / year / brand among its own linked
      offers — independent of whatever `match.py`'s SQL currently does, so a
      future edit that weakens a gate gets caught immediately instead of by
      the next manual audit. 6 regression tests
      (`tests/test_match_invariants.py`) reproduce each historical bug with
      synthetic data, in a transaction that's always rolled back (never
      touches the live DB). Built because 3 bugs in a row were each found by
      a one-off manual audit — a slow, non-repeatable process with no
      guarantee the next edit wouldn't reintroduce one already fixed.
- [x] `mcpipe enrich` — per-offer category corrections for coarse feed buckets,
      plus the colour reader's missing vocabulary. **Phase 2 closes here**:
      everything left in `enrich` turned out to be a *display* problem, not a
      matching one, and belongs to phase 3 where the output can actually be
      looked at (see "Deliberately left to phase 3" below).

      What shipped, each measured against a before/after snapshot of all
      79,199 multi-merchant GTINs:
      - **FC-Moto `tops`** — real motorcycle jackets filed as `apparel_casual`.
        Re-read from the title: 28,278 corrections, review queue 30,800 →
        21,630, **0 merges lost**.
      - **FC-Moto `helmets`** — every helmet type forced to `helmet.integral`.
        A cascade: the feed's own `google_product_category_text` pulls out what
        is not a motorcycle helmet at all (bicycle, ski, goggles → `unknown`,
        the sentinel the conflict gate ignores); spare parts (visors, liners)
        never take a subtype; then the subtype is **borrowed from a GTIN
        neighbour**, and only failing that read from the title. Borrowing
        outranks the title because a title can name two types at once and
        FC-Moto calls the adventure family "enduro/cross" where everyone else
        says integral — trusting it would contradict ~851 neighbours that agree.
        8,881 corrections, queue 21,630 → 17,287, **0 merges lost**.
      - **Colour** — the reader matched tokens exactly, so it knew "noir" but
        not "noire". Feminine forms added as a *fallback*, consulted only when
        the primary pass found nothing: publishable products 109,150 → 110,983,
        **4 merges lost**. `bordeaux`/`camo`/`turquoise` were tried and
        reverted — see `textnorm._COLOUR_FALLBACK` for why a brand-new colour
        code reads as a disagreement (74 of 78 lost merges).

      Measured and NOT done, because the gain was zero:
      - Cross-merchant colour propagation (`colour_source = 'xmerchant_gtin'`,
        step 1 of the cascade in architecture.md). `match` already achieves it:
        whenever a colourless offer has a coloured GTIN neighbour they are
        already on the same product, so **0** additional product becomes
        publishable. The conflict gate ignores NULL colours, so filling them
        changes nothing on the GTIN path either.
      - FC-Moto `pants` — 28,914 offers, already classified correctly, **0** to
        change.

### Deliberately left to phase 3 (display, not matching)

`unknown` (25) is excluded from the conflict gate by design, so a wrongly
classified offer in one of these buckets **still merges correctly today**.
Fixing them changes what a visitor browsing a category sees, which cannot be
judged before `publish` runs in shadow mode:

- Motoblouz `Habillage & protection moto` (38,854) is bodywork — mudguards,
  screens, engine guards — filed under rider `protection`. 91% have no GTIN
  neighbour, so there is no comparison to win either.
- Motoblouz `Intercoms et accessoires` (5,659) is mostly helmet spare parts.
- La Bécanerie `Kit plastique` (2,066).
- The `unknown` bulk (~50,000 offers at Motoblouz + La Bécanerie) is **not
  misclassified**: carburation, clutch, filters, lighting, batteries, wheels,
  cooling have no category in the 25-code taxonomy at all. Extending it is a
  product decision, and parts rank last commercially (docs/product-decisions.md).
- Motocross jerseys and rain gear (~9,300) do land in `unknown`, but 7,236 of
  them are already linked and only 107 are quarantined — again display only.

### Known, measured, not fixed

- **Model year in the GTIN conflict gate.** Two offers sharing one barcode but
  stating different years are quarantined. The owner's rule is explicit: same
  manufacturer code ⇒ same product, the year is noise (docs/product-decisions.md).
  Worth **199 queue groups**, and separately 37 groups / 349 products are
  duplicates differing only by year. Small because only **2.5%** of products
  carry a year at all. A surgical fix (drop `model_year` from the gate, keep it
  in `identity_hash` so the Leatt 2023-vs-2026 case below stays split).
- Three unchecked `cur.fetchone()` results in `normalize.py` and `load.py`
  (flagged by mypy): a crash with a confusing message if a query ever returns
  no row. Phase-1 code, not urgent.

### What went wrong building `match` (kept honest for the retro)

The first cut computed `identity_hash` per *offer* and required every offer
sharing a GTIN to match exactly — different merchants word the same
product's title differently, so that flagged 86% of shared GTINs as false
conflicts. Fixed by computing the hash from one representative offer per
*unit* instead. The representative's `model_core_ref` (e.g. "v2", "dl650")
was then letting a short, common suffix fully *replace* `model_tokens` in
the hash — merging unrelated products (gloves, boots, a jacket, and an
airbag vest all sharing `model_core_ref='v2'`) into one, at systemic scale
(~15% of linked offers). Fixed by hashing brand + **category** + colour +
year + genre/pack + **both** the anchor and the tokens together, never
either/or. Separately, `reset_match_state()`'s plain `DELETE FROM product`/
`variant` had no usable index for the FK-cascade check on large tables —
minutes-long hangs twice, once briefly during a `TRUNCATE ... CASCADE`
mistake that cascaded into `raw_offer` (recovered from `stg_feed_row`, nothing
lost). Fixed with `sql/005`/`006` indexes and a reset routine that drops the
two FKs pointing at `product` from outside the truncated set, `TRUNCATE`s
(instant regardless of row count), then restores them.

### A second real bug, found by the phase-2 sign-off review

A category-mixing bug was fixed once (identity_hash gained a category field)
but the *linking* step still had the same class of bug one level down: a GTIN
or item_group unit picks ONE representative offer to decide the product's
category, then attaches *every* offer sharing that GTIN/item_group to the
resulting product — without checking that each individual offer's own
category agreed with the representative's. Concretely: a validated GTIN
shared by Speedway ("jacket"), Motoblouz ("jacket") and FC-Moto
("apparel_casual", because FC-Moto's own category for that row was the
generic "tops") all linked to one product before this was caught — same bug
as the `model_core_ref` one, one layer further down the pipeline. Fixed by
adding `count(DISTINCT category_id) > 1` to the GTIN conflict check and
`category_id` to the item_group unit's grouping key. **This is why the
linked/quarantined counts changed between the first "0 mix" verification and
this one** — the first check was run before the bug was found, and the
number it reported (0) was real for what it checked, but the checking method
itself (an aggregate over already-linked offers) can't tell you whether a
row that *should* have blocked a merge was silently included in the
`product_id` it's now checked against. Caught by an external review agent
asked to independently re-verify the "0 mix" claim from scratch, not by
re-running the same check.

### A third and fourth real bug, found by `verify.py` — not by a human

A third bug, same class again, one level deeper: the item_group unit's
grouping key had gained `category_id` but still not `genre_age`/`is_pack`/
`model_year` — a men's and a women's V'Quattro back protector merged under
one `item_group_id` (raw_offer 140102 vs 140103). Fixed by grouping on the
full per-member `identity_hash` instead of an enumerated field list, so the
split key structurally can't miss a field again.

At that point `verify.py` (this section's own subject) was built instead of
auditing by hand a fourth time — and it immediately paid for itself, finding
two more real bugs no human review round had caught, straight from live
data:

- `brand_code` was in `identity_hash` but never in the GTIN conflict gate —
  two offers sharing a GTIN with different brands could merge silently. Low
  real-world odds (a barcode collision across brands is a data error, not
  normal), but live: 1,500 products were affected. Fixed by adding it to the
  gate.
- The deeper one: a GTIN unit's `identity_hash` came from ONE "representative"
  offer's entire row — brand, colour, year, genre, *and* wording, all from
  whichever member won a model_strength/id tiebreak. When a merchant never
  states colour in its title (but the title still parses "strong"), that
  colour-blind offer could keep winning the tiebreak across *every* GTIN of
  the same product line — collapsing 13 real, differently-coloured barcodes
  of one RST suit onto a single product, because none of their
  representatives ever carried the real colour a different merchant's row
  had. A first fix just reordered the tiebreak (colour, then genre, then
  year, then strength) — that only relocated the bug: two validated GTINs
  for the same Leatt goggles, a 2023 and a 2026 edition, then collapsed onto
  one product because both representatives were re-picked for genre and
  their real, different years got discarded instead. The actual fix: stop
  picking one row for every field. The conflict gate already guarantees a
  non-conflicting group agrees on every gated field, so each one (brand,
  colour, year, genre, pack, category) is now taken independently, straight
  from whichever member has it — only the two wording fields (model anchor,
  title tokens), which the gate deliberately does not check, still come from
  one best-parsed row.

`verify` went from 2,400 violations (mostly the `brand_code` gap, still
present in already-linked data) to 6 (the Leatt-style year case) to 0 after
this last fix — each step re-confirmed by re-running the full match and the
check together, not assumed.

### The one bug still open: generic-title fitment parts

Measured on the live DB (2026-09-12) so the next attempt starts from evidence
rather than another guess. Grouping GTIN-linked products by how many distinct
GTINs each one absorbed:

| distinct GTINs | products | avg sizes | avg merchants | GTINs per distinct size |
|---|---|---|---|---|
| 1 | 108,775 | 1.0 | 1.15 | 1.0 |
| 2–5 | 28,929 | 3.0 | 1.18 | 1.5 |
| 6–10 | 14,421 | 6.1 | 1.22 | 2.0 |
| 11–20 | 2,505 | 7.2 | 1.19 | 6.6 |
| 21–40 | 637 | 5.6 | 1.05 | 20.6 |
| 41–100 | 240 | 2.0 | 1.02 | 55.9 |
| 100+ | 101 | 1.0 | 1.01 | 233.0 |

Two things this settles:

**The right discriminator is GTINs *per distinct size*, not raw fan-out.** A
legitimate product is one GTIN per size (ratio ~1–2, which is exactly what the
healthy buckets show). The mega-merges sit at ratio 233 with a single distinct
size — 233 different barcodes all filed as "one size", which is precisely what
a per-bike fitment part looks like. Merchant count corroborates it: the bad
buckets are ~1.0 merchants (single-merchant artefacts), the healthy ones ~1.2.

**But the ratio is confounded by the size-parsing gap, and that matters more
than the threshold.** Sampling products at ratio 8–13 returns almost entirely
ordinary apparel — "Gants Segura ERWAN" (12 GTINs / 1 size), "Casque intégral
Shoei NXR2" (8 / 1), "Pantalon cross Kenny TRACK" (13 / 1). These are not
false merges at all: they are real size runs whose sizes never got parsed
(Motoblouz's feed has no size column), so every size collapsed into the shared
`TU` bucket. Quarantining them would repeat the reverted fix's mistake on a
smaller scale. Sampling at ratio 25–60 is ~90% genuine fitment parts
(Silencieux Arrow 28, Roulement All Balls 55, Bulle Ermax 41, Disque Brembo
43), with gloves/apparel still leaking in occasionally.

Candidate thresholds and what each would quarantine:

| ratio ≥ | products | % of products | offers |
|---|---|---|---|
| 3 | 7,631 | 4.90% | 97,536 |
| 5 | 4,761 | 3.06% | 86,049 |
| 10 | 2,007 | 1.29% | 67,435 |
| 20 | 848 | 0.54% | 51,732 |

Recommended order of work: **fix Motoblouz size extraction first**, then this
ratio becomes a clean discriminator at a low threshold. Doing it in the other
order forces a high, noisy threshold (~25–40) that still misses the smaller
mega-merges and still catches real apparel. Either way the action should be
`match_review_queue`, never a silent split.

### Notes for phase 2 (remaining)

- (pre-`enrich` figure, kept for the record) 71% of the then 36,685 GTIN
  review-queue groups (≈25,996) disagreed on category
  *alone* — everything else (colour/genre/pack/year) agrees. The dominant
  cause: FC-Moto's own feed puts a lot of real jackets/gear under a generic
  `tops`/`pants`-style bucket that the keyword classifier can't split
  further (it only reads `raw_category`, and FC-Moto's is too coarse). This
  is the conservative-but-correct outcome (no false merge), not a merge
  bug — but it's leaving real comparison value in the review queue. Fixing
  it properly means falling back to the *title* for category when the feed's
  own category is one of these known-coarse buckets — a good `enrich` task,
  deliberately not done now (`category_map` is a (merchant, raw_path) cache
  by design, so a per-offer override needs its own mechanism, not a bigger
  `category_map`).
- Motoblouz's no-GTIN rows (~30%) and Speedway's no-GTIN, no-item_group
  rows need `base_sku` (Motoblouz) / the fuzzy stage to ever get linked —
  both explicitly out of scope for this pass.
- `match_override` has 0 rows so far — the "operator says never merge"
  guard exists in the code and is exercised by the dry-run tooling, but
  has not yet been proven against a real operator decision.
- 664 product slugs (from the first, pre-fix run) had a cosmetic
  double-hyphen from truncation; fixed going forward.
- `reset_match_state()` looks up its two FK constraint names from
  `pg_constraint` rather than hardcoding them — the hardcoded version broke
  because `sql/001_schema.sql` doesn't name them explicitly, so Postgres's
  default name isn't guaranteed stable across environments.
