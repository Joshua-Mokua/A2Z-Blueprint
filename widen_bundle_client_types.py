#!/usr/bin/env python3
"""Bundles are mostly Business loans, but the cloned flow is tagged Consumer-only.
Widen Bundled Loan Product's client_types to both, so it appears for Business RMs too.
Safe: backup, refuse-if-core-missing, atomic.

    python widen_bundle_client_types.py --apply
"""
import json, shutil, sys, time, os
from pathlib import Path
PS = Path("data/pipeline_settings.json")
cfg = json.loads(PS.read_text(encoding="utf-8"))
pf = cfg.get("product_flows", {})
if "Bundled Loan Product" not in pf:
    print("REFUSING — Bundled Loan Product flow not found"); sys.exit(1)
cur = pf["Bundled Loan Product"].get("client_types")
print(f"current client_types: {cur}")
new = ["Consumer", "Business"]
if cur == new:
    print("already both."); sys.exit(0)
if "--apply" not in sys.argv:
    print(f"would set client_types -> {new}\n[DRY-RUN]"); sys.exit(0)
pf["Bundled Loan Product"]["client_types"] = new
if "product_flows" not in cfg or "product_catalogue" not in cfg:
    print("ABORT — core keys missing"); sys.exit(1)
shutil.copy2(PS, PS.with_suffix(f".json.pre_widen_{int(time.time())}"))
tmp = PS.with_suffix(".json.tmp"); tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
os.replace(tmp, PS)
print(f"set client_types -> {new}. Restart API.")
