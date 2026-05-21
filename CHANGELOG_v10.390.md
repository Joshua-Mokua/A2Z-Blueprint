# Changelog — v10.390 Bundle: Prioritization Rescue 5/5 COMPLETE + Tier-1 Class B KPI Foundation

**Date:** 2026-05-13
**Phase:** Phase C continues — bundled batch
**Phase 4 arc count:** seventy-fourth arc — fourth Phase C execution batch
**Audit:** G275 added
**Tests:** 13/13 PASSED in `test_v10390_rescue_complete_and_ratios_engine.py` + 1 forward-compatible update to v10.380
**Verifier:** 483/483 checks pass on clean extract
**G162 baseline:** 4022 (83 consecutive zero-drift batches)
**Master prompt:** v4.32 → v4.33 (lockstep — 34 consecutive batches)

---

## Your direction

> "bundle" — Joshua-approved exception to Rule N2 to combine final rescue step + new workstream foundation

## What v10.390 delivers

### Concern A — Prioritization organ rescue 5/5 COMPLETE

The `pillar_weights` orphan field is removed from `data/org_config.json`.

```diff
{
   "bank_name": "Ecobank Kenya",
   ...
-  "pillar_weights": {"Financial": 0.40, "Customer Focus": 0.25, ...},
   ...
}
```

`health_check.orphan_detected` flips from dict to None.

**Five-batch rescue complete:**

| Step | Batch | What |
|---|---|---|
| 1 | v10.384 | Canonical accessor module + history schema |
| 2 | v10.386 | Working admin UI migrated to canonical save |
| 3 | v10.388 | Deprecated Bank Identity form removed |
| 4 | v10.389 | `pillars[].weight` shadow data removed |
| 5 | **v10.390** | **`org_config.pillar_weights` orphan field removed** |

The body's prioritization organ now has:
- ONE storage (`kpi_library.json::pillar_weights`)
- ONE admin UI (KPI Library → Pillar weights tab)
- Audit history captured
- Validation enforced
- NO shadow data
- NO orphan locations

### Concern B — Tier-1 Class B KPI foundation

New leaf module `utils/financial_ratios_engine.py` (AST-verified leaf — zero upward `utils.*` imports):

| Function | Returns | Computes |
|---|---|---|
| `compute_nim(mgmt_data)` | `NIMResult` | Net Interest Margin |
| `compute_cir(mgmt_data)` | `CIRResult` | Cost-to-Income Ratio |
| `compute_roe(mgmt_data)` | `ROEResult` | Return on Equity (PBT with caveat) |
| `compute_total_deposit_growth(mgmt_data)` | `DepGrowthResult` | Total Deposit Growth |
| `compute_all_financial_ratios(mgmt_data)` | `Dict[str, Result]` | All 4 at once |

Each result dataclass has `.to_dict()` for safe JSON serialization (Decimal → float).

**Live computation:**

| KPI | Value | Note |
|---|---|---|
| NIM | 1.15% | Raw period (mgmt_accounts.key_ratios.nim_pct=5.82 is annualized) |
| **CIR** | **53.67%** | **Matches bank's published key_ratios.cir_pct=53.7 ±0.5 — independent validation** |
| ROE | 4.26% | Uses PBT — caveat in `ROEResult.note` (no tax field in mgmt_accounts) |
| DEP_GROWTH | 3.18% | (110.2 - 106.8) / 106.8 |

**9 embedded self-tests pass** on `python3 utils/financial_ratios_engine.py`.

**4 KPI entries added to library** (all `active=False` per v10.381 Decision K7):

| KPI | Pillar | Direction | Weight | Active |
|---|---|---|---|---|
| NIM | Financial | higher | 0.15 | False |
| CIR | Financial | lower | 0.15 | False |
| ROE | Financial | higher | 0.10 | False |
| DEP_GROWTH | Financial | higher | 0.15 | False |

Each entry has `_added: "v10.390"` and `_tier: "Class B Tier 1"` for traceability.

### Forward-compatible test update

v10.380 alias resolver test previously asserted `get_kpi_definition("NIM") is None` (Class B orphan with no library entry). v10.390 added NIM to the library. Test updated to accept either:
- pre-v10.390: returns None (orphan)
- post-v10.390: returns dict with `active=False` (entry exists, awaiting target)

Same test continues to verify NIM isn't accidentally activated.

## Verified outcome

| Metric | Value |
|---|---|
| org_config orphan removed | ✅ |
| Backup at `data/_v10390_backups/org_config.json.before` | ✅ |
| `health_check.orphan_detected` is None | ✅ |
| `health_check.shadow_pillars_field` still False (v10.389) | ✅ |
| `utils/financial_ratios_engine.py` is leaf module | ✅ |
| 9 engine self-tests pass | ✅ |
| CIR matches bank published value | ✅ (53.67% vs 53.7%) |
| ROE caveat in `.note` | ✅ |
| 4 new KPIs in library, all inactive | ✅ |
| 13 v10.390 tests pass | ✅ |
| All 155 Phase B+C arc tests pass | ✅ |
| v10.380 forward-compatible update | ✅ |
| Audit gates | 274 → **275** |
| Verifier | 475 → **483 checks** |
| Master prompt lockstep | **34/34 consecutive batches** |
| G162 baseline | 4022 (**83 consecutive zero-drift batches**) |

