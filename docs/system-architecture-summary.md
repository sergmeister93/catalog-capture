# Catalog Capture — System Architecture Summary

## One-line description
An AI-assisted workflow that turns photographs of used items into priced, reviewed, export-ready marketplace listings.

## How it works (executive narrative)
A reviewer drops photos into the **Upload** screen of a single-page web app. The FastAPI backend stores the images, then dispatches each one to **Google Gemini** in a single multimodal call that is grounded against **Google Search** for live market pricing. Structured results — product details, specs, accessories, and a pricing block sourced from eBay, MPB, KEH, and B&H — land as JSON artifacts on disk.

The reviewer opens the **Review** screen, where each photo becomes an editable listing card. They can correct fields, adjust pricing, and approve items individually. When the batch is ready, one click bulk-approves and writes a timestamped CSV to the `exports/` folder, ready to feed a marketplace-posting pipeline.

A **Batch History** screen lets reviewers audit and re-export prior runs.

## Why this shape
- **Single-pass Gemini call** (extraction + pricing) keeps latency and cost low and keeps the AI surface area small.
- **Filesystem-backed artifacts** match the proof-of-concept scope — no database to operate, but results survive server restarts.
- **Human-in-the-loop approval** is non-negotiable; no listing exits the system without reviewer sign-off.
- **Contracts-first design** (OpenAPI + JSON Schemas + CSV spec) means the AI output, the UI, and the export are all validated against the same source of truth.

## Data flow (happy path)
1. Reviewer drags photos → `POST /inbound/input-images` → files land in `input_images/`.
2. Reviewer clicks **Run Extraction** → `POST /inbound/extract` starts a daemon thread.
3. Orchestrator iterates images → sends each to Gemini with Google Search grounding.
4. Each response is validated and written to `inbound/extraction_<UTC>__<stem>.json`.
5. Front end polls `GET /inbound/extract/{job_id}` for live progress.
6. Reviewer edits and approves cards; edits are cached in `localStorage`.
7. Reviewer clicks **Export** → `POST /inbound/export` → CSV written to `exports/`.

## Current state
- **Active pipeline**: filesystem-backed `/api/v1/inbound/*` routes (Phase 3.5 → 6 complete).
- **Dormant pipeline**: a fully tested PostgreSQL-backed `/jobs/*` pipeline with 12 tables and 47/47 tests passing, retained for future promotion (multi-reviewer queues, durability, audit).
- **Out of scope (POC)**: authentication, marketplace posting, background job queue, multi-tenant isolation.

## Risks and ambiguities
- **In-memory job state** is lost on backend restart — completed artifacts survive, but in-flight extractions do not.
- **Pricing accuracy** depends on Gemini's grounded search; no independent price verification.
- **Single-user assumption** — concurrent reviewers will race on `input_images/` and `inbound/`.
- **Local filesystem coupling** — the current design is single-host; cloud deployment would require object storage.

## Files in this package
- [`system-architecture-diagram.svg`](system-architecture-diagram.svg) — presentation-ready (drop into PowerPoint).
- [`system-architecture-diagram.mmd`](system-architecture-diagram.mmd) — executive Mermaid source.
- [`system-architecture-diagram-technical.mmd`](system-architecture-diagram-technical.mmd) — detailed Mermaid source for engineering.
- [`system-architecture-components.md`](system-architecture-components.md) — box-by-box inventory.
