# Changelog — v10.380 KPI Alias Resolver + Deep Review (Phase B Continues)

**Date:** 2026-05-13
**Phase:** 4 (sixty-fifth arc — Phase B fourth batch — deep review + alias resolution)
**Audit:** G266 added (locks review doc + resolver module + zero unknown orphans assertion)
**Tests:** 13/13 PASSED in `test_v10380_kpi_alias_resolver.py`; 307 prior tests unchanged = **320 total**
**Verifier:** 409/409 checks pass on a clean extract
**G162 baseline:** 4022 (74 consecutive zero-drift batches)
**Master prompt:** v4.23 → v4.24 (lockstep — twenty-fifth consecutive batch)

---

## Your direction

> "Continue. Also do a deep review of the target cascade and kpi library for more understanding and appreciation also on how they are configured, what can be fixed. this could help"

The deep-review-before-execute discipline you've consistently emphasized. v10.380 prioritized understanding over action. The review surfaced significant drift that I'd been under-counting.

## What v10.380 delivered

### 1. `docs/TARGET_CASCADE_KPI_LIBRARY_REVIEW_v10.380.md` — NEW (~15KB, 10 Parts)

The deep architectural survey. Concrete counts on every dimension:

| Part | Content |
|---|---|
| 1 | Target Cascade structure: 1,051 entries, 51 cascading staff, 21 KPIs, **1 corrupted key (`deadline|300001|2026`)** |
| 2 | KPI Library structure: 185 KPIs (109 active), 3 ID conventions coexisting, 167/185 KPIs with id≠name drift |
| 3 | **The 34 orphan KPI references** — Class A (alias drift) vs Class B (genuinely missing) |
| 4 | Cross-reference matrix: where each KPI appears (cascade vs role_kpis vs bsc_actuals) |
| 5 | Pillar weights drift (40/25/25/10 vs 68/14/6/12) |
| 6 | Cascade configuration patterns + lock state metadata |
| 7 | Other findings: source_module diversity, empty cbk_ref, active=None edge cases |
| 8 | What v10.380 ships vs what's deferred |
| 9 | Decisions awaiting Joshua |
| 10 | Honest acknowledgement |

### 2. `utils/kpi_alias_resolver.py` — NEW (leaf module, 10 self-tests)

Provides the alias resolution layer:

```python
KPI_ALIASES = {                 # 19 Class A mappings
    "TOTAL_NFI":          "Total NFI",
    "LOAN_GROWTH":        "Loan Book Growth",
    "COMPLIANCE":         "COMPLIANCE_SCORE",
    "AUDIT_SCORE":        "Audit Score",
    "CX_SCORE":           "CX Score",
    "STAFF_PROD":         "Staff Productivity",
    "LOAN_DISB":          "K001",  # Loans Disbursed (KES M)
    "TRADE_FIN":          "TRADE_FINANCE_REVENUE",
    # ... 11 more
}

CLASS_B_ORPHANS = [             # 15 documented missing KPIs
    {"orphan_id": "DEP_GROWTH",  "suggested_name": "Total Deposit Growth", ...},
    {"orphan_id": "NIM",         "suggested_name": "Net Interest Margin", ...},
    {"orphan_id": "ROE",         "suggested_name": "Return on Equity", ...},
    {"orphan_id": "NPS",         "suggested_name": "Net Promoter Score", ...},
    {"orphan_id": "CIR",         "suggested_name": "Cost-to-Income Ratio", ...},
    # ... 10 more with suggested definitions
]

def resolve_kpi_id(maybe_alias) -> str: ...
def get_kpi_definition(maybe_alias) -> Optional[Dict]: ...
def is_class_b_orphan(maybe_alias) -> bool: ...
def list_class_b_orphans() -> List[Dict]: ...
def clean_cascade_dict(raw) -> Dict: ...      # strips deadline|* corruption
def scan_role_kpis_coverage() -> Dict: ...    # diagnostic
```

### Coverage snapshot (after v10.380)

```
Total roles:           227
Distinct KPI refs:     193
Resolved direct:       159  (already in kpi_library)
Resolved via alias:    19   (Class A — fixed by KPI_ALIASES)
Class B orphans:       15   (genuinely missing — documented)
Unknown orphans:       0    ← was 8 in the deep review's first pass
```

**Every single KPI reference in role_kpis is now either resolved or documented.** The original review documented 8 Class B orphans; running the resolver against real data surfaced 6 more I'd missed (5 LEGAL_* SLAs for Chief Legal Officer + TRANSACTIONS + initially missed 2 Class A candidates: LOAN_DISB + TRADE_FIN). v10.380 ships with everything mapped.

### G266 audit gate

