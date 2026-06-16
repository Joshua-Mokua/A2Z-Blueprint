"""Add the credit_workflow policy section to lms_config.json.

Admin-configurable credit operating model — each bank picks its own policy
without code changes. Idempotent, backs up first, non-destructive.

  committee_mode:                          authority_tier | committee_voting
  signed_offer_attachment:                 reference | file_upload
  require_line_manager_offer_validation:   bool
  require_analyst_confirmation:            bool
  credit_admin_two_layer_authorization:    bool
  offer_letter:                            { template_label, validity_days, sla_days }

Usage (project root, venv active):  python scripts\add_credit_workflow.py
"""
import json, shutil
from datetime import datetime
from pathlib import Path

POLICY = {
    "committee_mode": "authority_tier",
    "signed_offer_attachment": "reference",
    "require_line_manager_offer_validation": True,
    "require_analyst_confirmation": True,
    "credit_admin_two_layer_authorization": True,
    "offer_letter": {
        "template_label": "Letter of Offer",
        "validity_days": 14,
        "sla_days": 5,
    },
}

p = Path(__file__).resolve().parent.parent / "data" / "lms_config.json"
s = json.loads(p.read_text(encoding="utf-8"))
if s.get("credit_workflow"):
    print("credit_workflow already present — no change. Edit it in admin config.")
else:
    shutil.copy2(p, p.with_suffix(f".json.bak-{datetime.now():%Y%m%d-%H%M%S}"))
    s["credit_workflow"] = POLICY
    p.write_text(json.dumps(s, indent=2), encoding="utf-8")
    print("Added credit_workflow policy:")
    for k, v in POLICY.items():
        print(f"  {k}: {v}")
