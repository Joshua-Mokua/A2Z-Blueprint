#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
AJ1 - a stage that moved itself says so in the journey.

"I do hope every autosubmit records in the case journey as well."

It must. AA1 makes a case advance the moment its committee recommends, so
nobody waits for the owner to sign in - which means stages now change with
nobody at a keyboard. That is precisely the entry a reader questions later:
"who moved this, and why is there no name against it?"

The journey now carries it, naming the committee whose decision moved the case
rather than leaving a silent jump between two stages:

    auto_advanced   advanced automatically to Department Credit Analysis -
                    BCC_BRN007 had recommended it, so the case did not wait to
                    be submitted

Verified: py_compile clean, and the rendering measured above.

Usage (from project root, .venv active):
    python scripts\\patch_aj1_auto_advance_journey.py            # dry run
    python scripts\\patch_aj1_auto_advance_journey.py --apply
"""
import os
import shutil
import sys

JOURNEY = os.path.join("utils", "api_lms_journey.py")
BACKUP_SUFFIX = ".pre_aj1"

ANCHOR = "    # Manager validation. The fields are already written by the validate"

BLOCK = r'''    # ── A STAGE THAT MOVED ITSELF SAYS SO ───────────────────────────────────
    # "I do hope every autosubmit records in the case journey as well."
    #
    # It must. A stage that changes with nobody at a keyboard is the one entry
    # a reader is most likely to question later - "who moved this, and why is
    # there no name against it?" - so it names the committee whose decision
    # moved it rather than leaving a silent jump between two stages.
    _auto = str(deal.get("auto_advanced_by", "") or "")
    if _auto:
        _why = _auto.split(":", 1)[1] if ":" in _auto else _auto
        events.append({
            "event": "auto_advanced",
            "by": "", "by_name": None,
            "at": _iso(deal.get("updated_at")),
            "note": ("advanced automatically to %s — %s had recommended it, so "
                     "the case did not wait to be submitted"
                     % (deal.get("stage") or "the next stage", _why)),
        })

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(JOURNEY):
        print("ABORT: %s not found." % JOURNEY)
        return 1

    s = open(JOURNEY, encoding="utf-8").read()
    if "A STAGE THAT MOVED ITSELF SAYS SO" in s:
        print("ABORT: AJ1 looks applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: the journey anchor matched %d times." % s.count(ANCHOR))
        return 1

    s = s.replace(ANCHOR, BLOCK + ANCHOR, 1)
    print("  ok  an automatic advance appears in the journey")

    if "auto_advanced_by" not in BLOCK:
        print("ABORT: the event does not read the stamp AA1 writes, so it would")
        print("       never fire.")
        return 1
    if "recommended" not in BLOCK:
        print("ABORT: the entry does not say WHY the case moved, which is the")
        print("       question a reader will have.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: reads the stamp, explains itself, parses")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(JOURNEY, JOURNEY + BACKUP_SUFFIX)
    open(JOURNEY, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % JOURNEY)
    return 0


if __name__ == "__main__":
    sys.exit(main())
