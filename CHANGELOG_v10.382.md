# Changelog — v10.382 Three Deep Reviews (Phase B, Review-Before-Action)

**Date:** 2026-05-13
**Phase:** 4 (sixty-seventh arc — Phase B sixth batch — REVIEWS ONLY, no code changes)
**Audit:** G268 added
**Tests:** 10/10 PASSED in `test_v10382_three_deep_reviews.py`; **343 total**
**Verifier:** 428/428 checks pass on clean extract
**G162 baseline:** 4022 (76 consecutive zero-drift batches)
**Master prompt:** v4.25 → v4.26 (lockstep — 27 consecutive batches)

---

## Your direction (layered)

> "Continue with v10.382 (rm_profitability refactor)?, before you completely close on the customer you could consider a deep review of what is on the customer 360 which might help us, the the recommendations on kpis let us plan their implemantation note on the weights, we had a recommenation to have them configured at the admin module so you may want to do a deep review on the same as well."

Four concerns layered:
1. **Phase B continues** — confirmed
2. **Deep review Customer 360** — before completely closing the customer
3. **Plan KPI implementation** — concrete steps for the recommendations
4. **Deep review pillar weights admin module** — per earlier recommendation

I deferred the rm_profitability commitment to v10.383 to honor "review-before-action" discipline. v10.382 ships **REVIEWS ONLY** (no code changes).

## Three deliverables

### 1. `docs/CUSTOMER_360_DEEP_REVIEW_v10.382.md` (8 Parts)

Survey of `pages/34_customer360.py` — **3,314 lines**, **7 top-level tabs**:

| # | Tab | Sub-tabs |
|---|---|---|
| 1 | 🔍 Customer Lookup | — |
| 2 | 📊 Portfolio Intelligence | — |
| 3 | ⚠️ Churn Risk | 3 (Score Engine, Retention Priority, Engine Reference) |
| 4 | 💡 Next Best Action | — |
| 5 | 📈 Segment Analytics | 5+ (RFM, Value Tier, Lifecycle, Card Usage, CVS) |
| 6 | 💰 Customer Lifetime Value | 3+ (with CLV-Depth) |
| 7 | 📄 IFRS 7 / IAS 24 Disclosures | 2 |

