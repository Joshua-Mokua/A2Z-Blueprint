#!/usr/bin/env python3
"""Seed the bank's consumer-lending documents into the Required-documents
PICKER (Administration -> Configuration -> Products & Flows).

IMPORTANT: the picker is fed by /api/admin/document-catalog, which flattens
`lms_config.json -> document_checklist` (its tiers) — NOT pipeline_settings.json.
So this writes the documents into a dedicated `consumer_lending` tier there.

Additive + idempotent (only adds missing names; never removes existing tiers or
documents). Writes a timestamped backup of lms_config.json before any change.

Usage (from the repo root, venv active):
    python scripts/seed_bank_documents.py --dry-run
    python scripts/seed_bank_documents.py --apply

After --apply, restart uvicorn so the API reloads the config.
"""
from __future__ import annotations
import argparse
import datetime as _dt
import json
import os
import sys
import tempfile

TIER = "consumer_lending"

BANK_DOCUMENTS = [
    "Duly Filled & Signed Loan Application Form",
    "3 Months' Payslips",
    "Letter of Introduction (Employer)",
    "Scheme / Check-off Letter",
    "Loan Repayment Schedule (Signed)",
    "Total Cost of Credit Disclosure (Signed)",
    "Letter of Offer (Executed)",
    "Call-Back Memo",
    "Transaction Memo",
]


def _find_config() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    for cand in (
        os.path.join(root, "data", "lms_config.json"),
        os.path.join(root, "a2z", "data", "lms_config.json"),
        os.path.join(root, "lms_config.json"),
    ):
        if os.path.exists(cand):
            return cand
    print("ERROR: could not locate lms_config.json", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.apply and not args.dry_run:
        args.dry_run = True

    path = _find_config()
    with open(path, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    if not isinstance(cfg, dict):
        print("ERROR: lms_config.json is not an object", file=sys.stderr)
        sys.exit(2)

    dc = cfg.get("document_checklist")
    if not isinstance(dc, dict):
        dc = {}

    existing = set()
    for _tier, items in dc.items():
        if isinstance(items, list):
            for d in items:
                if isinstance(d, str) and d.strip():
                    existing.add(d.strip().lower())

    tier_items = list(dc.get(TIER, []) or [])
    tier_existing = {str(x).strip().lower() for x in tier_items if str(x).strip()}

    to_add = [d for d in BANK_DOCUMENTS
              if d.strip().lower() not in existing and d.strip().lower() not in tier_existing]

    print(f"config file  : {path}")
    print(f"tier         : document_checklist['{TIER}'] ({len(tier_items)} item(s))")
    if not to_add:
        print("Nothing to add — all bank documents already in the catalogue.")
        return
    print(f"would add    : {len(to_add)} document(s):")
    for d in to_add:
        print(f"  + {d}")

    if args.dry_run:
        print("\n[DRY-RUN] no changes written. Re-run with --apply.")
        return

    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{path}.pre_{ts}"
    with open(bak, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    print(f"backup       : {bak}")

    tier_items.extend(to_add)
    dc[TIER] = tier_items
    cfg["document_checklist"] = dc

    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print(f"applied: added {len(to_add)} document(s) to the '{TIER}' tier. Restart uvicorn.")


if __name__ == "__main__":
    main()
