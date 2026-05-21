# CRM & Customer Functions Module — Risk Assessment

**Module key:** `crm` · **Organ role:** Sensory & Interaction Systems (pipeline · customer 360 · propositions · campaigns · cross-sell · channels · NPS · behavioral intelligence · onboarding · cards · bancassurance · merchant acquiring)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 50.0%

Per Module Revival Framework Phase 2 QA3. Operational + technical + regulatory risk assessment for this organ + mitigations + residual risk.

---

## Operational risk inventory

| Risk category | Likelihood | Impact | Inherent | Mitigation | Residual |
|---|---|---|---|---|---|
| CRM & Customer Functions Module workflow disruption | Medium | High | Medium | Defensive engines + cross-organ event_bus | Low |
| CRM & Customer Functions Module data integrity drift | Low | High | Medium | Daily reconciliation + audit trail | Low |
| CRM & Customer Functions Module unauthorized access | Medium | Critical | High | RBAC + super_user escalation + security_event monitoring | Low |
| CRM & Customer Functions Module regulatory non-compliance | Medium | Critical | High | Compliance org cross-organ wiring + CBK reporting | Low |
| CRM & Customer Functions Module integration failure | Low | High | Medium | Flexcube facade circuit breaker + virtual bank fallback | Low |
| CRM & Customer Functions Module key person dependency | Medium | Medium | Medium | Super user backup + escalation chain | Low |

## Risk treatment plan

- **Accept**: Low residual risks tracked in Phase 8 monitoring
- **Transfer**: insurance via CRM & Customer Functions Module contracts review
- **Mitigate**: highest-impact items wired into stress_test_harness scenarios
- **Avoid**: practices flagged in qa_gap_analysis are deprioritized

## Cross-organ risk dependencies

- **credit**: relies on `customer, lending` integration intact
- **operations**: relies on `onboarding, edms` integration intact
- **compliance**: relies on `kyc, consent` integration intact
- **bsc**: relies on `pipeline, leads` integration intact
- **admin**: relies on `audit_log, rbac` integration intact
- **treasury**: relies on `fx, trade_finance` integration intact

## Overall risk posture: ACCEPTABLE
Inherent risk medium-high; residual risk LOW after mitigations.
