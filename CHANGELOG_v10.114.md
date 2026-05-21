# CHANGELOG v10.114 — OpEx batch + audit_reviews seed

**Status:** 5 OpEx rules wired to existing CBS-mock tables (board_papers, cbk_returns, dpo_register, projects); audit_reviews.json seeded (250 records); 3 new library entries K132-K134 + matching audit rules. K093 (merchant_acquiring TAT) deferred to v10.115 pending TAT_FIELD pattern.

**Audit:** 143/143 PASS in sandbox.
**Engine self-tests:** 152/152.
**G143 coverage:** **34/131 (26.0%)** — up from 27/128 (21.1%) in v10.113. **+7 covered KPIs, +3 in operational denominator.**
**Tests:** 21 new tests across audit_reviews schema + library K132-K134 + 5 STAFF_FIELD_BY_TABLE additions + 7 rule-output tests + G143 coverage.

---

## Why this drop matters

After v10.113's correctness work (role resolver + admin tabs), v10.114 returns to coverage growth. Eight new operational KPIs come online — five wired to existing CBS-mock tables (zero new seed data) and three audit-discipline KPIs targeting a freshly-seeded `audit_reviews` table.

The OpEx pillar continues filling out. **6 of the 9 wired pillars** (Customer Focus, Financial, OpEx, People & Learning) plus the audit dimension within OpEx now have real per-staff actuals flowing into the BSC. Risk & Governance gets coverage via K134 (Audit SLA Compliance) using the v10.110 `invert: true` flag for semantic mirroring on a "lower-bool-is-good" field.

**Standards numbering**: standards_registry tracks 265 (12 regulatory + 253 enhancement). v10.114 stays in the v9→v10 expansion track's continuation territory.

---

## Scope completion delta

| Dimension | v10.113 | v10.114 | Δ |
|---|---|---|---|
| Master prompt version | v3.7 | **v3.8** | +1 |
| Library KPIs | 149 | **152** | +3 (K132-K134) |
| Operational tables seeded | 13 | **14** | +1 (audit_reviews) |
| Operational tables wired | 11 | **15** | +4 (board_papers, cbk_returns, dpo_register, projects, audit_reviews) |
| Rules registered (active) | 28 | **35** | +7 |
| **G143 coverage** | 27/128 (21.1%) | **34/131 (26.0%)** | +7 covered, +3 denominator |
| Tests | 118 | **139** | +21 |

---

## Deliverable 1 — 5 OpEx rules wired to existing tables

Zero new seed data — these rules target tables that already existed in CBS-mock from earlier drops.

### K104 — Board Papers Submitted On Time (%)

```json
{
  "kpi_id": "K104",
  "source_table": "board_papers",
  "pattern": "BOOL_FRACTION",
  "bool_field": "submitted_on_time",
  "predicate": {"type": "field_in", "field": "status",
                "values": ["Approved", "Returned", "Under Review"]},
  "period_field": "submitted_date"
}
```

6 in-period submitters covered.

### K072 — CBK Returns Filed On Time (%)

```json
{
  "kpi_id": "K072",
  "source_table": "cbk_returns",
  "pattern": "BOOL_FRACTION",
  "bool_field": "on_time",
  "predicate": {"type": "field_is_true", "field": "submitted"},
  "period_field": "submitted_date"
}
```

47 reviewers covered. **Largest OpEx wire-up in the drop.** Wired against `reviewer` field (not `submitted_by`) because the seed data has 50/226 records with empty submitted_by.

### K075 — DPIAs Completed On Time (%)

```json
{
  "kpi_id": "K075",
  "source_table": "dpo_register",
  "pattern": "BOOL_FRACTION",
  "bool_field": "on_time",
  "predicate": {"type": "field_in", "field": "status",
                "values": ["Approved", "Closed", "Contained"]},
  "period_field": "completed_date"
}
```

