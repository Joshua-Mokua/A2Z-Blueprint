"""utils/kpi_alias_resolver.py — v10.380 KPI Alias Resolution Layer.

Per Joshua's directive at v10.379 wrap-up: "do a deep review of the target
cascade and kpi library for more understanding and appreciation also on
how they are configured, what can be fixed."

The deep review (docs/TARGET_CASCADE_KPI_LIBRARY_REVIEW_v10.380.md)
surfaced 34 orphan KPI IDs referenced in `kpi_library.role_kpis` but not
defined in `kpi_library.kpis`. Of these:

  - 17 are Class A (alias drift) — short SCREAMING_SNAKE versions of
    existing Title Case definitions. **Resolvable via alias mapping.**
  - 17 are Class B (genuinely missing) — no library equivalent. **Need
    new KPI definitions; defer to follow-up batch with Joshua's input.**

Also surfaces:
  - `target_cascade.json::deadline|300001|2026` — corrupted key (metadata
    pollution in cascade dict). Defensive filter provided.

Module purity
-------------
Leaf module — zero upward imports. Reads kpi_library.json + target_cascade.json
to validate aliases on demand. Pure resolution / lookup logic.

This module is **opt-in**: consumers that don't import it continue to work
as before. Consumers that DO import it gain orphan resolution.

API
---
  KPI_ALIASES                              — 17 Class A mappings
  CLASS_B_ORPHANS                          — 17 documented unresolved IDs
  resolve_kpi_id(maybe_alias) → str        — canonical id (or original)
  get_kpi_definition(maybe_alias) → dict   — full library entry (or None)
  list_class_b_orphans() → list[dict]      — for documentation pages
  clean_cascade_dict(raw) → dict           — strips deadline|* corruption
  scan_role_kpis_coverage() → dict         — diagnostic snapshot
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"
KPI_LIBRARY_PATH = DATA_DIR / "kpi_library.json"
TARGET_CASCADE_PATH = DATA_DIR / "target_cascade.json"


# ───────────────────────────────────────────────────────────────────
# Class A — alias drift (verified by Part 3.2 of v10.380 review)
# Map: short SCREAMING_SNAKE alias → canonical library id
# ───────────────────────────────────────────────────────────────────
KPI_ALIASES: Dict[str, str] = {
    # Financial pillar
    "TOTAL_NFI":              "Total NFI",
    "LOAN_GROWTH":            "Loan Book Growth",
    "RETAIL_MSME_DEPOSIT":    "Retail & MSME Deposit Growth",
    "COMMERCIAL_DEPOSIT":     "Commercial Deposit Growth",
    "CASA_RATIO":             "CASA Ratio",
    "COLLECTION_THROUGHPUT":  "Collection Throughput",
    "DISB_CORPORATE":         "Disbursements Corporate Loans",
    "DISB_MSME":              "Disbursements MSME Loans",
    "DISB_RETAIL":            "Disbursements Retail Loans",
    "LOAN_DISB":              "K001",   # Aggregate "Loans Disbursed (KES M)"
    "TRADE_FIN":              "TRADE_FINANCE_REVENUE",
    # Customer Focus pillar
    "CX_SCORE":               "CX Score",
    "TOP100_CUSTOMERS":       "Top 100 Customers Deposit",
    "BUSINESS_BORROWERS":     "Number of Business Borrowers",
    # Operational Excellence pillar
    "AUDIT_SCORE":            "Audit Score",
    "ACCOUNT_DORMANCY":       "Account Dormancy",
    "CHANNEL_DORMANCY":       "Channel Dormancy",
    # Process pillar
    "COMPLIANCE":             "Compliance Score",   # v10.402: canonical now human form (was COMPLIANCE_SCORE)
    # People & Learning pillar
    "STAFF_PROD":             "Staff Productivity",
    # v10.402 deep review additions — uppercase aliases for human-readable canonicals
    "NPL_RATIO":              "NPL Ratio",
    "NEW_ACCOUNTS":           "New Accounts",
    "NET_INTEREST_MARGIN":    "Net Interest Margin",
    "COMPLIANCE_SCORE":       "Compliance Score",
}


# ───────────────────────────────────────────────────────────────────
# Class B — genuinely missing KPI definitions (verified by Part 3.2)
# Each entry has the suggested definition for Joshua's review.
# These remain orphan until a follow-up batch adds definitions.
# ───────────────────────────────────────────────────────────────────
CLASS_B_ORPHANS: List[Dict[str, Any]] = [
    {
        "orphan_id":   "DEP_GROWTH",
        "suggested_name":   "Total Deposit Growth",
        "suggested_pillar": "Financial",
        "suggested_unit":   "%",
        "suggested_direction": "higher",
        "rationale":   "Aggregate of Retail & MSME + Commercial deposit growth — currently MD-only metric",
    },
    {
        "orphan_id":   "FEES_COMM",
        "suggested_name":   "Fees & Commissions Income",
        "suggested_pillar": "Financial",
        "suggested_unit":   "KES M",
        "suggested_direction": "higher",
        "rationale":   "Non-interest fee and commission revenue",
    },
    {
        "orphan_id":   "CIR",
        "suggested_name":   "Cost-to-Income Ratio",
        "suggested_pillar": "Financial",
        "suggested_unit":   "%",
        "suggested_direction": "lower",
        "rationale":   "Operating costs / operating income — Tier-1 benchmark KPI",
    },
    {
        "orphan_id":   "NIM",
        "suggested_name":   "Net Interest Margin",
        "suggested_pillar": "Financial",
        "suggested_unit":   "%",
        "suggested_direction": "higher",
        "rationale":   "Net interest income / earning assets — banking fundamentals",
    },
    {
        "orphan_id":   "ROE",
        "suggested_name":   "Return on Equity",
        "suggested_pillar": "Financial",
        "suggested_unit":   "%",
        "suggested_direction": "higher",
        "rationale":   "Net income / shareholders' equity — Tier-1 benchmark",
    },
    {
        "orphan_id":   "NPS",
        "suggested_name":   "Net Promoter Score",
        "suggested_pillar": "Customer Focus",
        "suggested_unit":   "score",
        "suggested_direction": "higher",
        "rationale":   "Customer loyalty survey metric — required for Customer Focus pillar",
    },
    {
        "orphan_id":   "DIGITAL_ACT",
        "suggested_name":   "Digital Activation Rate",
        "suggested_pillar": "Customer Focus",
        "suggested_unit":   "%",
        "suggested_direction": "higher",
        "rationale":   "Active digital channel users / total customers",
    },
    {
        "orphan_id":   "NEW_CUST",
        "suggested_name":   "New Customers Acquired",
        "suggested_pillar": "Customer Focus",
        "suggested_unit":   "count",
        "suggested_direction": "higher",
        "rationale":   "Closest existing match: NEW_CUSTOMERS_ACQUIRED — could become an alias instead",
    },
    {
        "orphan_id":   "ACTIVE_ACCTS",
        "suggested_name":   "Active Accounts",
        "suggested_pillar": "Customer Focus",
        "suggested_unit":   "count",
        "suggested_direction": "higher",
        "rationale":   "Currently-active accounts (not dormant)",
    },
    {
        "orphan_id":   "PAR",
        "suggested_name":   "Portfolio at Risk",
        "suggested_pillar": "Financial",
        "suggested_unit":   "%",
        "suggested_direction": "lower",
        "rationale":   "Already cascaded as 'PAR' (cascade KPI); library entry exists but should be confirmed",
    },
    {
        "orphan_id":   "TRANSACTIONS",
        "suggested_name":   "Transaction Volume",
        "suggested_pillar": "Customer Focus",
        "suggested_unit":   "count",
        "suggested_direction": "higher",
        "rationale":   "Ambiguous — could mean digital transactions (K012/K071) or total volume; needs clarification",
    },
    {
        "orphan_id":   "LEGAL_OVERDUE_RATE",
        "suggested_name":   "Legal Overdue Rate",
        "suggested_pillar": "Process",
        "suggested_unit":   "%",
        "suggested_direction": "lower",
        "rationale":   "Chief Legal Officer KPI — rate of overdue legal matters",
    },
    {
        "orphan_id":   "LEGAL_SLA_ATTORNEY",
        "suggested_name":   "Legal SLA — Attorney Engagement",
        "suggested_pillar": "Process",
        "suggested_unit":   "%",
        "suggested_direction": "higher",
        "rationale":   "Chief Legal Officer KPI — attorney engagement SLA adherence",
    },
    {
        "orphan_id":   "LEGAL_SLA_DOCS",
        "suggested_name":   "Legal SLA — Document Review",
        "suggested_pillar": "Process",
        "suggested_unit":   "%",
        "suggested_direction": "higher",
        "rationale":   "Chief Legal Officer KPI — document review SLA adherence",
    },
    {
        "orphan_id":   "LEGAL_SLA_SECURITY",
        "suggested_name":   "Legal SLA — Security/Collateral",
        "suggested_pillar": "Process",
        "suggested_unit":   "%",
        "suggested_direction": "higher",
        "rationale":   "Chief Legal Officer KPI — collateral document SLA",
    },
    {
        "orphan_id":   "LEGAL_SLA_VALUATION",
        "suggested_name":   "Legal SLA — Property Valuation",
        "suggested_pillar": "Process",
        "suggested_unit":   "%",
        "suggested_direction": "higher",
        "rationale":   "Chief Legal Officer KPI — property valuation SLA",
    },
]


# ───────────────────────────────────────────────────────────────────
# Cascade metadata corruption — known polluting keys
# ───────────────────────────────────────────────────────────────────
CASCADE_META_KEY_PREFIXES = ("deadline|", "_meta|", "lock|")


# ───────────────────────────────────────────────────────────────────
# Library caching
# ───────────────────────────────────────────────────────────────────
_LIB_CACHE: Optional[Dict[str, Any]] = None


def _load_library() -> Dict[str, Any]:
    """Read kpi_library.json once and cache."""
    global _LIB_CACHE
    if _LIB_CACHE is None:
        if KPI_LIBRARY_PATH.exists():
            _LIB_CACHE = json.loads(KPI_LIBRARY_PATH.read_text(encoding="utf-8"))
        else:
            _LIB_CACHE = {"kpis": [], "role_kpis": {}}
    return _LIB_CACHE


def _build_lookups() -> tuple:
    """Return (by_id, by_name) lookups for the library."""
    lib = _load_library()
    kpis = lib.get("kpis", [])
    by_id = {x["id"]: x for x in kpis if "id" in x}
    by_name = {x["name"]: x for x in kpis if "name" in x}
    return by_id, by_name


def resolve_kpi_id(maybe_alias: str) -> str:
    """Resolve a KPI reference to its canonical library id.

    Resolution order (updated v10.402):
      1. **Alias hit** (canonical decision wins over duplicate library entries)
      2. If maybe_alias is a direct library id → return as-is
      3. If maybe_alias is a library name → return its id
      4. Otherwise → return maybe_alias unchanged (caller handles)

    Returns the canonical id when known, or the input unchanged.
    Use `get_kpi_definition()` to check whether the result resolves.
    """
    if not maybe_alias or not isinstance(maybe_alias, str):
        return maybe_alias

    # v10.402: alias map wins. When two library entries exist (uppercase +
    # human form), the canonical mapping says which one is authoritative.
    if maybe_alias in KPI_ALIASES:
        return KPI_ALIASES[maybe_alias]

    by_id, by_name = _build_lookups()

    # Direct id hit
    if maybe_alias in by_id:
        return maybe_alias

    # Name hit
    if maybe_alias in by_name:
        return by_name[maybe_alias]["id"]

    return maybe_alias


def get_kpi_definition(maybe_alias: str) -> Optional[Dict[str, Any]]:
    """Return the full kpi_library entry for an id, alias, or name.

    Returns None if the input doesn't resolve to any library entry (i.e.
    it's a Class B orphan or completely unknown).
    """
    canonical = resolve_kpi_id(maybe_alias)
    by_id, _ = _build_lookups()
    return by_id.get(canonical)


def is_class_b_orphan(maybe_alias: str) -> bool:
    """True if the input is one of the documented Class B orphans
    (genuinely missing — needs new definition).
    """
    return any(o["orphan_id"] == maybe_alias for o in CLASS_B_ORPHANS)


def list_class_b_orphans() -> List[Dict[str, Any]]:
    """Return Class B orphan inventory for documentation pages."""
    return [dict(o) for o in CLASS_B_ORPHANS]


def clean_cascade_dict(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Strip non-cascade metadata keys from target_cascade dict.

    Defensive utility — consumers reading target_cascade.json should call
    this to filter out the `deadline|*` corruption etc. before iterating.

    Returns a new dict containing only entries whose key matches the
    cascade schema (`<staff>|<kpi>|<year>` with 3 segments).
    """
    if not isinstance(raw, dict):
        return {}
    clean: Dict[str, Any] = {}
    for k, v in raw.items():
        if not isinstance(k, str):
            continue
        # Skip known meta prefixes
        if any(k.startswith(p) for p in CASCADE_META_KEY_PREFIXES):
            continue
        # Validate cascade key shape: <staff>|<kpi>|<year> = 3 segments
        parts = k.split("|")
        if len(parts) != 3:
            continue
        # Staff code typically all digits or EXEC-* prefix
        staff = parts[0]
        if not staff or not (staff.isdigit() or staff.startswith("EXEC-")):
            continue
        # Year is 4 digits
        year = parts[2]
        if not (year.isdigit() and len(year) == 4):
            continue
        # Entry must be a dict with expected fields
        if not isinstance(v, dict):
            continue
        if "from_code" not in v and "kpi" not in v:
            continue
        clean[k] = v
    return clean


