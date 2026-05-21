# Canonical Write-Bridge — Design Document

**Version anchor:** v10.379 (May 2026)
**Per:** Constitutional §5.2 (Central BSC Integration Engine)
**Companion to:** `A2Z_GOVERNANCE_CONSTITUTION_INTERNAL_v10.377.md`, `CUSTOMER_MASTER_MERGE_v10.378.md`

> "Lets have our virtual bank unify how all KPIs flow, test all modules and ensure every staff works and is measured." — Joshua

v10.377 established the contract; v10.378 added the customer recognition layer; **v10.379 makes canonical engines actually flow into `bsc_actuals_*.json`**. This closes the last arrow in the constitutional data flow:

```
Source (CBS)
    ↓
Staging (canonical engines: pbt_computation, customer_pbt_allocator, ...)
    ↓
Transformation (universal records via v10.377 unifier)
    ↓
Clean (UniversalBSCRecord with validated contract fields)
    ↓
BSC Integration (THIS MODULE — v10.379 write-bridge)  ← was missing
    ↓
Reporting (bsc_actuals → bsc_score_computation → MD cockpit BSC tab → MD's daily question)
```

---

## Part 1 — Why a write-bridge is non-trivial

It's tempting to think: "we have UniversalBSCRecord.to_submit_kwargs() that mirrors bsc_engine.submit() — just loop and call submit". That's the core of the writer. But three constraints make this non-trivial:

### 1.1 Idempotency hash collisions

`bsc_engine._idempotency_hash` is computed over `(staff_code, kpi_id, period, source_module)`. The v10.377 unifier produces records that **share these 4 fields when**:

- Multiple SBUs map to the same Chief (Commercial/Corporate/Treasury → EXEC-CCMO-001)
- Multiple SBUs map to MD as fallback (Support/Executive/Unallocated → 300001)
- Multiple branches have no configured BM → all fall back to MD (300001)

For these cases, naive submission causes:
- "Last write wins" arithmetic (later records overwrite earlier ones in same source_module)
- 60-70% of submissions silently lost on a seeded bank with sparse BM coverage

### 1.2 Period format mismatch

v10.377 unifier produces records with `period="2026"` (calendar year — the period over which canonical PBT is computed). But `bsc_engine.validate` accepts only `YYYY-MM` or `YYYY-QN`. The writer must translate.

### 1.3 Write to live data is dangerous

`bsc_engine.submit()` writes to `data/bsc_actuals_<period>.json` — production data. A buggy writer corrupts MD's BSC view. Defense:
- **Default `dry_run=True`** — naked call previews without side effects
- Explicit `dry_run=False` required to mutate
- Reconciliation gate refuses to write when Σ-identity broken
- Tests use tempdir DATA_DIR; never touch live files

---

## Part 2 — The filter (`_should_write`)

To avoid the idem-collision problem, the writer applies these rules:

| Dimension | Condition | Action |
|---|---|---|
| `bank` | always | **WRITE** (authoritative MD PBT) |
| `staff` | always | **WRITE** (real staff_code by construction) |
| `sbu` | `staff_code == MD` | **SKIP** ("absorbed SBU" — Support/Executive/Unallocated) |
| `sbu` | other | **WRITE** (real SBU head) |
| `branch` | `fallback_used == True` | **SKIP** (no configured BM) |
| `branch` | `staff_code == MD` (defensive) | **SKIP** |
| `branch` | other | **WRITE** (real BM) |

Why skipping is correct (not data loss):
- **Bank dimension already represents MD's PBT** — any record collapsing to MD is mathematically redundant
- **Absorbed SBUs** (Support functions reporting to MD) have no separate Chief — their PBT is part of the bank total
- **Branches without BMs** are a data-quality issue — their PBT should be reflected in the BM seat once configured; for now, captured in the bank dimension

The writer tracks `skipped_records` and `skip_reasons` so the operator sees the data-quality picture explicitly per constitution §5.4.

---

## Part 3 — Remaining SBU-head collision (acknowledged)

Even after the filter, multiple real SBUs can share a Chief:
- Commercial Banking → EXEC-CCMO-001
- Corporate Banking → EXEC-CCMO-001
- Treasury → EXEC-CCMO-001

All three submissions hit the same `(EXEC-CCMO-001, PBT, 2026-Q4, canonical_pbt_sbu_engine_v10377)` idem-hash. The last write wins arithmetic.

**v10.379 documents this as a known constraint.** Mitigation paths:

