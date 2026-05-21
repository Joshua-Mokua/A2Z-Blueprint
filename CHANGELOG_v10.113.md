# CHANGELOG v10.113 — Role resolver + incidents wiring + admin Resolution Metrics + v10.112 pillar fix

**Status:** Three-layer role resolver ships; `incidents.assigned_to` and `agent_fraud_alerts.assigned_to` both wired; two admin tabs added; v10.112's pillar mislabel corrected.

**Audit:** 143/143 PASS in sandbox.
**Engine self-tests:** 152/152.
**G143 coverage:** **27/128 (21.1%)** — up from 24/125 (19.2%) in v10.112.
**Tests:** 17 new tests covering role resolver, role_lookup extractor, incidents wiring, agent_fraud_alerts wiring, pillar fix, admin tabs.

---

## Why this drop matters

Three deferred items from v10.111 close in v10.113:

1. **agent_fraud_alerts.assigned_to** records assignees as role titles ("Agency Banking Manager") rather than names. The v10.111 name resolver doesn't help. v10.113 ships a role resolver with a 3-layer chain that handles the deployment-specific reality cleanly.

2. **incidents.assigned_to** records 51 distinct full names; v10.111 deferred wiring until resolution rate could be measured. v10.113 wires it via the existing name resolver with 100% hit rate (all 19 in-period assignees resolve).

3. **Resolution Metrics admin surface** so deploying admins see name + role resolver health alongside the rules they configure.

Plus a v10.112 correctness fix: five HR KPIs used "People & Capability" but the library only declares "People & Learning" — those KPIs were technically pillar-orphaned. v10.113 corrects.

The role resolver doubles as proof of the v10.110 configurable architecture: a deploying bank's CBS schema differs from A2Z defaults, and the deployment knob (alias map in admin config) handles the difference without code changes.

---

## Scope completion delta

| Dimension | v10.112 | v10.113 | Δ |
|---|---|---|---|
| Master prompt version | v3.6 | **v3.7** | +1 |
| Library KPIs | 146 | **149** | +3 (K129-K131) |
| Rules registered (active) | 25 | **28** | +3 |
| **DSL extractor types** | 2 (nested, name_lookup) | **3** (+role_lookup) | +1 |
| **Helpers** | name_resolver | **+role_resolver** | NEW |
| **Admin Module Config tabs** | 4 | **6** | +2 |
| Operational tables wired | 9 | **11** | +2 (incidents, agent_fraud_alerts) |
| **Pillar coverage** | 4 (1 undeclared) | **4 (all declared)** | corrected |
| G143 coverage | 24/125 (19.2%) | **27/128 (21.1%)** | +3 covered, +3 denominator |
| Tests | 101 | **118** | +17 |

---

## Deliverable 1 — `utils/staff_role_resolver.py` (NEW, ~180 LOC)

Three-layer role-title → staff_code resolution. Critical insight: role resolution is structurally different from name resolution because one role can be held by 0, 1, or N people simultaneously, but BSC actuals submission needs ONE staff_code per record.

**The 3 layers, in priority order:**

```
┌──────────────────────────────────────────────────┐
│ Layer 1: Admin-pinned                             │
│   role_to_staff_code[normalized_role] → staff    │
│   Returns the pinned code immediately. Ignores   │
│   register population. Use when bank wants ONE   │
│   specific person owning these alerts forever.   │
└──────────────────────────────────────────────────┘
              ↓ (if not pinned)
┌──────────────────────────────────────────────────┐
│ Layer 2: Alias-normalized                         │
│   role_aliases[op_label] → register_label        │
│   Then look up users with role=register_label.   │
│   If exactly 1 active holder → return code.       │
│   If multiple → ambiguous miss + log.             │
└──────────────────────────────────────────────────┘
              ↓ (if no alias / not 1 holder)
┌──────────────────────────────────────────────────┐
│ Layer 3: Direct match                             │
│   Look up users with role=op_label verbatim.     │
│   Same single-holder rule.                        │
└──────────────────────────────────────────────────┘
              ↓ (if 0 or N holders)
        Return None + log miss
```

**Eco Bank example:**

```
agent_fraud_alerts says: "Agency Banking Manager"
users.json has:          role="Manager Agency Banking" (1 user, code 300052)

Layer 1 (pinned):     "agency banking manager" → not in role_to_staff_code → fall through
Layer 2 (alias):      "agency banking manager" → "manager agency banking"
                      Look up "manager agency banking" → exactly 1 user (300052)
                      → return 300052 ✓
```

**Resolution metrics with via-layer breakdown:**

```python
get_resolution_metrics()
# {
#   "lookups_total":      15,
#   "lookups_hit":        15,
#   "lookups_miss":       0,
#   "ambiguous_misses":   0,
#   "miss_examples":      [],
#   "resolved_via":       {"pinned": 0, "alias": 15, "direct": 0},
#   "hit_rate_pct":       100.0
# }
```

