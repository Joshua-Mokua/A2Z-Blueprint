# A2Z MIS 360 — v10.192 Changelog

## RUNTIME FIXES — clear blocking errors after consolidated bundle extraction

**Release date:** 2026-05-06
**Audit score:** 159/159 gates = 100.0% PASS (unchanged from v10.191)

---

## Summary

This release does not add new standards or close new modules. It fixes
three classes of runtime errors that surfaced when the consolidated
v10.154→v10.191 bundle was extracted into the live Streamlit
environment:

1. `audit_log()` calls using a non-existent `user=` keyword argument
2. Pages calling `a2z_db.load_json(...)` without importing `a2z_db`
3. Module-arc cockpits dumping engine summaries as raw JSON instead
   of rendering proper UI

None of these changed any audit gates. The closure ratchets at
G150-G159 continue to lock the 5 closed modules (Treasury, AML/
Compliance, Legal, Resource Optimization, Strategy).

---

## Fix 1 — `audit_log()` keyword argument mismatch

### Symptom
```
TypeError: audit_log() got an unexpected keyword argument 'user'
File "pages/99_integration_cockpit.py", line 58, in <module>
    audit_log(
        "integration_cockpit_view",
        f"username={username}",
        user=ud)
```

### Root cause
The canonical signature in `utils/core_audit.py` is:
```python
def audit_log(action: str, username: str, detail: str = "",
              module: str = "", before: str = "", after: str = ""):
```
There is no `user=` parameter — `username` (positional) is the
correct argument. Three call sites in `pages/99_integration_cockpit.py`
used the wrong shape (lines 58, 444, 450).

### Fix
Rewrote all three call sites to pass `username` positionally:
```python
audit_log("integration_cockpit_view", username, f"username={username}")
audit_log("integration_cockpit_run_period", username, "...")
audit_log("integration_cockpit_run_period_error", username, "...")
```
Confirmed via `grep -rn "user=ud" pages/` that no other call sites
use the broken pattern.

### Files changed
- `pages/99_integration_cockpit.py`

---

## Fix 2 — Missing `a2z_db` import in 4 pages

### Symptom
```
NameError: name 'a2z_db' is not defined
File "pages/71_bid_bond.py", line 31, in _load
    raw = a2z_db.load_json(p) if p.exists() else []
```

### Root cause
Four pages call `a2z_db.load_json(...)` without importing it. The
canonical pattern (used by `pages/12_cascade.py` and others) is:
```python
from utils.db import db as a2z_db
```

### Affected pages
| Page | a2z_db usage sites |
|------|---------------------|
| `pages/69_consent.py`         | 2 |
| `pages/70_retailer_finance.py` | 2 |
| `pages/71_bid_bond.py`         | 2 |
| `pages/72_observability.py`   | 2 |

### Fix
Added the canonical import to all four pages, immediately after
`from utils.core_audit import audit_log`. No usage sites were
modified — only the missing import was added.

`pages/_shared.py` also references `a2z_db` but does so inside a
function with a local import (`from utils.db import db as _a2z_db`),
which is a deliberate bootstrap fallback pattern and was left alone.

### Verification
```
grep -rln "a2z_db" pages/ | xargs grep -L "from utils.db import.*as.*a2z_db"
# (returns no broken pages — all references are now satisfied)
```

---

## Fix 3 — Cockpit tabs rendering raw JSON instead of UI

### Symptom
The Resource Optimization cockpit's "Work Mode Declarations" tab
showed the engine summary as a collapsed JSON tree:
```
{
  "engine": "ENH-156 WorkModeDeclarationEngine",
  "n_declarations_total": 0,
  "n_active": 0,
  "by_status": {},
  ...
}
```
The other module cockpits exhibited the same pattern in tab content.

### Root cause
Cockpit tabs were calling `st.json(engine.board_summary())` directly,
which renders the dict as a debug-style collapsible tree. Functional,
but unreadable for an operator. Across the 5 closure cockpits:

| Cockpit | `st.json` calls |
|---------|------------------|
| `pages/15_strategy_arc_cockpit.py`         | 1 (cosmetic) |
| `pages/26_treasury_arc_cockpit.py`         | 13 |
| `pages/27_compliance_arc_cockpit.py`       | 9 |
| `pages/28_legal_arc_cockpit.py`            | 11 |
| `pages/29_resource_optimization_cockpit.py` | 7 |

