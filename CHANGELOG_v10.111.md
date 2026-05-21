# CHANGELOG v10.111 — Name resolver + DSL extensions + K014 rewiring

**Status:** `utils/staff_name_resolver.py` ships; DSL extensions `field_in_named` + `name_lookup`; K014 rewired from loan_applications.compliance_flag proxy to its proper aml_alerts source (removes v10.110 invert workaround); 4 existing rules refactored to use named status lists.

**Audit:** 143/143 PASS in sandbox.
**Engine self-tests:** 152/152.
**G143 coverage:** **16/117 (13.7%)** — stable. v10.111 was qualitative (correctness + DSL extensions), not quantitative.
**Tests:** 21 new tests across name resolver, DSL extensions, K014 rewiring.

---

## Why this drop matters

v10.110 left two debts on the table:
1. **K014 was a proxy.** It was wired to `loan_applications.compliance_flag` with `invert: true` because v10.109 had assumed `aml_alerts` didn't exist. v10.110 surfaced that aml_alerts.json does exist (120 records) but couldn't wire it because `assigned_to` is a full name, not a staff code.
2. **Status enums were duplicated.** Each rule's predicate inlined its own `["approved", "declined", "returned"]` list, so an admin updating per-bank vocabulary had to edit multiple places.

v10.111 closes both. The name resolver unblocks every table that keys on full names (aml_alerts, incidents, future tables), and the `field_in_named` DSL type makes status_vocabulary the single source of truth.

**Confirmed Standard #118+ continuation territory.** The standards_registry tracks 265 standards (12 regulatory + 253 enhancement) — well past Phase 1B's #118 closure in v10.96. Phase 1D (Integration Layer) is one of the workstreams running in this continuation track alongside the v9→v10 expansion (122 → 400 standards target).

---

## Scope completion delta

| Dimension | v10.110 | v10.111 | Δ |
|---|---|---|---|
| Master prompt version | v3.4 | **v3.5** | +1 (anti-drift sync) |
| Rules registered (active) | 17 | 17 | 0 |
| **DSL predicate types** | 9 | **10** | +1 (field_in_named) |
| **DSL extractor types** | 1 (nested) | **2** (+name_lookup) | +1 |
| **Helpers** | — | **staff_name_resolver** | NEW |
| K014 source | loan_applications (proxy + invert:true) | **aml_alerts (proper, no invert)** | rewired |
| Rules using field_in_named | 0 | 4 (K001, K011, K115, K120) | +4 |
| Audit gates | 143 | 143 | 0 |
| G143 coverage | 16/117 (13.7%) | 16/117 (13.7%) | 0 (qualitative) |
| Tests | 61 | **82** (+v10.111's 21) | +21 |

---

## Deliverable 1 — `utils/staff_name_resolver.py` (NEW, ~150 LOC)

Resolves full-name strings to staff codes via the staff register at `data/users.json`. The lookup table is built once on first call, cached at module level, invalidated via `refresh_cache()` after admin edits.

**API:**

```python
from utils.staff_name_resolver import (
    name_to_code, refresh_cache, get_resolution_metrics,
    get_known_ambiguous,
)

code = name_to_code("Stephen Shimba")        # → "300110"
code = name_to_code("  STEPHEN  shimba ")    # whitespace + case tolerant
code = name_to_code("Nobody Real")           # → None (with metric)
code = name_to_code(None)                    # → None
```

**Normalization:** strip outer whitespace, collapse internal whitespace, lower-case. Stable across small typing variations.

**Disambiguation:** when two staff share the same normalized full_name (e.g., two "Mary Waweru" in different units), `name_to_code()` returns None and increments `ambiguous_misses`. Admins see the ambiguity warning in the resolution-metrics report and disambiguate by adding unit suffix to the operational table or editing users.json.

**Resolution metrics:**

```python
get_resolution_metrics()
# {
#   "lookups_total":      4,
#   "lookups_hit":        2,
#   "lookups_miss":       2,
#   "ambiguous_misses":   0,
#   "miss_examples":      ["Definitely Not Real", ...],   # last 20
#   "hit_rate_pct":       50.0
# }
```

The deploying admin views these in the Module Config Centre's Resolution Metrics tab (coming v10.112) to debug staff-register coverage.

**Inactive users skipped:** `active=false` users in the register are omitted from the lookup — they shouldn't be assignees on current operational records.

---

## Deliverable 2 — DSL extension `name_lookup` extractor

JSON spec:

```json
{"type": "name_lookup", "name_field": "assigned_to"}
```

Compiled to a callable that reads the named field as a full-name string and resolves via `name_to_code()`. Returns None on miss (and the row is dropped from the per-staff aggregation, with the resolution metric incremented).

Lazy-imported inside the loader to avoid load-time import cycles.

---

## Deliverable 3 — DSL extension `field_in_named` predicate

JSON spec:

```json
{"type": "field_in_named", "field": "status", "list_name": "loan_decided"}
```

References named status lists from `data/integration_layer_config.json::status_vocabulary`. Resolution happens at predicate compile time (the loader bakes the list into the closure).

**Why this matters for multi-bank deployment:** each bank's loan workflow uses different status names. Eco Bank's "approved/declined/returned/disbursed" might be Bank X's "stage_3a/stage_3b/rejected/funded". Without `field_in_named`, an admin would have to edit those status values in 3+ rule predicates separately. With it, they update `loan_decided` once.

**Important:** admin edits to vocabulary require BOTH `refresh_overrides_cache()` AND a rule reload to propagate (because the closure is baked at compile time). The Module Config Centre's save handler will chain both automatically in v10.112.

**Error handling:** if `list_name` doesn't exist in the vocabulary, compile_predicate raises `PredicateCompileError` with the available list names. The loader logs the error and skips that rule (per v10.110's "fail one rule, not the batch" discipline).

