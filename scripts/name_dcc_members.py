#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Name real people to a department credit committee. DRY RUN by default.

B1, B2 and B3 were created with a chair and FOUR BLANK member rows - placeholders
that look configured, so the voting panel showed "0/4 voted" above four nameless
lines and nobody went looking for the cause.

This resolves the names you give against the STAFF REGISTER, so each member
carries a real staff code. That matters twice over: the vote endpoint refuses
anybody not on the roster by code, and the panel keys its dropdown on it.

It writes BOTH places - the palette (what Admin edits, and what the pipeline
gate reads) and credit_workflow.dcc (what the LMS voting panel reads) - because
writing one and not the other is how the roster and the panel came to disagree.

    python scripts\\name_dcc_members.py --committee B1 \\
        --members Lunar,Annet,Fiona,Maingi --deputies Annet,Fiona
    python scripts\\name_dcc_members.py --committee B1 --members Lunar,Annet,Fiona,Robert --apply

A name may be a first name, a surname, or any distinctive part. If it matches
more than one person the script stops and lists them rather than guessing -
naming the wrong person to a credit committee is not a small error.
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
    code = ""
    names = []
    if "--committee" in sys.argv:
        i = sys.argv.index("--committee")
        if i + 1 < len(sys.argv):
            code = sys.argv[i + 1].strip()
    if "--members" in sys.argv:
        i = sys.argv.index("--members")
        if i + 1 < len(sys.argv):
            names = [n.strip() for n in sys.argv[i + 1].split(",") if n.strip()]
    if not code or not names:
        print("ABORT: --committee <code> and --members <a,b,c> are both required.")
        return 1

    try:
        from utils.api_pipeline_scope import get_staff_roster
        df = get_staff_roster()
    except Exception as exc:
        print("ABORT: staff register unreadable: %s" % exc)
        return 1

    people = []
    for _i, r in df.iterrows():
        people.append({
            "staff_code": str(r.get("Staff Code") or "").strip(),
            "name": str(r.get("Staff Name") or "").strip(),
            "role": str(r.get("Role") or "").strip(),
            "unit": str(r.get("Unit") or "").strip(),
        })

    cfg = json.load(open(CFG, encoding="utf-8"))
    cw = cfg.get("credit_workflow") or {}
    pal = cw.get("committee_palette") or []
    target = next((c for c in pal if str(c.get("code")) == code), None)
    if not target:
        print("ABORT: no committee %r." % code)
        print("       Available: %s" % ", ".join(str(c.get("code")) for c in pal))
        return 1

    print("=" * 78)
    print("NAMING MEMBERS TO %s — %s" % (code, target.get("name")))
    print("=" * 78)
    if target.get("chaired_by"):
        print("  chair: %s" % target.get("chaired_by"))

    resolved, failed = [], []
    for want in names:
        w = want.lower()
        hits = [p for p in people if p["name"] and w in p["name"].lower()]
        if len(hits) == 1:
            resolved.append(hits[0])
        elif not hits:
            failed.append((want, "nobody in the register matches"))
        else:
            failed.append((want, "%d people match: %s"
                           % (len(hits), "; ".join(h["name"] for h in hits[:5]))))

    print("\n  RESOLVED (%d):" % len(resolved))
    for p in resolved:
        print("     %-10s %-30s %s" % (p["staff_code"], p["name"][:30], p["role"][:30]))
    if failed:
        print("\n  NOT RESOLVED (%d):" % len(failed))
        for want, why in failed:
            print("     %-14s %s" % (want, why))
        print("")
        print("  NOTHING IS WRITTEN while a name is ambiguous or missing.")
        print("  Naming the wrong person to a credit committee is not a small")
        print("  error - give a more distinctive part of the name and re-run.")
        return 1

    # The chair sits on the committee too, and votes: CH1 makes their vote
    # mandatory, so a chair who is not a member could never satisfy it.
    chair = str(target.get("chaired_by", "") or "").strip()
    if chair and not any(p["name"].lower() == chair.lower() for p in resolved):
        ch = [p for p in people if p["name"].lower() == chair.lower()]
        if ch:
            resolved.insert(0, ch[0])
            print("\n  (the chair %s is added as a member - their vote is" % chair)
            print("   mandatory, so they must be on the roster to cast it)")
        else:
            print("\n  warn: the chair %r is not in the register, so their" % chair)
            print("        mandatory vote cannot be matched by staff code.")

    members = [{
        "id": p["staff_code"],
        "member_id": p["staff_code"],
        "staff_code": p["staff_code"],
        "name": p["name"],
        "role": p["role"],
    } for p in resolved]

    print("\n  WILL WRITE %d member(s) to the palette AND the LMS roster."
          % len(members))
    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    target["members"] = members
    dcc = dict(cw.get("dcc") or {})
    if str(dcc.get("source_committee", "")) == code or not dcc.get("members"):
        dcc.update({
            "enabled": True,
            "name": target.get("name") or "Department Credit Committee",
            "members": members,
            "chaired_by": target.get("chaired_by", ""),
            "voting_rule": target.get("voting_rule", "SIMPLE_MAJORITY"),
            "source_committee": code,
        })
        cw["dcc"] = dcc
        print("  the LMS roster now reads from %s" % code)
    else:
        print("  the LMS roster is copied from %s, so it is left alone."
              % dcc.get("source_committee"))
        print("  Point it here with: python scripts\\enable_dcc.py --apply --from %s" % code)

    cw["committee_palette"] = pal
    cfg["credit_workflow"] = cw
    bak = CFG + ".pre_names_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nwritten.  (backup: %s)" % os.path.basename(bak))
    print("RESTART UVICORN, then check with:")
    print("   python scripts\\diag_dcc_members.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
