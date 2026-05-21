# CHANGELOG v10.48 — credit_model_risk arc · ENH-268 Credit Committee Governance

**Status:** credit_model_risk arc 2/3 batches complete (closure pending v10.49)
**Audit:** 130/130 PASS · **G128:** STABLE (313 modules · 780 imports · 3 HARD baseline)
**Active standards:** 119 / 260 · **Scenario library:** 54 (4 COM-* added)

## New module

- `utils/credit_committee.py` (~770 lines · 18 self-tests) — diagnostic
  governance engine for credit committee decisions per CBK PG/03 §6.
  Pure stdlib (Decimal + frozen dataclasses + enums). Single public
  engine `CreditCommitteeEngine.evaluate(...) → DecisionResult`.

## Architecture

**Static charter** (`CommitteeCharter`):
- `members: Tuple[CommitteeMember, ...]`
- `voting_rule: VotingRule` (4 enums)
- `min_quorum_count: int`
- `required_roles: FrozenSet[CommitteeRole]` (must be present for valid decision)
- `authority_limit_kes: Decimal` (above → escalate, no vote held)
- `independent_member_min: int` (independence quorum)
- `escalation_target: str` (default "BOARD_RISK_COMMITTEE")

**Enums:**
- `CommitteeRole` — 7 values (CHAIR / CRO / CCO / CFO / HEAD_OF_CREDIT /
  INDEPENDENT_MEMBER / EXECUTIVE_MEMBER)
- `VotingRule` — 4 values (SIMPLE_MAJORITY [ties→REJECT defensively] /
  SUPERMAJORITY_TWO_THIRDS / UNANIMOUS / CHAIR_TIEBREAKER)
- `VoteValue` — 4 values (YES / NO / ABSTAIN / RECUSED)
- `QuorumStatus` — 4 values (MET / NOT_MET_HEADCOUNT /
  NOT_MET_REQUIRED_ROLE / NOT_MET_INDEPENDENT_MIN)
- `DecisionOutcome` — 6 values (APPROVED / APPROVED_WITH_CONDITIONS /
  REJECTED / DEFERRED / ESCALATED / QUORUM_FAILED)

## Decision pipeline

1. **Authority check supersedes voting.** If `facility_kes >
   authority_limit_kes`, the engine returns `ESCALATED` immediately
   without evaluating votes — a committee cannot decide outside its
   sanctioned limit, even unanimously. Vote tally is still surfaced
   in the result for record-keeping.

2. **Quorum check** (3 sub-checks):
   - Headcount ≥ `min_quorum_count`
   - All `required_roles` present (typically `{CRO}` per CBK PG/03 §6.4)
   - Independent member count ≥ `independent_member_min`

   Failure → `QUORUM_FAILED` outcome with `quorum_reason` populated.

3. **Vote tally** counts only votes from members listed as attending
   (absent-member votes silently ignored), and only the first vote
   per member (duplicates ignored). RECUSED votes count toward
   "present" but are excluded from `total_voting`.

