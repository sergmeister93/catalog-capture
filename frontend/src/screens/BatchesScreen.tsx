/**
 * BatchesScreen — index of Gemini extraction batches.
 *
 * Each row = one Prep-initiated extraction run, assembled by the backend
 * from per-image artifacts grouped by (batch_name, batch_started_at_utc).
 * Click a row to jump to Inbound filtered to just that batch's cards.
 *
 * No localStorage, no DB — the filesystem is the source of truth. Deleting
 * files from inbound/ makes a batch disappear; running a new extraction
 * (with purge_existing=true) replaces the list.
 */

import { useCallback, useEffect, useState } from "react";
import { listBatches, type BatchSummary } from "@/api/inbound";

type LoadState =
  | { kind: "loading" }
  | { kind: "loaded"; batches: BatchSummary[] }
  | { kind: "error"; message: string };

export default function BatchesScreen() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  const refresh = useCallback(async () => {
    setState({ kind: "loading" });
    try {
      const data = await listBatches();
      setState({ kind: "loaded", batches: data.batches });
    } catch (err) {
      setState({
        kind: "error",
        message: err instanceof Error ? err.message : String(err),
      });
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "16px" }}>
        <div>
          <h1 style={{ margin: "0 0 4px 0" }}>Recent Batches</h1>
          <p className="text-muted" style={{ margin: 0 }}>
            One row per extraction run. Click to review the cards from that
            batch. Start a new one from <a href="#/">Upload</a>.
          </p>
        </div>
        <button
          className="btn btn-secondary"
          onClick={refresh}
          disabled={state.kind === "loading"}
          style={{ fontSize: "12px" }}
        >
          {state.kind === "loading" ? "Loading…" : "Refresh"}
        </button>
      </header>

      {state.kind === "loading" && <div className="card text-muted">Loading…</div>}

      {state.kind === "error" && (
        <div className="card" style={{ borderColor: "var(--status-error)" }}>
          <strong style={{ color: "var(--status-error)" }}>Couldn't load batches.</strong>
          <div className="text-muted" style={{ marginTop: "4px", fontSize: "12px" }}>{state.message}</div>
        </div>
      )}

      {state.kind === "loaded" && state.batches.length === 0 && (
        <div className="card text-muted">
          No batches yet. Head to <a href="#/">Upload</a>, name an upload, and click{" "}
          <em>Approve → Send to Gemini</em>.
        </div>
      )}

      {state.kind === "loaded" &&
        state.batches.map((batch) => <BatchRow key={batch.batch_id} batch={batch} />)}
    </div>
  );
}

function BatchRow({ batch }: { batch: BatchSummary }) {
  // Legacy batches (no batch_started_at_utc in meta) get a synthetic
  // "__legacy__" id; they're not filterable, so we render them as a plain
  // grouping header rather than a link to avoid a 404'd filter.
  const isLegacy = batch.batch_id === "__legacy__";
  const href = isLegacy ? undefined : `#/inbound/batch/${batch.batch_id}`;

  const title = batch.batch_name ?? (isLegacy ? "Legacy extractions" : "Unnamed batch");
  const subtitle = formatBatchSubtitle(batch);

  const content = (
    <div style={batchRowInnerStyle}>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: "15px", fontWeight: 600, color: "var(--brand-dark)" }}>{title}</div>
        <div className="text-muted" style={{ fontSize: "12px", marginTop: "2px" }}>{subtitle}</div>
      </div>
      <div style={batchCountsStyle}>
        <Counter label="images" value={batch.image_count} />
        <Counter label="ok" value={batch.succeeded} color="var(--status-success)" />
        {batch.failed > 0 && <Counter label="failed" value={batch.failed} color="var(--status-error)" />}
      </div>
    </div>
  );

  return href ? (
    <a href={href} style={batchRowLinkStyle} className="card">
      {content}
    </a>
  ) : (
    <div className="card" style={{ marginBottom: "10px" }}>{content}</div>
  );
}

function Counter({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div style={{ minWidth: "56px", textAlign: "right" }}>
      <div style={{ fontSize: "18px", fontWeight: 700, color: color ?? "var(--brand-dark)" }}>{value}</div>
      <div className="text-muted" style={{ fontSize: "10px", textTransform: "uppercase", letterSpacing: "0.04em" }}>
        {label}
      </div>
    </div>
  );
}

function formatBatchSubtitle(batch: BatchSummary): string {
  const parts: string[] = [];
  if (batch.started_at_utc) parts.push(formatTimestamp(batch.started_at_utc));
  if (batch.model) parts.push(batch.model);
  return parts.join(" · ") || "—";
}

/**
 * Backend stamps batch_started_at_utc as a standard ISO instant
 * ("2026-04-19T15:45:22Z"). Pretty-print locally for display. If parsing
 * fails (e.g. the meta field is garbled), fall back to the raw string.
 */
function formatTimestamp(raw: string): string {
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const batchRowInnerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "16px",
};

const batchCountsStyle: React.CSSProperties = {
  display: "flex",
  gap: "14px",
  alignItems: "center",
};

const batchRowLinkStyle: React.CSSProperties = {
  display: "block",
  textDecoration: "none",
  color: "inherit",
  marginBottom: "10px",
};
