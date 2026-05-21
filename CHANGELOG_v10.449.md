# Changelog — v10.449 Credit 4-Level Approval Hierarchy + Phone Disbursement

**Date:** 2026-05-15
**Phase:** Credit organ rescue — completing the approval hierarchy + phone workflow
**Audit:** G335 added (cumulative 336 gates)
**Tests:** 18/18 PASSED in `test_v10449_approval_hierarchy.py`
**Combined regression:** 445 v10.4xx tests PASSED (427 prior + 18 new)
**Verifier:** 851 → **859** (+8 v10.449 checks)
**G162 baseline:** 4022 (142 consecutive zero-drift batches)
**Master prompt:** v4.91 → v4.92 (lockstep — 93 consecutive batches)

**❤️ CREDIT SECTION HEALTH: 83.0% → 84.8%** (+1.8 pp). All **4 approval levels** distinctly visible. Phone disbursement live.

---

## Your directive

> "Seems we are also missing the Board Credit Committee (BCC) approval. This should align with the swim lanes as well since there are amounts that go to the board for approval. We should have Branch Credit committee approval, Credit Analyst approval, Credit Committee approval, Board Credit Committee approval. Then within the process there are limits approved by a scoring matrix and disburses mostly by phone."

The `credit_workflow` engine already had branch-tier infrastructure (TIER_BRANCH_AUTO/TIER_BRANCH_FWD, 3 branch CommitteeRole values, `determine_branch_tier()`). What was missing was the **UI surfacing all 4 levels distinctly** + **phone disbursement workflow**. This batch fixes both.

## The 4 approval levels now visible

`pages/82_credit_approvals.py` expanded from **6 → 8 tabs**, with each approval level getting its own tab:

| Level | Tab | Amount band | Approvers |
|---|---|---|---|
| 1 | 🤖 **Credit Analyst** | ≤ 500K (within scoring matrix limit) | Single analyst signature, score-banded |
| 2 | 🏢 **Branch Credit Committee** | 500K – 5M | Branch Manager + Branch Credit Manager (+Ops for forward) |
| 3 | 🏛️ **Credit Committee (CCC)** | 5M – 50M (head office central) | Head of Credit + Risk + Business + Compliance |
| 4 | ⚖️ **Board Credit Committee** | > 50M (board-level) | CEO/MD + CFO + Risk + Credit + Board Credit Member |

### Tab 2 — 🤖 Credit Analyst (NEW)

Scoring matrix made concrete with 7 score bands:

| Score band | PD ceiling | Auto-limit (KES) | Notes |
|---|---|---|---|
| AAA (≥ 850) | ≤ 1.0% | 500,000 | Top-tier; fast-track |
| AA (750-849) | ≤ 2.0% | 350,000 | Strong credit |
| A (650-749) | ≤ 4.0% | 250,000 | Acceptable; light review |
| BBB (550-649) | ≤ 7.0% | 150,000 | Sign-off + collateral |
| BB (450-549) | ≤ 12.0% | 75,000 | Higher scrutiny |
| B (350-449) | ≤ 20.0% | 30,000 | Analyst + supervisor |
| CCC (≤ 349) | > 20.0% | 0 | Decline default |

Plus: counts of apps within scoring-matrix range vs. escalating to Branch CC.

### Tab 4 — 🏛️ Credit Committee (CCC) (split from old "HO Committee Queue")

TIER_2 + TIER_3 only. Distinct count metrics for each tier, sorted TIER_3 first.

### Tab 5 — ⚖️ Board Credit Committee (NEW, split from old "HO Committee Queue")

TIER_4 only. Highest approval authority in the bank.
- Metric cards: applications at BCC · total exposure (KES M) · largest single
- Warning banner when items present
- Quorum 4/5; 80% threshold

## Phone Disbursement (NEW)

`pages/23_credit_admin.py` got a new **📞 Phone Disbursement** tab[3]:

**3 metric cards**:
- 📞 Pending phone call
- ⏳ Call attempted, awaiting follow-up
- ✅ Disbursed (phone-confirmed)

**Pending phone disbursements** table — sorted by amount, top 30.

**Phone call logging form** with 5 outcomes:
- DISBURSED
- CUSTOMER_NOT_REACHED
- KYC_DOC_OUTSTANDING
- CUSTOMER_WITHDREW
- CALLBACK_REQUESTED

Persists to `data/phone_disbursement_log.json`. Fires K028 BSC trigger.

**Recent call log** — last 50 calls with timestamps + caller.

`23_credit_admin.py` itself promoted from **112 LOC stub → 286 LOC substantial**.

## Verified outcome