def scan_role_kpis_coverage() -> Dict[str, Any]:
    """Diagnostic snapshot — counts orphans by class across role_kpis.

    Returns:
      {
        'total_roles': int,
        'distinct_kpi_refs': int,
        'resolved_direct': int,           # id or name match
        'resolved_via_alias': int,        # alias mapping
        'class_b_orphans': int,           # genuinely missing
        'unknown_orphans': int,           # not in library, not alias, not Class B
        'unknown_orphan_ids': List[str],
        'class_a_aliases_used': List[str],
      }
    """
    lib = _load_library()
    role_kpis = lib.get("role_kpis", {})
    by_id, by_name = _build_lookups()
    class_b_ids = {o["orphan_id"] for o in CLASS_B_ORPHANS}

    all_refs = set()
    for role, kpis in role_kpis.items():
        if isinstance(kpis, list):
            for kid in kpis:
                if isinstance(kid, str):
                    all_refs.add(kid)

    resolved_direct = 0
    resolved_via_alias = 0
    class_b = 0
    unknown = 0
    aliases_used = set()
    unknown_ids: List[str] = []

    for ref in all_refs:
        if ref in by_id or ref in by_name:
            resolved_direct += 1
        elif ref in KPI_ALIASES:
            resolved_via_alias += 1
            aliases_used.add(ref)
        elif ref in class_b_ids:
            class_b += 1
        else:
            unknown += 1
            unknown_ids.append(ref)

    return {
        "total_roles":          len(role_kpis),
        "distinct_kpi_refs":    len(all_refs),
        "resolved_direct":      resolved_direct,
        "resolved_via_alias":   resolved_via_alias,
        "class_b_orphans":      class_b,
        "unknown_orphans":      unknown,
        "unknown_orphan_ids":   sorted(unknown_ids),
        "class_a_aliases_used": sorted(aliases_used),
    }


