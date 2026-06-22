"""Cascade Retain Authorization Engine — v10.416 (F3).

Per Joshua's F3 architectural design:
  - 100% cascade required up to Branch Manager tier (MD, directors,
    heads, regional heads, BMs all MUST cascade everything they receive)
  - Below BM tier (Branch Operations Manager, SME/Corporate RMs, etc.):
    the line manager's IMMEDIATE BOSS can tick "can retain" per direct
    report, authorizing them to retain (not cascade 100%)
  - Without retention authorization: report must cascade 100% (default)
  - With retention authorization: report can allocate < 100% to their
    own reports, keeping the residual as their personal target

This engine handles:
  - Eligibility check by role (tier 1 = must cascade; below = eligible)
  - Authorization CRUD with full audit trail (who authorized whom when)
  - Helper for callers to ask "can staff X retain in period P?"

NOT handled here:
  - Modification of the existing cascade total-validation rule in the
    Set team targets save logic (deferred — that surgery is risky and
    can be done in a later batch once the auth surface is exercised)
  - UI representation — Streamlit wrapper in pages/12_cascade.py

ARCHITECTURAL NOTE (API-first discipline locked v10.412):
  ZERO streamlit imports. All public functions take primitive types and
  return JSON-serializable dataclasses. FastAPI-ready.

Shipped: v10.416.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
AUTH_FILE = DATA_DIR / "retain_authorizations.json"


# ════════════════════════════════════════════════════════════════════
# Eligibility — Role-based tier rule
# ════════════════════════════════════════════════════════════════════
#
# Tier 1 roles (MUST cascade 100% — NOT eligible for retention):
#   Managing Director, Director, Head of *, Regional Head, Branch Manager
#
# Everyone else with reports is "below BM" and eligible to receive
# retention authorization from their immediate boss.
#
# Pure leaf roles (Teller, CSO, BOS, etc.) usually have no reports, so
# the question doesn't arise — but the engine doesn't gate on that.

TIER1_ROLE_KEYWORDS = (
    "Managing Director",
    "Chief Executive",
    "Director",
    "Chief Retail",
    "Chief Commercial",
    "Chief Financial",
    "Chief Operating",
    "Chief Risk",
    "Chief Information",
    "Chief Human",
    "Chief Compliance",
    "Head Of",
    "Head of",
    "Regional Head",
    "Branch Manager",
)


def is_eligible_for_retention(role: str) -> bool:
    """Returns True if the role is below Branch Manager tier."""
    if not role or not isinstance(role, str):
        return False
    role_lower = role.lower()
    for kw in TIER1_ROLE_KEYWORDS:
        if kw.lower() in role_lower:
            return False
    return True


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class RetainAuthorization:
    """One staff's retention authorization for a period."""
    staff_code: str
    period: str
    authorized_by: str            # boss's staff_code
    authorized_at: str            # ISO datetime
    can_retain: bool              # explicit yes/no
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ════════════════════════════════════════════════════════════════════
# Persistence
# ════════════════════════════════════════════════════════════════════

def _key(staff_code: str, period: str) -> str:
    return f"{staff_code}|{period}"


