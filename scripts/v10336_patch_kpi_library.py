"""
v10.336 — Patch kpi_library.json and bank_targets.json

  1. Add 11 new canonical KPIs (Treasury 4 + TF 3 + Marketing 4)
  2. Migrate role_kpis K→canonical for 13 specialist roles
     (mirrors v10.324 + v10.328 + v10.334 pattern)
  3. Add bank_targets entries (Q3'25/Q4'25 mirrors of 2026 per v10.322
     multi-period pattern)
  4. Tag everything with _v10336_specialist_canonical_migration

Idempotent: re-running this script does not duplicate entries.
"""
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
LIB_PATH = ROOT / "data" / "kpi_library.json"
TARGETS_PATH = ROOT / "data" / "bank_targets.json"
ROLE_DEFAULTS_PATH = ROOT / "data" / "role_default_targets.json"

# ────────────────────────────────────────────────────────────────────
# Step 1 — Canonical KPI definitions
# ────────────────────────────────────────────────────────────────────

NEW_KPIS = [
    # Treasury — 4 new KPIs
    {
        "id": "LIQUIDITY_COVERAGE_RATIO",
        "code": "LIQUIDITY_COVERAGE_RATIO",
        "name": "Liquidity Coverage Ratio",
        "pillar": "Risk",
        "weight": 0.08,
        "unit": "%",
        "direction": "higher",
        "active": True,
        "description": "BCBS d295 LCR — HQLA / 30-day net cash outflows. Regulatory minimum 100%. Treasury-owned.",
        "_origin": "v10.336_specialist_canonical",
    },
    {
        "id": "NET_STABLE_FUNDING_RATIO",
        "code": "NET_STABLE_FUNDING_RATIO",
        "name": "Net Stable Funding Ratio",
        "pillar": "Risk",
        "weight": 0.06,
        "unit": "%",
        "direction": "higher",
        "active": True,
        "description": "BCBS d295 NSFR — Available stable funding / required stable funding. Regulatory minimum 100%.",
        "_origin": "v10.336_specialist_canonical",
    },
    {
        "id": "NET_INTEREST_MARGIN",
        "code": "NET_INTEREST_MARGIN",
        "name": "Net Interest Margin",
        "pillar": "Financial",
        "weight": 0.10,
        "unit": "%",
        "direction": "higher",
        "active": True,
        "description": "Net interest income / average earning assets. Core Treasury profitability driver.",
        "_origin": "v10.336_specialist_canonical",
    },
    {
        "id": "FX_TRADING_INCOME",
        "code": "FX_TRADING_INCOME",
        "name": "FX Trading Income",
        "pillar": "Financial",
        "weight": 0.08,
        "unit": "CCY_M",
        "direction": "higher",
        "active": True,
        "description": "Foreign exchange trading revenue — dealer P&L plus corporate FX spread. Treasury-owned.",
        "_origin": "v10.336_specialist_canonical",
    },
    # Trade Finance — 3 new KPIs
    {
        "id": "TRADE_FINANCE_REVENUE",
        "code": "TRADE_FINANCE_REVENUE",
        "name": "Trade Finance Revenue",
        "pillar": "Financial",
        "weight": 0.10,
        "unit": "CCY_M",
        "direction": "higher",
        "active": True,
        "description": "Total revenue from trade finance instruments (LC, guarantees, collections, supplier finance). Replaces K022.",
        "_origin": "v10.336_specialist_canonical",
    },
    {
        "id": "TRADE_DOC_TAT",
        "code": "TRADE_DOC_TAT",
        "name": "Trade Document Check TAT",
        "pillar": "Process",
        "weight": 0.05,
        "unit": "hours",
        "direction": "lower",
        "active": True,
        "description": "Average hours from document receipt to discrepancy decision. ICC UCP 600 §14 mandates within 5 banking days; operational target far tighter.",
        "_origin": "v10.336_specialist_canonical",
    },
    {
        "id": "LC_VOLUME",
        "code": "LC_VOLUME",
        "name": "Letters of Credit — Volume",
        "pillar": "Financial",
        "weight": 0.05,
        "unit": "count",
        "direction": "higher",
        "active": True,
        "description": "Number of LCs issued in the period. Volume proxy for trade finance market share.",
        "_origin": "v10.336_specialist_canonical",
    },
    # Marketing — 4 new KPIs
    {
        "id": "CAMPAIGN_ROI",
        "code": "CAMPAIGN_ROI",
        "name": "Campaign ROI",
        "pillar": "Customer Focus",
        "weight": 0.08,
        "unit": "%",
        "direction": "higher",
        "active": True,
        "description": "Marketing-attributable revenue / campaign spend, expressed as %. Marketing-owned.",
        "_origin": "v10.336_specialist_canonical",
    },
    {
        "id": "BRAND_AWARENESS",
        "code": "BRAND_AWARENESS",
        "name": "Brand Awareness",
        "pillar": "Customer Focus",
        "weight": 0.05,
        "unit": "%",
        "direction": "higher",
        "active": True,
        "description": "Unaided brand recall in target segment, survey-based.",
        "_origin": "v10.336_specialist_canonical",
    },
    {
        "id": "MARKETING_QUALIFIED_LEADS",
        "code": "MARKETING_QUALIFIED_LEADS",
        "name": "Marketing-Qualified Leads",
        "pillar": "Customer Focus",
        "weight": 0.05,
        "unit": "count",
        "direction": "higher",
        "active": True,
        "description": "Leads passed to sales pipeline meeting MQL criteria. Feeds pipeline_to_bsc downstream.",
        "_origin": "v10.336_specialist_canonical",
    },
    {
        "id": "MARKETING_DRIVEN_REVENUE",
        "code": "MARKETING_DRIVEN_REVENUE",
        "name": "Marketing-Driven Revenue",
        "pillar": "Financial",
        "weight": 0.08,
        "unit": "CCY_M",
        "direction": "higher",
        "active": True,
        "description": "Revenue attributable to marketing-sourced leads (UTM + first-touch attribution).",
        "_origin": "v10.336_specialist_canonical",
    },
]

