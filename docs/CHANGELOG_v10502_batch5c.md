# CHANGELOG_v10502_batch5c.md

**Batch:** v10.502 Stage C Arc D2 Batch 5c
**Date:** 2026-06-10
**Authors:** Joshua Mokua + Claude
**Closure:** API_CONTRACTS + DATA_DICTIONARY reality-checked; G389 + G390 audit gates authored
**Stage C Arc D2 status after this batch:** 2 of 4 batches complete (5b, 5c). Remaining: 5d, 5e.

---

## Summary

Second Arc D2 pairing — interface-shaped artifacts. Same-turn inspection found very different shapes of drift in the two artifacts:

- **API_CONTRACTS** had a 3.5x numerical drift — 81 endpoints documented vs **276 actual** endpoints across 16 router files. Plus 3 stale Auth-domain entries (cookie/Bearer, missing change-password, missing whoami-detailed).
- **DATA_DICTIONARY** had 4 specific drift entries out of 73 rows — locally fixable in a single batch.

The two new gates reflect this difference:
- **G389** runs in TRANSITIONAL mode — surfaces the gap as INFO, FAILS only if the actual surface grows beyond a ceiling of 300. Substantive rewrite of API_CONTRACTS (documenting all 276) is deferred.
- **G390** runs in strict mode — every `git-tracked` / `gitignored` claim must match `git check-ignore` / `git ls-files` output exactly. Post-correction: 74/74 rows pass.

---

## Files changed

| Path | Action |
|---|---|
| `scripts/audit.py` | NEW `gate_api_contract_inventory` (~130 LOC) + NEW `gate_data_dictionary_tracking_claims` (~115 LOC) + both registered in GATES dispatch |
| `docs/architecture/API_CONTRACTS.md` | 5 surgical edits — Status field → `transitional`, Last-updated bumped, Authoritative source expanded, Endpoint inventory section header rewritten with doctrine-debt declaration, Auth domain table (3 row corrections + 2 new rows) |
| `docs/architecture/DATA_DICTIONARY.md` | 5 surgical edits — users.json / jwt_blocklist.json / super_user_registry.json / observability_metrics.json rows + DD5 PII doctrine line |
| `docs/architecture/GOVERNANCE_REALITY_INDEX.md` | Classification table: API_CONTRACTS → `TRANSITIONAL`, DATA_DICTIONARY → `ACTIVE`; new Batch 5c CGR1 correction appended; chronological reading order extended |
| `docs/architecture/POLICY_GAPS.md` | Stage C Arc D status row updated |
| `docs/architecture/REVIVAL_LEDGER.md` | New top entry (RL1 append-only) |
| `docs/continuity/SESSION_BOOTSTRAP.md` | Gate count 389 → 391; Stage C commits row + active workstreams updated |
| `app.py` | `_APP_VERSION` → `v10.502-batch5c-2026.06.10` |
| `docs/CHANGELOG_v10502_batch5c.md` | NEW — this file |
| `tests/test_gate_api_and_data_dictionary.py` | NEW — 16 regression tests (8 per gate) |

---

## The three findings

### Finding 1 — API_CONTRACTS documents 81 endpoints; actual surface is 276

AST walk of `utils/api*.py` (all 16 router files):

```
   81  utils/api.py
    1  utils/api_branding.py
    5  utils/api_capacity_feedback.py
   29  utils/api_cascade.py
    0  utils/api_client.py
   25  utils/api_cockpit.py
   21  utils/api_compliance.py
    8  utils/api_crud.py
    0  utils/api_gateway_developer_portal.py
   16  utils/api_legal.py
   24  utils/api_product.py
   11  utils/api_resource_optimization.py
    1  utils/api_roles.py
   19  utils/api_strategy.py
    0  utils/api_telemetry.py
   43  utils/api_treasury.py
  ----
  276  TOTAL
```

The gap accumulated during the Stage-C-paused period. **Closed mechanically** (G389 TRANSITIONAL ceiling 300, INFO summary always emits counts) + **closed surgically** (5 Auth-domain row corrections). **Substantive rewrite deferred** to a future arc.

### Finding 2 — DATA_DICTIONARY had 4 incorrect tracking claims

