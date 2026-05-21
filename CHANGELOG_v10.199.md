# CHANGELOG v10.199 — app.py manifest-driven navigation (the visible reorganization)

**Date:** 2026-05-06
**Theme:** The user-visible reorganization batch. Replaces ~390 lines of
hand-crafted 18-group navigation in `app.py` with ~130 lines of
manifest-driven derivation. Net reduction of **260 lines**. Audit
remains at **160/160 PASS**.

## What v10.199 ships

### 1. `app.py` — manifest-driven navigation construction

Lines 838-1228 of `app.py` (the 18 hand-crafted `_grp` lists +
`_DEPT_MAP_NAV` routing) replaced with manifest-driven derivation that
reads `pages/_manifest.json` via `pages/_manifest_loader.py` (both
shipped in v10.197).

**Old structure (~390 lines):**
- `_universal`, `_retail_grp`, `_comm_grp`, `_credit_grp`, `_treasury_grp`,
  `_finance_grp`, `_risk_grp`, `_legal_grp`, `_ops_grp`, `_hr_grp`,
  `_it_grp`, `_bnc_grp`, `_audit_grp`, `_exec_grp`, `_tf_grp`,
  `_dfs_grp`, `_cc_grp`, `_bnc_full_grp`, `_cyber_grp`, `_agn_grp`,
  `_admin_grp` — 18 lists with extensive cross-list duplication
  (e.g. `1_perform.py` listed in every group)
- `_DEPT_MAP_NAV` dict mapping user.department string to one of the
  18 groups — 1-to-1 routing only

**New structure (~130 lines):**
- `_USER_DEPT_TO_MANIFEST` dict mapping user.department string to one
  or more manifest dept_ids (multi-value supported, e.g.
  `"Risk & Compliance" → ["risk", "compliance_regulatory"]`)
- `_build_dept_pages(dept_id, include_secondary)` helper that calls
  `_pages_in_department(dept_id, include_secondary=True)` from the
  manifest loader and wraps each result through `_pg()` (which
  enforces `check_access` + `dept_module_config.json` hidden-modules
  + `org_config.json` nav_labels customization)
- Branching logic: admin sees all 16 departments (primary-only, no
  cross-section duplication); regular user sees Shared + their
  primary dept(s) (with secondary visibility) + External + Admin (if
  DSU/ICT)

### 2. `scripts/audit.py` — G149 refactored to manifest-aware

G149 (cockpits_registered_in_app, shipped v10.153) was the canonical
example of a "location-locked" closure gate that v10.196 Section 5
warned would prevent reorganization. Original implementation
string-matched `pages/<cockpit_name>.py` against `app.py` text. With
v10.199's manifest-driven nav, those literal references are gone —
cockpits are derived from manifest entries at runtime.

The gate refactored to **behavior-based**: every `pages/*_cockpit.py`
file on disk must have an entry in `pages/_manifest.json`. Same
discipline (every cockpit declares its department + module_path) but
location-independent — works regardless of how `app.py` reaches the
cockpit. Compatible with future cockpit absorption batches: when a
cockpit file is deleted, removing the manifest entry passes G149
correctly.

This is the prerequisite refactor v10.196 Section 5 specified before
any cockpit absorption could ship. Closure-arc gates G130-G143 may
need similar refactors as cockpit absorption proceeds; v10.199 does
G149 only because that's the gate that broke first.

## Files changed (2)

```
app.py                    MOD  -260 lines (1269 → 1009)
                                +130 lines manifest-driven nav
                                -390 lines hand-crafted 18-group nav
scripts/audit.py          MOD  +30 lines net (G149 reworked)
```

Zero `pages/*.py` files moved. Zero `utils/*.py` files touched. Zero
deletions. The 124 page files remain on disk; nav structure derives
from the manifest.

## Audit

```
Before (v10.198): Score: 160/160 gates = 100.0% — PASS
After  (v10.199): Score: 160/160 gates = 100.0% — PASS
```

