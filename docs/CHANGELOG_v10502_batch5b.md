# CHANGELOG_v10502_batch5b.md

**Batch:** v10.502 Stage C Arc D2 Batch 5b
**Date:** 2026-06-10
**Authors:** Joshua Mokua + Claude
**Closure:** CANONICAL_TRUTH_REGISTRY + GOVERNANCE_CLASSIFICATION_REGISTRY reality-checked; G388 audit gate authored
**Previous batch commit:** `72b1f1f` (v10.502 Stage C Arc D1 Batch 5a — doctrine baseline alignment, local-only)
**Stage C Arc D2 status after this batch:** 1 of 4 batches complete (5b). Remaining: 5c, 5d, 5e.

---

## Summary

First gate-authoring batch of Stage C Arc D2. Same-turn inspection of CANONICAL_TRUTH_REGISTRY.md and GOVERNANCE_CLASSIFICATION_REGISTRY.md surfaced 5 findings; the most significant is a textbook CGR1 stated-vs-enforced gap (D4 doctrine cited `gate_canonical_truth_registry_sync` by name, but the gate didn't exist in `scripts/audit.py`). Batch 5b closes that gap by authoring the gate, adds an 11-test regression suite, makes 4 surgical corrections inside CANONICAL_TRUTH_REGISTRY, and promotes both artifacts to ACTIVE.

---

## Files changed

| Path | Action |
|---|---|
| `scripts/audit.py` | NEW `gate_canonical_truth_registry_sync` function (~120 LOC, just before `GATES = [`) + new `("G388", ...)` entry in GATES dispatch table |
| `docs/architecture/CANONICAL_TRUTH_REGISTRY.md` | 4 surgical edits — Auth Conflict rule + Auth Critical drift + User identity Conflict/Enforcement/Classification + Frontend domain split |
| `docs/architecture/GOVERNANCE_REALITY_INDEX.md` | Classification table: both registries promoted from `ACTIVE (provisional)` to `ACTIVE`; new Batch 5b CGR1 correction appended; chronological reading order note updated |
| `docs/architecture/POLICY_GAPS.md` | Stage C Arc D status updated |
| `docs/architecture/REVIVAL_LEDGER.md` | New top entry per RL1 append-only |
| `docs/continuity/SESSION_BOOTSTRAP.md` | Gate count 388 → 389; Stage C commits row extended with 5b; active workstreams updated |
| `app.py` | `_APP_VERSION` bumped to `v10.502-batch5b-2026.06.10` |
| `docs/CHANGELOG_v10502_batch5b.md` | NEW — this file |
| `tests/test_gate_canonical_truth_registry_sync.py` | NEW — 11-test regression suite for G388 |

---

## The five findings

### Finding 1 — `gate_canonical_truth_registry_sync` named but missing

D4 doctrine of CANONICAL_TRUTH_REGISTRY.md stated: "Audit gate `gate_canonical_truth_registry_sync` enforces this." Same-turn `grep -n "gate_canonical_truth_registry_sync" scripts/audit.py` returned zero hits. **Closed** by authoring the gate.

### Finding 2 — `data/users.json` narrative correction

Pre-compaction summary said "intentionally TRACKED." Same-turn inspection: `.gitignore:52`, `git check-ignore -v` confirms gitignored, `git ls-files` returns empty, `git log` returns empty. The file is gitignored AND not in git history. The Phase 2 Arc C / Batch 4c work updated the .gitignore comment to explain *why* the file is gitignored — narrative around the closure was confused; the closure itself stands. **Closed** by recording the correction; G388's RUNTIME_GITIGNORED allowlist explicitly handles this case.

### Finding 3 — Three stale entries inside CANONICAL_TRUTH_REGISTRY

(a) Auth domain Conflict rule "Cookie source wins over Bearer header" — WRONG since Phase 1 Batch 3a (Bearer-header only). **Corrected.**
(b) Auth domain Critical drift "name collision must be resolved in Wave 2" — already RESOLVED in v10.498 Stage C Batch 1b. **Corrected.**
(c) User identity domain "Password is SHA-256 today with bcrypt migration on successful login" — migration COMPLETE in Phase 1 Batch 3c. **Corrected**, Enforcement column extended with Phase 2 closures.

### Finding 4 — Frontend domain conflated ACTIVE and ASPIRATIONAL parts

Classification claimed `canonical (post v10.497 P0 shadcn pivot)` but shadcn pivot was rolled back per Batch 2a-shadcn correction. **Corrected** — domain split into explicit ACTIVE (bespoke React primitives + tokens.ts + Tailwind config + index.css) and ASPIRATIONAL (shadcn paths).

### Finding 5 — GOVERNANCE_CLASSIFICATION_REGISTRY held up

No drift. G1-G5 doctrine sound; classification mechanism in active use; "Open registry items" section is forward-looking, not drift. **Promoted to ACTIVE** without edits.

---

## The gate

`gate_canonical_truth_registry_sync` (G388):

- Parses `Authoritative source` and `Canonical interface` rows from CANONICAL_TRUTH_REGISTRY.md via two regexes
- Extracts every backticked path-shaped value
- Skips bare identifiers without `/`
- Expands globs (`*`, `?`) and requires at least one filesystem match
- Honors `RUNTIME_GITIGNORED` allowlist (currently: `data/users.json`)
- Honors `SHADCN_ASPIRATIONAL` allowlist (currently: `frontend/web/components.json`, `frontend/web/src/components/ui/*`, `lib/cn`)
- Reports remaining missing pointers as violations
- Handles missing-registry-file case with clean failure (not crash)

Post-correction registry: **82 paths checked, 78 resolved, 0 violations, PASS.**

11 regression tests in `tests/test_gate_canonical_truth_registry_sync.py` — all green in sandbox verification.

---

## Operator extraction instructions

The delivery is a ZIP whose root contains `_batch5b_payload/` per Trap #14. Tree:

```
_batch5b_payload/
  app.py
  scripts/
    audit.py
  docs/
    architecture/
      CANONICAL_TRUTH_REGISTRY.md
      GOVERNANCE_REALITY_INDEX.md
      POLICY_GAPS.md
      REVIVAL_LEDGER.md
    continuity/
      SESSION_BOOTSTRAP.md
    CHANGELOG_v10502_batch5b.md
  tests/
    test_gate_canonical_truth_registry_sync.py
```

### Step 1 — Extract at the repo root

Open the ZIP via Windows GUI → Extract All → browse to `C:\Users\Joshua\Desktop\A2Z Blue Print\a2z` → Extract. Verify:

```cmd
dir _batch5b_payload
```

Expect `app.py`, `scripts\`, `docs\`, `tests\`.

### Step 2 — Copy the 9 files into place

Each command starts with `copy /Y`. Lines starting with `::` are cmd comments.

```cmd
copy /Y _batch5b_payload\app.py app.py
copy /Y _batch5b_payload\scripts\audit.py scripts\audit.py
copy /Y _batch5b_payload\docs\architecture\CANONICAL_TRUTH_REGISTRY.md docs\architecture\CANONICAL_TRUTH_REGISTRY.md
copy /Y _batch5b_payload\docs\architecture\GOVERNANCE_REALITY_INDEX.md docs\architecture\GOVERNANCE_REALITY_INDEX.md
copy /Y _batch5b_payload\docs\architecture\POLICY_GAPS.md docs\architecture\POLICY_GAPS.md
copy /Y _batch5b_payload\docs\architecture\REVIVAL_LEDGER.md docs\architecture\REVIVAL_LEDGER.md
copy /Y _batch5b_payload\docs\continuity\SESSION_BOOTSTRAP.md docs\continuity\SESSION_BOOTSTRAP.md
copy /Y _batch5b_payload\docs\CHANGELOG_v10502_batch5b.md docs\CHANGELOG_v10502_batch5b.md
copy /Y _batch5b_payload\tests\test_gate_canonical_truth_registry_sync.py tests\test_gate_canonical_truth_registry_sync.py
```

Expect `1 file(s) copied.` nine times.

### Step 3 — Run the new G388 gate directly

```cmd
python scripts\audit.py --gate G388
```

Expected: `1/1 gates = 100.0% — PASS`, with summary `checked=82 resolved=78 violations=0` and informational notes about gitignored/aspirational paths.

### Step 4 — Run the new test suite

```cmd
python -m pytest tests\test_gate_canonical_truth_registry_sync.py -v
```

Expect: **11 passed**.

### Step 5 — Run the Phase 2 regression suite (confirms no breakage)

```cmd
python -m pytest tests\test_validate_password_policy.py tests\test_rate_limit_auth.py tests\test_gate_canonical_truth_registry_sync.py -v
```

Expect: **41 passed** (30 Phase 2 + 11 Batch 5b).

### Step 6 — Verify doctrine landed (ASCII-only findstr patterns per Batch 5a em-dash lesson)

```cmd
findstr /n "389 total" docs\continuity\SESSION_BOOTSTRAP.md
findstr /n /c:"v10.502 Stage C Arc D2 Batch 5b" docs\architecture\GOVERNANCE_REALITY_INDEX.md
findstr /n /c:"Bearer Authorization header only" docs\architecture\CANONICAL_TRUTH_REGISTRY.md
findstr /n /c:"gate_canonical_truth_registry_sync" scripts\audit.py
```

Expectations:
- First: at least 1 match (gate count post-G388)
- Second: at least 2 matches (the new section header + chronological reading order note)
- Third: 1 match (the corrected Auth domain Conflict rule)
- Fourth: at least 3 matches (function definition, GATES registry entry, docstring references — all ASCII)

### Step 7 — Clean up

```cmd
rmdir /S /Q _batch5b_payload
```

### Step 8 — Stage and commit

```cmd
git add app.py scripts\audit.py docs\architecture\CANONICAL_TRUTH_REGISTRY.md docs\architecture\GOVERNANCE_REALITY_INDEX.md docs\architecture\POLICY_GAPS.md docs\architecture\REVIVAL_LEDGER.md docs\continuity\SESSION_BOOTSTRAP.md docs\CHANGELOG_v10502_batch5b.md tests\test_gate_canonical_truth_registry_sync.py
git status
git commit -m "v10.502 Stage C Arc D2 Batch 5b - G388 gate_canonical_truth_registry_sync + 4 registry corrections"
```

Expect 2 new + 7 modified files staged.

### Step 9 — Push deferred

Push happens at Arc D phase boundary, after 5c-5e (and any 5f). Local commit only for now.

---

## Stage C Arc D2 progress

| Batch | Pairing | Status |
|---|---|---|
| 5b (this) | CANONICAL_TRUTH_REGISTRY + GOVERNANCE_CLASSIFICATION_REGISTRY | **CLOSED** — G388, 4 registry corrections, 11 tests |
| 5c | API_CONTRACTS + DATA_DICTIONARY | pending |
| 5d | CANONICAL_DEPENDENCY_MAP + TELEMETRY_MAP | pending |
| 5e | ORGANS_REGISTRY + DIGITAL_TWIN_ARCHITECTURE + RESILIENCE_AND_CERTIFICATION_GOVERNANCE | pending |
| 5f (optional) | Ledger backfill | deferred to Arc D2 end |

## Next batch

**v10.502 Stage C Arc D2 Batch 5c — API_CONTRACTS + DATA_DICTIONARY reality-check.**

Expected scope: same pattern as 5b — same-turn inspection of both artifacts against the code they describe, 1-2 new audit gates if mechanical enforcement gaps exist, surgical doctrine corrections if drift found, classification updates, standard doctrine sync, regression tests per new gate.

API_CONTRACTS is likely the meatier of the two — it describes the 22 FastAPI endpoints surface. DATA_DICTIONARY is data-shape-focused, smaller scope. Expected new gate IDs: G389 (and possibly G390 if both warrant separate enforcement).
