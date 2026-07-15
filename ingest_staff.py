#!/usr/bin/env python3
"""A2Z — ingest the REAL staff register (permanent + DSA), v2.

CHANGED vs v1: NO fuzzy guessing. A designation is resolved by
    exact match  ->  curated alias  ->  otherwise ADDED as a new catalog role
so nobody is ever silently filed into the wrong job. Everything added or aliased
is reported for your admin amendment.

READ-ONLY until --apply. With --apply it writes (backing each up first):
    data/staff_register.xlsx      the register
    data/org_config.json          only to append genuinely new roles

Inputs:
    data/staff_source_permanent.xlsx   Staff Number | Name of Staff | Designation | Department
    data/staff_source_dsa.xlsx         Staff Number | Name | Title | Branch

Usage:  python ingest_staff.py            # dry-run
        python ingest_staff.py --apply
"""
import json, os, re, sys, shutil
from datetime import datetime

# --- curated aliases: source designation -> canonical catalog role -------------
ALIASES = {
    # typos / word-order drift
    "senior treasure sales officer": "Senior Treasury Sales Officer",
    "manager, operations risk": "Manager Operation Risk",
    "service assistant, operations": "Service Assistant, Operations Officer",
    "assistant branch operations & service manager": "Assistant Branch Service & Operations Manager",
    "assistant branch  operations & service manager": "Assistant Branch Service & Operations Manager",
    # zonal structure removed -> plain Branch Manager
    "zonal manager & branch manager": "Branch Manager",
    # HR head: keeps Christine's data-custodian grant working
    "acting hr head": "Ag. Head Human Resources & Senior HR Business Partner",
}
# --- source typos corrected before resolution (clean names enter the catalog) --
TYPO_FIX = {
    "social medial officer": "Social Media Officer",
    "head of cusomer experience kenya & cesa 1": "Head of Customer Experience Kenya & CESA 1",
    "head information & techonolgy": "Head Information & Technology",
    "head informations security & bcp": "Head Information Security & BCP",
    "finanacial risk manager": "Financial Risk Manager",
    "portfololio analysis & reporting manager": "Portfolio Analysis & Reporting Manager",
}

# --- DSA titles: grade is a separate attribute, NOT a role --------------------
DSA_ROLE_MAP = {
    "team leader": "Branch DSA Team Lead",
    "standard dsa": "Direct Sales Agent",
    "intermediate dsa": "Direct Sales Agent",
    "senior dsa": "Direct Sales Agent",
    "bancassurance sales officer": "Bancassurance Officer",
}
DSA_GRADE = {"standard dsa": "Standard", "intermediate dsa": "Intermediate",
             "senior dsa": "Senior", "team leader": "Team Leader",
             "bancassurance sales officer": "Bancassurance"}
BRANCH_ALIASES = {"mombasa": "Mombasa Moi"}
HUB_NAMES = {"the hub branch", "the hub", "hub"}
# The Hub is hosted at Ecobank Towers — DSAs there book into Towers until reassigned.
HUB_BRANCH = "Ecobank Towers"
# roles that MUST sit in a branch (used to flag missing branch assignment)
BRANCH_ROLE_HINTS = ("branch manager", "branch operations", "customer service manager",
                     "assistant branch", "branch credit", "teller")

def norm(s):
    return re.sub(r"\s+", " ", str(s or "").replace("\u2019", "'").strip())

def key(s):
    return re.sub(r"[^a-z0-9]", "", norm(s).lower())

def find_col(cols, *wants):
    for w in wants:
        for c in cols:
            if key(w) == key(c):
                return c
    for w in wants:
        for c in cols:
            if key(w) in key(c):
                return c
    return None

def canon_code(raw, is_dsa):
    r = norm(raw).replace(" ", "")
    if not r or r.lower() in ("new", "n/a", "-"):
        return "", "pending"
    if is_dsa:
        return r.upper(), "dsa"
    m = re.match(r"^(?:KE)?0*(\d+)$", r, re.I)
    return ("KE" + m.group(1), "perm") if m else (r.upper(), "perm")

def display_name(full):
    p = [x for x in norm(full).split(" ") if x]
    return "" if not p else (" ".join(p) if len(p) <= 2 else f"{p[0]} {p[-1]}")

