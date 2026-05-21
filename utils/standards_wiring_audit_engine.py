"""Standards-Wide Engine Wiring Audit — v10.439.

Per Joshua directive: "Just curious if there are standards from the QA
for BSC that were also not wired that needs wiring... We have to rescue
this body completely, we are leaving no stone unturned."

The HR section diagnostic (v10.436) found 4 of 8 HR engines unwired.
This engine extends that pattern across the ENTIRE codebase:

  - 478 engines in utils/
  - 330 standards in registry (CBK + Basel + IFRS + Enhancement)
  - 153 unique engines referenced by standards

For each engine, classifies:
  - **wired_direct**: imported in 1+ pages (page-visible to users)
  - **wired_infrastructure**: imported by 2+ other engines but no pages
    (legitimately infrastructure, OK to be page-unwired)
  - **wired_via_aggregator**: imported only by a few specific aggregator
    engines (finance_hub_render, platform_hub_render, scenario_simulator,
    api_resource_optimization) — accessible to users through the
    aggregator's wired pages
  - **unwired_standalone**: registry-referenced, exists, NOT used
    anywhere, needs page wiring (the real gaps)
  - **orphan**: registry-referenced but no engine file (missing)

Read-only diagnostic. No fixes — v10.440+ executes rescue per priorities.

Public API (API-first, ZERO streamlit):
  - audit_engine_inventory() -> EngineInventoryAudit
  - audit_standards_wiring() -> StandardsWiringAudit
  - audit_unwired_standalone() -> UnwiredStandaloneAudit
  - audit_orphan_standards() -> OrphanStandardsAudit
  - standards_full_audit() -> StandardsFullAudit (master rollup)

Shipped: v10.439.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).parent.parent
UTILS_DIR = REPO_ROOT / "utils"
PAGES_DIR = REPO_ROOT / "pages"

# Aggregator engines: pages call THEM, they call many other engines.
# Engines wired only through aggregators are still user-accessible.
AGGREGATOR_ENGINES: Set[str] = {
    "finance_hub_render",
    "platform_hub_render",
    "scenario_simulator",
    "api_resource_optimization",
    "competitor_hub_render",
    "propositions_hub_render",
    "mlops_persistence",
    "campaigns_orchestration",
    "treasury_hub_render",
    "credit_hub_render",
}

# Engines that are EXPECTED to be infrastructure-only (BSC contract layer,
# data adapters, persistence layers). Surfacing as "unwired" would be
# noise; whitelist them so they don't appear in the rescue priorities.
EXPECTED_INFRASTRUCTURE: Set[str] = {
    "bsc_engine",            # Std #1+#2 contract layer, called by 16
    "flexcube_adapter",      # CBS adapter, called by 10
    "api",                   # FastAPI server itself, not page-imported
    "db",                    # database access layer
    "core",                  # global utilities
    "static_check",          # AST static checker
}


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class EngineClassification:
    name: str
    loc: int
    react_ready: bool
    classification: str    # wired_direct | wired_via_aggregator |
                           # wired_infrastructure | unwired_standalone |
                           # expected_infrastructure
    pages_using: List[str]
    aggregators_using: List[str]
    other_engines_using: List[str]
    in_standards_registry: bool
    standards_count: int


@dataclass
class EngineInventoryAudit:
    total_engines: int
    wired_direct: int
    wired_via_aggregator: int
    wired_infrastructure: int
    unwired_standalone: int
    expected_infrastructure: int
    classifications: List[EngineClassification]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_engines": self.total_engines,
            "wired_direct": self.wired_direct,
            "wired_via_aggregator": self.wired_via_aggregator,
            "wired_infrastructure": self.wired_infrastructure,
            "unwired_standalone": self.unwired_standalone,
            "expected_infrastructure": self.expected_infrastructure,
            "classifications": [asdict(c) for c in self.classifications],
            "timestamp": self.timestamp,
        }


@dataclass
class StandardsWiringAudit:
    total_standards: int
    standards_with_existing_engines: int
    standards_with_wired_engines: int
    standards_with_unwired_engines: int
    standards_with_orphan_engines: int
    wiring_coverage_pct: float
    by_category: Dict[str, Dict[str, int]]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class UnwiredStandaloneAudit:
    """The real rescue targets - registry-backed engines NOT used anywhere."""
    total_unwired: int
    engines: List[Dict[str, Any]]   # [{name, loc, standards, react}]
    by_domain: Dict[str, List[str]]
    rescue_priority_estimates: List[Dict[str, Any]]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OrphanStandardsAudit:
    """Standards referencing engines that don't exist."""
    orphan_count: int
    orphan_engines: List[str]
    standards_orphaned: List[Dict[str, str]]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StandardsFullAudit:
    engine_inventory: EngineInventoryAudit
    standards_wiring: StandardsWiringAudit
    unwired_standalone: UnwiredStandaloneAudit
    orphan_standards: OrphanStandardsAudit
    wiring_health_pct: float
    rescue_priorities: List[str]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_inventory": self.engine_inventory.to_dict(),
            "standards_wiring": self.standards_wiring.to_dict(),
            "unwired_standalone": self.unwired_standalone.to_dict(),
            "orphan_standards": self.orphan_standards.to_dict(),
            "wiring_health_pct": self.wiring_health_pct,
            "rescue_priorities": self.rescue_priorities,
            "timestamp": self.timestamp,
        }


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _list_engines() -> List[str]:
    if not UTILS_DIR.exists():
        return []
    return sorted(
        f.stem for f in UTILS_DIR.glob("*.py")
        if not f.name.startswith("_")
    )


