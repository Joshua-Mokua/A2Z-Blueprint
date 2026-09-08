#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""List the deals the business-line roll-up cannot classify.

Business line - Consumer, Commercial, CIB - is read from client_type, falling
back to the owner's place in the org chart. A deal that answers neither shows
as Unclassified, and its value is missing from whichever line it belonged to.

    python scripts/list_unclassified_deals.py
    python scripts/list_unclassified_deals.py --csv unclassified.csv

Read only. Prints what each deal actually carries, so the pattern can be seen
rather than guessed at.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.getcwd())


def kes(v):
    try:
        return format(int(float(v or 0)), ",")
    except (TypeError, ValueError):
        return "0"


def main():
    out_csv = ""
    if "--csv" in sys.argv:
        i = sys.argv.index("--csv")
        if i + 1 < len(sys.argv):
            out_csv = sys.argv[i + 1]

    from utils.core import PipelineManager
    import utils.api as A

    try:
        from utils.api_pipeline_scope import get_staff_roster
        roster = get_staff_roster()
        col = "Branch" if "Branch" in roster.columns else "Unit"
        info = {}
        for _i, r in roster.iterrows():
            c = str(r.get("Staff Code") or "").strip()
            if c:
                info[c] = {"name": str(r.get("Staff Name") or "").strip(),
                           "role": str(r.get("Role") or "").strip(),
                           "unit": str(r.get(col) or "").strip()}
    except Exception:
        info = {}

    deals = PipelineManager().deals or []

    def val(d):
        try:
            return float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            return 0.0

    rows = []
    for d in deals:
        try:
            bl = A._business_line_of(d) or ""
        except Exception:
            bl = ""
        if bl:
            continue
        owner = str(d.get("staff_code", "") or "").strip()
        oi = info.get(owner, {})
        rows.append({
            "id": str(d.get("id") or ""),
            "client": str(d.get("client_name") or ""),
            "client_type": str(d.get("client_type") or ""),
            "segment": str(d.get("segment") or ""),
            "product": str(d.get("product_type") or d.get("product") or ""),
            "stage": str(d.get("stage") or ""),
            "value": val(d),
            "owner": owner,
            "owner_name": oi.get("name", ""),
            "owner_role": oi.get("role", ""),
            "owner_unit": oi.get("unit", ""),
            "created": str(d.get("created_at") or d.get("created_date") or "")[:10],
        })

    total = sum(val(d) for d in deals)
    unval = sum(r["value"] for r in rows)
    print("=" * 100)
    print("DEALS THE BUSINESS-LINE ROLL-UP CANNOT CLASSIFY")
    print("=" * 100)
    print("  deals            %d" % len(deals))
    print("  unclassified     %d" % len(rows))
    print("  their value      KES %s of KES %s\n" % (kes(unval), kes(total)))
    if not rows:
        print("  Every deal classifies.")
        return 0

    print("  WHAT THEY CARRY")
    ct = Counter(r["client_type"] or "(blank)" for r in rows)
    print("     client_type:")
    for k, n in ct.most_common():
        print("        %-28s %d" % (k[:28], n))
    sg = Counter(r["segment"] or "(blank)" for r in rows)
    print("     segment:")
    for k, n in sg.most_common(8):
        print("        %-28s %d" % (k[:28], n))
    ur = Counter(r["owner_role"] or "(not in the register)" for r in rows)
    print("     owner's role:")
    for k, n in ur.most_common(8):
        print("        %-28s %d" % (k[:28], n))
    uu = Counter(r["owner_unit"] or "(no unit)" for r in rows)
    print("     owner's unit:")
    for k, n in uu.most_common(8):
        print("        %-28s %d" % (k[:28], n))

    print("\n  EVERY ONE")
    print("  %-8s %-24s %-14s %-16s %-14s %-12s %s"
          % ("DEAL", "CLIENT", "CLIENT_TYPE", "SEGMENT", "OWNER", "VALUE", "CREATED"))
    for r in sorted(rows, key=lambda x: -x["value"]):
        print("  %-8s %-24s %-14s %-16s %-14s %-12s %s"
              % (r["id"][:8], r["client"][:24],
                 (r["client_type"] or "-")[:14], (r["segment"] or "-")[:16],
                 (r["owner_name"] or r["owner"])[:14], kes(r["value"]),
                 r["created"]))

    if out_csv:
        import csv
        with open(out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print("\n  Written to %s" % out_csv)

    print("\n" + "=" * 100)
    print("Reading this")
    print("=" * 100)
    blank = sum(1 for r in rows if not r["client_type"])
    if blank:
        print("  %d have NO client_type at all. The field was optional until"
              % blank)
        print("  CT1 added the toggle - turning it on in Administration stops")
        print("  the next one.")
    odd = Counter(r["client_type"] for r in rows if r["client_type"])
    if odd:
        print("\n  %d carry a client_type that maps to no business line:"
              % sum(odd.values()))
        for k, n in odd.most_common():
            print("        %-28s %d" % (k[:28], n))
        print("  Consumer, Commercial and CIB are the three that map. Anything")
        print("  else - Existing, Individual, Business - falls through.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