| Path | Claim | Reality | Action |
|---|---|---|---|
| `data/users.json` | git-tracked | gitignored | → **gitignored** with `.gitignore:52` + GAP-002 cross-ref |
| `data/jwt_blocklist.json` | git-tracked | gitignored (file does not exist; runtime-generated) | → **gitignored** with runtime-generated note |
| `data/super_user_registry.json` | git-tracked | neither tracked nor ignored; file does not exist | → **ORPHANED** with future-arc note |
| `data/observability_metrics.json` | "TBD (likely gitignored)" | tracked | → **git-tracked** |

DD5 PII doctrine line also corrected (users.json "in git" claim was wrong). G390 prevents regression.

### Finding 3 — Both gates registered and tested

- G389 `gate_api_contract_inventory` — AST + regex; TRANSITIONAL ceiling; INFO surfacing.
- G390 `gate_data_dictionary_tracking_claims` — `git check-ignore` + `git ls-files` per row.

16/16 regression tests green.

---

## The two new gates

### G389 — api_contract_inventory

```
Run: python scripts\audit.py --gate G389
Expected: 1/1 gates = 100.0% — PASS
Summary: documented=83 actual=276 undocumented=195 (TRANSITIONAL ceiling 300)
```

INFO emission shows first 5 undocumented endpoints + documented_but_missing list. INFO violations are filtered out by the `passed` check; gate FAILS only if `actual > 300` (ceiling).

### G390 — data_dictionary_tracking_claims

```
Run: python scripts\audit.py --gate G390
Expected: 1/1 gates = 100.0% — PASS
Summary: rows_checked=74 rows_ok=74 violations=0
```

Strict mode: any future row added with a wrong git-tracked / gitignored claim will FAIL the gate.

---

## Operator extraction instructions

Delivery ZIP whose root contains `_batch5c_payload/`. Tree:

```
_batch5c_payload/
  app.py
  scripts/
    audit.py
  docs/
    architecture/
      API_CONTRACTS.md
      DATA_DICTIONARY.md
      GOVERNANCE_REALITY_INDEX.md
      POLICY_GAPS.md
      REVIVAL_LEDGER.md
    continuity/
      SESSION_BOOTSTRAP.md
    CHANGELOG_v10502_batch5c.md
  tests/
    test_gate_api_and_data_dictionary.py
```

### Step 1 — Extract

Open ZIP via Windows GUI → Extract All → browse to `C:\Users\Joshua\Desktop\A2Z Blue Print\a2z` → Extract. Then verify:

```cmd
dir _batch5c_payload
```

### Step 2 — Copy 10 files

```cmd
copy /Y _batch5c_payload\app.py app.py
copy /Y _batch5c_payload\scripts\audit.py scripts\audit.py
copy /Y _batch5c_payload\docs\architecture\API_CONTRACTS.md docs\architecture\API_CONTRACTS.md
copy /Y _batch5c_payload\docs\architecture\DATA_DICTIONARY.md docs\architecture\DATA_DICTIONARY.md
copy /Y _batch5c_payload\docs\architecture\GOVERNANCE_REALITY_INDEX.md docs\architecture\GOVERNANCE_REALITY_INDEX.md
copy /Y _batch5c_payload\docs\architecture\POLICY_GAPS.md docs\architecture\POLICY_GAPS.md
copy /Y _batch5c_payload\docs\architecture\REVIVAL_LEDGER.md docs\architecture\REVIVAL_LEDGER.md
copy /Y _batch5c_payload\docs\continuity\SESSION_BOOTSTRAP.md docs\continuity\SESSION_BOOTSTRAP.md
copy /Y _batch5c_payload\docs\CHANGELOG_v10502_batch5c.md docs\CHANGELOG_v10502_batch5c.md
copy /Y _batch5c_payload\tests\test_gate_api_and_data_dictionary.py tests\test_gate_api_and_data_dictionary.py
```

Expect `1 file(s) copied.` ten times.

### Step 3 — Run the two new gates directly

```cmd
python scripts\audit.py --gate G389
python scripts\audit.py --gate G390
```

Expected: both `1/1 gates = 100.0% — PASS`.

### Step 4 — Run the new test suite (16 tests)

```cmd
python -m pytest tests\test_gate_api_and_data_dictionary.py -v
```

Expect: **16 passed**.

### Step 5 — Full regression (Phase 2 + Batch 5b + Batch 5c)

```cmd
python -m pytest tests\test_validate_password_policy.py tests\test_rate_limit_auth.py tests\test_gate_canonical_truth_registry_sync.py tests\test_gate_api_and_data_dictionary.py -v
```

Expect: **57 passed** (30 Phase 2 + 11 Batch 5b + 16 Batch 5c).

