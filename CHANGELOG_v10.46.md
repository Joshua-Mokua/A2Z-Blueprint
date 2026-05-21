# CHANGELOG v10.46 — Risk arc UI integration backfill · G130 ratchet · Protocol amended

**Status:** Risk arc UI-COMPLETE (was engine-complete + audit-complete + scenario-complete at v10.45, now also UI-complete). 10 closed arcs.
**Audit:** 130/130 PASS (+1 G130) · **G128:** STABLE (311 modules · 777 imports · 3 HARD baseline)
**Active standards:** 117 / 260 (unchanged — UI integration of existing standards) · **Scenario library:** 46 (unchanged)

## Why this batch

Surfaced post-v10.45 gap: across v10.39-v10.44 the Risk arc shipped
13 active standards, 6 engine modules, 27 scenarios, and the G129
closure ratchet — but **zero operator-facing Streamlit surfaces**.
A grep of `pages/` for the Risk-arc engine class names showed only
descriptive entries inside the Tier 24 admin block; no calculator,
no scenario builder, no what-if cockpit. An operator logging into
Streamlit could not drive any of the four engines from a browser.

This diverged from the v5.x integration discipline (every engine got
a Streamlit page with form inputs + scenario builders + engine
reference) that the Master Prompt records in detail. The Lean+Compact
protocol I followed across v10.39-v10.44 deferred UI work to closure,
but the deferral was never rescheduled into a closure batch the way
Engine Hub Tier and Master Prompt updates were. v10.46 closes that
gap and amends the protocol so it doesn't recur.

## New page: `pages/93_risk_arc_cockpit.py`

**~720 lines · 5 tabs** following the v5.x Engine Studio pattern
(see `pages/89_capital_risk_engines.py` as the closest analogue).

### Tab 1 — 📈 Market Risk VaR (ENH-MR-001)
- Methodology selector: Parametric (Normal) vs Historical
- Portfolio value, confidence (90%-99.9%), horizon (1-30 days)
- Comma-separated returns text-area (≥30 obs recommended)
- Output: VaR (KES), Expected Shortfall (KES), VaR % of portfolio
- Provenance expander surfaces return distribution (n / mean / stdev /
  min / max) and framework refs

### Tab 2 — 🏛️ IRB Capital (ENH-CR-001)
- Exposure ID, exposure class (LARGE_CORPORATE / SME_CORPORATE)
- PD slider (3 bp floor), LGD slider, EAD input, M slider (1-5y)
- Output: K%, RWA (KES), Expected Loss, Capital ratio
- Provenance expander surfaces correlation_R, maturity_adj_b, all
  inputs + intermediates + outputs per Rule 1
- Validation errors surfaced (PD floor, M bounds, EAD positivity)

### Tab 3 — ⚙️ Op Risk SMA (ENH-OR-001)
- 10 BI inputs across 3 columns (II/IE/IEA/DI/OI/OE/FI/FE/TB/BB)
- EUR/KES rate, Bucket-1 discretion checkbox
- Average annual op-loss + years-of-history slider (0-10)
- Output: BI 3y avg (EUR), BIC (KES), ILM, RWA op
- ILM source surfaced (COMPUTED / BUCKET_1_DISCRETION /
  INSUFFICIENT_HISTORY) so operator sees *why* ILM = X

### Tab 4 — 💧 Stressed LCR (ENH-LR-001)
- Severity radio (BASELINE / MODERATE / SEVERE / BANK_RUN)
- HQLA composition: L1 + L2A + L2B inputs
- Outflows: retail stable + wholesale unsec with base run-off rates
- Inflows: performing loans
- **Breach-band traffic-light banner** (COMPLIANT green / AMBER amber /
  RED red / CRITICAL dark-red) showing LCR ratio prominently
- Output: HQLA after caps, stressed outflows, NCO, survival horizon
- Provenance expander surfaces HQLA breakdown per level + per-category
  StressedFlow records (base rate, multiplier, stressed rate,
  stressed KES) + caps applied

### Tab 5 — ℹ️ About
- Risk arc batch progression table (v10.39 → v10.46)
- Framework refs (BCBS d352 / d424 / d457 / d295 + CBK PG/12 + PG/15)
- Rule 7 posture statement (no auto-rebalance / auto-hedge /
  auto-liquidate affordances)
- Rule 1 provenance discipline statement
- Locks under G129 + G130 cited

## Standard discipline preserved

- `require_access("perform")` access control on entry
- `audit_log("RISK_ENGINE_USED", ...)` event emitted for every
  engine invocation (4 events: market_risk_var / credit_risk_irb /
  op_risk / liquidity_stress)
- 5 top-level tabs (under G4-strict cap of 7)
- Decimal-internal monetary precision preserved end-to-end
- All 4 engines invoked via the same form → compute → render
  pattern; no engine bypassed

## New audit gate: G130 `risk_arc_ui_integrated`

Pushes audit suite **129 → 130**. Codifies the v10.46 UI backfill
discipline as a permanent invariant. Verifies:

1. `pages/93_risk_arc_cockpit.py` exists on disk.
2. Cockpit imports all 4 Risk-arc engine modules (`market_risk_var`,
   `credit_risk_irb`, `op_risk`, `liquidity_stress`).
