# Changelog — v10.377 Universal BSC Data Contract + Virtual Bank KPI Flow (Phase B Opens)

**Date:** 2026-05-13
**Phase:** 4 (sixty-second arc — Phase B first batch — nervous-system establishment)
**Audit:** G263 added (locks constitution doc + contract module + unifier + end-to-end probe)
**Tests:** 15/15 PASSED in `test_v10377_universal_bsc_contract.py`; 264 prior tests unchanged = **279 total**
**Verifier:** 354/354 checks pass on a clean extract
**G162 baseline:** 4022 (71 consecutive zero-drift batches)
**Master prompt:** v4.20 → v4.21 (lockstep — twenty-second consecutive batch)

---

## Your direction

> "Continue. The objective is to have a single MIS system that is akin to an Operating System but does not replace core banking. It aims to solve the major pain that the banking industry experiences... Lets have our virtual bank unify how all KPIs flow, test all modules and ensure every staff works and is measured."

Plus the **Technical Governance Framework** transmitted as official constitution. The critical mandates:

- **§5.1 Universal BSC Data Contract**: every module outputs `{staff_code, kpi_id, value, period, source_module}` — non-negotiable
- **§5.2 Central BSC Integration Engine**: all modules pass through central validation
- **§4.3 PostgreSQL = single source of truth** (Phase F destination)
- **§9.1 Streamlit internal / React enterprise** (Phase E destination)
- **§12 Flow Principle**: every banking activity flows through MIS structurally
- **§14 Final Governance**: enterprise-grade banking MIS, not just reporting

## What v10.377 delivered

### 1. `docs/A2Z_GOVERNANCE_CONSTITUTION_INTERNAL_v10.377.md` — NEW (~14KB, 8 Parts)

Internal codification of the constitution + mapping current state to target state. Anchors future development.

| Part | Content |
|---|---|
| 1 | Constitutional mandates from Sections 4-9 + 11-14 of the Framework — current state vs target |
| 2 | The five problems A2Z MIS 360 solves (operating-system framing, MI aggregation, staff performance, target cascade, strategy) |
| 3 | Body-system framing anchored in constitution (skeleton/circulatory/nervous/endocrine/brain) |
| 4 | Today's directive: virtual bank unifies KPI flow |
| 5 | What v10.377 deliberately does NOT do (Rule N2 scope discipline) |
| 6 | Next 10 batches constitutionally aligned |
| 7 | Migration arc to PostgreSQL (Phase F) |
| 8 | Honest acknowledgement |

### 2. `utils/bsc_universal_contract.py` — NEW (~340 LOC, 10 self-tests)

The **nervous-system signal carrier**. Leaf module — zero upward imports. Pure validation + conversion.

```python
@dataclass
class UniversalBSCRecord:
    staff_code:    str                # mandatory
    kpi_id:        str                # mandatory
    value:         float              # mandatory, finite (NaN/inf rejected)
    period:        str                # mandatory, validated against PERIOD_FORMATS
    source_module: str                # mandatory, snake_case convention
    actor:         str = "system"
    metadata:      Dict[str, Any] = {}

    def to_submit_kwargs() -> Dict   # mirrors bsc_engine.submit() exactly
```

Validation per Section 5.4 (silent failures prohibited):
- Empty fields → ContractViolation
- NaN / inf values → ContractViolation
- Bad period format → ContractViolation
- Bad source_module (uppercase, spaces, etc.) → ContractViolation
- Bool as value → ContractViolation (Python tomfoolery defense)
- Decimal accepted, coerced to float

Period formats accepted: `YYYY` / `YYYY-QN` / `YYYY-MM` / `YYYY-MM-DD`.

Source module convention: `snake_case` only (lowercase + digits + underscores; starts with letter). The traceability requirement (§5.2) is enforced at the validator level.

### 3. `utils/virtual_bank_kpi_unifier.py` — NEW (~340 LOC, 8 self-tests)

The **end-to-end demonstration**: virtual bank → all canonical engines → universal records for every dimension.

```python
def unify_all_kpi_flow(cbs_dir=None, period="2026") -> Dict:
    """Runs:
       1. compute_pbt_from_cbs (G250) → 1 record for MD
       2. compute_pbt_by_sbu (G254) → N records, one per SBU head Chief
       3. compute_pbt_by_branch (G255) → M records, one per Branch Manager
       4. compute_pbt_by_staff (G257) → P records, one per tagged staff
       Returns all records + validation + reconciliation report.
    """
```

**Live demonstration against seeded bank:**

```
Bank PBT:       KES -7.90B
SBU records:    6   (Σ tolerance KES 0)
Branch records: 63  (Σ tolerance KES 2)
Staff records:  28  (Σ tolerance KES 6)
                ──
Total:          98 universal records, 0 contract violations
```

