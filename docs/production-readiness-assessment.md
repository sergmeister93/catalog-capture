# Production Readiness Assessment

A scorecard across ten standard production-readiness dimensions. Ratings are **Ready** / **Partially Ready** / **Not Ready**.

---

## Scorecard

| # | Category | Rating | Rationale |
|---|---|---|---|
| 1 | Architecture | **Partially Ready** | Clean layering, contracts-first design, solid abstractions (draft vs review, integration interface). But: single-host assumption, in-memory job state, and shared-folder data storage limit horizontal scaling and multi-user use. |
| 2 | Code quality | **Partially Ready** | Typed schemas, clear service boundaries, externalized prompts, and documented gotchas. Offset by two large modules (`InboundScreen.tsx`, `inbound_routes.py`) that concentrate risk and a parallel dormant codebase that increases surface area. |
| 3 | Error handling | **Partially Ready** | Custom FastAPI exception handler exists and is contract-aligned; approval gate surfaces all failures together. But: no retry/backoff for Gemini, no dead-letter for per-image failures, and `/inbound` routes do not emit structured errors as richly as `/jobs`. |
| 4 | Observability | **Not Ready** | `print`-based logging only. No structured logs, no log levels, no request IDs, no metrics, no tracing, no health endpoint beyond FastAPI's default. |
| 5 | Security | **Not Ready** | No authentication, no authorization, no rate limiting, no secret rotation policy. `.env` holds `GEMINI_API_KEY` locally. CORS and CSP not audited. Safe for localhost-only POC use. |
| 6 | Configuration | **Partially Ready** | `.env` + pydantic-settings with absolute-path loader is robust across working-directory contexts. `USE_MOCK_GEMINI` flag enables offline dev. Missing: secret manager integration, environment-specific profiles, config validation on boot. |
| 7 | Test coverage | **Partially Ready** | 47/47 tests passing on the dormant `/jobs` pipeline with unit + integration + E2E coverage. **Zero automated tests on the active `/inbound` pipeline** — the pipeline that actually runs in the UI. Frontend has no tests. |
| 8 | Resilience | **Not Ready** | In-memory job state lost on restart. No retry on Gemini failures. Extraction loop is single-threaded and sequential. No circuit breaker. No graceful shutdown that drains in-flight jobs. |
| 9 | Deployment readiness | **Not Ready** | Windows-first `dev.bat` launcher. No Dockerfile for the application. No CI pipeline. No reverse proxy or TLS config. Postgres is run locally via docker run, not composed. No deployment runbook. |
| 10 | Workflow completeness | **Ready** | Happy path is functional and verified end-to-end against the live Gemini API (5/5 images). Upload, extract, review/edit, per-card approve, bulk export all work. Reviewer can complete a batch without developer intervention. |

---

## Aggregate score

| Ready | Partially Ready | Not Ready |
|---|---|---|
| 1 | 5 | 4 |

**Overall verdict:** Not production-ready as-is. Credible as a POC, suitable for continued evaluation and internal demos. Material engineering investment required before hosting beyond a single developer workstation.

---

## Path to "Ready" in each category

| Category | Minimum work to reach **Ready** |
|---|---|
| Architecture | Promote `_jobs` to SQLite; design multi-user data ownership if required. |
| Code quality | Decompose `InboundScreen.tsx` and `inbound_routes.py`; decide whether to delete or revive the dormant pipeline. |
| Error handling | Add retry/backoff on Gemini; standardize error response shape across `/inbound`. |
| Observability | Replace `print` with structured JSON logging; add `job_id` correlation; `/health` endpoint; minimum metrics. |
| Security | Add authentication (shared credential is enough for internal use; OAuth/SSO for external); rate-limit `/inbound/extract`; move secrets to a manager. |
| Configuration | Per-environment config profile; boot-time validation (fail fast on missing `GEMINI_API_KEY`). |
| Test coverage | Integration tests for `/inbound` routes; one frontend E2E test using Playwright. |
| Resilience | Persistent job tracker; retry/backoff; graceful shutdown. |
| Deployment | Dockerfile + docker-compose; CI that runs `pytest` and `tsc --noEmit`; deployment runbook. |
| Workflow | Already ready. Only "export approved-only" toggle would tighten UX (gotcha #13). |

---

## What would change the rating

- If the system must support **multiple concurrent reviewers** → C1, C6, C7 each escalate from concern to blocker; rating becomes a hard "Not Ready" overall until addressed.
- If the system is only ever used by **one reviewer on one machine with a trusted local network** → current "Partially Ready" state is defensible and the POC is already useful.
- If a **real marketplace integration** replaces CSV export → the CSV contract becomes the API contract and requires verification against the target's import spec.

---

## Cost considerations

**Not assessed in detail.** The only external paid dependency is the Gemini API. Without rate limiting or per-user quotas, unbounded usage is possible. Before any production-like deployment:
- Establish a monthly Gemini spend cap.
- Add per-extraction cost logging.
- Rate-limit `/inbound/extract` to a sane per-minute bound.
