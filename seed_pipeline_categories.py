#!/usr/bin/env python3
"""scripts/seed_pipeline_categories.py — A2a backend: balance-sheet pipeline categories.

Adds the 3 balance-sheet pipeline categories (Loan/Asset, Deposit/Liability,
Insurance) to deal_categories, each carrying:
  - product_class: [productClass...] so the create form filters products correctly
  - surface: "pipeline" so it shows in the create-deal category dropdown
  - stages: a sensible default flow (products override via their own product_flow)

The existing 9 deal-types (New Facility, Renewal, etc.) are marked
surface="dormant" — kept in config for future event/sponsorship tracking, but
hidden from the create-deal category dropdown.

Idempotent. Backup-before-mutation (.pre_catseed_<ts>). --revert restores backup.
"""
import sys, json, shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "data" / "pipeline_settings.json"

# The 3 balance-sheet pipeline categories. product_class maps to the product
# catalogue groups' classes (asset/liability/insurance/other) used by the create
# form's product filter + analytics.
BALANCE_SHEET_CATEGORIES = [
    {
        "category": "Loan / Asset",
        "product_class": ["asset"],
        "surface": "pipeline",
        "description": "Asset-side pipeline — loans and credit facilities.",
        "stages": ["Lead", "Prospecting", "Needs Analysis", "Proposal",
                   "Negotiation", "Credit Review", "Approval",
                   "Documentation", "Disbursed", "Closed Won", "Closed Lost"],
    },
    {
        "category": "Deposit / Liability",
        "product_class": ["liability", "other"],
        "surface": "pipeline",
        "description": "Liability-side pipeline — deposits, accounts, transactional.",
        "stages": ["Lead", "Prospecting", "Needs Analysis", "Proposal",
                   "Negotiation", "Account Opening", "Funded",
                   "Closed Won", "Closed Lost"],
    },
    {
        "category": "Insurance",
        "product_class": ["insurance"],
        "surface": "pipeline",
        "description": "Bancassurance / insurance product pipeline.",
        "stages": ["Lead", "Prospecting", "Needs Analysis", "Quotation",
                   "Proposal", "Negotiation", "Policy Issued",
                   "Closed Won", "Closed Lost"],
    },
]

def revert():
    backups = sorted(CFG.parent.glob("pipeline_settings.pre_catseed_*.json"))
    if not backups:
        print("  no .pre_catseed backup found"); return
    latest = backups[-1]
    shutil.copy2(latest, CFG); print(f"  reverted from {latest.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    dc = cfg.get("deal_categories", [])
    if not isinstance(dc, list):
        dc = []
    existing_names = {c.get("category") for c in dc if isinstance(c, dict)}
    bs_names = {c["category"] for c in BALANCE_SHEET_CATEGORIES}

    # Mark existing non-balance-sheet categories as dormant (kept, hidden).
    dormant_count = 0
    for c in dc:
        if isinstance(c, dict) and c.get("category") not in bs_names:
            if c.get("surface") != "dormant":
                c["surface"] = "dormant"
                dormant_count += 1

    # Add the balance-sheet categories if missing; refresh if present.
    added, refreshed = 0, 0
    by_name = {c.get("category"): c for c in dc if isinstance(c, dict)}
    for bs in BALANCE_SHEET_CATEGORIES:
        if bs["category"] in by_name:
            by_name[bs["category"]].update({
                "product_class": bs["product_class"],
                "surface": "pipeline",
            })
            refreshed += 1
        else:
            dc.append(dict(bs)); added += 1

    cfg["deal_categories"] = dc
    print(f"  balance-sheet categories: +{added} added, {refreshed} refreshed")
    print(f"  existing deal-types marked dormant: {dormant_count}")
    print(f"  total deal_categories now: {len(dc)}")
    if dry:
        print("  --dry-run: nothing written."); return

    backup = CFG.parent / f"pipeline_settings.pre_catseed_{datetime.now():%Y%m%d-%H%M%S}.json"
    backup.write_text(CFG.read_text(encoding="utf-8"), encoding="utf-8")
    # atomic write
    import tempfile, os
    fd, tmp = tempfile.mkstemp(dir=str(CFG.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
        fh.flush(); os.fsync(fh.fileno())
    os.replace(tmp, str(CFG))
    print(f"  written (backup: {backup.name}). Restart API.")

if __name__ == "__main__":
    main()
