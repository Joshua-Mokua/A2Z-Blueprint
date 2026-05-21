# CHANGELOG v10.212 — Final dual cockpit absorption: ML Governance + Integration → 91_systems_view.py

**Date:** 2026-05-07
**Theme:** Final batch of the cockpit absorption sub-campaign.
Absorbs the last 2 cockpits (`98_ml_governance_arc_cockpit.py` +
`99_integration_cockpit.py`) into `91_systems_view.py`. Refactors
G140 to manifest-aware behavior-based — thirteenth and final
manifest-aware refactor. **🎉 13/13 cockpits absorbed (100%).
Sub-campaign complete.** Audit holds at **160/160 PASS**.

## What v10.212 ships

### Constraint: target page is at G4 7-tab ceiling

`91_systems_view.py` already had 7 top-level tabs (the 7-tab cap):
1️⃣ The One Question, 2️⃣ System Stocks, 3️⃣ Feedback Loops, 4️⃣ Hard
Invariants, 5️⃣ Boundary Awareness, 6️⃣ Bounded Contexts, 7️⃣ Health
Composites. Could not add an 8th top-level tab without violating G4.

**Resolution:** 3-level nested absorption inside Tab 7 (Health
Composites). The composite_tabs list extends from 4 → 6 entries.
Each new entry holds a cockpit's full absorbed content as a further
nested st.tabs() call. Both cockpits fit thematically as system
health composites.

### A) ML Governance Arc → composite_tabs[4] "🤖 ML Models"

Tab 7's nested composite_tabs goes 4 → 5 → 6:

```
🧠 AML Health  🏢 RCSA Health  👥 Workforce Health  🎯 Customer Value  🤖 ML Models  ← NEW (4)
```

Inside "🤖 ML Models", 6 nested sub-sub-tabs reproduce the cockpit:

```
🗂️ Registry (ENH-281)         — MLOpsModelRegistryEngine
✋ Adjudication (ENH-282)       — MLOpsAdjudicationLogEngine
🔄 Retraining (ENH-283)        — MLOpsRetrainingSchedulerEngine
🆎 A/B Harness (ENH-284)       — MLOpsABHarnessEngine
📋 Model Cards (ENH-285)       — MLOpsModelCardComposerEngine
🔌 Cross-Platform Wiring (G141) — MLOPS_INTEGRATION_REGISTRY catalog
```

All 5 mlops engines (ENH-281..285) preserved + the integration
registry catalog (G141 catalog ratchet). All engines diagnostic.

### B) Integration → composite_tabs[5] "🔌 Integration"

Tab 7's composite_tabs extends to:

```
🧠 AML Health  🏢 RCSA Health  👥 Workforce Health  🎯 Customer Value  🤖 ML Models  🔌 Integration  ← NEW (5)
```

Inside "🔌 Integration", 6 nested sub-sub-tabs reproduce the cockpit:

```
📊 Coverage             — _compute_g143_summary (KPI source → aggregator coverage)
📋 Rules                — utils.integration.rules
🔢 Preview Actuals      — Integration Layer preview path
🔎 Resolution Metrics   — utils.integration.resolver
▶️ Run Period           — utils.integration.runner
🐛 Debug                — Integration Layer debug helpers
```

Surfaces the G143 KPI source → aggregator coverage health metric
inline within the Health Composites tab. Diagnostic only — writes
happen via the Integration Layer scripts at `utils/integration/`,
not from this UI.

### C) `scripts/audit.py` — G140 refactored to manifest-aware

Thirteenth instance of the manifest-aware refactor pattern (final
instance — every closure-arc-UI gate is now manifest-aware).
Simple variant: searches `it_platform` department for 5 mlops
imports + 5 constructors + require_access + audit_log.

Note: the Integration cockpit had no dedicated UI integration gate
(the G143 KPI aggregator gate is informational-pass and doesn't
require the cockpit file). So only G140 needed refactoring; G143
continues to function based on the standards registry, not the
cockpit's existence.

### D) `pages/_manifest.json` — final 2 cockpit entries removed

Manifest goes 97 → **95 pages**. **0 deprecated cockpits remaining
— campaign complete.**

