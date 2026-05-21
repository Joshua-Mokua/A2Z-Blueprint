# A2Z MIS 360 — CHANGELOG v7.8

**v7.8 Composite surfacing campaign — 4 composites surfaced on per-domain pages**
**Released:** May 2026
**Audit gates:** **105/105** = 100% PASS (clean on first attempt — 17th consecutive)
**Strategic milestone:** **🎯 BIGGEST SINGLE-BATCH UI JUMP IN v7.x.** Integration tally 55 → **59 standards in UI** (+4). Composite surfacing pattern complete on 4 per-domain pages.

---

## What this batch is

**Pure UI integration progress.** Zero systems-layer changes. Zero engine changes. Zero new audit gates.

**One uniform pattern applied 4 times**: each composite from `composite_scores.py` is now surfaced on its natural per-domain page using `st.expander()` BEFORE the page's top-level tabs row. This respects G4-strict cap (no new top-level tabs needed) and gives operators a one-click view of the relevant health composite right at the top of the page they're already on.

The composite surfacing campaign closes the gap between "composites built and registered" (v6.0) → "composites surfaced on systems-view page 91" (v7.6) → "composites surfaced on per-domain pages where operators actually work" (v7.8). This is the natural completion of Charter §13's acceptance criteria for composites.

---

## What changed

### Page 2 (People & HR Intelligence)

`📊 Workforce Health Composite (v6.0 / v7.8 surfaced)` expander BEFORE the 4-tab row.

| Input | UI control | Default |
|---|---|---|
| Engagement score | slider 0-100 | 78 |
| eNPS | slider -100 to +100 | 35 |
| Weakest driver | slider 0-100 | 65 |
| Flight risk HIGH % | slider 0-100 | 8 |

Result: **74.9 (MODERATE)** on illustrative healthy bank profile.

### Page 54 (RCSA)

`📊 RCSA Health Composite (v6.0 / v7.8 surfaced)` expander BEFORE the 7-tab row.

| Input | UI control | Default |
|---|---|---|
| COSO overall | slider 0-5 | 4.2 |
| Control effectiveness % | slider 0-100 | 88 |
| Material weaknesses | number_input | 0 |
| Significant deficiencies | number_input | 2 |
| Other deficiencies | number_input | 8 |

Result: **76.8 (HEALTHY)** on illustrative healthy profile.

### Page 34 (Customer 360)

`📊 Customer Value Composite (v6.0 / v7.8 surfaced)` expander BEFORE the 7-tab row.

| Input | UI control | Default |
|---|---|---|
| RFM segment | selectbox | CHAMPIONS |
| CLV (KES) | number_input | 850,000 |
| Customer value tier | selectbox | PLATINUM |

Result: **94.0 (HEALTHY)** on illustrative high-value customer.

### Page 55 (AML Monitoring) — LIVE STOCK READ

`📊 AML Health Composite (v7.5 / v7.8 surfaced)` expander BEFORE the 7-tab row.

**Uniquely composes 2 LIVE inputs:**
- KYC band distribution: `get_stock_snapshot("customer_base").by_kyc_risk_band_count` LIVE from systems-layer stock
- Alert summary: computed LIVE from page's `alerts` list state

| Input | UI control / source | Default / Live |
|---|---|---|
| KYC distribution | LIVE from `customer_base` stock | 700K customers |
| Total alerts | LIVE from page state | (depends on state) |
| SAR conversion % | slider 0-30 | 10.0 |
| Txn velocity change % | slider -50 to +50 | 2.0 |

Result: **94.1 (HEALTHY)** when systems layer is at typical bank profile (75% LOW + 20% MEDIUM KYC bands).

This is the v7.6 page 91 AML composite pattern continued — now with two pages reading the same `customer_base` stock for AML composite computation. **Wiring once, surfacing many.**

---

## Uniform pattern documented

```python
with st.expander("📊 [Composite Name] (v[origin] / v7.8 surfaced)", expanded=False):
    from utils.composite_scores import [composite_function]
    st.caption("v7.8 surfacing per Charter §13...")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Inputs (illustrative ...):**")
        # sliders / selectboxes / number_inputs
    with c2:
        result = [composite_function](**inputs)
        score = result.get("score")
        severity = result.get("severity")
        sev_color = {"HEALTHY": "✅", "MODERATE": "🟡",
                     "LOW": "🚨", "UNKNOWN": "⚠"}.get(severity, "")
        st.metric("[Composite Name] score",
                  f"{score:.1f}/100" if score else "—", severity)
        st.markdown(f"**{sev_color} {severity}**")
        if result.get("components"):
            st.markdown("**Component scores:**")
            for k, v in result["components"].items():
                st.markdown(f"- `{k}`: {v:.1f}")
```

**Future surfacings copy/paste this pattern.** When L05 closes (cards engine ships) and a `cards_health_composite` is added, its surfacing on the relevant card-management page follows the same template.

---

## End-to-end smoke test (all green)

