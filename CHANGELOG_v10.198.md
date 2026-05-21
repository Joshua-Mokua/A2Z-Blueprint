# CHANGELOG v10.198 — G160 page_manifest_complete (lock the rule that drifted)

**Date:** 2026-05-06
**Theme:** Pure audit-hardening batch. Locks the v10.197 page manifest as
a permanent invariant. Pushes audit suite **159 → 160 gates**. Closes
the drift mechanism that produced 13 cockpit pages, 7 page-number
collisions, and a fragmented 18-group navigation.

## What v10.198 ships

### G160 `page_manifest_complete`

A behavior-based audit gate (~140 lines added to `scripts/audit.py`)
that enforces the rule the master prompt has stated since v3.16 but
never enforced:

> "But always: measure before changing, and **prefer extending
> existing patterns over inventing new ones**. The audit script is
> the measuring stick."
>
> — `docs/Master_Prompt_v3.62.md` line 957

The gate runs 9 checks against `pages/_manifest.json` + the actual
filesystem state of `pages/*.py`:

1. **Manifest file exists** — `pages/_manifest.json` must be present
2. **Loader exists + is in FOUNDATIONAL** — `pages/_manifest_loader.py`
   must be present and on the G2 allowlist (config readers do I/O by
   design)
3. **Manifest is valid JSON** — fast-fail on parse errors
4. **Required top-level keys present** — `schema_version`,
   `departments`, `pages`
5. **Every numbered page on disk is registered** — no
   `pages/<NN>_<name>.py` may exist without a manifest entry; this is
   the core drift-prevention check
6. **Every manifest entry points to an existing file** — stale entries
   referencing deleted files are flagged
7. **Every entry has required fields with valid shapes** —
   `department_primary` must be one of the 16 declared departments;
   `module_path` must be dotted (`department.module`);
   `secondary_visibility` must be a list; deprecated entries must
   declare `deprecation_target_page`
8. **No two pages share the same module_path** — collision detection
   (catches accidental copy-paste of manifest entries)
9. **Loader self-test passes** — invokes
   `_manifest_loader.self_test()` to verify the manifest is consumable
   end-to-end

The gate is **behavior-based, not location-based** — it locks the
discipline (every page declares department + module_path) without
locking file existence (which would prevent the cockpit absorption
work scheduled for v10.200+). This was a deliberate design choice
informed by what went wrong with G130-G143 (closure-arc gates that
locked specific cockpit filenames and thereby prevented their later
cleanup).

## Drift detection — verified end-to-end

The gate was tested against 7 scenarios. Each scenario mutates the
manifest, runs the gate, and expects a specific failure. Final
restoration must produce a clean pass.

```
Scenario                                  Pass?  Violations  Sample
─────────────────────────────────────────  ─────  ──────────  ────────
A. Clean baseline                          True   0
B. Removed 25_treasury.py from manifest    False  1           "pages/25_treasury.py: not in pages/_manifest.json"
C. Non-dotted module_path                  False  2           "module_path 'treasury_no_dot' is not dotted"
D. Duplicate module_path                   False  2           "module_path collision: 25_treasury.py and 32_ifrs9.py..."
E. Invalid department_primary              False  1           "department_primary 'imaginary_dept' not in declared..."
F. Deprecated cockpit no target            False  1           "marked deprecated but missing deprecation_target_page"
G. Stale entry (file missing)              False  1           "manifest references NONEXISTENT_999.py which does not exist"
H. Restored clean state                    True   0
```

All 6 violation types produce precise diagnostics. The gate distinguishes
each error class so future failures arrive with actionable messages.

## Files changed (1)

```
scripts/audit.py    MOD  +140 lines  (G160 gate function + GATES tuple registration)
```

Zero `pages/*.py` files moved. Zero `utils/*.py` files touched. Zero
deletions. The manifest itself unchanged from v10.197.

## Audit

```
Before (v10.197): Score: 159/159 gates = 100.0% — PASS
After  (v10.198): Score: 160/160 gates = 100.0% — PASS
```

The audit suite gained one gate. The gate's first run on the v10.197
manifest reports **0 violations** because the manifest was carefully
constructed. Future regressions will fail audit with specific
diagnostics — that's the value.

## What v10.198 does NOT ship

- **`app.py` refactor** to consume the manifest (deferred to v10.199)
- **Dotted-path access** in `pages/_access.py` (deferred to v10.200)
- **Cockpit absorption** (continuous improvement v10.200-v10.250)

## Strategic narrative — closing the drift mechanism

The v10.196 advisory diagnosed the entanglement that produced 124 page
files: at every closure batch, the easiest path was to create a new
cockpit file because adding a tab to an existing page required
understanding that page's existing structure. The closure audit gates
G130-G143 then locked those cockpit files in place by checking exact
filename string matches.

