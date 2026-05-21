# A2Z MIS 360 — CHANGELOG v5.81

**v5.81 Eleventh Integration Batch — CBK Returns (#80)**
**Released:** April 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt — 7th clean-first-try in a row)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **🏛️ REGULATORY FRAMEWORK INTEGRATION ARC COMPLETE.** Cumulative: **28 of 116 standards integrated.** Eleventh integration batch.

---

## Strategic milestone — regulatory framework arc complete

With v5.81, every major CBK supervisory framework is now wired into the UI:

| Framework | Standard | Integrated in |
|---|---|---|
| **CBK PG/02** Capital Adequacy + IRRBB | #74, #76, #77 | v5.72 |
| **CBK PG/03** FX Position + LCR/NSFR | #75, #71 | v5.76 |
| **CBK ICAAP** Stress Testing | #79 | v5.78 |
| **CBK PG/04** Channels Availability | #91 | v5.80 |
| **CBK BSD Returns** (BSD-1/2/3/17) | **#80** | **v5.81** ⭐ |

The 5 batches together cover what would typically be 5 separate regulatory submission systems in a tier-1 bank, all consolidated into the same unified A2Z platform with the same audit guardrails.

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.81 wires **Standard #80 CBK Returns** (`regulatory_returns.py`) — the engine that auto-generates CBK BSD prudential returns from validated financial inputs.

**Second regulatory engine `regulatory_reporting.py` deliberately NOT integrated** — it overlaps with engines already in UI (CAR via v5.72, LCR via v5.76, sectoral exposure analogous to v5.78). Integrating it would duplicate functionality. Documented as a deliberate decision.

---

## What was modified

### `pages/74_cbk_returns.py` — BSD auto-generators added
**231 → 596 lines (+365)**

**Top-level tab list UNCHANGED at 7** (already at G4 limit). Used **sub-tab containment pattern** in tab[2] "➕ Submit Return" (proven in v5.73, v5.76, v5.79):

