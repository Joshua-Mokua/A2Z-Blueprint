# Changelog — v10.320 Data hygiene cleanup (B-018 + B-019)

**Date:** 2026-05-11
**Phase:** 4 (seventh arc — score correctness for demo)
**Audit:** 211/211 gates PASS = 100.0%
**Tests:** 475/475 passing across 27 integration suites
**G162 Rebase:** none — 16 consecutive zero-drift batches

---

## What v10.320 fixed

After v10.319 surfaced **B-018 (weights ≠ 100%) and B-019 (bank
target misconfigurations)**, this batch closes the demo-critical
parts cleanly:

### 1. `Staff Productivity` bank target: 3.0 → 85.0 (B-019 fix)

This was the root cause of Teller 300230's incorrect 3.4/5.0 score
in v10.319. The bank target was 3.0 (looked like a 1-5 score target
got stored in a 0-100 KPI's slot), so achievement_pct came out to
59.94 / 3.0 = 1998% → score 5.0 (artificially inflated).

The fix value 85.0 matches v10.317's generator config target, so
the math is now self-consistent: actuals are generated against
target 85, scoring engine evaluates against target 85.

**Result**: Teller 300230 final score now **2.4/5.0** — accurately
reflects a below-target performer (matches the v10.317 generator's
`below_target` band assignment for this staff).

### 2. `Audit Score` description corrected (data hygiene)

The kpi_library description for Audit Score said "1-5 scale" but
the actuals data (and bank target) are on 0-100. Fixed the
description text so future audits don't false-positive on this
KPI. No data semantics changed.

### 3. KPI alias map auto-built from `kpi.code` field (proper B-010 fix)

Previously the alias map was 18 hardcoded entries. v10.320 auto-
derives it from the `code` field present on every KPI in the
library — every `code → id` mismatch becomes an alias automatically.
This means **B-010 stays solved system-wide as the KPI library
grows** — no manual additions needed when new KPIs are added with
both `id` and `code` fields.

The auto-build picks up 19 aliases. Six manual extras handle
legacy abbreviations that don't appear in any KPI's code field
(STAFF_PROD vs STAFF_PRODUCTIVITY, DEP_GROWTH, FEES_COMM, etc.).

### 4. Weight normalization exposed on `validate_role_weights`

`validate_role_weights(role)` now returns:
- `normalized_weights`: dict of `kpi_id → normalised_weight`
  (sum to exactly 1.0)
- `normalization_factor`: 1.0 / raw_total_weight (multiplier
  callers can apply to raw weights to get the 100% sum)

The actual `compute_staff_scorecard` math has always been correct
(uses weight-of-scored-KPIs as denominator). The new fields make
the normalization explicit and inspectable for UI / debugging.

### 5. New `scripts/audit_data_hygiene.py`

Comprehensive hygiene auditor. Reports on:
- **Weight sums per role** (227 roles): 1 balanced, 208 under-
  weighted, 13 overweighted, 5 empty
- **Bank target sanity** (45 entries): now 0 HIGH-severity
  findings (post-Staff Productivity fix)

Uses **actuals cross-check** for bank target sanity — compares
against observed value ranges in `bsc_actuals_*.json` rather than
relying on description heuristics alone. This eliminated 2 false
positives from v10.319's heuristic-only audit (PAR=5% and CX
Score=4.0 on 1-5 scale are both correct).

Run anytime:
```bash
python scripts/audit_data_hygiene.py             # full report
python scripts/audit_data_hygiene.py --role Teller
python scripts/audit_data_hygiene.py --bank-targets-only
```

## Configurable vs hardcoded — Rule of Configurability honoured

**CONFIGURABLE**:
- All KPI definitions and weights (`kpi_library.json`)
- Bank targets per period (`bank_targets.json`)
- Per-staff cascaded targets (`target_cascade.json`)
- Manual alias extras (in `bsc_score_computation.py`)

**HARDCODED** (system invariants):
- Auto-alias derivation rule (kpi.code → kpi.id mapping)
- 5pp tolerance for weight validation `valid` flag
- Bank target cross-check heuristic (actuals max > 20 + target < 10 = mismatch)
- 1-5 scoring scale thresholds

## What this batch unlocks for the demo

- **Teller scorecards now compute correctly.** Final scores reflect
  actual performance, not data artifacts. ✓
- **No HIGH-severity bank target issues** when cross-checked against
  shipped actuals. ✓
- **Alias resolution is self-maintaining.** New KPIs added to the
  library with `id` + `code` fields get aliased automatically. ✓
- **Hygiene visibility is permanent.** Run the audit script anytime
  to see current state. ✓
- **Weight situation is documented honestly.** 222 of 227 roles
  have weights that don't sum to 100%. The math still works (we
  normalize at scoring time). Individual role rebalancing is a
  separate exercise per role, logged as B-018 follow-ups but not
  blocking the demo.

## What was NOT fixed (and why)

