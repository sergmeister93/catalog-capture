# ADR 0001 — Draft vs Reviewed Layer Separation

- **Status:** Accepted
- **Date:** 2026-04-19
- **Supersedes:** —
- **Superseded by:** —

---

## Context

Gemini generates structured listing content from uploaded photos. Store staff must review and correct that content before it is exported. The design question is whether AI-generated output and reviewed output should share the same storage (one row per job per section), or live in parallel layers.

Tradeoffs we considered:
- Storing both in one table is simpler but destroys the original AI output when the reviewer edits
- We need to compare AI vs human values later for prompt tuning and analytics
- Approval and export must have a clear, unambiguous source of truth

---

## Decision

Use two parallel layers of storage, each with four tables:

### Draft layer — AI/system output, read-only after creation
- `listing_draft_overview`
- `listing_draft_description`
- `listing_draft_specifications`
- `listing_draft_accessories`

### Review layer — human-edited, authoritative for approval and export
- `listing_review_overview`
- `listing_review_description`
- `listing_review_specifications`
- `listing_review_accessories`

Each table is one-to-one with `listing_jobs` via `UNIQUE(job_id)`. The review layer is the exclusive source of truth for the approval gate and the export payload. The draft layer is never modified after the AI write step.

---

## Consequences

### Benefits
- Original AI output is preserved for prompt tuning, audit, and debugging
- Reviewer edits cannot accidentally overwrite AI-generated source material
- Approval gate runs against a single, unambiguous set of tables
- Export snapshot is clean (reviewed content only)
- Future analytics on AI-vs-human correction rates become possible

### Costs
- 8 content tables instead of 4
- Slight duplication of schema between layers
- Save-review logic must upsert rather than mutate

### Alternatives Considered and Rejected
- **Single table per section with a `status` column**
  Rejected. Any in-place edit destroys the AI output. Undo/rollback would require a separate audit log, duplicating complexity.
- **JSONB-only payloads (one `listing_draft_payloads` + one `listing_review_payloads` table)**
  Rejected for Phase 1 core sections. Weakens field-level validation, harder SQL reporting, less schema discipline. May still be used selectively for truly flexible sub-fields (`raw_source_payload`, `other_specifications`).
- **Event-sourced model**
  Rejected as premature for a POC. Would slow Phase 1 without clear near-term benefit.

---

## References

- [Database schema architecture](../01_database_schema_architecture.md) §4, §12
- [Physical schema spec](../02_physical_schema_spec.md) §4
- [Approval validation rules](../../contracts/approval_validation_rules.md)
- [Backend workflow spec](../../contracts/backend_workflow_spec.md) §3
