# Phase 5 — Pricing / Web Enrichment Handoff

**Status as of 2026-04-19:** Phase 4 smoke test passed. UI-triggered Gemini extraction works end-to-end. Inbound flow is seamless: drop photos → click **Run Gemini Extraction** → progress bar → cards populate → review/edit/approve → export CSV. Time to add pricing.

> Paste this whole file into the next chat as the opening message.

---

## What works today (don't regress this)

- `POST /api/v1/inbound/extract` spawns a threaded Gemini run with progress tracking (`GET /inbound/extract/{job_id}`). In-memory `_jobs` dict in `backend/src/service_photo/api/inbound_routes.py`. Daemon thread, purges prior JSONs so re-runs are clean.
- Shared extraction service at `backend/src/service_photo/services/inbound_extraction.py` — both CLI and HTTP endpoint delegate here. Emits progress via `on_image_start` / `on_image_done` callbacks.
- Inbound UI (`frontend/src/screens/InboundScreen.tsx`) polls every 1.5s, shows a progress banner, auto-refreshes cards on completion. Per-card edit/approve, localStorage persistence, bulk export to CSV.
- `.env` loading fixed: `core/config.py` resolves `.env` by absolute path from the repo root, not cwd. Don't regress — a relative path will break uvicorn-from-`backend/`.
- 47/47 backend tests passing.
- Out of scope for this phase (still): auth, marketplace posting, pagination, soft deletes.

---

## What Phase 5 is about

Add **pricing and/or web enrichment** to each extracted listing. The goal is to move from "Gemini told me what this camera is" to "Gemini told me what this camera is AND what it's selling for on the used market, with source links I can verify." The current CSV has no pricing columns, and the review card has no market context — this is the gap.

---

## Key decisions to make before writing code

These are genuine judgment calls, not obvious choices. Sergey should weigh in:

### 1. Enrichment approach

| Option | What it is | Tradeoffs |
|---|---|---|
| **A. Gemini web search tool** | Give the current Gemini call web-search access; ask it to return comparables + price bands in the same response | Simplest to wire. One API, one prompt. Quality depends on Gemini's search. Cost goes up per call. |
| **B. Separate enrichment call** | After extraction, do a second Gemini call (or text-only model) with the extracted `brand + model + variant` and ask for pricing | Clean separation, easier to debug. Two calls per image = ~2× cost + latency. |
| **C. Dedicated pricing API** | Integrate something like eBay Terapeak, or scrape completed listings | Most accurate for used-market pricing. But it's scope creep: new auth, rate limits, contract negotiation. |
| **D. Skip pricing, enrich metadata only** | Use web search to fill `condition_notes`, accessory guesses, known serial-number batches, release year, etc. — no price | Lower-risk narrowing of Phase 5. Lets us ship the enrichment loop without pricing-specific complexity. |

**Default recommendation (challenge me on this):** Option A (Gemini web search) for the POC. It's the fastest way to prove whether grounded pricing is useful at all; if the signal is good, Phase 6 swaps in a dedicated API. If Gemini's search surfaces bad comparables, we learn that cheaply and skip to option C without having built option B first.

### 2. What fields get added

Proposed additions to the Gemini response schema + CSV:

- `price_estimate_low` (USD, integer or decimal)
- `price_estimate_high` (USD)
- `price_confidence` (low / medium / high)
- `comparables` — array of `{title, price, condition, source_url, observed_at}`. CSV flattens to JSON string.
- `source_urls` — distinct list, also JSON-stringified in CSV.
- `pricing_notes` — free text ("Prices reflect body-only sales; kit lens bundles trend $150 higher")
- `pricing_fetched_at_utc` — so we know how stale the numbers are

Open question: do we also add `market_observations` (release year, discontinued status, successor model) or keep Phase 5 strictly about price?

### 3. Where pricing happens in the flow

