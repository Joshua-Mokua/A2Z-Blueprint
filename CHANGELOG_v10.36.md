# CHANGELOG v10.36 — SCENARIO SIMULATION FOUNDATION

**Audit:** 126/126 PASS — **119th consecutive clean.**
**Tests:** 787 integration (+19 from v10.35's 768) + 18 self-tests on the scenario simulator + 11 executable banking scenarios.
**Status:** Pause Treasury content; ship cross-arc scenario simulation foundation per the user-supplied **Comprehensive Scenario Simulation & Safe Learning Framework**. Treasury arc remains at 8/16 active; 8 specialized standards + G127 closure deferred to v10.37.

---

## Why this batch is different

The user supplied a strategic framework document for scenario-based testing + safe ML learning. Rather than continue mechanically with v10.36 specialized Treasury work, the right move was to honestly review the document and execute the most actionable element: **a scenario simulation foundation that grows with the platform.**

Honest review of the framework document is at the top of this batch's user-facing message. Summary:

- **Already built (v10.18-v10.35):** Virtual bank simulation, model governance with Tier 1/2/3, drift detection PSI/KS, audit trail with hash-chained certifications, cross-sell bandit with risk appetite + bias guards. ~70-80% of the document's "safe learning architecture" already exists.
- **Premature given current state:** Daily-CI champion/challenger pipeline with auto-PRs (we have one ML model — bandit — not multiple competing). Defer until we have 2+ models in same domain (likely v10.40+).
- **Most actionable now:** The scenario harness itself — codifying executable banking scenarios that grow into a regression suite.

## What v10.36 ships

### `utils/scenario_simulator.py` (1219 lines, 18 self-tests)

Cross-arc executable scenario harness:

| Component | Implementation |
|---|---|
| **10 ScenarioCategory enums** | CUSTOMER_LIFECYCLE · CREDIT_LENDING · DEPOSIT_LIQUIDITY · PERFORMANCE_MGMT · RISK_COMPLIANCE · OPERATIONS_TREASURY · STRATEGY_CAMPAIGNS · FRAUD_SECURITY · RECOVERY_DISASTER · COMPETITOR_MARKET (matches the document taxonomy) |
| **5 ScenarioStatus enums** | PASS / WARNING / FAIL / SKIPPED / ERROR with deterministic outcomes |
| **Scenario contract** | `setup(bundle)` → `actions(bundle)` → `assertions(bundle)` lifecycle. Each callback receives an EngineBundle dict. Returns `Sequence[AssertionResult]` |
| **AssertionResult** | Per Rule 1: every assertion surfaces `expected` + `observed` + `matched` + `description`. Failures retain specific values, not just bool |
| **ScenarioRunner — dual mode** | (1) `engines={...}` for shared-bundle (state accumulates across scenarios — useful for sequenced cross-scenario interactions). (2) `bundle_factory=callable` for fresh-bundle-per-scenario (default for regression suites) |
| **Requirements declaration** | Each Scenario declares `requires_engines` + optional `requires_providers`. Runner skips with status SKIPPED rather than fabricating responses (Rule 7) |
| **Roll-up reporting** | `summary()` aggregates by status + by category. `failures()` filters to FAIL-only. `first_failure()` per result for quick triage |

### Initial library — 11 Treasury-focused scenarios

| ID | Category | Description |
|---|---|---|
| **LI-01** | DEPOSIT_LIQUIDITY | LCR compliance: 200M HQLA L1 + 100M outflows → LCR 200% ≥ Basel 100% |
| **LI-02** | DEPOSIT_LIQUIDITY | LCR breach detection: 50M HQLA + 100M outflows → system flags non-compliant |
| **IRRBB-01** | OPERATIONS_TREASURY | IRRBB outlier on extreme position: 10B unhedged 5y+ vs 1B Tier 1 → BCBS 368 ΔEVE outlier flag |
| **CAP-01** | RISK_COMPLIANCE | Dual capital threshold: 8% CET1 passes Basel 4.5% but fails CBK PG/03 10.5% |
| **FX-01** | OPERATIONS_TREASURY | FX net exposure: 5M USD long − 2M USD short = 3M USD net |
| **NIM-01** | PERFORMANCE_MGMT | NIM decomposition: loan 15% − FTP 10% = 5% lending margin; deposit FTP 8% − customer 5% = 3% funding margin |
| **DASH-01** | OPERATIONS_TREASURY | Dashboard breach roll-up: ALM LCR breach → dashboard overall_status BREACH |
| **CF-01** | OPERATIONS_TREASURY | Cash forecast generates 14-day projection from 60-day history |
| **CF-02** | RISK_COMPLIANCE | Per Rule 7: ML overlay without provider raises REQUIRES_PROVIDER |
| **MODGOV-01** | RISK_COMPLIANCE | Tier 1 model registers in governance registry |
| **CROSS-01** | OPERATIONS_TREASURY | End-to-end LCR breach propagation: ALM detects → dashboard surfaces |

All 11 scenarios pass with fresh-bundle-per-scenario.

## Honest scope notes

1. **No new standards activated.** v10.36 is platform infrastructure. It exercises standards that are already active. Treasury count remains 8/16 (50%); platform count remains 95/247.
2. **AUDIT-01 scenario was dropped.** Initial design assumed `audit_core` had an event-log API (`AuditEvent`/`AuditEventType`/`ActorRole`). The actual v10.23-27 audit_core is structured around BCBS 239 / GRC controls + working papers (`Control` / `WorkingPaper` / `ControlTestResult`). Per Rule 7, the simulator does not invent a missing API — it documents the gap and defers. Audit_core scenarios will be added when control-evidence flows are exercised by future batches.
3. **CROSS-01 was simplified.** Originally planned to test ALM → dashboard → audit. Reduced to ALM → dashboard for the same Rule-7 reason.
4. **Champion/challenger pipeline NOT shipped.** The document's CI/CD auto-PR pattern is industry-standard but premature for one ML model (the bandit). When we have 2+ models competing in same domain — likely v10.40+ when fraud detection / churn / dynamic pricing land — champion/challenger will extend the EXISTING `model_governance` module rather than create a separate registry. Reduces duplication.
5. **Shadow-mode deployment NOT shipped.** Will add as a flag on `model_governance.Model.current_state` when we have a model worth shadow-deploying. Skip until then.
6. **CI/CD GitHub Actions NOT shipped.** Daily training jobs make sense when: (a) you have multiple models in production, (b) you have a team reviewing PRs, (c) you have a stable simulation→training feedback loop. None of these is true yet for a one-developer project. Manual training scripts work fine until then.

## Refined incremental plan — scenarios grow batch-by-batch

This is the pattern v10.36 establishes:

| Batch | Domain | New scenarios |
|---|---|---|
| v10.36 | Treasury foundation library | 11 scenarios (this batch) |
| v10.37 | Treasury closure | + 8 covering ENH-239/240/R1-R6 |
| v10.38+ | Risk arc | + 4-6 per batch covering market/operational/credit/conduct risk |
| v10.40+ | When 2+ models compete | + champion/challenger extending model_governance |
| Long-run | All arcs | ~100-150 scenario regression suite |

This is honest, incremental, and matches the platform's growth curve.

## Engine Hub addition

Tier 18 in `pages/7_admin.py` documents `scenario_simulator` as cross-arc infrastructure (not domain engine). Tier numbering preserved.

## Honesty Rule conformance

- **Rule 1.** Every `AssertionResult` reports `expected` + `observed` + `matched` + `description`. Failures retain specific values for triage. Every `ScenarioResult` reports `n_passed` + `n_failed` + `first_failure()` accessor + per-category category roll-up via `summary()`.
- **Rule 7.** `requires_engines` + `requires_providers` declared per scenario. Runner emits SKIPPED (not fabricated PASS) when requirements unmet. AUDIT-01 scenario dropped because `audit_core` doesn't have the event-log API the original design assumed — simulator did not invent that API.
- **Decimal-internal precision 28** maintained where applicable (assertion observed/expected can be any type).

## Honest closing notes

1. **126 gates passing; 119th consecutive clean batch.** Platform integrity unbroken across the strategic pivot.
2. **The scenario library is small but high-quality.** 11 scenarios versus the document's 160+ target. Every additional scenario gets added in subsequent batches as new functionality lands. Quality > inflation.
3. **The bigger value of this batch is the pattern, not the scenarios.** Once `Scenario` + `ScenarioRunner` + the bundle-factory contract are in place, every future batch can add scenarios cheaply (10-50 lines each). The platform's growth becomes regression coverage growth.
4. **The user's framework document was strategic but partially aspirational.** Honest review flagged what's already built (so we don't duplicate) and what's premature (so we don't build prematurely). That honesty is more valuable than mechanical execution of every framework recommendation.
5. **Treasury arc 50% done; specialized work + closure remain in v10.37.** When v10.37 ships, we add 8 scenarios covering ENH-239 Islamic, ENH-240 Agentic, ENH-TRS-R1 through R6 — and lock G127.

---

## Phase 2 progress after v10.36

| Arc | Standards | Status |
|---|---|---|
| Climate · Credit · KESONIA · RMS · Audit/GRC · Model Gov · Virtual Bank · Bandit | 75 closed | ✅ 8 arcs |
| **Treasury (v10.33–v10.37)** | **8/16 active = 50%** | **🟡 batch 4 ships infra; specialized work in v10.37** |
| Risk · Trade · IT · etc. | 0/152 | pending |

**95 of 247 standards active.** Treasury arc 50% complete. **Cross-arc scenario harness foundation shipped — every subsequent batch will add 3-5 scenarios covering its new functionality.**

## What ships next — v10.37

Treasury arc closure batch — all 8 specialized Treasury standards activated + G127 audit gate + 8 new scenarios covering them: ENH-239 Islamic Treasury, ENH-240 Agentic Treasury Orchestration, ENH-TRS-R1 (9900+ bank connections), ENH-TRS-R2 (stablecoin / digital asset), ENH-TRS-R3 (MMF direct access), ENH-TRS-R4 (MX.3 cross-asset), ENH-TRS-R5 (real-time API ERP-to-bank), ENH-TRS-R6 (climate-adjusted treasury limits — composes v10.6-10 climate with v10.33-35 treasury).

**119 consecutive clean batches.** Scenario foundation shipped. Treasury arc 50% complete. Specialized Treasury + closure remaining.
