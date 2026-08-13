#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
BR1 (v2) - A2Z everywhere, as ANCHORED EDITS.

WHY THERE IS A v2, and it is the third time this exact trap has been sprung.
v1 shipped WHOLE FILES. One of them was PipelineCreate.tsx, captured from a
tree that has the origin/channels work - which is in NOT_FOR_RELEASE. On the
pilot's branch those imports do not exist, so the release built cleanly and
then failed to compile:

    Module '"@/lib/api"' has no exported member 'fetchOriginSources'

A whole-file patcher carries everything that was in that file, including the
parts that must not travel. v1's own guard checked markers in
PipelineManagerQueues and never looked at the other ten files.

THIS VERSION CHANGES 15 LINES AND NOTHING ELSE. Each is an exact string that
must appear exactly once; anything unexpected aborts before a byte is written.
It cannot carry code that does not belong to it, because it carries no code.

WHAT IT DOES

  Seventeen hardcoded 'EKE ' labels become 'A2Z ' - the fallback app_name in
  BrandingProvider, which the sidebar shows before branding loads, and the
  breadcrumbs on ten pages. data/org_config.json always read "A2Z Blueprint";
  these labels simply ignored it.

  The Committee tab stops rendering cancellation cards beneath it. The
  suppression list was written before that tab existed.

NOT INCLUDED, deliberately: the live committee count. It needs a fetch and a
hook, which is not an anchored edit, and this patcher's whole point is that it
only swaps strings. It ships separately.

Verified: tsc --noEmit clean.

Usage (from project root, .venv active):
    python scripts\\patch_br1_a2z_and_committee_tab.py            # dry run
    python scripts\\patch_br1_a2z_and_committee_tab.py --apply
