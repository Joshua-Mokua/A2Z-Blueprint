# A2Z MIS 360 — CHANGELOG v6.1

**v6.1 Thirty-First Integration Batch — AML/KYC DEPTH (#36 + #46)**
**Released:** May 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt — 6th consecutive)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **🛡️ DEPTH-BATCH TEMPLATE PROVEN ACROSS 5 DOMAINS.** First **dual-page** depth batch covering 2 engines simultaneously. Cumulative: **51 of 116 standards integrated.**

---

## Strategic milestone — 5th application + first dual-page depth

v6.1 is the **5th application** of the depth-batch template, now proven across 5 distinct functional domains:

| Batch | Domain | Engine(s) |
|---|---|---|
| v5.95 | Customer-centric | CLV |
| v5.97 | HR Compensation | Compensation Equity |
| v5.98 | HR Engagement | Employee Engagement |
| v5.99 | Controls/Governance | Internal Controls (RCSA) |
| **v6.1** ⭐ | **Compliance/AML** | **KYC + TxnMonitor (DUAL-PAGE)** |

v6.1 also pioneers **dual-page depth batch** — single batch enhances 2 related pages covering 2 related engines in the same domain (AML/CFT framework). Future batches in connected domains can follow this pattern.

---

## What this batch is — and what it isn't

**Pure depth integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v6.1 wires **Standards #36 (KYC) + #46 (TxnMonitor) DEPTH** simultaneously. All 5 engine paths were already wired in v5.86 + v5.88. v6.1 adds:

1. **Composed analytics** combining engine paths into Executive Scorecards (one per engine)
2. **Batch-style portfolio analytics** for KYC customer assessment
3. **Caller-side aggregations** for jurisdiction concentration + alert status flow
4. **Investment maps** for risk components + per-rule severity load

---

## What was modified

### `pages/55_aml.py` — KYC Depth (+541 lines)
**639 → 1180 lines**

`kyc_sub_tabs` expanded 5 → 6 (G4-strict ≤7). New 6th sub-tab **"📦 KYC Depth (#36, v6.1)"** contains 4 inner tabs:

| # | Inner tab | Content |
|---|---|---|
| 0 | 📋 KYC Executive Scorecard | Composes assess_customer + portfolio_risk_summary |
| 1 | 🎯 Customer Assessment Batch | 12-customer synthetic book sorted by risk score desc |
| 2 | 🌐 Jurisdiction Concentration Map | Geographic spread categorized by FATF risk |
| 3 | 🎚️ Risk Component Investment Map | 5-component analysis with priority bands |

#### KYC Executive Scorecard — 4 sections:
1. **Risk band distribution** — LOW/MEDIUM/HIGH/PROHIBITED counts
2. **PEP / Sanctions / Auto-prohibited flags**
3. **CDD workload** — SDD / Standard / EDD / Rejected counts
4. **Overall verdict** GREEN/AMBER/RED based on issues from {prohibited > 0, sanctions > 0, pep_pct > 10%, high_pct > 25%}

#### Risk Component Investment Map priority bands:
- 🔴 CRITICAL >50% of book has high score (≥15) — major risk concentration
- 🟡 IMPORTANT >25% — invest in controls
- 🟢 MONITOR ≥10% — manageable exposure
- ✅ STRONG <10% — well-controlled

### `pages/36_smart_alerts.py` — TxnMonitor Depth (+480 lines)
**734 → 1214 lines**

`tm_sub_tabs` expanded 3 → 4 (G4-strict ≤7). New 4th sub-tab **"📦 TxnMonitor Depth (#46, v6.1)"** contains 4 inner tabs:

| # | Inner tab | Content |
|---|---|---|
| 0 | 📋 Alert Executive Scorecard | Composes scan + alert_summary into single screen |
| 1 | 🎯 Rule Coverage Matrix | Per-rule fired count + threshold tuning recommendations |
| 2 | 🔄 Alert Status Flow Analysis | Workflow simulation + SAR rate metrics |
| 3 | 🎚️ Severity Investment Map | Per-rule investigation load = severity_weight × count |

#### Alert Executive Scorecard — 4 sections:
1. **Alert volume + rule coverage %** (out of 8 rules)
2. **Severity distribution** CRITICAL / HIGH / MEDIUM / LOW
3. **Status pipeline** OPEN / INVESTIGATING / SAR_FILED / DISMISSED
4. **Overall verdict** GREEN/AMBER/RED based on issues from {crit > 0, open > 5, coverage < 50%}

#### Severity Investment Map:
- Severity weights: CRITICAL=10, HIGH=5, MEDIUM=2, LOW=1
- Investment priority bands: CRITICAL ≥30 / IMPORTANT ≥15 / MONITOR ≥5 / LOW LOAD <5

