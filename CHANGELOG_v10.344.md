# Changelog — v10.344 Page Smoke-Test Suite (Option C)

**Date:** 2026-05-12
**Phase:** 4 (twenty-ninth arc — Option C of the harmonization plan)
**Audit:** 231/231 gates PASS = 100.0%
**Tests:** 12 new in `test_v10344_page_smoke.py`, all passing
**G162 Baseline:** 4022 — 38 consecutive zero-drift batches

---

## Your ask

> "v10.344 — Move to Option C"

The page smoke-test suite. Every Streamlit page imports headlessly with a mock streamlit module; the audit run fails if any page crashes. This is the structural answer to your v10.341 problem: "the audit gates pass but localhost crashes." After v10.344, the audit run also imports every page, so the kind of bug that broke `12_cascade.py:782` gets caught at audit time, before shipping.

## What v10.344 shipped

### Three new modules

| Module | Lines | Purpose |
|---|---|---|
| `tests/helpers/streamlit_mock.py` | 220 | Headless Streamlit mock — proxies every `st.*` call, supplies session_state defaults, mocks viz libraries (plotly/altair/pydeck/folium) so page LOGIC is what's tested |
| `utils/page_smoke.py` | 175 | Smoke-test engine — `smoke_test_all()` walks `pages/`, imports each headlessly, classifies PASS/FAIL/SKIP, produces structured + human-readable reports |
| `tests/integration/test_v10344_page_smoke.py` | 180 | 12 tests across 4 sections — mock mechanics, engine API, full-run results, audit gate |

### Audit gate G231 — page_smoke_test

Runs `smoke_test_all()` every audit cycle. Fails the gate if:
- ANY page crashes with KeyError / AttributeError / NameError / TypeError / ImportError at module top
- Pass rate drops below 95%

Current state: **118/118 pages PASS at 100.0%** (some pages are filtered as helpers — underscore-prefixed).

### Classification logic

PASS — the gate's true target:
- Page imported cleanly (no exception)
- Page hit `st.stop()` during import (auth/permission gating — got far enough to call stop)
- Page hit `SystemExit` (clean exit, same logic)

FAIL — what the gate catches:
- `KeyError` / `AttributeError` / `TypeError` / `NameError` / `ImportError`
- The v10.341 crash class — accessing a dict key the data doesn't have, calling `.get()` on a float, subscripting before checking type

### Mock-design discipline

The `_MockProxy` class supports:
- Any attribute access → returns another proxy (chainable)
- Any call → returns proxy
- Coercion to `int(0)`, `float(0.0)`, `str("")`, `bool(False)` — so code like `int(st.slider(...))` doesn't false-fail
- Iteration → empty
- Subscript → another proxy
- Arithmetic / comparison → returns proxy or False

This means widget-value patterns the codebase uses (e.g. `within = st.slider(...); int(within)` in `97_it_digital_pt2.py`) work in the mock without false-positive failures.

`session_state` is a dict-subclass with attribute access, pre-populated with sensible defaults (user, logged_in, role) so auth-gating checks pass with the mock user as MD.

Viz library mocks (plotly, altair, pydeck, folium) are installed alongside streamlit — pages that do `import plotly.express as px` at module top now work in the smoke run even though those libs aren't in the sandbox. The test is about LOGIC, not third-party availability.

### Real bug surfaced and resolved

While building the smoke engine, the first pass found `97_it_digital_pt2.py` failing with `TypeError: int() argument must be a string, a bytes-like object or a real number, not '_MockProxy'`. Investigation: the page calls `int(within)` where `within` is from `st.slider`. Not a real page bug — a mock-completeness issue. Added `__int__`, `__float__`, `__index__` to `_MockProxy`. After the fix: 118/118 PASS.

## What v10.344 deliberately did NOT do

- **Did not patch any page.** The smoke test surfaces failures; fixing them is a separate decision per-page. All 118 pages currently pass, so nothing needs fixing.
- **Did not test runtime behavior.** Smoke is module-load only. Pages may still have runtime bugs that only surface during widget interaction — those would need a different test layer.
- **Did not enforce stricter pass threshold.** 95% gives headroom for future legitimately-untestable pages (e.g. ones that depend on real network calls). Today it's 100%, but the gate doesn't force-fail if one page legitimately can't be smoked.

## Why this matters

