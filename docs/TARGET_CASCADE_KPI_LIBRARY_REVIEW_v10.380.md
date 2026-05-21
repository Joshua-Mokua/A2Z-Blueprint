# Target Cascade + KPI Library — Deep Review

**Version anchor:** v10.380 (May 2026)
**Per:** Joshua's directive — *"do a deep review of the target cascade and kpi library for more understanding and appreciation also on how they are configured, what can be fixed."*
**Companion to:** `PERFORMANCE_MANAGEMENT_FRAMEWORK_REVIEW_v10.376.md`

This document is the **deep architectural review** Joshua asked for. Three goals:
1. Understand the cascade + library as they actually exist (with concrete counts)
2. Identify drift, gaps, and bugs systematically
3. Surface what can be safely fixed in v10.380 vs what needs separate batches

---

## Part 1 — Target Cascade: structure and scale

### 1.1 Storage

`data/target_cascade.json` is a dict keyed by **composite string**:

```
'<staff_code>|<kpi_name>|<year>' → cascade_entry
```

Example: `'300001|PBT|2026'` → MD's PBT cascade for 2026.

### 1.2 Scale (verified counts)

| Dimension | Count |
|---|---:|
| Total entries | **1,051** |
| Distinct cascading staff (`from_code`) | 51 |
| Distinct KPIs cascaded | **21** (+1 corrupted key — see 1.4) |
| Years used | 1 (2026 only) |
| Allocation count per entry | min=1, max=386, avg=38.3 |
| Top originators | MD (300001), Nicholas Ndegwa (300002), other Chiefs |

Every Chief cascades 21 KPIs — the standard "full BSC" set. Branch Managers and below cascade fewer (the subset relevant to their role).

### 1.3 Entry schema

```python
{
    'from_code': '300001',           # cascading staff
    'from_name': 'William Mwanake',  # display name
    'kpi':       'PBT',              # KPI name (NOT id — see Part 3)
    'period':    '2026',
    'total_target':   22_000_000_000,
    'allocated_sum':  22_000_000_000,
    'allocations': [
        {'to_code': '300002', 'to_name': 'Nicholas Ndegwa', 'amount': 2_200_000_000},
        ...12 allocations for MD's PBT...
    ]
}
```

### 1.4 The corruption: `deadline|300001|2026`

One key violates the schema:

```python
'deadline|300001|2026': {
    'staff_code': '300001',
    'period': '2026',
    'targets_locked': True,
    'locked_at': '2026-04-15T18:14:31.308820',
    'confirmed': True,
    'confirmed_at': '2026-04-15T18:14:31.308836',
    'confirm_by': '2026-05-25',
    'cascade_by': '2026-05-09'
}
```

This is **MD's lock-state metadata** stuffed into the cascade dict. Causes:
- `for k in tc.keys()` iterations need explicit filtering
- Reading code (e.g. v10.376 canonical_pbt_bsc_view) must be defensive
- A naïve consumer treating this as a cascade entry would crash

**Status**: documented; cleanup deferred (touching live data needs careful migration). v10.380 ships a defensive utility in `kpi_alias_resolver`; full cleanup is a follow-up batch.

### 1.5 The 21 cascaded KPIs

```
Account Dormancy        Loan Book Growth
Audit Score             NPL Ratio
CASA Ratio              New Accounts
CX Score                Number of Business Borrowers
Channel Dormancy        PAR
Collection Throughput   PBT
Commercial Deposit Growth  Retail & MSME Deposit Growth
Compliance Score        Staff Productivity
Disbursements Corporate Loans  Top 100 Customers Deposit
Disbursements MSME Loans       Total NFI
Disbursements Retail Loans
```

All Title Case names. Match `kpi_library.kpis[*].name` field, NOT `id` field.

---

## Part 2 — KPI Library: structure and scale

### 2.1 Storage

`data/kpi_library.json` is a top-level dict with these keys:

