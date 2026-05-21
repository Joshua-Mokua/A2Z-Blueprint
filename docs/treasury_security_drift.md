# Treasury Module — Security Drift Scan

**Module key:** `treasury` · **Organ role:** Cash Flow Reservoir & Arterial Blood Pressure (ALM · FTP · FX · liquidity · market risk · VAR)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 60.0%

Per Phase 8 Anti-Deterioration: detect security configuration drift over time (RBAC gates removed, audit_log calls dropped).

---

## Current state

- Pages with require_access: 3/3
- audit_log calls in engines: 0

## Drift indicators

- No baseline yet — establish in this batch
- Future audits should compare against this snapshot

## Recommended baselines

- RBAC coverage must not drop below current level
- audit_log count must not decrease
