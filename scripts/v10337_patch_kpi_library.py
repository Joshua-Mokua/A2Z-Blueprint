"""
v10.337 — Patch kpi_library.json, bank_targets.json, role_default_targets.json

  1. Add 5 new canonical KPIs (ACCOUNT_OPENING_TAT,
     COMPLAINT_RESOLUTION_RATE, PIPELINE_DEALS_WON,
     PIPELINE_CONVERSION_RATE, NEW_CUSTOMERS_ACQUIRED)
  2. Migrate role_kpis K→canonical for 6 retail branch roles
     (CSO + BB / PB / BRM / BSRO / DSR)
  3. Add bank_targets entries
  4. Add role_default_targets for per-role quarterly fallbacks

Idempotent — re-running does not duplicate entries.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LIB_PATH = ROOT / "data" / "kpi_library.json"
TARGETS_PATH = ROOT / "data" / "bank_targets.json"
ROLE_DEFAULTS_PATH = ROOT / "data" / "role_default_targets.json"

NEW_KPIS = [
    {
        "id": "ACCOUNT_OPENING_TAT",
        "code": "ACCOUNT_OPENING_TAT",
        "name": "Account Opening TAT",
        "pillar": "Process",
        "weight": 0.05,
        "unit": "hours",
        "direction": "lower",
        "active": True,
        "description": "Median hours from KYC submission to account live. CSO-owned operational quality metric.",
        "_origin": "v10.337_branch_staff_canonical",
    },
    {
        "id": "COMPLAINT_RESOLUTION_RATE",
        "code": "COMPLAINT_RESOLUTION_RATE",
        "name": "Complaint Resolution Rate",
        "pillar": "Customer Focus",
        "weight": 0.06,
        "unit": "%",
        "direction": "higher",
        "active": True,
        "description": "% of customer complaints resolved within SLA. Replaces K008.",
        "_origin": "v10.337_branch_staff_canonical",
    },
    {
        "id": "PIPELINE_DEALS_WON",
        "code": "PIPELINE_DEALS_WON",
        "name": "Pipeline Deals Won",
        "pillar": "Financial",
        "weight": 0.06,
        "unit": "count",
        "direction": "higher",
        "active": True,
        "description": "Count of pipeline deals reaching won stages (Disbursed / Closed Won / Signed / Documentation) per quarter. Sourced from pipeline_activity_bridge.",
        "_origin": "v10.337_branch_staff_canonical",
    },
    {
        "id": "PIPELINE_CONVERSION_RATE",
        "code": "PIPELINE_CONVERSION_RATE",
        "name": "Pipeline Conversion Rate",
        "pillar": "Financial",
        "weight": 0.05,
        "unit": "%",
        "direction": "higher",
        "active": True,
        "description": "Won / (won + lost + active) × 100. Sales effectiveness. Replaces K020.",
        "_origin": "v10.337_branch_staff_canonical",
    },
    {
        "id": "NEW_CUSTOMERS_ACQUIRED",
        "code": "NEW_CUSTOMERS_ACQUIRED",
        "name": "New Customers Acquired",
        "pillar": "Customer Focus",
        "weight": 0.06,
        "unit": "count",
        "direction": "higher",
        "active": True,
        "description": "Distinct customers from won pipeline deals per quarter. Sourced from pipeline_activity_bridge OR estimated by branch_staff_generator for staff not active in pipeline.",
        "_origin": "v10.337_branch_staff_canonical",
    },
]

# CSO + 5 branch sales roles
ROLE_KPI_MIGRATION = {
    "Customer Service Officer": [
        "NEW_ACCOUNTS",
        "ACCOUNT_OPENING_TAT",
        "COMPLAINT_RESOLUTION_RATE",
        "Account Dormancy",
        "CX Score",
        "COMPLIANCE_SCORE",
        "Staff Productivity",
    ],
    "Relationship Officer-Business Banker": [
        "Disbursements MSME Loans",
        "Total NFI",
        "PIPELINE_DEALS_WON",
        "PIPELINE_CONVERSION_RATE",
        "NEW_CUSTOMERS_ACQUIRED",
        "CX Score",
        "COMPLIANCE_SCORE",
        "Audit Score",
        "Staff Productivity",
    ],
    "Relationship Officer-Personal Banker": [
        "Disbursements Retail Loans",
        "Total NFI",
        "Retail & MSME Deposit Growth",
        "PIPELINE_DEALS_WON",
        "PIPELINE_CONVERSION_RATE",
        "NEW_CUSTOMERS_ACQUIRED",
        "CX Score",
        "COMPLIANCE_SCORE",
        "Audit Score",
        "Staff Productivity",
    ],
    "Branch Relationship Manager": [
        "Disbursements Retail Loans",
        "Disbursements MSME Loans",
        "Total NFI",
        "PIPELINE_DEALS_WON",
        "PIPELINE_CONVERSION_RATE",
        "NEW_CUSTOMERS_ACQUIRED",
        "Number of Business Borrowers",
        "CX Score",
        "COMPLIANCE_SCORE",
        "Audit Score",
        "Staff Productivity",
    ],
    "Branch Senior Relationship Officer": [
        "Disbursements Retail Loans",
        "Disbursements MSME Loans",
        "Total NFI",
        "PIPELINE_DEALS_WON",
        "PIPELINE_CONVERSION_RATE",
        "NEW_CUSTOMERS_ACQUIRED",
        "Number of Business Borrowers",
        "CX Score",
        "COMPLIANCE_SCORE",
        "Audit Score",
        "Staff Productivity",
    ],
    "Direct Sales Representative - Assets & Liabilities": [
        "Disbursements Retail Loans",
        "Total NFI",
        "Retail & MSME Deposit Growth",
        "PIPELINE_DEALS_WON",
        "PIPELINE_CONVERSION_RATE",
        "NEW_CUSTOMERS_ACQUIRED",
        "CX Score",
        "COMPLIANCE_SCORE",
        "Audit Score",
        "Staff Productivity",
    ],
}

NEW_BANK_TARGETS = {
    "ACCOUNT_OPENING_TAT|2025": 4.0,
    "ACCOUNT_OPENING_TAT|2026": 3.5,
    "COMPLAINT_RESOLUTION_RATE|2025": 90.0,
    "COMPLAINT_RESOLUTION_RATE|2026": 95.0,
    "PIPELINE_DEALS_WON|2025": 8,        # quarterly target per branch staff
    "PIPELINE_DEALS_WON|2026": 10,
    "PIPELINE_CONVERSION_RATE|2025": 35.0,
    "PIPELINE_CONVERSION_RATE|2026": 40.0,
    "NEW_CUSTOMERS_ACQUIRED|2025": 25,   # quarterly target per branch staff
    "NEW_CUSTOMERS_ACQUIRED|2026": 30,
}

# Per-role per-KPI quarterly targets — feeds the cascading-target lookup
ROLE_DEFAULT_TARGETS_ADDITIONS = {
    "Customer Service Officer": {
        "NEW_ACCOUNTS": {"quarterly": 75},
        "ACCOUNT_OPENING_TAT": {"quarterly": 4},
        "COMPLAINT_RESOLUTION_RATE": {"quarterly": 92},
    },
    "Relationship Officer-Business Banker": {
        "PIPELINE_DEALS_WON": {"quarterly": 8},
        "PIPELINE_CONVERSION_RATE": {"quarterly": 35},
        "NEW_CUSTOMERS_ACQUIRED": {"quarterly": 22},
    },
    "Relationship Officer-Personal Banker": {
        "PIPELINE_DEALS_WON": {"quarterly": 12},
        "PIPELINE_CONVERSION_RATE": {"quarterly": 38},
        "NEW_CUSTOMERS_ACQUIRED": {"quarterly": 30},
    },
    "Branch Relationship Manager": {
        "PIPELINE_DEALS_WON": {"quarterly": 6},
        "PIPELINE_CONVERSION_RATE": {"quarterly": 35},
        "NEW_CUSTOMERS_ACQUIRED": {"quarterly": 18},
    },
    "Branch Senior Relationship Officer": {
        "PIPELINE_DEALS_WON": {"quarterly": 10},
        "PIPELINE_CONVERSION_RATE": {"quarterly": 38},
        "NEW_CUSTOMERS_ACQUIRED": {"quarterly": 25},
    },
    "Direct Sales Representative - Assets & Liabilities": {
        "PIPELINE_DEALS_WON": {"quarterly": 15},
        "PIPELINE_CONVERSION_RATE": {"quarterly": 32},
        "NEW_CUSTOMERS_ACQUIRED": {"quarterly": 40},
    },
}


def apply():
    from utils.db import db as _db

    # ── KPI library ──────────────────────────────────────────────────
    lib = _db.load_json(LIB_PATH, default={}) or {}
    backup = LIB_PATH.with_suffix(".json.v10337.bak")
    if not backup.exists():
        _db.save_json(backup, lib)

    existing_ids = {
        k["id"] for k in lib.get("kpis", []) if isinstance(k, dict) and "id" in k
    }
    added_kpis = []
    for new_kpi in NEW_KPIS:
        if new_kpi["id"] in existing_ids:
            continue
        lib["kpis"].append(new_kpi)
        added_kpis.append(new_kpi["id"])

    previous_role_kpis = {}
    for role in ROLE_KPI_MIGRATION:
        prev = lib.get("role_kpis", {}).get(role, [])
        if prev:
            previous_role_kpis[role] = list(prev)

    lib.setdefault("role_kpis", {})
    for role, canonical_list in ROLE_KPI_MIGRATION.items():
        lib["role_kpis"][role] = list(canonical_list)

    lib["_v10337_branch_staff_canonical_migration"] = {
        "shipped": "v10.337",
        "ts": datetime.now(timezone.utc).isoformat(),
        "roles_migrated": list(ROLE_KPI_MIGRATION.keys()),
        "previous_kpis": previous_role_kpis,
        "rationale": (
            "6 retail branch roles migrated from K-coded role_kpis to "
            "canonical names. CSO gets a full service scorecard from "
            "branch_staff_generator. 5 sales roles get a split scorecard: "
            "operational KPIs from branch_staff_generator, sales/pipeline "
            "KPIs from pipeline_to_bsc (existing) + pipeline_activity_bridge "
            "(new in v10.337)."
        ),
    }
    lib["_v10337_branch_staff_kpis_added"] = {
        "added": added_kpis,
        "ts": datetime.now(timezone.utc).isoformat(),
        "rationale": (
            "5 new canonical KPIs for branch staff scorecards: "
            "ACCOUNT_OPENING_TAT + COMPLAINT_RESOLUTION_RATE (CSO operational "
            "quality); PIPELINE_DEALS_WON + PIPELINE_CONVERSION_RATE + "
            "NEW_CUSTOMERS_ACQUIRED (sales activity from pipeline_activity_bridge)."
        ),
    }

    _db.save_json(LIB_PATH, lib)
    print(
        f"  kpi_library: +{len(added_kpis)} canonical KPIs, "
        f"+{len(ROLE_KPI_MIGRATION)} role_kpi migrations"
    )

    # ── bank_targets ─────────────────────────────────────────────────
    targets = _db.load_json(TARGETS_PATH, default={}) or {}
    added_tgts = 0
    for key, val in NEW_BANK_TARGETS.items():
        if key not in targets:
            targets[key] = val
            added_tgts += 1
    _db.save_json(TARGETS_PATH, targets)
    print(f"  bank_targets: +{added_tgts} entries")

    # ── role_default_targets ─────────────────────────────────────────
    defaults = _db.load_json(ROLE_DEFAULTS_PATH, default={}) or {}
    added_defaults = 0
    for role, kpis in ROLE_DEFAULT_TARGETS_ADDITIONS.items():
        defaults.setdefault(role, {})
        for kpi_id, target_spec in kpis.items():
            if kpi_id not in defaults[role]:
                defaults[role][kpi_id] = target_spec
                added_defaults += 1
    _db.save_json(ROLE_DEFAULTS_PATH, defaults)
    print(f"  role_default_targets: +{added_defaults} entries")


if __name__ == "__main__":
    apply()
    print("\nv10.337 KPI library + bank_targets + role_default_targets patched.")
