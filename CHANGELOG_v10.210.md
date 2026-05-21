# CHANGELOG v10.210 — Revenue Assurance Arc absorbed + editorial reassignment to Finance

**Date:** 2026-05-07
**Theme:** Combined batch — editorial department reassignment + ninth
cockpit absorption. Joshua's call: SBU profitability and revenue
assurance belong under Finance, not under Sales/Operations. This
addresses the v10.197 CHANGELOG acknowledgement #3 ("Finance has only
2 pages — if you want Finance to own more, the manifest is editable
JSON") through real editorial decision rather than artificial padding.
Audit holds at **160/160 PASS**.

## What v10.210 ships

### A. Editorial reassignment to Finance department

Two pages reassigned from their old primary departments to Finance:

| Page | Before (primary) | After (primary) | After (secondary) |
|---|---|---|---|
| `9_sbu.py` | sales_customer | **finance** | sales_customer, strategy_performance |
| `29_revenue_assurance.py` | operations | **finance** | operations |

**Rationale:**
- **SBU Profitability:** P&L by business unit is Finance work. The CFO
  owns this number; sales drives revenue but doesn't own the
  cost-allocated bottom line. Sales remains secondary-visible — sales
  managers consume SBU dashboards but don't own them.
- **Revenue Assurance:** Detecting revenue leakage, verifying billing
  accuracy, reconciling partner/supplier shares — all CFO-owned
  activities. Operations consumes the leakage log but doesn't own
  the function.

This is JSON-only editorial — `department_primary` field changed in
the manifest. No code changes for this part. The manifest is the
canonical source of truth (per v10.197 design); changing the dept
membership is a 2-line JSON edit, exactly as v10.197 intended.

**Finance department goes from 1 → 3 active pages:**
```
Before v10.210:  finance = [52_mgmt_accounts.py]
After v10.210:   finance = [9_sbu.py, 29_revenue_assurance.py, 52_mgmt_accounts.py]
```

A future v10.211 Finance Arc cockpit absorption will add `52_mgmt_accounts.py`
content + the cockpit's engines, bringing Finance to a complete
operational footprint.

### B. Cockpit absorption: Revenue Assurance → 29_revenue_assurance.py

Revenue Assurance page (now in finance dept) goes from 5 → 6 top-level
tabs:

```
📋 All Records  🔴 Leakages  ⏳ Pending Waivers  📊 Analytics  ➕ Log Record  🤖 Arc Engines  ← NEW
```

Inside the new tab, 7 nested sub-tabs reproduce the cockpit's structure:

```
📋 Validation              — RevenueValidationEngine (validate_all)
🔍 Patterns                — RevenueAnomalyPatternEngine (detect_*)
🧭 Orchestrator + 📊 Metrics — RevenueOrchestrator + RevenueDashboardMetrics
🤝 Partner/Supplier        — PartnerSupplierReconciliationEngine
✅ Pre-issuance            — ContinuousBillingVerificationEngine
💼 Commission              — CommissionAssuranceEngine
🏛️ Regulatory              — RegulatoryRevenueReportingEngine
```

All 8 engines (ENH-301..308) preserved. Engines are diagnostic —
outputs feed the leakage log, waiver workflow, and CBK regulatory
submissions; nothing auto-recovers.

### C. `scripts/audit.py` — G134 refactored to manifest-aware

Tenth instance of the manifest-aware refactor pattern. Strict variant
(constructor + 8 method invocation checks preserved). The refactored
gate searches the **finance** department (not operations), since
`29_revenue_assurance.py` was editorially reassigned to finance.

This demonstrates an important property: **closure gates follow the
page, not the original cockpit name.** The gate's logic is "find the
canonical page that hosts these engines, search its current department".
If the page moves between departments via manifest edit, the gate
follows. No code change needed for dept reassignments.

### D. `pages/_manifest.json` — cockpit entry removed + dept reassignments

Three manifest changes:
1. `9_sbu.py`: `department_primary: sales_customer → finance`
2. `29_revenue_assurance.py`: `department_primary: operations → finance`
3. `95_revenue_assurance_cockpit.py`: deleted

Manifest goes 100 → **99 pages**. 5 → 4 deprecated cockpits.

### E. `pages/95_revenue_assurance_cockpit.py` — DELETED

**⚠️ Manual deletion required when applying this zip:**

```bash
rm pages/95_revenue_assurance_cockpit.py
python scripts/audit.py
```

