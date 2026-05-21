# Changelog — v10.352 Smoke Test Enhancement (Static AST checks)

**Date:** 2026-05-12
**Phase:** 4 (thirty-seventh arc — smoke gap closure)
**Audit:** 238/238 gates PASS = 100.0%
**Tests:** 15 new in `test_v10352_static_checks.py`, all passing
**Page smoke:** 123/123 PASS at 100% + **0 static AST findings**
**Verifier:** 104/104 checks pass on a clean extract
**G162 Baseline:** 4022 (46 consecutive zero-drift batches)

---

## Your ask

> "v10.352 — Smoke test enhancement"

The last two reports (v10.350 STREAMLIT_AVAILABLE NameError, v10.351 get_stock_snapshot UnboundLocalError) exposed a structural gap: the smoke test only checks module-load integrity. Bugs inside function bodies that fire only when specific code paths execute slip through. This batch closes that gap with static AST analysis — deterministic, zero runtime cost, no need to mock streamlit + session state + data fixtures.

## Honest framing of scope

**What this batch does:** catches the two exact bug classes that broke localhost in v10.350 + v10.351, by analyzing the AST of every utility and page file. Found and fixed one additional latent NameError (`DATA_DIR` typo in `actuals_engine.py`) in the process.

**What this batch does NOT do:** catch the *other* bug classes from v10.350 — `Decimal/float` TypeError, `campaign_id` KeyError, `phase` KeyError. Those need runtime data fixtures + actual rendering execution, or much more sophisticated type inference. Static AST analysis can't infer that a dict might lack `campaign_id`. A future batch could layer dynamic execution onto the smoke test (calling render functions with synthetic actors + mocked data), but that's multi-batch work and out of scope here.

The static checks cover the largest attack surface revealed by the last two reports. Dynamic execution is incremental work for diminishing returns.

## What v10.352 delivered

### `utils/static_check.py` — AST-based analyzer (411 lines)

Two detectors, both conservative to suppress false positives:

| Detector | Catches | Heuristic |
|---|---|---|
| `find_undefined_caps_constants` | v10.350 `STREAMLIT_AVAILABLE` class | ALL_CAPS_NAMES used in function bodies not resolvable through own scope, enclosing function scopes (closure), class body (for default args), module top, or builtins |
| `find_unbound_local_imports` | v10.351 `get_stock_snapshot` class | Local imports that shadow a module-top name AND have a USE before the EARLIEST local binding line. Use-after-bind is wasteful but not a bug — skipped |

False-positive suppression refined through three iterations:

1. **Walk enclosing scopes** — closures (inner function reading outer function's local) are valid, not flagged. Fixed `DATA` in `propositions_hub_render` and `REPO_ROOT` in `platform_hub_render`.

2. **Class-body scope for default args** — `def method(self, x: int = DEFAULT_X)` resolves `DEFAULT_X` in class scope, not function scope. Fixed `DEFAULT_TOP_N` in `revenue_dashboard_metrics`.

3. **Only `ctx=Store` Names count as bindings** — `st.session_state["x"] = y` is an `Assign` with subscript target. The `Name('st')` inside has `ctx=Load` (attribute access read), not `ctx=Store`. Don't treat it as binding `st`. Fixed 7 false positives across the unified hubs.

4. **Use earliest binding for use-before-bind check** — if a function has two local imports of the same name at lines 343 and 405, only the 343 import matters. Uses between them are fine because 343 already made the name local. Fixed `_dt`, `count_by`, `pd` false positives.

### Real bug found and fixed: `DATA_DIR` typo

The analyzer surfaced one latent bug at `utils/actuals_engine.py:764, 766` in `_add_initiative_kpis()`:

```python
# Before
try:
    ra_file = DATA_DIR.parent / "data" / "recovery_actuals.json"
    if not ra_file.exists():
        ra_file = DATA_DIR / "recovery_actuals.json"
    ...
```

`DATA_DIR` was never defined anywhere in the module — typo for `data_dir`. Latent NameError that fires when DRS recovery actuals injection runs. The function uses lowercase `data_dir` everywhere else; uppercase was a code-completion mistake at some point. Fixed by resolving the data directory via `get_cbs_paths()` like other functions in the module.

```python
# After
try:
    # v10.352 — DATA_DIR was undefined here (latent NameError). Resolve
    # the data directory via the same helper other functions in this
    # module use.
    _cbs_dir, _data_dir = get_cbs_paths()
    ra_file = _data_dir.parent / "data" / "recovery_actuals.json"
    if not ra_file.exists():
        ra_file = _data_dir / "recovery_actuals.json"
```

### Integration with smoke test

`utils/page_smoke.py` extended. `smoke_test_all()` now returns two new keys:

- `static_findings: List[dict]` — per-finding details (file, function, line, name, category)
- `static_clean: bool` — convenience flag

`format_summary()` displays a "static: clean" line when zero findings, or a list of up to 15 findings when present.

### New audit gate G238

`gate_static_function_checks` runs the analyzer across 549 files (425 utils + 123 numbered pages) and fails on any finding. Audit cost: ~0.4s. Locks the v10.350 + v10.351 bug classes from regressing — if any future batch reintroduces them, G238 catches it before delivery.

### 15 tests across 5 sections

| Section | Tests | What they cover |
|---|---|---|
| 1 — Synthetic CLASS 1 | 3 | Recreates v10.350 STREAMLIT_AVAILABLE pattern, generic undefined caps, and the must-not-flag case (resolvable via module top) |
| 2 — Synthetic CLASS 2 | 3 | Recreates v10.351 get_stock_snapshot pattern, local-import-before-use (not flagged), and no-shadowing case |
| 3 — False positive suppression | 4 | Class attribute in default arg, closure access, subscript assign, redundant subsequent local imports |
| 4 — Real codebase clean | 2 | Current codebase has 0 findings; DATA_DIR typo fixed |
| 5 — G238 + integration | 3 | Gate passes, registered in GATES list, smoke_test_all returns static fields |

## Files changed

| File | Change |
|---|---|
| `utils/static_check.py` | NEW — AST analyzer with two detectors |
| `utils/page_smoke.py` | Extended — `smoke_test_all()` runs static checks; `format_summary()` displays them |
| `utils/actuals_engine.py` | DATA_DIR typo fix in `_add_initiative_kpis` |
| `scripts/audit.py` | NEW gate G238 `gate_static_function_checks` |
| `scripts/verify_local_state.py` | Extended to 104 checks across v10.336-v10.352 |
| `tests/integration/test_v10352_static_checks.py` | NEW — 15 tests |

## Verified outcome

| Metric | Before → After v10.352 |
|---|---|
| Audit gates | 237 → **238** (G238 added) |
| Page smoke | 123/123 PASS + **0 static findings** |
| Tests | +15 in v10.352 file, all passing |
| Verifier | 100 → **104 checks** |
| Latent NameError bugs found | 1 (DATA_DIR — fixed) |
| G162 baseline | 4022 (46 consecutive zero-drift batches) |
| Smoke-test coverage | module-load only → module-load + AST function-body checks |

## What's actually catchable now

Run the smoke test from the repo root:

```bash
python -c "from utils.page_smoke import smoke_test_all, format_summary; print(format_summary(smoke_test_all()))"
```

Output now includes a static-clean line:

```
Page smoke test — 123 pages
  PASS:    123
  FAIL:    0
  SKIP:    0
  rate:    100.0%
  static:  clean (0 findings)
```

If a future batch reintroduces a `STREAMLIT_AVAILABLE`-style undefined constant OR a `get_stock_snapshot`-style shadowing local import, **the static check fires immediately** — both in the smoke report and as G238 audit failure. No more "fix lands, ships green, blows up on Joshua's localhost a day later" for these two classes.

## On your end

1. Close Streamlit
2. Delete any leftover subfolder extracts
3. Extract `a2z_v10352_session_cumulative.zip` flat into the A2Z workspace, overwriting everything
4. Run `python scripts\verify_local_state.py` → expect **ALL 104 CHECKS PASSED**
5. Run `python scripts\audit.py` → expect **238/238 PASS**
6. Restart Streamlit
7. (Optional) Run the static checker on demand:
   ```python
   from utils.static_check import static_check_paths, format_findings
   from pathlib import Path
   paths = sorted(Path("utils").glob("*.py")) + sorted(Path("pages").glob("[0-9]*.py"))
   print(format_findings(static_check_paths(paths)))
   ```
   → expect "(no findings — static checks clean)"

The `_add_initiative_kpis` function in `utils/actuals_engine.py` should no longer crash when DRS recovery actuals are loaded (the latent DATA_DIR NameError is fixed).

## Suggested direction for v10.353

The smoke gap is closed for the two proven classes. Natural next steps:

1. **You verify v10.352 on localhost first** ← recommended
2. **v10.353 — Dynamic render-function smoke** — actually call each `render_*()` function with a synthetic actor + mocked data. Heavy mock surface needed (streamlit st.*, st.session_state, st.cache_data, st.tabs, etc.), data fixtures for engines that read JSON files, stubs for engines that connect externally. Would catch KeyError / TypeError / AttributeError bugs that need execution to surface. Multi-batch undertaking.
3. **v10.353 — Return to original roadmap** — partnerships P&L, B-027 tail, Strategic Initiative engine
4. **v10.353 — Address documented divergences** — `strategic_initiatives.rag_status` Title-vs-UPPER, `kpi.direction` short-vs-long
5. **v10.353 — Expand static checks to more patterns** — e.g. detect calls to functions that don't exist in the imported module, detect type-confusion patterns (Decimal/float division), detect dict accesses that might miss keys. Each pattern is a separate detector function.

My honest position: option 1 (verify locally first), then choose between (2) — keep closing the smoke gap, or (3)/(4)/(5) — return to feature work. The static analyzer is the highest-precision low-cost addition; dynamic execution is real engineering with diminishing returns relative to going back to feature delivery.

Which way?