def _engine_loc(name: str) -> int:
    p = UTILS_DIR / f"{name}.py"
    if not p.exists():
        return 0
    try:
        return len(p.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeDecodeError):
        return 0


def _engine_react_ready(name: str) -> bool:
    p = UTILS_DIR / f"{name}.py"
    if not p.exists():
        return False
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    has_st = bool(re.search(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    ))
    has_dc = "@dataclass" in text
    return (not has_st) and has_dc


def _build_import_graph() -> Tuple[
    Dict[str, List[str]],   # engine -> pages importing it
    Dict[str, List[str]],   # engine -> engines importing it
]:
    """Scan utils/ and pages/ for `from utils.X import` patterns."""
    page_to_engines: Dict[str, List[str]] = {}
    engine_to_engines: Dict[str, List[str]] = {}

    for p in PAGES_DIR.glob("[0-9]*.py"):
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in re.finditer(r"from\s+utils\.([a-z0-9_]+)\s+import", text):
            page_to_engines.setdefault(m.group(1), []).append(p.name)

    for src in UTILS_DIR.glob("*.py"):
        if src.name.startswith("_"):
            continue
        try:
            text = src.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for m in re.finditer(r"from\s+utils\.([a-z0-9_]+)\s+import", text):
            target = m.group(1)
            if target == src.stem:
                continue
            engine_to_engines.setdefault(target, []).append(src.stem)

    return page_to_engines, engine_to_engines


def _registry_standards() -> List[Any]:
    """Load standards registry."""
    try:
        import sys
        # Make sure repo root is in path when run as __main__
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        import importlib
        if "utils.standards_registry" in sys.modules:
            sr = importlib.reload(sys.modules["utils.standards_registry"])
        else:
            sr = importlib.import_module("utils.standards_registry")
        out = []
        for name in dir(sr):
            if name.endswith("_STANDARDS"):
                obj = getattr(sr, name)
                if isinstance(obj, (list, tuple)):
                    out.extend(obj)
        return out
    except Exception as exc:  # noqa: BLE001
        # When run as standalone module
        try:
            import sys
            sys.path.insert(0, str(REPO_ROOT))
            from utils import standards_registry as sr
            out = []
            for name in dir(sr):
                if name.endswith("_STANDARDS"):
                    obj = getattr(sr, name)
                    if isinstance(obj, (list, tuple)):
                        out.extend(obj)
            return out
        except Exception:
            return []


