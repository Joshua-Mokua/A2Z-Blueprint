"""Add the committee charter under credit_workflow in lms_config.json.

Admin-configurable. Adding this does NOT change behaviour — the committee
only activates when credit_workflow.committee_mode is set to
"committee_voting". Idempotent, backs up, non-destructive.

Roles: CHAIR, CRO, CCO, CFO, HEAD_OF_CREDIT, INDEPENDENT_MEMBER, EXECUTIVE_MEMBER
Voting rules: SIMPLE_MAJORITY, SUPERMAJORITY_TWO_THIRDS, UNANIMOUS, CHAIR_TIEBREAKER

Usage (project root, venv active):  python scripts\add_committee_config.py
"""
import json, shutil, sys
from datetime import datetime
from pathlib import Path

COMMITTEE = {
    "refer_above_kes": 100000000,
    "voting_rule": "SIMPLE_MAJORITY",
    "min_quorum_count": 3,
    "authority_limit_kes": 500000000,
    "independent_member_min": 1,
    "required_roles": ["CRO"],
    "committee_id": "MCC",
    "name": "Management Credit Committee",
    "members": [
        {"member_id": "m1", "name": "Committee Chair", "role": "CHAIR", "is_independent": False},
        {"member_id": "m2", "name": "Chief Risk Officer", "role": "CRO", "is_independent": False},
        {"member_id": "m3", "name": "Chief Credit Officer", "role": "CCO", "is_independent": False},
        {"member_id": "m4", "name": "Independent Member 1", "role": "INDEPENDENT_MEMBER", "is_independent": True},
        {"member_id": "m5", "name": "Independent Member 2", "role": "INDEPENDENT_MEMBER", "is_independent": True},
    ],
}

p = Path(__file__).resolve().parent.parent / "data" / "lms_config.json"
s = json.loads(p.read_text(encoding="utf-8"))
cw = s.get("credit_workflow")
if not isinstance(cw, dict):
    print("credit_workflow section missing — run add_credit_workflow.py first.")
    sys.exit(1)
if cw.get("committee"):
    print("committee config already present — no change. Edit it in admin config.")
else:
    shutil.copy2(p, p.with_suffix(f".json.bak-{datetime.now():%Y%m%d-%H%M%S}"))
    cw["committee"] = COMMITTEE
    s["credit_workflow"] = cw
    p.write_text(json.dumps(s, indent=2), encoding="utf-8")
    print("Added committee charter (MCC, 5 members, simple majority, quorum 3).")
    print("NOTE: set credit_workflow.committee_mode = 'committee_voting' to activate.")
