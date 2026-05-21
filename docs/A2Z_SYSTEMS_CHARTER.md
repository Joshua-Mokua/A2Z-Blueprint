# A2Z MIS 360 — Systems Charter

> **Status**: Foundational (v7.0, May 2026)
> **Owner**: A2Z Platform Engineering
> **Supersedes**: scattered references to "system purpose" across master prompt and module docstrings
> **References**: Donella Meadows *Thinking in Systems* (Chelsea Green, 2008); Stafford Beer *The Heart of Enterprise* (Wiley, 1979); Eric Evans *Domain-Driven Design* (Addison-Wesley, 2003); John Gall *Systemantics* (Quadrangle, 1977)

This document is the **constitutional layer** for A2Z. Every module, page, batch, and design decision is governed by what's written here. When the master prompt and this document disagree, **this document wins** — and the master prompt should be updated to align.

---

## Section 1 — The One Question

A2Z MIS 360 exists to answer **one question** for the Managing Director:

> **"Is the bank on track to achieve its strategic goals, and if not, what should I do about it?"**

Every module, every standard, every feature must serve this question. Specifically:

| What we collect | Only what helps answer the question |
|---|---|
| What we calculate | Only what produces insight or enables action |
| What we surface | Only what the MD or a decision-maker needs |
| What we prioritize | Only what closes the strategy-execution gap |

**The question has two halves.** The first half ("on track?") is *measurement* — KPIs, dashboards, stress tests, BSC scores. The second half ("what should I do?") is *action* — recommendations, alerts, nudges, escalations, workflows. **A feature that does only the first half without enabling the second half is incomplete by design.**

This is the constitutional purpose. All other purposes (engine-level, module-level, page-level) are subordinate.

---

## Section 2 — The Football Team Test (acceptance criterion)

A2Z is a system, not a library, when the following holds:

> **"The Managing Director can see, in real-time, the impact of a teller's action on the bank's ROE — and trace the chain of cause-and-effect across every layer in between."**

This is borrowed from Donella Meadows' football team analogy: *a team is more than 11 players because the passing patterns, the trust, the play-calling are the system, not the individuals*. The test asks: do our 116 engines play together, or do they each run their own drills?

As of v7.0 we cannot yet pass this test fully. The acceptance criterion is documented here so we know what we are evolving toward. Each subsequent batch should advance the test, not regress it.

---

## Section 3 — Bounded Contexts (the 13 sub-domains)

Following Eric Evans' *Domain-Driven Design*, A2Z decomposes into 13 bounded contexts. Each context owns its data model, its vocabulary, and its invariants. **Cross-context integration must use one of the explicit patterns documented in Section 7.**

| # | Context | Engines (representative) | Owns |
|---|---|---|---|
| 1 | **Strategy & Cascade** | bsc_engine, target_cascade, kpi_library | Goals, weights, calibration |
| 2 | **Performance Measurement** | actuals_engine, predictive_performance, calibration | Scores, ratings, distribution |
| 3 | **HR Intelligence** | compensation_equity, employee_engagement, workforce_planning, coaching | Pay equity, engagement, flight risk |
| 4 | **Customer Intelligence** | customer_segmentation, customer_lifetime_value, customer_value, churn_prediction | RFM, CLV, segments, churn |
| 5 | **Profitability** | customer_profitability, rm_profitability, profitability_hierarchy | Customer / RM / segment P&L |
| 6 | **Credit Risk** | credit_monitoring, ifrs9_staging, behavioral_pd, expected_credit_loss | PD, LGD, EAD, ECL, staging |
| 7 | **Operational Risk** | operational_risk, internal_controls, rcsa | Risk events, COSO, deficiencies |
| 8 | **Compliance / AML** | kyc_aml_risk, transaction_monitoring, cbk_returns | KYC bands, alerts, regulatory filings |
| 9 | **Daily-Risk Trifecta** | irrbb, liquidity_lcr_nsfr, stress_testing | Rate risk, liquidity ratios, scenario impact |
| 10 | **Treasury & ALM** | treasury, alm, capital_adequacy | Asset-liability gaps, capital ratios |
| 11 | **Branch & Channels** | branch_log, channels_cost, channels_reliability, channels_income | Branch performance, channel economics |
| 12 | **Cross-sell & NBA** | cross_sell, allocation_optimizer | Next-best-action, RM-customer assignments |
| 13 | **Smart Alerts & Nudges** | smart_alerts, notifications, nudge_engine | Proactive workflows |

