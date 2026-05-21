# CHANGELOG v10.206 — Fifth cockpit absorption (Legal Arc → 26_legal.py)

**Date:** 2026-05-07
**Theme:** Fifth cockpit absorption batch. Folds
`28_legal_arc_cockpit.py` (291 lines) into `26_legal.py` (607 lines)
as a 4th top-level "🤖 Arc Engines" tab with 7 nested sub-tabs.
Refactors G155 from location-based to manifest-aware behavior-based —
sixth instance of the same refactor pattern. Audit holds at
**160/160 PASS**.

## What v10.206 ships

### 1. `pages/26_legal.py` — absorbed Arc Engines as 4th top-level tab

Legal page goes from 3 → 4 top-level sections (within G4's 7-tab cap,
3 slots of headroom remaining):

```
📋 Operational  📊 Reporting  🔧 Admin  🤖 Arc Engines  ← NEW
```

Inside the new tab, 7 nested sub-tabs reproduce the cockpit's structure:

```
📊 Dashboard            — LegalDashboardEngine (ENH-228, cross-engine rollup)
⚖️ Matters              — LegalCaseManagementEngine
💰 Spend + Counsel     — LegalSpendManagementEngine + OutsideCounselPortalEngine
📜 Obligations          — ObligationTrackingEngine
🔒 Holds + Docs         — LegalHoldManagementEngine + LegalDocumentManagementEngine
📚 Clauses              — ClauseLibraryEngine
📈 Analytics            — LegalAnalyticsEngine
```

All 9 fully-engineered engines (ENH-222..230, with ENH-221 contracts
META_ONLY) preserved. Engine instances cached at session level via
`@st.cache_resource`. The dashboard and analytics engines have
constructor dependencies on the other 7 — preserved exactly.

### 2. `scripts/audit.py` — G155 refactored to manifest-aware

Sixth instance of the manifest-aware refactor pattern (after G149
v10.199, G151 v10.202, G159 v10.203, G148 v10.204, G153 v10.205).
Searches all non-deprecated pages in the `legal` department,
verifies the 9 engine class references appear somewhere.

### 3. `pages/_manifest.json` — cockpit entry removed

Manifest entry for `28_legal_arc_cockpit.py` deleted. Manifest goes
104 → 103 pages, 9 → 8 deprecated cockpits.

### 4. `pages/28_legal_arc_cockpit.py` — DELETED

**⚠️ Manual deletion required when applying this zip:**

```bash
rm pages/28_legal_arc_cockpit.py
python scripts/audit.py
```

## Files changed (3 modified + 1 deletion)

```
pages/26_legal.py                 MOD  +210 lines  (607 → 817)
                                       (4th top-level tab + 7 nested sub-tabs + cached engine factory)
scripts/audit.py                  MOD  +56 lines net  (G155 manifest refactor)
pages/_manifest.json              MOD  -16 lines  (cockpit entry removed)
pages/28_legal_arc_cockpit.py     DEL  -291 lines  (manual deletion required)
```

Net cockpit absorption: -291 (cockpit) + +210 (target) - 16 (manifest)
= -97 lines net code reduction.

## Audit

```
Before (v10.205): Score: 160/160 gates = 100.0% — PASS
After  (v10.206): Score: 160/160 gates = 100.0% — PASS
```

## What changed for users

A General Counsel or Legal Officer who used to navigate to "Legal Arc
Cockpit" now opens "Legal Management" (`26_legal.py`) and clicks the
new "🤖 Arc Engines" top-level tab.

The 4-tab structure groups Legal work by operator scope:
- **Operational** — daily case management (active matters, new matter
  creation) used by Legal Officers and Paralegals
- **Reporting** — case reports and dispositions
- **Admin** — system configuration
- **Arc Engines** — the strategic/analytical layer (obligation
  tracking, outside counsel coordination, spend management, clause
  library, legal holds, dashboard rollup, analytics) used by GC for
  monthly/quarterly reporting

## Cockpit absorption schedule — 5/13 done (38%)

| # | Status | Cockpit | Target |
|---|---|---|---|
| 1 | ✅ v10.202 | 26_treasury_arc_cockpit.py | 25_treasury.py |
| 2 | ✅ v10.203 | 15_strategy_arc_cockpit.py | 83_strategy.py |
| 3 | ✅ v10.204 | 16_product_arc_cockpit.py | 5_products.py |
| 4 | ✅ v10.205 | 27_compliance_arc_cockpit.py | 24_compliance.py |
| 5 | **✅ v10.206** | **28_legal_arc_cockpit.py** | **26_legal.py** |
| 6 | pending | 29_resource_optimization_cockpit.py | 10_opex.py |
| 7 | pending | 93_risk_arc_cockpit.py | 35_stress_testing.py |
| 8 | pending | 94_credit_governance_cockpit.py | 22_credit_analysis.py |
| 9 | pending | 95_revenue_assurance_cockpit.py | 29_revenue_assurance.py |
| 10 | pending | 96_finance_arc_cockpit.py | 52_mgmt_accounts.py |
| 11 | pending | 97_trade_finance_arc_cockpit.py | 46_trade_finance.py |
| 12 | pending | 98_ml_governance_arc_cockpit.py | 91_systems_view.py |
| 13 | pending | 99_integration_cockpit.py | 91_systems_view.py |

