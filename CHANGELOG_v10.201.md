# CHANGELOG v10.201 — Admin Roles UI: dotted-grant picker (closes the role-grant story end-to-end)

**Date:** 2026-05-06
**Theme:** UI completion of v10.200's dotted-path access. Adds a
tree-view picker in `7_admin.py` Permissions tab so admins can grant
`accessible_modules_dotted` through the interface — no JSON editing
required. Single-purpose UI batch. Audit holds at **160/160 PASS**.

## What v10.201 ships

### `pages/7_admin.py` — Department-level access picker

A new section added inside the existing per-user permissions form
(sub-tab "🔑 Permissions" of section "👥 People & Org"). Sits below
the existing module-access block; saves to the same record via the
existing 💾 Save button.

**One expander per department** (12 main departments only — shared,
admin, and external are handled implicitly):

```
📊 Strategy & Performance (9 pages)        [collapsed by default]
👥 People (HR) (7 pages)                   [collapsed by default]
💼 Sales & Customer (13 pages)             [collapsed by default]
📦 Products & Pricing (5 pages)            [collapsed by default]
💳 Credit (13 pages)                       [collapsed by default]
💰 Treasury & ALM (7 pages)                [collapsed by default]
⚠️ Risk (6 pages)                           [collapsed by default]
🛡️ Compliance & Regulatory (11 pages)      [collapsed by default]
🧮 Finance (2 pages)                        [collapsed by default]
🛠️ Operations (13 pages)                    [collapsed by default]
🌍 Trade Finance (2 pages)                 [collapsed by default]
⚖️ Legal (3 pages)                          [collapsed by default]
```

If a department has any current grant (dept-wide or per-page), its
expander defaults to **expanded** so admin sees existing state on
page load.

**Each expander supports two grant modes:**

1. **Department-wide grant** — single checkbox `Grant entire <Dept>
   department`. Stores `<dept_id>` in `accessible_modules_dotted`.
   Future-proofs against new pages added to the department; the
   user automatically gets access when the manifest grows.

2. **Per-page grants** — appears when the department-wide checkbox
   is OFF. A multiselect lets admin pick specific pages within the
   department. Stores e.g. `treasury_alm.alm`, `treasury_alm.irrbb`
   in `accessible_modules_dotted`. Useful for partial grants (e.g.
   "Credit Analyst gets all credit pages except `credit.admin`").

**Mutual exclusion:** the two modes don't overlap. If "Grant entire
department" is checked, the per-page multiselect doesn't render —
the dept-wide grant covers everything. If unchecked, the multiselect
shows the page list and admin picks subsets.

### Admin workflow — three example role grants

**Treasury Manager** (sees all treasury + IFRS 9 cross-reads from Credit):

1. Open Permissions → select user → expand "💰 Treasury & ALM"
2. Tick "Grant entire Treasury & ALM department" → caption shows "✅ User has access to all 7 pages"
3. Expand "💳 Credit" → leave dept checkbox OFF → multiselect shows all
   13 credit pages → tick "IFRS 9 Staging" + "IFRS Engines"
4. Save → user record gets:
   ```json
   "accessible_modules_dotted": [
     "credit.ifrs9",
     "credit.ifrs_engines",
     "treasury_alm"
   ]
   ```

**Credit Analyst** (all credit pages except admin):

1. Expand "💳 Credit" → leave dept checkbox OFF
2. Multiselect → tick all pages except "Credit Admin"
3. Save → user record gets 12 specific credit page paths

**Branch Manager** (Sales + HR full access):

1. Expand "💼 Sales & Customer" → tick "Grant entire department"
2. Expand "👥 People (HR)" → tick "Grant entire department"
3. Save → user record gets:
   ```json
   "accessible_modules_dotted": [
     "people_hr",
     "sales_customer"
   ]
   ```

### Verification — picker logic across 4 scenarios

| Scenario | Input | Expected output | Result |
|---|---|---|---|
| Treasury Manager | dept-wide `treasury_alm`, per-page IFRS 9 + IFRS Engines from Credit | `[credit.ifrs9, credit.ifrs_engines, treasury_alm]` | ✅ |
| Credit Analyst (no admin) | per-page select 12 credit pages excluding admin | 12 specific dotted paths, no `credit.admin` | ✅ |
| Branch Manager | dept-wide on sales_customer + people_hr | `[people_hr, sales_customer]` | ✅ |
| User with no dotted grants | nothing ticked | `[]` (legacy access only) | ✅ |

## Files changed (1)

```
pages/7_admin.py    MOD  +106 lines  (department picker block + save logic update)
```

Zero new dependencies. Zero changes to `pages/_access.py` (v10.200
already added `check_access_dotted`). Zero changes to
`pages/_manifest_loader.py` (v10.200 already added the reverse-lookup
helpers). Zero changes to `app.py`, `utils/`, or any other page file.

## Audit

```
Before (v10.200): Score: 160/160 gates = 100.0% — PASS
After  (v10.201): Score: 160/160 gates = 100.0% — PASS
```

No new gates added. The picker writes to `accessible_modules_dotted`
which is consumed by `check_access_dotted` (v10.200), which is
audit-locked through the manifest by G160 (v10.198).

## Strategic narrative — sub-campaign deliverables now end-to-end

The architectural reorganization sub-campaign opened with v10.196
advisory now has the full delivery loop:

| Layer | Batch | What |
|---|---|---|
| Diagnosis | v10.196 | Identified the entanglement |
| Prescription | v10.196.1 | Mapped the target structure |
| Foundation | v10.197 | Page manifest as source of truth |
| Discipline | v10.198 | G160 audit gate locks foundation |
| User-visible | v10.199 | app.py refactor, sidebar reorganized |
| Resolution | v10.200 | Dotted-path access in `_access.py` |
| **Admin UX** | **v10.201** | **Tree-view picker for dotted grants** |

