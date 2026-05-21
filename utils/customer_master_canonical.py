"""utils/customer_master_canonical.py — v10.378 Customer Master Merge.

Per Joshua's "merge into 1" approval (v10.374 wrap-up). Establishes the
**recognition / sensory layer** of the body-system framing: how the bank
recognizes its customers across both transactional (CBS) and intelligence
(marketing) universes.

Two source universes today:
  1. CBS customers.csv          — 100 seed / 700K production, system of record
                                  CIF format 10-digit (1000000001), fields
                                  cif/full_name/segment/branch_code/rm_code
  2. customer_intelligence.json — 3,000 individuals + 206 businesses
                                  CIF formats: 9-digit numeric / CIFNNNNNN,
                                  fields CLV/NPS/churn_risk/propensity/tags/...

Merge strategy (strict CIF match):
  - CIFs in both sources → enrichment_status='both' (full record)
  - CIFs only in CBS → enrichment_status='cbs_only'
  - CIFs only in marketing → enrichment_status='marketing_only'

Conflict resolution: see docs/CUSTOMER_MASTER_MERGE_v10.378.md Part 2.3.
Read-only: no source file mutated. Per constitution §4.3, no new JSON
output file.

Module purity
-------------
Leaf module. Reads CBS customers.csv via Path argument + reads
customer_intelligence.json + customer_intelligence_business.json from
data/. Returns in-memory unified records. No upward imports.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"

# Marketing master files (legacy — preserved during transition)
MARKETING_INDIVIDUALS = DATA_DIR / "customer_intelligence.json"
MARKETING_BUSINESSES = DATA_DIR / "customer_intelligence_business.json"

# Enrichment status values
STATUS_CBS_ONLY = "cbs_only"
STATUS_MARKETING_ONLY = "marketing_only"
STATUS_BOTH = "both"

# Source identifiers
SRC_CBS = "cbs"
SRC_MARKETING = "marketing"
SRC_DERIVED = "derived"


@dataclass
class UnifiedCustomerRecord:
    """One unified customer record from merging CBS + marketing master.

    All Optional fields default to None when the source doesn't supply them.
    `_field_lineage` documents which source each populated field came from.
    """
    cif: str
    full_name: Optional[str] = None
    customer_type: str = "unknown"
    enrichment_status: str = STATUS_CBS_ONLY

    # Transactional fields (from CBS)
    segment: Optional[str] = None
    branch_code: Optional[str] = None
    rm_code: Optional[str] = None

    # Intelligence fields (from marketing)
    clv_estimate: Optional[float] = None
    churn_risk: Optional[float] = None
    nba: Optional[str] = None
    nps_score: Optional[int] = None
    digital_engagement: Optional[str] = None
    products_held: Optional[int] = None
    propensity_scores: Dict[str, float] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    complaints_12m: Optional[int] = None
    last_contact_days: Optional[int] = None

    # Lineage tracking
    sources: List[str] = field(default_factory=list)
    _field_lineage: Dict[str, str] = field(default_factory=dict)

    def has_transactional_data(self) -> bool:
        return self.branch_code is not None and self.rm_code is not None

    def has_intelligence_data(self) -> bool:
        return any(
            v is not None
            for v in (self.clv_estimate, self.churn_risk, self.nba,
                      self.nps_score, self.digital_engagement)
        )


def _load_cbs_customers(cbs_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Read CBS customers.csv into CIF → dict mapping."""
    out: Dict[str, Dict[str, Any]] = {}
    csv_path = cbs_dir / "customers.csv"
    if not csv_path.exists():
        return out
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cif = str(row.get("cif", "")).strip()
            if cif:
                out[cif] = {
                    "full_name":   row.get("full_name", "") or None,
                    "segment":     row.get("segment", "") or None,
                    "branch_code": row.get("branch_code", "") or None,
                    "rm_code":     row.get("rm_code", "") or None,
                }
    return out


