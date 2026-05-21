# A2Z MIS 360 — CHANGELOG v5.74

**v5.74 Fourth Integration Batch — Vendor Risk + Procurement**
**Released:** April 2026
**Audit gates:** 103/103 = 100% PASS (unchanged from v5.73)
**Engine batch tests:** 49 files / 2211 tests (unchanged from v5.73)
**Strategic milestone:** **Standard #96 Third-Party Risk live for the first time** + vendor-contextualised cross-reference to v5.71's #98 Procurement Workflow. **Cumulative: 10 of 116 standards integrated.**

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.74 wires Standard #96 (Third-Party Risk & Outsourcing Oversight per CBK PG/06) into the live Streamlit deployment for the first time, surfaced where vendor data already lives. It also adds a vendor-contextualised cross-reference to the v5.71-integrated #98 Procurement Workflow engine — demonstrating that a single engine can be surfaced multiple times in different contexts (deep usage at IFRS Engines Studio, vendor-record-driven at vendors page) without code duplication.

---

## What was modified

### `pages/64_vendors.py` — Risk Assessment + Procurement Workflow tabs added
**137 → 598 lines (+461)**

**Tab list expanded from 4 to 6** (within G4's 7-tab limit):

| # | Tab | Change |
|---|---|---|
| 0 | 📋 Vendor List | unchanged |
| 1 | ⚠️ Compliance | unchanged |
| 2 | 📊 Performance | unchanged |
| **3** | **🛡️ Risk Assessment** | **NEW (Standard #96)** |
| **4** | **🛒 Procurement Workflow** | **NEW (Standard #98 cross-ref)** |
| 5 | ➕ Onboard Vendor | shifted from tabs[3] |

### Risk Assessment tab — 4 sub-tabs (Standard #96)

- **🔍 Due Diligence Check** — `due_diligence_completeness()`. Verify required checks for any vendor. TIER_1_CRITICAL needs all 5 of `FINANCIAL_HEALTH` / `INFOSEC_CERT` / `BUSINESS_CONTINUITY` / `REGULATORY_COMPLIANCE` / `GEOGRAPHIC_RISK`; lower tiers need at minimum `FINANCIAL_HEALTH` + `REGULATORY_COMPLIANCE`. Missing checks block onboarding via `eligible_for_onboarding=False` (Rule 6 fail-closed).

- **📅 Review Schedule** — `review_due()` applied to **every vendor in the loaded register**. Status column color-coded: OVERDUE (red), DUE_SOON ≤30d (amber), ON_SCHEDULE (green), MISSING_DATA (grey). Top-of-tab summary banner: "X OVERDUE / Y DUE_SOON". Cadences: TIER_1=365d / TIER_2=730d / TIER_3=1095d / TIER_4=1825d.

- **📊 Concentration Risk** — `vendor_concentration_check()`. Single-vendor concentration check per CBK PG/06; alerts when one vendor exceeds **VENDOR_CONCENTRATION_CRITICAL_THRESHOLD_PCT=25%** within a category.

- **⚠️ SLA Breach Severity** — `sla_breach_severity()`. 4-level classification: CRITICAL ≥4hr · HIGH 2-4hr · MEDIUM 1-2hr · LOW <1hr per `SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS`. Severity at HIGH/CRITICAL surfaces escalation guidance.

### Procurement Workflow tab — 2 sub-tabs (Standard #98 cross-reference)

- **🎯 Vendor Procurement Quick-Check** — combines `approval_authority()` + `procurement_method()` + **vendor compliance pre-check** in one shot. Pulls vendor from the loaded register; surfaces vendor-specific guardrails: KRA non-compliance blocks payment, missing insurance flags risk, suspended status blocks PO. The full procurement engine remains at the IFRS Engines Studio (v5.71); this tab is the vendor-contextualised entry point.

- **✅ 3-Way Match Pre-Pay** — `three_way_match()`. Pre-payment validation with ±2% tolerance.

### Engine files — UNCHANGED
`utils/vendor_risk.py` and `utils/procurement_workflow.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED
Page already registered.

---

## 16 engine paths verified end-to-end

**Vendor Risk (10 paths):**

| Input | Engine call | Output |
|---|---|---|
| 5/5 DD checks for TIER_1_CRITICAL | `due_diligence_completeness()` | complete=True, eligible=True |
| 1/5 DD checks | `due_diligence_completeness()` | complete=False, missing 4 surfaced |
| Last review 200d ago, TIER_1 | `review_due()` | due_in=165, NOT overdue |
| Last review 360d ago | `review_due()` | due_in=5, due_soon |
| Last review 400d ago | `review_due()` | due_in=-35, **OVERDUE** |
| Downtime 0.5hr | `sla_breach_severity()` | LOW |
| Downtime 1.5hr | `sla_breach_severity()` | MEDIUM |
| Downtime 3hr | `sla_breach_severity()` | HIGH |
| Downtime 5hr | `sla_breach_severity()` | CRITICAL |
| V1=60M of 100M CRITICAL_TECH | `vendor_concentration_check()` | alert=True, max=V1@60% |

**Procurement Workflow (6 paths):**

| Amount | tier | method | quotes |
|---|---|---|---|
| 50K | BUYER | DIRECT_PURCHASE | 1 |
| 500K | MANAGER | REQUEST_FOR_QUOTATION | 3 |
| 10M | DIRECTOR | OPEN_TENDER | 0 |
| 50M | MD | RESTRICTED_TENDER | 5 |
| 100M | BOARD | RESTRICTED_TENDER | 5 |
| PO 100K / GRN 102K / Inv 100K | `three_way_match()` | matched=True, eligible=True |
| PO 100K / GRN 110K / Inv 100K | `three_way_match()` | matched=False (10% > 2% tolerance) |

---

## Heuristic page-to-engine mappings (documented honestly)

The page's vendor JSON schema differs from the engine's expected `VendorRecord`. Mappings applied:

**Page category → engine VENDOR_CATEGORIES** (keyword-based):
- "IT" / "Technology" → `CRITICAL_TECH` if TIER_1, else `NON_CRITICAL_TECH`
- "Cleaning" / "Security" / "Maintenance" → `FACILITIES`
- "Outsourc" → `OUTSOURCED_OPS`
- everything else → `PROFESSIONAL_SERVICES`

**Spend → engine VENDOR_TIERS** (proxy, since page lacks explicit tier):
- ≥50M → `TIER_1_CRITICAL`
- ≥10M → `TIER_2_HIGH`
- ≥1M → `TIER_3_MEDIUM`
- else → `TIER_4_LOW`

These heuristics work for the demonstration but are documented spec deviations. **For production deployment, the vendor JSON schema should be extended** to store explicit `tier` and `risk_classification` fields so the engine applies without inference.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "VendorRisk #96: DD check V001 tier=TIER_1_CRITICAL complete=True")
audit_log("IFRS_ENGINE_USED", uname, "VendorRisk #96: Review schedule scanned, overdue=2, due_soon=5")
audit_log("IFRS_ENGINE_USED", uname, "VendorRisk #96: Concentration CRITICAL_TECH max=V1@60% alert=True")
audit_log("IFRS_ENGINE_USED", uname, "VendorRisk #96: SLA severity 3hr → HIGH")
audit_log("IFRS_ENGINE_USED", uname, "Procurement #98: Workflow check vendor=V001 amt=500000 tier=MANAGER")
audit_log("IFRS_ENGINE_USED", uname, "Procurement #98: 3WM PO=100000/GRN=102000/INV=100000 matched=True")
```

---

## Cross-page integration pattern

This batch demonstrates that a single engine can be surfaced in **multiple contexts** without code duplication:

- **#98 Procurement Workflow** lives at v5.71's IFRS Engines Studio (`pages/88_ifrs_engines.py`) for **deep workflow use** (any procurement amount, any vendor, full state machine)
- The same engine is surfaced at v5.74's vendors page (`pages/64_vendors.py`) for **vendor-contextualised use** (selected from loaded register, with vendor compliance pre-check)

Both surfaces call the engine; neither duplicates business logic. The page is pure presentation. This is the integration pattern at scale.

---

## Honesty discipline visualised

- **KRA non-compliance blocks payment** — visible in vendor procurement quick-check
- **Suspended status blocks PO** — surfaces immediately on vendor selection
- **Missing insurance flagged as risk** — yellow warning, not silent
- **Goodwill-style fail-closed**: missing DD checks → onboarding BLOCKED (no override)
- **OVERDUE reviews** color-coded red across all loaded vendors
- **Concentration ≥25%** triggers explicit alert with vendor ID and percentage
- Every engine call audit-logged with `IFRS_ENGINE_USED` events

---

## What didn't change

- Both engine source files — byte-for-byte unchanged
- `scripts/audit.py` — gates G92 (vendor_risk) / G90 (procurement) still pass exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- v5.71 IFRS Engines Studio (88_ifrs_engines.py) — unchanged
- v5.72 Capital & Risk page (89_capital_risk_engines.py) — unchanged
- v5.73 modified pages (19_credit_monitoring, 52_mgmt_accounts) — unchanged
- `app.py` — unchanged (vendors page already registered)

---

## Comparison vs v5.73

| | v5.73 | v5.74 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **9** | **10** ⭐ |
| Audit gates | 103/103 | 103/103 (unchanged) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 89 numbered | 89 numbered (unchanged) |
| **Modified existing pages** | 2 | **3** (cumulative) |
| Lines added across pages this batch | — | +461 (vendors only) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Page passes `python -m py_compile`, module-level import test, and 16-path engine call simulation at the CLI. User must run `streamlit run app.py` locally to confirm browser rendering.

2. **10 of 116 integrated.** 106 standards remain library-only.

3. **Heuristic page-to-engine mappings** documented above. The page's free-text categories and spend-based tier proxy work for demonstration but should be replaced with explicit schema fields in production.

4. **Onboarding tab moved from tabs[3] to tabs[5]** — any external deep-link using `?tab=3` would now land on Risk Assessment instead of Onboarding. None known to exist, but worth flagging.

5. **Status styling fallback** — if `pandas.style.map` is unavailable in the deployment environment, the Review Schedule table falls back to plain dataframe (content preserved, color coding lost).

6. **Vendor records may have missing fields** — engine handles via Rule 1 (returns None / surfaces reason) and the page is robust to that. Missing last_review_date displays as MISSING_DATA rather than crashing.

7. **The new tabs assume the vendor register is loaded** — if `vendor_register.json` is missing/empty, the Risk Assessment tab gracefully shows "No vendors in register — onboard a vendor first". No crash.

8. **Vendor concentration uses page's `total_spend_ytd_m`** field as proxy for `annual_spend_kes` — close enough for the demonstration but YTD spend in mid-year is not the same as annualised. Production should use a 12-month rolling annualised spend.

---

## Next batch options ranked by impact

| Priority | Batch | Standards | Strategy |
|---|---|---|---|
| **(1) Recommended** | Customer 360 + Disclosures | #95 CLV + #110 IFRS 7 + #116 IAS 24 | Enhance `pages/34_customer360.py` |
| (2) | Treasury / ALM | #75 FX + #71 LCR/NSFR | Enhance `pages/25_treasury.py` + `pages/81_alm.py` |
| (3) | Stress Testing | #79 | Enhance `pages/35_stress_testing.py` |
| (4) | HR Performance | #63 + #64 | Enhance `pages/2_people.py` |
| (5) | Remaining IFRS Engines | #101-#108 | New consolidated page |

Recommend **(1) Customer 360 + Disclosures** for v5.75 — covers **3 standards in one batch** (CLV is operationally useful for RM teams, IFRS 7 + IAS 24 are statutory disclosure requirements). Customer 360 is one of the platform's high-traffic pages for any RM role.

Alternative: **(2) Treasury / ALM** if regulatory urgency higher than customer analytics — wires #75 FX limits per CBK PG/03 and #71 LCR/NSFR per Basel III.

---

**Cumulative tally:** 116 standards delivered, **10 integrated into UI via 2 dedicated pages + 3 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.
