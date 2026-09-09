#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""A reworked case goes back to the analyst who returned it.

The server already does this: resubmit-after-rework sends the case to
returned_by_code, and both return paths record it. Nothing in the app ever
calls that endpoint.

So when an analyst returns a case, the owner attaches the documents, presses
the same Submit button, and it goes in as a FRESH submission into the pool -
where anybody may claim it and the analyst who asked for the documents has to
find it again.

When the deal is back with the owner for rework, the panel now calls
resubmit-after-rework instead.

    python scripts/patch_rw1_rework_returns_to_the_analyst.py            # dry run
    python scripts/patch_rw1_rework_returns_to_the_analyst.py --apply

LOCAL FIX (not in the original): the import-anchor regex
`^import \\{ ([A-Za-z]+),` matches the FIRST `import {` line in the whole
file, which is the React import (`import { useCallback, ...`), not the
api.ts import list further down - inserting resubmitAfterRework there would
import it from 'react' and fail the build. Matched the bare
`openProtectedFile,` token (the api.ts list's current first entry) instead,
the same fix already needed for AM2.
"""
import os
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "pages", "PipelineDealDetail.tsx")

OLD = """      const res = await submitDealToCredit(deal.id, checklist.required.filter((d) => docFiles[d]));
      toast({
        tone: 'success',
        message: `✓ Submitted to credit — application ${res.application_id}.`,
      });"""

NEW = """      // Back with the owner for rework? Then this is a RESUBMISSION, and it
      // belongs to the analyst who returned it - they asked for the documents
      // and they have the context. submitDealToCredit would put it in the pool
      // as a fresh case for anybody to claim.
      const appId = String((deal as { lms_application_id?: string })
        .lms_application_id ?? '');
      if (reopenedForDocs && appId) {
        await resubmitAfterRework(appId, {});
        toast({
          tone: 'success',
          message: '✓ Sent back to the analyst who asked for the documents.',
        });
      } else {
        const res = await submitDealToCredit(deal.id, checklist.required.filter((d) => docFiles[d]));
        toast({
          tone: 'success',
          message: `✓ Submitted to credit — application ${res.application_id}.`,
        });
      }"""


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "resubmitAfterRework" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The submit call matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    # Import it. Match the bare token the api.ts list currently opens with,
    # not the first `import {` line in the file - that one is React's.
    if s.count("openProtectedFile,") < 1:
        print("Could not find the api import list.")
        return 1
    s = s.replace("openProtectedFile,", "resubmitAfterRework,\n  openProtectedFile,", 1)

    if "reopenedForDocs && appId" not in s:
        print("The rework path is not gated on the deal being back for rework.")
        return 1
    if "submitDealToCredit" not in s:
        print("A first submission would no longer work.")
        return 1
    head = s.split("function ")[0]
    if "resubmitAfterRework" not in head:
        print("resubmitAfterRework is used but never imported.")
        return 1
    if s.count("{") != s.count("}") or s.count("(") != s.count(")"):
        print("The page no longer balances.")
        return 1
    print("A reworked case resubmits to the analyst who returned it.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("Run tsc afterwards.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_rw1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
