# Changelog — v10.457 Manifest Invariant Hotfix

**Date:** 2026-05-15
**Phase:** Runtime KeyError hotfix + invariant lock
**Audit:** G343 added (cumulative 345 gates)
**Tests:** 11/11 PASSED in `test_v10457_manifest_invariant.py`
**Combined regression:** 597 v10.4xx tests PASSED (586 prior + 11 new)
**Verifier:** 892 → **897** (+5 v10.457 checks)
**G162 baseline:** 4022 (151 consecutive zero-drift batches)
**Master prompt:** v5.00 → v5.01 (lockstep — 102 consecutive batches)

---

## 🛠️ Your error report

```
KeyError: 'current_module_key'
  File "...\app.py", line 900, in _build_dept_pages
    page = _pg(path, entry["title"], entry["icon"], entry["current_module_key"])
                                                    ~~~~~^^^^^^^^^^^^^^^^^^^^^^
```

## 🔍 Root cause

`app.py:900` reads `entry["current_module_key"]` from each `pages/_manifest.json` entry. Two recent batches added pages without complete manifest registration:

| Batch | Page | Defect |
|---|---|---|
| **v10.448** | `pages/82_credit_approvals.py` | Added to manifest but `current_module_key` field never set |
| **v10.454** | `pages/85_chief_credit_centre.py` | NEW Chief Credit Centre — never registered in manifest at all |

The crash hit when navigation built credit-dept pages and dictionary-accessed the missing key with `entry["current_module_key"]` (which throws KeyError instead of returning None).

## ✅ Fix

### 1. `pages/_manifest.json` — both entries corrected

**`82_credit_approvals.py`** — added missing field:
```json
{
  "title": "Credit Approvals",
  "icon": "🏛️",
  "department_primary": "credit",
  "module_path": "credit.approvals",
  "current_module_key": "approvals",   // ← added
  "secondary_visibility": []
}
```

**`85_chief_credit_centre.py`** — newly registered (mirrors `81_chief_hr_centre.py` pattern):
```json
{
  "department_primary": "credit",
  "module_path": "credit.chief_centre",
  "secondary_visibility": [],
  "title": "Chief Credit — 360 Command Centre",
  "icon": "🏛️",
  "current_module_key": "chief_centre",
  "description": "Chief Credit panoramic surface. 6 doctrine tabs..."
}
```

**130 pages total · 0 entries missing required fields.**

### 2. NEW `G343 — Manifest Invariant Gate`

Locks the contract: **every manifest entry MUST have** `title` + `icon` + `current_module_key` + `department_primary`. Future page additions cannot ship without complete manifest registration. This gate runs on every audit and would have caught both prior defects.

## What didn't change

Health remains exactly the same — this is a runtime fix, not a doctrine batch:

| Module | Health |
|---|---|
| Admin | 74.8% |
| HR | 70.5% |
| BSC & Cascade | 75.6% |
| Credit | 60.3% |
| ICT | 63.1% |
| **Average (5 organs)** | **68.9%** |

| Metric | v10.456 | v10.457 |
|---|---|---|
| Audit gates | 344 | **345** (G343) |
| v10.4xx tests | 586 | **597** (+11) |
| Verifier | 892 | **897** (+5) |
| Lockstep batches | 101 | **102** consecutive |
| G162 baseline | 4022 (150) | 4022 (**151** zero-drift) |
| Manifest pages | 129 | **130** (+85_chief_credit_centre) |
| Body health (G330) | 91.1% | 91.1% ✓ |
| 360 harmony | 100% | **100%** ✓ |
| BSC rescue | 100% | **100%** ✓ |

## Rescue path to CERTIFIED × 5 (continues from v10.456)

| v | Mission | Expected avg |
|---|---|---|
| ~~v10.457~~ | **Manifest hotfix + invariant gate** | **DONE — KeyError eliminated** |
| v10.458 | Stress test harness + scalability validation (criteria #10 + #14) | ~74% |
| v10.459 | Cross-organ event sync + super users + notification broadcast | ~80% |
| v10.460 | 9 missing credit roles + credit→HR bridge | ~85% |
| v10.461 | `module_revival.md` × 5 + `capacity_plan.md` × 5 | **CERTIFIED × 5** |

## On your end

1. Close Streamlit · extract `a2z_v10457_patch.zip` on v10.456 (overwrite all)
2. `python scripts/verify_local_state.py` → **897/897**
3. Restart Streamlit — the KeyError at app.py:900 should be gone
4. Navigate to **Credit dept** — you should now see "🏛️ Chief Credit — 360 Command Centre" in the nav
5. Validate manifest invariant:
   ```python
   import json
   m = json.load(open("pages/_manifest.json"))
   missing = [f for f, e in m["pages"].items()
              if not all(k in e for k in ("title", "icon", "current_module_key", "department_primary"))]
   print(f"Entries missing required fields: {len(missing)}")  # 0
   ```
6. Tell me **"continue"** → v10.458 = stress test harness + scalability validation

## The honest read

This was a runtime crash caused by **incomplete manifest registration** in two prior batches. Both pages worked when accessed directly via URL, but the dept-navigation builder threw KeyError because it dictionary-indexed (which is strict). The fix is one-line per page in the manifest JSON; the bigger value is **G343 locking the invariant** so this class of bug can't recur.

**Tell me "continue"** for v10.458 — stress test harness + scalability validation toward CERTIFIED × 5.
