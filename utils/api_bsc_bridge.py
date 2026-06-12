"""utils/api_bsc_bridge.py — shared best-effort BSC recompute bridge.

Phase P Batch P1 (2026-06-12).

WHY THIS EXISTS
---------------
`update_bsc_from_modules(username)` in utils/core.py is the canonical
operational-modules -> BSC actuals bridge. In the Streamlit app, every
module page calls it after a state-changing action. In the React/FastAPI
rebuild only the Pipeline routes preserved that wiring (via the local
`emit_bsc_trigger` in api_pipeline_mutations.py); the LMS and Credit-Admin
routes shipped BSC-blind.

This module is the neutral, cross-module home for that trigger so any
route can recompute BSC without importing a sibling domain's module (LMS
importing from pipeline would be a layering smell). The Pipeline route's
local copy is a future consolidation target — migrating it to import from
here is a pure import swap, deliberately deferred to keep this batch's
blast radius at zero on the G381-protected pipeline path.

SEMANTICS (mirrors the proven pipeline pattern)
-----------------------------------------------
- Best-effort: a BSC recompute failure must NEVER roll back or fail an
  already-successful mutation. The recompute is a side effect, not part
  of the transactional contract.
- Returns True on success, False on any swallowed failure. Callers may
  log the boolean but must not branch request success on it.

ACTUALS-SOURCE PRECEDENCE (documented decision, P1)
---------------------------------------------------
Two actuals sources coexist:
  1. CBS-derived (utils/actuals_engine.py, from cbs_data/) — the
     realized-financial source of truth (deposits, loan book, NPL).
  2. Module-derived (update_bsc_from_modules, from module JSON) —
     operational / activity KPIs (e.g. K041, K060-K071).
RULE: for any KPI present in BOTH sources, the CBS-derived value WINS
(it is the core-banking ledger truth; module activity is a leading
indicator only). update_bsc_from_modules must therefore only write the
KPIs it owns and must not overwrite CBS-derived realized financials.
This batch does not change that behaviour; it records the rule so the
CEO Dashboard (Phase P4) never sums conflicting values.
"""

from __future__ import annotations


def emit_bsc_trigger(username: str) -> bool:
    """Recompute the caller's BSC actuals from operational modules.

    Best-effort. See module docstring for semantics and precedence.
    """
    if not username:
        return False
    try:
        from utils.core import update_bsc_from_modules
        update_bsc_from_modules(username)
        return True
    except Exception:
        # Best-effort: never let a BSC recompute failure break a
        # successful mutation. Mirrors the Streamlit pages' pattern
        # (`except Exception: pass`) and the pipeline route pattern.
        return False
