# A2Z MIS 360 — Comprehensive System Audit (v10.219)

**Audit date:** 2026-05-07
**Scope:** End-to-end review of every concern scooped during the
v10.193–v10.218 campaign window (cockpit absorption, helper extraction,
MD Cockpit, data scaffolding, editorial reassignments, dotted-form
rollout, G161 ratchet) plus broader platform discipline (config vs
hardcoding, PostgreSQL adoption, admin page coherence, drift risks).
**Audit baseline:** 161/161 PASS at start of batch.

---

## Executive summary

The v10.193–v10.218 campaign delivered substantively — cockpit
absorption sub-campaign closed at 13/13, MD Cockpit shipped,
manifest discipline held, dotted-form access activated for finance,
G161 ratchet introduced. However, a holistic audit reveals
**three significant drift areas** that the campaign's incremental
batches couldn't address from inside their own scope:

| # | Drift area | Severity | Status |
|---|---|---|---|
| 1 | Tenant identity hardcoding | **CRITICAL** | ~4,100 hardcoded values; 40 cfg() lookups |
| 2 | PostgreSQL adoption gap | **HIGH** | 12 tables in DDL; 2 migrators in script; 165 JSON files still file-based |
| 3 | Test coverage absent | **HIGH** | No coverage.xml; pytest infra exists but no recent run |

These are not regressions — they pre-date the v10.193 starting point. But
they ARE drift in the sense that they grow worse as new pages are added
without using the existing config/PG infrastructure. The audit's goal
is to lock current state as the baseline ceiling and make future drift
audit-detectable.

This audit's **concrete deliverable**: G162 ratchet with baseline file,
KAIZEN framework, master prompt addendum, advisory roadmap. NOT the
fix to all 4,100 hardcoded values — that's a multi-batch sub-campaign.

---

## 1. Drift area 1: Tenant identity hardcoding (~4,100 values)

### 1.1 The numbers

Audited every Python file in pages/, utils/, scripts/ for hardcoded
tenant-specific identifiers:

```
"Ecobank"   240 occurrences      (bank name)
"KES"      1,410 occurrences      (currency code)
"CBK"      1,371 occurrences      (regulator)
"Kenya"      324 occurrences      (country)
"FLEXCUBE"   649 occurrences      (core banking system)
"KRA"        125 occurrences      (tax authority)
                ──────
            ~4,100 total hardcoded tenant references
```

### 1.2 The infrastructure that EXISTS but isn't used

`utils/config.py` (86 lines) provides `cfg(key, default)`, plus
helpers like `get_departments()`, `get_branches()`, `get_roles()`.

`data/org_config.json` (81KB) contains:
```json
{
  "bank_name": "Ecobank Kenya",
  "app_name": "A2Z Blueprint",
  "bank_code": "ECO",
  "country": "Kenya",
  "currency": "KES",
  "currency_symbol": "KES",
  ... 22 departments, 94 branches, 123 roles, 88 modules ...
}
```

So the platform DOES have:
- A configuration file with tenant identity
- A loader API (`cfg()`, `get_*()` helpers)
- A 6-section admin page that edits this config

What it DOESN'T have:
- **A discipline that pages READ from config instead of hardcoding**
- **An audit gate that catches hardcoded tenant strings**
- **Helper functions for the most common cases** (e.g. `bank_name()`,
  `currency()`, `country()`)

### 1.3 Why this matters

Ecobank-Kenya is the current target client, but the platform's
ambition is to be a **multi-tenant bank-wide intelligence platform**.
The 4,100 hardcoded values are technical debt against that ambition.
When a second tenant is onboarded (or when Ecobank rebrands, or when
a regulatory consultation requires "the Bank" instead of "Ecobank"),
the codebase needs ~4,100 changes versus ~4,100 config reads.

This is the SAME class of drift that v10.198's manifest discipline
addressed for routes — pre-v10.197, page metadata was scattered across
sidebar definitions, route registrations, and access checks. v10.197
unified them in the manifest. v10.219+ should do the same for tenant
identity.

### 1.4 Recommended ratchet — G162 (implemented this batch)

**Implementation:** baselined kaizen ratchet. Records current count
of hardcoded `"Ecobank"`, `"KES"`, `"CBK"`, `"FLEXCUBE"`, `"KRA"`,
`"Kenya"` strings in `data/audit_baselines.json` on first run. On
subsequent runs, FAILS if count exceeds baseline.

**The kaizen interpretation:** "no new hardcoding; gradual reduction."
New pages must use `cfg()` helpers; refactors of existing pages
that REPLACE hardcoded strings with cfg() calls reduce the
baseline. Either direction works; only adding more hardcoded
strings fails the gate.

