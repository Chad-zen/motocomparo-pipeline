# Architecture

> ⚠️ **CONTESTED — read `docs/REPRENDRE-ICI.md` before acting on this file.**
>
> On 2026-09-13 a v2 storefront was written that reads PostgreSQL directly
> (`src/mcsite/`), which removes the need for the publish path described below.
> Two architectures are live in this repository and they contradict each other.
> **The choice has not been made.** Do not build either side until it is.

## Shape

A standalone Python service with its own PostgreSQL database. It fetches 6 merchant
feeds, normalizes and matches them into a product catalog, and publishes that catalog
into the WordPress site's database. WordPress stays as the storefront (product pages,
search, SEO); only the data engine is replaced.

```
feeds → fetch → load → normalize → signature → categorize → enrich → match → verify → freshness → publish
                       (Postgres, the system of record)                                          (WordPress MySQL)
```

Merchants: Speedway, La Bécanerie (Effinity), Motoblouz (Netaffiliation),
Maxxess, Moto-Axxe (Effinity, synthetic GTINs), FC-Moto (Webgains). Adding a
merchant is an entry in `src/mcpipe/feeds.py` — a `FeedSpec` with its platform,
delimiter, column map and gtin_trust; nothing else changes.

## The three hard problems

### 1. Two feeds emit barcodes that change every refresh

Speedway, La Bécanerie and Motoblouz emit real, stable GTINs — safe to use as a join
key. Maxxess and Moto-Axxe emit synthetic sequential ids that drift on every feed
export. Using them as identity has already glued unrelated products together in v1.

**Handling:** those two merchants are `gtin_trust = 'synthetic'`. Their offers are
*quarantined* on ingest and only linked to a product by a separate fuzzy stage
(brand + model + colour + price band + title similarity) behind hard gates — same
brand, same top-level category, same model year, no edition-token mismatch — and only
above a high confidence threshold. Below it, they stay quarantined. They never create
a product.

Cost of being conservative here is near zero. Their actual feeds are small — ~16k and
~17k rows. But because v1 keyed rows on the drifting GTIN, its catalog table
accumulated **~430k and ~440k rows** for those two merchants (every refresh's new
barcodes piled on top of the old, never cleaned) — for a grand total of under 900 live
offers. v2 keys those two on their (stable) normalized deeplink, so a refresh updates
the row instead of orphaning it.

### 2. One feed gives no colour and no size (Motoblouz)

The v1 trick was: strip the trailing size token off the merchant part-number
(`168075199XS` → `168075199`) and treat the remainder as a colour group. It mostly
works — each colourway usually has its own base SKU — but it fails silently when
colour A ships in sizes S/M/L and colour B (same base SKU) ships only in XS/XL: no
size overlap, so the "duplicate size ⇒ reject" guard never fires, and two colours get
merged as sizes of one product.

**Handling:** the base SKU is treated as a *hypothesis*, never an authority. Colour is
resolved by a cascade, each step with a confidence score:

1. cross-merchant: a GTIN shared with a trusted feed that *does* carry colour → 0.95
2. colour parsed from the title, unambiguous across the group → 0.90
3. perceptual hash of the product images clusters into one group → 0.55
4. price band agreement only → 0.35 (corroboration, not decision)

Auto-merge needs ≥ 0.85 from an independent signal. Anything less goes to the review
queue with the size-disjoint sub-clusters shown side by side. Because every Motoblouz
size row carries its own real GTIN, steps 1 and 3 work even with zero size overlap —
which is exactly the case the v1 guard missed.

### 3. Product identity must stay stable, or URLs churn

v1's identity was a string built entirely from derived attributes
(`brand|type|colour|model|year`). Any change to a colour dictionary or a tokenizer
rewrote the key → the storefront URL changed → redirect chains.

**Handling:** identity is a surrogate integer `product.id` with a frozen slug. The
attribute-derived `identity_hash` is stored, and every hash a product has ever had is
kept in `product_identity_alias`. When the hashing logic changes, hashes are
recomputed and both old and new are pointed at the same `product.id` — the slug never
moves. `identity_hash` deliberately excludes `category` (a correctable attribute, not
identity) and anchors on stable alphanumeric model refs (`rpha12`, `ff807`) where they
exist.

## Matching pipeline (ordered; first auto-decision wins)

| stage | key | auto-merge when |
|---|---|---|
| 0 signature | — | always computed first |
| 1 exact GTIN | `raw_gtin` (trusted merchants) | GTIN already on a product, same category |
| 2 cross-merchant GTIN | `raw_gtin` on ≥2 merchants | brands + categories agree; propagates colour |
| 3 item_group_id | La Bécanerie `item_group_id` | single brand + single colour in the group |
| 4 base SKU + attributes | mpn minus size token | colour confidence ≥ 0.85 from an independent signal |
| 5 fuzzy | brand + category + price band | score ≥ 0.90 and all hard gates pass |

`match_override` rows (operator decisions) are consulted before stage 1 and always win.

## Publish

The publish step builds `wp_pc_catalog_next` and `wp_pc_offers_next` in the WordPress
database, runs sanity gates (row counts within tolerance, every product has a price,
≥4 merchants present, existing consolidations still map 1:1), then does one atomic
`RENAME TABLE` swap. The storefront never sees an empty table. The previous data stays
in the `_next` tables for one cycle → rollback is a second swap.

Modes: `off` (default), `shadow` (writes `wp_pc_*_shadow`, live tables untouched, for
diffing), `live`.

## Not built by this pipeline

The ~286 size-variant consolidations already applied in WordPress, and their 301
redirects, stay owned by WordPress. This pipeline only *proposes* clusters; the
existing canonical choices win.

**Correction (2026-09-13): cutover does NOT add zero redirects.** That was true only
of those 286 hand-made consolidations. Measured since: 79,199 multi-merchant barcodes
(the basis of the v1 pages) map onto 24,529 v2 products - roughly 3.2 old pages per
new one - and 17,253 of those barcodes have no v2 product at all. Of the ~23,000 pages
Google has indexed, ~18,000 must merge and ~5,000 have no destination. A cutover
without a redirect plan is ~23,000 404s. See docs/infrastructure.md and the SEO
sequence in the reprise notes: freeze the v1 inventory *before* anything else.

## Observability

- `healthchecks.io` dead-man switch per feed + one for the whole run → email/Telegram
  if a run doesn't check in.
- systemd `OnFailure=` → alert on any crash (the direct fix for v1's silent 3-day freeze).
- publish gates that refuse the swap on anomalies → the safe failure is "serve
  yesterday's data", never "publish garbage".
