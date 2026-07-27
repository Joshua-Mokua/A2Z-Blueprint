#!/usr/bin/env python3
"""Step 1 (fixed): seed "Bundled Loan Product" so the create-time readiness gate passes.
product_catalogue is a dict {category: [product names]} — loan products live under 'Assets'.
Adds the name there, and clones a loan product_flows entry (its per-stage target_days = SLA).

Safe write: backup, refuse-if-core-keys-missing, atomic replace, only ADD our product.

    python seed_bundled_loan_product.py            # dry run
    python seed_bundled_loan_product.py --apply
"""
import json, shutil, sys, time, os
from pathlib import Path

PRODUCT    = "Bundled Loan Product"
CLONE_FROM = "Personal Loan"
CATEGORY   = "Assets"           # loan products live here
PS = Path("data/pipeline_settings.json")

cfg = json.loads(PS.read_text(encoding="utf-8"))
CORE = ("stages", "product_catalogue", "product_flows", "stage_flows")
missing = [k for k in CORE if k not in cfg]
if missing:
    print(f"REFUSING — missing core keys {missing}"); sys.exit(1)

cat = cfg["product_catalogue"]
if not isinstance(cat, dict) or CATEGORY not in cat or not isinstance(cat[CATEGORY], list):
    print(f"REFUSING — product_catalogue['{CATEGORY}'] is not a list as expected"); sys.exit(1)

already_cat = any(str(n).strip().lower() == PRODUCT.lower() for n in cat[CATEGORY])
print(f"catalogue['{CATEGORY}']: {len(cat[CATEGORY])} products; '{PRODUCT}' present: {already_cat}")

pflows = cfg["product_flows"]
if CLONE_FROM not in pflows:
    cand = next((k for k in pflows if any(w in k.lower() for w in ("personal","business","loan"))), None)
    if not cand: print("REFUSING — no loan flow to clone"); sys.exit(1)
    CLONE_FROM = cand
clone = json.loads(json.dumps(pflows[CLONE_FROM]))
day_sum = sum(s.get("target_days", 0) for s in clone.get("stages", []))
already_flow = PRODUCT in pflows
print(f"clone flow from '{CLONE_FROM}': {len(clone.get('stages',[]))} stages, day-sum {day_sum}")
print(f"product_flows['{PRODUCT}'] present: {already_flow}")

print("\n=== planned additions ===")
print(f"   catalogue['{CATEGORY}'] += '{PRODUCT}'  {'(skip, present)' if already_cat else ''}")
print(f"   product_flows['{PRODUCT}'] = clone of '{CLONE_FROM}'  {'(skip, present)' if already_flow else ''}")

if "--apply" not in sys.argv:
    print("\n[DRY-RUN] re-run with --apply"); sys.exit(0)

if not already_cat:
    cfg["product_catalogue"][CATEGORY].append(PRODUCT)
if not already_flow:
    clone["client_types"] = clone.get("client_types") or ["Consumer"]
    cfg["product_flows"][PRODUCT] = clone

if any(k not in cfg for k in CORE):
    print("ABORT — core keys would be lost"); sys.exit(1)

shutil.copy2(PS, PS.with_suffix(f".json.pre_bundle_{int(time.time())}"))
tmp = PS.with_suffix(".json.tmp")
tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
os.replace(tmp, PS)
print("\napplied. Restart the API, then verify _product_readiness('Bundled Loan Product').")
