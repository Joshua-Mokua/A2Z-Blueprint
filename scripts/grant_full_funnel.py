#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Let named people see the whole bank pipeline. DRY RUN by default.

RULING (2026-08-17): "I also want to give the credit risk team the rights to
view the entire bank pipeline."

THE MECHANISM ALREADY EXISTS and nothing needed building. A committee member
carrying `full_funnel: true` sees the whole roster - the same breadth as the
MD - through _is_exco_full_funnel_member in api_pipeline_scope. It was built
for EXCO planning and is exactly the right shape for this.

So this only sets a flag on people who are already on a committee. It does not
invent a new permission, and it will not grant anybody who is not already
seated somewhere - if you want to elevate somebody who sits on no committee,
name them to one first.

TWO KINDS OF SIGHT, and they are different:

    full_funnel      the whole bank's PIPELINE - every deal, every branch
    pool visibility  the whole CREDIT pool - cases in credit, by role

The credit-risk function needs both. This is the first; Administration >
Credit Pool Access is the second.

    python scripts\\grant_full_funnel.py
    python scripts\\grant_full_funnel.py --who Korir,Okumu
    python scripts\\grant_full_funnel.py --who Korir,Okumu --apply
    python scripts\\grant_full_funnel.py --revoke Korir --apply
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
    who, revoke = [], []
    for flag, dest in (("--who", who), ("--revoke", revoke)):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                dest.extend(n.strip() for n in sys.argv[i + 1].split(",") if n.strip())

    if not os.path.isfile(CFG):
        print("ABORT: %s not found." % CFG)
        return 1
    cfg = json.load(open(CFG, encoding="utf-8"))
    cw = cfg.get("credit_workflow") or {}
    pal = cw.get("committee_palette") or []

    seated = []
    for c in pal:
        for m in (c.get("members") or []):
            if not isinstance(m, dict):
                continue
            code = str(m.get("staff_code", "") or "").strip()
            name = str(m.get("name", "") or "").strip()
            if code or name:
                seated.append((c, m, code, name))

    print("=" * 76)
    print("WHO CAN SEE THE WHOLE BANK PIPELINE")
    print("=" * 76)
    have = [(c, m, code, name) for c, m, code, name in seated if m.get("full_funnel")]
    print("  granted now (%d):" % len(have))
    for c, _m, code, name in have:
        print("     %-10s %-30s  (%s)" % (code, name[:30], c.get("code")))
    if not have:
        print("     (nobody)")

    if not who and not revoke:
        print("\n  Name people with --who, using a distinctive part of the name:")
        print("     python scripts\\grant_full_funnel.py --who Korir,Okumu")
        print("\n  People currently on a committee, who may be granted:")
        for _c, _m, code, name in seated[:30]:
            print("     %-10s %s" % (code, name[:40]))
        return 0

    def find(term):
        t = term.lower()
        hits = [(c, m, code, name) for c, m, code, name in seated
                if t in name.lower() or t == code.lower()]
        # One person may sit on several committees; that is one person.
        uniq = {}
        for c, m, code, name in hits:
            uniq.setdefault(code or name, []).append((c, m, code, name))
        return uniq

    changes = []
    for term in who + revoke:
        uniq = find(term)
        if not uniq:
            print("\n  ABORT: nobody on any committee matches %r." % term)
            print("         They must sit on a committee before they can be")
            print("         elevated. Name them to one first.")
            return 1
        if len(uniq) > 1:
            print("\n  ABORT: %r matches %d people:" % (term, len(uniq)))
            for k, v in list(uniq.items())[:6]:
                print("     %-10s %s" % (k, v[0][3]))
            print("         Give a more distinctive part of the name.")
            return 1
        rows = list(uniq.values())[0]
        changes.append((term in revoke, rows))

    print("")
    for is_revoke, rows in changes:
        _c, _m, code, name = rows[0]
        print("  %-8s %-10s %-30s  (on %d committee(s))"
              % ("REVOKE" if is_revoke else "GRANT", code, name[:30], len(rows)))

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for is_revoke, rows in changes:
        for _c, m, _code, _name in rows:
            m["full_funnel"] = not is_revoke

    cw["committee_palette"] = pal
    cfg["credit_workflow"] = cw
    bak = CFG + ".pre_funnel_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("\nwritten.  (backup: %s)" % os.path.basename(bak))
    print("The config is read per request - no restart needed.")
    print("\nThey see every deal in the bank now. Check with:")
    print("   python scripts\\grant_full_funnel.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
