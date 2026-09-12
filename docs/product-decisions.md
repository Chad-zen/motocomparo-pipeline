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

## Competitor study (2026-09-12) — what a product page is

Checked against two merchants and one comparison site, because the two do not
model the catalogue the same way and only one of them is our business.

**Dafy-Moto and Motoblouz — merchants — put one page per MODEL.** Colour and
size are both selectors; the URL does not change when you switch colour
(Motoblouz's RPHA 12 keeps the same page and the same reference HJ1093 across
grey, titanium, blue/black, metallic blue). Comfortable for a shop that owns its
own stock.

**idealo — a comparison site — puts one page per COLOURWAY**, which is what v2
does. Their page is titled "HJC RPHA 12 Solid black"; the colour is part of the
product name and appears again as an attribute ("Couleur: Noir").

The difference is not taste, it is the job. A merchant sells its own stock, so
grouping colourways is convenient. A comparison site puts several merchants side
by side on *the same article* — if colour were only a selector, the page would
be comparing one merchant's grey against another's blue and the price would mean
nothing. Measured on our own data: the RPHA 12 titanium semi-matte is 328,27 € at
Speedway, 390,90 € at Motoblouz, 459,90 € at FC-Moto. That comparison is only
honest because colour defines the page.

**→ Keep colour in the product identity. Do not follow the merchants here.**

### What idealo's page contains, and how it maps to what we have

| idealo | us |
|---|---|
| Colour in the product name + as an attribute | `product.colour_code`, already there |
| Size as a filter, one offer row per size | `variant` + `offer_variant_link`, already there |
| Price history graph (3 months / 6 months / 1 year) | `price_history`, first 763,550 rows written 2026-09-12 |
| A **Prix / Prix total** toggle (before / including shipping) | not built — needs a per-merchant shipping table, the feeds do not carry it |
| Offer name carries the size ("…Noir Metal **M**") | we have `size_code` per offer |
| "Ce produit peut contenir des offres en différentes tailles" — an honest caveat | worth reusing verbatim |
| Price alert (email) | out of scope, needs accounts |

Three things worth copying: the size inside each offer's name, that honest
caveat sentence, and offering the shipping toggle rather than imposing one view
(the owner's preference stays "before shipping" as the default).

### Scope for the first shadow publish (decided 2026-09-12)

Publish with what the pipeline already holds; look at the result; enrich after.
The point of shadow mode is to decide on the evidence, not in advance.

- **Shipping is deferred.** No feed carries it, so it needs a hand-maintained
  per-merchant table (free-shipping threshold, weight or basket bands) that
  someone has to keep current. Worth doing, not worth delaying the first look.
  Until then the site shows the product price only, which is the owner's
  preferred default anyway.
- **Offer display name: ours, with the merchant's title kept underneath.**
  idealo shows the raw merchant title — honest but redundant ("Casque HJC RPHA
  12 Uni Métal Noir - Casque Intégral HJC Noir Metal M"). We have the parts to
  write a clean one ("HJC RPHA 12 — Titane mat — Taille M") and the raw title
  stays visible in smaller type, so nothing is hidden from the buyer.
- **Product attributes: only what we actually have** — type, colour, sizes,
  gender. Materials and weight are not in any feed; extracting them from
  descriptions is its own project and is not a prerequisite to looking at the
  catalogue.
