# Changelog — v10.373 System State Review (Strategic Mapping)

**Date:** 2026-05-13
**Phase:** 4 (fifty-eighth arc — strategic review batch; no engine work)
**Audit:** G259 added (locks SYSTEM_STATE_REVIEW_v10.373.md presence + key sections)
**Tests:** 8/8 PASSED in `test_v10373_system_review.py`; 216 prior tests unchanged = **224 total**
**Verifier:** 285/285 checks pass on a clean extract
**G162 baseline:** 4022 (67 consecutive zero-drift batches)
**Master prompt:** v4.16 → v4.17 (lockstep — eighteenth consecutive batch)

---

## Your ask

> "continue. note a deep review of what the entire system has helps to ensure we do not repeat what is there, then once done we need to continue with the complete virtual bank set up to meet the objective set for today which is ultimately to run real virtual simulations of every staff role and module we have as we keep cleaning, iterating and improving the system. also note this is one system bringing together all bank modules together. I will be keen to ensure what we have done with profitability unification happens across"

This reframes the next several batches significantly:

1. **Deep review FIRST** — survey the system before continuing, so we don't rebuild what exists
2. **End objective**: real virtual simulations of every staff role and every module
3. **One holistic system** — all bank modules integrated (performance, profitability, risk, customer, treasury, compliance, HR)
4. **Pattern to extend**: the unification we just shipped for profitability (atomic units + reconciliation identities + canonical engines + audit gates) should be applied across the system

v10.373 is the deep review. v10.374+ executes on it.

## What v10.373 delivered

### `docs/SYSTEM_STATE_REVIEW_v10.373.md` — NEW (~14KB, 8 Parts)

A deep survey of the entire A2Z MIS 360 system covering:

**Part 1 — System scale (verified counts):**
- 123 pages, 439 utils modules, 208 data files, 383,548 LOC
- 258 audit gates, 216 integration tests
- 4 canonical profitability allocators shipped; 5+ legacy parallel engines remain

**Part 2 — The simulation gap (most important finding):**
- Two simulation models coexist
- Model A (live actions): ONLY `teller_actions.py` — fire_teller_deposit/withdrawal mutate the bank live, flow through to PBT in real time
- Model B (static generators): all other roles use `*_generator.py` modules that pseudo-randomize KPI numbers without bank impact
- **~25 roles** need live action interfaces analogous to `teller_actions.py` to enable real simulations:
  - Branch field: Teller (done), CSO, BOS, RM Retail, DSO, RM SME, RM Corporate, Branch Credit Manager, Branch Operations Manager, Branch Manager
  - Regional / division: Regional Head, Head of Retail/SME/Corporate, Director Retail/Commercial Banking
  - Head office: Credit Officer, Treasury Officer, Treasurer, Risk Officer, CRO, Compliance Officer, AML Analyst, Internal Auditor, Finance, CFO, MD
  - Support: CIO/Technology, HR

**Part 3 — Parallel profitability engines remaining:**
- `customer_profitability.py` (legacy) vs `customer_pbt_allocator.py` (v10.370 canonical) — DUAL ENGINES
- `rm_profitability.py` (809 LOC, legacy) vs `compute_pbt_by_staff` (v10.370 canonical) — DUAL ENGINES
- `product_profitability.py` — unsurveyed; may be parallel
- Helper modules to verify: `profitability_heatmap`, `profitability_hierarchy`, `profitability_integration`, `profitability_trends`
- Engine B rollup entry points (`rollup_by_segment`, `rollup_by_cbk_sector`, etc.) still use legacy mode

**Part 4 — Other modules needing unification:**
- **Risk** (credit/market/operational/capital/IRRBB/IFRS9): many parallel files — credit_risk_irb, credit_risk_scoring, credit_alt_scoring, market_risk + 4 sub-modules, liquidity_risk + liquidity_stress, ifrs7/ifrs9, etc.
- **Customer 360**: customer_behavioral_profile, customer_lifetime_value, customer_needs_analyzer, customer_segmentation, customer_value_segments + the new v10.370 atomic + customer_intelligence.json legacy
- **Treasury / ALM / FTP**: treasury_alm, treasury_dashboard, liquidity_*, market_risk_*, ftp
- **Compliance / CIMS**: 15+ CIMS modules, multiple compliance modules
- **Audit**: multiple audit_* modules

