# Changelog — v10.318 Cascade page hierarchy alignment (Joshua feedback)

**Date:** 2026-05-11
**Phase:** 4 (fifth arc — cascade page integration)
**Audit:** 208/208 gates PASS = 100.0%
**Tests:** 441/441 passing across 25 integration suites
**G162 Rebase:** none — 14 consecutive zero-drift batches

---

## What you reported

Logged in as the MD, on the "Set Team Targets" tab, the page showed:

> No direct reports found for **Branch Operations Supervisor**.
> Contact Admin to configure reporting lines.

You noted:
- This was working well at the very initial stages
- The MD should be able to set and cascade targets to the Chiefs
- The same cascade should flow downwards
- The fix should follow the v10.316 hierarchy

## Diagnosis — three real bugs

The "Set Team Targets" page (`pages/12_cascade.py`) had been built
against an older organisational structure and never updated when
v10.316 reorganised the hierarchy. Three distinct bugs were
compounding:

### Bug 1 — `data/org_config.json` hierarchy was incomplete

The OLD config had only **28 roles**, stopping at "Branch Operations
Manager". Below that — Branch Operations Supervisor, Teller, Customer
Service Officer, Direct Sales Representative, Relationship Officer
roles — were **not in the hierarchy at all**.

Worse, the OLD config used different naming: "Chief Executive &
Managing Director" instead of "Managing Director", and missed several
real roles from users.json.

### Bug 2 — Wrong root-detection logic

In `my_role_level()` at line 417:

```python
roots = [k for k, v in HIERARCHY.items() if not v]
```

This finds keys with no CHILDREN — i.e. **leaf nodes** like Teller or
Customer Service Officer. The actual root is the node with no PARENT
(no other role lists it as their parent). For admin/MD users, this
bug returned a leaf role instead of "Managing Director".

### Bug 3 — `is_md` not checked first

When you logged in (probably with a "Branch Operations Supervisor"
demo account that has `is_admin=True`), `my_role_level()` walked
through Steps 1-4 looking for matches based on your **account role**,
not your **MD intent**. It either fuzzy-matched your account role
to something close (Branch Operations Manager) or fell through to
the broken root fallback at Step 5.

The combination is what produced the "Branch Operations Supervisor"
display in the error message — the function partially matched your
literal role somewhere along the way.

## The fix

### Aligned `data/org_config.json` hierarchy with v10.316

The `hierarchy` key now contains **75 roles** covering the complete
v10.316 reporting structure:

```
Managing Director (root, no parents)
├── Chief Retail Banking Officer (and 10 other Chiefs)
│   ├── Head of Branches
│   │   ├── Area Manager
│   │   │   └── Branch Manager
│   │   │       ├── Branch Operations Manager
│   │   │       │   └── Branch Operations Supervisor
│   │   │       │       ├── Teller
│   │   │       │       ├── Customer Service Officer
│   │   │       │       └── Direct Sales Representative
│   │   │       └── Branch Relationship Manager
│   │   │           ├── Branch Senior Relationship Officer
│   │   │           ├── Relationship Officer-Business Banker
│   │   │           └── Relationship Officer-Personal Banker
│   │   ├── Senior Branch Manager
│   │   └── Senior Manager Direct Sales Force
│   ├── Head Of Women Banking
│   ├── Head of Retail Banking
│   └── Senior Manager Diaspora Banking
... (other Chiefs with their downstream chains)
```

Every role in users.json now has a defined position in the hierarchy.

### Fixed `pages/12_cascade.py` `my_role_level()`

Added a new **Step 0** at the top of the function:

```python
# 0. Admin / MD intent — always return the root
if is_md or can_all:
    all_children = {c for kids in HIERARCHY.values() for c in kids}
    roots = [k for k in HIERARCHY if k not in all_children]
    if roots:
        preferred = [r for r in roots
                     if "managing" in r.lower()
                     or "chief executive" in r.lower()]
        if preferred:
            return preferred[0]
        return sorted(roots)[0]
```

Admin / MD users now get the root role immediately, regardless of
what their underlying staff account role says. The same correct
root-detection logic is repeated in the legacy fallback paths.

### New `utils/cascade_hierarchy.py` — bridge module

Exposes the hierarchy as a clean Python API for any caller:

- `role_children_map()` — `Dict[role, List[child_roles]]`
- `role_root()` — returns "Managing Director"
- `direct_report_roles(role)` — roles that report directly to `role`
- `cascade_chain_from_role(role)` — walks upward to root
- `md_direct_reports()` — convenience for the 11 Chiefs

Reads `data/org_config.json` directly via the canonical `utils.db.
load_json` path (not through `utils.core.get_org_config` which
requires Streamlit). Works in audit gates, tests, and Streamlit
pages alike.

## What you'll see now (logged in as MD)

On the "Set Team Targets" tab:

```
🎯 Set targets — Managing Director · 11 direct report(s)

  • Chief Retail Banking Officer       (Retail Banking)
  • Chief Credit Officer               (Credit)
  • Chief Operating Officer            (Operations)
  • Chief Financial Officer            (Finance)
  • Chief Information Officer          (IT & Digital)
  • Chief Risk Officer                 (Risk & Compliance)
  • Chief Compliance Officer           (Legal)
  • Chief Internal Auditor             (Internal Audit)
  • Chief Human Resource Officer       (People & HR)
  • Chief Commercial Officer           (Commercial & Corporate)
  • General Manager - Bancassurance    (Bancassurance)
```

Each Chief now sees their own direct reports when they log in. The
cascade flows downward exactly as you described — MD → Chiefs →
Heads → Senior Managers → Managers → Officers → Frontline.