### Fix
Created a shared rendering helper at `pages/_cockpit_render.py` that
exposes a single function `render_summary(dict)` and translates a
`board_summary()` shape into proper Streamlit UI:

- `engine` → identity caption
- Numeric scalars (counts, totals, percentages) → `st.metric` cards
  in rows of up to 4
- Dict-valued distributions (e.g. `by_status`, `bands_distribution`)
  → labelled dataframes with Category / Count / Share % columns
- List-valued fields → compact dataframes (first 20 rows)
- `regulatory_basis` → italic caption
- `deferrals` (dict or list) → captioned expander labelled
  "Honest deferrals" with bullet entries

Each closure cockpit now imports the shared helper through a
graceful try/except shim so an ImportError falls back to the
previous `st.json` behaviour rather than crashing.

```python
try:
    from pages._cockpit_render import render_summary as _render_summary
except ImportError:
    def _render_summary(summary, *, exclude=()):
        st.json(summary)
```

### Files changed
- `pages/_cockpit_render.py` (new — ~150 lines)
- `pages/15_strategy_arc_cockpit.py`         (1 import + 1 call site)
- `pages/26_treasury_arc_cockpit.py`         (1 import + 13 call sites)
- `pages/27_compliance_arc_cockpit.py`       (1 import + 9 call sites)
- `pages/28_legal_arc_cockpit.py`            (1 import + 11 call sites)
- `pages/29_resource_optimization_cockpit.py` (refactored to use shared helper)

After the fix:
```
pages/15_strategy_arc_cockpit.py:         0 raw st.json calls
pages/26_treasury_arc_cockpit.py:         0 raw st.json calls
pages/27_compliance_arc_cockpit.py:       0 raw st.json calls
pages/28_legal_arc_cockpit.py:            0 raw st.json calls
pages/29_resource_optimization_cockpit.py: 0 raw st.json calls
```

---

## Audit ratchet

```
v10.191 (entering this release): 159/159 = 100% PASS
v10.192 (this release):           159/159 = 100% PASS
                                  no new gates
```

This is a fix-only release. No new ratchets, no new closure ceremonies.
The existing G150-G159 closure protections remain in force and verify
that the cockpit refactor preserved the engine class imports they
require (G151, G153, G155, G157, G159 all check that all engine
classes are referenced in their cockpit pages).

---

## Files changed (consolidated)

```
pages/69_consent.py                          (1 line added — a2z_db import)
pages/70_retailer_finance.py                 (1 line added — a2z_db import)
pages/71_bid_bond.py                         (1 line added — a2z_db import)
pages/72_observability.py                    (1 line added — a2z_db import)
pages/99_integration_cockpit.py              (3 audit_log calls rewritten)
pages/_cockpit_render.py                     (new — ~150 lines)
pages/15_strategy_arc_cockpit.py             (1 import shim + 1 call site)
pages/26_treasury_arc_cockpit.py             (1 import shim + 13 call sites)
pages/27_compliance_arc_cockpit.py           (1 import shim + 9 call sites)
pages/28_legal_arc_cockpit.py                (1 import shim + 11 call sites)
pages/29_resource_optimization_cockpit.py    (refactored to share render)
CHANGELOG_v10.192.md                         (this file)
```

---

## How to apply

This zip contains only the changed files. Extract over a working
v10.191 tree:

```bash
unzip -o a2z_v10.192_runtime_fixes.zip
python scripts/audit.py        # should still report 159/159 PASS
streamlit run app.py           # all cockpits and previously-broken
                                # pages should load without errors
```

---

## Honest scope statement

This release fixes **three observed runtime errors plus a UX issue**.
It does not address:

- Performance characteristics of the renderer at large summary sizes
  (untested with summaries >100 numeric fields — the metric-card
  layout assumes board_summary outputs stay roughly the size we ship)
- Whether the rendered tables align with operator expectations for
  every specific engine — the helper makes a best-guess inference
  from the dict shape, but module-specific custom tabs (where
  cockpits already render explicit metrics, not just summaries)
  remain unchanged
- The 88 spec-only standards that have no engines, the platform-
  level deferrals (PG migration, FATCA/CRS XML, CBK reports), or
  any module activations
- The v10.175 changelog gap from the consolidated bundle

These remain open and were not part of this release's scope.