**Part 5 — Strategic roadmap (5 phases):**

| Phase | Range | Purpose |
|---|---|---|
| A | v10.374-v10.375 | UX surface the profitability work just shipped |
| B | v10.376-v10.379 | Close remaining parallel profitability engines |
| C | v10.380-v10.400 | Live action interfaces for every role (the big simulation push) |
| D | v10.40X-v10.44X | Module-by-module unification (risk, customer, treasury, compliance, HR) |
| E | v10.45X+ | Executive UI (Standard #9, React frontend) |

**Part 6 — Recommended next concrete batch:** v10.374 — Role-aware filter for staff PBT (BRM/SRO/RO portfolio owners vs Tellers/CSOs/BOS service staff). This:
- Surfaces v10.370 work visibly
- Resolves Joshua's teller-vs-RM framing
- Establishes the `users.json::role` join pattern for future role-specific UI
- Small and well-scoped (Rule N2)

**Part 7 — Decisions awaiting Joshua** (4 explicit asks for clarity before v10.374+)

**Part 8 — What this review is NOT proposing** (explicit boundaries: no rewrites, no deletions, no framework changes, no v11.0)

### G259 — locks the document

Verifies the review document remains present and contains all 8 Parts plus key cross-reference anchors (`teller_actions.py`, `customer_pbt_allocator`). Cost: 0.001s — pure file existence + string match.

### Tests — 8/8 across 3 sections

**Section 1 (document presence + key sections):** document exists, is substantive (>5KB), has all 8 Parts, identifies simulation gap with multiple roles named, identifies parallel engines, proposes phased roadmap

**Section 2 (gate + no regression):** G259 passes, all prior unification identities still hold (no engine code changed)

**Section 3 (Charter §2):** still passes

## Files changed

| File | Change |
|---|---|
| `docs/SYSTEM_STATE_REVIEW_v10.373.md` | **NEW** (~14KB, 8 Parts) — strategic map |
| `scripts/audit.py` | **NEW** `gate_system_state_review` (G259) |
| `scripts/verify_local_state.py` | Extended to 285 checks |
| `tests/integration/test_v10373_system_review.py` | **NEW** — 8 tests across 3 sections |
| `docs/Master_Prompt_v4.17.md` | **NEW** — lockstep bump from v4.16 |

**Zero engine code changed.** Zero parallel engines closed. Zero roles simulated. This batch is pure strategic mapping — the deliverable is clarity for v10.374+.

## Verified outcome

| Metric | Value |
|---|---|
| Audit gates | 258 → **259** (G259 added) |
| Charter §2 + all prior identities (G250-G258) | still PASS (engines untouched) |
| Page smoke | 123/123 + 0 static + 14/14 dynamic |
| Tests | +8 in v10.373; **224 total across v10.358–v10.373** |
| Verifier | 275 → **285 checks** |
| Master prompt | v4.16 → **v4.17** — lockstep (18 consecutive batches) |
| G162 baseline | 4022 (**67 consecutive zero-drift batches**) |

## Honest acknowledgements

1. **This isn't an engine batch.** No code that runs in production changed. Some teams would call this "documentation" and skip it; in this codebase, a 14KB strategic map gated by an audit gate is the right artifact for the moment — before charging into 25+ role simulations, knowing what exists prevents waste.

2. **The simulation gap is the biggest finding.** Charter §2 (G249) passes because teller actions flow live to PBT. But that's ONE role out of ~25. The objective Joshua stated ("real virtual simulations of every staff role") requires building action interfaces for the other 24. That's a large arc — Phase C in the roadmap (v10.380-v10.400) is ~21 batches. Worth being explicit about scale before starting.

3. **The legacy `customer_profitability.py` and `rm_profitability.py` ARE structurally identical to the Engine A vs Engine B fragmentation we just closed.** They walk their own data via callbacks; the new canonical engines walk CBS. Migrating them follows the v10.372 pattern: add `cost_source="canonical"` mode, preserve callback API. Same playbook, just applied to a smaller engine.

4. **Customer master alignment is a real fork in the road.** `customer_intelligence.json` (3,206 customers) is the marketing/segmentation master. CBS `customers.csv` (100 in seed, 700K in production) is the transactions master. They're DIFFERENT universes today — same person could exist in both with different attributes. Joshua needs to decide: merge them (single customer master, painful migration), or document the mapping (keep both, formally bridge them).

5. **Risk module unification is at least as large as profitability.** Multiple credit risk engines (irb, scoring, alt_scoring), 5 market risk files, liquidity, capital, IFRS — each with its own data shape and rollup. The atomic unit isn't yet established (likely per-exposure RWA + expected loss). When Phase D begins (v10.40X), this is the headline.

6. **Recommended next batch (v10.374) is deliberately small.** Role-aware UI filter for staff PBT. ~200 LOC max. It surfaces v10.370 work, establishes the role-join pattern, and proves Phase A works before bigger swings. After v10.374-v10.375, Phase B starts closing parallel engines.

7. **Rule N2 held**: single batch, one concern (strategic review). No engine work mixed in.

8. **No new data files.** No new fixtures. Just the markdown document. Footprint is minimal — if Joshua disagrees with the roadmap, only the doc needs updating; nothing else has to change.

9. **G259's cost is essentially zero.** File-existence check + 9 string matches. Won't slow audits.

10. **The decisions list (Part 7) is explicit** because next batches depend on the answers. Roadmap phasing, role definitions, batch granularity, customer master alignment — all worth confirming before committing 20+ batches to the path.

11. **The objective ("real virtual simulations of every staff role") is now backed by a concrete roadmap with ~21 batches.** That's a clear, finite arc. Not open-ended exploration.

12. **The profitability unification pattern is genuinely reusable.** v10.368-v10.372 demonstrated it; the review extracts the abstraction (atomic + identity + canonical + gate + backward-compat) and shows where to apply it next.

## On your end

1. Close Streamlit
2. Delete leftover subfolder extracts
3. Extract `a2z_v10373_session_cumulative.zip` flat
4. Run `python scripts\verify_local_state.py` → expect **ALL 285 CHECKS PASSED**
5. **Read the review:** `docs\SYSTEM_STATE_REVIEW_v10.373.md` — this is the strategic anchor for v10.374+
6. **Respond on the four decisions in Part 7:**
   - (1) Roadmap phasing (A → B → C → D → E) — approved or different order?
   - (2) Role definitions: are `{BRM, SRO, RO, RM, Branch Manager, Regional Head}` the portfolio-owners?
   - (3) Phase C granularity: one role per batch (21 batches) or grouped (e.g. all branch field staff in one batch)?
   - (4) Customer master alignment: merge `customer_intelligence.json` + CBS `customers.csv`, or keep separate with documented bridge?
7. Read `docs\Master_Prompt_v4.17.md`
8. (Optional, takes >5min) Audit → expect **259/259 PASS**

## What to expect next

Once you respond to the four decisions (or say "proceed" to accept the defaults proposed), the next concrete batches will be:

- **v10.374** — Role-aware filter for staff PBT (Phase A first batch). Pages affected: `pages/115_live_cockpits.py`, `pages/13_branch_log.py`, RM cockpits. Estimated ~200-400 LOC, one new audit gate.
- **v10.375** — MD dashboard surfaces per-SBU/per-branch drill-down using canonical engine (Phase A second batch).
- **v10.376** — Refactor `customer_profitability.py` to canonical mode (Phase B start).

Want me to proceed with v10.374 using the proposed default decisions (or wait for your direction on Part 7)?
