#!/usr/bin/env python3
"""Emit a FILLED STAFF_UPLOAD_TEMPLATE from the ingested register, ready for
Admin -> Staff -> Upload (which validates, then writes PostgreSQL).

It does the tedious parts for you:
  * Branch      : Head Office for departmental staff; real branch for branch staff.
                  Branch-facing staff with no branch are left BLANK for you to fill.
  * Reports To  : DERIVED from org_config.hierarchy (role -> parent role), matching
                  the parent person in the same branch, else same department, else
                  bank-wide when unambiguous. Anything ambiguous is left BLANK.
  * Root        : the Managing Director is the single blank Reports To (as required).
  * Roles       : any role missing from org_config.hierarchy is added with NO parent
                  (--apply-roles), so upload validation passes and you can set the
                  real reporting line in Admin -> Hierarchy.

Read-only unless --apply-roles. Always writes data/STAFF_UPLOAD_FILLED.xlsx.

    python build_upload_template.py
    python build_upload_template.py --apply-roles
"""
import json, os, re, sys, shutil, collections
from datetime import datetime

OUT = "data/STAFF_UPLOAD_FILLED.xlsx"
COLS = ["Staff Code", "Staff Name", "Role", "Department", "Branch", "Region (DSA only)",
        "Reports To Code", "Dotted Line Code 1", "Dotted Line Code 2",
        "Band", "Gender", "Email", "Date of Employment"]
BRANCH_ROLE_HINTS = ("branch manager", "branch operations", "customer service manager",
                     "assistant branch", "branch credit", "teller", "direct sales agent",
                     "branch dsa team lead", "bancassurance officer")
ROOT_ROLE_HINTS = ("managing director",)

def norm(s):
    return re.sub(r"\s+", " ", str(s or "").replace("\u2019", "'").strip())