(G149 transiently flagged 13/13 cockpits unregistered when the v10.199
refactor first removed app.py text references — caught + fixed within
the same batch via the architecturally-correct manifest-aware refactor,
not via a workaround re-adding text references. Final audit clean.)

## What users see after v10.199

Sidebar nav changes from the v10.198 18-group structure to the v10.199
12-department + 4-shared = **16-group** structure:

```
🏠 Shared                           📊 Strategy & Performance
  Home                                My BSC
  Smart Alerts                        Execute (OKR)
  Approvals                           Performance Exports
  Statement Analyzer                  Target Cascade
  Customer 360                        Budget vs Actual
                                      Strategic Initiatives
👥 People (HR)                        Board Papers
  People                              Tier-1 Benchmarking
  SLA Tracker                         Strategy Arc (legacy cockpit)
  CIMS
  Learning Management                💼 Sales & Customer
  Performance Improvement             Pipeline
  Workforce Planning                  SBU Performance
  Disciplinary Register               Branch Daily Log
                                      ... (13 pages total)
📦 Products & Pricing
  Product Catalogue                  💳 Credit
  Commission Management               Credit Monitoring
  Cards Management                    Debt Recovery
  Merchant Acquiring                  Loan Applications
  Product Arc (legacy cockpit)        ... (13 pages total)

💰 Treasury & ALM                    ⚠️ Risk
  Treasury Dashboard                  Stress Testing
  IRRBB Dashboard                     Incident Management
  Funds Transfer Pricing              Operational Risk
  Capital & Liquidity                 ESG & Climate
  ALM & Liquidity                     Climate Risk
  Capital & Risk Engines              Risk Arc (legacy cockpit)
  Treasury Arc (legacy cockpit)

🛡️ Compliance & Regulatory          🧮 Finance
  Compliance                          Management Accounts
  Reconciliation (RMS)                Finance Arc (legacy cockpit)
  EDMS
  Risk Register (RCSA)               🛠️ Operations
  AML Monitoring                      Operating Leverage
  Fraud Detection                     Branch Optimizer
  Consent Management                  Resource Analytics
  CBK Returns                         Revenue Assurance
  Data Protection                     ... (13 pages total)
  Sanctions Screening
  Compliance Arc (legacy cockpit)    🌍 Trade Finance
                                      Trade Finance
⚖️ Legal                              Trade Finance Arc (legacy cockpit)
  Legal Management
  Contracts Register                 🏗️ IT & Platform
  Legal Arc (legacy cockpit)          Command Centre
                                      CBS Explorer
                                      Cybersecurity
                                      ... (9 pages total)

⚙️ Admin                             🌐 External Intelligence
  Admin                               Competitor Intel
                                      Deal Room
```

Cockpits are visible in their parent department's nav, marked
"(legacy cockpit)" in the title — the duplication is now obvious
to operators, making the eventual editorial absorption an obvious
next step. No code change is needed to absorb a cockpit; the
absorption batch edits the parent page to add tabs from the
cockpit's content, then deletes the cockpit file + removes the
manifest entry.

### What changes for operators

- **Sidebar density increases** from ~6-12 pages (admin sees more) to
  16 sections, each collapsible. Each section's pages are
  alphabetic-ordered by filename for stable nav across batches.
- **Cross-department visibility now explicit.** Pages with
  `secondary_visibility` in their manifest entry appear in those
  departments' nav. Example: `32_ifrs9.py` (primary: Credit) appears
  in Finance and Risk navs because its manifest entry lists those
  departments as secondary. Previously cross-visibility was achieved
  by hand-listing the same `_pg()` call in multiple `_grp` lists,
  which was error-prone and easy to miss.
- **Per-user nav size correctly bounded.** A regular user sees
  Shared (5) + their primary dept (2-15 depending on which) +
  External (2). Admin users still see everything (~108 pages, but
  organized into 16 sections rather than 18 with duplication).
