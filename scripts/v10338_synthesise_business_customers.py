"""
v10.338 — Business customer dataset synthesis.

The virtual bank's customer_intelligence.json is 100% individual customers
(3,000 records). For SBU drill-down on the Business side (MSME + Corporate
× CBK sector) we need business customer records.

This script takes the 214 distinct business clients already present in
pipeline.json and synthesizes a business customer intelligence file:

  - cif:                  re-using client_cif from pipeline
  - client_name:          re-using from pipeline
  - annual_turnover_kes:  heuristic based on max facility × 5-15 multiplier
  - segment_code:         classify_business(turnover) → MICRO/SMALL/MEDIUM/CORPORATE
  - cbk_sector:           deterministic via keyword match + hash fallback
  - customer_type:        'business'
  - tagged_rm_staff_code: from the most-recent pipeline deal

Deterministic — hash(client_name) drives sector + turnover multiplier so
re-runs produce identical output. Idempotent — running twice does not
duplicate.

KAIZEN principle: every assumption tagged with a `_v10338_synthesis`
metadata entry per record so replacement with real FLEXCUBE data later
is a clean override.
"""

import hashlib
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PIPELINE_PATH = ROOT / "data" / "pipeline.json"
OUT_PATH = ROOT / "data" / "customer_intelligence_business.json"

BIZ_PRODUCTS = {
    "SME Term Loan", "Asset Finance", "SME Working Capital",
    "MSME Working Capital", "Business Loan", "LPO Financing",
    "SME Invoice Discounting", "Invoice Discounting", "Agribusiness Loan",
    "Corporate Loan", "Term Loan Corporate", "Trade Finance LC",
    "Bid Bond", "Performance Bond", "Corporate Bond", "Letter of Credit",
    "Term Loan", "Working Capital Loan", "Bank Guarantee", "Trade Loan",
    "Overdraft Facility", "Import Finance", "Export Finance LC",
    "Documentary Collection", "Seasonal Crop Finance",
    "Diaspora Business Account",
}

# Keyword → CBK sector inference (Joshua's 14 sectors). Falls back to
# hash-distributed assignment when no keyword matches.
SECTOR_KEYWORDS = {
    "Agriculture, Forestry & Fishing": [
        "farm", "tea", "coffee", "sugar", "growers", "cooperative",
        "livestock", "fishing", "agri", "crop",
    ],
    "Mining & Quarrying": ["mining", "quarry", "mineral"],
    "Manufacturing": [
        "mills", "textile", "factory", "manufactur", "industries",
        "industrial", "production",
    ],
    "Electricity, Gas & Water Supply": ["power", "electric", "gas", "water", "energy"],
    "Building & Construction": [
        "construction", "builder", "contractor", "concrete", "steel",
    ],
    "Trade (Wholesale & Retail)": [
        "traders", "wholesale", "retail", "shop", "supplies", "supplier",
    ],
    "Tourism, Restaurant & Hotels": [
        "hotel", "restaurant", "tourism", "tours", "lodge", "safari",
    ],
    "Transport & Communication": [
        "transport", "logistics", "airfield", "shipping", "freight",
        "telecom", "courier",
    ],
    "Real Estate & Business Services": [
        "real estate", "property", "services", "consult", "advisory",
    ],
    "Financial Services": ["sacco", "bank", "credit union", "finance"],
    "Community, Social & Personal Services": [
        "school", "schools", "education", "health", "hospital", "clinic",
        "ngo",
    ],
    "Government & Public Sector": ["county", "government", "public", "ministry"],
    "Non-Profit / NGO": ["foundation", "trust", "ngo", "charity"],
}


def _stable_hash(s: str) -> int:
    return int.from_bytes(
        hashlib.sha256(s.encode("utf-8")).digest()[:8], "big"
    )


def _classify_sector(name: str) -> str:
    n = name.lower()
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(k in n for k in keywords):
            return sector
    # Hash-distributed fallback across the 14 sectors
    sectors = list(SECTOR_KEYWORDS.keys()) + ["Other / Not Classified"]
    return sectors[_stable_hash(name) % len(sectors)]


def apply():
    from utils.db import db as _db
    from utils.segment_classifier import classify_business

    pipeline = _db.load_json(PIPELINE_PATH, default=[]) or []
    if not isinstance(pipeline, list):
        print("  pipeline.json shape unexpected")
        return

    # Aggregate per (client_cif, client_name) → max facility, tagged RM
    by_client = {}
    for d in pipeline:
        if d.get("product") not in BIZ_PRODUCTS:
            continue
        cn = d.get("client_name")
        cif = d.get("client_cif")
        if not cn or not cif:
            continue
        rec = by_client.setdefault(cif, {
            "cif": cif,
            "client_name": cn,
            "max_facility_kes": 0,
            "facility_count": 0,
            "currencies": set(),
            "tagged_rm_staff_code": None,
            "tagged_rm_role": None,
            "deals": [],
        })
        amt = float(d.get("amount", 0) or 0)
        if amt > rec["max_facility_kes"]:
            rec["max_facility_kes"] = amt
            rec["tagged_rm_staff_code"] = d.get("staff_code")
            rec["tagged_rm_role"] = d.get("role")
        rec["facility_count"] += 1
        rec["currencies"].add(d.get("currency") or "KES")
        rec["deals"].append(d.get("id"))

    out = {}
    sector_distribution = defaultdict(int)
    segment_distribution = defaultdict(int)
    ts = datetime.now(timezone.utc).isoformat()

    for cif, agg in by_client.items():
        name = agg["client_name"]
        max_fac = agg["max_facility_kes"]
        h = _stable_hash(name)

        # Deterministic turnover multiplier (5-15x max facility)
        multiplier = 5 + ((h % 1000) / 100.0)
        turnover = round(max_fac * multiplier, 0)

        sector = _classify_sector(name)
        segment_code = classify_business(turnover)

        sector_distribution[sector] += 1
        segment_distribution[segment_code] += 1

        out[cif] = {
            "cif": cif,
            "client_name": name,
            "customer_type": "business",
            "segment_code": segment_code,
            "cbk_sector": sector,
            "annual_turnover_kes": float(turnover),
            "max_facility_kes": float(max_fac),
            "facility_count": agg["facility_count"],
            "currencies": sorted(agg["currencies"]),
            "tagged_rm_staff_code": agg["tagged_rm_staff_code"],
            "tagged_rm_role": agg["tagged_rm_role"],
            "deal_ids": agg["deals"],
            "_v10338_synthesis": {
                "shipped":  "v10.338",
                "ts":       ts,
                "turnover_method": (
                    "max_facility × deterministic_multiplier "
                    "(5 + hash(name) % 1000 / 100)"
                ),
                "sector_method": "keyword_match_or_hash_fallback",
                "replace_with":  "FLEXCUBE CIF turnover field when integrated",
            },
        }

    _db.save_json(OUT_PATH, out)
    print(f"  Synthesized {len(out)} business customer records")
    print(f"\n  Segment distribution:")
    for code in ("MICRO", "SMALL", "MEDIUM", "CORPORATE"):
        n = segment_distribution.get(code, 0)
        print(f"    {code:11s}  {n}")
    print(f"\n  Top sectors:")
    for sector, n in sorted(
        sector_distribution.items(), key=lambda kv: -kv[1]
    )[:10]:
        print(f"    {n:3d}  {sector}")


if __name__ == "__main__":
    apply()
    print("\nv10.338 business customer synthesis complete.")