A. **Aggregate SBU PBT by Chief before writing.** Sum Commercial+Corporate+Treasury → write one record. This is the most correct fix; deferred to a follow-up batch.

B. **Use distinct source_modules per SBU.** E.g. `canonical_pbt_sbu_engine_v10377_commercial`. Defeats the idem-hash but bloats source_module proliferation. Rejected.

C. **Use kpi_id sub-tagging.** PBT_COMMERCIAL / PBT_CORPORATE / PBT_TREASURY. Defeats validation since kpi_library only has "PBT". Rejected.

The right fix is (A). v10.380 will address it when KPI-ID canonicalisation lands.

---

## Part 4 — Module API

```python
@dataclass
class WriteResult:
    target_period:    str          # e.g. "2026-Q4"
    dry_run:          bool
    total_records:    int          # from unifier
    eligible_records: int          # passed filter
    skipped_records:  int          # absorbed/fallback
    skip_reasons:     Dict[str,int]
    created:          int          # bsc_engine returned "created"
    updated:          int          # bsc_engine returned "updated"
    errors:           List[Dict]   # submit() returned (False, reason)
    kwargs_preview:   List[Dict]   # what would be / was submitted
    actor:            str
    note:             str

def write_canonical_pbt_to_bsc(
    cbs_dir:       Optional[Path] = None,
    target_period: str = "2026-Q4",
    dry_run:       bool = True,             # SAFETY: default no side effects
    actor:         str = "canonical_writer_v10379",
) -> WriteResult: ...

def preview_canonical_pbt_writes(cbs_dir, target_period) -> List[Dict]:
    """Convenience: returns just kwargs_preview from dry-run."""
```

---

## Part 5 — Reconciliation gate (G265 enforces)

Before writing, the writer verifies the v10.377 unifier's reconciliation:

```python
recon = unifier_output["reconciliation"]
if not recon["all_within_kes_100"]:
    result.note = "reconciliation failed — REFUSING to write"
    return result
```

Per constitution §5.5 — never persist broken reconciliation. The MD's cockpit must show numbers that reconcile mathematically.

---

## Part 6 — What v10.379 deliberately does NOT do

- Does NOT write to live `bsc_actuals_*.json` automatically (must be invoked deliberately)
- Does NOT change `bsc_engine.py` (it's the consumer interface — stable)
- Does NOT migrate existing source_modules (they coexist with `canonical_*_v10377` records)
- Does NOT remove the `management_accounts` source_module records (they remain authoritative until consumers migrate)
- Does NOT do per-Chief SBU aggregation (deferred — see Part 3)
- Does NOT extend to other KPIs (PBT only — Phase D applies pattern)
- Does NOT touch the MD cockpit page (v10.376 reads bsc_actuals already; will pick up canonical records automatically)

Single concern: **make canonical PBT records actually flow into bsc_actuals_*.json via bsc_engine.submit(), safely and idempotently.**

---

## Part 7 — Honest acknowledgement

1. **Default dry_run=True is essential safety.** Production deploys must explicitly invoke `write_canonical_pbt_to_bsc(dry_run=False)`. This is human-in-the-loop by design.

2. **Filter loses ~60-70% of unifier records on seeded bank.** This is correct — those records represented fallback aggregation already captured in the bank dimension. Production bank with configured BMs will see different ratios (most branches will write).

3. **3 SBU records collide to 1 EXEC-CCMO-001 record** in production (Commercial/Corporate/Treasury → same Chief). Last-write-wins arithmetic. Documented in Part 3; fix path identified for follow-up batch.

4. **Period translation is "annual → target_period".** Today the canonical engines run on full-year CBS data; the writer attributes the result to a single BSC reporting period. When quarterly canonical engines arrive, the writer can run per-quarter.

5. **`bsc_engine.submit()` validates against `kpi_library.json` and `users.json`.** Records with unknown KPIs or staff_codes are rejected with explicit error — captured in `WriteResult.errors`. No silent failures.

6. **The MD cockpit (v10.376 panel) reads `bsc_actuals` via `get_actual()`.** Once v10.379 runs in production, the panel's "Canonical PBT" value comes from `bsc_actuals_2026-Q4.json` directly — same data path as the existing BSC perspective scores. **The MD sees one number.**

7. **Idempotency means re-running is safe.** Operator can re-invoke `write_canonical_pbt_to_bsc(dry_run=False)` after CBS data refresh — bsc_engine.submit() upserts. No duplicates, no double-counting.
