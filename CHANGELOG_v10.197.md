# CHANGELOG v10.197 — Page Manifest (foundational batch for department-first reorganization)

**Date:** 2026-05-06
**Theme:** First batch of the architectural reorganization sub-campaign
opened by the v10.196 + v10.196.1 advisory reviews. Pure additive — no
existing files moved, no `app.py` routing changes yet, no audit gate
count change. Future batches (v10.198 G160, v10.199 app.py refactor,
v10.200 dotted-path access) build on this foundation.

## What v10.197 ships

### 1. `pages/_manifest.json` — canonical page registry

The single source of truth for which department owns which page,
what the dotted module path is, and which other departments have
secondary visibility. 108 page entries covering 100% of files in
`pages/*.py` (excluding `_*.py` helpers and `__init__.py`).

Schema includes:
- `department_primary` — one of 16 department/shared keys
- `module_path` — dotted path like `treasury_alm.alm`
- `secondary_visibility` — list of departments with read access
- `title`, `icon` — UI metadata
- `current_module_key` — backward-compat link to `check_access` keys
- `deprecated`, `deprecation_target_page`, `deprecated_reason` —
  for the 13 cockpit pages awaiting absorption by v10.250

The 16 departments (12 + 4 shared):
1. Strategy & Performance — 9 pages
2. People (HR) — 7 pages
3. Sales & Customer — 13 pages
4. Products & Pricing — 5 pages
5. Credit — 13 pages
6. Treasury & ALM — 7 pages
7. Risk — 6 pages
8. Compliance & Regulatory — 11 pages
9. Finance — 2 pages (honest: most "finance" work lives in Strategy
   or Operations; the dept owns mgmt accounts directly)
10. Operations — 13 pages
11. Trade Finance — 2 pages
12. Legal — 3 pages

Plus 4 shared:
- IT & Platform — 9 pages
- Shared (Home, Smart Alerts, Approvals, Customer 360, Statement Analyzer) — 5 pages
- Admin — 1 page (the admin dashboard itself)
- External Intelligence — 2 pages

### 2. `pages/_manifest_loader.py` — typed read-side API

Thread-safe, cached loader exposing 9 functions:
- `list_departments()` → 16 dept registry
- `list_pages()` → 108 page entries
- `get_page(filename)` → entry or None
- `pages_in_department(dept_id, include_secondary)` → ordered list
- `page_path_to_module_key(filename)` → backward-compat key
- `is_deprecated(filename)` → cockpit check
- `deprecation_info(filename)` → target_page + reason
- `list_deprecated_cockpits()` → all 13 cockpits + their absorption targets
- `manifest_version()` → schema version string
- `total_pages()` → 108
- `self_test()` → smoke check

Self-test verifies: manifest loads, every entry has dotted module_path,
no two pages share a module_path. Self-test passes:
`{passed: true, schema_version: "v10.197", total_pages: 108, total_departments: 16}`

### 3. `scripts/audit.py` — FOUNDATIONAL allowlist extended

`pages/_manifest_loader.py` added to FOUNDATIONAL set. The loader is a
config reader by design (same architectural role as
`scripts/docgen/_registry_loader.py` from v8.12), so G2 (no direct I/O
outside foundational) is the architecturally correct gate to satisfy
via allowlist update — not via workaround patterns like
`# noqa: a2z-bootstrap-fallback`.

## What v10.197 does NOT ship (deferred to future batches)

- **G160 audit gate** that locks manifest completeness — v10.198
- **`app.py` refactor** to consume the manifest and replace the 18 hand-crafted
  `_grp` lists with manifest-derived navigation — v10.199
- **Dotted-path access** in `pages/_access.py` — v10.200
- **Cockpit absorption** (folding deprecated cockpits into target pages
  as tabs) — continuous improvement v10.200+ through v10.250

## Files changed (3)

```
pages/_manifest.json          NEW  35,860 bytes  (108 page entries)
pages/_manifest_loader.py     NEW   6,107 bytes  (typed read-side API)
scripts/audit.py              MOD       +1 line  (FOUNDATIONAL allowlist)
```

Zero `pages/*.py` files moved. Zero `utils/*.py` files touched. Zero
deletions. Existing 18-group navigation in `app.py` continues to work
unchanged — the manifest sits alongside as a parallel source of truth
that future batches will progressively consume.

## Audit

```
Before: Score: 159/159 gates = 100.0% — PASS
After:  Score: 159/159 gates = 100.0% — PASS
```

(G2 transiently flagged the new loader's `read_text()` call before the
FOUNDATIONAL allowlist update — caught + fixed within the same batch
per existing convention. Final audit clean.)

Self-test: `python pages/_manifest_loader.py` returns
`{passed: true, schema_version: "v10.197", total_pages: 108, total_departments: 16}`.

## Strategic narrative

This is the foundational batch for the **department-first reorganization**
sub-campaign. The v10.196 + v10.196.1 advisory reviews diagnosed the
entanglement (124 pages across 18 hand-crafted nav groups, 7 page-number
collisions, 13 cockpit duplicates) and proposed a 12-department + 4-shared
target structure consumed via a manifest-driven navigation.

v10.197 ships the manifest itself — the source of truth — without
touching `app.py`. This is deliberately the smallest possible first
batch: no behavior changes for users (sidebar still renders the existing
18 hand-crafted groups), no risk to closure-arc audit gates G130-G143
(no page files moved), and no breaking changes to access control
(existing `check_access(ud, module_key)` keys preserved via
`current_module_key` field).

