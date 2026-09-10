#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Put "Seek input" on the credit risk workbench.

SI1 added the endpoints. Nothing calls them, so the only way to involve a
committee member is still to return the case - which marks it 'returned' and
says on the file that the work was deficient.

Adds a fifth action beside approve, escalate, decline and return: ask a named
person on the case for their input. The case does not move.

    python scripts/patch_si2_seek_input_on_the_workbench.py            # dry run
    python scripts/patch_si2_seek_input_on_the_workbench.py --apply

Needs CreditRiskWorkbench.tsx in frontend/web/src/pages/.
"""
import os
import shutil
import sys

PAGE = os.path.join("frontend", "web", "src", "pages", "CreditRiskWorkbench.tsx")
API = os.path.join("frontend", "web", "src", "lib", "api.ts")

API_FN = '''
/** Ask a named person on the case for their input. The case does not move and
 *  is not marked returned - a question is not a rejection. */
export async function seekInput(
  appId: string,
  body: { to: string; to_name?: string; question: string },
): Promise<{ application_id: string; asked: string }> {
  return postJson<{ application_id: string; asked: string }, typeof body>(
    `/lms/applications/${encodeURIComponent(appId)}/seek-input`, body);
}
'''

OLD_MODE = "type Mode = 'approve' | 'escalate' | 'decline' | 'return';"
NEW_MODE = "type Mode = 'approve' | 'escalate' | 'decline' | 'return' | 'input';"

OLD_TABS = """                      {([['approve', 'Approve'],
                         ['escalate', 'Approve — send up to the Chief'],
                         ['decline', 'Decline'],
                         ['return', 'Return for rework']] as [Mode, string][])"""
NEW_TABS = """                      {([['approve', 'Approve'],
                         ['escalate', 'Approve — send up to the Chief'],
                         ['decline', 'Decline'],
                         ['return', 'Return for rework'],
                         // A question is not a rejection. The case stays here.
                         ['input', 'Seek input']] as [Mode, string][])"""

OLD_ACT = """      } else if (mode === 'return') {"""
NEW_ACT = """      } else if (mode === 'input') {
        const to = peopleOn(a).find((p) => p.code === returnTo);
        await seekInput(id, {
          to: returnTo,
          to_name: to?.label.split(' — ')[0],
          question: reason.trim(),
        });
      } else if (mode === 'return') {"""

OLD_PICK = "                    {mode === 'return' && ("
NEW_PICK = "                    {(mode === 'return' || mode === 'input') && ("

OLD_READY = """  const canRecord = reason.trim().length >= 5
    && (mode !== 'return' || returnTo !== '');"""
NEW_READY = """  const canRecord = reason.trim().length >= 5
    && (mode !== 'return' || returnTo !== '')
    // A request for input needs somebody to ask and something to ask them.
    && (mode !== 'input' || (returnTo !== '' && reason.trim().length >= 10));"""


def main():
    apply = "--apply" in sys.argv
    for f in (PAGE, API):
        if not os.path.isfile(f):
            print("%s not found." % f)
            return 1

    p = open(PAGE, encoding="utf-8").read()
    a = open(API, encoding="utf-8").read()
    if "seekInput" in p:
        print("Already applied.")
        return 1
    for label, old, src in (("the Mode type", OLD_MODE, p),
                            ("the action tabs", OLD_TABS, p),
                            ("the act branch", OLD_ACT, p),
                            ("the picker", OLD_PICK, p),
                            ("the ready check", OLD_READY, p)):
        if src.count(old) != 1:
            print("%s matched %d times." % (label, src.count(old)))
            return 1

    if "seekInput" not in a:
        a = a.rstrip() + "\n" + API_FN
    p = p.replace(OLD_MODE, NEW_MODE, 1)
    p = p.replace(OLD_TABS, NEW_TABS, 1)
    p = p.replace(OLD_ACT, NEW_ACT, 1)
    p = p.replace(OLD_PICK, NEW_PICK, 1)
    p = p.replace(OLD_READY, NEW_READY, 1)
    p = p.replace("  returnCaseForRework, escalateToChief, claimCase,",
                  "  returnCaseForRework, escalateToChief, claimCase, seekInput,", 1)

    if "seekInput," not in p.split("} from '@/lib/api'")[0]:
        print("seekInput is used but not imported.")
        return 1
    if "mode !== 'input'" not in p:
        print("A request with nobody named would be sent.")
        return 1
    if p.count("{") != p.count("}") or p.count("(") != p.count(")"):
        print("Braces unbalanced.")
        return 1
    print("Seek input added beside the four decisions.")
    print("It reuses the picker, so only people on the case can be asked.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    for path, src in ((API, a), (PAGE, p)):
        shutil.copy2(path, path + ".pre_si2")
        open(path, "w", encoding="utf-8", newline="").write(src)
        print("Applied %s" % path)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
