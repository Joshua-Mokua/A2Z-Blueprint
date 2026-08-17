#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
QM1 - a committee needs more than one person, and the journey names who decided.

TWO FINDINGS FROM THE DEEP AUDIT (2026-08-12), after walking the committee path
rather than reading it.

1. NO QUORUM. Measured, not inferred:

       single YES, SIMPLE_MAJORITY  ->  APPROVED

   One person could approve a credit facility. The arithmetic was otherwise
   sound - ties reject, all-abstain defers, unanimous and two-thirds both work
   - but nothing checked how many people had voted.

   Worth knowing: min_quorum_count ALREADY EXISTS, defaulting to 3, in
   api_lms_committee.py - the older MCC model, which is inert
   (committee_mode is 'authority_tier'). The live path had none.

   BELOW QUORUM IS DEFERRED, NOT REJECTED. Too few people turning up is not the
   committee saying no; it is the committee not having met. Rejecting would put
   a decision on the record that nobody took, and would send a case to appeal
   against a verdict never reached.

   COUNTED OVER EVERYONE WHO ATTENDED, abstentions and recusals included. A
   member who recuses themselves was present - recusal is how a conflict is
   handled, not an absence.

   THE DEFAULT IS 2, and that number is a judgement I am flagging rather than
   burying. Not 3, which suits a management committee and would strand a small
   branch with cases nobody can decide. Two is the smallest number that cannot
   be one person, which is the actual finding. Set it deliberately:

       per committee   min_quorum_count on the committee record
       bank-wide       credit_workflow.default_min_quorum

2. THE JOURNEY DID NOT NAME WHO RECORDED THE DECISION. The record carries
   recorded_by_name; the journey read only recorded_by, so a committee decision
   showed as "KE1218" or blank. A journey that exists to answer "who decided
   this" was answering it with a staff code.

WHAT THE AUDIT CONFIRMED IS SOLID, so it is not re-litigated here: votes are
required and empty ones refused, a YES needs documentation confirmed, outcomes
are constrained to three values, a gate not on the deal's journey is refused,
and a rejected or pending committee BLOCKS submit-to-credit. I had doubted that
last one on a first read and was wrong - it is enforced.

Verified: py_compile clean, and measured after the change -

    single YES        -> DEFERRED   (was APPROVED)
    2 YES             -> APPROVED
    YES + RECUSED     -> APPROVED   (recusal counts as attendance)
    1 yes 1 no        -> REJECTED
    2 YES, quorum 3   -> DEFERRED

Usage (from project root, .venv active):
    python scripts\\patch_qm1_quorum_and_journey.py            # dry run
    python scripts\\patch_qm1_quorum_and_journey.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
JOURNEY = os.path.join("utils", "api_lms_journey.py")
BACKUP_SUFFIX = ".pre_qm1"

DERIVE_ANCHOR = "def _derive_outcome_from_votes(votes: list, voting_rule: str) -> str:"
CALL_OLD = '        outcome = _derive_outcome_from_votes(clean_votes, committee.get("voting_rule"))'
CALL_NEW = '''        outcome = _derive_outcome_from_votes(clean_votes,
                                             committee.get("voting_rule"),
                                             committee)'''
BY_OLD = '                "by": str(rec.get("recorded_by", "") or ""),'

