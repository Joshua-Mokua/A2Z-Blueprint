#!/usr/bin/env python3
"""Seed the known dotted (functional) reporting lines into
org_config.json -> functional_hierarchy. Dotted lines grant pipeline/performance
VISIBILITY only (no BSC rollup). Idempotent. Run after Phase A + B1, then
restart uvicorn. Add more lines yourself in Admin -> Hierarchy (functional)."""
import json, os, sys, shutil
from datetime import datetime

DOTTED = {
    "Relationship Officer":                    ["Head of Consumer"],
    "Relationship Manager, Premier Banking":   ["Head Premier Banking"],
    "Relationship Officer, Premier Banking":   ["Head Premier Banking"],
    "Relationship Manager, Employee Schemes":  ["Head of Consumer"],
    "Relationship Manager, SME":               ["Head, SME"],
    "Relationship Manager, Local Corporate":   ["Head, Local Corporates"],
}

def find_cfg():
    here = os.path.dirname(os.path.abspath(__file__))
    for c in [os.path.join(here, "..", "data", "org_config.json"),
              os.path.join(os.getcwd(), "data", "org_config.json")]:
        if os.path.exists(c):
            return os.path.abspath(c)
    return None

def main():
    p = find_cfg()
    if not p:
        print("org_config.json not found (run from repo root or scripts/)"); sys.exit(1)
    cfg = json.load(open(p, encoding="utf-8"))
    roles = set(cfg.get("roles", [])) | set(cfg.get("hierarchy", {}).keys())
    func = dict(cfg.get("functional_hierarchy", {}) or {})
    added = []
    for role, parents in DOTTED.items():
        if role not in roles:
            print(f"  skip (role absent): {role}"); continue
        ps = [x for x in parents if x in roles]
        if not ps:
            print(f"  skip (parent absent): {role} -> {parents}"); continue
        if func.get(role) == ps:
            continue
        func[role] = ps; added.append(f"{role}  \u21e2  {', '.join(ps)}")
    if not added:
        print("no changes — already seeded."); return
    shutil.copyfile(p, p + f".pre_dotted_{datetime.now():%Y%m%d-%H%M%S}")
    cfg["functional_hierarchy"] = func
    json.dump(cfg, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("seeded dotted (functional) lines:")
    for a in added: print("  +", a)
    print("\nRestart uvicorn to apply.")

if __name__ == "__main__":
    main()
