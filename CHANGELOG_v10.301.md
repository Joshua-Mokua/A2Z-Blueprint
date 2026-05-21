# Changelog — v10.301 Phase 3 Arc 7: Compliance Live Cockpit

**Date:** 2026-05-11
**Phase:** 3 (seventh arc — fourth live cockpit)
**Audit:** 192/192 gates PASS = 100.0%
**Tests:** 156/156 passing across 8 integration suites (13
skipped in audit env)
**G162 Rebase:** 4006 → 4016 (+5 CBK, +5 KRA)

---

## Summary

Fourth live cockpit. Compliance follows the **record-registry**
pattern (CIMS-style) — counts of work-in-progress across four
regulatory registries (compliance cases, AML alerts, sanctions
screening, regulatory filings).

Compression continues. Credit (the third cockpit) was faster
than Treasury (the second) was faster than CIMS (the first).
Compliance was the smoothest yet — the meta-test caught the
React-readiness gap, the EXPECTED_ENDPOINTS staleness, the
G177 require_access mismatch (this one was a real catch — see
findings).

---

## What shipped

### `utils/cockpit_read.py` — `compliance_open_work` composer added

12 documented headline keys:

| Key | Meaning |
|-----|---------|
| `compliance_cases_total` | All compliance case records |
| `compliance_cases_open` | Non-terminal status (open, investigating, pending) |
| `compliance_cases_by_risk` | `{risk_level: count}` (case-insensitive) |
| `aml_alerts_total` | All AML alert records |
| `aml_alerts_open` | Non-closed alerts |
| `aml_alerts_high_risk` | Open + high-risk subset (escalation candidates) |
| `sanctions_screening_total` | All sanctions screening records |
| `sanctions_hits_pending_review` | **The most regulatorily critical metric** — non-terminal sanctions statuses |
| `regulatory_returns_total` | All regulatory return records |
| `regulatory_returns_overdue` | Past due_date + null filed_date |
| `regulatory_returns_on_time_pct` | filed-on-time ÷ filed-total × 100 (None if no filed returns) |
| `as_at` | ISO timestamp of THIS read |

Plus four safe-loader helpers: `compliance_cases`,
`compliance_aml_alerts`, `compliance_sanctions_screening`,
`compliance_regulatory_returns`.

Status normalisation via `_norm_status` / `_norm_risk` —
case-insensitive comparison. "HIGH" / "high" / "High" all
count as `high` for risk grouping.

### `pages/112_compliance_live.py` (NEW)

Seven-tab cockpit at G4 ceiling:

1. **Open work pulse** — 4-metric headline + risk distribution
   row. **Three escalation banners**:
   - 🛑 Red: sanctions matches awaiting review (regulatory SLA)
   - 🛑 Red: regulatory returns overdue (CBK/KRA penalties)
   - ⚠ Yellow: >5 high-risk AML alerts (MLRO escalation)
2. **Compliance cases** — by status, flag_type, risk; recent 20
3. **AML alerts** — by rule_triggered, risk; recent 20
4. **Sanctions screening** — pending review count, by source,
   by status, top 20 by match_score
5. **Regulatory returns** — overdue, on-time rate, by frequency,
   by status, next 15 by due_date
6. **CRA & training** — placeholder listing 9 compliance engines
7. **Audit trail** — emits `compliance_audit_view` event

Discipline (locked by G192): TTL caching, hard `require_access`,
`audit_log` emission, manual refresh button.

### `utils/api_cockpit.py` — 5 compliance HTTP endpoints

| Endpoint | Composer |
|----------|----------|
| `GET /api/cockpit/compliance/open-work` | `compliance_open_work` |
| `GET /api/cockpit/compliance/cases` | `compliance_cases` |
| `GET /api/cockpit/compliance/aml-alerts` | `compliance_aml_alerts` |
| `GET /api/cockpit/compliance/sanctions` | `compliance_sanctions_screening` |
| `GET /api/cockpit/compliance/regulatory-returns` | `compliance_regulatory_returns` |

16 total cockpit endpoints now (was 11). `COCKPIT_READ_API_VERSION`
→ "15.0". All endpoints: `Depends(get_current_user)` auth,
`_audit_cockpit()` call, JSON-serialisable.

### `scripts/audit.py` — G192 added

`gate_compliance_live_cockpit_integrated` locks the Phase 3
discipline for the CMS arc via 8 sub-checks (same shape as
G186/G187/G191).

### `pages/_manifest.json` — page 112 registered

Department `compliance_regulatory`, module_path
`compliance_regulatory.compliance_live`. 116 total manifest
entries.

