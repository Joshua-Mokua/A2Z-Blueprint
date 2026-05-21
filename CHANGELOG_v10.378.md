# Changelog — v10.378 Customer Master Merge (Phase B Continues)

**Date:** 2026-05-13
**Phase:** 4 (sixty-third arc — Phase B second batch — recognition/sensory layer)
**Audit:** G264 added (locks design doc + canonical engine + end-to-end identity probe + read-only invariant)
**Tests:** 13/13 PASSED in `test_v10378_customer_master_merge.py`; 279 prior tests unchanged = **292 total**
**Verifier:** 373/373 checks pass on a clean extract
**G162 baseline:** 4022 (72 consecutive zero-drift batches)
**Master prompt:** v4.21 → v4.22 (lockstep — twenty-third consecutive batch)

---

## Your direction

> "Continue."

Per the v10.377 wrap-up roadmap, v10.378 = Customer Master Merge per Joshua's "merge into 1" approval at v10.374 wrap-up.

## What v10.378 delivered

### 1. `docs/CUSTOMER_MASTER_MERGE_v10.378.md` — NEW (~7KB, 7 Parts)

Design document for the merge:

| Part | Content |
|---|---|
| 1 | The two customer universes (CBS transactional + marketing intelligence) |
| 2 | Merge strategy: atomic unit + strict CIF match + conflict resolution rules + reconciliation identity + backward compat + storage policy |
| 3 | Module API (UnifiedCustomerRecord schema + function signatures) |
| 4 | Reconciliation identity (G264 lock) |
| 5 | What v10.378 deliberately does NOT do (Rule N2) |
| 6 | Where customer master fits in the body-system framing |
| 7 | Honest acknowledgement |

### 2. `utils/customer_master_canonical.py` — NEW (leaf module, 10 self-tests)

The canonical merge engine:

```python
@dataclass
class UnifiedCustomerRecord:
    cif: str
    full_name: Optional[str]
    customer_type: str                        # individual | business | unknown
    enrichment_status: str                    # cbs_only | marketing_only | both
    # Transactional (CBS)
    segment, branch_code, rm_code: Optional[str]
    # Intelligence (Marketing)
    clv_estimate, churn_risk: Optional[float]
    nba, digital_engagement: Optional[str]
    nps_score, products_held, complaints_12m, last_contact_days: Optional[int]
    propensity_scores: Dict[str, float]
    tags: List[str]
    # Lineage
    sources: List[str]
    _field_lineage: Dict[str, str]            # field → 'cbs' | 'marketing' | 'derived'

def compute_unified_customer_master(cbs_dir) -> Dict[cif, UnifiedCustomerRecord]
def reconciliation_summary(unified, cbs_dir) -> Dict
def get_customer(cif, cbs_dir) -> Optional[UnifiedCustomerRecord]
```

**Live demonstration on seeded bank:**

```
CBS:        100      (100% cbs_only — seed customers)
Marketing:  3,206    (100% marketing_only — 3,000 individuals + 206 businesses)
Overlap:    0        (disjoint CIF schemes in seed)
Unified:    3,306    (= 100 + 3,206 - 0)
Identity:   HOLDS    (|A∪B| = |A| + |B| - |A∩B|)
```

In production (700K CBS + 3,206 marketing), the overlap would be substantial — the engine handles it identically.

### G264 audit gate

Verifies on every audit run:
1. Design doc present with all 7 Parts
2. Canonical module has all 10 required exports
3. Module is a leaf — no top-level upward utils.* imports
4. End-to-end probe produces ≥3,000 unified records
5. Identity equation `|A∪B| = |A| + |B| - |A∩B|` HOLDS
6. Status totals add up: `cbs_only + marketing_only + both = unified_count`
7. Read-only invariant: module does NOT write to source files

Cost: ~1.0s (runs seed + merge).

### Tests — 13/13 across 4 sections

**Section 1 (presence + purity):** design doc with 7 Parts; canonical module exports; leaf-module AST verification

**Section 2 (merge mechanics):** marketing-only universe; business customer classification; CBS lineage tagging; marketing lineage tagging

**Section 3 (reconciliation):** identity equation holds end-to-end; status totals match; get_customer lookup

**Section 4 (gate + no-regression):** G264 passes; all 8 prior unification identities (G250+G253+G254+G255+G256+G257+G258+G263) still hold; role taxonomy still 100% coverage

## Files changed

| File | Change |
|---|---|
| `docs/CUSTOMER_MASTER_MERGE_v10.378.md` | **NEW** (~7KB, 7 Parts) |
| `utils/customer_master_canonical.py` | **NEW** (~340 LOC, 10 self-tests) — leaf module |
| `scripts/audit.py` | **NEW** `gate_customer_master_merge` (G264) |
| `scripts/verify_local_state.py` | Extended to 373 checks |
| `tests/integration/test_v10378_customer_master_merge.py` | **NEW** — 13 tests across 4 sections |
| `docs/Master_Prompt_v4.22.md` | **NEW** — lockstep bump from v4.21 |

## Verified outcome

| Metric | Value |
|---|---|
| Customer master canonical engine operational | **YES** |
| Strict CIF match identity equation | **HOLDS** (|A∪B| = |A| + |B| - |A∩B|) |
| Field-level lineage tracking | **OPERATIONAL** |
| Body-system recognition/sensory layer | **OPERATIONAL** |
| Canonical module is a leaf (v10.364 lesson) | **AST-VERIFIED** |
| Read-only invariant | **AST-VERIFIED** (no source mutations) |
| Audit gates | 263 → **264** (G264 added) |
| All 8 prior unification identities | still PASS |
| Tests | +13 in v10.378; **292 total across v10.358–v10.378** |
| Verifier | 354 → **373 checks** |
| Master prompt | v4.21 → **v4.22** — lockstep (23 consecutive batches) |
| G162 baseline | 4022 (**72 consecutive zero-drift batches**) |

