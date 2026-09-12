# Product decisions

Business rules that the code must honour but could never derive on its own.
Answers from the site owner, who sells this gear — recorded verbatim in intent,
so a later reader does not "fix" one of them by mistake. Each entry says what it
changes in the pipeline.

Last updated: 2026-09-12.

## Identity — what makes two listings the same product

**Matte and gloss are different products.** A buyer treats a matte black helmet
and a gloss black one as two different items, not one item in two finishes.
→ `textnorm._COLOUR_FINISH` keeping MAT/GLO apart is correct. Do not merge them.

**Model year does NOT define a product.** The same helmet ships for years with no
change; the barcode is what identifies it, and the buyer takes the cheapest. The
ECE 22.06 rule already removed the genuinely obsolete stock from sale, so an old
year is not a hazard.
→ `model_year` is currently a gated field in `match`, so a 2023 and a 2026
edition stay separate. That contradicts this rule and is likely the largest
single lever left for comparability. **Not changed yet**: the year gate was
itself the fix for a real bug (two Leatt GTINs, 2023 and 2026, collapsing onto
one product — see roadmap). Needs its own measured pass before touching.

**Leg-length fits (standard / long / court) are not real product variants.**
Rarely used in practice for trousers.
→ `textnorm` dropping them from the model name is correct. No change.

## Colour

**Read the real colour, not the tint word.** "Écran fumé gris" → grey.
"Visière iridium bleu" → blue. The tint word (fumé, iridium, transparent) only
names the colour when no real colour is present in the title.
→ Tint words may only ever be a LAST RESORT in `textnorm.colour`, never used
when a known colour was already found. Measured: ignoring this rule breaks ~31%
of the barcode groups it touches, because these words sit *alongside* a colour.

**"Clair" is not a colour.** In visor vocabulary the trade says *transparent*,
not *clair*; and 82% of titles containing "clair" use it as a shade of another
colour ("bleu clair", "fumé clair").
→ Stays in `_STOP`. Never add it as a colour word.

## Catalogue and display (phase 3)

**Single-merchant products are published, but kept out of site navigation.**
Reachable by direct URL only. This earns the SEO without putting a page that
cannot compare anything in front of a browsing visitor — and the day a second
merchant lists the item, it joins the navigation on its own.
→ `publish` needs a per-product "indexable but unlisted" state, not a filter
that drops them. ~220,000 of ~244,000 products are in this case.

**A price older than 24 hours is not shown.** Sending a buyer to a price that no
longer exists is the worst failure a comparison site can have.
→ That is the freshness window for `freshness`.

**Out-of-stock offers stay visible, marked "rupture de stock". Nothing is ever
removed from the site** — removing pages damages SEO.
→ `publish` must never delete a product page; stock is a displayed state.

**Shipping is researched per merchant and computed, but the displayed price
excludes it.** Both figures are kept: total delivered price, and price before
shipping. Preference is to display the price before shipping.
→ Needs a per-merchant shipping-terms table; not in the feeds.

**Sizes display as the plain letter: "S", never "S 55/56".** Head-circumference
numbers mean nothing to a buyer.
→ Display-side normalisation; `size_code` may keep the richer value internally
(FC-Moto ships "S5556"), but the site shows the letter.

**Cross and adventure/trail belong together for the buyer.** Someone shopping
for a cross helmet wants trail/adventure helmets in the same results — same
spirit. This is a *browsing* rule, not a matching rule: merchants disagree on
the label (FC-Moto titles them "enduro/cross", everyone else says integral), and
`enrich` deliberately follows the neighbours so the item still merges.
→ The site's "cross" listing must also draw in adventure/trail helmets. No
change to matching.

## Commercial priority

Where quality effort goes, in order:

1. **Helmets**
2. **Jackets**
3. **Gloves**
4. **Boots**
5. Parts — last.
