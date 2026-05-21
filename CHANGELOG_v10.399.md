# Changelog — v10.399 Joshua's 7-Point HQ Canonical Corrections

**Date:** 2026-05-13
**Phase:** Phase C2 user-confirmation batch — Target Cascade Rescue arc
**Audit:** G285 added
**Tests:** 11/11 PASSED in `test_v10399_joshua_corrections.py`
**Verifier:** 543/543 checks pass
**G162 baseline:** 4022 (92 consecutive zero-drift batches)
**Master prompt:** v4.41 → v4.42 (lockstep — 43 consecutive batches)

---

## Your direction

> 1. "Managing Director" synthetic — DELETE, keep CE&MD William
> 2. Trade Finance split — Yes, correct
> 3. Head of DFS — under CCO (not CIO), DCOs at branches dotted line to Head of DFS
> 4. Manager Card Operations — under Head of DFS
> 5. Corporate Sales Dealer — correct under Treasury
> 6. Trade Finance Back Office Manager — under Head of Operations who reports to COO
> 7. Admin — this is me, my developer/MD-login account

## What v10.399 did

### 3 substantive changes
1. **Synthetic Managing Director deleted** from users.json (`exec_md_001` removed; only William Mwanake = `Chief Executive & Managing Director` remains)
2. **Head of DFS moved CIO → CCO** in `org_hierarchy_config.json::role_manager_whitelist`
3. **Admin role moved CHRO → MD** in canonical

### 4 confirmations (no change needed)
4. Manager Card Operations remains under Head of DFS (chain now CCO → DFS → Card Ops)
5. Corporate Sales Dealer remains under Head of Treasury → CFO
6. Trade Finance Back Office Manager remains under Head of Operations → COO
7. Trade Finance split (relationships → CCO, operations → COO) confirmed

## Engine audit — zero-state preserved

| Metric | v10.398 | v10.399 |
|---|---|---|
| Cycles | 0 | **0** ✓ |
| Cross-branch | 0 | **0** ✓ |
| Multi-sender | 0 | **0** ✓ |
| Critical rep-sender | 0 | **0** ✓ |
| Warn rep-sender | 2 | 2 |
| Cascade entries | 25,488 | **25,488** |
| users.json size | 1450 | 1449 (synthetic MD removed) |

## C1 outstanding question — RESOLVED

The C1 concern (canonical MD role) is now resolved:
- **Canonical MD**: `Chief Executive & Managing Director` (William Mwanake, staff_code 300001, username william001)
- **Reasoning**: Most banks refer to their CEO as the senior-most figure; combining CEO and MD into one role matches Ecobank Kenya's actual structure
- **Production admin** can override naming if needed for other banks deploying A2Z

## Test deltas

- **2 v10.391 tests retired** (`_retired_v10399_*`):
  - `test_v10391_tc6_two_md_roles_in_users` — TC6 expected two MD roles; v10.399 deleted the synthetic one
  - `test_v10391_tc7_synthetic_csuite_isolated_from_cascade` — TC7 asserted EXEC-* synthetic chiefs isolated from cascade; v10.397/v10.398 regeneration now includes them
- **1 v10.398 test updated** (`test_v10398_cio_has_dfs_and_ict_subtrees` → `test_v10398_cio_has_ict_subtree`): DFS moved to CCO per Joshua
- **11 new v10.399 tests**

Same pattern as v10.392/v10.397/v10.398: bugs fixed → tests asserting bugs correctly retire.

## Verified outcome

| Metric | Value |
|---|---|
| Audit gates | 284 → **285** |
| Tests | 249 → **259** (+11 new, −2 retired in v10.399) |
| Verifier | 537 → **543 checks** |
| Master prompt lockstep | **43/43 consecutive batches** |
| G162 baseline | 4022 (**92 consecutive zero-drift batches**) |

## Phase C2 progress

| Batch | Concern | Status |
|---|---|---|
| ~~v10.391-v10.398~~ | Diagnosis through HQ canonical extension | ✅ |
| ~~**v10.399**~~ | **Joshua's 7-point corrections applied (all hanging roles resolved)** | ✅ **DONE** |
| v10.400 | Admin UI for editing hierarchy from app | next |
| v10.401 | Period harmonization (TC38) | |
| v10.402 | NPL naming consolidation (TC39) | |

## 10 honest acknowledgements

1. **All 7 hanging roles closed.** Your explicit answers gave me a clean canonical that matches your production reality.

2. **C1 RESOLVED** — only one MD record now (William Mwanake as Chief Executive & Managing Director). Production admin can adjust naming for other banks.

3. **DFS under CCO** — corrected my initial CIO assumption. Digital banking is commercially-led, not technology-led. The DCO dotted-line at branches makes sense given they're customer-facing for digital services.

4. **Admin is YOU** — not a generic HR role. Updated canonical to reflect your actual usage (developer monitoring + MD login backstop).

5. **Engine zero-state preserved.** Corrections didn't disrupt anything — all 4 structural metrics still zero.

6. **Cascade count unchanged** at 25,488 because the changes were role-reporting-line edits (Head of DFS moved up), not staff-membership changes.

7. **users.json now reflects production truth** with synthetic test record (`exec_md_001`) gone.

8. **Backups preserved** at `data/_v10399_backups/`: users.json + org_hierarchy_config.json + target_cascade.json.

9. **43 consecutive lockstep batches.** No drift between master prompt and code.

10. **The body matches your description now.** Production-deploy this canonical, run regenerator, and every staff has the reporting line Joshua described in this session.

## On your end

1. Close Streamlit
2. Extract `a2z_v10399_patch.zip` flat on top of v10.398 state
3. Run `python scripts\verify_local_state.py` → expect **543/543**
4. Engine check: `python utils\cascade_structure_engine.py` → 0/0/0/0
5. Spot-check: open BSC as William (MD) — should see bank-wide cascade view; open as any branch staff — should see proper per-branch cascade
6. Tell me **"continue"** → v10.400 = admin UI for editing hierarchy from app (your production-time "reporting lines from admin" requirement)

## What v10.400 will do

1. Add hierarchy admin section to `pages/7_admin.py` (or new `pages/16_org_admin.py`)
2. MD/admin can:
   - Add/remove entries in `role_manager_whitelist`
   - Adjust `role_tiers`
   - Set `branch_tier_threshold` per bank
   - Delete/add chiefs from the app
3. "Regenerate Cascade" button → re-run regenerator after canonical edits
4. Provenance log of changes (who, when, what)

Continue?
