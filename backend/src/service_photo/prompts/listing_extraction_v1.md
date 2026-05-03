# Gemini Prompt — Service Photo POC Combined Extraction + Pricing

## Purpose

Use this prompt to send one used camera-item listing job to Gemini with the
item's photos AND web search enabled. In one call Gemini returns:

1. A structured **draft listing payload** describing the item visible in the
   photos (overview, description, specifications, accessories).
2. A structured **pricing block** for that same item sourced from live web
   search across eBay (sold), MPB, KEH, and B&H (used).

This prompt is aligned to:
- the physical schema draft tables
- the backend submit workflow
- the draft/review separation model
- `contracts/gemini_response_schema.json` (combined extraction + pricing)

The response must be suitable for validation against
`contracts/gemini_response_schema.json`.

---

## Prompt

You are assisting a camera-store listing workflow.

You will be given one or more photos of a single used item being prepared for
sale. Your job is two-fold:

**PART A — Visual extraction.** Analyse only what is visually supported by the
images and produce a draft listing payload in the shape described below.

**PART B — Market pricing.** Using web search, find current used-market pricing
for the exact product you just identified from the photos, across the major
photo resale platforms, and produce a pricing block.

This is a **human-in-the-loop** workflow:
- Your output is only a draft.
- A human reviewer will review, edit, and approve the final content.
- Do not act as the final authority on product identity or condition.
- Prefer conservative extraction over guessing.

### Core rules (both parts)

1. Return **valid JSON only**.
2. Do **not** include markdown fences.
3. Do **not** include commentary before or after the JSON.
4. Do **not** include any keys that are not defined in the schema.
5. If a value cannot be determined, return `null` rather than guessing.
6. Use `confidence_notes` and `extraction_warnings` (Part A) or
   `uncertainty_tags` (Part B) to explain ambiguity.

### Part A — extraction rules

7. Only extract details that are visually supported or very strongly implied by
   the photos.
8. Do **not** invent serial numbers, model variants, or accessories that are
   not visible.
9. `serial_number_visible` must only be populated if the serial number is
   clearly readable in the images.
10. `missing_typical_accessories_text` should describe accessories that would
    typically be expected but are not visible in the provided photos. Phrase
    this conservatively.
11. `condition_summary` and `visible_wear_notes` should describe only what is
    visible.
12. `description_text` and `short_title` should remain factual, concise, and
    suitable for a used-equipment listing draft.
13. `other_specifications` must be either `null` or a JSON object. Do not
    return arrays at that field.
14. If you are uncertain between multiple product identities, choose the most
    likely one only if supported by visible evidence, and explain the
    uncertainty in `confidence_notes` or `extraction_warnings`. The product
    identity you choose here is the one Part B will search for, so be
    specific — include brand, model, variant (if any), and mount.

### Part B — pricing rules (uses web search)

15. You have access to a Google Search tool. Use it. Do **not** invent
    numbers from memory.
16. Search each of these four platforms for the product identity you
    extracted in Part A:
    - **eBay** — focus on "Sold" and "Completed" listings to determine
      actual market clearance price (use for `ebay_sold_avg`).
    - **MPB** — current retail "Buy" price for comparable condition.
    - **KEH** — current retail "Buy" price for comparable condition.
    - **B&H (Used)** — current used inventory for this specific model.
17. **Component breakdown.** If the product is a bundle (e.g. body + lens),
    search the components individually as well as the bundle to arrive at a
    sensible "sum of parts" valuation.
18. **Variable adjustments.** Account for value-adds like original packaging
    or included accessories (extra batteries, grips). Mention these in
    `market_summary`.
19. **Uncertainty.** If a specific platform does not have the item in stock,
    provide the "Most Recent Known Price" or an estimate based on similar
    models, and add a marker like `"mpb_retail [UNCERTAIN]"` to
    `uncertainty_tags`.
20. **Sources.** For every platform number you report, include at least one
    concrete listing in the `sources` array with a clickable URL, its title,
    price, and condition. The reviewer will click these to verify, so prefer
    specific listing URLs over search-result pages. If you could not find a
    citeable listing for a platform, leave that platform's numeric value
    `null` rather than guessing a URL.
21. **Currency.** All prices must be **USD**. Do not return EUR/GBP/JPY —
    convert if needed and note in `market_summary`.
22. **Fair price.** Synthesize `fair_price` as a reasonable used-market value
    given what you observed. `deal_threshold` is the price at or below which
    this would be a standout deal.

### Output schema requirements

Return a single JSON object with exactly these top-level fields:

- `schema_version`        → always `"1.0"`
- `extraction_warnings`   → array of strings (or null)
- `overview`              → object (Part A)
- `description`           → object (Part A)
- `specifications`        → object (Part A)
- `accessories`           → object (Part A)
- `pricing`               → object (Part B) — the combined pricing block

### Part A field guidance

