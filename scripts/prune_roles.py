#!/usr/bin/env python3
"""Prune kpi_library.json -> role_kpis to keep only roles that exist in the
Ecobank org_config (data/org_config.json -> roles). Removes the legacy generic
banking roles so the Roles panel shows Ecobank roles only. Backs up first
(.pre_prune_*). Kept roles retain their KPI mapping; the other Ecobank roles can
be assigned KPIs in the KPI Library afterwards. Restart uvicorn after running."""
import json, os, sys, shutil
from datetime import datetime

def dfile(name):
    here=os.path.dirname(os.path.abspath(__file__))
    for c in [os.path.join(here,"..","data",name), os.path.join(os.getcwd(),"data",name)]:
        if os.path.exists(c): return os.path.abspath(c)
    return None

def main():
    kp=dfile("kpi_library.json"); oc=dfile("org_config.json")
    if not kp or not oc:
        print("kpi_library.json or org_config.json not found"); sys.exit(1)
    eco=set(json.load(open(oc,encoding="utf-8")).get("roles",[]))
    lib=json.load(open(kp,encoding="utf-8"))
    rk=lib.get("role_kpis",{}) or {}
    keep={r:v for r,v in rk.items() if r in eco}
    removed=sorted(set(rk)-set(keep))
    if not removed:
        print("nothing to prune (already Ecobank-only)."); return
    if "--yes" not in sys.argv:
        print(f"Would keep {len(keep)} Ecobank role(s), remove {len(removed)} legacy role(s).")
        print("Sample removed:", removed[:8], "...")
        print("\nRe-run with --yes to apply:  python scripts/prune_roles.py --yes")
        return
    shutil.copyfile(kp, kp+f".pre_prune_{datetime.now():%Y%m%d-%H%M%S}")
    lib["role_kpis"]=keep
    json.dump(lib, open(kp,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"kept {len(keep)} Ecobank role(s); removed {len(removed)} legacy role(s).")
    print("kept:", sorted(keep))
    print("\nRestart uvicorn. Assign KPIs to the remaining Ecobank roles in the KPI Library as needed.")

if __name__=="__main__": main()
