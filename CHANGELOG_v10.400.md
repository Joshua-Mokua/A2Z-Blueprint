# Changelog — v10.400 Admin UI for Canonical Hierarchy Editing

**Date:** 2026-05-13
**Phase:** Phase C2 ARCHITECTURAL ENDPOINT — Target Cascade Rescue arc COMPLETE
**Audit:** G286 added
**Tests:** 12/12 PASSED in `test_v10400_canonical_admin_ui.py`
**Verifier:** 547/547 checks pass
**G162 baseline:** 4022 (93 consecutive zero-drift batches)
**Master prompt:** v4.42 → v4.43 (lockstep — 44 consecutive batches)

---

## Your direction

> "reporting lines can be set from the admin"

(Plus throughout the rescue arc: "this is to help us test all the modules", "at production the ADMIN can configure accordingly".)

## What v10.400 did

Built **production-time admin controls** for the canonical hierarchy. MD/admin can now reconfigure organizational reporting lines from within the app — no developer involvement needed.

### Component 1: Backend leaf module (`utils/canonical_admin.py`)

**~300 LOC, AST-verified leaf-pure (zero upward `utils.*` imports), 6 self-tests pass.**

| Function | Purpose |
|---|---|
| `load_canonical()` | Read `org_hierarchy_config.json` |
| `save_canonical(cfg, who, reason)` | Write with auto-backup + provenance stamps |
| `list_role_managers()` | Get clean role_manager_whitelist dict |
| `list_role_tiers()` | Get clean role_tiers dict |
| `get_branch_tier_threshold()` | Get branch_tier_threshold (default 4) |
| `set_role_managers(role, mgrs, who, reason)` | Update reporting line for role |
| `remove_role(role, who, reason)` | Remove from rmw + tiers |
| `set_role_tier(role, tier, who, reason)` | Set seniority tier (0-9) |
| `set_branch_tier_threshold(t, who, reason)` | Set bank-wide branch threshold |
| `regenerate_cascade_from_canonical(who, reason)` | Trigger cascade regenerator |
| `validate_canonical()` | Cycle detection + tier inversion + missing managers |
| `log_change(who, action, target, old, new, reason)` | Append to provenance ledger |
| `read_change_log(limit)` | Read last N changes |

**Auto-backup**: every save creates `data/_canonical_backups/org_hierarchy_config.<timestamp>.before.json` so any change is reversible.

**Provenance**: every mutation stamps `last_modified`, `last_modified_by`, `last_reason` into canonical, AND appends to `data/canonical_change_log.json` (capped at 1000 entries).

**Validation**: detects cycles in reporting lines, tier inversions (subordinate above manager), and managers referenced but not defined in tiers.

### Component 2: Streamlit page (`pages/_admin_canonical.py`)

6 views available to MD/admin:

| View | What it shows |
|---|---|
| **📋 Overview** | 4 metrics (mapped roles / tier entries / threshold / valid Y/N), tier distribution table, validation issues |
| **🔗 Reporting Lines** | Search bar + filtered table of all role mappings + edit existing (manager order matters — first = primary) + add new role mapping + remove role |
| **🎚️ Role Tiers** | Search + filtered table + edit tier 0-9 per role |
| **⚙️ Threshold** | Number input to set branch_tier_threshold per bank |
| **🔄 Regenerate** | Big button → calls regenerator → spinner → status. Auto-backup. |
| **📜 Change Log** | Table of last 100 changes: when / who / action / target / old → new / reason |

### Component 3: Integration into `pages/7_admin.py`

- Added: `from pages._admin_canonical import render_canonical_admin`
- Added 8th tab label: `🎯 Canonical Hierarchy`
- Added: `render_canonical_admin(sub[7], uname)` in the People & Org section
- No other code changes to 7_admin.py

## Architectural arc complete

**Phase C2 progression — canonical-driven design end-to-end:**

