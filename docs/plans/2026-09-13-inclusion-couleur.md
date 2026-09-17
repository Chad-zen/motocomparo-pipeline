# Plan — an imprecise colour is not a disagreement

Status: **proposed, not implemented.** Measured 2026-09-13. Replaces
`2026-09-13-couleur-imprecise.md`, whose framing (finish only) was too narrow
and whose safety claim was wrong — see "What the review found" below.

## What is happening

The GTIN conflict gate quarantines a barcode when its merchants report different
colours. It cannot tell two situations apart:

| | |
|---|---|
| `{BK}` vs `{WH}` | a **contradiction** — someone is wrong |
| `{BK}` vs `{BK, SI}` | one merchant read one colour, the other two |
| `{BK}` vs `{BK\|MAT}` | one merchant did not say the finish |

The last two are the same shape: **one description is contained in the other.**
The most frequent real pairs in the data are `['BK','BK-SI']`,
`['BK','BK-SI','SI']`, `['CB','CB-SI','SI']`, `['GY','GY-SI','SI']` — one
merchant naming a two-tone helmet by one of its colours.

## Scale

| | |
|---|---|
| Barcodes with disagreeing colours, trusted merchants | 10,052 |
| …that are an **inclusion**, not a contradiction | **7,100 (71%)** |
| …still safe once the parent-barcode guard applies | **7,094** |
| **Offers that would link** | **14,677** |

For helmets alone, 10,772 offers are quarantined and 96% of those conflicts are
about colour.

## The measurement that settles the main objection

A review argued this is unsafe because a "parent" barcode can cover a whole
range, so one merchant's `BK` could be the gloss variant and another's `BK|MAT`
the matte one. That shape exists — but it was measured, not assumed:

```
barcodes where ONE merchant carries several colours   17 of 426,782   = 0.004%
same, on helmets                                       0 of  43,943   = 0%
```

Three real examples were found; they are exceptions, not a pattern. The guard
against them stays in the rule anyway and costs only 6 of the 7,100 cases.

## The rule

> Two colour descriptions are compatible when one is **contained** in the other.
> The more complete one wins. Anything else stays a conflict.

`{BK} ⊆ {BK,SI}` → compatible, keep `BK-SI`.
`{BK} ⊆ {BK,MAT}` → compatible, keep `BK|MAT`.
`{BK}` vs `{WH}` → conflict, quarantine, unchanged.

### Gates

- trusted-GTIN merchants only;
- **no single merchant may hold both values** under that barcode — this is what
  catches the 17 real parent barcodes;
- the comparison is on the **set** of colour tokens, finish included, so
  `BK|MAT` vs `BK|GLO` remains a conflict: neither contains the other. The
  owner's rule that matte and gloss are different products is untouched;
- the gate groups by barcode, so a chain `BK`, `BK|MAT`, `BK|GLO` must NOT let
  `BK` act as a bridge. Compatibility is required **pairwise across the whole
  group**, not against one representative.

### Open question to settle by measurement, not by argument

How much to trust a colour read from a title. Requiring `colour_source = 'feed'`
on both sides drops the yield from 14,677 offers to 696 — the quarantine is
mostly populated by title-derived colours (17,445 title, 13,973 none, 11,093
feed). Both extremes are wrong; the threshold is an experiment: run the rule at
`feed`-only, then at feed+title, and compare both columns of
`ops/mesure_catalogue.py`.

---

# Second piece — a conflict is a photograph, not a verdict

Found by the owner, and it is a design flaw independent of the rule above.

**A barcode sent to quarantine is never looked at again.** The catalogue changes
every day: a merchant fixes its colour, a fourth arrives with clean data, or one
of our own corrections makes the disagreement moot. None of that reaches an
offer already quarantined.

It happened today: the size repairs of 2026-09-13 never reached the offers
already in quarantine, because they were out of the circuit.

Two distinct gaps:

| | |
|---|---|
| **Re-computation** | a full `match --reset` already replays everything. An incremental `match` does not. |
| **Leaving quarantine** | once a conflict row exists, nothing ever checks whether it still holds. |

Proposed: at every run, recompute the conflict from current data. A barcode
whose merchants now agree links normally, and its queue row is closed with a
verdict of `resolved_by_data`. A row a human has ruled on (`match_override`)
keeps winning, as today.

This is low risk — it can only re-examine, never merge on its own — and every
future correction benefits from it, not just this one.

## Verification for both pieces

`ops/mesure_catalogue.py` on a frozen snapshot, both columns: comparable
products and quarantine size against barcodes-per-distinct-size, one merchant
twice on one size, tenfold price gaps. `verify` at 0. Plus twenty newly merged
barcodes read by hand — the measurement says nothing about whether the merges
are *right*.
