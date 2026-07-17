#!/usr/bin/env python3
"""Seed org_config.data_custodian_roles — the roles that get full data-custodian
visibility (all pipeline/activity/referrals/portfolio): the CFO + her Finance team
and the Ag Head HR. Edit the DEFAULTS below to taste, or pass --roles "A;B;C".
Backs up org_config.json (.pre_custodians_*). Dry-run unless --apply. Run from repo root."""
import json, os, sys, shutil
from datetime import datetime

DEFAULTS = [
    "Chief Finance Officer",
    "Finance Officer",
    "Manager, Business Finance & Performance Management",
    "Manager, Financial Control & Regulatory Reporting",
    "Ag. Head Human Resources & Senior HR Business Partner",
]

def main():
    p = None
    for c in ("data/org_config.json", "a2z/data/org_config.json"):
        if os.path.exists(c):
            p = c; break
    if not p:
        print("org_config.json not found"); sys.exit(1)
    roles = DEFAULTS
    if "--roles" in sys.argv:
        i = sys.argv.index("--roles")
        if i + 1 < len(sys.argv):
            roles = [r.strip() for r in sys.argv[i + 1].split(";") if r.strip()]
    cfg = json.load(open(p, encoding="utf-8"))
    known = set(cfg.get("roles", []) or [])
    matched = [r for r in roles if r in known]
    missing = [r for r in roles if r not in known]
    print("custodian roles to set:")
    for r in roles:
        print(f"  {'OK ' if r in known else '?? '} {r}")
    if missing:
        print("\nWARNING: these are not in org_config.roles (will be stored but never match a real user):")
        for r in missing:
            print("   -", r)
    if "--apply" not in sys.argv:
        print("\n[DRY-RUN] add --apply to write org_config.data_custodian_roles")
        return
    shutil.copyfile(p, p + f".pre_custodians_{datetime.now():%Y%m%d-%H%M%S}")
    cfg["data_custodian_roles"] = roles
    json.dump(cfg, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nwrote {p} with {len(roles)} custodian role(s). Restart uvicorn.")

if __name__ == "__main__":
    main()
