#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
DUP1 - where a staff code has two rows, take the one that answers the question.

FOUND BY ALEX (2026-09-07): staff code CN205 has TWO user rows in Postgres -

    username=CN205       "Billy Owiny Ochieng"   Direct Sales Agent   Kisumu
    username=BOOCHIENG   "OCHIENG Billy"         Staff                (no branch)

The register is rebuilt from that table and inherits both. A lookup by staff
code takes whichever comes first - the incomplete one - so Billy's branch reads
as blank, VA1's branch test cannot match, and it refuses. VA1 is doing exactly
what it was built to do when it cannot see both branches; the data underneath
it is ambiguous.

THE DUPLICATE SHOULD BE CLEANED UP, and that is the real fix. This is the
guard for the meantime, and for the next one nobody has noticed yet: it is the
second time this pattern has cost a day, after Kyuma/Muthama.

WHAT THIS CHANGES: when several register rows share a staff code, the lookup
prefers the row that HAS a branch over one that does not. It does not merge
them, does not choose between two rows that both have a branch, and does not
touch a code that appears once.

    one row                      used, as now
    two rows, one has a branch   the one with the branch
    two rows, both have one      the first, as now - that is a real ambiguity
                                 and a guess would be worse than a refusal
    two rows, neither has one    the first, as now - nothing to prefer

IT IS LOGGED. A duplicate staff code is a data fault that will cause something
else later, and it should be visible rather than quietly worked around.

Usage (from project root, .venv active):
    python scripts\patch_dup1_prefer_the_complete_row.py            # dry run
    python scripts\patch_dup1_prefer_the_complete_row.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_pipeline_scope.py")

HELPER = '''def row_for_staff_code(df, code, branch_col=None):
    """The register row for a staff code, preferring one that has a branch.

    FOUND 2026-09-07: CN205 has two rows in the user table - a complete one at
    Kisumu and a stale one with no branch. A lookup by code took whichever came
    first, got the blank, and every branch test on that officer's deals failed.

    Two rows for one person is a data fault and should be cleaned up. Until it
    is, taking the row that can answer the question is better than taking the
    one that cannot - and where BOTH rows have a branch this still returns the
    first, because that is a real ambiguity and a guess would be worse than a
    refusal.
    """
    code = str(code or "").strip()
    if not code:
        return None
    try:
        hits = df[df["Staff Code"].astype(str).str.strip() == code]
    except Exception:
        return None
    if hits.empty:
        return None
    if len(hits) == 1:
        return hits.iloc[0]

    col = branch_col or ("Branch" if "Branch" in df.columns else "Unit")
    withb = [i for i in range(len(hits))
             if str(hits.iloc[i].get(col) or "").strip()]
    try:
        import logging
        logging.getLogger(__name__).warning(
            "staff code %s appears %d times in the register - %d with a %s. "
            "Using a complete row; the duplicate should be cleaned up.",
            code, len(hits), len(withb), col.lower())
    except Exception:
        pass
    if len(withb) == 1:
        return hits.iloc[withb[0]]
    return hits.iloc[0]


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "def row_for_staff_code" in s:
        print("ABORT: DUP1 looks applied.")
        return 1

    anchor = "def get_staff_roster("
    if s.count(anchor) != 1:
        print("ABORT: get_staff_roster matched %d times." % s.count(anchor))
        return 1

    s = s.replace(anchor, HELPER + anchor, 1)
    print("  ok  a helper that prefers the row with a branch")

    if "len(withb) == 1" not in HELPER:
        print("ABORT: two complete rows would be guessed between.")
        return 1
    if "logging" not in HELPER:
        print("ABORT: a duplicate staff code must be logged - it will cause")
        print("       something else later.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: no guessing between two complete rows, logged")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        print("\nTHIS ADDS THE HELPER ONLY. The places that look a staff code")
        print("up still do it their own way - VA1, BV4 and the scope engine")
        print("each have their own two lines. Pointing them here is the next")
        print("step, and it is the one that stops this recurring.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_dup1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nNOTHING BEHAVES DIFFERENTLY YET - the helper is not called from")
    print("anywhere. Cleaning up CN205's duplicate row is the fix for today.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
