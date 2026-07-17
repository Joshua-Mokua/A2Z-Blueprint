#!/usr/bin/env python3
"""Fill the missing branches without scrolling a 390-row sheet.

    python branch_fill.py            -> writes data/BRANCH_FILL.xlsx (only the rows
                                        that need a branch, with a dropdown of your
                                        16 branches). Fill the Branch column in Excel.
    python branch_fill.py --merge    -> reads it back, writes Branch+Unit into
                                        data/staff_register.xlsx (backed up first).

Then re-run:  python build_upload_template.py
"""
import json, os, shutil, sys
from datetime import datetime

FILL = "data/BRANCH_FILL.xlsx"
REG = "data/staff_register.xlsx"
BRANCH_ROLE_HINTS = ("branch manager", "branch operations", "customer service manager",
                     "assistant branch", "branch credit", "teller", "direct sales agent",
                     "branch dsa team lead", "bancassurance officer")

def branches():
    oc = json.load(open("data/org_config.json", encoding="utf-8"))
    return [str(b["name"]) for b in oc.get("branches", []) if b.get("name")]

def main():
    import pandas as pd
    if not os.path.exists(REG):
        print(f"MISSING {REG}"); sys.exit(1)
    df = pd.read_excel(REG, dtype=str).fillna("")
    names = branches()

    if "--merge" in sys.argv:
        if not os.path.exists(FILL):
            print(f"MISSING {FILL} — run without --merge first"); sys.exit(1)
        fill = pd.read_excel(FILL, dtype=str).fillna("")
        m = {str(r["Staff Code"]).strip(): str(r.get("Branch") or "").strip()
             for _, r in fill.iterrows() if str(r.get("Staff Code") or "").strip()}
        bad = sorted({b for b in m.values() if b and b not in names})
        if bad:
            print("ABORT — these are not one of your branches (check spelling):")
            for b in bad:
                print(f"   {b!r}")
            sys.exit(1)
        applied = 0
        for i, r in df.iterrows():
            code = str(r.get("Staff Code") or "").strip()
            b = m.get(code, "")
            if b and not str(r.get("Branch") or "").strip():
                df.at[i, "Branch"] = b
                df.at[i, "Unit"] = b       # Unit MUST equal the branch name for scoping
                applied += 1
        shutil.copyfile(REG, REG + f".pre_branchfill_{datetime.now():%Y%m%d-%H%M%S}")
        df.to_excel(REG, index=False)
        still = sum(1 for _, r in df.iterrows()
                    if not str(r.get("Branch") or "").strip()
                    and any(h in str(r.get("Role") or "").lower() for h in BRANCH_ROLE_HINTS))
        print(f"merged {applied} branch assignment(s) into {REG}")
        print(f"still missing a branch: {still}")
        print("\nNEXT: python build_upload_template.py")
        return

    need = [r for _, r in df.iterrows()
            if not str(r.get("Branch") or "").strip()
            and any(h in str(r.get("Role") or "").lower() for h in BRANCH_ROLE_HINTS)]
    if not need:
        print("nothing to fill — every branch-facing person already has a branch.")
        return
    out = pd.DataFrame([{
        "Staff Code": str(r.get("Staff Code") or ""),
        "Staff Name": str(r.get("Staff Name") or ""),
        "Role": str(r.get("Role") or ""),
        "Department": str(r.get("Department") or ""),
        "Branch": "",
    } for r in need])
    out.to_excel(FILL, index=False)

    # add a real dropdown so nobody typos a branch name
    try:
        from openpyxl import load_workbook
        from openpyxl.worksheet.datavalidation import DataValidation
        wb = load_workbook(FILL); ws = wb.active
        dv = DataValidation(type="list", formula1='"' + ",".join(names) + '"', allow_blank=True)
        dv.error = "Pick a branch from the list"
        ws.add_data_validation(dv)
        dv.add(f"E2:E{len(out) + 1}")
        for col, w in (("A", 12), ("B", 34), ("C", 44), ("D", 22), ("E", 22)):
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "A2"
        wb.save(FILL)
        drop = "with a dropdown of your 16 branches"
    except Exception as e:
        drop = f"(dropdown unavailable: {e})"

    print(f"wrote {FILL}  ({len(out)} rows) {drop}\n")
    import collections
    for rl, n in collections.Counter(r["Role"] for r in need).most_common():
        print(f"   x{n:<4} {rl}")
    print(f"\nbranches: {', '.join(names)}")
    print("\nFill the Branch column, save, then:  python branch_fill.py --merge")

if __name__ == "__main__":
    main()