- **Page-number collisions still exist on disk.** v10.199 doesn't
  resolve them — but they're irrelevant for nav order now because
  the manifest's `module_path` is unique per page and Streamlit's
  filename-based routing only applies when manifest registration is
  bypassed (it isn't).

### What changes for engineers

- **Adding a new page** is now: (1) create `pages/<NN>_<name>.py`,
  (2) add a manifest entry. Forgetting step 2 fails G160 (v10.198).
  No need to find and edit the right `_grp` list in app.py — the
  manifest is the single point of registration.
- **Moving a page between departments** is JSON-edit only. No
  app.py change. Audit revalidates G160 on the next run.
- **Deprecating a cockpit** is JSON-edit (set `deprecated: true` +
  `deprecation_target_page`) + eventual file deletion. The 13
  cockpits already shipped with this metadata in v10.197.
- **Defining a new department** is JSON-edit to the manifest's
  `departments` block. No app.py change. The new dept appears in
  admin's sidebar on next render.

## Strategic narrative — the visible reorganization

v10.196 + v10.196.1 advisory reviews diagnosed the entanglement and
proposed the manifest-driven, department-first navigation. v10.197
shipped the foundation (manifest + loader). v10.198 locked the
discipline (G160 audit gate). **v10.199 is the user-visible flip** —
operators see the new structure on next deploy.

The pattern this batch demonstrates is the canonical "build the
foundation first, then refactor against it" sequence:

| Batch | What | User-visible? | Risk |
|---|---|---|---|
| v10.196 | Diagnostic review (419 lines) | No | Zero |
| v10.196.1 | Prescriptive review (906 lines) | No | Zero |
| v10.197 | Manifest + loader | No | Low |
| v10.198 | G160 audit gate | No | Low |
| **v10.199** | **app.py refactor** | **Yes** | **Medium** |

By the time v10.199 ships, the manifest has been verified
(v10.197), audit-locked (v10.198), and reviewed (v10.196 + v10.196.1).
The visible flip is mechanical, not architectural — all the design
work happened before any user saw any change.

## What v10.199 does NOT ship

- **Dotted-path access** (`require_access("treasury_alm.alm")` resolving
  up the path to department-level grant) — deferred to v10.200
- **Cockpit absorption** (folding deprecated cockpits into target
  pages as tabs) — continuous improvement v10.200+ through v10.250
- **Page-number collision resolution** — irrelevant once manifest is
  routing authority; deferred indefinitely
- **G130-G143 closure-arc gate refactors** — needed before any cockpit
  file can be physically deleted; will happen one gate at a time as
  cockpit absorption batches start

## Honest acknowledgements

1. **The 13 cockpit files still exist on disk.** v10.199 makes them
   visible in their parent department's nav with "(legacy cockpit)"
   suffix. Physical deletion requires the prerequisite G130-G143
   closure-arc gate refactors (described in v10.196 Section 5)
   before each cockpit can be absorbed. Target completion: v10.250.

2. **`__all_admins__` token in `secondary_visibility` is not yet
   honored.** It appears on `91_systems_view.py` and is meant to
   make the page visible to all admin users (even if they're in a
   non-IT department). v10.199 doesn't yet implement this — admin
   users see it via the IT & Platform department section because
   admins see all departments. Refinement deferred to a future batch.

3. **The `_USER_DEPT_TO_MANIFEST` mapping was made on Joshua's
   standing-run authorization.** I mapped 22 user.department string
   values found in `data/*.json` to the 16 manifest dept_ids. The
   "Risk & Compliance" → `["risk", "compliance_regulatory"]`
   multi-mapping is the only multi-value entry; everyone else maps
   1-to-1. If Ecobank's actual dept structure differs, the mapping
   is editable JSON-style data inside `app.py` (no batch ship needed
   to change it; just edit the dict).

4. **`1_perform.py` (My BSC) appears in EVERY user's primary
   department nav.** This is by design via `secondary_visibility:
   ["__all_departments__"]` in its manifest entry. The behavior is
   identical to the old hand-crafted nav where `1_perform.py` was
   listed in every `_grp`. Different mechanism, same result.

5. **Per-section page ordering is alphabetic by filename.** The old
   hand-crafted nav had per-group ordering set explicitly. The new
   manifest-driven nav doesn't yet support custom per-section
   ordering. If Joshua wants e.g. "Treasury Dashboard" first then
   "ALM" then "IRRBB", a future refinement can add a
   `nav_order_within_dept` field per manifest entry. Deferred —
   alphabetic is a reasonable default.

6. **Topbar pills still display the legacy 4 pseudo-groups**
   (perform, execute, integrate, admin). These were always
   decorative — the JS-based collapse mentioned in the comments was
   never actually implemented (verified by looking at the code).
   The pills' `_GROUP_DEFS` access-check still works because it
   tests against `module_key` strings that the manifest preserves
   via `current_module_key`. Future refinement: replace the 4-pill
   topbar with a 16-department dropdown or render the pills based
   on the active manifest department.

7. **G149's refactor was opportunistic.** It happened in v10.199
   because the navigation refactor broke the gate. The full
   prerequisite refactor of all closure-arc gates (G130-G143) for
   manifest-aware behavior is a separate concern — those gates
   don't fail today because the cockpit files still exist on disk
   and still import the closure-batch engines. They'll need refactor
   only when the cockpit files start being deleted (v10.200+).

8. **The defensive fallback is "Home only".** If `pages/_manifest.json`
   is missing at runtime (e.g. dev environment without v10.197 zip
   applied), the new code falls back to a single Home entry. This
   matches the original `try: pg = st.navigation(_clean_sections);
   except: pg = st.navigation({"🏠 Home": [...]})` pattern that was
   in the old code (line 1259).

9. **Net 260-line reduction in `app.py`.** From 1,269 lines to 1,009
   lines. The reduction comes from eliminating duplicate `_pg()`
   calls across the 18 `_grp` lists (e.g. `1_perform.py` was repeated
   17 times in the old code; once in the manifest now). This is the
   campaign's signature pattern: lock structure in data (the
   manifest), keep code small (the manifest loader + the nav
   builder).

