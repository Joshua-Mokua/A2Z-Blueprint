# CHANGELOG v10.60 → v10.62 — finance arc batches 2/10, 3/10, 4/10

**Status:** finance arc progresses to 4/10 standards active.
**Audit:** 134/134 PASS · **G128:** STABLE (327 modules · 830 imports · 3 HARD baseline)
**Active standards:** 128 → **131** / 260 (+3 ENH-250/251/252)
**Scenario library:** 90 → **102** (+12: 4 ICM + 4 GCS + 4 CBK)
**Total self-tests across stack:** 224/224 PASS

---

## v10.60 — ENH-250 Intercompany Matching & Elimination

### What it does

Pairs IC entries across legal entities and recommends elimination journals at consolidation. Where ENH-249's `detect_intercompany_pending` only knows one entity's books and flags unbalanced refs within them, ENH-250 takes a multi-entity view: GLEntries from parent + all subs flow in, the engine pairs by `(reference, period)` where `entity_id` and `counterparty_entity_id` are mirror images and Dr/Cr sides are opposite.

### Module

`utils/intercompany_matching.py` (~625 lines · 18 self-tests · all PASS first run).

### Architecture

**4 MatchStatus enums:**
- `EXACT` — within tolerance (default KES 100 absolute, configurable)
- `AMOUNT_MISMATCH` — same ref + opposite sides + variance > tolerance
- `UNMATCHED` — solo entry with no offsetting counter
- `MULTI_LEG_CHAIN` — entries sharing `chain_id` reported as a unit with net signed amount

**5 EliminationType enums** drive elimination account routing: `REVENUE_EXPENSE`, `RECEIVABLE_PAYABLE`, `DIVIDEND`, `LOAN`, `OTHER`. Default placeholder accounts (`IC-REC`, `IC-PAY`, `IC-DIV-RCVD`, `IC-DIV-PAID`, `IC-LOAN-PAY`, `IC-LOAN-REC`) — production deployments map these from CoA + entity policy.

**Pairing logic:** Two entries form an IC pair candidate iff `a.entity_id == b.counterparty_entity_id AND b.entity_id == a.counterparty_entity_id AND a.is_dr != b.is_dr`. Same-side pairs (both Dr or both Cr) explicitly rejected. Same-reference pairs across non-mirror entities (e.g., A→B and A→C) explicitly rejected.

### Rule 1 / Rule 7

- 6 frozen dataclasses including `IcEntry` with construction-time validation (self-counterparty rejected, Dr-XOR-Cr enforced, reference non-empty, amounts ≥ 0).
- Every `IcMatch` surfaces `match_id + status + severity + period + reference + entity_a + entity_b + amounts + variance_kes + related_entry_ids + recommended_elimination + framework_refs`.
- Engine never posts eliminations, never decides which side is correct in a mismatch (returns `recommended_elimination=None` for `AMOUNT_MISMATCH` so operators reconcile first).
- `_test_engine_does_not_mutate_inputs` verifies frozen contract.

### Scenarios

- **ICM-01 EXACT match** — paired entries, LOW severity, elimination recommendation populated with amount 100k.
- **ICM-02 AMOUNT_MISMATCH** — variance 25k exceeds default tolerance → HIGH severity, NO elimination (operator reconciles first).
- **ICM-03 UNMATCHED solo** — solo Dr 250k vs SUBC, no counter → HIGH severity, counterparty surfaced for triage.
- **ICM-04 match_all orchestrator** — mixed input (paired + solo + 2-leg chain) → 3 status types + 1 elimination recommendation + framework refs cite ENH-250 + Rule 7.

15/15 assertions all PASS.

### Honest scope notes

1. **No fuzzy reference resolution.** Engine pairs on exact reference match. Real-world IC entries sometimes have slight reference variations (e.g., `IC-INV-001` on parent vs `IC-INV-001-A` on sub). Pre-processing to canonicalize references is the caller's responsibility.
2. **No multi-currency in this engine.** Amounts assumed already in same currency. ENH-251 handles FX translation at the consolidation step.
3. **Elimination accounts are placeholders.** Production CoA mapping is operator policy, not engine logic.
4. **Chain detection requires `chain_id`.** No automatic chain discovery from transitive IC relationships.

---

## v10.61 — ENH-251 Group Consolidation Engine (operational TB)

### What it does

Operational TB consolidation per IFRS 10 + IAS 21. Distinct from Standard #100 (`utils/group_consolidation.py` — policy-side method selection by ownership %, classification rules); ENH-251 is the operational side (`utils/consolidated_tb_engine.py` — taking individual entity trial balances, applying ENH-250 eliminations, FX-translating, producing consolidated TB ready for ENH-255 statement generator).