# ────────────────────────────────────────────────────────────────────
# Step 2 — role_kpi migration (K-codes → canonical names)
# ────────────────────────────────────────────────────────────────────

ROLE_KPI_MIGRATION = {
    # Treasury roles
    "Senior Manager Treasury": [
        "LIQUIDITY_COVERAGE_RATIO",
        "NET_STABLE_FUNDING_RATIO",
        "NET_INTEREST_MARGIN",
        "FX_TRADING_INCOME",
        "Total NFI",
        "Audit Score",
        "COMPLIANCE_SCORE",
    ],
    "Manager Forex Trader": [
        "FX_TRADING_INCOME",
        "NET_INTEREST_MARGIN",
        "Total NFI",
        "Audit Score",
        "COMPLIANCE_SCORE",
    ],
    "Corporate Sales Dealer": [
        "FX_TRADING_INCOME",
        "Total NFI",
        "CX Score",
        "Audit Score",
        "COMPLIANCE_SCORE",
    ],
    "Treasury Dealer": [
        "FX_TRADING_INCOME",
        "NET_INTEREST_MARGIN",
        "Total NFI",
        "Audit Score",
        "COMPLIANCE_SCORE",
    ],
    "Treasury Front Office Officer": [
        "FX_TRADING_INCOME",
        "Total NFI",
        "Audit Score",
        "COMPLIANCE_SCORE",
        "Staff Productivity",
    ],
    # Trade Finance specialist roles
    "Trade Finance Back Office Manager": [
        "TRADE_FINANCE_REVENUE",
        "TRADE_DOC_TAT",
        "LC_VOLUME",
        "Total NFI",
        "Audit Score",
        "COMPLIANCE_SCORE",
    ],
    "Senior Trade Finance Officer": [
        "TRADE_FINANCE_REVENUE",
        "TRADE_DOC_TAT",
        "LC_VOLUME",
        "Total NFI",
        "Audit Score",
        "COMPLIANCE_SCORE",
    ],
    "Trade Finance Officer": [
        "TRADE_FINANCE_REVENUE",
        "TRADE_DOC_TAT",
        "LC_VOLUME",
        "Total NFI",
        "Audit Score",
        "COMPLIANCE_SCORE",
    ],
    "Trade Finance Operations Officer": [
        "TRADE_DOC_TAT",
        "LC_VOLUME",
        "Total NFI",
        "Audit Score",
        "COMPLIANCE_SCORE",
        "Staff Productivity",
    ],
    "Senior Relationship Manager-Trade Finance Specialist": [
        "TRADE_FINANCE_REVENUE",
        "LC_VOLUME",
        "Total NFI",
        "Number of Business Borrowers",
        "CX Score",
        "Audit Score",
        "COMPLIANCE_SCORE",
    ],
    # Marketing roles
    "Head Of Marketing and Corporate Communication": [
        "CAMPAIGN_ROI",
        "BRAND_AWARENESS",
        "MARKETING_QUALIFIED_LEADS",
        "MARKETING_DRIVEN_REVENUE",
        "CX Score",
        "Audit Score",
        "Staff Productivity",
    ],
    "Marketing Assistant Manager": [
        "CAMPAIGN_ROI",
        "MARKETING_QUALIFIED_LEADS",
        "MARKETING_DRIVEN_REVENUE",
        "CX Score",
        "Audit Score",
        "Staff Productivity",
    ],
    "Marketing Officer": [
        "CAMPAIGN_ROI",
        "MARKETING_QUALIFIED_LEADS",
        "MARKETING_DRIVEN_REVENUE",
        "CX Score",
        "Audit Score",
        "Staff Productivity",
    ],
}

