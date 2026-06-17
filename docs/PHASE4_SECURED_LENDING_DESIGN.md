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

## React-A — Disbursement gate UI + override + data layer: DELIVERED (frontend — tsc gate)

- types/creditAdmin.ts: CP/CS condition fields; SecurityClassification; LinkedCollateral,
  LegalReview, SecurityPerfection, InsurancePolicy, PerfectionOverride, GateFailure,
  DisbursementGate; all P4 request bodies.
- lib/api.ts: full P4 fetcher set (classifyCondition/Facility, link/unlinkCollateral,
  legalAssign/Comment/Outcome, add/updatePerfection, add/updateInsurance,
  requestOverride/approveOverride, fetchDisbursementGate).
- components/DisbursementGatePanel.tsx (NEW): self-contained — reads /disbursement-gate,
  renders the green/red control checklist; when blocked, a controlled-override flow that
  shows the authority TIER (high-value: HoC AND CRO AND MD; standard: any one) with
  per-role approval badges, justification capture, request + approve. Self-hides for
  unsecured facilities.
- pages/CreditAdminCaseDetail.tsx: renders DisbursementGatePanel above the disburse panel.
- Syntax-checked via esbuild; canonical gate is `pnpm tsc --noEmit`.
- NEXT (React-A2): per-domain entry panels (facility classify, CP/CS classify, collateral
  link, legal, perfection, insurance) so credit-admin can SET what the checklist reads.
  Then React-B: FCY/LCY dashboard consumption.

## React-A2 — secured-lending entry panels: DELIVERED (frontend — tsc gate)

- types/creditAdmin.ts: P4 fields promoted to first-class optionals on
  CreditAdminCase (facility_security_type, security_subtype,
  security_classification, coverage_ratio, required_ratio, currency,
  currency_book, amount_kes, linked_collateral, legal_review,
  security_perfections, insurance_policies, perfection_override,
  disbursed_under_override).
- components/SecuredLendingPanels.tsx (NEW): six self-contained panels —
  FacilityClassificationPanel (secured/unsecured + subtype, shows coverage +
  classification badge), CollateralPanel (link/unlink, live coverage table),
  ConditionsCpCsPanel (precedent/subsequent classify), LegalReviewPanel
  (assign/comment/approve/reject), PerfectionPanel (add instrument + mark
  perfected), InsurancePanel (add policy + bank-interest-noted). Shared useAction
  hook (busy + toast + onChange). Legal/perfection/insurance self-hide for
  unsecured facilities.
- pages/CreditAdminCaseDetail.tsx: renders the six panels above the gate panel,
  each wired to refetch on change so the gate checklist updates live.
- Syntax-checked via esbuild; canonical gate is `pnpm tsc --noEmit`.
- Credit-admin can now drive the full secured workflow from the UI and watch the
  disbursement gate clear control-by-control.
- NEXT: React-B (FCY/LCY dashboard consumption), then Phase 7 certification.

## React-B — FCY/LCY dashboard split: DELIVERED (backend + frontend)

- utils/api.py pipeline_summary: BOTH code paths now emit lcy_value/fcy_value.
  - DB-first path: SQL split on currency column, summing KES-equivalent
    COALESCE((metadata->>'amount_kes')::numeric, amount, 0). metadata is JSONB
    DEFAULT '{}' so extraction is safe.
  - Canonical-manager path: accumulators using amount_kes (native fallback),
    book = currency_book or derived from currency (non-KES -> FCY).
  - md_dashboard passes lcy_value/fcy_value through the pipeline block.
- frontend types/dashboard.ts: pipeline.lcy_value/fcy_value optionals.
- frontend pages/Dashboard.tsx: two tiles below the pipeline row — LCY (KES
  equiv) and FCY (KES equiv), each with % of pipeline.
- Harness: asserts the split is present AND LCY+FCY reconciles to pipeline_value.
- HONEST CAVEAT: split basis is KES-equivalent via amount_kes; the synthetic
  portfolio is all-KES, so FCY ~ 0 today — the value is structural readiness for
  when FCY deals appear, not a current numeric story. CBS Deposit Snapshot (for
  FCY/LCY on the deposit side) remains a separate pending item.
- Phase 4 + React pass COMPLETE. Next: Phase 7 certification (fresh full
  simulation + written verdict).

## React-B-fix — pipeline_value to KES-equivalent (probe-caught)

The FX currency probe (first live FCY deal: USD 1M -> 129.5M KES) surfaced that
pipeline_value summed NATIVE amounts (USD 1M counted as 1M) while lcy/fcy summed
KES-equivalent, so LCY+FCY != pipeline_value once any FCY deal existed. With
all-KES data this was invisible.

