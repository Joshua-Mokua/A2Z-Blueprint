# Changelog — v10.300 Phase 3 Arc 6: Credit Live Cockpit

**Date:** 2026-05-11
**Phase:** 3 (sixth arc — third live cockpit)
**Audit:** 191/191 gates PASS = 100.0%
**Tests:** 124/124 passing across 7 integration suites (13
skipped in audit env, run in production CI)
**G162 Rebase:** 3999 → 4006 (+3 KES, +4 CBK) — page 111 + API
endpoints + Tier 56 admin reference CBK Prudential / IFRS9
Stage 3 NPL definition and KES default currency in loan display.

---

## Summary

Third live cockpit arc following CIMS (v10.295, record-registry
pattern) and Treasury (v10.296, compute+JSON pattern). Credit
follows the Treasury pattern: stateful compute engines reading
JSON data files. Comes with HTTP endpoints from the start —
the React-readiness invariant from v10.297 forced it, exactly
as designed.

This is option (2) from the v10.298 next-arc list, taken in
order after v10.299's CORS + deploy config groundwork landed.

---

## What shipped

### `utils/cockpit_read.py` — `credit_open_work` composer added

Aggregates the bank-wide Credit landscape from three JSON
files. Documented return keys (all 10 always present):

| Key | Source | Meaning |
|-----|--------|---------|
| `applications_total` | loan_applications.json | All records |
| `applications_open` | non-terminal swim_lanes | Pipeline/review/underwriting/risk_review/committee/awaiting_docs/pending/in_progress/intake |
| `applications_by_stage` | swim_lane field | `{lane: count}` |
| `ifrs9_total` | ifrs9_loans.json | All records |
| `ifrs9_stage1` | stage == 1 | Performing |
| `ifrs9_stage2` | stage == 2 | Significant credit increase |
| `ifrs9_stage3` | stage == 3 | NPL per IFRS9 / CBK Prudential |
| `npl_pct` | Stage 3 outstanding ÷ total outstanding × 100 | Regulatory KPI |
| `watchlist_count` | credit_monitoring.json | Watchlist entries |
| `as_at` | `datetime.utcnow().isoformat()` | This-read timestamp |

Plus three safe-loader helpers: `credit_loan_applications`,
`credit_ifrs9_loans`, `credit_watchlist`. All return empty list
on missing/malformed files (legacy tolerance per Phase 3
discipline).

Field coercion helpers `_coerce_stage` and `_coerce_amount`
handle legacy data where stage arrives as a string or
outstanding is missing — counted in totals, skipped from
stage-specific aggregates rather than crashing.

### `pages/111_credit_live.py` (NEW)

Seven-tab live cockpit at G4 ceiling:

1. **Open work pulse** — 5-metric headline (apps total, apps
   open, IFRS9 records, NPL ratio with 5% threshold warning,
   watchlist), Stage 1/2/3 row, triage banners for NPL >5% and
   Stage 2 migration risk.
2. **Loan pipeline** — applications by swim_lane, by product,
   by currency, recent 20 by application_date.
3. **IFRS9 stages** — stage 1/2/3 counts + outstanding per
   stage, per IFRS9 / CBK Prudential definition.
4. **NPL & watchlist** — top 20 Stage 3 accounts sorted by
   outstanding (descending), watchlist entries with reasons.
5. **Credit admin** — approved book by product, top 5 RMs by
   deal count, recent 10 approvals.
6. **Portfolio analytics** — placeholder enumerating the 7
   credit engines available; Cat A composer wiring is a
   follow-on batch.
7. **Audit trail** — emits `credit_audit_view` audit event;
   composer-backed view is a follow-on batch.

Discipline (locked by G191):
- `@st.cache_data(ttl=10)` on every read function
- Hard `require_access("credit.credit_live")` — no silent
  try/except
- `audit_log()` on view + cache-clear actions
- Manual 🔄 Refresh button that clears the cache

### `utils/api_cockpit.py` — 4 credit HTTP endpoints

Per the React-readiness invariant from v10.297, every cockpit
composer used by a `*_live.py` page must have a matching HTTP
endpoint. The meta-test catches gaps. Added:

| Endpoint | Composer | Returns |
|----------|----------|---------|
| `GET /api/cockpit/credit/open-work` | `credit_open_work` | Headline dict (10 keys) |
| `GET /api/cockpit/credit/applications` | `credit_loan_applications` | `{records, count}` |
| `GET /api/cockpit/credit/ifrs9` | `credit_ifrs9_loans` | `{records, count}` |
| `GET /api/cockpit/credit/watchlist` | `credit_watchlist` | `{records, count}` |

