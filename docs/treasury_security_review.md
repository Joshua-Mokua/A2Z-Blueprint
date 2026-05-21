# Treasury Module — Security Gap Analysis

**Module key:** `treasury` · **Organ role:** Cash Flow Reservoir & Arterial Blood Pressure (ALM · FTP · FX · liquidity · market risk · VAR)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 60.0%

Per Phase 1 Technical Health: security gaps and RBAC coverage.

---

## RBAC coverage

- Pages with `require_access`: **3/3 (100.0%)**
- Audit log calls: **5**

## Known security considerations

- Session-based authentication via Streamlit session_state
- Role checks at page entry via `require_access(roles_list)`
- Sensitive writes wrapped in audit_log for traceability

## Gaps

- ⚠️ Only 5 audit_log calls (target >=10)
- ⚠️ No security_event monitoring in this module
- ⚠️ No failed-access tracking surfaced
