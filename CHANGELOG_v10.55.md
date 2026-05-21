# CHANGELOG v10.55 — revenue_assurance arc · ENH-246 Continuous Billing Verification

**Status:** revenue_assurance arc 6/8+1 batches (2 standards remaining + closure)
**Audit:** 132/132 PASS · **G128:** STABLE (320 modules · 801 imports · 3 HARD)
**Active standards:** 124 → **125** / 260 · **Scenario library:** 74 → **78** (4 CBV-* added)

## What this batch does

Pre-issuance billing verification — screens **pending** records before they post. Critical scope distinction from ENH-242 which screens *posted* records. The job here is to flag billing mistakes *before* the invoice goes out so humans can hold or release; per Rule 7, the engine never blocks billing itself.

## New module

`utils/continuous_billing_verification.py` (~870 lines · 17 self-tests). Single public engine `ContinuousBillingVerificationEngine` exposing `verify(draft, contracts, extended_contracts) → VerificationResult` and `verify_batch(...)`.

## Five checks

| Check | Status drivers | Verdict impact |
| ----- | -------------- | -------------- |
| `CONTRACT_LIFECYCLE` | contract exists, draft_date ∈ [effective_from, effective_to] | FAIL → REJECT |
| `RATE_BAND` | applied_rate vs floor/ceiling | below floor → WARN/HOLD; above ceiling → FAIL/REJECT |
| `TAX_COMPUTATION` | computed_tax ≈ amount × (1−discount) × tax_rate, 1% tolerance + KES 5 floor | FAIL → REJECT |
| `DISCOUNT_AUTH` | discount > 0 needs authorization_id | FAIL → REJECT |
| `DISCOUNT_BAND` | discount ≤ ExtendedContractRate.max_discount_pct | FAIL → REJECT |

Verdict aggregation: any FAIL → `REJECT_RECOMMENDED`; otherwise any WARN → `HOLD_PENDING_REVIEW`; otherwise `PASS`. SKIPPED checks (missing optional inputs) don't drive verdict.

## Compositional reuse

- `ContractRate` from ENH-242 — NOT redefined; imported and reused with an `ExtendedContractRate` sidecar for `max_discount_pct`. Keeps ENH-242 pristine.
- `ValidationSeverity` from ENH-241 — same severity vocabulary across all six revenue_assurance engines.

## Tax-on-net-of-discount discipline

Tax base is `proposed_amount × (1 − discount_pct)`, NOT the gross. CBV-04 scenario verifies this: amount 10k × 0.90 net × 0.16 VAT = KES 1440 expected. Common production bug to compute tax on gross then apply discount; engine catches both.

## Scenario library

- **CBV-01** clean draft → PASS (3 assertions)
- **CBV-02** below-floor rate → HOLD_PENDING_REVIEW with WARN check status (2 assertions)
- **CBV-03** unauthorised 20% discount → REJECT_RECOMMENDED (3 assertions)
- **CBV-04** tax-on-net-of-discount validation → PASS (2 assertions)

10/10 PASS.

## Standards registry

ENH-246 activated: `planned → active`, `v10.40+ → v10.55`,
`affected_engines: ("revenue_assurance",) → ("continuous_billing_verification",)`. Description rewritten to capture all 5 checks + verdict aggregation + tax-base discipline + Rule 1/7 contracts.

## Verification

- `python3 -m utils.continuous_billing_verification` → ✓ 17 tests
- `python3 scripts/audit.py` → **132/132 PASS**
- `python3 scripts/structure_audit.py` → STABLE (320 modules · 801 imports · HARD=3)
- All upstream engines: no regression

## Honest scope notes

1. **No FX handling.** Foreign-currency drafts must be converted to KES before verification.
2. **No customer-eligibility check.** "Account in good standing" is out of scope; that requires CRM lookup which doesn't belong here.
3. **No partial-payment scenarios.** Engine treats each draft as full-amount; instalment billing requires a `BillingSchedule` shape not currently present.
4. **`ExtendedContractRate` is a sidecar.** Max-discount data didn't fit cleanly into ENH-242's `ContractRate` without breaking that contract; sidecar was the cleanest move. Closure cockpit will need to load both.

## Files changed

- **NEW** `utils/continuous_billing_verification.py`
- **MOD** `utils/standards_registry.py` (ENH-246)
- **MOD** `utils/scenario_simulator.py` (+4 CBV-*)

**Next:** v10.56 ENH-247 Commission & Incentive Assurance.
