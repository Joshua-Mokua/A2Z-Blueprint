# Phase 3 Backlog

Living document of debt surfaced by Phase 3 work. Items here are
real but non-blocking — they don't fail the audit, but they
degrade real-world use and should be addressed in future Phase 3
batches.

Per `STANDING_RULES_PHASE_3.md`: ~10% of each batch effort goes
to clearing this backlog.

---

## Open items

### B-001 (v10.295) — CIMS field vocabulary harmonization — CLOSED v10.303

**Status:** ✅ Closed in v10.303 (2026-05-11).

**Resolution:** Translation layer added to
`utils/cockpit_read.py`:
- `normalize_instruction_type(raw)` maps non-canonical
  capture/NLP names to canonical SLA framework keys
- `cims_vocabulary_map()` exposes the full mapping for
  operators and the React SPA
- `cims_instruction_trace()` enriches each capture record
  with `canonical_instruction_type` so SLA deadlines
  auto-attach across engines
- G194 locks the mapping (8 sub-checks) so vocabulary drift
  surfaces on first audit
- 13-test integration suite at
  `tests/integration/test_cims_vocabulary_harmonization.py`

Engines were NOT rewritten — they remain byte-for-byte
locked under G182-G185. The translation layer is read-side
only.

**Original entry preserved below for reference:**

**Surface:** Smoke-testing the live cockpit (page 109) revealed
that different CIMS engines use different field names and
vocabularies for the same concept.

**Examples:**

| Concept | Capture (#166) | SLA (#171) | Notes |
|---------|---------------|------------|-------|
| Channel field name | `originating_channel` | n/a | Cockpit must read `originating_channel` not `channel` |
| Dispute instruction | `COMPLAINT` (INSTRUCTION_TYPES) | `DISPUTE_INVESTIGATION` (INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS) | A `COMPLAINT` instruction at capture won't match SLA's `DISPUTE_INVESTIGATION` deadline key |
| Engine init param naming | `transitions_path` (some engines) | `categories_path` (#175) | No uniform `{records}_path` + `{events}_path` pattern; each engine has its own convention |

**Impact:** Real-world data flowing through the CIMS arc may
fail to join correctly across engines. The cockpit handles
missing data gracefully (shows `?`) but operators won't see
correct cross-engine traces until vocabularies align.

**Fix approach:**
1. Audit all 15 CIMS engine enum tuples for vocabulary
   overlap; produce a mapping table.
2. Decide canonical vocabulary (likely the SLA framework's
   regulatory-aligned names: `DISPUTE_INVESTIGATION`,
   `BILLING_ERROR`, etc., since they map to Reg E/Reg Z).
3. Add a translation layer in `utils/cockpit_read.py`
   (`normalize_instruction_type()`) rather than rewriting
   engine enums (would break G182-G185 byte-for-byte locks).
4. Document the mapping in `STANDING_RULES_PHASE_3.md`.

**Audit gate:** none yet. A future gate could lock the
mapping table.

**Estimate:** 1 batch (~v10.297-ish).

---

### B-002 (v10.295) — Tier 54 "Class" column shows function names

**Surface:** Tier 54 in the admin Engine Hub registers four
helper functions from `utils/cockpit_read.py` (`load_records`,
`filter_records`, `cims_instruction_trace`, `cims_open_work`).
The admin renderer's column is labeled "Class" — but these are
functions, not classes. The status shows correctly
(`✓ load_records`), but the label is misleading.

**Impact:** Cosmetic only. Admin users see "Class: load_records"
which is technically wrong but informative.

**Fix approach:**
1. Either rename the column to "Class / Function" in
   `pages/7_admin.py`, or
2. Split Tier 54 into a separate "Cockpit composers" section
   with its own renderer that uses a "Function" header.

**Estimate:** small change, can ride along with any v10.29X
admin edit.

---

### B-003 (v10.295) — Engine init parameter inconsistency

**Surface:** CIMS engines don't follow a uniform `__init__`
parameter pattern. Some use `transitions_path`, others use
`categories_path`. This makes generic testing harder and
prevents a "create all engines with a uniform data dir"
pattern.

**Examples:**

```python
# Some pattern
ExceptionManagementEngine(
    categories_path=..., exceptions_path=...,
    escalations_path=..., resolutions_path=...,
)

# Different pattern
OmnichannelCaptureEngine(
    sessions_path=..., touches_path=..., handoffs_path=...,
)
```

**Impact:** Integration tests have to special-case each engine's
init signature. Test code is brittle.

**Fix approach:**
1. Audit all engine `__init__` signatures.
2. Add a uniform `from_data_dir(base_dir)` classmethod on each
   engine that takes a single base directory and constructs the
   appropriate per-table paths.
3. Update `utils/cockpit_read.py` to use the classmethod.

**Estimate:** spread across 2-3 batches as engines are touched.

---

### B-004 (v10.295) — Pytest not installed in audit environment

**Surface:** The integration test suite uses pytest fixtures,
but the audit environment doesn't have pytest installed. Tests
were run via a manual runner that fakes the pytest module.

**v10.297 update:** Mitigated for the cockpit HTTP API tests.
`test_api_cockpit.py` now has a Section 9 of static-analysis
tests that parse `utils/api_cockpit.py` with `ast` and verify
discipline (every endpoint has auth dep, audit_log call, no
state-changing verbs). These run without pytest and without
FastAPI. The HTTP-level tests still need both, but the
structural contract is enforced regardless.

**Impact:** Reduced — structural correctness no longer
depends on the test runtime being complete.

**Status:** Still open for full pytest integration, but
the urgency is lower.

**Fix approach:** unchanged from v10.295 — add pytest to
documented deps + a wrapper script.

**Estimate:** 1 small change.

---

### B-006 (v10.297) — FastAPI not installed in audit environment

**Surface:** While building v10.297 (cockpit HTTP API),
FastAPI couldn't be installed in the audit environment
(pip network restricted). Thirteen of the twenty
test_api_cockpit.py tests skip with "FastAPI not installed"
in the audit env, only running in production.

**Impact:** Audit-env coverage of HTTP behavior is limited
to static analysis (8 tests including AST checks for
auth/audit/no-state-changes). Live HTTP roundtrip tests
(401 enforcement, JSON schema, audit emission on real
endpoint hits) run in production but not during pre-flight.

**Fix approach:**
1. Bundle FastAPI in the documented dev deps.
2. The CI / dev environment runs the full HTTP suite.
3. The audit environment runs only the static-analysis
   suite, which is sufficient to catch refactor mistakes.

**Estimate:** part of dev-deps cleanup.

---

### B-005 (carried from v10.294 pre-flight) — Documentation drift

**Surface:** The Phase 3 pre-flight audit found memory line
references to "PG at 19/52 tables" and "API at 22/136 endpoints"
that didn't match audit-derived actuals.

**Status:** Memory line 1 refreshed in v10.294. But other
docs (e.g. README.md, individual CHANGELOG entries) may carry
similar stale references.

**Fix approach:** Single pass through `docs/` and root `*.md`
files looking for outdated counts. Replace with audit-derived
numbers or remove the count entirely.

**Estimate:** small batch, low priority.

---

## Closed items

(none yet — this is the initial backlog from v10.295.)

---

## Maintenance

This file lives at the repo root. Updates happen at every batch
closure. Items get added when surfaced and closed when fixed
(with a closing batch + version).