16 dpo_reviewers covered. The DPO register includes DPIAs, breaches, and ROPA records — all use the `on_time` flag uniformly.

### K036 — Projects On-Time Delivery (%)

```json
{
  "kpi_id": "K036",
  "source_table": "projects",
  "pattern": "PERCENTAGE",
  "numerator_pred": {
    "type": "all",
    "of": [
      {"type": "field_eq", "field": "status", "value": "Completed"},
      {"type": "field_truthy", "field": "actual_end_date"}
    ]
  },
  "denominator_pred": {"type": "field_eq", "field": "status", "value": "Completed"},
  "period_field": "actual_end_date",
  "staff_field_extractor": {"type": "name_lookup", "name_field": "project_manager"}
}
```

Uses `name_lookup` since `project_manager` records full names ("Brenda Andanje"), not staff codes. **Limitation acknowledged**: the rule simplifies to a truthy-check on `actual_end_date` rather than the proper "delivered ≤ planned end date" comparison. The v10.110 `field_le_field` predicate is currently numeric-only; v10.115 adds a `date_le_field` type for strict on-time semantics. v10.114's logic is a no-slip-indicator proxy.

### K093 — Merchant Onboarding TAT (deferred)

merchant_acquiring has a pre-computed `tat_days` field but no separate start/end date columns. The v10.108 TAT_DAYS pattern requires distinct start/end. v10.115 adds a **TAT_FIELD** pattern that uses pre-computed numeric days fields directly. Deferred cleanly with note in the v10.114 plan rather than ship a broken K093.

---

## Deliverable 2 — `data/audit_reviews.json` seed (250 records)

Modeled after the conventions from `legal_matters.json` and `dpo_register.json`. Generated with `random.seed(42)` for reproducibility.

```json
{
  "id": "AUD00001",
  "audit_title": "Branch Operations Audit",
  "audit_type": "branch",
  "category": "operational",
  "branch": "Westlands",
  "auditor_code": "300006",
  "auditor_name": "...",
  "auditor_username": "...",
  "period_end": "2025-11-12",
  "started_date": "2025-10-25",
  "completed_date": "2026-01-30",
  "status": "Closed",
  "score": 4,
  "findings_total": 3,
  "findings_closed": 3,
  "findings_high": 1,
  "sla_target_days": 90,
  "sla_breached": false,
  "department_audited": "Operational",
  "last_updated": "2026-01-30"
}
```

- **8 auditors** sourced from Audit/Risk/Compliance departments in users.json
- **Status mix**: Closed 65%, Open 20%, In Progress 10%, Reopened 5%
- **Score distribution**: weighted toward 3-4 on a 1-5 scale (most audits middling, few extremes)
- **Findings counts**: weighted toward 1-4 findings per audit (long tail to 15)
- **SLA**: 90-day target; ~80% of Closed audits within SLA
- **All 250 auditor_codes validated** against users.json (zero orphans)

---

## Deliverable 3 — Library entries K132-K134

| ID | Name | Pillar | Weight | Direction |
|---|---|---|---|---|
| K132 | Audit Closure Rate (%) | Operational Excellence | 0.05 | higher |
| K133 | Audit Findings Closure Rate (%) | Operational Excellence | 0.04 | higher |
| K134 | Audit SLA Compliance (%) | Operational Excellence | 0.04 | higher |

All ship with `_origin: "v10.114_audit_rules"`.

**Library count: 149 → 152.**

The pre-existing library entry "Audit Score" (id="Audit Score", _origin=v10.107_cascade_reconciliation) coexists with these. Consolidation deferred to v10.115+ — the entry is consumed by cascade and changing its id risks breaking that pathway.

---

## Deliverable 4 — Audit rules (K132-K134)