## Files changed (3 modified + 1 deletion)

```
pages/29_revenue_assurance.py            MOD  +474 lines  (199 → 673)
                                                (6th top-level tab + 7 nested sub-tabs)
scripts/audit.py                         MOD  +14 lines net  (G134 manifest refactor)
pages/_manifest.json                     MOD  -16 lines  (cockpit removed) + 3 entries edited
pages/95_revenue_assurance_cockpit.py    DEL  -573 lines  (manual deletion required)
```

Net: -573 + 474 - 16 = **-115 lines code reduction**. Cumulative across
9 batches: -812 lines.

## Audit

```
Before (v10.209): Score: 160/160 gates = 100.0% — PASS
After  (v10.210): Score: 160/160 gates = 100.0% — PASS
```

## Department distribution after v10.210

```
sales_customer            12  (was 13 — lost 9_sbu)
credit                    12  (unchanged)
compliance_regulatory     10
operations                10  (was 11 — lost 29_revenue_assurance)
strategy_performance       8
people_hr                  7
it_platform                7
treasury_alm               6
shared                     5
risk                       5
products_pricing           4
finance                    3  (was 1 — gained 9_sbu + 29_revenue_assurance)
external                   2
legal                      2
admin                      1
trade_finance              1
```

Finance is no longer the smallest department. Trade Finance + Admin
remain at 1 each (intentional — Trade Finance has only its dashboard
page; Admin only its config page).

## Cockpit absorption schedule — 9/13 done (69%)

| # | Status | Cockpit | Target |
|---|---|---|---|
| 1-8 | ✅ v10.202-v10.209 | Treasury, Strategy, Product, Compliance, Legal, Resource Opt, Risk, Credit Governance | (various) |
| 9 | **✅ v10.210** | **95_revenue_assurance_cockpit.py** | **29_revenue_assurance.py** (now in finance dept) |
| 10 | pending | 96_finance_arc_cockpit.py | 52_mgmt_accounts.py |
| 11 | pending | 97_trade_finance_arc_cockpit.py | 46_trade_finance.py |
| 12 | pending | 98_ml_governance_arc_cockpit.py | 91_systems_view.py |
| 13 | pending | 99_integration_cockpit.py | 91_systems_view.py |

9/13 absorbed (69%). At 1/batch, completion at v10.214. Items 12+13
share `91_systems_view.py` — v10.213 needs dual-target sequencing.

## MD/CEO visibility — preserved + improved

The reassignment improves the MD/CEO experience. Previously, finance
had only 1 page (Management Accounts), so a CFO/MD glance at the
"finance" department in the sidebar showed almost nothing actionable.
Now Finance department contains:
- Management Accounts (existing)
- SBU Profitability (reassigned — central CFO concern)
- Revenue Assurance (reassigned — leakage detection)
- (Soon: Finance Arc engines via 96_finance_arc_cockpit absorption in v10.211)

This makes the **Finance section of the sidebar an actually useful
financial command surface** — exactly what the MD/CEO + CFO need.

The MD's primary pan-departmental modules (Command Centre, Board Papers,
BSC, Tier-1 Benchmarking, Strategic Initiatives, Capital & Liquidity)
remain in their canonical locations. A dedicated MD Cockpit page
that aggregates these views remains a candidate for after the cockpit
absorption sub-campaign completes (v10.215+).

## Strategic narrative

This batch demonstrates the manifest's fundamental value as data,
not code:

