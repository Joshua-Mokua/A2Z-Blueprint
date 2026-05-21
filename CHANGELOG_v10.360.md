# Changelog — v10.360 Branch Single Source of Truth

**Date:** 2026-05-13
**Phase:** 4 (forty-fifth arc — data-integrity fix interrupting Football Team Test chain closure)
**Audit:** G246 added (passes in ~30ms isolated)
**Tests:** 11/11 PASSED in `test_v10360_branch_single_source.py`; v10.358 + v10.359 test files updated (29/29 still pass under new dynamic branch count)
**Page smoke:** 123/123 PASS + 0 static findings + 14/14 dynamic renders pass
**Verifier:** 165/165 checks pass on a clean extract
**G162 baseline:** 4022 (54 consecutive zero-drift batches)
**Master prompt:** v4.3 → v4.4 (lockstep — fifth consecutive batch)

---

## Your ask

> "proceed, with our initial tests we had more branches and structure i guess there are two sets of bank data that we needed to determine which rich for our use. then if possibl discard one set so that we have 1 maintained even for future uses when testing"

You spotted a foundational data-integrity gap during the v10.359 review. The v10.359 readiness audit reported "29 RMs across 21 branches" — but earlier sessions had referenced larger numbers. That's because **the platform actually has TWO parallel branch sources**, and the v10.358 seeder picked the smaller one.

## What v10.360 found

**Two parallel branch sources existed:**

| Source | Entries | Regions | Schema |
|---|---|---|---|
| `utils.core.BRANCH_REGION` | 21 hardcoded entries | 3 (South/Central/North) | name → region (flat dict) |
| `data/org_config.json::branches[]` | **94 entries** | **7** (Nairobi 27, Other 45, Rift Valley 8, Coast 5, Central 5, Nyanza 2, Eastern 2) | id, name, region, branch_code, dept_id, opened_date, region_group, active |

The overlap was minimal — only **15 of 21** legacy names matched (after stripping " Branch" suffix). The legacy list missed Mombasa Kenyatta Avenue, Mombasa Nkrumah, Eastleigh, JKIA, Westlands, FB Towers Corporate, Cargen House, City Hall, Donholm, and 60+ others that actually exist in the Ecobank network.

**The rich source is org_config.json.** v10.360 unifies on it.

## What v10.360 delivered

### 1. `utils/core.py` — BRANCH_REGION dynamically sourced

The hardcoded `BRANCH_REGION: dict = {...21 entries...}` is replaced with:

```python
_BRANCH_REGION_FALLBACK: dict = {
    # Legacy 21-entry list retained as fallback for degraded environments
    'Mombasa Branch': 'South',
    ...
}

def _build_branch_region_from_org_config() -> dict:
    """Read active branches from data/org_config.json. Falls back to
    the legacy 21-entry list if config is missing/malformed."""
    try:
        import json
        from pathlib import Path
        path = Path(__file__).parent.parent / "data" / "org_config.json"
        if not path.exists():
            return dict(_BRANCH_REGION_FALLBACK)
        cfg = json.loads(path.read_text(encoding="utf-8"))
        branches = cfg.get("branches", [])
        if not branches:
            return dict(_BRANCH_REGION_FALLBACK)
        return {
            b["name"]: b.get("region", "Other")
            for b in branches
            if b.get("active", True) and b.get("name")
        }
    except Exception:
        return dict(_BRANCH_REGION_FALLBACK)

BRANCH_REGION: dict = _build_branch_region_from_org_config()
```

**Module-load time computation.** All 7 consumers (utils/finance_hub_render.py, pages/1_perform.py, pages/2_people.py, pages/15_optimize.py, pages/16_commission.py, pages/18_cims.py, pages/63_assets.py, pages/7_admin.py, pages/_sidebar.py) continue to read `BRANCH_REGION` as a dict and **need no code changes**. The dict interface is preserved; the source is what changed.

`utils.core.REGIONS` follows the same pattern — derived from `BRANCH_REGION.values()` rather than the legacy `['South', 'Central', 'North']`.

### 2. `utils/virtual_bank_seed.py` — ECOBANK_BRANCHES dynamic

Same pattern. The old 21-entry hardcoded dict is replaced with:

```python
_FALLBACK_BRANCHES: Dict[str, str] = {
    "Mombasa Branch":     "South",
    "Nairobi CBD Branch": "Central",
    "Eldoret Branch":     "North",
    "Kisumu Branch":      "North",
    "Nakuru Branch":      "North",
}  # only 5 fallback entries — production always reads org_config

def get_ecobank_branches() -> Dict[str, str]:
    """v10.360 — return {branch_name: region} from data/org_config.json."""
    try:
        config_path = REPO / "data" / "org_config.json"
        if not config_path.exists():
            return dict(_FALLBACK_BRANCHES)
        import json
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        branches = cfg.get("branches", [])
        if not branches:
            return dict(_FALLBACK_BRANCHES)
        return {
            b["name"]: b.get("region", "Other")
            for b in branches
            if b.get("active", True) and b.get("name")
        }
    except Exception:
        return dict(_FALLBACK_BRANCHES)

ECOBANK_BRANCHES: Dict[str, str] = get_ecobank_branches()
```