# ────────────────────────────────────────────────────────────────────
# Step 3 — bank_targets entries (KPI|YYYY → target value)
# ────────────────────────────────────────────────────────────────────

NEW_BANK_TARGETS = {
    # Treasury — annual targets
    "LIQUIDITY_COVERAGE_RATIO|2025": 130.0,
    "LIQUIDITY_COVERAGE_RATIO|2026": 135.0,
    "NET_STABLE_FUNDING_RATIO|2025": 115.0,
    "NET_STABLE_FUNDING_RATIO|2026": 120.0,
    "NET_INTEREST_MARGIN|2025": 5.2,
    "NET_INTEREST_MARGIN|2026": 5.5,
    "FX_TRADING_INCOME|2025": 800.0,        # CCY_M annual
    "FX_TRADING_INCOME|2026": 950.0,
    # Trade Finance
    "TRADE_FINANCE_REVENUE|2025": 1400.0,   # CCY_M annual
    "TRADE_FINANCE_REVENUE|2026": 1650.0,
    "TRADE_DOC_TAT|2025": 36.0,             # hours — lower is better
    "TRADE_DOC_TAT|2026": 30.0,
    "LC_VOLUME|2025": 850,                  # count annual
    "LC_VOLUME|2026": 1000,
    # Marketing
    "CAMPAIGN_ROI|2025": 220.0,             # %
    "CAMPAIGN_ROI|2026": 250.0,
    "BRAND_AWARENESS|2025": 70.0,           # %
    "BRAND_AWARENESS|2026": 75.0,
    "MARKETING_QUALIFIED_LEADS|2025": 6500, # count annual
    "MARKETING_QUALIFIED_LEADS|2026": 8000,
    "MARKETING_DRIVEN_REVENUE|2025": 1100.0,# CCY_M annual
    "MARKETING_DRIVEN_REVENUE|2026": 1400.0,
}

# ────────────────────────────────────────────────────────────────────
# Step 4 — role-default targets per quarter (for cascaded-target roles)
# ────────────────────────────────────────────────────────────────────
#
# Quarterly targets (annual / 4). Stored under role_default_targets to
# match the v10.323 pipeline pattern.

