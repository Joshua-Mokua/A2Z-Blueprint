# A2Z MIS 360 — Consolidated Bundle v10.113 → v10.132

**Bundle date:** 2026-05-05
**Span:** 20 drops (v10.113 through v10.132)
**Cumulative state at:** v10.132
**Audit at v10.132:** 143/143 PASS · Engine self-tests 152/152 · G143 99/131 STRICT-READY (high)

---

## What this is

This single zip contains the cumulative state of all work shipped between v10.113 and v10.132 — 20 sequential drops covering the full Phase 1D Integration Layer build-out, Window 4 closure, Streamlit cockpit, PostgreSQL migration steps, and the rule-explain debug endpoint.

**Extract this once and your repo will be at the v10.132 state.** No need to apply the 20 individual zips one-by-one.

---

## How to apply

```bash
# From your repo root (where the existing utils/, scripts/, data/ etc. are)
unzip a2z_v10.113_to_v10.132_consolidated.zip

# Verify
python scripts/audit.py                   # → 143/143 PASS
python scripts/run_engine_self_tests.py   # → 152/152

# Commit + push
git add -A
git commit -m "Cumulative apply: v10.113 → v10.132 (20 drops, Phase 1D + Cockpit + PG migration + rule-explain)"
git push origin main

# Optional: tag each drop retroactively
for v in 113 114 115 116 117 118 119 120 121 122 123 124 125 126 127 128 129 130 131 132; do
  echo "Tagging v10.$v"
done
git tag v10.132   # at minimum, tag the final state
git push origin --tags
```

---

## What's inside

### Code changes

| Path | What changed |
|---|---|
| `utils/api.py` | Integration Layer endpoints (rules, actuals, coverage, resolution-metrics, run-period, **rule-explain v10.132**); JWT + role-gating (default ON since v10.126); React-readiness shape |
| `utils/db.py` | PG schemas for `sla_tickets` (v10.129), `debt_recovery` (v10.130), supplementary indexes for `loan_applications` (v10.131) |
| `utils/kpi_aggregation_rules.py` | 8 universal aggregation patterns (COUNT, SUM, PERCENTAGE, TAT_DAYS, RATIO, BOOL_FRACTION, TAT_FIELD, MEAN_FIELD); 13 DSL predicates |
| `utils/aggregation_rules_loader.py` | JSON loader + DSL compiler for rule definitions |
| `utils/staff_field_resolver.py` | 39 STAFF_FIELD entries; per-rule override pattern |
| `utils/actuals_engine.py` | `compute_actuals_from_operational_tables(period)`; v10.116 `_data_source` shim for PG-readiness |
| `scripts/audit.py` | G143 informational gate with strict-preview tier (50% / 75% / 100%) |
| `scripts/migrate_to_postgres.py` | FLAT_MIGRATIONS entries for sla_tickets / debt_recovery / loan_applications |
| `pages/99_integration_cockpit.py` | 6-tab Streamlit cockpit (Coverage / Rules / Preview / Resolution / Run / **Debug v10.132**) |

### Data files

100 active aggregation rules + 18 operational JSON files including 12 fresh CBS-mock seeds shipped during this window:

- `aggregation_rules.json` — 100 rules across 39 wired tables
- `kpi_library.json` — 152 KPIs
- `integration_layer_config.json` — `_data_source` toggle (default JSON, opt-in PG) + `_security` (role_gating_enabled=true)
- Fresh CBS-mock seeds: `sla_tickets.json`, `branch_log.json`, `hr.json`, `agency_banking.json`, `bsc_scores.json`, `clearing.json`, `nps.json`, `compliance.json`, `cims.json`, `partnerships.json`, `vendors.json`, `agent_fraud.json`, `collateral.json`, `360_feedback.json`, `audit_reviews.json`

### Documentation