### E) Both cockpit files DELETED

**⚠️ Manual deletion required when applying this zip:**

```bash
rm pages/98_ml_governance_arc_cockpit.py
rm pages/99_integration_cockpit.py
python scripts/audit.py
```

## Files changed (3 modified + 2 deletions)

```
pages/91_systems_view.py                     MOD  +998 lines  (1326 → 2324)
                                                   (composite_tabs 4 → 6 + 2 new sub-tab handlers)
scripts/audit.py                             MOD  +18 lines net  (G140 refactor)
pages/_manifest.json                         MOD  -32 lines  (2 cockpit entries removed)
pages/98_ml_governance_arc_cockpit.py        DEL  -559 lines
pages/99_integration_cockpit.py              DEL  -669 lines
```

Net: -1228 (cockpits) + 998 (target) - 32 (manifest) = **-262 lines
net code reduction**.

Cumulative reduction across 12 absorption batches: **-1378 lines**.

## Audit

```
Before (v10.211): Score: 160/160 gates = 100.0% — PASS
After  (v10.212): Score: 160/160 gates = 100.0% — PASS
```

## 🎉 Cockpit absorption sub-campaign — COMPLETE

| # | Status | Cockpit | Target |
|---|---|---|---|
| 1 | ✅ v10.202 | 26_treasury_arc_cockpit.py | 25_treasury.py |
| 2 | ✅ v10.203 | 15_strategy_arc_cockpit.py | 83_strategy.py |
| 3 | ✅ v10.204 | 16_product_arc_cockpit.py | 5_products.py |
| 4 | ✅ v10.205 | 27_compliance_arc_cockpit.py | 24_compliance.py |
| 5 | ✅ v10.206 | 28_legal_arc_cockpit.py | 26_legal.py |
| 6 | ✅ v10.207 | 29_resource_optimization_cockpit.py | 10_opex.py |
| 7 | ✅ v10.208 | 93_risk_arc_cockpit.py | 35_stress_testing.py |
| 8 | ✅ v10.209 | 94_credit_governance_cockpit.py | 22_credit_analysis.py |
| 9 | ✅ v10.210 | 95_revenue_assurance_cockpit.py | 29_revenue_assurance.py (+ editorial reassign) |
| 10 | ✅ v10.211 | 96_finance_arc_cockpit.py | 52_mgmt_accounts.py (at G4 ceiling) |
| 11 | ✅ v10.211 | 97_trade_finance_arc_cockpit.py | 46_trade_finance.py |
| 12 | **✅ v10.212** | **98_ml_governance_arc_cockpit.py** | **91_systems_view.py** (3-level nested) |
| 13 | **✅ v10.212** | **99_integration_cockpit.py** | **91_systems_view.py** (3-level nested) |

**13/13 absorbed (100%).** Total batches: 11 (v10.202 + v10.203 + ... +
v10.207 + v10.208 + v10.209 + v10.210 + v10.211 dual + v10.212 dual).

## Final platform state

```
Pre-v10.197:  124 page files on disk (chaos)
v10.197:      108 manifest entries (canonical source declared)
v10.202:      107 (Treasury absorbed)
v10.203:      106 (Strategy)
v10.204:      105 (Product)
v10.205:      104 (Compliance)
v10.206:      103 (Legal)
v10.207:      102 (Resource Opt)
v10.208:      101 (Risk)
v10.209:      100 (Credit Governance)  ← milestone
v10.210:       99 (Revenue Assurance + editorial reassignment)
v10.211:       97 (Finance + Trade Finance dual)
v10.212:       95 (ML Governance + Integration dual)  ← END STATE
```

**95 pages** — clean, organized, manifest-tracked, department-routed.
Down from 124 sprawling files pre-v10.197. **23% page count reduction**
plus the deeper architectural gain of every page having a department
+ module_path + manifest entry.

Department distribution at campaign close:
```
sales_customer            12
credit                    12
compliance_regulatory     10
operations                10
strategy_performance       8
people_hr                  7
it_platform                7
treasury_alm               6
shared                     5
risk                       5
products_pricing           4
finance                    3   (was 1 before v10.210)
external                   2
legal                      2
admin                      1
trade_finance              1
                         ────
                          95 active pages
```

