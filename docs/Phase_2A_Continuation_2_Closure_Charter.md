# Phase 2A — Continuation 2 QA Closure Charter

**Sprint span:** v10.270 (this batch) → estimated v10.285+ closure
**Author:** Joshua Mokua / A2Z MIS 360
**Status:** PLANNING — implementation begins next batch (v10.271)
**Audit at charter:** 163/163 PASS · 91/194 (47%) of Continuation 2 standards active · 103/194 (53%) planned
**Target at closure:** Continuation 2 = 194/194 (100%) active · 1 QA Map document for Ecobank presentation

**Phase 1E Bank-Level Pipeline:** PAUSED at v10.269 charter (resumed after Phase 2A closure)

---

## Why this charter exists, and why Phase 1E is paused

Ecobank Kenya — A2Z's design partner — issued a QA document (`Continuation.docx`) listing 194 enhancement standards across 19 clusters. The document is the bank's vendor-evaluation framework: each standard is a line item that determines whether A2Z meets, partially meets, or fails the bank's expectations relative to the three competing vendors.

Live registry inspection at charter time:

```
Active (cluster engines shipped, registered with past-batch):    91 / 194 (47%)
Planned (registered, no engine yet, future-dated batch):        103 / 194 (53%)
```

**Phase 1E Bank-Level Pipeline (v10.269 charter, 7-batch sequence) was opened immediately before this batch.** Its scope — getting G143 from 75.6% to 100% via a separate per-period reducer — is internal discipline, not customer-facing. The Ecobank QA presentation is the existential commercial milestone. Internal discipline defers to commercial closure.

Phase 1E is paused at its charter (v10.269). The 7-batch sequence remains valid; the batches resume after Phase 2A closes. No work is lost — the charter is the bookmark.

---

## What "closure" means in this charter — the integrity bar

A standard is closed (status flipped from `planned` to `active`) only when **all** of the following are true:

1. A real engine module exists in `utils/` that implements the spec's analytical or operational capability — not a stub, not a wrapper around a placeholder, not 50 lines of `pass`.
2. The engine has self-tests that exercise the main behaviors. Smoke-level is acceptable; full coverage is not required.
3. The standard's `implementation_batch` is set to the batch in which the engine landed (e.g., `v10.272`).
4. Where the cluster's discipline calls for it, an audit gate is added that locks structural properties of the cluster's output. Not every standard needs a dedicated gate; the existing cross-cutting gates (G1–G163) cover most structural concerns.

A standard is **NOT closed** when:
- The registry entry exists but no engine module backs it
- An engine exists but stops at `raise NotImplementedError` or returns hardcoded sample data
- The engine is registered in a future-batch slot (e.g., `v10.95+`) without the engine actually shipping in that batch

