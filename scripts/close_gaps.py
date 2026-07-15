#!/usr/bin/env python3
"""Close the reporting-line gaps with the business-confirmed structure.

Does four things (dry-run unless --apply; every file backed up first):

 1. ROLE PARENTS  for the roles that had none (Operations family -> Head of Operations,
    Card Officer -> Head of Consumer, Trade Sales Manager -> Director Corporate Banking,
    Value Chain Manager -> Head EFS, etc.)
 2. PEOPLE        Joshua Muthama added as Head of Branches (placeholder staff code until
    HR issues one); Jane Jelagat KE1158 -> Head of Consumer (interim); Rosemary Gitonga
    KE594 removed (retired) and her CX role retired.
 3. ACTING BMs    Mombasa Moi -> Fenella Mwamburi (ops manager in charge).
 4. NO-MANAGER BRANCHES  Eldoret / Thika / Karatina / Nyeri have neither a BM nor an ops
    manager, so their staff report to the Head of Branches until a BM is appointed.
    Written as an EXPLICIT Reports To Code, which the template builder respects.

    python close_gaps.py            # dry-run
    python close_gaps.py --apply
"""
import json, os, shutil, sys
from datetime import datetime

STAGING = "data/staff_register_staging.xlsx"
OCP = "data/org_config.json"

HOB_CODE = "KE1354"        # next in sequence after KE1353; confirm with HR, editable in admin
HOB_NAME = "Joshua Muthama"

ROLE_PARENTS = {
    "Operations Officer": ["Head of Operations"],
    "Operations Assistant Officer": ["Head of Operations"],
    "Cards Operations Officer": ["Head of Operations"],
    "Cheque Validation Officer": ["Head of Operations"],
    "Payments Operations Officer": ["Head of Operations"],
    "Service Officer, TROPS": ["Head of Operations"],
    "Service Officer- Payments": ["Head of Operations"],
    "Officer Operations": ["Head of Operations"],
    "Card Officer": ["Head of Consumer"],
    "Digital sales Officer": ["Head, Cash Management"],
    "Social Media Officer": ["Corporate Communications Manager"],
    "Trade Sales Manager": ["Director, Corporate Banking Kenya & EAC"],
    "Value Chain Manager": ["Head EFS"],
}
# Branches recruiting a BM: whoever is in charge acts as Branch Manager. Where there
# is an ops manager they hold it; elsewhere the Customer Service Manager does.
ACTING_BM = {
    "Mombasa Moi": "KE807",   # Fenella Mwamburi   (ops manager)
    "Eldoret":     "KE439",   # Ludy Chebet Mining (CSM)
    "Thika":       "KE637",   # Brenda Cherono Rono (CSM)
    "Karatina":    "KE546",   # Elizabeth Nyawira Miano (CSM)
    "Nyeri":       "KE461",   # Betty Wachera Waiguru (CSM)
}
NO_MANAGER_BRANCHES = []

# Individual calls that derivation can't make.
EXPLICIT = {
    # Westlands has two ops managers: Esther holds the solid line, Benson a dotted one.
    "KE96": "KE792", "KE467": "KE792", "KE1153": "KE792", "KE1162": "KE792",
    # Head-office RMs sit in no branch, so "report to your Branch Manager" can't apply.
    "KE1223": "KE1158",   # Josphat Gichana   -> Head of Consumer
    "KE1261": "KE1158",   # Stephen Kimuyu    -> Head of Consumer
    "KE1230": "KE1265",   # Shen Xue PEI      -> Director, Corporate Banking
}
DOTTED = {"KE96": "KE833", "KE467": "KE833", "KE1153": "KE833", "KE1162": "KE833"}
RETIRED = {"KE594": "Rosemary Gaicugi Gitonga (retired)"}
ROLE_MOVES = {"KE1158": "Head of Consumer"}          # Jane Jelagat, interim