- **Inline with extraction** — one call produces both content + pricing. Simpler. Fails atomically (whole card fails if pricing fails).
- **Second pass after extraction** — separate button in UI ("Add pricing"), separate endpoint. Lets you re-run pricing without re-running extraction. Adds UI complexity but better failure isolation.
- **Automatic but separable** — extraction triggers a pricing task; both stream into the same card. Complex but ideal long-term.

**Default recommendation:** Inline for the POC. Second-pass can come later if failure rates are high.

### 4. Review UX for pricing

- **Read-only** — card shows Gemini's numbers + links; user accepts or flags for rework.
- **Editable** — user can overwrite the price band before export (handles obvious hallucinations).
- **Source-click verification** — every price shown has a clickable source URL.

**Default recommendation:** All three — read-only by default, but with "Edit" unlocking the price fields alongside content fields. Sources always clickable.

---

## Shape of the work (after decisions are made)

Rough task breakdown — not prescriptive, adjust once the approach is picked:

1. **Contracts**: extend `contracts/gemini_response_schema.json` with the new pricing fields; extend `contracts/csv_export_schema.md` column list; update ADR if the approach is non-obvious.
2. **Prompt**: add a pricing section to `backend/src/service_photo/prompts/listing_extraction_v1.md` (or write a second prompt for a second-pass call).
3. **Backend**:
   - If option A: enable Gemini web search tool in `real_gemini.py`; extend response parsing to tolerate the new fields.
   - If option B: new service + endpoint for the pricing pass.
   - Either way: update the shared extraction service in `services/inbound_extraction.py` so pricing lands in the artifact JSON and the progress callbacks surface pricing-specific failures.
4. **CSV export**: add the new columns to `api/inbound_routes.py::CSV_COLUMNS` and the `_build_csv_row` mapping. Add the new columns to `_FLATTEN_NEWLINE_FIELDS` where needed.
5. **Frontend**:
   - Extend `ListingResponse` types in `frontend/src/api/inbound.ts`.
   - Add a **Pricing** section to the review card (between Description and Specifications, probably).
   - Render `comparables[]` as a small table with clickable source links.
   - Decide per above whether fields are editable; wire `handleFieldChange` accordingly.
6. **Tests**: fixture a sample Gemini response with pricing and confirm the CSV produces the right columns. The existing 47 don't cover inbound pricing — add a targeted few.
7. **Handoff doc** for Phase 6 once Phase 5 ships.

---

## Things that might trip you up

- **Cost**: Gemini 2.5 Flash with web search is multiples more expensive per call than without. Keep `USE_MOCK_GEMINI` honest — if you toggle it on, the mock must produce plausibly-shaped pricing data too, or the UI breaks.
- **Latency**: web-grounded calls can take 20–40s each. At 5 images that's 2–3 min for a batch. The progress bar already exists; make sure the `current_image` label still updates mid-call (the callback fires once per image, not per web-search step).
- **Hallucinated URLs**: Gemini will sometimes cite URLs that 404 or don't contain what it claims. Decide whether to verify source URLs server-side (HEAD request) or trust and let the reviewer catch it.
- **Currency assumptions**: the prompt should say USD explicitly. Otherwise regional Gemini responses will mix EUR/GBP/JPY.
- **Stale prices**: once exported to CSV, the prices are frozen. Consider whether to re-fetch on re-export or warn the user if `pricing_fetched_at_utc` is more than N days old.
- **Schema validation is currently non-fatal**: the extraction artifact still writes even if the Gemini response fails schema validation. Pricing fields will widen the schema; plan for the validator to be loud-but-not-blocking during iteration.
- **Don't touch the dormant `/jobs` pipeline yet.** Still passing 47 tests; don't break them by changing shared types. If the draft/review shape needs pricing too, that's a separate decision after Phase 5 validates the approach.

---

## How to start the next chat

Open Claude Code in this project directory and paste:

> Read `docs/claude_code_phase5_pricing_handoff.md`. I want to decide on approach first (A/B/C/D and the other decision points), then implement.

That's it. The `CLAUDE.md` at repo root loads automatically and orients Claude on everything else.
