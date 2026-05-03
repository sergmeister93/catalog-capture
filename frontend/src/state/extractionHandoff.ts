/**
 * Tiny cross-screen handoff for "extraction just kicked off" state.
 *
 * PrepScreen kicks off POST /inbound/extract and navigates the user to the
 * Inbound screen. Inbound needs the new job_id to resume polling, but the
 * hash alone can't carry it cleanly. We stash {job_id, total, batch_name}
 * in localStorage under this key; Inbound reads + clears it on mount.
 *
 * If localStorage is unavailable (private mode), the handoff silently no-ops
 * and Inbound just renders whatever cards the backend already has on disk.
 */

export const ACTIVE_EXTRACTION_KEY = "service-photo:active-extraction-v1";

export interface ActiveExtractionHandoff {
  job_id: string;
  total: number;
  batch_name: string | null;
}

export function readActiveExtraction(): ActiveExtractionHandoff | null {
  try {
    const raw = localStorage.getItem(ACTIVE_EXTRACTION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ActiveExtractionHandoff;
    if (!parsed || typeof parsed.job_id !== "string") return null;
    return parsed;
  } catch {
    return null;
  }
}

export function clearActiveExtraction(): void {
  try {
    localStorage.removeItem(ACTIVE_EXTRACTION_KEY);
  } catch {
    // Ignore — key was never set in private-mode browsers.
  }
}