| Field | Purpose | Count |
|---|---|---:|
| `pillars` | 4 BSC perspectives + 2 sub-pillars (Process, Risk) | 4 + 2 |
| `pillar_weights` | Current weight distribution | 4 entries |
| `kpis` | The KPI definitions (id, name, pillar, weight, unit, direction, cbk_ref, active, description, source) | **185** (109 active) |
| `active_kpis` | Quick-access list of active IDs | — |
| `role_kpis` | Role → list of KPI IDs assigned | **227** roles |
| `kpi_weights` | Per-KPI weight overrides | — |
| `_v10324_*` ... `_v10337_*` | Migration breadcrumbs (10 fields) | history |

### 2.2 The dual ID convention drift

The library mixes THREE generations of ID styles:

| Style | Count | Example | Era |
|---|---:|---|---|
| Numeric K-codes | 18 (`K001`-`K084`+) | `K001` = "Loans Disbursed (KES M)" | Original |
| Title Case (id == name) | ~14 | `id="CASA Ratio"`, `name="CASA Ratio"` | Middle (2023?) |
| SCREAMING_SNAKE_CASE | **169** (dominant) | `id="NPL_RATIO"`, `name="NPL Ratio"` | Current |
| Other | 2 | `"CASA Ratio"`, `"CX Score"` | Edge cases |

**Critical:** when `id ≠ name`, **167 of 185 KPIs have drift**.

### 2.3 Two reference systems coexist

- **bsc_engine.submit / validate** uses `kpi_library.id` field
- **target_cascade.json** uses `kpi_library.name` field
- **role_kpis** mostly uses `kpi_library.id` (with 34 orphans — see Part 3)
- **bsc_actuals_*.json records** use `kpi_id` matching library `id`
- **pages/1_perform.py** (canonical BSC) reads through both

Same KPI, different identifiers depending on where you look. This is the source of **most BSC integration friction**.

### 2.4 Library duplicates

The library has internal duplicates:

| Duplicate | Same name |
|---|---|
| `K006` and `NEW_ACCOUNTS` | both name `"New Accounts Opened"` |
| `K004` and `NPL_RATIO` | both refer to NPL Ratio |
| `K005` and revenue KPIs | likely overlap |
| `K003` and `TOTAL_NFI` | overlap on fee income |

Likely from when the SCREAMING_SNAKE migration ran without retiring K-codes. Cleanup deferred (need source-of-truth decision per KPI).

---

## Part 3 — The 34 orphan KPI references in `role_kpis`

`role_kpis` references 193 distinct KPI IDs across 227 roles. **34 of those references have NO definition in `kpis[]`**.

### 3.1 The orphan inventory (by impact)

```
COMPLIANCE              referenced in 21 roles  ← biggest impact
LOAN_GROWTH             referenced in 17 roles
AUDIT_SCORE             referenced in 16 roles
TOTAL_NFI               referenced in 15 roles
CX_SCORE                referenced in 15 roles
BUSINESS_BORROWERS      referenced in 13 roles
COMMERCIAL_DEPOSIT      referenced in 12 roles
DISB_CORPORATE          referenced in 12 roles
NEW_CUST                referenced in 10 roles
FEES_COMM               referenced in 9 roles
RETAIL_MSME_DEPOSIT     referenced in 9 roles
DISB_MSME               referenced in 9 roles
DEP_GROWTH              referenced in 8 roles
COLLECTION_THROUGHPUT   referenced in 8 roles
TOP100_CUSTOMERS        referenced in 7 roles
CASA_RATIO              referenced in 6 roles
DISB_RETAIL             referenced in 6 roles
ACCOUNT_DORMANCY        referenced in 6 roles
CHANNEL_DORMANCY        referenced in 6 roles
STAFF_PROD              referenced in 6 roles
... 14 more with lower frequency
```

### 3.2 Two classes of orphans

**Class A — alias drift (17 IDs).** Short SCREAMING_SNAKE version of an existing Title Case library entry. Resolvable by alias mapping:

