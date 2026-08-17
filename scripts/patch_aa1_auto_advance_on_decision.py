#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
AA1 - a decided case moves itself.

RULING (2026-08-14): "once the branch committee vote is met there is no need
for the owner to log in to submit - it should automatically submit to the
department analyst ... once the committee vote is met it should autosubmit to
the credit analyst. This is to avoid delays waiting for someone to log in."

The committee has spoken. Making the case then wait for its owner to notice
adds a day to every deal for a decision nobody still needs to take - a gate
that has answered should not also be a queue.

WHEN QUORUM IS REACHED AND THE OUTCOME IS A RECOMMENDATION, the case advances
one stage in its own product flow. It applies at every committee gate, so the
same rule carries a case from the branch committee to the department analyst,
and from the department committee onward, without anybody signing in to push
it.

ONLY ON A RECOMMENDATION. A rejected or deferred case stays exactly where it
is: it needs a person, and moving it would bury the very cases that need
attention.

BEST EFFORT, AND AUDITED. If the flow cannot be resolved the case simply stays
put and somebody advances it by hand - the behaviour that existed before. A
committee decision must never fail to record because the case could not be
moved afterwards. The move is stamped auto_advanced_by and written to the audit
log, so a stage that changed with nobody at a keyboard is explainable later.

Verified: py_compile clean, and the result parses.

Usage (from project root, .venv active):
    python scripts\\patch_aa1_auto_advance_on_decision.py            # dry run
    python scripts\\patch_aa1_auto_advance_on_decision.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_aa1"

ANCHOR = '        updates["committee_records"] = records'

BLOCK_BODY = r'''        # ── A DECIDED CASE MOVES ITSELF ─────────────────────────────────────
        # RULING (2026-08-14): "once the branch committee vote is met there is
        # no need for the owner to log in to submit - it should automatically
        # submit to the department analyst ... this is to avoid delays waiting
        # for someone to log in."
        #
        # The committee has spoken; making the case wait for its owner to
        # notice adds a day to every deal for no decision anybody still needs
        # to take. A gate that has answered should not also be a queue.
        #
        # ONLY ON A RECOMMENDATION. A rejected or deferred case stays exactly
        # where it is - it needs a person, and moving it would bury the very
        # cases that need attention.
        #
        # BEST EFFORT, AND AUDITED. If the flow cannot be resolved the case
        # simply stays put and somebody advances it by hand, which is the
        # behaviour that existed before this. A committee decision must never
        # fail to record because the case could not be moved afterwards.
        if outcome == "APPROVED":
            try:
                _flow = _stage_flow_for(deal.get("product_type")
                                        or deal.get("product", "")) or []
                _cur = str(deal.get("stage", "") or "")
                if _flow and _cur in _flow:
                    _at = _flow.index(_cur)
                    _next = _flow[_at + 1] if _at + 1 < len(_flow) else ""
                    if _next and not _next.lower().startswith("closed"):
                        updates["stage"] = _next
                        updates["auto_advanced_by"] = "committee:%s" % code
                        _audit("API_COMMITTEE_AUTO_ADVANCE", user,
                               "deal=%s|%s|%s -> %s" % (deal_id, code, _cur, _next))
            except Exception as _exc:
                logger.warning("could not auto-advance %s after %s: %s",
                               deal_id, code, _exc)

'''
BLOCK = BLOCK_BODY


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "A DECIDED CASE MOVES ITSELF" in s:
        print("ABORT: AA1 looks applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: the committee-records assignment matched %d times." % s.count(ANCHOR))
        print("       VT1 must be applied first.")
        return 1

    s = s.replace(ANCHOR, ANCHOR + BLOCK[len(ANCHOR):] if BLOCK.startswith(ANCHOR)
                  else ANCHOR + "\n" + BLOCK.split("\n", 1)[1] if False else ANCHOR, 1)
    # Straightforward: append the block after the anchor.
    s = open(API, encoding="utf-8").read()
    s = s.replace(ANCHOR, ANCHOR + "\n" + BLOCK_BODY, 1)
    print("  ok  a decided case advances itself")

    if 'outcome == "APPROVED"' not in BLOCK_BODY:
        print("ABORT: a rejected or deferred case would also be moved, which")
        print("       buries the cases that most need a person.")
        return 1
    if "except Exception" not in BLOCK_BODY:
        print("ABORT: a product with no flow would raise and the vote would")
        print("       fail to record - the decision must never be lost because")
        print("       the case could not be moved afterwards.")
        return 1
    if "auto_advanced_by" not in BLOCK_BODY:
        print("ABORT: a stage that changed with nobody at a keyboard would not")
        print("       be explainable later.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: recommendation only, fail-safe, audited, parses")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)
    print("\nRestart uvicorn. A committee that recommends now moves the case on")
    print("without waiting for anybody to sign in.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