**Pages** (`pages/*.py`) are *user-facing surfaces* over these contexts, not contexts themselves. A single page may surface multiple contexts (e.g. `2_people.py` surfaces HR + Performance Measurement). A single context may be surfaced by multiple pages.

---

## Section 4 — System IS / IS NOT (boundary statement)

A2Z is one of three systems in the bank's IT estate. The other two are **systems of record** (ground truth) and **systems of engagement** (customer-facing). A2Z is the **system of intelligence** that sits between them.

### A2Z IS responsible for

- ✅ **Strategy cascade** — board to teller, with bidirectional feedback
- ✅ **Performance measurement** — BSC scores, KPI tracking, calibrated ratings
- ✅ **Profitability intelligence** — customer / RM / branch / segment / product P&L
- ✅ **Risk aggregation** — credit, market, operational, liquidity, compliance, COSO
- ✅ **Compliance tracking** — regulatory obligations, audit trail, CBK returns
- ✅ **Decision support** — what-if scenarios, recommendations, alerts, nudges
- ✅ **Process orchestration** — workflows that span departments
- ✅ **Strategic intelligence** — environment scanning, peer comparison, scenario planning

### A2Z is NOT responsible for

- ❌ **Core banking transactions** — Oracle FLEXCUBE 12 is the system of record for payments, deposits, loans
- ❌ **General ledger postings** — the bank's ERP is the system of record for accounting (A2Z calculates; ERP posts)
- ❌ **Customer-facing mobile / agent banking** — separate digital channels are the system of engagement (A2Z feeds recommendations; channels execute)
- ❌ **Real-time payment switching** — KEPSS, RTGS, SWIFT are systems of execution
- ❌ **Physical document storage** — the bank's DMS is the system of record for documents (A2Z indexes; DMS stores)
- ❌ **Identity & access management** — the corporate IDP (Active Directory / Okta) is authoritative (A2Z federates)

**Any feature that expands these boundaries requires explicit charter amendment**, not a batch-level decision.

---

## Section 5 — System Stocks (the six accumulators)

Following Donella Meadows: a stock is a quantity that accumulates over time. Stocks change slowly, even when flows are fast — and the system's behaviour comes from how stocks evolve, not from individual flow events.

A2Z explicitly tracks six stocks. Each stock has contributors (engines that add to it) and drainers (engines that remove from it). The stock is the **system-level memory** between flows.

| # | Stock | Unit | Contributors (+) | Drainers (−) | Owner context |
|---|---|---|---|---|---|
| 1 | **Customer base** | count | Onboarding, KYC approval | Churn, attrition, account closure | Customer Intelligence |
| 2 | **Loan portfolio** | KES | Disbursements | Repayments, write-offs, sales | Credit Risk |
| 3 | **Deposit base** | KES | Customer inflows, new accounts | Withdrawals, account closure | Treasury & ALM |
| 4 | **NPL inventory** | KES | New defaults, downgrades | Recoveries, write-offs, upgrades | Credit Risk |
| 5 | **Dormant accounts** | count | Inactivity (time-based) | Reactivation, closure | Customer Intelligence |
| 6 | **Capital base (Tier 1 + Tier 2)** | KES | Profit retention, new issuance | Losses, dividends, redemption | Treasury & ALM |

**Why six and not more.** Other quantities (e.g. RWA, branches, staff headcount) accumulate too, but they're either derived (RWA is a function of the loan portfolio) or low-frequency (branches change quarterly at most). The six listed are the ones that move daily and govern the bank's behaviour.

**Why this matters.** Most engines today operate on flows (a transaction, a survey, an assessment). Stocks are implicit — they live in the CBS database but are not first-class citizens in A2Z. v7.0 makes them first-class via `utils/system_stocks.py`.

---

## Section 6 — Hard Non-Linear Constraints (the seven invariants)

Banking has hard constraints that **cannot** be violated. These are non-negotiable and bind every transaction in the system. Today they are scattered across engines (CAR floor in 4 places, 1/3 rule in 2). v7.0 introduces a single registry (`utils/system_invariants.py`) so a regulatory change updates everywhere at once.

| # | Constraint | Threshold | Source | Engines that enforce |
|---|---|---|---|---|
| 1 | **CBK Total CAR** | ≥ 14.5% | CBK PG/03 | capital_adequacy, stress_testing |
| 2 | **CBK Tier 1 CAR** | ≥ 10.5% | CBK PG/03 | capital_adequacy |
| 3 | **LCR** | ≥ 100% | Basel III, CBK | liquidity, alm |
| 4 | **NSFR** | ≥ 100% | Basel III, CBK | liquidity, alm |
| 5 | **Single obligor limit** | ≤ 25% of core capital | CBK PG/03 | credit_monitoring |
| 6 | **Staff loan 1/3 rule** | monthly repayment ≤ net salary × 0.33 | Bank policy | staff_loans (where present) |
| 7 | **IFRS 9 staging floors** | Stage 2: 12-month ECL; Stage 3: lifetime ECL | IFRS 9 | ifrs9_staging, expected_credit_loss |
| 8 | **CBK consumer protection** | complaint resolution ≤ 14 days | CBK PG/06 | case management, smart_alerts |