def _classify_engine(
    name: str,
    page_to_engines: Dict[str, List[str]],
    engine_to_engines: Dict[str, List[str]],
    standards_map: Dict[str, int],
) -> EngineClassification:
    pages = sorted(set(page_to_engines.get(name, [])))
    engine_callers = sorted(set(engine_to_engines.get(name, [])))
    aggregators = [e for e in engine_callers if e in AGGREGATOR_ENGINES]
    non_agg_callers = [e for e in engine_callers if e not in AGGREGATOR_ENGINES]

    if name in EXPECTED_INFRASTRUCTURE:
        classification = "expected_infrastructure"
    elif pages:
        classification = "wired_direct"
    elif aggregators:
        classification = "wired_via_aggregator"
    elif len(engine_callers) >= 2:
        classification = "wired_infrastructure"
    elif name in standards_map:
        classification = "unwired_standalone"
    else:
        # Not in registry, not wired anywhere — internal helper or test fixture
        classification = "wired_infrastructure" if engine_callers else "unwired_standalone"

    return EngineClassification(
        name=name,
        loc=_engine_loc(name),
        react_ready=_engine_react_ready(name),
        classification=classification,
        pages_using=pages,
        aggregators_using=aggregators,
        other_engines_using=non_agg_callers,
        in_standards_registry=name in standards_map,
        standards_count=standards_map.get(name, 0),
    )


# ════════════════════════════════════════════════════════════════════
# Audits
# ════════════════════════════════════════════════════════════════════

def audit_engine_inventory() -> EngineInventoryAudit:
    """Classify every engine in utils/."""
    page_to, engine_to = _build_import_graph()
    standards = _registry_standards()
    standards_map: Dict[str, int] = {}
    for s in standards:
        for e in (getattr(s, "affected_engines", None) or ()):
            standards_map[e] = standards_map.get(e, 0) + 1

    classifications = [
        _classify_engine(name, page_to, engine_to, standards_map)
        for name in _list_engines()
    ]

    counts = {
        "wired_direct": 0,
        "wired_via_aggregator": 0,
        "wired_infrastructure": 0,
        "unwired_standalone": 0,
        "expected_infrastructure": 0,
    }
    for c in classifications:
        counts[c.classification] = counts.get(c.classification, 0) + 1

    return EngineInventoryAudit(
        total_engines=len(classifications),
        wired_direct=counts["wired_direct"],
        wired_via_aggregator=counts["wired_via_aggregator"],
        wired_infrastructure=counts["wired_infrastructure"],
        unwired_standalone=counts["unwired_standalone"],
        expected_infrastructure=counts["expected_infrastructure"],
        classifications=classifications,
        timestamp=datetime.now().isoformat(),
    )


def audit_standards_wiring() -> StandardsWiringAudit:
    """Per-standard: is its engine wired anywhere user-visible?"""
    standards = _registry_standards()
    page_to, engine_to = _build_import_graph()
    existing_engines = set(_list_engines())

    # A standard's engine is "accessible" if any of its affected_engines
    # is wired_direct OR wired_via_aggregator.
    n_total = len(standards)
    n_existing = 0
    n_wired = 0
    n_unwired = 0
    n_orphan = 0
    by_category: Dict[str, Dict[str, int]] = {}

    for s in standards:
        cat = getattr(s, "category", "unknown")
        by_category.setdefault(cat, {"total": 0, "wired": 0, "unwired": 0})
        by_category[cat]["total"] += 1
        engines = getattr(s, "affected_engines", None) or ()
        if not engines:
            continue
        # Standard is "wired" if any of its engines exists AND is
        # accessible via pages or aggregators (excluding expected
        # infrastructure which is OK to not be page-wired).
        any_existing = False
        any_wired = False
        for e in engines:
            if e in existing_engines:
                any_existing = True
                if e in EXPECTED_INFRASTRUCTURE:
                    any_wired = True
                    continue
                if page_to.get(e):
                    any_wired = True
                    continue
                # Via aggregator?
                callers = engine_to.get(e, [])
                if any(c in AGGREGATOR_ENGINES for c in callers):
                    any_wired = True
                    continue
                # Used by >=2 other engines (infrastructure):
                if len(callers) >= 2:
                    any_wired = True
        if any_existing:
            n_existing += 1
            if any_wired:
                n_wired += 1
                by_category[cat]["wired"] += 1
            else:
                n_unwired += 1
                by_category[cat]["unwired"] += 1
        else:
            n_orphan += 1

    coverage = n_wired / n_existing * 100 if n_existing else 0.0

    return StandardsWiringAudit(
        total_standards=n_total,
        standards_with_existing_engines=n_existing,
        standards_with_wired_engines=n_wired,
        standards_with_unwired_engines=n_unwired,
        standards_with_orphan_engines=n_orphan,
        wiring_coverage_pct=round(coverage, 1),
        by_category=by_category,
        timestamp=datetime.now().isoformat(),
    )