ROLE_DEFAULT_TARGETS_ADDITIONS = {
    # The producer submits per-staff actuals; role_default_targets gives the
    # cascading engine a reasonable per-staff quarterly target so achievement_pct
    # is computed sensibly. Values are conservative (slightly below the bank
    # annual / 4, reflecting that individual staff handle a slice).

    # Treasury specialists
    "Senior Manager Treasury": {
        "FX_TRADING_INCOME": {"quarterly": 200_000_000},  # raw
        "NET_INTEREST_MARGIN": {"quarterly": 5.5},
        "LIQUIDITY_COVERAGE_RATIO": {"quarterly": 130},
        "NET_STABLE_FUNDING_RATIO": {"quarterly": 118},
    },
    "Manager Forex Trader": {
        "FX_TRADING_INCOME": {"quarterly": 135_000_000},
        "NET_INTEREST_MARGIN": {"quarterly": 5.3},
    },
    "Corporate Sales Dealer": {
        "FX_TRADING_INCOME": {"quarterly": 90_000_000},
    },
    "Treasury Dealer": {
        "FX_TRADING_INCOME": {"quarterly": 70_000_000},
        "NET_INTEREST_MARGIN": {"quarterly": 5.0},
    },
    "Treasury Front Office Officer": {
        "FX_TRADING_INCOME": {"quarterly": 42_000_000},
    },
    # Trade Finance specialists
    "Trade Finance Back Office Manager": {
        "TRADE_FINANCE_REVENUE": {"quarterly": 360_000_000},
        "TRADE_DOC_TAT": {"quarterly": 28},
        "LC_VOLUME": {"quarterly": 200},
    },
    "Senior Trade Finance Officer": {
        "TRADE_FINANCE_REVENUE": {"quarterly": 165_000_000},
        "TRADE_DOC_TAT": {"quarterly": 30},
        "LC_VOLUME": {"quarterly": 90},
    },
    "Trade Finance Officer": {
        "TRADE_FINANCE_REVENUE": {"quarterly": 90_000_000},
        "TRADE_DOC_TAT": {"quarterly": 32},
        "LC_VOLUME": {"quarterly": 50},
    },
    "Trade Finance Operations Officer": {
        "TRADE_DOC_TAT": {"quarterly": 26},
        "LC_VOLUME": {"quarterly": 70},
    },
    "Relationship Manager- Trade Finance": {
        "TRADE_FINANCE_REVENUE": {"quarterly": 220_000_000},
        "LC_VOLUME": {"quarterly": 75},
    },
    "Senior Relationship Manager-Trade Finance Specialist": {
        "TRADE_FINANCE_REVENUE": {"quarterly": 400_000_000},
        "LC_VOLUME": {"quarterly": 135},
    },
    # Marketing
    "Head Of Marketing and Corporate Communication": {
        "CAMPAIGN_ROI": {"quarterly": 260},
        "BRAND_AWARENESS": {"quarterly": 72},
        "MARKETING_QUALIFIED_LEADS": {"quarterly": 1700},
        "MARKETING_DRIVEN_REVENUE": {"quarterly": 300_000_000},
    },
    "Marketing Assistant Manager": {
        "CAMPAIGN_ROI": {"quarterly": 210},
        "MARKETING_QUALIFIED_LEADS": {"quarterly": 680},
        "MARKETING_DRIVEN_REVENUE": {"quarterly": 110_000_000},
    },
    "Marketing Officer": {
        "CAMPAIGN_ROI": {"quarterly": 160},
        "MARKETING_QUALIFIED_LEADS": {"quarterly": 400},
        "MARKETING_DRIVEN_REVENUE": {"quarterly": 55_000_000},
    },
}


# ────────────────────────────────────────────────────────────────────
# Apply
# ────────────────────────────────────────────────────────────────────

def apply():
    import sys as _sys
    _sys.path.insert(0, str(ROOT))
    from utils.db import db as _db

    # ── KPI library ──────────────────────────────────────────────────
    lib = _db.load_json(LIB_PATH, default={}) or {}
    # Back up via db helper (idempotent)
    if (LIB_PATH.with_suffix(".json.v10336.bak")).exists() is False:
        _db.save_json(LIB_PATH.with_suffix(".json.v10336.bak"), lib)
    existing_ids = {k["id"] for k in lib["kpis"] if isinstance(k, dict) and "id" in k}
    added_kpis = []
    for new_kpi in NEW_KPIS:
        if new_kpi["id"] in existing_ids:
            continue
        lib["kpis"].append(new_kpi)
        added_kpis.append(new_kpi["id"])

    # Capture previous K-coded role_kpis for rollback
    previous_role_kpis = {}
    for role in ROLE_KPI_MIGRATION:
        prev = lib.get("role_kpis", {}).get(role, [])
        if prev:
            previous_role_kpis[role] = list(prev)

    # Apply migration
    lib.setdefault("role_kpis", {})
    for role, canonical_list in ROLE_KPI_MIGRATION.items():
        lib["role_kpis"][role] = list(canonical_list)

    # Tag the migration
    lib["_v10336_specialist_canonical_migration"] = {
        "shipped": "v10.336",
        "ts": datetime.now(timezone.utc).isoformat(),
        "roles_migrated": list(ROLE_KPI_MIGRATION.keys()),
        "previous_kpis": previous_role_kpis,
        "rationale": (
            "Specialist roles migrated from K-coded role_kpis to "
            "canonical names matching specialist_activity_generator output. "
            "Same migration pattern as earlier role_kpi canonicalisation batches."
        ),
    }
    lib["_v10336_specialist_kpis_added"] = {
        "added": added_kpis,
        "ts": datetime.now(timezone.utc).isoformat(),
        "rationale": (
            "Specialist department canonical KPIs — capital/liquidity ratios, "
            "FX trading, trade finance revenue + doc TAT + LC volume, "
            "and marketing campaign ROI + brand + lead generation."
        ),
    }

    _db.save_json(LIB_PATH, lib)
    print(f"  kpi_library: +{len(added_kpis)} canonical KPIs, "
          f"+{len(ROLE_KPI_MIGRATION)} role_kpi migrations")

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
    print("\nv10.336 KPI library + bank_targets + role_default_targets patched.")
