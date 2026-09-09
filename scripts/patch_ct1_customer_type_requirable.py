#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Let the admin make Customer type compulsory.

Business line - Consumer, Commercial, CIB - is read from client_type first.
A deal without it falls to Unclassified, and the roll-up understates whichever
line the deal belonged to.

Segment already has a toggle. Customer type never did, so the one field the
business-line roll-up depends on could not be made compulsory from the screen
built for exactly that.

    python scripts/patch_ct1_customer_type_requirable.py            # dry run
    python scripts/patch_ct1_customer_type_requirable.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("frontend", "web", "src", "pages", "AdminConfig.tsx")

OLD = "  { key: 'segment', label: 'Segment' },"
NEW = ("  { key: 'segment', label: 'Segment' },\n"
       "  // Business line (Consumer / Commercial / CIB) is read from this\n"
       "  // first. Without it a deal falls to Unclassified and the roll-up\n"
       "  // understates whichever line it belonged to.\n"
       "  { key: 'client_type', label: 'Customer type (Consumer / Commercial / CIB)' },")


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "'client_type', label:" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The segment entry matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    # The form has to honour it, not just offer the toggle - that was the BF1
    # mistake: required in validation, never rendered.
    form = os.path.join("frontend", "web", "src", "pages", "PipelineCreate.tsx")
    if os.path.isfile(form):
        f = open(form, encoding="utf-8").read()
        if "reqStar('client_type')" not in f:
            print("The create form does not mark Customer type as required.")
            print("It reads requiredFields, so the toggle will work, but the")
            print("field will not show a star. Worth checking after applying.")
        if 'data-field="clientType"' not in f and "client_type" not in f:
            print("The create form has no Customer type field at all - the")
            print("toggle would ask for something nobody can fill in.")
            return 1
    print("Customer type can now be made compulsory from Administration.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("\nApplying only adds the toggle. Turn it on in Administration,")
        print("or nothing changes for anybody.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_ct1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    print("Next: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
