# CHANGELOG v10.205 — Fourth cockpit absorption (Compliance Arc → 24_compliance.py)

**Date:** 2026-05-07
**Theme:** Fourth cockpit absorption batch. Folds
`27_compliance_arc_cockpit.py` (439 lines) into `24_compliance.py`
(262 lines) as a 6th top-level "🤖 Arc Engines" tab containing 7
nested sub-tabs. Refactors G153 from location-based to manifest-aware
behavior-based — fifth instance of the same refactor pattern (after
G149, G151, G159, G148). Audit holds at **160/160 PASS**.

## What v10.205 ships

### 1. `pages/24_compliance.py` — absorbed Arc Engines as 6th top-level tab

Compliance page goes from 5 → 6 top-level tabs (within G4's 7-tab cap,
1 slot of headroom remaining):

```
📋 All Cases  🔴 Open  ✅ Cleared  📊 Analytics  📅 Regulatory Calendar  🤖 Arc Engines  ← NEW
```

Inside the new tab, 7 nested sub-tabs reproduce the cockpit's structure:

```
📊 Dashboard            — Cross-engine compliance posture rollup (ENH-198)
👤 KYC + Screening       — KycOnboardingEngine + optional ScreeningOrchestrator
🚨 AML Monitoring        — AmlMonitoringEngine
📋 SAR Filings           — SarFilingEngine
📊 Risk Assessment       — ComplianceRiskAssessmentEngine
📑 Reg + Policy          — RegulatoryChangeEngine + PolicyManagementEngine
🎓 Training + Examiner   — ComplianceTrainingEngine + ExaminerReportingEngine
```

All 8 mandatory engines (ENH-191..199 minus the optional
ScreeningOrchestrator) preserved. Engine instances cached at session
level via `@st.cache_resource`. The optional ScreeningOrchestrator is
imported defensively — present when available, gracefully absent
otherwise.

### 2. `scripts/audit.py` — G153 refactored to manifest-aware

G153 (compliance_arc_ui_integrated, shipped v10.169) is the fifth
location-locked closure gate to require manifest-aware refactoring,
following G149 (v10.199), G151 (v10.202), G159 (v10.203), and G148
(v10.204).

Refactored to **behavior-based**: scans all non-deprecated pages in
the `compliance_regulatory` department (resolved via the manifest),
concatenates their text, verifies all 8 engine classes are referenced
somewhere. Same discipline (Compliance arc engines must be
UI-integrated) but location-independent.

### 3. `pages/_manifest.json` — cockpit entry removed

Manifest entry for `27_compliance_arc_cockpit.py` deleted. Manifest
goes 105 → 104 pages, 10 → 9 deprecated cockpits.

### 4. `pages/27_compliance_arc_cockpit.py` — DELETED

**⚠️ Manual deletion required when applying this zip:**

```bash
rm pages/27_compliance_arc_cockpit.py
python scripts/audit.py
```

## Files changed (3 modified + 1 deletion)

```
pages/24_compliance.py                MOD  +346 lines  (262 → 608)
                                            (6th top-level tab + 7 nested sub-tabs + cached engine factory)
scripts/audit.py                      MOD  +49 lines net  (G153 manifest refactor)
pages/_manifest.json                  MOD  -16 lines  (cockpit entry removed)
pages/27_compliance_arc_cockpit.py    DEL  -439 lines  (manual deletion required)
```

Net cockpit absorption: -439 (cockpit) + +346 (target) - 16 (manifest)
= -109 lines net code reduction.

## Audit

```
Before (v10.204): Score: 160/160 gates = 100.0% — PASS
After  (v10.205): Score: 160/160 gates = 100.0% — PASS
```

## What changed for users

A Compliance Officer who used to navigate to "Compliance Arc Cockpit"
now opens "Compliance" (`24_compliance.py`) and clicks the new
"🤖 Arc Engines" top-level tab.

The 6-tab structure groups Compliance work by operator scope:
- **All Cases / Open / Cleared / Analytics / Regulatory Calendar** —
  the operational case-management workflow used by Compliance
  Officers daily for screening hits and case dispositions
- **Arc Engines** — the strategic-analytical layer (KYC onboarding,
  AML monitoring posture, SAR filings register, enterprise
  compliance risk score, regulatory change impact, policy
  attestation, examiner reporting) used by MLRO and Head of
  Compliance for monthly/quarterly reporting and regulator
  interactions

## Cockpit absorption schedule — 4/13 done (31%)