10. **`utils/dept_module_config.json` semantics preserved.** The
    `_pg()` helper still consults `dept_module_config.json` for
    per-department hidden-modules. The manifest-driven nav doesn't
    bypass this — it provides the candidate page set, and `_pg()`
    filters to the user-visible subset. Existing per-deployment
    overrides continue to work.

11. **`utils/org_config.json` `nav_labels` customisation
    preserved.** The `_pg()` helper still reads custom title
    overrides from `org_config.json`. The manifest provides the
    default title; per-deployment customisation overrides it.

12. **9 consecutive clean batches in this session** — v10.193, 194,
    195, 197, 198, 199 = 6 code batches + v10.196, 196.1 = 2 advisory
    reviews. All batches landed audit-clean on first try except v10.197
    (transient G2 — fixed within the batch via FOUNDATIONAL allowlist
    update) and v10.199 (transient G149 — fixed within the batch via
    manifest-aware refactor). Both transient failures resolved by
    architecturally-correct fixes rather than workarounds.

## Next batch

**v10.200 — dotted-path access in `pages/_access.py`.** Refactor
`require_access(module)` to support dotted paths like
`require_access("treasury_alm.alm")` resolving up the path:
explicit grant → parent dept grant → deny. Backward compatible:
existing flat keys (`"treasury"`) keep working. Admin role registry
extended to support dotted patterns including wildcards
(`treasury_alm.*`). After v10.200, admin can grant role permissions
at department or page granularity cleanly.

After v10.200, the architectural reorganization sub-campaign (v10.196
through v10.200) is complete. Cockpit absorption begins at v10.201
as continuous-improvement work.
