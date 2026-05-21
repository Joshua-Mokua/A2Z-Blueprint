# CHANGELOG v10.28 — MODEL GOVERNANCE ARC BATCH 1: FOUNDATION

**Audit:** 123/123 PASS — **111th consecutive clean.**
**Tests:** 574 integration (+27 from v10.27's 547) + 39 self-tests on the new engine.
**Status:** Phase 2 Model Governance arc OPEN at batch 1 of 2.

---

## What v10.28 ships

`utils/model_governance.py` (1709 lines, **Cat A**) — pre-requisite safety net before any ML pilot. Five model governance standards activated:

| Standard | Component |
|---|---|
| **ENH-259** Model Risk Governance Framework | 15-type ModelType enum × 3-tier risk classification per SR 11-7 (TIER_1_HIGH 12-month / TIER_2_MEDIUM 24-month / TIER_3_LOW 36-month validation cadence) × 4-category EU AI Act mapping × 8-state lifecycle with explicit transition graph (DEV→TESTING→VALIDATION→APPROVED→IN_PRODUCTION + UNDER_REMEDIATION/SUSPENDED/RETIRED branches; RETIRED terminal). Tier 1/2 IN_PRODUCTION transition blocked without passed independent validation report on file |
| **ENH-261** Continuous Model Monitoring | PSI (Siddiqi 2017 thresholds 0.10/0.20/0.25 → NO_DRIFT/SMALL_SHIFT/SIGNIFICANT_SHIFT/MAJOR_DRIFT) + KS test (Smirnov 1948 critical values c(α)=1.36 at α=0.05) + Wasserstein 1D earth mover's distance. INSUFFICIENT_DATA verdict explicit when n<100 (PSI) or n<30 (KS) per Rule 1 |
| **ENH-262** AI Model Validation & Testing Suite | 11 ValidationGate enum (data quality / conceptual soundness / OOT / OOS / benchmarking / sensitivity / stress / fairness / explainability / production readiness) × tier-based requirements (T1=11, T2=6, T3=3 gates). Overall verdict FAIL if any required gate FAIL; INCONCLUSIVE if any not tested |
| **ENH-263** Credit Decision Explainability | 7 ExplanationMethod (SHAP/LIME/permutation/partial_dependence/integrated_gradients/counterfactual/rule_extraction) — Rule 7 hookable, returns REQUIRES_PROVIDER without explainer. CFPB Reg B Appendix C adverse action codes (20 codes) + feature-to-AA-code mapper for top negative contributions |
| **ENH-265** Continuous Bias Monitoring | 6 BiasMetric (4/5ths rule per EEOC 29 CFR §1607.4 threshold=0.80, demographic parity tolerance=0.05, equal opportunity, equalized odds, predictive parity, calibration) × 4 verdicts (NO_BIAS/POTENTIAL/DISPARATE_IMPACT/INSUFFICIENT_DATA) |

## Key design decisions

**Honesty Rule 7 — explainers never fabricate.** SHAP/LIME explanation requests without a wired explainer return `REQUIRES_PROVIDER` with explicit notes. The framework refuses to invent feature contributions even if the caller could be fooled.

**Honesty Rule 1 — surface evidence at every decision boundary.** Drift results show method + statistic + threshold + sample sizes + severity. Bias results show selection rates + ratio + verdict. Validation reports show passed/failed/not-tested counts.

**Lifecycle is governance-enforced.** A Tier 1 (HIGH) model cannot transition to IN_PRODUCTION without (a) at least one ValidationReport on file AND (b) that report's overall verdict being PASS or PASS_WITH_OBSERVATIONS. The engine raises ValueError on attempted bypass.

**Validation gates are tier-graduated.** Tier 1 requires 11 gates (full SR 11-7 workup); Tier 2 requires 6 (skip benchmarking/sensitivity/stress for medium models); Tier 3 requires only 3 (data quality + dev testing + production readiness for descriptive analytics).

**PSI thresholds match credit scoring industry practice** per Siddiqi 2017: <0.10 stable, 0.10-0.20 minor shift, 0.20-0.25 significant, ≥0.25 major drift. The framework uses 0.001 epsilon smoothing for empty bins to handle log(0).

**KS critical value uses Smirnov 1948 large-sample approximation:** c(α) × √((nb+nc)/(nb·nc)) where c(0.05)=1.36, c(0.01)=1.63. Verdicts walk multiples of critical: <c=NO_DRIFT, <1.5c=SMALL_SHIFT, <2c=SIGNIFICANT, ≥2c=MAJOR.

**4/5ths rule per EEOC 29 CFR §1607.4.** Verdict thresholds: ratio ≥ 0.80 → NO_BIAS, 0.70-0.80 → POTENTIAL_BIAS, < 0.70 → DISPARATE_IMPACT.

## Regulatory provenance

Federal Reserve SR 11-7 · OCC 2011-12 · PRA SS1/23 · EU AI Act (Reg 2024/1689) Art 9/13/14/15 · NIST AI RMF 1.0 · CFPB Reg B (ECOA) Appendix C · CBK CRMF April 2021 §5 · Basel BCBS 449 · ISO/IEC 23894:2023 · Singapore MAS FEAT · Siddiqi 2017 (PSI) · Kolmogorov 1933 + Smirnov 1948 (KS) · Vaserstein 1969 (Wasserstein) · Lundberg & Lee 2017 (SHAP) · Ribeiro et al. 2016 (LIME) · EEOC 29 CFR §1607.4 (4/5ths rule)

## Tests

**39 self-tests** in module covering lifecycle (4) + PSI drift (7) + KS drift (4) + validation (4) + explainability (4) + bias (6) + engine enforcement (10).

**22 integration tests** covering imports + public symbols + registry alignment + lifecycle + drift detection + validation + explainability + bias monitoring + engine enforcement + coexistence with v10.23-v10.27.

## Engine Hub

Tier 12 added to `pages/7_admin.py` — surfaces `model_governance` engine alongside the 11 existing tiers (Climate/ESG, Credit, KESONIA, RMS, Audit/GRC).

## Acknowledgements

The 5/6-batch arc pattern proven across 5 prior arcs holds for Model Governance too — but compressed to 2 batches given the cross-cutting nature (foundation → closure). v10.29 ships ENH-264 (vendor model management) + ENH-266 (automated retraining) + G124 audit gate locking the closure set.

The remaining 3 standards — ENH-260 alt scoring, ENH-267 risk appetite, ENH-268 credit committee — defer to v10.32+ where the cross-sell bandit pilot will need them.

## What v10.29 ships next

`utils/model_governance_runtime.py` (~800-1000 lines):
- ENH-264 Vendor Model Management — third-party model registry + vendor due diligence + contractual audit rights
- ENH-266 Automated Model Retraining Workflow — drift-triggered retraining policy + champion-challenger deployment
- G124 audit gate locking 7 modgov standards (5 v10.28 + 2 v10.29)
- 4 drift tests verifying gate behavior
- Closing CHANGELOG_v10.29.md with 2-batch retrospective
- Forward-compat for any v10.27 assertions

## Honest closing notes for v10.28

1. **Module is the chassis, not the bandit pilot.** The framework provides drift detection, validation, explainability hooks, bias tests — but the cross-sell bandit at v10.32 will exercise this discipline against actual model behavior. v10.28 alone doesn't deploy any ML.

2. **Statistical methods are deterministic; ML methods are hookable.** PSI, KS, Wasserstein, 4/5ths rule, demographic parity all run without external dependencies. SHAP/LIME explainers and ML-based bias detectors are callable hooks per Rule 7.

3. **Audit chain integration deferred to v10.29.** The engine state is in-memory per-instance; cryptographic chain-of-custody via v10.27 audit_trail_certification will wire in v10.29 closure.

4. **No persistence.** Models, lifecycle transitions, drift results, validation reports, explanations, bias results — all in-memory per ModelGovernanceEngine instance. Production deployment needs Postgres persistence layer.

5. **No Streamlit UI surface beyond Engine Hub admin.** Same deferral as Credit + RMS + Audit/GRC arcs — dedicated `pages/N_model_governance.py` is future UI work.

111 consecutive clean batches. Model Governance foundation in place. v10.29 next opens vendor model management + retraining workflow, then G124 closes the arc and v10.30 opens Virtual Bank simulation.