### Module

`utils/consolidated_tb_engine.py` (~625 lines · 16 self-tests · all PASS first run).

### Four-step pipeline

1. **AGGREGATION** — line-by-line sum after FX translation
2. **ELIMINATIONS** — apply operator-approved subset from ENH-250 `IcMatchReport` via `debit_account`/`credit_account` routing
3. **NCI ALLOCATION** — for each non-100%-owned subsidiary, post-elimination contribution split between parent share and non-controlling interest at `(1 - ownership_pct)`
4. **FX TRANSLATION** per IAS 21 — `CLOSING` rate for B/S items (ASSET/LIABILITY/EQUITY), `AVERAGE` rate for P&L items (REVENUE/EXPENSE); translation differential accumulates as `cumulative_translation_adjustment_kes` for OCI booking

### Rule 1 / Rule 7

- 8 frozen dataclasses including `EntityProfile` (ownership in [0,1] + parent must be 100% owned), `TrialBalanceLine`, `FxRate` (rate > 0).
- Every `ConsolidatedLine` surfaces account_code + per-entity FX-detailed contributions + pre/post elimination + NCI/parent split + framework refs.
- Engine never posts to source GLs, never goes to FX market, never auto-selects eliminations.

### Scenarios

- **GCS-01 simple aggregation** — PARENT 5m + SUBA 2m (KES) → consolidated Dr 7m, both contributions surfaced.
- **GCS-02 NCI allocation** — 70%-owned sub with 10m equity → NCI 3m + parent 7m; invariant `NCI + parent == post_elimination_total` verified.
- **GCS-03 IAS 21 FX translation** — USD asset @ CLOSING 130 = 13m KES; USD revenue @ AVERAGE 128 = 6.4m; rate types surfaced explicitly per Rule 1.
- **GCS-04 elimination application** — IC-REC/IC-PAY pair fully eliminated, count = 1, framework refs cite ENH-251 + Rule 7.

15/15 assertions all PASS.

### Honest scope notes

1. **NCI on equity is an approximation.** The engine scales the post-elim balance by `(1 - ownership_pct)`. Full IFRS 10 NCI accounting includes goodwill allocation, fair-value adjustments at acquisition, and the share of post-acquisition retained earnings — those belong to a true acquisition-accounting engine, out of scope here.
2. **Translation differential is informational.** The engine tracks `cumulative_translation_adjustment_kes` as a single number; it doesn't post the OCI entry. ENH-255 statement generator will route this to the cumulative translation reserve.
3. **FX rates are caller-supplied.** Engine doesn't go to market. Per IAS 21 the closing/average distinction is enforced by `_rate_type_for_account` based on account type.
4. **No mid-period acquisitions.** Engine assumes ownership is stable for the entire period. Step acquisitions/disposals would need date-aware ownership accounting.

---

## v10.62 — ENH-252 CBK Regulatory Reporting Automation (Enhanced)

### What it does

Diagnostic CBK banking-specific returns generator extending ENH-248 framework. 5 return families covering CBK Prudential Guidelines.

### Module

`utils/cbk_regulatory_reporting.py` (~485 lines · 17 self-tests · all PASS first run).

### Five returns

| Code | PG | Computation | Threshold |
| --- | --- | --- | --- |
| `CAR` | PG 03 §4 | (tier1 + tier2 - deductions) / RWA | min 14.5% |
| `LIQ` | PG 04 | liquid_assets / total_deposits | min 20% |
| `SBL` | PG 05 | top borrower (funded + unfunded) / core capital | max 25% per borrower |
| `LXP` | PG 05 | aggregate of large exposures (>10% core each) / core | max 800% (8.0×) |
| `FXE` | PG 06 | per-currency `\|long − short\|` / core capital | max 10% per currency |

### Severity classification by deviation magnitude

For `min` thresholds: `shortfall = (threshold - actual) / threshold`; for `max` thresholds: `excess = (actual - threshold) / threshold`. Then:
- ≤10% deviation → `MARGINAL`
- ≥25% deviation → `SEVERE_BREACH`
- between → `BREACH`
- meets/within threshold → `NONE`

This gives operators granularity beyond binary pass/fail.

### Rule 1 / Rule 7

