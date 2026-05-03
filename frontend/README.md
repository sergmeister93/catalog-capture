# Frontend

Review UI shell for the Service Photo POC.

## Status

Scaffolding only. Implementation begins in Phase 3. See [`../docs/progress.md`](../docs/progress.md).

## Planned Stack

Framework TBD — likely React with Vite, or a thin server-rendered alternative. Decision will be captured in an ADR under [`../docs/decisions/`](../docs/decisions/).

## Purpose

- Upload and preview item photos
- Trigger AI analysis
- Display AI-extracted draft content side-by-side with editable review fields
- Reviewer edits, saves, and approves listing
- Trigger CSV export

## Layout

```
frontend/
├── public/       Static assets (logo, favicon)
├── src/          Application source
└── tests/        Component/integration tests
```

## Integration Points

- [API contract](../contracts/openapi_service_photo_poc.yaml) — the UI consumes this spec directly
- [Review payload schema](../contracts/review_payload_schema.json) — shape of the review editor state
- [Approval validation rules](../contracts/approval_validation_rules.md) — UI should display rule failures returned by `POST /jobs/{id}/approve`
- [UI design notes](../docs/03_ui_design.md) — layout and interaction intent
