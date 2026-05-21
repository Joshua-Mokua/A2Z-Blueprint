"""utils/standards_wiring_per_module.py — v10.460 Per-Module Standards Wiring.

Per Joshua v10.460: "there is also the part of the QA gap analysing
standards that we need to confirm if all the standards were done and
wired for each."

The existing utils/standards_wiring_audit_engine.py audits standards
system-wide. This wrapper produces a **per-module** view answering:
  - Which standards apply to this module?
  - Are the engines backing those standards wired into the module's pages?
  - What is the per-module standards wiring coverage %?

Public API (API-first, ZERO streamlit):
  - get_module_standards(module_key) -> List[StandardEntry]
  - audit_module_standards_wiring(module_key) -> ModuleStandardsAudit
  - audit_all_module_standards() -> Dict[str, ModuleStandardsAudit]
  - generate_module_standards_doc(module_key) -> str

Shipped: v10.460.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

REPO_ROOT = Path(__file__).parent.parent
UTILS_DIR = REPO_ROOT / "utils"
PAGES_DIR = REPO_ROOT / "pages"
DATA_DIR = REPO_ROOT / "data"


# Domain mapping: which standards-registry keywords go to which module.
# This is the bridge between the standards registry (system-wide) and
# the 5-organ MODULE_REGISTRY.
MODULE_STANDARD_DOMAINS: Dict[str, List[str]] = {
    "admin": [
        "admin", "audit", "compliance", "rbac", "standards",
        "config", "users", "permissions",
    ],
    "hr": [
        "hr", "staff", "training", "wellness", "onboarding",
        "exit", "pip", "disciplinary", "lms", "performance",
    ],
    "bsc_cascade": [
        "bsc", "balanced_scorecard", "kpi", "cascade", "target",
        "pillar", "scorecard",
    ],
    "credit": [
        "credit", "loan", "npl", "ifrs9", "collateral", "underwriting",
        "disbursement", "recovery", "scoring",
    ],
    "ict": [
        "it_", "ict", "observability", "cybersecurity", "uptime",
        "incident", "sla", "deployment", "infrastructure",
        "flexcube", "integration", "api_gateway", "cicd",
        "disaster_recovery", "encryption", "tenancy",
    ],
    "finance": [
        "finance", "fin_", "gl_", "accounting", "ledger", "book_",
        "accruals", "operating_segments", "audit_compliance",
    ],
    "treasury": [
        "treasury", "trsry", "liquidity", "funds_transfer", "fx_",
        "alm_", "benchmark_rates", "market_risk",
    ],
    "legal": [
        "legal", "company_sec", "board", "governance", "corporate",
        "legal_hold", "case_management",
    ],
    "risk": [
        "risk_", "enterprise_risk", "risk_weight", "operational_risk",
        "compliance_risk",
    ],
    "compliance": [
        "compliance", "aml_", "kyc_", "sanctions", "regulatory_reporting",
        "cbk_", "tax_compliance", "kra_", "insurance_ira",
    ],
    "operations": [
        "ops_", "operations", "sla_", "cims", "edms", "approval",
        "branch_log", "fraud", "clearing", "swift", "p2p_", "vendor",
        "asset_", "contract", "incident_",
    ],
    "crm": [
        "crm_", "pipeline", "customer_360", "customer_behavioral",
        "cross_sell", "nps_", "campaign", "proposition", "lead_",
        "onboarding", "channel", "contact_centre", "bancassurance",
    ],
    "reporting_analytics": [
        "analytics", "reporting", "benchmark", "competitor",
        "branch_rank", "sbu_", "nlq", "anomaly", "dashboard",
    ],
}


@dataclass
class StandardEntry:
    standard_id: str
    name: str
    engine: str
    wired_state: str          # wired_direct/wired_infrastructure/unwired_standalone/orphan
    pages_using: List[str]

    def to_dict(self): return asdict(self)


@dataclass
class ModuleStandardsAudit:
    module_key: str
    total_standards_for_module: int
    wired_count: int
    unwired_count: int
    orphan_count: int
    wiring_coverage_pct: float
    standards: List[StandardEntry]
    recommendation: str
    timestamp: str

    def to_dict(self):
        return {
            "module_key": self.module_key,
            "total_standards_for_module": self.total_standards_for_module,
            "wired_count": self.wired_count,
            "unwired_count": self.unwired_count,
            "orphan_count": self.orphan_count,
            "wiring_coverage_pct": self.wiring_coverage_pct,
            "standards": [s.to_dict() for s in self.standards],
            "recommendation": self.recommendation,
            "timestamp": self.timestamp,
        }


@dataclass
class AllModuleStandardsAudit:
    by_module: Dict[str, ModuleStandardsAudit]
    avg_coverage_pct: float
    timestamp: str

    def to_dict(self):
        return {
            "by_module": {k: v.to_dict() for k, v in self.by_module.items()},
            "avg_coverage_pct": self.avg_coverage_pct,
            "timestamp": self.timestamp,
        }


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _belongs_to_module(engine_name: str, module_key: str) -> bool:
    """Check if an engine likely belongs to a module by keyword match."""
    domains = MODULE_STANDARD_DOMAINS.get(module_key, [])
    lower = engine_name.lower()
    return any(d in lower for d in domains)


def _pages_using_engine(engine_name: str) -> List[str]:
    """Return list of pages that import this engine."""
    pages = []
    for p in PAGES_DIR.glob("*.py"):
        try:
            text = p.read_text(encoding="utf-8")
            if (f"from utils.{engine_name}" in text
                or f"import utils.{engine_name}" in text):
                pages.append(p.name)
        except (OSError, UnicodeDecodeError):
            continue
    return pages


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════

def get_module_standards(module_key: str) -> List[StandardEntry]:
    """Return list of standards entries that apply to this module."""
    try:
        import sys
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from utils.standards_wiring_audit_engine import audit_engine_inventory
        inv = audit_engine_inventory()
    except Exception:
        return []

    entries: List[StandardEntry] = []
    classifications = getattr(inv, "classifications", [])
    for engine_cls in classifications:
        # EngineClassification dataclass fields:
        # name, loc, react_ready, classification, pages_using,
        # aggregators_using, other_engines_using, in_standards_registry,
        # standards_count
        name = getattr(engine_cls, "name", "")
        if not name or not _belongs_to_module(name, module_key):
            continue
        # Only include engines that are in the standards registry
        if not getattr(engine_cls, "in_standards_registry", False):
            continue
        state = getattr(engine_cls, "classification", "unknown")
        pages_using = list(getattr(engine_cls, "pages_using", []))
        entries.append(StandardEntry(
            standard_id=f"engine.{name}",
            name=f"{getattr(engine_cls, 'standards_count', 0)} standard(s)",
            engine=name,
            wired_state=state,
            pages_using=pages_using,
        ))
    return entries


def audit_module_standards_wiring(module_key: str) -> ModuleStandardsAudit:
    """Audit standards wiring for one module."""
    standards = get_module_standards(module_key)
    total = len(standards)
    wired = sum(1 for s in standards
               if s.wired_state in ("wired_direct",
                                    "wired_infrastructure",
                                    "wired_via_aggregator"))
    unwired = sum(1 for s in standards
                 if s.wired_state == "unwired_standalone")
    orphan = sum(1 for s in standards if s.wired_state == "orphan")
    coverage = (wired / total * 100) if total else 0.0

    if coverage >= 90:
        rec = (f"EXCELLENT: {coverage:.1f}% standards wired. "
              f"{unwired} unwired engine(s) to address.")
    elif coverage >= 70:
        rec = (f"GOOD: {coverage:.1f}% wired. Address {unwired} unwired "
              f"+ {orphan} orphan(s).")
    elif coverage >= 50:
        rec = (f"NEEDS WORK: only {coverage:.1f}% wired. Priority: "
              f"wire {unwired} unwired engine(s).")
    else:
        rec = (f"CRITICAL: {coverage:.1f}% wiring coverage. "
              f"{unwired} engines need page wiring.")

    return ModuleStandardsAudit(
        module_key=module_key,
        total_standards_for_module=total,
        wired_count=wired,
        unwired_count=unwired,
        orphan_count=orphan,
        wiring_coverage_pct=round(coverage, 1),
        standards=standards,
        recommendation=rec,
        timestamp=datetime.now().isoformat(),
    )


def audit_all_module_standards() -> AllModuleStandardsAudit:
    """Audit all 5 modules' standards wiring."""
    try:
        import sys
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from utils.module_doctrine_audit import MODULE_REGISTRY
        keys = list(MODULE_REGISTRY.keys())
    except Exception:
        keys = list(MODULE_STANDARD_DOMAINS.keys())

    by_module = {k: audit_module_standards_wiring(k) for k in keys}
    if by_module:
        avg = sum(m.wiring_coverage_pct for m in by_module.values()) / len(by_module)
    else:
        avg = 0.0
    return AllModuleStandardsAudit(
        by_module=by_module,
        avg_coverage_pct=round(avg, 1),
        timestamp=datetime.now().isoformat(),
    )


