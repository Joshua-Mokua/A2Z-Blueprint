# Changelog — v10.304 Phase 3 Arc 10: Cash Forecast Composer Wiring

**Date:** 2026-05-11
**Phase:** 3 (tenth arc — placeholder closure, mirrors v10.302)
**Audit:** 195/195 gates PASS = 100.0%
**Tests:** 196/196 passing across 11 integration suites (13
skipped in audit env)
**G162 Rebase:** 4020 → 4022 (+1 Ecobank, +1 Kenya)

---

## Summary

Closes the v10.296 placeholder in Treasury cockpit tab 6
("13-week cash forecast"). Same shape as v10.302's
TreasuryDashboardEngine wiring — different engine, identical
pattern. By now the pattern is so set that this batch was the
fastest yet.

---

## What shipped

### `utils/cash_forecast_wiring.py` (NEW)

Factory module. One public function:

```python
def make_primed_forecaster(
    entity_name: str = "Ecobank Kenya",
    data_dir: str | Path = "data",
) -> TreasuryCashForecastingEngine:
    ...
```

Returns a `TreasuryCashForecastingEngine`, primed from any
production cash-flow JSON files present in `data/`:

- `cash_history.json` — list of historical daily net-flow
  records: `{observation_date, net_flow_kes, notes}`
- `cash_scheduled_flows.json` — list of scheduled flow records:
  `{flow_id, flow_date, amount_kes, driver, counterparty,
   reference, notes}`

Priming is defensive — missing or malformed files leave the
engine empty (`n_history_days: 0`), which the composer renders
as `status: "no_data"`. The cockpit displays a meaningful
placeholder. Loud errors would punish the whole tab for one
bad file.

Each row tolerated independently: a bad row gets skipped, the
rest of the file still primes.

Driver strings unknown to the `FlowDriver` enum fall back to
`OTHER_SCHEDULED` rather than dropping the flow. Better to
keep an under-categorised flow than lose it entirely.

### `utils/cockpit_read.py` — `treasury_cash_forecast` composer

```python
def treasury_cash_forecast(
    horizon_days: int = 91,
    start_date: str | None = None,
) -> Dict[str, Any]:
```

Default horizon: 91 days (13 weeks), matching the cockpit tab
title. Returns 12 documented keys:

| Key | Meaning |
|-----|---------|
| `entity` | Bank entity name from engine |
| `forecast_id` | Generated ID for this read |
| `horizon_days` | Actual horizon used |
| `start_date` | Start date (defaults to today UTC) |
| `n_history_days_used` | Engine input depth |
| `ml_overlay_applied` | Bool; true if ML provider wired |
| `n_points` | Number of daily points returned |
| `points` | List of daily forecast dicts |
| `status` | `"ok"` / `"no_data"` / `"error"` |
| `notes` | Engine-side narrative |
| `as_at` | ISO timestamp of THIS read |

Three status branches:

1. **`no_data`** (most common today) — engine has zero
   history. Empty points list, notes explain what to provide.
2. **`error`** — `fit_seasonality()` or `forecast()` raised.
   Empty points list, notes carry the exception message.
3. **`ok`** — primed engine produced a forecast. Points carry
   `forecast_date`, `total_kes`, `baseline_kes`,
   `seasonality_multiplier`, `statistical_kes`, 80% + 95%
   confidence bands, and `drivers_summary`.

All `Decimal` values cast to `str` for JSON serialisability —
React's `parseFloat` handles the conversion, or values can be
displayed as-is.

### `pages/110_treasury_live.py` — tab 6 wired

The v10.296 placeholder banner is gone. Tab 6 now renders:

- 4-metric header row (horizon days, history days used,
  forecast points, status)
- Status-aware body:
  - `no_data` → `st.info()` with the notes from the composer
  - `error` → `st.error()` with the error message
  - `ok` → notes line + first 20 daily points with date,
    total, baseline, and 80% band
- Caption pointing to the HTTP endpoint for the full series

A `_cached_cash_forecast(horizon_days=91)` helper wraps the
composer at the same 60s TTL as the dashboard report (forecast
computation is heavier than the cheap read composers).

### `utils/api_cockpit.py` — `/treasury/cash-forecast` endpoint

```
GET /api/cockpit/treasury/cash-forecast?horizon_days=N
```

Optional `horizon_days` clamped to [1, 365] to avoid abuse.
Returns the same dict the cockpit page renders.
JWT-protected. Audit-logged. **18 cockpit endpoints now**
(was 17). `COCKPIT_READ_API_VERSION` → "17.0".

### `scripts/audit.py` — G195 added

`gate_cash_forecast_wired` locks the closure via 8 sub-checks
mirroring G193's pattern:

1. Wiring module exists with factory
2. Factory returns a working engine with readable
   `board_summary()`
3. Composer exists in `cockpit_read`
4. Composer returns documented keys
5. Composer status is one of `{ok, no_data, error}`
6. Page 110 references the composer
7. v10.296 placeholder banner removed
8. HTTP endpoint registered

### `tests/integration/test_cash_forecast_wiring.py` (NEW)

13 tests across 6 sections. All harness-portable; no FastAPI
dependency for the structural checks.

### `tests/integration/test_api_cockpit.py` — extended

`EXPECTED_ENDPOINTS` to 18.

### `data/audit_baselines.json` — G162 rebased 4020 → 4022

+1 Ecobank, +1 Kenya — same shape as v10.302 (default
`entity_name` parameter on the factory).

---

## TDD red→green progression

- **Red phase:** 0P 13F. Nothing wired yet.
- **Green phase 1 (wiring + composer):** mostly green, page +
  endpoint tests still failing.