def main():
    apply = "--apply" in sys.argv
    ocp = "data/org_config.json" if os.path.exists("data/org_config.json") else "a2z/data/org_config.json"
    oc = json.load(open(ocp, encoding="utf-8"))
    roles = [norm(r) for r in oc.get("roles", [])]
    role_by_key = {key(r): r for r in roles}
    branches = {norm(b["name"]) for b in oc.get("branches", []) if b.get("type") != "HO"}
    branch_by_key = {key(b): b for b in branches}
    print(f"canonical: {len(roles)} roles, {len(branches)} branches\n")

    rows, aliased, new_roles, unknown_branches, hub_hosted = [], [], {}, [], []
    import pandas as pd

    def resolve_role(desig):
        # 1) exact catalog match ALWAYS wins — the catalog was built from this same
        #    list, typos included; "correcting" a matching designation would create
        #    a duplicate role (clean + typo'd) for the same job.
        if key(desig) in role_by_key and role_by_key[key(desig)] not in new_roles:
            return role_by_key[key(desig)], None
        # 2) only unmatched designations get typo-corrected before entering the catalog
        desig = TYPO_FIX.get(norm(desig).lower(), norm(desig))
        k = key(desig)
        if k in role_by_key:
            canon = role_by_key[k]
            if canon in new_roles:                # already added this run
                new_roles[canon] += 1
                return canon, "new"
            return canon, None
        a = ALIASES.get(norm(desig).lower())
        if a and key(a) in role_by_key:
            return role_by_key[key(a)], "alias"
        canon = norm(desig)
        role_by_key[key(canon)] = canon           # becomes a catalog role
        new_roles[canon] = 1
        return canon, "new"

    # ---- permanent ----
    p = "data/staff_source_permanent.xlsx"
    if os.path.exists(p):
        df = pd.read_excel(p, dtype=str).fillna("")
        c_no = find_col(df.columns, "Staff Number", "Staff No", "Staff Code")
        c_nm = find_col(df.columns, "Name of Staff", "Name", "Staff Name")
        c_ds = find_col(df.columns, "Designation", "Title", "Role")
        c_dp = find_col(df.columns, "Department", "Dept")
        c_br = find_col(df.columns, "Branch", "Unit", "Location", "Posting")
        print(f"permanent: {len(df)} rows  (branch/unit column: {c_br or 'NONE — the source has no Unit/Branch'})")
        for _, r in df.iterrows():
            full, desig = norm(r.get(c_nm)), norm(r.get(c_ds))
            if not full:
                continue
            code, kind = canon_code(r.get(c_no), False)
            role, how = resolve_role(desig)
            if how == "alias":
                aliased.append((full, desig, role))
            dept = norm(r.get(c_dp)).replace("Human resources", "Human Resources")
            braw = norm(r.get(c_br)) if c_br else ""
            # a Unit value only counts as a branch when it actually names one
            branch = branch_by_key.get(key(braw), "") if braw else ""
            if braw and not branch and key(BRANCH_ALIASES.get(braw.lower(), "")) in branch_by_key:
                branch = branch_by_key[key(BRANCH_ALIASES[braw.lower()])]
            rows.append({"Staff Code": code, "Staff Name": full, "Display Name": display_name(full),
                         "Role": role, "Source Designation": desig, "Grade": "",
                         "Unit": branch or dept, "Department": dept, "Branch": branch,
                         "Region": "", "Introducer Code": "", "Status": kind})
    else:
        print(f"MISSING {p}")

    # ---- DSAs ----
    p = "data/staff_source_dsa.xlsx"
    if os.path.exists(p):
        df = pd.read_excel(p, dtype=str).fillna("")
        c_no = find_col(df.columns, "Staff Number", "Staff No", "Code")
        c_nm = find_col(df.columns, "Name", "Name of Staff")
        c_ti = find_col(df.columns, "Title", "Designation")
        c_br = find_col(df.columns, "Branch", "Unit")
        print(f"DSA:       {len(df)} rows")
        for _, r in df.iterrows():
            full, title = norm(r.get(c_nm)), norm(r.get(c_ti))
            if not full:
                continue
            code, kind = canon_code(r.get(c_no), True)
            tk = title.lower()
            role = DSA_ROLE_MAP.get(tk)
            grade = DSA_GRADE.get(tk, "")
            if not role:
                role, how = resolve_role(title)
            braw = norm(r.get(c_br)); bk = key(braw)
            if bk in {key(h) for h in HUB_NAMES}:
                unit = branch = branch_by_key.get(key(HUB_BRANCH), HUB_BRANCH)
                hub_hosted.append(full)
            elif bk in branch_by_key:
                unit = branch = branch_by_key[bk]
            elif key(BRANCH_ALIASES.get(braw.lower(), "")) in branch_by_key:
                unit = branch = branch_by_key[key(BRANCH_ALIASES[braw.lower()])]
            else:
                unknown_branches.append((full, braw)); unit = branch = braw
            rows.append({"Staff Code": code, "Staff Name": full, "Display Name": display_name(full),
                         "Role": role, "Source Designation": title, "Grade": grade,
                         "Unit": unit, "Department": "Consumer Banking", "Branch": branch,
                         "Region": "", "Introducer Code": "", "Status": kind})
    else:
        print(f"MISSING {p}")

    # ---- reports ----
    print("\n" + "=" * 64)
    print(f"TOTAL {len(rows)}   permanent {sum(1 for r in rows if r['Status']=='perm')}"
          f" | DSA {sum(1 for r in rows if r['Status']=='dsa')}"
          f" | pending recruitment {sum(1 for r in rows if r['Status']=='pending')}")

    if aliased:
        print(f"\n-- aliases applied (curated, safe): {len(aliased)} --")
        seen = set()
        for n, d, rl in aliased:
            if d not in seen:
                seen.add(d)
                print(f"   {d[:44]:44} -> {rl}")

    if new_roles:
        print(f"\n-- NEW ROLES added to catalog ({len(new_roles)}) — each needs a reporting line + KPIs in admin --")
        for rl, n in sorted(new_roles.items(), key=lambda x: -x[1]):
            print(f"   x{n:<3} {rl}")

    nobranch = [r for r in rows if r["Status"] == "perm" and not r["Branch"]
                and any(h in r["Role"].lower() for h in BRANCH_ROLE_HINTS)]
    if nobranch:
        print(f"\n-- !! BRANCH-FACING STAFF WITH NO BRANCH: {len(nobranch)} --")
        import collections
        for rl, n in collections.Counter(r["Role"] for r in nobranch).most_common():
            print(f"   x{n:<3} {rl}")
        print("   (the permanent source has no Branch column — branch scoping needs these)")

    if hub_hosted:
        print(f"\n-- Hub-hosted DSAs mapped to {HUB_BRANCH}: {len(hub_hosted)} (reassign in admin if needed) --")
        for n in hub_hosted:
            print(f"   {n}")

    if unknown_branches:
        print(f"\n-- UNKNOWN BRANCHES: {len(unknown_branches)} --")
        for n, b in unknown_branches[:12]:
            print(f"   {n:32} {b}")

    codes = [r["Staff Code"] for r in rows if r["Staff Code"]]
    dups = sorted({c for c in codes if codes.count(c) > 1})
    if dups:
        print(f"\n-- !! DUPLICATE STAFF CODES: {dups}")

    disp = [r["Display Name"] for r in rows]
    coll = sorted({d for d in disp if disp.count(d) > 1})
    if coll:
        print(f"\n-- display-name collisions ({len(coll)}) --")
        for d in coll[:10]:
            print(f"   {d:26} {[x['Staff Code'] or 'pending' for x in rows if x['Display Name']==d]}")

    import collections
    print("\n-- departments seen --")
    for d, n in collections.Counter(r["Department"] for r in rows).most_common():
        print(f"   x{n:<4} {d}")

    if not apply:
        print("\n[DRY-RUN] nothing written. Re-run with --apply when the above reads right.")
        return

    out = "data/staff_register.xlsx"
    if os.path.exists(out):
        shutil.copyfile(out, out + f".pre_ingest_{datetime.now():%Y%m%d-%H%M%S}")
    pd.DataFrame(rows).to_excel(out, index=False)
    print(f"\nwrote {out}  ({len(rows)} rows)")
    if new_roles:
        shutil.copyfile(ocp, ocp + f".pre_ingest_{datetime.now():%Y%m%d-%H%M%S}")
        oc["roles"] = sorted(set(oc.get("roles", [])) | set(new_roles))
        json.dump(oc, open(ocp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"wrote {ocp}  (+{len(new_roles)} roles, now {len(oc['roles'])})")
    print("\nRestart uvicorn. Then map the new roles' reporting lines in admin.")

if __name__ == "__main__":
    main()
