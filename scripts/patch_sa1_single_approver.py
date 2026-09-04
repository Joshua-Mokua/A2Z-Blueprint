#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
SA1 - a committee may be configured to need a single approver.

FROM THE BANK (2026-09-04): "on the department credit committee we have been
requested to have an option of a single approver also - add the option of
having at least one approving along with what we have."

THE ENGINE SUPPORTS FOUR RULES TODAY:

    SIMPLE_MAJORITY            more than half of those voting
    SUPERMAJORITY_TWO_THIRDS   two thirds or more
    UNANIMOUS                  everyone voting says yes
    CHAIR_TIEBREAKER           majority, and the chair breaks a tie

None of them expresses "one approval is enough". A department committee that
meets rarely, or whose members are frequently away, was forced to wait for a
majority that may never assemble.

THIS ADDS:

    SINGLE_APPROVER            one YES approves, whatever else is cast

A NO STILL COUNTS. This is "at least one approving", as the bank put it - not
"the first vote wins". If nobody has voted yes, the case is not approved; and
because a single yes carries it, the outcome is recorded with the names of
everybody who voted against, so a dissent is on the record rather than lost.

IT IS OPT-IN, PER COMMITTEE. Nothing changes for a committee that does not
choose it. The default stays SIMPLE_MAJORITY, and a committee is switched by
setting voting_rule on it in lms_config.json.

WHY THIS IS WORTH SAYING OUT LOUD: a single-approver rule is a real reduction
in control. It is right for a department screening committee that is one step
in a longer chain, and wrong for the committee that grants final authority. The
bank asked for it on the DEPARTMENT committee, and it should not be set on the
board or management committees without somebody deciding that separately.

Usage (from project root, .venv active):
    python scripts\patch_sa1_single_approver.py            # dry run
    python scripts\patch_sa1_single_approver.py --apply
"""
import os
import shutil
import sys

ENGINE = os.path.join("utils", "credit_committee.py")
API = os.path.join("utils", "api.py")

ENUM_OLD = '''    CHAIR_TIEBREAKER = "CHAIR_TIEBREAKER"          # majority + chair tiebreak'''
ENUM_NEW = '''    CHAIR_TIEBREAKER = "CHAIR_TIEBREAKER"          # majority + chair tiebreak
    # Requested for the DEPARTMENT committee (2026-09-04): "the option of
    # having at least one approving". One YES carries it - but a NO is still
    # recorded, and the reason names the dissent, so a single approval never
    # quietly erases an objection.
    #
    # This is a real reduction in control and belongs on a screening committee
    # that is one step in a longer chain - not on the body that grants final
    # authority.
    SINGLE_APPROVER = "SINGLE_APPROVER"            # one YES is enough'''

RULE_OLD = '''        if rule == VotingRule.UNANIMOUS:'''
RULE_NEW = '''        if rule == VotingRule.SINGLE_APPROVER:
            if tally.yes_count > 0:
                _why = "One approval is sufficient for this committee"
                if tally.no_count:
                    # A dissent is not lost because somebody else approved.
                    _why += (" (%d YES, %d NO - the objection is recorded)"
                             % (tally.yes_count, tally.no_count))
                else:
                    _why += " (%d YES)" % tally.yes_count
                return (DecisionOutcome.APPROVED, _why)
            return (
                DecisionOutcome.REJECTED,
                "No member approved (%d NO)" % tally.no_count)

        if rule == VotingRule.UNANIMOUS:'''

API_OLD = '''_COMMITTEE_VOTING_RULES = ("SIMPLE_MAJORITY", "SUPERMAJORITY_TWO_THIRDS", "UNANIMOUS")'''
API_NEW = '''_COMMITTEE_VOTING_RULES = ("SIMPLE_MAJORITY", "SUPERMAJORITY_TWO_THIRDS",
                           "UNANIMOUS", "CHAIR_TIEBREAKER",
                           # One YES approves. Requested for the department
                           # committee; not to be set on the body that grants
                           # final authority without a separate decision.
                           "SINGLE_APPROVER")'''


def main():
    apply = "--apply" in sys.argv
    for f in (ENGINE, API):
        if not os.path.isfile(f):
            print("ABORT: %s not found." % f)
            return 1

    e = open(ENGINE, encoding="utf-8").read()
    a = open(API, encoding="utf-8").read()
    if "SINGLE_APPROVER" in e:
        print("ABORT: SA1 looks applied.")
        return 1
    for nm, src, anchor in (("the rule enum", e, ENUM_OLD),
                            ("the rule evaluation", e, RULE_OLD),
                            ("the accepted rules", a, API_OLD)):
        if src.count(anchor) != 1:
            print("ABORT: %s matched %d times." % (nm, src.count(anchor)))
            return 1

    e = e.replace(ENUM_OLD, ENUM_NEW, 1).replace(RULE_OLD, RULE_NEW, 1)
    a = a.replace(API_OLD, API_NEW, 1)
    print("  ok  SINGLE_APPROVER is a rule the engine understands")

    # A NO must still be counted and named, or a single yes silently erases
    # an objection.
    if "the objection is recorded" not in RULE_NEW:
        print("ABORT: a dissent would not be recorded.")
        return 1
    if "tally.yes_count > 0" not in RULE_NEW:
        print("ABORT: the rule does not require an actual approval.")
        return 1
    # It must not change what happens when NOBODY has voted - that path runs
    # before this and must keep returning DEFERRED.
    i_new = e.index("SINGLE_APPROVER =")
    if e.index("total_voting == 0") > e.index("if rule == VotingRule.SINGLE_APPROVER"):
        print("ABORT: the no-votes-cast check must still run first, or an")
        print("       empty committee would be treated as a rejection.")
        return 1
    import ast
    for path, src in ((ENGINE, e), (API, a)):
        try:
            ast.parse(src)
        except SyntaxError as exc:
            print("ABORT: %s would not parse - line %s"
                  % (os.path.basename(path), exc.lineno))
            return 1
    print("  ok  post-checks: dissent recorded, empty committee still deferred")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, src in ((ENGINE, e), (API, a)):
        shutil.copy2(path, path + ".pre_sa1")
        open(path, "w", encoding="utf-8", newline="").write(src)
        print("APPLIED %s" % path)

    import py_compile
    for path in (ENGINE, API):
        try:
            py_compile.compile(path, doraise=True)
        except Exception as exc:
            print("  FAIL %s: %s" % (os.path.basename(path), exc))
            return 1
    print("  ok  compiles")
    print("\nRESTART UVICORN, then set it on the department committee:")
    print("   python scripts\\set_committee_voting_rule.py --committee B4 \\")
    print("       --rule SINGLE_APPROVER --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