Fix (both pipeline_summary paths): ALL money sums are now KES-equivalent
(COALESCE(amount_kes, amount)) — pipeline_value, won_value, by_stage total_value,
validated/pending, lcy/fcy. This is also more correct: the MD reports in KES, and
summing mixed native currencies is meaningless. For all-KES data the numbers are
unchanged (amount_kes == amount at rate 1). Harness reconciliation assertion now
passes with an FCY deal present.

## #2 — Client-type-aware sector / MOU source: DELIVERED (backend + frontend)

DESIGN (assumption flagged to Josh): the third field's SOURCE switches by client
type (replace, not alongside). Business -> CBK sector; Individual -> MOU.
- Config: scripts/seed_sector_config.py seeds business_sectors (from CBK_SECTORS,
  14 classes) + allow_other_sector/mou into pipeline_settings.json — idempotent,
  backup-before-mutation, non-destructive (admin edits win).
- Endpoint /api/pipeline/stages now returns business_sectors (CBK, admin-config
  with constant fallback), individual_mous (active MOUs read LIVE from
  partnerships_mous.json — never duplicated), allow_other_sector/mou.
- Model PipelineDealCreate: + mou_id, mou_title (sector kept for Business).
  Persisted in deal metadata (_db_sync). extra="allow" already tolerated them.
- Frontend PipelineCreate: third field is client-type-aware — Business shows
  "Sector (CBK)" from business_sectors; Individual shows "Partnership / MOU" from
  individual_mous; both offer "Other…" -> free-text. Selections reset on client-
  type flip so no stale value rides along. Business sets sector; Individual sets
  mou_id + mou_title; "Other" sets the free text.
- Harness: config exposes CBK sectors + active MOUs; Individual deal carries
  mou_id; Business deal carries CBK sector.
- ADMIN-CONFIGURABLE per Josh's steer: extend CBK sectors by editing
  pipeline_settings.business_sectors; MOUs are managed in the partnerships
  register. No code change to extend either.

## #3a — Analytics enrichment (backend): DELIVERED

- _deal_value now returns KES-equivalent (amount_kes fallback deal_value) — the
  ENTIRE pipeline analytics endpoint is now in the bank's reporting currency,
  consistent with pipeline_summary. All-KES data unchanged.
- _compute_pipeline_analytics adds three cross-cutting breakdowns over live deals:
  - by_product: [{product, value, count, won_value}] sorted desc.
  - by_sector: CBK sector (Business); Individual/MOU deals grouped as
    "Individual / Partnership". [{sector, value, count}] sorted desc.
  - by_currency_book: {LCY:{value,count}, FCY:{value,count}}.