| Orphan ID | Library equivalent | Pillar |
|---|---|---|
| `TOTAL_NFI` | `Total NFI` | Financial |
| `CX_SCORE` | `CX Score` | Customer Focus |
| `AUDIT_SCORE` | `Audit Score` | Operational Excellence |
| `COMPLIANCE` | `COMPLIANCE_SCORE` | Process |
| `RETAIL_MSME_DEPOSIT` | `Retail & MSME Deposit Growth` | Financial |
| `COMMERCIAL_DEPOSIT` | `Commercial Deposit Growth` | Financial |
| `CASA_RATIO` | `CASA Ratio` | Financial |
| `TOP100_CUSTOMERS` | `Top 100 Customers Deposit` | Customer Focus |
| `ACCOUNT_DORMANCY` | `Account Dormancy` | Operational Excellence |
| `CHANNEL_DORMANCY` | `Channel Dormancy` | Operational Excellence |
| `STAFF_PROD` | `Staff Productivity` | People & Learning |
| `COLLECTION_THROUGHPUT` | `Collection Throughput` | Financial |
| `DISB_CORPORATE` | `Disbursements Corporate Loans` | Financial |
| `DISB_MSME` | `Disbursements MSME Loans` | Financial |
| `DISB_RETAIL` | `Disbursements Retail Loans` | Financial |
| `BUSINESS_BORROWERS` | `Number of Business Borrowers` | Customer Focus |
| `LOAN_GROWTH` | `Loan Book Growth` | Financial |

**Class B — genuinely missing (17 IDs).** No library equivalent exists. Need real KPI definitions to be added.

| Orphan ID | Likely meaning | Status |
|---|---|---|
| `DEP_GROWTH` | Total Deposit Growth (aggregate) | Missing — closest is "Retail & MSME" + "Commercial" separately |
| `FEES_COMM` | Fees & Commissions | Missing |
| `CIR` | Cost-to-Income Ratio | Missing |
| `NIM` | Net Interest Margin | Missing |
| `ROE` | Return on Equity | Missing |
| `NPS` | Net Promoter Score | Missing |
| `DIGITAL_ACT` | Digital Activation Rate | Missing |
| `NEW_CUST` | New Customers Acquired | Closest: `NEW_CUSTOMERS_ACQUIRED` exists |
| `ACTIVE_ACCTS` | Active Accounts | Missing |
| `PAR` | Portfolio at Risk | Library HAS both `K077` ("ROPA Records...") and `PAR` (different concept) |
| ...7 more | various | Missing |

**Class B is more significant than Class A** — these are KPIs that someone said should be measured but were never defined.

### 3.3 Impact on MD's BSC

MD's `role_kpis['Managing Director']` has 12 IDs. Today:

| ID | Status |
|---|---|
| `PBT` | ✓ defined |
| `NPL_RATIO` | ✓ defined |
| `DILIGENCE` | ✓ defined (name="Due Diligence Quality") |
| `DEP_GROWTH` | **Class B orphan** |
| `LOAN_GROWTH` | **Class A** (→ `Loan Book Growth`) |
| `FEES_COMM` | **Class B orphan** |
| `CIR` | **Class B orphan** |
| `NIM` | **Class B orphan** |
| `ROE` | **Class B orphan** |
| `NEW_CUST` | **Class B orphan** (closest: NEW_CUSTOMERS_ACQUIRED) |
| `DIGITAL_ACT` | **Class B orphan** |
| `NPS` | **Class B orphan** |

After v10.380 alias resolution: 4/12 resolvable (the existing 3 + LOAN_GROWTH via alias). **8 still orphan after aliases.**

The MD's BSC currently CANNOT submit those 8 KPIs through `bsc_engine.submit()` — it would reject with `kpi_id not in kpi_library`.

---

## Part 4 — Cross-reference matrix

For each cascaded KPI name, where else does it appear?

