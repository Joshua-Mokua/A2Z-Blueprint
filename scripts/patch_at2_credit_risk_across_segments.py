#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
AT2 - credit risk works across every segment, so it may attach to any case.

RULING (2026-08-25): "those in that list with no segment belong to credit risk
now, and for them they have visibility across all the segments."

AT1 let a SEGMENT analyst attach to her segment's cases, and the check then
showed who was still refused on a consumer case:

    Loise Wanjiku Gachigua   Corporate Credit Analyst      cib         403
    George Nyamai Jimmy      Corporate Credit Analyst      cib         403
    Brian Ong'era Ontita     Credit Analyst                commercial  403
    Dennis Mwangi Mutiga     Credit Analyst                commercial  403

    Paul Macharia Kirega     Credit Administration Officer  -          403
    Alex Odanga Ochieng      Credit Administration Officer  -          403
    Justus Kimutai Korir     Credit Risk Manager            -          403
    Thomas Okumu             Director, Credit Risk Mgmt     -          403
    Joseph Onyango Odipo     Regional Head Remedial CESA    -          403
    Sharon Osimbo Ombonya    Remedial Officer               -          403

THE FIRST FOUR ARE CORRECT. A CIB analyst and a Commercial analyst have no
business putting papers on a Consumer case, and AT1 refusing them is the point
of having segments at all.

THE LAST SIX ARE THE RULING. Credit risk, credit administration and remedial
are not segment functions - they meet every case in the bank at their own
stage, which is exactly why _analyst_segment returns "" for them.

WHY NOT SIMPLY "NO SEGMENT MAY ATTACH TO ANYTHING": because "" also means the
register could not place somebody. A Quality Analyst, a Business Analyst, a
role spelled unusually - all return "". Treating an empty segment as a licence
would hand every case in the bank to anybody the register failed to classify.

So the test is on the ROLE, named explicitly:

    credit risk · credit administration · credit admin · remedial ·
    recover · chief credit · director credit · head of credit

A NAMED LIST IS THE POINT. It is auditable, it is arguable, and adding to it is
a decision somebody makes rather than a side effect of a blank field.

THIS GRANTS ATTACHMENT ONLY. Deciding, submitting and editing are untouched.

Usage (from project root, .venv active):
    python scripts\patch_at2_credit_risk_across_segments.py            # dry run
    python scripts\patch_at2_credit_risk_across_segments.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_at2"

OLD = '''    _seg_ok = False
    try:
        from utils.api_lms_scope import _analyst_segment, _app_segment
        _mine = (_analyst_segment(str(user.get("role", "") or ""),
                                  str(user.get("staff_code", "") or "")) or "")
        _theirs = (_app_segment(app) or "")
        _seg_ok = bool(_mine) and bool(_theirs) and _mine == _theirs
    except Exception as exc:  # surfaced, never silent (CGR1)
        logger.warning("segment check failed while attaching to %s: %s",
                       app_id, exc)'''

NEW = '''    _seg_ok = False
    try:
        from utils.api_lms_scope import _analyst_segment, _app_segment
        _mine = (_analyst_segment(str(user.get("role", "") or ""),
                                  str(user.get("staff_code", "") or "")) or "")
        _theirs = (_app_segment(app) or "")
        _seg_ok = bool(_mine) and bool(_theirs) and _mine == _theirs

        # ── CREDIT RISK MEETS EVERY SEGMENT ─────────────────────────────────
        # RULING (2026-08-25): "those with no segment belong to credit risk,
        # and for them they have visibility across all the segments."
        #
        # Credit risk, credit administration and remedial are not segment
        # functions. They meet every case in the bank at their own stage,
        # which is precisely why _analyst_segment returns "" for them.
        #
        # THE TEST IS ON THE ROLE, NOT ON THE EMPTY SEGMENT. "" also means the
        # register could not place somebody - a Quality Analyst, a Business
        # Analyst, a title spelled unusually. Treating a blank segment as a
        # licence would hand every case in the bank to anybody the register
        # failed to classify.
        #
        # The list is named so it can be audited and argued with. Adding to it
        # is a decision somebody makes, not a side effect of a blank field.
        _CROSS_SEGMENT = (
            "credit risk", "credit administration", "credit admin",
            "remedial", "recover", "chief credit", "director credit",
            "director, credit", "head of credit",
        )
        _role = str(user.get("role", "") or "").lower()
        if not _seg_ok and any(w in _role for w in _CROSS_SEGMENT):
            _seg_ok = True
    except Exception as exc:  # surfaced, never silent (CGR1)
        logger.warning("segment check failed while attaching to %s: %s",
                       app_id, exc)'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "CREDIT RISK MEETS EVERY SEGMENT" in s:
        print("ABORT: AT2 looks applied.")
        return 1
    if "THE SEGMENT'S ANALYST MAY BRING PAPERS" not in s:
        print("ABORT: AT1 must be applied first - AT2 extends its check.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the segment check matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  credit risk, credit admin and remedial reach every segment")

    # The blank segment must NOT be the licence. This is the check that stops
    # an unclassified role inheriting the whole bank.
    if 'any(w in _role for w in _CROSS_SEGMENT)' not in NEW:
        print("ABORT: the grant is not gated on the role.")
        return 1
    if 'not _seg_ok and any(' not in NEW:
        print("ABORT: the role test must run only after the segment test, so a")
        print("       matched segment is still the reason where it applies.")
        return 1
    for wrong in ('not _mine', 'not _theirs', '_mine == ""'):
        if wrong in NEW:
            print("ABORT: %r appears - an EMPTY segment must never be the" % wrong)
            print("       reason somebody is let in.")
            return 1
    # Still attachment only.
    for verb in ("can_decide", "can_submit_to_dcc", "can_edit"):
        if NEW.count(verb) != OLD.count(verb):
            print("ABORT: %r changed - this grants attachment only." % verb)
            return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: named roles only, blank is not a licence")

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
    print("\nRESTART UVICORN, then:")
    print("   python scripts\\diag_who_can_attach.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
