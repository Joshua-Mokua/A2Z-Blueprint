# Changelog — v10.305 Phase 3 Arc 11: Audit Trail Composer

**Date:** 2026-05-11
**Phase:** 3 (eleventh arc — multi-cockpit placeholder closure)
**Audit:** 196/196 gates PASS = 100.0%
**Tests:** 214/214 passing across 12 integration suites (13
skipped in audit env)
**G162 Rebase:** none — audit gate text + composer + endpoint
all stayed tenant-token neutral

---

## Summary

Closes the audit-trail placeholder banners that v10.300 (Credit
cockpit) and v10.301 (Compliance cockpit) shipped. Single
composer reading `data/audit_log.json` with filters, wired into
both cockpits' tab 7s, exposed via HTTP for the React SPA.

Same shape as v10.302 + v10.304 placeholder closures but with
**double leverage** — one composer + one gate + one endpoint
covers two cockpits.

CIMS tab 7 already shows its module-specific #176 history
(different file, different schema — `cims_audit_history.json`).
Treasury tab 7 is the daily dashboard report. Both out of
scope. **Every remaining "composer not yet wired" placeholder
banner across the cockpit estate is now closed.**

---

## What shipped

### `utils/cockpit_read.py` — `audit_log_records` composer

```python
def audit_log_records(
    data_dir: str | Path = "data",
    *,
    action: str | None = None,
    module: str | None = None,
    user: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 100,
) -> Dict[str, Any]:
```

Reads `data/audit_log.json` (13 records on disk today, gated
to 1000 in production). Filters apply AND-wise; date filters
use ISO-string lex compare (works because the file writes ISO
8601 timestamps).

Sort: most-recent first by `ts`. Operators want latest activity
at the top.

Returns:

| Key | Meaning |
|-----|---------|
| `records` | list of audit records (length ≤ limit) |
| `count` | filtered total — may exceed `len(records)` |
| `filters` | dict of what was applied (operator confirmation) |
| `as_at` | ISO timestamp of THIS read |

Distinct `count` vs `len(records)` lets the UI render "showing
100 of 487" cleanly without two requests.

Defensive: missing file → empty list; non-dict rows skipped;
non-comparable `ts` falls back to input order rather than
crashing.

### `pages/111_credit_live.py` — tab 7 wired

Placeholder banner removed. Tab 7 now renders:

- 3 filter inputs (action, user, last-N selector)
- 2-metric row (filtered count, showing count)
- List of recent records with timestamp + user + action +
  detail
- Pre-filtered to `module="credit_live"` so operators see
  credit-cockpit-tagged actions

The filter UI is intentionally simple — operators can dig
deeper via the platform audit module page if they need cross-
module queries.

### `pages/112_compliance_live.py` — tab 7 wired

Same shape as Credit tab 7, pre-filtered to
`module="compliance_live"`. The empty-state message documents
that **SAR filing decisions are audit-logged separately under
`module=sar_filing`** — operators need to drop the
`compliance_live` filter to see those. Honest documentation
better than a misleading view.

### `utils/api_cockpit.py` — `/audit/log` endpoint

```
GET /api/cockpit/audit/log
  ?action=<exact>
  &module=<exact>
  &user_filter=<exact>
  &since=<ISO date or timestamp>
  &until=<ISO date or timestamp>
  &limit=<1-1000, default 100>
```

JWT-protected. Audit-logged (every audit-log query is itself
audit-logged — meta-discipline).

**Naming note:** the FastAPI `user` parameter is the JWT-
authenticated actor injected by `Depends(get_current_user)`.
The `user_filter` query parameter is the filter applied to
`record["user"]` in the result set. Distinct names to avoid
collision.

19 cockpit endpoints now (was 18). `COCKPIT_READ_API_VERSION` →
"18.0".

### `scripts/audit.py` — G196 added

`gate_audit_trail_composer_wired` locks the closure via 7
sub-checks:

1. `audit_log_records` exists in cockpit_read
2. Signature accepts all required filter params
3. Smoke call on missing data dir returns count=0 cleanly
4. Page 111 references composer + banner gone
5. Page 112 references composer + banner gone
6. HTTP endpoint registered
7. Endpoint documented in module docstring

### `tests/integration/test_audit_trail_composer.py` (NEW)

18 tests across 9 sections — composer contract, filters
(individual + combined), sort, limit, read-only guarantee,
page wiring (both pages), endpoint registration, gate
liveness, JSON-serialisability.

### `tests/integration/test_api_cockpit.py` — extended

`EXPECTED_ENDPOINTS` to 19.

---

## TDD red→green progression

- **Red phase:** 0P 18F. Nothing built yet.
- **Green phase 1 (composer added):** ~12P, page + endpoint
  tests still failing.
- **Green phase 2 (page wiring):** ~16P, endpoint + gate left.
- **Green phase 3 (endpoint + G196):** 18P 0F.

Zero audit failures this batch — the design avoided new tenant
tokens (audit gate text uses neutral words like "module",
"endpoint", "composer", "filter" instead of "Ecobank" or
"KES").

---

## Real findings during this batch