This is gate #162. New audit baseline becomes 162/162 PASS once
the baseline file is created.

### 1.5 Recommended config helpers (advisory — future batch)

Add to `utils/config.py`:

```python
def bank_name() -> str:
    """Returns configured bank name. e.g. 'Ecobank Kenya'."""
    return load_org_config().get("bank_name", "[Bank Name]")

def currency() -> str:
    """Returns configured currency code. e.g. 'KES'."""
    return load_org_config().get("currency", "USD")

def currency_symbol() -> str:
    """Returns configured currency symbol. e.g. 'KES' or 'KSh'."""
    return load_org_config().get("currency_symbol", "$")

def country() -> str:
    """Returns configured country. e.g. 'Kenya'."""
    return load_org_config().get("country", "")

def regulator() -> str:
    """Returns configured prudential regulator. e.g. 'CBK'."""
    return load_org_config().get("regulator", "[Regulator]")

def core_banking_system() -> str:
    """Returns configured core banking system. e.g. 'FLEXCUBE'."""
    return load_org_config().get("cbs_name", "[CBS]")

def tax_authority() -> str:
    """Returns configured tax authority. e.g. 'KRA'."""
    return load_org_config().get("tax_authority", "[Tax Authority]")
```

Note: `regulator`, `cbs_name`, `tax_authority` aren't in
org_config.json yet — adding them is part of the future batch.

### 1.6 Recommended admin page enhancement (advisory)

The admin page's "🏦 Organisation" sub-tab already exists. Currently
it edits departments, branches, roles. It should also expose
**tenant identity** as the FIRST thing visible:

```
🏦 Organisation
├── Tenant Identity (NEW — top of page)
│   ├── Bank name:    [Ecobank Kenya          ] (editable)
│   ├── Bank code:    [ECO                    ] (editable)
│   ├── Country:      [Kenya                  ] (dropdown)
│   ├── Currency:     [KES — Kenyan Shilling  ] (dropdown)
│   ├── Currency sym: [KES                    ] (editable)
│   ├── Regulator:    [CBK — Central Bank Kenya] (editable)
│   ├── Core banking: [Oracle FLEXCUBE v12    ] (editable)
│   └── Tax authority:[KRA — Kenya Revenue    ] (editable)
├── Departments (existing)
├── Branches (existing)
└── Roles (existing)
```

This makes tenant identity:
- **Discoverable** — first thing in Organisation sub-tab
- **Editable** without code change
- **Validated** before save (no empty values, etc.)
- **Audit-logged** when changed

Effort: ~80 lines in `pages/7_admin.py`. **Future batch (v10.220+).**

---

## 2. Drift area 2: PostgreSQL adoption gap

### 2.1 The numbers

```
DDL files                       2 files (create_tables.sql, create_tables_v53.sql)
Tables defined in DDL          12 tables  (8 + 4 across the two files)
Migration script               scripts/migrate_to_postgres.py exists (422 lines)
Migration functions defined     2  (migrate_bank_targets, migrate_baselines)
db.dual_load/dual_save calls   42 across pages/ + utils/
JSON data files (file-based)  165
Direct write_text in pages/    94 (some legitimate, some PG-bypass)
```

### 2.2 The gap

Memory says "PG migration (33/52 tables)". The actual count of
*defined-in-DDL-files* is 12, with 2 migrators. The "33/52" tracking
got ahead of the work — likely from earlier optimistic planning that
counted "tables we COULD migrate" rather than "tables we HAVE migrated."

This is itself a drift signal: **campaign tracking has decoupled
from actual progress.** Worth flagging.

### 2.3 What's working

- `utils/db.py` has the dual-mode seam (`load_json`, `save_json`,
  `dual_load`, `dual_save`). When PG is reachable, writes go to BOTH
  PG and JSON; reads prefer PG.
- `is_postgres_ready()` toggles the mode at runtime.
- 42 dual_load/dual_save calls show that the seam IS in active use
  for the migrated subset.
- G2 (direct_io) gate already polices direct json.loads/write_text
  in non-foundational files.

### 2.4 What's missing

- **No DDL for the 40+ JSON data files that should be migrated**
  (loan_applications, pipeline, treasury_fd, board_papers,
  strategic_initiatives, smart_alerts, tier1_benchmarking, sbu_pnl,
  revenue_leakage, mgmt_accounts, capital_adequacy, liquidity_metrics,
  bsc_data, etc.).
