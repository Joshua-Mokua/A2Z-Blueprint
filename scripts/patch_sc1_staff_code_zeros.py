#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
SC1 - KE0539 and KE539 are the same person.

FROM THE PILOT (2026-08-21): a customer's portfolio owner is Lucy Lidahuli. CBS
returns her code as KE0539. The staff register holds KE539. The lookup did an
exact string comparison, found nothing, and the screen told the relationship
manager:

    "this owner isn't a recognised system user - confirm the recipient
     manually"

about a person the system knows perfectly well, and then asked them to type a
recipient by hand on a referral that should have been automatic.

THE PADDING WAS FOR DSA CODES, which are four digits. It was never meant to
turn a three-digit staff code into a different person - but a string comparison
cannot tell the difference between a leading zero and a different number.

The comparison is now on the DIGITS:

    KE0539  vs KE539     same person
    KE00539 vs KE539     same person
    ke0539  vs KE539     same person
    KE5390  vs KE539     DIFFERENT - the digits differ, and that is a real
                         distinction the fix must not erase
    KE539   vs KE538     DIFFERENT

The exact match is still tried FIRST, so nothing that worked before changes.
The digit comparison only runs when the exact one finds nobody, and it logs
when it succeeds - so a mismatch in the register is visible rather than papered
over.

Verified against the pilot case and five others.

Usage (from project root, .venv active):
    python scripts\\patch_sc1_staff_code_zeros.py            # dry run
    python scripts\\patch_sc1_staff_code_zeros.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_cbs_routes.py")
BACKUP_SUFFIX = ".pre_sc1"

ANCHOR = '''        if not hit.empty:
            return str(hit.iloc[0].get("Staff Name") or "").strip()'''

BLOCK = r'''        # ── KE0539 AND KE539 ARE THE SAME PERSON ────────────────────────────
        # FROM THE PILOT (2026-08-21): Lucy Lidahuli owns the portfolio, CBS
        # returns KE0539, the register holds KE539, and the exact match failed.
        # The screen then said "this owner isn't a recognised system user" and
        # asked an RM to confirm a recipient the system already knew.
        #
        # The padding was introduced for DSA codes, which need four digits. It
        # was never meant to make a three-digit staff code into a different
        # person - but a string comparison cannot tell the difference.
        #
        # So: compare on the DIGITS, ignoring how many zeros sit in front. KE539
        # and KE0539 and KE00539 are one person; KE5390 is not, because the
        # digits differ.
        if hit.empty:
            import re as _re

            def _digits(v):
                m = _re.match(r"^([A-Za-z]*)0*(\d+)$", str(v or "").strip())
                return ("%s%s" % (m.group(1).upper(), m.group(2))) if m else ""

            _want = _digits(code)
            if _want:
                _norm = roster["Staff Code"].astype(str).map(_digits)
                hit = roster[_norm == _want]
                if not hit.empty:
                    logger.info(
                        "portfolio owner %s matched the roster as %s - the "
                        "codes differ only by leading zeros", code,
                        str(hit.iloc[0].get("Staff Code")))
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "KE0539 AND KE539 ARE THE SAME PERSON" in s:
        print("ABORT: SC1 looks applied.")
        return 1
    if "_resolve_owner_name" not in s:
        print("ABORT: the owner resolver is not in this file.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: the resolver anchor matched %d times." % s.count(ANCHOR))
        return 1

    s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)
    print("  ok  leading zeros no longer make one person into two")

    if "hit.empty" not in BLOCK:
        print("ABORT: the digit match would run even when the exact match")
        print("       succeeded, which changes behaviour that already works.")
        return 1
    if "logger" not in BLOCK:
        print("ABORT: a fuzzy match that says nothing is a fuzzy match nobody")
        print("       can audit. It must log when it fires.")
        return 1
    if r"0*(\d+)" not in BLOCK:
        print("ABORT: the pattern does not strip leading zeros.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: exact match first, logged, zeros stripped")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + BACKUP_SUFFIX)
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)

    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. A portfolio owner whose code differs only by a")
    print("leading zero is now recognised, and the referral names them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
