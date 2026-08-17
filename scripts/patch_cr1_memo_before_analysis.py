#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CR1 - the Transaction Memo is needed before analysis, not before the committee.

LIVE PILOT, minutes after GT1 (2026-08-14): "why are we going to Transaction
Memo when on this we just said it is the attachments and submit should work to
the department."

With every document attached and no committee outstanding, Submit was still
disabled, and the only hint was "Submission opens once all prerequisites are
complete."

cr_required was flat True, carrying a comment from a time when Documentation
submitted STRAIGHT TO CREDIT and the memo was the analytical artifact that went
with it. The flow has a branch committee in front of that now, and the memo is
written AFTER the committee gives its input - the Forwarding Memo card on the
same page says so in as many words.

So the gate demanded a document that does not exist yet at that point, and
nothing on screen named it: the memo is deliberately left out of the blocking
banner as "noise on the Documents tab", which was fair when it did not block
and misleading once it did.

THE MEMO IS NOW REQUIRED TO REACH THE ANALYSIS. Reaching a committee needs the
papers, which is what a committee reads.

    at Documentation                      required False   can_submit True
    at Branch Credit Committee Review     required True
    at Department Credit Committee Review required True

WHERE THERE IS NO FLOW to reason with, it stays required - dropping a
requirement silently is the wrong way to guess.

Verified: py_compile clean, and the three stages measured above.

Usage (from project root, .venv active):
    python scripts\\patch_cr1_memo_before_analysis.py            # dry run
    python scripts\\patch_cr1_memo_before_analysis.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_cr1memo"

OLD = '    cr_required = True  # CR is the baseline artifact (Josh: "a CR should suffice")'

BLOCK = r'''    # ── THE MEMO IS NEEDED LATER, NOT AT THE FIRST GATE ─────────────────────
    # RULING (2026-08-14): "why are we going to Transaction Memo when on this
    # we just said it is the attachments and submit should work to the
    # department."
    #
    # cr_required was flat True, from a time when Documentation submitted
    # straight to credit and the memo was the analytical artifact that went
    # with it. The flow has a branch committee in front of that now, and the
    # memo is written AFTER the committee gives its input - the Forwarding Memo
    # card says exactly that. So the gate was asking for a document that does
    # not exist yet, and the button sat disabled with nothing naming the cause.
    #
    # The memo is required to reach CREDIT ANALYSIS. Getting to a committee
    # needs the papers, which is what the committee reads.
    _flow_cr = [str(x) for x in (_stage_flow_for(deal.get("product_type")
                                                 or deal.get("product", "")) or [])]
    _at = _flow_cr.index(str(current_stage)) if str(current_stage) in _flow_cr else -1
    _next_stage = _flow_cr[_at + 1] if 0 <= _at < len(_flow_cr) - 1 else ""
    # Required only when the very next step is the analysis itself - or when
    # there is no flow to reason with, which keeps the old behaviour rather
    # than quietly dropping a requirement.
    cr_required = (not _flow_cr) or ("credit analysis" in _next_stage.lower()
                                     and "committee" not in _next_stage.lower())
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "THE MEMO IS NEEDED LATER" in s:
        print("ABORT: CR1 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the cr_required line matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, BLOCK.rstrip(), 1)
    print("  ok  the memo is required before analysis, not before a committee")

    if "not _flow_cr" not in BLOCK:
        print("ABORT: a product with no flow would silently lose the")
        print("       requirement. That is the wrong way to guess.")
        return 1
    if "credit analysis" not in BLOCK:
        print("ABORT: the requirement is not tied to the analysis stage.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: tied to the analysis, fails safe, parses")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. Documents alone submit to the branch committee.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