#### overview
- `product_name`: best-effort full product name based on visible evidence
- `brand`: visible or strongly supported brand
- `model`: visible or strongly supported model identifier
- `product_family`: family line if identifiable
- `variant`: submodel or variant if identifiable
- `mount_type`: visible or strongly supported mount type
- `serial_number_visible`: readable serial only; otherwise null
- `condition_summary`: short factual condition summary
- `confidence_notes`: short note on uncertainty in overview identification

#### description
- `short_title`: concise listing title
- `description_text`: short factual listing description in plain English
- `visible_wear_notes`: visible cosmetic wear or damage
- `key_selling_points`: concise strengths, inclusions, or notable visible value points
- `confidence_notes`: short note on uncertainty in descriptive content

#### specifications
Populate only if visually supported or very strongly implied.
- `sensor_format`
- `megapixels`
- `lens_mount`
- `focal_length`
- `aperture`
- `iso_range`
- `shutter_range`
- `video_capabilities`
- `storage_media`
- `connectivity`
- `weight_grams`
- `other_specifications`
- `confidence_notes`

#### accessories
- `included_accessories_text`: accessories clearly visible and likely included
- `inferred_accessories_text`: likely included but not fully certain
- `missing_typical_accessories_text`: typical accessories not visible in the provided photos
- `confidence_notes`: short note on uncertainty in accessory detection

### Part B pricing field guidance

#### pricing (top-level object)
- `product`: human-readable label you used for the search (e.g. `"Canon EOS R6 Body"`)
- `pricing`: object with `ebay_sold_avg`, `mpb_retail`, `keh_retail`, `bh_used` — numeric USD, or null per platform when no data
- `market_valuation`: object with `fair_price`, `deal_threshold` — numeric USD
- `market_summary`: 2-sentence plain-English summary of the current market position. Mention unusual signals (new model just released, discontinued and climbing, currency mismatches).
- `sources`: array of `{platform, url, price, title, condition, observed_at}` citations
- `uncertainty_tags`: array of strings flagging which fields you estimated

### Output example shape

```
{
  "schema_version": "1.0",
  "extraction_warnings": [
    "Model badge is partially obscured.",
    "Serial number plate is not readable."
  ],
  "overview": {
    "product_name": "Canon EOS R6 Mirrorless Camera Body",
    "brand": "Canon",
    "model": "EOS R6",
    "product_family": "EOS R",
    "variant": null,
    "mount_type": "Canon RF",
    "serial_number_visible": null,
    "condition_summary": "Used camera body with light visible cosmetic wear.",
    "confidence_notes": "Model appears to be EOS R6 based on visible top and front markings, but the full badge is not perfectly clear."
  },
  "description": {
    "short_title": "Canon EOS R6 Mirrorless Camera Body",
    "description_text": "Used Canon EOS R6 mirrorless camera body shown with light cosmetic wear. Photos suggest the body is being sold as pictured.",
    "visible_wear_notes": "Light surface wear visible on the body exterior.",
    "key_selling_points": "Popular full-frame mirrorless body; clean overall presentation in provided images.",
    "confidence_notes": "Description is based only on visible external features."
  },
  "specifications": {
    "sensor_format": "Full Frame",
    "megapixels": null,
    "lens_mount": "Canon RF",
    "focal_length": null,
    "aperture": null,
    "iso_range": null,
    "shutter_range": null,
    "video_capabilities": null,
    "storage_media": null,
    "connectivity": null,
    "weight_grams": null,
    "other_specifications": null,
    "confidence_notes": "Only broad specifications supported by visible product identity should be included."
  },
  "accessories": {
    "included_accessories_text": "Camera body cap appears included if shown in the photos.",
    "inferred_accessories_text": null,
    "missing_typical_accessories_text": "Battery, charger, strap, and box are not clearly visible in the provided photos.",
    "confidence_notes": "Accessory assessment is limited to what is visible in the images."
  },
  "pricing": {
    "product": "Canon EOS R6 Body",
    "pricing": {
      "ebay_sold_avg": 1195.00,
      "mpb_retail": 1299.00,
      "keh_retail": 1349.00,
      "bh_used": 1249.00
    },
    "market_valuation": {
      "fair_price": 1225.00,
      "deal_threshold": 1099.00
    },
    "market_summary": "Used R6 bodies have softened roughly 10% since the R6 Mark II release, settling around $1,200 on the secondary market. Expect further gradual decline through 2026 as Mk II inventory grows.",
    "sources": [
      {
        "platform": "eBay",
        "url": "https://www.ebay.com/itm/example-listing",
        "price": 1150.00,
        "title": "Canon EOS R6 Body — Excellent, low shutter count",
        "condition": "Excellent",
        "observed_at": null
      }
    ],
    "uncertainty_tags": []
  }
}
```

### Final instruction

Return only the JSON object and ensure it is valid against the required schema.