- **No migration plan ratchet** — no audit gate enforces "any new
  data file in production must have a corresponding DDL".
- **No coverage report on what fraction of writes go through dual_save
  vs direct write_text** — would quantify the bypass.

### 2.5 Recommended approach (advisory — future batch sub-campaign)

A multi-batch sub-campaign analogous to the cockpit campaign:

| Batch | Scope |
|---|---|
| v10.220 | DDL for all 40+ data files; lock as v10.220.sql |
| v10.221 | Migrators for the 5 highest-value tables (board_papers, pipeline, loan_apps, smart_alerts, mgmt_accounts) |
| v10.222 | Migrators for next 10 |
| v10.223–v10.225 | Remaining tables, with ratcheting gate |
| v10.226 | G164 ratchet: every JSON file under data/ must have DDL OR be on a documented exemption list |

Effort: significant (15+ batches). But the platform is at the right
architectural maturity for this sub-campaign — the manifest discipline,
manifest-aware closure gates, and dotted-form access give clean
foundations.

### 2.6 No new ratchet implemented this batch

PG migration ratcheting requires the DDL work to land first.
v10.219 documents the gap; v10.220+ executes the sub-campaign.

---

## 3. Drift area 3: Test coverage absent

### 3.1 The numbers

```
tests/ directory                exists (14 sub-directories)
tests/__init__.py               exists
README.md                       exists
coverage.xml                    NOT present
htmlcov/                        NOT present
```

The pytest infrastructure is in place, but no recent coverage report
was generated. Memory says "test coverage (~45%)" but without a
coverage.xml to verify against, that number is reported, not measured.

### 3.2 What's needed

A coverage run + ratchet that prevents coverage regression. Same
kaizen pattern as G162:
- G165: record current coverage as baseline; fail if it drops by
  more than 0.5pp.

### 3.3 Why this matters less than 1 and 2

Test coverage is important but the platform's audit-gate suite
(currently 161 gates) provides substantial behavioural assurance
even without unit-test coverage. Each closure-arc gate verifies
imports + constructors + methods + access + audit_log discipline.
The 161 gates ARE a kind of integration test suite.

So while coverage is a gap, it's not the most urgent gap.

### 3.4 No new ratchet implemented this batch

Requires running pytest first to establish baseline. Future batch.

---

## 4. What's working well

The campaign held discipline across 26 consecutive code batches.
Specific strengths:

