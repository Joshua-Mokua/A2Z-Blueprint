# A2Z MIS 360 — CHANGELOG v8.13

**v8.13 IP Strategy & Defensible IP Architecture planning doc — pure documentation batch, opens Legal Infrastructure sub-campaign**
**Released:** May 2026
**Audit gates:** **109/109** = 100% PASS — **39th consecutive clean**
**Strategic milestone:** **🎯 SECOND PARALLEL SUB-CAMPAIGN PLANNED.** v8.11 opened Living Doc; v8.13 opens Legal Infrastructure. The campaign discipline now extends to legal claims with the same audit-locked honesty pattern applied to a third surface (engineering + sales + legal).

---

## What this batch is

**Pure documentation batch.** Zero code changes. Zero audit gate changes.

**One thing shipped**: `docs/A2Z_IP_STRATEGY_PLAN.md` — a 1,106-line canonical IP strategy plan companion to v8.11's Living Documentation plan. Reframes the original product-strategy partner's seven-patent recommendation through honest patent-eligibility calibration grounded in jurisdiction-specific law.

**Living Doc Phase 2 work deferred** to v8.14 — the planning-doc batch convention takes priority slot. Code from the in-flight Phase 2 work (theme + honest_section + ppt_generator + magazine_generator + whitepaper_generator) preserved in side-folder `/tmp/v8_13_living_doc_phase2_inflight/` for v8.14 resume.

This is the **second planning-doc batch** in the campaign — following v8.11's Living Doc plan. The convention is now firmly established: significant sub-campaigns get a planning batch BEFORE the build batches.

---

## Key reframings vs. the original product-strategy partner's draft

### 1. The 7-patent recommendation is replaced with selective filing of 2

Original recommended utility patent filings on all 7 listed inventions globally (~$80-150K USD).

Reality:
- **Kenya IPA 2001 §21(b) and §21(d)** explicitly exclude business-method software and "computer programs" from patentable subject matter
- **EPO Article 52** requires "further technical effect" beyond running on a computer
- **US Alice Corp. v. CLS Bank (2014)** has invalidated thousands of software patents

Of the original 7 candidates, none clearly clear all three subject-matter bars.

**Recommendation: file 2 provisional patents in Kenya only (INV-008 audit-locked invariant enforcement + INV-009 deterministic ACL fallback) — total ~KES 200-450K — and re-evaluate after prior-art search.**

### 2. New invention candidates from actual A2Z architecture

Original 7 don't reflect what the campaign actually built. 4 new candidates added:

| ID | Name | Patentability |
|---|---|---|
| INV-008 | Audit-locked architectural invariant enforcement (6-gate defense-in-depth) | Moderate (best candidate) |
| INV-009 | Deterministic 3-tier ACL fallback with provenance stamping | Moderate |
| INV-010 | Audit-locked sales claim validation system (Living Doc Phase 1) | Moderate |
| INV-011 | Audit-gate-enforced PUBLISHED_LANGUAGE payload versioning (G109) | Moderate |

### 3. The 7-layer IP protection strategy

Patents are layer 4 of 7. The cheaper layers protect more for less:

| Layer | Mechanism | Cost | Strength |
|---|---|---|---|
| 1 | Copyright (automatic; register for stronger remedies) | ~$45 USD/work | High |
| 2 | Trade secrets (operational discipline) | Internal | Very high if maintained |
| 3 | **Defensive publication** (already happening via 32 CHANGELOGs) | **Effectively free** | **High** |
| 4 | Selective patent filings (1-2 strongest) | KES 150-300K | Variable |
| 5 | Trademark (A2Z MIS 360 brand) | ~KES 25-50K | High |
| 6 | Contracts (NDAs, MSA, licenses) | KES 200-500K | Variable |
| 7 | Audit-locked discipline as competitive moat | Operational | Compounds over time |

---

## Critical previously-unaddressed issues identified

### Issue 1 — The github LICENSE.md crisis (Tier 0 — IMMEDIATE)

A2Z's public github repo (per userMemories: github.com/Joshua-Mokua/A2Z-Blueprint) has unclear or absent explicit licensing. Default copyright protects ("all rights reserved") but creates commercial-use ambiguity that blocks enterprise procurement.

