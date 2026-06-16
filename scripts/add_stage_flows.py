"""Add per-product-class stage_flows to pipeline_settings.json.

Admin config is the single source of truth for the loan / deposit / insurance /
other stage flows. Idempotent + backs up first + non-destructive (won't
overwrite if you've already customised stage_flows in admin).

Usage (project root, venv active):  python scripts\add_stage_flows.py
"""
import json, shutil
from datetime import datetime
from pathlib import Path

STAGE_FLOWS = {
    "asset":     ["Lead", "Contacted", "Qualified", "Application",
                  "Credit Assessment", "Offer / Proposal", "Negotiation",
                  "Compliance", "Closed Won", "Closed Lost"],
    "liability": ["Lead", "Contacted", "Proposal", "Negotiation",
                  "Documentation", "Closed Won", "Closed Lost"],
    "insurance": ["Lead", "Contacted", "Proposal", "Negotiation",
                  "Documentation", "Closed Won", "Closed Lost"],
    "other":     ["Lead", "Contacted", "Qualified", "Proposal", "Negotiation",
                  "Closed Won", "Closed Lost"],
}

p = Path(__file__).resolve().parent.parent / "data" / "pipeline_settings.json"
s = json.loads(p.read_text(encoding="utf-8"))
if s.get("stage_flows"):
    print("stage_flows already present — no change. Customise it in admin config.")
else:
    shutil.copy2(p, p.with_suffix(f".json.bak-{datetime.now():%Y%m%d-%H%M%S}"))
    s["stage_flows"] = STAGE_FLOWS
    p.write_text(json.dumps(s, indent=2), encoding="utf-8")
    print("Added stage_flows (per product class):")
    for k, v in STAGE_FLOWS.items():
        print(f"  {k:<10} {' -> '.join(v)}")