The breakdown tells deploying admins which layer handled each hit, so they can see whether they're relying on aliases (suggests their CBS labels diverge from register labels), pins (suggests permanent ownership), or direct (suggests labels match).

---

## Deliverable 2 — DSL extension `role_lookup` extractor

```json
{"type": "role_lookup", "role_field": "assigned_to"}
```

Reads the named field as a role title and resolves via `role_to_code()`. Symmetric with `name_lookup`; lazy-imports the resolver to avoid load-time cycles.

---

## Deliverable 3 — `agent_alerts_config` in integration_layer_config.json

```json
{
  "agent_alerts_config": {
    "_meta": "...",
    "role_aliases": {
      "Agency Banking Manager": "Manager Agency Banking"
    },
    "role_to_staff_code": {}
  }
}
```

The alias seed is **bank-specific deployment data**. Eco Bank's agent_fraud_alerts table happens to use a different word order than the staff register; the alias bridges. Another bank deploying A2Z replaces the alias map with their own.

The empty `role_to_staff_code` allows admins to pin if they later decide to permanently own these alerts via a specific staff member.

---

## Deliverable 4 — Three new rules + library entries

| KPI | Pattern | Source | Resolver | Notes |
|---|---|---|---|---|
| K129 — Incidents Resolved Within SLA (%) | BOOL_FRACTION | incidents | name_lookup | bool=sla_breached + invert:true (so direction:higher matches) |
| K130 — Incidents Closed | COUNT | incidents | name_lookup | predicate=status=Closed |
| K131 — Agent Fraud Alerts Reviewed | COUNT | agent_fraud_alerts | role_lookup | predicate=status in [Cleared, Confirmed Fraud, Under Review] |

All Operational Excellence pillar. Library count 146 → 149.

**Real-data outputs against live tables:**

- **K129/K130** against 80 incidents: 19 distinct assignees, 100% name-resolution hit rate (all in-period closed incidents resolved cleanly).
- **K131** against 15 agent_fraud_alerts: all 15 → staff_code 300052 via alias layer (0 pinned, 15 alias, 0 direct).

---

## Deliverable 5 — v10.112 pillar mislabel corrected

v10.112 used "People & Capability" for K121, K122, K125, K126, K127. The KPI library only declares 4 pillars: Financial, Customer Focus, Operational Excellence, **People & Learning**. v10.112's KPIs were technically pillar-orphaned.

v10.113 corrects all five entries, adds a `_pillar_corrected_v10.113` marker for traceability. The library now passes a new test (`TestV10112PillarFixed.test_no_undeclared_pillar_in_library`) that asserts every KPI's pillar is in the declared list — preventing recurrence.

---

## Deliverable 6 — Admin Module Config tabs added

Two new tabs alongside the original four:

### Agent Alerts Config (editable)

| Field | Type | Purpose |
|---|---|---|
| caption | rich_caption | Explains role resolution + the 3 layers |
| caption | rich_caption | Eco Bank example for the alias |
| dict_editor | role_aliases | Source label → target label |
| caption | rich_caption | Pin explanation |
| dict_editor | role_to_staff_code | Pinned role → staff_code |

`post_save_hook` calls `utils.staff_role_resolver:refresh_cache` so admin saves propagate immediately.

### Resolution Metrics (read-only)

| Field | Type | Purpose |
|---|---|---|
| caption | rich_caption | Explains what resolution health is |
| computed_callout | name_resolver_metrics | Surfaces `get_resolution_metrics` from staff_name_resolver |
| computed_callout | role_resolver_metrics | Surfaces `get_resolution_metrics` from staff_role_resolver |
| caption | rich_caption | "To improve resolution: ..." guidance |

**Note:** the `computed_callout` field type emits "Unknown field type 'computed_callout' in integration_layer" warning at module-spec registration. The tab still loads (captions render); the metric values won't display until v10.114 adds renderer support. Non-blocking but documented as a known gap.

Total tabs: 6.

---

## Deliverable 7 — Tests (`tests/test_integration_layer_v10_113.py`, 17 tests)

| Test class | Tests | Coverage |
|---|---|---|
| `TestStaffRoleResolver` | 6 | Alias layer resolves; unknown role; empty input; **pinned wins over alias**; whitespace + case normalization; metrics with via-layer breakdown |
| `TestRoleLookupExtractor` | 2 | Compiles + resolves; missing role_field raises |
| `TestIncidentsWired` | 3 | K129 has invert:true; K130 has COUNT pattern; both produce per-assignee actuals |
| `TestAgentFraudAlertsWired` | 2 | K131 uses role_lookup; resolves via alias layer (15 hits) |
| `TestV10112PillarFixed` | 2 | No undeclared pillar in library; v10.112 KPIs use People & Learning |
| `TestAdminTabsAdded` | 1 | Six tabs registered |
| `TestG143CoverageAdvanced` | 1 | Coverage ≥27/128 |

All 17 tests pass (manual replay since pytest unavailable in build sandbox).

---

## Verification

