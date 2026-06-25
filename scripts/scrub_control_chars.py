#!/usr/bin/env python3
"""scripts/scrub_control_chars.py — remove illegal control characters from deal
text fields in pipeline_deals.json. These rows were created by the Phase 3
input-robustness probe BEFORE the validator was hardened; they break the xlsx
export (openpyxl rejects control chars). The export now scrubs at read-time too,
so this is cleanup, not a hard requirement. Dry-run by default; backs up.
    python scripts/scrub_control_chars.py [--apply]
"""
from __future__ import annotations
import argparse, json, os, re, shutil
from datetime import datetime
ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
TEXT_FIELDS = ("client_name", "product_type", "staff_name", "unit",
               "next_action", "referral_note", "client_type")
PATH = os.path.join("data", "pipeline_deals.json")
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(PATH):
        print(f"FATAL: {PATH} not found"); return
    deals = json.loads(open(PATH, encoding="utf-8").read())
    if not isinstance(deals, list):
        print(f"FATAL: {PATH} is not a list"); return
    hits = []
    for d in deals:
        if not isinstance(d, dict): continue
        for f in TEXT_FIELDS:
            v = d.get(f)
            if isinstance(v, str) and ILLEGAL.search(v):
                hits.append((d.get("id", "?"), f, repr(v)[:50]))
                if args.apply: d[f] = ILLEGAL.sub("", v)
    print(f"{PATH}: {len(deals)} deals scanned; {len(hits)} field(s) with control chars")
    for did, f, sample in hits[:20]:
        print(f"  {did}: {f} = {sample}")
    if not hits:
        print("Nothing to scrub."); return
    if not args.apply:
        print("\n[DRY-RUN] No file written. Re-run with --apply."); return
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = f"{PATH}.pre_scrub_{ts}"; shutil.copy2(PATH, bak)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(deals, fh, ensure_ascii=False, indent=2); fh.flush(); os.fsync(fh.fileno())
    os.replace(tmp, PATH)
    print(f"\nScrubbed {len(hits)} field(s). Backup: {bak}. Restart API.")
if __name__ == "__main__":
    main()