## All 13 manifest-aware gate refactors

The campaign refactored 13 closure-arc-UI gates from location-locked
to manifest-aware behavior-based:

**Simple variants (8 — imports + constructors only):**
- G149 (cockpits_registered_in_app, v10.199)
- G151 (treasury_arc_ui_integrated, v10.202)
- G159 (strategy_arc_ui_integrated, v10.203)
- G148 (product_arc_ui_integrated, v10.204)
- G153 (compliance_arc_ui_integrated, v10.205)
- G155 (legal_arc_ui_integrated, v10.206)
- G157 (resource_optimization_arc_ui_integrated, v10.207)
- G140 (ml_governance_arc_ui_integrated, v10.212)

**Strict variants (5 — imports + constructors + method invocations):**
- G130 (risk_arc_ui_integrated, v10.208)
- G132 (credit_model_risk_arc_ui_integrated, v10.209)
- G134 (revenue_assurance_arc_ui_integrated, v10.210)
- G136 (finance_arc_ui_integrated, v10.211)
- G138 (trade_finance_arc_ui_integrated, v10.211)

A future helper extraction (`scripts/_check_engines_in_dept`) with
a `strict_mode=True` flag would unify these. Strong candidate for
v10.213+.

## All 6 cockpit pattern variants documented

| Variant | Cockpit | Tab convention |
|---|---|---|
| Hand-paste | v10.202 Treasury | n/a |
| Named descriptive | v10.203 Strategy | `with tab_form:` etc. |
| Indexed inline | v10.204 Product, v10.205 Compliance, v10.210 Revenue Assurance | `with tabs[N]:`, body col 8 |
| Numbered named | v10.206 Legal, v10.212 ML Gov + Integration | `with tabN:` or `with tab_X:` |
| Render-funcs-per-tab | v10.207 Resource Opt | `def render_X_tab(engines):` + call sites |
| Indexed multi-line strings | v10.211 Finance + Trade Finance | string-aware extraction needed |

The pattern catalog is complete. A `scripts/absorb_cockpit.py`
extraction would cover all observed patterns with one helper.

## MD/CEO visibility — campaign-end state

Per the standing reminder throughout the campaign, the MD/CEO has
full cross-departmental visibility through the manifest's
admin-traversal path. After the campaign:

**MD's primary modules — all in canonical locations, unaffected:**
- Command Centre (`6_integrate.py` — it_platform dept)
- Board Papers (`84_board.py` — strategy_performance dept)
- BSC (`1_perform.py` — strategy_performance dept)
- Tier-1 Benchmarking (`87_benchmarking.py` — strategy_performance dept)
- Strategic Initiatives (`83_strategy.py` — strategy_performance dept,
  now with Strategy Arc Engines tab from v10.203)
- Management Accounts (`52_mgmt_accounts.py` — finance dept, now with
  Finance Arc Engines tab from v10.211)
- Capital & Liquidity (Treasury dept pages — Treasury Arc Engines tab
  from v10.202 in `25_treasury.py`)

**Engine relocations preserved MD access:** Every absorbed engine is
still reachable, just from its primary department's parent page
instead of a separate cockpit. The MD's department-traversal sees
all engines because admin sees all departments.

**Future MD Cockpit candidate:** With the cockpit campaign done,
all engine relocations stable, and departments properly organized,
a dedicated `xx_md_cockpit.py` page that aggregates the 7 above
modules into a single executive surface is now a clean standalone
batch. Estimated effort: ~150 lines, similar pattern to existing
composite dashboards. Strong candidate for v10.215+.

## Honest acknowledgements

1. **3-level nesting in 91_systems_view.py is heavy UX.** Tab 7
   (Health Composites) > composite_tabs[4 or 5] > arc_tabs[N] is
   3 levels deep. The alternative (replace one of the 7
   systems-thinking tabs to free a top-level slot) would have been
   editorial loss. The chosen approach preserves all existing
   content + adds the absorbed cockpits in a thematically-sensible
   place (engines as health composites alongside AML Health, RCSA
   Health, etc.). A future v10.215+ batch could reconsider if 3
   levels feels too deep — moving ML Models + Integration to a new
   `xx_platform_engines.py` page would flatten to 2 levels but adds
   a new page entry.

