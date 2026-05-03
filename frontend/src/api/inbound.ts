/**
 * Typed client for the inbound-folder endpoints (the new per-image flow).
 *
 * These bypass the existing /jobs DB pipeline entirely. They serve extraction
 * artifacts from the repo's inbound/ folder, and write CSVs to exports/.
 *
 * All shapes mirror the Pydantic models in
 * backend/src/service_photo/api/inbound_routes.py — keep them in sync.
 */

const API_BASE = "/api/v1";

// --- Shapes ------------------------------------------------------------------

/** One Gemini-extracted listing (the "response" block from the artifact JSON). */
export interface ListingResponse {
  schema_version?: string;
  extraction_warnings?: string[] | null;
  overview: ListingOverview;
  description: ListingDescription;
  specifications: ListingSpecifications;
  accessories: ListingAccessories;
}

export interface ListingOverview {
  product_name?: string | null;
  brand?: string | null;
  model?: string | null;
  product_family?: string | null;
  variant?: string | null;
  mount_type?: string | null;
  serial_number_visible?: string | null;
  condition_summary?: string | null;
  confidence_notes?: string | null;
}

export interface ListingDescription {
  short_title?: string | null;
  description_text?: string | null;
  visible_wear_notes?: string | null;
  key_selling_points?: string | null;
  confidence_notes?: string | null;
}

/**
 * Spec values are typed as `unknown` for the numeric-looking ones because
 * Gemini occasionally returns strings like "33MP" instead of a number.
 * The UI tolerates both shapes — see formatSpecValue in InboundScreen.
 */
export interface ListingSpecifications {
  sensor_format?: string | null;
  megapixels?: unknown;
  lens_mount?: string | null;
  focal_length?: string | null;
  aperture?: string | null;
  iso_range?: string | null;
  shutter_range?: string | null;
  video_capabilities?: string | null;
  storage_media?: string | null;
  connectivity?: string | null;
  weight_grams?: unknown;
  other_specifications?: Record<string, unknown> | null;
  confidence_notes?: string | null;
}

export interface ListingAccessories {
  included_accessories_text?: string | null;
  inferred_accessories_text?: string | null;
  missing_typical_accessories_text?: string | null;
  confidence_notes?: string | null;
}

/** One artifact card. */
export interface InboundItem {
  extraction_id: string;
  file_name: string;
  image_files: string[];
  image_urls: string[];
  meta: {
    started_at_utc?: string;
    finished_at_utc?: string;
    duration_ms?: number;
    model?: string;
    schema_valid?: boolean;
    schema_error?: string | null;
    api_error?: string | null;
    // Phase 5 (single-pass) meta fields — stamped when the combined
    // extraction+pricing call returned a pricing block.
    pricing_fetched_at_utc?: string | null;
    pricing_web_search_enabled?: boolean | null;
    // Phase 6 batch identity — stamped by the Prep-initiated extraction
    // endpoint so Recent Batches can group artifacts. Null for legacy
    // CLI-started runs that predate the Prep flow.
    batch_name?: string | null;
    batch_started_at_utc?: string | null;
    [key: string]: unknown;
  };
  response: ListingResponse | null;
  /** Phase 5 pricing block — populated by the same Gemini call that produced the extraction. Null when Gemini returned no pricing. */
  pricing: PricingBlock | null;
}

// --- Pricing shapes (Phase 5) ------------------------------------------------
// Shape of the optional `pricing` block Gemini returns inline with the
// extraction. All fields are optional because Gemini may return partial data
// for some platforms. The UI tolerates null/missing everywhere.

export interface PricingBlock {
  schema_version?: string;
  product?: string | null;
  pricing?: PricingPlatforms | null;
  market_valuation?: PricingValuation | null;
  market_summary?: string | null;
  sources?: PricingSource[] | null;
  uncertainty_tags?: string[] | null;
  fetched_at_utc?: string | null;
}

export interface PricingPlatforms {
  ebay_sold_avg?: number | null;
  mpb_retail?: number | null;
  keh_retail?: number | null;
  bh_used?: number | null;
}

export interface PricingValuation {
  fair_price?: number | null;
  deal_threshold?: number | null;
}

export interface PricingSource {
  platform?: string | null;
  url?: string | null;
  price?: number | null;
  title?: string | null;
  condition?: string | null;
  observed_at?: string | null;
}

export interface InboundListResponse {
  items: InboundItem[];
  inbound_dir: string;
}

export interface ExportRequestItem {
  extraction_id: string;
  image_files: string[];
  response: ListingResponse;
  /** Optional pricing block (possibly edited by the reviewer) included in the exported CSV row. */
  pricing?: PricingBlock | null;
}

export interface ExportResponse {
  csv_path: string;
  csv_filename: string;
  row_count: number;
  exported_at_utc: string;
}

// --- Extraction job shapes ---------------------------------------------------

export type ExtractionStatus = "queued" | "running" | "completed" | "failed";

