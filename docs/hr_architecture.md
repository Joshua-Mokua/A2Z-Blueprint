# HR Module — Architecture

**Module key:** `hr` · **Organ role:** Human Capital & Regenerative System
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 88.7%

Module architecture per the doctrine Phase 1 Technical Health review. Identifies pages, engines, boundaries, and dependencies.

---

## Pages (8)

- `2_people.py` — 4034 LOC
- `42_lms.py` — 199 LOC
- `43_pip.py` — 244 LOC
- `58_workforce.py` — 86 LOC
- `60_disciplinary.py` — 110 LOC
- `79_staff_onboarding.py` — 305 LOC
- `80_staff_exit.py` — 273 LOC
- `81_chief_hr_centre.py` — 732 LOC

## Engines (10)

- `utils/peer_learning.py` — 982 LOC · (undocumented)
- `utils/coaching_intelligence.py` — 814 LOC · (undocumented)
- `utils/predictive_performance.py` — 633 LOC · (undocumented)
- `utils/gamification.py` — 645 LOC · (undocumented)
- `utils/efficiency.py` — 462 LOC · (undocumented)
- `utils/wellness.py` — 609 LOC · (undocumented)
- `utils/staff_onboarding_engine.py` — 871 LOC · (undocumented)
- `utils/staff_exit_engine.py` — 907 LOC · (undocumented)
- `utils/hr_actuals_engine.py` — 692 LOC · (undocumented)
- `utils/compliance_training.py` — 555 LOC · (undocumented)

## Module boundaries

- **Organ role**: Human Capital & Regenerative System
- **Cross-organ links**: credit, bsc, admin

## Architecture style

- Streamlit multipage app with API-first engines under `utils/`
- PostgreSQL via `utils/db` adapter where available
- React-readiness target: zero `unsafe_allow_html` excess + minimal raw HTML
- BSC integration via `_bsc_trigger()` hooks
- RBAC via `require_access()` gates