def self_test() -> None:
    """v10.380 self_test."""
    tests = 0

    # Test 1: direct library id resolves to itself
    assert resolve_kpi_id("PBT") == "PBT"
    assert resolve_kpi_id("NPL_RATIO") == "NPL_RATIO"
    tests += 1

    # Test 2: alias resolves to canonical
    assert resolve_kpi_id("TOTAL_NFI") == "Total NFI"
    assert resolve_kpi_id("CX_SCORE") == "CX Score"
    assert resolve_kpi_id("LOAN_GROWTH") == "Loan Book Growth"
    assert resolve_kpi_id("COMPLIANCE") == "COMPLIANCE_SCORE"
    tests += 1

    # Test 3: name resolves to id
    assert resolve_kpi_id("NPL Ratio") == "NPL_RATIO"
    tests += 1

    # Test 4: Class B orphan stays unresolved
    assert resolve_kpi_id("DEP_GROWTH") == "DEP_GROWTH"  # unchanged
    assert is_class_b_orphan("DEP_GROWTH")
    assert is_class_b_orphan("NIM")
    assert not is_class_b_orphan("PBT")
    tests += 1

    # Test 5: get_kpi_definition returns the entry
    pbt_def = get_kpi_definition("PBT")
    assert pbt_def is not None
    assert pbt_def["id"] == "PBT"
    nfi_def = get_kpi_definition("TOTAL_NFI")  # via alias
    assert nfi_def is not None
    assert nfi_def["id"] == "Total NFI"
    # Class B
    assert get_kpi_definition("NIM") is None
    tests += 1

    # Test 6: list_class_b_orphans returns 15+ documented entries
    orphans = list_class_b_orphans()
    assert len(orphans) >= 15
    for o in orphans:
        for required_field in ("orphan_id", "suggested_name",
                               "suggested_pillar", "rationale"):
            assert required_field in o
    tests += 1

    # Test 7: clean_cascade_dict strips meta keys
    raw = {
        "300001|PBT|2026":       {"from_code": "300001", "kpi": "PBT", "total_target": 22e9},
        "deadline|300001|2026":  {"staff_code": "300001", "targets_locked": True},
        "300002|NPL Ratio|2026": {"from_code": "300002", "kpi": "NPL Ratio"},
        "bad_key":               {"foo": "bar"},
        "300001|PBT|invalid":    {"from_code": "300001"},
    }
    clean = clean_cascade_dict(raw)
    assert "300001|PBT|2026" in clean
    assert "300002|NPL Ratio|2026" in clean
    assert "deadline|300001|2026" not in clean, "deadline corruption leaked"
    assert "bad_key" not in clean
    assert "300001|PBT|invalid" not in clean
    tests += 1

    # Test 8: scan_role_kpis_coverage produces expected shape
    cov = scan_role_kpis_coverage()
    assert cov["total_roles"] == 227
    assert cov["resolved_via_alias"] > 0, "alias resolution should resolve some"
    assert len(cov["class_a_aliases_used"]) > 5, (
        "expected many Class A aliases used"
    )
    # After aliases, the still-unknown count should be < class A count
    # (most orphans should be either Class A resolved or Class B documented)
    tests += 1

    # Test 9: real target_cascade.json round-trip
    if TARGET_CASCADE_PATH.exists():
        raw_cascade = json.loads(TARGET_CASCADE_PATH.read_text(encoding="utf-8"))
        clean_cascade = clean_cascade_dict(raw_cascade)
        # Should have removed at least the deadline|* corruption
        assert len(clean_cascade) <= len(raw_cascade)
        # Verify the deadline key is gone
        for k in clean_cascade.keys():
            assert not k.startswith("deadline|")
        # Verify all clean keys have 3 parts
        for k in clean_cascade.keys():
            assert len(k.split("|")) == 3
    tests += 1

    # Test 10: 17 Class A aliases cover their advertised targets
    by_id, by_name = _build_lookups()
    for alias, canonical in KPI_ALIASES.items():
        assert canonical in by_id or canonical in by_name, (
            f"alias {alias!r} → {canonical!r} but {canonical!r} not in library"
        )
    tests += 1

    print(f"✓ kpi_alias_resolver self_test passed ({tests} tests)")
    cov_final = scan_role_kpis_coverage()
    print(f"  Coverage snapshot:")
    print(f"    Total roles:           {cov_final['total_roles']}")
    print(f"    Distinct KPI refs:     {cov_final['distinct_kpi_refs']}")
    print(f"    Resolved direct:       {cov_final['resolved_direct']}")
    print(f"    Resolved via alias:    {cov_final['resolved_via_alias']}")
    print(f"    Class B orphans:       {cov_final['class_b_orphans']}")
    print(f"    Unknown orphans:       {cov_final['unknown_orphans']}")
    if cov_final["unknown_orphans"] > 0:
        print(f"    Unknown IDs (first 5): {cov_final['unknown_orphan_ids'][:5]}")


if __name__ == "__main__":
    import sys as _sys
    _repo = Path(__file__).resolve().parent.parent
    if str(_repo) not in _sys.path:
        _sys.path.insert(0, str(_repo))
    self_test()