- 5 frozen input dataclasses with construction-time validation: `CapitalComponents` (non-negative tier1/tier2/deductions + RWA > 0); `LiquidityComponents` (deposits > 0); `BorrowerExposure` (id non-empty + amounts ≥ 0); `CurrencyPosition` (rejects KES + amounts ≥ 0).
- `CbkReturnPackage` carries `return_code + computed_metrics dict + threshold + threshold_direction + breach_severity + breach_description + inputs_used dict + framework_refs`. Operators have everything to reproduce the calc.
- Engine never serialises XBRL/XML/CSV (caller's responsibility), never submits to CBK portal, never auto-corrects breaches, never modifies balances.

### Scenarios

- **CBK-01 CAR passing** — Tier1 1.5b + Tier2 0.3b - deductions 0.1b = 1.7b cap; RWA 10b → CAR 17% > 14.5% → NONE breach.
- **CBK-02 LIQ severe** — liquid 1b / deposits 10b = 10% → 50% shortfall vs 20% min → SEVERE_BREACH.
- **CBK-03 SBL severe** — MEGA-CORP at 40% of core (60% over 25% threshold) → SEVERE_BREACH; 1 borrower in breach.
- **CBK-04 FXE multi-currency** — 3 currencies; USD net 16% breaches (60% over 10%); 1 currency in breach; per-currency pcts in `inputs_used`.

16/16 assertions all PASS.

### Honest scope notes

1. **No netting of unfunded exposures.** Treats unfunded fully — production frameworks may apply credit conversion factors (50% for short-term, 20% for trade-related) before counting toward the limit. CCF application is operator policy.
2. **Related-party exposures not separately tracked.** `BorrowerExposure.is_related_party` field exists but the engine doesn't apply the lower related-party limits separately — that's a future enhancement aligned with PG 05 §5.
3. **No BSD-1 to BSD-13 schedule serialization.** The standard description originally mentioned full BSD return schedule generation; the data layer is now in place but rendering to CBK's XML schema is operator-side per Rule 7.
4. **Severity classification uses simple percentage deviation.** Real-world CBK enforcement applies escalation tables that consider trends + size + cure period; this engine surfaces a single point-in-time severity.
5. **No multi-period rollup.** Each return is single-period. Quarterly/annual aggregation belongs to the caller.

---

## Combined gate verification

- `python3 scripts/audit.py` → **Score: 134/134 gates = 100.0% — PASS**
- `python3 scripts/structure_audit.py` → **STABLE: HARD findings match baseline exactly** (327 modules · 830 imports · HARD=3 unchanged · +3 modules / +5 imports across the three batches)
- All 14 engine self-tests green: **224/224**

## Lean+Compact protocol — applied (v10.46 amended)

Per batch (v10.60, v10.61, v10.62):
- 1 ENH per batch ✅
- Engine Hub Tier addition DEFERRED to arc closure (v10.68) ✅
- Master Prompt update DEFERRED to arc closure ✅
- UI integration DEFERRED to arc closure ✅
- Audit + G128 + scenario library extension SHIPPED ✅
- Per Rule 1 every dataclass surfaces full provenance ✅
- Per Rule 7 engine diagnostic only — verified by mutation tests ✅

## Files changed across the three batches

- **NEW** `utils/intercompany_matching.py` (~625 lines, 18 tests)
- **NEW** `utils/consolidated_tb_engine.py` (~625 lines, 16 tests)
- **NEW** `utils/cbk_regulatory_reporting.py` (~485 lines, 17 tests)
- **MOD** `utils/standards_registry.py` (3 standards activated with full descriptions)
- **MOD** `utils/scenario_simulator.py` (+12 scenarios + library extensions)
- **NEW** `CHANGELOG_v10.60_to_v10.62.md` (this file)

## finance arc state

| Standard | Module | Status | Batch |
| --- | --- | --- | --- |
| ENH-249 | finance_close_orchestrator | active | v10.59 |
| **ENH-250** | **intercompany_matching** | **active** | **v10.60** |
| **ENH-251** | **consolidated_tb_engine** | **active** | **v10.61** |
| **ENH-252** | **cbk_regulatory_reporting** | **active** | **v10.62** |
| ENH-253 | predictive_financial_analytics | planned | v10.63 |
| ENH-254 | finance_intelligence_dashboard (split-impl) | planned | v10.64 |
| ENH-255 | financial_statement_generator | planned | v10.65 |
| ENH-256 | tax_compliance_reporting | planned | v10.66 |
| ENH-257 | multi_entity_multi_currency | planned | v10.67 |
| ENH-258 | finance_audit_compliance | planned | v10.67+ |
| closure | G135 + G136 + Tier 27 + cockpit | planned | v10.68 |

## Next batch

Reverting to **one batch per session** per Joshua's updated direction. Next session ships **v10.63 — ENH-253 Predictive Financial Analytics**: forecasting + variance analysis. Per Rule 7, predictions never auto-act; per Rule 6, ML models surfaced through `ml_disabled` flag when not available.

**144 consecutive clean batches.** 12 closed arcs hold; finance arc at 4/10.
