# Credit Factory Hardening — Phases 4–7 Certification

Date: 2026-06-16 · Baseline: simulation-green **69/69** (scripts/simulate_credit_chain.py)
Method: verified from code; every runtime claim is backed by a named assertion in
the live simulation against Josh's instance (Postgres, A2Z_USE_DB=true). No claim
is asserted from memory — this continues the CGR1 / Trap-#11 discipline.

This document certifies the secured-lending build (Phase 4) and the React pass,
and renders the sprint verdict (Phase 7). It builds on
`CREDIT_FACTORY_CERT_P1_P3.md` (Create Deal, parity matrix, BSC wiring).

---

## 1. What was built (Phase 4 — secured lending)

The reconciliation audit found that security perfection, legal review, conditions
precedent/subsequent, and insurance existed only as generic free-text condition
checkboxes — never as structured workflow, in **either** Streamlit or React. The
collateral register and legal-matters tracker existed but were unwired to the
facility lifecycle. Phase 4 closed that gap, backend-first, as six batches.

| # | Capability | Backend | React | Runtime evidence |
|---|---|---|---|---|
| P4-1 | FX foundation (admin rate table, KES-normalized money set) | utils/fx_engine.py | FxRates page | `deal carries currency_book` (both routes) |
| P4-1b | Money-set stamping on deal create | api.py + _db_sync metadata | — | same |
| P4-2 | Facility classification + CP/CS as first-class | core.py | CP/CS panel | `classify facility (secured/debenture)` |
| P4-3 | Collateral linkage + coverage engine | collateral_coverage.py | Collateral panel | `link collateral -> coverage computed`, `security_classification set` |
| P4-4 | Legal review (assign / comment / outcome) | core.py | Legal panel | `legal assign`, `legal cleared` |
| P4-5 | Security perfection + insurance | core.py | Perfection / Insurance panels | `add security perfection`, `mark perfection perfected`, `add insurance policy` |
| P4-6 | Disbursement HARD-GATE + tiered override | core.py + api_credit_admin_routes.py | DisbursementGatePanel | `disbursement gate passes (secured controls met)`, full negative probe |

All rows runtime-verified. The React surface (React-A / A2 / B) is `tsc`-clean and
consumes the proven backend contract.

---

## 2. Enforcement — proven BOTH directions

A control that only passes when satisfied is not proven; it must also *block* when
violated and be *overridable* only with authority. The negative+override probe
proves all three on the live API:

| Assertion | Result |
|---|---|
| Secured facility missing perfection → disburse returns 400 with `security_perfection` in `failures[]` | PASS |
| Override request (justification captured) | PASS |
| Override approved → `authorized` (MD authority, standard tier) | PASS |
| Disburse then SUCCEEDS under override | PASS |
| Case flagged `disbursed_under_override` (governance breadcrumb) | PASS |

Authority model (corrected during P4-6c, probe-caught): standard facility = any
one of {Head of Credit, CRO, MD}; high-value (≥ KES 100M) = all three. The MD is
always an acceptable approver. Every override step is audited.

---

## 3. FCY/LCY reporting (React-B)

The MD dashboard now splits pipeline value into Local- and Foreign-currency books,
both in KES-equivalent, in both `pipeline_summary` code paths.

Runtime: `LCY=5,516,230,000, FCY=0.0`, reconciling exactly to `pipeline_value`.
This is the **correct** result for an all-KES synthetic portfolio — the dimension
is wired end-to-end (FX table → stamping → KES-normalized aggregation → dashboard)
and the FCY bucket sits ready at zero until foreign-currency business arrives. The
harness asserts LCY+FCY reconciles to the headline, so the split cannot drift.

---

## 4. VERDICT: READY WITH FIXES (pilot-ready)

The credit factory and its secured-lending controls are faithfully migrated to
React and proven end-to-end. This is **not** an unconditional "ship it": three
items are pilot-scoped and must change before a production deployment, and three
are explicitly deferred. Stating them is the certification — a verdict that hid
them would be the checklist theater this sprint set out to avoid.

### 4a. PROVEN (runtime-verified, ready)
- Full credit chain: create → advance → doc-gate → submit → LMS (authority +
  committee) → offer loop → CALMS case → disburse. Both routes, 69/69.
- Secured-lending controls: classification, coverage, legal, perfection,
  insurance, CP/CS — as structured workflow, enforced at disbursement.
- Disbursement hard-gate + tiered controlled override, blocking and unblocking
  proven, fully audited.
- FX normalization and FCY/LCY pipeline reporting.
- Cascade scope guard; owner-attributed BSC through the chain (Phase 3).

### 4b. PILOT-SCOPED — must change before production
1. **Override superuser shortcut.** An `admin` approval satisfies any override
   tier (so the pilot can be exercised by one persona). Production needs distinct
   Head-of-Credit, CRO, and MD seats so the high-value 3-signature control is
   genuinely three people — otherwise one admin can clear a high-value override,
   defeating segregation of duties.
2. **Real authority seats.** Same root cause as (1): the canonical role hierarchy
   needs HoC / CRO / Legal Officer seats provisioned (currently deferred to the
   hierarchy rework).
3. **Security hardening** (from POLICY_GAPS): password policy (GAP-001/005), API
   rate limiting (GAP-006), and the `users.json` tracking decision remain open.

### 4c. CONFIG — confirm with Ecobank (not code)
- Coverage ratios + over-secured boundary (currently pilot placeholders).
- `insurance_required_subtypes` (currently property/vehicle/stock proposal; not
  cash-cover or debenture-only).
- `high_value_threshold_kes` (currently KES 100M).

### 4d. DEFERRED (named, out of this sprint)
- CBS Deposit Snapshot — deposit-side FCY/LCY (only the lending side is wired).
- Executive drill-down by branch / RM / product (Phase 5; pairs with hierarchy
  rework) — `md_dashboard` is currently flat.
- UX polish pass (Phase 6).

---

## 5. Recommendation

Cleared for **pilot demonstration as a prospect-tenant pitch** — the credit
factory tells a complete, honest, runtime-proven story end-to-end. Before any
production deployment with real customer data, close 4b (1)–(3) and confirm 4c
with the bank. 4d items are roadmap, not blockers for the pitch.

Evidence of record: `scripts/simulate_credit_chain.py` (69/69),
`docs/PHASE4_SECURED_LENDING_DESIGN.md`, the P4 test suite (43 + probe/override),
and `CREDIT_FACTORY_CERT_P1_P3.md`.
