# System Overview

A one-page orientation for anyone new to the project.

## In one sentence
Catalog Capture turns a photo of a used item into a priced, reviewer-approved marketplace listing by calling Google Gemini once per image with live web grounding, then exporting approved listings to CSV.

## Who uses it
A single reviewer (store staff) at a used-camera operation. No accounts, no roles, no multi-tenancy.

## The four-step workflow
1. **Upload.** Drag photos into the Upload screen. One photo = one listing.
2. **Extract.** Click a button. The backend dispatches each image to Gemini with Google Search grounding attached. Gemini returns structured JSON containing the visual extraction (product, specs, accessories, condition) and a pricing block (eBay / MPB / KEH / B&H comps with sources).
3. **Review.** Each image becomes a card on the Review screen. The reviewer edits any field and toggles per-card approval.
4. **Export.** One click bulk-approves remaining cards and writes a timestamped CSV to the `exports/` folder. The CSV is the deliverable.

## What's under the hood
- **Frontend**: React 18 + TypeScript + Vite. Three screens, all in one file (`InboundScreen.tsx`), custom hash router.
- **Backend**: FastAPI (Python 3.12). The active path uses seven `/api/v1/inbound/*` endpoints and writes JSON artifacts to `inbound/`.
- **AI**: Google Gemini 2.x via the `google-genai` SDK, with `types.Tool(google_search=...)` attached to the same multimodal call.
- **Storage (active)**: local filesystem (`input_images/`, `inbound/`, `exports/`), plus an in-memory dict for extraction job progress.
- **Storage (dormant)**: a fully tested PostgreSQL pipeline retained from Phase 2. It has 12 tables, Alembic migrations, 47/47 passing tests, and is currently unused by the UI.

## The two pipelines
The codebase contains two parallel backend pipelines. Only one is live.

| | Active | Dormant |
|---|---|---|
| Routes | `/api/v1/inbound/*` | `/jobs/*` |
| Storage | Filesystem + in-memory | PostgreSQL |
| UI wired? | Yes | No |
| Tests | None | 47/47 passing |
| Why both? | A mid-Phase-3 pivot changed the domain model from "one job = many photos" to "one image = one listing." Rather than tear out the DB pipeline, the team built the filesystem pipeline alongside. |

## The build process at a glance
Six completed phases, all documented:
1. **Contracts & scaffolding** — OpenAPI, JSON Schemas, validation rules, DDL spec authored before code.
2. **Backend (DB)** — 12 models, 5 repositories, 7 services, 8 routes, full test suite.
3–3.5. **Frontend pivot → Inbound pipeline** — filesystem-backed parallel stack.
4. **E2E validation** — UI-triggered extraction verified live.
5. **Pricing via grounding** — single-pass extraction + pricing; SDK migration to `google-genai`.
6. **UX polish** — rebrand, design tokens, humanization of vendor strings, drag-and-drop upload.

Phase 7 (productionization) is open and unstarted.

## What makes this project unusual
- **Contracts-first at POC scale.** Most POCs skip the spec. This one wrote OpenAPI, three JSON Schemas, and an approval-rules document before any code.
- **Preserve-on-pivot.** When the domain model changed, the team built a second pipeline rather than mutating the first. Risk-averse; costs some complexity now.
- **Captured institutional memory.** `CLAUDE.md` lists 13 specific bugs with root causes and "do not reintroduce" guidance — a living postmortem.
- **Documented handoff briefs.** Each phase has a `claude_code_*_handoff.md` that doubles as a work package and a post-hoc development record.

## The three things most likely to surprise an inheriting engineer
1. **`README.md` is out of date** (stuck at Phase 1). Read `CLAUDE.md` instead.
2. **Half the backend is dormant.** The `/jobs/*` routes and 12-table schema are fully implemented and tested, but the UI does not use them.
3. **Job tracking is a module-level dict** (`_jobs` in `inbound_routes.py`). A restart drops all in-flight progress.

## Where to find the deeper docs
- Full audit: [`project-audit-and-development-spec.md`](project-audit-and-development-spec.md)
- Build chronology: [`implementation-sequence.md`](implementation-sequence.md)
- Component list: [`component-build-inventory.md`](component-build-inventory.md)
- Risks: [`open-issues-and-risks.md`](open-issues-and-risks.md)
- Readiness: [`production-readiness-assessment.md`](production-readiness-assessment.md)
- Handoff: [`developer-handoff.md`](developer-handoff.md)
- Architecture diagram: [`system-architecture-diagram.svg`](system-architecture-diagram.svg)
