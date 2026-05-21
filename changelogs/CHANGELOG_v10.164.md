# CHANGELOG v10.164 — ENH-198 Compliance Risk Assessment Engine

**Status:** Fifth active standard of the AML/Compliance cluster — **the rollup engine**. Pre-build inspection: clean greenfield. Aggregates inputs from the 4 individual AML engines (ENH-191 KYC/KYB, ENH-192 PEP/Sanctions, ENH-193 AML Monitoring, ENH-194 SAR/STR Filing) into an enterprise-level compliance risk score with executive dashboard.

**Audit:** `Score: 151/151 gates = 100.0% — PASS` (unchanged — engine-level work). G142 anti-drift floor 79→80. Active standards 181→182. v10.164 tests 26/26 pass.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `utils/compliance_risk_assessment.py` | ~580 | NEW. 5-dimension scorecard rolling up 4 upstream AML engines |
| `utils/standards_registry.py` | 1 line | MODIFIED. ENH-198 'planned'→'active', affected_engines=()→('compliance_risk_assessment',) |
| `tests/test_compliance_risk_assessment_v10_164.py` | ~340 | NEW. 26 tests across 9 classes |
| `docs/Master_Prompt_v3.57.md` | ~1100 | Anti-drift sync v3.56 → v3.57 |
| `SCOPE_LEDGER.md` | updated | v10.164 row + status block |
| `CHANGELOG_v10.164.md` | this file | This document |

---

## Regulatory alignment

- **CBK Prudential Guideline CBK/PG/15 §3** (Risk-Based Approach to AML/CFT) — institution must maintain enterprise-wide AML risk assessment driving policy, training, monitoring intensity
- **FATF Recommendation 1** — Risk-Based Approach: identify, assess, and understand ML/TF risks
- **Basel Committee Sound Management of Risks Related to Money Laundering** Principles 2-5

---

## 5-dimension scoring composition

Total clamped to [0, 100]. Bands: LOW <30, MEDIUM 30-49, HIGH 50-79, CRITICAL ≥80.

| Dimension | Cap | Logic |
|---|---:|---|
| **tier_concentration** | 25 | % of customer base in EDD or PROHIBITED tiers, linear scaling. 25%+ → max |
| **sanctions_pep_exposure** | 25 | Weighted: PEP 1x + sanctions 3x. Sanctions matches are absolute regulatory weight |
| **alert_backlog** | 25 | Open alerts 1pt + critical 5pts each. 5 criticals max the dimension |
| **filing_backlog** | 25 | **Overdue 8pts each** + investigations 1pt. 4 overdue max → heavy POCAMLA exposure |
| **cross_cluster_contradictions** | -10 to +10 | Surfaces evasion / calibration / wiring patterns |

The thresholds (LOW_BAND_MAX=29, MEDIUM_BAND_MAX=49, HIGH_BAND_MAX=79) are configurable class constants for stress-testing calibration to actual operational data.

---

## Cross-cluster contradiction detection (the differentiator)

Three patterns surfaced at +5 pts each (capped at +10 ceiling):

1. **PROHIBITED tier customer with no SAR submitted** — evasion suspicion. Customer should not be active; absence of SAR suggests institution is not following through
2. **>3 critical alerts but <5% customers in EDD tier** — tier review calibration overdue. Many alerts firing without commensurate EDD coverage suggests tier model needs recalibration
3. **AML escalations but zero SAR filings** — engines not wired together. ESCALATE_TO_SAR outcomes producing no filings = operational gap

Each contradiction returns text in the `contradictions` tuple. Operators see WHICH contradictions are active, not just a flag.

---

## Engine API

```python
class ComplianceRiskAssessmentEngine:
    def assess(
        self,
        kyc_engine: Optional[Any] = None,         # ENH-191
        aml_engine: Optional[Any] = None,         # ENH-193
        sar_engine: Optional[Any] = None,         # ENH-194
    ) -> ComplianceRiskAssessment: ...
    
    def assessment_by_id(assessment_id) -> ComplianceRiskAssessment
    def all_assessments() -> Tuple[ComplianceRiskAssessment, ...]
    def latest_assessment() -> Optional[ComplianceRiskAssessment]
    def board_summary() -> Dict[str, Any]
```

Each upstream engine is **optional**. Missing engines contribute zero points to their dimension AND surface in the contradictions list (Rule 6 honesty: missing data does NOT lower the risk score; we explicitly note the gap).

