# CHANGELOG v10.273 — Phase 2A: Partnerships Cluster Closure (#369-378)

**Date:** 2026-05-07
**Phase:** 2A — Continuation 2 QA Closure (per v10.270 charter)
**Cluster:** Partnerships — third of 10 planned Phase 2A clusters
**Audit:** 165/165 → **166/166 PASS** (+G166 partnerships_registered)
**Continuation 2 status:** 111/194 → **121/194 active** (+10); 83 → 73 planned

---

## What v10.273 ships

7 new engine modules in `utils/`, totaling 3,630 lines of new code. Standards #372+#373 (lead tracking + commission) consolidated into one module since commissions are computed directly from WON leads. #374+#375 (portal API + ecosystem analytics) consolidated since they share the partner-master + scorecard read surface. #377+#378 (risk + KPIs) consolidated since both aggregate across the same partner population.

```
utils/partner_master.py                 (#369)        451 lines  PartnerMasterEngine
utils/contract_management.py            (#370)        463 lines  ContractManagementEngine
utils/partner_scorecard.py              (#371)        425 lines  PartnerScorecardEngine
utils/partner_leads_commissions.py      (#372+#373)   668 lines  LeadTrackingEngine + CommissionEngine
utils/partner_portal_and_analytics.py   (#374+#375)   434 lines  PartnerPortalAndAnalyticsEngine
utils/partner_onboarding.py             (#376)        512 lines  PartnerOnboardingEngine
utils/partner_risk_and_kpis.py          (#377+#378)   677 lines  PartnerRiskAndKpisEngine
                                                     ────────────
                                        subtotal:   3,630 lines
```

Plus:

- `pages/7_admin.py` — new "Tier 35 — Partnerships Cluster (v10.273, Phase 2A)" with 7 engine entries.
- `scripts/audit.py` — new gate `gate_partnerships_registered()` registered as G166.
- `utils/standards_registry.py` — ENH-369 through ENH-378 flipped from `status="planned"` (target batch `v10.92+`) to `status="active"` with `implementation_batch="v10.273"`.
- `data/audit_baselines.json` — G162 baseline rebased 3,699 → 3,712 (+13) with scope_history entry; rationale below.

---

## Per-standard honest scope

### #369 Partner Master Data & Lifecycle — `utils/partner_master.py`

Partner master record with full lifecycle state machine. `PARTNER_TYPES = ("REFERRAL", "INTEGRATION", "DISTRIBUTION", "ECOSYSTEM", "SERVICE")` byte-for-byte. Lifecycle: `PROSPECT → ONBOARDING → ACTIVE → SUSPENDED ↔ ACTIVE → OFF_BOARDING → OFF_BOARDED` with OFF_BOARDED as terminal (Rule 4 no-skip; G166 locks).

`update_partner_data` separates data updates from state transitions — state can ONLY change through `transition_state`, which preserves the audit trail invariant. Forbidden update fields: `partner_id, state, transitions, registered_by, registered_at, data_updates`.

`RISK_TIERS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")` byte-for-byte. Note the deliberate distinction from `RISK_ALERT_LEVELS` in `partner_risk_and_kpis.py` — risk tiers are administrative classifications (used for review cadence), alert levels are computed from monitoring scores.

**Out of scope:** External partner discovery (CRM-style prospect sourcing). Engine ingests partner records; the upstream "find me prospects" workflow is a downstream BD tool concern.

### #370 MOU & Contract Management — `utils/contract_management.py`

