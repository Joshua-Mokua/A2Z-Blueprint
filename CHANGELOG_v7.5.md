# A2Z MIS 360 — CHANGELOG v7.5

**v7.5 AML-health composite + L13 — composites extended + 80% loops batch**
**Released:** May 2026
**Audit gates:** **105/105** = 100% PASS (clean on first attempt — 14th consecutive)
**Strategic milestone:** **🎯 80% LOOPS WIRED + COMPOSITES EXTENDED.** First composite added since v6.0. Loops at 80%, stocks at 100%, composites at 4. Systems layer is at near-full capacity.

---

## What this batch is

**Pure systems-layer work + composite extension.** Zero new domain features. Zero new pages. Zero new engines. Zero new audit gates.

**Two things shipped**: L13 loop closure + new AML-health composite. Both are systems-layer extensions: L13 closes another cross-engine feedback loop; AML composite gives a single 0-100 view of AML programme health that composes outputs from KYC + TxnMonitor.

---

## What changed

### `aml_health_composite()` added — 4th composite

**New function** in `utils/composite_scores.py`:

```python
def aml_health_composite(
    kyc_band_distribution=None,    # from customer_base stock
    alert_summary=None,             # from transaction_monitoring.alert_summary()
    sar_conversion_pct=None,        # bank-supplied
    txn_velocity_change_pct=None,   # bank-supplied
    weights=None,
) → {
    "score": 92.0,                  # 0-100
    "severity": "HEALTHY",          # HEALTHY / MODERATE / LOW / UNKNOWN
    "components": {
        "kyc_band_stability_pct": 95.0,    # 30% weight — % LOW+MEDIUM
        "alert_disposition_pct": 85.0,      # 30% weight — % out-of-OPEN
        "sar_conversion_pct_inverse": 100.0, # 20% weight — peaks at 10%
        "txn_velocity_stability_pct": 90.0,  # 20% weight — period stability
    },
    "missing_inputs": [],
    "weights_used": {...},
    "reason": "computed",
}
```

**Composes**:
- KYC band stability — directly reads `customer_base.by_kyc_risk_band_count` (the stock wired in v7.4)
- Alert disposition — directly reads `transaction_monitoring.alert_summary()` (engine wired in v7.2)
- SAR conversion — bank-supplied; inverse-scored, peaks at 10% (5-15% healthy, <1% noise, >25% under-detection)
- Transaction velocity — bank-supplied period-over-period change

**Per Charter §13** acceptance criteria: composite cites Customer Intelligence + Compliance/AML bounded contexts, uses Published Language pattern.

### `AML_HEALTH_WEIGHTS` constant exposed

Bank-specific calibration available via caller override.

### `ALL_COMPOSITES` registry extended (3 → 4)

```python
ALL_COMPOSITES = {
    "workforce_health": workforce_health_composite,   # v6.0
    "customer_value": customer_value_composite,        # v6.0
    "rcsa_health": rcsa_health_composite,              # v6.0
    "aml_health": aml_health_composite,                # v7.5 ⭐
}
```

### L13: Compensation equity → Workforce planning (WIRED)

**Consumer added** to `utils/workforce_analytics.py`:
```python
WorkforceAnalyticsEngine.merit_budget_from_compensation_equity(
    gender_pay_gap_payload,
    internal_equity_payload,
    annual_payroll_kes,
    target_remediation_pct_of_payroll=1.5,
) → {
    "recommended_merit_budget_kes": 100000000,
    "target_merit_pct": 5.0,
    "drivers": {"baseline_target_pct": 1.5, "gender_gap_pct_overall": 8.5},
    "priority_grades": [
        {"grade": "G3", "trigger": "gender_gap_over_5pct", "gap_pct": 12.0},
        {"grade": "G7", "trigger": "gender_gap_over_5pct", "gap_pct": 7.5},
        {"grade": "G5", "trigger": "internal_equity_ratio_over_4x", "ratio": 4.5},
    ],
    "consumed_payload_version": "compensation_equity.gender_pay_gap+internal_equity_ratios v1.0",
}
```

**Strategy**:
- target_merit_pct = max(baseline 1.5%, |gender_gap_pct|, max_internal_gap_pct/10)
- Capped at 5% of payroll
- priority_grades flag grades with gender gap >5% OR internal equity ratio >4×

**Round-trip verified**: 8.5% gap + 4.5× ratio scenario → 5.0% target → 100M KES merit budget on 2B payroll, 3 priority grades.

**Registry correction**: L13's `to_engine` was `utils.workforce_planning` (doesn't exist). Corrected to `utils.workforce_analytics`. **Fourth such correction in v7.x** (v7.2 audit_workflow→audit_universe, v7.3 cross_sell→cross_sell_nba, v7.4 branch_log→branch_performance, v7.5 workforce_planning→workforce_analytics). The original v7.0 registry was drafted from charter design notes; subsequent batches correct paths as engines are actually wired.

### Charter §8 updated

Wired count 11 → 12 (80%); 3 remaining unwired (L04, L05, L14).

---

## End-to-end smoke test (all green)