Every staff record carries the v10.374 profitability_tier in metadata. Every record's `engine_gate` references one of G250/G254/G255/G257 — full traceability per §5.2.

### G263 audit gate

Verifies:
1. Constitution doc present with all 8 Parts
2. Contract module has all 10 canonical symbols
3. Contract module is a leaf (AST-verified: no upward utils.* imports)
4. Unifier module has all 12 canonical symbols
5. End-to-end probe: ≥50 records, 0 violations, reconciliation passes
6. Every record has engine_gate metadata referencing valid gate
7. Every record's source_module ends with `_v10377` (convention)

Cost: ~1.5s (runs the full virtual bank pipeline).

### Tests — 15/15 across 4 sections

**Section 1 (constitution + contract module):** doc present with 8 Parts; contract module exports; contract is leaf module (AST-verified)

**Section 2 (contract validation):** valid record constructs; empty fields rejected; NaN/inf rejected; bad period format rejected; bad source_module rejected

**Section 3 (unifier end-to-end):** module present; ≥50 records produced; 0 contract violations; Σ-reconciliation holds at every dimension within KES 100; every record has engine_gate provenance; every staff record has profitability_tier

**Section 4 (gate alignment):** G263 passes

## Files changed

| File | Change |
|---|---|
| `docs/A2Z_GOVERNANCE_CONSTITUTION_INTERNAL_v10.377.md` | **NEW** (~14KB, 8 Parts) |
| `utils/bsc_universal_contract.py` | **NEW** (~340 LOC, 10 self-tests) — leaf module |
| `utils/virtual_bank_kpi_unifier.py` | **NEW** (~340 LOC, 8 self-tests) — demonstration |
| `scripts/audit.py` | **NEW** `gate_universal_bsc_contract` (G263) |
| `scripts/verify_local_state.py` | Extended to 354 checks |
| `tests/integration/test_v10377_universal_bsc_contract.py` | **NEW** — 15 tests across 4 sections |
| `docs/Master_Prompt_v4.21.md` | **NEW** — lockstep bump from v4.20 |

## Verified outcome

| Metric | Value |
|---|---|
| Constitution codified internally | **YES** (8 Parts, mapped current → target) |
| Universal BSC Data Contract layer established | **YES** (§5.1 mandate satisfied) |
| Virtual bank produces conforming records for every staff | **YES** (98 records, 28 staff) |
| Body-system nervous layer | **OPERATIONAL** |
| Contract module is leaf (v10.364 lesson) | **AST-VERIFIED** |
| Audit gates | 262 → **263** (G263 added) |
| Σ-reconciliation across all dimensions | **WITHIN KES 6** (vs KES 100 tolerance) |
| All 8 prior unification identities (G250-G262) | still PASS |
| Charter §2 (G249) | still PASS |
| Page smoke | 124/124 + 0 static |
| Tests | +15 in v10.377; **279 total across v10.358–v10.377** |
| Verifier | 328 → **354 checks** |
| Master prompt | v4.20 → **v4.21** — lockstep (22 consecutive batches) |
| G162 baseline | 4022 (**71 consecutive zero-drift batches**) |

## Honest acknowledgements

1. **The constitution explicitly says JSON files are deprecated.** This codebase has 208 JSON data files. v10.377 does NOT migrate them. The migration arc is Phase F. v10.377 establishes the contract layer that makes the migration tractable: when PostgreSQL arrives, the contract layer stays; only the storage swap underneath.

2. **`UniversalBSCRecord.to_submit_kwargs()` mirrors `bsc_engine.submit()` exactly.** This is intentional. When the write-bridge (v10.379) is built, it's a one-line call: `bsc_engine.submit(**record.to_submit_kwargs())`. No translation layer. The contract IS the bsc_engine.submit signature, formalized.

3. **The unifier handles SBU → head mapping via `SBU_HEAD_STAFF_CODE` constant**. Real-world variants: Treasury reports to Commercial in this bank's structure, hence `Treasury` → `EXEC-CCMO-001`. Same for Corporate Banking. Joshua's earlier note about Commercial covering both is reflected.

4. **Branch records use Branch Manager's actual staff_code** from users.json lookup. If no BM is configured for a branch, falls back to MD with `fallback_used=True` in metadata — surfaces as data-quality issue (per §5.4 reconciliation discipline) rather than silently hiding it.

5. **Customer-level data does NOT fit the staff-keyed BSC contract.** The universal contract requires `staff_code`; customers don't have one. This is correct: customer-level data flows through customer_360 modules, not BSC. The unifier therefore aggregates customer → staff first via `compute_pbt_by_staff`. Customer dimension is for customer analytics, not staff performance.