Locks 8 invariants:
1. Review doc with all 10 Parts
2. Resolver module with all 9 canonical symbols
3. Module is leaf (AST-verified no top-level upward utils.* imports)
4. ≥17 Class A aliases (now 19)
5. ≥15 Class B orphans documented
6. End-to-end resolution: TOTAL_NFI → Total NFI, LOAN_GROWTH → Loan Book Growth, etc.
7. **Zero unknown orphans in role_kpis coverage scan**
8. Real `target_cascade.json::deadline|*` corruption stripped by clean_cascade_dict

### Tests — 13/13 across 4 sections

**Section 1 (review + module presence + purity):** doc with 10 Parts; resolver module exports; **AST-verified leaf module**

**Section 2 (alias mechanics):** Class A aliases resolve correctly; direct IDs pass through; get_kpi_definition via alias; Class B orphans documented with required fields

**Section 3 (cascade cleaner + coverage):** clean_cascade_dict strips deadline|* corruption; real cascade cleans to valid entries; **zero unknown orphans assertion**

**Section 4 (G266 + no regression):** G266 passes; module does NOT modify source files; all prior canonical identities (G250-G265) still hold

## Files changed

| File | Change |
|---|---|
| `docs/TARGET_CASCADE_KPI_LIBRARY_REVIEW_v10.380.md` | **NEW** (~15KB, 10 Parts) |
| `utils/kpi_alias_resolver.py` | **NEW** (~440 LOC, 10 self-tests) |
| `scripts/audit.py` | **NEW** `gate_kpi_alias_resolver` (G266) |
| `scripts/verify_local_state.py` | Extended to 409 checks |
| `tests/integration/test_v10380_kpi_alias_resolver.py` | **NEW** — 13 tests across 4 sections |
| `docs/Master_Prompt_v4.24.md` | **NEW** — lockstep bump from v4.23 |

## Verified outcome

| Metric | Value |
|---|---|
| Deep review document substantive (10 Parts) | **YES** (~15KB) |
| 34 orphan IDs discovered + classified | **YES** (19 Class A + 15 Class B) |
| Unknown orphans after v10.380 | **0** (down from 8 in initial pass) |
| Class A aliases working | **YES** (19 mappings) |
| Class B documentation complete | **YES** (15 with suggested definitions) |
| `deadline|*` cascade corruption surfaced + filter provided | **YES** |
| Resolver is read-only (no source mutation) | **AST-VERIFIED** |
| Module is a leaf (no upward imports) | **AST-VERIFIED** |
| Audit gates | 265 → **266** (G266 added) |
| All prior canonical identities (G250-G265) | still PASS |
| Tests | +13 in v10.380; **320 total across v10.358–v10.380** |
| Verifier | 390 → **409 checks** |
| Master prompt lockstep | **25/25 consecutive batches** |
| G162 baseline | 4022 (**74 consecutive zero-drift batches**) |

## Honest acknowledgements

1. **The deep review was the most valuable part of v10.380** — it surfaced things I'd been missing in earlier batches. The "8 undefined KPIs for MD" I'd mentioned in earlier reviews actually expanded to 34 orphans across role_kpis when scanned systematically. Joshua's "deep review" directive made this visible.

2. **The 8 unknown orphans I missed initially** (5 LEGAL_*, TRANSACTIONS, LOAN_DISB, TRADE_FIN) were caught by the resolver's coverage scanner, not by manual inspection. Per constitution §5.4 — no silent failures. The scanner enforced the explicit accounting.

3. **The `deadline|300001|2026` corruption has been there since v10.X (unknown when).** Multiple modules that iterate `target_cascade.keys()` either crash on it or silently ignore. v10.380 provides the defensive filter; in-place cleanup is a follow-up batch.

4. **MD's 12 KPIs: 4 resolvable, 8 Class B.** This means MD's BSC currently can't be fully populated through `bsc_engine.submit()` — 8 of 12 KPIs would be rejected as "kpi_id not in kpi_library". The MD's actual BSC view today uses other paths (legacy management_accounts source_module) or accepts the 4 valid IDs only.

5. **Class B definitions need Joshua's product-management input.** I've suggested name/pillar/unit/direction for each but the canonical decision needs business owner sign-off: what IS the bank's official definition of NIM? Which calc for ROE? Which CIR formula? Etc. v10.380 does not assume — it documents and asks.

6. **K-code duplicates remain.** `K006` and `NEW_ACCOUNTS` both name "New Accounts Opened". `K001` and `LOAN_DISB` (via alias) and "Loans Disbursed (KES M)" all coexist. Retiring K-codes is a careful migration (consumers may reference them); deferred.

