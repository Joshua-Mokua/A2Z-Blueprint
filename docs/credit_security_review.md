# Credit Module — Security Gap Analysis

**Module key:** `credit` · **Organ role:** The heart of the bank
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 38.6%

Per Phase 1 Technical Health: security gaps and RBAC coverage.

---

## RBAC coverage

- Pages with `require_access`: **8/14 (57.1%)**
- Audit log calls: **24**

## Known security considerations

- Session-based authentication via Streamlit session_state
- Role checks at page entry via `require_access(roles_list)`
- Sensitive writes wrapped in audit_log for traceability

## Gaps

- ⚠️ Only 57.1% of pages have RBAC gates (target >=80%)
- ⚠️ No security_event monitoring in this module
- ⚠️ No failed-access tracking surfaced