def main():
    apply_roles = "--apply-roles" in sys.argv
    import pandas as pd
    reg = "data/staff_register_staging.xlsx"   # staging: the live register is projected from PostgreSQL
    ocp = "data/org_config.json"
    for p in (reg, ocp):
        if not os.path.exists(p):
            print(f"MISSING {p}"); sys.exit(1)
    df = pd.read_excel(reg, dtype=str).fillna("")
    oc = json.load(open(ocp, encoding="utf-8"))
    hier = oc.get("hierarchy", {}) or {}
    acting_bm = {str(k): str(v) for k, v in (oc.get("acting_bm", {}) or {}).items()}
    branch_names = {norm(b["name"]) for b in oc.get("branches", [])}
    print(f"register {len(df)} rows | hierarchy roles {len(hier)} | branches {len(branch_names)}")

    people = []
    for _, r in df.iterrows():
        people.append({
            "code": norm(r.get("Staff Code")), "name": norm(r.get("Staff Name")),
            "role": norm(r.get("Role")), "branch": norm(r.get("Branch")),
            "dept": norm(r.get("Department")), "unit": norm(r.get("Unit")),
            "grade": norm(r.get("Grade")), "status": norm(r.get("Status")),
            "explicit": norm(r.get("Reports To Code")),   # manual override wins over derivation
            "dotted1": norm(r.get("Dotted Line 1")),
        })

    # ---- roles missing from the hierarchy (upload validates Role against hierarchy keys)
    missing = sorted({p["role"] for p in people if p["role"] and p["role"] not in hier})
    if missing:
        print(f"\n-- roles NOT in hierarchy ({len(missing)}) — upload would reject these people --")
        for m in missing:
            print(f"   {m}")
        if apply_roles:
            shutil.copyfile(ocp, ocp + f".pre_roles_{datetime.now():%Y%m%d-%H%M%S}")
            for m in missing:
                hier[m] = []                 # no parent yet — set it in Admin -> Hierarchy
            oc["hierarchy"] = hier
            json.dump(oc, open(ocp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print(f"   -> added to hierarchy with NO parent (set the real line in admin)")
        else:
            print("   -> re-run with --apply-roles to add them (blank parent) so upload passes")

    # ---- index people by role for parent resolution
    by_role = collections.defaultdict(list)
    for p in people:
        if p["code"]:
            by_role[p["role"]].append(p)

    def resolve_manager(p):
        """Find this person's manager's staff code.

        The hierarchy lists parent roles in PREFERENCE order — a DSA reports to the
        Branch DSA Team Lead, falling back to the Branch Manager only where that
        branch has no team lead. So we try each parent role in turn rather than
        pooling them (pooling made every DSA look 'ambiguous' between their team
        lead and their BM).

        Branch staff are matched INSIDE their own branch: a Westlands teller reports
        to a Westlands manager, never to one in Kisumu. Head-office staff are matched
        by department, then bank-wide when there is exactly one holder.
        """
        parents = hier.get(p["role"]) or []
        if not parents:
            return "", "no-parent-role"
        reasons = []
        for pr in parents:                       # hierarchy order = preference order
            cands = by_role.get(pr, [])
            if not cands:
                continue                          # nobody holds this parent role: try the next
            if p["branch"]:
                same = [c for c in cands if c["branch"] == p["branch"]]
                if len(same) == 1:
                    return same[0]["code"], ""
                if len(same) > 1:
                    # genuinely ambiguous — two managers of the same role in one branch
                    return "", f"{len(same)} {pr} in {p['branch']}"
                # Branch recruiting a BM? Whoever acts as BM fills the slot. This keeps
                # the real chain intact — a DSA still reports to their Team Lead, who
                # reports to the acting BM — instead of flattening the whole branch onto
                # one person. BSC rollup is transitive, so the (acting) BM still gets
                # every DSA's numbers through the team lead.
                if pr == "Branch Manager" and acting_bm.get(p["branch"]):
                    a = acting_bm[p["branch"]]
                    if a != p["code"]:
                        return a, ""
                # Nobody of that role in this branch. If the role has exactly one holder
                # bank-wide it is a head-office manager (e.g. a Branch Manager reports to
                # the single Head of Branches, who sits at HO) — unambiguous, take it.
                if len(cands) == 1:
                    return cands[0]["code"], ""
                continue                          # otherwise try the next parent role
            same_dept = [c for c in cands if c["dept"] and c["dept"] == p["dept"]]
            if len(same_dept) == 1:
                return same_dept[0]["code"], ""
            if len(same_dept) > 1:
                return "", f"{len(same_dept)} {pr} in {p['dept']}"
            if len(cands) == 1:
                return cands[0]["code"], ""
            reasons.append(f"{len(cands)} {pr} bank-wide")
        return "", (reasons[0] if reasons else f"nobody holds {', '.join(parents)}")

    # ---- build rows
    rows, why = [], collections.Counter()
    root_code = ""
    for p in people:
        role_l = p["role"].lower()
        is_root = any(h in role_l for h in ROOT_ROLE_HINTS)
        branch_facing = any(h in role_l for h in BRANCH_ROLE_HINTS)
        branch = p["branch"] or p["unit"]
        if branch not in branch_names:
            branch = "" if branch_facing else "Head Office"
        if is_root:
            mgr, reason = "", ""
            root_code = p["code"]
        elif p.get("explicit"):
            mgr, reason = p["explicit"], ""      # someone decided this by hand — respect it
        else:
            mgr, reason = resolve_manager(p)
            if reason:
                why[reason] += 1
        rows.append({
            "Staff Code": p["code"], "Staff Name": p["name"], "Role": p["role"],
            "Department": p["dept"], "Branch": branch, "Region (DSA only)": "",
            "Reports To Code": mgr, "Dotted Line Code 1": p.get("dotted1", ""),
            "Dotted Line Code 2": "",
            "Band": "", "Gender": "", "Email": "", "Date of Employment": "",
        })

    pd.DataFrame(rows, columns=COLS).to_excel(OUT, index=False)

    # ---- report what YOU still need to fill
    no_code = sum(1 for r in rows if not r["Staff Code"])
    no_branch = [r for r in rows if not r["Branch"]]
    no_mgr = [r for r in rows if not r["Reports To Code"] and r["Staff Code"] != root_code]
    print(f"\nwrote {OUT}  ({len(rows)} rows)")
    print(f"\n== still to fill in Excel ==")
    print(f"  Branch blank        : {len(no_branch)}")
    print(f"  Reports To blank    : {len(no_mgr)}")
    print(f"  No Staff Code (new) : {no_code}   <- upload SKIPS these; add via Admin -> Staff when recruited")
    if root_code:
        print(f"  Root (MD)           : {root_code}  [single blank Reports To — required]")
    else:
        print("  !! NO ROOT FOUND — exactly one row (the MD) must have blank Reports To")
    if why:
        print("\n  why Reports To couldn't be derived:")
        for k, n in why.most_common():
            print(f"    x{n:<4} {k}")
    if no_branch:
        print("\n  branches to fill, by role:")
        for rl, n in collections.Counter(r["Role"] for r in no_branch).most_common(8):
            print(f"    x{n:<4} {rl}")
    print("\nNEXT: open the file, fill the blanks, then Admin -> Staff -> Upload (preview validates first).")

if __name__ == "__main__":
    main()