7. **Pillar weight drift unchanged.** Library has `pillars[]` 40/25/25/10 AND `pillar_weights` 68/14/6/12. Both are read by different consumers. Composite scores depend on which file is read. Needs Joshua decision.

8. **The resolver is opt-in by design.** Consumers that don't import `kpi_alias_resolver` work exactly as before. This is the v10.378/v10.379 pattern — surface the canonical engine, but don't force migration. Consumer migration is per-batch follow-up.

9. **`clean_cascade_dict` is defensive, not destructive.** It returns a NEW dict with valid entries; the original `target_cascade.json` file is untouched. Consumers can adopt the filter incrementally.

10. **Active KPI count may be off by ~1-2.** Library has some `active=null` entries (e.g. `K084`) that fall through the `if x.get('active')` check. The "109 active" count is approximate. Cleanup is a normalisation batch.

11. **`role_kpis` has 227 roles but role_taxonomy (v10.374) classified 126 distinct roles from users.json+hr.json.** The 101 extra `role_kpis` entries include aspirational roles or aliases not yet staffed. Documented but not reconciled.

12. **`cbk_ref` is empty for most KPIs.** Audit Score, Compliance Score, NPL Ratio, PAR — all should reference CBK regulatory standards. Currently empty in library. Compliance documentation gap.

13. **Cascade uses friendly names; role_kpis uses IDs.** Same KPI referenced two different ways depending on consumer. The resolver bridges both directions but the underlying drift remains. Eventually one convention should win.

14. **Rule N2 single concern held strictly.** Did NOT modify kpi_library.json. Did NOT modify target_cascade.json. Did NOT modify role_kpis. Did NOT add Class B KPI definitions (needs Joshua decisions). Did NOT touch BSC engine. Did NOT touch existing pages.

15. **Phase B continues.** v10.381 = refactor `customer_profitability.py` to consume v10.378 unified customer master. v10.382 = refactor `rm_profitability.py`. Then Phase C live actions, Phase D 108 remaining KPIs.

## Decisions awaiting Joshua (Part 9 of review doc)

1. **Add Class B KPI definitions?** 15 orphans documented with suggestions — needs your sign-off on name/pillar/unit/direction/source for each
2. **Pillar weights** — 40/25/25/10 (library array) or 68/14/6/12 (current field)?
3. **K-code retirement** — 18 numeric K-codes duplicate newer SCREAMING_SNAKE entries — retire?
4. **Cascade `deadline|*` cleanup** — move to top-level `cascade_meta` field?
5. **Active KPI count** — normalize `active=null` to `active=False`?
6. **role_kpis vs taxonomy alignment** — reconcile 227 role_kpis entries with 126 v10.374 taxonomy roles?
7. **cbk_ref** — populate for compliance KPIs?
8. **ID convention** — one of three to win going forward?

## On your end

1. Close Streamlit
2. Extract `a2z_v10380_session_cumulative.zip` flat
3. Run `python scripts\verify_local_state.py` → expect **ALL 409 CHECKS PASSED**
4. **Read the deep review:** `docs\TARGET_CASCADE_KPI_LIBRARY_REVIEW_v10.380.md` (most important artifact)
5. **See the alias resolver in action:**
   ```
   python -c "
   from utils.kpi_alias_resolver import (
       resolve_kpi_id, get_kpi_definition,
       scan_role_kpis_coverage, clean_cascade_dict,
   )
   print(f'TOTAL_NFI → {resolve_kpi_id(\"TOTAL_NFI\")!r}')
   print(f'LOAN_GROWTH → {resolve_kpi_id(\"LOAN_GROWTH\")!r}')
   print(f'PBT → {resolve_kpi_id(\"PBT\")!r}')
   print(f'NIM → {resolve_kpi_id(\"NIM\")!r}  (Class B orphan)')
   cov = scan_role_kpis_coverage()
   print(f'\nCoverage: {cov[\"resolved_direct\"]}+{cov[\"resolved_via_alias\"]}={cov[\"resolved_direct\"]+cov[\"resolved_via_alias\"]} resolved, {cov[\"class_b_orphans\"]} documented Class B, {cov[\"unknown_orphans\"]} unknown')
   "
   ```
6. Read `docs\Master_Prompt_v4.24.md`
7. **Review Part 9 decisions** — your call on each
8. (Optional, takes >5min) Audit → expect **266/266 PASS**

## What comes next — v10.381

**Refactor `customer_profitability.py` to consume v10.378 unified customer master.** Today's `customer_profitability.py` reads `customer_intelligence.json` directly; v10.381 has it call `compute_unified_customer_master()` so it sees CBS-merged data with full lineage. Same engine output, broader data source. The legacy file remains untouched for backward compat.

Want me to continue with v10.381?