def _load_marketing_individuals() -> Dict[str, Dict[str, Any]]:
    """Read customer_intelligence.json into CIF → dict mapping."""
    out: Dict[str, Dict[str, Any]] = {}
    if not MARKETING_INDIVIDUALS.exists():
        return out
    try:
        data = json.loads(MARKETING_INDIVIDUALS.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for cif, rec in data.items():
                if isinstance(rec, dict) and not cif.startswith("_"):
                    out[str(cif)] = rec
    except Exception:
        pass
    return out


def _load_marketing_businesses() -> Dict[str, Dict[str, Any]]:
    """Read customer_intelligence_business.json into CIF → dict mapping."""
    out: Dict[str, Dict[str, Any]] = {}
    if not MARKETING_BUSINESSES.exists():
        return out
    try:
        data = json.loads(MARKETING_BUSINESSES.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for cif, rec in data.items():
                if isinstance(rec, dict) and not cif.startswith("_"):
                    out[str(cif)] = rec
    except Exception:
        pass
    return out


def _merge_one(
    cif: str,
    cbs_rec: Optional[Dict[str, Any]],
    mkt_rec: Optional[Dict[str, Any]],
    is_business: bool = False,
) -> UnifiedCustomerRecord:
    """Apply conflict resolution rules per docs/CUSTOMER_MASTER_MERGE.md."""
    sources: List[str] = []
    lineage: Dict[str, str] = {}
    record_kwargs: Dict[str, Any] = {"cif": cif}

    # Determine enrichment status
    if cbs_rec and mkt_rec:
        record_kwargs["enrichment_status"] = STATUS_BOTH
        sources = [SRC_CBS, SRC_MARKETING]
    elif cbs_rec:
        record_kwargs["enrichment_status"] = STATUS_CBS_ONLY
        sources = [SRC_CBS]
    elif mkt_rec:
        record_kwargs["enrichment_status"] = STATUS_MARKETING_ONLY
        sources = [SRC_MARKETING]

    # full_name: CBS wins (KYC authoritative)
    if cbs_rec and cbs_rec.get("full_name"):
        record_kwargs["full_name"] = cbs_rec["full_name"]
        lineage["full_name"] = SRC_CBS
    elif mkt_rec and mkt_rec.get("full_name"):
        record_kwargs["full_name"] = mkt_rec["full_name"]
        lineage["full_name"] = SRC_MARKETING

    # customer_type: marketing wins (it tracks individual/business explicitly)
    if mkt_rec and mkt_rec.get("customer_type"):
        record_kwargs["customer_type"] = mkt_rec["customer_type"]
        lineage["customer_type"] = SRC_MARKETING
    elif is_business:
        record_kwargs["customer_type"] = "business"
        lineage["customer_type"] = SRC_DERIVED
    elif cbs_rec:
        # Default to individual when only CBS has it
        record_kwargs["customer_type"] = "individual"
        lineage["customer_type"] = SRC_DERIVED

    # Transactional fields — CBS wins
    if cbs_rec:
        for fname in ("segment", "branch_code", "rm_code"):
            v = cbs_rec.get(fname)
            if v is not None:
                record_kwargs[fname] = v
                lineage[fname] = SRC_CBS
    # Marketing segment as fallback only if CBS doesn't have it
    if "segment" not in record_kwargs and mkt_rec and mkt_rec.get("segment"):
        record_kwargs["segment"] = mkt_rec["segment"]
        lineage["segment"] = SRC_MARKETING

    # Intelligence fields — marketing only
    if mkt_rec:
        for fname in ("clv_estimate", "churn_risk", "nba", "nps_score",
                       "digital_engagement", "products_held",
                       "complaints_12m", "last_contact_days"):
            v = mkt_rec.get(fname)
            if v is not None:
                record_kwargs[fname] = v
                lineage[fname] = SRC_MARKETING
        # propensity_scores (dict)
        ps = mkt_rec.get("propensity_scores")
        if isinstance(ps, dict):
            record_kwargs["propensity_scores"] = dict(ps)
            lineage["propensity_scores"] = SRC_MARKETING
        # tags (list)
        tags = mkt_rec.get("tags")
        if isinstance(tags, list):
            record_kwargs["tags"] = list(tags)
            lineage["tags"] = SRC_MARKETING

    record_kwargs["sources"] = sources
    record_kwargs["_field_lineage"] = lineage
    return UnifiedCustomerRecord(**record_kwargs)


def compute_unified_customer_master(
    cbs_dir: Optional[Path] = None,
) -> Dict[str, UnifiedCustomerRecord]:
    """The canonical merge engine.

    Reads CBS customers.csv (if cbs_dir provided) + marketing masters.
    Returns CIF → UnifiedCustomerRecord. Strict CIF matching.
    """
    cbs = _load_cbs_customers(cbs_dir) if cbs_dir else {}
    individuals = _load_marketing_individuals()
    businesses = _load_marketing_businesses()

    # Combine the two marketing universes
    marketing: Dict[str, Dict[str, Any]] = {}
    marketing.update(individuals)
    marketing.update(businesses)  # business CIFs (CIFXXXXXX) don't collide with numeric

    # Collect distinct CIFs across both sources
    all_cifs = set(cbs.keys()) | set(marketing.keys())

    unified: Dict[str, UnifiedCustomerRecord] = {}
    for cif in all_cifs:
        cbs_rec = cbs.get(cif)
        mkt_rec = marketing.get(cif)
        is_business = cif in businesses
        unified[cif] = _merge_one(
            cif=cif,
            cbs_rec=cbs_rec,
            mkt_rec=mkt_rec,
            is_business=is_business,
        )
    return unified


def reconciliation_summary(
    unified: Dict[str, UnifiedCustomerRecord],
    cbs_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Verify the identity equation and compute summary stats.

    Identity: count(unified) == |CBS ∪ marketing|
                              == |CBS| + |marketing| - |overlap|
    """
    cbs = _load_cbs_customers(cbs_dir) if cbs_dir else {}
    individuals = _load_marketing_individuals()
    businesses = _load_marketing_businesses()
    marketing_all = dict(individuals)
    marketing_all.update(businesses)

    cbs_cifs = set(cbs.keys())
    mkt_cifs = set(marketing_all.keys())
    overlap = cbs_cifs & mkt_cifs
    union = cbs_cifs | mkt_cifs

    # Status counts from unified
    counts = {STATUS_CBS_ONLY: 0, STATUS_MARKETING_ONLY: 0, STATUS_BOTH: 0}
    customer_types = {"individual": 0, "business": 0, "unknown": 0}
    fully_tagged = 0  # has both transactional + intelligence
    for r in unified.values():
        counts[r.enrichment_status] = counts.get(r.enrichment_status, 0) + 1
        customer_types[r.customer_type] = customer_types.get(r.customer_type, 0) + 1
        if r.has_transactional_data() and r.has_intelligence_data():
            fully_tagged += 1

    # Identity equation check (the G264 invariant)
    identity_lhs = len(unified)
    identity_rhs = len(cbs_cifs) + len(mkt_cifs) - len(overlap)
    identity_holds = identity_lhs == identity_rhs

    # Status totals equation check
    status_total = sum(counts.values())
    status_totals_match = status_total == len(unified)

    return {
        "unified_count":     len(unified),
        "cbs_count":         len(cbs_cifs),
        "marketing_count":   len(mkt_cifs),
        "overlap_count":     len(overlap),
        "union_count":       len(union),
        "by_status":         counts,
        "by_customer_type":  customer_types,
        "fully_tagged":      fully_tagged,
        "identity_lhs":      identity_lhs,
        "identity_rhs":      identity_rhs,
        "identity_holds":    identity_holds,
        "status_totals_match": status_totals_match,
    }


def get_customer(
    cif: str,
    cbs_dir: Optional[Path] = None,
) -> Optional[UnifiedCustomerRecord]:
    """Single-customer lookup. Useful for module integration."""
    unified = compute_unified_customer_master(cbs_dir=cbs_dir)
    return unified.get(cif)


def self_test() -> None:
    """v10.378 self_test — uses real marketing data + synthetic CBS for clarity."""
    tests = 0

    # Test 1: marketing-only run (no cbs_dir) produces the 3,206 marketing universe
    unified = compute_unified_customer_master(cbs_dir=None)
    assert len(unified) >= 3000, (
        f"expected ≥3000 marketing customers, got {len(unified)}"
    )
    for r in unified.values():
        assert r.enrichment_status == STATUS_MARKETING_ONLY
    tests += 1

    # Test 2: reconciliation summary identity holds (marketing-only)
    summary = reconciliation_summary(unified, cbs_dir=None)
    assert summary["identity_holds"], summary
    assert summary["status_totals_match"], summary
    assert summary["cbs_count"] == 0
    assert summary["marketing_count"] >= 3000
    assert summary["overlap_count"] == 0
    tests += 1

    # Test 3: a known marketing CIF gets enrichment from marketing
    sample = next(iter(_load_marketing_individuals().keys()))
    r = unified.get(sample)
    assert r is not None
    assert r.enrichment_status == STATUS_MARKETING_ONLY
    assert r.cif == sample
    assert SRC_MARKETING in r.sources
    assert SRC_CBS not in r.sources
    tests += 1

    # Test 4: business customers classified correctly
    biz = _load_marketing_businesses()
    if biz:
        biz_cif = next(iter(biz.keys()))
        r = unified.get(biz_cif)
        assert r is not None
        assert r.customer_type == "business"
        # business CIFs start with 'CIF'
        assert biz_cif.startswith("CIF")
    tests += 1

    # Test 5: end-to-end with seeded CBS bank — both universes coexist
    import tempfile
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        unified_with_cbs = compute_unified_customer_master(cbs_dir=td_path)
        summary_with = reconciliation_summary(unified_with_cbs, cbs_dir=td_path)

    # Seed CBS has 100; marketing has ~3,206; should be ~3,306 unique
    assert summary_with["cbs_count"] == 100
    assert summary_with["marketing_count"] >= 3000
    # Seed CIFs and marketing CIFs are disjoint (different schemes) → 0 overlap
    assert summary_with["overlap_count"] == 0
    assert summary_with["unified_count"] == summary_with["cbs_count"] + summary_with["marketing_count"]
    assert summary_with["identity_holds"]
    tests += 1

    # Test 6: status distribution matches (cbs_only + marketing_only + both = total)
    s = summary_with["by_status"]
    assert s[STATUS_CBS_ONLY] == 100  # all 100 seed customers are CBS-only
    assert s[STATUS_MARKETING_ONLY] >= 3000
    assert s[STATUS_BOTH] == 0  # disjoint in seed
    tests += 1

    # Test 7: CBS records carry transactional fields with CBS lineage
    cbs_only_record = next(
        (r for r in unified_with_cbs.values() if r.enrichment_status == STATUS_CBS_ONLY),
        None,
    )
    assert cbs_only_record is not None
    assert cbs_only_record.branch_code is not None
    assert cbs_only_record.rm_code is not None
    assert cbs_only_record._field_lineage.get("branch_code") == SRC_CBS
    assert cbs_only_record._field_lineage.get("rm_code") == SRC_CBS
    assert cbs_only_record.has_transactional_data()
    assert not cbs_only_record.has_intelligence_data()
    tests += 1

    # Test 8: marketing-only records carry intelligence fields with marketing lineage
    mkt_only_record = next(
        (r for r in unified_with_cbs.values()
         if r.enrichment_status == STATUS_MARKETING_ONLY and r.clv_estimate is not None),
        None,
    )
    if mkt_only_record:
        assert mkt_only_record._field_lineage.get("clv_estimate") == SRC_MARKETING
        assert mkt_only_record.has_intelligence_data()
    tests += 1

    # Test 9: get_customer single-lookup works
    if unified_with_cbs:
        any_cif = next(iter(unified_with_cbs.keys()))
        single = get_customer(any_cif)
        assert single is not None
        assert single.cif == any_cif
    tests += 1

    # Test 10: identity equation explicitly
    assert summary_with["identity_lhs"] == summary_with["identity_rhs"]
    tests += 1

    print(f"✓ customer_master_canonical self_test passed ({tests} tests)")
    print(f"  CBS:        {summary_with['cbs_count']}")
    print(f"  Marketing:  {summary_with['marketing_count']}")
    print(f"  Overlap:    {summary_with['overlap_count']}")
    print(f"  Unified:    {summary_with['unified_count']}")
    print(f"  Identity:   {'HOLDS' if summary_with['identity_holds'] else 'BROKEN'}")
    print(f"  Status: cbs_only={summary_with['by_status'][STATUS_CBS_ONLY]} "
          f"marketing_only={summary_with['by_status'][STATUS_MARKETING_ONLY]} "
          f"both={summary_with['by_status'][STATUS_BOTH]}")


if __name__ == "__main__":
    import sys
    _repo = Path(__file__).resolve().parent.parent
    if str(_repo) not in sys.path:
        sys.path.insert(0, str(_repo))
    self_test()