6. **`UNASSIGNED_STAFF_BUCKET` records are deliberately skipped** by `unify_staff_pbt`. The bucket isn't a real staff — it's a data-quality marker (customers without rm_code). The unifier focuses on the 28 real staff with portfolios. The unassigned bucket can be reported separately (it's surfaced in pages/120_staff_pbt.py).

7. **`source_module` convention enforces traceability**. Every record's source_module ends with `_v10377` so future audits can identify which batch introduced which records. Phase D batches will use `_v10NNN` consistently. Helps with the "JSON migration" — when reading old bsc_actuals files, source_module tells us which engine produced what.

8. **Module purity (v10.364 lesson) held strictly**. `bsc_universal_contract.py` has ZERO upward utils imports — AST-verified by G263. It's a leaf. The unifier consumes the contract + the canonical engines; the contract consumes nothing.

9. **Reconciliation in metadata is mathematical, not aspirational.** When the unifier reports `tolerances_kes`, those are actual Decimal arithmetic differences, not estimates. The 98-record run shows 0 / 2 / 6 KES tolerance across the three dimensions — well within the 100 KES bound that G256/G257 enforce.

10. **The constitution's §5.5 reconciliation mandate is satisfied at end-to-end.** Every G256/G257/G258 identity holds; the unifier verifies them explicitly per-run; G263 enforces verification. Mathematical defensibility from atom to bank, made visible to the MD in real-time (via v10.376 cockpit panel) and producible as BSC records (v10.377).

11. **`PERIOD_FORMATS` accepts daily, monthly, quarterly, annual** — the contract is calendar-agnostic. Banking moves at different cadences for different KPIs (NPL daily, PBT quarterly, NPS annually). The contract supports all.

12. **No new JSON files for performance data** per constitution §4.3. The unifier produces in-memory `List[UniversalBSCRecord]` — no JSON persistence in v10.377. When the write-bridge ships (v10.379), it calls `bsc_engine.submit()` which today still writes JSON; the JSON → Postgres migration is its own arc.

13. **Bool rejected as value**. Python's `True == 1` is technically a number, but a KPI value being `True` is almost certainly a bug. The contract rejects it. Defensive design per §5.4.

14. **The 5 problems summary in Part 2 of the constitution doc** captures Joshua's strategic restatement: operating-system framing, MI aggregation, staff performance daily, target cascade, strategy anchored in MIS. Every future batch can be traced back to which of the 5 problems it advances.

15. **Phase B is properly opened** with this batch. The customer master merge (v10.378), write-bridge (v10.379), and KPI-ID canonicalisation (v10.380) all build on the contract layer established here. Without v10.377, Phase B couldn't proceed cleanly.

## On your end

1. Close Streamlit
2. Delete leftover subfolder extracts
3. Extract `a2z_v10377_session_cumulative.zip` flat
4. Run `python scripts\verify_local_state.py` → expect **ALL 354 CHECKS PASSED**
5. **Read the constitution codification**: `docs\A2Z_GOVERNANCE_CONSTITUTION_INTERNAL_v10.377.md` — this is the new strategic anchor for all future batches
6. **See the universal contract in action:**
   ```
   python -c "
   from utils.virtual_bank_kpi_unifier import unify_all_kpi_flow
   result = unify_all_kpi_flow(cbs_dir=None, period='2026')
   print(f\"Bank PBT (1 record): KES {result['bank_record'].value/1e9:,.2f}B\")
   print(f\"SBU records: {len(result['sbu_records'])}\")
   print(f\"Branch records: {len(result['branch_records'])}\")
   print(f\"Staff records: {len(result['staff_records'])}\")
   print(f\"TOTAL: {len(result['all_records'])} universal records\")
   print(f\"Contract violations: {result['validation']['violations']}\")
   print(f\"Reconciliation: {result['reconciliation']['all_within_kes_100']}\")
   "
   ```
7. Read `docs\Master_Prompt_v4.21.md`
8. (Optional, takes >5min) Audit → expect **263/263 PASS**

## What comes next — v10.378

**v10.378 — Customer master merge** (Phase B continues, per your earlier approval "merge into 1"):
- `customer_intelligence.json` (3,206 customers, marketing master)
- CBS `customers.csv` (700K production, transactions master)
- → unified customer master + reconciliation identity + audit gate
- Pattern: atomic per-customer record + Σ-identity + canonical engine + backward compat

After v10.378: **v10.379 = write-bridge** (canonical engines feed `bsc_engine.submit()` so MD's BSC actuals come from canonical, not management_accounts).

Want me to continue with v10.378?
