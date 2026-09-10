#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""The credit risk workbench shows everything at its stage, not just two slices.

My cases shows what is assigned to you. Pool shows what is assigned to nobody.
A case assigned to SOMEBODY ELSE is in neither - so eleven cases at credit
risk showed as six, and the five with an older analyst's name on them were
invisible.

Adds a third tab: All. Every case a department committee has recommended,
whoever holds it, with the holder's name against each.

    python scripts/patch_cw2_all_tab.py            # dry run
    python scripts/patch_cw2_all_tab.py --apply
"""
import os
import shutil
import sys

PAGE = os.path.join("frontend", "web", "src", "pages", "CreditRiskWorkbench.tsx")

OLD_STATE = "  const [tab, setTab] = useState<'mine' | 'pool'>('mine');"
NEW_STATE = "  const [tab, setTab] = useState<'mine' | 'pool' | 'all'>('all');"

OLD_SHOWN = "  const shown = tab === 'mine' ? mine : pool;"
NEW_SHOWN = """  // All: everything at this stage, whoever holds it. Without it a case
  // assigned to somebody else was in neither tab, and eleven read as six.
  const shown = tab === 'mine' ? mine : tab === 'pool' ? pool : ready;
  const withOthers = ready.filter(
    (a) => assigneeOf(a).code && assigneeOf(a).code !== myCode);"""

OLD_TABS = """        <button type="button" onClick={() => setTab('pool')}
                className={`rounded-lg px-4 py-2 text-sm font-medium ${
                  tab === 'pool' ? 'bg-[#0097A7] text-white' : 'border bg-white'}`}>
          Pool ({pool.length})
        </button>"""
NEW_TABS = """        <button type="button" onClick={() => setTab('pool')}
                className={`rounded-lg px-4 py-2 text-sm font-medium ${
                  tab === 'pool' ? 'bg-[#0097A7] text-white' : 'border bg-white'}`}>
          Pool ({pool.length})
        </button>
        <button type="button" onClick={() => setTab('all')}
                className={`rounded-lg px-4 py-2 text-sm font-medium ${
                  tab === 'all' ? 'bg-[#0097A7] text-white' : 'border bg-white'}`}>
          All ({ready.length})
        </button>
        {withOthers.length > 0 && (
          <span className="text-xs text-gray-500">
            {withOthers.length} held by somebody else
          </span>
        )}"""

OLD_EMPTY = """            {tab === 'mine' ? 'Nothing is assigned to you.' : 'The pool is empty.'}"""
NEW_EMPTY = """            {tab === 'mine' ? 'Nothing is assigned to you.'
              : tab === 'pool' ? 'The pool is empty.'
              : 'Nothing is at credit risk.'}"""


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(PAGE):
        print("%s not found." % PAGE)
        return 1

    p = open(PAGE, encoding="utf-8").read()
    if "tab === 'all'" in p:
        print("Already applied.")
        return 1
    for label, old in (("the tab state", OLD_STATE),
                       ("the shown list", OLD_SHOWN),
                       ("the Pool button", OLD_TABS),
                       ("the empty message", OLD_EMPTY)):
        if p.count(old) != 1:
            print("%s matched %d times." % (label, p.count(old)))
            return 1

    p = p.replace(OLD_STATE, NEW_STATE, 1)
    p = p.replace(OLD_SHOWN, NEW_SHOWN, 1)
    p = p.replace(OLD_TABS, NEW_TABS, 1)
    p = p.replace(OLD_EMPTY, NEW_EMPTY, 1)

    # The All tab must fall through to the full list.
    if "tab === 'pool' ? pool : ready" not in p:
        print("The All tab would show nothing.")
        return 1
    if "Claim" not in p:
        print("Claiming was lost.")
        return 1
    if p.count("{") != p.count("}") or p.count("(") != p.count(")"):
        print("Braces unbalanced.")
        return 1
    print("Three tabs: My cases, Pool, All. It opens on All, because the")
    print("question this screen answers is 'what is at credit risk'.")
    print("A case held by somebody else shows their name and can be claimed")
    print("only from the pool - taking it silently is how work gets lost.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(PAGE, PAGE + ".pre_cw2")
    open(PAGE, "w", encoding="utf-8", newline="").write(p)
    print("Applied %s" % PAGE)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