| # | Top-level tab | Inner sub-tabs |
|---|---|---|
| 0 | 📋 Returns Calendar | unchanged |
| 1 | 🔴 Overdue & Upcoming | unchanged |
| **2** | **➕ Submit Return** | **NEW: 📝 Manual Submission + 🤖 BSD Auto-Generators (#80)** |
| 3 | 🔍 Findings | unchanged |
| 4 | 📊 Analytics | unchanged |
| 5 | ⚙️ Config | unchanged |
| 6 | 📈 BSC | unchanged |

The "📝 Manual Submission" sub-tab preserves the existing flow byte-for-byte. The new "🤖 BSD Auto-Generators (Standard #80)" sub-tab adds 4 inner tabs:

### BSD Auto-Generators — 4 inner tabs

**💧 BSD-1 Daily Liquidity** — 5 inputs (cash / CB balances / T-bills / other liquid assets / total deposits). Engine computes:
- liquid_assets total
- liquidity_ratio_pct vs `STATUTORY_LIQUIDITY_RATIO_MIN_PCT=20%`
- COMPLIANT/BREACH verdict

**📊 BSD-2 Weekly Balance Sheet** — 8 inputs across assets and liabilities/equity sides. Engine validates accounting equation Assets = Liabilities + Equity:
- balance_check_passed boolean
- balance_check_diff_kes (absolute difference)
- Flags imbalances for review before submission

**💰 BSD-3 Monthly Capital Adequacy** — 4 inputs (CET1 / Tier 1 / total capital / total RWA). Engine computes:
- CET1 ratio
- Tier 1 ratio  
- Total CAR
- compliant_cbk verdict against CBK floor

**🏦 BSD-17 Monthly Credit Quality** — variable number of loans (loan_id / outstanding / DPD). Engine classifies into 5 `LOAN_CLASSIFICATIONS`:

| Class | DPD range | Provision % |
|---|---|---|
| NORMAL | 0-30 days | 1% |
| WATCH | 31-60 days | 3% |
| SUBSTANDARD | 61-90 days | 20% |
| DOUBTFUL | 91-180 days | 50% |
| LOSS | 181+ days | 100% |

Produces NPL ratio + total provisions + per-classification breakdown table. Surfaces `excluded_count` for loans with missing data per Rule 6 transparency.

### Engine file — UNCHANGED
`utils/regulatory_returns.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED
Page already registered.

---

## 4 engine paths verified end-to-end (8 scenarios)

Healthy + breach scenarios for each return:

**BSD-1 Daily Liquidity:**

| Scenario | Inputs | Output |
|---|---|---|
| Healthy | 25B liquid / 100B deposits | ratio **25%**, **COMPLIANT** ✅ |
| Breach | 10B liquid / 100B deposits | ratio **10%**, **NON-COMPLIANT** ⛔ |

**BSD-2 Balance Sheet:**

| Scenario | Inputs | Output |
|---|---|---|
| Balanced | Assets 190B = Liab 168B + Equity 22B | diff=0, **BALANCED** ✅ |
| Imbalance | Equity 2B too low | diff=**2B**, **IMBALANCED** ⛔ |

**BSD-3 Capital Adequacy:**

| Scenario | Inputs | Output |
|---|---|---|
| Healthy | CET1=18B / T1=20B / Total=25B / RWA=150B | CET1 **12%** / T1 **13.33%** / CAR **16.67%** → **COMPLIANT** ✅ |
| Breach | All capital 60% lower | CAR **8%** → **NON-COMPLIANT** ⛔ |

**BSD-17 Credit Quality:**

| Scenario | Inputs | Output |
|---|---|---|
| 7 loans across all 5 classes | DPD 5/10/25/45/75/120/250 | NPL ratio **34.88%**, total provisions **KES 4.10M**, per-classification table |
| 7 loans + 1 with missing DPD | Same + L008 with `days_past_due=None` | count=7, **excluded=1** (Rule 6 transparency) |

---

## Critical engine API specifics documented

These were verified during build:

1. **`Bsd1Inputs / Bsd2Inputs / Bsd3Inputs`** are dataclasses where ALL fields are `Optional[Decimal]` except `reporting_date: Optional[date]`. Missing inputs gracefully produce None outputs (Rule 1).

2. **BSD generators all return dict** with `return_type` (BSD_1/2/3/17), `frequency` (DAILY/WEEKLY/MONTHLY), `generated` (boolean), `reporting_date`, plus return-specific computed fields.

3. **BSD-2 returns `balance_check_diff_kes`** as the absolute difference between assets and (liabilities + equity), with `balance_check_passed=True` only when diff is exactly 0. For IFRS reporting practice this is too strict (rounding always introduces small differences); for regulatory submission purposes it should be exact.

4. **BSD-3 `compliant_cbk`** checks ALL three thresholds simultaneously — CET1 ≥ floor AND Tier 1 ≥ floor AND total CAR ≥ floor. Failing any one fails the overall verdict.

5. **BSD-17 `LOAN_CLASSIFICATION_DAYS`** dict has tuples representing inclusive ranges — `NORMAL=(0,30)` means 0-30 days inclusive on both ends, `WATCH=(31,60)` starts at exactly 31.

6. **BSD-17 `LOAN_PROVISION_PCT`** returns Decimal NOT percentage — `Decimal('20')` means 20%, page must format with `%` suffix.

7. **`LoanForClassification`** with `outstanding_kes=None` OR `days_past_due=None` is silently excluded from BSD-17 computation but counted in `excluded_count`. Never raises exception (Rule 6 fail-soft).

8. **BSD-1 `compliant=True`** only when `liquidity_ratio_pct ≥ 20%` strictly — not `>`.

9. **BSD-3 returns Decimal ratios with 2 decimal places** (e.g. `"12.00"`, `"13.33"`, `"16.67"`) — page can format directly with `%`.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "CBK Returns #80: BSD-1 ratio=25.00% compliant=True")
audit_log("IFRS_ENGINE_USED", uname, "CBK Returns #80: BSD-2 balance check=True diff=0.00")
audit_log("IFRS_ENGINE_USED", uname, "CBK Returns #80: BSD-3 CET1=12.00% T1=13.33% CAR=16.67% compliant=True")
audit_log("IFRS_ENGINE_USED", uname, "CBK Returns #80: BSD-17 7 loans, NPL=34.88%, provisions=4100000.00")
```

---

## ✅ Seventh clean-first-try batch in a row

Audit clean on first attempt (after v5.74, v5.76, v5.77, v5.78, v5.79, v5.80). G3 (audit_log alias) and G4 (7-tab limit) lessons embedded in process. Sub-tab containment pattern proven for the 4th time.

---

## Honesty discipline visualised

- **CBK statutory thresholds bound byte-for-byte** in caption — STATUTORY_LIQUIDITY_RATIO_MIN_PCT=20%, classification ranges, provision percentages
- **Loan classification reference table** in expander shows engine constants — single source of truth
- **BSD-3 compliance is AND-gated** — must pass CET1, T1, AND total CAR thresholds simultaneously
- **BSD-2 imbalance surfaced exactly** — diff in KES so user can decide rounding vs true imbalance
- **BSD-17 excluded_count** transparently flags loans skipped due to missing data (Rule 6)
- **NPL ratio bands color-coded** — < 5% green, < 10% amber, ≥ 10% red
- Every engine call audit-logged with ratio + compliance verdict

---

## What didn't change

- Engine source file — byte-for-byte unchanged
- `scripts/audit.py` — gate G80 still passes exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v5.80 pages — unchanged
- The 6 other top-level tabs in `74_cbk_returns.py` — completely untouched
- The existing manual submission flow — byte-for-byte preserved inside its new sub-tab wrapper
- `app.py` — unchanged

---

## Comparison vs v5.80

| | v5.80 | v5.81 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **27** | **28** ⭐ (+1) |
| Audit gates | 103/103 | 103/103 (clean first try) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| **Modified existing pages cumulative** | 10 | **11** |
| Lines added across pages this batch | +567 (branch+channel) | +365 (cbk_returns) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Page passes `python -m py_compile`, module-level engine import test, and 4-path engine call simulation at the CLI. User must run `streamlit run app.py` locally to confirm browser rendering — especially the **4-level nested tab structure** (top-level tabs → submit return → BSD auto-generators → BSD-1/2/3/17). Streamlit handles deep nesting but visual density is high.

2. **28 of 116 integrated** — 88 standards remain library-only.

3. **BSD inputs are user-entered with sensible defaults** — they do NOT auto-pull from CBS, treasury, or ledger data. **For production CBK submission, all values MUST be sourced from validated financial systems** — the engine produces deterministic computations from inputs, but the inputs themselves are the user's responsibility. The defaults reflect a representative Ecobank-sized Tier-2 bank but should be overridden with real period-end figures before any actual CBK submission.

4. **BSD-17 takes only 7 sample loans** — production loan books have 100K-1M+ loans. **The page is a teaching/QA tool not a production batch processor.** For real BSD-17 generation, the engine should be called from a backend job that streams the full loan book; the page can be used to validate the engine produces correct classifications for sample loans before trusting the batch output.

5. **BSD-2 balance check is strict (zero tolerance)** — even rounding differences cause failure. For real submissions where rounding is unavoidable, the engine surfaces the diff in KES so user can decide if it's a true imbalance vs rounding artifact. The page does not provide a configurable tolerance.

6. **The new BSD auto-generators sub-tab does NOT integrate with the page's existing `cbk_returns.json` data store** — engine output is computed live, displayed on screen, and audit-logged but not persisted. To submit an engine-generated return through the existing manual flow, user must transcribe values. **Documented as a deferred enhancement** (auto-fill the manual submission form from engine output would be the natural integration).

7. **`regulatory_reporting.py` not integrated this batch** — overlaps with v5.72 (CAR), v5.76 (LCR), and v5.78 (sectoral exposure analogous to stress testing). Integrating it would duplicate functionality. **Deliberate decision documented**; if a use case emerges (e.g. unified "all-in-one" regulatory dashboard), it could be revisited.

8. **CBK return frequency strings ("DAILY", "WEEKLY", "MONTHLY")** in `RETURN_FREQUENCIES` dict are bound byte-for-byte — they don't auto-trigger reminders or schedule the page's existing Returns Calendar. The page's calendar uses its own status data; integrating engine-driven status would require refactoring the calendar logic. Deferred.

---

## Strategic narrative — regulatory framework arc complete

With v5.81, the Compliance team operating CBK returns submission can now use deterministic engine-generated returns alongside their existing manual submission flow — the engine output can be cross-checked against the bank's actual financial systems before submission, **reducing accuracy errors that drive the K072 KPI**.

The 5 regulatory batches (v5.72 → v5.76 → v5.78 → v5.80 → v5.81) together cover what would typically be 5 separate regulatory submission systems in a tier-1 bank, all consolidated into the same unified A2Z platform with the same audit guardrails.

---

## Next batch options ranked by impact

| Priority | Batch | Standards | Strategy |
|---|---|---|---|
| **(1) Recommended** | Branch Ops Excellence | branch_ops_excellence | Enhance `pages/14_branch_log.py` further (wait time / error rate / TAT — completes Branch axis after v5.80) |
| (2) | Channel SLA | channel_sla | Enhance `pages/73_channels.py` further (outages + latency — completes Channels axis) |
| (3) | Predictive Performance | predictive_performance + performance_insights | If not already covered |
| (4) | Project / Audit / Compliance | smaller engines | Multiple integrations |
| (5) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer) |

With the regulatory framework arc now complete (v5.72 → v5.76 → v5.78 → v5.80 → v5.81), recommend **(1) Branch Ops Excellence** for v5.82 — completes the operational axis Branch Managers already use heavily.

---

**Cumulative tally:** 116 standards delivered, **28 integrated into UI via 3 dedicated pages + 11 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.

🏛️ **Regulatory framework integration arc COMPLETE.**
