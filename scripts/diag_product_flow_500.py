#!/usr/bin/env python3
"""scripts/diag_product_flow_500.py — reproduce the product-flows upsert path
locally (no HTTP) to surface the exact exception, and verify every JSON the
pipeline reads loads under the platform default encoding (the cp1252 trap).

Run from project root with the venv active:
    python scripts/diag_product_flow_500.py
"""
from __future__ import annotations
import json, os, sys, traceback

DATA = "data"

def check_encoding(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return f"  (absent) {name}"
    # 1) platform-default open (what a bare open() would do)
    try:
        with open(p) as f:
            json.load(f)
        d1 = "default-open OK"
    except Exception as e:
        d1 = f"default-open FAIL: {type(e).__name__}: {str(e)[:60]}"
    # 2) explicit utf-8
    try:
        with open(p, encoding="utf-8") as f:
            json.load(f)
        d2 = "utf-8 OK"
    except Exception as e:
        d2 = f"utf-8 FAIL: {type(e).__name__}: {str(e)[:60]}"
    flag = "" if "OK" in d1 else "   <-- cp1252 TRAP"
    return f"  {name:32s} {d1:42s} | {d2}{flag}"

def main():
    print("=== JSON encoding check (default-open vs utf-8) ===")
    for n in ["pipeline_settings.json", "lms_config.json", "loan_applications.json",
              "pipeline_deals.json", "org_config.json", "credit_admin.json",
              "partnerships_mous.json", "target_cascade.json", "bank_targets.json"]:
        print(check_encoding(n))

    print("\n=== reproduce get/save_pipeline_settings + a product-flow upsert ===")
    try:
        sys.path.insert(0, ".")
        from utils.core import get_pipeline_settings, save_pipeline_settings
        cfg = get_pipeline_settings()
        print(f"  get_pipeline_settings OK: {len(cfg)} keys; "
              f"core present: {[k for k in ('stage_flows','deal_categories','product_catalogue','stages') if k in cfg]}")
        print(f"  product_flows: {len(cfg.get('product_flows', {}))}")
        # simulate the upsert read-modify-write with a throwaway product
        cfg2 = dict(cfg)
        flows = dict(cfg2.get("product_flows", {}) or {})
        flows["__DIAG_PROBE__"] = {"client_types": [], "stages": [{"stage": "Lead", "target_days": 2}]}
        cfg2["product_flows"] = flows
        save_pipeline_settings(cfg2)
        print("  save_pipeline_settings OK (probe flow written)")
        # clean up the probe
        cfg3 = get_pipeline_settings()
        f3 = dict(cfg3.get("product_flows", {}))
        f3.pop("__DIAG_PROBE__", None)
        cfg3["product_flows"] = f3
        save_pipeline_settings(cfg3)
        print("  cleanup OK (probe flow removed)")
        print("\n  => save path is HEALTHY. The 500 is NOT in get/save_pipeline_settings.")
    except Exception:
        print("  REPRODUCED THE FAILURE:")
        traceback.print_exc()

if __name__ == "__main__":
    main()
