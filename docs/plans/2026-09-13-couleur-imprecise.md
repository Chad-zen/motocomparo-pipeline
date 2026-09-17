# Plan — stop quarantining a barcode over a missing finish word

Status: **proposed, not implemented.** Measured 2026-09-13.

## What is happening

```
barcode 0768686046469
  FC-Moto        colour column = "Noir mat"      -> BK|MAT
  La Bécanerie   colour column = "noir"          -> BK
                 its own title = "…noir mat- S"      the word is right there
```

The same Bell Riot. Both merchants know it is matte black. La Bécanerie puts
"noir" in its colour column and "noir mat" in its title; the pipeline reads the
declared column and never looks at the title, because a declared value beats a
guessed one. That rule is right. Here it costs us the more precise value.

`BK` and `BK|MAT` are then treated as a disagreement, the GTIN conflict gate
fires, and both offers are quarantined instead of merged.

## Scale

| | |
|---|---|
| Barcodes whose merchants disagree on colour | 10,052 |
| …where the **only** difference is the finish | **2,495 (25%)** |
| Helmet offers quarantined | 10,772 |
| …of those conflicts caused by colour | **96%** |

Helmets are the worst-hit category because finish is how helmets are sold: the
same shell ships in matte and gloss, and every merchant words it differently.

## Why the gate exists, and what it is really for

Not "colour defines the product" — it is a sanity check on the barcode itself. A
feed can carry a parent EAN copied across a range, a typo, or a code recycled
after a model was discontinued. When the barcode claims two offers are the same
article and their descriptions say visibly different things, one of them is
wrong, and merging them would put a white helmet on a black helmet's page.

It just cannot currently tell two situations apart:

| | |
|---|---|
| `BK` vs `WH` | a **contradiction** — someone is wrong |
| `BK` vs `BK\|MAT` | an **imprecision** — one side says less |

## Proposed, in two independent pieces

### 1. Let a declared colour take a finish from its own title

`signature` only. When a merchant declares a base colour with no finish, and its
own title carries a finish word for that same colour, keep the finish. Same
merchant, same offer, no borrowing from anyone: this is reading one source more
completely, not trusting a second one.

Nothing else changes — `colour_source` stays `feed`, the base colour is never
altered, and a title finish is ignored whenever the feed already declared one.

### 2. Treat a missing finish as compatible, not as a conflict

`match`'s conflict gate. Compare the base colour first; a difference there stays
a conflict, exactly as today. Differ only by finish, with one side silent, and
the pair is compatible — the more precise value wins.

⚠️ **This does not touch the owner's rule** (docs/product-decisions.md): matte
and gloss remain different products. `BK|MAT` vs `BK|GLO` stays a conflict. Only
`BK` vs `BK|MAT` — where one side simply said nothing — becomes compatible.

## Risk

Piece 1 is safe: one merchant, one offer, strictly more information from a source
already trusted.

Piece 2 is a matching change and the dangerous one. Loosening a conflict gate can
only create merges, and a false merge is the expensive error. The gate must stay
strict on the base colour, and the measurement below must show the over-merge
column not moving.

## Verification before/after

`ops/mesure_catalogue.py` on a frozen snapshot, both columns: comparable
products and quarantine size against barcodes-per-distinct-size, merchant
duplicates on one size, and tenfold price gaps. Plus `verify` at 0, and a sample
of twenty newly merged barcodes read by hand.

## Not in this plan

Maxxess and Moto-Axxe contribute 8,757 helmet offers and **zero** links, because
they carry no usable barcode and the fuzzy stage (roadmap phase 5) was never
written. That is the larger number, and a separate piece of work.
