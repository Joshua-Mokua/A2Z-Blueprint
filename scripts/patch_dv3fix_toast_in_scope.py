#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Give CommitteeDocumentStrip the toast it calls.

DV3 put a failure message in CommitteeDocumentStrip, which never called
useToast(). tsc catches it: "Cannot find name 'toast'".

Same one-line fix the pilot already carries.

    python scripts/patch_dv3fix_toast_in_scope.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "pages", "PipelineDealDetail.tsx")

OLD = "function CommitteeDocumentStrip({ dealId }: { dealId: string }) {"
NEW = ("function CommitteeDocumentStrip({ dealId }: { dealId: string }) {\n"
       "  const { toast } = useToast();")


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1
    s = open(MOD, encoding="utf-8").read()
    if s.count(OLD) != 1:
        print("The component matched %d times." % s.count(OLD))
        return 1
    i = s.index(OLD)
    if "useToast()" in s[i:i + 260]:
        print("Already applied.")
        return 1
    if "useToast" not in s.split("function ")[0]:
        print("useToast is not imported in this file.")
        return 1

    s = s.replace(OLD, NEW, 1)
    if s.count("{") != s.count("}") or s.count("(") != s.count(")"):
        print("The page no longer balances.")
        return 1
    print("toast is in scope in CommitteeDocumentStrip.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0
    shutil.copy2(MOD, MOD + ".pre_dv3fix")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
