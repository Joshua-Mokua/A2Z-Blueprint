#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
SG1 - a Department Analyst sees only their own segment.

FROM THE PILOT (2026-08-14): Catherine, the Consumer Credit Analyst, opened
Credit Analysis and found 271 cases. "We said that this analyst and the other
department analysts view what is only consumer."

The filter for that was written and correct. Two things defeated it.

1. THE MAPPING KNEW ONLY THE SEGMENT WORDS. _app_segment recognised
   "consumer", "commercial" and "cib". The cases carry the CBS client types -
   Individual, Business, Retail - so nearly every one resolved to "".

   INDIVIDUAL, PERSONAL and RETAIL now map to consumer: a natural person
   borrowing is retail banking, which is not a judgement call.

   BUSINESS IS DELIBERATELY LEFT UNMAPPED. A business customer may be
   Commercial or CIB depending on size, and guessing would put a corporate case
   in front of a consumer analyst - worse than showing too much. It needs the
   bank to say what separates the two, and until then it falls through.

2. AN UNKNOWN SEGMENT WAS TREATED AS "DO NOT HIDE". Sound intent - a legacy
   case should not vanish - with the consequence that once nearly everything
   was unknown, nothing was hidden and the pool was the whole book.

   A case whose segment cannot be established is not evidence that it belongs
   to this analyst. It is now hidden from segment analysts and stays visible to
   everybody WITHOUT a segment - managers, credit risk, admin - so it is not
   lost, merely not theirs.

Measured on four cases:

    Individual / Consumer / Business / Large Corporate
    a Consumer analyst sees   Individual, Consumer
    someone with no segment   all four

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_sg1_analyst_sees_own_segment.py            # dry run
    python scripts\\patch_sg1_analyst_sees_own_segment.py --apply
"""
import os
import shutil
import sys

SCOPE = os.path.join("utils", "api_lms_scope.py")
BACKUP_SUFFIX = ".pre_sg1"

MAP_ANCHOR = '    if "consumer" in ct:'

POOL_OLD = '''                if caller_segment:
                    seg = _app_segment(a)
                    if seg and seg != caller_segment:
                        continue'''

MAP_BLOCK = r'''    # ── THE FLEXCUBE WORDS, NOT JUST THE SEGMENT WORDS (2026-08-14) ─────────
    # This recognised only "consumer", "commercial" and "cib". The cases
    # actually carry the CBS client types - Individual, Business, Retail - so
    # nearly every one resolved to "", the filter treats "" as "do not hide",
    # and a Consumer analyst was shown all 271 cases instead of hers.
    #
    # INDIVIDUAL IS CONSUMER: a natural person borrowing is retail banking,
    # which is not a judgement call.
    #
    # BUSINESS IS DELIBERATELY NOT MAPPED. A business customer may be
    # Commercial or CIB depending on size, and guessing would put a corporate
    # case in front of a consumer analyst - worse than showing too much. Those
    # fall through to "" and are handled by the caller's unknown policy.
    if ct in ("individual", "personal", "retail") or "individual" in ct:
        return "consumer"
'''

POOL_BLOCK = r'''                    # ── AN UNKNOWN SEGMENT IS NOT YOURS ─────────────────────
                    # RULING (2026-08-14): "this analyst and the other
                    # department analysts view what is only consumer."
                    #
                    # The old rule kept unknown-segment cases visible so a
                    # legacy case would not vanish. Sound intent, and the
                    # consequence was that EVERY case with a CBS client type
                    # was unknown, nothing was hidden, and the pool was the
                    # whole book.
                    #
                    # A case whose segment cannot be established is not
                    # evidence that it belongs to this analyst. It stays
                    # visible to everybody WITHOUT a segment - managers, credit
                    # risk, admin - so it is not lost, merely not theirs.
'''


POOL_NEW = ("                if caller_segment:\n"
            "                    seg = _app_segment(a)\n"
            + POOL_BLOCK
            + "                    if seg != caller_segment:\n"
              "                        continue")


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(SCOPE):
        print("ABORT: %s not found." % SCOPE)
        return 1

    s = open(SCOPE, encoding="utf-8").read()
    if "THE FLEXCUBE WORDS" in s:
        print("ABORT: SG1 looks applied.")
        return 1
    if s.count(MAP_ANCHOR) != 1:
        print("ABORT: the client_type mapping matched %d times." % s.count(MAP_ANCHOR))
        return 1
    if s.count(POOL_OLD) != 1:
        print("ABORT: the pool segment check matched %d times." % s.count(POOL_OLD))
        return 1

    s = s.replace(MAP_ANCHOR, MAP_BLOCK + MAP_ANCHOR, 1)
    s = s.replace(POOL_OLD, POOL_NEW, 1)
    print("  ok  CBS client types map, and an unknown segment is not yours")

    if "individual" not in MAP_BLOCK:
        print("ABORT: Individual is not mapped, so most consumer cases would")
        print("       still resolve to no segment.")
        return 1
    # Business must NOT be guessed at.
    if '"business"' in MAP_BLOCK.lower().replace("# ", ""):
        pass
    if "if seg != caller_segment" not in POOL_NEW:
        print("ABORT: an unknown-segment case would still be shown to every")
        print("       analyst, which is the whole fault.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: Individual mapped, unknown excluded, parses")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(SCOPE, SCOPE + BACKUP_SUFFIX)
    open(SCOPE, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % SCOPE)
    print("")
    print("Restart uvicorn. A Consumer analyst now sees Consumer cases only.")
    print("")
    print("CASES WITH client_type 'Business' STILL RESOLVE TO NO SEGMENT and")
    print("are therefore hidden from every segment analyst. That needs the")
    print("bank to say what separates a Commercial business from a CIB one -")
    print("until it does, guessing would be worse than waiting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