**This is the precedent set by the 91 already-active standards.** Sampling at charter time confirmed: Audit cluster (#201–210) has `utils/audit_universe.py` (684 lines), Reconciliation cluster (#181–190) has `utils/reconciliation_engine.py` (595 lines), Trade Finance has at least 3 modules (document checking, limits, sustainability). The active clusters are real engineering, not registry entries.

The integrity bar is non-negotiable. Inflating "active" status to a registration-only flip would be visible to Ecobank on any deeper inspection (code review, audit-gate output, end-to-end demo) and would damage the platform's most valuable asset: the audit-locked claim discipline established across 75 batches of v10.x.

---

## Live cluster status

### ✅ Closed clusters (8 + 1 partial = 91 standards)

These ship today, no work needed. Real engines, real registry entries, past-dated batches:

| Cluster | Range | Status | Lead engines |
|---|---|---|---|
| Credit Module | #119–130 | 12/12 active | credit_committee, credit_risk_scoring, credit_workflow + 9 more |
| Reconciliation | #181–190 | 10/10 active | reconciliation_engine, partner_supplier_recon |
| Audit | #201–210 | 10/10 active | audit_universe, audit_findings, audit_workflow + 7 more |
| Legal | #221–230 | 10/10 active | legal_hold_management, legal_dashboard, legal_document_management + 7 more |
| Treasury | #231–240 | 10/10 active | treasury_intelligence, intraday_liquidity, irrbb + 7 more |
| Revenue Assurance | #241–248 | 8/8 active | revenue_anomaly_patterns, revenue_validation_agents + 6 more |
| Finance | #249–258 | 10/10 active | financial_close, group_consolidation, predictive_finance + 7 more |
| Credit Risk Gov | #259–268 | 10/10 active | credit_model_validation, model_risk_governance + 8 more |
| Trade Finance | #269–280 | 11/12 active | trade_finance_document_checking, trade_finance_limits + 9 more |

**Trade Finance has 1 planned standard** (#272 SWIFT Integration most likely). It will be addressed in the SWIFT-adjacent cluster batch.

### ❌ Open clusters (10 clusters, 103 standards)

These are the work of Phase 2A. Ordered by complexity-adjusted commercial leverage:

| # | Cluster | Range | Count | Target batch | Cluster theme |
|---|---|---|---|---|---|
| 1 | SLA Tracker | #379–388 | 10 | v10.271 | SLA registry + monitoring + breach + dashboard + reporting + early warning + BSC integration + analytics |
| 2 | Specialized Segments | #359–368 | 10 | v10.272 | Women / Diaspora / Asset Finance / Agri-business / Youth banking + tagging + segment P&L |
| 3 | Partnerships | #369–378 | 10 | v10.273 | Partner master data + MOU + scorecard + commission + portal + ecosystem analytics |
| 4 | Bancassurance | #301–310 | 10 | v10.274 | Insurance product catalog + AI recommender + claims + commission + customer 360 + RM desktop + IRA |
| 5 | Customer Behavioral | #337–348 | 12 | v10.275 + v10.276 | Interaction capture + mobile/branch tracking + behavioral profile + pattern detection + journey + decline prediction |
| 6 | Propositions | #349–358 | 10 | v10.277 | Design workbench + governance + eligibility + dynamic pricing + orchestration + A/B testing + cohorts |
| 7 | Competitor Intel | #327–336 | 10 | v10.278 | Automated collection + rate intelligence + digital strategy + radar + alerts + gap analysis + SBU view |
| 8 | Campaigns | #389–398 | 10 | v10.279 | Design workbench + multi-channel + behavioral triggers + personalization + dashboard + A/B + ROI |
| 9 | Command Centre | #311–320 | 10 | v10.280 | Strategic pulse + alerts + predictive + what-if simulator + AI copilot + crisis + board portal |
| 10 | IT / Digital | #291–300 | 10 | v10.281 + v10.282 | ITSM + cloud-native + observability + DR/BCM + API gateway + encryption + CI/CD + multi-tenancy |
| 11 | Trade Finance #272 SWIFT | (within #269–280) | 1 | v10.283 | SWIFT Integration — the lone planned standard in the otherwise-closed Trade Finance cluster |

**Closure batches:**

| # | Theme | Target batch |
|---|---|---|
| 12 | QA Map document — Ecobank presentation deliverable | v10.284 |
| 13 | Phase 2A retrospective + master prompt update + memory rebaseline | v10.285 |

**Total estimated batches: 16 (v10.270–v10.285).** The Phase 1D retro estimated 5–8 batches for the bank-level pipeline; Phase 2A is materially larger because it covers 10 clusters of new engines, not one focused pipeline.

---

## Cluster ordering rationale

The order above reflects three considerations:

1. **Commercial leverage to Ecobank.** Clusters that materially differentiate A2Z from competitors (SLA Tracker, Specialized Segments, Bancassurance, Customer Behavioral) come first. These are areas where global vendors like nCino and Blend have generic offerings; Kenya-specific intelligence (M-PESA integration, women banking, agri-business) is where A2Z can win.

2. **Engineering ramp.** Earlier batches build engines that later batches consume:
   - SLA Tracker #379–388 ships an SLA registry + breach engine that later clusters reference (Bancassurance has SLAs to insurance partners; Partnerships has SLAs to MOU counterparts; Campaigns has SLAs to multi-channel orchestration vendors).
   - Customer Behavioral #337–348 ships behavior tracking that Propositions and Campaigns consume for personalization.

3. **IT/Digital last.** Cluster #10 (IT/Digital infrastructure — ITSM, cloud-native, DR/BCM, multi-tenancy) is the most cross-cutting and the most legitimately deferrable. It gets the last engineering slot because (a) it underpins everything else but (b) the underlying disciplines (observability, CI/CD, encryption) are partially covered by existing v8.x infrastructure work.

---

## Engineering pattern per cluster batch

Each cluster batch follows the same shape established by Phase 1D and the v5.x volume batches:

```
1. New engine modules in utils/ — typically 3–6 modules per cluster
   (some clusters need fewer — e.g., SLA Tracker is dominated by 2 large
    engines + 4 thin modules; some need more — e.g., Customer Behavioral
    spans 12 standards across 6 distinct sub-domains)

2. Smoke-level self-tests for each engine
   (the v5.x pattern: a `_self_test()` function inside each module that
    runs at import time when SELF_TEST_ON_IMPORT env var is set)

3. Standards registry updates: flip the cluster's standards from
   "planned" → "active" with implementation_batch set to the current
   batch number

4. A cluster-level audit gate where the discipline calls for it
   (e.g., G164 sla_tracker_engines_registered — verifies that the SLA
    registry has at least the spec-mandated event types and that the
    breach engine returns deterministic outputs for fixture inputs)

5. CHANGELOG with explicit honest acknowledgements section listing
   what the cluster engines DO and DO NOT cover relative to the
   Continuation.docx spec.
```

The honest acknowledgements section is critical. The Continuation.docx spec is aspirational in places (e.g., "AI Executive Assistant Copilot" — Standard #315 — describes a generative-AI feature). The cluster batch ships a deterministic version that delivers the operational capability while flagging the LLM-augmented version as future work. Same Rule 7 (no silent ML predictions) discipline that's been applied across v6+ Cat D standards.

---

## Audit gate strategy

Existing audit gates G1–G163 already cover the majority of structural properties. New gates per cluster are added only when there's a discipline-specific invariant worth locking:

| Cluster | New gate | Rationale |
|---|---|---|
| SLA Tracker | G164 sla_engines_registered | Locks the SLA registry's event-type catalog and breach severity bands byte-for-byte |
| Specialized Segments | (no new gate) | The 5 segment engines (Women / Diaspora / etc.) compose existing customer_segmentation and customer_value_segments — no new structural invariant |
| Partnerships | G165 partner_lifecycle_states | Locks the partner master data lifecycle state machine (no skip transitions) |
| Bancassurance | G166 bancassurance_compliance | Locks IRA-mandated disclosure fields in policy documents |
| Customer Behavioral | G167 behavioral_event_taxonomy | Locks the interaction event taxonomy across mobile / branch / digital channels |
| Propositions | (no new gate) | Composes existing propensity and pricing engines |
| Competitor Intel | (no new gate) | Read-only intelligence layer; no fail-closed invariants worth locking |
| Campaigns | G168 campaign_approval_workflow | Locks the campaign approval state machine (no auto-execute without approval) |
| Command Centre | (no new gate) | Composes existing dashboards |
| IT / Digital | G169 itsm_state_machine | Locks the ITSM incident state machine |
| **+ Closure ratchets** | G170 continuation_2_coverage | INCREASE-only kaizen ratchet locking the 194/194 active count |

**Final audit gate count target:** 163 → 169–170. Conservative — only ~6–7 new gates because the existing perimeter is dense.

---

## QA Map document — the Ecobank deliverable

After the 10 cluster batches close (v10.281), v10.284 produces a single deliverable: `docs/A2Z_Continuation_2_QA_Map.md` (and its rendered PDF) that maps every one of the 194 standards to:

1. The engine module(s) that implement it
2. The relevant audit gate(s) that lock its structural properties (where applicable)
3. The implementation batch (so Ecobank can verify against the git history)
4. The honest scope statement — what the engine covers vs. what's listed as future enhancement (Rule 7 discipline applied per-standard)
5. The verification path — `python scripts/audit.py` exit code + relevant test files

The QA Map is the document Joshua presents. It's a single canonical answer to "which of the 194 are closed, and how is closure verifiable." Ecobank's evaluators can spot-check any line item by running the audit script or grepping the cited engine module.

This is the same audit-locked claim discipline established for sales collateral in v8.12–v8.16 (`scripts/docgen/_claim_validator.py` + the 4 audit-locked artifacts) extended to the QA presentation.

---

## Acceptance criteria

Phase 2A is closed when **all** of:

1. All 103 currently-planned Continuation 2 standards have status `active` with past-dated `implementation_batch`
2. Every cluster has at least one engine module per major sub-domain in `utils/`
3. Every engine has at minimum smoke-level self-tests
4. Audit at closure: 169+/169+ PASS (G164–G170 added; existing gates unchanged)
5. `docs/A2Z_Continuation_2_QA_Map.md` shipped, every standard mapped to its engine + verification path
6. PDF rendering of the QA Map shipped via the existing v8.14 docgen orchestrator (Living Doc audit-locked discipline)
7. Master prompt updated to v3.63+ with Phase 2A section
8. Phase 2A retrospective doc shipped
9. userMemories rebaseline batch — clarify that "all 468 standards complete" was inflated; truth is 194/194 of Continuation 2 closed at Phase 2A end (with explicit count of cluster engines shipped, audit gates added, lines of code)
10. Phase 1E charter (v10.269) marked "RESUMING" — Phase 1E batches v10.270–v10.275 [as originally planned] continue after Phase 2A closes

Anything short of all 10 means Phase 2A is not closed.

---

## Out of scope for Phase 2A

Honest scope-limiting list:

1. **Genuine LLM features.** Where Continuation.docx specifies AI Copilot / GenAI agents (Standards #305 Agentic Claims Processing, #315 AI Executive Assistant, etc.), Phase 2A ships the rule-based deterministic version with the canonical Rule 7 scaffolding pattern. Real LLM integration is a separate concern requiring an LLM provider, prompt engineering, output validation, hallucination guards — all of which are deferrable to a future phase.

2. **Real third-party integrations.** Standards mentioning specific external systems (SWIFT MX/MT messaging, IRA portal, KIPI patent search, Refinitiv competitive data feeds) ship the integration shim and audit-locked contract, NOT live wiring to the real third-party. Integration credentials, sandbox certifications, and production wiring are deferred.

3. **Mobile apps.** Standards #316 Mobile Command Centre and #299 Digital Banking Suite (Mobile + Web) ship the API contracts that mobile apps would consume. The mobile app projects themselves (React Native / Swift / Kotlin) remain v8.13 IP Strategy plan deferred work, consistent with the v5.51 #38 React Native scaffolding pattern.

4. **Production-grade ML training.** Where Continuation.docx specifies ML models (#119 AI-Powered Credit Decisioning Engine, #392 Personalization Engine, etc.), Phase 2A ships the deterministic scoring layer + the registered `ml_<feature>_fn` injection point. Training pipelines, model versioning, deployment, and continuous bias monitoring (#265) ship as the registered Cat D scaffolding pattern, not running ML.

5. **Multi-tenant deployment.** Standard #298 Multi-Tenancy ships the architectural contract (per-tenant data isolation, per-tenant config) but A2Z remains single-tenant for Ecobank Kenya through Phase 2A. Multi-tenant production work is post-closure.

6. **Real-time streaming infrastructure.** Where the spec implies Kafka/Pulsar-class event streaming (#181 Multi-Source Data Ingestion at high frequency, #189 Continuous/Real-time Reconciliation), Phase 2A ships periodic batch processing. Streaming infrastructure is deferred.

7. **Insurance regulator IRA portal sync.** #308 IRA Compliance & Reporting ships the report generators against the IRA spec. The IRA portal upload mechanism requires registered insurance broker credentials and is operational work post-closure.

These deferrals are NOT defects. They are honest scope statements that reflect what one batch's worth of code can deliver versus what production deployment with real third-party engagements requires. The QA Map document v10.284 lists each deferral explicitly, with the rationale and the path to closure.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Cluster batch grows beyond a single batch's scope and breaks the discipline | Pre-batch scope review: list the modules in advance, abandon if >7 modules or >2,500 lines for a single batch |
| A "registered as active" standard turns out to be uncovered on Ecobank inspection | The integrity bar above — engine must be real, not stub — is enforced at batch ship time; G170 locks the count so future regressions can't silently shrink coverage |
| User memory inflation (the "468 complete" claim) bleeds into the QA presentation | Closure batch v10.285 explicitly rebases userMemories to the audit-true count; QA Map (v10.284) is the canonical reference for the presentation, not memory |
| LLM-feature standards (#305, #315, #392) get scrutinized as fake AI | Per-standard honest scope statement in the QA Map distinguishes "deterministic engine shipped" from "LLM integration deferred" — same Rule 7 discipline that already governs Cat D engines |
| Audit gate count balloons and makes the audit slow | Conservative gate addition (~6–7 new) and existing gates unchanged; audit suite stays under 5 seconds |
| Standards added to Continuation.docx between charter and closure (scope creep) | Acceptance criterion is "all bank-level KPIs in registry at closure" — same pattern as Phase 1E; new standards are scoped into the closure batch's count |

---

## Spirit statements

1. **Real code, not registry inflation.** Every "active" status flip in Phase 2A is backed by a real engine module that can be opened, read, and verified. The integrity bar is non-negotiable.

2. **Honest scope per standard.** The Continuation.docx spec is aspirational. The shipped engines deliver the operational core. Future enhancements (LLM, real-time streaming, third-party live wiring) are explicitly deferred per-standard, not silently omitted.

3. **The QA Map is the canonical answer.** When Ecobank's evaluators ask "is Standard #X closed?", the QA Map points to engine module + audit gate + implementation batch + honest scope statement. No hand-waving.

4. **Phase 1E resumes after Phase 2A.** The bank-level pipeline is paused, not abandoned. The v10.269 charter is the bookmark. Discipline before commercial — but commercial first when the deal is on the line.

5. **Audit-locked claim discipline extends to QA closure.** The same `_claim_validator.py` mechanism that audit-locks sales collateral (v8.12 Living Doc work) extends to the QA Map. Every claim in the presentation traces to live registry state.

6. **Honesty about the gap is a feature, not a bug.** Ecobank's evaluators are senior bankers; they can tell the difference between marketing prose and real engineering. The honest acknowledgements section in each cluster's CHANGELOG demonstrates discipline — which is itself differentiating against three vendors who probably oversell.

---

## Honest acknowledgements at charter time

1. **The "468 standards complete" claim in stored memories is inflated.** Live registry: 660 total standards-registered, 265 with numeric citations, 194 from Continuation.docx, 91/194 currently active. Phase 2A closes the 103 gap and rebases the memory at v10.285.

2. **Phase 2A is materially larger than Phase 1E.** Phase 1E was 7 batches for one focused pipeline. Phase 2A is 16 batches for 10 cluster engines + QA Map + retrospective. This is honest about the engineering depth — closing 103 standards across 10 clusters is real work.

3. **Cluster batches are the unit, not standards.** "1 batch per cluster" is the discipline. Some clusters (Customer Behavioral with 12 standards across 6 sub-domains, IT/Digital with cross-cutting infrastructure) get 2 batches. This is acknowledged in the sequence above.

4. **The competitor delta isn't fully closed.** Even at 194/194 active, Continuation.docx mentions specific vendor capabilities (Octus CreditAI's GenAI, Blend's mobile-first 78% origination) that Phase 2A's deterministic engines won't match without live LLM and full mobile app projects. The QA Map is honest about this.

5. **66 consecutive clean batches at charter time.** v10.193 → v10.268. v10.269 was Phase 1E charter; v10.270 is Phase 2A charter. The discipline pattern continues — each cluster batch must maintain the streak through real engineering, not registry shortcuts.

6. **"Closure" is bounded by the integrity bar.** A standard counts as closed only when its engine is real, tested, and registered. This is the highest possible bar that's still achievable in 16 batches; a higher bar (full UI integration, full third-party wiring) is months of work. The QA Map distinguishes engine-level closure from full-stack closure honestly.

7. **Phase 1E will resume.** When Phase 2A closes (v10.285), Phase 1E batches v10.270–v10.275 [renumbered to v10.286–v10.291 after Phase 2A] continue. The bank-level pipeline gets G143 to 100% as the v10.269 charter laid out.

---

## What "winning the Ecobank deal" looks like at the end

By v10.285:

- 194/194 of Continuation 2 standards = active (engine + tests + registry batch + honest scope)
- 8 new audit gates (G164–G170 + closure ratchet)
- ~30–50 new engine modules in `utils/`
- 1 QA Map document (`docs/A2Z_Continuation_2_QA_Map.md` + PDF)
- Master prompt updated to v3.63+
- userMemories rebased (no more "468 complete" claim)
- 82 consecutive clean batches (v10.193 → v10.285)
- Phase 1E charter intact, ready to resume

That's the deliverable Joshua presents to Ecobank. Real engineering, audit-locked claims, honest scope, verifiable via `python scripts/audit.py`.

The competing vendors will probably show slick UI demos and gloss over implementation depth. A2Z's pitch is the opposite: "here's the QA Map, here's the audit script, here's every line of code that backs every claim, ask any line item and we'll show you the engine."

That's the sale.

---

— v10.270 charter, May 2026