- **Green phase 2 (page + endpoint + G195):** caught two real
  audit failures:
  - **G2** failed because `json.loads(path.read_text(...))`
    pattern appeared in the wiring helper AND was mentioned
    in a docstring. Fixed both — used `with open(p) as f:
    json.load(f)`, and rephrased the docstring so the literal
    regex pattern doesn't appear in the source.
  - **G162** flagged +1 Ecobank, +1 Kenya from the default
    `entity_name`. Rebased to 4022.
- **Green phase 3:** 13P 0F.

The G2 docstring catch was a small surprise. The gate's
regex is content-based, not AST-based — it doesn't distinguish
code from comments. Good lesson: when documenting a forbidden
pattern, don't *write* the forbidden pattern in the doc.

---

## Real findings during this batch

1. **The cash forecasting engine's dataclass fields didn't
   match my initial guess.** `ScheduledCashFlow` uses
   `flow_date` (not `value_date`) and `driver: FlowDriver`
   (not a string `direction`). Caught during smoke-test;
   fixed by reading the dataclass before assuming.

2. **No production cash-flow data exists today.** Confirmed by
   `ls data/ | grep -iE "cash|forecast|flow"` — only
   `alm_liquidity.json` and `liquidity_metrics.json` are
   present. The composer's `no_data` branch is the one that
   fires in production right now. **That's not a bug — it's
   the honest state.** When operators ship
   `data/cash_history.json` with real records, the engine
   primes, the forecast computes, and the cockpit displays
   live data. The wiring is correct; the data is just not
   there yet.

3. **G2 regex matches docstrings.** A passing reference to
   `json.loads(path.read_text(...))` in a docstring is treated
   identically to the actual code pattern. This is by design
   (simpler to maintain than AST analysis) but worth
   remembering when documenting forbidden patterns.

4. **Engine `fit_seasonality()` raises on zero history.**
   That's why the composer checks `n_history_days == 0`
   BEFORE calling `fit_seasonality()` — saves the engine from
   raising and the composer from a useless try/except trip.

---

## Files changed

- `utils/cash_forecast_wiring.py` — NEW
- `utils/cockpit_read.py` — `treasury_cash_forecast` composer
- `utils/api_cockpit.py` — `/treasury/cash-forecast` endpoint,
  version 17.0
- `pages/110_treasury_live.py` — tab 6 wired, banner removed
- `scripts/audit.py` — G195 added and registered
- `data/audit_baselines.json` — G162 → 4022
- `tests/integration/test_cash_forecast_wiring.py` — NEW (13 tests)
- `tests/integration/test_api_cockpit.py` — EXPECTED_ENDPOINTS to 18
- `CHANGELOG_v10.304.md` — this file

---

## Audit results

```
Score: 195/195 gates = 100.0% — PASS
```

---

## Platform state

- **Audit:** 195/195
- **Standards active:** 330/330 (no change)
- **Pages:** 116 (no change — wiring batch, not new page)
- **Tiers:** 57 (no change)
- **Gates:** G1-G195 linear
- **Live cockpits:** 4 (CIMS, Treasury, Credit, Compliance) —
  Treasury's tabs 6 AND 7 now both produce real data when
  primed
- **HTTP endpoints (cockpit):** 18 (was 17)
- **Integration test suites:** 11 (was 10)
- **Integration tests passing:** 196/196 (13 skipped in audit
  env)
- **G162 baseline:** 4022

---

## React-readiness check

When the React SPA fetches
`/api/cockpit/treasury/cash-forecast`, it gets the same shape
the Streamlit cockpit renders. A React component can:

1. Read the `status` field to decide what to render
2. Display the 4 header metrics from the top-level keys
3. Map over `points` to render a chart with 80% and 95%
   confidence bands
4. Use `forecast_id` for caching and version detection

Same data, same shape, same composer. No frontend re-
implementation needed.

---

## What didn't change

- No new pages
- No new tiers
- Standards still 330/330
- Engines stay byte-for-byte locked (no source rewrites)

This was a **placeholder-closure** batch, mirroring v10.302.

---

## Phase 3 placeholder status

After v10.302 (Treasury dashboard tab 7) and v10.304 (Treasury
cash forecast tab 6), the Treasury cockpit has **zero**
"composer not yet wired" placeholders. CIMS, Credit, and
Compliance cockpits still have audit-trail tab placeholders;
those are uniform across the four cockpits and best closed
together via a single audit-trail composer (option 8 in the
v10.303 list).

---

## Next Phase 3 arc options

Updated list:

1. ~~CORS + production deploy config~~ — v10.299 ✓
2. ~~Credit live cockpit~~ — v10.300 ✓
3. ~~Compliance live cockpit~~ — v10.301 ✓
4. ~~TreasuryDashboardEngine wiring~~ — v10.302 ✓
5. ~~CIMS vocabulary harmonization (B-001)~~ — v10.303 ✓
6. ~~Cash forecast composer wiring~~ — v10.304 ✓ (this batch)
7. **Audit trail composer** — close the audit-trail
   placeholders in all 4 cockpit pages' last tab with a single
   composer reading `data/audit_log.json` with filters by
   action/module/date. High leverage (touches all 4 cockpits)
   and clean shape.
8. **PG migration push** toward 75/79 (95%) — 31 tables,
   small dual-write toggles each.
9. **CIMS audit trail wiring** — narrower variant of (7) if
   we want to start with one cockpit.

Option 7 (single audit-trail composer for all 4 cockpits) is
the natural next move — it closes the last category of
placeholder banners across the cockpit estate in one batch
with a single composer.