- **Editorial reassignment** = JSON edit. No code batch. Audit checks
  via G160 that the new department membership is valid (i.e. the
  declared department exists in the manifest's departments block).
- **Closure gate refactor** = behavior-based search through the
  canonical department. Gate follows the page, not the original
  cockpit name.
- **Cockpit absorption** = standard 5-step pattern, mechanical at
  this point.

The combination in one batch showed how the three layers cooperate.
Future editorial decisions ("move this page to that department")
are JSON edits; closure gates remain valid; cockpit absorptions can
target reassigned pages without special-casing.

## Honest acknowledgements

1. **Combined batch crosses single-purpose discipline.** v10.210 has
   two distinct concerns (editorial reassignment + cockpit absorption)
   in one ship. Justified because the closure gate refactor needs to
   know which department to search, and that's the new finance
   department only after the reassignment. Doing them in two batches
   would have required either (a) the gate searching "operations"
   first then "finance" later, or (b) the editorial reassignment
   batch having no closure gate change. Combined is cleaner; flagged
   transparently.

2. **The cockpit's 7 tab labels included some I didn't predict.**
   First-pass placeholder labels were "Validation, Anomaly Patterns,
   Orchestrator, Partner/Supplier Recon, Dashboard Metrics, Continuous
   Billing, Commission Assurance" but the cockpit's actual labels
   were "Validation, Patterns, Orchestrator + Metrics, Partner/Supplier,
   Pre-issuance, Commission, Regulatory" (different content groupings).
   The script extracted the cockpit's actual labels and used those.
   This is the right behavior — preserve cockpit's UX choices rather
   than impose mine.

3. **Cockpit had 7 tabs but Regulatory was its 7th, not 8th.** I'd
   originally allocated 8 sub-tabs in my placeholder design (one per
   engine); cockpit's design merged Orchestrator + Metrics into one
   tab, so 7 tabs cover 8 engines. Preserved exactly.

4. **G134 refactor preserves all 8 strict invocation checks.** Same
   strictness as G130 + G132. The refactored gate is the third strict
   variant (alongside G130 Risk and G132 Credit Gov). Helper
   extraction at v10.215+ would need a `strict_mode=True` flag for
   these three.

5. **9_sbu.py has been in sales_customer since v10.197.** The
   reassignment is editorial, not a correction — the original
   assignment was reasonable (SBU Performance is consumed by sales),
   but the page is conceptually owned by Finance (P&L numbers).
   Both are valid views; Joshua's call is the better organizational
   match for Ecobank's actual operating model.

6. **The cockpit's deprecation_target_page was already
   29_revenue_assurance.py** in the v10.197 manifest design. The
   v10.210 absorption matches that target. The fact that the target
   moved from operations to finance department is incidental —
   target_page is identified by filename, not department. Manifest
   design honors this.

7. **No code changes for the editorial reassignment.** No imports
   updated, no access keys changed, no API routes touched. The
   reassignment is pure metadata. After v10.210 deploys, sales
   staff still see SBU Performance in their nav (via secondary
   visibility); finance staff now see it in their primary section.
   Two views, same page, same access logic.

8. **Net code reduction: -115 lines** — back in the typical range
   after Risk (-49) and Credit Gov (-35). Revenue Assurance cockpit
   had typical boilerplate compression (header, page_config,
   require_access, audit_log call all eliminated on transfer).

9. **Page-number collision count unchanged at 2.** Slot 95 was only
   claimed by `95_revenue_assurance_cockpit.py`; no collision relief.
   Slot 29 still has 2 claimants (`29_revenue_assurance.py` +
   formerly `29_resource_optimization_cockpit.py` which was already
   absorbed in v10.207, so slot 29 is now uniquely held).

10. **20 consecutive clean batches in this session** — v10.193
    through v10.210 (18 code batches + 2 advisory reviews).
    Cockpit absorption sub-campaign at 9/13 = 69% complete. 4
    cockpits remaining.

11. **The Finance Arc absorption (v10.211) will further enrich
    Finance department.** Currently 3 active pages (Management
    Accounts + SBU + Revenue Assurance). After v10.211 Finance Arc
    cockpit absorption, the Management Accounts page will gain its
    Arc Engines tab covering whatever engines that closure gate
    expects. Finance will become a substantial department with a
    proper CFO-focused operational surface.

12. **MD Cockpit candidate keeps getting clearer.** With finance
    department now substantive (3 → 4 pages projected after v10.211),
    the MD's natural information needs span: Strategy & Performance
    (BSC, Initiatives, Board Papers, Benchmarking) + Finance
    (Management Accounts, SBU, RA) + Treasury (Capital, ALM) +
    IT/Platform (Command Centre). A dedicated 4-tab "🎯 MD Cockpit"
    page would surface the top-level metrics from each of those
    departments at a glance, with click-through to the underlying
    department pages. Becomes a natural standalone batch after
    v10.214 completion.

## Next batch options

1. **v10.211 — Finance Arc absorption** (`96_finance_arc_cockpit.py`
   → `52_mgmt_accounts.py`). Complete the Finance department's
   operational footprint.
2. **v10.211 — Trade Finance Arc** (`97_trade_finance_arc_cockpit.py`
   → `46_trade_finance.py`).
3. **v10.211 — Begin MD Cockpit design.**

I'll continue with **option 1** (Finance Arc) — it pairs naturally
with v10.210's editorial reassignment, completing the Finance
department's transformation in two consecutive batches.
