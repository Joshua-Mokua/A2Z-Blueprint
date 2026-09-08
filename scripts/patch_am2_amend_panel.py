#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Add an Amend value panel to the deal screen.

AM1 added the endpoint. Without a control on the screen the only way to correct
a mistyped figure is a script, which is not a way to run a bank - a value gets
keyed wrong, or a customer's ability to service turns out lower than they
hoped, and both are ordinary.

Adds a tab beside the others. The server decides who may: the owner before the
deal goes to credit, a manager after that, an admin at any point. A reason is
required and lands on the case journey.

    python scripts/patch_am2_amend_panel.py            # dry run
    python scripts/patch_am2_amend_panel.py --apply

LOCAL FIX (not in the original): the import-anchor regex assumed
fetchPipelineDealDetail was the first name after `import {`. DV3 (applied
earlier on this branch) put openProtectedFile first instead, pushing
fetchPipelineDealDetail onto the continuation line - so the original
`^import \\{ fetchPipelineDealDetail,` anchor no longer matches anywhere.
Matched on the bare `fetchPipelineDealDetail,` token instead, wherever it
falls, and inserted amendDealValue immediately before it.
"""
import os
import re
import shutil
import sys

PAGE = os.path.join("frontend", "web", "src", "pages", "PipelineDealDetail.tsx")
API = os.path.join("frontend", "web", "src", "lib", "api.ts")

API_FN = '''
/** Change a deal's value, with a reason. The server decides who may: the owner
 *  before the deal goes to credit, a manager after that, an admin at any time.
 *  The reason lands on the case journey. */
export async function amendDealValue(
  dealId: string, value: number, reason: string,
): Promise<{ deal_id: string; was?: number; value: number; changed: boolean }> {
  return postJson<{ deal_id: string; was?: number; value: number; changed: boolean },
                  { value: number; reason: string }>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/amend-value`,
    { value, reason });
}
'''

PANEL = '''
// ── AMEND VALUE ──────────────────────────────────────────────────────────────
// A value gets keyed wrong, or the customer's ability to service turns out
// lower than they hoped. Both are ordinary and neither should need a script.
function AmendValuePanel({ deal, onChanged }: { deal: PipelineDeal; onChanged: () => void }) {
  const [value, setValue] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const current = Number(deal.amount_kes ?? deal.deal_value ?? 0);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await amendDealValue(String(deal.id), Number(value), reason.trim());
      setValue('');
      setReason('');
      onChanged();
    } catch (e) {
      // The server refuses with a reason - show it rather than a generic
      // failure, because "a manager has to make this change" is actionable.
      setError(e instanceof Error ? e.message : 'Could not amend the value.');
    } finally {
      setBusy(false);
    }
  }

  const ready = Number(value) > 0 && reason.trim().length >= 5 && !busy;
  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">
        Current value <span className="font-semibold">
          KES {current.toLocaleString()}</span>. A change is recorded on the
        case journey with your name and the reason.
      </p>
      {error && (
        <div className="rounded-lg bg-red-50 border border-red-300 p-3 text-sm text-red-800">
          {error}
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            New value (KES)
          </label>
          <input className="w-full rounded-lg border border-gray-300 px-3 py-2"
                 value={value} inputMode="numeric"
                 onChange={(e) => setValue(e.target.value.replace(/[^0-9]/g, ''))}
                 placeholder="100000" />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Why is it changing?
          </label>
          <input className="w-full rounded-lg border border-gray-300 px-3 py-2"
                 value={reason}
                 onChange={(e) => setReason(e.target.value)}
                 placeholder="Keyed 1B instead of 100K" />
        </div>
      </div>
      <div className="flex justify-end">
        <button type="button" disabled={!ready} onClick={() => void save()}
                className={`rounded-lg px-4 py-2 font-medium text-white
                  ${ready ? 'bg-brand-primary' : 'bg-gray-300'}`}>
          {busy ? 'Saving…' : 'Amend value'}
        </button>
      </div>
    </div>
  );
}
'''


def main():
    apply = "--apply" in sys.argv
    for f in (PAGE, API):
        if not os.path.isfile(f):
            print("%s not found." % f)
            return 1

    p = open(PAGE, encoding="utf-8").read()
    a = open(API, encoding="utf-8").read()
    if "AmendValuePanel" in p:
        print("Already applied.")
        return 1
    if "amendDealValue" in a:
        print("The api helper is already there.")
        return 1

    # The tab list - sit beside Documentation, which is where the value is read.
    m = re.search(r"^(\s*)\{ id: 'documents',.*$", p, re.M)
    if not m:
        print("Could not find the documents tab to sit beside.")
        return 1
    indent = m.group(1)

    a = a.rstrip() + "\n" + API_FN
    p = p.replace(m.group(0), m.group(0) + "\n"
                  + "%s{ id: 'amend', label: 'Amend value', color: '#7E57C2',"
                    " content: <AmendValuePanel deal={deal}"
                    " onChanged={() => void reloadDeal()} /> }," % indent, 1)

    # The component itself, before the panel it sits next to.
    anchor = "function CreditSubmissionPanel"
    if p.count(anchor) != 1:
        print("Could not find where to put the component.")
        return 1
    p = p.replace(anchor, PANEL + "\n" + anchor, 1)

    # And the import. DV3 put openProtectedFile first in this list, pushing
    # fetchPipelineDealDetail onto the continuation line - match the bare
    # token wherever it falls rather than assuming it opens the import.
    if p.count("fetchPipelineDealDetail,") < 1:
        print("Could not find the api import list.")
        return 1
    p = p.replace("fetchPipelineDealDetail,", "amendDealValue,\n  fetchPipelineDealDetail,", 1)

    if "reason.trim().length >= 5" not in PANEL:
        print("A reason would not be required.")
        return 1
    if "setError" not in PANEL:
        print("A refusal would be silent.")
        return 1
    if p.count("{") != p.count("}") or p.count("(") != p.count(")"):
        print("The page no longer balances.")
        return 1
    print("Panel added, imported and tabbed.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("Run tsc afterwards - it will catch anything this assumed.")
        return 0

    for path, src in ((API, a), (PAGE, p)):
        shutil.copy2(path, path + ".pre_am2")
        open(path, "w", encoding="utf-8", newline="").write(src)
        print("Applied %s" % path)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
