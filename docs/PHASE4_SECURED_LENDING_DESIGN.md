# Phase 4 — Secured Lending, Security Perfection & FX-Normalized Reporting
## Design Document (for sign-off — NO code until approved)

Date: 2026-06-16 · Author: hardening sprint · Status: **DRAFT FOR REVIEW**
Grounding: collateral_register (db.py), FxRate/FxRateType (consolidated_tb_engine.py),
credit_admin_disburse gate (api_credit_admin_routes.py:247), app.created_by attribution.

---

## 0. Decisions locked (from Josh)

1. **FCY/LCY = Foreign Currency / Local Currency**, a *universal reporting
   dimension* across loans, deposits, and executive reporting. MD dashboards
   support LCY and FCY book analysis.
2. **FX-normalized architecture.** Store native amount, currency, FX rate, KES
   equivalent, rate date, rate source. Pilot uses an **admin-maintained FX rate
   table**.
3. **Security perfection HARD-GATES disbursement.** Disbursement blocked until all
   mandatory legal / collateral / insurance / perfection requirements are met.
   **Controlled override workflow with full audit trail** is included.
4. **Secured vs unsecured facility model.** Unsecured → affordability workflow.
   Secured → legal review, collateral, valuation, insurance, coverage-ratio,
   perfection.

---

## 1. Facility classification — the branch point

A new field `facility_security_type` on the application drives the whole workflow:

```
facility_security_type ∈ { "unsecured", "secured" }
security_subtype (secured only) ∈ { "mortgage", "debenture", "chattel",
    "cash_cover", "guarantee", "lien", "mixed" }
```

Derivation: default from the product (products.json class) but **RM-overridable at
submit-to-credit**, validated by credit. Unsecured facilities skip the entire
perfection sub-workflow; their disburse gate checks only affordability + standard
conditions. Secured facilities must pass the perfection gate (§5).

**Doctrine alignment:** the *classification* is config-influenced (product default)
but the *gate enforcement* is hardcoded — config never lets a secured facility
skip perfection.

---

## 2. Conditions Precedent vs Conditions Subsequent — first-class objects

Today conditions are flat strings (`"type": str(c)`). Promote to a typed object,
each row a record (table `facility_conditions`, §9):

```
condition {
  id, application_id, case_id,
  text, condition_type (from lms_config.condition_types),
  classification ∈ { "precedent", "subsequent" },   # CP must be met BEFORE disburse
  mandatory: bool,                                   # mandatory CP blocks the gate
  status ∈ { "open", "in_progress", "satisfied", "waived" },
  owner_staff_code, evidence_document_id,
  due_date,                                          # CS typically has post-disburse due date
  satisfied_by, satisfied_at, waived_by, waiver_reason, waived_at,
  created_at, updated_at
}
```

Gate rule: **all mandatory `precedent` conditions must be `satisfied` (or formally
`waived` via override) before disbursement.** `subsequent` conditions do NOT block
disbursement but are tracked with due dates and feed a post-disbursement
monitoring queue (and BSC operational-excellence KPIs).

---

## 3. Legal Review workflow

New object `legal_review` (one per secured application; table §9):

```
legal_review {
  id, application_id,
  assigned_officer_code, assigned_officer_name,    # the Legal Officer role
  status ∈ { "not_started", "in_review", "queries_raised", "cleared", "rejected" },
  comments[] { author_code, text, at },
  outcome ∈ { null, "approved", "approved_with_conditions", "rejected" },
  conditions_raised[] -> facility_conditions ids,  # legal can raise CP/CS
  started_at, completed_at
}
```

- Introduces the **Legal Officer role** (new canonical role + React surface).
- A secured facility cannot reach `cleared_for_disbursement` unless
  `legal_review.outcome ∈ {approved, approved_with_conditions}`.
- State machine is hardcoded; transitions audited (LEGAL_REVIEW_*).

---

## 4. Security Perfection workflow

New object `security_perfection` (one per security instrument; table §9):

```
security_perfection {
  id, application_id, collateral_id (-> collateral_register),
  security_type ∈ security_subtype,
  registration_status ∈ { "pending", "lodged", "registered", "failed" },
  registration_reference,                          # e.g. charge no., debenture reg no.
  registration_date,
  perfection_status ∈ { "unperfected", "in_progress", "perfected", "lapsed" },
  perfecting_officer_code, notes,
  created_at, updated_at
}
```