# Domain prefixes for grouping unwired engines
DOMAIN_PREFIXES: List[Tuple[str, str]] = [
    ("mlops",     "MLOps & Model Governance"),
    ("market_risk", "Market Risk & Treasury"),
    ("audit",     "Audit & Compliance"),
    ("finance",   "Finance"),
    ("credit",    "Credit & Lending"),
    ("initiative","Strategy & Initiatives"),
    ("workload",  "Workforce Planning"),
    ("regulatory","Regulatory"),
    ("board",     "Governance & Board"),
    ("rwa",       "Capital Adequacy"),
    ("ifrs",      "IFRS & Accounting"),
    ("deposit",   "Customer & Deposits"),
    ("dormancy",  "Customer & Deposits"),
    ("cross_sell","Customer & Sales"),
    ("benchmark", "Treasury"),
    ("funds_transfer", "Treasury"),
    ("fund_transfer",  "Treasury"),
    ("operating", "Finance"),
    ("queue",     "Operations"),
    ("reconcil",  "Operations"),
    ("issue",     "Operations"),
    ("notification", "Platform"),
    ("api",       "Platform"),
    ("model_governance_runtime", "MLOps & Model Governance"),
    ("lending",   "Credit & Lending"),
    ("risk_based","Credit & Lending"),
    ("risk_weighted", "Capital Adequacy"),
]


def _domain_of(engine_name: str) -> str:
    for prefix, label in DOMAIN_PREFIXES:
        if engine_name.startswith(prefix):
            return label
    return "Other"


def audit_unwired_standalone() -> UnwiredStandaloneAudit:
    """Surface the engines that NEED rescue (truly user-facing, not wired)."""
    inv = audit_engine_inventory()
    unwired = [
        c for c in inv.classifications
        if c.classification == "unwired_standalone"
        and c.in_standards_registry
    ]
    unwired.sort(key=lambda c: (-c.loc, c.name))

    engines_info = [{
        "name": c.name,
        "loc": c.loc,
        "react_ready": c.react_ready,
        "standards_count": c.standards_count,
        "domain": _domain_of(c.name),
    } for c in unwired]

    # Group by domain
    by_domain: Dict[str, List[str]] = {}
    for info in engines_info:
        by_domain.setdefault(info["domain"], []).append(info["name"])

    # Rescue priority estimates (largest LOC + most standards first)
    priorities = sorted(unwired,
                       key=lambda c: -(c.loc + c.standards_count * 100))
    priority_list = [{
        "rank": i + 1,
        "engine": c.name,
        "loc": c.loc,
        "standards": c.standards_count,
        "domain": _domain_of(c.name),
        "react_ready": c.react_ready,
    } for i, c in enumerate(priorities[:20])]

    return UnwiredStandaloneAudit(
        total_unwired=len(unwired),
        engines=engines_info,
        by_domain=by_domain,
        rescue_priority_estimates=priority_list,
        timestamp=datetime.now().isoformat(),
    )


def audit_orphan_standards() -> OrphanStandardsAudit:
    """Standards referencing engines that don't exist as files."""
    standards = _registry_standards()
    existing = set(_list_engines())
    orphan_engines: Set[str] = set()
    orphaned_records: List[Dict[str, str]] = []
    for s in standards:
        engines = getattr(s, "affected_engines", None) or ()
        missing = [e for e in engines if e not in existing]
        if missing:
            for m in missing:
                orphan_engines.add(m)
            orphaned_records.append({
                "standard_id": getattr(s, "standard_id", "?"),
                "name": getattr(s, "name", "?"),
                "missing_engines": ",".join(missing),
            })
    return OrphanStandardsAudit(
        orphan_count=len(orphan_engines),
        orphan_engines=sorted(orphan_engines),
        standards_orphaned=orphaned_records,
        timestamp=datetime.now().isoformat(),
    )