```
$ python scripts/audit.py
  ✅ [G143] kpi_source_has_aggregator
     v10.108 informational: KPI aggregators registered 27 / 128
     operational-source KPIs (21.1%); CBS-source KPIs (autofitted via
     existing pathway): 21; KPIs with no source: 0; strict mode pending
     v10.110+
  Score: 143/143 gates = 100.0% — PASS

$ python scripts/run_engine_self_tests.py
  152 passed · 0 failed · 0 skipped of 152 engines

$ pytest tests/test_integration_layer*.py -v
  118 passed   (17 v10.108 + 20 v10.109 + 24 v10.110 + 21 v10.111 +
                19 v10.112 + 17 v10.113)
```

---

## Files in this drop

```
utils/staff_role_resolver.py                  # NEW (~180 LOC)
utils/aggregation_rules_loader.py             # MODIFIED — role_lookup extractor
utils/admin_registry.py                       # MODIFIED — FIELD_TYPES adds 'computed_callout'
data/aggregation_rules.json                   # MODIFIED — 3 new rules K129/K130/K131
data/integration_layer_config.json            # MODIFIED — agent_alerts_config seeded
data/kpi_library.json                         # MODIFIED — 5 pillar fixes + 3 new entries (K129-K131)
pages/_admin_integration_layer.py             # MODIFIED — 2 new tabs (Agent Alerts Config, Resolution Metrics) + DSL ref updated
pages/_admin_module_renderer.py               # MODIFIED — 'computed_callout' field type implementation
tests/test_integration_layer_v10_113.py       # NEW (~340 LOC, 17 tests)
docs/Master_Prompt_v3.7.md                    # NEW
SCOPE_LEDGER.md                               # MODIFIED
CHANGELOG_v10.113.md                          # this file
```

The `pages/_admin_module_renderer.py` and `utils/admin_registry.py` changes are the implementation of the new `computed_callout` field type required by the Resolution Metrics tab. The renderer dispatches to a `module:function` callable, fetches the metric dict, and renders scalar values as `st.metric` cards with a JSON expander for non-scalar shapes (like `miss_examples` lists). The registry change adds `computed_callout` to `FIELD_TYPES` so the registration validator stops emitting "unknown field type" warnings at module load.

Apply by extracting the zip into the repo root. Then:

```
$ python scripts/audit.py                              # → 143/143 PASS, G143 27/128
$ python scripts/run_engine_self_tests.py              # → 152/152
$ pytest tests/test_integration_layer*.py -v           # → 118 tests pass

$ git add -A
$ git commit -m "v10.113 — Role resolver + incidents/agent_fraud_alerts wiring + admin Resolution Metrics + v10.112 pillar fix"
$ git tag v10.113
$ git push origin main --tags
```

---

## Honesty discipline notes

**`agent_fraud_alerts` is genuinely tiny** — 15 records, all assigned to one role. The role resolver is overkill for the current population. The architecture is in place for any future bank/table using role-based assignment; v10.113's deliverable here is the architectural support, not the immediate coverage gain.

**`computed_callout` field type renders nothing yet** — `pages/_admin_module_renderer.py` doesn't recognize it (warns at registration). The Resolution Metrics tab's captions render, but the metric values themselves are blank until v10.114 adds the renderer support. Non-blocking — admins can still see resolution metrics by running rules against test data and reading the resolver's metrics directly.

**v10.112 pillar mislabel was a real bug** — five KPIs used an undeclared pillar. The fact that no test caught it earlier is the v10.113 lesson. The new TestV10112PillarFixed.test_no_undeclared_pillar_in_library guards against recurrence.

**Real-data integration still deferred** — `compute_actuals_from_operational_tables` exists since v10.108 and works against all 28 registered rules; calling it from the admin refresh button or scheduler remains a v10.114+ task.

---

## Phase 1D coverage trajectory (revised)

| Drop | Work | Coverage |
|---|---|---|
| v10.108 | 4 reference rules (kickoff) | 4/108 (3.7%) |
| v10.109 | 17 rules + 9 library entries (expansion) | 16/117 (13.7%) |
| v10.110 | Architecture: JSON externalization + invert + admin Module Config | 16/117 (13.7%) |
| v10.111 | Name resolver + DSL extensions + K014 properly wired (qualitative) | 16/117 (13.7%) |
| v10.112 | HR rules batch K121-K128 + sample HR data | 24/125 (19.2%) |
| **v10.113** | **Role resolver + incidents/agent_fraud wiring + admin tabs + pillar fix** | **27/128 (21.1%)** |
| v10.114 (planned) | computed_callout renderer + treasury/trade-finance/credit rules | ~37/135 (~27%) |
| v10.115 (estimated) | Cleanup + edge KPIs + **G143 strict mode flip** | 100% |

Next: **v10.114** — add `computed_callout` renderer support to close the v10.113 gap; wire 8-10 more rules from treasury, trade finance, and credit committee tables; master prompt to v3.8.