Both module-level constant AND fresh-from-disk getter. Callers that need stale-tolerant data use the constant; callers that need live data call the function.

### 3. SeedConfig change — n_branches default 21 → 0 (meaning "all")

```python
@dataclass
class SeedConfig:
    n_branches: int = 0  # 0 means "all branches in ECOBANK_BRANCHES"
```

The seeder loop:

```python
branches_to_seed = get_ecobank_branches()
branch_cap = config.n_branches if config.n_branches > 0 else len(branches_to_seed)
```

Default seed now produces **94 branches**, not 21. Tests and downstream consumers don't assume a specific count — they read `len(ECOBANK_BRANCHES)`.

### 4. G246 — Branch single source of truth ratchet

Locks three invariants:

1. **`utils.core.py` contains the dynamic builder.** Static-dict-literal pattern of >5 entries is forbidden — verified by checking for `_build_branch_region_from_org_config` string.
2. **`utils.virtual_bank_seed.py` reads org_config.** Verifies `def get_ecobank_branches` is present and `org_config.json` is referenced.
3. **Runtime count agreement.** `len(get_ecobank_branches())` equals the active branch count in `data/org_config.json`. Catches caching skew if the dynamic builder is ever broken.

Runs in 30ms isolated. **Pattern R5 — Ratchets, not heroics.** Drift back to two hardcoded lists is now mechanically prevented.

### 5. Test migration — v10.358 + v10.359 updated, not broken

The pre-v10.360 tests asserted "21 branches" as a hardcoded expectation. v10.360 updates them to:

```python
# Old:
assert result.n_branches == 21

# New:
from utils.virtual_bank_seed import ECOBANK_BRANCHES
assert result.n_branches == len(ECOBANK_BRANCHES)
```

The tests now express the right invariant: "the seeder uses all branches from the source," not "21". They pass against both small-fallback environments (5 branches) and full production (94 branches).

## Files changed

| File | Change |
|---|---|
| `utils/core.py` | `BRANCH_REGION` now built at import time from `org_config.json`; `REGIONS` derived from `BRANCH_REGION.values()` |
| `utils/virtual_bank_seed.py` | `ECOBANK_BRANCHES` + `get_ecobank_branches()` read org_config; `SeedConfig.n_branches` default 21→0 |
| `scripts/audit.py` | NEW gate G246 `gate_branch_single_source`; G244 updated for v10.360 sync semantics |
| `scripts/verify_local_state.py` | Extended to 165 checks |
| `tests/integration/test_v10358_seed_the_bank.py` | Updated to expect dynamic branch count |
| `tests/integration/test_v10359_cbs_writer.py` | Updated `test_v10359_actuals_engine_reads_branches` bound |
| `tests/integration/test_v10360_branch_single_source.py` | NEW — 11 tests |
| `docs/Master_Prompt_v4.4.md` | NEW — lockstep bump from v4.3 |

## Verified outcome

| Metric | Before v10.360 → After v10.360 |
|---|---|
| Branch sources | **2 parallel (drifting)** → **1 unified (org_config)** |
| Seeded branches | 21 (3 regions) → **94 (7 regions)** |
| Audit gates | 245 → **246** (G246 added) |
| Page smoke | 123/123 PASS (preserved — dict interface unchanged) |
| Static AST | 0 findings (preserved) |
| Dynamic render | 14/14 effective PASS (preserved) |
| Tests | +11 in v10.360 file; v10.358 + v10.359 updated (29/29 pass) |
| Verifier | 161 → **165 checks** |
| Master prompt | v4.3 → **v4.4** — lockstep (5 consecutive batches) |
| G162 baseline | 4022 (**54 consecutive zero-drift batches**) |

## Honest acknowledgements

1. **The legacy fallback in `utils/core.py` is still 21 entries.** That's deliberate — it's the safety net for degraded environments (CI without data fixtures, broken org_config.json). In production deployments it should never fire; G246 verifies the live source is org_config, not the fallback. If the fallback ever kicks in unexpectedly, downstream consumers will see only 21 branches and 3 regions, which is a degradation rather than a crash.

2. **The smaller fallback in `utils/virtual_bank_seed.py` is only 5 entries.** Different rationale — the seeder is a test/demo utility; if org_config isn't readable, falling back to a 5-branch toy bank is more honest than pretending you have 21. Production runs would notice and fix the config issue.

