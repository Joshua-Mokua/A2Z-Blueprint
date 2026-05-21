# Changelog — v10.284 Runtime hotfix + G177 import-integrity gate

**Date:** 2026-05-08
**Phase:** 2A — Hotfix + audit-coverage hardening
**Audit:** 177/177 gates PASS = 100.0%
**G162 Rebase:** none required

---

## Why this release exists

Three runtime errors were reported from the field after v10.283 deployed:

1. `ModuleNotFoundError: No module named 'utils.audit_log'` — page 95
2. `KeyError: 'campaign_id'` — page 94
3. `ModuleNotFoundError: No module named 'utils.interaction_capture'` — page 92

Errors 1 and 2 are real platform bugs introduced or exposed by recent
work. Error 3 is a deployment-state issue (v10.275 module did not reach
the runtime tree), not a code bug.

The diagnosis traced error 1 to fictitious utility module names I
introduced when building the v10.281, v10.282, and v10.283 cockpits.
The audit gate suite did not catch this because no gate was checking
that `from utils.X import` statements in pages reference real modules.
That gap is now closed by G177.

This release fixes the four affected pages, hardens page 94 against
legacy campaign data, and adds the missing static-integrity gate so
this bug class cannot ship again.

---

## What changed

### Pages 95, 96, 97, 99 — import name corrections

The four pages I built in v10.281 / v10.282 / v10.283 used module names
that don't exist on disk:

| Wrong import                                          | Correct import                                        |
|-------------------------------------------------------|-------------------------------------------------------|
| `from utils.audit_log import audit_log`               | `from utils.core_audit import audit_log`              |
| `from utils.access_helpers import require_access`     | `from pages._access import require_access`            |

Both corrected across all four pages.

### Pages 95, 96, 97, 99 — `audit_log()` signature corrections

The real `audit_log()` signature is:

```python
def audit_log(action: str, username: str, detail: str = "",
              module: str = "", before: str = "", after: str = ""):
```

I had been calling it with `actor=`, `target=`, `entity=`, `outcome=`,
and `metadata=` — none of which match. Every call site across the four
pages has been rewritten to use the canonical signature with `action`,
`username`, and `module` named correctly. The `detail`, `before`, and
`after` slots remain available for future enrichment but are not
currently populated.

### Pages 95, 96, 97, 99 — `require_access` dotted-path corrections

Each page's `require_access()` argument now matches its manifest
`module_path` exactly. Previously they used flat names like
`"shared.it_digital_pt2"`; the v10.200 dotted-path resolver requires
the manifest's exact `module_path` value:

| Page                       | `require_access(...)`                  |
|----------------------------|----------------------------------------|
| `95_command_centre.py`     | `shared.command_centre`                |
| `96_it_digital_pt1.py`     | `it_platform.it_digital_pt1`           |
| `97_it_digital_pt2.py`     | `it_platform.it_digital_pt2`           |
| `99_swift_cockpit.py`      | `trade_finance.swift_cockpit`          |

### Page 94 — campaigns_management hardened against legacy data

`KeyError: 'campaign_id'` was triggered by legacy `data/campaigns.json`
records that pre-date the v10.279 schema (they use `id` / `type` /
`status` instead of `campaign_id` / `campaign_type` / `state`). The
page now filters `list_campaigns()` results to only engine-shaped
records and surfaces a banner when legacy records are present:

```
N legacy campaign record(s) ignored — they predate the v10.279
catalog schema and need migration to the campaign_id/state shape
before they appear here.
```

The cockpit no longer crashes on stale data. Migration of the legacy
records to the engine schema is a separate task (it requires data
mapping by Joshua, not code).

### Audit gate G177 — `gate_page_imports_resolve`

Static integrity check that prevents this entire bug class from
shipping again. Two checks per page in `pages/`:

1. Every `from utils.X import ...` must reference a real `utils/X.py`
   on disk. Imports inside `try:` blocks are intentionally skipped
   (those are explicit soft imports — see `91_systems_view.py:
   utils.integration` for the canonical example).

2. Every dotted-form `require_access("a.b")` must match a manifest
   `module_path`. Without this match, `check_access_dotted` falls
   through to deny once the user lacks the explicit grant — silent
   denial in production rather than a build failure.

Specific patterns this gate catches:

- `from utils.audit_log import ...` (canonical: `utils.core_audit`)
- `from utils.access_helpers import ...` (canonical: `pages._access`)
- Any other invented-name import I or another contributor might add

Regression test: deliberately injecting a bad import into any page
fails the gate immediately with a clear message naming the page,
the bad module, and the runtime impact.

---

## System-wide integrity sweep results

A deeper sweep beyond just imports verified the rest of the platform
is consistent:

| Check                                                    | Result               |
|----------------------------------------------------------|----------------------|
| All pages parse cleanly                                  | 104 / 104 ✓         |
| Pages on disk match manifest entries                     | 104 = 104 ✓         |
| All dotted-form `require_access` resolve to manifest     | 96 / 96 ✓           |
| All `from utils.X` imports reference real modules        | clean (after fix) ✓ |
| Pre-existing soft imports (try/except)                   | 1 (91_systems_view) |
| Module-level fastapi/streamlit env errors                | env-only, not bugs  |

No further latent module-name bugs were found.

---

## What is NOT fixed by this release

**`utils.interaction_capture` missing on the runtime machine** is a
deployment-state issue, not a code defect. The module was shipped in
`a2z_v10.275_customer_behavioral_pt1_cluster.zip` along with six other
modules (mobile_app_tracking, branch_interaction, journey_and_widget,
onboarding_optimization, customer_behavioral_profile, dynamic_cohorts).
If those files are not present in `utils/` on the runtime tree,
re-extract that v10.275 zip over the working directory.

This release does not bundle those modules — they are not part of the
v10.284 work and bundling them would obscure what changed in this
hotfix. They remain available in the original v10.275 cluster zip.

---

## Files changed

```
pages/94_campaigns_management.py             legacy-data filter + warning banner
pages/95_command_centre.py                   imports + audit_log + require_access fixed
pages/96_it_digital_pt1.py                   imports + audit_log + require_access fixed
pages/97_it_digital_pt2.py                   imports + audit_log + require_access fixed
pages/99_swift_cockpit.py                    imports + audit_log + require_access fixed
scripts/audit.py                             G177 gate_page_imports_resolve added
CHANGELOG_v10.284.md                         NEW (this document)
```

---

## Audit summary

```
  Score: 177/177 gates = 100.0% — PASS
```

G177 now in production. The fictitious-module bug class cannot ship
again.

---

## Note on the v10.284 QA Map document

The QA Map for the Ecobank engagement (`a2z_v10.284_qa_map_ecobank.docx`)
is a separate v10.284 deliverable that shipped before this hotfix was
needed. It is unaffected — the document references the platform's
posture, not the runtime fixes — and continues to be the canonical
Q&A reference for the panel discussion.

This release uses the same v10.284 version tag because the runtime
hotfix is part of the same delivery cycle. The next batch advances
to v10.285 (Phase 2A retrospective).