3. Cockpit constructs each engine class AND invokes a compute-style
   method on it. Class construction without method invocation = fail
   ("UI must be interactive, not just import-and-display").
4. Cockpit declares `require_access(...)` for access control.
5. Cockpit emits `audit_log(...)` events for observability.

The grep-based check is deliberately flexible — accepts both
`engine = X(); engine.compute(...)` and `X().compute(...)` patterns.
Strict pattern-matching would create false positives on cosmetic
refactors.

Combined with G129, the Risk arc is now locked along **three axes**:
registry presence (`status='active'`), scenario coverage (≥27
Risk-arc scenarios), and UI presence (this gate). Removing or
gutting the cockpit page would now fail the audit.

## Lean+Compact protocol — amended

Before v10.46:

> Engine Hub Tier additions DEFERRED to arc closure
> Master Prompt updates DEFERRED to arc closure

After v10.46:

> Engine Hub Tier additions DEFERRED to arc closure
> Master Prompt updates DEFERRED to arc closure
> **UI integration page (Streamlit cockpit) DEFERRED to arc closure**

All three discharged at closure as a single batch. The closure batch
is now: G-gate ratchet + Engine Hub Tier + Master Prompt + UI cockpit
+ CHANGELOG. UI integration is **non-negotiable** going forward — no
arc may be marked closed if its engines have not been wired
interactively into Streamlit.

This amendment matches the v5.x integration discipline that the
existing pages (`19_perform.py`, `32_ifrs9.py`, `34_customer360.py`,
`88_ifrs_engines.py`, `89_capital_risk_engines.py`, etc.) already
follow. v10.x Phase 2 had drifted from that discipline; v10.46
re-anchors.

## Master Prompt update

`Master_Prompt_v3.md` line 108 `**Current version:**` updated from
v10.45 to **v10.46** with the cockpit summary, G130 ratchet
description, and protocol amendment. Surgical replacement, no other
sections touched.

## Verification

- `scripts/audit.py` → **Score: 130/130 gates = 100.0% — PASS** ·
  G130 reports 0 violations on first run.
- `scripts/structure_audit.py` → **STABLE: HARD findings match
  baseline exactly** (311 modules · 777 imports · 59 findings ·
  HARD=3). New page adds 1 module + 7 imports; structural baseline
  preserved.
- `python3 -c "import ast; ast.parse(open('pages/93_risk_arc_cockpit.py').read())"` → AST OK.
- All earlier self-tests still pass (op_risk 17/17, liquidity_stress
  18/18, credit_risk_irb tests, scenario_simulator 18/18).

## Files changed

- **NEW** `pages/93_risk_arc_cockpit.py` (~720 lines)
- **MOD** `scripts/audit.py` (+G130 function ~120 lines, +1 GATES
  entry)
- **MOD** `Master_Prompt_v3.md` (line 108 surgical replacement)
- **NEW** `CHANGELOG_v10.46.md`

## Limitations / honest acknowledgements

1. **No live Streamlit deployment verification by Claude.** The page
   passes AST parse + import check + structural audit. The actual
   browser rendering — form layout, button interactions, expander
   behaviour, traffic-light banner colour rendering — must be
   validated by Joshua running `streamlit run app.py` locally.

2. **VaR tab uses comma-separated text-area for returns.** Production
   deployment with daily P&L feed would replace with a CBS query or
   uploaded CSV; current pattern is the v5.x convention for "operator
   pastes returns from spreadsheet for ad-hoc analysis".

3. **Op Risk SMA tab simplifies BI inputs to one fiscal year
   replicated across 3 years.** Production with proper 3-year
   submission would use a 3-row form or CSV upload; current pattern
   is the cockpit's teaching/QA mode.

4. **Stressed LCR tab covers 2 outflow categories + 1 inflow
   category.** The engine itself supports arbitrary numbers of each;
   the cockpit form is intentionally minimal so operators see the
   pattern. Production deployment with full Basel III outflow
   taxonomy (10+ categories) would use a `st.data_editor` table.

5. **Market Risk Sensitivities, VaR backtesting (Kupiec /
   Christoffersen), Trading Book Boundary, and Market Risk Limits
   are not surfaced on the cockpit.** They remain reachable via
   `pages/91_systems_view.py` and the audit/scenario surface, but a
   future v10.47 or v10.48 batch could deepen the cockpit with
   additional sub-tabs. Keeping v10.46 focused on the four
   highest-value engine surfaces was a deliberate scope choice.

6. **G130 grep is intentionally loose.** A future cosmetic refactor
   that, say, splits `LiquidityStressEngine().compute(...)` across
   two lines would still pass — only the constructor token and a
   compute-method token need to appear in the source. Tighter checks
   (AST-based) would require more audit infrastructure than the
   ratchet warrants today.

7. **`pages/82_oprisk.py` (older) and `pages/89_capital_risk_engines.py`
   (v5.72) are not modified.** The Risk arc cockpit is additive at
   slot 93. Future operations work could consolidate older pages,
   but that's orthogonal to v10.46.
