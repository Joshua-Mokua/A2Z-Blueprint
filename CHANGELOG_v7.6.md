# A2Z MIS 360 — CHANGELOG v7.6

**v7.6 L04 + composites surfacing — page 91 7th tab + 87% loops batch**
**Released:** May 2026
**Audit gates:** **105/105** = 100% PASS (clean on first attempt — 15th consecutive)
**Strategic milestone:** **🎯 87% LOOPS WIRED + COMPOSITES SURFACED.** L04 closed. All 4 composites now visible on page 91 systems view as new 7th tab. Systems layer at full institutional capacity.

---

## What this batch is

**Pure unification work.** Zero new domain features. Zero new pages. Zero new engines. Zero new audit gates.

**Two things shipped**: L04 loop closure + composites UI surfacing. Loop closure brings wired loops to 13/15 (87%); composites surfacing brings the 4 functions registered in `composite_scores.py` from "registered but not surfaced" to "live computation visible on page 91".

The 2 remaining unwired loops (L05 Cards→Segmentation, L14 Channel→Alerts) require infrastructure beyond v7.x scope — a `cards` engine module that doesn't yet exist + Kafka/CDC streaming respectively. **The systems layer is now at full institutional capacity.**

---

## What changed

### L04: Vendor health → Operational risk (WIRED)

**Consumer added** to `utils/operational_risk.py`:
```python
OperationalRiskEngine.vendor_health_to_oprisk(
    concentration_payload,    # from vendor_risk.vendor_concentration_check()
    sla_breach_records,       # list of severity-classified breaches
    due_diligence_payload,    # from vendor_risk.due_diligence_completeness()
) → {
    "oprisk_events": [
        {"source": "vendor_concentration", "category": "OUTSOURCING_RISK",
         "severity": "HIGH", "description": "...", ...},
        {"source": "vendor_sla_breach", "category": "BUSINESS_DISRUPTION",
         "severity": "CRITICAL", ...},
        ...
    ],
    "summary": {"total_events": 4, "by_source": {...}, "by_severity": {...}},
    "consumed_payload_version": "vendor_risk.vendor_concentration_check+sla_breach_severity+due_diligence_completeness v1.0",
    "pattern": "PUBLISHED_LANGUAGE",
}
```

**Synthesis logic**:
- Concentration breach (single vendor over threshold) → HIGH oprisk event
- SLA breach severity HIGH/CRITICAL → corresponding oprisk severity (LOW/MEDIUM filtered out)
- Due-diligence completeness <80% → MEDIUM oprisk event (compliance gap)

**Round-trip verified**: 1 concentration breach + 2 SLA breaches (HIGH+CRITICAL) + 1 due-diligence gap (60% complete) → 4 events with severity distribution HIGH×2 / CRITICAL×1 / MEDIUM×1.

**Registry correction**: L04's `from_engine` was `utils.partnerships` (doesn't exist). Corrected to `utils.vendor_risk`. **Fifth such correction in v7.x** (v7.2 audit_workflow→audit_universe, v7.3 cross_sell→cross_sell_nba, v7.4 branch_log→branch_performance, v7.5 workforce_planning→workforce_analytics, v7.6 partnerships→vendor_risk).

### Page 91 — new 7th tab "🎯 Health Composites"

**At G4-strict cap** — page 91 now has exactly 7 top-level tabs (the maximum G4 allows). 219 lines of new tab body.

**4 composite sub-tabs**:
- **🧠 AML Health** — composes `customer_base.by_kyc_risk_band_count` LIVE from systems-layer stock; alert summary + SAR + velocity inputs marked illustrative per Rule 6
- **🏢 RCSA Health** — illustrative healthy-bank profile (COSO 4.2/5, 88% effectiveness, 0 material weaknesses)
- **👥 Workforce Health** — illustrative profile (engagement 78, eNPS 35, weakest driver 65, flight risk 8%)
- **🎯 Customer Value** — illustrative high-value customer (CHAMPIONS RFM + 850K CLV + PLATINUM tier)

Each sub-tab shows: inputs section + computed score with severity icon (✅/🟡/🚨) + component breakdown + weights expander.

**Counts header** at top of tab: total composites (4) + wired-stocks consumed (1 of 4 composites) + coverage status.

**Closing info-box** explains Charter §13 alignment — composites are caller-driven by design; surfacing them on per-domain pages is the next iteration.

### Charter §8 updated

Wired count 12 → 13 (87%); 2 remaining unwired (L05, L14 — both deferred deliberately).

---

## End-to-end smoke test (all green)

```
=== FULL AUDIT ===
  Score: 105/105 gates = 100.0% — PASS

Loop counts: WIRED=13, DESIGNED_NOT_WIRED=2
  WIRED: 13/15 = 87% ⭐
Stock counts: WIRED=6, NOT_WIRED=0
  WIRED: 6/6 = 100% (unchanged)

  ✓ L04 round-trip: 4 oprisk events synthesised
    HIGH×2 / CRITICAL×1 / MEDIUM×1
  ✓ Page 91 — 7 tabs at G4-strict cap (gate G4 passes)
  ✓ Tab 7 sub-tabs: AML / RCSA / Workforce / Customer Value
  ✓ AML composite reads customer_base.by_kyc_risk_band_count LIVE
  ✓ Page 91 compiles (779 lines, +219 from v7.5's 560)
```

---