**Strengths identified:**
- Substantial depth (Standards #58, #65, etc.)
- Churn engine + retention priority scoring
- CLV with cost allocation
- Customer Value Composite (multi-dimensional)
- IFRS 7/IAS 24 regulatory disclosures
- Engine reference tabs (§8.1 traceability)

**7 integration gaps surfaced:**
- Doesn't consume v10.378 canonical master (the **largest unmigrated page**)
- No PBT view per customer (canonical engine exists but not surfaced here)
- No segment cross-reference (CBS vs marketing conflict)
- No BSC integration (churn scores don't feed Customer Focus KPIs)
- No staff/RM context per customer
- No campaign linkage
- No pipeline linkage

**Phased migration plan:** v10.384 (preview tab) → v10.385 (Tab 1 canary) → v10.386 (PBT panel) → v10.387 (remaining tabs) → v10.388 (reconciliation strip) → v10.390 (remove preview)

### 2. `docs/KPI_IMPLEMENTATION_PLAN_v10.382.md` (9 Parts)

Concrete spec for the 9 new KPIs recommended in v10.381:

**Tier 1 — must add (5 KPIs):**

| KPI | Pillar | Unit | Direction | Suggested target | Data source |
|---|---|---|---|---|---|
| NIM | Financial | % | higher | 4.5% | mgmt_accounts + CBS (interest income / earning assets) |
| CIR | Financial | % | lower | 55% | mgmt_accounts (opex / income — pbt_computation provides both) |
| ROE | Financial | % | higher | 15% | mgmt_accounts (needs shareholders' equity field added) |
| NPS | Customer Focus | score | higher | +30 | unified master (nps_score per customer, aggregated) |
| DEP_GROWTH | Financial | % | higher | 10% | CBS aggregate (Retail+Commercial deposit growth) |

**Tier 2 — should add (4 KPIs):**

| KPI | Pillar | Notes |
|---|---|---|
| DIGITAL_ACT | Customer Focus | reads digital_engagement field from v10.378 master |
| 5 LEGAL_* SLAs | Process | Needs new SLA capture mechanism (v10.387+) |

**Two new leaf modules proposed:**
- `utils/financial_ratios_engine.py` — NIM/CIR/ROE/DEP_GROWTH
- `utils/customer_focus_engine.py` — NPS/DIGITAL_ACT

**7-batch implementation schedule** (v10.384 → v10.390) ending with first end-to-end BSC computation with all new KPIs.

### 3. `docs/PILLAR_WEIGHTS_ADMIN_MODULE_REVIEW_v10.382.md` (8 Parts)

**3 storage locations identified** for the same concept:

| # | Location | Status |
|---|---|---|
| 1 | `kpi_library.json::pillar_weights` | **CANONICAL** (5 readers) |
| 2 | `kpi_library.json::pillars[].weight` | SHADOW (read for structure, ignored for weight) |
| 3 | `org_config.json::pillar_weights` | **ORPHAN** (written by admin Bank Identity tab, **read by NOTHING**) |

**2 admin UIs editing the same concept**, one orphaned:

- Bank Identity tab — writes to dead branch (**silent failure** per §5.4)
- KPI Library → Pillar weights tab — writes to canonical location

**6 defects documented:**
1. Two admin UIs editing same concept, only one works → silent failure
2. Defaults drift between UIs (40/25/25/10 hardcoded vs 68/14/6/12 stored)
3. `pillars[].weight` is shadow data
4. Default fallback masks real config (consumers silently fall back to 40/25/25/10)
5. No audit history (audit_log fires but doesn't capture OLD/NEW values)
6. Per-role pillar weights have separate older structure

**Consolidation plan** over 5 batches v10.384-v10.389.

## Verified outcome

| Metric | Value |
|---|---|
| Three reviews delivered | **YES** (8 Parts each, body-system-framed) |
| Joshua decisions queued | **YES** (C1+ Customer 360, K1+ KPIs, W1+ Weights — 23 questions across docs) |
| No code changes shipped | **YES** (v10.382 is review-only by design) |
| Audit gates | 267 → **268** |
| All prior canonical identities | still PASS |
| Tests | +10 in v10.382; **343 total across v10.358-v10.382** |
| Verifier | 424 → **428 checks** |
| Master prompt lockstep | **27/27 consecutive batches** |
| G162 baseline | 4022 (**76 consecutive zero-drift batches**) |

## 15 honest acknowledgements

1. **The "review-before-action" discipline is yours, not mine.** I would have proceeded directly to rm_profitability refactor. Your insistence on understanding first is what creates these review documents.

2. **The biggest finding is the Bank Identity tab dead-branch.** Anyone editing pillar weights there today thinks they're changing scoring — they aren't. Silent failure per constitution §5.4. This is the kind of bug that erodes trust quietly.

3. **Customer 360 is the largest unmigrated consumer of customer_intelligence.json.** 3,314 lines reading legacy data directly. Migrating it touches 7 tabs and many sub-tabs. Phased approach is essential.

4. **MD's BSC currently can't present a complete banking story.** Without NIM/CIR/ROE/NPS, the MD cannot answer questions like "is the loan book productive?", "are costs in line?", "are shareholders being rewarded?", "do customers advocate for us?" — these are foundational banking questions. The recommendation to add all four stands.

5. **ROE has a data dependency I didn't fully resolve.** Needs shareholders' equity in mgmt_accounts.json. Calling this out so v10.384 can address it before assuming the data exists.

6. **5 LEGAL_* SLAs need new data capture mechanism** — not just engine. Pushed to v10.387+ so this doesn't bottleneck Tier 1 ratios.

7. **The pillar weights drift (40/25/25/10 vs 68/14/6/12) is real — someone deliberately set 68/14/6/12.** The deep review doesn't change it; it asks you to confirm or reverse the deliberate choice with audit trail.

8. **Reading 3,314 lines of pages/34_customer360.py for the deep review surfaced more sub-tabs than my initial count.** The page has churn engine with retention priority + engine reference, RFM with value tier + lifecycle, CLV with depth analysis. The complexity is real.

9. **Rule N2 single concern held strictly.** Three reviews are one v10.382 concern: "understand before deeper action on customer + KPI plan + weights." Each is a deep dive into a different organ of the same body.

10. **No tests for review documents would mean no enforcement.** G268 + 10 integration tests verify each review has 8 Parts, body-system framing, decisions queue, and content coverage (specific KPIs in plan, specific files in pillar review, specific tabs in Customer 360 review).

11. **The Customer 360 review surfaces an MD-cockpit insight.** Customer PBT (canonical, v10.370/376) and Customer Lifetime Value (forward-looking, in Customer 360) live in different places. Unifying them would let MD see "this customer earned us X this year, will likely earn us Y over the next 5 years."

12. **The KPI plan estimates targets that need your validation.** I suggested NIM 4.5%, CIR 55%, ROE 15%, NPS +30. These are industry-benchmark suggestions, not Ecobank Kenya's actual targets. Your call.

13. **23 Joshua decisions are queued across the three reviews.** No batch should ship without your approval on the relevant decisions. v10.383 (rm_profitability) needs no decisions — it's mechanical. v10.384+ needs your approvals.

14. **The phased Customer 360 migration plan stretches across 7+ batches.** This isn't a quick win; it's the most invasive Phase B work after v10.378. Worth doing carefully.

15. **Phase B continues with discipline.** Body-system framing held: each review identifies an organ-level concern (customer recognition organ, body's KPI sensors, body's prioritization). The body becomes self-aware about its own gaps.

## Joshua decisions queued (23 total across 3 reviews)

| Doc | # | Question |
|---|---|---|
| C1-C7 | Customer 360 | Migrate to canonical? Add Customer PBT panel? Cross-organ links? Reconciliation strip? Phasing order? Keep CLV alongside PBT? |
| K1-K8 | KPI Plan | Approve Tier 1+2? NIM weight 0.15? ROE — does mgmt_accounts have equity? NPS target? DIGITAL_ACT threshold? LEGAL_* timing? Target values? Cascade logic? |
| W1-W8 | Pillar Weights | Canonical = kpi_library? Remove Bank Identity orphan? Version history? Move to Tab 23 thresholds? 40/25/25/10 or 68/14/6/12? Per-role weights? Validation rules? Audit log every change? |

You can answer in any order. Each "yes" cascades to its respective implementation batch.

## On your end

1. Close Streamlit
2. Extract `a2z_v10382_session_cumulative.zip` flat
3. Run `python scripts\verify_local_state.py` → expect **428/428**
4. **Read all three reviews** — these are the most substantive review documents this session:
   - `docs\CUSTOMER_360_DEEP_REVIEW_v10.382.md`
   - `docs\KPI_IMPLEMENTATION_PLAN_v10.382.md`
   - `docs\PILLAR_WEIGHTS_ADMIN_MODULE_REVIEW_v10.382.md`
5. Answer any decisions you're ready on
6. Tell me to "continue" → v10.383 = rm_profitability canonical refactor (mechanical, needs no decisions)

## What comes next

**v10.383**: rm_profitability.py canonical refactor (same pattern as v10.381 customer_profitability). This is the Phase B commitment from v10.378/v10.379/v10.380/v10.381 wrap-ups, deferred by v10.382 review-first.

After v10.383, the parallel profitability engines (customer + RM) both consume v10.378.

**v10.384+** depends on your decisions. If you approve KPI Tier 1 (NIM/CIR/ROE/NPS/DEP_GROWTH): v10.384 implements them. If you approve Customer 360 phasing: v10.385+ migrates. If you approve pillar weights consolidation: parallel batches address it.

The body becomes increasingly unified. Continue with v10.383?
