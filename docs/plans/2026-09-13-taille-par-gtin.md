# Plan — recover a missing size from the barcode

Status: **implemented and run in production on 2026-09-13** (03:16), after review
by three seniors. Two defects were found in it afterwards — see the last section.
Neither is fixed yet.

## The problem, as seen by a visitor

On the Arai SZ-R VAS Evo page, Motoblouz appears four times: same title, same
600,40 €, size shown as "—". They are in fact XS, S, M and L. The page then
prints "169,55 € d'écart" against a Speedway offer in M — a spread we cannot
guarantee is like-for-like. That is the failure a comparison site must not have.

## The fact this rests on

A GTIN identifies one article in one size. Measured on the live database:

```
4530935639908  FC-Moto  "XS (53/54)"   Speedway  XS   Motoblouz  (none)
4530935639915  FC-Moto  "S (55/56)"    Speedway  S    Motoblouz  (none)
4530935639922  FC-Moto  "M (57/58)"    Speedway  M    Motoblouz  (none)
4530935639939  FC-Moto  "L (59)"       Speedway  L    Motoblouz  (none)
```

So the size is not unknown — it is written next door, on the same barcode.

## Scale (measured 2026-09-13)

| | |
|---|---|
| Offers whose size is recoverable from a shared GTIN | 30,721 |
| …of which unambiguous (the GTIN maps to exactly one size elsewhere) | 27,715 |
| Offers lacking a size but carrying a GTIN, in total | 214,065 |

It fixes 13%. The rest have a barcode nobody else carries with a size.

Missing sizes by merchant: Motoblouz 151,055 (its feed has no size column at
all — 20 fields, none of them a size), La Bécanerie 35,630, Speedway 16,458,
FC-Moto 10,922.

## Why this is the next step, not a side quest

`match.py` says so already, in a comment written before this was measured:

> the ratio is confounded today by Motoblouz having no size column at all, so
> ordinary apparel whose sizes never parsed (12 GTINs, one "TU" size) looks
> identical to a fitment part at moderate ratios. **Fix size extraction first**,
> then this becomes a clean check.

The open mega-merge bug (docs/roadmap.md, "The one bug still open": products
absorbing up to 1,314 distinct barcodes, 756 of them visible among the 24,664
comparable products) is gated on this. The discriminator it needs — GTINs per
*distinct size* — cannot work while every unparsed size collapses into `TU`.

## Proposed mechanism

Mirror `offer_category_override`, the per-offer override already in production
since phase 2 and already fed by `enrich`'s neighbour-borrowing.

1. New table `offer_size_override (raw_offer_id PK, size_code, source,
   donor_count, created_at)`. No FK to `product`, so it survives
   `reset_match_state()`.
2. `enrich` populates it: for every live offer whose signature size is empty,
   look at the other live offers sharing the same validated GTIN that do carry a
   size; if they agree, write it.
3. `match._CREATE_VARIANTS` / `_LINK_VARIANTS` read
   `coalesce(ovr.size_code, nullif(s.size_code, ''), 'TU')` — two lines.

## Gates (the project's rule: abstain rather than guess)

- Donor and receiver must both be `gtin_trust = 'trusted'`. Maxxess and
  Moto-Axxe barcodes drift on every export; borrowing across them would be the
  worst possible false merge.
- Only checksum-validated barcodes (the `gtin` column already guarantees this).
- Donors must be `is_live`.
- Donors are compared on the **normalised letter form**: FC-Moto's `XS5354` and
  Speedway's `XS` are the same size. If two distinct letter forms disagree →
  **abstain**, leave `TU`.
- `source` records the rule that fired, so any adoption is traceable and
  reversible.

## Risk

Lower than a matching change: size is never part of product identity
(docs/product-decisions.md), so this cannot merge or split a product. It only
moves an offer from the `TU` variant to a real one. The blast radius is the size
filter and the per-size price.

## Open question for review

FC-Moto stores `XS5354`, Speedway stores `XS`. Today those are **two different
variants of the same product for the same real size** — a pre-existing defect
this plan brushes against. Options:

- **(a)** adopt the letter form only, and leave the existing duplicate variants
  alone (smallest change, defect stays);
- **(b)** canonicalise `size_code` to the letter form when one is derivable, for
  every offer — fixes the duplicate variants too, but touches variants that are
  working today.

## Verification before/after

On a frozen snapshot: offers still on `TU`, distinct variants per product,
products whose merchant count changes (must be zero), `verify` anomalies (must
stay 0), and the Arai SZ-R page showing XS/S/M/L instead of four dashes.

---

# Where the size actually is — settled 2026-09-13, late evening

Three claims were made and tested tonight. Two of mine were wrong. Recorded here
so nobody re-runs the same dead ends.

## 1. "Motoblouz never sends a size" — FALSE

It sends it in `HAN`, the manufacturer reference, whenever the manufacturer puts
it there: `100101026-9001-M` / `…-L` for the Ixon Stream jacket. `textnorm`'s
`_SIZE_MPN_RE` already extracts it. Measured share of live linked offers that
carry a real size today:

| merchant | offers | with a size | share |
|---|---|---|---|
| FC-Moto | 135,403 | 124,195 | **91.7%** |
| Speedway | 41,603 | 25,145 | 60.4% |
| La Bécanerie | 216,994 | 121,986 | 56.2% |
| Motoblouz | 196,815 | 45,760 | **23.3%** |

The gap is the Arai case: `HAN = 8009013011`, a bare manufacturer code with no
size in it. Nothing in the CSV distinguishes those four offers except the GTIN.

An earlier measurement in this session reported "15% of descriptions contain a
size". That was a bad regex matching the `L` of `L'assemblage`. The honest
figure, on a strict token match, is 0.1% in `name` and 0% in `product url`.

## 2. "The size is in the feed's product URL" — FALSE, but it IS behind it

The CSV's `product url` is an opaque affiliate tracker
(`https://pkw.motoblouz.com/?P4122…`). Following it lands on

```
…/vente-casque-jet-arai-sz-r-vas-evo-solid-271011.html?color=Matte%20Black&size=XS
```

so the destination carries **both the size and the colour**, exactly. Verified on
the four Arai offers: XS, S, M, L.

⚠️ **This is not free.** Reading it means following the affiliate link, and every
follow registers as a click. 151,055 automated clicks with no sale behind them is
what an affiliate network calls click fraud; the realistic consequence is the
account being closed, which ends the site's revenue. Options, least dangerous
first:

1. **Ask Motoblouz** (via Netaffiliation) for a feed carrying size and colour.
   Free, legitimate, permanent, and worth asking every merchant with the gap.
2. **One follow per product, not per offer**, to learn the canonical page, then
   read that page directly without the tracker.
3. **One follow per offer** — never.

## 3. "The colour is in the image filename" — partly true, not a fix

`stream-transparent-noir-face.jpg`. Measured on 30,000 offers of products whose
colour is `unknown`: a colour word appears in the filename **7.4%** of the time,
and part of that is finish/tint vocabulary (`gloss`, `fume`) which
docs/product-decisions.md says may only ever be a last resort. Real yield is
lower. Worth keeping as a tie-breaker, not as a source.

## What this leaves

Borrowing the size from another merchant's offer on the same GTIN remains the
only mechanism that needs no new data and no merchant request. It covers 27,715
offers of the 214,065 missing — and it still carries the parent-EAN hole all
three reviewers found independently. The gates they proposed are in the plan
above and are not optional.


---

# Post-run review — 2026-09-13, 03:20. Two real defects.

Reviewed against the live database after the full run. Recorded before sleeping;
neither is fixed.

## Defect 1 — the guard misses the case it was built for, 109 times

`parent_ean` vetoes a merchant that puts **one** barcode on several of its own
offers. It does not see the opposite shape: **several distinct barcodes landing
on the same size, at the same merchant, on the same product.**

Measured: **109 products** where two offers of one merchant now carry the same
borrowed size. Product 106271 — Motoblouz, six offers all given `L`, six
**distinct** GTINs, all borrowed from FC-Moto. Product 11714 — the whole S→3XL
run, doubled.

A merchant does not sell the same size of the same article twice. So either the
borrow is wrong, or the product is wrong. The likely root cause is the known
mega-merge bug (several colourways agglomerated into one product), which would
make the product wrong rather than the borrow — but the visible effect on the
page is exactly the defect this plan set out to remove: one merchant listed
several times for one size.

The check that catches it was proposed in the first review round and skipped,
because `product_id` does not exist yet when `enrich` runs. That was true, and
the wrong conclusion was drawn: **the check belongs after `match`, not inside
`enrich`.** It costs one query.

## Defect 2 — a borrowed size outranks the merchant's own, forever

```sql
_SIZE_OF_OFFER = "coalesce(ovr.size_code, nullif(s.size_code, ''), 'TU')"
```

The override comes **first**. And `offer_size_override` is deliberately never
purged, so the day Motoblouz starts sending a real size, the borrowed one keeps
masking it — silently, with no trace and no alert. A guess must never outrank a
declaration.

Correct order, a one-word change:

```sql
coalesce(nullif(s.size_code, ''), ovr.size_code, 'TU')
```

## Two numbers reconciled

The run reported **13,597** borrows written; the table holds **13,698**. The 101
extra are rows from the first manual pass whose donors no longer qualify. The
table is sticky by design (see sql/010), so they survive — which is the intended
behaviour and also means 101 borrows can no longer be re-proved. They need a
`confirmed_at` age check, which does not exist yet.

## Settled: the −74 comparable products are not the code's doing

Measured on the live database: **250 products dropped to a single live merchant**
because of merchant retirements, while ~176 became comparable. Net −74. Nothing
to attribute to this change.

## What the reviewers asked for, and is not done

- A **state lock**, not a printed reminder: `enrich` should bump a generation
  counter when it writes overrides, and `match` without `--reset` should refuse
  to start while that counter is ahead of the last full match. Tonight's incident
  came from an instruction printed on screen and not read.
- `verify` should run at the end of `enrich`, not only after `match`.
- The A/B measurement, re-done cold: same data, `offer_size_override` emptied and
  refilled, so the effect of this change alone is finally attributable. The table
  being separate makes this possible without re-downloading anything.