- For a **debenture**: registration_reference = Companies Registry charge no.;
  perfection requires `registered` + (if applicable) a stamped debenture document.
- Gate rule: every mandatory security instrument must be `perfected`.
- Lapsed perfection (e.g. charge expiry) raises a monitoring alert.

---

## 5. Insurance workflow

New object `insurance_policy` (link to collateral; reuse collateral_register
insurance_expiry, add structure; table §9):

```
insurance_policy {
  id, collateral_id, application_id,
  insurer, policy_number, sum_insured, currency,
  effective_date, expiry_date,
  bank_interest_noted: bool,                       # bank noted as loss payee/co-insured
  status ∈ { "active", "expired", "cancelled", "pending" },
  renewal_alert_days (default 30),
  created_at, updated_at
}
```

- Gate rule (secured, where insurance is mandatory): an `active`, unexpired policy
  with `bank_interest_noted = true` must exist.
- **Renewal alerts**: a daily check flags policies within `renewal_alert_days` of
  expiry → monitoring queue + RM/credit-admin notification surface.

---

## 6. Collateral workflow & coverage ratio

Reuse `collateral_register` (already has market_value, forced_sale_value,
loan_outstanding, ltv, valuation dates, valuer). Add **facility linkage**:

```
collateral_facility_link {
  id, collateral_id, application_id,
  allocated_value,                  # portion of collateral allocated to this facility
  created_at
}
```

Coverage ratio (computed, not stored as source of truth):

```
coverage_ratio = Σ(forced_sale_value of linked collateral, KES-equiv)
                 / facility_amount_kes_equiv
```

- Gate rule (secured): `coverage_ratio >= min_coverage_ratio` (config threshold per
  security_subtype, e.g. mortgage 1.25, debenture 1.50). Threshold is **config**;
  the *check* is hardcoded.
- Valuation freshness: `last_valuation` within config max-age, else gate fails.

---

## 7. The disbursement HARD-GATE + override

Hook: `credit_admin_disburse` (api_credit_admin_routes.py:247), before clearing.

```
def perfection_gate(case, app):
    if app.facility_security_type == "unsecured":
        return ok_if(all mandatory CP satisfied)        # affordability path unchanged
    checks = [
        legal_review.outcome in {approved, approved_with_conditions},
        all mandatory security_perfection.perfection_status == "perfected",
        insurance active & unexpired & bank_interest_noted (where mandatory),
        coverage_ratio >= min_coverage_ratio,
        valuation fresh,
        all mandatory precedent conditions satisfied,
    ]
    return GateResult(passed = all(checks), failures = [...])
```