- `SCOPE_LEDGER.md` — cumulative status ledger (last updated v10.132)
- `docs/Master_Prompt_v3.7.md` → `Master_Prompt_v3.26.md` — 20 anti-drift sync versions
- `docs/Phase_1D_Integration_Layer_Retro.md` — comprehensive sprint retro at v10.126
- `docs/Path_to_100_Bank_Level_Pipeline.md` — Phase 1E architecture proposal
- `docs/Standards_14_20_Verification_Report.{json,md}` — peer learning + amplification API verification
- `docs/PG_Migration_sla_tickets.md` — v10.129 deployment note
- `docs/PG_Migration_debt_recovery.md` — v10.130 deployment note
- `docs/PG_Migration_loan_applications.md` — v10.131 deployment note
- `docs/API_Rule_Explain.md` — v10.132 endpoint reference

### CHANGELOGs

20 per-drop CHANGELOG files (`CHANGELOG_v10.113.md` → `CHANGELOG_v10.132.md`) — each documents a single drop's deliverables, rationale, and verification commands.

### Tests

20 per-drop test files (`tests/test_integration_layer_v10_113.py` → `test_integration_layer_v10_132.py`) — 413 tests cumulative covering rule registration, pattern dispatch, DSL predicate logic, audit gates, role-gating, PG migration plumbing, cockpit + endpoint integration.

---

## What this bundle does NOT include

This is a snapshot at v10.132. **It does not include v10.133 Phase 0 Registry Hygiene** — that's a separate zip (`a2z_v10.133_phase_0_qa_spec_registry_hygiene.zip`) that should be applied AFTER this bundle.

The recommended apply sequence:

```
1. unzip a2z_v10.113_to_v10.132_consolidated.zip   # this bundle
2. unzip a2z_v10.133_phase_0_qa_spec_registry_hygiene.zip   # Phase 0 of QA spec closure
3. python scripts/audit.py                          # → 144/144 PASS
4. git add -A && git commit -m "v10.113 → v10.133"
5. git tag v10.133 && git push --tags
```

---

## Headline trajectory across the window

| Drop | Coverage | Headline |
|---|---|---|
| v10.113 | 27/128 (21%) | Role resolver + incidents/agent_fraud_alerts |
| v10.115 | 40/131 (30%) | TAT_FIELD pattern + DSL extension + React-readiness API |
| v10.116 | 45/131 (34%) | PG-readiness shim + POST run-period endpoint |
| v10.117 | 51/131 (39%) | Strict-mode preview + role-gating draft |
| v10.119 | 66/131 (50%) | **STRICT-READY (preview) — 50% crossing** |
| v10.122 | 78/131 (60%) | Pool-wall break with 2 fresh seeds |
| v10.125 | 99/131 (76%) | **STRICT-READY (high) — 75% crossing** |
| v10.126 | 99/131 | Phase 1D close-out (role-gating hard-flip + retro) |
| v10.127 | 99/131 | Window 4 close (standards #14-#20 verified COMPLETE) |
| v10.128 | 99/131 | Streamlit cockpit (5 tabs) |
| v10.129 | 99/131 | PG migration step 1 (sla_tickets) |
| v10.130 | 99/131 | PG migration step 2 (debt_recovery) |
| v10.131 | 99/131 | PG migration step 3 (loan_applications) |
| v10.132 | 99/131 | Rule-explain endpoint + cockpit Debug tab |

**Window summary**: Phase 1D Integration Layer rule-density work closed at 99/131 = 75.6% STRICT-READY (high). 100 production rules across 39 tables. 5 → 6 stable JWT-protected API endpoints. 6-tab operator cockpit. 3 of 39 wired tables now PG-eligible.

---

## After applying

Run the audit and engine self-tests to confirm:

```bash
python scripts/audit.py
# Expected: Score: 143/143 gates = 100.0% — PASS

python scripts/run_engine_self_tests.py
# Expected: 152 passed · 0 failed · 0 skipped of 152 engines
```

Then proceed to v10.133 Phase 0 Registry Hygiene (separate zip).