Halfway through after this batch (38% complete). Completion projected
at v10.214.

## Strategic narrative — pattern variant catalog growing

Tab convention encountered so far:

| Variant | Cockpit | Tab convention | Indentation |
|---|---|---|---|
| Hand-paste | v10.202 Treasury | n/a | n/a |
| Programmatic + named | v10.203 Strategy | `with tab_form:` etc., body col 4 | col 4 → col 12 |
| Programmatic + indexed | v10.204 Product | `with tabs[N]:`, body col 8 | col 8 → col 12 |
| Programmatic + indexed | v10.205 Compliance | `with tabs[N]:`, body col 8 | col 8 → col 12 |
| Programmatic + numbered named | **v10.206 Legal** | `with tabN:` (N=1..7) inside `def render():`, body col 8 | col 8 → col 12 |

Three convention families now:
1. Named with descriptive name (`tab_form`, `tab_cascade`)
2. Indexed (`tabs[0]`, `tabs[1]`)
3. Numbered named (`tab1`, `tab2`)

The extraction script was updated for v10.206 to match `with tabN:`.
Each cockpit's variant is identified during reconnaissance; the script
adapts.

## Honest acknowledgements

1. **Engine constructor dependencies preserved exactly.** Legal's
   `LegalDashboardEngine` and `LegalAnalyticsEngine` take 6-8 of the
   other engines as constructor arguments. The cached factory
   `_get_arc_legal_engines()` instantiates in dependency order:
   leaves first (ob, ca, sp, co, cl, ho, do), then dashboard (depends
   on 6), then analytics (depends on 7 + dashboard). Same as the
   cockpit's `_engines()` function.

2. **Tuple-position engine unpacking preserved.** The cockpit body
   uses `(ob, ca, sp, co, cl, ho, da, do, an) = get_engines()` and
   refers to engines by these short names throughout. The absorbed
   section preserves this pattern — same naming, same destructuring,
   so the pasted body code still works.

3. **`26_legal.py` is at 4/7 top-level tabs.** 3 slots of headroom
   remaining within G4 — most generous of any post-absorption page so
   far. Compare: 25_treasury (4/7), 5_products (5/7), 24_compliance
   (6/7), 83_strategy (7/7 ceiling).

4. **The cockpit's `def render():` wrapper** complicated extraction
   slightly — body lines are at col 8 (function body + with-block)
   instead of col 4. The script handles this correctly: the regex
   matches `^    with tab\d+:` and the body collection accepts
   `^        ` (8+ space) lines.

5. **`audit_log` action renamed** from `legal_arc_cockpit.view`
   (actually was `render_legal_cockpit` in this cockpit — slightly
   different from the others) to `legal_arc_engines.view`. Same
   discontinuity rationale.

6. **Net code reduction: -97 lines.** Reduction trend across all 5
   batches: -132, -99, -86, -109, -97. Mean ≈ -105 lines per
   absorption. Across 13 absorptions, projected total ≈ -1300 lines.

7. **G155 refactor is the sixth instance of the same pattern.** At
   six instances, the helper extraction case is now strong. After
   one more absorption (v10.207 Resource Optimization) makes 7
   instances, helper extraction becomes the natural pause batch.

8. **Page-number collision dropping.** Slot 28 was claimed by
   `28_legal_arc_cockpit.py` only — no collision relief from this
   batch. Slot 26 was already cleared by v10.202 (Treasury cockpit
   absorbed). Net collisions remain at 3 after v10.206.

9. **Compliance department's manifest count** now 11 → 10 → 10
   (steady; v10.205 absorbed Compliance cockpit but the entry was a
   `compliance_regulatory` department member). Legal department
   count: 3 → 2 (v10.206 absorbed legal cockpit).

10. **16 consecutive clean batches in this session** — v10.193
    through v10.206 (14 code batches + 2 advisory reviews). Cockpit
    absorption sub-campaign at 5/13 = 38% complete after 5 batches.

11. **Looking ahead.** v10.207 Resource Optimization cockpit (G157)
    → 10_opex.py. v10.208 Risk Arc → 35_stress_testing.py. v10.209
    Credit Governance → 22_credit_analysis.py. After v10.211, the
    consecutive single-target absorptions would be done; v10.212/213
    address the ML Governance + Integration → 91_systems_view dual
    target which needs sequencing.

## Next batch options

1. **v10.207 — Resource Optimization absorption** (`29_resource_optimization_cockpit.py`
   → `10_opex.py`). Continue alphabetic-by-cockpit-number order. G157.
2. **v10.207 — Extract `scripts/absorb_cockpit.py`.** After 6
   refactor instances + 5 absorptions, pattern is fully stable. ~80
   lines, single-purpose tooling batch. The pause point is right
   around now.
3. **v10.207 — Page migration to dotted form (Treasury department).**
   Validates v10.200 dotted-path access end-to-end on a real
   department.
4. **v10.207 — Return to deferred platform items.**

I'll continue with option 1 — momentum is high, pattern is mechanical,
each batch ratchets structural quality. Helper extraction (option 2)
becomes the natural pause point after one more absorption.
