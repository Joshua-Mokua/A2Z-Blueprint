#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Point committee routing at committees that exist. DRY RUN by default.

THE FAULT. pipeline_settings.committee_routing maps client types to committee
codes, and it names four that are not in the palette:

    Consumer    -> DCC_CONS      not in the palette
    Commercial  -> DCC_COMM      not in the palette
    CIB         -> DCC_CIB       not in the palette
    branch-only -> BCC1          not in the palette

The committees that exist for precisely those roles are B1, B2 and B3 -
Consumer, Commercial and Corporate & Investment Banking Credit Committee -
each already carrying four members. So the map and the palette were built
against different naming and never joined up.

Nothing failed loudly. _effective_committee_journey happily returns a code
nobody can resolve, and the case stops at a gate that does not exist.

WHY THE PALETTE WINS. B1/B2/B3 are what the admin page edits, what the product
journeys reference, and they have members. Renaming them to match the map would
break every existing reference to save editing three strings.

BCC1 IS DIFFERENT - IT IS A PLACEHOLDER, NOT A COMMITTEE. A product journey
naming BCC1 gets it substituted at runtime for the deal's OWN branch committee
(BCC_BRN0NN). That substitution is why a single product flow can serve sixteen
branches. But the product-flow validator checks journey codes against the
palette, so the placeholder has to exist there to be assignable - created here
as a marker, with no members, and never voted on directly.

    python scripts\\fix_committee_routing.py
    python scripts\\fix_committee_routing.py --apply
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.getcwd())

PS = os.path.join("data", "pipeline_settings.json")
LMS = os.path.join("data", "lms_config.json")

# client_type -> the committee that actually exists for it
WANT_DCC = {"Consumer": "B1", "Commercial": "B2", "CIB": "B3"}
PLACEHOLDER = "BCC1"


def main():
    apply = "--apply" in sys.argv
    for p in (PS, LMS):
        if not os.path.isfile(p):
            print("ABORT: %s not found - run from the project root." % p)
            return 1

    ps = json.load(open(PS, encoding="utf-8")) or {}
    lms = json.load(open(LMS, encoding="utf-8")) or {}
    cw = lms.get("credit_workflow") or {}
    palette = cw.get("committee_palette") or []
    codes = {str(c.get("code")): c for c in palette}

    routing = ps.get("committee_routing")
    if not isinstance(routing, dict):
        routing = {}
    cur_map = routing.get("client_type_to_dcc") or {}
    cur_branch = routing.get("branch_only_codes") or []

    print("=" * 74)
    print("COMMITTEE ROUTING")
    print("=" * 74)
    print("  palette committees   %d" % len(palette))

    changes = []
    for ct, want in WANT_DCC.items():
        have = str(cur_map.get(ct, "") or "")
        if have == want:
            print("  %-12s -> %-6s already correct" % (ct, have))
            continue
        if want not in codes:
            print("  %-12s -> %s does NOT exist in the palette either -"
                  % (ct, want))
            print("               stop and tell me what the %s committee is called"
                  % ct)
            return 1
        print("  %-12s -> %-6s  was %r%s"
              % (ct, want, have or "(unset)",
                 "  (that code is not in the palette)"
                 if have and have not in codes else ""))
        changes.append(("map", ct, want))

    # The branch placeholder.
    if PLACEHOLDER in codes:
        print("  %-12s    %-6s already in the palette" % ("placeholder", PLACEHOLDER))
    else:
        print("  %-12s    %-6s to be CREATED as a placeholder"
              % ("placeholder", PLACEHOLDER))
        changes.append(("placeholder", PLACEHOLDER, ""))
    if PLACEHOLDER not in cur_branch:
        changes.append(("branch_only", PLACEHOLDER, ""))

    print("")
    for want in sorted(set(WANT_DCC.values())):
        c = codes.get(want)
        if c:
            n = len(c.get("members") or [])
            print("  %-4s %-46s members: %d%s"
                  % (want, str(c.get("name"))[:46], n,
                     "   <-- below quorum" if n < 2 else ""))

    if not changes:
        print("\n  Nothing to change.")
        return 0

    print("\n  AFTER THIS, a product routed through %s will send:" % PLACEHOLDER)
    print("     a branch deal   -> that deal's own branch committee")
    print("     a Consumer deal -> B1, and so on by client type")
    print("")
    print("  Assign the gate in Admin > product flow > '+ Add committee gate'.")
    print("  Nothing routes anywhere until a product names it.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(PS, PS + ".pre_routing")
    for kind, a, b in changes:
        if kind == "map":
            cur_map[a] = b
        elif kind == "branch_only" and a not in cur_branch:
            cur_branch.append(a)
    routing["client_type_to_dcc"] = cur_map
    routing["branch_only_codes"] = cur_branch
    ps["committee_routing"] = routing
    tmp = PS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(ps, fh, indent=2)
    os.replace(tmp, PS)

    if any(k == "placeholder" for k, _a, _b in changes):
        shutil.copy2(LMS, LMS + ".pre_routing")
        palette.append({
            "code": PLACEHOLDER,
            "name": "Branch Credit Committee (routes to the deal's branch)",
            "chaired_by": "",
            "recording_mode": "voting",
            "voting_rule": "SIMPLE_MAJORITY",
            "amount_threshold_kes": 0.0,
            "kind": "branch_placeholder",
            # NO MEMBERS ON PURPOSE. This is never voted on directly - it is
            # substituted for the deal's own branch committee before anybody
            # sees it. Members here would be members of nothing.
            "members": [],
        })
        cw["committee_palette"] = palette
        lms["credit_workflow"] = cw
        tmp = LMS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(lms, fh, indent=2)
        os.replace(tmp, LMS)

    print("\napplied %d change(s). Restart uvicorn, then:" % len(changes))
    print("  python scripts\\audit_committee_path.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
