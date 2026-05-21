# Changelog — v10.303 Phase 3 Arc 9: CIMS Vocabulary Harmonization (B-001 Closure)

**Date:** 2026-05-11
**Phase:** 3 (ninth arc — backlog closure)
**Audit:** 194/194 gates PASS = 100.0%
**Tests:** 183/183 passing across 10 integration suites (13
skipped in audit env)
**G162 Rebase:** 4018 → 4020 (+2 CBK)

---

## Summary

Closes the oldest item in the Phase 3 backlog: **B-001 CIMS
field vocabulary harmonization**, logged in v10.295 when the
first live cockpit smoke test caught that the capture engine
(#166) writes `originating_channel` but the cockpit was reading
`channel`. That part was hot-fixed in v10.295. This batch
closes the deeper issue: different CIMS engines use different
names for the same semantic concept, breaking cross-engine
joins.

The fix is a **read-side translation layer** — engines stay
byte-for-byte locked under G182-G185 (no enum rewrites).
`cockpit_read.normalize_instruction_type()` is the bridge.

---

## The real problem (recap from v10.295)

| Concept | Capture #166 | NLP #167 | SLA #171 |
|---------|-------------|----------|----------|
| Customer complaint | `COMPLAINT` | `COMPLAINT` | `CUSTOMER_COMPLAINT` |
| Information request | `GENERAL_INQUIRY` | `INFORMATION_REQUEST` | `GENERAL_INQUIRY` |
| Dispute (Reg E) | n/a | n/a | `DISPUTE_INVESTIGATION` |
| Billing error (Reg Z) | n/a | n/a | `BILLING_ERROR` |
| Regulatory filing | n/a | n/a | `REGULATORY_REPORTING` |

Without translation, a `COMPLAINT` captured at the front door
never matches SLA's `CUSTOMER_COMPLAINT` deadline key — so the
regulatory deadline doesn't auto-attach. In production, that
means a customer dispute could sit past its SLA window without
any cockpit alert firing.

---

## What shipped

### `utils/cockpit_read.py` — three additions

**1. `_CIMS_INSTRUCTION_TYPE_CANONICAL_MAP`** (module-level)

Mapping table from non-canonical names to SLA framework keys.
Idempotent — canonical values pass through.

**2. `normalize_instruction_type(raw)`** — the canonical mapper

```python
normalize_instruction_type("COMPLAINT")
# → "CUSTOMER_COMPLAINT"

normalize_instruction_type("information_request")  # case-insensitive
# → "GENERAL_INQUIRY"

normalize_instruction_type("CUSTOMER_COMPLAINT")  # already canonical
# → "CUSTOMER_COMPLAINT"

normalize_instruction_type("VENDOR_XYZ_2018")  # unknown
# → "VENDOR_XYZ_2018"  (passthrough; cockpit still displays it)
```

Properties:
- Idempotent: `normalize(normalize(x)) == normalize(x)`
- Case-insensitive on known keys
- Unknown values pass through (legacy / vendor / typo tolerance)
- `None` and empty pass through (caller decides placeholders)
- Non-strings (numbers, dicts) pass through

**3. `cims_vocabulary_map()`** — operator-facing reference

Returns a dict grouped by source vocabulary so operators (and
the React SPA) can render a reference table:

```python
{
    "capture": {"COMPLAINT": "CUSTOMER_COMPLAINT"},
    "nlp": {
        "INFORMATION_REQUEST": "GENERAL_INQUIRY",
        "COMPLAINT": "CUSTOMER_COMPLAINT",
    },
    "canonical": [
        "CUSTOMER_COMPLAINT", "GENERAL_INQUIRY",
        "DISPUTE_INVESTIGATION", "BILLING_ERROR",
        "REGULATORY_REPORTING",
    ],
    "rationale": "<one-line explanation>",
}
```

### `cims_instruction_trace` enriched

When the trace returns a capture record with an
`instruction_type`, it now also includes
`canonical_instruction_type` (a shallow-copy mutation of the
result dict — never touches the source records on disk):

```python
result = cims_instruction_trace("SESS-123")
# result["capture"]["instruction_type"]            == "COMPLAINT"
# result["capture"]["canonical_instruction_type"]  == "CUSTOMER_COMPLAINT"
```

The React SPA can join against SLA deadlines without
re-implementing the mapping. Same for any downstream consumer
of the trace API.

### `scripts/audit.py` — G194 added

`gate_cims_vocabulary_harmonized` locks the closure via 8
sub-checks:

1. `normalize_instruction_type` exists
2. Maps `COMPLAINT` → `CUSTOMER_COMPLAINT`
3. Maps `INFORMATION_REQUEST` → `GENERAL_INQUIRY`
4. Idempotent
5. Unknown values pass through
6. `cims_vocabulary_map` exists with required groups
7. **Every canonical target is a real key in SLA's
   `INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS`** — this is the
   critical structural check
8. `cims_instruction_trace` source mentions
   `canonical_instruction_type` (greppable enrichment proof)

### `tests/integration/test_cims_vocabulary_harmonization.py` (NEW)

13 tests across 8 sections:

1. Basic mappings
2. Canonical targets match SLA framework keys
3. Idempotency
4. Unknown / None / empty passthrough
5. Case-insensitive matching
6. `cims_vocabulary_map` structure
7. `cims_instruction_trace` enriched with canonical field
8. G194 liveness

### `PHASE_3_BACKLOG.md` — B-001 marked CLOSED

Original entry preserved for reference; resolution block added
at the top of the entry documenting the v10.303 fix.

### `data/audit_baselines.json` — G162 rebased 4018 → 4020

+2 CBK for cockpit_read vocabulary rationale + G194 audit gate
text mentioning "CBK Banking Act" regulatory framework
context.

---

## TDD red→green progression

- **Red phase:** 1P 12F. The one passing test was the
  passthrough check (trivial without any implementation).
- **Green phase 1 (mapper + vocab map):** 11P 2F.
- **Green phase 2 (trace enrichment):** 12P 1F (only G194
  remained).
- **Green phase 3 (G194 added):** 13P 0F.
- **Audit caught G162 drift** → +2 CBK, rebased to 4020.

---

## Real findings during this batch

1. **The vocabulary fragmentation is real but bounded.** Only
   two cross-engine mismatches matter today: `COMPLAINT` and
   `INFORMATION_REQUEST`. The other capture/NLP/SLA names
   either already match or live in separate semantic spaces
   (capture's `CARD_REQUEST` vs SLA's `DISPUTE_INVESTIGATION`
   are unrelated concepts, not synonyms).

2. **Engine rewrites would have broken byte-for-byte locks.**
   G182-G185 enforce that the CIMS engine vocabularies don't
   drift silently. Rewriting `COMPLAINT` → `CUSTOMER_COMPLAINT`
   inside `cims_omnichannel_capture.py` would trigger G182-G185
   failures and require regenerating the byte-baselines. The
   read-side translation layer avoids that entirely.

3. **The trace enrichment is a shallow copy, not in-place
   mutation.** `find_by_id` returns a reference to the
   in-memory record list. Mutating that reference would
   pollute subsequent calls and (depending on the
   `load_records` cache) potentially break read-only
   guarantees. Creating `capture = dict(capture)` before
   adding `canonical_instruction_type` keeps everything clean.

4. **Unknown-passthrough is a feature, not a bug.** Real-world
   data has vendor-specific names ("vendor_xyz_legacy_2018"),
   operator typos, and free-form entries. A strict mapper that
   raised on unknowns would crash the cockpit every time. The
   passthrough lets unknown values show up in the UI exactly
   as captured — operators can investigate or extend the map.

---

## Files changed

- `utils/cockpit_read.py` — 3 additions:
  `_CIMS_INSTRUCTION_TYPE_CANONICAL_MAP`,
  `normalize_instruction_type`, `cims_vocabulary_map` +
  `cims_instruction_trace` enrichment
- `scripts/audit.py` — G194 added and registered
- `data/audit_baselines.json` — G162 → 4020
- `tests/integration/test_cims_vocabulary_harmonization.py` — NEW (13 tests)
- `PHASE_3_BACKLOG.md` — B-001 marked CLOSED
- `CHANGELOG_v10.303.md` — this file

---

## Audit results

```
Score: 194/194 gates = 100.0% — PASS
```

---

## Platform state

- **Audit:** 194/194
- **Standards active:** 330/330
- **Pages:** 116 (no change)
- **Tiers:** 57 (no change)
- **Gates:** G1-G194 linear
- **Live cockpits:** 4 (all with HTTP endpoints + harmonized
  vocabulary)
- **HTTP endpoints (cockpit):** 17
- **Integration test suites:** 10 (was 9)
- **Integration tests passing:** 183/183
- **G162 baseline:** 4020

---

## React-readiness check

When the React SPA fetches
`/api/cockpit/cims/instruction-trace/{session_id}`, the
returned capture record now includes:

```json
{
  "instruction_type": "COMPLAINT",
  "canonical_instruction_type": "CUSTOMER_COMPLAINT",
  ...
}
```

React components can use `canonical_instruction_type` as a
join key against SLA deadline data without re-implementing
the mapping. Streamlit cockpit gets the same enrichment from
the same composer — single source of truth, two transports.

A future React-side admin page could call
`/api/cockpit/cims-vocabulary-map` (not yet exposed; trivial
to add when needed) to render the operator reference table.

---

## What didn't change

- No engine source files touched (G182-G185 locks intact)
- No new pages
- No new tiers
- Memory + live-data files untouched

This was a **translation layer + backlog closure** batch.

---

## Next Phase 3 arc options

Updated list:

1. ~~CORS + production deploy config~~ — v10.299 ✓
2. ~~Credit live cockpit~~ — v10.300 ✓
3. ~~Compliance live cockpit~~ — v10.301 ✓
4. ~~TreasuryDashboardEngine wiring~~ — v10.302 ✓
5. ~~CIMS vocabulary harmonization (B-001)~~ — v10.303 ✓ (this batch)
6. **PG migration push** — toward 75/79 (95%). 31 tables to
   migrate; each is a small dual-write toggle + migration
   script + table-specific G163 test.
7. **Cash forecast composer wiring** — close the 13-week
   cash projection placeholder in Treasury cockpit tab 6
   (same shape as v10.302's dashboard wiring).
8. **Audit trail composer** — close the audit-trail
   placeholders in all four cockpit pages' last tab.
9. **CIMS vocabulary expansion** — extend the canonical map
   to cover state-name overlaps (`COMPLETED` vs `FULFILLED`)
   when real-world data flows surface joins that need them.
   Logged but not urgent — instruction-type was the binding
   constraint per B-001.

Option 7 (cash forecast wiring) is the natural next move —
it's identical in shape to v10.302's dashboard wiring and
would close another v10.296 placeholder. Compresses fast.

The Phase 3 backlog is now lighter than it was when we
started: B-001 (oldest, hardest) closed, leaving only B-002
(admin label, cosmetic), B-003 (engine init parameters,
deferred), B-004 (pytest in audit env, mitigated), B-005
(docs), and B-006 (FastAPI in audit env, mitigated). Real
backlog debt down from 6 items to 5 items, with the
highest-leverage one off the list.