| Batch | Layer | What |
|---|---|---|
| v10.395 | Engine reads canonical | WITHIN_BRANCH_ROLE_PAIRS derived from config |
| v10.396 | Canonical aligned | SBM tier 3→4, DSR→BM/SBM (Joshua's clarification) |
| v10.397 | Cascade regenerated | target_cascade.json rebuilt from canonical |
| v10.398 | HQ canonical extended | 4 new chiefs + every role mapped; TC42 resolved |
| v10.399 | Joshua corrections | 7-point production-truth corrections applied |
| **v10.400** | **Admin edits canonical** | **MD reconfigures from UI; regenerate button** |

After v10.400, deploying to a new bank looks like:
1. Install A2Z with default Ecobank Kenya canonical
2. Bank's MD opens admin → Canonical Hierarchy
3. Edits reporting lines / tiers / threshold to match their org
4. Clicks "Regenerate Cascade"
5. Their KPI cascade is live

No developer involvement. No code changes. No SQL.

## Engine state preserved

| Metric | v10.399 | v10.400 |
|---|---|---|
| Cycles | 0 | **0** ✓ |
| Cross-branch | 0 | **0** ✓ |
| Multi-sender | 0 | **0** ✓ |
| Rep_critical | 0 | **0** ✓ |
| Cascade entries | 25,488 | **25,488** ✓ |

Adding admin UI doesn't change engine state. Cascade only regenerates when admin clicks the button.

## Verified outcome

| Metric | Value |
|---|---|
| Audit gates | 285 → **286** |
| Tests | 259 → **270** (+12 new) |
| Verifier | 543 → **547 checks** |
| Master prompt lockstep | **44/44 consecutive batches** |
| G162 baseline | 4022 (**93 consecutive zero-drift batches**) |

## 12 honest acknowledgements

1. **Phase C2 rescue arc COMPLETE.** From v10.391's deep diagnosis to v10.400's admin UI — every problem identified has been addressed.

2. **Backend + UI separation.** `canonical_admin.py` is a leaf module — works without Streamlit. Page is the presentation layer. Easy to test, easy to script-call.

3. **Auto-backup every save.** Reversibility built in. Nobody can break canonical without leaving a restore point.

4. **Provenance ledger.** Every change traced to user + reason. Audit trail for compliance.

5. **Validation runs free.** Cycle detection + tier sanity surface bad edits before they break cascade.

6. **Regenerate button is the "publish" gesture.** Admin edits canonical, then explicitly chooses to push it to cascade. Two-stage edit/publish workflow.

7. **0/0/0/0 preserved.** Adding the admin UI doesn't touch live cascade data; only Regenerate does.

8. **Streamlit page is ~250 LOC.** Compact, readable, well-organised by view.

9. **8th tab integrated.** Joshua's existing People & Org section now has Canonical Hierarchy alongside Organisation/Users/Permissions/etc.

10. **Bank-portable.** Default canonical ships with the codebase; admin reconfigures for their reality.

11. **44 consecutive lockstep batches.** Master prompt and code remain in sync.

12. **The body now has its nervous system AND its steering wheel.** Engine + cascade work; admin can adjust.

## On your end

1. Close Streamlit
2. Extract `a2z_v10400_patch.zip` flat on top of v10.399 state
3. Run `python scripts\verify_local_state.py` → expect **547/547**
4. **Open Streamlit, login as admin/MD**
5. Navigate to **System Administration → People & Org → 🎯 Canonical Hierarchy**
6. Try each view:
   - **Overview**: should show 130 roles / 142 tiers / threshold 4 / Valid 🟢
   - **Reporting Lines**: search for "Bancassurance" — should see Branch Manager primary + GM Banc fallback
   - **Role Tiers**: search for "Chief" — all chiefs at tier 1
   - **Threshold**: try changing to 5 then back to 4 (logs the change)
   - **Regenerate**: click button → spinner → "Regenerated 25,488 cascade entries"
   - **Change Log**: see your test edits
7. Tell me **"continue"** → v10.401 = period harmonization (TC38: quarterly fixed vs annual cascade)

## What v10.401 will do

Address TC38 — periods are inconsistent:
- `fixed_kpis.json` uses **quarterly** keys (2026-Q1, 2026-Q2, ...)
- `bank_targets.json` uses **annual** keys (PBT|2026)
- `target_cascade.json` uses **annual** keys (300001|PBT|2026)

When an annual cascade asks "is KPI X fixed?", we currently union all quarters. But mid-year a fixed-in-Q1 KPI may have changed status in Q3. Decide canonical period scheme + harmonize across the three files.

Continue?
