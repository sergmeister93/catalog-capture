Enterprise Design System Reference: Service Photo Integration
Version: 1.0
Target Integration: AI-Powered Enterprise Application (Gemini API)
This document serves as the formal UI/UX specification for the application development. It captures the visual language of the Service Photo framework to ensure consistency across the enterprise suite.
1. Core Visual Identity
Element
Specification
Primary Brand Color
#D12027 (Service Red)
Secondary Color
#222222 (Onyx Black)
Typography
Sans-Serif Stack: Roboto, Helvetica Neue, Arial
Border Radius
2px (Sharp, professional edges)

2. Design Tokens (CSS/Code Implementation)
The following tokens should be used in the application's root theme to maintain scalability and easy updates.
:root {
  /* Brand Colors */
  --brand-primary: #D12027;
  --brand-dark: #222222;
  --brand-light: #FFFFFF;
  
  /* UI Colors */
  --ui-background: #F8F9FA;
  --ui-border: #E5E5E5;
  --ui-text-primary: #1A1A1A;
  --ui-text-muted: #666666;
  
  /* AI/Gemini Specific Accents */
  --ai-accent-gradient: linear-gradient(90deg, #D12027 0%, #7B1113 100%);
  
  /* Spacing & Geometry */
  --radius-sm: 2px;
  --spacing-unit: 8px;
}


3. Component Specifications
Navigation Bar: High-contrast Onyx background (#222222) with white text. Top-tier categories should be uppercase with a 700 font weight.
Action Buttons: Primary actions must use the Service Red (#D12027) with white text. Hover states should darken to #A81A1F.
AI Interaction Surface: For Gemini API outputs, use a clean white card with a subtle 1px border (#E5E5E5). Use the AI accent gradient for loading states or "Generate" buttons to distinguish AI features while staying within the brand family.
4. Gemini API UI Considerations
When displaying model outputs within this framework:
Response Containers: Use a max-width of 800px for readability, aligned with the site's product grid logic.
Code Blocks: Use the Onyx Black (#222222) for background contrast in technical snippets.
Streaming Feedback: Use the Primary Red for the cursor or blinking indicator to maintain brand presence during real-time data retrieval.
Reference generated for internal project alignment and code file injection.

---

## Revision 2.0 — Phase 6G polish pass (2026-04-19)

The section above captures the **original** brand spec. Phase 6G deliberately expanded and, in a few places, **overrode** that spec for polish and readability. The canonical, up-to-date design system lives in [`frontend/src/index.css`](../frontend/src/index.css) — treat that file as the source of truth for token values. The notes below explain **what changed and why**, so future updates don't regress to v1.

### Deliberate overrides of the v1 spec

| v1 spec | v2 (Phase 6G) | Why |
|---|---|---|
| Border radius: **2px** everywhere | Scale: `sm` 6 / `md` 10 / `lg` 14 / `pill` 999. Cards use `lg`, buttons/inputs use `md`, chips use `sm` or `pill`. | Sergey's polish brief explicitly asked for 10–14px card radii. 2px "sharp" edges read as prototype/default; scaled radii read as deliberate enterprise SaaS. |
| Typography: **Roboto** stack for everything | **Inter** for UI body, **Manrope** (700) for the `.navbar__brand` wordmark. Both loaded via Google Fonts `@import` in `index.css`; `--font-sans` and `--font-display` tokens. | Separate display font gives the wordmark intentional presence without dragging the rest of the UI into marketing-font territory. Inter's OpenType tweaks (`cv02`/`cv03`/`cv04`/`cv11` + negative letter-spacing on headings) read cleaner than Roboto at small sizes. |
| Navbar: **Onyx Black** (#222) background, uppercase nav, 700 weight | **White** navbar, title-case nav, 500 default / 600 active with red underline on active. | Logo has a solid white canvas — black bar made it look boxed. Title-case is the product standard per the Phase 6G copy cleanup; all-caps reserved for genuinely small micro-labels. |

### Expanded token set (v2)

All defined in `index.css`:

- **Typography**: `--fs-xs` 12 · `--fs-sm` 13 · `--fs-base` 14 · `--fs-md` 15 · `--fs-lg` 16 · `--fs-xl` 18 · `--fs-2xl` 22 · `--fs-3xl` 30. Weights `--fw-regular`/`--fw-medium`/`--fw-semibold`/`--fw-bold`. Line heights `--lh-tight`/`--lh-snug`/`--lh-normal`/`--lh-relaxed`.
- **Spacing** (4/8px grid): `--space-1` 4 · `--space-2` 8 · `--space-3` 12 · `--space-4` 16 · `--space-5` 20 · `--space-6` 24 · `--space-8` 32 · `--space-10` 40 · `--space-12` 48. (Legacy `--spacing-unit` preserved.)
- **Radius**: `--radius-xs` 4 · `--radius-sm` 6 · `--radius-md` 10 · `--radius-lg` 14 · `--radius-pill` 999.
- **Shadows**: `--shadow-xs` / `--shadow-sm` / `--shadow-md` / `--shadow-lg` / `--shadow-focus` (brand-tinted ring) / `--shadow-focus-neutral`.
- **Neutrals**: `--ui-background` #f6f7f9 · `--ui-surface` #fff · `--ui-surface-muted` #f2f4f7 · `--ui-border` #e4e7eb · `--ui-border-strong` #cdd2da · `--ui-divider` #eceef1 · text `--ui-text-primary` #111827 / `--ui-text-secondary` #374151 / `--ui-text-muted` #6b7280 / `--ui-text-disabled` #9ca3af.
- **Semantic**: full color families (bg + text + border) for success / error / warning / info.

### Preserved from v1

- Brand primary `#d12027` (Service Red) — still drives primary CTAs, active nav underline, focus rings, AI accents.
- `--ai-accent-gradient` unchanged.

### New utility components (v2)

- `.btn-danger`, `.btn-ghost`, `.btn-sm`, `.btn-lg` (in addition to existing `.btn-primary` / `.btn-secondary`).
- `.status-pill--success` / `--error` / `--warning` / `--info`.
- `.card__section` (quiet internal divider using `--ui-divider`).
- `.action-bar` (translucent, blurred, sticky footer bar).
- Global form controls: `input` / `textarea` / `select` are styled by element (no class required) — 40px min height, `--radius-md`, inset shadow, focus ring, `aria-invalid` state.

### Copy/language rules (v2 scope)

Text-side rules that now apply across the product:

- **Title case** for labels, section titles, nav, and buttons.
- **Sentence case** for body and helper text.
- **No all-caps** except in genuinely tiny micro-labels (currently unused — the old uppercase field labels and section headers were removed).
- **No vendor / system / implementation strings in user copy** — no `Gemini`, `input_images/`, `snake_case_keys`, `[BRACKETED_FLAGS]`, raw UTC ISO timestamps, or raw file paths. The helpers `humanizeModelName`, `humanizePlatform`, `titleCaseCondition`, `humanizePricingTag`, `humanizeWarning`, and `formatFetchedAt` in `frontend/src/screens/InboundScreen.tsx` scrub these before render. Any new surface that renders AI output should route through the matching helper or add a new one.
- `—` (em dash) is the single convention for empty/unavailable values. Do not mix with `N/A`, blank, or dash-minus.


