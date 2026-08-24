#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
HD2 - a Head is a manager, however the register punctuates it.

FOUND 2026-08-24, checking the eight people the bank seated on its Consumer and
Commercial credit committees:

    Jane Jelagat Atugah      Head of Consumer                    manager
    Robert Githaiga Maingi   Head, Digital Channels & Agency     NOT
    Lunar Magero             Head of Sales                       manager
    Esther Wambui Mbano      Asset Product Manager               manager
    Victor Mutabari Mbaabu   Head EFS                            NOT
    Upendo Mutave Wambua     Head, SME                           NOT
    Livingstone Maina Kagio  Head, Local Corporates              NOT
    Joshua Muthama           Head of Branches                    manager

FOUR OF EIGHT, and the only difference is a comma. The keyword is "head of",
so "Head of Sales" matches and "Head, SME" does not - the same seniority, the
same committee, written two ways in one register.

Upendo signed in and had no Manager Queues at all, which is where the committee
bench lives. She was seated on B2, sent cases, and shown a pipeline that
answered 404.

THE FIX: match "head" rather than "head of".

WHAT THAT LETS IN, deliberately: "Head EFS", "Head, SME", "Head, Local
Corporates", "Department Head", "Head of Branches". Every one of them is a
manager in this bank. There is no role in the register where "head" appears and
the person is not senior - it is not a word that turns up by accident in a job
title.

BOTH LISTS CHANGE TOGETHER. lib/role.ts carries a copy of this tuple and its
own comment warns that drift between them is a real risk; the frontend decides
whether a menu appears and the backend decides whether the request is allowed,
so a change in one and not the other produces a menu that leads to a 403.

Usage (from project root, .venv active):
    python scripts\patch_hd2_head_is_a_manager.py            # dry run
    python scripts\patch_hd2_head_is_a_manager.py --apply
"""
import os
import shutil
import sys

PY = os.path.join("utils", "api_pipeline_manager_actions.py")
TS = os.path.join("frontend", "web", "src", "lib", "role.ts")
BACKUP_SUFFIX = ".pre_hd2"

PY_OLD = '''    "head of",          # Head of Retail / Head of SME / Head of Corporate'''
PY_NEW = '''    # "head" not "head of" (2026-08-24). The register writes the same rank
    # three ways - "Head of Sales", "Head, SME", "Head EFS" - and only the
    # first matched. Four of the eight people seated on the Consumer and
    # Commercial credit committees were not managers by this test, so they had
    # no Manager Queues, which is where the committee bench lives.
    #
    # Nothing junior is let in by this: there is no role in the register where
    # "head" appears and the person is not senior.
    "head",             # Head of Retail / Head, SME / Head EFS'''

TS_OLD = '''  'head of',            // Head of Retail / Head of SME / Head of Corporate'''
TS_NEW = '''  // "head" not "head of" (2026-08-24) - see the matching change in
  // utils/api_pipeline_manager_actions.py. The register writes the same rank
  // as "Head of Sales", "Head, SME" and "Head EFS", and only the first
  // matched. This file and that tuple must change together: this one decides
  // whether the menu appears, that one decides whether the request is allowed,
  // and a change in one alone produces a menu that leads to a 403.
  'head',              // Head of Retail / Head, SME / Head EFS'''


def main():
    apply = "--apply" in sys.argv
    for f in (PY, TS):
        if not os.path.isfile(f):
            print("ABORT: %s not found." % f)
            return 1

    p = open(PY, encoding="utf-8").read()
    t = open(TS, encoding="utf-8").read()
    if '"head",' in p and "'head'," in t:
        print("ABORT: HD2 looks applied.")
        return 1
    if p.count(PY_OLD) != 1 or t.count(TS_OLD) != 1:
        print("ABORT: anchors matched %d / %d times."
              % (p.count(PY_OLD), t.count(TS_OLD)))
        return 1

    p = p.replace(PY_OLD, PY_NEW, 1)
    t = t.replace(TS_OLD, TS_NEW, 1)
    print("  ok  a Head is a manager in both lists")

    # THE TWO LISTS MUST STILL AGREE. That is the whole point of the change.
    import re
    py_kw = set(re.findall(r'^\s*"([a-z ]+)",', p, re.M))
    ts_kw = set(re.findall(r"^\s*'([a-z ]+)',", t, re.M))
    if not py_kw or not ts_kw:
        print("ABORT: could not read one of the keyword lists back.")
        return 1
    drift = (py_kw ^ ts_kw) - {""}
    if drift:
        print("ABORT: the two lists disagree on: %s" % ", ".join(sorted(drift)))
        print("       A menu that appears when the request is refused is worse")
        print("       than no menu.")
        return 1
    if "head" not in py_kw:
        print("ABORT: 'head' is not in the result.")
        return 1
    print("  ok  post-checks: %d keywords, both lists identical" % len(py_kw))

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, src in ((PY, p), (TS, t)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(src)
        print("APPLIED %s" % path)

    import py_compile
    try:
        py_compile.compile(PY, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN, rebuild the frontend, then check:")
    print("   python scripts\\diag_committee_sidebar.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
