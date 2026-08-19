#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
QC1 - only cases that have reached a committee reach the committee queue.

RULING (2026-08-19): "from the committee side, on the manager queue, products
that don't require a committee like accounts are still flowing there. We needed
those that require the credit committee's recommendation - but those starting
and ending at the branches."

TWO WAYS A CASE ARRIVED THAT SHOULD NOT HAVE:

1. A PRODUCT WITH NO COMMITTEE AT ALL. A current account, a debit card, a fixed
   deposit - no committee stage in the flow, no committee decision to make,
   nothing for a member to do. 23 of 36 products are in this position and they
   were arriving anyway.

2. A STAGE NOBODY COULD PLACE. The filter only ran when the deal's stage could
   be FOUND in its product's flow. Where it could not, the whole block was
   skipped and the deal was INCLUDED - so every deal sitting on a stage its
   product no longer defines landed in the committee queue, whatever the
   product was.

   That is the wrong way to fail. A queue of things to vote on should hold only
   cases that have DEMONSTRABLY reached a committee, and a case nobody can
   place has demonstrated nothing. It matters more now than it did: 22 flows
   lost their Lead, Contacted, Proposal and Negotiation stages yesterday, and
   any deal still standing on one became unplaceable overnight.

   audit_200 reports unplaceable deals separately, so they stay visible rather
   than being quietly swept in here.

Measured, one manager, three deals:

    a Mortgage at Branch Credit Committee Review     in the queue
    a Current Account at Documentation               gone
    a Current Account stranded on Negotiation        gone

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_qc1_committee_queue_only_committees.py            # dry run
    python scripts\\patch_qc1_committee_queue_only_committees.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_qc1"

ANCHOR = "            if _flow and _cur in _flow:"

BLOCK = r'''            # ── A PRODUCT WITH NO COMMITTEE HAS NO BUSINESS HERE ─────────────
            # RULING (2026-08-19): "products that don't require a committee,
            # like accounts, are still flowing there. We needed those that
            # require the credit committee's recommendation - but those
            # starting and ending at the branches."
            #
            # A current account, a debit card, a fixed deposit: no committee
            # stage in the flow, no committee decision to make, nothing for a
            # committee member to do. They were arriving anyway.
            if _flow and not any("committee" in str(x).lower() for x in _flow):
                continue

            # ── AN UNPLACEABLE STAGE IS NOT A COMMITTEE STAGE ────────────────
            # The filter below only ran when the deal's stage could be FOUND in
            # its flow. Where it could not, the whole block was skipped and the
            # deal was INCLUDED - so every deal sitting on a stage its product
            # no longer defines landed in the committee queue, whatever the
            # product.
            #
            # That is the wrong way to fail. A queue of things to vote on
            # should hold only cases that have demonstrably reached a
            # committee; a case nobody can place has not demonstrated it.
            # audit_200 reports unplaceable deals separately, so they stay
            # visible rather than being quietly swept in here.
            if _flow and _cur not in _flow:
                continue

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "A PRODUCT WITH NO COMMITTEE HAS NO BUSINESS HERE" in s:
        print("ABORT: QC1 looks applied.")
        return 1
    # The same line appears in _is_deputy at a different indent, so a bare
    # count over the whole file finds two and refuses a correct edit. Anchor
    # INSIDE the queue function.
    i = s.find("def pipeline_queue_committee")
    if i < 0:
        print("ABORT: the committee queue endpoint is not in this file.")
        return 1
    j = s.find("\n@app.", i + 10)
    seg = s[i:j if j > 0 else len(s)]
    if seg.count(ANCHOR) != 1:
        print("ABORT: the filter matched %d times inside the queue."
              % seg.count(ANCHOR))
        return 1
    s = s[:i] + seg.replace(ANCHOR, BLOCK + ANCHOR, 1) + (s[j:] if j > 0 else "")
    print("  ok  non-committee products and unplaceable stages are excluded")

    if '"committee" in str(x).lower()' not in BLOCK:
        print("ABORT: a product with no committee would still arrive.")
        return 1
    if "_cur not in _flow" not in BLOCK:
        print("ABORT: an unplaceable stage would still be INCLUDED, which is")
        print("       the wrong way to fail.")
        return 1
    if BLOCK.count("continue") < 2:
        print("ABORT: one of the two exclusions does not actually skip.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: both exclusions present and skipping")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. The committee queue holds only cases that have")
    print("reached a committee.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