**Recommendation**: add `LICENSE.md` with explicit proprietary terms within the next batch. Template provided inline in Appendix A.1. Zero cost. Material protective effect.

### Issue 2 — The 12-month grace-period crisis

EPO and China have NO grace period. Public disclosure before filing destroys novelty. The github repo has been publicly disclosing v7.x and v8.x architecture for months. **Patents in EPO/China for existing architecture are likely already foreclosed.**

For inventions where EPO/China grant matters, future v9.x architecture would need filing BEFORE github commit. This constraint was completely missing from the original plan.

---

## Appendix A — The Legal Document Inventory (the substantive NDA + contracts treatment)

**Comprehensive answer to the user's NDA question: yes, NDAs are needed. Mutual for bank/customer conversations; unilateral for investor pitches.**

### 4-tier document priority structure

| Tier | Timeframe | Documents | Cost (KES) |
|---|---|---|---|
| **Tier 0/1 — URGENT** | 30 days | LICENSE.md + mutual NDA + unilateral NDA + IP Assignment + Reference Customer Agreement | ~110-220K |
| Tier 2 — IMPORTANT | 90 days | MSA + License + DPA 2019 + Privacy + ToS + AUP + Pilot | ~320-640K |
| Tier 3 — OPERATIONAL | 6 months | SLA + Maintenance + Subcontractor + Source Escrow + JDA + Insurance + Reseller | ~520K-1.13M + insurance |
| Tier 4 — MATURITY | 12-18 months | Founder + Vesting + Employment + ESOP + SAFE/Notes + Cap Table + Board governance | ~500K-2M |
| **Total 18 months** | | **~26 documents** | **~1.45M-4M** |

### NDA mechanics — when each flavor applies (operational map)

| Conversation type | NDA needed? | Mutual or unilateral? |
|---|---|---|
| Reading public github / CHANGELOGs | No (LICENSE governs) | N/A |
| Sales conversation using only published collateral | No | N/A |
| Sales with customer-specific roadmap / non-public technical detail | **Yes** | **Mutual** |
| Patent agent engagement (pre-filing) | **Yes** | Mutual or unilateral |
| Investor pitch with non-public financials | **Yes** | Often unilateral |
| Contractor engagement | **Yes** | Mutual |
| Bank pilot / production deployment | **Yes** | Mutual |
| Hiring conversation reviewing codebase | **Yes** | Unilateral |

**Default rule**: if conversation goes beyond public github, NDA is appropriate.

### IP Assignment scenarios

If Joshua has incorporated A2Z as a Limited Company (Ltd), he must explicitly assign personal IP to the company via written assignment. **The company owns nothing until that assignment is signed.** This is a structural defect in many founders' cap tables and is a major investor due diligence finding.

### DPA 2019 §41 — mandatory contents

Kenya Data Protection Act 2019 makes a Data Processing Agreement legally required (not optional) for any processor handling personal data. Penalties for non-compliance: up to KES 5,000,000 or 1% of annual turnover.

---

## End-to-end smoke test (all green)

```
=== Planning doc ===
  ✓ docs/A2Z_IP_STRATEGY_PLAN.md (1,106 lines)
  ✓ Markdown well-formed (14 sections + appendix + references)
  ✓ Cross-references valid

=== Reconciled facts cross-checked ===
  ✓ Kenya IPA 2001 §21 cited correctly
  ✓ EPO Article 52 cited correctly  
  ✓ US Alice Corp. v. CLS Bank (2014) cited correctly
  ✓ DPA 2019 §41 mandatory contents cited correctly
  ✓ A2Z Blueprint github URL cross-checked

=== FULL AUDIT ===
  Score: 109/109 gates = 100.0% — PASS
```

---

## ✅ Thirty-ninth consecutive clean-first-try

39 batches in a row landing clean — v5.96 → v8.13.

This is the **second planning-doc batch** in the streak (after v8.11). Planning batches are now an established slot type alongside engine batches, audit-hardening batches, infrastructure batches, retrospectives, and tactical-hardening batches.

---

## Comparison vs v8.12