| # | Status | Cockpit | Target |
|---|---|---|---|
| 1 | ✅ v10.202 | 26_treasury_arc_cockpit.py | 25_treasury.py |
| 2 | ✅ v10.203 | 15_strategy_arc_cockpit.py | 83_strategy.py |
| 3 | ✅ v10.204 | 16_product_arc_cockpit.py | 5_products.py |
| 4 | **✅ v10.205** | **27_compliance_arc_cockpit.py** | **24_compliance.py** |
| 5 | pending | 28_legal_arc_cockpit.py | 26_legal.py |
| 6 | pending | 29_resource_optimization_cockpit.py | 10_opex.py |
| 7 | pending | 93_risk_arc_cockpit.py | 35_stress_testing.py |
| 8 | pending | 94_credit_governance_cockpit.py | 22_credit_analysis.py |
| 9 | pending | 95_revenue_assurance_cockpit.py | 29_revenue_assurance.py |
| 10 | pending | 96_finance_arc_cockpit.py | 52_mgmt_accounts.py |
| 11 | pending | 97_trade_finance_arc_cockpit.py | 46_trade_finance.py |
| 12 | pending | 98_ml_governance_arc_cockpit.py | 91_systems_view.py |
| 13 | pending | 99_integration_cockpit.py | 91_systems_view.py |

4/13 absorbed (31%). At ~1 cockpit per batch, completion at v10.214.

## Strategic narrative

This is the fourth absorption in a row using the v10.204 pattern
variant (programmatic body extraction with `tabs[N]` indexing). The
pattern is now mechanical — investigation per cockpit reduced to:

1. **What's the closure gate ID?** (grep audit.py)
2. **What engines does it expect?** (look at expected_engines list)
3. **What top-level tab structure does the cockpit use?** (read tab list)
4. **What's the target page's current tab count?** (verify within G4)

For v10.205 specifically: G153, 8 engines (+1 optional), 7 thematic
tabs, target had 5 tabs (room for +1). Took ~3 minutes of investigation
+ 5 minutes of script execution, vs the original ~30 minutes of v10.202
when the pattern was new. Each subsequent absorption gets faster.

## Honest acknowledgements

1. **Optional engine handled gracefully.** The ScreeningOrchestrator
   is imported in a try/except in the absorbed section — present when
   available, gracefully absent otherwise. The closure gate G153 only
   checks the 8 mandatory engines, so the optional one's presence
   doesn't affect audit pass/fail.

2. **`24_compliance.py` is now at 6/7 top-level tabs.** One slot of
   headroom remaining within G4. Future Compliance capabilities can
   add 1 more top-level tab without restructuring; beyond that, the
   pattern is tab-merging or sub-tab nesting.

3. **Engine caching preserved.** The cockpit cached engines via
   `@st.cache_resource _get_engines()`; the absorbed version uses
   `@st.cache_resource _get_arc_compliance_engines()`. Same caching
   semantics, namespaced function name.

4. **The audit_log action renamed** from `compliance_arc_cockpit.view`
   to `compliance_arc_engines.view`. Same rationale as previous
   absorptions — accurate description of the new integration point.

5. **Net code reduction: -109 lines.** Consistent with the trend
   (v10.202: -132; v10.203: -99; v10.204: -86; v10.205: -109).
   Across 13 absorptions, expected total ≈ 1300-1500 lines reduction.

6. **G153 refactor is the fifth instance of the same pattern.**
   At five instances, the helper extraction case is strong. I'm
   continuing to defer until either: (a) we hit 6-7 instances and
   the pattern is fully stabilized, OR (b) one of the remaining
   absorptions reveals a variant that the helper would need to
   accommodate. Both signals can be addressed in a single helper-
   extraction batch later.

7. **Compliance department is the 2nd-largest in the manifest** (10
   pages after this absorption, was 11 before). Cross-references in
   the absorbed text are minimal — the 8 engines are imported only
   in the new section, not scattered across other Compliance pages.

8. **Page-number collision dropping continues.** Slot 27 was claimed
   by `27_compliance_arc_cockpit.py` and `27_propositions.py`; after
   v10.205 only propositions remains. Net collision count dropping
   to 3 (from 7 at v10.197).

9. **15 consecutive clean batches in this session** — v10.193
   through v10.205 (13 code batches + 2 advisory reviews). Cockpit
   absorption sub-campaign at 4/13 = 31% complete after 4 batches.

10. **9 cockpits remain — 6 of them target the same 5 pages.** 
    Looking ahead: ML Governance (98) + Integration (99) both
    target `91_systems_view.py`. This will require sequencing —
    the second absorption into `91_systems_view.py` won't be
    purely mechanical because the page's tab structure will already
    be modified by the first. The other 4 cockpits each target
    distinct pages, so they remain independent.

## Next batch options

1. **v10.206 — Legal Arc absorption** (`28_legal_arc_cockpit.py`
   → `26_legal.py`). Continue alphabetic order.
2. **v10.206 — Extract `scripts/absorb_cockpit.py`.** After 5
   refactor instances + 4 absorptions, the pattern is fully stable.
   Single-purpose tooling batch, ~80 lines.
3. **v10.206 — Page migration to dotted form (Treasury department).**
   Validates v10.200 dotted-path access.
4. **v10.206 — Return to deferred platform items.**

I'd lean toward option 1 (continue cockpit absorption) — momentum
is high, pattern is mechanical, and each absorption ratchets
structural quality. After 6-7 absorptions complete, helper
extraction (option 2) becomes the natural pause point.
