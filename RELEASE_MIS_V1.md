# RELEASE — MIS V1

**Tag:** `MIS-V1` → commit `d641de0`
**Date:** 2026-06-16
**One line:** The complete credit operating model — backend + UI, end to end —
on the established A2Z architecture. Baseline before the Ecobank hierarchy rework.

## What MIS V1 contains

### Credit operating model (the spine)
A deal travels the whole chain, all of it now visible in the React UI:

  pipeline → submit-to-credit (document-gated; blocked until every required
  document is attached; advances the deal stage on success) → LMS analyst assign
  → info-request loop → decision OR credit committee (config: authority_tier vs
  committee_voting) → offer issued → offer signed (+ signed copy) → offer
  validated (line manager) → analyst confirmed → Credit-Admin case → conditions
  fulfilled → authorization requested (officer) → authorized (CA manager) →
  disbursed.

All policy is admin-configurable (committee mode, attachment mode, validation/
confirmation toggles, thresholds). State machines, transitions, guards and
permissions are hardcoded for integrity. One shared `history[]` timeline.

### Committee voting
Wired to the existing `CreditCommitteeEngine` (charter, quorum, voting rules,
authority limits) via an adapter — not a re-implementation. Config-driven charter.

### Frontend
LMS application detail (assign, info-request, decision, offer issue/sign/validate,
confirm, committee vote + resolve, workflow timeline); Credit-Admin case detail
(conditions, two-layer authorize, disburse); Pipeline (assured tiles, validated
funnel, aging, product-class advance, Credit-Assessment stage lock); CBS lookup
(name search + direct CIF fetch/autopopulate).

### Foundations carried in
JWT auth (bcrypt-enveloped credentials), cascade scope resolver, per-product-class
stage flows, admin config as single source of truth, Postgres-first reads.

## Batch arc captured by this tag
α8–α10, β5–β6, γ1–γ3b (auth + LMS + Credit-Admin + CBS + Target Cascade),
B9–B10 (doc-gated submit), B16–B18 (stage flows + create cascade), B19–B21
(LMS workflow state machine + CA two-layer authz + committee voting),
B22a–B22b (workflow frontend), B23 (debt clearing — see DEBT_LEDGER.md).

## How to return here later
- Browse read-only:           `git checkout MIS-V1`
- Restart work from here:      `git checkout -b <branch> MIS-V1`
- Hard reset main to here:     `git reset --hard MIS-V1`  (destructive)

Note: `users.json` / `pipeline_deals.json` are gitignored — the tag captures
code + config, not runtime data (which is regenerable from the seed/generator
scripts).

## Known carried debt at V1 boundary
See `DEBT_LEDGER.md`. #1 (dashboard alignment) and #2 (pipeline→credit stage
sync) are CLEARED in B23. #3 (`credit_workflow.py` consolidation) and #4
(committee charter exposure to frontend) remain OPEN but do not distort numbers.

## Next phase
Ecobank hierarchy rework (org/scope/cascade layer): real area-manager regions,
`org_config.hierarchy` completion, retire the hardcoded reporting tree. The
credit-workflow engine and body-organs architecture are unchanged — V1 is a
forward baseline, not a fork.
