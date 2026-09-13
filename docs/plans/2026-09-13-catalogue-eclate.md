# Plan — stop splitting one product across several pages

Status: **proposed, not implemented.** Measured 2026-09-13.

## What a visitor sees

The Arai SZ-R VAS EVO in matte blue exists twice:

| page | sizes |
|---|---|
| `arai-evo-r-sz-vas-bl-mat-ad048414` | S |
| `arai-evo-r-solid-sz-vas-bl-mat-5cfda3d` | XS, M, L, XL |

Same helmet, same colour, same merchants. The split comes from one word:
`Solid`. Motoblouz writes "Casque jet Arai SZ-R VAS EVO - SOLID", FC-Moto writes
"Arai SZ-R EVO Frost Casque jet". The word enters `model_tokens`, therefore
`identity_hash`, therefore the product. Matte white and the XL of matte black
split the same way.

Measured on 400 comparable pages: **21.8% offer a single size**. That is what a
one-size page usually means — the rest of the size run is on another page.

## Scale

Grouping by (8-char manufacturer-reference prefix, brand, colour, category):

| | |
|---|---|
| Families split across several pages | 9,540 |
| Pages involved | 32,633 |
| Worst family | 223 pages |
| Families analysed in detail | 5,846 |
| **Would merge by keeping only the shared tokens** | **5,549 — 95%** |

The tokens doing the splitting, by frequency across families:

- **category words that survived the stop list**: `valises` (399), `top` (302),
  `case` (290), `textile` (244), `dames` (208), `blouson` (185), `veste` (180),
  `tubulaire` (147)
- **bare numbers**: `8` (377), `2` (326), `9` (325), `7` (307), `6` (275),
  `5` (248), `35` (245), `45` (241), `55` (200) — glove sizes and pannier litres
  leaking into the model
- **motorcycle names**: `yamaha` (153)

## The rule

> Inside a group of offers sharing one validated GTIN, a token that only some
> merchants write is not part of the model name.

A GTIN identifies one article. If three merchants sell it and one of them writes
"SOLID", that word describes how that merchant names things, not the product.
Keep the **intersection** of the tokens, not the union.

Same family of reasoning as the helmet-type and the size borrowing already in
production: ask the neighbours. Here nothing is borrowed — what they disagree
about is dropped.

## Why this is the safe direction, and where it is not

Dropping a token can only make two identities **more** alike, so the risk is a
false merge — the expensive kind (docs/product-decisions.md). Gates that keep it
honest:

- only inside a **validated GTIN group with 2+ trusted merchants**. One merchant
  alone has no one to disagree with, so its tokens are kept untouched.
- **never drop the last token.** A product with an empty model name would merge
  with every other product of the same brand and colour. If the intersection is
  empty, keep the union — abstain.
- **`model_core_ref` is not touched.** It is the stable anchor (`rpha12`,
  `ff807`) and it is what makes a merge meaningful.
- the GTIN conflict gate stays in front: anything that disagrees on
  category/colour/genre/year still goes to `match_review_queue`.

## Verification before/after

On a frozen snapshot, with only this variable changing: products, comparable
products, single-size pages (the 21.8% above), merges lost, `verify` anomalies,
and `ops/audit_site.py` re-run on the same 400 slugs. The Arai blue matte must
end up as one page with XS/S/M/L/XL.

## Open question for review

Bare numbers are the second-biggest cause. Dropping them inside a GTIN group is
covered by the rule above, but a number that *is* part of a model name (LS2
FF800, Shoei NXR2) is normally welded to letters and survives as one token — to
be confirmed on a sample before implementing, not assumed.