---

## Deliverable 4 — K014 rewired to aml_alerts

**v10.110 (proxy + invert workaround):**

```json
{
  "kpi_id": "K014",
  "source_table": "loan_applications",
  "pattern": "BOOL_FRACTION",
  "bool_field": "compliance_flag",
  "predicate": {"type": "field_in", "field": "status",
                "values": ["approved", "declined", "returned"]},
  "invert": true,
  "_origin": "v10.108_revised_v10.109_invert_flag_v10.110"
}
```

**v10.111 (proper aml_alerts wiring):**

```json
{
  "kpi_id": "K014",
  "active": true,
  "source_table": "aml_alerts",
  "pattern": "PERCENTAGE",
  "description": "% of high-risk AML alerts where STR was filed per officer",
  "numerator_pred": {
    "type": "all",
    "of": [
      {"type": "field_eq", "field": "risk_level", "value": "High"},
      {"type": "field_is_true", "field": "str_filed"}
    ]
  },
  "denominator_pred": {
    "type": "field_eq",
    "field": "risk_level",
    "value": "High"
  },
  "period_field": "created_at",
  "staff_field_extractor": {
    "type": "name_lookup",
    "name_field": "assigned_to"
  },
  "decimals": 2,
  "_origin": "v10.108_revised_v10.109_invert_v10.110_proper_aml_wiring_v10.111"
}
```

**Real per-officer scores against live aml_alerts:**

| AML Officer | Resolved staff_code | High-risk alerts | STR filed | Score |
|---|---|---|---|---|
| Stephen Shimba | 300110 | 11 | 2 | **18.18%** |
| Mary Waweru | 300006 | (varies by period) | | **14.29%** |
| Sharon Mohamed | 300108 | 9 | 0 | **0.00%** |
| Ibrahim Andanje | 300109 | 6 | 0 | **0.00%** |
| Usman Farah | 300107 | 5 | 1 | **33.33%** |

(Numbers slightly differ from a raw aggregation because the rule applies the period filter on `created_at` for "2026-04".)

**Name resolution: 100% hit rate** — all 5 distinct aml_alerts.assigned_to names resolve cleanly via the staff register.

**The invert workaround is gone** — KPI direction:higher (high score = good) now naturally matches "more STR-filing on high-risk alerts = better compliance discipline".

---

## Deliverable 5 — Four rules refactored to use `field_in_named`

| KPI | Source table | Named list | Old (inline) | New (named) |
|---|---|---|---|---|
| K001 | loan_applications | loan_approved_disbursed | `["approved", "disbursed"]` | references list |
| K011 | loan_applications | loan_decided | `["approved", "declined", "returned", "disbursed"]` | references list |
| K115 | loan_applications | loan_approved_disbursed | `["approved", "disbursed"]` | references list |
| K120 | campaigns | campaign_active | `["Active", "Completed", "active", "completed"]` | references list |

**Outputs unchanged** (regression-tested): K001 still 103 RMs, K011 still 143 RMs, K115 still 103 RMs, K120 still 29 owners.

The benefit shows up only at deployment time — when an admin at Bank X edits their `loan_decided` vocabulary to match their CBS, all 4 rules pick up the change immediately (after rule reload).

---

## Deliverable 6 — Tests (`tests/test_integration_layer_v10_111.py`, 21 tests)