### `pages/7_admin.py` — Tier 57 added

Documents the 5 compliance composers in the Engine Hub.

### `data/audit_baselines.json` — G162 rebased 4006 → 4016

+5 CBK, +5 KRA for legitimate regulatory references across
page + endpoints + admin + audit gate text.

### `tests/integration/test_compliance_live_cockpit.py` (NEW)

24 tests across 8 sections, all harness-portable.

### `tests/integration/test_phase3_cockpit_discipline.py` — extended

Live cockpit count expectation bumped to 4 pages. Composer
allowlist extended with 5 compliance names. **40 effective
checks** (was 32).

### `tests/integration/test_api_cockpit.py` — extended

`EXPECTED_ENDPOINTS` to 16 (was 11).

---

## TDD red→green progression

- **Red phase:** 3P 17F 4S. The 3 passing were real-data
  contract checks against production JSON files.
- **Green phase 1 (composer added):** 18P 2F 4S. Only
  page/manifest checks remained.
- **Green phase 2 (page + manifest):** 24P 0F 0S.
- **Meta-test caught the cockpit-count drift** → bumped to 4.
- **Meta-test caught the React-readiness gap** → composer
  allowlist extended with 5 names.
- **API endpoint test caught EXPECTED_ENDPOINTS staleness**
  → extended to 16.
- **G177 caught a require_access string mismatch** (page used
  `"compliance.compliance_live"` but manifest module_path is
  `"compliance_regulatory.compliance_live"`). Fixed in the same
  batch. This is exactly what G177 is for.
- **G162 detected new CBK + KRA tokens** → rebased to 4016.

---

## Real finding: G177 catch on require_access

`require_access(...)` strings must match a manifest
module_path. I initially wrote `"compliance.compliance_live"`
matching my mental model ("the compliance arc"), but the
department key in the manifest is `compliance_regulatory`
(carrying the regulatory connotation). The G177 audit gate
caught it because:

> At runtime check_access_dotted falls through to deny once
> the user lacks the explicit grant

That's the right behavior: a typo silently denying access is
worse than a typo causing audit failure. The gate works.

Logged here for the next batch: when writing a new cockpit page,
**read the manifest department key first** before typing the
`require_access` string. Or — better — let G177 catch it on
first audit and fix.

---

## Files changed

- `utils/cockpit_read.py` — `compliance_open_work` + 4 loaders
  + 2 normalisation helpers
- `pages/112_compliance_live.py` — NEW (7 tabs)
- `utils/api_cockpit.py` — 5 compliance endpoints, version 15.0
- `pages/_manifest.json` — page 112 registered
- `pages/7_admin.py` — Tier 57
- `scripts/audit.py` — G192 added
- `data/audit_baselines.json` — G162 → 4016
- `tests/integration/test_compliance_live_cockpit.py` — NEW (24 tests)
- `tests/integration/test_phase3_cockpit_discipline.py` — meta
  expectations updated for 4th cockpit
- `tests/integration/test_api_cockpit.py` — EXPECTED_ENDPOINTS
  extended to 16
- `CHANGELOG_v10.301.md` — this file

---

## Audit results

```
Score: 192/192 gates = 100.0% — PASS
```

---

## Platform state

- **Audit:** 192/192
- **Standards active:** 330/330
- **Pages:** 116 (was 115)
- **Tiers:** 57 (was 56)
- **Gates:** G1-G192 linear
- **Live cockpits:** 4 (CIMS, Treasury, Credit, Compliance)
- **HTTP endpoints (cockpit):** 16 (was 11)
- **Integration test suites:** 8 (was 7)
- **Integration tests passing:** 156/156
- **G162 baseline:** 4016

---

## React-readiness check

Four arcs now HTTP-reachable for React. The same SPA component
that today renders a "compliance dashboard" against backend
state will be able to do so via:

```
GET /api/cockpit/compliance/open-work
```

Returns 12 keys ready for React state hydration. Same data the
Streamlit cockpit renders. Single source of truth.

---

## Next Phase 3 arc options

Updated list:

1. ~~CORS + production deploy config~~ — v10.299 ✓
2. ~~Credit live cockpit~~ — v10.300 ✓
3. ~~Compliance live cockpit~~ — v10.301 ✓ (this batch)
4. **TreasuryDashboardEngine wiring** — close the "0 sections"
   placeholder in Treasury cockpit tab 7. Cat A composer for
   Treasury that pulls from upstream Treasury engines.
5. **CIMS field vocabulary harmonization (B-001)** — real-world
   data-join bug.
6. **PG migration push** — toward 75/79 (95%).