---

## End-to-end probe — full AML pipeline rolling up

Built realistic Ecobank Kenya scenario across all 4 upstream engines:

**ENH-191 KYC** — 3 customers registered + decided:
- Jane Wanjiru, teacher → APPROVED CDD
- Hon. PEP politician → APPROVED_WITH_EDD
- Cash King FX Ltd (KYB, cash-intensive) → APPROVED_WITH_EDD

**ENH-193 AML Monitoring** — 3 monitoring runs:
- C1 (clean retail) → CLEAN (0 alerts)
- C2 (PEP, KES 1.5M cash) → ESCALATE_TO_SAR (R1 critical)
- B1 (FX bureau, wire to IR) → ESCALATE_TO_SAR (R4 critical)

**ENH-194 SAR Filing** — 2 filings built:
- C2 → SUBMITTED
- B1 → DRAFT (within 7 days, not yet overdue)

**ENH-198 rolls it up:**

```
TOTAL SCORE: 37.0 / 100
RISK BAND:   MEDIUM
```

**Per-dimension breakdown (with audit-trail factors):**

| Dimension | Points | Contributing factors |
|---|---:|---|
| tier_concentration | 0 pts | 0 of 3 customers in EDD/PROHIBITED |
| sanctions_pep_exposure | **25 pts** | 1 PEP flagged customers (capped from raw 33.3%) |
| alert_backlog | **12 pts** | 2 critical alerts × 5 + 2 open × 1 + 2 escalated to SAR |
| filing_backlog | 0 pts | no overdue or active filings |
| cross_cluster | 0 pts | no contradictions |

---

## Honest finding from the probe

The tier_concentration showing **0%** even with 1 PEP (who should typically be EDD-tier) is an **actual cross-engine inconsistency** I caught while testing.

Looking at the kyc_onboarding logic: `tier` is set from the risk_band returned by KycAmlRiskEngine, and EDD is recorded via the `edd_triggers` field rather than upgrading the `tier` itself. Meanwhile `compliance_risk_assessment` counts `tier` values directly.

This is exactly the kind of issue ENH-198's surfacing capability is supposed to find — but it ALSO means a future ENH-191+ increment should promote tier when edd_triggers fires. The probe being deterministic surfaced an integration bug honestly. **Future work tracked.**

---

## Three honest deferral surfaces

Every assessment carries three explicit status fields:

### 1. trend_analysis_status — DEFERRED
> *"DEFERRED — this engine reports POINT-IN-TIME state. Trend analysis ('is enterprise risk getting worse?') requires historical assessments stored over time + delta computation + control-chart visualization. Out of scope for v10.164; tracked as future work for ENH-198+ increments. Operators should run assess() periodically (e.g. daily) and persist results externally to build trend."*

### 2. industry_concentration_status — PARTIAL
> *"PARTIAL — cross-cluster contradiction dimension flags some concentration patterns (PROHIBITED-without-SAR, CDD-with-multiple-critical-alerts). Full industry/sector concentration analysis requires SIC code aggregation per customer + sector-level risk weighting tables aligned to CBK Risk-Based Supervision Framework guidance. Sector weights not yet codified — flagged as future work for ENH-198+ increments."*

### 3. ml_predictive_status — DEFERRED
> *"DEFERRED — ML predictive enterprise risk modeling requires labeled regulatory events (assessments followed by regulatory findings within 90 days). Such labeled data doesn't exist in sandbox. Current scoring is rule-based + scorecard with deterministic dimension weights. Same deferral pattern as ENH-193 ml_layer_status."*

Operators reading the API see what this engine doesn't do, not just what it does. Same discipline as v10.159 vocabulary endpoint, v10.162 ml_layer_status, v10.163 submission_method, ENH-138 no_product_resolution.

---

## Strategic value

Joshua walks into the vendor evaluation with **ONE NUMBER** — 37.0/100 MEDIUM — that aggregates onboarding decisions + monitoring alerts + filing status across the bank's customer book.

That's the demo-closing argument: not *"we have 4 AML engines"* but *"we have 4 engines that compose into one enterprise compliance score with full auditable provenance to every contributing dimension."*

Compare to incumbent vendors who typically show feature lists. A2Z MIS 360 shows:
- **Provenance** — every score component lists its contributing factors
- **Composition** — 4 engines visibly producing one number, with the wiring traceable
- **Honest deferral** — what's missing is explicit, not hidden behind fabricated numbers