```
=== FULL AUDIT ===
  Score: 105/105 gates = 100.0% — PASS

  ✓ Page 2 workforce: 74.9 (MODERATE) — illustrative healthy
  ✓ Page 54 rcsa: 76.8 (HEALTHY) — illustrative healthy
  ✓ Page 34 customer_value: 94.0 (HEALTHY) — illustrative high-value
  ✓ Page 55 aml: 94.1 (HEALTHY) — reading LIVE customer_base (700K)

  ✓ All 4 pages compile
  ✓ G4 gate: 0 pages exceed 7-tab limit
    (page 2: 4 tabs, pages 34/54/55: 7 tabs at G4-strict cap)
  ✓ All 4 expanders BEFORE the tabs row — opt-in surfacing
```

---

## ✅ Seventeenth consecutive clean-first-try

17th batch in a row landing clean.

---

## Comparison vs v7.7

| | v7.7 | v7.8 |
|---|---|---|
| Audit gates | 105/105 | **105/105** |
| Stocks WIRED | 6 (100%) | 6 (100%, unchanged) |
| Feedback loops WIRED | 13 (87%) | 13 (87%, unchanged) |
| Composites surfaced | 4 (page 91 only) | **4 (page 91 + 4 per-domain pages)** ⭐ |
| **Standards in UI** | **55** | **59** ⭐ (+4 in one batch) |
| Per-domain composite surfacings | 0 | **4** ⭐ |
| Clean-first-try streak | 16 | **17** |

---

## Strategic narrative — biggest single-batch UI jump

| Batch | Integration tally |
|---|---|
| v7.0 | 53 |
| v7.1 (Credit Risk depth p19) | 54 (+1) |
| v7.2 — v7.6 (5 systems-layer batches) | 54 (+0 each — pure systems) |
| v7.7 (IFRS 9 engine depth p32) | 55 (+1) |
| **v7.8 (4 composite surfacings)** | **59 (+4)** ⭐ |

**The composite surfacing pattern multiplies UI integration progress.** Instead of one functional sub-tab per batch, four parallel surfacings using one uniform pattern — all of them shipping in one batch.

This is the natural way to transition the platform from *"engines + stocks + loops + composites all built"* to *"engines + stocks + loops + composites all visible to operators on the pages they actually use"*.

**51% of all standards now have a UI surface** (59 of 116), up from 47% at v7.7.

---

## Honest acknowledgements

1. **No live Streamlit deployment verification by Claude** — all 4 pages compile + composites round-trip-tested.
2. **Pages 2/34/54 inputs are illustrative** — production deployment wires the relevant engines (engagement, internal_controls, customer_segmentation).
3. **Page 55 AML composite is LIVE on 2 of 4 inputs** — kyc_band_distribution + alert_summary; SAR + velocity remain caller-supplied (not yet system stocks).
4. **All 4 expanders default to `expanded=False`** — opt-in surfacing; future iteration could default expanded=True.
5. **No persistence of slider values** — recomputes each render; trivial for illustrative inputs.
6. **No new audit gate** — pages adding composite expanders not currently audited; future G106 could enforce 'every composite has per-domain surface'.
7. **Visual styling is uniform plain markdown + metric** — easy to maintain; per-page theming could be added later.
8. **Composite invocation not in audit log** — page audit_log calls exist but composite computation isn't separately traced; probably overkill.
9. **G4-strict cap respected** — expanders BEFORE tabs row use header real estate but don't count as tabs.
10. **Pattern naturally extensible** — copy/paste template for future composites.
11. **Page 55 AML reads `customer_base` stock with same pattern as page 91 systems view** — first cross-page wiring shared with the systems layer.
12. **Composite surfacing campaign now complete on 4 of 4 per-domain pages** — this batch completes the v7.6 → v7.8 surfacing arc.

---

## Next batch options

| Priority | Batch | Strategy |
|---|---|---|
| **(1) Recommended** | **v7.9 Continue Credit Risk depth on pages/88_ifrs_engines.py** | Final leg of v7.1's triple-page plan; integration 59 → 60 |
| (2) | v7.9 Wire deposit_base / loan_portfolio to FLEXCUBE ACL | Replaces demo defaults; closes 'demo defaults' open item |
| (3) | v7.9 Build cards engine + close L05 | New module + functional batch |
| (4) | v7.9 Add per-page audit_log("COMPOSITE_VIEWED") tracing | Bookkeeping batch |
| (5) | L14 streaming infrastructure | Beyond v7.x scope |

**Strong recommendation: v7.9 = Continue Credit Risk depth on pages/88_ifrs_engines.py** — final leg of v7.1's planned triple-page Credit Risk depth campaign; gives substantive functional progress.

Alternative: FLEXCUBE ACL wiring as more strategic infrastructure for the v8.x transition.

---

🎯 **4 composites surfaced on per-domain pages — biggest single-batch UI integration jump in v7.x.**

⭐ **51% of all standards now have a UI surface (59/116). Composite surfacing campaign complete.**