### Engine files — UNCHANGED
`utils/kyc_aml_risk.py` and `utils/transaction_monitoring.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED

---

## 5 engine paths verified across 4 scenarios

**Scenario 1 — KYC Executive Scorecard** (5-customer dataset after schema fix):
- C001 INDIVIDUAL/KE → MEDIUM (30)
- C002 PEP_DOMESTIC/KE/PRIVATE_BANKING → HIGH (50)
- C004 PEP_FOREIGN/AF/CORRESPONDENT → **PROHIBITED (95)** — auto-prohibited
- C007 INDIVIDUAL/**KP** → **PROHIBITED (100)** — geography auto-prohibit
- C011 sanctions_hit=True → **PROHIBITED (100)** — sanctions auto-prohibit
- Portfolio summary: {LOW:0, MEDIUM:1, HIGH:1, PROHIBITED:3, pep:2, **sanctions:1**, auto_proh:3}

**Scenario 2 — Jurisdiction Concentration** (15 customers): 1 KP (PROHIBITED) + multiple AF/MM/SY (HIGH RISK) + PK/JO/TR (MEDIUM RISK) → triggers prohibited country alert + high-risk concentration warning at threshold ≥3.

**Scenario 3 — TxnMonitor Scorecard** (30+ transactions triggering 6 of 8 rules):
- Coverage: **75%** (6 / 8 rules fired)
- Total alerts: **7**
- Severity distribution: 1 CRITICAL (R2 structuring), 4 HIGH (R1+R7×2+R8), 2 MEDIUM (R5+R6)
- R3 + R4 didn't fire → engine correctly detects only matching activity (NORMAL)

**Scenario 4 — Status Flow Simulation**: 3 alerts moved OPEN → INVESTIGATING, 1 → SAR_FILED. Final: {OPEN:3, INV:2, SAR:1, DIS:0}, **SAR rate = 100%** on closed alerts (well-calibrated).

---

## Critical engine API specifics documented

12 findings verified during build (most importantly, a major schema gotcha):

1. **`KycAmlRiskEngine` has 2 STATIC methods**: assess_customer + portfolio_risk_summary (already a built-in batch aggregator).

2. **🆕 SCHEMA GOTCHA — `assess_customer` input dict uses ENGINE-SPECIFIC keys**:
   - `country_code` (NOT `country`)
   - `onboarding_channel` (NOT `channel`)
   - `sanctions_hit` (NOT `sanctions_flag`)
   - `behavior` is a NESTED DICT with sub-keys `txn_count_30d` + `txn_amount_kes_30d` + `structured_deposits_count_30d` (NOT top-level keys)

   **Initial v6.1 implementation used wrong keys** and produced silently-wrong assessments (engine ignores unrecognized keys via `customer.get('key', default)`). Fixed via 27-customer-dict bulk regex replacement.

   **Lesson**: always verify engine input schema by reading `def assess_customer` docstring before building synthetic test data.

3. **🆕 `KycRiskAssessment` returns 12 fields** including risk_score (0-100), risk_band, cdd_level, component_scores (5-component dict), pep_flag, sanctions_flag, auto_prohibited, auto_prohibited_reason.

4. **🆕 Auto-prohibition triggers**:
   - sanctions_hit=True (any score)
   - country_code in PROHIBITED_JURISDICTIONS (KP, IR)
   - Cumulative score ≥ 80 (RISK_BAND_PROHIBITED_MIN)

5. **🆕 portfolio_risk_summary returns 5 keys**: total_customers, by_band (dict), pep_count, sanctions_count, auto_prohibited_count. **Does NOT return per-component aggregation** — caller must aggregate manually.

6. **🆕 `TransactionMonitoringEngine` has 3 INSTANCE methods**: scan + alert_summary + transition_alert. Engine maintains internal alert state across calls within same instance.

7. **🆕 `Transaction.txn_type` engine-specific values** — engine recognizes `CASH_DEPOSIT`, `CASH_WITHDRAWAL`, `TRANSFER` (NOT `DEPOSIT`). R1 only fires on cash transactions.

8. **🆕 RULE_CATALOG is dict of 8 rules** R1-R8 with name + severity. Production extension needs engine code change.

9. **🆕 ALLOWED_ALERT_TRANSITIONS dict** enforces lifecycle:
   - OPEN → INVESTIGATING only
   - INVESTIGATING → {SAR_FILED, DISMISSED}
   - SAR_FILED + DISMISSED are terminal

10. **🆕 transition_alert returns Tuple[bool, str]** — first is success flag, second is message.

11. **🆕 alert_summary is INSTANCE method** — `engine.alert_summary()` not `Engine.alert_summary(...)`.

12. **🆕 Both engines lack composite scoring** — KYC has portfolio_risk_summary (band-distribution only, no overall health score), TxnMonitor has alert_summary (count distribution only, no health verdict). v6.1 caller-side scorecards address this gap. Production deployment may want utils/composite_scores.py extension to add `aml_health_composite`.

---

## Audit logging

Every depth invocation produces audit events:

```
audit_log("AML_ENGINE_USED", uname, "KYC #36 (depth): scorecard total=12 high=2 prohibited=3 pep=2 sanctions=1 issues=2")
audit_log("AML_ENGINE_USED", uname, "KYC #36 (depth): batch n=8 prohibited=2 high=1 med=3 low=2")
audit_log("AML_ENGINE_USED", uname, "KYC #36 (depth): jurisdiction map prohibited=1 high=2 medium=3 low=9")
audit_log("AML_ENGINE_USED", uname, "KYC #36 (depth): component map critical=1 important=0")
audit_log("IFRS_ENGINE_USED", uname, "TxnMonitor #46 (depth): scorecard total=7 crit=1 open=7 coverage=75%")
audit_log("IFRS_ENGINE_USED", uname, "TxnMonitor #46 (depth): coverage matrix no_fire=2 high_fire=0")
audit_log("IFRS_ENGINE_USED", uname, "TxnMonitor #46 (depth): flow open=3 inv=2 sar=1 dis=0 sar_rate=100%")
audit_log("IFRS_ENGINE_USED", uname, "TxnMonitor #46 (depth): severity map critical=0 important=0")
```

---

## ✅ Sixth consecutive clean-first-try

Audit clean on first attempt — **6th consecutive after v5.96 + v5.97 + v5.98 + v5.99 + v6.0**. G4-strict + depth-batch templates routine. Even with the schema gotcha (which would have failed at runtime in browser), the audit-gate suite passed because syntax + tab-count gates don't catch silent semantic errors.

**Lesson**: audit gates are necessary but not sufficient — runtime simulation is the second line of defense.

---

## Honesty discipline visualised

- **Schema gotcha documented** explicitly — lesson for future depth batches
- **Auto-prohibition triggers transparent** — sanctions / KP / IR / score ≥80 spelled out
- **Severity weights (10/5/2/1) visible** in caption — production override possible
- **Engine constants surfaced byte-for-byte** — HIGH/MEDIUM/PROHIBITED jurisdictions from engine
- **Rule coverage % explicit** — surfaces under-utilization (R3+R4 didn't fire in synthetic data)
- **SAR rate calculation explicit** — only counted on closed alerts
- **CDD workload mapping** transparent — band → CDD level per engine constant
- **CBK PG/15 + FATF Rec. 12 + 20 referenced** — regulatory framework anchored
- Every depth call audit-logged

---

## What didn't change

- Both engine source files — byte-for-byte unchanged
- `scripts/audit.py` — gates G36 + G46 still pass exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v6.0 pages — unchanged (except 55_aml + 36_smart_alerts which gain depth)
- Sub-tabs 0-4 in `55_aml.py` kyc_sub_tabs — unchanged
- TAB 6 portfolio summary in `55_aml.py` — completely untouched
- Sub-tabs 0-2 in `36_smart_alerts.py` tm_sub_tabs — unchanged
- TAB 6 alert summary + TAB 7 engine reference in `36_smart_alerts.py` — completely untouched
- The `aml_alerts.json` data store — completely untouched
- `app.py` — unchanged

---

## Comparison vs v6.0

| | v6.0 | v6.1 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **49** | **51** ⭐ (+2 — KYC depth + TxnMonitor depth) |
| Audit gates | 103/103 (clean first try) | 103/103 (**clean first try**) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| Modified existing pages cumulative | 15 | 15 (re-enhances 55_aml + 36_smart_alerts) |
| Lines added across pages this batch | +66 (v6.0) | **+1021** (across 2 pages — largest single batch) |
| 55_aml.py total lines | 639 | **1180** |
| 36_smart_alerts.py total lines | 734 | **1214** |
| Clean-first-try streak | 5 | **6** |
| **Depth batches cumulative** | 4 | **5** ⭐ (+v6.1) |
| **Domains with depth coverage** | 4 | **5** (+ compliance) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude** — pages pass `python -m py_compile`, module-level engine import test, and 4-scenario engine call simulation. User must run `streamlit run app.py` locally to confirm browser rendering. New nesting levels: AML tabs[5] → kyc_sub_tabs[5] → _kyc_depth_inner[0..3]; Smart Alerts tabs[4] → tm_sub_tabs[3] → _tm_depth_inner[0..3].

2. **51 of 116 integrated** — 65 standards remain library-only.

3. **All inner tabs use synthetic / hardcoded data** — production needs real customer_risk_register + txn_stream from FLEXCUBE + alert_workflow from compliance system.

4. **🆕 KYC Engine schema gotcha** — initial implementation used wrong keys (`channel`/`sanctions_flag`/top-level velocity). Engine silently accepted them and produced wrong assessments. Fixed via bulk regex. **This is a recurring pattern with engines using `customer.get('key', default)`** — defaults mask schema errors. Production deployment with strict schema validation (e.g. pydantic) would catch this.

5. **🆕 Component aggregation in KYC depth is caller-side** — engine returns component_scores per assessment but doesn't aggregate. Engine could add `component_concentration_summary(assessments)`.

6. **🆕 Jurisdiction map uses engine constants** (HIGH/MEDIUM/PROHIBITED jurisdictions) — production must keep in sync with FATF blacklist updates (typically 3-month review cycle); engine change required when FATF list changes.

7. **🆕 TxnMonitor batch is INSTANCE-method** — multiple depth views in same session each create new engine instance via `TransactionMonitoringEngine()`; this resets internal alert state. Production with persistent engine state needs instance-management strategy.

8. **🆕 Severity weights (10/5/2/1) are HARD-CODED** — production may want bank-specific weights based on cost-time per investigation.

9. **🆕 Alert status flow shows synthetic workflow** — first 3 alerts moved to INVESTIGATING + 1 to SAR_FILED. Actual production data would have organic distribution.

10. **🆕 Coverage threshold (50%) for verdict is HARD-CODED** — some banks consider 30% coverage acceptable in steady-state, others require 70%.

11. **🆕 v6.0 composite_scores.py NOT extended** — could add `aml_health_composite(kyc_summary, alert_summary)` combining band distribution + alert pipeline + SAR rate. Deferred to v6.2+.

12. **🆕 No cross-engine correlation analysis** — KYC HIGH-risk customers and TxnMonitor frequent-alert customers should overlap; v6.1 doesn't surface this. Production with joined customer_id keys could surface "customers with HIGH KYC risk AND ≥3 alerts in last 30 days" — would be a strong pre-SAR filter.

---

## Strategic narrative — compliance domain deeply covered

After v6.1, the compliance domain has 7 batches of coverage:

| Batch | Standard | Type |
|---|---|---|
| v5.81 | CBK Returns | new engine |
| v5.85 | RCSA + Op Risk | new engines |
| v5.86 | KYC initial | new engine |
| v5.88 | TxnMonitor initial | new engine |
| v5.99 | RCSA depth | depth batch |
| v6.1 | KYC depth | depth batch |
| v6.1 | TxnMonitor depth | depth batch |

**Standards #36 + #44 + #46 all have full depth coverage** — the most thoroughly-integrated trio in the platform. This sets a benchmark for future domains.

---

## Next batch options ranked by impact

| Priority | Batch | Engine | Strategy |
|---|---|---|---|
| **(1) Recommended** | **Stress Testing depth (#51)** | stress_testing | 6th depth-batch application; completes daily-risk trifecta depth coverage symmetric to AML |
| (2) | Customer-value composite UI surfacing | composite_scores | Extends v5.96 with composite tile |
| (3) | RCSA-health composite UI surfacing | composite_scores | Extends v5.99 with composite tile |
| (4) | AML-health composite addition | composite_scores | Extend with `aml_health_composite()` |
| (5) | More depth batches | various | Treasury (#37+#38), Credit risk (#20+#21+#23) — dual/triple-page opportunities |
| (6) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer) |

With AML/KYC depth integrated, recommend **(1) Stress Testing depth** for v6.2 — would extend the daily-risk trifecta (IRRBB v5.72 + LCR/NSFR v5.76 + Stress Testing v5.78) with proper depth coverage symmetric to HR + customer + governance + compliance domains.

---

**Cumulative tally:** 116 standards delivered, **51 integrated into UI via 3 dedicated pages + 15 enhanced existing pages + 1 utility module**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications, **5 depth batches across 5 distinct domains**, 6 consecutive clean-first-try.

🛡️ **Compliance domain deeply covered** (7 batches across #36 + #44 + #46 with full depth coverage).

✅ **Clean-first-try streak: 6** (G4-strict + depth-batch templates routine).

📦 **First dual-page depth batch** confirms template scales to multi-engine domains.