| Item | Status | Why deferred |
|------|--------|--------------|
| Rebalance kpi_library weights so each role sums to 100% | Open (B-018 follow-up) | 227 roles × specific weight choices = substantial review work. The runtime normalization in scoring makes this **informational**, not blocking. Each role can be rebalanced individually as needed. |
| Add missing KPI definitions (NEW_ACCOUNTS, NPL_RATIO, COMPLIANCE, NIM, ROE, etc.) | Open (B-020) | These are real KPIs without entries in kpi_library.json. The scoring engine handles their absence gracefully (KPI gets skipped, weight excluded from denominator). Adding them requires domain decisions on weight + direction + scale. |
| Audit `Disbursements Corporate Loans` target = 12B in KES M (= 12 trillion KES?) | Open (latent) | No actuals exist for this KPI yet, so it doesn't surface in any current scorecard. Will need fixing if/when Corporate Banking activity is generated. |
| 246 stale-role references in source code | Open (B-015, B-016) | Mostly in fallback paths (DEFAULT_ORG_CONFIG, DEFAULT_ROLE_KPIS) that don't actively execute. Cleanup batch needed but not demo-blocking. |
| 199 direct file I/O in pages/ | Open (B-017) | All current usages work. Migrating to `utils.db` is consistency improvement, not a correctness issue. |

## Real findings during this batch

1. **`kpi.code` is the proper B-010 alias source.** The schema
   already had a `code` field on every KPI that mirrors the
   UPPER_SNAKE_CASE convention. v10.319's 18 hardcoded aliases
   were duplicating this. v10.320 derives the alias map from the
   `code` field at module load time — proper system-wide solution.

2. **Heuristic audits produce false positives.** v10.319's bank
   target audit flagged PAR=5% as suspicious because 5 < 10. But
   5% is a perfectly reasonable PAR target. The actuals cross-
   check approach in v10.320 only flags when there's clear evidence
   (observed range conflicts with target scale).

3. **Joshua's intuition was correct.** The cascade page bug was
   indeed the tip of a wider pattern. The follow-up audit found:
   - Multiple pages using stale role names (now mostly inactive fallback paths)
   - Many roles with weight drift (informational; math still works)
   - 1 active data bug breaking Teller scorecards (Staff Productivity target — now fixed)

4. **The original BSC design IS in the system.** What got lost
   was the consistent use — newer modules drifted from the
   canonical scoring path. v10.319's `bsc_score_computation.py`
   re-establishes the canonical path; v10.320 ensures the data
   it consumes is clean enough to produce correct scores for the
   demo.

5. **G162 holds. 16 consecutive zero-drift batches.**

## Platform state

| Metric | v10.319 → v10.320 |
|--------|-------------------|
| Audit gates | 210 → **211** |
| Integration test suites | 26 → **27** |
| Tests passing | 461 → **475** |
| HIGH-severity bank target issues | 1 (Staff Productivity) → **0** |
| Critical aliases auto-derived | 0 → **19** (from kpi.code) |
| Teller 300230 final score | 3.4 (broken) → **2.4 (correct)** |
| G162 baseline | 4022 (16 consecutive zero-drift batches) |

## Backlog status

| ID | Status | Notes |
|----|--------|-------|
| B-009 | Open | IFRS9 product field |
| B-010 | **Partially closed (auto-aliasing)** | KPI ID convention — auto-resolved via kpi.code field. Remaining 26 unresolved refs (ACTIVE_ACCTS, CIR, COMPLIANCE, etc.) need actual KPI definitions added (B-020). |
| B-011 | Open | Dept naming |
| B-013 | Open | Manager rollup engine |
| B-014 | Open | get_org_config Streamlit dep |
| B-015 | Open | core.py stale-role fallback constants (dead code) |
| B-016 | Open | cascade page LEVEL_ORDER/ROLE_MAP fallback |
| B-017 | Open | Direct I/O in pages |
| B-018 | **Reframed (informational)** | Weight sums per role. 13 overweighted at 1.61, 208 underweighted. Math correct via runtime normalization. Individual rebalance work per role. |
| **B-019** | **✅ Closed** | Staff Productivity bank target fixed. Audit Score description corrected. |
| B-020 | Open | 26 role_kpis refs without KPI definitions |

## Next: v10.321 — Manager rollup engine (B-013)

Now that scoring is clean for the leaf level (Tellers), the rollup
engine can produce manager scores correctly. Design per Joshua's
v10.318 reminder:

- For FIXED KPIs (bank-level, like CX Score): manager scores on
  their own actual against the bank target, just like any staff
- For CASCADED KPIs: manager's actual = aggregate of team's
  actuals (or measured at manager level), target = their own
  cascaded target

After v10.321:
- Branch Operations Supervisor's BSC score = computed from their
  own KPI set (with actuals aggregated from their Tellers for
  cascaded KPIs)
- Branch Operations Manager's score = same pattern, one level up
- ...all the way to MD

Estimated 3-4 hours. Proceed?
