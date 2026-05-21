# CHANGELOG v10.268 — BSD save wiring (CBK persistence layer COMPLETE)

**Date:** 2026-05-07
**Theme:** Phase 4 (final) of CBK persistence layer. Adds
`save_bsd_result()` adapter to handle BSD generators' `Dict[str, Any]`
return shape (different from CbkReturnPackage), then wires all 4 BSD
tabs (BSD-1/2/3/17). **All 9 generation paths now persist.**
**Audit gates: 163/163 PASS. Lines added: ~125 helper + ~40 wiring.**

## What v10.268 ships

### 1. New `save_bsd_result()` adapter in utils/cbk_regulatory_reporting.py

BSD generators return `Dict[str, Any]` with keys like `return_type`,
`generated`, `compliant`, `liquidity_ratio_pct`, etc. — NOT a
`CbkReturnPackage`. Two options were considered:

**Option A: Make BSD generators return CbkReturnPackage** — would
require breaking changes to `utils/regulatory_returns.py` and
unwiring/rewiring all 4 BSD tabs. High risk.

**Option B: Adapter** — map BSD dict → same persist_dict shape as
save_cbk_package. Both flows write to the same
cbk_returns_generated table. **Chosen.**

The adapter:
- `return_code`: passed in (e.g. "BSD-1", "BSD-2", "BSD-3", "BSD-17")
- `period`: passed in (caller supplies — typically reporting_date for
  daily BSD-1 or YYYY-MM for monthly BSD-2/3/17)
- `breach_severity`: derived from BSD's `compliant` flag
  (True → NONE, False → BREACH, None → NONE)
- `computed_metrics`: full BSD result dict (as JSONB, all values stringified)
- `inputs_used`: empty (BSD inputs already audit-logged separately)
- `framework_refs`: ["Standard #80", "BSD return suite — daily/weekly/monthly cadence"]

Same dual_save plumbing, same append-only history, same id format.

### 2. Wired all 4 BSD tabs

After each `audit_log("IFRS_ENGINE_USED")` site:

```python
audit_log("IFRS_ENGINE_USED", uname, ...)
_persist = _save_bsd(r, "BSD-X", period_string, uname, DATA)
if _persist.get("persisted"):
    st.caption(
        f"💾 Persisted (id={_persist['data']['id']}, "
        f"PG={'✅' if _persist.get('pg_persisted') else '—'})")
```

Tabs wired:
- 💧 BSD-1 (Daily Liquidity) — period = `str(today)` (full date)
- 📊 BSD-2 (Weekly Balance Sheet) — period = `str(today)[:7]` (YYYY-MM)
- 💰 BSD-3 (Monthly Capital Adequacy) — period = `str(today)[:7]`
- 🏦 BSD-17 (Monthly Credit Quality) — period = `str(today)[:7]`

## Files changed

```
utils/cbk_regulatory_reporting.py    MOD  +125 lines (save_bsd_result)
pages/74_cbk_returns.py              MOD  +40 lines (4× wire blocks + import)
```

## Audit

```
163/163 PASS
G162: 3,663 → 3,664 → 3,663 (caught a "CBK" docstring token, refactored)
G163: GROWING (DDL 27→32, MIGRATORS 17→18) — same as v10.267
```

A docstring in `save_bsd_result` initially said "CBK risk-based
packages" — refactored to "the risk-based packages" to keep G162
clean. Lesson: even docstrings count toward G162.

## Smoke test verified

```python
BSD-1 result (compliant=True):
  Persisted: True
  ID: BSD-1_2026-04-30_20260507T114728
  Severity: NONE
  Description: BSD-1 compliant for period 2026-04-30

BSD-3 result (compliant=False):
  Persisted: True
  Severity: BREACH

Total rows after both: 2 ✓
```

## CBK persistence layer COMPLETE

```
✅ DDL                          (v10.265)
✅ Migrator                     (v10.265)
✅ Save helper for CBK packages (v10.265 + bugfix v10.266)
✅ UI wiring — 5 Risk-Based tabs (v10.266)
✅ Calendar enrichment           (v10.267)
✅ Save adapter for BSD          (v10.268) THIS BATCH
✅ UI wiring — 4 BSD tabs        (v10.268) THIS BATCH
```

**All 9 generation paths now persist. Calendar surfaces all 9 in the
Recent Generations enrichment.**

## Sub-campaign closure

CBK persistence layer = 4-batch sub-campaign (v10.265-v10.268)
delivering:
- 1 new table (cbk_returns_generated)
- 1 new migrator
- 2 save helpers (save_cbk_package + save_bsd_result)
- 1 calendar enrichment
- 9 UI wiring sites (5 Risk-Based + 4 BSD)
- 1 latent bug fixed (v10.266)

Plus the original v10.262-v10.264 work (Risk-Based UIs themselves)
and v10.253-v10.260 PG migration sub-campaign that established the
dual_save pattern.

## Honest acknowledgements

1. **Period strings are caller-supplied.** v10.268 uses
   `str(today)` for BSD-1 (daily) and `str(today)[:7]` for monthly
   BSDs. If the user generates for a different reporting period than
   today's date, the persisted period won't match. Future polish:
   add a period selector at the top of each BSD tab.

2. **Severity is binary for BSDs.** Unlike risk-based packages
   (NONE/MARGINAL/BREACH/SEVERE_BREACH), BSDs only signal
   compliant/non-compliant. The adapter maps to NONE/BREACH —
   MARGINAL and SEVERE_BREACH are not used. This is faithful to
   what the BSD generators actually report.

3. **The audit gate G162 caught even a docstring "CBK".** This is
   as designed — Rule N1 says no hardcoded tenant tokens, and the
   gate doesn't distinguish docstring vs runtime. Worth noting that
   "documentation comments" can drift just like code.

4. **65 consecutive clean batches** — v10.193 through v10.268.

## What's next

The CBK persistence sub-campaign is COMPLETE. Available paths:

1. **Resume direct-write cleanup** (Phase A.2 — partnership migrators
   from v10.261)
2. **FATCA/CRS XML** (utils/fatca_crs.py has 4 builder methods unwired)
3. **Continued G162 cleanup** (chip away at 3,663 baseline)
4. **G167 ratchet — smoke tests for save helpers** (close the v10.265
   bug detection gap)
5. **Update consolidated zip** to include v10.265-v10.268
6. **Wrap up for the day**

The kaizen ratchets G161 + G162 + G163 will continue policing in the
background regardless of which path you pick.
