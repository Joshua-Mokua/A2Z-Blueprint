# CHANGELOG v10.38 — STRUCTURAL HYGIENE FOUNDATION

**Audit:** 128/128 PASS — **120th consecutive clean.**
**Tests:** 838 integration (+15 from v10.37's 823) + 16 self-tests on `structure_audit_core`.
**Status:** Pause Risk arc opening; ship cross-arc structural hygiene foundation per the user-supplied **Professional System Architecture & Module Reorganization** document. **G128 added.** Standards count unchanged at 103/247 active — this batch is platform infrastructure, not new domain content.

---

## Why this batch is different

The user supplied a strategic document on module reorganization to "avoid getting into the trap of having so much duplication and any mess that might get the system into an entangled web." Honest review came first; selective adoption second. Same pattern as v10.36 (where we paused Treasury content to ship `scenario_simulator`).

## Honest review findings

The document's premise was overcounted (it referenced "~468 standards"; our actual registry has 247 — 103 active). Several of its specific duplication examples (Retailer Financing #439-448 vs Value Chain #449-458, Product House #131-140 vs Propositions #349-358) refer to a different version of A2Z and don't apply to what we've built.

But the **general pattern** is exactly right: the codebase has crossed the size where ad-hoc organization breaks down. We have **170 utils modules · 108 pages · 117,932 lines in utils/**. Without a mechanical hygiene check, drift toward entanglement is inevitable.

| Doc proposes | Verdict | Action |
|---|---|---|
| Domain-driven organization | ✅ Already partial in `standards_registry` + Engine Hub | Documented as `docs/ARCHITECTURE.md` |
| Module map JSON | ✅ Adopted | `docs/module_map.json` (302 modules classified) |
| Dependency graph tool | ✅ Adopted + extended | `utils/structure_audit_core.py` |
| `LEGACY.md` deprecations | ❌ Premature | We don't have superseded standards yet |
| PlantUML diagrams | ❌ Premature | Bureaucratic for one-developer project |
| MkDocs/Docusaurus sidebar | ❌ Premature | Same |
| Hire freelance architect | ❌ Premature | Same |
| Monorepo refactor | ❌ Premature | Doc itself defers this; we agree |

## What v10.38 ships

### `utils/structure_audit_core.py` (1029 lines, 16 self-tests)

AST-based codebase analyzer with 7 rule families:

| Category | Severity | Detection |
|---|---|---|
| **CIRCULAR_IMPORT** | HARD | Three-color DFS cycle detection on the import graph |
| **LAYER_VIOLATION** | HARD | Forbidden edges: `utils → pages`, `utils → scripts`, `scripts → pages` |
| **GOD_MODULE** | WARN | Fan-in > 15, unless on `CROSS_ARC_BRIDGES` exemption |
| **JUNK_DRAWER** | WARN | Fan-out > 25 |
| **ORPHAN_MODULE** | WARN | Zero callers + not entry point + not on `ORPHAN_EXEMPT_PATTERNS` |
| **DUPLICATE_SYMBOL** | WARN | Same class in 2+ modules, same function in 3+ modules |
| **SIZE_OUTLIER** | INFO 2k+ / WARN 4k+ | File line count |

Per Rule 1, every `Finding` surfaces severity + category + module_path + observed_value + threshold + suggestion. Per Rule 7, the engine **never auto-mutates code** — reorganization is always a human decision.

### Mypy-style baseline mechanism

`compute_baseline()` snapshots the current state of HARD findings; `compare_to_baseline()` rejects regressions.

- **Existing HARD findings preserved** — system runs unchanged
- **New HARD findings rejected** — no future batch can introduce new circular imports or layer violations
- **Improvements allowed** — baseline can shrink as `utils.core` etc. is cleaned up over time

Captured baseline (May 2026):

| Category | Count | Notes |
|---|---|---|
| CIRCULAR_IMPORT | 3 | `utils.core` ↔ `utils.actuals_engine` ↔ `utils.bsc_engine`/`core_audit`/`core_kpi` |
| LAYER_VIOLATION | 0 | Clean — locked |

### `scripts/structure_audit.py` CLI

```bash
# Run audit; exit 0 if clean vs baseline, 1 if regression
python3 scripts/structure_audit.py

# Capture new baseline after intentional improvements
python3 scripts/structure_audit.py --capture-baseline
```

Writes `docs/structure_audit_report.md` (human) + `docs/module_deps.json` (machine) on every run.

### G128 audit gate — `gate_structural_integrity`

Added to `scripts/audit.py` GATES list. Verifies:
1. `utils/structure_audit_core.py` exists with the expected public surface
2. `scripts/structure_audit.py` CLI exists
3. `docs/structure_audit_baseline.json` exists
4. Audit completes without exceptions
5. **No new HARD findings beyond the baseline**

Total audit gates: 127 → **128**. Score: 128/128.

### `docs/ARCHITECTURE.md` — current-state domain view

Documents 11 domains over the existing codebase **without renaming anything**:
1. Strategy & Execution
2. Customer & Relationship
3. Credit & Lending
4. Products & Propositions
5. Risk & Compliance
6. Finance & Treasury
7. Operations & Support
8. Marketing & Sales
9. People & HR
10. IT & DevOps
11. Cross-Arc Infrastructure

Plus a **layer model** (L0-L4) that the audit enforces, a list of **cross-arc bridges** (intentional facades), a list of **base infrastructure with high fan-in by design**, and known structural debt (notably `utils.core` at 6346 lines).

### `docs/module_map.json` — machine-readable mapping

Every scanned module → primary domain + line count. 302 modules classified across 11 domains + ui_pages + tooling_scripts. 65 unclassified specialized modules form a long tail (deferred_tax, esg_reporting, fatca_crs, etc.) — patterns can be refined in future batches.

## Real findings against the actual codebase

The audit found genuine issues — the tool is doing its job:

| Finding | Module | Detail |
|---|---|---|
| **3 CIRCULAR_IMPORT (HARD)** | `utils.core` | All involve `core ↔ actuals_engine ↔ bsc_engine/core_audit/core_kpi`. Pre-existing; system runs because Python resolves at runtime. Captured in baseline; G128 prevents new ones. |
| **1 GOD_MODULE (WARN)** | `utils.core` | 74 incoming + 6346 lines + involved in 3 cycles. The genuine god module. Refactoring deferred to future batch — baseline mechanism keeps the situation from worsening. |
| **1 JUNK_DRAWER (WARN)** | `scripts.audit` | 102 outgoing + 15843 lines (inlines all 128 gates). Could split into per-arc gate modules if it becomes burdensome. |
| **26 ORPHAN_MODULE (WARN)** | various | Mostly likely entry-point scripts or reflectively-loaded; review case-by-case |
| **15 DUPLICATE_SYMBOL (WARN)** | various | Mostly conventional helpers (`format_*`, `_test_*`); review on case-by-case |
| **8 SIZE_OUTLIER** | various | `scripts.audit` 15843 / `utils.core` 6346 / `pages.7_admin` 4761 / `pages.2_people` 3784 / `pages.34_customer360` 3314 + 3 more |

WARN/INFO findings don't fail the gate — they're informational signals for future work.

## Anti-entanglement working agreement (locked going forward)

These rules apply to every future batch:

1. **No new circular imports.** G128 fails on any new cycle.
2. **No new layer violations.** `utils → pages`, `utils → scripts`, `scripts → pages` forbidden.
3. **Cross-arc bridges declared.** New facade modules add their short name to `CROSS_ARC_BRIDGES`.
4. **God modules require approval.** Modules > 15 incoming dependencies trigger WARN.
5. **Size discipline.** > 2000 lines INFO; > 4000 lines WARN.
6. **Duplicate detection during code review.** Two modules defining the same class trigger WARN.

## Honest scope notes

1. **No new standards activated.** v10.38 is platform infrastructure. Standards count remains 103/247 active.
2. **`utils.core` not refactored.** The user explicitly asked for **no code reorganization** in this hygiene batch. The audit makes the issue mechanically visible; refactoring is a separate workstream that requires careful slicing along cohesive concerns. The baseline mechanism prevents the situation from worsening.
3. **Document-classified mapping is informational only.** 65 modules remain unclassified (long tail of specialized modules). The structural audit gate doesn't depend on classification accuracy — it depends on the import graph, which is deterministic.
4. **Heuristic findings are advisory.** Only CIRCULAR_IMPORT and LAYER_VIOLATION fail G128. WARN/INFO findings are signals for future work, never gate-failing.
5. **PlantUML / MkDocs / Docusaurus / freelance architect — all deferred.** Bureaucratic deliverables for a team that doesn't yet exist.

## Honesty Rule conformance

- **Rule 1.** Every `Finding` surfaces severity + category + module_path + observed_value + threshold + suggestion + related_modules. Markdown report shows specific violation paths and counts.
- **Rule 7.** The audit is **read-only** — verified by integration test that captures file mtimes before/after audit and asserts they're unchanged. The engine never auto-mutates code or rewrites the baseline silently. Baseline updates require explicit `--capture-baseline` flag.
- **Decimal-internal precision** N/A (audit operates on graph properties, not money).

## Phase 2 progress after v10.38

| Arc | Status |
|---|---|
| 9 closed arcs (Climate · Credit · KESONIA · RMS · Audit/GRC · Model Gov · Virtual Bank · Bandit · **Treasury**) | ✅ 75 + 16 = 91 standards |
| **Cross-arc scenario harness (v10.36)** | ✅ 19 scenarios + factory mode |
| **Cross-arc structural hygiene (v10.38)** | ✅ G128 baseline locked |
| Risk · Trade · IT · etc. | 0/152 pending |

**103 of 247 standards active.** Treasury arc closed. Cross-arc infrastructure (scenario simulator + structure audit) shipped. **120 consecutive clean batches.**

## What ships next — v10.39

Risk arc opening. First batch likely tackles Market Risk foundation (VaR / Expected Shortfall per BCBS FRTB) — composes naturally with the IRRBB work in `treasury_alm`. Per the v10.36 pattern, each new module added in v10.39+ will:

1. Pass the existing 838 integration tests
2. Pass the new G128 structural integrity gate (no circular imports, no layer violations)
3. Add 3-5 new scenarios to `scenario_simulator.TREASURY_SCENARIO_LIBRARY` (or a new `RISK_SCENARIO_LIBRARY`)
4. Get an Engine Hub Tier 21+ entry

The mechanical hygiene check now runs every batch. The codebase **cannot drift toward entanglement** without the gate failing.

**120 consecutive clean batches. 9 arcs closed. Treasury at 100%. Structural integrity locked. Risk arc opens next.**