### Step 6 — Verify doctrine landed (ASCII-only findstr patterns)

```cmd
findstr /n "391 total" docs\continuity\SESSION_BOOTSTRAP.md
findstr /n /c:"v10.502 Stage C Arc D2 Batch 5c" docs\architecture\GOVERNANCE_REALITY_INDEX.md
findstr /n /c:"81 endpoints documented; 276 actual" docs\architecture\API_CONTRACTS.md
findstr /n /c:"data/super_user_registry.json" docs\architecture\DATA_DICTIONARY.md
findstr /n /c:"def gate_api_contract_inventory" scripts\audit.py
findstr /n /c:"def gate_data_dictionary_tracking_claims" scripts\audit.py
```

Expectations:
- First: 1 match
- Second: at least 2 matches (table entry + section header)
- Third: 1 match (the doctrine-debt declaration)
- Fourth: 1 match (ORPHANED row)
- Fifth + sixth: 1 match each (function definitions)

### Step 7 — Clean up

```cmd
rmdir /S /Q _batch5c_payload
```

### Step 8 — Stage and commit

```cmd
git add app.py scripts\audit.py docs\architecture\API_CONTRACTS.md docs\architecture\DATA_DICTIONARY.md docs\architecture\GOVERNANCE_REALITY_INDEX.md docs\architecture\POLICY_GAPS.md docs\architecture\REVIVAL_LEDGER.md docs\continuity\SESSION_BOOTSTRAP.md docs\CHANGELOG_v10502_batch5c.md tests\test_gate_api_and_data_dictionary.py
git status
git commit -m "v10.502 Stage C Arc D2 Batch 5c - G389 + G390 + API_CONTRACTS TRANSITIONAL + DATA_DICTIONARY ACTIVE"
```

Expect 2 new + 8 modified files staged.

### Step 9 — Push deferred

Push happens at Arc D phase boundary, after 5d, 5e, and any 5f. Local commit only.

---

## Stage C Arc D2 progress

| Batch | Pairing | Status | Tests added |
|---|---|---|---|
| 5b | CANONICAL_TRUTH_REGISTRY + GOVERNANCE_CLASSIFICATION_REGISTRY | CLOSED | 11 (G388) |
| 5c (this) | API_CONTRACTS + DATA_DICTIONARY | **CLOSED** | **16 (G389+G390)** |
| 5d | CANONICAL_DEPENDENCY_MAP + TELEMETRY_MAP | pending | — |
| 5e | ORGANS_REGISTRY + DIGITAL_TWIN_ARCHITECTURE + RESILIENCE_AND_CERTIFICATION_GOVERNANCE | pending | — |
| 5f (optional) | Ledger backfill | deferred to Arc D2 end | — |

## Classification table post-5c

- ACTIVE (4 + 4 promoted): ROLE_GOVERNANCE, RBAC_MATRIX, FRONTEND_GOVERNANCE, AI_GOVERNANCE (TRANSITIONAL), SYSTEM_CONSTITUTION, REVIVAL_LEDGER, CHANGELOG_MASTER, OPERATIONAL_PROTOCOL, POLICY_GAPS, GOVERNANCE_REALITY_INDEX, **CANONICAL_TRUTH_REGISTRY (5b)**, **GOVERNANCE_CLASSIFICATION_REGISTRY (5b)**, **DATA_DICTIONARY (5c)**
- TRANSITIONAL: AI_GOVERNANCE, RESILIENCE_AND_CERTIFICATION_GOVERNANCE, DIGITAL_TWIN_ARCHITECTURE (provisional), **API_CONTRACTS (5c — substantive rewrite deferred)**
- ACTIVE (provisional, awaiting 5d-5e): CANONICAL_DEPENDENCY_MAP, TELEMETRY_MAP, ORGANS_REGISTRY

## Next batch

**v10.502 Stage C Arc D2 Batch 5d — CANONICAL_DEPENDENCY_MAP + TELEMETRY_MAP reality-check.**

Both artifacts already have partial G384 coverage (D2 + T2 respectively per the v10.498 Batch 1b enforcement). Expected scope: extend or supplement G384's coverage to validate the artifacts' broader claims, surface stale entries, classify.

Expected new gate IDs: G391, possibly G392. Whether two distinct gates or one combined depends on whether the two artifacts share enforcement surface (likely they do — dependency map and telemetry map both describe relations between modules).
