/**
 * App shell — navbar + routed page content.
 *
 * Routing is hash-based (see state/router.ts). The dormant DB-pipeline screens
 * (HomeScreen, NewJobScreen, JobDetailScreen, ReviewScreen) were removed in
 * Phase 6A — the app now has exactly three top-level screens: Prep, Inbound,
 * and Recent Batches. Prep is the landing page.
 */

import { useRoute } from "@/state/router";
import PrepScreen from "@/screens/PrepScreen";
import InboundScreen from "@/screens/InboundScreen";
import BatchesScreen from "@/screens/BatchesScreen";

export default function App() {
  const route = useRoute();

  return (
    <>
      <nav className="navbar">
        <a href="#/" style={{ color: "inherit", textDecoration: "none", display: "flex", alignItems: "center", gap: "14px" }}>
          {/* Brand lockup: logo next to wordmark. logo.png lives in /public.
              Logo is black-on-white, so the navbar bg is also white (Phase 6C)
              — letting the logo breathe instead of sitting in a boxed rectangle. */}
          <img
            src="/logo.png"
            alt="Service Photo"
            style={{ height: "48px", width: "auto", display: "block" }}
          />
          <span className="navbar__brand">
            Catalog Capture
          </span>
        </a>

        {/* Top-level nav links. Styled inline since the navbar only has a few. */}
        <div style={{ marginLeft: "auto", display: "flex", gap: "20px" }}>
          <NavLink active={route.kind === "prep"} href="#/">Upload</NavLink>
          <NavLink active={route.kind === "inbound"} href="#/inbound">Review</NavLink>
          <NavLink active={route.kind === "batches"} href="#/batches">Batch History</NavLink>
        </div>
      </nav>

      <main className="page">
        {route.kind === "prep" && <PrepScreen />}
        {route.kind === "inbound" && <InboundScreen batchId={route.batchId} />}
        {route.kind === "batches" && <BatchesScreen />}
      </main>
    </>
  );
}

function NavLink({ href, active, children }: { href: string; active: boolean; children: React.ReactNode }) {
  return (
    <a
      href={href}
      style={{
        color: active ? "var(--brand-primary)" : "var(--ui-text-secondary)",
        textDecoration: "none",
        fontSize: "14px",
        fontWeight: active ? 600 : 500,
        letterSpacing: "-0.005em",
        borderBottom: active ? "2px solid var(--brand-primary)" : "2px solid transparent",
        paddingBottom: "4px",
      }}
    >
      {children}
    </a>
  );
}
