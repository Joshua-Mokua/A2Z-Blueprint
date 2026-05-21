# Changelog — v10.381 Customer Profitability Canonical Refactor + Recommendations (Phase B)

**Date:** 2026-05-13
**Phase:** 4 (sixty-sixth arc — Phase B fifth batch)
**Audit:** G267 added
**Tests:** 13/13 PASSED in `test_v10381_customer_profitability_canonical.py`; **333 total**
**Verifier:** 424/424 checks pass on clean extract
**G162 baseline:** 4022 (75 consecutive zero-drift batches)
**Master prompt:** v4.24 → v4.25 (lockstep — twenty-sixth consecutive batch)

---

## Your direction

> "continue with the original Phase B roadmap, on the questions requiring my decision, i would welcome your recommendation on what decision will make the body function better as one"

Two parts:
1. **Phase B roadmap** — refactor `customer_profitability.py` to consume v10.378 unified master
2. **Recommendations on the 8 Part 9 decisions** through body-system lens

Both delivered in v10.381.

## Part 1 — Customer Profitability Refactor

### What changed

| File | Change |
|---|---|
| `utils/customer_profitability.py` | Default lookup now canonical-first with legacy fallback |

### How the refactor stayed surgical

The engine already had dependency injection (`customer_lookup_fn`). I changed only:

1. **Renamed** old `_default_customer_lookup` logic to `_legacy_customer_intelligence_lookup` (preserves as fallback)
2. **Added** `_canonical_customer_lookup_v10381` — calls `compute_unified_customer_master()` from v10.378
3. **Rewrote** `_default_customer_lookup` to try canonical first, fall through to legacy
4. **Added** `_UNIFIED_MASTER_CACHE` (module-level) + `reset_canonical_customer_cache()` (test helper)

The public API (`CustomerProfitabilityEngine`) is unchanged. Callers passing their own `customer_lookup_fn` are unaffected.

### Verified compatibility

Round-trip test with real CIF `100625608`:
- **Legacy** segment: `'Mass'`
- **Canonical** segment: `'Mass'`
- **Match: True ✓**

All 42 existing `tests/test_customer_profitability.py` tests pass unchanged.

### What the engine now sees (superset)

| Field | Legacy | Canonical |
|---|---|---|
| `segment` | ✓ | ✓ |
| `cif`, `tags`, `propensity_scores`, etc. | ✓ | ✓ |
| `sources` (which data source(s) the record came from) | absent | **NEW** |
| `enrichment_status` (cbs_only / marketing_only / both) | absent | **NEW** |
| `_field_lineage` (per-field provenance) | absent | **NEW** |

## Part 2 — Recommendations on Decisions

Body-system framing applied throughout. The recommendations document is `docs/V10380_DECISIONS_RECOMMENDATIONS_v10.381.md`.

### Summary table (full reasoning in the doc)

| # | Decision | Recommendation | Why "better as one" |
|---|---|---|---|
| 1 | Class B KPIs (15) | **Tiered:** add 9 (NIM, CIR, ROE, NPS, DEP_GROWTH, DIGITAL_ACT, 5 LEGAL_*); alias 1 (NEW_CUST); verify 1 (PAR); defer 4 | The MD can't sense her own pulse without NIM/CIR/ROE/NPS. Without these the Financial pillar is incomplete and Customer Focus has no loyalty signal. |
| 2 | Pillar weights | **Return to 40/25/25/10** (balanced) | 68/14/6/12 means Financial = 68% — single-variable optimization. Donella Meadows: this destroys complex systems. The other organs atrophy and eventually pull Financial down too. |
| 3 | K-code retirement | **Phased**: alias → deactivate → remove | Duplicate organs split the body's immune system. K001 + LOAN_DISB + "Loans Disbursed (KES M)" = 3 names for 1 truth. |
| 4 | Cascade `deadline\|*` | **Move to top-level `cascade_meta`** | Mixing metadata with cascade entries is a category error. Each organ should know its role. |
| 5 | active=null | **Normalize to `active=False`** | Schrödinger's-KPI breaks audit trails. Alive/dead distinction is needed. |
| 6 | role_kpis (227) vs taxonomy (126) | **Add `role_status` field**: active/aspirational/retired | The body should know which organs exist vs which are planned. Status tagging makes self-knowledge explicit. |
| 7 | `cbk_ref` | **Populate for the ~10 regulatory KPIs** | Each regulatory KPI shows its provenance directly. The body's regulatory pulse becomes traceable. |
| 8 | ID convention | **SCREAMING_SNAKE wins** (91% already) | One canonical name per organ across all consumers = integration friction drops to zero. |

### The most important recommendation if you only had time for one