def standards_full_audit() -> StandardsFullAudit:
    inv = audit_engine_inventory()
    sw = audit_standards_wiring()
    uw = audit_unwired_standalone()
    orph = audit_orphan_standards()

    # Wiring health: avg of coverage + (1 - unwired/total)
    health = sw.wiring_coverage_pct

    priorities: List[str] = []
    if uw.total_unwired > 0:
        top_domains = sorted(
            uw.by_domain.items(), key=lambda kv: -len(kv[1]),
        )[:5]
        for dom, engines in top_domains:
            priorities.append(
                f"Wire {dom}: {len(engines)} engines ({engines[:3]}...)"
            )
    if orph.orphan_count > 0:
        priorities.append(
            f"Build {orph.orphan_count} orphan engines referenced by "
            f"standards but missing: {orph.orphan_engines[:5]}"
        )

    return StandardsFullAudit(
        engine_inventory=inv,
        standards_wiring=sw,
        unwired_standalone=uw,
        orphan_standards=orph,
        wiring_health_pct=round(health, 1),
        rescue_priorities=priorities,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ standards_wiring_audit_engine self-test ─")

    text = Path(__file__).read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports")

    inv = audit_engine_inventory()
    print(f"\n  Engine inventory:")
    print(f"    Total engines:                 {inv.total_engines}")
    print(f"    Wired direct (in pages):        {inv.wired_direct}")
    print(f"    Wired via aggregator:           {inv.wired_via_aggregator}")
    print(f"    Wired as infrastructure:        {inv.wired_infrastructure}")
    print(f"    Expected infrastructure:        {inv.expected_infrastructure}")
    print(f"    UNWIRED STANDALONE:             {inv.unwired_standalone} 🔴")

    sw = audit_standards_wiring()
    print(f"\n  Standards wiring:")
    print(f"    Total standards in registry:    {sw.total_standards}")
    print(f"    Standards with existing engines: {sw.standards_with_existing_engines}")
    print(f"    Standards with wired engines:    {sw.standards_with_wired_engines}")
    print(f"    Standards with unwired engines:  {sw.standards_with_unwired_engines}")
    print(f"    Standards with orphan engines:   {sw.standards_with_orphan_engines}")
    print(f"    Wiring coverage:                 {sw.wiring_coverage_pct}%")

    uw = audit_unwired_standalone()
    print(f"\n  Unwired standalone (need rescue): {uw.total_unwired}")
    print(f"  By domain:")
    for dom, engines in sorted(uw.by_domain.items(),
                              key=lambda kv: -len(kv[1])):
        print(f"    {dom:35} {len(engines)} engines")
    print(f"\n  Top 10 rescue priorities (LOC + standards weight):")
    for p in uw.rescue_priority_estimates[:10]:
        rdy = "✓" if p["react_ready"] else "✗"
        print(f"    #{p['rank']:2}  {p['engine']:35} {p['loc']:5} LOC  "
              f"{p['standards']:2} stds  React={rdy}  ({p['domain']})")

    orph = audit_orphan_standards()
    print(f"\n  Orphan engines (referenced but missing): {orph.orphan_count}")
    if orph.orphan_engines:
        for e in orph.orphan_engines[:10]:
            print(f"    ✗ {e}")

    full = standards_full_audit()
    print(f"\n  ═══ STANDARDS WIRING HEALTH: {full.wiring_health_pct}% ═══")
    print(f"  Rescue priorities:")
    for i, p in enumerate(full.rescue_priorities, 1):
        print(f"    {i}. {p}")

    json.dumps(full.to_dict())
    print(f"\n  ✓ JSON-serializable")

    print("\n✓ self_test passed")


if __name__ == "__main__":
    self_test()