### 4.1 Audit gate suite
161 → 162 gates (after this batch's G162). Every closure-arc-UI
gate is manifest-aware behavior-based (13 gates refactored during
v10.202–v10.212). G161 (this batch's predecessor) catches
module_path drift in real time.

### 4.2 Manifest discipline
v10.197's pages/_manifest.json is the canonical source of truth.
G160 enforces well-formedness; G161 enforces module_path/dept
alignment. 96 active pages, 0 cockpits remaining.

### 4.3 Cockpit absorption sub-campaign (v10.202–v10.212)
13/13 cockpits absorbed. -1378 lines net code reduction.
6 absorption pattern variants documented. Helper extracted at
v10.213. Documentation at docs/COCKPIT_ABSORPTION_PATTERNS.md.

### 4.4 Editorial reassignment power
v10.210 + v10.216 demonstrated JSON-only dept reassignments.
Finance dept grew 1 → 4 active pages organically through
functional-owner reasoning.

### 4.5 Dotted-form access (v10.200, activated in v10.217)
Hierarchical access grants now possible. Backward compat preserved.
Finance dept is the first production user.

### 4.6 Single-purpose batch discipline
Each v10.X batch had clear single concern. Cross-cutting concerns
(like the v10.215 bug-fix-plus-scaffolding) were transparently
flagged. No silent scope creep.

---

## 5. Risks going forward

### 5.1 Tenant hardcoding will keep growing without G162

Every new page added without G162 contributes to the drift. G162
caps it at current baseline; new code must use cfg().

### 5.2 PG migration debt will compound

Each new data file added without DDL widens the gap. A future
G164 should require DDL for new data files.

### 5.3 Admin page complexity could erode the registry pattern

Current discipline says "no module-specific tabs in 7_admin.py;
use registry pattern". If a future batch slips a tab in, the
discipline degrades. Worth a periodic audit.

### 5.4 Master prompt drift

The campaign has accumulated many discipline rules across batches
(e.g. "never combine multiple standards into one ZIP", "audit_log
after every write", "use registry pattern in admin"). These are
spread across user memory + CHANGELOGs. A consolidated
docs/MASTER_PROMPT.md doesn't exist yet. Worth creating.

### 5.5 Memory tracking vs reality

PG migration "33/52" is aspirational, not measured. Worth
periodically reconciling memory tracking against ground truth.

---

## 6. Concrete deliverables in this batch (v10.219)

1. **This audit report** (`docs/SYSTEM_AUDIT_v10.219.md`)
2. **KAIZEN framework** (`docs/KAIZEN_FRAMEWORK.md`)
3. **G162 tenant_identity_hardcoding ratchet** in scripts/audit.py
4. **Baseline file** (`data/audit_baselines.json`)
5. **Master prompt addendum** (`docs/MASTER_PROMPT_ADDENDUM.md`)

---

## 7. Advisory roadmap (NOT in this batch)

Single batches are kept tight. The bigger work splits across batches:

### v10.220 — Config helpers + admin tenant identity card
- Add `bank_name()`, `currency()`, `country()`, `regulator()`,
  `core_banking_system()`, `tax_authority()` helpers to utils/config.py
- Add Tenant Identity card to admin Organisation sub-tab
- Add `regulator`, `cbs_name`, `tax_authority` to org_config.json

### v10.221–v10.230 — Tenant hardcoding reduction sub-campaign (10 batches)
- Each batch reduces hardcoded count by ~400 (~10% of total)
- Start with highest-density files (utils/, then large pages)
- G162 baseline ratchets DOWN as pages migrate
- Target: 4,100 → 0 hardcoded over 10 batches (kaizen pace)

### v10.231–v10.245 — PG migration sub-campaign (15 batches)
- v10.231: DDL for 40+ data files
- v10.232–v10.244: migrators in groups of 3-5
- v10.245: G164 ratchet locking the discipline

### v10.246+ — Test coverage push
- Generate baseline coverage report
- G165 ratchet
- Targeted test additions for highest-risk modules

### Continuous — Master prompt evolution
- docs/MASTER_PROMPT.md as living document
- Updated each batch where discipline rules emerge
- Periodic consolidation passes

---

## 8. KAIZEN framework integration

See `docs/KAIZEN_FRAMEWORK.md` for the full framework. Key points:

1. **Baseline is the ceiling, not the floor.** Drift counts can
   only go DOWN, never up.
2. **Small batches, daily cadence.** Average ~120 lines/batch as
   established by the v10.193–v10.218 window.
3. **Audit before AND after every change.** Established discipline.
4. **Document what you fix AND what you defer.** CHANGELOG honest
   acknowledgements.
5. **Ratchets, not heroics.** A new gate that holds the line
   permanently > a one-time cleanup that lets drift back in.

---

## 9. Honest acknowledgements

1. **Audit took ~30 minutes of analysis.** Substantially more
   reconnaissance than usual. Worth it for the comprehensive view.

2. **The 4,100 hardcoded values number is precise but not actionable
   in one batch.** That's deliberate — listing them all would let
   one batch try to fix 4,100 things, which would violate
   single-purpose discipline. The kaizen approach is to lock current
   state, then incrementally reduce.

3. **Admin page enhancement is advisory, not delivered.** The Tenant
   Identity card belongs in v10.220+. Adding it to v10.219 alongside
   audit + framework + ratchet would have been scope creep.

4. **PG sub-campaign sizing is approximate.** "15 batches" assumes
   ~3 tables per batch, which mirrors the cockpit campaign's pace.
   Could compress to 10 batches if migrators are mostly mechanical.

5. **The audit didn't review code quality (style, docstrings, type
   hints, performance).** Scope was limited to drift detection.
   Code quality is a separate audit dimension.

6. **Master prompt addendum is short.** Five new rules added; not a
   full rewrite. The existing master prompt has substantial wisdom
   already (the user memory captures it). Addendum is incremental.

7. **G162's ratchet is intentionally permissive at start** (records
   current state as baseline rather than failing immediately). This
   is the kaizen pattern and matches the spirit of Joshua's request.

---

## 10. Audit baseline

```
v10.218 → v10.219:
  Audit gates: 161 → 162 (G162 added)
  All gates passing: 162/162 = 100% PASS
  Drift areas documented: 3
  New ratchet: 1 (G162)
  New advisories: 5 (config helpers, admin enhancement, PG plan,
                     test coverage, master prompt)
```

The platform is **structurally sound**. The drift areas are real but
identifiable, and now have ratchets / advisories pointing at them.
**Discipline is intact, audit suite is comprehensive, manifest-as-canonical
is working.** The campaign window proved that 26 consecutive clean
batches is achievable with this discipline — v10.219 documents how to
keep that going.
