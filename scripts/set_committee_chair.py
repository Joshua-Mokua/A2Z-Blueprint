#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Set who chairs a committee, and who may stand in. DRY RUN by default.

RULING (2026-08-18): "the vote of Tom is significant when the MD is away. For
as long as the MD is there, and at least a rep from credit - who would be Korir
in case Thomas is absent - it should be okay."

So on the Business Credit Committee the MD chairs, and the mandatory vote is
hers. Thomas stands in when she is away; Korir stands in when Thomas is too.
That is a chair and two deputies, in that order of precedence.

WHY THIS MATTERS MORE THAN IT LOOKS: the chair's vote is MANDATORY. Naming the
wrong person as chair does not merely mislabel a row - it decides whose absence
can stop the committee. Eldoret sat twice and finished nothing over exactly
this.

The chair and every deputy are seated on the roster automatically, because a
chair who cannot vote is not a chair.

    python scripts\\set_committee_chair.py --committee B4 --chair Rabecca \\
        --deputies "Thomas Okumu",Justus
    python scripts\\set_committee_chair.py --committee B4 --chair Rabecca \\
        --deputies "Thomas Okumu",Justus --apply
"""
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

CFG = os.path.join("data", "lms_config.json")


def main():
    apply = "--apply" in sys.argv
    code = chair = ""
    deputies = []
    for flag in ("--committee", "--chair", "--deputies"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                v = sys.argv[i + 1].strip()
                if flag == "--committee":
                    code = v.upper()
                elif flag == "--chair":
                    chair = v
                else:
                    deputies = [x.strip() for x in v.split(",") if x.strip()]
    if not code or not chair:
        print("ABORT: --committee and --chair are required.")
        return 1

    cfg = json.load(open(CFG, encoding="utf-8"))
    cw = cfg.get("credit_workflow") or {}
    pal = cw.get("committee_palette") or []
    c = next((x for x in pal if str(x.get("code")) == code), None)
    if not c:
        print("ABORT: no committee %r." % code)
        return 1

    members = [m for m in (c.get("members") or []) if isinstance(m, dict)]

    def find(term):
        t = term.strip().lower()
        hits = [m for m in members
                if t in str(m.get("name", "")).lower()
                or t == str(m.get("staff_code", "")).strip().lower()]
        if len(hits) == 1:
            return hits[0], None
        if not hits:
            return None, ("%r is not on this committee. Name them to it first "
                          "with name_dcc_members.py." % term)
        return None, ("%r matches %d members: %s" % (
            term, len(hits), "; ".join(str(h.get("name")) for h in hits[:4])))

    cm, err = find(chair)
    if err:
        print("ABORT: --chair: %s" % err)
        return 1
    deps = []
    for d in deputies:
        dm, err = find(d)
        if err:
            print("ABORT: --deputies: %s" % err)
            return 1
        if dm is cm:
            print("ABORT: %r is the chair; they cannot deputise for themselves."
                  % d)
            return 1
        deps.append(dm)

    print("=" * 76)
    print("%s  —  %s" % (code, c.get("name")))
    print("=" * 76)
    print("  chair now      %s" % (c.get("chaired_by") or "nobody"))
    print("  chair will be  %s (%s)" % (cm.get("name"), cm.get("staff_code")))
    was = [str(m.get("name")) for m in members if m.get("deputy_chair")]
    print("  deputies now   %s" % (", ".join(was) or "none"))
    print("  will be        %s" % (", ".join(str(d.get("name")) for d in deps) or "none"))
    print("")
    print("  The chair's vote is MANDATORY. A deputy's stands in for it when")
    print("  the chair is away - so this decides whose absence can stop the")
    print("  committee, which is not a labelling question.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    c["chaired_by"] = str(cm.get("name"))
    if cm.get("staff_code"):
        c["chair_staff_code"] = str(cm.get("staff_code"))
    for m in members:
        m.pop("deputy_chair", None)
    for d in deps:
        d["deputy_chair"] = True

    cw["committee_palette"] = pal
    cfg["credit_workflow"] = cw
    bak = CFG + ".pre_chair_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nwritten.  (backup: %s)" % os.path.basename(bak))
    print("\nCheck it:  python scripts\\rehearse_bcc.py --committee %s" % code)
    return 0


if __name__ == "__main__":
    sys.exit(main())