| Cascade name | role_kpis ID (if any) | bsc_actuals seen? |
|---|---|---|
| PBT | `PBT` ✓ | YES (3 source_modules including `canonical_*_v10377`) |
| NPL Ratio | `NPL_RATIO` ✓ | YES (legacy) |
| Compliance Score | `COMPLIANCE_SCORE` or `COMPLIANCE` (alias) | YES |
| Audit Score | `AUDIT_SCORE` (orphan in role_kpis) | YES (Title Case "Audit Score" used) |
| CX Score | `CX_SCORE` (orphan) | YES (Title Case used) |
| Total NFI | `TOTAL_NFI` (orphan) | YES (Title Case used) |
| ... | | |
| New Accounts | none (cascade orphan?) | Possibly `K006` or `NEW_ACCOUNTS` |

The cross-reference shows: **`bsc_actuals_*.json` mostly uses cascade-style Title Case names**, while `role_kpis` mostly uses SCREAMING_SNAKE IDs.

---

## Part 5 — Pillar weights drift (re-stated from v10.376 review)

Two parallel weight stores:

| Source | Weights | Notes |
|---|---|---|
| `pillars[]` array | Financial 0.40 / Customer Focus 0.25 / Op Excellence 0.25 / People&Learning 0.10 | Original "balanced" |
| `pillar_weights` dict | Financial **0.68** / Customer Focus 0.14 / Op Excellence 0.06 / People&Learning 0.12 | Current "financial-heavy" |

Both are read by different consumers; different consumers may compute different MD composite scores.

**Status**: documented; not fixed in v10.380 (Joshua decision needed on which weights are authoritative).

---

## Part 6 — Cascade configuration patterns

### 6.1 Top originators

The 51 cascading staff are mostly Chiefs and Directors. Branch Managers DO cascade (to their reports). The MD cascades to 12 direct reports; each of those cascades to ~10-20 reports; and so on down to Branch Manager → Officers.

### 6.2 Allocation patterns

- Most KPIs use *amount* allocations (KES values for PBT, Deposits)
- Score KPIs (Audit Score, Compliance Score) cascade as flat targets (not divisible)
- Ratio KPIs (NPL Ratio, CASA Ratio) cascade as common targets (everyone hits the same %)

These different patterns aren't reflected in the cascade schema — `allocations[].amount` is always a number but its meaning depends on KPI type. **Documented; needs schema hardening in follow-up batch.**

### 6.3 Lock state

The `deadline|300001|2026` corrupted key is MD's lock state. Per the schema:
- `targets_locked: True` — MD has committed targets
- `confirmed: True` — confirmed by approval
- `cascade_by: '2026-05-09'` — deadline for cascading to direct reports
- `confirm_by: '2026-05-25'` — deadline for full bank confirmation

This is **valuable PM-cycle metadata** that just lives in the wrong place. Should move to a dedicated `cascade_meta` field at the top level.

---

## Part 7 — Other findings

### 7.1 BSC actuals source_module diversity

Today's `bsc_actuals_2026-Q2.json` has 8,167 records across many source_modules:
- `verification_test` (probably most records — generated for testing)
- `pipeline` (CRM pipeline)
- `bsc_admin` (manual entry)
- `actuals_engine` (automated)
- `management_accounts` (the PBT source per kpi_library)
- ... and now (v10.379) `canonical_pbt_*_v10377` (canonical engines)

A migration ladder: deprecate `verification_test` records → migrate `pipeline` and `actuals_engine` records to canonical sources → eventually only canonical source_modules remain. **That's Phase D for each KPI.**

### 7.2 cbk_ref field

Many KPIs have empty `cbk_ref`. Central Bank of Kenya regulatory references should populate this for compliance KPIs (Audit Score, Compliance Score, NPL Ratio, PAR). Documented; data-quality follow-up.

### 7.3 active=null vs active=True/False

Some KPIs have `active=None` (e.g. `K084`). The 109 "active" count uses `if x.get('active')` which is False for None — accidentally excluded. **109 may be slightly undercounted.** Audit needed.

---

## Part 8 — What v10.380 ships (fixes what can be safely fixed)

