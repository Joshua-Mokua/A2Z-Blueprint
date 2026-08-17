#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Seed readable department names for the nine units derivation gets wrong.

unit_label() strips title prefixes and suffixes, which handles most cases:

    Director, Internal Audit        -> Internal Audit
    Director Operations & Technology -> Operations & Technology
    Head of Consumer                -> Consumer

But stripping alone is not enough, and pretending otherwise would ship wrong
department names to the bank:

    Business Manager                -> "Business"          not a department
    Country Risk Manager, Kenya & EAC -> "Risk Manager..."  suffix missed
    Personal Assistant              -> unchanged            not a unit at all
    Ag. Head HR & Senior HR Business Partner -> keeps the tail

These are JUDGEMENTS, which is exactly why they live in org_config rather than
in code - the bank should correct any of them without a deploy.

    python scripts\\seed_unit_labels.py            # show them
    python scripts\\seed_unit_labels.py --apply
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.getcwd())

OVERRIDES = {
    "Ag. Head Human Resources & Senior HR Business Partner": "Human Resources",
    "Country Risk Manager, Kenya & EAC": "Risk Management",
    "Business Manager": "Business Management",
    "Personal Assistant": "Office of the MD",
    "Director Compliance- CESA 1": "Compliance",
    "Director, Credit Risk Management- Kenya & EAC": "Credit Risk Management",
    "Director, Corporate Banking Kenya & EAC": "Corporate Banking",
    "Director, Treasury & FICC, EAC": "Treasury & FICC",
    "Director Consumer & Commercial Banking (CCB)": "Consumer & Commercial Banking",
}


def main():
    apply = "--apply" in sys.argv
    try:
        from utils.org_validator import md_reporting_roles, unit_label
    except Exception as exc:
        print("ABORT: %s  (apply patch_ul1_unit_labels.py first)" % exc)
        return 1

    units = sorted(md_reporting_roles() or [])
    if not units:
        print("ABORT: no MD-reporting units found in org_config.")
        return 1

    unknown = [u for u in OVERRIDES if u not in units]
    if unknown:
        print("ABORT: these overrides name units that do not exist:")
        for u in unknown:
            print("   %s" % u)
        print("An override for a unit nobody has would sit in config forever,")
        print("looking configured and doing nothing.")
        return 1

    print("=" * 78)
    print("%-50s %s" % ("KEY (unchanged)", "LABEL"))
    print("=" * 78)
    for u in units:
        lab = OVERRIDES.get(u) or unit_label(u)
        mark = "  <- override" if u in OVERRIDES else ""
        print("%-50s %s%s" % (u[:50], lab, mark))

    print("")
    print("%d units · %d explicit overrides · %d derived"
          % (len(units), len(OVERRIDES), len(units) - len(OVERRIDES)))
    print("The key stays the role title, so no saved config has to migrate.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    path = os.path.join("data", "org_config.json")
    if not os.path.isfile(path):
        print("ABORT: %s not found." % path)
        return 1
    shutil.copy2(path, path + ".pre_unitlabels")
    cfg = json.load(open(path, encoding="utf-8"))
    existing = cfg.get("unit_display_names") or {}
    existing.update(OVERRIDES)
    cfg["unit_display_names"] = existing
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.replace(tmp, path)
    print("\nwrote %d display names to %s" % (len(existing), path))
    print("Restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