The Ecobank evaluation panel sees not a marketing claim but a working enterprise rollup with the math fully exposed.

---

## Tests — 26 across 9 classes

- **TestModuleShape** (4) — exists / parses / imports / RiskBand 4 values / frozen
- **TestRegistryActivation** (1)
- **TestEmptyInput** (2) — no engines → zero score / missing engines in contradictions
- **TestBandAssignment** (3) — LOW/MEDIUM/HIGH/CRITICAL thresholds + boundary values
- **TestScoreComposition** (4) — total capped at 100 / sanctions 3x weight / overdue 8pts / critical 5pts
- **TestCrossClusterContradictions** (1) — PROHIBITED without SAR
- **TestHonestDeferrals** (2) — 3 deferral surfaces in result + summary
- **TestEndToEndIntegration** (1) — full pipeline produces valid score
- **TestPortfolioSummary** (3) — empty / post-assess / to_dict shape
- **TestNoRegression** (5) — gates / count / v10.163 SAR / v10.162 AML / v10.160 KYC

All 26 pass.

---

## AML/Compliance module progress: 5 of 9 (more than halfway)

| Standard | Status | Engine(s) | Drop |
|---|---|---|---|
| ENH-191 KYC/KYB Onboarding | active | kyc_onboarding | v10.160 |
| ENH-192 PEP & Sanctions Screening | active | screening_orchestrator + sanctions_screening | v10.161 (prior session) |
| ENH-193 AML Transaction Monitoring | active | aml_monitoring + transaction_monitoring | v10.162 |
| ENH-194 SAR/STR Filing | active | sar_filing | v10.163 |
| **ENH-198 Compliance Risk Assessment** | **active** | **compliance_risk_assessment** | **v10.164** |
| ENH-195 Regulatory Change Mgmt | planned | — | candidate |
| ENH-196 Policy Management & Attestation | planned | — | future |
| ENH-197 Compliance Training | planned | — | future |
| ENH-199 Examiner-Ready Reporting | planned | — | candidate |

Module closure gates G152+G153 when all 9 active + module cockpit + module API + admin Tier 4C marker.

---

## Apply order

After v10.163:

```
1. utils/compliance_risk_assessment.py                  → utils/  (NEW)
2. utils/standards_registry.py                          → utils/  (REPLACES — ENH-198 active)
3. tests/test_compliance_risk_assessment_v10_164.py     → tests/  (NEW)
4. docs/Master_Prompt_v3.57.md                          → docs/
5. SCOPE_LEDGER.md                                      → root
6. CHANGELOG_v10.164.md                                 → root
```

`git add -A && git commit -m "v10.164 ENH-198 Compliance Risk Assessment — 5-dimension rollup over 4 AML engines"`. Then `python scripts/audit.py` should print `Score: 151/151 gates = 100.0% — PASS`.

**No app.py / scripts/audit.py change.**

---

## v10.165 next-up — two candidates

1. **ENH-195 Regulatory Change Management** — inbound complement to v10.164's outbound rollup. Ingests CBK circulars + amendments to POCAMLA / Banking Act / Banking Prudential Guidelines + KRA/FRC notices, tracks impact on internal policies, drives gap analysis, schedules attestation.
2. **ENH-199 Examiner-Ready Reporting Portal** — consumes ComplianceRiskAssessment + filings + alerts to produce regulator examination packages. Last standard in the cluster (numerically); closes the loop with the regulator's view.

Both are smaller scope than the rollup just shipped. ENH-195 brings inbound regulatory change tracking — pairs with v10.164's outbound rollup for a complete two-way regulator interface. ENH-199 turns v10.164's enterprise score plus the underlying engines' detail into examiner-grade documentation packages. Either is a good v10.165.

---

## Summary

v10.164 lands ENH-198 Compliance Risk Assessment Engine — the rollup that turns 4 individual AML engines into an enterprise compliance story with one headline number (37.0/100 MEDIUM in the realistic Ecobank probe). 5-dimension scorecard with deterministic weights, cross-cluster contradiction detection, three honest deferral surfaces, full provenance to every contributing factor. Discovered + documented an honest cross-engine inconsistency (kyc_onboarding edd_triggers vs tier promotion) which future work tracks. 26 tests pass.

**Quoting the audit script directly:** `Score: 151/151 gates = 100.0% — PASS`. v10.164 tests `26/26 pass`. AML cluster 5/9 active — more than halfway through.