- Harness: by_product / by_sector / by_currency_book present.
- NEXT (#3b): React Analytics page consuming totals + funnel + pipelines +
  these breakdowns, with charts (recharts v2), routed + nav.

## #3a-fix — DB-first read path lifts FX money set (probe-caught)

Symptom: analytics by_currency_book FCY = 4,000,000 (native, 4 deals x 1M USD)
while dashboard FCY = 518,000,000 (KES-equiv). Root cause: _normalize_db_deal_row
(the DB-first reader feeding analytics) lifted only pipeline_category +
lms_application_id from metadata, NOT amount_kes/currency_book — so _deal_value
fell back to NATIVE for FCY deals. The dashboard's DB SQL path extracted amount_kes
directly, so the two paths disagreed.

Fix: _normalize_db_deal_row now lifts amount_kes, currency_book, fx_rate(_date/
_source), client_type, mou_id, mou_title, sector, segment from metadata onto the
deal dict — so ALL DB-first readers see KES-equivalent + the full classification.
Also persisted sector + segment in _db_sync metadata (were not stored at all, so
by_sector collapsed to Unclassified on DB-first reads).

Harness: new assertion "analytics FCY == dashboard FCY (KES-equiv, no drift)".
This is the same native-vs-KES class the React-B-fix caught — different read path.

## #3b — Analytics page (frontend): DELIVERED (tsc gate)

- types/pipeline.ts: PipelineAnalyticsResponse += by_product / by_sector /
  by_currency_book (ProductBreakdown, SectorBreakdown, CurrencyBookSplit).
- hooks/useAnalytics.ts (NEW): mirrors useMdDashboard.
- pages/Analytics.tsx (NEW): headline KPIs (assured/weighted/won/win-rate/live),
  product mix bar chart, sector + currency-book donuts, conversion funnel,
  product-class pipeline cards. Reuses existing CategoryBarChart/DonutChart
  (recharts v2). KES-equivalent throughout — consistent with the dashboard.
- App.tsx: /analytics route. Sidebar: Analytics nav item after Pipeline.
- "Showcase all products and items" (#3) now has a real surface.
- REMAINING: #4 UX/design pass over dashboard + analytics together.

## #4 — UX design pass (Dashboard exemplar): DELIVERED (tsc gate)

DIRECTION: institutional-fintech command centre grounded in the Ecobank palette
(navy #0e2440 anchor, cyan #1797ce live-data, gold #ffd200 reserved for the one
headline). Not the AI-default cream/serif or acid-on-black looks — the brand is
fixed, so the distinctiveness is in hierarchy + restraint.

- pages/Dashboard.tsx: the navy header now carries a HERO figure — Total Pipeline
  (KES-equivalent) shown large, gold eyebrow, with LCY/FCY + live-deal count as
  supporting data and three glass read-outs (BSC avg / NPL / Assured). A 3px gold
  rule closes the command band. Single focal point; everything else stays quiet.
- This is a DIRECTION exemplar on the highest-visibility surface. Pending Josh's
  reaction before propagating the treatment (gold accents, hero pattern, spacing)
  to Analytics and the rest.

## #5a — Executive drill dimensions (backend foundation): DELIVERED

Feedback (screenshot): the dashboard hero LUMPS the whole pipeline into one
figure and duplicates the sections below — execs need to DRILL DOWN. Scope
narrowed to pipeline + credit, improved incrementally.

- _compute_pipeline_analytics += by_unit (branch/org unit) and by_rm
  (relationship manager) — straight off the deal record (unit, staff_name).
  product/sector/currency/stage already existed; this completes the org axes.
- Harness: by_unit + by_rm present.
- NEXT (#5b, pending Josh's UI-model confirmation): interactive drill on the
  Analytics page — dimension picker (Product/Sector/Currency/Stage/Branch/RM)
  re-slices the view; then de-lump the dashboard so it LINKS into drill-downs
  instead of repeating section totals. Credit drill (class/branch/NPL) parallel.

## #5b — Model A pipeline drill (frontend): DELIVERED (tsc gate)

- Analytics page: replaced the static product-bar + sector/currency donuts with
  a PipelineSlicer — a dimension picker (Product / Sector / Stage / Currency /
  Branch / RM). Selecting a dimension re-slices the pipeline into a bar chart +
  a breakdown table (value, deals, % share). KES-equivalent throughout.
- types/pipeline.ts: by_unit / by_rm breakdown types.
- Handles thin dimensions gracefully ("No data for this dimension yet").

### SEED-DATA REALITY (flagged to Josh — NOT a UI defect)
The drill is only as good as the data. The current DB pipeline (~453 deals) is
dominated by accumulated SIMULATION/test deals created by 1-2 harness personas
with no `unit` set — so Branch collapses to "Unassigned" and RM shows ~2 names.
Product (13) and Stage have real spread. For the pitch, regenerate a realistic
pipeline seed: deals spread across the 35 branches / 232 RMs / CBK sectors so
the Branch/RM/Sector drills populate. This is a data-generation task (Josh's
domain: generators at project root), separate from the drill UI which is correct.

## #6 — Realistic demo pipeline seed (data foundation): DELIVERED (dry-run proven)

scripts/seed_pipeline_demo.py — lays down a realistic pipeline so executive
drill-downs populate (the prerequisite for Josh's branch/individual drill ask).

- Distributes deals across real branches (flexcube_mock_branches), RMs
  (flexcube_mock_staff, round-robin per branch so Branch->RM is a coherent
  hierarchy), CBK sectors / segments by client type, product catalogue ->
  pipeline_category, stage_flows per category (incl. Closed Won/Lost), and
  currency (~86% KES, FCY stamped to KES-equiv).
- SAFE: --dry-run (build + summarise, touches nothing); --reset (timestamped
  JSON backup to data/_backups/ BEFORE delete); deterministic ids (SEEDxxxxx,
  idempotent). Writes via the canonical _db_sync_pipeline_deal.
- DRY-RUN PROOF (600 deals): 35 branches, 212 RMs, 14 sectors, LCY 523/FCY 77,
  asset 327/liability 164/insurance 55/other 54, stages spread, regions spread.

NEXT (recommended sequence):
  #7 richer visuals — per-dimension chart type (donut for sector/currency/
     category share, bars for ranked branch/RM/product, funnel for stage).
  #8 click-to-drill depth — Branch -> its RMs -> individual RM -> deals.
  (optional) seed a validated-deal portion so the "assured" funnel isn't empty.

## #7 — Richer per-dimension visuals (frontend): DELIVERED (tsc gate)

PipelineSlicer now picks the chart that fits each dimension:
  - Sector / Currency -> DonutChart (share; top 8 + "Others", center total).
  - Stage -> funnel (flow-ordered descending bars, share labels, depth fade).
  - Product / Branch / RM -> ranked value bars (top 12).
Breakdown table retained alongside every chart (value / deals / % share).
Now meaningful thanks to #6 seed (35 branches, 212 RMs, 14 sectors).

NEXT: #8 click-to-drill depth (Branch -> RMs -> individual deals); then credit
drill + dashboard de-lump (figures link into drills).

## #8 — Click-to-drill: branch → RM → individual deals: DELIVERED (tsc gate)

Backend:
- GET /api/pipeline/drill?unit=&rm= — reuses _acquire_scoped_deals (cascade
  scope enforced), filters by unit then rm, returns by_rm (branch level) +
  individual deal list (RM level) + totals. Pure filter over the scoped set,
  so it can't drift from analytics totals.
- Harness: drill returns by_rm+deals+totals; unit filter narrows to a branch's
  RMs; unit+rm yields that RM's individual deals.

Frontend (Analytics page):
- BranchDrill component below the slicer: breadcrumb All branches › <branch> ›
  <RM>. Level 1 lists branches (click) -> Level 2 lists that branch's RMs
  (click) -> Level 3 lists the RM's individual deals (client/product/stage/
  value/close). fetchPipelineDrill + DrillDeal/PipelineDrillResponse types.
- This is the "drill to individual level" capstone; coherent because the #6
  seed gives each branch a stable RM set.

REMAINING: credit-side drill (class/branch/NPL) + dashboard de-lump (hero
figures link into these drills instead of repeating section totals).

## #9 — Credit analytics + drill (hierarchy-scoped) + scope confirmation + seed FCY fix

CREDIT (backend, loan book over credit_monitoring's 5001 accounts):
- _acquire_scoped_credit(user): SAME get_visible_staff_codes the pipeline uses,
  applied to account rm_code -> an individual sees credit exactly as they see
  pipeline (own subtree; MD/full-view see all). All 232 watchlist rm_codes are
  real staff codes, so scoping narrows correctly (not to zero).
- /api/credit/analytics: outstanding + NPL by classification / region / branch /
  RM (NPL ratio per slice).
- /api/credit/drill?region=&branch=&rm=: Region -> Branch -> RM -> individual
  accounts; pure filter over the scoped set (can't drift from totals).

SCOPE CONFIRMATION (answers "individuals see by hierarchy like pipeline"):
- hierarchy_scope_probe: a non-MD (OWNER) sees a STRICT subset of both pipeline
  (drill count) and credit (account count) vs MD. Mechanism is identical for
  both surfaces, so the reporting tree governs the loan book the same way it
  governs the pipeline.
- NOTE: the credit endpoints were previously UN-scoped (full book to any
  caller). This batch closes that gap.

SEED FCY REALISM FIX:
- seed_pipeline_demo.py VALUE_RANGES are now KES-equivalent bands; native amount
  is derived from the rate (native = kes_target / rate), so FCY deals no longer
  balloon. Dry-run total dropped from 387B (FCY 369B) to ~21B with FCY a
  proportional minority. RE-RUN --reset to apply.

NEXT: credit Analytics PAGE (mirror the pipeline slicer + drill); dashboard
de-lump.

## #9-fix + #10 — Credit read fix (probe-caught) + currency expansion (combined)

CREDIT READ FIX (probe-caught: MD saw branches=0/accounts=0):
- Root cause: _load_json routes through the dual-mode DB/JSON loader, which
  returns [] for credit_monitoring.json under PostgreSQL (the loan book was
  migrated to the watchlist table, leaving the JSON key empty).
- Fix: _acquire_scoped_credit reads credit_monitoring.json DIRECTLY (file read,
  bypassing the dual-mode loader) — reliably carries rm_code/region/branch_name.
  MD now sees all 5001; non-MD sees a strict subset (scope confirmed).

CURRENCY EXPANSION (EcoBank footprint + CNY):
- seed_fx_rates.py: idempotently adds USD, CNY, EUR, GBP + EcoBank's African
  currencies (NGN, GHS, XOF[WAEMU x8], XAF[CEMAC x6], ZAR, TZS, UGX, RWF, ZMW,
  MZN, ETB, AOA, CDF, MWK, GNF, LRD, SLE, GMD, CVE, STN). Synthetic mid rates;
  never overwrites admin edits.
- PipelineCreate currency picker now orders KES (local), USD, CNY first, then
  the rest alphabetically.

## #9-fix-2 — Credit read DB-first from credit_watchlist (probe-caught, round 2)

The file-direct read still returned 0 for MD: under PG the loan book lives in
the credit_watchlist TABLE and credit_monitoring.json is emptied. Confirmed all
232 watchlist rm_codes ARE in staff_register.xlsx, so rm_code scoping is valid —
the only fault was the read source.

Fix: _acquire_scoped_credit now reads DB-first from credit_watchlist (identity
columns top-level; classification/outstanding/npl_days flattened out of the
risk_data JSONB), file fallback for dev/no-PG. MD now sees all 5001; non-MD a
strict subset. Expected harness: credit branches > 0, scope owner=0 < MD=5001.

## #11 — Credit Analytics page (frontend): DELIVERED (tsc gate)

Mirrors the pipeline Analytics page, pointed at /api/credit/analytics + drill:
- KPIs: outstanding, NPL outstanding, NPL ratio, accounts, performing.
- Slicer (Classification / Region / Branch / RM): donut for classification,
  ranked bars otherwise; NPL ratio shown per slice as a tone Badge
  (>=10% danger, >=5% warning, else success).
- Drill: Region -> Branch -> RM -> individual accounts with breadcrumbs
  (account / class / outstanding / DPD / collateral).
- types/creditAnalytics.ts, hooks/useCreditAnalytics.ts, lib/api fetchers,
  /credit-analytics route + sidebar nav.
- Hierarchy-scoped: an individual sees only their subtree's loan book.

REMAINING: dashboard de-lump (hero figures link into pipeline + credit drills).

## #12 — Dashboard de-lump (frontend): DELIVERED (tsc gate)

Answers the original critique ("lumping up the entire pipeline ... need to drill
down"). The hero figures are now DOORS, not a billboard:
- Total Pipeline block -> /analytics (pipeline drill), with a "Drill into
  pipeline →" affordance.
- Glass read-outs: BSC -> /perform, NPL -> /credit-analytics, Assured ->
  /analytics.
- Section headers gained drill links: Performance & Risk -> "Credit drill →"
  (/credit-analytics); Pipeline -> "Pipeline drill →" (/analytics).
The lumped numbers now lead somewhere. (Further de-duplication of the repeated
section tiles can follow if desired.)

=== ARC COMPLETE: pipeline + credit drill-down, hierarchy-scoped, with the
dashboard as the launchpad. ===

## #13 — Application shell rework (UX transformation, batch 1): DELIVERED (tsc gate)

The new frame (Phase 1 + Phase 2 of the UX audit):
- AppShell: h-screen + overflow-hidden -> browser page never scrolls. Full-height
  navy sidebar (fixed) + a white TopBar (fixed) + a single content scroll area
  (<main overflow-y-auto>). Only content scrolls; nav + header stay put.
- TopBar (NEW): current-module title, a working module search (type + Enter or
  click to jump), notifications affordance ("You're all caught up"), compact
  user chip (initials + name + role). Presentation only.
- Sidebar: min-h-screen -> h-full; flat NAV_ITEMS -> domain groups
  (Executive Intelligence / Business Development / Credit Factory /
  Reference & Admin) with group eyebrows. Active-state + visibleFor unchanged.
- Safe for live users: no routes, business logic, or page content changed.

NEXT (UX roadmap): table power-ups (filter/search/pagination on the Table
primitive), exec exceptions strip + sparklines, drill rows -> detail pages,
wide-screen density.

## #14 — Table power-ups (UX transformation, batch 2): DELIVERED (tsc gate)

Production-grade upgrade to the shared Table primitive — every table inherits,
all power-ups OPT-IN so no existing caller breaks:
- Sticky header (default on; sticks under the fixed TopBar when content scrolls).
- Click-to-sort columns (opt-in per column via `sortable`; numeric-aware via
  `sortAccessor`; aria-sort set).
- Global search (`searchable`) with live match count.
- Client-side pagination (`paginated`, `pageSize`) with range + page controls.
- CSV export (`exportable`, `exportFilename`) — real Blob download, RFC-4180
  escaping, exports the filtered+sorted set (not just the page).
- Column `exportValue`/`exportHeader` for clean CSV of rendered columns.

Wired ON for the pipeline deals table (Pipeline.tsx): searchable + paginated
(25) + exportable + sortable on Deal ID / Client / Stage / Value / Age / Owner.

NEXT (UX roadmap): exec exceptions strip + sparklines; drill rows -> detail
pages; wide-screen density; then the deferred production-hardening (real
HoC/CRO/MD authorizer seats, password/rate-limit) per Josh's production directive.

## #15 — Executive exceptions strip (UX transformation, batch 3): DELIVERED

The dashboard "needs a decision" surface — Phase 3/6 of the UX brief, no
dead-end widgets. Read-only derivation; no business logic / workflow change.

Backend (utils/api.py): NEW GET /api/dashboard/exceptions — scoped, drill-linked.
Computes top exceptions from the SAME scoped summaries the dashboard shows, so the
strip and the tiles always agree:
- NPL ratio breach (>=5% warning / >=10% danger) -> /credit-analytics
- Worst-NPL branch in scope (>=10%) -> /credit-analytics
- Deals awaiting validation (pending_validation) -> /pipeline/queues
- Stalled active deals (>14 days, defensive on timestamp) -> /analytics
Each item: {id, severity, title, detail, value, link}. Danger sorted first.
Helper _count_stalled_deals is defensive — any deal without a usable timestamp
is skipped, never falsely counted.

Harness (simulate_credit_chain.py): NEW exceptions_probe — reachable, list shape,
items well-formed (id/severity/title/link), valid severities, links restricted to
known drill routes, NPL breach surfaces for MD, scoped persona returns its subset
without error.

Frontend: types/exceptions.ts, lib/api.ts (fetchDashboardExceptions),
hooks/useExceptions.ts, components/ExceptionsStrip.tsx (severity-striped cards,
click -> drill; "all within thresholds" when empty; skeletons while loading),
wired at the top of Dashboard.tsx content.

NOTE (pre-production): NPL bands 5%/10% are Claude's defaults pending Ecobank
confirmation. Stalled-deal window is 14 days (confirm). Per Josh's directive the
admin-superuser override + test/EcoStaff logins remain INTACT until the very end.

NEXT (UX roadmap): drill rows -> detail pages; wide-screen density; design-system
spec. Then the deferred auth/production-hardening LAST.

## #16 — Drill rows -> detail pages (UX transformation, batch 4): DELIVERED (tsc gate)

Closes the analytics arc — drills now end on a real record, not a list.
- Pipeline drill (Analytics.tsx / BranchDrill): each individual deal row clicks
  through to /pipeline/:dealId (the existing PipelineDealDetail). Client name
  shown in brand-primary, row hover + cursor.
- Credit drill (CreditAnalytics.tsx / CreditDrill): each account row clicks
  through to /cbs/:cif (the existing customer detail, which shows the customer
  and their accounts — the natural existing surface, since there is no
  standalone single-account page). Guarded: only clickable when the account
  carries a CIF; account number shown in brand-primary when drillable.
Presentation only — no backend, no business logic.

NEXT (UX roadmap): wide-screen density (xl/2xl), then design-system spec; then
the deferred auth/production-hardening LAST (admin override + test logins stay
intact until the very end, per Josh).

## #17 — Wide-screen density (UX transformation, batch 5): DELIVERED (tsc gate)

Reclaims the empty margins on 1920/2560 monitors (Phase 8 of the UX brief).
- Data-dense pages (dashboards, lists, analytics, detail-with-tables) gained a
  `2xl:max-w-[1680px]` cap on their `mx-auto` containers; the old base
  (max-w-7xl / bumped from max-w-6xl) still governs below 1536px.
- The `2xl:` prefix means ZERO change under 1536px (1366/1440 laptops untouched);
  on a 1920 screen the content fills the usable area (~1680 after the sidebar),
  on 2560 it caps at 1680 (comfortable, not sprawling).
- Forms / detail / auth (max-w-5xl: PipelineCreate, Cbs, Login, ChangePassword,
  Lms/CreditAdmin/Cbs detail) left narrow on purpose — readability over width.
12 pages widened (26 containers); hero band + body widen together so they align.

NEXT (UX roadmap): design-system spec doc (lock consistency). Then the deferred
auth/production-hardening LAST (admin override + test logins stay intact until
the very end, per Josh).

## #18 — Login wording removal + Enterprise Excellence audit: DELIVERED

- Login.tsx: removed the "Central Bank of Kenya" (regulator_full) line at login
  per Josh. branding still used elsewhere (no unused-var). Dashboard/ChangePassword
  left as-is (only login was requested).
- A2Z_ENTERPRISE_EXCELLENCE_AUDIT.md delivered. Verdict: STRONG BUT NEEDS
  ENHANCEMENT. CRITICAL grounded finding (Phase 2): deal validation is gated by a
  flat is_manager() boolean whose keywords include "managing"/"chief"/"director"
  -> the MD's role (Chief Executive & Managing Director) matches, so the CEO/MD
  CAN validate deals (plus the is_admin short-circuit). Correct model = validate
  by the owner's reporting line; executives only at policy gates. Gated on the
  Ecobank DOA matrix + ties into the deferred auth-hardening -> do in the final
  pass, not invented now. Other gaps: xlsx/PDF export (CSV-only today),
  page-header/breadcrumb/action-bar framework, sticky filters/tabs, design-system
  spec.

RECOMMENDED NEXT (no decision needed, high value): page-header/breadcrumb/action-bar
framework, then xlsx+PDF exports. THEN auth/DOA hardening LAST (admin override +
test logins intact until then).

## #19 — Page-header framework (excellence sprint, batch 1): DELIVERED (tsc gate)

Phase 1's real ask — one page-title framework so pages stop reading as separate
screens. NEW components/PageHeader.tsx: white header (matches the TopBar, no
navy-on-navy) with optional breadcrumbs, optional domain eyebrow, title,
subtitle, and a right-aligned action slot. Breadcrumb crumbs can be links.

Migrated as proof-of-pattern: Analytics ("Business Development / Pipeline
Analytics") and CreditAnalytics ("Credit Factory / Credit Analytics") — replaced
their bare inline <h1>+<p> with <PageHeader>. Bodies unchanged.

ROLLOUT PATTERN (mechanical, one page each): wrap the page return in a fragment,
add <PageHeader breadcrumbs/title/subtitle/actions .../>, keep the body container.
For list pages, pass primary actions (e.g. "+ New Deal") into `actions`. The navy
hero pages (Dashboard) stay as the deliberate executive landing; the navy-strip
detail pages can migrate next for full consistency.

NEXT (excellence sprint): xlsx + PDF export with full banking field set (SheetJS
in stack); then sticky filters/tabs; then auth/DOA hardening LAST.

## #20 — Page-header sweep + redundant navy band removal (excellence sprint, batch 2): DELIVERED

Resolves the "two stacked headers" Josh saw: the fixed white TopBar stayed while
each page's OWN navy band (app name + role, already shown in shell) scrolled.
Migrated 5 more pages onto the shared PageHeader, removing the navy strips:
- Pipeline ("Business Development / Pipeline")
- Loan Applications ("Credit Factory / Loan Applications")
- Credit Admin ("Credit Factory / Credit Admin")
- Strategic Initiatives ("Executive Intelligence / Strategic Initiatives")
- Target Cascade ("Executive Intelligence / Target Cascade") — period input moved
  into the PageHeader action slot.
Also removed internal DEV-STAGE BADGES (β5/β6/γ4/γ3) from production headers.
PageHeader.tsx included so the batch is self-contained.

Now consistent: ONE fixed global TopBar (module title + search + user) + ONE white
PageHeader per page (breadcrumbs + title + subtitle + actions) that scrolls as the
top of content (standard pattern; global chrome fixed, page header scrolls).

REMAINING header sweep (follow-up): detail pages (PipelineDealDetail,
LmsApplicationDetail, CreditAdminCaseDetail, CbsCustomerDetail, InitiativeDetail)
+ PipelineManagerQueues + PipelineCreate still carry navy strips; Dashboard keeps
its hero deliberately. NEXT: xlsx+PDF export; then auth/DOA hardening LAST.

## #21 — Remove Central Bank of Kenya + FLEXCUBE wording: DELIVERED

Josh: this wording appeared on the Dashboard hero (top-right) and across pages.
Removed at every level:
- Render sites: Dashboard hero block (regulator_full + core_banking_system),
  ChangePassword line. (Login already done in #18.)
- Frontend defaults: BrandingProvider regulator_full/core_banking_system -> ''.
- Backend: api_branding payload returns '' for both fields (so it can't leak into
  future xlsx/PDF exports or reports either). Underlying config functions left
  intact. py_compile OK. Requires API restart to take effect.
Grep confirms zero remaining render sites in pages/components.

NOTE (observed in screenshot, flagged): the MD dashboard hero figures + Performance
& Risk tiles appeared blank/skeleton while the exceptions strip was populated —
likely a mid-load snapshot (md endpoint slower); if it persists, investigate
/api/dashboard/md. NEXT: xlsx+PDF export; then auth/DOA hardening LAST.

## #22 — TopBar refinement + identity de-duplication: DELIVERED (tsc gate)

Josh: search was the dominant item (misplaced); wanted Streamlit-style titles
across; logged-in user repeated everywhere.
- TopBar rewritten title-forward: domain eyebrow (brand-cyan) + page TITLE as the
  hero (Streamlit-style), consistent across all routes (route->domain+title map).
  Search demoted to a compact right-aligned utility (w-56, "Search…"), no longer
  the centre of gravity. Bell + single canonical user chip on the right. h-16.
- Dashboard hero: removed the redundant user name·role line (was a 3rd copy of
  identity alongside the TopBar chip + sidebar). user/useRole import cleaned up.
- PageHeader SLIMMED: TopBar now owns the visible title, so PageHeader no longer
  renders it (kept as sr-only heading for a11y). It now carries breadcrumb +
  subtitle + action slot only — prevents title showing twice on interior pages.
  No page edits needed (props unchanged).

Result: ONE prominent title (TopBar, across all pages), ONE identity chip
(TopBar) + sidebar sign-out, breadcrumb+subtitle+actions per page. Much less
repetition.

NEXT: xlsx+PDF export; further page polish; then auth/DOA hardening LAST.

## #23 — TopBar in Ecobank navy (scroll differentiation): DELIVERED (tsc gate)

Josh: don't leave the TopBar white — apply Ecobank colours so the fixed bar is
differentiated as content scrolls under it.
- TopBar background -> var(--brand-secondary) navy, matching the sidebar: the two
  now form one continuous brand frame around the light content.
- Internals restyled light-on-dark: domain eyebrow in sky/cyan, title white,
  compact search as translucent white/10 field, bell + user chip white, avatar
  ring. Search/notification popovers stay white (readable).
- shadow-md + z-20 so page content visibly scrolls UNDER the fixed bar.
On the Dashboard the navy TopBar meets the navy hero (a cohesive executive header
zone); on all other pages it sits over light content / white PageHeader for clear
separation.

NEXT: xlsx+PDF export; sticky filters/tabs; detail-page header sweep; KPI
sparklines; then auth/DOA hardening LAST.

## #24 — Pipeline card polish + sidebar scrollbar (excellence sprint): DELIVERED (tsc gate)

Addresses 3 of Josh's 5 points from the Pipeline/Analytics screenshots:
1. Sidebar "little extension" = the nav scrollbar nub -> styled thin/subtle
   (w-1.5, white/15 thumb, transparent track) so it no longer protrudes on navy.
4. Card colours "not shouting": Stat gains a `tone` prop (subtle tinted bg —
   sky-50/slate-50/amber-50) used INSTEAD of the bold top stripe on the Pipeline
   pillar + summary cards. Other Stat usages unchanged (default stripe restored).
5. Cards clickable: Stat gains `onClick` (cursor + hover:shadow + corner →).
   Asset/Liability/Insurance/Other/Deals Visible/Total Assured -> /analytics;
   Pending Validation -> /pipeline/queues.

STILL OPEN (Josh's other 2 points, teed up):
- (2) Slicer "compare two items": add a compare mode to the analytics slicer
  (pick two products/sectors/etc. side-by-side). Feature batch.
- (3) Funnel empty / Assured = KES 0 everywhere (dashboard, analytics, pipeline):
  DATA reality — no deals are validated in the seed, so validated_value=0 and the
  funnel has nothing to show. Fix = validate a slice of seed deals (need to
  inspect how a deal's validated/assured state is stored first). High value: one
  fix lights up the funnel + Assured on dashboard + analytics + pipeline at once.

Deep per-class drill (Asset card -> analytics filtered to asset) needs an
analytics URL-filter param — pairs with the compare feature.

## #25 — Seed manager-validation (lights up funnel + Assured): DELIVERED

Root cause of "Assured KES 0" everywhere + empty funnel: no seed deals had
`manager_validated=true`. Assured/funnel read ACTIVE deals where manager_validated
is true -> all zero.

Fix: NEW scripts/seed_validate_deals.py — validates a slice of active deals via the
app's own PipelineManager.validate_deal (not a raw DB write), so the path matches
production exactly. SAFE + IDEMPOTENT: targets the first N% of active deals by id
(deterministic); re-running converges to the target and skips already-validated;
--dry-run writes nothing. Default --pct 60.

After running + API restart, these all populate at once: MD dashboard "Assured"
tile, Pipeline Analytics "Assured value", Pipeline "Total Assured" card, and the
Validated-pipeline funnel. pending_validation drops to the remaining ~40% (a
realistic queue). No API/logic change — harness stays 100/100.

STILL OPEN: (2) slicer "compare two items" feature; deep per-class card drill
(needs analytics URL-filter param). Then auth/DOA hardening LAST.