| Metric | v10.448 | v10.449 |
|---|---|---|
| Audit gates | 335 | **336** (G335) |
| v10.4xx tests | 427 | **445** (+18) |
| Verifier | 851 | **859** (+8) |
| Lockstep batches | 92 | **93** consecutive |
| G162 baseline | 4022 (141) | 4022 (**142** zero-drift) |
| **Credit health** | 83.0% | **84.8%** ↑ +1.8 pp |
| Module placement | 100% | 100% ✓ |
| **Page completeness** | 57.1% | **64.3%** (9 substantial of 14) |
| Engine wiring | 75.0% | 75.0% |
| Flow coverage | 100% | 100% ✓ |
| Severity (h/m) | 2/1 | **1/1** |
| Body health (G330) | 91.1% | 91.1% ✓ |
| 360 harmony | 100% | **100%** ✓ |
| BSC rescue | 100% | **100%** ✓ |

## 10 honest acknowledgements

1. **The engine work was already there.** `TIER_BRANCH_AUTO`, `TIER_BRANCH_FWD`, branch roles, `determine_branch_tier` — all pre-existing. This batch surfaced them in the UI distinctly per your 4-level naming. No engine extension needed.

2. **Credit Analyst tab makes scoring matrix concrete.** Previously TIER_1 was "automated, no committee." Now it's "Credit Analyst approves within scoring matrix bands" — a real human step with a visible matrix.

3. **Board Credit Committee (BCC) is now distinctly visible.** Previously lumped in "HO Committee Queue" alongside TIER_2 and TIER_3. Now it has its own tab with board-specific framing + exposure metrics.

4. **Phone disbursement is the bank's actual practice.** Per your note "disburses mostly by phone" — the workflow now exists in code. Calls are logged, outcomes tracked, K028 fires.

5. **23_credit_admin promoted from stub to substantial.** 112 LOC → 286 LOC. Genuinely earns its dedicated page status now.

6. **The scoring matrix bands are illustrative banking conventions.** AAA/AA/A/BBB/BB/B/CCC with PD ceilings and KES auto-limits are reasonable defaults. Exact numbers should be reviewed by Risk + Credit policy and made admin-configurable (v10.450 or v10.451 task).

7. **Phone disbursement is independent of FLEXCUBE.** It's a logging mechanism for the operational reality of phone-confirmed disbursements. Integration with FLEXCUBE disbursement queue could be added later.

8. **Cast Vote still works across all tiers.** The vote-recording logic in tab 6 handles all 4 levels — picks up the right `COMMITTEE_REQUIREMENTS` via `determine_tier()` based on amount and `originated_at_branch`.

9. **Severity dropped from 2 high to 1 high.** Remaining "high" finding is `analytics_credit_workbench` still admin-only. v10.450 will tackle it.

10. **Backups intact.** `data/_v10449_backups/` contains snapshots of `82_credit_approvals.py`, `23_credit_admin.py`, and `22_credit_analysis.py`.

## What's left to reach Credit 95%+

| Dimension | v10.449 | Target | Remaining |
|---|---|---|---|
| Module placement | 100% | 100% | ✅ Done |
| Page completeness | 64.3% | 80%+ | 4 stubs: 39_ews, 40_collateral, 70_retailer_finance, 71_bid_bond — **v10.450** |
| Engine wiring | 75.0% | 87%+ | Wire `analytics_credit_workbench` — **v10.450** |
| Flow coverage | 100% | 100% | ✅ Done |
| Cross-organ bridges | 4/5 | 5/5 | Staff loans HR↔Credit (strand 4) — **v10.450** |

## On your end

1. Close Streamlit · extract `a2z_v10449_patch.zip` on v10.448 (overwrite all)
2. `python scripts/verify_local_state.py` → **859/859**
3. Login as Chief Credit / Head of Risk / CFO / MD / Branch Manager
4. Navigate to **🏛️ Credit Approvals** — explore all 8 tabs:
   - 🤖 Credit Analyst → see scoring matrix bands
   - 🏢 Branch Credit Committee → branch-originated queue
   - 🏛️ Credit Committee (CCC) → head office TIER_2+TIER_3
   - ⚖️ Board Credit Committee → TIER_4 board-level
5. Navigate to **💼 Credit Admin** → **📞 Phone Disbursement** tab
   - Try logging a phone call against an approved app
   - See it appear in the recent call log
6. Check `data/phone_disbursement_log.json` — your call is persisted
7. Tell me **"continue"** → v10.450 = build remaining 4 stubs + staff loans + Chief Credit Centre

## Roadmap

| Batch | Phase | Status |
|---|---|---|
| ~~v10.446~~ | Phase 1: Diagnostic (65.8% baseline) | **DONE** |
| ~~v10.447~~ | Phase 2: Wire SWIM LANE (+12 pp) | **DONE** |
| ~~v10.448~~ | Phase 3: NEW Approvals page (+5.2 pp; flow 100%) | **DONE** |
| ~~**v10.449**~~ | **4-level hierarchy + Phone disbursement (+1.8 pp)** | **DONE** |
| **v10.450** | **Phase 3-6: 4 stub buildouts + Staff loans + Chief Credit Centre** | **Next** |

**Target: Credit health 95%+ by v10.450.**

Your specific naming (Credit Analyst, Branch Credit Committee, Credit Committee, Board Credit Committee) is now in code, with phone disbursement reflecting actual operational practice. Tell me **"continue"** for v10.450.