```
=== FULL AUDIT ===
  Score: 105/105 gates = 100.0% — PASS

Loop counts: WIRED=12, DESIGNED_NOT_WIRED=3
  WIRED: 12/15 = 80% ⭐
Stock counts: WIRED=6, NOT_WIRED=0
  WIRED: 6/6 = 100% (unchanged)

  Composite functions registered: 4
    ✓ workforce_health (v6.0)
    ✓ customer_value (v6.0)
    ✓ rcsa_health (v6.0)
    ✓ aml_health (v7.5) ⭐

  ✓ aml_health_composite: 92.0 (HEALTHY) on healthy book
  ✓ aml_health_composite: 31.1 (LOW) on risky book
  ✓ L13 round-trip: 100M KES budget on 2B payroll, 3 priority grades
```

---

## ✅ Fourteenth consecutive clean-first-try

14th batch in a row landing clean.

---

## Comparison vs v7.4

| | v7.4 | v7.5 |
|---|---|---|
| Audit gates | 105/105 | **105/105** |
| Stocks WIRED | 6 (100%) | 6 (100%, unchanged) |
| Feedback loops WIRED | 11 (73%) | **12 (80%)** ⭐ |
| Composite functions | 3 | **4** ⭐ (first composite since v6.0) |
| Engines reading from registry | 6 | 6 (unchanged) |
| Clean-first-try streak | 13 | **14** |

---

## The 12 wired loops + 4 composites

**Loops wired:** L01, L02, L03, L06, L07, L08, L09, L10, L11, L12, **L13** ⭐, L15
**Loops remaining:** L04 (vendor→opl risk), L05 (cards→segmentation), L14 (channel→alerts; needs streaming)

**Composites:**
- `workforce_health_composite` (v6.0) — engagement + eNPS + flight risk
- `customer_value_composite` (v6.0) — RFM + CLV + value tier
- `rcsa_health_composite` (v6.0) — COSO + control effectiveness + deficiencies
- `aml_health_composite` (v7.5) ⭐ — KYC bands + alert disposition + SAR rate + velocity

---

## Honest acknowledgements

1. **No live Streamlit deployment verification by Claude** — engines + composites compile + round-trip-tested.
2. **AML composite uses sample inputs** — production will pull `customer_base.by_kyc_risk_band_count` + `transaction_monitoring.alert_summary()` + monthly SAR + velocity stats.
3. **3 of 15 loops still DESIGNED_NOT_WIRED** — L04, L05, L14.
4. **L13 consumer accepts both flat and nested gender-pay-gap payload shapes** — flexibility for caller.
5. **AML composite SAR conversion uses inverse-scoring peaking at 10%** — bank can override AML_HEALTH_WEIGHTS.
6. **L13 priority_grades enumerate triggers, not severity ranking** — caller decides remediation order.
7. **No new audit gate** — G104+G105 sufficient.
8. **AML composite doesn't yet have a UI surface** — page 91 OR page 55 should surface it; deferred.
9. **L13 capped at 5% of payroll** — runaway protection; revisit if >5% gaps emerge.
10. **3 unwired loops require engine extensions** — not just registry flips.
11. **G105 scope unchanged** at 6 regulated engines.
12. **Composites still don't auto-publish** — caller must call them; future ALL_COMPOSITES iteration could feed unified system-health dashboard.

---

## Strategic narrative — composites resume + 80% loops

| Batch | Type | Loops | Stocks | Composites |
|---|---|---|---|---|
| v6.0 | Composites | implicit | implicit | **3** ⭐ (first batch) |
| v7.0 | Foundation | 5 | 0 | 3 |
| v7.0.1 | Propagation | 5 | 1 | 3 |
| v7.1 | Credit Risk | 6 | 3 | 3 |
| v7.2 | Loops | 9 | 3 | 3 |
| v7.3 | Expansion | 10 | 4 | 3 |
| v7.4 | Stocks 100% | 11 | 6 | 3 |
| **v7.5** | **Composites + L13** | **12 (80%)** | **6 (100%)** | **4** ⭐ |

**First composite added since v6.0.** composite_scores.py was idle through 8 systems-layer batches; v7.5 demonstrates that composites + systems layer are complementary, not competing.

**80% loops + 100% stocks + 4 composites = systems layer is at near-full capacity.**

---

## Next batch options

| Priority | Batch | Strategy |
|---|---|---|
| **(1) Recommended** | **v7.6 Continue Credit Risk depth on pages/32_ifrs9.py + surface 2-3 composites on page 91** | Combines functional progress (Credit Risk) with composite UI surfacing |
| (2) | v7.6 Close L05 Card usage → Segmentation | Pushes loops to 87% |
| (3) | v7.6 Close L04 Vendor health → Operational risk | partnerships engine surfacing |
| (4) | v7.6 Wire deposit_base / loan_portfolio to FLEXCUBE ACL | Replaces demo defaults with real CBS data |
| (5) | Customer-value + RCSA composite UI surfacing | Surfaces existing v6.0 composites |

**Strong recommendation: v7.6 = Credit Risk depth on pages/32_ifrs9.py + surface composites on page 91** — combines functional progress (overdue Credit Risk depth from v7.1's planned triple-page) with composite UI surfacing (overdue since v6.0).

---

🎯 **80% loops + 100% stocks + 4 composites — systems layer is at near-full capacity.**