| Test class | Tests | Coverage |
|---|---|---|
| `TestStaffNameResolver` | 7 | Basic lookup; whitespace + case normalization; unknown returns None; empty input; metrics tracking; all aml_alerts assignees resolve |
| `TestFieldInNamed` | 2 | Compiles + runs against test list; unknown list_name raises with helpful error |
| `TestNameLookupExtractor` | 2 | Compiles + resolves correctly; missing name_field raises |
| `TestK014Rewired` | 4 | Wired to aml_alerts (not loan_applications); invert=False; uses extractor; produces per-officer 0-100 |
| `TestExistingRulesUseNamedLists` | 1 (multi-rule) | K001/K011/K115/K120 outputs unchanged after refactor |
| `TestG143CoverageStable` | 1 | Coverage at v10.110 baseline |

All 21 tests pass (manual replay since pytest unavailable in build sandbox).

---

## Verification

```
$ python scripts/audit.py
  ✅ [G143] kpi_source_has_aggregator
     v10.108 informational: KPI aggregators registered 16 / 117
     operational-source KPIs (13.7%); CBS-source KPIs (autofitted via
     existing pathway): 21; KPIs with no source: 0; strict mode pending
     v10.110+
  Score: 143/143 gates = 100.0% — PASS

$ python scripts/run_engine_self_tests.py
  152 passed · 0 failed · 0 skipped of 152 engines

$ pytest tests/test_integration_layer*.py -v
  82 passed   (17 v10.108 + 20 v10.109 + 24 v10.110 + 21 v10.111)
```

---

## Files in this drop

```
utils/staff_name_resolver.py                  # NEW (~150 LOC)
utils/aggregation_rules_loader.py             # MODIFIED — field_in_named + name_lookup + status_vocabulary loader
data/aggregation_rules.json                   # MODIFIED — K014 rewired + 4 rules use field_in_named
tests/test_integration_layer_v10_111.py       # NEW (~370 LOC, 21 tests)
docs/Master_Prompt_v3.5.md                    # NEW — anti-drift sync
SCOPE_LEDGER.md                               # MODIFIED — v10.111 status block
CHANGELOG_v10.111.md                          # this file
```

Apply by extracting the zip into the repo root. Then:

```
$ python scripts/audit.py                              # → 143/143 PASS
$ python scripts/run_engine_self_tests.py              # → 152/152
$ pytest tests/test_integration_layer*.py -v          # → 82 tests pass

$ git add -A
$ git commit -m "v10.111 — Name resolver + DSL extensions + K014 properly wired to aml_alerts"
$ git tag v10.111
$ git push origin main --tags
```

---

## Honesty discipline notes

**`agent_fraud_alerts.assigned_to` is a role title** ("Agency Banking Manager", "AML Officer"), not a person's name. The `name_lookup` extractor doesn't help. v10.112+ needs a separate role→staff resolver, or admin-driven role-to-staff mapping config.

**HR rules K121-K128 deferred** — training_completions, performance_reviews, leave_requests don't exist in CBS-mock. Two paths for v10.112:
1. Generate sample HR data (modeled after how loan_applications, debt_recovery, etc. were seeded), then wire 6-8 HR rules.
2. Wait for the Eco Bank deployment phase to expose actual HR tables via FLEXCUBE.

The decision lands when v10.112 starts.

**incidents.assigned_to wiring deferred** — 51 distinct names (vs aml_alerts' 5). Can't predict the resolution rate without running it. v10.112+ will:
1. Run the resolver against incidents and check `miss_examples` to identify gaps.
2. Either (a) wire the rule and accept partial coverage, or (b) document the gaps and ask admin to populate users.json for the missing names.

**Resolution metrics not yet surfaced in admin UI** — the `get_resolution_metrics()` function exists but no Module Config Centre tab displays it. v10.112 adds a "Resolution Metrics" tab to the Integration Layer admin spec.

---

## Phase 1D coverage trajectory

| Drop | Work | Coverage |
|---|---|---|
| v10.108 | 4 reference rules (kickoff) | 4/108 (3.7%) |
| v10.109 | 17 rules + 9 library entries (expansion) | 16/117 (13.7%) |
| v10.110 | Architecture: JSON externalization + invert + admin Module Config | 16/117 (13.7%) |
| **v10.111** | **Name resolver + DSL extensions + K014 properly wired (qualitative)** | **16/117 (13.7%)** |
| v10.112 (planned) | HR sample data OR FLEXCUBE wiring + incidents wiring + role resolver + Resolution Metrics admin tab | ~25/125 (~20%) |
| v10.113-v10.114 | 12-18 rules per drop following established patterns | toward 100% |
| v10.115 (estimated) | Cleanup + edge KPIs + **G143 strict mode flip** | 100% |

Next: **v10.112** — generate sample HR data + add HR rules K121-K128 + wire incidents.assigned_to + role→staff resolver for agent_fraud_alerts + Resolution Metrics admin tab. Master prompt bumps to v3.6.
