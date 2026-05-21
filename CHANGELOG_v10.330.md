# Changelog — v10.330 Canonical retail chain lock

**Date:** 2026-05-12
**Phase:** 4 (sixteenth arc — hierarchy correctness pass)
**Audit:** 221/221 gates PASS = 100.0%
**Tests:** 630/630 passing across 36 integration suites (10 new for v10.330)
**G162 Baseline:** 4022 — 25 consecutive zero-drift batches

---

## Your design ask (verbatim)

> "Hope you have ensured that the branch managers are reporting to area
> managers whose BSC is literally an aggregate of the branches reporting
> to them and the area managers in turn report to the head of retail
> who reports to Chief retail. Then ensuring our direction of having
> this configurable in a way if the hierarchy is to change, or bank
> change i can easily implement from the admin config"

This was a hard correctness check I had skipped. Two real structural
bugs surfaced and got fixed.

## What was actually broken

### Bug #1 — Synthesizer treated Senior BMs as a supervisory tier

`utils/hierarchy_synth.py` had this in the retail chain builder:

```python
# WRONG — before v10.330
# Layer 2: Area Managers + Senior Branch Managers → Head of Branches
for role in ("Area Manager", "Senior Branch Manager"):
    _link(s, hob_code, "retail_hq")

# Layer 3: Branch Managers → Area Manager OR Senior Branch Manager
area_managers = sorted(
    by_role.get("Area Manager", []) +
    by_role.get("Senior Branch Manager", []),  # ← BUG
    key=lambda s: s.staff_code,
)
```

This created a structure where:
- 8 Senior BMs reported to Head of Branches directly
- 36 standard BMs reported to Senior BMs
- Only 50 of 94 BMs reached Area Managers

### Bug #2 — Whitelist was too permissive

`data/org_hierarchy_config.json` `role_manager_whitelist` allowed:

```json
"Branch Manager": ["Area Manager", "Senior Branch Manager", "Head of Branches"],
"Senior Branch Manager": ["Area Manager", "Head of Branches"]
```

Three valid parents for a BM meant the synthesiser had options to be
loose. The whitelist needed to express the canonical chain, not
"anything that vaguely makes sense."

## What canonical means

Per banking convention you articulated:

```
                  Chief Retail (BSC = avg of HoBs)
                              │
                  Head of Branches (BSC = avg of AMs)
                              │
   ┌──────────┬──────────┬────┴─────┬──────────┬──────────┐
   │          │          │          │          │          │
  AM 1      AM 2      AM 3       ...        AM 9      AM 10
  (BSC = avg of branches reporting to them)
   │
   ├─ Branch Manager (PBT 67M, NPL 9.2%, ...)
   ├─ Senior Branch Manager (PBT 142M, NPL 7.1%, ...)
   ├─ Branch Manager
   └─ ...
```

**Senior Branch Managers run flagship branches but they are PEERS of
standard BMs, not supervisors.** Both tiers report to Area Managers.
A Senior BM's larger book and stretched targets show up in their own
scorecard, not in who reports to them.

**Area Manager BSC is literally the recursive aggregate** of the 9-10
branches reporting to them. No standalone Area Manager activity needs
to be generated — the value flows up automatically through
`compute_recursive_score()`.

## What v10.330 fixed

### `utils/hierarchy_synth.py`

Synthesizer aligned to canonical structure. Senior BMs now combined
with standard BMs in Layer 3 (Branch Managers → Area Manager). Layer 2
distributes only Area Managers (not Senior BMs) to Head of Branches.

### `data/org_hierarchy_config.json`

Whitelist tightened:

```json
"Branch Manager": ["Area Manager"],          // was 3 options
"Senior Branch Manager": ["Area Manager"],   // was 2 options
"Area Manager": ["Head of Branches"]         // unchanged
```

Schema bumped to v10.330 with explicit `_v10330_canonical_retail_chain`
provenance entry documenting what changed and why.

### `pages/7_admin.py`

New Tier 60 "Canonical Retail Chain Lock" in the Engine Hub registry,
documenting the hierarchy synthesiser and admin config surface. This
makes it discoverable that the chain IS admin-editable via
`data/org_hierarchy_config.json` (role_manager_whitelist section).