4. **Voting rule application:**
   - `SIMPLE_MAJORITY`: strictly `> 50%` of YES vs NO; ties REJECT
     (defensive default — pick `CHAIR_TIEBREAKER` if ties should pass).
   - `SUPERMAJORITY_TWO_THIRDS`: YES ratio ≥ 0.6667.
   - `UNANIMOUS`: zero NO votes.
   - `CHAIR_TIEBREAKER`: majority wins; ties resolved by chair's vote
     (DEFERRED if chair absent or didn't cast YES/NO).
   - All-abstain → DEFERRED (`total_voting == 0`).

5. **Conditions:** APPROVED + `applied_conditions` →
   `APPROVED_WITH_CONDITIONS`.

6. **Policy override governance (CBK PG/03 §6.7):** If
   `is_policy_override=True` and outcome is APPROVED-class, the engine
   sets `escalation_required=True` and `escalation_target` to the
   charter's escalation target. Override approvals must be reported
   upward for ratification — the committee can approve, but cannot
   silence the escalation. `override_rationale` is mandatory at
   construction (raises `ValueError` if empty).

## Rule 1 / Rule 7 alignment

- `DecisionResult` (frozen dataclass) surfaces: request_id, committee_id,
  members_present_ids + roles, quorum_status, quorum_reason,
  full `VoteTally` (yes/no/abstain/recused/total_voting/total_present),
  voting_rule, outcome, rationale, conditions, is_policy_override,
  escalation_required, escalation_target, framework_refs, notes.
- All 6 dataclasses (`CommitteeMember`, `CommitteeCharter`, `Vote`,
  `CreditDecisionRequest`, `VoteTally`, `DecisionResult`) are frozen
  per Rule 7 — runtime tampering with member rosters / vote records /
  decision results is impossible.
- Engine never auto-approves a facility, never auto-disburses funds,
  never modifies the charter. Output feeds minute-recording +
  downstream disbursement / escalation workflow (caller
  responsibility).
- Decimal-internal precision for monetary thresholds.

## Validation envelope

- `CommitteeMember.__post_init__` rejects empty `member_id` / `name`.
- `CommitteeCharter.__post_init__` rejects: `min_quorum_count < 1`,
  quorum exceeding member count, negative authority limit, negative
  `independent_member_min`, duplicate member IDs.
- `CreditDecisionRequest.__post_init__` rejects: empty `request_id`,
  non-positive `facility_kes`, override flag without rationale.

## Standards registry

- **ENH-268** activated: `status: planned → active`,
  `implementation_batch: v10.33+ → v10.48`, full architectural
  description rewritten capturing the 7 roles / 4 voting rules /
  4 vote values / 4 quorum statuses / 6 outcomes, the authority-
  supersedes-voting rule, the §6.7 escalation discipline, and the
  Rule 1 / Rule 7 contracts. `regulatory_source` updated from generic
  Continuation.docx to "CBK PG/03 §6 + sound credit governance
  practice".
- Registry self-test PASS · total 260 · active **118 → 119**.

## Scenario library extension

Appended to `TREASURY_SCENARIO_LIBRARY`:

- **COM-01 Quorum met + simple majority approves** — 4 members
  present (chair + CRO + CCO + 1 independent), 3 YES / 1 NO under
  SIMPLE_MAJORITY → APPROVED, no escalation. 4 assertions.
- **COM-02 CRO absent → QUORUM_FAILED** — required role missing
  per CBK PG/03 §6.4, `quorum_reason` cites CRO absence, vote
  tally not consulted. 3 assertions.
- **COM-03 Authority limit exceeded → ESCALATED** — facility KES
  250m exceeds committee authority KES 100m, 5 unanimous YES votes
  ignored, ESCALATED to BOARD_RISK_COMMITTEE. 3 assertions.
- **COM-04 Policy override approval triggers §6.7 escalation** —
  LTV 92% vs 80% policy max approved unanimously → APPROVED with
  `is_policy_override=True`, `escalation_required=True`, framework
  refs cite §6.7. 5 assertions.

End-to-end runner: COM-01..COM-04 all PASS · **15/15 assertions**.
Scenario library 50 → **54**.

## Self-tests

- `python3 -m utils.credit_committee` → ✓ 18 tests covering
  validation envelope, all 4 quorum failure modes, all 4 voting
  rules, authority limit, conditions, policy override, recused
  votes, all-abstain deferral, provenance, duplicate-vote handling,
  absent-member-vote handling.
- `python3 -m utils.standards_registry` → ✓ self-test PASS.
- `python3 -m utils.scenario_simulator` → ✓ 18 tests (no regression).

## Gate verification

- `python3 scripts/audit.py` → **Score: 130/130 gates = 100.0% — PASS**.
- `python3 scripts/structure_audit.py` → **STABLE: HARD findings
  match baseline exactly** (313 modules · 780 imports · 60 findings
  · HARD=3). +1 module (credit_committee) · +1 import.

## credit_model_risk arc state

| Batch    | Module                                          | Standards | Status |
| -------- | ----------------------------------------------- | --------- | ------ |
| v10.47   | credit_alt_scoring                              | ENH-260   | ✅      |
| **v10.48** | **credit_committee**                          | **ENH-268** | ✅      |
| pending  | arc closure (G131 + Tier 25 + Master Prompt + UI cockpit) | closure | ⏳ |

## Lean+Compact protocol — applied

- 1 ENH per batch (ENH-268) ✅
- ~770 line module (over the ~600 target — same self-test breadth
  pattern as op_risk and liquidity_stress; trimmed at closure if
  needed)
- Engine Hub Tier addition DEFERRED to closure ✅
- Master Prompt update DEFERRED to closure ✅
- UI integration page DEFERRED to closure (per v10.46 amendment) ✅
- Audit + G128 + scenario library extension SHIPPED (non-negotiable) ✅
- Per Rule 1 every DecisionResult surfaces full provenance ✅
- Per Rule 7 engine diagnostic only — no auto-approve / auto-disburse /
  charter mutation ✅
- Decimal-internal precision for monetary thresholds ✅

## Files changed

- **NEW** `utils/credit_committee.py` (~770 lines, 18 self-tests)
- **MOD** `utils/standards_registry.py` (ENH-268 activated, ~32 lines
  description rewrite)
- **MOD** `utils/scenario_simulator.py` (+4 COM-* scenarios + library
  extension)
- **NEW** `CHANGELOG_v10.48.md`

## Honest scope notes

- The engine handles **single-meeting decisions**; multi-meeting
  workflows (decision deferred → revisited next meeting → final
  outcome) require caller-side state. Future enhancement could add
  a `DecisionHistory` ledger that links related decisions.
- **No vote weighting** — all members' votes count equally. Some
  bank charters give the chair extra weight or weight by role; this
  engine assumes equal weighting (matches CBK PG/03 default).
- **No conflict-of-interest detection** — caller must populate
  `VoteValue.RECUSED` when a member has a conflict. The engine
  trusts the caller's recusal flagging; it does not cross-check
  against an external relationship registry.
- The engine doesn't model **ratification by higher committee**
  after escalation. When `escalation_required=True`, the next-level
  committee runs its own evaluation (likely with a charter pointing
  to a higher authority limit and different membership). v10.49
  closure may compose the engine into a hierarchical workflow.

## Next batch

- **v10.49** — credit_model_risk arc closure: G131 ratchet (locks
  ENH-260 + ENH-268 + their scenarios), Engine Hub Tier 25
  (credit_alt_scoring + credit_committee), Master Prompt v3 line
  108 update, UI cockpit page wiring both engines (per v10.46
  protocol amendment).