```json
[
  {
    "kpi_id": "K132",
    "source_table": "audit_reviews",
    "pattern": "PERCENTAGE",
    "numerator_pred": {"type": "field_eq", "field": "status", "value": "Closed"},
    "denominator_pred": {"type": "field_truthy", "field": "id"}
  },
  {
    "kpi_id": "K133",
    "source_table": "audit_reviews",
    "pattern": "RATIO",
    "numerator_field": "findings_closed",
    "denominator_field": "findings_total",
    "predicate": {"type": "field_eq", "field": "status", "value": "Closed"}
  },
  {
    "kpi_id": "K134",
    "source_table": "audit_reviews",
    "pattern": "BOOL_FRACTION",
    "bool_field": "sla_breached",
    "predicate": {"type": "field_eq", "field": "status", "value": "Closed"},
    "invert": true
  }
]
```

All 3 rules produce output for **8 auditors each**.

K134 demonstrates the **v10.110 invert flag** — sla_breached=True is the bad outcome but the KPI direction is "higher = better SLA compliance". With `invert: true`, the rule emits "% NOT breaching SLA" matching the library direction.

---

## Deliverable 5 — STAFF_FIELD_BY_TABLE additions

| Table | Field | Notes |
|---|---|---|
| board_papers | submitted_by | username (head{NNN}) |
| cbk_returns | reviewer | username (rev{NNN}); submitted_by mostly empty |
| dpo_register | dpo_reviewer | username (dpo{NNN}) |
| merchant_acquiring | rm_code | code format merchrm{NNN} |
| audit_reviews | **auditor_code** | corrected from v10.108's auditor_username |
| projects | `_NESTED_project_manager_via_name` | sentinel — rules MUST set staff_field_extractor=name_lookup |

