#!/usr/bin/env python3
"""Seed the document catalogue with the bank's consumer-lending checklist
documents, so they are tickable as required documents at product-flow creation
(Administration -> Configuration -> Products & Flows).

This ONLY adds names that are missing — it never removes or renames existing
catalogue entries, and it is idempotent (safe to re-run). A timestamped backup
of pipeline_settings.json is written before any change.

Usage (from the repo root, with the venv active):
    python scripts/seed_bank_documents.py --dry-run
    python scripts/seed_bank_documents.py --apply

After --apply, restart uvicorn so the API reloads the settings.
"""
from __future__ import annotations
import argparse
import datetime as _dt
import json
import os
import sys
import tempfile

# Documents the bank uses for consumer salary-backed / check-off facilities.
# Add/trim this list as the bank confirms; re-running only adds what's missing.
BANK_DOCUMENTS = [
    "Duly Filled & Signed Loan Application Form",
    "3 Months' Payslips",
    "Letter of Introduction (Employer)",
    "Scheme / Check-off Letter",
    "CRB Report",
    "Bank Statements (6 Months)",
    "Copy of National ID / Passport",
    "KRA PIN Certificate",
    "Loan Repayment Schedule (Signed)",
    "Total Cost of Credit Disclosure (Signed)",
    "Letter of Offer (Executed)",
    "Call-Back Memo",
    "Transaction Memo",
]


def _find_settings() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    for cand in (
        os.path.join(root, "data", "pipeline_settings.json"),
        os.path.join(root, "a2z", "data", "pipeline_settings.json"),
        os.path.join(root, "pipeline_settings.json"),
    ):
        if os.path.exists(cand):
            return cand
    print("ERROR: could not locate pipeline_settings.json", file=sys.stderr)
    sys.exit(2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the changes")
    ap.add_argument("--dry-run", action="store_true", help="show what would change")
    args = ap.parse_args()
    if not args.apply and not args.dry_run:
        args.dry_run = True

    path = _find_settings()
    with open(path, "r", encoding="utf-8") as fh:
        settings = json.load(fh)
    if not isinstance(settings, dict):
        print("ERROR: pipeline_settings.json is not an object", file=sys.stderr)
        sys.exit(2)

    dcat = settings.get("document_catalogue")
    if not isinstance(dcat, dict):
        dcat = {}
    docs = list(dcat.get("documents", []) or [])

    def _name(d):
        return str(d.get("name", "") if isinstance(d, dict) else d).strip()

    existing = {_name(d).lower() for d in docs if _name(d)}

    to_add = [d for d in BANK_DOCUMENTS if d.strip().lower() not in existing]
    print(f"settings file : {path}")
    print(f"catalogue now : {len(docs)} document(s)")
    if not to_add:
        print("Nothing to add — all bank documents already present.")
        return
    print(f"would add     : {len(to_add)} document(s):")
    for d in to_add:
        print(f"  + {d}")

    if args.dry_run:
        print("\n[DRY-RUN] no changes written. Re-run with --apply to write.")
        return

    # backup
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{path}.pre_{ts}"
    with open(bak, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, ensure_ascii=False, indent=2)
    print(f"backup written: {bak}")

    for d in to_add:
        docs.append({"name": d})
    dcat["documents"] = docs
    settings["document_catalogue"] = dcat

    # atomic write
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    print(f"applied: added {len(to_add)} document(s). Restart uvicorn to reload.")


if __name__ == "__main__":
    main()