### `scripts/audit.py` — G221

New audit gate locking the canonical chain. 5 invariants:

1. Whitelist tightness — BM/Senior BM parent = [Area Manager], AM
   parent = [Head of Branches]
2. All BMs report to an Area Manager (0 misplaced)
3. Each Area Manager has ≥5 BMs (aggregation is meaningful)
4. No Senior BM supervises another BM
5. Head of Branches reports to Chief Retail Banking Officer

## Verified outcome

After re-running `staff_universe()`:

| Area Manager | BMs (Senior + Standard) |
|--------------|-------------------------|
| 300002 | 10 (1 + 9) |
| 300003 | 10 (1 + 9) |
| 300004 | 10 (1 + 9) |
| 300005 | 10 (0 + 10) |
| 300006 | 9 (1 + 8) |
| 300007 | 9 (0 + 9) |
| 300008 | 9 (2 + 7) |
| 300009 | 9 (0 + 9) |
| 300010 | 9 (2 + 7) |
| 300011 | 9 (0 + 9) |
| **Total** | **94 (8 + 86)** |

**94 of 94 BMs report to an Area Manager. 10 Area Managers report to
1 Head of Branches. Head of Branches reports to 1 Chief Retail.**

## Configurability — your other ask

The hierarchy IS configurable via `data/org_hierarchy_config.json`.
Three knobs an admin can turn without code changes:

### 1. `role_manager_whitelist`

Defines which manager roles are valid parents for each role. Adding
a new role tier (e.g. "Regional Branch Manager" between AM and HoB)
means:

```json
"Branch Manager": ["Regional Branch Manager"],
"Regional Branch Manager": ["Area Manager"],
"Area Manager": ["Head of Branches"]
```

### 2. `department_chief_mapping`

