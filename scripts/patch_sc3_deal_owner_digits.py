#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
SC3 - the deal owner is recognised on the deal screen too.

FROM THE BANK (2026-09-04): "the consumer credit analyst has returned a case
requesting additional documents, but the owner cannot attach them - the place
to attach is greyed out."

EVERY UPLOAD CONTROL ON THE DEAL SCREEN IS GATED ON canEdit:

    const canEditDocs = (!!viewer?.staff_code
      && String(viewer.staff_code) === String(deal.staff_code)) || _viewerIsAdmin;

An EXACT STRING COMPARISON. "KE0539" === "KE539" is false, so the owner of the
deal is not recognised as its owner and every attach button, the "other
document" box and the submit control are all withheld.

THIS IS THE THIRD PLACE. SC1 fixed the server's portfolio-owner lookup. SC2
fixed three comparisons on the create form. This one gates the documents panel,
the transaction memo, the committee card, the forwarding memo and the rate
request - so a padded code silently removes five panels' worth of controls from
the person who owns the deal.

    KE0539 vs KE539    the same person
    KE00539 vs KE539   the same person
    KE5390 vs KE539    DIFFERENT, and that survives

WHY IT KEEPS RECURRING: the padding was introduced for DSA codes and every
comparison written before that assumption still reads the strings. Each one has
to be found. This patch also leaves a helper the next comparison can use rather
than writing a fourth copy.

Usage (from project root, .venv active):
    python scripts\patch_sc3_deal_owner_digits.py            # dry run
    python scripts\patch_sc3_deal_owner_digits.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "pages", "PipelineDealDetail.tsx")

OLD = ('  const canEditDocs = (!!viewer?.staff_code '
       '&& String(viewer.staff_code) === String(deal.staff_code)) '
       '|| _viewerIsAdmin;')

NEW = '''  // ── THE OWNER IS THE OWNER, HOWEVER THEIR CODE IS PADDED ────────────────
  // This was an exact string comparison, so "KE0539" was not "KE539" and the
  // person who raised the deal was not recognised as its owner. Every upload
  // control, the transaction memo, the committee card, the forwarding memo and
  // the rate request are all gated on this one line - so a padded code
  // silently removed five panels' worth of controls from the deal's owner.
  //
  // A credit analyst returned a case asking for more documents and the owner
  // could not attach them.
  //
  // KE5390 is still NOT KE539: the digits differ, and that distinction stands.
  const sameStaffCode = (a?: string | null, b?: string | null): boolean => {
    const norm = (v?: string | null) => {
      const m = /^([A-Za-z]*)0*(\\d+)$/.exec((v ?? '').trim());
      return m ? `${m[1].toUpperCase()}${m[2]}` : '';
    };
    const x = norm(a);
    return x !== '' && x === norm(b);
  };
  const canEditDocs = sameStaffCode(viewer?.staff_code, deal.staff_code) || _viewerIsAdmin;'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "sameStaffCode" in s:
        print("ABORT: SC3 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the canEditDocs line matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  the owner is recognised however their code is padded")

    # No raw comparison of staff codes may survive on this screen.
    import re
    raw = re.findall(r"String\(viewer\.staff_code\)\s*===\s*String\(deal\.staff_code\)", s)
    if raw:
        print("ABORT: %d raw comparison(s) remain." % len(raw))
        return 1
    if "_viewerIsAdmin" not in NEW:
        print("ABORT: admin access was dropped.")
        return 1
    if "0*(\\\\d+)" not in NEW and "0*(\\d+)" not in NEW:
        print("ABORT: the pattern does not strip leading zeros.")
        return 1
    if s.count("{") != s.count("}") or s.count("(") != s.count(")"):
        print("ABORT: braces unbalanced.")
        return 1
    print("  ok  post-checks: no raw comparison, admin kept, zeros stripped")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_sc3")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