These are **system-wide invariants**. Any engine, page, or workflow that affects the underlying quantity must read its threshold from the registry, not hard-code it.

When a regulator changes a threshold, the change applies in **one place** and propagates everywhere. This is Meadows' "leverage point #5: rules of the system" made operational.

---

## Section 7 — Cross-Context Integration Patterns

Following Eric Evans, cross-context integration is never accidental. It uses one of these documented patterns:

### Pattern A — **Published Language** (preferred)
A context exposes a stable data structure (e.g. `KycRiskAssessment`, `ScenarioResult`, `BSCScore`) that consumers depend on. The producer commits to backward compatibility; consumers depend on the public structure, not the internal model. Most A2Z cross-context integration uses this pattern.

### Pattern B — **Customer/Supplier**
Downstream context (customer) and upstream context (supplier) negotiate the contract together. Used when the consumer has explicit requirements (e.g. BSC needs profitability data shaped a particular way; profitability_integration is the supplier).

### Pattern C — **Anti-Corruption Layer (ACL)**
When two contexts have incompatible models, an explicit translation layer prevents one model from corrupting the other. Used at A2Z ↔ FLEXCUBE boundary (`flexcube_etl_dag` is the ACL).

### Pattern D — **Conformist**
Downstream simply uses the upstream model as-is. Acceptable for low-stakes integrations; risky for core ones. Used sparingly.

### Pattern E — **Open Host Service**
A context exposes a public API for many consumers. `bsc_engine.submit()` is an open host service.

### Pattern F — **Shared Kernel**
Two contexts share a small core (e.g. `core.py` audit logging). Use only when truly necessary; tight coupling.

**Every cross-context import must declare its pattern** in a comment. v7.0 enforces this for new integrations; existing integrations are documented retroactively in `utils/system_flows.py`.

---

## Section 8 — Mandatory Feedback Loops (the 15 designed loops)

Donella Meadows: a system is its feedback loops. A2Z has 15 designed feedback loops — some wired today, most designed but not yet wired. The registry (`utils/system_flows.py`) tracks status and freshness.

| # | Loop | From | To | Pattern | Status (v7.0) |
|---|---|---|---|---|---|
| L01 | Collections → PD recalibration | collections | behavioral_pd | Published Language | DESIGNED_NOT_WIRED |
| L02 | Customer profitability → Target cascade | customer_profitability | target_cascade | Published Language | WIRED |
| L03 | Staff campaigns → BSC engine | nudge_engine, campaigns | bsc_engine | Open Host Service | WIRED |
| L04 | Value chain health → Risk module | partnerships, vendors | operational_risk | Published Language | DESIGNED_NOT_WIRED |
| L05 | Card usage → Customer 360 | cards | customer_segmentation | Published Language | DESIGNED_NOT_WIRED |
| L06 | Stress test scenarios → Capital plan | stress_testing | capital_adequacy | Published Language | DESIGNED_NOT_WIRED |
| L07 | KYC risk band → Transaction monitoring | kyc_aml_risk | transaction_monitoring | Published Language | DESIGNED_NOT_WIRED |
| L08 | Engagement scores → Flight risk → Succession | employee_engagement | predictive_performance | Published Language | WIRED (v5.98) |
| L09 | Branch performance → Resource allocation | branch_log | allocation_optimizer | Published Language | DESIGNED_NOT_WIRED |
| L10 | Customer churn → Cross-sell prioritisation | churn_prediction | cross_sell | Published Language | DESIGNED_NOT_WIRED |
| L11 | RCSA deficiencies → Audit findings | internal_controls | audit_workflow | Published Language | DESIGNED_NOT_WIRED |
| L12 | Profitability hierarchy → BSC | profitability_hierarchy | bsc_engine | Customer/Supplier | WIRED (v5.92) |
| L13 | Compensation equity → HR planning | compensation_equity | workforce_planning | Published Language | DESIGNED_NOT_WIRED |
| L14 | Channel reliability → Customer experience | channels_reliability | smart_alerts | Open Host Service | DESIGNED_NOT_WIRED |
| L15 | FLEXCUBE actuals → All engines | flexcube_etl_dag | (many) | Anti-Corruption Layer | WIRED (foundational) |

