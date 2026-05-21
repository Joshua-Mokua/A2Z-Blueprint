"""utils/super_user_registry.py — v10.459 Super User Registry.

Per Joshua doctrine Phase 4 Workflow Alignment + v10.456 directive:
"we even had mapped a second level of system admin from the supper
user to come from ICT". Plus Phase 4 WF5 (super user per module) and
WF6 (escalation paths).

This module is the canonical registry for super_user permissions
across all 5 organs. Each organ has:
  - A primary super_user (executive)
  - A 2nd-level super_user (escalation)
  - An ICT Super User (cross-organ admin per Joshua doctrine)

The escalation_path is canonical: any operational alert may be
escalated to the relevant super_user within seconds via the event_bus.

Public API (API-first, ZERO streamlit):
  - get_super_user(organ_key) -> SuperUserConfig
  - list_super_users() -> List[SuperUserConfig]
  - escalate(organ_key, reason) -> EscalationRecord
  - get_escalation_path(organ_key) -> List[str]
  - is_super_user(staff_code) -> bool
  - audit_super_user_coverage() -> SuperUserCoverage

Shipped: v10.459.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"


# Canonical super_user mapping per organ.
# Per Joshua: ICT Super User is the 2nd-level admin across all organs.
SUPER_USER_MAP: Dict[str, Dict[str, Any]] = {
    "admin": {
        "primary_role": "Admin Super User",
        "primary_title": "Chief Operating Officer / Admin Super User",
        "secondary_role": "ICT Super User",
        "escalation_path": [
            "Admin Operator",
            "Admin Super User",
            "ICT Super User",  # 2nd-level admin per Joshua
            "MD",
        ],
        "notes": "Admin organ super_user is COO; escalation via ICT.",
    },
    "hr": {
        "primary_role": "Chief Human Resources Officer",
        "primary_title": "CHRO / HR Super User",
        "secondary_role": "ICT Super User",
        "escalation_path": [
            "HR Business Partner",
            "Head of HR",
            "Chief Human Resources Officer",
            "ICT Super User",
            "MD",
        ],
        "notes": "HR organ super_user is CHRO; ICT Super User handles "
                "system-level escalations.",
    },
    "bsc_cascade": {
        "primary_role": "MD",
        "primary_title": "MD / BSC Super User",
        "secondary_role": "ICT Super User",
        "escalation_path": [
            "Director Retail Banking / Director Commercial Banking",
            "MD",
            "ICT Super User",
        ],
        "notes": "BSC organ super_user is the MD; cascade integrity "
                "issues escalate to ICT Super User.",
    },
    "credit": {
        "primary_role": "Chief Credit Officer",
        "primary_title": "CCO / Credit Super User",
        "secondary_role": "ICT Super User",
        "escalation_path": [
            "Credit Analyst",
            "Senior Credit Analyst",
            "Head of Credit",
            "Chief Credit Officer",
            "ICT Super User",
            "MD",
        ],
        "notes": "Credit organ super_user is CCO; system-level issues "
                "(e.g. NPL data feed) escalate to ICT Super User.",
    },
    "ict": {
        "primary_role": "ICT Super User",
        "primary_title": "Chief Information Officer / ICT Super User",
        "secondary_role": "Chief Technology Officer",
        "escalation_path": [
            "Systems Administrator",
            "IT Manager",
            "ICT Super User",  # 2nd-level admin per Joshua
            "Chief Information Officer",
            "MD",
        ],
        "notes": "ICT organ super_user is the canonical 2nd-level admin "
                "per Joshua doctrine; serves as escalation point for "
                "ALL other organs' system-level issues.",
    },
    # v10.461 + v10.463 - Finance Chief (Chief Financial Officer per
    # actual users.json; covers BOTH finance + treasury per Joshua).
    "finance": {
        "primary_role": "Chief Financial Officer",  # Actual in users.json
        "primary_title": "CFO / Finance Super User",
        "secondary_role": "ICT Super User",
        "escalation_path": [
            "Finance Officer",
            "Finance Manager & Money Laundering Reporting Officer",
            "Chief Financial Officer",  # Actual title
            "ICT Super User",
            "Chief Executive & Managing Director",
        ],
        "notes": "Finance organ super_user is CFO (Chief Financial "
                "Officer per actual users.json); CFO command centre "
                "covers BOTH finance and treasury per Joshua doctrine.",
    },
    # v10.461 + v10.463 - Treasury Head (stand-alone with own head per
    # Joshua; reports up to CFO).
    "treasury": {
        "primary_role": "Head of Treasury",  # Actual in users.json
        "primary_title": "Head of Treasury / Treasury Super User",
        "secondary_role": "Chief Financial Officer",
        "escalation_path": [
            "Treasury Dealer",
            "Treasury Front Office Officer",
            "Senior Manager Treasury",  # Actual
            "Head of Treasury",
            "Chief Financial Officer",  # Reports up to CFO
            "ICT Super User",
            "Chief Executive & Managing Director",
        ],
        "notes": "Treasury organ has its own Head + dedicated command "
                "centre per Joshua; reports up to CFO.",
    },
    # v10.461 + v10.463 - Legal Chief (actual title from users.json:
    # 'Company Secretary and Chief Legal Officer'; Joshua said Company
    # Secretary IS the Chief).
    "legal": {
        "primary_role": "Company Secretary and Chief Legal Officer",
        "primary_title": "Company Secretary / Legal Super User",
        "secondary_role": "ICT Super User",
        "escalation_path": [
            "Legal Officer",
            "Manager- Legal",  # Actual
            "Company Secretary and Chief Legal Officer",  # Actual chief
            "ICT Super User",
            "Chief Executive & Managing Director",
            "Board",
        ],
        "notes": "Legal organ chief is the Company Secretary (actual "
                "users.json title: 'Company Secretary and Chief Legal "
                "Officer'); escalation continues to the Board for "
                "governance matters.",
    },
    # v10.461 + v10.463 - Risk Chief (CRO covers BOTH risk +
    # compliance per Joshua; mirrors CFO finance+treasury pattern).
    "risk": {
        "primary_role": "Chief Risk Officer",  # Actual in users.json
        "primary_title": "CRO / Risk Super User",
        "secondary_role": "ICT Super User",
        "escalation_path": [
            "Risk Manager",              # Actual
            "Operational Risk Manager",  # Actual
            "Chief Risk Officer",
            "ICT Super User",
            "Chief Executive & Managing Director",
        ],
        "notes": "Risk organ chief is CRO; CRO command centre covers "
                "BOTH risk and compliance per Joshua doctrine "
                "(mirrors CFO finance+treasury pattern).",
    },
    # v10.461 + v10.463 - Compliance Head (sub-organ; reports to CRO).
    "compliance": {
        "primary_role": "Senior Manager- Compliance",  # Actual in users.json
        "primary_title": "Head of Compliance / Compliance Super User",
        "secondary_role": "Chief Risk Officer",
        "escalation_path": [
            "Regulatory Compliance Officer",  # Actual
            "Senior Manager- Compliance",     # Actual head
            "Chief Risk Officer",             # Reports up to CRO
            "ICT Super User",
            "Chief Executive & Managing Director",
        ],
        "notes": "Compliance organ has its own Head (actual title: "
                "'Senior Manager- Compliance') + dedicated centre per "
                "Joshua; reports up to CRO.",
    },
}


@dataclass
class SuperUserConfig:
    organ_key: str
    primary_role: str
    primary_title: str
    secondary_role: str
    escalation_path: List[str]
    notes: str

    def to_dict(self): return asdict(self)


@dataclass
class EscalationRecord:
    organ_key: str
    reason: str
    escalation_chain: List[str]
    timestamp: str
    severity: str = "warning"

    def to_dict(self): return asdict(self)


@dataclass
class SuperUserCoverage:
    total_organs: int
    organs_with_super_user: int
    organs_with_ict_secondary: int
    coverage_pct: float
    timestamp: str

    def to_dict(self): return asdict(self)


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════

def get_super_user(organ_key: str) -> Optional[SuperUserConfig]:
    """Return the super_user config for an organ."""
    info = SUPER_USER_MAP.get(organ_key)
    if info is None:
        return None
    return SuperUserConfig(
        organ_key=organ_key,
        primary_role=info["primary_role"],
        primary_title=info["primary_title"],
        secondary_role=info["secondary_role"],
        escalation_path=info["escalation_path"],
        notes=info["notes"],
    )


def list_super_users() -> List[SuperUserConfig]:
    """List super_users across all 5 organs."""
    return [get_super_user(k) for k in SUPER_USER_MAP]


def escalate(organ_key: str, reason: str,
             severity: str = "warning") -> EscalationRecord:
    """Trigger an escalation_path. Publishes event via event_bus."""
    cfg = get_super_user(organ_key)
    chain = cfg.escalation_path if cfg else [organ_key]
    record = EscalationRecord(
        organ_key=organ_key,
        reason=reason,
        escalation_chain=chain,
        severity=severity,
        timestamp=datetime.now().isoformat(),
    )
    # Publish via event_bus
    try:
        import sys
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from utils.cross_organ_event_bus import publish_event
        publish_event(
            "workload.escalation_triggered",
            source_organ=organ_key,
            payload={"reason": reason, "chain": chain},
            severity=severity,
        )
    except Exception:
        pass
    return record


def get_escalation_path(organ_key: str) -> List[str]:
    """Return the canonical escalation_path for an organ."""
    cfg = get_super_user(organ_key)
    return cfg.escalation_path if cfg else []


def is_super_user(staff_code: str) -> bool:
    """Check if a staff_code maps to any super_user role."""
    users_file = DATA_DIR / "users.json"
    if not users_file.exists():
        return False
    try:
        data = json.loads(users_file.read_text(encoding="utf-8"))
        users = data.get("users", data) if isinstance(data, dict) else data
        if not isinstance(users, list):
            users = list(data.values()) if isinstance(data, dict) else []
        all_super_roles = set()
        for info in SUPER_USER_MAP.values():
            all_super_roles.add(info["primary_role"])
            all_super_roles.add(info["secondary_role"])
        for u in users:
            if not isinstance(u, dict):
                continue
            if u.get("staff_code") == staff_code:
                return u.get("role") in all_super_roles
    except Exception:
        pass
    return False


def audit_super_user_coverage() -> SuperUserCoverage:
    """Audit super_user + escalation_path coverage."""
    total = len(SUPER_USER_MAP)
    with_super = sum(1 for v in SUPER_USER_MAP.values()
                    if v.get("primary_role"))
    with_ict = sum(1 for v in SUPER_USER_MAP.values()
                  if "ICT Super User" in v.get("escalation_path", []))
    pct = (with_super / total * 100) if total else 0.0
    return SuperUserCoverage(
        total_organs=total,
        organs_with_super_user=with_super,
        organs_with_ict_secondary=with_ict,
        coverage_pct=round(pct, 1),
        timestamp=datetime.now().isoformat(),
    )


if __name__ == "__main__":  # pragma: no cover
    for su in list_super_users():
        print(f"  {su.organ_key}: primary={su.primary_role}")
        print(f"    escalation_path: {' → '.join(su.escalation_path)}")

    cov = audit_super_user_coverage()
    print(f"\nCoverage: {cov.coverage_pct}% — "
          f"{cov.organs_with_ict_secondary}/{cov.total_organs} have "
          f"ICT Super User in escalation_path")