All four follow the locked v10.297 pattern: `Depends(get_current_user)`
auth, `_audit_cockpit()` call, read-only, JSON-serialisable
return. `COCKPIT_READ_API_VERSION` bumped to "14.0" so the
React SPA can detect the new endpoints.

### `pages/_manifest.json` — page 111 registered

Entry under department `credit`, module_path `credit.credit_live`,
icon 💳, with G160-compliant description naming all 12 standards
(#119-#130) + extension standards (CRD-R1..R7 + KESONIA) the
cockpit composes. **115 total manifest entries** (was 114).

### `pages/7_admin.py` — Tier 56 added

Engine Hub Tier 56 documents the 4 credit composers (one entry
per composer with description matching its docstring). Follows
the v10.295/v10.296 pattern of one tier per Phase 3 cockpit
composer set.

### `scripts/audit.py` — G191 added

`gate_credit_live_cockpit_integrated` locks the Phase 3
discipline for the Credit arc via 8 sub-checks:
1. `pages/111_credit_live.py` exists
2. No silent try/except around `require_access`
3. `utils.cockpit_read.credit_open_work` API exists
4. Returns all 10 documented keys
5. Manifest entry with `credit.credit_live` module_path
6. `@st.cache_data(ttl=...)` present
7. `audit_log()` call present
8. `/api/cockpit/credit/open-work` endpoint exists (React-
   readiness)

### `data/audit_baselines.json` — G162 rebased 3999 → 4006

+3 KES, +4 CBK for page 111 + API endpoints + Tier 56 admin
entry references to NPL ratio / CBK Prudential / KES currency
display.

### `tests/integration/test_credit_live_cockpit.py` (NEW)

21 tests across 9 sections, all harness-portable:

1. Composer contract (keys, dict return, missing files)
2. Loan applications JSON contract (real + synthetic)
3. IFRS9 stage logic (counts + NPL percentage math)
4. Watchlist counting
5. Read-only guarantee (mtime + content unchanged after 5 calls)
6. Edge cases (malformed JSON, legacy record shapes with string
   stages or missing outstanding)
7. Performance smoke (5,000 records aggregate in <1 second)
8. Page 111 manifest + discipline checks (hard require_access,
   audit_log, TTL cache, no direct filesystem reads)
9. Idempotency + JSON-serialisability

### `tests/integration/test_phase3_cockpit_discipline.py` — extended

Meta-test now expects 3 live cockpit pages (was 2). Composer
allowlist extended to include `credit_open_work`,
`credit_loan_applications`, `credit_ifrs9_loans`,
`credit_watchlist`. 32 effective checks (was 24).

### `tests/integration/test_api_cockpit.py` — extended

`EXPECTED_ENDPOINTS` includes the 4 new credit routes. 11 total
endpoints now (was 7).

---

## TDD red→green progression

Per Kaizen, tests written FIRST:

- **Red phase (composer not yet built):** 2P 15F 4S. The 2
  passing tests were the JSON contract checks against real
  production data. The 15 failing tests defined the composer
  surface.
- **Green phase 1 (composer added):** 16P 1F 4S. The 4 skipped
  tests were waiting on `pages/111_credit_live.py`.
- **Green phase 2 (page written + manifest registered):** 21P 0F 0S.
- **Meta-test caught the live cockpit count drift** (`test_live_
  cockpit_pages_count_matches_v10296` failed expecting 2 pages;
  bumped to 3).
- **Meta-test caught the React-readiness gap** (composer
  allowlist didn't include credit composers; extended it).
- **API endpoint test caught the EXPECTED_ENDPOINTS drift**
  (was 7, now 11).
- **Audit caught the G162 drift twice** (page 111 + Tier 56);
  rebased to 4006.

That's the Kaizen system working as designed: every invariant
that could silently regress is encoded as a test, and every test
failure surfaces in the same batch that introduced the change.

---

## Real findings during this batch

1. **The standards registry has non-numeric `ENH-CRD-R*`
   IDs** alongside the numeric `ENH-119..130` entries. My first
   filter attempt did `int(s.standard_id.replace('ENH-', ''))`
   and crashed on `CRD-R1`. Fixed via regex match. Now the
   31-standard credit category is correctly surfaced.

2. **Credit module data is production-scale.** 724 loan
   applications, **5,045 IFRS9 loan records**, 214 credit
   admin records. The performance test forced me to verify the
   composer handles 5k records in under 1 second — it does
   (single-pass aggregation, no nested loops).

3. **Credit JSON file shapes vary.** `credit_monitoring.json` is
   a dict with a `watchlist` key (not a list of records like the
   others). `credit_loan_applications` rows have `swim_lane`,
   `pipeline_deal_id`, `client_cif`; `ifrs9_loans` rows have
   `account_id`, `stage`, `outstanding`, `pd_12m`. The composer
   accommodates both shapes cleanly.

4. **The React-readiness invariant earned its keep.** The
   meta-test detected the gap automatically: composer added to
   cockpit_read + used by page → MUST have HTTP endpoint. Forced
   the API endpoints to ship in the same batch, not deferred.

5. **NPL ratio math is regulatorily sensitive.** NPL =
   Stage 3 outstanding / total outstanding × 100. Per CBK
   Prudential / IFRS9 Stage 3 definition. The 5% threshold
   triggers the cockpit's red banner — that's the CBK advisory
   threshold for portfolio concern. Tested with 10% (banner
   should fire) and 0% (clean book, banner suppressed).

---

## Files changed

- `utils/cockpit_read.py` — `credit_open_work` + 3 loaders + 2
  helpers added
- `pages/111_credit_live.py` — NEW (7 tabs)
- `utils/api_cockpit.py` — 4 credit endpoints, version → 14.0,
  docstring extended
- `pages/_manifest.json` — page 111 registered
- `pages/7_admin.py` — Tier 56 added
- `scripts/audit.py` — G191 added and registered
- `data/audit_baselines.json` — G162 rebased to 4006
- `tests/integration/test_credit_live_cockpit.py` — NEW (21 tests)
- `tests/integration/test_phase3_cockpit_discipline.py` — meta
  expectations updated for 3rd cockpit
- `tests/integration/test_api_cockpit.py` — EXPECTED_ENDPOINTS
  extended to 11
- `CHANGELOG_v10.300.md` — this file

---

## Audit results

```
Score: 191/191 gates = 100.0% — PASS
```

---

## Platform state

- **Audit:** 191/191 gates green
- **Standards active:** 330/330 (no change)
- **Pages:** 115 (was 114; page 111 added)
- **Tiers:** 56 (was 55; Tier 56 added)
- **Gates:** G1-G191 (linear, no gaps)
- **Live cockpits:** 3 (CIMS, Treasury, Credit) — all HTTP-
  reachable
- **HTTP endpoints (cockpit):** 11 (was 7)
- **Integration test suites:** 7 (was 6)
- **Integration tests passing:** 124/124 (13 skipped in audit env)
- **PG migration:** 48/79 tables (61%) — unchanged
- **G162 baseline:** 4006

---

## React-readiness check

After this batch:

- **Credit data is HTTP-fetchable.** The React SPA can render a
  credit dashboard via `GET /api/cockpit/credit/open-work` and 3
  detail endpoints.
- **NPL ratio is consistently computed.** Same number whether
  the Streamlit cockpit or React SPA renders it — single
  source of truth in `credit_open_work`.
- **Meta-test prevents drift.** Future credit-composer additions
  will be forced to expose HTTP endpoints by the same React-
  readiness invariant.

When the React frontend work begins, Credit is now one of three
arcs ready to wire up alongside CIMS and Treasury. Three down,
~17 module arcs to go before the platform is fully React-ready.

---

## Architectural patterns now codified

Three live cockpits demonstrating two patterns:

1. **Record-registry** (CIMS): persistent JSON of records, count
   open ones, instruction-trace composer for cross-engine joins.
2. **Compute+JSON** (Treasury, Credit): regulatory JSON files,
   computations + aggregations, ratios with breach detection.

Future cockpits should fit one of these patterns. The two are
distinguished by whether the cockpit's main job is **counting
work-in-progress** (CIMS) versus **aggregating regulatory
state** (Treasury, Credit). Once that question is answered, the
implementation is largely fill-in-the-blanks against the
patterns and inherits Phase 3 discipline + React-readiness
automatically.

---

## Next Phase 3 arc options

Updated list:

1. ~~CORS + production deploy config~~ — v10.299 ✓
2. ~~Credit live cockpit~~ — DONE this batch ✓
3. **Compliance live cockpit** — CMS engines (#191-#200). KYC/
   KYB, PEP/sanctions, AML monitoring, SAR filing, regulatory
   change. Record-registry pattern (cases + screenings).
4. **TreasuryDashboardEngine wiring** — close the "0 sections"
   placeholder in Treasury cockpit tab 7.
5. **CIMS field vocabulary harmonization (B-001)** — real-world
   data-join bug.
6. **PG migration push** — toward 75/79 (95%).

Compliance is the natural option (3) given two cockpits ship
faster after a third — the pattern is locked, the test discipline
is locked, the React-readiness invariant is locked. Same shape,
different domain.
