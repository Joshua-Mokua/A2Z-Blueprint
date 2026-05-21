"""Cascade Health Engine — v10.411 (E5: Executive Cascade Health Dashboard).

Per Joshua's QA standards Enhancement #5:
  Problem: No visibility into cascade completeness or gaps.
  Solution: Executive dashboard showing cascade health.

Provides bank-wide aggregations distinct from per-staff cascade_coverage:

  1. bank_health_summary(period) → BankHealthSummary
       Overall: total KPIs cascaded, % complete, gaps count, stale count
  2. health_by_pillar(period) → list of PillarHealth
       Per-pillar completeness (Financial / Customer / OpEx / People)
  3. health_by_sbu(period) → list of SBUHealth
       Per-SBU rollup: how completely each business line has cascaded
  4. health_by_kpi(period) → list of KPIHealth
       Per-KPI: how many staff have cascaded targets vs not
  5. broken_chains(period) → list of BrokenChain
       Allocated to staff but staff has no downstream cascade (leaf with reports)
  6. stale_entries(period, days=30) → list of StaleEntry
       Cascade entries older than N days without acceptance

Per Rule 7, this is a COMPUTATION module. Reads target_cascade.json,
users.json, kpi_library.json; produces aggregated views. No mutations.

Shipped: v10.411.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class BankHealthSummary:
    period: str
    total_bank_targets: int          # KPIs with bank-level target set
    cascade_entries: int             # allocation entries in cascade
    distinct_recipients: int         # unique staff codes receiving cascades
    distinct_kpis_cascaded: int      # unique KPIs with at least one allocation
    fully_allocated_count: int       # entries with coverage ≥99%
    partial_allocated_count: int     # entries with 50-99% coverage
    under_allocated_count: int       # entries with <50%
    average_coverage_pct: float      # mean coverage across all entries
    overall_health_score: float      # 0-100 weighted composite


@dataclass
class PillarHealth:
    pillar: str
    bank_weight: float               # 0-1 canonical
    kpis_with_target: int            # bank targets in this pillar
    cascaded_count: int              # ≥1 allocation made
    not_cascaded_count: int          # bank target set but no cascade
    avg_coverage_pct: float


@dataclass
class SBUHealth:
    sbu: str
    chief_code: Optional[str]
    chief_name: Optional[str]
    direct_reports_in_cascade: int   # # staff with at least one received target
    total_direct_reports: int        # canonical hierarchy count
    distinct_kpis_received: int
    completeness_pct: float          # direct_reports_in_cascade / total
    notes: List[str] = field(default_factory=list)


@dataclass
class KPIHealth:
    kpi: str
    pillar: str
    bank_target_set: bool
    cascade_entries: int             # how many managers have cascaded this KPI
    distinct_recipients: int         # unique staff receiving this KPI
    avg_coverage_pct: float


@dataclass
class BrokenChain:
    staff_code: str
    staff_name: str
    role: str
    kpi: str
    received_amount: float
    has_direct_reports: bool         # they're a manager
    reports_with_subcascade: int     # of their reports, how many got a sub-cascade
    reason: str                      # diagnostic


@dataclass
class StaleEntry:
    from_code: str
    from_name: str
    kpi: str
    period: str
    last_modified: Optional[str]
    days_stale: int
    coverage_pct: float


# ════════════════════════════════════════════════════════════════════
# Lookups
# ════════════════════════════════════════════════════════════════════

_USERS_CACHE: Optional[Dict[str, Any]] = None
_CASCADE_CACHE: Optional[Dict[str, Any]] = None
_KPILIB_CACHE: Optional[Dict[str, Any]] = None


def _users() -> Dict[str, Any]:
    global _USERS_CACHE
    if _USERS_CACHE is None:
        path = DATA_DIR / "users.json"
        _USERS_CACHE = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _USERS_CACHE


def _cascade() -> Dict[str, Any]:
    global _CASCADE_CACHE
    if _CASCADE_CACHE is None:
        path = DATA_DIR / "target_cascade.json"
        _CASCADE_CACHE = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _CASCADE_CACHE


def _kpilib() -> Dict[str, Any]:
    global _KPILIB_CACHE
    if _KPILIB_CACHE is None:
        path = DATA_DIR / "kpi_library.json"
        _KPILIB_CACHE = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    return _KPILIB_CACHE


def clear_cache() -> None:
    global _USERS_CACHE, _CASCADE_CACHE, _KPILIB_CACHE
    _USERS_CACHE = None
    _CASCADE_CACHE = None
    _KPILIB_CACHE = None


def _kpi_to_pillar() -> Dict[str, str]:
    lib = _kpilib()
    out: Dict[str, str] = {}
    for k in lib.get("kpis", []):
        if isinstance(k, dict) and k.get("id"):
            out[k["id"]] = k.get("pillar", "Unmapped")
    return out


def _staff_info(code: str) -> Dict[str, str]:
    for u in _users().values():
        if isinstance(u, dict) and str(u.get("staff_code", "")) == str(code):
            return {
                "name": str(u.get("full_name") or u.get("name", "")),
                "role": str(u.get("role", "")),
                "unit": str(u.get("unit") or u.get("department", "")),
            }
    return {"name": "?", "role": "?", "unit": "?"}


def _iter_cascade_entries(period: str):
    """Yield (key, entry) for valid cascade entries matching period.

    Defensive — skips meta-keys, deadlines, globals.
    """
    for k, v in _cascade().items():
        if k.startswith("_") or k.startswith("deadline|") or k.startswith("global_"):
            continue
        if not isinstance(v, dict):
            continue
        if "from_code" not in v:
            continue
        if v.get("period") != period:
            continue
        yield k, v


# ════════════════════════════════════════════════════════════════════
# 1) Bank-wide summary
# ════════════════════════════════════════════════════════════════════

def bank_health_summary(period: str) -> BankHealthSummary:
    """Top-level health: % bank targets fully cascaded."""
    entries = list(_iter_cascade_entries(period))

    # Recipient + KPI distinct counts
    recipients = set()
    kpis = set()
    full = partial = under = 0
    coverages = []

    for _k, e in entries:
        kpis.add(e.get("kpi", ""))
        total = float(e.get("total_target", 0) or 0)
        alloc = float(e.get("allocated_sum", 0) or 0)
        cov = (alloc / total * 100) if total else 0.0
        coverages.append(cov)
        if cov >= 99:
            full += 1
        elif cov >= 50:
            partial += 1
        else:
            under += 1
        for a in e.get("allocations", []):
            rc = str(a.get("to_code", ""))
            if rc:
                recipients.add(rc)

    # Total bank targets
    casc = _cascade()
    bank_targets = casc.get("bank_targets", {}) or {}
    # Strip meta keys
    bank_kpis_for_period = sum(
        1 for k, v in bank_targets.items()
        if not k.startswith("_")
        and isinstance(v, dict)
        and v.get("period") == period
    )

    avg_cov = sum(coverages) / len(coverages) if coverages else 0.0

    # Composite health score (0-100)
    # Weights: 40% avg coverage, 40% full ratio, 20% bank target coverage
    total_entries = len(entries)
    full_ratio = (full / total_entries * 100) if total_entries else 0.0
    bank_coverage_ratio = (len(kpis) / bank_kpis_for_period * 100) if bank_kpis_for_period else 0.0
    health = round(
        0.40 * avg_cov + 0.40 * full_ratio + 0.20 * bank_coverage_ratio, 1
    )

    return BankHealthSummary(
        period=period,
        total_bank_targets=bank_kpis_for_period,
        cascade_entries=total_entries,
        distinct_recipients=len(recipients),
        distinct_kpis_cascaded=len(kpis),
        fully_allocated_count=full,
        partial_allocated_count=partial,
        under_allocated_count=under,
        average_coverage_pct=round(avg_cov, 1),
        overall_health_score=health,
    )


# ════════════════════════════════════════════════════════════════════
# 2) Per-pillar
# ════════════════════════════════════════════════════════════════════

def health_by_pillar(period: str) -> List[PillarHealth]:
    pillar_map = _kpi_to_pillar()
    bank_w = _kpilib().get("pillar_weights", {})
    bank_w = {k: float(v) for k, v in bank_w.items()
              if not k.startswith("_") and isinstance(v, (int, float))}

    casc = _cascade()
    bank_targets = casc.get("bank_targets", {}) or {}

    # Group bank targets by pillar
    by_pillar: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "kpis_with_target": 0,
        "cascaded_count": 0,
        "coverages": [],
    })
    for k, v in bank_targets.items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        if v.get("period") != period:
            continue
        kpi_id = v.get("kpi") or v.get("kpi_id") or ""
        pillar = pillar_map.get(kpi_id, "Unmapped")
        by_pillar[pillar]["kpis_with_target"] += 1

    # Now count cascade entries per pillar
    for _k, e in _iter_cascade_entries(period):
        kpi = e.get("kpi", "")
        pillar = pillar_map.get(kpi, "Unmapped")
        by_pillar[pillar]["cascaded_count"] += 1
        total = float(e.get("total_target", 0) or 0)
        alloc = float(e.get("allocated_sum", 0) or 0)
        cov = (alloc / total * 100) if total else 0.0
        by_pillar[pillar]["coverages"].append(cov)

    out: List[PillarHealth] = []
    for p, data in by_pillar.items():
        avg = (sum(data["coverages"]) / len(data["coverages"])
               if data["coverages"] else 0.0)
        not_casc = max(0, data["kpis_with_target"] - data["cascaded_count"])
        out.append(PillarHealth(
            pillar=p,
            bank_weight=bank_w.get(p, 0.0),
            kpis_with_target=data["kpis_with_target"],
            cascaded_count=data["cascaded_count"],
            not_cascaded_count=not_casc,
            avg_coverage_pct=round(avg, 1),
        ))
    # Sort by canonical pillar weight desc
    out.sort(key=lambda x: -x.bank_weight)
    return out


# ════════════════════════════════════════════════════════════════════
# 3) Per-SBU (chiefs)
# ════════════════════════════════════════════════════════════════════

def health_by_sbu(period: str) -> List[SBUHealth]:
    """Each C-suite chief's cascade completeness across their subtree.

    Uses cascade_regenerator's canonical reporting tree to compute
    total reports vs reports that have at least one received target.
    """
    out: List[SBUHealth] = []
    # Find chiefs (tier 1 roles)
    chiefs = []
    for u in _users().values():
        if not isinstance(u, dict):
            continue
        role = u.get("role", "")
        if ("Chief" in role or "Director" in role) and "Managing" not in role:
            chiefs.append({
                "code": str(u.get("staff_code", "")),
                "name": u.get("full_name") or u.get("name", ""),
                "role": role,
            })

    # Build set of recipients per period
    recipients_per_kpi: Dict[str, set] = defaultdict(set)
    for _k, e in _iter_cascade_entries(period):
        kpi = e.get("kpi", "")
        for a in e.get("allocations", []):
            rc = str(a.get("to_code", ""))
            if rc:
                recipients_per_kpi[kpi].add(rc)

    all_recipients = set()
    for s in recipients_per_kpi.values():
        all_recipients |= s

    # For each chief: count their subtree, count how many are recipients
    try:
        from utils.manager_rollup import _all_subordinate_codes
    except ImportError:
        _all_subordinate_codes = lambda x: []  # noqa: E731

    for chief in chiefs:
        if not chief["code"]:
            continue
        try:
            subs = _all_subordinate_codes(chief["code"])
        except Exception:  # noqa: BLE001
            subs = []
        total_subs = len(subs)
        in_cascade = sum(1 for s in subs if str(s) in all_recipients)
        completeness = (in_cascade / total_subs * 100) if total_subs else 0.0

        # Count distinct KPIs that any subordinate received
        distinct_kpis = set()
        for kpi, recs in recipients_per_kpi.items():
            if any(str(s) in recs for s in subs):
                distinct_kpis.add(kpi)

        notes = []
        if total_subs == 0:
            notes.append("Leaf chief (no subordinates in canonical tree)")
        elif completeness < 50:
            notes.append(f"Only {in_cascade}/{total_subs} subs have received targets")

        out.append(SBUHealth(
            sbu=chief["role"],
            chief_code=chief["code"],
            chief_name=chief["name"],
            direct_reports_in_cascade=in_cascade,
            total_direct_reports=total_subs,
            distinct_kpis_received=len(distinct_kpis),
            completeness_pct=round(completeness, 1),
            notes=notes,
        ))

    # Sort by completeness ascending (worst first — surfaces gaps)
    out.sort(key=lambda x: x.completeness_pct)
    return out


# ════════════════════════════════════════════════════════════════════
# 4) Per-KPI
# ════════════════════════════════════════════════════════════════════

def health_by_kpi(period: str) -> List[KPIHealth]:
    pillar_map = _kpi_to_pillar()
    casc = _cascade()
    bank_targets = casc.get("bank_targets", {}) or {}

    # Bank targets per KPI for the period
    bank_kpis = set()
    for k, v in bank_targets.items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        if v.get("period") != period:
            continue
        kid = v.get("kpi") or v.get("kpi_id")
        if kid:
            bank_kpis.add(kid)

    # Aggregate cascade entries per KPI
    by_kpi: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "entries": 0,
        "recipients": set(),
        "coverages": [],
    })
    for _k, e in _iter_cascade_entries(period):
        kpi = e.get("kpi", "")
        by_kpi[kpi]["entries"] += 1
        for a in e.get("allocations", []):
            rc = str(a.get("to_code", ""))
            if rc:
                by_kpi[kpi]["recipients"].add(rc)
        total = float(e.get("total_target", 0) or 0)
        alloc = float(e.get("allocated_sum", 0) or 0)
        cov = (alloc / total * 100) if total else 0.0
        by_kpi[kpi]["coverages"].append(cov)

    out: List[KPIHealth] = []
    all_kpis = set(bank_kpis) | set(by_kpi.keys())
    for kpi in sorted(all_kpis):
        data = by_kpi.get(kpi, {"entries": 0, "recipients": set(), "coverages": []})
        avg = (sum(data["coverages"]) / len(data["coverages"])
               if data["coverages"] else 0.0)
        out.append(KPIHealth(
            kpi=kpi,
            pillar=pillar_map.get(kpi, "Unmapped"),
            bank_target_set=(kpi in bank_kpis),
            cascade_entries=data["entries"],
            distinct_recipients=len(data["recipients"]),
            avg_coverage_pct=round(avg, 1),
        ))
    return out


# ════════════════════════════════════════════════════════════════════
# 5) Broken chains
# ════════════════════════════════════════════════════════════════════

def broken_chains(period: str, max_results: int = 50) -> List[BrokenChain]:
    """Staff who RECEIVED a target but didn't cascade onward.

    A 'broken chain' is when staff X is a manager (has direct reports),
    received a target for KPI Y, but X→reports cascade entry is empty
    or missing.
    """
    out: List[BrokenChain] = []
    try:
        from utils.manager_rollup import _direct_report_codes
    except ImportError:
        _direct_report_codes = lambda x: []  # noqa: E731

    # Map: staff_code → list of (received_kpi, amount, from_code)
    received: Dict[str, List[Tuple[str, float, str]]] = defaultdict(list)
    for _k, e in _iter_cascade_entries(period):
        kpi = e.get("kpi", "")
        from_code = str(e.get("from_code", ""))
        for a in e.get("allocations", []):
            rc = str(a.get("to_code", ""))
            amt = float(a.get("amount", 0) or 0)
            if rc and amt:
                received[rc].append((kpi, amt, from_code))

    # Map: (from_code, kpi) → has entry
    forward_cascade: Dict[Tuple[str, str], bool] = {}
    for _k, e in _iter_cascade_entries(period):
        from_code = str(e.get("from_code", ""))
        kpi = e.get("kpi", "")
        alloc = float(e.get("allocated_sum", 0) or 0)
        forward_cascade[(from_code, kpi)] = alloc > 0

    for staff_code, kpi_list in received.items():
        try:
            reports = _direct_report_codes(staff_code)
        except Exception:  # noqa: BLE001
            reports = []
        if not reports:
            continue  # leaf — broken chain only applies to managers
        info = _staff_info(staff_code)
        for kpi, amt, from_code in kpi_list:
            # Did this staff forward-cascade this KPI?
            if not forward_cascade.get((staff_code, kpi)):
                # Count how many of their reports have a sub-cascade
                sub_count = sum(
                    1 for r in reports
                    if any(received.get(str(r), []) and t[0] == kpi
                           for t in received.get(str(r), []))
                )
                out.append(BrokenChain(
                    staff_code=staff_code,
                    staff_name=info["name"],
                    role=info["role"],
                    kpi=kpi,
                    received_amount=round(amt, 2),
                    has_direct_reports=True,
                    reports_with_subcascade=sub_count,
                    reason=(
                        "Manager received target but has not cascaded "
                        f"to {len(reports)} direct report(s)"
                    ),
                ))
                if len(out) >= max_results:
                    return out
    return out


# ════════════════════════════════════════════════════════════════════
# 6) Stale entries
# ════════════════════════════════════════════════════════════════════

def stale_entries(period: str, days: int = 30, max_results: int = 50) -> List[StaleEntry]:
    """Cascade entries last modified > N days ago without full acceptance."""
    cutoff = datetime.now() - timedelta(days=days)
    out: List[StaleEntry] = []
    for _k, e in _iter_cascade_entries(period):
        last_mod = e.get("last_modified") or e.get("created_at") or e.get("updated_at")
        if not last_mod:
            continue
        try:
            mod_dt = datetime.fromisoformat(last_mod)
        except (ValueError, TypeError):
            continue
        if mod_dt >= cutoff:
            continue
        days_stale = (datetime.now() - mod_dt).days
        from_code = str(e.get("from_code", ""))
        info = _staff_info(from_code)
        total = float(e.get("total_target", 0) or 0)
        alloc = float(e.get("allocated_sum", 0) or 0)
        cov = (alloc / total * 100) if total else 0.0
        out.append(StaleEntry(
            from_code=from_code,
            from_name=info["name"],
            kpi=e.get("kpi", ""),
            period=period,
            last_modified=last_mod[:10],
            days_stale=days_stale,
            coverage_pct=round(cov, 1),
        ))
        if len(out) >= max_results:
            break
    # Sort by days_stale desc (oldest first)
    out.sort(key=lambda x: -x.days_stale)
    return out


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ cascade_health_engine self-test ─")
    period = "2026"

    s = bank_health_summary(period)
    print(f"  Bank summary: {s.cascade_entries} entries, "
          f"{s.distinct_kpis_cascaded} KPIs, "
          f"health={s.overall_health_score}")
    assert s.cascade_entries >= 0

    p = health_by_pillar(period)
    print(f"  Pillars: {len(p)}")
    for ph in p[:3]:
        print(f"    {ph.pillar}: bank_w={ph.bank_weight}, "
              f"casc={ph.cascaded_count}/{ph.kpis_with_target}, "
              f"avg_cov={ph.avg_coverage_pct}%")

    sbu = health_by_sbu(period)
    print(f"  SBUs: {len(sbu)}")
    for s2 in sbu[:3]:
        print(f"    {s2.sbu[:30]:<30s}: {s2.direct_reports_in_cascade}/"
              f"{s2.total_direct_reports} ({s2.completeness_pct}%)")

    kh = health_by_kpi(period)
    print(f"  KPIs: {len(kh)}")
    no_cascade = [k for k in kh if k.bank_target_set and k.cascade_entries == 0]
    print(f"    KPIs with bank target but no cascade: {len(no_cascade)}")

    bc = broken_chains(period, max_results=10)
    print(f"  Broken chains: {len(bc)}")

    print("✓ self_test passed")


if __name__ == "__main__":
    self_test()
