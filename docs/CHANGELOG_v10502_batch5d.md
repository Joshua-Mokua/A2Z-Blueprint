# CHANGELOG_v10502_batch5d.md

**Batch:** v10.502 Stage C Arc D2 Batch 5d
**Date:** 2026-06-10
**Authors:** Joshua Mokua + Claude
**Closure:** CANONICAL_DEPENDENCY_MAP + TELEMETRY_MAP reality-checked; G391 + G392 audit gates authored
**Stage C Arc D2 status after this batch:** 3 of 4 batches complete (5b, 5c, 5d). Remaining: 5e (final D2 triple).

---

## Summary

Third Arc D2 pairing — relation-shaped artifacts. Both already had partial coverage via G384 (the v10.498 Stage C Batch 1b gate enforcing D2 + T2 simultaneously). Batch 5d extends coverage to D5 (no cycles) and T1+T2 (event-naming discipline).

Two new gates, both run strict (no TRANSITIONAL ceiling), both pass post-corrections:

- **G391** (`gate_canonical_dependency_map_sync`) — Tarjan SCC for cycle detection + self-loop INFO surfacing. KNOWN_CYCLES allowlist captures 2 multi-module SCCs that exist in the current import graph (5-module and 2-module). Future arcs drain the allowlist.
- **G392** (`gate_telemetry_event_naming`) — AST scan of `utils/api*.py` for `_audit()` literals; every actual event must appear in TELEMETRY_MAP. 4 missing events added in this batch; gate now passes strictly.

---

## Files changed

| Path | Action |
|---|---|
| `scripts/audit.py` | NEW `gate_canonical_dependency_map_sync` (~180 LOC) + NEW `gate_telemetry_event_naming` (~110 LOC) + both registered in GATES |
| `docs/architecture/TELEMETRY_MAP.md` | 4 surgical edits — Auth events 3→7, DOMAIN list extended, cookie/bearer fix, Stage C planned gates Status column |
| `docs/architecture/CANONICAL_DEPENDENCY_MAP.md` | UNCHANGED — artifact claims hold up; only mechanical enforcement was missing, closed via G391 |
| `docs/architecture/GOVERNANCE_REALITY_INDEX.md` | Both artifacts → `ACTIVE`; new Batch 5d CGR1 correction |
| `docs/architecture/POLICY_GAPS.md` | Arc D status row updated |
| `docs/architecture/REVIVAL_LEDGER.md` | New top entry (RL1) |
| `docs/continuity/SESSION_BOOTSTRAP.md` | Gate count 391 → 393; commits + workstreams |
| `app.py` | `_APP_VERSION` → `v10.502-batch5d-2026.06.10` |
| `docs/CHANGELOG_v10502_batch5d.md` | NEW — this file |
| `tests/test_gate_dependency_and_telemetry.py` | NEW — 17 regression tests (9 G391 + 8 G392) |

---

## The four findings

### Finding 1 — `gate_canonical_dependency_map_sync` named but missing

D4 doctrine of CANONICAL_DEPENDENCY_MAP cited the gate by name. Same-turn grep: zero hits. Same fabrication-by-omission as Batch 5b's G388. **Closed** — G391 authored.

### Finding 2 — Import graph has 2 SCCs + 32 self-loops

```
Multi-module SCCs:
  ['actuals_engine', 'bsc_engine', 'core', 'core_audit', 'core_kpi']  (5-module)
  ['credit_doctrine_audit', 'credit_section_audit_engine']            (2-module)
Self-loops: 32 (api_*, auth_jwt, db, core_audit, ...)
```

Allowlist captures the 2 SCCs; self-loops surface as INFO with doctrine-exemption note (Python import semantics).

### Finding 3 — `gate_telemetry_event_naming` named but missing

TELEMETRY_MAP listed 5 Stage-C-planned gates; only `gate_event_bus_publisher_purity` (G384) existed. **Closed** — G392 authored. 3 others remain planned for future arcs.

### Finding 4 — 4 events emitted by code, not documented

`API_LOGIN_FORCE_PW`, `API_AUTH_WHOAMI_DETAILED`, `API_PASSWORD_CHANGE_SUCCESS`, `API_PASSWORD_CHANGE_FAILED`. All 4 added to TELEMETRY_MAP Auth section. G392 now passes.

---

## The two new gates

### G391 — canonical_dependency_map_sync

```
Run: python scripts\audit.py --gate G391
Expected: 1/1 gates = 100.0% — PASS
Summary: modules=528 multi_module_cycles=2 (allowed=2, new=0) self_loops=32
```

Fails if a NEW multi-module cycle appears outside the KNOWN_CYCLES allowlist.

### G392 — telemetry_event_naming

```
Run: python scripts\audit.py --gate G392
Expected: 1/1 gates = 100.0% — PASS
Summary: documented=40 actual=24 undeclared=0 violations=0
```

Fails if any future `_audit("API_X", ...)` call uses a literal event name not in TELEMETRY_MAP.

---

## Operator extraction instructions

Delivery ZIP whose root contains `_batch5d_payload/`. Tree:

```
_batch5d_payload/
  app.py
  scripts/
    audit.py
  docs/
    architecture/
      GOVERNANCE_REALITY_INDEX.md
      POLICY_GAPS.md
      REVIVAL_LEDGER.md
      TELEMETRY_MAP.md
    continuity/
      SESSION_BOOTSTRAP.md
    CHANGELOG_v10502_batch5d.md
  tests/
    test_gate_dependency_and_telemetry.py
```

Note: CANONICAL_DEPENDENCY_MAP.md is **not** in the payload because it requires no edits — its claims held up under reality-check; only G391 was missing, and that's authored in scripts/audit.py.