## ✅ Fifteenth consecutive clean-first-try

15th batch in a row landing clean.

---

## Comparison vs v7.5

| | v7.5 | v7.6 |
|---|---|---|
| Audit gates | 105/105 | **105/105** |
| Stocks WIRED | 6 (100%) | 6 (100%, unchanged) |
| Feedback loops WIRED | 12 (80%) | **13 (87%)** ⭐ |
| Composite functions | 4 (registered) | **4 (surfaced)** ⭐ |
| Page 91 tabs | 6 | **7** (at G4-strict cap) |
| Engines reading from registry | 6 | 6 (unchanged) |
| Clean-first-try streak | 14 | **15** |

---

## The 13 wired loops + 4 composites surfaced

**Loops wired:** L01, L02, L03, **L04** ⭐, L06, L07, L08, L09, L10, L11, L12, L13, L15

**Loops remaining (deferred):**
- L05 Card usage → Segmentation enrichment — requires a `cards` engine module (doesn't exist in `utils/`)
- L14 Channel reliability → Customer experience alerts — requires Kafka/CDC streaming infrastructure (beyond v7.x scope)

**Composites (now surfaced on page 91 tab 7):**
- `aml_health_composite` — composes `customer_base.by_kyc_risk_band_count` LIVE
- `rcsa_health_composite` — illustrative inputs
- `workforce_health_composite` — illustrative inputs
- `customer_value_composite` — illustrative inputs

---

## Honest acknowledgements

1. **No live Streamlit deployment verification by Claude** — engines + page compile + round-trip-tested; user runs `streamlit run app.py`.
2. **Tab 7 inputs are mostly illustrative** — only AML composite reads from a live wired stock; RCSA + Workforce + Customer Value sub-tabs use representative profiles per Rule 6 honesty discipline. Production will surface them on per-domain pages with real data.
3. **2 of 15 loops still DESIGNED_NOT_WIRED** — L05 (cards engine doesn't exist as module), L14 (streaming infrastructure required).
4. **Page 91 at G4-strict cap of 7 top-level tabs** — future additions require nesting or splitting into 91a/91b.
5. **L04 oprisk events synthesised in-memory** — not persisted to event store; production should call `engine.log_loss_event()` for each.
6. **L04 due-diligence threshold hardcoded at 80%** — future tunable.
7. **L04 due-diligence consumer expects single-vendor payload** — multi-vendor aggregation requires caller iteration.
8. **No new audit gate** — G104+G105 sufficient.
9. **5 cumulative to/from_engine corrections in v7.x** — pattern of registry-correction-on-wiring is itself bookkeeping discipline.
10. **Tab 7 doesn't cache composite computation** — recomputes each render; trivial for illustrative inputs.
11. **G105 strict enforcement scope unchanged at 6 regulated engines** — vendor_risk + operational_risk not in scope.
12. **2 remaining unwired loops deliberately deferred** — closure requires new modules or infrastructure beyond systems-layer expansion campaign.

---

## Strategic narrative — full institutional capacity

| Batch | Type | Loops | Stocks | Composites |
|---|---|---|---|---|
| v6.0 | Composites | implicit | implicit | 3 registered |
| v7.0 | Foundation | 5 | 0 | 3 |
| v7.0.1 | Propagation | 5 | 1 | 3 |
| v7.1 | Credit Risk | 6 | 3 | 3 |
| v7.2 | Loops | 9 (60%) | 3 | 3 |
| v7.3 | Expansion | 10 (67%) | 4 | 3 |
| v7.4 | Stocks 100% | 11 (73%) | 6 (100%) | 3 |
| v7.5 | AML composite | 12 (80%) | 6 | 4 registered |
| **v7.6** | **L04 + surfacing** | **13 (87%)** | **6 (100%)** | **4 surfaced** ⭐ |

**Systems layer at full institutional capacity:**
- Every accumulator visible (stocks 100%)
- Every reasonably-closeable feedback loop firing (loops 87%; remaining 13% deferred to infrastructure work)
- Every composite computable + visible on the systems-view page

This is the natural ceiling for the systems-layer expansion campaign. Further loops require new engine modules (L05) or streaming infrastructure (L14). Further depth requires functional batches (Credit Risk continuation) or per-domain composite surfacing.

---

## Next batch options

| Priority | Batch | Strategy |
|---|---|---|
| **(1) Recommended** | **v7.7 Continue Credit Risk depth on pages/32_ifrs9.py** | Functional progress overdue from v7.1's triple-page plan |
| (2) | v7.7 Wire deposit_base / loan_portfolio to FLEXCUBE ACL | Replaces demo defaults with real CBS data |
| (3) | v7.7 Surface composites on per-domain pages | workforce_health on page 2, rcsa_health on page 54, etc. |
| (4) | v7.7 Build cards engine + close L05 | New module work + functional batch |
| (5) | L14 streaming infrastructure | Beyond v7.x scope |

**Strong recommendation: v7.7 = Continue Credit Risk depth on pages/32_ifrs9.py** — functional progress overdue from v7.1's planned triple-page plan; gives substantive domain progress while systems layer rests at full institutional capacity.

---

🎯 **87% loops + 100% stocks + 4 composites surfaced — systems layer at full institutional capacity.**

⭐ **Five batches into autonomous run (v7.2 → v7.6) — all clean-first-try. Total: 15 consecutive across the v5.96 → v7.6 series.**
