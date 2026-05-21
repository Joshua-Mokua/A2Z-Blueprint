# BSC & Target Cascade — Architecture

**Module key:** `bsc_cascade` · **Organ role:** Brain Intelligence, Direction & Decision Flow
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 100.0%

Module architecture per the doctrine Phase 1 Technical Health review. Identifies pages, engines, boundaries, and dependencies.

---

## Pages (2)

- `1_perform.py` — 1939 LOC
- `12_cascade.py` — 5383 LOC

## Engines (11)

- `utils/bsc_engine.py` — 693 LOC · (undocumented)
- `utils/bsc_audit_engine.py` — 704 LOC · (undocumented)
- `utils/bsc_admin_panel.py` — 1132 LOC · (undocumented)
- `utils/bsc_cascade_linkage_engine.py` — 392 LOC · (undocumented)
- `utils/bsc_completeness_engine.py` — 688 LOC · (undocumented)
- `utils/bsc_library_register_engine.py` — 527 LOC · (undocumented)
- `utils/bsc_pillar_normalize_engine.py` — 400 LOC · (undocumented)
- `utils/bsc_score_computation.py` — 555 LOC · (undocumented)
- `utils/bsc_universal_contract.py` — 339 LOC · (undocumented)
- `utils/cascade_bsc_360_engine.py` — 778 LOC · (undocumented)
- `utils/api_cascade.py` — 868 LOC · (undocumented)

## Module boundaries

- **Organ role**: Brain Intelligence, Direction & Decision Flow
- **Cross-organ links**: credit, hr, admin

## Architecture style

- Streamlit multipage app with API-first engines under `utils/`
- PostgreSQL via `utils/db` adapter where available
- React-readiness target: zero `unsafe_allow_html` excess + minimal raw HTML
- BSC integration via `_bsc_trigger()` hooks
- RBAC via `require_access()` gates
