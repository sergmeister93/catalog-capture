/**
 * PrepScreen — the first screen. Shows photos currently sitting in the
 * backend's input_images/ folder on the left, and a batch-name + Approve
 * panel on the right.
 *
 * "Approve → Send to Gemini" here actually kicks off extraction: one call to
 * POST /api/v1/inbound/extract with the batch name, followed by an automatic
 * hash-nav to the Inbound screen, which picks up the running job from
 * localStorage and resumes polling.
 *
 * Drag-and-drop: dropping image files anywhere on this screen POSTs them
 * to /inbound/input-images, which writes them into input_images/ and then
 * triggers a refresh of the thumbnail list. Both the top-of-rail drop zone
 * (also clickable for a native file picker) and a window-level overlay
 * accept drops — whichever the user reaches first.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  clearAllData,
  listInputImages,
  startExtraction,
  uploadInputImages,
  type InputImageFile,
  type UploadedFileResult,
} from "@/api/inbound";
import { navigate } from "@/state/router";
import { ACTIVE_EXTRACTION_KEY } from "@/state/extractionHandoff";

// Browser-side caches the "Clear Data" button also wipes, so the UI doesn't
// keep showing review state for items that no longer exist on the server.
// Keep this in sync with the keys defined in InboundScreen.tsx and
// extractionHandoff.ts — they're not exported because they're considered
// internal to those modules.
const REVIEW_STATE_KEY = "service-photo:inbound-review-state-v2";

type LoadState =
  | { kind: "loading" }
  | { kind: "loaded"; files: InputImageFile[] }
  | { kind: "error"; message: string };

type ApproveState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "error"; message: string };

type UploadState =
  | { kind: "idle" }
  | { kind: "uploading"; count: number }
  | { kind: "done"; results: UploadedFileResult[] }
  | { kind: "error"; message: string };

// Client-side extension gate — matches the backend IMAGE_SUFFIXES set.
// We only filter by extension here; the backend is the real authority.
const ALLOWED_EXTS = [".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"];

function isImageFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return ALLOWED_EXTS.some((ext) => name.endsWith(ext));
}

export default function PrepScreen() {
  const [loadState, setLoadState] = useState<LoadState>({ kind: "loading" });
  const [batchName, setBatchName] = useState("");
  const [approveState, setApproveState] = useState<ApproveState>({ kind: "idle" });
  const [uploadState, setUploadState] = useState<UploadState>({ kind: "idle" });
  // True while a drag is active anywhere over the window. Drives the
  // overlay + drop-zone visual state. We count dragenter/dragleave pairs
  // with a ref because child elements fire dragleave when the drag crosses
  // into them, which would otherwise flicker the state off and on.
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const refresh = useCallback(async () => {
    setLoadState({ kind: "loading" });
    try {
      const data = await listInputImages();
      setLoadState({ kind: "loaded", files: data.files });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setLoadState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Upload path shared by the drop zone, the window-level overlay, and the
  // click-to-browse file input. Filters junk extensions client-side, POSTs
  // the rest, then reloads the thumbnail list.
  const handleFiles = useCallback(
    async (incoming: FileList | File[]) => {
      const all = Array.from(incoming);
      const images = all.filter(isImageFile);
      if (images.length === 0) {
        setUploadState({
          kind: "error",
          message: "No image files in drop. Supported: JPG, PNG, HEIC, WebP.",
        });
        return;
      }
      setUploadState({ kind: "uploading", count: images.length });
      try {
        const response = await uploadInputImages(images);
        setUploadState({ kind: "done", results: response.results });
        // Pull the fresh list so newly-uploaded files appear immediately.
        void refresh();
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        setUploadState({ kind: "error", message });
      }
    },
    [refresh],
  );

  // Full reset: deletes every uploaded image, every extraction JSON, and
  // every exported CSV from the persistent volume, plus the browser-side
  // review/handoff state. Gated behind window.confirm so a stray click can't
  // wipe a working batch. Pre-Cloudflare-Access this is the only "I'm done,
  // start over" affordance — once Access is in place we may layer auth on
  // top, but the destructive nature is the same either way.
  const handleClearData = useCallback(async () => {
    const ok = window.confirm(
      "Clear ALL data?\n\n" +
        "This permanently deletes every uploaded image, every extraction result, " +
        "and every exported CSV on the server, plus your in-progress review " +
        "state in this browser.\n\n" +
        "This cannot be undone. Continue?",
    );
    if (!ok) return;

    try {
      const result = await clearAllData();
      try {
        localStorage.removeItem(ACTIVE_EXTRACTION_KEY);
        localStorage.removeItem(REVIEW_STATE_KEY);
      } catch {
        // localStorage can throw in private mode — best-effort only.
      }
      void refresh();
      window.alert(
        `Cleared ${result.input_images_deleted} image(s), ` +
          `${result.inbound_deleted} extraction(s), ` +
          `${result.exports_deleted} export(s), ` +
          `${result.db_rows_deleted} review/job record(s).`,
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      window.alert(`Clear failed: ${message}`);
    }
  }, [refresh]);

  // Window-level drag tracking. Attached once on mount. We preventDefault on
  // every dragover so the browser doesn't navigate to the file on drop.
  useEffect(() => {
    const onDragEnter = (e: DragEvent) => {
      if (!e.dataTransfer || !Array.from(e.dataTransfer.types).includes("Files")) return;
      dragCounter.current += 1;
      setIsDragging(true);
    };
    const onDragLeave = () => {
      dragCounter.current = Math.max(0, dragCounter.current - 1);
      if (dragCounter.current === 0) setIsDragging(false);
    };
    const onDragOver = (e: DragEvent) => {
      // Required — without this the drop event never fires.
      if (e.dataTransfer && Array.from(e.dataTransfer.types).includes("Files")) {
        e.preventDefault();
      }
    };
    const onDrop = (e: DragEvent) => {
      if (!e.dataTransfer || !Array.from(e.dataTransfer.types).includes("Files")) return;
      e.preventDefault();
      dragCounter.current = 0;
      setIsDragging(false);
      if (e.dataTransfer.files.length > 0) {
        void handleFiles(e.dataTransfer.files);
      }
    };
    window.addEventListener("dragenter", onDragEnter);
    window.addEventListener("dragleave", onDragLeave);
    window.addEventListener("dragover", onDragOver);
    window.addEventListener("drop", onDrop);
    return () => {
      window.removeEventListener("dragenter", onDragEnter);
      window.removeEventListener("dragleave", onDragLeave);
      window.removeEventListener("dragover", onDragOver);
      window.removeEventListener("drop", onDrop);
    };
  }, [handleFiles]);

  const files = loadState.kind === "loaded" ? loadState.files : [];
  const trimmedName = batchName.trim();
  const canApprove =
    loadState.kind === "loaded" &&
    files.length > 0 &&
    trimmedName.length > 0 &&
    approveState.kind !== "submitting";

  async function handleApprove() {
    setApproveState({ kind: "submitting" });
    try {
      const started = await startExtraction(trimmedName);
      // Hand off the running job id to the Inbound screen via localStorage.
      // Picking the hash alone wouldn't carry job_id without another fetch,
      // and localStorage survives the hash change cleanly.
      try {
        localStorage.setItem(
          ACTIVE_EXTRACTION_KEY,
          JSON.stringify({
            job_id: started.job_id,
            total: started.total,
            batch_name: trimmedName,
          }),
        );
      } catch {
        // Private-mode browsers: InboundScreen still works, it just won't
        // auto-resume the poll — user will see completed cards on arrival.
      }
      navigate({ kind: "inbound" });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setApproveState({ kind: "error", message });
    }
  }

  const failedUploads =
    uploadState.kind === "done" ? uploadState.results.filter((r) => !r.ok) : [];
  const succeededUploads =
    uploadState.kind === "done" ? uploadState.results.filter((r) => r.ok) : [];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "380px 1fr", gap: "24px", alignItems: "start" }}>
      {/* ========== LEFT RAIL: input images ========== */}
      <aside className="card" style={{ padding: 0, position: "sticky", top: "16px" }}>
        <header style={leftRailHeaderStyle}>
          <div>
            <h2 style={{ margin: 0, fontSize: "14px" }}>Upload Images</h2>
            <div className="text-muted" style={{ fontSize: "11px", marginTop: "2px" }}>
              {loadState.kind === "loaded"
                ? files.length === 0
                  ? "No images added yet"
                  : `${files.length} image${files.length === 1 ? "" : "s"} added`
                : "\u00A0"}
            </div>
          </div>
          <div style={{ display: "flex", gap: "6px" }}>
            <button
              className="btn btn-secondary"
              onClick={refresh}
              disabled={loadState.kind === "loading"}
              style={{ fontSize: "11px", padding: "4px 8px" }}
              title="Check for newly added images"
            >
              {loadState.kind === "loading" ? "…" : "Check for Images"}
            </button>
            <button
              className="btn btn-secondary"
              onClick={handleClearData}
              style={{ fontSize: "11px", padding: "4px 8px" }}
              title="Delete all uploaded images, extractions, and exports"
            >
              Clear Data
            </button>
          </div>
        </header>

        {/* Hidden file input — the drop zone triggers a click on this for
            the native file picker fallback. Keeps keyboard/ARIA users happy
            too: the zone is a <button> so it gets focus + Enter/Space. */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,.heic,.heif"
          multiple
          style={{ display: "none" }}
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              void handleFiles(e.target.files);
            }
            // Reset so picking the same file twice in a row re-fires change.
            e.target.value = "";
          }}
        />

        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          style={{
            ...dropZoneStyle,
            borderColor: isDragging ? "var(--brand-primary)" : "var(--ui-border-strong)",
            backgroundColor: isDragging ? "rgba(209, 32, 39, 0.06)" : "var(--ui-background)",
          }}
          disabled={uploadState.kind === "uploading"}
        >
          <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--brand-dark)" }}>
            {uploadState.kind === "uploading"
              ? `Uploading ${uploadState.count} file${uploadState.count === 1 ? "" : "s"}…`
              : isDragging
              ? "Drop to upload"
              : "Drag images here"}
          </div>
          <div className="text-muted" style={{ fontSize: "12px", marginTop: "4px" }}>
            or click to browse
          </div>
          <div className="text-muted" style={{ fontSize: "11px", marginTop: "2px" }}>
            Supported formats: JPG, PNG, HEIC, WebP
          </div>
        </button>

        {/* Upload result summary — shown under the zone so it doesn't push
            the thumbnails too far down. Per-file failures listed explicitly
            so a mis-named file doesn't silently vanish. */}
        {uploadState.kind === "done" && (
          <div style={uploadResultStyle}>
            {succeededUploads.length > 0 && (
              <div style={{ color: "var(--status-success)", fontSize: "12px" }}>
                ✓ Uploaded {succeededUploads.length} file{succeededUploads.length === 1 ? "" : "s"}
              </div>
            )}
            {failedUploads.map((r) => (
              <div
                key={r.original_name}
                style={{ color: "var(--status-error)", fontSize: "11px", marginTop: "2px" }}
                title={r.error ?? undefined}
              >
                ✗ {r.original_name}: {r.error}
              </div>
            ))}
          </div>
        )}
        {uploadState.kind === "error" && (
          <div style={{ ...uploadResultStyle, color: "var(--status-error)", fontSize: "12px" }}>
            {uploadState.message}
          </div>
        )}

        <div style={{ maxHeight: "60vh", overflowY: "auto" }}>
          {loadState.kind === "loading" && (
            <div style={{ padding: "16px" }} className="text-muted">Loading…</div>
          )}
          {loadState.kind === "error" && (
            <div style={{ padding: "16px", color: "var(--status-error)" }}>
              Couldn't read folder: {loadState.message}
            </div>
          )}
          {loadState.kind === "loaded" && files.length === 0 && (
            <div style={{ padding: "16px" }} className="text-muted">
              No images added yet.
            </div>
          )}
          {loadState.kind === "loaded" && files.map((file, index) => (
            <div key={file.file_name} style={thumbRowStyle}>
              <img src={file.image_url} alt={file.file_name} style={thumbImgStyle} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--ui-text-muted)" }}>
                  #{index + 1}
                </div>
                <div
                  style={{ fontSize: "12px", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                  title={file.file_name}
                >
                  {file.file_name}
                </div>
                <div className="text-muted" style={{ fontSize: "11px" }}>
                  {formatBytes(file.file_size_bytes)}
                </div>
              </div>
            </div>
          ))}
        </div>
      </aside>

      {/* ========== RIGHT PANEL: batch metadata + Approve ========== */}
      <section>
        <h1 style={{ margin: "0 0 4px 0" }}>Create New Batch</h1>
        <p className="text-muted" style={{ marginTop: 0 }}>
          Create one batch for each item or group of items. Add images on the
          left, enter a batch name, then start analysis to send the images for
          AI review.
        </p>

        <div className="card">
          <label style={fieldLabelStyle} htmlFor="batch-name">Batch Name</label>
          <input
            id="batch-name"
            type="text"
            value={batchName}
            onChange={(e) => setBatchName(e.target.value)}
            placeholder="batchname_uploadername"
            style={batchNameInputStyle}
            disabled={approveState.kind === "submitting"}
          />
          <div className="text-muted" style={{ fontSize: "12px", marginTop: "6px" }}>
            This name will appear in Batch History.
          </div>

          <div style={summaryRowStyle}>
            <div style={summaryNumberStyle}>{files.length}</div>
            <div>
              <div style={{ fontSize: "14px", fontWeight: 500 }}>
                image{files.length === 1 ? "" : "s"} ready
              </div>
              <div className="text-muted" style={{ fontSize: "12px" }}>
                {files.length === 0 ? "Add images to continue" : "Ready for analysis"}
              </div>
            </div>
          </div>

          {approveState.kind === "error" && (
            <div style={errorBannerStyle}>
              <strong>Couldn't start extraction.</strong>
              <div className="text-muted" style={{ fontSize: "12px", marginTop: "4px" }}>
                {approveState.message}
              </div>
            </div>
          )}

          <button
            className="btn btn-primary"
            onClick={handleApprove}
            disabled={!canApprove}
            style={{ marginTop: "16px", minWidth: "160px", fontSize: "15px", padding: "12px 20px" }}
          >
            {approveState.kind === "submitting" ? "Starting…" : "Start Analysis"}
          </button>
          {!canApprove && approveState.kind !== "submitting" && (
            <div className="text-muted" style={{ fontSize: "12px", marginTop: "8px" }}>
              {files.length === 0 && trimmedName.length === 0
                ? "Enter a batch name and add images to continue"
                : files.length === 0
                ? "Add at least one image to continue"
                : "Enter a batch name to continue"}
            </div>
          )}
        </div>

        <p className="text-muted" style={{ fontSize: "12px" }}>
          Looking for an earlier batch?{" "}
          <a href="#/batches">View Batch History →</a>
        </p>
      </section>

      {/* Full-window drag overlay — appears the moment a drag enters the
          page, so users get a visible "yes you can drop here" hint even if
          they aren't aiming at the left-rail zone. Pointer-events: none so
          it doesn't intercept the drop itself; the window-level listener
          handles the drop. */}
      {isDragging && (
        <div style={dragOverlayStyle}>
          <div style={dragOverlayPanelStyle}>
            <div style={{ fontSize: "24px", fontWeight: 700, color: "var(--brand-primary)" }}>
              Drop photos to upload
            </div>
            <div className="text-muted" style={{ marginTop: "8px" }}>
              JPG, PNG, HEIC, WebP — up to 25 MB each
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------- Helpers ----------

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// ---------- Styles ----------

const leftRailHeaderStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  padding: "14px 16px",
  borderBottom: "1px solid var(--ui-border)",
  backgroundColor: "var(--ui-background)",
};

const dropZoneStyle: React.CSSProperties = {
  display: "block",
  width: "calc(100% - 24px)",
  margin: "12px",
  padding: "18px 12px",
  border: "2px dashed var(--ui-border-strong)",
  borderRadius: "var(--radius-sm)",
  cursor: "pointer",
  textAlign: "center",
  fontFamily: "inherit",
  transition: "border-color 120ms ease, background-color 120ms ease",
};

const uploadResultStyle: React.CSSProperties = {
  padding: "8px 16px",
  borderBottom: "1px solid var(--ui-border)",
  backgroundColor: "var(--ui-background)",
};

const thumbRowStyle: React.CSSProperties = {
  display: "flex",
  gap: "10px",
  padding: "10px 12px",
  borderBottom: "1px solid var(--ui-border)",
  alignItems: "center",
};

const thumbImgStyle: React.CSSProperties = {
  width: "56px",
  height: "56px",
  objectFit: "cover",
  borderRadius: "var(--radius-sm)",
  backgroundColor: "var(--ui-background)",
  flexShrink: 0,
};

const fieldLabelStyle: React.CSSProperties = {
  display: "block",
  fontSize: "13px",
  fontWeight: 600,
  marginBottom: "6px",
  letterSpacing: "-0.005em",
  color: "var(--ui-text-secondary)",
};

const batchNameInputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  fontSize: "15px",
  border: "1px solid var(--ui-border)",
  borderRadius: "var(--radius-sm)",
  fontFamily: "inherit",
  backgroundColor: "var(--brand-light)",
};

const summaryRowStyle: React.CSSProperties = {
  marginTop: "20px",
  paddingTop: "16px",
  borderTop: "1px solid var(--ui-border)",
  display: "flex",
  alignItems: "center",
  gap: "12px",
};

const summaryNumberStyle: React.CSSProperties = {
  fontSize: "32px",
  fontWeight: 700,
  color: "var(--brand-primary)",
  lineHeight: 1,
  minWidth: "40px",
  textAlign: "center",
};

const errorBannerStyle: React.CSSProperties = {
  marginTop: "16px",
  padding: "14px",
  backgroundColor: "#fef2f2",
  color: "var(--status-error)",
  border: "1px solid var(--status-error)",
  borderRadius: "var(--radius-sm)",
  fontSize: "14px",
};

const dragOverlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  backgroundColor: "rgba(26, 26, 26, 0.45)",
  backdropFilter: "blur(2px)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
  pointerEvents: "none",
};

const dragOverlayPanelStyle: React.CSSProperties = {
  backgroundColor: "var(--brand-light)",
  border: "3px dashed var(--brand-primary)",
  borderRadius: "var(--radius-sm)",
  padding: "40px 60px",
  textAlign: "center",
  boxShadow: "0 10px 30px rgba(0, 0, 0, 0.25)",
};
