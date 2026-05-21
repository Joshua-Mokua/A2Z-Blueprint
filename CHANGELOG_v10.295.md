# Changelog — v10.295 Phase 3 Arc 1: CIMS Live Cockpit Integration

**Date:** 2026-05-11
**Phase:** 3 (first integration arc)
**Audit:** 186/186 gates PASS = 100.0%
**G162 Rebase:** 3984 → 3986 (+2: CBK +1, Kenya +1) — page 109
description and G186 audit gate text reference Reg E/Reg Z/CBK
Banking Act/DPA Kenya 2019 frameworks.

---

## Summary

First Phase 3 cockpit integration arc. Closes the G130
deferred-to-closure obligation for the CIMS arc by delivering a
live read-side cockpit that composes all 15 CIMS engines into a
single operating view.

This is the first arc to operate under the v10.294 Phase 3
standing rules: UI integration is a first-class deliverable
(not deferred), pages must fail loud on access errors (no silent
try/except), live cockpits use TTL caching for refresh, and every
new audit gate must be paired with a working cockpit.

---

## What shipped

### `utils/cockpit_read.py` (NEW)

9-function library providing read-side composability across engine
records. Generic helpers (`load_records`, `filter_records`,
`sort_records`, `group_by`, `count_by`, `find_by_id`, `latest_n`)
plus two CIMS-specific composers:

- `cims_instruction_trace(session_id, data_dir)` — given a
  `linked_session_id`, joins capture (#166) + classification
  (#167) + STP (#168) + exceptions (#175) + SLA (#171) + audit
  history (#176) records into a single trace dictionary.

- `cims_open_work(data_dir, limit)` — aggregates the bank-wide
  CIMS work landscape: open capture sessions, pending NLP,
  pending STP manual reviews, open exceptions, upcoming/breached
  SLA obligations, pending identity merges. All live data,
  no precomputed snapshots.

Read-only, legacy-data-tolerant (returns empty list on any error).
Never modifies upstream records.

### `pages/109_cims_live.py` (NEW)

Live CIMS cockpit with 7 tabs at the G4 ceiling:

1. **Open work pulse** — bank-wide CIMS landscape NOW (7 headline
   metrics across the top, with triage banners for breached SLAs
   and high exception counts)
2. **Instruction trace** — full lifecycle for one
   `linked_session_id`, joining 6 engines into a single view
3. **Recent capture** — latest 50 sessions with channel + state
   breakdowns
4. **SLA risk board** — upcoming and breached deadlines
5. **Exception board** — open exceptions by severity + category
6. **Pending reviews** — STP manual queue, identity merges,
   low-confidence NLP
7. **Audit trail explorer** — recent audit history records,
   filterable by `kind`

All tabs use `@st.cache_data(ttl=10)` for automatic refresh.
Manual `🔄 Refresh now` button clears the cache and emits an
audit log event. Uses `require_access("operations.cims_live")`
without a try/except swallow.

### `scripts/audit.py` — G186 added

`gate_cims_live_cockpit_integrated` locks the Phase 3 live
cockpit discipline:

- `pages/109_cims_live.py` exists
- Pages 105-109 use HARD `require_access` (no silent try/except)
- `utils/cockpit_read.py` exposes the documented 9-function API
- Manifest entry for page 109 has `module_path =
  "operations.cims_live"`
- Page 109 uses `@st.cache_data(ttl=...)` for live refresh
- Page 109 calls `audit_log()` (real audit trail, not stubs)

### `pages/_manifest.json` — page 109 registered

All 7 required fields present (now G160-enforced):
- `department_primary: "operations"`
- `module_path: "operations.cims_live"`
- `secondary_visibility: ["__all_admins__"]`
- `title: "CIMS — Live Cockpit"`
- `icon: "🎛️"`
- `description`: full description of all 15 composed engines
- `current_module_key: "cims_live"`

### `pages/7_admin.py` — Tier 54 added

Engine Hub admin entry for the cockpit_read composer with 4
function entries (load_records, filter_records,
cims_instruction_trace, cims_open_work).

Note: Tier 54 entries are functions, not classes. The admin
renderer's "Class" column shows the function name. Logged as
backlog item B-002 for future cosmetic fix.

### Pages 105/106/107/108 hardened

Removed the silent `try: from pages._access import require_access /
except: pass` pattern. These pages now fail loud on any
require_access issue, per Phase 3 standing rule.

### `tests/integration/test_cims_live_cockpit.py` (NEW)

11 integration tests covering:

- Capture engine writes `originating_channel` field (contract test
  that caught the v10.295 build-time bug)
- Instruction trace joins capture and history records
- Instruction trace returns well-formed empty result for unknown
  session
- Open work snapshot counts open sessions
- Open work snapshot excludes COMPLETED/ABANDONED/CANCELLED
  sessions
- Filter records by date window (inclusive/exclusive boundaries)
- Filter records tolerates missing date field
- `count_by` handles missing field gracefully
- Page 109 manifest entry exists with correct fields
- CIMS pages 105-109 use hard `require_access` (no silent swallow)
- `cockpit_read` exposes the documented 9-function API

All 11 pass. Tests are pytest-compatible but were also run via
a fallback runner since pytest isn't installed in the audit env
(backlog item B-004).

### `PHASE_3_BACKLOG.md` (NEW)

Living backlog of debt surfaced by Phase 3 work. Initial
5 items: CIMS field vocabulary harmonization (B-001), Tier 54
"Class" label drift (B-002), engine init parameter
inconsistency (B-003), pytest unavailable in audit env (B-004),
documentation drift (B-005).

### `data/audit_baselines.json` — G162 rebased

3984 → 3986 (+2: CBK +1, Kenya +1) for v10.295 framework
references in page 109 description and G186 summary.

---

## What integration testing surfaced

These were caught by the cockpit smoke test before shipping:

1. **The cockpit was wired to the wrong field name.** Capture
   engine writes `originating_channel`; cockpit was reading
   `channel`. Fixed in 3 places (rows display, manifest display,
   `count_by`). Now covered by the
   `test_capture_engine_writes_originating_channel_field` test.

2. **CIMS instruction-type vocabularies don't align across
   engines.** Capture uses `COMPLAINT`/`FUNDS_TRANSFER`/etc.; SLA
   uses `DISPUTE_INVESTIGATION`/`BILLING_ERROR`/etc. Logged as
   backlog item B-001 — needs a translation layer.

3. **Engine init parameters aren't uniform.** Logged as B-003.

These are non-blocking (the cockpit handles missing data
gracefully) but real. They will be addressed in future Phase 3
batches per the standing-rules ~10% cleanup allocation.

---

## Files changed

- `utils/cockpit_read.py` — NEW (456 lines, 9 public functions)
- `pages/109_cims_live.py` — NEW (425 lines, 7 tabs)
- `pages/_manifest.json` — page 109 entry added
- `pages/7_admin.py` — Tier 54 added
- `pages/105_cims_capture.py` — removed silent require_access try/except
- `pages/106_cims_process.py` — same fix
- `pages/107_cims_compliance.py` — same fix
- `pages/108_cims_closure.py` — same fix
- `scripts/audit.py` — G186 gate added and registered
- `data/audit_baselines.json` — G162 rebased to 3986
- `tests/integration/test_cims_live_cockpit.py` — NEW (11 tests)
- `PHASE_3_BACKLOG.md` — NEW
- `CHANGELOG_v10.295.md` — this file

---

## Audit results

```
Score: 186/186 gates = 100.0% — PASS
```

Including the new G186. Including the new G160-enforced
`description` field on all 113 pages (page 109 added).

---

## Platform state

- **Audit:** 186/186 gates green
- **Standards active:** 330/330 (no change)
- **Pages:** 113 (was 112, +1 page 109)
- **Tiers:** 54 (was 53, +1 Tier 54)
- **Gates:** G1-G186 (linear, no gaps)
- **CIMS arc:** 15/15 standards + live cockpit (G130 closed)
- **PG migration:** 48/79 tables (61%) — unchanged
- **API endpoints:** 192 across 19 modules — unchanged
- **Tests:** 188 test files (was 187, +1 integration suite)

---

## What this arc demonstrates

Phase 3 standing rules in action:

- **UI integration is a first-class deliverable** — page 109 is
  the deliverable; the cockpit_read library is in service of the
  page, not the other way around.
- **No new audit gates without a cockpit** — G186 ships paired
  with page 109.
- **Honesty in claims** — backlog file logs the field-vocabulary
  issue rather than paving over it.
- **Cleanup is part of the cycle** — 4 pages had their silent
  try/except removed; the legacy-leaning admin tier renderer
  shows function names where it labels "Class" and is logged as
  B-002 rather than papered over with marketing language.
- **Integration tests exist** — 11 new tests that exercise live
  engine→cockpit composition, the path that masks the most
  bugs.

---

## Next Phase 3 arc options

In rough order of leverage:

1. **Replicate the live cockpit pattern across other arcs.**
   Treasury, Credit, Compliance, Risk all have engines today
   but no live composer. Each could get its own "Live Cockpit"
   page following the page 109 template.

2. **CIMS field vocabulary harmonization (B-001).** Without
   this, the cross-engine joins in `cims_instruction_trace`
   won't catch instructions that flow through capture as
   `COMPLAINT` but need SLA tracking as `DISPUTE_INVESTIGATION`.

3. **PG migration push** to lift from 48/79 (61%) toward
   75/79 (95%). Tables touched by Phase 2B engines are likely
   candidates.

4. **API endpoint coverage** — many CIMS engines have no public
   API surface today. The mobile app and React SPA will need
   them.

5. **Regulatory artifacts** — FATCA/CRS XML, remaining 5/8 CBK
   reports.

The CIMS live cockpit is now a template. Each follow-on arc
should compress to ~1 batch as the pattern matures.
