#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Hide Credit Analysis from the segment analysts, not from everybody else.

SB2 hid it from anyone whose role does not read "credit risk", then SB3 bolted
on exemptions for admins. Both were the wrong shape: a rule that hides
something from everyone and then lists who may see it will always miss
somebody - it missed the MD's office.

The intent was one sentence: the segment analysts work on Department Review,
so Credit Analysis should not be in their menu. That is a rule about THEM.

Everyone else - credit risk, admins, the MD, the business managers - keeps it.

    python scripts/patch_sb4_hide_from_analysts_only.py            # dry run
    python scripts/patch_sb4_hide_from_analysts_only.py --apply
"""
import os
import re
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "components", "Sidebar.tsx")

NEW_RULE = """              // Credit Analysis is credit risk's screen. Hidden from the
              // SEGMENT ANALYSTS only - they work on Department Review, and
              // seeing both, they could not tell which was theirs.
              //
              // Stated as a rule about them, not about everybody else: the
              // earlier shape hid it from admins and the MD's office too.
              && !(/^credit analyst\\b/i.test((user?.role ?? '').trim())
                   && item.label === 'Credit Analysis'),"""


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "Hidden from the" in s and "SEGMENT ANALYSTS only" in s:
        print("Already applied.")
        return 1

    # Replace whichever earlier shape is present.
    pat = re.compile(
        r"\n\s*//[^\n]*\n(?:\s*//[^\n]*\n)*\s*&& !\(!/credit risk/i\.test\(user\?\.role \?\? ''\)"
        r"(?:\s*\n\s*&& !isAdmin && !isAdminOrMd)?"
        r"\s*\n\s*&& item\.label === 'Credit Analysis'\),")
    m = pat.search(s)
    if not m:
        pat2 = re.compile(
            r"\n\s*&& !\(!/credit risk/i\.test\(user\?\.role \?\? ''\)"
            r"(?:\s*\n\s*&& !isAdmin && !isAdminOrMd)?"
            r"\s*\n\s*&& item\.label === 'Credit Analysis'\),")
        m = pat2.search(s)
    if m:
        s = s[:m.start()] + "\n" + NEW_RULE + s[m.end():]
    else:
        # No earlier version on this box - add the rule fresh, beside the one
        # that already hides Department Review from credit risk. SB2 and SB3
        # were interim shapes; this is the one that stands, and it does not
        # need them to have been applied.
        # Insert BEFORE the trailing comma - that comma closes the filter
        # expression, and anything after it is a syntax error. Caught by tsc
        # on a clean tree; the first version put the rule after it.
        anchor = re.search(
            r"\n(\s*)&& !\(/credit risk\|credit admin\|remedial\|recover/i\.test\(user\?\.role \?\? ''\)"
            r"\s*\n\s*&& item\.label === 'Department Review'\)(,)", s)
        if not anchor:
            print("Could not find the Department Review rule to sit beside.")
            print("Nothing changed - send me the current lines and I will")
            print("match them rather than guess.")
            return 1
        cut = anchor.end(2) - 1          # just before the comma
        s = s[:cut] + "\n" + NEW_RULE.rstrip().rstrip(",") + s[cut:]

    if "item.label === 'Department Review'" not in s:
        print("The Department Review rule was lost.")
        return 1
    if s.count("Credit Analysis'),") != 1:
        print("The rule appears %d times." % s.count("Credit Analysis'),"))
        return 1
    if s.count("{") != s.count("}") or s.count("(") != s.count(")"):
        print("Braces unbalanced.")
        return 1
    print("Hidden from Credit Analyst roles only.")

    print("\n  WHO SEES IT NOW")
    import re as _re
    for who, role in (("Korir", "Credit Risk Manager"),
                      ("Catherine", "Credit Analyst"),
                      ("Brian", "Credit Analyst"),
                      ("Joshua", "Business Manager"),
                      ("Sera", "Head, CAD"),
                      ("the MD", "Chief Executive & Managing Director")):
        hidden = bool(_re.match(r"^credit analyst\b", role, _re.I))
        print("     %-12s %-36s %s" % (who, role, "no" if hidden else "yes"))

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_sb4")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("\nApplied %s" % MOD)
    print("Next: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