The original drift mechanism had two ingredients:
1. **No discipline** preventing new pages from being created
   instead of tabs added (master prompt rule existed but wasn't audited)
2. **Audit gates that lock locations, not behaviors** (G130-G143
   string-match against specific filenames, preventing reorganization)

v10.197 + v10.198 close ingredient #1. Every new page must register
in the manifest with a department + dotted module_path. Adding a new
page is no longer the easy path — declaring its department forces the
question "could this be a tab on the existing department dashboard
instead?" into every page-creation decision.

Ingredient #2 (location-locked closure gates) is closed in the
prerequisite refactor before any cockpit absorption ships. That refactor
is described in v10.196 Section 5 and will be a single small batch
just before the first cockpit absorption.

After v10.198, **the audit script enforces the rule that drifted**.
`scripts/audit.py` is now the measuring stick the master prompt
referenced in v3.16.

## The 6-gate defense-in-depth perimeter is now 7

| Gate | Locks | Since |
|---|---|---|
| G104 | engine migration ratchet (count never decreases) | v7.0.1 |
| G105 | strict invariant registry usage | v7.1 |
| G106 | feedback-loop round-trip-testability | v7.15 |
| G107 | stock data_source provenance | v7.15 |
| G108 | FLEXCUBE retry/circuit/observability surface | v8.3 |
| G109 | PUBLISHED_LANGUAGE payload_version contract | v8.7 |
| G110 | Living Doc collateral claims traceable to registry | v8.16 |
| **G160** | **page manifest completeness (department + dotted module_path)** | **v10.198** |

The perimeter now covers structural drift across engines (G104),
domain models (G105), system flows (G106), system stocks (G107),
runtime resilience (G108), inter-context messaging (G109),
documentation generation (G110), and **navigation/role architecture
(G160)**.

## Honest acknowledgements

1. **G160 doesn't catch the deeper question of "should this be a tab
   instead of a page?"** — the manifest forces every new page to
   declare its department, but a developer who insists on creating a
   new cockpit file can still do so by adding a manifest entry. The
   gate makes drift visible and intentional rather than invisible and
   accidental. Human review of new manifest entries (especially during
   PR review) remains the second line of defense.

2. **The gate adds ~140 lines to a 20,000-line audit script.** That's
   ~0.7% size growth for an explicit cross-cutting invariant. The 9
   sub-checks could be split into multiple smaller gates (G160 manifest
   exists, G161 module_paths dotted, G162 no collisions, etc.) but
   single gate with 9 sub-checks gives a single pass/fail signal,
   matching the existing G108/G109/G110 pattern.

3. **The loader self-test is invoked at gate evaluation time.** This
   means G160 takes ~50ms longer than other gates because it imports
   the loader module via `importlib.util.spec_from_file_location`.
   Acceptable cost for end-to-end consume-side verification.

4. **The drift test (Scenarios B-G) is in-process monkey-patching of
   the manifest file.** This proved the gate's diagnostic logic across
   all 6 known violation types. A more robust test would commit a
   deliberately-broken manifest to a branch, run audit, observe
   failure, revert. The in-process test is sufficient verification of
   gate logic; the full PR-cycle drift test would catch CI integration
   issues that don't apply to this gate.

5. **G160 doesn't lock the 16-department list.** The manifest's
   `departments` block is editable JSON. Future batches can add a
   department, rename one, or merge two without breaking G160 — the
   gate just checks that every page's `department_primary` matches
   one of the declared keys. This intentional flexibility means
   departmental restructuring at Ecobank doesn't require code ships.

6. **`__all_departments__` and `__all_admins__` special tokens in
   `secondary_visibility` aren't validated by G160.** They're free
   strings the loader interprets specially. A typo (e.g.
   `__all_depatments__`) would silently fail to grant cross-dept
   visibility. Future enhancement: add a check that every entry in
   `secondary_visibility` is either a valid department key OR one of
   the 2 known special tokens. Deferred — current usage is bounded
   to 4 pages.

7. **No new audit gate for the loader's behavior beyond self_test.**
   The 11 loader functions (`list_departments`, `pages_in_department`,
   etc.) are not individually tested by G160. The self_test() inside
   the loader covers the critical paths; full unit-test coverage is
   `tests/test_manifest_loader.py` which is a future bookkeeping
   batch (not blocking).

8. **G160 fires on every audit run.** ~50ms overhead per `python
   scripts/audit.py` invocation, which is fine for the typical
   pre-batch + post-batch run pattern. CI deployments running the
   audit on every PR will pay this cost; acceptable trade for the
   discipline guarantee.

9. **The gate's behavior on a missing manifest is fast-fail.** If
   `pages/_manifest.json` doesn't exist (e.g. someone deletes it),
   G160 returns immediately with "manifest missing" — no further
   checks run. This is intentional: every other check assumes the
   manifest exists, so chaining failures would produce noise.

10. **No retroactive enforcement on legacy pages.** All 108 existing
    pages pass G160 because v10.197 manually populated their entries.
    If any of those entries are slightly wrong (e.g. a department
    assignment that should be different per Ecobank's actual org
    chart), G160 doesn't flag the problem — it only checks structural
    validity, not editorial correctness. Editorial review is a
    separate human responsibility (recommended before v10.199 ships
    the user-visible navigation).

11. **The "rule that drifted" is now enforced at the audit boundary,
    not the design boundary.** Master prompt v3.62 line 957 stays
    authoritative for new architecture decisions; G160 catches drift
    at the page-level granularity. Higher-level architectural drift
    (e.g. utils/ entanglement, cross-context utility imports) remains
    governed by other gates (G2 direct_io, G104 engine migration
    ratchet) plus human review.

12. **8th consecutive clean batch in this session** — v10.193, 194,
    195, 196 (review), 196.1 (review), 197, 198 = 7 batches + 2 reviews
    = clean ratio 7/7 with audit at 159 → 159 → 159 → 159 → 159 →
    159 → 160. The campaign discipline (single-purpose batches with
    audit-clean before/after, honest acknowledgements at the end of
    each) is preserved through the architectural reorganization.

## Next batch

**v10.199 — `app.py` refactor to consume the manifest.** Replace the
~400-line hand-crafted 18-group navigation construction (lines ~840-1228
of `app.py`) with manifest-derived `_nav_sections`. Estimated ~250 lines
of net change in `app.py`, zero `pages/*.py` files moved. Audit stays
at 160/160. After v10.199, the platform's sidebar reflects the
12-department + 4-shared structure; users see the reorganization.