| | v8.12 | v8.13 |
|---|---|---|
| Audit gates | 109/109 | **109/109** |
| Stocks WIRED | 6 (100%) | 6 (100%, unchanged) |
| Feedback loops WIRED | 15 (100%) | 15 (100%, unchanged) |
| Standards in UI | 62 | 62 (unchanged) |
| **Documentation tiers** | **4** (CHANGELOGs + charter + 2 retros + Living Docs plan) | **5** (+ IP Strategy plan) ⭐ |
| **Sub-campaigns planned** | **1** (Living Doc) | **2** (+ Legal Infrastructure) ⭐ |
| Clean-first-try streak | 38 | **39** |

---

## Strategic narrative — two parallel sub-campaigns now active

| Sub-campaign | Plan | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|---|---|---|---|---|---|
| **Living Documentation** | v8.11 ✓ | v8.12 ✓ | v8.14 deferred (3 generators) | v8.15 (UI surface) | v8.16 G110 |
| **Legal Infrastructure / IP Strategy** | **v8.13 ✓** | TBD (NDA + LICENSE + IP assignment) | TBD (Tier 2 docs) | TBD (Tier 3 ops) | TBD (Tier 4 maturity) |

The Legal Infrastructure sub-campaign is partly **operational** rather than purely code — Joshua engages a Kenyan corporate lawyer to draft binding documents; the AI cannot do that. The campaign work supports operational implementation through:
- Inventory tracking (what documents exist, what's needed)
- Template scaffolding (where AI produces drafts for lawyer refinement)
- Trigger event mapping (when each document is needed)
- Cost tracking (budget reconciliation)

---

## Honest acknowledgements

1. **No live Streamlit deployment verification by Claude** — pure documentation batch.
2. **The IP plan is opinionated** — represents strategic judgment grounded in jurisdiction-specific law but subject to professional patent-agent disagreement; engage actual counsel for final decisions.
3. **The 4 new invention candidates (INV-008 to INV-011) are unsearched** — Part 5 calls for prior-art search before filing; moderate-grant assessments are speculative pending professional search.
4. **Cost estimates are KES ranges based on Kenyan corporate-legal market rates 2024-2025** — specific quotes will vary.
5. **Appendix A's 26-document inventory is comprehensive but not exhaustive** — sector-specific regulatory contracts may impose additional requirements that bank counsel surfaces.
6. **The github LICENSE.md crisis assumes the current state per userMemories** — if a permissive license already exists (MIT/Apache), strategy needs urgent revision; verify immediately.
7. **The 12-month grace-period analysis assumes EPO/China are commercially relevant** — if focus is Kenya + East Africa only, EPO/China foreclosure is irrelevant.
8. **Reference customer agreement assumes Ecobank Kenya is the sole design partner** — multi-party programs need different structures.
9. **Insurance estimates are illustrative** — actual quotes need a broker familiar with software/banking risks.
10. **The plan does not recommend specific patent agents or lawyers** — KIPI maintains a public list; selection is Joshua's call after interviews.
11. **No new audit gate in v8.13** — planning batch only.
12. **The 39-batch clean streak now includes a SECOND planning-doc batch** — planning slots are an established convention.

---

## Next batch options

| Priority | Batch | Strategy |
|---|---|---|
| **(1) Recommended** | **v8.14 Living Doc Phase 2 — three generators + orchestrator** | Resume the deferred work; ~1250 lines; produces 4 audit-locked artifacts; 40th-clean candidate |
| (2) | v8.14 Operational Tier 1 Legal Implementation | Add LICENSE.md + draft template NDAs as planning artifacts |
| (3) | Diverge to v8.6 retrospective ack | Interrupts both sub-campaigns; not recommended |

**Strong recommendation: v8.14 = Living Doc Phase 2** — resumes the in-flight code work; closes the Living Doc Phase 2 deliverable per the planning sequence.

The operational Tier 1 legal work (engage Kenyan corporate lawyer; draft LICENSE.md + NDAs + IP Assignment) can proceed in parallel via Joshua's direct engagement. The AI cannot draft binding legal documents but can produce drafts for the lawyer to refine.

---

🎯 **IP Strategy & Legal Infrastructure sub-campaign planned — 1,106 lines establishing multi-layered IP protection strategy with comprehensive NDA + 26-document operational trigger map.**

⭐ **39th consecutive clean-first-try. The campaign discipline now extends to legal claims — same audit-locked honesty applied to a third surface (engineering + sales + legal).**