**Add NIM, CIR, ROE, NPS as KPIs.** Without these, the MD's BSC cannot present a complete banking story.

### Proposed downstream batches

| Batch | Concern |
|---|---|
| v10.382 | Apply canonical refactor pattern to `rm_profitability.py` |
| v10.383 | If you approve Decision 1: add the 9 new KPIs to kpi_library; alias NEW_CUST; verify PAR; normalize active=null; rebalance pillar weights |
| v10.384 | If Decision 3: K-code aliases + deactivate; Title Case → SCREAMING_SNAKE aliases |
| v10.385 | If Decision 4: cascade_meta migration |
| v10.386+ | Continue Phase B/C/D |

## Verified outcome

| Metric | Value |
|---|---|
| Public API unchanged (CustomerProfitabilityEngine) | **YES** |
| All 42 existing engine tests pass | **YES** |
| Engine consumer field (segment) round-trip | **MATCH** (legacy == canonical) |
| Provenance fields now visible | sources, enrichment_status, _field_lineage |
| Audit gates | 266 → **267** (G267 added) |
| All prior canonical identities | still PASS |
| Tests | +13 in v10.381; **333 total across v10.358–v10.381** |
| Verifier | 409 → **424 checks** |
| Master prompt lockstep | **26/26 consecutive batches** |
| G162 baseline | 4022 (**75 consecutive zero-drift batches**) |

## Honest acknowledgements

1. **The refactor was small because the engine was well-designed.** Dependency injection paid for itself. No structural changes were needed.

2. **Module-level cache (`_UNIFIED_MASTER_CACHE`) is global state.** It works for the typical request-response pattern but tests must reset between cases. `reset_canonical_customer_cache()` is provided.

3. **Recommendations are advisory, not authoritative.** I've documented my reasoning for each but they don't ship code changes. The 8 decisions are still yours.

4. **The body-system framing is the constitution's framing too** (§12 Flow Principle). Reusing it consistently means recommendations align with the framework you've established.

5. **"Add NIM/CIR/ROE/NPS" is the strongest recommendation.** A bank without those on its MD BSC is a bank that can't tell its own story. Other recommendations are improvements; this one is foundational.

6. **Returning to 40/25/25/10 may feel risky in a crisis quarter.** Counter-acknowledged in the recommendations doc. If 68/14/6/12 reflects deliberate crisis-posture, document it with a return-to-balance date.

7. **K-code retirement is the most invasive change.** Some existing `bsc_actuals_*.json` records may reference K001 etc. Phased migration (alias first, deactivate next, remove last) reduces risk.

8. **The canonical refactor caches the entire unified master (~3,206 records).** Memory cost is small but real. For larger banks this may need reconsidering (e.g. LRU cache per-customer instead of full master cache).

9. **CIFs in CBS but not in marketing are now visible.** They have None for marketing fields (clv, churn, etc). Engine handles None correctly today (only reads `segment`); downstream consumers should be aware.

10. **The recommendations doc is ~12KB and substantive.** Read it before approving any decisions. Each recommendation has a "why this makes the body function better as one" section showing the reasoning.

11. **Rule N2 single concern held.** Two artifacts (refactor + recommendations) but both serve the same v10.381 commitment: continue Phase B with full transparency on the open decisions.

12. **No tests were re-baselined.** The 42 existing engine tests run identically because the engine output is identical (segment is what they check; segment matches).

13. **`_canonical_customer_lookup_v10381` falls back silently on exception.** This may mask real bugs. Documented as a deliberate trade-off — robustness over fail-loud.

14. **42+13 = 55 tests touch this engine.** That's strong coverage for the v10.381 refactor.

15. **Phase B continues.** v10.382 = `rm_profitability.py` same pattern. After that, ready for either your Decision approvals (cascading to v10.383+) or Phase C live actions.

## On your end

1. Close Streamlit
2. Extract `a2z_v10381_session_cumulative.zip` flat
3. Run `python scripts\verify_local_state.py` → expect **424/424**
4. **Read `docs\V10380_DECISIONS_RECOMMENDATIONS_v10.381.md`** — your 8 decisions, my best argument for each
5. Read `docs\CUSTOMER_PROFITABILITY_CANONICAL_REFACTOR_v10.381.md` — the refactor itself
6. **Optional:** answer one or more decisions and tell me which to action in v10.382+
7. (Optional, >5min) Audit → expect **267/267 PASS**

## What comes next — v10.382

Same refactor pattern applied to `rm_profitability.py`. That engine reads customer + RM data through different paths today; canonical-first + legacy fallback gets it consuming v10.378 too.

After v10.382, both parallel profitability engines are unified. If you've approved decisions by then, v10.383 can action them (e.g. add NIM/CIR/ROE/NPS).

Want me to continue with v10.382?
