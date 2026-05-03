/**
 * Minimal hash-based router.
 *
 * We're avoiding react-router to keep the dependency graph tiny for a POC.
 * Routes are expressed in the URL hash so back/forward and refresh all work.
 *
 * Supported routes:
 *   #/                           → { kind: "prep" }    — batch prep (home)
 *   #/inbound                    → { kind: "inbound" } — review all extractions
 *   #/inbound/batch/<batchId>    → { kind: "inbound", batchId } — filtered to one batch
 *   #/batches                    → { kind: "batches" } — recent-batches index
 *
 * Unknown hashes fall back to the home (prep) route. The dormant DB-pipeline
 * routes (#/jobs, #/jobs/new, #/jobs/:id, #/jobs/:id/review) were removed in
 * Phase 6A along with the screens that served them.
 */

import { useEffect, useState } from "react";

export type Route =
  | { kind: "prep" }
  | { kind: "inbound"; batchId?: string }
  | { kind: "batches" };

// Batch ids are URL-safe (we use the `2026-04-19T15-45-22Z` timestamp the
// backend stamps in meta). Allow alnum, dash, colon — colons survive in the
// hash fine and this keeps the regex tolerant for future id shapes.
const BATCH_ID_PATTERN = /^\/inbound\/batch\/([A-Za-z0-9:_-]+)$/;

function parse(hash: string): Route {
  // Strip the leading "#" if present. Accept both "#/" and "#" with no slash.
  const path = hash.replace(/^#/, "") || "/";

  if (path === "/" || path === "") return { kind: "prep" };
  if (path === "/inbound") return { kind: "inbound" };
  if (path === "/batches") return { kind: "batches" };

  const batchMatch = path.match(BATCH_ID_PATTERN);
  if (batchMatch) return { kind: "inbound", batchId: batchMatch[1] };

  return { kind: "prep" };
}

/** React hook: returns the current route and re-renders on hash changes. */
export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash));

  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  return route;
}

/** Imperatively navigate to a route. Triggers hashchange for the hook above. */
export function navigate(route: Route): void {
  const hash = routeToHash(route);
  if (window.location.hash === hash) {
    // Force a re-render when navigating to the same hash (e.g., after a
    // destructive action that should reload the current screen).
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  } else {
    window.location.hash = hash;
  }
}

export function routeToHash(route: Route): string {
  switch (route.kind) {
    case "prep":
      return "#/";
    case "inbound":
      return route.batchId ? `#/inbound/batch/${route.batchId}` : "#/inbound";
    case "batches":
      return "#/batches";
  }
}
