/**
 * InboundScreen — review pending listings from the inbound/ folder.
 *
 * Each artifact in inbound/ produces one card. A card shows the source photo
 * on the left and Gemini's structured listing on the right, grouped into the
 * four sections (overview, description, specifications, accessories). The user
 * can toggle each card into edit mode to fix any field, then mark it approved.
 *
 * State persistence:
 *   Edits and approval flags are kept in localStorage keyed by extraction_id,
 *   so a refresh mid-review doesn't lose work. Nothing is written to the
 *   backend until the user clicks "Approve All & Export to CSV", which sends
 *   every approved card to POST /api/v1/inbound/export.
 *
 * Why localStorage instead of backend writes per edit:
 *   This is a POC checkpoint. The CSV is the durable artifact; edits in the
 *   browser are working state. Keeps the backend stateless, no DB involved.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  exportInbound,
  exportDownloadUrl,
  getExtractionStatus,
  listInbound,
  type ExportRequestItem,
  type ExportResponse,
  type ExtractionJob,
  type InboundItem,
  type ListingResponse,
  type PricingBlock,
  type PricingPlatforms,
  type PricingValuation,
} from "@/api/inbound";
import {
  clearActiveExtraction,
  readActiveExtraction,
} from "@/state/extractionHandoff";

// --- Local state shapes (per-card, persisted to localStorage) ----------------

interface CardState {
  /** Edited copy of the Gemini response — starts as a deep clone of the original. */
  edited: ListingResponse;
  /**
   * Edited copy of the pricing block, or null when Gemini returned no pricing
   * in the combined extraction+pricing call. Survives refresh (localStorage)
   * so a reviewer can come back to an in-progress edit session.
   */
  editedPricing: PricingBlock | null;
  approved: boolean;
  approvedAt: string | null;
  /** Whether the card is currently in edit mode (UI affordance only). */
  editing: boolean;
}

type CardStateMap = Record<string, CardState>;

// Bumped v1 → v2 for Phase 5. The shape change (added editedPricing) means old
// v1 state objects are missing a field. Rather than writing a migration, we
// let the old key fall through and re-initialise from scratch — no loss of
// in-flight data for most users and simpler code.
const STORAGE_KEY = "service-photo:inbound-review-state-v2";

// --- Top-level loader state --------------------------------------------------

type LoadState =
  | { kind: "loading" }
  | { kind: "loaded"; items: InboundItem[] }
  | { kind: "error"; message: string };

// --- Component ---------------------------------------------------------------

/**
 * Props — `batchId` (optional) restricts the rendered cards to one batch,
 * matched against `meta.batch_started_at_utc`. No filter ⇒ show everything.
 */
interface InboundScreenProps {
  batchId?: string;
}