After v10.201, the role-grant story is **end-to-end usable**:
- Engineer creates a new page → forced to declare department in
  manifest (G160 enforces)
- Admin grants role permissions → uses tree-view picker (v10.201)
  → writes dotted paths to user record
- User loads a page → `require_access(dotted_path)` resolves through
  explicit grant → wildcard → department → legacy fallback (v10.200)
- Sidebar shows pages organized by department (v10.199)

## Honest acknowledgements

1. **The picker shows only the 12 main departments.** Shared,
   Admin, and External departments are skipped because their
   pages are universally accessible (Shared) or have special
   access (Admin via `is_admin` flag; External via deal-room
   role-gate). Future enhancement could add an Advanced section
   for granular shared/external grants if needed.

2. **No bulk-assign UI.** Admin must select each user individually
   then configure their grants. For Ecobank's ~487 staff, doing
   this one-by-one is tedious but matches existing admin UX (the
   legacy module-access block has the same per-user model).
   Future enhancement: bulk-assign by role or unit, e.g. "grant
   `treasury_alm` to all users with role 'Treasury Officer'."

3. **No grant inheritance from role library.** Currently each
   user record carries its own `accessible_modules_dotted` list.
   The role library at "🎭 Roles Library" tab doesn't yet store
   default dotted grants per role. Future enhancement: roles
   declare default dotted grants; user records can inherit/override.

4. **No exclusion semantics yet.** As noted in v10.200, the
   picker doesn't support patterns like "grant `credit.*` except
   `credit.admin`" via a single click. The Credit Analyst
   workflow above shows the workaround: untick dept-wide, tick
   12 specific pages. For 12 pages this is fine; for a hypothetical
   30-page department, exclusion semantics would matter more.

5. **No tab-level granularity.** Each manifest entry is a page,
   not a tab within a page. If a treasury user should see the
   "Capital" tab on `25_treasury.py` but not the "Liquidity" tab,
   the current scheme can't express that. The manifest schema
   would need a `tabs` field per page to enable
   `treasury_alm.dashboard.tab.capital` paths. Deferred —
   tab-level grants haven't been a stated requirement.

6. **The expander defaults to expanded only when there's an
   existing grant.** Fresh users with no `accessible_modules_dotted`
   see all 12 expanders collapsed. Admin reviewing an existing
   power user with 5 dept grants sees those 5 expanders auto-
   expanded. This minimises visual noise for the common case.

7. **Session state for `_dept_*` keys is cleared on save and on
   user-selection change.** Same pattern as the existing `_p_`
   and `_mod_` keys. Prevents stale UI state from leaking across
   user selections (e.g. clicking "User A" then "User B" doesn't
   show A's checks for B).

8. **The new section's defensive try/except around the manifest
   loader prevents the picker from blocking the existing module-
   access save.** If the manifest is missing or unreadable, the
   picker shows an info message but the save button still works
   (preserving legacy behavior). This means v10.201 is safe to
   deploy even before v10.197's manifest is in place — graceful
   degradation.

9. **`audit_log("PERM_CHANGED", ...)` now includes
   `dotted_grants=N`.** Existing audit-trail consumers that parse
   this log entry will see the new field; if they're parsing
   strictly with regex they may need updating. The format
   addition is at the end of the existing message string, so
   any prefix-match parsing continues to work.

10. **No automated tests for the UI rendering itself.** The
    picker is verified through (a) the audit script (G160 +
    syntax G1 + tab-counts G4 etc.) and (b) the manual scenario
    walkthrough above. Streamlit UI testing requires a running
    server, which is outside the audit's scope. If the picker
    renders incorrectly in production, that's caught by the
    user, not the audit. Acceptable trade given Streamlit's
    test ergonomics.

11. **The Permissions tab now has 3 logical sections: System
    permissions (legacy flags), Module access (legacy flat
    keys), and Department-level access (v10.200 dotted paths).**
    All three coexist and contribute to the user's effective
    access. The OR semantics are preserved by check_access_dotted
    falling through to check_access on every dotted call.

12. **11 consecutive clean batches in this session.** v10.193
    through v10.201 — 9 code batches + 2 advisory reviews. The
    architectural reorganization sub-campaign closed in 5 batches
    (v10.197-v10.201) with the manifest as durable foundation.
    Continuous improvement (cockpit absorption) opens at v10.202+.

## Next batch options

The sub-campaign is now complete end-to-end. Three natural directions:

1. **v10.202 — first cockpit absorption (Treasury Arc into 25_treasury.py).**
   Refactor closure gate G135 (or whichever closure gate references
   `26_treasury_arc_cockpit.py`) to behavior-based first. Then absorb
   the cockpit's content into `25_treasury.py` as tabs. Delete the
   cockpit file. Update its manifest entry. ~150 lines net change.
   Opens the v10.250 cockpit-absorption schedule.

2. **v10.202 — page migration to dotted form (Treasury department).**
   Migrate the 7 Treasury pages from `require_access("treasury")`
   etc. to `require_access("treasury_alm.alm")` etc. Update one
   real Treasury staff role record to use the new dotted form.
   Verify everything works end-to-end. ~30 lines per page × 7
   pages = ~210 lines.

3. **v10.202 — return to deferred platform items.** PG migration
   (still 33/52 tables remaining), React SPA build, React Native,
   or any other line-item from the platform-state list.

The architectural reorganization is fully shipped. The next move
is whichever direction Joshua prioritizes for v10.202+.