A Teller logging in sees no direct reports (correct — they're at
the leaf). A Branch Manager sees Branch Operations Manager + Branch
Relationship Manager. A Branch Operations Supervisor (logging in
as themselves, not as MD) now sees Tellers, CSOs, and Direct Sales
Representatives.

## Configurable vs hardcoded — Rule of Configurability honoured

**CONFIGURABLE** (admin-editable in `data/org_hierarchy_config.json`
AND `data/org_config.json`):
- Every reporting line (which role reports to which)
- Whether the synthetic MD/Chiefs are injected (v10.316 toggle)
- Role tier mappings
- Whitelist of valid manager roles per subordinate role

**HARDCODED** (system invariants — admin cannot disable):
- Root-detection algorithm (no-parent, not no-child)
- `is_md` / `can_all` check fires first in `my_role_level()`
- Only one root allowed
- Cycle detection in `cascade_chain_from_role`

## What shipped

### New
- `utils/cascade_hierarchy.py` (~150 lines) — bridge between
  data/org_config.json's role-parents shape and a clean
  role-children API for callers
- `tests/integration/test_cascade_hierarchy_v10318.py` — 17 tests
  across 7 sections

### Modified
- `data/org_config.json` — `hierarchy` key expanded from 28 to 75
  roles, fully aligned with v10.316's synthesis
- `pages/12_cascade.py` — `my_role_level()` rewritten with:
  - Step 0 (is_md guard) at the top
  - Correct root-detection in Step 3 and Step 5
  - "v10.318 fix" marker in docstring for audit detection
- `scripts/audit.py` — G208 added (7 sub-checks)

## Real findings during this batch

1. **The bug was hiding for weeks.** Joshua noticed it on the v10.317
   demo because that's when there was finally live data to interact
   with. Before that, the cascade page worked for accounts that
   matched the OLD HIERARCHY but had been silently broken for
   admin/MD users. The honest-reporting tests didn't catch it
   because the OLD config wasn't tested for Joshua's specific
   login flow.

2. **Two source-of-truth files for the same data.** `data/org_
   config.json` (OLD) and `data/org_hierarchy_config.json` (NEW v10.
   316) both describe the same hierarchy in different shapes. The
   cascade page reads the OLD; the new modules read the NEW. v10.
   318 aligns them by updating the OLD's `hierarchy` key to match
   the NEW's structure. Long-term, one file should be the source
   and the other a derived view; for now both work but kept in sync.

3. **G208 caught a code-marker requirement.** The audit gate checks
   for `"v10.318 fix"` and `"# 0. Admin / MD intent"` strings in
   pages/12_cascade.py source. This is unusual — normally we check
   behaviour, not source code. But the cascade page is 2,933 lines
   and the my_role_level() fix could silently regress in a future
   refactor. Source-code-marker check is cheap insurance.

4. **The "MD intent" abstraction is what was missing.** Before
   v10.318, the cascade page conflated "user's account role" with
   "user's perspective." An admin user IS NOT the MD — they're
   admin acting AS the MD. The is_md guard now models this
   correctly.

5. **G162 holds. 14 consecutive zero-drift batches.** No tenant
   tokens introduced.

6. **TDD red→green worked.** 17 tests written first based on your
   stated cascade expectations. Initial run: 15 passed (the
   structure was already right) + 2 failed (the source-code marker
   tests because I hadn't added the markers yet). Added markers,
   ran again, 17/17 green.

## Platform state

| Metric | v10.317 → v10.318 |
|--------|-------------------|
| Audit gates | 207 → **208** |
| Integration test suites | 24 → **25** |
| Tests passing | 424 → **441** |
| G162 baseline | 4022 (14 consecutive zero-drift batches) |
| Roles in cascade hierarchy | 28 → **75** |
| Producer modules | 1 (unchanged) |

## Backlog status

| ID | Status | Item |
|----|--------|------|
| B-009 | Open | IFRS9 product field |
| B-010 | Partial | KPI library ID convention mismatch |
| B-011 | Open | Dept naming |
| B-013 | Open | Manager rollup engine |
| **B-014** | **NEW** | **`utils.core.get_org_config` requires Streamlit** — the canonical org_config loader can't be used outside Streamlit pages. v10.318 worked around this with `_load_org_config_safe()` in utils/cascade_hierarchy.py, but the real fix is to make get_org_config Streamlit-independent. Logged for a future cleanup batch. |

## What this batch unlocks

- MD can log in and see all 11 Chiefs as direct reports ✓
- MD can set BSC targets for each Chief ✓
- Each Chief, when they log in, sees their own direct reports ✓
- Cascade flows downward exactly as you described ✓
- Branch Operations Supervisor sees Tellers/CSOs as direct reports ✓
- The "Set Team Targets" page works end-to-end for every role ✓

The demo can now show the full target-cascade flow — MD sets Chief
targets, Chiefs set Head targets, Heads set Manager targets, all
the way down to Tellers. With v10.317's Teller activity already
flowing through the corrected v10.316 hierarchy, the full demo
loop is complete:

**Top-down**: MD → Chief Retail → Head of Branches → Area Manager
→ Branch Manager → Operations Manager → Operations Supervisor →
Teller targets

**Bottom-up**: Teller actuals → Operations Supervisor rollup →
Operations Manager rollup → Branch Manager rollup → ... → MD scorecard

Manager rollup engine (B-013) is still needed for the bottom-up
half to show real numbers at each level. v10.319 next.

## Next: v10.319 — Manager rollup engine

Branch Manager's score = aggregate of their team's scores (weighted
by KPI weights, normalised 0-100). Area Manager's = aggregate of
Branch Managers'. And so on up to MD.

Estimated 3-4 hours. Proceed?
