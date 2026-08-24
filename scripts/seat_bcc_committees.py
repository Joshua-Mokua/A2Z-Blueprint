#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Seat the Consumer and Commercial credit committees. DRY RUN by default.

RULING (2026-08-22): the official membership is

    B1  Consumer Banking Credit Committee
        Jane Jelagat        CHAIR
        Robert Githaiga
        Lunar
        Esther Mbano

    B2  Commercial Banking Credit Committee
        Victor              CHAIR
        Upendo
        Kagio
        Joshua Muthama

BOTH COMMITTEES HAVE FOUR EMPTY SEATS TODAY. The names are in `chaired_by` as
plain strings with nobody behind them, which is why seat_the_chairs.py could
never match B1 - there was no member record to match against.

    python scripts\seat_bcc_committees.py
    python scripts\seat_bcc_committees.py --apply

IT RESOLVES NAMES AGAINST THE STAFF REGISTER, and reports anybody it cannot
find rather than seating a blank. A committee member who is not a real staff
code cannot vote, cannot be shown a case, and cannot be held to a decision -
so a name that does not resolve is a failure, not a warning.

PARTIAL NAMES ARE ACCEPTED - "Victor", "Kagio", "Lunar" - but only when they
match exactly ONE person. Two Victors is a question for a human, not a guess
by a script.

STAFF CODES ARE MATCHED ON THEIR DIGITS. KE0539 and KE539 are the same person;
the padding was introduced for DSA codes and was never meant to split anybody
in two.
"""
import json
import os
import re
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

CFG = os.path.join("data", "lms_config.json")

SEATS = {
    "B1": ("Jane Jelagat", ["Robert Githaiga", "Lunar", "Esther Mbano"]),
    # "Victor" alone matches THREE people in the register - Victor kibiwot
    # Kibet (CN207), Victor Njagi Ndambiri (KE1194) and Victor Mutabari Mbaabu
    # (KE959). The config already records the last of those as B2's chair, so
    # that is the bank's own answer and the code is used rather than the name.
    #
    # A committee seat is not a place to resolve an ambiguity by guessing which
    # of three people was meant.
    "B2": ("KE959", ["Upendo", "Kagio", "Joshua Muthama"]),
}


def _digits(v):
    m = re.match(r"^([A-Za-z]*)0*(\d+)$", str(v or "").strip())
    return ("%s%s" % (m.group(1).upper(), m.group(2))) if m else ""


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(CFG):
        print("ABORT: %s not found - run from the project root." % CFG)
        return 1

    try:
        from utils.api_pipeline_scope import get_staff_roster
        roster = get_staff_roster()
    except Exception as exc:
        print("ABORT: cannot read the staff register: %s" % str(exc)[:60])
        return 1

    people = []
    for _i, r in roster.iterrows():
        people.append({
            "name": str(r.get("Staff Name") or "").strip(),
            "staff_code": str(r.get("Staff Code") or "").strip(),
            "role": str(r.get("Role") or r.get("Designation") or "").strip(),
            "unit": str(r.get("Unit") or r.get("Department") or "").strip(),
        })

    def find(term):
        """Exactly one person, or a reason why not."""
        t = str(term or "").strip().lower()
        if not t:
            return None, "an empty name"
        # A staff code, however it is padded.
        d = _digits(term)
        if d:
            hits = [p for p in people if _digits(p["staff_code"]) == d]
            if len(hits) == 1:
                return hits[0], None
        hits = [p for p in people if t in p["name"].lower()]
        if len(hits) == 1:
            return hits[0], None
        if not hits:
            # Try each word, for "Jane Jelagat" against "Jane Jelagat Atugah".
            words = [w for w in t.split() if len(w) > 2]
            if words:
                hits = [p for p in people
                        if all(w in p["name"].lower() for w in words)]
                if len(hits) == 1:
                    return hits[0], None
        if not hits:
            return None, "nobody in the register matches %r" % term
        return None, ("%r matches %d people: %s" % (
            term, len(hits), "; ".join("%s (%s)" % (h["name"], h["staff_code"])
                                       for h in hits[:4])))

    cfg = json.load(open(CFG, encoding="utf-8"))
    pal = (cfg.get("credit_workflow") or {}).get("committee_palette") or []

    print("=" * 80)
    print("SEATING THE CONSUMER AND COMMERCIAL CREDIT COMMITTEES")
    print("=" * 80)
    print("  staff in the register  %d\n" % len(people))

    planned, problems = {}, []
    for code, (chair, others) in SEATS.items():
        c = next((x for x in pal if str(x.get("code")) == code), None)
        if not c:
            problems.append("there is no committee %s in the palette" % code)
            continue
        print("  %s  %s" % (code, c.get("name")))
        seats = []
        for term, is_chair in [(chair, True)] + [(o, False) for o in others]:
            p, err = find(term)
            if err:
                print("     %-18s *** %s" % (term, err[:52]))
                problems.append("%s: %s" % (code, err))
                continue
            seats.append((p, is_chair))
            print("     %-18s -> %-28s %-9s %s"
                  % (term, p["name"][:28], p["staff_code"],
                     "CHAIR" if is_chair else ""))
        planned[code] = seats
        print("")

    if problems:
        print("=" * 80)
        print("NOT SEATING ANYBODY")
        print("=" * 80)
        for p in problems:
            print("  * %s" % p)
        print("\n  A member who is not a real staff code cannot vote, cannot be")
        print("  shown a case, and cannot be held to a decision. Give me the")
        print("  full name or the staff code for each of the above and I will")
        print("  seat the lot in one pass.")
        return 1

    if not apply:
        print("DRY RUN - nothing written. Re-run with --apply.")
        return 0

    bak = CFG + ".pre_seatbcc_%s" % datetime.now().strftime("%H%M%S")
    shutil.copy2(CFG, bak)

    for code, seats in planned.items():
        c = next(x for x in pal if str(x.get("code")) == code)
        members = []
        for p, _is_chair in seats:
            members.append({
                "name": p["name"],
                "role": p["role"] or p["unit"],
                "staff_code": p["staff_code"],
                # full_funnel is NOT set here. It grants sight of the whole
                # bank's pipeline and is a separate decision from sitting on a
                # committee - grant_full_funnel.py exists for it.
                "full_funnel": False,
            })
        c["members"] = members
        c["chaired_by"] = next(p["name"] for p, ch in seats if ch)

    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2)
    print("seated %d committee(s).  (backup: %s)"
          % (len(planned), os.path.basename(bak)))
    print("\nRESTART UVICORN, then confirm each member can actually see their")
    print("cases:")
    print("   python scripts\\diag_committee_sight.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