If `not passed` → **HTTP 400** with a structured `failures[]` list (each: check,
reason, what's needed). Disbursement cannot proceed.

**Controlled override** (separate endpoint, distinct permission
`can_override_perfection`, e.g. CRO/Head of Credit only):

```
POST /api/credit-admin/{case_id}/perfection-override
body { failures_acknowledged[], justification (required, min length),
       approver_authority }
-> records override { who, when, justification, the exact failures bypassed }
-> audit PERFECTION_OVERRIDE (high-severity, immutable trail)
-> only THEN may disburse proceed, and the disbursement record is flagged
   `disbursed_under_override = true`
```

Override is logged to the append-only audit trail and surfaced on the MD dashboard
as a risk indicator (overrides are a governance metric, not a quiet bypass).

---

## 8. FCY/LCY + FX-normalized reporting architecture

### 8.1 Money fields — every monetary record carries the normalized set

```
amount_native        NUMERIC(20,2)   # the contractual amount
currency             VARCHAR(3)      # ISO: KES, USD, EUR, GBP...
fx_rate              NUMERIC(18,8)   # native -> KES at booking
amount_kes           NUMERIC(20,2)   # = amount_native * fx_rate (KES-equiv)
fx_rate_date         DATE
fx_rate_source       VARCHAR(50)     # "admin_table" for pilot
currency_book        VARCHAR(3)      # derived: "LCY" if KES else "FCY"
```

Applies to: pipeline deals, loan applications, credit-admin cases, disbursements,
collateral values, insurance sums, **and deposit records** (deposits gain the same
LCY/FCY tag for book analysis).

### 8.2 Admin-maintained FX rate table (model on existing FxRate/FxRateType)

```
fx_rates {
  id, currency_pair (e.g. "USD/KES"),
  rate NUMERIC(18,8), rate_type ∈ { "mid", "buy", "sell" },
  effective_date, source ("admin"), entered_by, created_at,
  active: bool
}
```

- Resolution reuses the `_resolve_fx_rate` pattern already in
  consolidated_tb_engine.py (latest active rate ≤ value date for the pair/type).
- Booking stamps the rate used (so historical amounts don't drift when rates
  change). Revaluation (re-stating open exposures at current rate) is a *reporting*
  computation, not a rewrite of booked amounts.
- Admin UI (Phase 4 React): maintain the rate table, view rate history.

### 8.3 Reporting dimension

LCY/FCY becomes a slice on every monetary aggregate:
`total_loan_book = { LCY: Σamount_kes where currency=KES, FCY: Σamount_kes where currency≠KES }`.
Same for deposits, pipeline value, disbursements. MD dashboard exposes the split.

---

## 9. PostgreSQL schema recommendations

New tables (all with created_at/updated_at, JSONB `data` escape hatch, indexed on
application_id):

| Table | Purpose |
|---|---|
| `facility_conditions` | CP/CS first-class objects (§2) |
| `legal_reviews` | legal review per application (§3) |
| `security_perfections` | perfection per instrument (§4) |
| `insurance_policies` | structured insurance (§5) |
| `collateral_facility_links` | collateral ↔ facility linkage (§6) |
| `fx_rates` | admin-maintained rate table (§8.2) |
| `perfection_overrides` | override audit (§7) |

Extend existing:
| Table | Add |
|---|---|
| `loan_applications` (data JSONB) | facility_security_type, security_subtype, money-normalized set |
| `pipeline_deals` | money-normalized set (currency exists; add fx_rate/amount_kes/book) |
| `credit_admin` cases | disbursed_under_override flag, gate_snapshot |
| `collateral_register` | (already rich) — link via collateral_facility_links |
| deposits table | currency_book LCY/FCY tag |

Migration discipline: idempotent, non-destructive scripts (CREATE TABLE IF NOT
EXISTS, ALTER ... ADD COLUMN IF NOT EXISTS); backfill currency_book from currency;
default existing facilities to `unsecured` then let credit reclassify.

---

## 10. BSC impact points

| Event | KPI(s) affected | Attributed to |
|---|---|---|
| Legal review cleared | Operational excellence / TAT | legal officer |
| Perfection completed | Operational excellence; risk quality | perfecting officer + owner RM |
| Insurance lapse/renewal handled | Operational excellence | credit admin |
| Coverage ratio maintained | Risk / asset quality | owner RM |
| CS satisfied by due date | Operational excellence | owner RM |
| **Override used** | Risk/governance (negative signal) | approver (visible to MD) |
| Disbursement (existing) | Loan book growth, disbursements | owner RM (via emit_bsc_for, HB1) |

Extends the HB1 `emit_bsc_for([owner, actor])` pattern to the new events.

---

## 11. Executive dashboard drill-down requirements (Phase 5 link)

Every secured-lending metric must drill:

```
Loan Book (LCY/FCY toggle)
  → by branch → by RM → by facility → facility detail (perfection state)
Perfection Pipeline
  → unperfected facilities → by stage (legal/registration/insurance) → facility
Coverage Health
  → facilities below min coverage → facility → collateral detail
Insurance Expiry
  → policies expiring ≤30d → policy → facility
Overrides (governance)
  → override list → override detail (justification, failures bypassed)
Conditions Subsequent
  → overdue CS → facility → condition
```

No static tiles — each is a navigation entry point.

---

## 12. React UI requirements

New surfaces:
- **Legal Officer workspace** — review queue, application detail with legal panel
  (assign, comment, raise condition, clear/reject). New role + route guard.
- **Security Perfection panel** (on credit-admin case detail) — per-instrument
  registration + perfection status, references, dates.
- **Insurance panel** — policy capture, expiry, bank-interest flag, renewal badges.
- **Collateral linkage panel** — link collateral to facility, live coverage ratio
  with pass/fail against threshold.
- **CP/CS manager** — split lists, satisfy/waive actions, due dates for CS.
- **Disbursement gate display** — a checklist showing each gate item pass/fail with
  "what's needed"; disburse button disabled until green OR override path.
- **Override modal** — justification (required), authority, failures acknowledged.
- **FX admin** — maintain rate table; **LCY/FCY toggle** on dashboards.

Reuse existing primitives (Card, Badge, Timeline, Wf* panel pattern). Zero new npm
deps target maintained.

---

## 13. Build sequence (proposed batches — each verified + shipped)

| Batch | Scope | Depends on |
|---|---|---|
| **P4-1** | FX foundation: fx_rates table + resolver + money-normalized fields + backfill; admin FX UI; LCY/FCY tag. Non-gating, safe first step. | — |
| **P4-2** | Facility classification (secured/unsecured) + CP/CS first-class objects (backend + React CP/CS manager). | P4-1 |
| **P4-3** | Collateral linkage + coverage ratio + valuation freshness (backend + panel). | P4-2 |
| **P4-4** | Legal Review workflow + Legal Officer role + React workspace. | P4-2 |
| **P4-5** | Security Perfection + Insurance workflows + panels. | P4-3, P4-4 |
| **P4-6** | The HARD-GATE on disburse + controlled override + audit + gate display. | P4-3,4,5 |
| **P4-7** | BSC impact points for new events; dashboard LCY/FCY + drill-down (merges into Phase 5). | all |

Each batch: design-aligned, py_compile + pytest in sandbox, tsc gate in your env,
ZIP delivery, idempotent migration script, commit per batch, push at phase
boundary. Simulation harness extended per batch to keep the chain green.

---

## 14. Open questions for sign-off

1. **Min coverage ratios** per security_subtype — your numbers (e.g. mortgage 1.25,
   debenture 1.50)? Or start with placeholders you tune in admin config?
2. **Valuation max-age** before a revaluation is required (e.g. 12 months)?
3. **Override authority** — which roles can override the gate? (Proposed: CRO +
   Head of Credit only.)
4. **Insurance mandatory** for which subtypes? (Proposed: mortgage + chattel + asset
   finance; not cash-cover.)
5. **Deposits table** — confirm the table/source so we add the LCY/FCY tag in the
   right place (CBS-derived vs a deposits register?).
6. **CS overdue consequence** — monitoring/alert only, or does it affect facility
   standing/BSC penalty?

Answer these and P4-1 (FX foundation) can start — it's the safe, non-gating base
every later batch builds on.

---

## DELTA (post sign-off) — decisions applied

**Coverage ratios → Admin-configurable Credit Policy Matrix** (no hardcoded
values). Pilot defaults: Cash/Fixed Deposit 100%, Residential Property 125%,
Commercial Property 120%, Motor Vehicle 130%, Debenture 150%, Stock/Inventory
150%. Stored in `data/credit_policy_matrix.json`; the *check* is hardcoded, the
*thresholds* are config. (Built in P4-3.)

**Override authority — tiered:** Standard facilities → Head of Credit OR Chief
Risk Officer. High-value facilities → Head of Credit AND Chief Risk Officer AND
Managing Director. Full audit history on every override. (Built in P4-6.)

**Deposits — CBS/Flexcube is system of record.** Implement a **CBS Deposit
Snapshot** model (not a standalone register); currency captured at account level,
aggregated to LCY/FCY reporting dimensions. (Built in P4-7 / dashboard.)

**Security Classification gradient** (NEW — replaces the binary secured/unsecured
for routing/reporting; derived from coverage vs the matrix-required ratio):
```
security_classification ∈ {
  "unsecured",          # no acceptable collateral linked
  "partially_secured",  # 0 < coverage_ratio < required_ratio
  "fully_secured",      # required_ratio <= coverage_ratio <= over_secured_band
  "over_secured",       # coverage_ratio > over_secured_band (e.g. > 1.0x required *
                        #   over_secured_multiple, admin-config)
}
```
Drives: workflow routing, document requirements, perfection requirements, and
executive reporting. `facility_security_type` (secured/unsecured) is retained as
the coarse switch; `security_classification` is the computed gradient. (Computed
in P4-3 once coverage is live.)

## P4-1 — FX Foundation: DELIVERED (this batch)

- `utils/fx_engine.py` — operational FX layer (separate from IAS-21 consolidation
  engine): `FxRateStore` (JSON-backed, admin-maintainable, history-preserving),
  `resolve_rate` (latest active rate ≤ as_of, KES→1), `normalize_money` (stamps
  amount_native/currency/fx_rate/amount_kes/fx_rate_date/fx_rate_source/
  currency_book), `currency_book` (LCY/FCY).
- `data/fx_rates.json` — KES base + pilot USD/EUR/GBP rates (admin-editable).
- `scripts/seed_fx_rates.py` — idempotent seed/verify.
- `tests/test_p4_1_fx_foundation.py` — 12 tests (resolution, history, rate-type
  separation, inactive/missing → loud error, KES passthrough, corrupt-file loud,
  absent-file first-run).
- Non-gating: nothing in the live credit chain is wired to it yet. P4-1b will add
  the FX admin API + React surface and begin stamping money fields at booking.

## P4-1b — Money stamping at booking + FX admin API: DELIVERED

- Pipeline create now stamps the normalized money set onto the deal
  (fx_engine.stamp_money_fields) — additive + resilient (never blocks create if a
  currency is unconfigured; currency_book is always computed). PipelineDeal has
  extra="allow" so the fields round-trip in the response with no model change.
- FX fields persisted through _db_sync_pipeline_deal metadata (fx_rate,
  amount_kes, fx_rate_date, fx_rate_source, currency_book).
- FX admin API:
  - GET  /api/fx/rates       (auth; list, optional currency/active filter)
  - GET  /api/fx/resolve     (auth; resolve a rate, 404 if missing)
  - POST /api/fx/rates       (admin-only; upsert, audited API_FX_RATE_UPSERT)
- Tests: tests/test_p4_1b_money_stamping.py (4) — USD/KES/unconfigured/no-clobber.
- Harness: asserts created deal carries currency_book (FX stamp) — keeps the
  live chain proving FX end-to-end.
- Still non-gating: disbursement is unaffected. Next: P4-1c React FX admin
  surface + LCY/FCY toggle (needs tsc gate in Josh's env).

## P4-1c — React FX admin surface: DELIVERED (frontend — needs tsc gate)

- types/fx.ts — FxRate, FxRatesResponse, FxResolveResponse, FxRateUpsert*,
  NormalizedMoney, CurrencyBook ('LCY'|'FCY'), FxRateType ('mid'|'buy'|'sell').
- lib/api.ts — fetchFxRates, resolveFxRate, upsertFxRate.
- hooks/useFxRates.ts (list), hooks/useFxMutations.ts (upsert, MutationResult).
- pages/FxRates.tsx — rate table grouped by currency + LCY/FCY badge; admin-only
  add/update editor (server also enforces admin on POST). KES shown as base.
- App.tsx route /fx-rates; Sidebar nav item 'FX Rates' gated visibleFor isAdmin.
- Syntax-checked via esbuild; **canonical gate is `pnpm tsc --noEmit` in Josh's
  env** — a frontend round-trip may surface minor type fixes (expected for FE
  batches).

**FX foundation (P4-1 / 1b / 1c) is now complete:** admin rate table, resolver,
money stamping at booking, API, and admin UI. Next: P4-2 — facility
classification (unsecured/partially/fully/over-secured) + CP/CS as first-class
objects (backend + React).

## P4-2 — Facility classification + CP/CS first-class objects: DELIVERED (backend)

- core.py create_case_from_application: conditions now carry `classification`
  ("precedent"|"subsequent"), `mandatory`, `due_date` (default mandatory
  precedent — safe, blocks until reclassified). Case carries
  `facility_security_type` + `security_subtype`.
- core.py create_from_pipeline_deal: application now inherits the deal's
  currency + normalized money set (fx_rate/amount_kes/currency_book/...) and
  carries facility_security_type/security_subtype (so FCY/LCY + classification
  flow pipeline -> LMS -> credit admin). Fixed the hardcoded currency="KES".
- CreditAdminManager: set_facility_classification, classify_condition,
  outstanding_mandatory_cp (pure gate-input helper for P4-6).
- API: POST /api/credit-admin/cases/{id}/conditions/classify and
  /classify-facility (manager-tier, in-scope, audited).
- Tests: tests/test_p4_2_cp_cs_classification.py (4) — outstanding-CP logic,
  safe defaults, classify mutation, facility classification.
- Harness: classify-facility check added.
- NON-GATING: the disburse gate is NOT yet enforced on these (that is P4-6,
  once legal/perfection/insurance/coverage exist to gate on). Next: P4-2b React
  CP/CS panel, then P4-3 collateral + coverage ratio.

## P4-3 — Collateral linkage + coverage ratio + Credit Policy Matrix: DELIVERED (backend)

- data/credit_policy_matrix.json — admin-configurable required coverage % per
  collateral type (Cash/FD 100, Residential 125, Commercial 120, Motor 130,
  Debenture 150, Stock/Inventory 150); over_secured_multiple 1.25;
  valuation_max_age_days 365. No hardcoded ratios.
- utils/collateral_coverage.py — pure engine: CreditPolicyMatrix (loud-on-corrupt,
  conservative-on-absent), compute_coverage_ratio (FSV KES capped at allocation /
  facility KES), classify_security (unsecured/partially/fully/over gradient),
  assess_facility. FX-aware (normalizes native collateral values via fx_engine).
- core.py CreditAdminManager: link_collateral / unlink_collateral (snapshot the
  security value on the link) + _recompute_coverage (writes coverage_ratio,
  required_ratio, security_total_kes, security_classification onto the case).
- API: POST /collateral/link, /collateral/unlink, GET /policy-matrix (auth).
- Tests: test_p4_3_coverage.py (9) + test_p4_3_link_recompute.py (2).
- Harness: link collateral -> assert coverage computed + classification set.
- Over-secured boundary uses over_secured_multiple (1.25) — CONFIRM Ecobank's
  real definition before go-live (see matrix _over_secured_note).
- NON-GATING still: coverage/classification computed + surfaced; the disburse
  HARD-GATE that consumes them is P4-6. Next: P4-4 Legal Review + P4-5
  Perfection/Insurance, then P4-6 gate, then combined React (P4-2b/3b/4b/5b).

## P4-4 — Legal Review workflow: DELIVERED (backend)

- core.py CreditAdminManager: _ensure_legal_review (lazy init on existing cases),
  assign_legal_officer (-> in_review), add_legal_comment (raises_query ->
  queries_raised), set_legal_outcome (approved/approved_with_conditions/rejected
  -> cleared/rejected). legal_review { status, assigned_officer_code/name,
  outcome, comments[], started_at, completed_at, completed_by }.
- Pure gate-input legal_blocks_disbursement(case): secured facilities require a
  cleared legal outcome; unsecured never blocked.
- API: POST /cases/{id}/legal/assign, /legal/comment, /legal/outcome —
  authorized by _can_perform_legal (admin | role~legal | manager-tier), in-scope,
  audited (CREDIT_ADMIN_LEGAL_*).
- Legal Officer role: pilot uses the capability check above; the canonical
  Legal Officer role + React workspace land with the hierarchy rework / React
  pass. Tests: test_p4_4_legal_review.py (3).
- Harness: legal assign -> clear check.
- NON-GATING still (gate is P4-6). Next: P4-5 Security Perfection + Insurance.

## P4-5 — Security Perfection + Insurance workflows: DELIVERED (backend)

- core.py CreditAdminManager:
  - Perfection: add_security_perfection, update_security_perfection. Object:
    { id, security_type, registration_status (pending/lodged/registered/failed),
    registration_reference, registration_date, perfection_status
    (unperfected/in_progress/perfected/lapsed), perfecting_officer_code, notes }.
  - Insurance: add_insurance_policy, update_insurance_policy. Object: { id,
    collateral_id, insurer, policy_number, sum_insured, currency, effective_date,
    expiry_date, bank_interest_noted, status (active/expired/cancelled/pending),
    renewal_alert_days }.
  - Gate helpers (pure): perfection_blocks_disbursement (secured: every
    instrument must be perfected; none-yet blocks), has_valid_insurance (active +
    bank-interest-noted + unexpired), insurance_blocks_disbursement (blocks when
    required and no valid policy; the `required` decision is the P4-6 gate's,
    per config).
- API: POST /perfection, /perfection/{id}/update, /insurance, /insurance/{id}/update
  (Legal/manager-gated, in-scope, audited CREDIT_ADMIN_PERFECTION/INSURANCE_*).
- Tests: test_p4_5_perfection_insurance.py (4). Harness: add perfection -> mark
  perfected; add insurance policy.
- OPEN (Q4): which subtypes make insurance MANDATORY (proposed mortgage/chattel/
  asset; not cash-cover). P4-6 reads this from config; default proposal applied.
- This is the LAST non-gating batch. Next: P4-6 wires the disburse HARD-GATE +
  tiered override consuming outstanding_mandatory_cp + legal + perfection +
  insurance + coverage. Then combined React + full simulation.

## P4-6 — Disbursement HARD-GATE + tiered override: DELIVERED (backend) — GATING

- core.py CreditAdminManager.evaluate_disbursement_gate(case): returns
  {passed, failures[], secured, overridden}. Unsecured -> only mandatory CP.
  Secured -> CP + legal cleared + all security perfected + valid insurance
  (where required per matrix) + coverage fully/over-secured + fresh valuations.
  An authorized override covering the current failures clears the gate.
- Wired into credit_admin_disburse: secured facility failing the gate -> 400 with
  structured failures[] + override hint. Disbursing under override sets
  disbursed_under_override=True and emits CREDIT_ADMIN_DISBURSED_UNDER_OVERRIDE.
- Tiered controlled override: request_perfection_override (snapshots current
  failures + justification), add_override_approval. Standard facility -> any one
  of {Head of Credit, CRO}; high-value (>= high_value_threshold_kes, config 100M)
  -> all of {Head of Credit, CRO, MD}. Authority from caller role
  (_override_role); admin acts as MD-equivalent for testing. Fully audited.
- API: GET /disbursement-gate (read), POST /perfection-override/request,
  /perfection-override/approve.
- Config: credit_policy_matrix.json += insurance_required_subtypes,
  high_value_threshold_kes.
- Case now inherits currency/amount_kes/currency_book/fx_rate from the app
  (coverage + high-value math + FCY/LCY dashboards).
- Tests: test_p4_6_gate_override.py (5) — unsecured CP-only, secured ready
  passes, per-requirement blocking, standard single-authority override, high-
  value three-signature override. Full P4 suite: 43 tests green together.
- Harness: GET disbursement-gate asserts passed before disburse (secured deal
  set up to satisfy all controls).
- BACKWARD COMPATIBLE: gate only bites facilities explicitly classified secured;
  facility_security_type defaults unsecured, so legacy cases disburse as before.

### Phase 4 backend COMPLETE (P4-1..P4-6). Remaining:
- Combined React pass (FX consumed on dashboards + CP/CS panel + collateral/legal/
  perfection/insurance panels + gate checklist + override modal).
- Full live simulation as the integration gate (Josh runs at the end).

## P4-6b — Live enforcement probe + admin superuser override: DELIVERED

- core.py add_override_approval: an 'admin' approval is a documented pilot
  SUPERUSER override that satisfies any tier (standard or high-value). Real
  Head-of-Credit/CRO/MD roles still follow the tiered rules. Fully audited.
- api_credit_admin_routes override-approve: admin records as role 'admin'.
- scripts/simulate_credit_chain.py: negative_override_probe — builds a secured
  facility, sets up everything EXCEPT perfection, then asserts:
    1. disburse is BLOCKED (400) with 'security_perfection' in failures
    2. override request + approve -> authorized
    3. disburse SUCCEEDS and case flagged disbursed_under_override
- Tests: test_p4_6_gate_override.py +1 (admin override any tier) = 6.
- PILOT AFFORDANCE (flagged): admin superuser override is for pilot testing;
  production needs real HoC/CRO/MD seats so the 3-signature high-value control
  is genuinely three people.


## P4-6c — Override authority fix (probe-caught)

The live probe caught that a STANDARD facility's override stayed `pending` when
approved only by the MD. Root cause: required set for standard was {HoC, CRO},
excluding MD — but the MD outranks both and is always an acceptable approver.
Corrected model (add_override_approval):
  - Standard facility    -> ANY ONE of {Head of Credit, CRO, MD}
  - High-value facility  -> ALL THREE of {Head of Credit, CRO, MD}
  - 'admin' approval      -> pilot superuser, satisfies any tier (audited)
This is also the more faithful banking model. Tests unchanged (6 pass); live
probe now: blocked -> override authorized -> disburse under override.