def main():
    import pandas as pd
    apply = "--apply" in sys.argv
    oc = json.load(open(OCP, encoding="utf-8"))
    hier = oc.get("hierarchy", {}) or {}
    roles = set(oc.get("roles", []) or [])
    df = pd.read_excel(STAGING, dtype=str).fillna("")
    if "Reports To Code" not in df.columns:
        df["Reports To Code"] = ""

    print("1) ROLE PARENTS")
    rp = []
    for r, parents in ROLE_PARENTS.items():
        missing = [x for x in parents if x not in roles and x not in hier]
        if missing:
            print(f"   !! {r:44} parent not in catalog: {missing}  SKIPPED"); continue
        if (hier.get(r) or []) == parents:
            continue
        print(f"   ~  {r:44} -> {parents}")
        rp.append((r, parents))

    print("\n2) PEOPLE")
    have_hob = (df["Role"] == "Head of Branches").any()
    print(f"   +  {HOB_CODE} {HOB_NAME:26} Head of Branches" + ("  (already present)" if have_hob else ""))
    for code, role in ROLE_MOVES.items():
        cur = df.loc[df["Staff Code"] == code, "Role"]
        print(f"   ~  {code} role {cur.iloc[0] if len(cur) else '?'!r} -> {role!r}")
    for code, who in RETIRED.items():
        print(f"   -  {code} {who}")

    print("\n3) ACTING BRANCH MANAGERS (branches recruiting a BM)")
    for b, code in ACTING_BM.items():
        nm = df.loc[df["Staff Code"] == code, "Staff Name"]
        rl = df.loc[df["Staff Code"] == code, "Role"]
        n = int(((df["Branch"] == b) & (df["Staff Code"] != code)).sum())
        print(f"   {b:16} -> {code} {(nm.iloc[0] if len(nm) else '?'):24} "
              f"[{rl.iloc[0] if len(rl) else '?'}]  {n} staff")

    print("\n5) INDIVIDUAL CALLS")
    for code, mgr in EXPLICIT.items():
        nm = df.loc[df["Staff Code"] == code, "Staff Name"]
        mn = df.loc[df["Staff Code"] == mgr, "Staff Name"]
        d = DOTTED.get(code)
        dn = df.loc[df["Staff Code"] == d, "Staff Name"] if d else []
        extra = f"   (dotted: {d} {dn.iloc[0]})" if d is not None and len(dn) else ""
        print(f"   {code} {(nm.iloc[0] if len(nm) else '?'):26} -> {mgr} "
              f"{mn.iloc[0] if len(mn) else '?'}{extra}")

    print("\n4) BRANCHES WITH NO MANAGER -> staff report to Head of Branches")
    tot = 0
    for b in NO_MANAGER_BRANCHES:
        n = int(((df["Branch"] == b) & (df["Staff Code"] != "")).sum())
        tot += n
        print(f"   {b:16} {n:3} staff -> {HOB_CODE}")
    print(f"   {'total':16} {tot:3}")

    if not apply:
        print("\n[DRY-RUN] re-run with --apply")
        return

    # --- org_config
    shutil.copyfile(OCP, OCP + f".pre_closegaps_{datetime.now():%Y%m%d-%H%M%S}")
    for r, parents in rp:
        hier[r] = parents
        roles.add(r)
    if "Head of Branches" not in roles:
        roles.add("Head of Branches")
    oc["hierarchy"] = hier
    oc["roles"] = sorted(roles)
    oc.setdefault("acting_bm", {}).update(ACTING_BM)
    json.dump(oc, open(OCP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nwrote {OCP}")

    # --- register (staging)
    shutil.copyfile(STAGING, STAGING + f".pre_closegaps_{datetime.now():%Y%m%d-%H%M%S}")
    df = df[~df["Staff Code"].isin(RETIRED)]                     # retirees out
    for code, role in ROLE_MOVES.items():
        df.loc[df["Staff Code"] == code, "Role"] = role
    df.loc[df["Role"] == "Head of Branches", "Staff Code"] = HOB_CODE
    if not (df["Role"] == "Head of Branches").any():
        df = pd.concat([df, pd.DataFrame([{
            "Staff Code": HOB_CODE, "Staff Name": HOB_NAME, "Display Name": HOB_NAME,
            "Role": "Head of Branches", "Source Designation": "Head of Branches",
            "Grade": "", "Unit": "Head Office", "Department": "Commercial Banking",
            "Branch": "", "Region": "", "Introducer Code": "", "Status": "perm",
            "Reports To Code": "",
        }])], ignore_index=True)
    # acting BMs: that branch's staff report to the acting BM
    for b, code in ACTING_BM.items():
        m = (df["Branch"] == b) & (df["Staff Code"] != code) & (df["Reports To Code"] == "")
        df.loc[m, "Reports To Code"] = code
        df.loc[df["Staff Code"] == code, "Reports To Code"] = HOB_CODE
    # branches with nobody at all: everyone reports to the Head of Branches
    for b in NO_MANAGER_BRANCHES:
        m = (df["Branch"] == b) & (df["Reports To Code"] == "")
        df.loc[m, "Reports To Code"] = HOB_CODE
    # individual calls override everything
    if "Dotted Line 1" not in df.columns:
        df["Dotted Line 1"] = ""
    for code, mgr in EXPLICIT.items():
        df.loc[df["Staff Code"] == code, "Reports To Code"] = mgr
    for code, d in DOTTED.items():
        df.loc[df["Staff Code"] == code, "Dotted Line 1"] = d
    df.to_excel(STAGING, index=False)
    print(f"wrote {STAGING}  ({len(df)} rows)")
    print("\nNEXT: python build_upload_template.py")

if __name__ == "__main__":
    main()