/** Per-image outcome inside an extraction job. */
export interface ExtractionImageStatus {
  image_name: string;
  success: boolean;
  duration_ms: number;
  api_error: string | null;
  schema_valid: boolean;
  schema_error: string | null;
}

/** Full state of one extraction run. Returned by GET /inbound/extract/:id. */
export interface ExtractionJob {
  job_id: string;
  status: ExtractionStatus;
  total: number;
  completed: number;
  succeeded: number;
  failed: number;
  current_image: string | null;
  started_at_utc: string;
  finished_at_utc: string | null;
  model: string | null;
  error: string | null;
  results: ExtractionImageStatus[];
}

export interface ExtractStartResponse {
  job_id: string;
  status: ExtractionStatus;
  total: number;
}

// --- Input-image listing (Prep screen) --------------------------------------

export interface InputImageFile {
  file_name: string;
  file_size_bytes: number;
  image_url: string;
}

export interface InputImagesResponse {
  files: InputImageFile[];
  input_dir: string;
}

export async function listInputImages(): Promise<InputImagesResponse> {
  const r = await fetch(`${API_BASE}/inbound/input-images`, {
    headers: { Accept: "application/json" },
  });
  if (!r.ok) throw new Error(`GET /inbound/input-images failed: ${r.status}`);
  return (await r.json()) as InputImagesResponse;
}

/** Per-file outcome returned by the upload endpoint. */
export interface UploadedFileResult {
  original_name: string;
  saved_name: string | null;
  file_size_bytes: number | null;
  image_url: string | null;
  ok: boolean;
  error: string | null;
}

export interface UploadInputImagesResponse {
  results: UploadedFileResult[];
  input_dir: string;
}

/**
 * Upload one or more image files into input_images/ via multipart/form-data.
 * The backend validates filename shape, extension, and size per file; failures
 * are reported per-file in the response rather than aborting the whole batch.
 */
export async function uploadInputImages(
  files: File[],
): Promise<UploadInputImagesResponse> {
  const form = new FormData();
  for (const file of files) {
    // Field name must be "files" to match the FastAPI list[UploadFile] param.
    form.append("files", file, file.name);
  }
  const r = await fetch(`${API_BASE}/inbound/input-images`, {
    method: "POST",
    body: form,
    // Do NOT set Content-Type — the browser will set it with the correct
    // multipart boundary. Setting it manually breaks the parse.
  });
  if (!r.ok) throw new Error(`POST /inbound/input-images failed: ${r.status}`);
  return (await r.json()) as UploadInputImagesResponse;
}

// --- Batch listing (Recent Batches screen) ----------------------------------

export interface BatchSummary {
  batch_id: string;
  batch_name: string | null;
  started_at_utc: string | null;
  image_count: number;
  succeeded: number;
  failed: number;
  image_files: string[];
  model: string | null;
}

export interface BatchesResponse {
  batches: BatchSummary[];
}

export async function listBatches(): Promise<BatchesResponse> {
  const r = await fetch(`${API_BASE}/inbound/batches`, {
    headers: { Accept: "application/json" },
  });
  if (!r.ok) throw new Error(`GET /inbound/batches failed: ${r.status}`);
  return (await r.json()) as BatchesResponse;
}

// --- Calls --------------------------------------------------------------------

export async function listInbound(): Promise<InboundListResponse> {
  const r = await fetch(`${API_BASE}/inbound`, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error(`GET /inbound failed: ${r.status}`);
  return (await r.json()) as InboundListResponse;
}

/**
 * Kick off a Gemini extraction over every image in input_images/.
 * Returns immediately with a job_id the caller can poll. The backend runs
 * the extraction in a daemon thread; inbound/ is purged first so the UI
 * reflects only the latest run.
 *
 * `batchName` (from the Prep screen) is stamped into every resulting
 * artifact's meta so Recent Batches can group them back.
 */
export async function startExtraction(batchName?: string | null): Promise<ExtractStartResponse> {
  const r = await fetch(`${API_BASE}/inbound/extract`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ batch_name: batchName ?? null }),
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`POST /inbound/extract failed: ${r.status} ${text}`);
  }
  return (await r.json()) as ExtractStartResponse;
}

/** Poll the current state of an extraction job. */
export async function getExtractionStatus(jobId: string): Promise<ExtractionJob> {
  const r = await fetch(`${API_BASE}/inbound/extract/${encodeURIComponent(jobId)}`, {
    headers: { Accept: "application/json" },
  });
  if (!r.ok) throw new Error(`GET /inbound/extract/${jobId} failed: ${r.status}`);
  return (await r.json()) as ExtractionJob;
}

export async function exportInbound(
  items: ExportRequestItem[],
  approvedBy?: string
): Promise<ExportResponse> {
  const r = await fetch(`${API_BASE}/inbound/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ items, approved_by: approvedBy ?? null }),
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`POST /inbound/export failed: ${r.status} ${text}`);
  }
  return (await r.json()) as ExportResponse;
}

