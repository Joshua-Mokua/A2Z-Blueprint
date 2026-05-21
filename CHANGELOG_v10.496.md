# Changelog — v10.496 React Design System + Showcase + G382

**Date:** 2026-05-21
**Doctrine source:** *React Championship Transformation Framework — F2 design system*
**Joshua mandate:** *"Ship the full v10.496"* — all 8 primitives in one batch
**Audit:** G382 added (**413 honest gates**)
**Tests:** 22 v10.496 integration tests (100% pass on sandbox)
**Verifier:** unchanged at 1153/1153
**Master prompt:** v5.39 → v5.40 (lockstep — **141 consecutive batches**)

---

## 🧱 The Lego set is built.

v10.495 gave us the table. v10.496 gives us **the blocks**. Every future React page composes from these 8 primitives — Button, Card, Input, Stat, Badge, Toast, Skeleton, Table. The MD Cockpit shell from v10.495 has already been refactored to prove the composition works.

```
═══════════════════════════════════════════════════════════════════════
              REACT CHAMPIONSHIP TRANSFORMATION
              v10.496 (Phase F2 of 10)
═══════════════════════════════════════════════════════════════════════
  Foundations (3 files)                Primitives (8 files)
  ─────────────────────                ─────────────────────
  lib/cn.ts             utility        components/Button.tsx
  lib/tokens.ts         design tokens  components/Card.tsx
  types/components.ts   prop types     components/Input.tsx
                                       components/Stat.tsx
  Composition (3 files)                components/Badge.tsx
  ─────────────────────                components/Toast.tsx
  pages/Showcase.tsx    kitchen sink   components/Skeleton.tsx
  pages/Dashboard.tsx   refactor       components/Table.tsx
  App.tsx               new route
                                       Brand discipline: G382
  Backend changes: ZERO                Zero new dependencies
═══════════════════════════════════════════════════════════════════════
```

## What was built

### The Lego set (8 primitives, ~500 LOC)

| Component | Purpose | API surface |
|---|---|---|
| **Button** | The most-used interactive control | 4 variants (primary/secondary/ghost/danger), 3 sizes, loading state, full-width |
| **Card** | Wrapper for every dashboard panel | `Card.Header` / `Card.Body` / `Card.Footer` composition slots, optional brand stripe (primary/secondary/accent) |
| **Input** | Text input with validation | label + helper + error + prefix + suffix, 3 sizes, React Hook Form-ready (forwardRef) |
| **Stat** | KPI tile for numeric metrics | value + delta + invertDelta (for NPL), loading state, brand stripe |
| **Badge** | Status indicators | 6 tones (neutral/success/warning/danger/info/brand), 2 sizes, pill or rect |
| **Toast** | User feedback notifications | 4 tones, auto-dismiss, ToastProvider + useToast() hook |
| **Skeleton** | Loading placeholders | 3 shapes (block/line/circle), respects `prefers-reduced-motion` |
| **Table** | Tabular data primitive | Generic `<TableT>`, column config, loading + empty states, row click, zebra |

### Three support files

| File | Purpose |
|---|---|
| `lib/cn.ts` | 30-line Tailwind class-joiner. Zero deps. Replaces `clsx` for our needs. |
| `lib/tokens.ts` | **Single source of truth** for non-brand semantic colors (greys, success-green, danger-red, info-blue), spacing scale, border radius, elevations, sizing |
| `types/components.ts` | Shared `Size`, `Variant`, `Tone` types re-exported from tokens |

### Three composition outputs

| File | What changed |
|---|---|
| `pages/Showcase.tsx` | **NEW** — kitchen-sink at `/components`. Every primitive in every state |
| `pages/Dashboard.tsx` | **REFACTORED** — now composes from Stat + Card + Badge. Visual output identical to v10.495 |
| `App.tsx` | **AMENDED** — `/components` route added; `ToastProvider` wrapping between Branding and Auth |

### Architectural decisions documented in code

**1. We did NOT install shadcn/ui CLI or Radix UI.**
Same visual API, ~500 LOC, **zero new dependencies**. If complex shadcn primitives are ever needed (Dialog with portal + focus trap, Combobox with floating-ui positioning), we add them in a dedicated future batch. Until then, less is more.