The v10.341 errors you reported on localhost had a common signature: page-level code accessing dict keys without `.get()`, on data shapes that drifted. The audit gates passed because they checked engine correctness, not page consumption. v10.342 + v10.343 locked the data shapes (Option D). v10.344 closes the loop on the consumer side — even if a page's expectations drift, the smoke run catches it before shipping.

If the v10.341 fixes are reverted (deleted, somehow), G231 fails the audit immediately. The 4 pages that crashed your localhost are explicitly checked by `test_v10344_v10341_crash_pages_now_pass`.

## Verified outcome

| Metric | Before → After v10.344 |
|---|---|
| Audit gates | 230 → **231** (G231 added) |
| Page smoke coverage | 0 → **118 pages (100% PASS)** |
| New modules | +3 (mock, engine, tests) |
| New tests | +12 |
| G162 baseline | 4022 (38 consecutive zero-drift batches) |
| Pattern R | NEW — distribution zips must be flat layout (no parent folder wrapper) |

## Pattern R (already in v10.343 brief but formalised here)

**Distribution zips must contain the file tree at the top level, never wrapped in a parent folder.**

Build: `cd staging_dir && zip -qr ../release.zip .` (not `zip -qr release.zip staging_dir/`)

Verify with `unzip -l release.zip | head -10` — first entries should be `data/`, `pages/`, `utils/`, `scripts/`, not `staging_dir/data/`. This avoids the v10.342 delivery gap where Windows extraction created subfolders inside `a2z\` instead of overwriting.

## Files changed

| File | Change |
|---|---|
| `tests/helpers/streamlit_mock.py` | NEW — 220 lines, full mock surface |
| `tests/helpers/__init__.py` | NEW — empty (package marker) |
| `utils/page_smoke.py` | NEW — 175 lines, smoke engine |
| `tests/integration/test_v10344_page_smoke.py` | NEW — 12 tests |
| `scripts/audit.py` | `gate_page_smoke_test` + G231 registration |

## Backlog status

| ID | Status |
|---|---|
| B-009 – B-018 | Open |
| B-027 (tail) | Mostly closed |
| B-028, B-029 | Open |
| B-030, B-034 | Closed |
| B-031, B-032, B-033, B-035, B-036, B-037, B-038 | Open |
| B-039 (page schema drift) | **Effectively closed** — G231 catches the entire class going forward |
| B-040, B-041 | Open |
| B-042 (Option E — kpi.direction consolidation) | Documented |
| B-043 (Option E — rag_status case consolidation) | Documented |

## What's next — the bigger arc

D and C are done. The harmonization plan was **D → C → E**, and Option E is where the front end starts projecting the backend as you originally asked.

E candidates (each is its own multi-batch arc):

1. **Finance hub consolidation** — Merge `9_sbu`, `114_sbu_drilldown`, `10_opex`, `52_mgmt_accounts` into one Finance module with tabs
2. **Live cockpits navigator** — Merge the 4 `*_live` cockpits (`110_treasury_live`, `111_credit_live`, `112_compliance_live`, `109_cims_live`) into one Live Cockpits page
3. **Propositions module** — Merge `27_propositions` + `92_propositions_workbench`
4. **Competitor module** — Merge `11_competitor` + `93_competitor_intelligence`
5. **Platform/IT consolidation** — Merge `91_systems_view`, `96_it_digital_pt1`, `97_it_digital_pt2`, `98_platform_health`

Each follows the v10.343 strategic-initiatives discipline:
- Feature inventory first (every tab, every metric, every action listed and confirmed with you)
- Feature parity in the consolidated module
- Old pages stay as thin redirect stubs until you've used the consolidated module on localhost
- Removed only after you confirm

Direction for v10.345:

1. **v10.345 — Option E sub-batch 1 (Finance hub)** — most-visible consolidation, would let you see harmonization concretely on localhost
2. **v10.345 — Option E sub-batch 1 (Live cockpits)** — smaller scope, lower risk for the first E batch
3. **v10.345 — Wire `validate_before_save` into more producers (B-041)** — close out the last D work first
4. **v10.345 — Continue original roadmap** — partnerships P&L / Strategic Initiative engine / B-027 tail
5. **v10.345 — Verify v10.344 on localhost first** — recommended

My honest recommendation: **option 5 — verify on localhost first.** v10.344 adds a runtime check; better to confirm the smoke suite catches things on YOUR end (not just mine) before starting the E arc. If verify_local_state passes 39/39 on your machine, we begin E.

Which way?