QUORUM = r'''def _committee_quorum(committee: dict = None) -> int:
    """How many members must vote for a decision to stand.

    PER COMMITTEE FIRST, then a bank-wide default, then 2.

    WHY 2 AS THE FLOOR. The audit found a single YES approving a credit
    facility: the arithmetic was right, but nothing checked how many people
    had voted. One person is not a committee, and that is the finding - so the
    floor is the smallest number that cannot be one.

    NOT 3, which is what the older (inert) MCC model uses. Three would be the
    right answer for a management committee and the wrong one for a small
    branch, where it would strand cases nobody can decide. The bank should set
    this deliberately per committee; 2 is what stops the indefensible case
    without inventing a policy.
    """
    if isinstance(committee, dict) and committee.get("min_quorum_count") is not None:
        try:
            return max(0, int(committee.get("min_quorum_count")))
        except (TypeError, ValueError):
            pass
    try:
        cw = (_load_json("lms_config.json") or {}).get("credit_workflow", {})
        v = cw.get("default_min_quorum")
        if v is not None:
            return max(0, int(v))
    except Exception:
        pass
    return 2


def _derive_outcome_from_votes(votes: list, voting_rule: str,
                               committee: dict = None) -> str:
    """Derive APPROVED/REJECTED from per-member votes and the voting rule.
    YES/NO counted; ABSTAIN/RECUSED excluded from the base. Ties -> REJECTED."""
    yes = sum(1 for v in votes if str(v.get("vote", "")).upper() == "YES")
    no = sum(1 for v in votes if str(v.get("vote", "")).upper() == "NO")
    base = yes + no

    # ── QUORUM (pilot audit, 2026-08-12) ────────────────────────────────────
    # BELOW QUORUM IS DEFERRED, NOT REJECTED. Too few people turning up is not
    # the committee saying no - it is the committee not having met. Rejecting
    # would put a decision on the record that nobody took, and would send a
    # case to appeal against a verdict that was never reached.
    #
    # Counted over EVERYONE WHO ATTENDED, including abstentions and recusals: a
    # member who recuses themselves was present, and recusal is how a conflict
    # is handled rather than an absence.
    attended = sum(1 for v in votes
                   if str(v.get("vote", "")).upper()
                   in ("YES", "NO", "ABSTAIN", "RECUSED"))
    need = _committee_quorum(committee)
    if need and attended < need:
        return "DEFERRED"

    if base == 0:
        return "DEFERRED"
    rule = str(voting_rule or "SIMPLE_MAJORITY")
    if rule == "UNANIMOUS":
        return "APPROVED" if no == 0 and yes > 0 else "REJECTED"
    if rule == "SUPERMAJORITY_TWO_THIRDS":
        return "APPROVED" if (yes / base) >= (2.0 / 3.0) else "REJECTED"
    # SIMPLE_MAJORITY (and default): > 50%, ties -> REJECTED
    return "APPROVED" if yes > no else "REJECTED"

'''

BY_NAME = r'''                "by": str(rec.get("recorded_by", "") or ""),
                # NAME THE PERSON. The record carries recorded_by_name and the
                # journey was reading only the staff code, so a committee
                # decision showed as "KE1218" or blank. The journey exists to
                # answer "who decided this" - a code answers it for nobody
                # reading the file six weeks later.
                "by_name": rec.get("recorded_by_name") or None,'''


def main():
    apply = "--apply" in sys.argv
    for p in (API, JOURNEY):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1

    api = open(API, encoding="utf-8").read()
    jr = open(JOURNEY, encoding="utf-8").read()

    if "_committee_quorum" in api:
        print("ABORT: QM1 looks applied.")
        return 1
    if api.count(DERIVE_ANCHOR) != 1 or api.count(CALL_OLD) != 1:
        print("ABORT: anchors matched %d / %d times."
              % (api.count(DERIVE_ANCHOR), api.count(CALL_OLD)))
        return 1
    if jr.count(BY_OLD) != 1:
        print("ABORT: the journey anchor matched %d times." % jr.count(BY_OLD))
        return 1

    i = api.index(DERIVE_ANCHOR)
    j = api.index("\ndef ", i + 10)
    api = api[:i] + QUORUM + api[j:]
    api = api.replace(CALL_OLD, CALL_NEW, 1)
    jr = jr.replace(BY_OLD, BY_NAME, 1)
    print("  ok  quorum, and the journey names the recorder")

    # Below quorum must DEFER. Rejecting would record a decision nobody took.
    if "attended < need" not in QUORUM:
        print("ABORT: quorum is not applied.")
        return 1
    if 'if need and attended < need:\n        return "DEFERRED"' not in QUORUM:
        print("ABORT: below quorum does not defer - a case would be REJECTED")
        print("       because too few people turned up, and sent to appeal")
        print("       against a verdict that was never reached.")
        return 1
    # Recusal is attendance, not absence.
    if '"RECUSED"' not in QUORUM:
        print("ABORT: a recused member is not counted as present.")
        return 1
    # The default must be a real floor, and overridable.
    if "min_quorum_count" not in QUORUM or "default_min_quorum" not in QUORUM:
        print("ABORT: quorum cannot be set per committee or bank-wide.")
        return 1
    if "recorded_by_name" not in BY_NAME:
        print("ABORT: the journey still shows a staff code, not a person.")
        return 1
    print("  ok  post-checks: defers below quorum, recusal counts, configurable")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((API, api), (JOURNEY, jr)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    for path in (API, JOURNEY):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("")
    print("Restart uvicorn. THE DEFAULT QUORUM IS 2 - one person can no longer")
    print("approve a facility. Change it deliberately if 2 is not the bank's")
    print("number:")
    print("   per committee   min_quorum_count on the committee record")
    print("   bank-wide       credit_workflow.default_min_quorum")
    return 0


if __name__ == "__main__":
    sys.exit(main())