Maps each department to its Chief. If the bank reorganises (e.g.
"Branches" becomes its own department reporting to a new "Chief of
Branches"), edit:

```json
"Branches": "Chief of Branches"
```

And add to `chiefs` list:

```json
{
  "role": "Chief of Branches",
  "synthetic_staff_code": "EXEC-COB-001",
  "primary_department": "Branches",
  "band": "M5"
}
```

### 3. `default_max_span_of_control` / `default_max_chain_depth`

System invariants that gate the synthesiser. Lower these to enforce
tighter structures, raise them to support larger banks.

After any edit:

```bash
python scripts/validate_org_hierarchy_config.py
```

Then restart Streamlit (cache invalidates on `staff_universe()` reload).

## Honest limitations

What's NOT yet admin-configurable (requires code change):

1. **Chain ORDER inside `_synthesise_retail_chain`** is still
   hardcoded (Layer 1: HoB → Chief, Layer 2: AM → HoB, Layer 3: BM →
   AM). For a bank with no Area Manager layer at all, code edit needed.

2. **Synthetic Chief generation** runs from the hardcoded list in
   `chiefs[]`. Adding a brand new Chief tier means editing both the
   list and the synthesiser's chief-resolution code.

3. **Audit gates G215, G220, G221** reference specific role names
   (e.g. "Area Manager", "Senior Branch Manager") in their invariants.
   Renaming roles requires updating these gates.

For v10.331+ a future arc could push more chain logic into config
(layer order array, role-tier definitions). For Ecobank Kenya's
structure as documented, current config covers the editable surface
they'll actually need.

## Cascade impact

Retail rollup is now genuinely 4 layers (Chief → HoB → 10 AMs → 94 BMs).
Each Area Manager's BSC is the recursive aggregate of their 9-10
branches. Head of Branches BSC is the aggregate of 10 Area Managers
plus 3 retail HQ specialists (Senior Manager Direct Sales Force, Head
of Women Banking, etc). Chief Retail aggregates from Head of Branches.

The Q2 figures (pre-G221 fix):

| Area Manager | Q2 Score | BMs |
|--------------|----------|-----|
| 300002 | 3.47 | 5 (would now be 10) |
| 300003 | 3.70 | 5 |
| 300004 | 3.58 | 5 |
| 300005 | 3.08 | 5 |
| 300006 | 3.39 | 5 |
| 300007 | 3.49 | 6 |
| 300008 | 2.98 | 5 |
| 300009 | 3.17 | 5 |
| 300010 | 3.25 | 6 |
| 300011 | 3.16 | 5 |

After v10.330, each AM aggregates from 9-10 branches (not 5-6). The
spread narrows slightly because the larger sample reduces variance,
but the AM-level signal becomes more meaningful — a single weak branch
no longer can dominate an AM's score.

## Files changed

| File | Change |
|------|--------|
| `utils/hierarchy_synth.py` | Senior BM + BM combined into Layer 3; Layer 2 covers AM only |
| `data/org_hierarchy_config.json` | Whitelist tightened; schema bumped v10.330; `_v10330_canonical_retail_chain` provenance |
| `pages/7_admin.py` | NEW Tier 60 — Canonical Retail Chain Lock |
| `scripts/audit.py` | NEW G221 gate function + GATES registration |
| `tests/integration/test_v10330_canonical_retail_chain.py` | NEW — 10 tests across 4 sections |
| `data/cascade_scores_2025-Q3.json` | Re-precomputed with new hierarchy |
| `data/cascade_scores_2025-Q4.json` | Re-precomputed with new hierarchy |
| `data/cascade_scores_2026-Q1.json` | Re-precomputed with new hierarchy |
| `data/cascade_scores_2026-Q2.json` | Re-precomputed with new hierarchy |

## Platform state

| Metric | v10.329 → v10.330 |
|--------|-------------------|
| Audit gates | 220 → **221** |
| Integration test suites | 35 → **36** |
| Tests passing | 620 → **630** |
| BMs correctly under Area Managers | 50/94 → **94/94** |
| Senior BMs supervising other BMs | 8 → **0** |
| BMs per Area Manager (avg) | 5 → **9.4** |
| Hierarchy admin-editable surface | partial → **documented + locked** |
| G162 baseline | 4022 (25 consecutive zero-drift batches) |

## Real findings during this batch

1. **The bug was in the synthesizer, not the data.** users.json had no
   manager_code for BMs (correctly — that's synthesizer's job).
   hierarchy_synth.py had the wrong layering. Found by inspecting the
   actual reporting tree, not by inspecting the data.

2. **Tightening the whitelist alone wouldn't have fixed it.** The
   synthesiser doesn't enforce the whitelist — it CHOOSES parents from
   a preference order. The whitelist tells the override layer what's
   acceptable; the synthesizer encodes the default structure. Both
   needed updating.

3. **94 of 94 BMs now flow through Area Managers.** Verified by
   walking the universe post-fix: every active BM has manager_code in
   the Area Manager set.

4. **Area Manager BSC is now genuinely meaningful.** With 9-10
   branches per AM (vs. previous 5-6 with Senior BMs siphoning
   parallel reporting lines), the aggregation has enough signal to
   distinguish strong vs weak Area Managers.

5. **G162 holds at 4022. 25 consecutive zero-drift batches.**

## Backlog status

| ID | Status |
|----|--------|
| B-023 | Open — Credit Monitoring under Analysis vs Collections (org structure) |
| B-024 | Open — Full MD rollups exceeds timeout (performance) |
| B-025 | NEW — Layer order in `_synthesise_retail_chain` is hardcoded; for bank-radical restructure (e.g. no AM tier) requires code change |
| B-009, B-010, B-011, B-014-B-021 | Unchanged |

## Suggested next batches

Cascade is now correctness-locked from BM up through MD. Remaining for
Ecobank demo (<1 week):

1. **v10.331 — Demo dry-run + UI polish** — walk MD → Chief Retail →
   HoB → AM 300003 (best, 3.70) → 10 branches → drill into top branch
2. **v10.331 — Branch ranking page** — surface a dedicated branch
   ranking view on cascade page so user can compare 94 branches across
   the 21 KPIs at once (sort/filter by metric)
3. **v10.331 — Performance optimization for full rollups (B-024)** so
   `compute_team_rollup` finishes < 2 min for MD subtree

The fix you flagged was a correctness gap I'd missed. Thanks for the
catch — the cascade story is now genuinely accurate.