## Honest acknowledgements

1. **Strict CIF matching is v10.378's limitation.** Real-world banks have CIF drift — one customer with multiple CIFs from past data migrations, or one CIF spanning multiple humans. Production deployment needs fuzzy matching by name + national_id + phone. That's v10.4XX scope — explicitly out of v10.378.

2. **Seed bank and marketing master are disjoint by design.** CBS seed uses 10-digit CIFs (`1000000001`); marketing individuals use 9-digit (`100625608`); marketing businesses use `CIF<digits>` format. Zero overlap is the correct outcome on this seed. Production data would show meaningful overlap.

3. **Constitution §4.3 honored — no new JSON output.** The canonical engine IS the source of truth, computable on every call. Phase F migrates source files to PostgreSQL; the engine API stays the same.

4. **Customer-level data is a SEPARATE concern from staff-keyed BSC.** The Universal BSC Data Contract (v10.377) is staff-keyed (`staff_code, kpi_id, value, period, source_module`). Customer-level analytics use `UnifiedCustomerRecord` from v10.378. These are deliberately distinct types — customer 360 modules use the customer record; BSC modules use the BSC contract; profitability_engine sees both via composition.

5. **Conflict resolution rules are admin-overridable in principle, hardcoded in v10.378.** Defaults: CBS wins for KYC-authoritative fields (full_name, segment, branch_code, rm_code); marketing wins for analytics (clv, churn, propensity). Future enhancement: configurable rules per field.

6. **`products_held` is a known special case.** Marketing tracks it as an integer estimate; CBS accounts.csv is ground truth. v10.378 uses marketing's number when available; v10.379+ batches can derive products_held directly from CBS accounts.csv aggregation.

7. **Field-level lineage is explicit.** Every populated field has a `_field_lineage[fname] → 'cbs' | 'marketing' | 'derived'` entry. Consumers can trace exactly where each value came from — vital for audit per constitution §8.1.

8. **The reconciliation identity equation is mathematical, not aspirational.** `|A∪B| = |A| + |B| - |A∩B|` is verified explicitly via `reconciliation_summary` on every call. G264 enforces it on every audit.

9. **Body-system recognition/sensory layer is the right framing.** The customer master is how the bank perceives its customers. Without it, every module sees different shadows of the same customer. With it: one customer = one record across all modules.

10. **`get_customer(cif)` is the single-lookup API** for module integration. Future batches (v10.381 customer_profitability refactor, v10.382 rm_profitability refactor) will consume it.

11. **`STATUS_BOTH` enrichment is the gold standard** — full transactional + intelligence on the same customer. Production tracking this status percentage indicates data integration health.

12. **`enrichment_status` makes data quality visible.** A module reading `STATUS_CBS_ONLY` records knows it lacks behavioral analytics; reading `STATUS_MARKETING_ONLY` knows there's no transactional grounding. Per constitution §5.4 — no silent failures.

13. **Rule N2 single concern held.** Did NOT write to source files. Did NOT migrate consumers. Did NOT do fuzzy matching. Did NOT touch BSC contract. Did NOT compute customer-level PBT (separate engine, separate concern).

14. **The 4 sections of tests provide layered defense.** Presence + mechanics + reconciliation + regression. Section 4 specifically asserts G250+G253+G254+G255+G256+G257+G258+G263 still hold — v10.378 has zero spillover into prior arc.

15. **Phase B continues per the constitutional roadmap.** v10.379 = write-bridge (canonical engines → bsc_engine.submit so MD's BSC actuals come from canonical, not management_accounts). v10.380 = KPI-ID canonicalisation. v10.381 = refactor customer_profitability.py to consume v10.378 unified master.

## On your end

1. Close Streamlit
2. Delete leftover subfolder extracts
3. Extract `a2z_v10378_session_cumulative.zip` flat
4. Run `python scripts\verify_local_state.py` → expect **ALL 373 CHECKS PASSED**
5. **Read the merge design doc:** `docs\CUSTOMER_MASTER_MERGE_v10.378.md`
6. **See the customer master in action:**
   ```
   python -c "
   from utils.customer_master_canonical import compute_unified_customer_master, reconciliation_summary
   import tempfile
   from pathlib import Path
   from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
   from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
   bank, _ = seed_virtual_bank(config=SeedConfig.small())
   with tempfile.TemporaryDirectory() as td:
       td_path = Path(td)
       persist_bank_to_cbs(bank, output_dir=td_path)
       unified = compute_unified_customer_master(cbs_dir=td_path)
       s = reconciliation_summary(unified, cbs_dir=td_path)
   print(f'Unified customers: {s[\"unified_count\"]}')
   print(f'  cbs_only:       {s[\"by_status\"][\"cbs_only\"]}')
   print(f'  marketing_only: {s[\"by_status\"][\"marketing_only\"]}')
   print(f'  both:           {s[\"by_status\"][\"both\"]}')
   print(f'  identity_holds: {s[\"identity_holds\"]}')
   "
   ```
7. Read `docs\Master_Prompt_v4.22.md`
8. (Optional, takes >5min) Audit → expect **264/264 PASS**

## What comes next — v10.379

**Write-bridge: canonical engines feed `bsc_engine.submit()`** — the MD's BSC actuals come from canonical PBT engines (v10.370 G256/G257) rather than the legacy `management_accounts` source_module. This closes the loop on the Universal BSC Data Contract (v10.377) by making the canonical engines actually flow into the BSC actuals stream.

Pattern: the contract layer is established; the unifier produces records; now the writer takes records and calls `bsc_engine.submit(**record.to_submit_kwargs())`.

Want me to continue with v10.379?