**All 15 designed loops are WIRED today** (L01 through L15). Of the wired loops, 3 are *learning loops* (Meadows' highest-value type — outcomes recalibrate behaviour): L01, L02, L08. The other wired loops span signal-routing, customer/supplier integration, control-feedback, retention-prioritisation, branch-allocation, compensation-merit, vendor-health, card-enrichment, channel-reliability-alerts, and coordination patterns. **L14 Channel reliability → Customer experience alerts was closed in v8.4** via the new `utils/event_bus.py` lightweight file-backed event bus + `utils/channels_reliability.py` PRODUCER + `utils/smart_alerts.py` CONSUMER — bringing wired loops to **100% (15 of 15)**. The campaign's last unwired loop is now closed. Production deployment can swap the file-backed event bus for Kafka without changing producer/consumer logic.

---

## Section 9 — Information Flows (the highest leverage point)

Donella Meadows ranks 12 leverage points; for A2Z the single highest-leverage one is:

> **The information flow from individual performance to strategic outcomes.**

Specifically: a teller closes a sale → BSC actuals update → branch score moves → regional rollup updates → MD's "on track?" tile reflects the change. Every link in this chain must work, with appropriate delay, for A2Z to be a system rather than a library.

This flow is the **vertical** axis of the systems layer. The **horizontal** axis is cross-context feedback (Section 8). Both must work.

The v7.0 systems view page (`pages/91_systems_view.py`) materialises these flows as the MD's primary surface.

---

## Section 10 — Delays (where they bind)

We do **not** require every engine to declare detection / decision / response delays universally. Most A2Z calculator engines are stateless and instantaneous. **Where delays bind, they are documented explicitly** and modelled in the engine.

Delays bind in these specific contexts:

| Domain | Delay class | Engine |
|---|---|---|
| Collections aging | Stage transition (1-30, 31-60, 61-90, 91+ days) | credit_monitoring |
| Dormancy windows | 90 / 180 / 365-day thresholds | dormancy modules |
| Complaint SLA | 14-day clock per CBK PG/06 | case management |
| Stress test horizon | 1-3 year compounding | stress_testing |
| RCSA cycle | Annual / quarterly review | internal_controls |
| BSC cascade | Quarterly target review | target_cascade |
| Engagement survey | Quarterly pulse | employee_engagement |

Outside these domains, delays are not first-class — they would add friction without value. This is a deliberate scope choice. (Meadows agrees: model what binds, ignore what doesn't.)

---

## Section 11 — Gall's Law (evolutionary discipline)

> *"A complex system that works is invariably found to have evolved from a simple system that worked. A complex system designed from scratch never works and cannot be made to work."* — John Gall

**A2Z evolves toward systemhood; it is not refactored into systemhood.** This means:

1. **No big-bang refactor** to make all 116 engines feedback-loop-aware in one batch.
2. **Each batch closes one or two specific feedback loops** in the registry, with the engine modifications documented in the changelog.
3. **The systems layer (this charter, plus `system_stocks.py`, `system_flows.py`, `system_invariants.py`, `pages/91_systems_view.py`) sits ABOVE the existing engines** without modifying them. Engines keep working as-is; the systems layer adds new capability.
4. **Existing depth-batch template (v5.95+) continues** alongside systems-layer evolution. They are complementary, not competing.

The systems layer is itself a system — it must work in v7.0 as a small thing, then evolve.

---

## Section 12 — Stafford Beer's VSM (recursion check)

Beer's Viable System Model has 5 systems (S1-S5). A2Z covers all 5, with varying depth:

| System | Beer's name | A2Z coverage | Depth |
|---|---|---|---|
| **S1** | Operations | Branch / RM / product engines | ✅ Heavy |
| **S2** | Coordination (anti-oscillation) | (gap — branches can compete for customers) | ⚠️ Light |
| **S3** | Control / audit | RCSA, internal_controls, audit_log | ✅ Heavy |
| **S4** | Intelligence (environment scanning) | stress_testing, scenario planning, peer benchmarking | 🟡 Medium |
| **S5** | Policy / identity / ethos | This charter, master prompt | ✅ NEW (v7.0) |

**S2 is the explicit gap.** The bank has no anti-oscillation logic — two branches can pull the same customer, two RMs can compete for the same prospect. v7.x batches should consider S2 coordination engines (allocation_optimizer is a partial answer; not yet a complete one).

**S5 emerges with this charter.** Before v7.0 there was no explicit identity / ethos document; the master prompt was the closest approximation. This charter formalises S5.

---

## Section 13 — Acceptance criteria for "is it a system yet?"

A batch advances the systems layer if it does **all** of:

1. ✅ Adds at least one stock observation to `system_stocks.py` (or surfaces an existing stock visibly)
2. ✅ Closes at least one feedback loop in `system_flows.py` (status WIRED) OR documents one new designed loop
3. ✅ Reads at least one constraint from `system_invariants.py` instead of hard-coding
4. ✅ Cites which bounded context(s) it touches (Section 3)
5. ✅ Cites which integration pattern is used (Section 7)

Batches that don't advance the systems layer are still valid — depth batches, formalisation batches, bug fixes — but they should be honest about it in the changelog ("this batch does not advance the systems layer; it improves [X]").

The football team test (Section 2) is the long-term acceptance criterion. A2Z is a system when an MD can trace a teller's action to the bank's ROE in real-time.

---

## Section 14 — Honest acknowledgements

What this charter does NOT do (updated through v7.4):

**Resolved since v7.0** (originally listed as gaps):

1. ~~**Does not retroactively migrate the 116 existing engines** to read from `system_invariants.py`.~~ → **PARTIALLY RESOLVED v7.0.1 / v7.1**: 6 high-leverage engines now read from registry (capital_adequacy, liquidity_risk, regulatory_reporting, stress_testing, treasury_intelligence, credit_risk_scoring). Audit gates G104 (ratchet) + G105 (strict enforcement) prevent regression. ~110 lower-priority engines remain locally constant; future batches migrate as needed.
2. ~~**Does not wire the 10 currently-designed-not-wired feedback loops.**~~ → **MOSTLY RESOLVED v7.1 / v7.2 / v7.3 / v7.4**: 11 of 15 loops now WIRED. 4 remain (L04, L05, L13, L14). All 3 designed learning loops (L01, L02, L08) are firing.
3. ~~Stocks NOT_WIRED (was implicit in v7.0).~~ → **FULLY RESOLVED v7.4**: 6 of 6 stocks WIRED (100%). All running on demo defaults; FLEXCUBE / CBS integration deferred but accessor patterns are stable.
4. **Does not add new audit gates** for charter compliance. → **RESOLVED v7.0.1 / v7.1**: G104 (charter compliance ratchet) + G105 (strict enforcement of regulated-engine registry usage) added.

**Still open** (acknowledged for honesty):

5. **Does not enforce S2 coordination.** The gap remains. Beer's anti-oscillation logic (preventing two branches from competing for the same customer) is partially addressed by L09 Branch→Allocation loop (v7.4) but not fully. Closure is v7.x+.
6. **Does not solve information-flow latency.** Live MD dashboards (Section 9) still require streaming infrastructure (Kafka, real-time CDC from FLEXCUBE) that is out of scope for v7.x.
7. **Does not include peer benchmarking data.** Environment scanning (S4) remains a documented strength without live peer data; integration is a separate workstream.
8. **Demo defaults vs live data.** All 6 stocks WIRED, **5 of 6 now flow through the FLEXCUBE Anti-Corruption Layer** (`utils/flexcube_aggregator.py`, added in v7.10 + extended in v7.11). The ACL is mode-aware: live FLEXCUBE Apigee (stub today, v8.x ready) → CBS synthetic JSON files → demo defaults. capital_base remains engine-derived from `CapitalAdequacyEngine.total_capital()` which is BETTER than ACL fallback for an already-engine-computed stock. **The original 'demo defaults' open item is now ~85% resolved** — when Ecobank flips FLEXCUBE config to live mode, 5 of 6 stocks pull from real CBS automatically with zero caller code changes.
9. **Bounded-context boundaries documented but not strictly enforced.** Charter §3+§7 specify integration patterns; engines can still cross-context-import without declaring the pattern. Future audit gate could enforce.
10. **The football team test (§2) is the long-term acceptance criterion.** Today A2Z passes it for several flows (BSC cascade, profitability hierarchy, engagement→succession, stress→capital, KYC→TxnMonitor, RCSA→audit, churn→cross-sell, branch→allocation). Real-time MD trace from teller-action to ROE still requires streaming infrastructure.

The charter is itself a system. It started as a small thing in v7.0 and has evolved; it will continue to evolve.

---

*Charter v1.0 (v7.0, May 2026). Update only via explicit charter amendment in a future major version. Update STATE OF PLAY in `Master_Prompt_v3.md` to reference this charter.*