### 8.1 Deliverables

1. **This review document** — locks the understanding
2. **`utils/kpi_alias_resolver.py`** — leaf module providing:
   - `KPI_ALIASES` dict (17 Class A mappings)
   - `resolve_kpi_id(maybe_alias) → canonical_id` (or original if no alias)
   - `get_kpi_definition(maybe_alias) → kpi_library entry` (None if truly missing)
   - `list_class_b_orphans() → list of (id, count, suggested_definition)` for documentation
   - `clean_cascade_dict(raw) → cascade_only` — defensive filter for `deadline|*` corruption
3. **G266 audit gate** — locks review + resolver + alias coverage check
4. **Tests** — verify resolver behavior + Class B orphan enumeration + cascade cleaner

### 8.2 Why this is safe

- **`kpi_library.json` is NOT modified** (no risk to consumers reading it directly)
- **`target_cascade.json` is NOT modified** (deadline corruption stays but resolver filters it for clean readers)
- **`role_kpis` is NOT modified** (consumers see same data; resolver translates on demand)
- Module is opt-in: consumers that don't import it work exactly as before

### 8.3 What v10.380 deliberately does NOT do

- Does NOT add Class B missing KPI definitions (need Joshua's product-mgmt input)
- Does NOT clean up `kpi_library.json` duplicates (K006 vs NEW_ACCOUNTS)
- Does NOT clean up `target_cascade.json` `deadline|*` corruption in place
- Does NOT reconcile pillar weight drift (Joshua decision)
- Does NOT modify role_kpis to canonicalise IDs
- Does NOT add cbk_ref values
- Does NOT touch bsc_actuals records or bsc_engine.py

Single concern: **provide an alias resolution layer so 17 Class A orphans resolve cleanly + document everything else for follow-up.**

---

## Part 9 — Decisions awaiting Joshua

### 9.1 Class B missing KPIs (8 on MD's BSC)

These 8 IDs are in `role_kpis['Managing Director']` but have NO library definition:

| ID | Suggested definition |
|---|---|
| `DEP_GROWTH` | Total Deposit Growth (%) — aggregate of Retail + Commercial |
| `FEES_COMM` | Fees & Commissions Income (KES M) |
| `CIR` | Cost-to-Income Ratio (%) |
| `NIM` | Net Interest Margin (%) |
| `ROE` | Return on Equity (%) |
| `NPS` | Net Promoter Score |
| `DIGITAL_ACT` | Digital Activation Rate (%) |
| `NEW_CUST` | New Customers (could alias to `NEW_CUSTOMERS_ACQUIRED`?) |

**Joshua decisions needed:**
- Add canonical definitions for each (name, pillar, weight, unit, direction, source)?
- Or remove them from MD's role_kpis (acknowledge they're aspirational)?
- Targets to cascade with?

### 9.2 Pillar weights

Library has `pillars[]` 40/25/25/10 AND `pillar_weights` 68/14/6/12. Which is authoritative?

### 9.3 K-code retirement

Library has 18 numeric K-codes (K001 etc) that duplicate newer SCREAMING_SNAKE entries. Retire?

### 9.4 Cascade `deadline|*` cleanup

Move lock-state metadata out of the cascade dict to a top-level `cascade_meta` field?

### 9.5 Active KPI count

Should `active=None` count as active? Need a normalisation pass.

---

## Part 10 — Honest acknowledgement

The KPI library + target cascade are clearly the product of multiple migration waves:
- Original K-code design
- Title Case names
- SCREAMING_SNAKE migration (`_v10324`-`_v10337` breadcrumbs)
- Cascade integration

Each wave added without fully retiring the previous. The result is a working system with substantial drift — exactly the kind Joshua warned about. v10.380 does not eliminate the drift; it provides the alias resolution layer so consumers can navigate it safely, and documents the cleanup plan for follow-up batches.

This review is the most important artifact of v10.380 — **understanding before action** per Joshua's discipline.
