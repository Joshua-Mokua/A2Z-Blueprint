#!/usr/bin/env python3
"""Make the register upload-ready: drop the ADMIN001 system row (fixes 'invalid role
Admin' AND 'multiple roots'), validate Branch against the known set, re-run all uploader
checks. Admin login is preserved by the uploader's keep-set, so ADMIN001 doesn't belong
in the staff upload.

Writes data/staff_register_upload.xlsx (the file to take to Alex). Original untouched.

    python finalize_upload_register.py
"""
import json
import pandas as pd
from pathlib import Path

reg = pd.read_excel("data/staff_register.xlsx").fillna("")
print(f"source register: {len(reg)} rows")

# drop system/admin rows (role Admin, or the ADMIN001 code)
before = len(reg)
reg = reg[~(reg["Staff Code"].astype(str).str.upper().str.startswith("ADMIN"))]
reg = reg[reg["Role"].astype(str).str.strip().str.lower() != "admin"]
print(f"dropped {before-len(reg)} admin/system row(s) -> {len(reg)} staff")

cfg = json.loads(Path("data/org_config.json").read_text(encoding="utf-8"))
roles = set(cfg.get("hierarchy", {}).keys())
# branches: the validator checks against a branch set. Gather robustly from whatever
# shape org_config uses (dict keys, list of strings, or list of dicts with a name/branch).
branches = set()
def _collect(v):
    if isinstance(v, dict):
        branches.update(str(k) for k in v.keys())
        for sub in v.values():
            _collect(sub)
    elif isinstance(v, list):
        for item in v:
            if isinstance(item, str):
                branches.add(item)
            elif isinstance(item, dict):
                for nk in ("name","branch","branch_name","Branch","unit"):
                    if nk in item:
                        branches.add(str(item[nk])); break
for key in ("branches", "units", "branch_region", "branch_list", "regions"):
    if key in cfg:
        _collect(cfg[key])
# also accept any Branch already present (fallback) — but report mismatches
reg_branches = set(reg["Branch"].astype(str).str.strip())
print(f"\norg_config branch set: {len(branches)} known"
      f"{' (empty — validator may use a different source)' if not branches else ''}")

errs = []
# roles
bad_roles = {}
for _, r in reg.iterrows():
    role = str(r["Role"]).strip()
    if role and role not in roles:
        bad_roles[role] = bad_roles.get(role,0)+1
if bad_roles:
    print(f"\n⚠ roles not in hierarchy: {bad_roles}")
    errs.append("roles")
else:
    print("\n✓ all roles valid")

# branch check (only if we found a branch set)
if branches:
    bad_branches = sorted(reg_branches - branches)
    if bad_branches:
        print(f"⚠ branches not in known set ({len(bad_branches)}): {bad_branches[:15]}")
        errs.append("branches")
    else:
        print("✓ all branches valid")
else:
    print("• branch set not found in org_config — check where _staffup_validate gets 'branches'")

# roots
codes = set(reg["Staff Code"].astype(str).str.strip())
roots = reg[reg["Reports To Code"].astype(str).str.strip()==""]
print(f"\nroots now: {len(roots)} — {list(roots['Staff Code'])}")
if len(roots) != 1:
    print(f"⚠ validator wants EXACTLY 1 root (the MD). Have {len(roots)}."); errs.append("roots")
else:
    print("✓ exactly one root (the MD)")

# reports-to resolve
broken = [(r["Staff Code"], str(r["Reports To Code"]).strip())
          for _, r in reg.iterrows()
          if str(r["Reports To Code"]).strip() and str(r["Reports To Code"]).strip() not in codes]
if broken:
    print(f"⚠ broken reports-to: {broken[:8]}"); errs.append("reports_to")
else:
    print("✓ all reports-to resolve")

out = Path("data/staff_register_upload.xlsx")
reg.to_excel(out, index=False)
print(f"\nwrote {out} ({len(reg)} staff)")
print("=== VERDICT ===")
print("✓ READY to upload on Alex's admin" if not errs
      else f"⚠ still failing: {errs} — fix before uploading")