Centralized MOU/contract repository with versioning + obligations + key dates. `CONTRACT_TYPES = ("MOU", "SLA", "REFERRAL", "DISTRIBUTION", "INTEGRATION", "NDA")` byte-for-byte. State lifecycle has 7 states with 3 distinct terminals (RENEWED, EXPIRED, TERMINATED) — different terminals carry different downstream consequences (renewed contracts spawn child contracts; expired contracts do not; terminated contracts trigger commission clawback workflows in #373).

`expiring_soon(days_ahead=90)` returns SIGNED contracts within renewal-notice window — designed to drive auto-alerts to relationship managers.

`OBLIGATION_STATES = ("PENDING", "IN_PROGRESS", "COMPLETE", "OVERDUE", "WAIVED")` for tracking individual deliverables embedded in a contract. Note: WAIVED is not the same as TERMINATED at contract level — WAIVED means a specific obligation has been formally relieved while the contract continues.

**Out of scope:** Document storage. The engine stores structured metadata (state, dates, obligations) but actual contract PDFs/Word docs go through the existing legal_repository (#221-230 cluster, already shipped). `contract_id` is the join key.

### #371 Partner Performance Scorecard — `utils/partner_scorecard.py`

5 weighted dimensions sum=100 byte-for-byte (G166 locks):

```
REVENUE_KES         = 30
LEADS_DELIVERED     = 20
CONVERSION_RATE     = 20
CSAT_SCORE          = 15
COMPLIANCE_SCORE    = 15
```

Tier classification byte-for-byte: `PLATINUM≥85 / GOLD≥75 / SILVER≥60 / BRONZE≥45 / AT_RISK<45`.

Rule 1 honesty: composite returns `None` when ANY dimension is missing. No imputation. The `compute_scorecard` response surfaces `missing_dimensions` list and `reason="missing_dimensions"`. Partners with incomplete scorecards do NOT appear in `rank_partners()`.

REVENUE_KES and LEADS_DELIVERED are normalized to 0-100 scale before composite computation using `revenue_baseline` (default 10M KES) and `leads_baseline` (default 100). Both baselines are constructor parameters — the engine itself doesn't hardcode KES; the dimension name carries the currency suffix per spec.

**Out of scope:** Tier-driven incentive automation. The scorecard classifies partners; downstream commission/perk logic per tier is the relationship management discipline, not engine concern.

### #372+#373 Lead Tracking + Commission Automation — `utils/partner_leads_commissions.py`

`LEAD_STATES = ("NEW", "QUALIFIED", "IN_PIPELINE", "WON", "LOST", "DUPLICATE", "EXPIRED")` byte-for-byte with 4 terminals (G166 locks). Rule 4 no-skip — `NEW → IN_PIPELINE` rejected; must go through QUALIFIED first.

`DEFAULT_LEAD_EXPIRY_DAYS = 90`. `expiry_date` set on submission; engine doesn't auto-transition (deferred to a scheduled job — see "Out of scope").

Commission engine: `compute_commissions` enforces `MIN_COMMISSION_SPLIT_PCT = 0` and `MAX_COMMISSION_SPLIT_PCT = 50` (defensive bound — 50% above which partner economics become questionable). G166 locks both bounds.

`reconcile_commission` uses 1% tolerance band: `|paid - expected| <= expected * 0.01` → PAID, else DISPUTED. The variance is captured for finance follow-up regardless of outcome.

**Out of scope:** Auto-EXPIRY scheduler. The engine flags leads as expiring when their expiry_date passes, but doesn't auto-transition. Scheduled job (`scripts/expire_stale_partner_leads.py`) is a future v10.x batch concern. Until then, leads must be manually moved to EXPIRED state by a human reviewer.

**Out of scope:** Multi-currency commission splits. All amounts assume KES. International partner commissions in foreign currencies require FX integration not yet wired.

### #374+#375 Partner Portal API + Ecosystem Analytics — `utils/partner_portal_and_analytics.py`

Portal API contract. `PORTAL_PERMISSION_MATRIX` byte-for-byte (G166 locks):

```
LEAD_SUBMIT          read=DENY,         write=OWN_PARTNER
LEAD_STATUS          read=OWN_PARTNER, write=DENY
COMMISSION_STATEMENT read=OWN_PARTNER, write=DENY
DOCUMENTS            read=OWN_PARTNER, write=DENY
TRAINING_RESOURCES   read=ALL,          write=DENY
OTHER_PARTNER_DATA   read=DENY,         write=DENY
```

Cross-partner isolation: a partner with `partner_id=P-001` cannot read `P-002`'s leads, commissions, or documents. TRAINING is the only resource open to ALL — partners can browse training catalog without revealing each other's existence.

`portal_dashboard_payload(partner_id)` returns the read-scoped data bundle for the portal landing page — partner state, latest scorecard tier, lead counts. The actual portal UI is a downstream Streamlit page concern.

Ecosystem analytics: `top_performers / underperformers / geographic_coverage / segment_coverage / profitability_by_partner` — all aggregate across partners using the master + scorecard + leads engines as data sources.

**Out of scope:** Portal authentication. JWT issuance for partner_portal users is the auth_jwt module's responsibility. This module defines the permission matrix; auth_jwt enforces it on tokens.

**Out of scope:** Portal UI. The Streamlit page rendering the partner-facing portal isn't shipped this batch — the engine surfaces `portal_dashboard_payload()` for that future UI.

### #376 Partner Onboarding Workflow — `utils/partner_onboarding.py`

6 sequential gates byte-for-byte (G166 locks):

```
DUE_DILIGENCE → CONTRACT → TRAINING → SYSTEM_ACCESS → SANDBOX_TESTING → GO_LIVE_APPROVAL
```

Strict no-skip enforcement: `advance_gate(G_n)` rejected when `G_(n-1).state != "PASSED"`. Gate state per gate: `PENDING / IN_PROGRESS / PASSED / FAILED`. Composite onboarding state derived from gate states: `DRAFT / IN_PROGRESS / BLOCKED / COMPLETE / ABANDONED`.

`fail_gate` cannot fail an already-PASSED gate — that would corrupt the audit trail. To re-fail a passed gate, the underlying decision must be reversed (a new onboarding record with explicit annotation).

`retry_failed_gate` resets a FAILED gate back to PENDING — preserving the failure event in the events log while permitting re-attempt. The composite state recomputes from BLOCKED back to IN_PROGRESS.

`bottleneck_summary()` answers "where are partners stuck" — counts active onboardings by their first non-PASSED gate. Operational tool for the BD team to identify pipeline friction.

**Out of scope:** Auto-trigger of `partner_master.transition_state(ONBOARDING → ACTIVE)` when onboarding reaches COMPLETE. The engine flags an onboarding as COMPLETE; the partner_master state transition is currently a manual call. Wiring them together is intentionally NOT done this batch — it would create a tight coupling that makes auditing each engine's behavior independently harder. A future batch will add an explicit orchestration layer.

### #377+#378 Partner Risk + Ecosystem KPIs — `utils/partner_risk_and_kpis.py`

4 weighted risk dimensions sum=100 byte-for-byte (G166 locks):

```
FINANCIAL_HEALTH    = 30
REGULATORY_STANDING = 30
CYBER_POSTURE       = 25
CUSTOMER_COMPLAINTS = 15
```

Alert classification: `GREEN ≥80 / AMBER ≥60 / RED <60 / CRITICAL <40`. Critical override: any **single dimension** below 40 forces CRITICAL even if the composite is GREEN. This matches IIA 2026 third-party risk guidance — a partner with healthy financials and regulatory standing but a cyber breach should not be classified as low risk just because the average looks fine.

Degradation detection: `DEGRADATION_DROP_THRESHOLD = 15` points. Composite drop ≥15 between consecutive periods triggers an alert. Auditable via the `alerts` array with from/to composites and tiers.

Ecosystem KPIs:
- `ecosystem_revenue_total(period)` — sum of WON lead revenue
- `share_of_new_acquisitions(total_new_customers=N)` — Rule 6: when N is None, returns explicit `reason="total_new_customers_required_for_share_pct"` rather than silently dividing by zero or imputing a denominator
- `customer_ltv_from_partners(partner_id)` — uses `actual_revenue_kes` from leads as LTV proxy; documented as a proxy
- `nps_of_partner_acquired_customers(nps_data={lead_id: score})` — Rule 6: when nps_data is None, returns `reason="nps_data_not_provided"` rather than fabricating a default

**Rule 6 discipline.** Both `share_of_new_acquisitions` and `nps_of_partner_acquired_customers` REQUIRE caller-provided data the engine cannot infer (total customer count from external CRM; survey scores from external NPS tooling). The engine surfaces explicit reasons rather than computing misleading partial answers. This is the same pattern as Rule 7 ML scaffolding from v10.272 (segment_dashboards competitor benchmark) — separate the deterministic part from the data-dependency-pending part.

**Out of scope:** Real NPS survey collection. The engine accepts a NPS data dict; the survey distribution + collection workflow lives outside MIS 360. When integrated, the dict comes from the survey engine's storage.

**Out of scope:** Customer LTV refinement. The engine uses `actual_revenue_kes` from a single WON lead as LTV proxy. Real LTV requires multi-period revenue tracking + retention probability modeling — those are downstream actuarial concerns.

---

## Audit gate G166 — `gate_partnerships_registered`

Locks 12 invariants byte-for-byte:

1. All 7 modules import cleanly
2. PARTNER_TYPES (5) + PARTNER_STATES (6) + RISK_TIERS (4)
3. ALLOWED_PARTNER_TRANSITIONS — OFF_BOARDED is empty (terminal)
4. CONTRACT_TYPES (6) + CONTRACT_STATES (7) + 3 terminals (RENEWED/EXPIRED/TERMINATED all empty)
5. SCORECARD_DIMENSIONS (5) + DIMENSION_WEIGHTS sum=100
6. PARTNER_TIERS (PLATINUM/GOLD/SILVER/BRONZE/AT_RISK)
7. LEAD_STATES (7) + ALLOWED_LEAD_TRANSITIONS — 4 terminals empty (WON/LOST/DUPLICATE/EXPIRED)
8. Commission split bounds [MIN=0, MAX=50]
9. ONBOARDING_GATES sequence (6 gates byte-for-byte)
10. PORTAL_PERMISSION_MATRIX — OTHER_PARTNER_DATA fully DENY, TRAINING read=ALL, role_name="PARTNER_PORTAL_USER"
11. RISK_DIMENSIONS (4) + RISK_DIMENSION_WEIGHTS sum=100
12. Standards #369-#378 status="active" with implementation_batch="v10.273"

Tampering with any of these in a future batch fails the build automatically.

---

## Audit gate posture summary

| Gate | Before v10.273 | After v10.273 | Note |
|------|---------------|---------------|------|
| G2 direct_io | PASS | PASS | All 7 modules use db.dual_save / db.dual_load (matches v10.271 + v10.272 precedent) |
| G117 engine_hub_coverage | PASS | PASS | 7 partnership modules added to denominator; Tier 35 added |
| G162 tenant_hardcoding | PASS @ 3,699 baseline | **PASS @ 3,712 baseline (rebased)** | +13 tokens from REVENUE_KES dimension constant + actual_revenue_kes field per Continuation.docx #371-#372 spec — same legitimate-citation precedent as v10.271 |
| G163 pg_migration | PASS | PASS | No PG migration work in this batch |
| G164 sla_engines_registered | PASS | PASS | Locked by v10.271; intact |
| G165 specialized_segments_registered | PASS | PASS | Locked by v10.272; intact |
| G166 partnerships_registered | — | **PASS (NEW)** | Locks 12 spec invariants byte-for-byte across 7 modules |

**Net audit posture:** 165/165 → 166/166 PASS. New gate adds without displacing anything.

---

## G162 baseline rebase — explicit rationale

v10.273 rebased G162 from 3,699 → 3,712 (+13 KES tokens). This is the second G162 rebase in Phase 2A (first was v10.271 for SLA regulatory citations).

**Why these +13 tokens are legitimate citations, not tenant drift:**

12 of the 13 KES tokens come from the `REVENUE_KES` constant — a SCORECARD_DIMENSIONS member byte-for-byte locked by G166 per Continuation.docx #371. The remaining 1 token is `actual_revenue_kes` field name on WON leads per Continuation.docx #372 commission attribution.

These are domain-bound API/field names defined by the spec. Renaming `REVENUE_KES` to `REVENUE` would:
- Break byte-for-byte lock on G166 (Continuation.docx specifies the dimension name)
- Make the dimension semantically ambiguous (revenue in what currency?)
- Create downstream churn in any future cluster that consumes the scorecard

**Why this isn't sloppiness vs v10.272's 4-token cleanup:**

v10.272's 4 tokens were docstring prose (e.g. "(CBK minimum)", "Property purchase in Kenya") that could be made currency-agnostic without breaking spec contracts. v10.273's 13 tokens are constant names and field names that ARE the spec contract.

The scope_history entry in `data/audit_baselines.json` documents this rebase with full rationale.

---

## Honest acknowledgements

1. **3 of 10 standards consolidated into joint modules.** Standards #372+#373 (lead tracking + commission), #374+#375 (portal API + ecosystem analytics), and #377+#378 (partner risk + ecosystem KPIs) ship as joint modules. Each pair shares state and would have required circular imports if shipped separately. All 10 standards still flip to active in the registry. Net file count: 7 modules covering 10 standards. Same engineering pattern as v10.272 (#360-364 → segment_propositions).

2. **G162 baseline rebased to 3,712.** Documented above. Worth flagging because rebasing G162 is a high-friction action — every rebase needs explicit rationale per the original v10.219 audit. Two rebases in Phase 2A so far (v10.271 and v10.273), both for legitimate Continuation.docx-locked spec citations. v10.272 cleaned 4 stray tokens without rebasing — that pattern is the default; rebases are exceptional.

3. **Onboarding ↔ partner_master state transition is intentionally NOT auto-wired.** When `PartnerOnboardingEngine` reaches COMPLETE, it does NOT auto-call `PartnerMasterEngine.transition_state(ONBOARDING → ACTIVE)`. This decoupling is deliberate — engine isolation makes audit easier. A future orchestration layer will wire them together with explicit logging. Documented in the #376 scope above.

4. **Commission auto-EXPIRY is not implemented.** `DEFAULT_LEAD_EXPIRY_DAYS = 90` sets the field on lead submission, but no scheduled job auto-transitions stale leads. A future cron job (`scripts/expire_stale_partner_leads.py`) is required. Until then, leads sit in IN_PIPELINE indefinitely until a human reviewer transitions them. Not a correctness issue — the engine accepts the manual transition — but operationally it means stale leads accumulate.

5. **Multi-currency assumed away.** All revenue/commission amounts assume KES. International partners with foreign-currency contracts require FX integration not yet wired. The `revenue_baseline` parameter on the scorecard is currency-agnostic, but the actual revenue field name carries the KES suffix per spec.

6. **Self-tests are smoke-level.** Each module has a `_self_test()` exercising 8-15 cases. Consistent with v10.271 + v10.272 precedent. Full integration testing across the 7 partnership modules + the existing customer_segmentation + the BSC engine is deferred to v11+ QA framework.

---

## Phase 2A progress

```
Phase 2A batches scheduled:    16 (v10.270 → v10.285)
Phase 2A batches shipped:       4 (charter, SLA Tracker, Specialized Segments, Partnerships)
Phase 2A batches remaining:    12
Continuation 2 active:        121/194 (62%)
Continuation 2 planned:        73/194 (38%)
```

**Per-cluster status:**

```
✅ Closed (11 clusters, 121 standards):
   Credit Module #119-130              12/12 active
   Reconciliation #181-190             10/10 active
   Audit #201-210                      10/10 active
   Legal #221-230                      10/10 active
   Treasury #231-240                   10/10 active
   Revenue Assurance #241-248           8/8 active
   Finance #249-258                    10/10 active
   Credit Risk Gov #259-268            10/10 active
   Trade Finance #269-280              11/12 active (#272 SWIFT planned)
   SLA Tracker #379-388                10/10 active   (v10.271)
   Specialized Segments #359-368       10/10 active   (v10.272)
   Partnerships #369-378               10/10 active   ← v10.273 NEW

❌ Open clusters (8 clusters, 73 standards remaining):
   Bancassurance #301-310              10  → v10.274
   Customer Behavioral #337-348        12  → v10.275-276
   Propositions #349-358               10  → v10.277
   Competitor Intel #327-336           10  → v10.278  (will wire real competitor data into segment_dashboards Rule 7 hook)
   Campaigns #389-398                  10  → v10.279
   Command Centre #311-320             10  → v10.280
   IT/Digital #291-300                 10  → v10.281-282
   SWIFT (#272)                         1  → v10.283
   QA Map document                          → v10.284
   Phase 2A retrospective                   → v10.285
```

---

## Files changed (v10.273)

```
utils/partner_master.py                 NEW    451 lines
utils/contract_management.py            NEW    463 lines
utils/partner_scorecard.py              NEW    425 lines
utils/partner_leads_commissions.py      NEW    668 lines
utils/partner_portal_and_analytics.py   NEW    434 lines
utils/partner_onboarding.py             NEW    512 lines
utils/partner_risk_and_kpis.py          NEW    677 lines
                                        ────────────
                          subtotal:    3,630 lines new code

scripts/audit.py                       EDIT   +189 lines (G166 function + 1 GATES entry)
pages/7_admin.py                       EDIT   +60 lines (Tier 35 with 7 entries)
utils/standards_registry.py            EDIT   ENH-369..ENH-378 status/batch flips (10 standards)
data/audit_baselines.json              EDIT   G162 rebase 3699→3712 + scope_history entry
CHANGELOG_v10.273.md                   NEW    (this file)
```

---

## Audit (final)

```
Score: 166/166 gates = 100.0% — PASS
G162: baseline rebased to 3,712 (REVENUE_KES dimension + actual_revenue_kes field)
G164: SLA Tracker cluster locked (v10.271)
G165: Specialized Segments cluster locked (v10.272)
G166: 7 Partnerships engines registered; PARTNER_TYPES (5) + PARTNER_STATES (6)
      + RISK_TIERS (4) byte-for-byte; partner + contract + lead state machines
      Rule 4 with terminals locked; commission split bounds [0,50]; portal
      cross-partner isolation locked; risk dimensions weights sum=100
```

70 consecutive clean batches (v10.193 → v10.273).

---

## What's next: v10.274 — Bancassurance cluster (#301-310)

10 standards covering insurance product registration, broker/agent management, premium collection automation, claim coordination, IRA Kenya regulatory reporting, and bancassurance-specific KPIs. Sized similarly to v10.273 (likely 6-8 modules). Probable G167 `bancassurance_registered` to lock policy state machine + premium collection lifecycle.

— v10.273, May 2026