2. **Integration cockpit had no dedicated closure gate.** Only
   G140 (ML Governance) needed refactoring. G143 (KPI source →
   aggregator coverage) continues to function based on the standards
   registry, not on cockpit existence. So G143 was unchanged.

3. **The G140 refactor str_replace had a partial match — the old
   summary tail wasn't included in my replacement string, leaving
   orphan code. A second str_replace cleaned it up. Standard
   debugging; total time impact ~2 minutes.

4. **Net code reduction: -262 lines in this batch, -1378 cumulative
   across 12 batches.** Average ~115 lines per batch. The cumulative
   reduction is ~24% of the original cockpit content — most absorbed
   content is preserved because it's unique business logic, not
   boilerplate.

5. **G140 is the thirteenth and final manifest-aware refactor.**
   No more closure-arc gates need this transformation. The pattern
   library is complete; helper extraction has clear scope.

6. **`91_systems_view.py` is now 2324 lines.** Largest single page
   on the platform. Could be split into multiple files in a future
   refactor (e.g. extract Tab 7 Health Composites to its own
   module), but this isn't urgent — the file is logically organized
   by tab, has clear section dividers, and reads cleanly top-to-bottom.

7. **Page-number collision count.** Slot 98 + 99 only had cockpits;
   no collision relief. Net collisions: 2 (slot 16 with 16_commission +
   formerly 16_product_arc; slot 26 with 26_legal + formerly
   26_treasury_arc). After v10.212, slots 98 and 99 are now uniquely
   held by other entries (or empty if no other page uses those numbers).

8. **22 consecutive clean batches in this session** — v10.193 through
   v10.212 (20 code batches + 2 advisory reviews). Cockpit absorption
   sub-campaign **complete** at 13/13 = 100%.

9. **The dual-target sequencing was clean.** Both cockpits absorbed
   into 91_systems_view.py within the same script execution, with
   the composite_tabs list extended to 6 in one go. No interaction
   between the two absorptions — each fits in its own slot.

10. **Both cockpits' content fits the "Health Composites" theme.**
    ML Governance is about ML model health (which models are deployed,
    are they drifting, when to retrain). Integration is about
    Integration Layer health (KPI coverage, rule resolution, period
    runs). Both are platform-level health concerns, naturally
    grouped with AML Health, RCSA Health, etc.

## What's next

With the cockpit absorption sub-campaign complete, natural next
batches are:

1. **v10.213 — `scripts/absorb_cockpit.py` helper extraction.**
   Codify the 6 absorption pattern variants + 13 gate refactor
   patterns into one reusable helper. Single-purpose tooling batch,
   ~120 lines. Useful for future similar work; clean wind-down of
   the campaign.

2. **v10.213 — MD Cockpit page design.** Build a dedicated
   `xx_md_cockpit.py` page aggregating Command Centre + Board Papers
   + BSC summary + Tier-1 Benchmarking + Capital snapshot +
   Management Accounts highlights + Strategic Initiatives RAG.
   Single-page executive surface for the MD/CFO. Per Joshua's
   earlier note, becomes a natural standalone batch now.

3. **v10.213 — Return to deferred platform items.** PG migration
   (33/52 tables remaining), API endpoints (114/136 remaining),
   test coverage expansion, FATCA/CRS XML, 5/8 CBK reports, React
   SPA (#37), React Native (#38), or the Streamlit cockpit UI
   integration completion.

4. **v10.213 — Page migration to dotted form.** v10.200 introduced
   dotted-path access; rolling out to all departments would solidify
   the manifest's role as canonical route registry.

I'd lean toward **option 1 (helper extraction)** as the immediate
clean wind-down of the cockpit campaign, then **option 2 (MD Cockpit)**
to address the standing reminder Joshua has been holding throughout.
After those two, the platform is structurally complete for the
absorption + reorganization phase, and v10.215+ can return to
deferred platform items in earnest.
