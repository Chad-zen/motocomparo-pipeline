# What `publish` has to produce

> ⚠️ **CONTESTED — read `docs/REPRENDRE-ICI.md` before acting on this file.**
>
> On 2026-09-13 a v2 storefront was written that reads PostgreSQL directly
> (`src/mcsite/`), which removes the need for the publish path described below.
> Two architectures are live in this repository and they contradict each other.
> **The choice has not been made.** Do not build either side until it is.

Read on 2026-09-13 from `staging.motocomparo.com` (an exact copy of production):
the WPCode snippets that render the site, and the real table structures in
`u660903589_4MFbB`. Everything below was read, not guessed. The point is that
**the site's display is good and stays untouched** — `publish` must simply feed
it what it already knows how to read.

## The two halves of a product page

A v1 product page is **a WooCommerce product post** whose attributes live in
`wp_postmeta`, plus **its offers, in `wp_pc_offers`**, joined on the post ID.

```
wp_posts (post_type=product) ─┬─ wp_postmeta        : brand, image, colour, type, price
        post_id ──────────────┴─ wp_pc_offers       : one row per merchant offer
                               └─ wp_pc_price_history: one row per merchant per day
```

`wp_pc_offers.product_id` **is the WordPress post ID.** That single fact
determines the shape of `publish`: every v2 product needs a post, and every
offer row points at it.

## `wp_pc_offers` — 20 columns (the table the comparator reads)

| column | v2 source |
|---|---|
| `product_id` | the post ID of the product page (see below) |
| `store` | `merchant.code` |
| `gtin` | `raw_offer.gtin` |
| `price` / `currency` | `raw_offer.price` / `currency` — phase 3, 100% covered |
| `stock_status` / `availability` | `raw_offer.in_stock` (NULL stays "unknown", never "out of stock") |
| `shipping_cost` / `shipping_time` | **not available** — no feed carries it; leave NULL (docs/product-decisions.md) |
| `buy_link` / `link` | merchant product URL |
| `title` | the merchant's raw title (kept, shown under ours) |
| `image_link` | merchant image URL |
| `first_seen` / `last_seen` / `last_updated` / `updated_at` | `raw_offer` already has these |
| `status` | live / retired |
| `price_history` | legacy text column — superseded by `wp_pc_price_history`; leave NULL |

## `wp_pc_price_history` — 7 columns

`product_id`, `store`, `gtin`, `price`, `recorded_at`, `recorded_date`.
Maps 1:1 onto the v2 `price_history` table written in phase 3 (763,550 rows).
Read by the snippet `MC Price History v2` to draw the price curve.

## The postmeta keys the display reads

Verified as referenced by the display snippets:

`_pc_brand` · `_spc_brand` · `_pc_image` · `_spc_image_url` · `_gtin` ·
`_pc_last_update` · `_mc_color` · `_mc_variant_label` · `_mc_ptype` ·
`_price` · `_regular_price` · `_stock_status` · `_mc_depub` · `_mc_depub_raison`

`_mc_depub` is how v1 unpublishes a product without deleting the page — exactly
the owner's rule that nothing is ever removed from the site.

## Shortcodes the theme calls

`smartprice_compare`, `smartprice_price_compare`, `smartprice`, `mc_categories`.
They must keep working; none of them needs changing.

## Two things this changes

**1. `wp_pc_catalog` is barely used by the display.** Of the snippets read, only
`MC Marchands - compteur dynamique` touches it, and only to count merchants. The
1.32-million-row table with its ~870,000 dead rows is **not** what the site reads
to draw a page — `wp_pc_offers` is. That lowers the stakes of the cleanup in
`ops/v1-menage-lignes-mortes.sql` further still.

**2. The v1 engine must be switched off at cutover.** About forty of the 70
active snippets are not display — they are the v1 engine, and they write to the
same tables `publish` will write to: `PC Import Engine`, `MC Feed Enrich v2`,
`MC Signature v1`, `MC Match Guard v1/v2/v3`, `MC Consolidation v1`,
`MC Color Extraction`, `MC Size Fill`, `MC Fraicheur`, `MC Price History v1`,
`MC Publication`, `MC Reconcile`, `MC Stabilise-lien`, `MC Rattrapage`,
`MC Auto-Create Engine`, `MC Category Correction`…

Leaving them on while v2 publishes means two engines overwriting each other.
**A list of exactly which snippets to disable is a prerequisite for cutover** and
does not exist yet.

**Already built in v1 and worth keeping:** `MC Canonical Merge (fusion variantes,
redirects 301)` and `MC Redirect 301`. The redirect machinery the cutover needs
is half-written already.