def _load_all() -> Dict[str, Dict[str, Any]]:
    if not AUTH_FILE.exists():
        return {}
    try:
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_all(records: Dict[str, Dict[str, Any]]) -> bool:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        AUTH_FILE.write_text(
            json.dumps(records, indent=2, default=str),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def _to_dataclass(rec: Dict[str, Any]) -> RetainAuthorization:
    return RetainAuthorization(
        staff_code=str(rec.get("staff_code", "")),
        period=str(rec.get("period", "")),
        authorized_by=str(rec.get("authorized_by", "")),
        authorized_at=str(rec.get("authorized_at", "")),
        can_retain=bool(rec.get("can_retain", False)),
        note=str(rec.get("note", "")),
    )


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════

def set_retain_authorization(
    staff_code: str,
    authorized_by: str,
    period: str,
    can_retain: bool = True,
    note: str = "",
) -> Optional[RetainAuthorization]:
    """Boss grants/revokes retention permission for a direct report.

    Args:
      staff_code: who is being authorized
      authorized_by: boss's staff_code (audit trail)
      period: target period
      can_retain: explicit True/False (default True for grants)
      note: optional rationale

    Returns RetainAuthorization on success; None on validation failure.
    """
    if not staff_code or not authorized_by or not period:
        return None

    records = _load_all()
    k = _key(str(staff_code), str(period))
    rec = {
        "staff_code": str(staff_code),
        "period": str(period),
        "authorized_by": str(authorized_by),
        "authorized_at": datetime.now().isoformat(),
        "can_retain": bool(can_retain),
        "note": str(note or "").strip(),
    }
    records[k] = rec
    if not _save_all(records):
        return None
    return _to_dataclass(rec)


def get_retain_authorization(
    staff_code: str,
    period: str,
) -> Optional[RetainAuthorization]:
    """Get retention auth for a single staff+period. None if not configured."""
    if not staff_code or not period:
        return None
    records = _load_all()
    rec = records.get(_key(str(staff_code), str(period)))
    if not rec:
        return None
    return _to_dataclass(rec)


def is_retention_allowed(staff_code: str, period: str) -> bool:
    """Convenience: True iff an authorization exists AND can_retain=True."""
    auth = get_retain_authorization(staff_code, period)
    return bool(auth and auth.can_retain)


def get_team_retain_authorizations(
    direct_report_codes: List[str],
    period: str,
) -> List[RetainAuthorization]:
    """All retain auths for a list of staff (typically a boss's reports)."""
    records = _load_all()
    out: List[RetainAuthorization] = []
    for code in (direct_report_codes or []):
        rec = records.get(_key(str(code), str(period)))
        if rec:
            out.append(_to_dataclass(rec))
    return out


def get_all_retain_authorizations(
    period: Optional[str] = None,
) -> List[RetainAuthorization]:
    """All authorizations, optionally filtered by period."""
    records = _load_all()
    out: List[RetainAuthorization] = []
    for k, rec in records.items():
        if period and rec.get("period") != period:
            continue
        out.append(_to_dataclass(rec))
    return out


def remove_retain_authorization(
    staff_code: str,
    period: str,
    removed_by: str,
) -> bool:
    """Revoke a retention authorization. Returns True on success."""
    if not staff_code or not period or not removed_by:
        return False
    records = _load_all()
    k = _key(str(staff_code), str(period))
    if k not in records:
        return False
    del records[k]
    return _save_all(records)


# ════════════════════════════════════════════════════════════════════
# Aggregations
# ════════════════════════════════════════════════════════════════════

@dataclass
class AllocationCompliance:
    """v10.418 — Compliance of a manager's cascade for one KPI, accounting
    for F3 retention authorization. The 100% cascade rule is RELAXED when
    a manager has retain auth granted by their boss — the residual
    (total - allocated) becomes their personal retained portion.
    """
    staff_code: str           # the manager cascading downward
    kpi: str
    period: str
    total_target: float
    allocated_sum: float
    retained_amount: float    # max(0, total - allocated)
    retained_pct: float       # retained / total (0..1)
    coverage_pct: float       # allocated / total (0..1)
    has_retain_auth: bool
    status: str               # one of: 'fully_cascaded', 'retained_authorized',
                              #         'under_no_auth', 'over_allocated', 'no_target'
    compliance_ok: bool       # True if status in {fully_cascaded, retained_authorized}
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_allocation_compliance(
    staff_code: str,
    kpi: str,
    period: str,
    total_target: float,
    allocated_sum: float,
    tolerance: float = 0.001,  # 0.1% slack for rounding
) -> AllocationCompliance:
    """Per Joshua's F3 design + v10.418 surgery:
    100% cascade required by default; relaxed when retain auth is granted.

    Status rules:
      - total_target <= 0  -> 'no_target' (cannot evaluate)
      - allocated > total (over tolerance)  -> 'over_allocated'
      - allocated within tolerance of total -> 'fully_cascaded'
      - allocated < total AND retain auth granted -> 'retained_authorized'
      - allocated < total AND no retain auth -> 'under_no_auth'
    """
    try:
        total = float(total_target or 0.0)
        alloc = float(allocated_sum or 0.0)
    except (TypeError, ValueError):
        total = 0.0
        alloc = 0.0

    if total <= 0:
        return AllocationCompliance(
            staff_code=str(staff_code), kpi=str(kpi), period=str(period),
            total_target=0.0, allocated_sum=alloc,
            retained_amount=0.0, retained_pct=0.0, coverage_pct=0.0,
            has_retain_auth=False, status="no_target",
            compliance_ok=False, note="No bank target set",
        )

    has_auth = is_retention_allowed(staff_code, period)
    coverage = alloc / total if total > 0 else 0.0
    retained = max(0.0, total - alloc)
    retained_pct = retained / total if total > 0 else 0.0

    # Over-allocation (> total + tolerance × total)
    if alloc > total * (1.0 + tolerance):
        return AllocationCompliance(
            staff_code=str(staff_code), kpi=str(kpi), period=str(period),
            total_target=total, allocated_sum=alloc,
            retained_amount=0.0, retained_pct=0.0, coverage_pct=coverage,
            has_retain_auth=has_auth, status="over_allocated",
            compliance_ok=False,
            note=f"allocated {coverage*100:.1f}% > 100%",
        )

    # Fully cascaded (within tolerance band of total)
    if abs(alloc - total) <= total * tolerance:
        return AllocationCompliance(
            staff_code=str(staff_code), kpi=str(kpi), period=str(period),
            total_target=total, allocated_sum=alloc,
            retained_amount=0.0, retained_pct=0.0, coverage_pct=coverage,
            has_retain_auth=has_auth, status="fully_cascaded",
            compliance_ok=True, note="",
        )

    # Under-allocated — depends on retain auth
    if has_auth:
        return AllocationCompliance(
            staff_code=str(staff_code), kpi=str(kpi), period=str(period),
            total_target=total, allocated_sum=alloc,
            retained_amount=retained, retained_pct=retained_pct,
            coverage_pct=coverage,
            has_retain_auth=True, status="retained_authorized",
            compliance_ok=True,
            note=f"retained {retained_pct*100:.1f}% under boss authorization",
        )

    return AllocationCompliance(
        staff_code=str(staff_code), kpi=str(kpi), period=str(period),
        total_target=total, allocated_sum=alloc,
        retained_amount=0.0, retained_pct=0.0, coverage_pct=coverage,
        has_retain_auth=False, status="under_no_auth",
        compliance_ok=False,
        note=f"under-cascaded {(1-coverage)*100:.1f}% — no retain auth granted",
    )


@dataclass
class RetentionAuditSummary:
    """Bank-wide retention authorization rollup."""
    period: str
    total_authorizations: int
    granted_count: int           # can_retain = True
    revoked_count: int           # can_retain = False (explicit denial)
    authorizing_managers: List[str]   # unique boss codes

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def retention_audit_summary(period: str) -> RetentionAuditSummary:
    """Bank-wide summary of retention auths for a period."""
    auths = get_all_retain_authorizations(period)
    granted = sum(1 for a in auths if a.can_retain)
    revoked = sum(1 for a in auths if not a.can_retain)
    managers = sorted({a.authorized_by for a in auths if a.authorized_by})
    return RetentionAuditSummary(
        period=str(period),
        total_authorizations=len(auths),
        granted_count=granted,
        revoked_count=revoked,
        authorizing_managers=managers,
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ cascade_retain_engine self-test ─")
    import tempfile
    global AUTH_FILE
    _orig = AUTH_FILE
    tmp_dir = Path(tempfile.mkdtemp())
    AUTH_FILE = tmp_dir / "retain_test.json"
    try:
        # Eligibility — Tier 1 NOT eligible
        assert is_eligible_for_retention("Branch Manager") is False
        assert is_eligible_for_retention("Director Consumer & Commercial Banking (CCB)") is False
        assert is_eligible_for_retention("Head Of Retail") is False
        assert is_eligible_for_retention("Regional Head") is False
        assert is_eligible_for_retention("Managing Director") is False
        assert is_eligible_for_retention("Chief Executive & Managing Director") is False
        print("  ✓ Tier 1 roles correctly ineligible (5 cases)")

        # Eligibility — below BM IS eligible
        assert is_eligible_for_retention("Branch Operations Manager") is True
        assert is_eligible_for_retention("Senior Relationship Manager - SME") is True
        assert is_eligible_for_retention("Relationship Manager - Corporate Banking") is True
        assert is_eligible_for_retention("Teller") is True  # leaf, but eligibility says True
        print("  ✓ Below-BM roles correctly eligible (4 cases)")

        # Edge cases
        assert is_eligible_for_retention("") is False
        assert is_eligible_for_retention(None) is False
        print("  ✓ Empty/None role handled gracefully")

        # Set/get authorization
        auth = set_retain_authorization(
            "BOM001", "BM001", "2026",
            can_retain=True, note="Branch lead — local discretion",
        )
        assert auth is not None
        assert auth.staff_code == "BOM001"
        assert auth.can_retain is True
        assert auth.authorized_by == "BM001"
        print(f"  ✓ Set auth: {auth.staff_code} by {auth.authorized_by}")

        got = get_retain_authorization("BOM001", "2026")
        assert got is not None and got.can_retain is True
        print(f"  ✓ Retrieved auth")

        # is_retention_allowed convenience
        assert is_retention_allowed("BOM001", "2026") is True
        assert is_retention_allowed("BOM999", "2026") is False  # not authorized
        print("  ✓ is_retention_allowed convenience works")

        # Reject invalid inputs
        assert set_retain_authorization("", "BM", "2026") is None
        assert set_retain_authorization("X", "", "2026") is None
        assert set_retain_authorization("X", "BM", "") is None
        print("  ✓ Validation rejects empty fields (3 cases)")

        # Revoke (set can_retain=False)
        revoked = set_retain_authorization(
            "BOM002", "BM001", "2026",
            can_retain=False, note="Below performance threshold",
        )
        assert revoked is not None and revoked.can_retain is False
        assert is_retention_allowed("BOM002", "2026") is False
        print("  ✓ Explicit revoke (can_retain=False)")

        # Team auths
        team = get_team_retain_authorizations(
            ["BOM001", "BOM002", "BOM003"], "2026",
        )
        assert len(team) == 2  # BOM003 not configured
        print(f"  ✓ Team auths: {len(team)}")

        # Bank-wide summary
        sm = retention_audit_summary("2026")
        assert sm.total_authorizations == 2
        assert sm.granted_count == 1
        assert sm.revoked_count == 1
        assert "BM001" in sm.authorizing_managers
        print(f"  ✓ Bank summary: {sm.granted_count} granted, {sm.revoked_count} revoked")

        # Remove
        assert remove_retain_authorization("BOM001", "2026", "BM001") is True
        assert get_retain_authorization("BOM001", "2026") is None
        # Removing nonexistent fails gracefully
        assert remove_retain_authorization("NOPE", "2026", "BM") is False
        print("  ✓ Remove works")

        # ── v10.418 — compliance (cascade-validation surgery) ──
        # Re-grant auth for BOM001 to test compliance
        set_retain_authorization("BOM001", "BM001", "2026", can_retain=True)
        # Fully cascaded: 100 == 100
        c1 = compute_allocation_compliance("MGR1", "PBT", "2026", 100.0, 100.0)
        assert c1.status == "fully_cascaded"
        assert c1.compliance_ok is True
        # Retained with auth: BOM001 has auth, allocates 70 of 100
        c2 = compute_allocation_compliance("BOM001", "PBT", "2026", 100.0, 70.0)
        assert c2.status == "retained_authorized"
        assert c2.compliance_ok is True
        assert abs(c2.retained_amount - 30.0) < 1e-9
        # Under-allocated without auth (MGR1 not in auths)
        c3 = compute_allocation_compliance("MGR1", "PBT", "2026", 100.0, 70.0)
        assert c3.status == "under_no_auth"
        assert c3.compliance_ok is False
        # Over-allocated (ignores auth — over is always violation)
        c4 = compute_allocation_compliance("BOM001", "PBT", "2026", 100.0, 110.0)
        assert c4.status == "over_allocated"
        assert c4.compliance_ok is False
        # No target
        c5 = compute_allocation_compliance("ANY", "ANY_KPI", "2026", 0.0, 50.0)
        assert c5.status == "no_target"
        assert c5.compliance_ok is False
        print(f"  ✓ Compliance: fully={c1.status}, retained={c2.status}, "
              f"under={c3.status}, over={c4.status}, none={c5.status}")
        # Cleanup
        remove_retain_authorization("BOM001", "2026", "BM001")

        # Zero streamlit imports
        import re
        this_file = Path(__file__).read_text()
        streamlit_imports = re.findall(
            r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
            this_file, re.MULTILINE,
        )
        assert len(streamlit_imports) == 0
        print("  ✓ Zero streamlit imports (React-ready)")

        print("✓ self_test passed")
    finally:
        AUTH_FILE = _orig
        try:
            (tmp_dir / "retain_test.json").unlink(missing_ok=True)
            tmp_dir.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    self_test()
