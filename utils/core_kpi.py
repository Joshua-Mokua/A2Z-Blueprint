"""utils.core_kpi — KPI library, role mappings, and BSC scoring helpers.

This module is currently a SHIM that re-exports symbols from utils.core.
The pattern matches v5.21's introduction of utils.core_audit:

    1. v5.28 (THIS RELEASE): introduce shim, migrate first pilot pages
    2. v5.29-v5.31: migrate the rest of the callers
    3. v5.32 (or wherever): physically move implementations from
       utils/core.py into this file, leaving constants behind in core
    4. v5.33+: delete the reverse-export back-compat block in core.py
       once 100% adoption is reached

Until step 3, the implementations still live in utils/core.py and this
module is a pure re-export shim. Pages and other callers should prefer:

    NEW (preferred): from utils.core_kpi import get_kpi_library
    OLD (legacy):    from utils.core import get_kpi_library

Both work identically right now (`is`-identity preserved).

Symbols exposed:

    KPI library config:
        KPI_LIBRARY_FILE       — path to data/kpi_library.json
        DEFAULT_KPI_LIBRARY    — fallback library if file is missing
        DEFAULT_ROLE_KPIS      — fallback role→KPI mapping
        get_kpi_library()      — load (or seed) the library
        save_kpi_library(lib)  — persist
        get_active_kpis()      — KPIs with active=True
        get_role_kpis(role)    — KPI IDs for a given role
        get_pillar_weights()   — {pillar: weight} from library config

    BSC scoring:
        get_scoring_scale()        — thresholds from org_config
        bsc_score_from_pct(pct)    — convert achievement % → 1-5 score
        get_performance_bands()    — band defs from org_config
        score_to_band(score)       — map a score → band dict

The G14 audit gate tracks adoption percentage across pages. The
test suite (tests/test_core_split.py) verifies that every symbol in
this module's __all__ is the SAME object as utils.core's, via
`is`-identity assertions.
"""
from __future__ import annotations

# Re-export the KPI cluster from utils.core. This is a pure shim.
# When v5.32 (or wherever) does the physical move, these `from utils.core
# import` lines will be replaced by actual function/class definitions
# physically homed in this file, and core.py will get a reverse-export
# block at the bottom (using PEP 562 __getattr__, see v5.25 lessons).
from utils.core import (
    # KPI library config
    KPI_LIBRARY_FILE,
    DEFAULT_KPI_LIBRARY,
    DEFAULT_ROLE_KPIS,
    get_kpi_library,
    save_kpi_library,
    get_active_kpis,
    get_role_kpis,
    get_pillar_weights,
    # BSC scoring
    get_scoring_scale,
    bsc_score_from_pct,
    get_performance_bands,
    score_to_band,
)

__all__ = [
    "KPI_LIBRARY_FILE",
    "DEFAULT_KPI_LIBRARY",
    "DEFAULT_ROLE_KPIS",
    "get_kpi_library",
    "save_kpi_library",
    "get_active_kpis",
    "get_role_kpis",
    "get_pillar_weights",
    "get_scoring_scale",
    "bsc_score_from_pct",
    "get_performance_bands",
    "score_to_band",
]