3. **Branch name format changed for downstream consumers reading the dict.** Pre-v10.360 names ended in " Branch" ("Mombasa Branch"). Post-v10.360 they don't ("Mombasa Kenyatta Avenue", "Westlands", "JKIA"). Any consumer that pattern-matched against the " Branch" suffix will silently miss matches. Searched the codebase — no consumer does that. Spot-check: the `BRANCH_REGION.get(unit, 'Head Office')` pattern in `pages/1_perform.py` and `utils/finance_hub_render.py` accepts whatever names exist in the dict. Safe.

4. **G244 sync check rewritten.** The pre-v10.360 G244 verified that `BRANCH_REGION` and `ECOBANK_BRANCHES` had matching counts via regex parsing of the hardcoded literal in `utils/core.py`. Post-v10.360 that regex no longer matches (the literal is replaced with a builder call). G244's Check 1 was rewritten to verify both derive from org_config; the determinism and minimum-viable-scale checks are unchanged.

5. **`SeedConfig.n_branches=21` from legacy code still works.** A user calling `SeedConfig(n_branches=21)` explicitly will still seed only 21 branches (the first 21 in dict-iteration order from org_config). It's not a hard error. Whether the first 21 are the "right" 21 depends on the consumer's intent.

6. **Region distribution skewed.** Of the 94 branches, 45 (48%) have region "Other". This is what's in org_config.json — not a v10.360 introduction. A future batch could re-classify the "Other" branches into the actual 7 regions per CBK guidance, but that's a data-cleanup task, not an architecture change.

7. **`utils.core.REGIONS` semantics shifted slightly.** Pre-v10.360 it was `['South', 'Central', 'North']` (legacy 3 regions). Post-v10.360 it's the sorted set of regions present in `BRANCH_REGION` values, excluding "Other" if a non-"Other" region exists. This means consumers iterating `REGIONS` now see 7 instead of 3. Spot-checked — no consumer assumes exactly 3 regions. Safe.

8. **Branch role generation gap amplified.** The roadmap-item-5 gap ("some branches lack the full role complement in synthesized data") was a 21-branch problem pre-v10.360. With 94 branches it's a 94-branch problem. Same shape, larger blast radius. Whichever batch closes it (v10.362+) should account for the expanded scope.

## On your end

1. Close Streamlit
2. Delete leftover subfolder extracts
3. Extract `a2z_v10360_session_cumulative.zip` flat into the A2Z workspace, overwriting everything
4. Run `python scripts\verify_local_state.py` → expect **ALL 165 CHECKS PASSED**
5. **Verify the unification:**
   ```
   python -c "
   from utils.virtual_bank_seed import get_ecobank_branches
   b = get_ecobank_branches()
   from collections import Counter
   print(f'Branches: {len(b)}')
   print(f'Regions: {dict(Counter(b.values()))}')"
   ```
   Expect: `Branches: 94, Regions: {'Nairobi': 27, 'Other': 45, ...}`
6. **Re-run the readiness audit:**
   ```
   python -c "from utils.virtual_bank_readiness import capture_readiness_report, format_readiness_summary; print(format_readiness_summary(capture_readiness_report()))"
   ```
   Boot probe now seeds across 94 branches.
7. Read `docs\Master_Prompt_v4.4.md` — fifth consecutive lockstep batch.
8. (Optional, takes >5min) Run audit → expect **246/246 PASS**

## v10.361 candidate — Link 7 MD tile bank-targets binding

Now genuinely the last PARTIAL link.

The MD's BSC view should display the bank-level "on track?" rollup against `data/bank_targets.json`, not against `data/target_cascade.json` (which is for staff/department/branch targets). The bank_targets.json file already exists and is well-formed:

```json
{
  "PBT|2026":                                  {"target": 650000000000.0, "buffer_pct": 0},
  "Total NFI|2026":                            {"target": 130000000000.0, "buffer_pct": 0},
  "Retail & MSME Deposit Growth|2026":         {"target": 400000000000.0, "buffer_pct": 0},
  "Commercial Deposit Growth|2026":            {"target": 5000000000000.0, "buffer_pct": 0},
  "CASA Ratio|2026":                           {"target": 60.0, "buffer_pct": 0},
  ...
}
```

What v10.361 needs to wire:
- When the MD (or any `can_view_all=True` role) loads the BSC, the target column reads from `bank_targets.json` for bank-level KPIs
- The actuals column shows the bank-wide aggregate (sum across all branches via existing rollup logic)
- The "on track?" indicator compares the two

The pieces are mostly there in `pages/1_perform.py`:
- BSC rollup logic exists
- MD role is identified via `users.json::can_view_all`
- bank_targets.json is loaded by existing code paths

What's missing: the MD-specific BSC view that uses bank_targets as the target source. Likely ~50-100 lines of conditional logic in `pages/1_perform.py` + maybe a small helper in `utils/`.

After v10.361, all 7 Football Team Test chain links are WIRED. v10.362 writes the end-to-end integration test → **Charter §2 PASSES**.

Want me to proceed with v10.361?