def generate_module_standards_doc(module_key: str) -> str:
    """Generate real <module>_standards_wiring.md content."""
    audit = audit_module_standards_wiring(module_key)
    today = datetime.now().strftime("%Y-%m-%d")
    out = f"# {module_key.upper()} — Standards Wiring Report\n\n"
    out += f"**Generated:** {today} (v10.460 real per-module audit)\n"
    out += f"**Module key:** `{module_key}`\n\n"
    out += "## Summary\n\n"
    out += f"- Total standards mapped to this module: **{audit.total_standards_for_module}**\n"
    out += f"- Wired engines: **{audit.wired_count}**\n"
    out += f"- Unwired standalone: **{audit.unwired_count}**\n"
    out += f"- Orphan (missing engine files): **{audit.orphan_count}**\n"
    out += f"- Wiring coverage: **{audit.wiring_coverage_pct}%**\n\n"
    out += f"## Recommendation\n\n{audit.recommendation}\n\n"

    if audit.standards:
        out += "## Standards & engine states\n\n"
        out += "| Standard | Engine | State | Pages using |\n|---|---|---|---|\n"
        for s in audit.standards[:30]:
            pages_str = ", ".join(f"`{p}`" for p in s.pages_using[:3])
            if len(s.pages_using) > 3:
                pages_str += f" + {len(s.pages_using) - 3} more"
            if not pages_str:
                pages_str = "_(none)_"
            out += (f"| {s.standard_id} {s.name[:30]} | "
                   f"`{s.engine}` | `{s.wired_state}` | {pages_str} |\n")
        if len(audit.standards) > 30:
            out += f"\n_({len(audit.standards) - 30} more standards "
            out += "— see standards_wiring_audit_engine for full list)_\n"
        out += "\n"

    out += "## Action items\n\n"
    if audit.unwired_count > 0:
        out += (f"- Wire {audit.unwired_count} standalone engine(s) into "
               f"this module's pages\n")
    if audit.orphan_count > 0:
        out += (f"- Investigate {audit.orphan_count} orphan(s) — "
               f"registry references missing engine file(s)\n")
    if audit.wiring_coverage_pct >= 90:
        out += "- Module standards wiring at excellent coverage; maintain\n"
    return out


if __name__ == "__main__":  # pragma: no cover
    print(f"{'Module':<14} {'Std':>5} {'Wired':>6} {'Unwired':>8} {'Orphan':>7} {'Coverage':>10}")
    a = audit_all_module_standards()
    for key, m in a.by_module.items():
        print(f"{key:<14} {m.total_standards_for_module:>5} "
              f"{m.wired_count:>6} {m.unwired_count:>8} "
              f"{m.orphan_count:>7} {m.wiring_coverage_pct:>9.1f}%")
    print(f"\nAvg coverage: {a.avg_coverage_pct}%")