"""
import json
import os
import shutil
import sys

BACKUP_SUFFIX = ".pre_br1"

EDITS = json.loads(r'''{
 "labels": {
  "frontend/web/src/components/AffordabilityAppraisal.tsx": [
   [
    "    const bank = branding?.app_name ?? 'EKE MIS 360';",
    "    const bank = branding?.app_name ?? 'A2Z MIS 360';"
   ]
  ],
  "frontend/web/src/pages/CommitteeConvening.tsx": [
   [
    "        breadcrumbs={[{ label: 'EKE Credit Intelligence System (CIS)' }, { label: 'Committee Convening' }]}",
    "        breadcrumbs={[{ label: 'A2Z Credit Intelligence System (CIS)' }, { label: 'Committee Convening' }]}"
   ]
  ],
  "frontend/web/src/pages/CreditAdmin.tsx": [
   [
    "        breadcrumbs={[{ label: 'EKE Credit Intelligence System (CIS)' }, { label: 'Credit Admin' }]}",
    "        breadcrumbs={[{ label: 'A2Z Credit Intelligence System (CIS)' }, { label: 'Credit Admin' }]}"
   ]
  ],
  "frontend/web/src/pages/CreditAnalytics.tsx": [
   [
    "        breadcrumbs={[{ label: 'EKE Credit Intelligence System (CIS)' }, { label: 'Credit Analytics' }]}",
    "        breadcrumbs={[{ label: 'A2Z Credit Intelligence System (CIS)' }, { label: 'Credit Analytics' }]}"
   ]
  ],
  "frontend/web/src/pages/Lms.tsx": [
   [
    "        breadcrumbs={[{ label: 'EKE Credit Intelligence System (CIS)' }, { label: 'Credit Analysis' }]}",
    "        breadcrumbs={[{ label: 'A2Z Credit Intelligence System (CIS)' }, { label: 'Credit Analysis' }]}"
   ]
  ],
  "frontend/web/src/pages/Pipeline.tsx": [
   [
    "        breadcrumbs={[{ label: 'EKE Pipeline Intelligence System (PIS)' }, { label: 'EKE Sales Pro' }]}",
    "        breadcrumbs={[{ label: 'A2Z Pipeline Intelligence System (PIS)' }, { label: 'A2Z Sales Pro' }]}"
   ],
   [
    "        title=\"EKE Sales Pro\"",
    "        title=\"A2Z Sales Pro\""
   ]
  ],
  "frontend/web/src/pages/PipelineCreate.tsx": [
   [
    "          { label: 'EKE Sales Pro', to: '/pipeline' },",
    "          { label: 'A2Z Sales Pro', to: '/pipeline' },"
   ]
  ],
  "frontend/web/src/pages/PipelineManagerQueues.tsx": [
   [
    "          breadcrumbs={[{ label: 'EKE Pipeline Intelligence System (PIS)' }, { label: 'Manager Queues' }]}",
    "          breadcrumbs={[{ label: 'A2Z Pipeline Intelligence System (PIS)' }, { label: 'Manager Queues' }]}"
   ],
   [
    "        breadcrumbs={[{ label: 'EKE Pipeline Intelligence System (PIS)' }, { label: 'Manager Queues' }]}",
    "        breadcrumbs={[{ label: 'A2Z Pipeline Intelligence System (PIS)' }, { label: 'Manager Queues' }]}"
   ]
  ],
  "frontend/web/src/pages/Referrals.tsx": [
   [
    "        title=\"EKE Sales Referral\"",
    "        title=\"A2Z Sales Referral\""
   ],
   [
    "        breadcrumbs={[{ label: 'EKE Pipeline Intelligence System (PIS)' }, { label: 'EKE Sales Referral' }]}",
    "        breadcrumbs={[{ label: 'A2Z Pipeline Intelligence System (PIS)' }, { label: 'A2Z Sales Referral' }]}"
   ]
  ],
  "frontend/web/src/pages/Troops.tsx": [
   [
    "          breadcrumbs={[{ label: 'EKE Credit Intelligence System (CIS)' }, { label: 'Trops Disbursement' }]}",
    "          breadcrumbs={[{ label: 'A2Z Credit Intelligence System (CIS)' }, { label: 'Trops Disbursement' }]}"
   ],
   [
    "        breadcrumbs={[{ label: 'EKE Credit Intelligence System (CIS)' }, { label: 'Trops Disbursement' }]}",
    "        breadcrumbs={[{ label: 'A2Z Credit Intelligence System (CIS)' }, { label: 'Trops Disbursement' }]}"
   ]
  ],
  "frontend/web/src/providers/BrandingProvider.tsx": [
   [
    "  app_name: 'EKE Blueprint',",
    "  app_name: 'A2Z Blueprint',"
   ]
  ]
 },
 "extra": {
  "frontend/web/src/pages/PipelineManagerQueues.tsx": [
   [
    "['dailylog', 'ranking', 'analytics'].includes(activeTab)",
    "['dailylog', 'ranking', 'analytics', 'committee'].includes(activeTab)",
    2
   ]
  ]
 }
}''')



def main():
    apply = "--apply" in sys.argv
    labels = EDITS.get("labels", {})
    extra = EDITS.get("extra", {})
    targets = sorted(set(list(labels) + list(extra)))

    missing = [f for f in targets if not os.path.isfile(f)]
    if missing:
        print("ABORT: not found: %s" % ", ".join(missing[:3]))
        return 1

    planned, skipped = {}, 0
    for f in targets:
        src = open(f, encoding="utf-8").read()
        out = src
        for item in labels.get(f, []) + extra.get(f, []):
            old, new = item[0], item[1]
            # An edit may DECLARE how many times it should match. The tab
            # suppression list appears twice and both need changing; a patcher
            # assuming one would silently fix half of it.
            want = item[2] if len(item) > 2 else 1
            if new in out and old not in out:
                skipped += 1
                continue
            n = out.count(old)
            if n != want:
                print("ABORT: in %s this line matched %d times, expected %d:"
                      % (os.path.basename(f), n, want))
                print("       %s" % old.strip()[:76])
                return 1
            out = out.replace(old, new)
        if out != src:
            planned[f] = out

    if not planned:
        print("ABORT: nothing to change - BR1 looks applied.")
        return 1
    print("  ok  %d file(s), %d edit(s)%s"
          % (len(planned), sum(len(labels.get(f, [])) + len(extra.get(f, []))
                               for f in planned),
             ", %d already done" % skipped if skipped else ""))

    # ANCHORED MEANS ANCHORED. A line count that moves means something other
    # than a swap happened, and this patcher has no business doing that.
    for f, out in planned.items():
        before = open(f, encoding="utf-8").read()
        if len(out.split("\n")) != len(before.split("\n")):
            print("ABORT: %s changed line count - not a pure swap."
                  % os.path.basename(f))
            return 1
        if "EKE " in out and "//" not in out.split("EKE ")[0].split("\n")[-1]:
            pass
        for op, cl in (("{", "}"), ("(", ")")):
            if out.count(op) != out.count(cl):
                print("ABORT: %s unbalanced %s%s." % (os.path.basename(f), op, cl))
                return 1
    print("  ok  post-checks: line counts unchanged, brackets balanced")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for f, out in planned.items():
        shutil.copy2(f, f + BACKUP_SUFFIX)
        open(f, "w", encoding="utf-8", newline="").write(out)
        print("APPLIED %s" % f)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