export default function InboundScreen({ batchId }: InboundScreenProps = {}) {
  const [loadState, setLoadState] = useState<LoadState>({ kind: "loading" });
  const [cardStates, setCardStates] = useState<CardStateMap>(() => loadCardStates());
  const [exportResult, setExportResult] = useState<ExportResponse | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  // --- Extraction job state ---
  // `extraction` is the most recent job snapshot from the backend. It drives
  // the progress banner. Extraction is always kicked off from Prep — this
  // screen only resumes polling a handoff that PrepScreen stashed before
  // navigating here.
  const [extraction, setExtraction] = useState<ExtractionJob | null>(null);
  // Poll handle so we can cancel on unmount or when a job terminates.
  const pollTimer = useRef<number | null>(null);

  // --- Initial fetch ---
  const refresh = useCallback(async () => {
    setLoadState({ kind: "loading" });
    setExportResult(null);
    setExportError(null);
    try {
      const data = await listInbound();
      setLoadState({ kind: "loaded", items: data.items });
      // Initialise card state for any item we haven't seen before.
      setCardStates((prev) => initialiseMissing(prev, data.items));
    } catch (err) {
      setLoadState({ kind: "error", message: err instanceof Error ? err.message : String(err) });
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Persist card state to localStorage on every change.
  useEffect(() => {
    saveCardStates(cardStates);
  }, [cardStates]);

  // --- Extraction: start + poll ---
  //
  // Flow:
  //   1. User clicks "Run Gemini Extraction".
  //   2. POST /inbound/extract returns a job_id. We store the first snapshot.
  //   3. Poll GET /inbound/extract/{job_id} every 1.5s.
  //   4. On terminal status (completed / failed): stop polling, refresh the
  //      card list. Keep the last snapshot so the banner still shows totals.
  //
  // Polling cadence: 1.5s is short enough that per-image ticks (~13s each)
  // feel live without hammering the backend. Poll timer is tracked in a ref
  // so we can cancel it cleanly across renders and on unmount.

  const stopPolling = useCallback(() => {
    if (pollTimer.current !== null) {
      window.clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const pollExtraction = useCallback(
    (jobId: string) => {
      // One tick: fetch, update state, decide whether to reschedule.
      const tick = async () => {
        try {
          const snapshot = await getExtractionStatus(jobId);
          setExtraction(snapshot);
          if (snapshot.status === "completed" || snapshot.status === "failed") {
            stopPolling();
            // Terminal: clear the Prep→Inbound handoff so a later revisit
            // doesn't re-poll a finished job.
            clearActiveExtraction();
            // Reload cards so the new extraction_*.json files show up.
            void refresh();
            return;
          }
        } catch (err) {
          // Polling failure isn't fatal — keep trying on the next tick unless
          // the error persists; let the user bail out via Stop or refresh.
          console.warn("extraction poll failed", err);
        }
        pollTimer.current = window.setTimeout(tick, 1500);
      };
      // Kick off the first tick immediately rather than waiting 1.5s.
      pollTimer.current = window.setTimeout(tick, 0);
    },
    [refresh, stopPolling]
  );

  // Always cancel any pending poll on unmount so we don't set state on a
  // component that's gone away.
  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  // Resume polling a job that PrepScreen handed off via localStorage.
  // We deliberately do NOT clear the handoff on read: React StrictMode
  // double-invokes this effect in dev (mount → cleanup via the unmount
  // effect above → remount), and the cleanup wipes the poll timer. If we
  // cleared the handoff on the first pass, the remount would have nothing
  // to resume from and the banner would sit at "Queued…" forever. Instead,
  // the poll tick clears the handoff once the job reaches a terminal state.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const handoff = readActiveExtraction();
    if (!handoff) return;
    setExtraction({
      job_id: handoff.job_id,
      status: "queued",
      total: handoff.total,
      completed: 0,
      succeeded: 0,
      failed: 0,
      current_image: null,
      started_at_utc: new Date().toISOString(),
      finished_at_utc: null,
      model: null,
      error: null,
      results: [],
    });
    pollExtraction(handoff.job_id);
  }, []);

  const allItems = loadState.kind === "loaded" ? loadState.items : [];
  // Apply the optional batch filter before rendering. We match on
  // meta.batch_started_at_utc because that's the stable id stamped at
  // extraction time.
  const items = useMemo(() => {
    if (!batchId) return allItems;
    return allItems.filter((it) => it.meta?.batch_started_at_utc === batchId);
  }, [allItems, batchId]);

  const filteredBatchName = useMemo(() => {
    if (!batchId || items.length === 0) return null;
    return (items[0].meta?.batch_name as string | null | undefined) ?? null;
  }, [batchId, items]);

  const approvedCount = useMemo(
    () => items.filter((it) => cardStates[it.extraction_id]?.approved).length,
    [items, cardStates]
  );

  const allApproved = items.length > 0 && approvedCount === items.length;
  const anyToExport = items.length > 0;

  // --- Per-card actions ---

  function setCard(extractionId: string, updater: (prev: CardState) => CardState) {
    setCardStates((prev) => ({ ...prev, [extractionId]: updater(prev[extractionId]) }));
  }

  function handleToggleEdit(it: InboundItem) {
    setCard(it.extraction_id, (s) => ({ ...s, editing: !s.editing }));
  }

  function handleFieldChange(
    extractionId: string,
    section: keyof ListingResponse,
    field: string,
    value: string
  ) {
    setCard(extractionId, (s) => {
      const sectionObj = { ...((s.edited[section] as Record<string, unknown>) ?? {}) };
      // Empty string → null, so blank values round-trip cleanly through the export.
      sectionObj[field] = value === "" ? null : value;
      return { ...s, edited: { ...s.edited, [section]: sectionObj } as ListingResponse };
    });
  }

  function handleApproveToggle(it: InboundItem) {
    setCard(it.extraction_id, (s) => ({
      ...s,
      approved: !s.approved,
      approvedAt: !s.approved ? new Date().toISOString() : null,
      editing: false, // closing edit mode on approve avoids accidentally editing approved content
    }));
  }

  /**
   * Update one editable pricing field on a card. `path` identifies where in
   * the pricing block the value lives:
   *   "market_summary"             → PricingBlock.market_summary
   *   "pricing.ebay_sold_avg"      → PricingBlock.pricing.ebay_sold_avg
   *   "market_valuation.fair_price"→ PricingBlock.market_valuation.fair_price
   * `value` is the raw string the user typed. Numeric paths get parsed; an
   * empty/invalid entry becomes null so downstream treats it as "unknown".
   */
  function handlePricingFieldChange(extractionId: string, path: string, value: string) {
    setCard(extractionId, (s) => {
      if (!s.editedPricing) {
        // Editing a pricing field on a card that has no pricing block yet is
        // a no-op — the UI should hide editors until pricing exists. Guard
        // just in case someone wires up a stale event.
        return s;
      }
      const next = JSON.parse(JSON.stringify(s.editedPricing)) as PricingBlock;
      const parts = path.split(".");
      const leaf = parts[parts.length - 1];
      // Walk into the object, creating empty dicts along the way if the
      // parent path is missing.
      let cursor: Record<string, unknown> = next as unknown as Record<string, unknown>;
      for (let i = 0; i < parts.length - 1; i++) {
        const key = parts[i];
        if (typeof cursor[key] !== "object" || cursor[key] === null) {
          cursor[key] = {};
        }
        cursor = cursor[key] as Record<string, unknown>;
      }
      // Decide numeric vs. string based on the field name. All pricing
      // numeric fields live under "pricing.*" or "market_valuation.*".
      const isNumeric =
        parts[0] === "pricing" || parts[0] === "market_valuation";
      if (isNumeric) {
        const trimmed = value.trim();
        if (trimmed === "") {
          cursor[leaf] = null;
        } else {
          const parsed = Number(trimmed);
          // Fall back to null rather than NaN — the CSV writer and the
          // displayed value both treat null as blank cleanly.
          cursor[leaf] = Number.isFinite(parsed) ? parsed : null;
        }
      } else {
        cursor[leaf] = value === "" ? null : value;
      }
      return { ...s, editedPricing: next };
    });
  }

  // --- Bulk approve + export ---

  async function handleApproveAllAndExport() {
    setExporting(true);
    setExportError(null);
    setExportResult(null);
    try {
      // Step 1: bulk-approve any pending cards (also persists to localStorage via effect).
      const now = new Date().toISOString();
      setCardStates((prev) => {
        const next = { ...prev };
        for (const it of items) {
          const cur = next[it.extraction_id];
          if (cur && !cur.approved) {
            next[it.extraction_id] = { ...cur, approved: true, approvedAt: now, editing: false };
          }
        }
        return next;
      });

      // Step 2: build payload from current edited state. Re-read from cardStates
      // via items mapping to ensure we send what's on screen, including any
      // not-yet-approved cards that are now approved-by-this-action.
      const payload: ExportRequestItem[] = items.map((it) => {
        const state = cardStates[it.extraction_id];
        // If we just bulk-approved, `state.edited` is still the most recent
        // edited copy — bulk approve only flips the flag.
        const edited = state?.edited ?? (it.response as ListingResponse);
        // Include the reviewer's edited pricing when we have one. Absence
        // produces blank pricing columns on the CSV row, which is correct
        // for items that were never priced.
        const editedPricing = state?.editedPricing ?? it.pricing ?? null;
        return {
          extraction_id: it.extraction_id,
          image_files: it.image_files,
          response: edited,
          pricing: editedPricing,
        };
      });

      const result = await exportInbound(payload, "ui-user");
      setExportResult(result);

      // Trigger a browser download of the CSV. We keep the file on the server
      // (Railway volume) AND push it to the user's Downloads folder via a
      // hidden anchor with `download` set. window.location.href would also
      // work but navigates the SPA — the anchor approach leaves the page intact.
      const a = document.createElement("a");
      a.href = exportDownloadUrl(result.csv_filename);
      a.download = result.csv_filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      setExportError(err instanceof Error ? err.message : String(err));
    } finally {
      setExporting(false);
    }
  }

  // --- Render ---

  return (
    <div>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "16px" }}>
        <div>
          <h1 style={{ margin: "0 0 4px 0" }}>
            {batchId
              ? filteredBatchName ?? "Batch"
              : "Review"}
          </h1>
          <p className="text-muted" style={{ margin: 0 }}>
            {batchId ? (
              <>
                Showing extractions from this batch only.{" "}
                <a href="#/inbound">View all →</a>
              </>
            ) : (
              <>Review each item, approve any changes if needed, then export the approved results as a CSV.</>
            )}
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            className="btn btn-secondary"
            onClick={refresh}
            disabled={loadState.kind === "loading"}
            style={{ fontSize: "12px" }}
            title="Reload the latest results"
          >
            {loadState.kind === "loading" ? "Loading…" : "Refresh Results"}
          </button>
        </div>
      </header>

      {/* Progress banner — visible whenever a job was handed off from Prep and
          hasn't finished yet, or has just finished and we still want the
          completion snapshot visible. */}
      {extraction && <ExtractionBanner job={extraction} />}

      {loadState.kind === "loading" && <div className="card text-muted">Loading…</div>}

      {loadState.kind === "error" && (
        <div className="card" style={{ borderColor: "var(--status-error)" }}>
          <strong style={{ color: "var(--status-error)" }}>Couldn't load results.</strong>
          <div className="text-muted" style={{ marginTop: "4px", fontSize: "12px" }}>{loadState.message}</div>
          <div className="text-muted" style={{ marginTop: "8px", fontSize: "12px" }}>
            Make sure the application service is running, then try Refresh Results.
          </div>
        </div>
      )}

      {loadState.kind === "loaded" && items.length === 0 && (
        <div className="card text-muted">
          {batchId ? (
            <>No items match this batch. It may have been replaced by a newer run.</>
          ) : (
            <>
              No items to review yet. Go to <a href="#/">Upload</a>, name a batch,
              and click <em>Start Analysis</em>.
            </>
          )}
        </div>
      )}

      {loadState.kind === "loaded" && items.map((it) => {
        const state = cardStates[it.extraction_id];
        if (!state) return null;
        return (
          <ListingCard
            key={it.extraction_id}
            item={it}
            state={state}
            onToggleEdit={() => handleToggleEdit(it)}
            onApproveToggle={() => handleApproveToggle(it)}
            onFieldChange={(section, field, value) => handleFieldChange(it.extraction_id, section, field, value)}
            onPricingFieldChange={(path, value) => handlePricingFieldChange(it.extraction_id, path, value)}
          />
        );
      })}

      {/* Sticky bottom action bar */}
      {loadState.kind === "loaded" && items.length > 0 && (
        <div style={stickyFooterStyle}>
          <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
            <div style={{ fontSize: "13px" }}>
              <strong>{approvedCount}</strong> of {items.length} item{items.length === 1 ? "" : "s"} approved
              {allApproved && <span style={{ marginLeft: "8px", color: "var(--status-success)" }}>✓ Ready to export</span>}
            </div>
            {exportResult && (
              <div style={{ fontSize: "12px", color: "var(--status-success)" }}>
                Exported {exportResult.row_count} item{exportResult.row_count === 1 ? "" : "s"} to CSV
              </div>
            )}
            {exportError && (
              <div style={{ fontSize: "12px", color: "var(--status-error)" }}>{exportError}</div>
            )}
          </div>
          <button
            className="btn btn-primary"
            onClick={handleApproveAllAndExport}
            disabled={!anyToExport || exporting}
            style={{ minWidth: "240px" }}
          >
            {exporting ? "Exporting…" : "Export Approved Items"}
          </button>
        </div>
      )}
    </div>
  );
}

// =============================================================================
// ListingCard — one artifact card
// =============================================================================

interface ListingCardProps {
  item: InboundItem;
  state: CardState;
  onToggleEdit: () => void;
  onApproveToggle: () => void;
  onFieldChange: (section: keyof ListingResponse, field: string, value: string) => void;
  /** Called when the user edits a pricing field. `path` is a dotted key — see handlePricingFieldChange. */
  onPricingFieldChange: (path: string, value: string) => void;
}

function ListingCard({
  item,
  state,
  onToggleEdit,
  onApproveToggle,
  onFieldChange,
  onPricingFieldChange,
}: ListingCardProps) {
  const { edited, editedPricing, approved, editing } = state;
  const meta = item.meta;
  const apiError = meta.api_error as string | null | undefined;
  const schemaValid = meta.schema_valid as boolean | undefined;

  // Strong visual signal of approval state via card border.
  const cardBorder = approved
    ? "2px solid var(--status-success)"
    : "1px solid var(--ui-border)";

  return (
    <section
      className="card"
      style={{
        padding: 0,
        border: cardBorder,
        marginBottom: "14px",
        // Faint green tint when approved — keeps state visible while scrolling.
        backgroundColor: approved ? "var(--status-success-bg)" : "var(--brand-light)",
      }}
    >
      {/* ----- Card header ----- */}
      <div style={cardHeaderStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0 }}>
          {approved && (
            <span style={approvedBadgeStyle} title={`Approved ${state.approvedAt ?? ""}`}>
              ✓ Approved
            </span>
          )}
          {!approved && schemaValid === false && (
            <span style={schemaWarnBadgeStyle} title={(meta.schema_error as string) ?? ""}>
              ⚠ Needs Review
            </span>
          )}
          {apiError && (
            <span style={apiErrorBadgeStyle} title={apiError}>
              ✗ Analysis Error
            </span>
          )}
          <span
            className="text-muted"
            style={{ fontSize: "11px", fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            title={item.extraction_id}
          >
            {item.image_files[0] ?? item.extraction_id}
          </span>
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            className="btn btn-secondary"
            onClick={onToggleEdit}
            disabled={!!apiError}
            style={smallBtnStyle}
          >
            {editing ? "Done Editing" : "Edit"}
          </button>
          <button
            className="btn btn-primary"
            onClick={onApproveToggle}
            disabled={!!apiError}
            style={{ ...smallBtnStyle, minWidth: "140px" }}
          >
            {approved ? "Remove Approval" : "Approve"}
          </button>
        </div>
      </div>

      {/* ----- Card body ----- */}
      <div style={cardBodyStyle}>
        {/* Image */}
        <div style={imageColumnStyle}>
          {item.image_urls[0] ? (
            <img src={item.image_urls[0]} alt={item.image_files[0]} style={imageStyle} />
          ) : (
            <div className="text-muted" style={{ padding: "40px 0", textAlign: "center" }}>(no image)</div>
          )}
          <div style={{ marginTop: "8px", fontSize: "11px" }} className="text-muted">
            Model: {humanizeModelName(meta.model)}
            {typeof meta.duration_ms === "number" && <> · {Math.round(meta.duration_ms / 1000)}s</>}
          </div>
        </div>

        {/* Content */}
        <div style={contentColumnStyle}>
          {apiError ? (
            <div style={{ color: "var(--status-error)" }}>
              <strong>AI analysis failed for this item.</strong>
              <div style={{ fontSize: "12px", marginTop: "4px" }}>{apiError}</div>
            </div>
          ) : (
            <>
              <Section title="Overview">
                <Field label="Product Name"     value={edited.overview?.product_name}     editing={editing} onChange={(v) => onFieldChange("overview", "product_name", v)} />
                <FieldRow>
                  <Field label="Brand" value={edited.overview?.brand} editing={editing} onChange={(v) => onFieldChange("overview", "brand", v)} />
                  <Field label="Model" value={edited.overview?.model} editing={editing} onChange={(v) => onFieldChange("overview", "model", v)} />
                </FieldRow>
                <FieldRow>
                  <Field label="Product Family" value={edited.overview?.product_family} editing={editing} onChange={(v) => onFieldChange("overview", "product_family", v)} />
                  <Field label="Variant"        value={edited.overview?.variant}        editing={editing} onChange={(v) => onFieldChange("overview", "variant", v)} />
                  <Field label="Mount"          value={edited.overview?.mount_type}     editing={editing} onChange={(v) => onFieldChange("overview", "mount_type", v)} />
                </FieldRow>
                <Field label="Visible Serial Number" value={edited.overview?.serial_number_visible} editing={editing} onChange={(v) => onFieldChange("overview", "serial_number_visible", v)} />
                <Field label="Condition Summary"     value={edited.overview?.condition_summary}     editing={editing} onChange={(v) => onFieldChange("overview", "condition_summary", v)} multiline />
              </Section>

              <Section title="Description">
                <Field label="Listing Title"       value={edited.description?.short_title}        editing={editing} onChange={(v) => onFieldChange("description", "short_title", v)} />
                <Field label="Description"         value={edited.description?.description_text}   editing={editing} onChange={(v) => onFieldChange("description", "description_text", v)} multiline />
                <Field label="Visible Wear"        value={edited.description?.visible_wear_notes} editing={editing} onChange={(v) => onFieldChange("description", "visible_wear_notes", v)} multiline />
                <Field label="Key Selling Points"  value={edited.description?.key_selling_points} editing={editing} onChange={(v) => onFieldChange("description", "key_selling_points", v)} multiline />
              </Section>

              {/* Pricing moved ABOVE specs/accessories (Phase 6B) — reviewers
                  typically glance at the price right after the description to
                  decide whether a listing is worth the effort. */}
              <PricingSection
                pricingBlock={editedPricing}
                editing={editing}
                onFieldChange={onPricingFieldChange}
              />

              <Section title="Specifications">
                <FieldRow>
                  <Field label="Sensor Format" value={edited.specifications?.sensor_format} editing={editing} onChange={(v) => onFieldChange("specifications", "sensor_format", v)} />
                  <Field label="Megapixels"    value={formatLoose(edited.specifications?.megapixels)} editing={editing} onChange={(v) => onFieldChange("specifications", "megapixels", v)} />
                  <Field label="Weight (g)"    value={formatLoose(edited.specifications?.weight_grams)} editing={editing} onChange={(v) => onFieldChange("specifications", "weight_grams", v)} />
                </FieldRow>
                <FieldRow>
                  <Field label="Lens Mount"    value={edited.specifications?.lens_mount}    editing={editing} onChange={(v) => onFieldChange("specifications", "lens_mount", v)} />
                  <Field label="Focal Length"  value={edited.specifications?.focal_length}  editing={editing} onChange={(v) => onFieldChange("specifications", "focal_length", v)} />
                  <Field label="Aperture"      value={edited.specifications?.aperture}      editing={editing} onChange={(v) => onFieldChange("specifications", "aperture", v)} />
                </FieldRow>
                <FieldRow>
                  <Field label="ISO Range"     value={edited.specifications?.iso_range}     editing={editing} onChange={(v) => onFieldChange("specifications", "iso_range", v)} />
                  <Field label="Shutter Range" value={edited.specifications?.shutter_range} editing={editing} onChange={(v) => onFieldChange("specifications", "shutter_range", v)} />
                  <Field label="Storage"       value={edited.specifications?.storage_media} editing={editing} onChange={(v) => onFieldChange("specifications", "storage_media", v)} />
                </FieldRow>
                <Field label="Video Capabilities" value={edited.specifications?.video_capabilities} editing={editing} onChange={(v) => onFieldChange("specifications", "video_capabilities", v)} multiline />
                <Field label="Connectivity"       value={edited.specifications?.connectivity}       editing={editing} onChange={(v) => onFieldChange("specifications", "connectivity", v)} />
              </Section>

              <Section title="Accessories">
                <Field label="Included"         value={edited.accessories?.included_accessories_text}        editing={editing} onChange={(v) => onFieldChange("accessories", "included_accessories_text", v)} multiline />
                <Field label="Inferred"         value={edited.accessories?.inferred_accessories_text}        editing={editing} onChange={(v) => onFieldChange("accessories", "inferred_accessories_text", v)} multiline />
                <Field label="Commonly Missing" value={edited.accessories?.missing_typical_accessories_text} editing={editing} onChange={(v) => onFieldChange("accessories", "missing_typical_accessories_text", v)} multiline />
              </Section>

              {edited.extraction_warnings && edited.extraction_warnings.length > 0 && (
                <div style={warningsStyle}>
                  <strong style={{ fontSize: "12px" }}>AI Warnings</strong>
                  <ul style={{ margin: "4px 0 0 16px", padding: 0, fontSize: "12px" }}>
                    {edited.extraction_warnings.map((w, i) => <li key={i}>{humanizeWarning(w)}</li>)}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}

// =============================================================================
// ExtractionBanner — progress UI for an in-flight or recently-finished job
// =============================================================================

function ExtractionBanner({ job }: { job: ExtractionJob }) {
  const running = job.status === "queued" || job.status === "running";
  const pct = job.total > 0 ? Math.min(100, Math.round((job.completed / job.total) * 100)) : 0;

  // Color the banner based on outcome so a finished state reads at a glance.
  const borderColor =
    job.status === "failed"
      ? "var(--status-error)"
      : job.status === "completed"
      ? "var(--status-success)"
      : "var(--brand-accent, #2563eb)";

  return (
    <div
      className="card"
      style={{
        marginBottom: "16px",
        borderColor,
        borderLeftWidth: "4px",
        borderLeftStyle: "solid",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "12px" }}>
        <div style={{ minWidth: 0 }}>
          <strong style={{ fontSize: "13px" }}>
            {job.status === "queued" && "Queued"}
            {job.status === "running" && "Analyzing"}
            {job.status === "completed" && "Analysis complete"}
            {job.status === "failed" && "Analysis failed"}
          </strong>
          <div className="text-muted" style={{ fontSize: "12px", marginTop: "2px" }}>
            {job.completed} of {job.total} image{job.total === 1 ? "" : "s"} processed
            {job.failed > 0 && <> · {job.failed} failed</>}
            {job.current_image && running && (
              <> · Currently processing: {job.current_image}</>
            )}
            {job.model && <> · Model: {humanizeModelName(job.model)}</>}
          </div>
          {job.error && (
            <div style={{ fontSize: "12px", color: "var(--status-error)", marginTop: "4px" }}>{job.error}</div>
          )}
        </div>
        {running && <Spinner />}
      </div>
      {/* Progress bar. Stays visible after completion for quick visual recap. */}
      <div style={progressTrackStyle}>
        <div style={{ ...progressFillStyle, width: `${pct}%`, backgroundColor: borderColor }} />
      </div>
    </div>
  );
}

function Spinner() {
  // Tiny inline SVG spinner — avoids pulling in a component library for one icon.
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
      <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="3" strokeOpacity="0.2" />
      <path d="M12 2 a10 10 0 0 1 10 10" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round">
        <animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="0.9s" repeatCount="indefinite" />
      </path>
    </svg>
  );
}

const progressTrackStyle: React.CSSProperties = {
  marginTop: "10px",
  height: "6px",
  backgroundColor: "var(--ui-border)",
  borderRadius: "3px",
  overflow: "hidden",
};

const progressFillStyle: React.CSSProperties = {
  height: "100%",
  transition: "width 0.3s ease-out",
};

// =============================================================================
// Small presentational helpers
// =============================================================================

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  // Body uses `display: grid` so each child takes its natural content height.
  // (A flex-column container would interpret Field's `flex: 1 1 200px` as
  // a 200px basis on the main axis = height, inflating every field to 200px
  // tall. Grid has no such quirk — children get `min-content` height.)
  return (
    <div style={{ marginBottom: "12px" }}>
      <h3 style={sectionHeaderStyle}>{title}</h3>
      <div style={{ display: "grid", rowGap: "6px" }}>{children}</div>
    </div>
  );
}

function FieldRow({ children }: { children: React.ReactNode }) {
  return <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>{children}</div>;
}

interface FieldProps {
  label: string;
  value: string | null | undefined;
  editing: boolean;
  onChange: (v: string) => void;
  multiline?: boolean;
}

function Field({ label, value, editing, onChange, multiline }: FieldProps) {
  const display = value === null || value === undefined || value === "" ? "—" : value;
  return (
    <div style={{ flex: "1 1 200px", minWidth: 0 }}>
      <div style={fieldLabelStyle}>{label}</div>
      {editing ? (
        multiline ? (
          <textarea
            value={value ?? ""}
            onChange={(e) => onChange(e.target.value)}
            rows={3}
            style={textareaStyle}
          />
        ) : (
          <input
            type="text"
            value={value ?? ""}
            onChange={(e) => onChange(e.target.value)}
            style={inputStyle}
          />
        )
      ) : (
        <div style={{ ...readonlyStyle, color: display === "—" ? "var(--ui-text-muted)" : "var(--ui-text-primary)" }}>
          {display}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Helpers
// =============================================================================

/**
 * Format a value that might be a number, string, or null. Used for spec fields
 * Gemini sometimes returns as strings (e.g. megapixels "33MP").
 */
function formatLoose(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return String(value);
  return String(value);
}

function loadCardStates(): CardStateMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as CardStateMap;
  } catch {
    return {};
  }
}

function saveCardStates(map: CardStateMap): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch {
    // localStorage might be disabled (private mode); silently ignore — the
    // user just loses persistence across refresh, the screen still works.
  }
}

/**
 * Add / refresh card state for each item.
 *
 * - Brand new extraction_id → initialise full card state from item.
 * - Already seen extraction_id → preserve user's `edited` and `editedPricing`
 *   edits, but adopt the backend's newest pricing block if one exists and
 *   we don't yet have one locally. This is how a fresh pricing pass surfaces
 *   on the card without wiping a reviewer's in-progress content edits.
 */
function initialiseMissing(prev: CardStateMap, items: InboundItem[]): CardStateMap {
  const next = { ...prev };
  for (const it of items) {
    const existing = next[it.extraction_id];
    if (!existing) {
      next[it.extraction_id] = {
        // Deep-clone the response so edits don't mutate the on-disk shape we
        // re-read on refresh. Falls back to an empty shell if Gemini failed.
        edited: it.response
          ? (JSON.parse(JSON.stringify(it.response)) as ListingResponse)
          : ({ overview: {}, description: {}, specifications: {}, accessories: {} } as ListingResponse),
        editedPricing: it.pricing ? (JSON.parse(JSON.stringify(it.pricing)) as PricingBlock) : null,
        approved: false,
        approvedAt: null,
        editing: false,
      };
    } else if (it.pricing && !existing.editedPricing) {
      // Backend now has pricing the UI hadn't seen yet (e.g. a pricing job
      // just finished). Seed editedPricing from the backend copy so the
      // reviewer sees the new numbers. Don't overwrite an existing local
      // copy — their edits win.
      next[it.extraction_id] = {
        ...existing,
        editedPricing: JSON.parse(JSON.stringify(it.pricing)) as PricingBlock,
      };
    }
  }
  return next;
}

// =============================================================================
// PricingSection — Phase 5 enrichment block on each review card
// =============================================================================

interface PricingSectionProps {
  pricingBlock: PricingBlock | null;
  editing: boolean;
  onFieldChange: (path: string, value: string) => void;
}

function PricingSection({
  pricingBlock,
  editing,
  onFieldChange,
}: PricingSectionProps) {
  // Phase 5 single-pass: pricing is produced by the same Gemini call that
  // produced the extraction. If the block is absent, Gemini chose not to
  // return one (low confidence, no web data, etc.). Re-running the whole
  // extraction is the only way to fetch fresh pricing.
  if (!pricingBlock) {
    return (
      <div style={{ marginBottom: "16px" }}>
        <h3 style={sectionHeaderStyle}>Pricing</h3>
        <div className="text-muted" style={{ fontSize: "12px", padding: "8px 0" }}>
          Pricing is not available for this item. Run analysis again to try once more.
        </div>
      </div>
    );
  }

  const platforms: PricingPlatforms = pricingBlock.pricing ?? {};
  const valuation: PricingValuation = pricingBlock.market_valuation ?? {};
  const sources = pricingBlock.sources ?? [];
  const uncertaintyTags = pricingBlock.uncertainty_tags ?? [];

  return (
    <div style={{ marginBottom: "12px" }}>
      <h3 style={sectionHeaderStyle}>Pricing</h3>

      {/* Valuation (fair price + deal threshold). These are the numbers we
          push to the CSV's "fair_price" / "deal_threshold" columns, so they
          lead the section visually. */}
      <FieldRow>
        <Field
          label="Estimated Fair Price (USD)"
          value={formatCurrencyValue(valuation.fair_price)}
          editing={editing}
          onChange={(v) => onFieldChange("market_valuation.fair_price", v)}
        />
        <Field
          label="Target Buy Price (USD)"
          value={formatCurrencyValue(valuation.deal_threshold)}
          editing={editing}
          onChange={(v) => onFieldChange("market_valuation.deal_threshold", v)}
        />
      </FieldRow>

      {/* Platform observations. Editable so reviewer can overwrite obvious
          hallucinations before export. */}
      <FieldRow>
        <Field
          label="eBay Sold Average"
          value={formatCurrencyValue(platforms.ebay_sold_avg)}
          editing={editing}
          onChange={(v) => onFieldChange("pricing.ebay_sold_avg", v)}
        />
        <Field
          label="MPB Retail"
          value={formatCurrencyValue(platforms.mpb_retail)}
          editing={editing}
          onChange={(v) => onFieldChange("pricing.mpb_retail", v)}
        />
        <Field
          label="KEH Retail"
          value={formatCurrencyValue(platforms.keh_retail)}
          editing={editing}
          onChange={(v) => onFieldChange("pricing.keh_retail", v)}
        />
        <Field
          label="B&H Used"
          value={formatCurrencyValue(platforms.bh_used)}
          editing={editing}
          onChange={(v) => onFieldChange("pricing.bh_used", v)}
        />
      </FieldRow>

      <Field
        label="Market Summary"
        value={pricingBlock.market_summary ?? null}
        editing={editing}
        onChange={(v) => onFieldChange("market_summary", v)}
        multiline
      />

      {/* Pricing notes — plain-English caveats derived from the uncertainty
          tags. Reviewer uses them to decide which numbers to double-check
          manually before approving. */}
      {uncertaintyTags.length > 0 && (
        <div style={pricingNotesStyle}>
          <div style={fieldLabelStyle}>Pricing Notes</div>
          <ul style={{ margin: "4px 0 0 16px", padding: 0, fontSize: "12px" }}>
            {uncertaintyTags.map((tag, i) => (
              <li key={i}>{humanizePricingTag(tag)}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Sources table. Always display-only — sources are citations, not user
          data. Clickable URLs open in a new tab so the reviewer can verify
          without losing the review screen. */}
      {sources.length > 0 && (
        <div style={{ marginTop: "10px" }}>
          <div style={fieldLabelStyle}>Sources ({sources.length})</div>
          <div style={sourcesTableStyle}>
            {sources.map((src, i) => (
              <div key={i} style={sourceRowStyle}>
                <span style={{ fontSize: "11px", fontWeight: 600, minWidth: "48px" }}>
                  {humanizePlatform(src.platform)}
                </span>
                <span style={{ fontSize: "12px", flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {src.url ? (
                    <a
                      href={src.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={src.title ?? src.url}
                      style={{ color: "var(--brand-accent, #2563eb)" }}
                    >
                      {src.title ?? src.url}
                    </a>
                  ) : (
                    <span className="text-muted">{src.title ?? "(no link)"}</span>
                  )}
                </span>
                {src.condition && (
                  <span className="text-muted" style={{ fontSize: "11px" }}>{titleCaseCondition(src.condition)}</span>
                )}
                {typeof src.price === "number" && (
                  <span style={{ fontSize: "12px", fontWeight: 600, minWidth: "52px", textAlign: "right" }}>
                    ${src.price.toFixed(2)}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {pricingBlock.fetched_at_utc && (
        <div className="text-muted" style={{ fontSize: "10px", marginTop: "6px" }}>
          Updated {formatFetchedAt(pricingBlock.fetched_at_utc)}
        </div>
      )}
    </div>
  );
}

/** Render a numeric price as a fixed-2 decimal string, or blank for null/undefined. */
function formatCurrencyValue(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  return value.toFixed(2);
}

// ----- Display humanizers --------------------------------------------------
// These turn raw vendor/system strings into product-ready copy. They are all
// pure string helpers — no data-shape changes, only presentation.

/** Turn "gemini-2.5-flash" into "Gemini 2.5 Flash". Unknown values pass through. */
function humanizeModelName(raw: unknown): string {
  if (raw === null || raw === undefined || raw === "") return "—";
  const s = String(raw);
  if (s.toLowerCase().startsWith("gemini")) {
    return s
      .split("-")
      .map((part, i) => (i === 0 ? "Gemini" : /^[a-z]+$/i.test(part) ? part[0].toUpperCase() + part.slice(1) : part))
      .join(" ");
  }
  return s;
}

/** Canonicalize known platform identifiers; leave unknowns as-is. */
function humanizePlatform(raw: string | null | undefined): string {
  if (!raw) return "—";
  const lower = raw.toLowerCase();
  const map: Record<string, string> = {
    ebay: "eBay",
    mpb: "MPB",
    keh: "KEH",
    "b&h": "B&H",
    bh: "B&H",
    "b_and_h": "B&H",
    adorama: "Adorama",
    amazon: "Amazon",
  };
  return map[lower] ?? raw;
}

/** Title-case a free-text condition label (e.g. "like new" → "Like New"). */
function titleCaseCondition(raw: string): string {
  return raw
    .toLowerCase()
    .split(/\s+/)
    .map((w) => (w.length > 0 ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}

/**
 * Convert a raw pricing-uncertainty tag (e.g.
 *   "keh_retail [ESTIMATED_LENS_PRICE]"
 *   "mpb_retail [COMBINED_BODY_LENS_PRICE]"
 *   "ebay_sold_avg [UNCERTAIN - no direct sold listings]"
 * ) into a plain-English note for reviewers.
 */
function humanizePricingTag(raw: string): string {
  const match = raw.match(/^([a-z_]+)\s*\[([^\]]+)\]\s*(.*)$/i);
  if (!match) return raw;
  const [, fieldRaw, flagRaw, trailing] = match;
  const field = PRICING_FIELD_LABELS[fieldRaw.toLowerCase()] ?? fieldRaw.replace(/_/g, " ");
  const flag = flagRaw.toUpperCase().split(/[\s-]+/)[0];
  const reason = trailing.replace(/^[\s\-–—:]+/, "").trim();

  const templates: Record<string, string> = {
    ESTIMATED: `${field} is estimated from comparable listings.`,
    UNCERTAIN: `${field} has limited data and should be verified.`,
    COMBINED: `${field} reflects a combined estimate for multiple components.`,
    SUM: `${field} is based on the combined value of individual components.`,
    NO: `${field} is not directly available and has been estimated.`,
  };
  let base = templates[flag] ?? `${field}: ${flagRaw.toLowerCase().replace(/_/g, " ")}`;
  // If Gemini added a trailing reason, append it as a short caveat.
  if (reason && reason.length < 140) {
    base += base.endsWith(".") ? "" : ".";
    base += ` ${reason.charAt(0).toUpperCase()}${reason.slice(1).replace(/\.$/, "")}.`;
  }
  return base;
}

const PRICING_FIELD_LABELS: Record<string, string> = {
  ebay_sold_avg: "eBay sold pricing",
  mpb_retail: "MPB price",
  keh_retail: "KEH price",
  bh_used: "B&H used price",
  fair_price: "Estimated fair price",
  deal_threshold: "Target buy price",
};

/**
 * Strip snake_case variable names and bracketed system flags from an AI
 * warning line. Keeps the human-readable remainder.
 */
function humanizeWarning(raw: string): string {
  let cleaned = raw.replace(/\[[^\]]+\]/g, "").replace(/\b[a-z][a-z0-9_]*_[a-z0-9_]+\b/gi, (m) =>
    m.replace(/_/g, " ")
  );
  cleaned = cleaned.replace(/\s{2,}/g, " ").trim();
  if (cleaned.length === 0) return raw;
  return cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
}

/** Shorten a UTC ISO timestamp to a readable local datetime. */
function formatFetchedAt(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

// =============================================================================
// Styles
// =============================================================================

const cardHeaderStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  padding: "10px 16px",
  borderBottom: "1px solid var(--ui-border)",
  gap: "12px",
};

const cardBodyStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "220px 1fr",
  gap: "18px",
  padding: "14px 16px",
  // Top-align so a short content column doesn't leave vertical slack next to
  // the image. (Grid rows stretch by default — "start" pins both to the top.)
  alignItems: "start",
};

const imageColumnStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  // Sticky image so it stays visible while the reviewer scrolls long cards.
  position: "sticky",
  top: "12px",
};

const imageStyle: React.CSSProperties = {
  width: "220px",
  height: "220px",
  objectFit: "cover",
  borderRadius: "var(--radius-sm)",
  border: "1px solid var(--ui-border)",
  backgroundColor: "var(--ui-background)",
};

const contentColumnStyle: React.CSSProperties = {
  minWidth: 0,
};

const sectionHeaderStyle: React.CSSProperties = {
  fontSize: "13px",
  letterSpacing: "-0.005em",
  color: "var(--ui-text-primary)",
  fontWeight: 600,
  margin: "0 0 10px 0",
  paddingBottom: "6px",
  borderBottom: "1px solid var(--ui-divider)",
};

const fieldLabelStyle: React.CSSProperties = {
  fontSize: "12px",
  letterSpacing: "-0.005em",
  color: "var(--ui-text-secondary)",
  marginBottom: "2px",
  fontWeight: 600,
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "6px 8px",
  fontSize: "13px",
  border: "1px solid var(--ui-border)",
  borderRadius: "var(--radius-sm)",
  fontFamily: "inherit",
};

const textareaStyle: React.CSSProperties = {
  ...inputStyle,
  resize: "vertical",
  minHeight: "60px",
};

const readonlyStyle: React.CSSProperties = {
  fontSize: "13px",
  padding: "4px 0",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

const smallBtnStyle: React.CSSProperties = {
  fontSize: "12px",
  padding: "6px 12px",
};

const approvedBadgeStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "3px 10px",
  borderRadius: "var(--radius-pill)",
  backgroundColor: "var(--status-success)",
  color: "var(--brand-light)",
  fontSize: "12px",
  fontWeight: 600,
  letterSpacing: "0.005em",
};

const schemaWarnBadgeStyle: React.CSSProperties = {
  ...approvedBadgeStyle,
  backgroundColor: "#b45309", // amber
};

const apiErrorBadgeStyle: React.CSSProperties = {
  ...approvedBadgeStyle,
  backgroundColor: "var(--status-error)",
};

const warningsStyle: React.CSSProperties = {
  marginTop: "12px",
  padding: "10px 12px",
  backgroundColor: "var(--ui-background)",
  borderLeft: "3px solid #b45309",
  borderRadius: "var(--radius-sm)",
};

const sourcesTableStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
  padding: "6px 8px",
  backgroundColor: "var(--ui-background)",
  borderRadius: "var(--radius-sm)",
  border: "1px solid var(--ui-border)",
  maxHeight: "180px",
  overflowY: "auto",
};

const sourceRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  padding: "2px 0",
};

const pricingNotesStyle: React.CSSProperties = {
  marginTop: "10px",
  padding: "10px 12px",
  backgroundColor: "var(--status-warning-bg, #fffaeb)",
  borderLeft: "3px solid #b45309",
  borderRadius: "var(--radius-sm)",
};

const stickyFooterStyle: React.CSSProperties = {
  position: "sticky",
  bottom: 0,
  marginTop: "24px",
  padding: "14px 20px",
  backgroundColor: "var(--brand-dark)",
  color: "var(--brand-light)",
  borderRadius: "var(--radius-sm)",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: "16px",
  boxShadow: "0 -4px 12px rgba(0,0,0,0.15)",
};