1. **CIMS tab 7 was already wired**, just to a different file
   (`cims_audit_history.json`, the #176 history register). It
   reads module-specific #176 records, not the platform-wide
   `audit_log.json`. Different schema, different purpose. Left
   alone — scope was the two cockpits with actual placeholder
   banners.

2. **Treasury tab 7 was already wired** to the dashboard
   report (v10.302). Not an audit-trail tab at all. Out of
   scope.

3. **The `user` parameter naming collision in FastAPI** —
   `Depends(get_current_user)` injects `user`, but the audit
   log records also have a `user` field that could be a
   filter. Solution: filter parameter named `user_filter` in
   the HTTP query string; the composer parameter named `user`
   internally; the FastAPI handler maps `user_filter` → `user`
   in the composer call. The HTTP API contract is explicit
   about which is which.

4. **Pre-filtering by module in the page** is a UX choice, not
   a hard restriction. Operators can clear the filter in
   custom requests via the HTTP endpoint. The page just
   defaults to the cockpit's own scope for ergonomic reasons.

5. **The empty-state message in Compliance tab 7 documents
   the SAR filing exception explicitly.** When a compliance
   officer files an SAR, the audit goes under `module=
   sar_filing` not `compliance_live`. Without that note, the
   absence of SAR records in the compliance audit view could
   look like a bug. With it, the operator knows where to
   look.

---

## Files changed

- `utils/cockpit_read.py` — `audit_log_records` composer
- `utils/api_cockpit.py` — `/audit/log` endpoint, version 18.0
- `pages/111_credit_live.py` — tab 7 wired, banner removed
- `pages/112_compliance_live.py` — tab 7 wired, banner removed
- `scripts/audit.py` — G196 added and registered
- `tests/integration/test_audit_trail_composer.py` — NEW (18 tests)
- `tests/integration/test_api_cockpit.py` — EXPECTED_ENDPOINTS to 19
- `CHANGELOG_v10.305.md` — this file

---

## Audit results

```
Score: 196/196 gates = 100.0% — PASS
```

---

## Platform state

- **Audit:** 196/196 (was 195)
- **Standards active:** 330/330
- **Pages:** 116 (no change)
- **Tiers:** 57 (no change)
- **Gates:** G1-G196 linear
- **Live cockpits:** 4 (all four with HTTP endpoints, fully
  wired tabs — no remaining "composer not yet wired"
  placeholder banners)
- **HTTP endpoints (cockpit):** 19 (was 18)
- **Integration test suites:** 12 (was 11)
- **Integration tests passing:** 214/214 (13 skipped in audit
  env)
- **G162 baseline:** 4022 (unchanged)

---

## React-readiness check

The React SPA can now build a unified audit trail view:

```js
fetch('/api/cockpit/audit/log?module=credit_live&limit=50')
fetch('/api/cockpit/audit/log?action=cockpit_cache_clear')
fetch('/api/cockpit/audit/log?since=2026-05-01T00:00:00')
```

Same composer drives Streamlit cockpit tabs + React. Single
source of truth, double leverage (one composer / two cockpits
/ React SPA).

---

## Phase 3 placeholder banners — final accounting

After this batch, the cockpit estate's "composer not yet
wired" placeholder banners are **all closed**:

| Cockpit | Tab | v10.296 / Phase-2 state | v10.305 state |
|---------|-----|-------------------------|---------------|
| CIMS pg 109 | Tab 7 | Wired to #176 history | Wired (unchanged) |
| Treasury pg 110 | Tab 6 | Placeholder banner | Wired in v10.304 ✓ |
| Treasury pg 110 | Tab 7 | Placeholder banner | Wired in v10.302 ✓ |
| Credit pg 111 | Tab 7 | Placeholder banner | Wired this batch ✓ |
| Compliance pg 112 | Tab 7 | Placeholder banner | Wired this batch ✓ |

Other "follow-on batch" labels still exist for **Portfolio
analytics** placeholders in Credit tab 6 and **CRA & training**
placeholders in Compliance tab 6 — but those are different
shape (Cat A composers, not single-engine wirings) and were
deliberately scoped out as future composer work.

---

## Next Phase 3 arc options

Updated list:

1. ~~CORS + production deploy config~~ — v10.299 ✓
2. ~~Credit live cockpit~~ — v10.300 ✓
3. ~~Compliance live cockpit~~ — v10.301 ✓
4. ~~TreasuryDashboardEngine wiring~~ — v10.302 ✓
5. ~~CIMS vocabulary harmonization (B-001)~~ — v10.303 ✓
6. ~~Cash forecast composer wiring~~ — v10.304 ✓
7. ~~Audit trail composer~~ — v10.305 ✓ (this batch)
8. **PG migration push** — toward 75/79 (95%). 31 tables to
   migrate; each is a small dual-write toggle + migration
   script + table-specific G163 test.
9. **Cat A Portfolio analytics composer** — close Credit
   tab 6 placeholder
10. **Cat A CRA & training composer** — close Compliance
    tab 6 placeholder

**Eleven Phase 3 arcs shipped. Backlog B-001 closed. Every
single-engine placeholder banner in the cockpit estate
closed.** The bigger structural items remaining (PG migration,
Cat A composers) are now what's blocking further compression.
