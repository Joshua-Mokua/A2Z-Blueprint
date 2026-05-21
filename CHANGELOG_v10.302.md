# Changelog — v10.302 Phase 3 Arc 8: TreasuryDashboardEngine Wiring

**Date:** 2026-05-11
**Phase:** 3 (eighth arc — engine integration, no new cockpit)
**Audit:** 193/193 gates PASS = 100.0%
**Tests:** 170/170 passing across 9 integration suites (13
skipped in audit env)
**G162 Rebase:** 4016 → 4018 (+1 Ecobank, +1 Kenya)

---

## Summary

This batch is different from v10.295-v10.301: no new cockpit
page, no new module. The work was to **close a known placeholder**
from v10.296 — the Treasury cockpit's tab 7 (Daily Treasury
Dashboard Report) was rendering with zero sections because
`TreasuryDashboardEngine()` was constructed with all 5 upstream
engine slots as `None`. The cockpit displayed an informational
banner saying "next Phase 3 step: connect ALM/Products/RWA/FTP/
Forecast engines."

v10.302 is that step. The dashboard is now wired with all 5
engines, the report composes real sections, and the report is
exposed via HTTP for the React SPA at parity with the Streamlit
cockpit.

---

## What's actually new

### `utils/treasury_dashboard_wiring.py` (NEW)

A small factory module. One public function:

```python
def make_wired_dashboard(
    entity_name: str = "Ecobank Kenya",
) -> TreasuryDashboardEngine:
    ...
```

Returns a `TreasuryDashboardEngine` with all 5 upstream engines
injected:

| Slot | Engine |
|------|--------|
| `alm_engine` | `treasury_alm.TreasuryALMEngine` |
| `products_engine` | `treasury_products.TreasuryProductsEngine` |
| `rwa_engine` | `rwa_optimization.RWAOptimizationEngine` |
| `ftp_engine` | `fund_transfer_pricing.FTPEngine` |
| `forecast_engine` | `cash_forecasting.TreasuryCashForecastingEngine` |

Each engine is instantiated via a `_try_instantiate` helper that
silently falls back to `None` on import / construction failure.
This is intentional: the dashboard's section builders render
NO_DATA cleanly for unwired engines, so a single transient
import error shouldn't break the whole cockpit tab. Loud errors
would punish the entire view for one engine having a bad day.

`entity_name` parameterised — production callers can pass their
own entity to support eventual multi-tenant deployments. Default
matches the existing dashboard default.

### `utils/cockpit_read.py` — `treasury_daily_report` composer

Wraps `make_wired_dashboard()` + `generate_daily_treasury()` and
returns a JSON-serialisable dict for the React SPA:

```
{
  "report_id": "DAILY-2026-05-11",
  "as_of_date": "2026-05-11",
  "n_sections": <int>,
  "sections": [
    {section_id, section_title, source_engine, status,
     metrics, thresholds, headroom, notes}, ...
  ],
  "board_summary": {entity, alm_wired, products_wired, ...},
  "as_at": "<ISO timestamp>"
}
```

Decimal values inside metrics/thresholds/headroom are cast to
`str` so the dict round-trips cleanly through `json.dumps`.

Defensive: wraps `generate_daily_treasury` in try/except. If a
wired engine raises on a bad-data day, the composer returns a
structured `{error: ...}` payload rather than crashing the
cockpit.

### `pages/110_treasury_live.py` — tab 7 rewritten

- Imports `make_wired_dashboard` (the greppable wiring proof
  G193 checks for)
- Uses `treasury_daily_report` composer instead of bare
  dashboard instantiation
- Renders all sections with status icons (✅ OK, ⚠ WARNING,
  🛑 BREACH, ⚪ NO_DATA), titles, IDs, notes, metric pairs
- 5-column engine wiring status row (one column per engine)
- v10.296 placeholder banner removed

### `utils/api_cockpit.py` — `/treasury/daily-report` endpoint

```
GET /api/cockpit/treasury/daily-report?as_of_date=YYYY-MM-DD
```

Optional `as_of_date` query param defaults to today UTC.
Returns the same dict the cockpit page renders. JWT-protected,
audit-logged, JSON-serialisable. **17 cockpit endpoints now**
(was 16). `COCKPIT_READ_API_VERSION` → "16.0".

### `scripts/audit.py` — G193 added

`gate_treasury_dashboard_wired` locks the closure via 8
sub-checks:

1. `utils/treasury_dashboard_wiring.py` exists with
   `make_wired_dashboard`
2. Factory returns a dashboard with all 5 engine slots non-None
3. `board_summary()` shows all 5 `*_wired` flags True
4. `generate_daily_treasury` produces ≥1 section
5. `utils.cockpit_read.treasury_daily_report` composer exists
6. Page 110 references `make_wired_dashboard` (wiring proof)
7. Old "next Phase 3 step: connect ALM" placeholder banner
   removed
8. `/api/cockpit/treasury/daily-report` endpoint registered

### `data/audit_baselines.json` — G162 rebased 4016 → 4018

+1 Ecobank, +1 Kenya for `make_wired_dashboard()`'s default
`entity_name` parameter.

### `tests/integration/test_treasury_dashboard_wiring.py` (NEW)

14 tests across 6 sections:

1. Wiring helper exists and instantiates
2. Daily report has sections after wiring (≥1, LCR + NSFR
   present)
3. Page 110 uses wired factory + placeholder banner removed
4. cockpit_read composer exists + returns documented keys +
   JSON-serialisable + non-zero sections
