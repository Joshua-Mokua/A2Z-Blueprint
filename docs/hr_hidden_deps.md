# HR Module — Hidden Dependencies

**Module key:** `hr` · **Organ role:** Human Capital & Regenerative System
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 88.7%

Per Phase 1 Operational Health: hidden/implicit dependencies.

---

## Implicit dependencies

- `streamlit` session_state cleared on code update (`_APP_VERSION` stamp)
- `users.json` must include `"active": true` for login
- Password format `EcoStaff` + last 4 digits of staff code
- BSC pillar weights hardcoded to Kaplan-Norton 40/25/25/10
- Cascade hierarchy MUST follow canonical org structure

## Risk if violated

- Login failures, blank dashboards, missing scores, broken role visibility