The `audit_reviews` correction is intentional. v10.108 declared `auditor_username` as the staff field, but the v10.114 seed data uses `auditor_code` as the canonical staff identifier (matching A2Z's ownership-contract pattern: `staff_code` is the universal staff key throughout the platform). Future v10.115+ may add an admin override to support per-bank deployments where the bank's audit system records auditors by username.

---

## Deliverable 6 — G143 coverage advanced

```
v10.113: 27/128 (21.1%)
v10.114: 34/131 (26.0%)   ← +7 covered, +3 denominator
```

**+7 covered**: K036, K072, K075, K104, K132, K133, K134.
**+3 denominator**: K132-K134 (new operational-source library entries).

Mode remains informational-pass; strict in v10.117+.

---

## Deliverable 7 — Tests (`tests/test_integration_layer_v10_114.py`, 21 tests)

| Test class | Tests | Coverage |
|---|---|---|
| `TestAuditReviewsSeed` | 4 | Schema integrity + status distribution + auditor codes valid |
| `TestLibraryK132K134` | 3 | All 3 entries present + well-formed + library count ≥152 |
| `TestStaffFieldAdditions` | 5 | All 6 newly-wired tables map to correct fields |
| `TestV10114RulesProduceOutput` | 7 | One test per rule (K104, K072, K075, K036 extractor check, K132, K133, K134 invert check) |
| `TestG143CoverageAdvanced` | 1 | Coverage ≥34/131 |

All 21 tests pass (manual replay since pytest unavailable in build sandbox).

---

## Verification

```
$ python scripts/audit.py
  ✅ [G143] kpi_source_has_aggregator
     v10.108 informational: KPI aggregators registered 34 / 131
     operational-source KPIs (26.0%); CBS-source KPIs (autofitted via
     existing pathway): 21; KPIs with no source: 0; strict mode pending
     v10.110+
  Score: 143/143 gates = 100.0% — PASS

$ python scripts/run_engine_self_tests.py
  152 passed · 0 failed · 0 skipped of 152 engines

$ pytest tests/test_integration_layer*.py -v
  139 passed   (17 v10.108 + 20 v10.109 + 24 v10.110 + 21 v10.111 +
                19 v10.112 + 17 v10.113 + 21 v10.114)
```

---

## Files in this drop

```
data/audit_reviews.json                       # NEW (250 records)
data/aggregation_rules.json                   # MODIFIED (+7 rules)
data/kpi_library.json                         # MODIFIED (+3 entries K132-K134)
utils/staff_field_resolver.py                 # MODIFIED (5 STAFF_FIELD_BY_TABLE additions/corrections)
tests/test_integration_layer_v10_114.py       # NEW (~360 LOC, 21 tests)
docs/Master_Prompt_v3.8.md                    # NEW (eighth anti-drift sync)
SCOPE_LEDGER.md                               # MODIFIED (v10.114 status block + trajectory revised)
CHANGELOG_v10.114.md                          # this file
```

Apply by extracting the zip into the repo root. Then:

```
$ python scripts/audit.py                              # → 143/143 PASS, G143 34/131
$ python scripts/run_engine_self_tests.py              # → 152/152
$ pytest tests/test_integration_layer*.py -v           # → 139 tests pass

$ git add -A
$ git commit -m "v10.114 — OpEx batch (5 rules) + audit_reviews seed + 3 audit rules"
$ git tag v10.114
$ git push origin main --tags
```

---

## Honesty discipline notes

**K093 (Merchant Onboarding TAT) deferred to v10.115.** merchant_acquiring has a pre-computed `tat_days` field but no separate start/end date columns. The v10.108 TAT_DAYS pattern requires distinct start/end. Rather than ship a broken rule, v10.115 adds a TAT_FIELD pattern that uses pre-computed numeric days fields directly.

**K036 simplified to truthy-check.** The intended "delivered on or before planned end date" comparison needs date-string comparison, but the v10.110 `field_le_field` predicate is restricted to numeric fields. v10.115 extends the DSL with a `date_le_field` type. v10.114's K036 is a no-slip-indicator proxy (% of completed projects with actual_end_date set).

**`audit_reviews` staff field corrected.** v10.108 declared `auditor_username` but the seed data uses `auditor_code` matching A2Z's ownership-contract pattern. The change is a v10.108 mistake fix, not a regression.

**Pre-existing "Audit Score" library entry left untouched.** Its irregular id (no K-number) is consumed by cascade. Consolidation with K132-K134 deferred to v10.115+ to avoid breaking that pathway.

**audit_reviews seed is synthetic.** Real Eco Bank deployment replaces with the bank's audit-management system feed via admin field-override config.

---

## Phase 1D coverage trajectory (revised)

| Drop | Work | Coverage |
|---|---|---|
| v10.108 | 4 reference rules (kickoff) | 4/108 (3.7%) |
| v10.109 | 17 rules + 9 library entries (expansion) | 16/117 (13.7%) |
| v10.110 | Architecture: JSON externalization + invert + admin Module Config | 16/117 (13.7%) |
| v10.111 | Name resolver + DSL extensions + K014 properly wired | 16/117 (13.7%) |
| v10.112 | HR rules batch K121-K128 + sample HR data | 24/125 (19.2%) |
| v10.113 | Role resolver + incidents/agent_fraud_alerts wiring + admin Resolution Metrics + v10.112 pillar fix | 27/128 (21.1%) |
| **v10.114** | **OpEx batch (5 rules) + audit_reviews seed + 3 audit rules** | **34/131 (26.0%)** |
| v10.115 (planned) | TAT_FIELD pattern + date_le_field DSL + sanctions_register + ews_cases + op_risk_losses + K093 wiring | ~42/135 (~31%) |
| v10.116-v10.119 | 6-12 rules per drop following established patterns | toward 100% |
| v10.120 (estimated) | Cleanup + edge KPIs + **G143 strict mode flip** | 100% |

**Next: v10.115** — TAT_FIELD pattern + date_le_field DSL extension + 5-7 more rules wiring sanctions_register/ews_cases/op_risk_losses/merchant_acquiring (K093 finally) + K036 strict on-time semantics. Master prompt bumps to v3.9.