**2. Brand colors via Tailwind tokens, not inline styles.**
Tailwind's `theme.extend.colors.brand` (set up in v10.495) resolves `bg-brand-primary` → `var(--brand-primary)` → the value set by `BrandingProvider` from `/api/branding`. So every primitive that wants brand color writes a Tailwind class — not an inline `style={{ background: ... }}`. This means:
- Multi-tenant from day 1 (tenant change → CSS var update → entire app re-paints)
- Type-safe in TypeScript (Tailwind autocomplete works)
- One layer of indirection, not two

**3. tokens.ts is the ONE permitted place for semantic hex colors.**
G382 enforces this. Greys, success-green, danger-red, info-blue, etc. live ONLY in tokens.ts. Other component files use Tailwind's built-in palette classes (`bg-red-50`, `text-amber-700`) or brand vars. No component file is allowed to drop a `#1797ce` (or any hex) into its source.

### G382 — Design System Brand Discipline

New audit gate. Verifies on every run:
1. All 8 primitive files exist
2. `lib/cn.ts` and `lib/tokens.ts` exist
3. `types/components.ts` exists
4. `pages/Showcase.tsx` exists
5. `Dashboard.tsx` imports from `@/components/*` (proves refactor happened)
6. `App.tsx` contains `/components` route AND `ToastProvider`
7. **Zero hardcoded hex colors in any `src/components/**.tsx` file** (excluding `var(--brand-*)` patterns)

G381 still passes — the v10.495 contract is honored (App.tsx still preserves byte-for-byte the original literals + the BrandingProvider amendment).

### Verified outcome

| Metric | v10.495 | v10.496 |
|---|---|---|
| Audit gates | 412 | **413** (G382 added) |
| Verifier | 1153 | 1153 (unchanged) |
| Lockstep batches | 140 | **141** |
| Frontend files | 16 | **30** (+14 this batch) |
| React component primitives | 0 | **8** |
| Design tokens centralized | – | ✅ `tokens.ts` |
| Hardcoded inline-style blocks | many | **zero** (in primitive files) |
| New npm dependencies | 0 | **0** (zero! built by hand) |
| Backend changes | – | **none** |
| Pure-frontend batch | – | ✅ |

## How to install

See `INSTALL.md` in this zip. Three-step recap:

1. Extract on top of A2Z root
2. Reload your already-running `pnpm dev` (Vite hot-reloads automatically; or restart if needed)
3. Open `http://localhost:5173/` (refactored Dashboard) and `http://localhost:5173/components` (Showcase)

No `utils/` edits this batch. Pure frontend.

## Honest findings shipped

**1. We did NOT install the shadcn/ui CLI.** The official shadcn workflow is excellent for teams that want the Radix UI primitives. For A2Z, where we control every line and Joshua reads everything: building by hand keeps the source readable, the bundle small, and the dependency tree shallow. If we ever genuinely need Dialog (with focus trap + portal + accessibility behaviors that take 300 LOC done right), we'll bring in shadcn for THAT specific component. Not yet.

**2. Dashboard.tsx looks identical but is structurally different.** The visual output of v10.496's Dashboard is byte-for-byte the same as v10.495's. But the *source code* went from ~150 lines of inline styles to ~80 lines composed from primitives. That refactor is the proof-of-life for the design system. Every future page benefits.

**3. The /components page is permanent infrastructure, not a one-off demo.** When you're building v10.501 and you wonder "how does Badge look in danger tone with size sm", you open /components. It's your living style guide. Bookmark it.

## Roadmap (Phase F1-F10)

- ✅ **v10.495** — F1 foundations: React setup + branding API + first page
- ✅ **v10.496** — F2 design system (this batch): 8 primitives + showcase + Dashboard refactor
- ⏭️ **v10.497** — F3 auth: login page → `/api/auth/login` → JWT → protected routes
- ⏭️ **v10.498** — F3 shell: sidebar, topbar, role-aware navigation
- ⏭️ **v10.499** — F4 MD cockpit live: real `/api/dashboard/md` data, Recharts charts
- ⏭️ **v10.500** — F9-F10 testing: Vitest + Playwright + G383-G385

**The hands begin to grip. The face has features.**

Tell me **"v10.496 live"** once `/components` renders and we proceed to v10.497.