The manifest is now ready for:
- v10.198 G160 audit gate to lock its completeness as permanent
  invariant (no new pages without a manifest entry)
- v10.199 `app.py` refactor to derive `_nav_sections` from the manifest
  rather than hand-crafted `_grp` lists, taking the platform from 18
  groups to 12+4 = 16 cleanly defined groups
- v10.200 dotted-path access (`treasury_alm.alm` resolves up the path
  to `treasury_alm` → fall through to deny)
- React migration: the manifest IS the React route registry; each
  `module_path` becomes a route (`/treasury_alm/alm`)

## Honest acknowledgements

1. **No `app.py` changes yet** — the manifest sits parallel to the
   existing 18-group structure for one or two batches before the
   v10.199 refactor consumes it. This is the safest sequencing: build
   the foundation, verify it, then refactor against it.

2. **The 12-department mapping reflects my best judgment, not
   Ecobank's actual org chart.** The decisions in v10.196.1 Section 10
   were made by Joshua's standing-run authorization. If Ecobank's
   department structure differs, the manifest's `departments` block
   and per-page `department_primary` fields are editable JSON — no
   code changes needed to redraw the lines. The manifest is intentionally
   data, not code, so org-chart updates don't require batch ships.

3. **Finance has only 2 pages.** This is honest, not a coverage gap.
   Most "finance" work in the existing codebase lives in pages owned
   by Strategy (budget, exports, BSC), Treasury (capital, FTP), or
   Operations (revenue assurance, P2P). The Finance department's true
   footprint is the management accounts dashboard plus its closure
   cockpit. If Joshua wants Finance to own more pages (e.g. move
   `41_budget.py` from Strategy to Finance), the manifest entry's
   `department_primary` is the only field that needs editing.

4. **Cross-department visibility uses department keys, not user
   roles.** `secondary_visibility: ["finance", "risk"]` means users in
   the Finance or Risk departments see this page in their nav. It does
   NOT bypass `check_access` — the user must still have the role-level
   permission. v10.200 dotted-path access will refine this with
   role-level granularity inside departments.

5. **`__all_departments__` and `__all_admins__` are special tokens** in
   `secondary_visibility` for pages like `1_perform.py` (BSC, visible
   in every dept) and `91_systems_view.py` (admin canonical cockpit,
   visible to all admins). These tokens are documented in the loader's
   docstring and must be preserved by future batches.

6. **The cockpit deprecation deadline of v10.250 is a soft target.**
   13 cockpit pages × 1 batch each = 13 batches starting at v10.200.
   That puts completion around v10.213 at the current cadence. v10.250
   gives ~37 batches of buffer for the harder consolidations (Risk arc
   spans 4 pages; Credit governance spans 3) and for unrelated work.

7. **Page-number collisions are NOT resolved by v10.197.** Files
   `15_cbs.py`, `15_optimize.py`, `15_strategy_arc_cockpit.py` all
   still claim slot 15. Streamlit's nav order is alphabetic-tiebreak
   for collisions. The manifest gives each page a unique `module_path`
   (`it_platform.cbs`, `operations.branch_optimizer`,
   `strategy_performance.strategy_arc_cockpit`) which is what matters
   for routing post-v10.199. The numeric-slot collisions become
   irrelevant when the manifest is the routing authority.

8. **Closure-arc audit gates G130-G143 are unchanged.** They still
   string-match against specific cockpit filenames. The cockpit files
   still exist (just marked `deprecated: true` in the manifest). When
   a future batch absorbs a cockpit's content into its target page,
   the corresponding closure gate must be refactored to behavior-based
   (engines invoked anywhere) rather than location-based (in a specific
   filename) before the cockpit file can be deleted. v10.196 Section 5
   describes this prerequisite refactor.

9. **`reload()` is exposed but not auto-triggered.** If admin edits
   the manifest at runtime (e.g. via the v10.200+ admin Roles UI), the
   loader caches the previous version until `reload()` is called.
   Streamlit's per-request module reload behavior may also help, but
   the explicit `reload()` is the safe path for admin-initiated changes.

10. **No `_manifest_loader.py` test in the audit suite.** The
    self_test() function works (verified above) but isn't yet wired
    into `scripts/audit.py` as a separate gate. v10.198's G160 will
    invoke `self_test()` as part of its checks, closing this gap.

11. **The 16-department structure is subject to refinement.** If the
    Ecobank operating model has fewer or more departments (likely 8-12
    in practice — most banks I've seen don't have separate Risk and
    Compliance departments at the page-navigation level), the manifest
    is editable JSON. Recommend reviewing with department heads before
    v10.199 ships the navigation refactor that makes the structure
    visible to all users.

12. **This is the smallest foundational batch possible for the
    reorganization sub-campaign.** It deliberately ships nothing the
    user will see — the manifest is a parallel source of truth. The
    visible reorganization happens in v10.199. Sequencing the
    foundation first means the visible-change batch can be reviewed
    on its own merits without entanglement with the manifest design.

## Next batch

**v10.198 — G160 audit gate `page_manifest_complete`.** Locks the
manifest as a permanent invariant: no new pages without a manifest entry,
every entry has dotted module_path, no two pages share module_path. The
gate is ~50 lines added to `scripts/audit.py`. Audit goes 159 → 160.

After v10.198, `scripts/audit.py` will be the enforcement mechanism for
the rule that drifted (master prompt v3.62 line 957: "prefer extending
existing patterns over inventing new ones") — every new page is
forced to declare its department at creation time, closing the original
drift mechanism.
