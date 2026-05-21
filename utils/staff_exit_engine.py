"""Staff Exit Risk Engine — v10.435 (target gap risk detection).

Per Joshua roadmap: after onboarding fit-in test, audit the inverse —
what happens when a staff exits? Which targets become orphaned? Who's
a single point of failure? How would peers absorb the gap?

This engine answers those questions. Five public functions:

  - audit_exit_risk(staff_code)            → StaffExitRisk
  - audit_all_exit_risks()                 → BankWideExitAudit
  - simulate_exit(staff_code)              → ExitSimulation (no writes)
  - simulate_redistribution(staff_code, strategy) → RedistributionPlan
  - rank_critical_staff(top_n)             → list of top-risk staff

Risk score (0-100) combines five dimensions:
  1. Outgoing cascade size (0-25): how many children depend on them
  2. Outgoing target value (0-20): how much $ flows through them
  3. Role uniqueness (0-25): how few peers can absorb
  4. Pillar criticality (0-15): if leaving leaves pillar gaps in unit
  5. Incoming reliance (0-15): how many parents/peers point at them

Bands: Critical (75+), High (50-74), Medium (25-49), Low (<25).

Redistribution strategies for simulating gap-fill:
  - "peer_split": distribute among role peers in same unit equally
  - "manager_absorb": push share up to their reporting manager
  - "hold_open": leave unassigned (creates documented gap)

Shipped: v10.435.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"

CANONICAL_PILLARS: Set[str] = {
    "Financial",
    "Customer Focus",
    "Operational Excellence",
    "People & Learning",
}

# Risk band thresholds
RISK_BAND_CRITICAL = 75
RISK_BAND_HIGH = 50
RISK_BAND_MEDIUM = 25

# Score component caps
SCORE_OUTGOING_CASCADE_MAX = 25
SCORE_OUTGOING_VALUE_MAX = 20
SCORE_ROLE_UNIQUENESS_MAX = 25
SCORE_PILLAR_CRITICALITY_MAX = 15
SCORE_INCOMING_RELIANCE_MAX = 15

ALLOWED_REDISTRIBUTION_STRATEGIES: Set[str] = {
    "peer_split", "manager_absorb", "hold_open",
}


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class StaffExitRisk:
    staff_code: str
    staff_name: str
    role: str
    unit: str
    # Cascade impact
    outgoing_cascade_entries: int
    outgoing_total_value: float
    outgoing_children_affected: int
    # Incoming cascade
    incoming_allocations: int
    incoming_total_value: float
    incoming_parent_codes: List[str]
    # BSC footprint
    bsc_row_count: int
    bsc_total_target_value: float
    bsc_unique_kpis: List[str]
    pillar_coverage: Dict[str, int]
    # Role criticality
    role_peer_count: int  # other staff with same role in bank
    role_peers_in_unit: int  # peers in same unit
    pillars_lost_if_exit: List[str]
    # Risk
    risk_score: float
    risk_band: str
    risk_drivers: List[str]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BankWideExitAudit:
    total_staff: int
    critical_risk_count: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    avg_risk_score: float
    critical_staff: List[Dict[str, Any]]
    high_staff: List[Dict[str, Any]]
    top_risk_drivers_global: Dict[str, int]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RedistributionPlan:
    staff_code: str
    staff_name: str
    strategy: str
    valid: bool
    receivers: List[Dict[str, Any]]   # [{code, name, added_target}]
    unassigned_value: float
    feasibility_pct: float            # 0-100, how much got absorbed
    warnings: List[str]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ExitSimulation:
    staff_code: str
    staff_name: str
    risk: StaffExitRisk
    redistribution_options: List[RedistributionPlan]
    recommended_strategy: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "staff_code": self.staff_code,
            "staff_name": self.staff_name,
            "risk": self.risk.to_dict(),
            "redistribution_options": [r.to_dict() for r in self.redistribution_options],
            "recommended_strategy": self.recommended_strategy,
            "timestamp": self.timestamp,
        }


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _find_actuals() -> Optional[Path]:
    if not DATA_DIR.exists():
        return None
    files = sorted(DATA_DIR.glob("actuals_*.xlsx"))
    return files[-1] if files else None


def _load_actuals_df() -> Optional["pandas.DataFrame"]:  # type: ignore
    import pandas as pd
    p = _find_actuals()
    if p is None:
        return None
    try:
        return pd.read_excel(p, skiprows=1)
    except Exception:  # noqa: BLE001
        return None


def _load_register() -> Optional["pandas.DataFrame"]:  # type: ignore
    import pandas as pd
    p = DATA_DIR / "staff_register.xlsx"
    if not p.exists():
        return None
    try:
        return pd.read_excel(p)
    except Exception:  # noqa: BLE001
        return None


# ════════════════════════════════════════════════════════════════════
# Risk scoring
# ════════════════════════════════════════════════════════════════════

def _score_outgoing_cascade(count: int) -> int:
    if count >= 16:
        return SCORE_OUTGOING_CASCADE_MAX  # 25
    if count >= 11:
        return 20
    if count >= 6:
        return 10
    return 0


def _score_outgoing_value(value: float) -> int:
    if value >= 10e9:
        return SCORE_OUTGOING_VALUE_MAX  # 20
    if value >= 1e9:
        return 15
    if value >= 100e6:
        return 10
    return 0


def _score_role_uniqueness(peer_count: int) -> int:
    if peer_count <= 1:
        return SCORE_ROLE_UNIQUENESS_MAX  # 25
    if peer_count <= 9:
        return 20
    if peer_count <= 29:
        return 10
    return 0


def _score_pillar_criticality(pillars_lost: int) -> int:
    if pillars_lost >= 2:
        return SCORE_PILLAR_CRITICALITY_MAX  # 15
    if pillars_lost == 1:
        return 10
    return 0


def _score_incoming_reliance(count: int) -> int:
    if count >= 10:
        return SCORE_INCOMING_RELIANCE_MAX  # 15
    if count >= 3:
        return 5
    return 0


def _risk_band(score: float) -> str:
    if score >= RISK_BAND_CRITICAL:
        return "Critical"
    if score >= RISK_BAND_HIGH:
        return "High"
    if score >= RISK_BAND_MEDIUM:
        return "Medium"
    return "Low"


# ════════════════════════════════════════════════════════════════════
# Per-staff audit
# ════════════════════════════════════════════════════════════════════

def audit_exit_risk(staff_code: str) -> StaffExitRisk:
    """Compute exit risk for a single staff."""
    code = str(staff_code).strip()

    df = _load_actuals_df()
    cascade = _load_json(DATA_DIR / "target_cascade.json")
    reg = _load_register()

    # Staff identity from BSC (or register)
    name = ""
    role = ""
    unit = ""
    if df is not None:
        df["_code_str"] = df["Staff Code"].astype(str).str.strip()
        rows = df[df["_code_str"] == code]
        if len(rows) > 0:
            name = str(rows.iloc[0]["Staff Name"])
            role = str(rows.iloc[0]["Role"])
            unit = str(rows.iloc[0]["Unit"])
    if not role and reg is not None:
        reg["_code"] = reg["Staff Code"].astype(str).str.strip()
        rrows = reg[reg["_code"] == code]
        if len(rrows) > 0:
            name = name or str(rrows.iloc[0].get("Staff Name", ""))
            role = role or str(rrows.iloc[0].get("Role", ""))
            unit = unit or str(rrows.iloc[0].get("Unit", ""))

    # Cascade analysis
    real_entries = {k: v for k, v in cascade.items()
                    if not k.startswith("_") and isinstance(v, dict)}

    outgoing_count = 0
    outgoing_value = 0.0
    children_affected: Set[str] = set()
    incoming_count = 0
    incoming_value = 0.0
    parent_codes: Set[str] = set()

    for entry in real_entries.values():
        from_code = str(entry.get("from_code", "")).strip()
        if from_code == code:
            outgoing_count += 1
            try:
                outgoing_value += float(entry.get("total_target", 0) or 0)
            except (ValueError, TypeError):
                pass
            for a in entry.get("allocations", []):
                if isinstance(a, dict):
                    children_affected.add(str(a.get("to_code", "")).strip())
        # Incoming
        for a in entry.get("allocations", []):
            if isinstance(a, dict):
                to_code = str(a.get("to_code", "")).strip()
                if to_code == code:
                    incoming_count += 1
                    try:
                        incoming_value += float(a.get("amount", 0) or 0)
                    except (ValueError, TypeError):
                        pass
                    parent_codes.add(from_code)

    # BSC footprint
    bsc_row_count = 0
    bsc_total_value = 0.0
    bsc_kpis: Set[str] = set()
    pillar_coverage: Dict[str, int] = {p: 0 for p in CANONICAL_PILLARS}

    if df is not None:
        rows = df[df["_code_str"] == code]
        bsc_row_count = len(rows)
        for _, r in rows.iterrows():
            try:
                bsc_total_value += float(r.get("Annual Target", 0) or 0)
            except (ValueError, TypeError):
                pass
            kpi = str(r.get("KPI", "")).strip()
            if kpi:
                bsc_kpis.add(kpi)
            pillar = str(r.get("Pillar", "")).strip()
            if pillar in pillar_coverage:
                pillar_coverage[pillar] += 1

    # Role criticality
    role_peer_count = 0
    role_peers_in_unit = 0
    pillars_lost: List[str] = []

    if df is not None and role:
        # peers in bank with same role (excluding self)
        peers = df[df["Role"] == role]["_code_str"].unique()
        role_peer_count = max(len(peers) - 1, 0)
        # peers in unit
        unit_peers = df[(df["Role"] == role) & (df["Unit"] == unit)]["_code_str"].unique()
        role_peers_in_unit = max(len(unit_peers) - 1, 0)

        # Pillars lost: pillars where this staff is the only contributor in their unit
        if unit:
            unit_rows = df[df["Unit"] == unit]
            for pillar in CANONICAL_PILLARS:
                # Pillar coverage in unit excluding this staff
                others = unit_rows[
                    (unit_rows["_code_str"] != code)
                    & (unit_rows["Pillar"] == pillar)
                ]
                if pillar_coverage.get(pillar, 0) > 0 and len(others) == 0:
                    pillars_lost.append(pillar)

    # Risk score
    s_out_cascade = _score_outgoing_cascade(outgoing_count)
    s_out_value = _score_outgoing_value(outgoing_value)
    s_role_unique = _score_role_uniqueness(role_peer_count)
    s_pillar_crit = _score_pillar_criticality(len(pillars_lost))
    s_in_reliance = _score_incoming_reliance(incoming_count)

    risk_score = float(
        s_out_cascade + s_out_value + s_role_unique
        + s_pillar_crit + s_in_reliance
    )
    band = _risk_band(risk_score)

    drivers: List[str] = []
    if s_out_cascade >= 10:
        drivers.append(f"Cascades to {outgoing_count} entries")
    if s_out_value >= 10:
        if outgoing_value >= 1e9:
            drivers.append(f"Owns KES {outgoing_value/1e9:.1f}B+ in flows")
        else:
            drivers.append(f"Owns KES {outgoing_value/1e6:.0f}M+ in flows")
    if s_role_unique >= 20:
        drivers.append(f"Only {role_peer_count + 1} of this role")
    if s_pillar_crit >= 10:
        drivers.append(f"Sole pillar contributor: {pillars_lost}")
    if s_in_reliance >= 5:
        drivers.append(f"{incoming_count} parents/peers allocate to them")

    return StaffExitRisk(
        staff_code=code,
        staff_name=name,
        role=role,
        unit=unit,
        outgoing_cascade_entries=outgoing_count,
        outgoing_total_value=round(outgoing_value, 2),
        outgoing_children_affected=len(children_affected),
        incoming_allocations=incoming_count,
        incoming_total_value=round(incoming_value, 2),
        incoming_parent_codes=sorted(parent_codes),
        bsc_row_count=bsc_row_count,
        bsc_total_target_value=round(bsc_total_value, 2),
        bsc_unique_kpis=sorted(bsc_kpis),
        pillar_coverage=pillar_coverage,
        role_peer_count=role_peer_count,
        role_peers_in_unit=role_peers_in_unit,
        pillars_lost_if_exit=pillars_lost,
        risk_score=round(risk_score, 1),
        risk_band=band,
        risk_drivers=drivers,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Bank-wide audit
# ════════════════════════════════════════════════════════════════════

def audit_all_exit_risks() -> BankWideExitAudit:
    """Bank-wide exit risk audit across all staff. Optimized to load data once."""
    df = _load_actuals_df()
    cascade = _load_json(DATA_DIR / "target_cascade.json")
    if df is None:
        return BankWideExitAudit(
            0, 0, 0, 0, 0, 0.0, [], [], {},
            datetime.now().isoformat(),
        )

    df["_code_str"] = df["Staff Code"].astype(str).str.strip()

    # Pre-compute cascade lookups
    real_entries = {k: v for k, v in cascade.items()
                    if not k.startswith("_") and isinstance(v, dict)}
    outgoing_count: Dict[str, int] = {}
    outgoing_value: Dict[str, float] = {}
    outgoing_children: Dict[str, Set[str]] = {}
    incoming_count: Dict[str, int] = {}
    incoming_value: Dict[str, float] = {}
    incoming_parents: Dict[str, Set[str]] = {}
    for entry in real_entries.values():
        from_code = str(entry.get("from_code", "")).strip()
        try:
            tt = float(entry.get("total_target", 0) or 0)
        except (ValueError, TypeError):
            tt = 0.0
        if from_code:
            outgoing_count[from_code] = outgoing_count.get(from_code, 0) + 1
            outgoing_value[from_code] = outgoing_value.get(from_code, 0.0) + tt
            outgoing_children.setdefault(from_code, set())
            for a in entry.get("allocations", []):
                if isinstance(a, dict):
                    to_code = str(a.get("to_code", "")).strip()
                    outgoing_children[from_code].add(to_code)
        for a in entry.get("allocations", []):
            if isinstance(a, dict):
                to_code = str(a.get("to_code", "")).strip()
                try:
                    amt = float(a.get("amount", 0) or 0)
                except (ValueError, TypeError):
                    amt = 0.0
                incoming_count[to_code] = incoming_count.get(to_code, 0) + 1
                incoming_value[to_code] = incoming_value.get(to_code, 0.0) + amt
                incoming_parents.setdefault(to_code, set()).add(from_code)

    # Pre-compute role peer counts globally
    role_peers: Dict[str, int] = (
        df["Role"].value_counts().to_dict()
    )

    # Pre-compute (Role, Unit) peer counts
    role_unit_peers: Dict[Tuple[str, str], int] = {}
    for (r, u), n in df.groupby(["Role", "Unit"]).size().items():
        role_unit_peers[(r, u)] = n

    # Pre-compute unit pillar coverage
    unit_pillar_contributors: Dict[Tuple[str, str], Set[str]] = {}
    for _, row in df.iterrows():
        u = str(row["Unit"]).strip()
        p = str(row.get("Pillar", "")).strip()
        c = row["_code_str"]
        if p in CANONICAL_PILLARS and u:
            unit_pillar_contributors.setdefault((u, p), set()).add(c)

    # BSC rows per staff
    bsc_by_code = {}
    for code, group in df.groupby("_code_str"):
        bsc_by_code[code] = group

    all_codes = sorted(df["_code_str"].dropna().unique())

    critical_count = 0
    high_count = 0
    medium_count = 0
    low_count = 0
    scores_sum = 0.0
    critical_staff: List[Dict[str, Any]] = []
    high_staff: List[Dict[str, Any]] = []
    drivers_global: Dict[str, int] = {}

    for code in all_codes:
        # Identity
        rows = bsc_by_code.get(code)
        if rows is None or len(rows) == 0:
            continue
        first = rows.iloc[0]
        name = str(first["Staff Name"])
        role = str(first["Role"])
        unit = str(first["Unit"])

        # Cascade
        out_cnt = outgoing_count.get(code, 0)
        out_val = outgoing_value.get(code, 0.0)
        in_cnt = incoming_count.get(code, 0)

        # Role peers (subtract self)
        peers = max(role_peers.get(role, 1) - 1, 0)

        # Pillars at risk
        pillars_lost: List[str] = []
        for pillar in CANONICAL_PILLARS:
            contribs = unit_pillar_contributors.get((unit, pillar), set())
            if code in contribs and len(contribs) == 1:
                # This staff is the sole contributor in this unit for this pillar
                # AND they have a row for it (they're in contribs because they have a row)
                pillars_lost.append(pillar)

        # Score
        s_out_c = _score_outgoing_cascade(out_cnt)
        s_out_v = _score_outgoing_value(out_val)
        s_role = _score_role_uniqueness(peers)
        s_pill = _score_pillar_criticality(len(pillars_lost))
        s_in = _score_incoming_reliance(in_cnt)
        score = float(s_out_c + s_out_v + s_role + s_pill + s_in)
        band = _risk_band(score)
        scores_sum += score

        # Drivers
        drivers: List[str] = []
        if s_out_c >= 10:
            drivers.append("outgoing_cascade")
        if s_out_v >= 10:
            drivers.append("outgoing_value")
        if s_role >= 20:
            drivers.append("role_unique")
        if s_pill >= 10:
            drivers.append("pillar_sole_contributor")
        if s_in >= 5:
            drivers.append("incoming_reliance")
        for d in drivers:
            drivers_global[d] = drivers_global.get(d, 0) + 1

        if band == "Critical":
            critical_count += 1
            critical_staff.append({
                "code": code, "name": name, "role": role, "unit": unit,
                "score": round(score, 1),
                "drivers": drivers,
            })
        elif band == "High":
            high_count += 1
            high_staff.append({
                "code": code, "name": name, "role": role, "unit": unit,
                "score": round(score, 1),
                "drivers": drivers,
            })
        elif band == "Medium":
            medium_count += 1
        else:
            low_count += 1

    total = len(all_codes)
    avg = scores_sum / total if total > 0 else 0.0

    # Sort hot lists
    critical_staff.sort(key=lambda x: -x["score"])
    high_staff.sort(key=lambda x: -x["score"])

    return BankWideExitAudit(
        total_staff=total,
        critical_risk_count=critical_count,
        high_risk_count=high_count,
        medium_risk_count=medium_count,
        low_risk_count=low_count,
        avg_risk_score=round(avg, 2),
        critical_staff=critical_staff[:20],
        high_staff=high_staff[:20],
        top_risk_drivers_global=dict(
            sorted(drivers_global.items(), key=lambda x: -x[1])
        ),
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Redistribution simulation
# ════════════════════════════════════════════════════════════════════

def simulate_redistribution(
    staff_code: str,
    strategy: str,
) -> RedistributionPlan:
    """Model how to redistribute a staff's targets when they exit."""
    code = str(staff_code).strip()
    if strategy not in ALLOWED_REDISTRIBUTION_STRATEGIES:
        return RedistributionPlan(
            staff_code=code, staff_name="", strategy=strategy,
            valid=False, receivers=[], unassigned_value=0.0,
            feasibility_pct=0.0,
            warnings=[f"strategy '{strategy}' not allowed. "
                     f"Choose from: {sorted(ALLOWED_REDISTRIBUTION_STRATEGIES)}"],
            timestamp=datetime.now().isoformat(),
        )

    df = _load_actuals_df()
    reg = _load_register()
    cascade = _load_json(DATA_DIR / "target_cascade.json")
    if df is None:
        return RedistributionPlan(
            staff_code=code, staff_name="", strategy=strategy,
            valid=False, receivers=[], unassigned_value=0.0,
            feasibility_pct=0.0,
            warnings=["BSC data not available"],
            timestamp=datetime.now().isoformat(),
        )

    df["_code_str"] = df["Staff Code"].astype(str).str.strip()
    rows = df[df["_code_str"] == code]
    if len(rows) == 0:
        return RedistributionPlan(
            staff_code=code, staff_name="", strategy=strategy,
            valid=False, receivers=[], unassigned_value=0.0,
            feasibility_pct=0.0,
            warnings=[f"staff {code} not in BSC"],
            timestamp=datetime.now().isoformat(),
        )

    first = rows.iloc[0]
    name = str(first["Staff Name"])
    role = str(first["Role"])
    unit = str(first["Unit"])

    # Total value to redistribute = staff's BSC annual target sum
    total_value = 0.0
    for _, r in rows.iterrows():
        try:
            total_value += float(r.get("Annual Target", 0) or 0)
        except (ValueError, TypeError):
            pass

    warnings: List[str] = []
    receivers: List[Dict[str, Any]] = []

    if strategy == "hold_open":
        return RedistributionPlan(
            staff_code=code, staff_name=name, strategy=strategy,
            valid=True, receivers=[],
            unassigned_value=round(total_value, 2),
            feasibility_pct=0.0,
            warnings=[
                f"Vacancy creates KES {total_value:,.0f} unassigned target. "
                f"Pillar coverage may degrade until role refilled."
            ],
            timestamp=datetime.now().isoformat(),
        )

    if strategy == "peer_split":
        # Find peers in same role + same unit
        peers_df = df[(df["Role"] == role) & (df["Unit"] == unit) & (df["_code_str"] != code)]
        peer_codes = sorted(peers_df["_code_str"].unique())
        if not peer_codes:
            # Try unit-only peers
            peers_df = df[(df["Unit"] == unit) & (df["_code_str"] != code)]
            peer_codes = sorted(peers_df["_code_str"].unique())
            if peer_codes:
                warnings.append(
                    f"No same-role peers in unit; splitting among {len(peer_codes)} unit peers"
                )
        if not peer_codes:
            return RedistributionPlan(
                staff_code=code, staff_name=name, strategy=strategy,
                valid=False, receivers=[], unassigned_value=total_value,
                feasibility_pct=0.0,
                warnings=["No peers found in role or unit; can't peer-split"],
                timestamp=datetime.now().isoformat(),
            )
        share = total_value / len(peer_codes)
        for pc in peer_codes:
            prow = df[df["_code_str"] == pc].iloc[0]
            receivers.append({
                "code": pc,
                "name": str(prow["Staff Name"]),
                "role": str(prow["Role"]),
                "added_target": round(share, 2),
            })
        return RedistributionPlan(
            staff_code=code, staff_name=name, strategy=strategy,
            valid=True, receivers=receivers,
            unassigned_value=0.0,
            feasibility_pct=100.0,
            warnings=warnings,
            timestamp=datetime.now().isoformat(),
        )

    if strategy == "manager_absorb":
        # Find manager via Reports To in register
        manager_code = ""
        if reg is not None:
            reg["_code"] = reg["Staff Code"].astype(str).str.strip()
            mrow = reg[reg["_code"] == code]
            if len(mrow) > 0:
                manager_code = str(mrow.iloc[0].get("Reports To", "")).strip()
        if not manager_code:
            return RedistributionPlan(
                staff_code=code, staff_name=name, strategy=strategy,
                valid=False, receivers=[], unassigned_value=total_value,
                feasibility_pct=0.0,
                warnings=["No 'Reports To' manager set in register"],
                timestamp=datetime.now().isoformat(),
            )
        mrow_bsc = df[df["_code_str"] == manager_code]
        if len(mrow_bsc) == 0:
            return RedistributionPlan(
                staff_code=code, staff_name=name, strategy=strategy,
                valid=False, receivers=[], unassigned_value=total_value,
                feasibility_pct=0.0,
                warnings=[f"Manager {manager_code} not in BSC"],
                timestamp=datetime.now().isoformat(),
            )
        receivers.append({
            "code": manager_code,
            "name": str(mrow_bsc.iloc[0]["Staff Name"]),
            "role": str(mrow_bsc.iloc[0]["Role"]),
            "added_target": round(total_value, 2),
        })
        warnings.append("Manager will carry the full additional target until role refilled")
        return RedistributionPlan(
            staff_code=code, staff_name=name, strategy=strategy,
            valid=True, receivers=receivers,
            unassigned_value=0.0,
            feasibility_pct=100.0,
            warnings=warnings,
            timestamp=datetime.now().isoformat(),
        )

    # Fallback (shouldn't reach)
    return RedistributionPlan(
        staff_code=code, staff_name=name, strategy=strategy,
        valid=False, receivers=[], unassigned_value=total_value,
        feasibility_pct=0.0,
        warnings=["Unknown error"],
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Full exit simulation
# ════════════════════════════════════════════════════════════════════

def simulate_exit(staff_code: str) -> ExitSimulation:
    """Full exit simulation: risk audit + 3 redistribution scenarios."""
    risk = audit_exit_risk(staff_code)

    plans = [
        simulate_redistribution(staff_code, "peer_split"),
        simulate_redistribution(staff_code, "manager_absorb"),
        simulate_redistribution(staff_code, "hold_open"),
    ]

    # Recommended: peer_split if valid, else manager_absorb, else hold_open
    recommended = "hold_open"
    for p in plans:
        if p.strategy == "peer_split" and p.valid:
            recommended = "peer_split"
            break
    else:
        for p in plans:
            if p.strategy == "manager_absorb" and p.valid:
                recommended = "manager_absorb"
                break

    return ExitSimulation(
        staff_code=risk.staff_code,
        staff_name=risk.staff_name,
        risk=risk,
        redistribution_options=plans,
        recommended_strategy=recommended,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ staff_exit_engine self-test ─")

    text = Path(__file__).read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports")

    assert SCORE_OUTGOING_CASCADE_MAX == 25
    assert sum([SCORE_OUTGOING_CASCADE_MAX, SCORE_OUTGOING_VALUE_MAX,
                SCORE_ROLE_UNIQUENESS_MAX, SCORE_PILLAR_CRITICALITY_MAX,
                SCORE_INCOMING_RELIANCE_MAX]) == 100
    print("  ✓ Risk score caps sum to 100")

    # Score functions
    assert _score_outgoing_cascade(0) == 0
    assert _score_outgoing_cascade(20) == 25
    assert _risk_band(80) == "Critical"
    assert _risk_band(60) == "High"
    assert _risk_band(30) == "Medium"
    assert _risk_band(10) == "Low"
    print("  ✓ Score + banding functions")

    # Per-staff audit on MD
    md = audit_exit_risk("300001")
    print(f"\n  MD exit risk (300001):")
    print(f"    Name:     {md.staff_name}")
    print(f"    Role:     {md.role}")
    print(f"    Outgoing: {md.outgoing_cascade_entries} entries, "
          f"KES {md.outgoing_total_value/1e9:.1f}B")
    print(f"    Incoming: {md.incoming_allocations} allocations")
    print(f"    Children affected: {md.outgoing_children_affected}")
    print(f"    Role peers (bank-wide): {md.role_peer_count}")
    print(f"    Pillars lost if exit:  {md.pillars_lost_if_exit}")
    print(f"    Risk score: {md.risk_score} ({md.risk_band})")
    print(f"    Drivers: {md.risk_drivers}")

    # Branch Manager (Kelvin Ndung'u)
    bm = audit_exit_risk("300277")
    print(f"\n  Branch Manager exit risk (300277):")
    print(f"    Name:     {bm.staff_name}")
    print(f"    Outgoing: {bm.outgoing_cascade_entries} entries")
    print(f"    Risk score: {bm.risk_score} ({bm.risk_band})")
    print(f"    Drivers: {bm.risk_drivers}")

    # A Teller (should be lower risk - many peers)
    tellers_df = None
    try:
        import pandas as pd
        df = pd.read_excel('data/actuals_2025_Dec_25.xlsx', skiprows=1)
        df['_c'] = df['Staff Code'].astype(str).str.strip()
        teller_codes = df[df['Role'] == 'Teller']['_c'].unique()
        if len(teller_codes) > 0:
            tc = teller_codes[0]
            tr = audit_exit_risk(tc)
            print(f"\n  Teller exit risk ({tc}):")
            print(f"    Outgoing: {tr.outgoing_cascade_entries} entries")
            print(f"    Role peers: {tr.role_peer_count}")
            print(f"    Risk score: {tr.risk_score} ({tr.risk_band})")
    except Exception as e:
        print(f"  Teller test skipped: {e}")

    # Redistribution
    print(f"\n  Redistribution for Branch Manager (300277):")
    for strat in ["peer_split", "manager_absorb", "hold_open"]:
        plan = simulate_redistribution("300277", strat)
        n = len(plan.receivers)
        print(f"    {strat:18}: valid={plan.valid}, receivers={n}, "
              f"unassigned={plan.unassigned_value:,.0f}")

    # Full simulation
    sim = simulate_exit("300277")
    print(f"\n  Full exit simulation (300277):")
    print(f"    Risk score:       {sim.risk.risk_score}")
    print(f"    Recommended:      {sim.recommended_strategy}")
    print(f"    Option count:     {len(sim.redistribution_options)}")

    # Bank-wide
    print(f"\n  Bank-wide exit risk audit:")
    full = audit_all_exit_risks()
    print(f"    Total staff:     {full.total_staff}")
    print(f"    Critical risk:   {full.critical_risk_count}")
    print(f"    High risk:       {full.high_risk_count}")
    print(f"    Medium risk:     {full.medium_risk_count}")
    print(f"    Low risk:        {full.low_risk_count}")
    print(f"    Avg risk score:  {full.avg_risk_score}")
    print(f"    Top drivers:     {full.top_risk_drivers_global}")
    print(f"    Top 3 critical:")
    for s in full.critical_staff[:3]:
        print(f"      {s['code']} {s['name']:25} ({s['role'][:30]}) score={s['score']}")

    # JSON
    json.dumps(full.to_dict())
    json.dumps(sim.to_dict())
    print(f"\n  ✓ JSON-serializable")

    print("\n✓ self_test passed")


if __name__ == "__main__":
    self_test()