## Phase C progress

| Batch | Concern | Status |
|---|---|---|
| ~~v10.386~~ | KPI Library tab canonical save + History view | ✅ |
| ~~v10.387~~ | History view | ✅ bundled |
| ~~v10.388~~ | Remove Bank Identity dead form | ✅ |
| ~~v10.389~~ | Remove `pillars[].weight` shadow data | ✅ |
| ~~**v10.390**~~ | **Remove org_config orphan + Tier-1 Class B KPI foundation** | ✅ **THIS BATCH** |
| v10.391 | customer_focus_engine (NPS + DIGITAL_ACT) | next |
| v10.392 | MD target setting + activation | pending |

**5 of Tier-1 batches done. 1 to go.**

## 15 honest acknowledgements

1. **Bundle was Joshua-approved.** Without that approval this would have been v10.390 = orphan only and v10.391 = engine. The bundle saves a batch number while keeping concerns logically separable.

2. **CIR matches the bank's own published value exactly (53.67 vs 53.7).** This is independent validation — my engine computes the same ratio Ecobank's management already reports. Confidence in correctness.

3. **NIM and ROE differ from key_ratios because they're annualized vs period.** Engine reports raw period (1.15% NIM, 4.26% ROE); key_ratios are annualized (5.82%, 16.8%). Annualization is a separate concern; consumers can multiply by 4 or 12 if needed.

4. **ROE uses PBT, not net income.** Honest caveat captured in `ROEResult.note` field. mgmt_accounts.json has no tax field. Future schema addition can switch to net income.

5. **All 4 new KPIs are inactive.** Per v10.381 Decision K7 recommendation. MD must set targets before activation. v10.392 will activate.

6. **The engine is a leaf module.** Zero upward `utils.*` imports. AST-verified. Safe to import anywhere.

7. **9 self-tests embedded in the engine** including divide-by-zero handling and empty-data graceful degradation.

8. **The rescue took 5 batches (v10.384-v10.390).** Each batch advanced without breaking. Two-stage removal pattern (stop writing → delete data) used twice (v10.388/v10.390 and v10.389 for shadow). Clean methodology.

9. **The orphan removal was anticlimactic.** One field deletion. The hard work was the 4 preceding batches of careful disconnection.

10. **Forward-compatible test update was the right call.** Strict assertion that NIM is None would have broken v10.390. Widened assertion accepts either state — verifies the intent (NIM not auto-activated).

11. **Finding N7 is still outstanding.** `utils/core.py::get_active_kpis()` calls `.items()` on a list (pre-existing bug discovered v10.389). Not bundled here — separate batch. v10.392 or earlier.

12. **The 4 KPI entries have explicit `_added: "v10.390"` markers.** Future readers can trace when each KPI joined the library. Traceability cheap insurance.

13. **Body-system framing held throughout the rescue.** Five batches of organ-specific surgery. The metaphor genuinely helped sequence the work and explain why each batch mattered.

14. **The cumulative LOC added by Phase C is small.** v10.386 ~50 admin LOC, v10.388 ~30 admin LOC, v10.389 0 LOC (data only), v10.390 ~370 engine LOC + 4 KPI entries. Most batches were small; the architecture pays compound dividends.

15. **Phase C is on track.** 5 of 6 Tier-1 batches done. v10.391 closes Tier-1 with customer-focus engine. v10.392 activates everything. Then Tier-2 (cascade cleanup) begins.

## On your end

1. Close Streamlit
2. Extract `a2z_v10390_session_cumulative.zip` flat
3. Run `python scripts\verify_local_state.py` → expect **483/483**
4. Confirm the rescue is complete: `python -c "import sys; sys.path.insert(0,'.'); from utils.pillar_weights_canonical import health_check; print(health_check())"` → see `orphan_detected: None`, `shadow_pillars_field: False`
5. Confirm the engine works: `python utils/financial_ratios_engine.py` → see 9 tests pass and 4 live ratios
6. Read `docs\RESCUE_COMPLETE_AND_FINANCIAL_RATIOS_v10.390.md`
7. Tell me "continue" → v10.391 = customer_focus_engine (NPS + DIGITAL_ACT)

## What's next — v10.391

Build `utils/customer_focus_engine.py` as another leaf module exposing:
- `compute_nps(survey_data)` → NPSResult
- `compute_digital_active(cbs_data)` → DigitalActiveResult

Plus 2 KPI library entries (NPS, DIGITAL_ACT) — both inactive until v10.392 target setting.

After v10.391, all Tier-1 Class B KPIs have engines + library entries. v10.392 activates them.

Continue with v10.391?
