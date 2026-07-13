#!/usr/bin/env python3
"""Clear ALL pipeline deals + LMS applications for a clean testing slate.
Backs up each file first (.pre_clear_*). Preserves the container type.
Usage: python scripts/clear_deals.py --yes   (then restart uvicorn)."""
import json, os, sys, shutil
from datetime import datetime

FILES = ["pipeline_deals.json", "loan_applications.json"]

def data_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    for c in [os.path.join(here, "..", "data"), os.path.join(os.getcwd(), "data")]:
        if os.path.isdir(c):
            return os.path.abspath(c)
    return None

def main():
    d = data_dir()
    if not d:
        print("data/ not found"); sys.exit(1)
    if "--yes" not in sys.argv:
        print("This clears ALL deals + LMS applications (backups kept).")
        print("Re-run with --yes to confirm:  python scripts/clear_deals.py --yes")
        return
    for fname in FILES:
        p = os.path.join(d, fname)
        if not os.path.exists(p):
            print(f"  (absent) {fname}"); continue
        try:
            existing = json.load(open(p, encoding="utf-8"))
            empty = {} if isinstance(existing, dict) else []
        except Exception:
            empty = []
        shutil.copyfile(p, p + f".pre_clear_{datetime.now():%Y%m%d-%H%M%S}")
        json.dump(empty, open(p, "w", encoding="utf-8"))
        print(f"  cleared {fname}  (backup kept)")
    print("\nDone. Restart uvicorn. If deals are DB-backed in your env, also")
    print("truncate the pipeline_deals / loan_applications tables.")

if __name__ == "__main__":
    main()