5. HTTP endpoint registered + documented in module docstring
6. G193 gate liveness

### `tests/integration/test_api_cockpit.py` — extended

`EXPECTED_ENDPOINTS` to 17 (was 16). Caught by the meta-test
during this batch — exactly the Kaizen pattern.

---

## TDD red→green progression

- **Red phase:** 0P 14F 0S. Nothing wired yet.
- **Green phase 1 (wiring module + composer):** mostly green,
  page-related tests still failing.
- **Green phase 2 (page 110 rewrite + HTTP endpoint):** 14P 0F.
- **Audit caught G162 drift** → +1 Ecobank, +1 Kenya, rebased
  to 4018.
- **API test caught EXPECTED_ENDPOINTS drift** → bumped to 17.

---

## Real findings during this batch

1. **Two engine class-name surprises.** `fund_transfer_pricing`
   exports `FTPEngine`, not `FundTransferPricingEngine`.
   `cash_forecasting` exports `TreasuryCashForecastingEngine`,
   not `CashForecastingEngine`. Caught during the engine
   inventory pass; documented in the wiring module's docstring
   so the next person doesn't trip on it.

2. **Wiring is safe even with empty upstream data.** The
   `build_*_section` functions in `utils/treasury_dashboard.py`
   gracefully degrade to `NO_DATA` sections when engines have
   no data. Wiring 5 engines with no production data still
   produces 4 sections (LCR + NSFR + FX exposure + cash
   forecast), all marked NO_DATA. That's a real improvement
   over zero sections — operators see the *shape* of the report
   they'll get when data lands.

3. **Defensive `_try_instantiate` matters.** Without it, a
   single engine import failure (e.g. a missing data file at
   module load time) would break the whole cockpit tab. With
   it, the failure is silent at module level and visible in
   the cockpit's wiring status row (the affected engine shows
   ⚪ instead of ✅). Operators can investigate at their pace.

4. **The Decimal → str cast is annoying but necessary.**
   `DashboardSection.metrics` uses `Decimal` for precision (FX
   rates, ratios). `json.dumps` doesn't serialise `Decimal` by
   default. The composer casts to `str` so the React SPA can
   parse with `parseFloat` or keep as string for display.

---

## Files changed

- `utils/treasury_dashboard_wiring.py` — NEW
- `utils/cockpit_read.py` — `treasury_daily_report` composer
- `pages/110_treasury_live.py` — tab 7 rewritten
- `utils/api_cockpit.py` — `/treasury/daily-report` endpoint,
  version 16.0
- `scripts/audit.py` — G193 added and registered
- `data/audit_baselines.json` — G162 → 4018
- `tests/integration/test_treasury_dashboard_wiring.py` — NEW
  (14 tests)
- `tests/integration/test_api_cockpit.py` — EXPECTED_ENDPOINTS
  to 17
- `CHANGELOG_v10.302.md` — this file

---

## Audit results

```
Score: 193/193 gates = 100.0% — PASS
```

---

## Platform state

- **Audit:** 193/193
- **Standards active:** 330/330 (no change)
- **Pages:** 116 (no change — this batch was engine wiring,
  not a new page)
- **Tiers:** 57 (no change)
- **Gates:** G1-G193 linear
- **Live cockpits:** 4 (CIMS, Treasury, Credit, Compliance) —
  Treasury's tab 7 now produces real reports
- **HTTP endpoints (cockpit):** 17 (was 16)
- **Integration test suites:** 9 (was 8)
- **Integration tests passing:** 170/170 (13 skipped in audit
  env)
- **G162 baseline:** 4018

---

## React-readiness check

The Treasury daily report is now HTTP-fetchable at
`/api/cockpit/treasury/daily-report`. A React component can
render the same `n_sections`, status icons, wiring flags, and
metrics that the Streamlit cockpit displays. Single source of
truth (the `treasury_daily_report` composer); two transports
(Streamlit cockpit + HTTP endpoint).

When the React frontend work begins, Treasury's daily report
view is the second tab type ready to wire (the first being any
of the four `*_open_work` composer outputs).

---

## What didn't change

- No new pages
- No new tiers
- Standards still 330/330
- Memory + live-data files untouched

This was a **gap-closure** batch. v10.296 left a known
placeholder; v10.302 closes it.

---

## Next Phase 3 arc options

Updated list:

1. ~~CORS + production deploy config~~ — v10.299 ✓
2. ~~Credit live cockpit~~ — v10.300 ✓
3. ~~Compliance live cockpit~~ — v10.301 ✓
4. ~~TreasuryDashboardEngine wiring~~ — v10.302 ✓ (this batch)
5. **CIMS field vocabulary harmonization (B-001)** — the
   real-world data-join bug logged in v10.295. Cockpit
   instruction-trace composer reads `channel` but the engine
   writes `originating_channel` — partial fix in v10.295.
   This batch would lock the vocabulary so cross-engine joins
   surface the real linkages.
6. **PG migration push** — toward 75/79 (95%).
7. **Cash forecast composer wiring** — close the 13-week cash
   projection placeholder in Treasury cockpit tab 6 (same
   shape as v10.302's dashboard wiring).
8. **Audit trail composer** — close the audit trail
   placeholders in all four cockpit pages' last tab. Single
   composer reading data/audit_log.json with filters by
   action/module/date.

Option 5 (CIMS B-001) is the natural next move — it's the
oldest backlog item and unblocks real-world CIMS data joins.
Option 7 (cash forecast) follows the same pattern this batch
established and would compress quickly.
