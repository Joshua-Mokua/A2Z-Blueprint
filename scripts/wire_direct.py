#!/usr/bin/env python3
"""Wire the Direct consumer segment.

Nyaberi heads Direct informally today; a substantive Head of Direct is planned. The
plain `Relationship Manager`s sitting in branches are the ones running direct business
(they juggle across segments, so their pipeline/portfolio is mixed) — they get a DOTTED
line to him: view of their leads and pipeline, NO BSC rollup. Their solid line stays
the Branch Manager.

Why a new role: functional_hierarchy maps role -> role, and Nyaberi's own title IS
`Relationship Manager`. Pointing that role at him would make him dotted to himself.
`Head of Direct` is the role the substantive hire will take anyway — Nyaberi holds it
interim, exactly like Jane on Head of Consumer. Remap in admin when the hire lands.

    python wire_direct.py            # dry-run
    python wire_direct.py --apply

Run AFTER close_gaps.py and wire_layers.py.
"""
import json, os, shutil, sys
from datetime import datetime

OCP = "data/org_config.json"
STAGING = "data/staff_register_staging.xlsx"
ROLE = "Head of Direct"
HOLDER = "KE1223"          # Josphat Nyaberi Gichana — interim
SEGMENT_DOTTED = {"Relationship Manager": [ROLE]}

def main():
    import pandas as pd
    apply = "--apply" in sys.argv
    oc = json.load(open(OCP, encoding="utf-8"))
    hier = oc.get("hierarchy", {}) or {}
    func = oc.get("functional_hierarchy", {}) or {}
    roles = set(oc.get("roles", []) or [])
    df = pd.read_excel(STAGING, dtype=str).fillna("")

    who = df[df["Staff Code"] == HOLDER]
    if who.empty:
        print(f"ABORT: {HOLDER} not in the register."); sys.exit(1)
    name = who.iloc[0]["Staff Name"]

    print(f"1) ROLE  '{ROLE}'  -> ['Head of Consumer']"
          + ("   (new)" if ROLE not in roles else "   (exists)"))
    print(f"2) HOLDER {HOLDER} {name}: {who.iloc[0]['Role']!r} -> {ROLE!r}  (interim)")

    print("\n3) DOTTED (view only, no BSC rollup)")
    for r, parents in SEGMENT_DOTTED.items():
        print(f"   {r} -> {parents}")
    branch_rms = df[(df["Role"] == "Relationship Manager") & (df["Branch"] != "")
                    & (df["Staff Code"] != HOLDER)]
    ho_rms = df[(df["Role"] == "Relationship Manager") & (df["Branch"] == "")
                & (df["Staff Code"] != HOLDER)]
    print(f"\n   {len(branch_rms)} branch RMs land in his view:")
    for _, r in branch_rms.iterrows():
        print(f"      {r['Staff Code']:8} {r['Staff Name'][:26]:26} {r['Branch']}")
    if len(ho_rms):
        print(f"\n   !! {len(ho_rms)} HEAD-OFFICE RM(s) carry the same plain title, so they")
        print( "      would also be dotted to him. Retitle them in admin if that's wrong:")
        for _, r in ho_rms.iterrows():
            print(f"      {r['Staff Code']:8} {r['Staff Name'][:26]:26} {r['Department']}")

    if not apply:
        print("\n[DRY-RUN] re-run with --apply")
        return

    shutil.copyfile(OCP, OCP + f".pre_direct_{datetime.now():%Y%m%d-%H%M%S}")
    roles.add(ROLE)
    hier[ROLE] = ["Head of Consumer"]
    for r, parents in SEGMENT_DOTTED.items():
        func[r] = parents
    oc["roles"] = sorted(roles); oc["hierarchy"] = hier; oc["functional_hierarchy"] = func
    json.dump(oc, open(OCP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nwrote {OCP}")

    shutil.copyfile(STAGING, STAGING + f".pre_direct_{datetime.now():%Y%m%d-%H%M%S}")
    df.loc[df["Staff Code"] == HOLDER, "Role"] = ROLE
    df.to_excel(STAGING, index=False)
    print(f"wrote {STAGING}")
    print("\nNEXT: python build_upload_template.py && python scripts\\test_hierarchy.py")

if __name__ == "__main__":
    main()