### Step 1 — Extract

Open ZIP via Windows GUI → Extract All → browse to `C:\Users\Joshua\Desktop\A2Z Blue Print\a2z` → Extract.

```cmd
dir _batch5d_payload
```

### Step 2 — Copy 9 files

```cmd
copy /Y _batch5d_payload\app.py app.py
copy /Y _batch5d_payload\scripts\audit.py scripts\audit.py
copy /Y _batch5d_payload\docs\architecture\TELEMETRY_MAP.md docs\architecture\TELEMETRY_MAP.md
copy /Y _batch5d_payload\docs\architecture\GOVERNANCE_REALITY_INDEX.md docs\architecture\GOVERNANCE_REALITY_INDEX.md
copy /Y _batch5d_payload\docs\architecture\POLICY_GAPS.md docs\architecture\POLICY_GAPS.md
copy /Y _batch5d_payload\docs\architecture\REVIVAL_LEDGER.md docs\architecture\REVIVAL_LEDGER.md
copy /Y _batch5d_payload\docs\continuity\SESSION_BOOTSTRAP.md docs\continuity\SESSION_BOOTSTRAP.md
copy /Y _batch5d_payload\docs\CHANGELOG_v10502_batch5d.md docs\CHANGELOG_v10502_batch5d.md
copy /Y _batch5d_payload\tests\test_gate_dependency_and_telemetry.py tests\test_gate_dependency_and_telemetry.py
```

Expect `1 file(s) copied.` nine times.

### Step 3 — Run the two new gates

```cmd
python scripts\audit.py --gate G391
python scripts\audit.py --gate G392
```

Both should report `1/1 gates = 100.0% — PASS`.

### Step 4 — Run the new test suite (17 tests)

```cmd
python -m pytest tests\test_gate_dependency_and_telemetry.py -v
```

Expect: **17 passed**.

### Step 5 — Full regression (Phase 2 + 5b + 5c + 5d = 74 tests)

```cmd
python -m pytest tests\test_validate_password_policy.py tests\test_rate_limit_auth.py tests\test_gate_canonical_truth_registry_sync.py tests\test_gate_api_and_data_dictionary.py tests\test_gate_dependency_and_telemetry.py -v
```

Expect: **74 passed**.

### Step 6 — Verify doctrine landed (ASCII-only findstr patterns)

```cmd
findstr /n "393 total" docs\continuity\SESSION_BOOTSTRAP.md
findstr /n /c:"v10.502 Stage C Arc D2 Batch 5d" docs\architecture\GOVERNANCE_REALITY_INDEX.md
findstr /n /c:"API_LOGIN_FORCE_PW" docs\architecture\TELEMETRY_MAP.md
findstr /n /c:"def gate_canonical_dependency_map_sync" scripts\audit.py
findstr /n /c:"def gate_telemetry_event_naming" scripts\audit.py
```

Expectations:
- First: 1 match (gate count)
- Second: at least 2 matches (CGR1 correction header + chronological reading order)
- Third: 1 match (the new event row)
- Fourth + fifth: 1 match each (function definitions)

### Step 7 — Clean up

```cmd
rmdir /S /Q _batch5d_payload
```

### Step 8 — Stage and commit

```cmd
git add app.py scripts\audit.py docs\architecture\TELEMETRY_MAP.md docs\architecture\GOVERNANCE_REALITY_INDEX.md docs\architecture\POLICY_GAPS.md docs\architecture\REVIVAL_LEDGER.md docs\continuity\SESSION_BOOTSTRAP.md docs\CHANGELOG_v10502_batch5d.md tests\test_gate_dependency_and_telemetry.py
git status
git commit -m "v10.502 Stage C Arc D2 Batch 5d - G391 + G392 + CANONICAL_DEPENDENCY_MAP and TELEMETRY_MAP ACTIVE"
```

Expect 2 new + 7 modified files staged.

### Step 9 — Push deferred

Push happens at Arc D phase boundary, after 5e (and any 5f). Local commit only.

---

## Arc D2 progress

| Batch | Pairing | Status | Tests |
|---|---|---|---|
| 5b | CANONICAL_TRUTH_REGISTRY + GOVERNANCE_CLASSIFICATION_REGISTRY | CLOSED | 11 (G388) |
| 5c | API_CONTRACTS + DATA_DICTIONARY | CLOSED `6085eda` | 16 (G389+G390) |
| 5d (this) | CANONICAL_DEPENDENCY_MAP + TELEMETRY_MAP | **CLOSED** | **17 (G391+G392)** |
| 5e | ORGANS_REGISTRY + DIGITAL_TWIN_ARCHITECTURE + RESILIENCE_AND_CERTIFICATION_GOVERNANCE | next | — |
| 5f (optional) | Ledger backfill | end of D2 | — |

Total Arc D2 tests so far: 44 across 3 batches.

## Next batch

**v10.502 Stage C Arc D2 Batch 5e — final D2 triple.** ORGANS_REGISTRY + DIGITAL_TWIN_ARCHITECTURE + RESILIENCE_AND_CERTIFICATION_GOVERNANCE. The biggest artifacts left in the queue.

DIGITAL_TWIN_ARCHITECTURE and RESILIENCE_AND_CERTIFICATION_GOVERNANCE are both already pre-classified TRANSITIONAL (provisional) — they may stay TRANSITIONAL even post-reality-check if their aspirational parts substantially outweigh their ACTIVE parts. ORGANS_REGISTRY is "ACTIVE (provisional)" — could go either way.

Expected new gate IDs: **G393, G394, G395** (one per artifact, depending on what each warrants).
