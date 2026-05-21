"""Cascade Buffer Engine — v10.414 (F2 part A).

Per Joshua's F2 architectural design:
  - MD sets per-KPI maximum stretch cap (e.g., 20% means max 20% stretch
    can be added across the cascade chain for that KPI)
  - Each cascade layer (MD → Chief → Head → Branch Manager → staff) can
    add their own stretch buffer when allocating downward
  - Layer's added stretch is HIDDEN from the layer below (the report sees
    only the final number, not knowing it was padded)
  - Sum of all stretch added down the chain must not exceed MD's cap
  - BSC dual-view (v10.417 F5): primary=stretch view, secondary=base aside

This engine handles:
  - Cap configuration: who set what cap, when (audit trail)
  - Validation: is a proposed stretch% within MD's cap?
  - Math helpers: base × (1+stretch%) = effective amount

NOT handled here (deferred batches):
  - Per-allocation stretch slider UI in Set team targets (v10.415)
  - Layer-hiding rendering logic in BSC (v10.417 F5)
  - Cumulative buffer tracking across chain (depends on v10.415 data shape)

ARCHITECTURAL NOTE (API-first discipline locked v10.412):
  ZERO streamlit imports. All public functions take primitive types and
  return JSON-serializable dataclasses. Suitable for FastAPI consumption.

Shipped: v10.414.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
BUFFER_CAPS_FILE = DATA_DIR / "buffer_caps.json"

# Sanity bounds — capped configurations cannot exceed these.
MAX_REASONABLE_STRETCH_PCT = 0.50   # 50% — beyond this, stretch becomes farce
MIN_STRETCH_PCT = 0.0


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class BufferCapConfig:
    """MD's per-KPI cap on total stretch buffer across the cascade chain."""
    kpi: str
    max_stretch_pct: float          # 0.0 to 0.50
    set_by: str                      # staff_code of MD (or whoever has perm)
    set_at: str                      # ISO datetime
    note: str = ""                   # optional rationale

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BufferValidation:
    """Result of validating a proposed stretch percentage."""
    kpi: str
    proposed_pct: float
    cap_pct: float
    ok: bool
    reason: str = ""                 # explanation if not ok

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BufferSummary:
    """Cascade-wide buffer rollup for one KPI / period."""
    kpi: str
    period: str
    cap_pct: float                   # MD's set cap
    cap_set_by: str
    total_allocations: int
    allocations_with_stretch: int    # count where stretch_pct > 0
    max_stretch_observed_pct: float  # largest single allocation's stretch
    avg_stretch_pct: float           # mean across allocations with stretch
    cap_utilization_pct: float       # max_observed / cap (0.0 if cap is 0)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ════════════════════════════════════════════════════════════════════
# Persistence
# ════════════════════════════════════════════════════════════════════

def _load_caps() -> Dict[str, Dict[str, Any]]:
    """Returns {kpi: {max_stretch_pct, set_by, set_at, note}}."""
    if not BUFFER_CAPS_FILE.exists():
        return {}
    try:
        data = json.loads(BUFFER_CAPS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_caps(caps: Dict[str, Dict[str, Any]]) -> bool:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        BUFFER_CAPS_FILE.write_text(
            json.dumps(caps, indent=2, default=str),
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def _to_cap_dataclass(kpi: str, rec: Dict[str, Any]) -> BufferCapConfig:
    return BufferCapConfig(
        kpi=str(kpi),
        max_stretch_pct=float(rec.get("max_stretch_pct", 0.0)),
        set_by=str(rec.get("set_by", "")),
        set_at=str(rec.get("set_at", "")),
        note=str(rec.get("note", "")),
    )


# ════════════════════════════════════════════════════════════════════
# Public API — Cap management
# ════════════════════════════════════════════════════════════════════

def set_buffer_cap(
    kpi: str,
    max_stretch_pct: float,
    set_by: str,
    note: str = "",
) -> Optional[BufferCapConfig]:
    """MD sets the maximum allowable stretch buffer for a KPI.

    Args:
      kpi: KPI identifier (must be non-empty)
      max_stretch_pct: 0.0 to 0.50 (50% absolute max)
      set_by: staff_code of person setting (audit trail)
      note: optional rationale

    Returns:
      BufferCapConfig on success; None on validation failure.
    """
    if not kpi or not isinstance(kpi, str):
        return None
    if not set_by:
        return None
    try:
        pct = float(max_stretch_pct)
    except (TypeError, ValueError):
        return None
    if pct < MIN_STRETCH_PCT or pct > MAX_REASONABLE_STRETCH_PCT:
        return None

    caps = _load_caps()
    caps[kpi] = {
        "max_stretch_pct": pct,
        "set_by": str(set_by),
        "set_at": datetime.now().isoformat(),
        "note": str(note or "").strip(),
    }
    if not _save_caps(caps):
        return None
    return _to_cap_dataclass(kpi, caps[kpi])


def get_buffer_cap(kpi: str) -> Optional[BufferCapConfig]:
    """Get MD's cap for one KPI. Returns None if unset."""
    if not kpi:
        return None
    caps = _load_caps()
    rec = caps.get(kpi)
    if not rec:
        return None
    return _to_cap_dataclass(kpi, rec)


def get_all_buffer_caps() -> List[BufferCapConfig]:
    """All KPI caps. Empty list if none configured."""
    caps = _load_caps()
    return [_to_cap_dataclass(k, v) for k, v in sorted(caps.items())]


def remove_buffer_cap(kpi: str, removed_by: str) -> bool:
    """Clear cap for a KPI. Returns True on success."""
    if not kpi or not removed_by:
        return False
    caps = _load_caps()
    if kpi not in caps:
        return False
    del caps[kpi]
    return _save_caps(caps)


# ════════════════════════════════════════════════════════════════════
# Public API — Validation
# ════════════════════════════════════════════════════════════════════

def validate_buffer(kpi: str, proposed_pct: float) -> BufferValidation:
    """Check if a proposed stretch % is allowed under MD's cap."""
    try:
        p = float(proposed_pct)
    except (TypeError, ValueError):
        return BufferValidation(
            kpi=str(kpi), proposed_pct=0.0, cap_pct=0.0,
            ok=False, reason="proposed_pct is not a number",
        )

    if p < 0:
        return BufferValidation(
            kpi=str(kpi), proposed_pct=p, cap_pct=0.0,
            ok=False, reason="stretch cannot be negative",
        )
    if p > MAX_REASONABLE_STRETCH_PCT:
        return BufferValidation(
            kpi=str(kpi), proposed_pct=p, cap_pct=MAX_REASONABLE_STRETCH_PCT,
            ok=False,
            reason=f"absolute max stretch is {MAX_REASONABLE_STRETCH_PCT * 100:.0f}%",
        )

    cap = get_buffer_cap(kpi)
    if cap is None:
        # No cap set — any non-zero stretch is denied (must be configured)
        if p > 0:
            return BufferValidation(
                kpi=str(kpi), proposed_pct=p, cap_pct=0.0,
                ok=False,
                reason="no cap configured for this KPI; ask MD to set one",
            )
        return BufferValidation(
            kpi=str(kpi), proposed_pct=p, cap_pct=0.0,
            ok=True, reason="",
        )

    if p > cap.max_stretch_pct:
        return BufferValidation(
            kpi=str(kpi), proposed_pct=p, cap_pct=cap.max_stretch_pct,
            ok=False,
            reason=(
                f"exceeds MD cap of {cap.max_stretch_pct * 100:.1f}% "
                f"(set by {cap.set_by})"
            ),
        )

    return BufferValidation(
        kpi=str(kpi), proposed_pct=p, cap_pct=cap.max_stretch_pct,
        ok=True, reason="",
    )


def is_within_cap(kpi: str, proposed_pct: float) -> bool:
    """Convenience wrapper around validate_buffer; returns bool."""
    return validate_buffer(kpi, proposed_pct).ok


# ════════════════════════════════════════════════════════════════════
# Public API — Math helpers
# ════════════════════════════════════════════════════════════════════

def compute_effective_amount(base: float, stretch_pct: float) -> float:
    """Return base × (1 + stretch_pct). Treats negatives/None as 0."""
    try:
        b = float(base)
        p = float(stretch_pct or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if b < 0:
        b = 0.0
    if p < 0:
        p = 0.0
    return b * (1.0 + p)


def extract_base_from_amount(amount: float, stretch_pct: float) -> float:
    """Reverse of compute_effective: given effective and stretch%, return base.

    Returns amount unchanged if stretch_pct is 0 or invalid.
    """
    try:
        a = float(amount)
        p = float(stretch_pct or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if a < 0:
        a = 0.0
    if p <= 0:
        return a
    return a / (1.0 + p)


# ════════════════════════════════════════════════════════════════════
# Public API — Per-allocation stretch application (v10.415, F2 part B)
# ════════════════════════════════════════════════════════════════════

@dataclass
class StretchApplicationResult:
    """Result of applying stretch to a manager's allocations."""
    kpi: str
    cap_pct: float
    total_allocations: int
    updated_count: int                       # how many were changed
    new_allocations: List[Dict[str, Any]]    # the updated list (caller persists)
    violations: List[Dict[str, Any]]         # entries that failed validation
    new_total_amount: float                  # sum of new amounts

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def apply_stretch_to_allocations(
    allocations: List[Dict[str, Any]],
    stretch_map: Dict[str, float],
    kpi: str,
) -> StretchApplicationResult:
    """Apply per-allocation stretch and return the updated list + any violations.

    For each allocation in `allocations`:
      - Look up the new stretch_pct in stretch_map (keyed by to_code)
      - If the new pct is provided, validate against MD's cap
      - Compute new amount: base × (1 + new_stretch_pct)
        where base is derived from existing amount / (1 + existing_stretch_pct)
      - Preserve all other fields unchanged

    Args:
      allocations: existing list (each dict must have 'to_code', 'amount';
        may have 'stretch_pct')
      stretch_map: {to_code: stretch_pct} — only entries present are updated
      kpi: KPI identifier (used for cap lookup)

    Returns StretchApplicationResult with updated allocations and any violations.
    Violations are not applied; their entries retain prior values.
    """
    cap_cfg = get_buffer_cap(kpi)
    cap_pct = cap_cfg.max_stretch_pct if cap_cfg else 0.0

    new_allocs: List[Dict[str, Any]] = []
    violations: List[Dict[str, Any]] = []
    updated_count = 0

    for alloc in (allocations or []):
        new_alloc = dict(alloc)  # shallow copy
        to_code = str(alloc.get("to_code", ""))

        if to_code not in stretch_map:
            # Untouched — passthrough
            new_allocs.append(new_alloc)
            continue

        try:
            proposed_pct = float(stretch_map[to_code])
        except (TypeError, ValueError):
            violations.append({
                "to_code": to_code,
                "to_name": alloc.get("to_name", ""),
                "stretch_pct": stretch_map[to_code],
                "cap_pct": cap_pct,
                "reason": "stretch_pct is not a number",
            })
            new_allocs.append(new_alloc)
            continue

        # Validate against cap
        v = validate_buffer(kpi, proposed_pct)
        if not v.ok:
            violations.append({
                "to_code": to_code,
                "to_name": alloc.get("to_name", ""),
                "stretch_pct": proposed_pct,
                "cap_pct": v.cap_pct,
                "reason": v.reason,
            })
            new_allocs.append(new_alloc)
            continue

        # Derive base from existing amount
        existing_stretch = float(alloc.get("stretch_pct") or 0.0)
        existing_amount = float(alloc.get("amount") or 0.0)
        base = existing_amount / (1.0 + existing_stretch) if existing_stretch > 0 else existing_amount

        # Apply new stretch
        new_amount = base * (1.0 + proposed_pct)
        new_alloc["base_amount"] = base
        new_alloc["stretch_pct"] = proposed_pct
        new_alloc["amount"] = new_amount

        if abs(proposed_pct - existing_stretch) > 1e-9:
            updated_count += 1

        new_allocs.append(new_alloc)

    total_amount = sum(float(a.get("amount") or 0) for a in new_allocs)

    return StretchApplicationResult(
        kpi=str(kpi),
        cap_pct=cap_pct,
        total_allocations=len(new_allocs),
        updated_count=updated_count,
        new_allocations=new_allocs,
        violations=violations,
        new_total_amount=total_amount,
    )


def derive_base_for_allocation(alloc: Dict[str, Any]) -> float:
    """Get an allocation's base amount, handling missing stretch_pct safely.

    base = amount / (1 + stretch_pct) when stretch is present;
    otherwise base = amount.
    """
    try:
        amount = float(alloc.get("amount") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    stretch = alloc.get("stretch_pct")
    if stretch is None:
        return amount
    try:
        s = float(stretch)
    except (TypeError, ValueError):
        return amount
    if s <= 0:
        return amount
    return amount / (1.0 + s)


def cascade_stretch_breakdown(
    entries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Roll up base + stretch across a list of cascade entries.

    Returns:
      {
        "total_base": float,        # sum of derived bases
        "total_effective": float,   # sum of allocation amounts
        "total_stretch_added": float,  # difference
        "per_kpi": {kpi: {base, effective, stretch_pct_avg, allocation_count}}
      }
    """
    total_base = 0.0
    total_eff = 0.0
    per_kpi: Dict[str, Dict[str, Any]] = {}

    for entry in (entries or []):
        if not isinstance(entry, dict):
            continue
        kpi = str(entry.get("kpi", ""))
        for alloc in entry.get("allocations", []):
            base = derive_base_for_allocation(alloc)
            try:
                eff = float(alloc.get("amount") or 0.0)
            except (TypeError, ValueError):
                eff = 0.0
            total_base += base
            total_eff += eff

            k = per_kpi.setdefault(kpi, {
                "base": 0.0, "effective": 0.0,
                "stretch_total_pct": 0.0,
                "allocation_count": 0,
            })
            k["base"] += base
            k["effective"] += eff
            try:
                k["stretch_total_pct"] += float(alloc.get("stretch_pct") or 0.0)
            except (TypeError, ValueError):
                pass
            k["allocation_count"] += 1

    # Finalize averages
    for kpi, k in per_kpi.items():
        cnt = k.pop("allocation_count")
        k["allocation_count"] = cnt
        k["stretch_pct_avg"] = (k.pop("stretch_total_pct") / cnt) if cnt else 0.0

    return {
        "total_base": total_base,
        "total_effective": total_eff,
        "total_stretch_added": total_eff - total_base,
        "per_kpi": per_kpi,
    }


# ════════════════════════════════════════════════════════════════════
# ════════════════════════════════════════════════════════════════════
# Public API — Dual-view (v10.417, F5)
# ════════════════════════════════════════════════════════════════════
# Per Joshua's F2 BSC dual-view design: when a staff member views their
# targets, show STRETCH as the primary metric (what they're striving for)
# with BASE as a secondary aside (what was originally cascaded, before
# the manager added stretch). Removes ambiguity between "real" and
# "stretch" target.

@dataclass
class DualViewEntry:
    """One KPI's dual-view breakdown for a receiving staff member."""
    staff_code: str
    period: str
    kpi: str
    base_amount: float           # received target before stretch
    stretch_pct: float           # stretch added by direct manager (0.0 default)
    stretch_amount: float        # stretch_amount = effective - base
    effective_amount: float      # what staff sees as their target
    has_stretch: bool            # convenience flag
    from_code: str               # who cascaded this
    from_name: str               # cascading manager's name

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_dual_view(
    staff_code: str,
    period: str,
    cascade_entries: Optional[List[Dict[str, Any]]] = None,
) -> List[DualViewEntry]:
    """Compute dual-view (base vs stretch) for all KPIs assigned to a staff.

    Args:
      staff_code: receiver's staff code
      period: target period
      cascade_entries: optional pre-loaded entries; if None, load all from
        data/target_cascade.json

    Returns one DualViewEntry per (KPI assigned to this staff). KPIs with
    no stretch get has_stretch=False, stretch_amount=0, base_amount=
    effective_amount. KPIs with stretch get the full breakdown.
    """
    if not staff_code or not period:
        return []

    if cascade_entries is None:
        try:
            cascade_file = DATA_DIR / "target_cascade.json"
            if cascade_file.exists():
                raw = json.loads(cascade_file.read_text(encoding="utf-8"))
                cascade_entries = []
                for k, v in raw.items():
                    if k.startswith("_") or not isinstance(v, dict):
                        continue
                    if "from_code" not in v:
                        continue
                    if v.get("period") != period:
                        continue
                    cascade_entries.append(v)
            else:
                cascade_entries = []
        except Exception:  # noqa: BLE001
            cascade_entries = []

    out: List[DualViewEntry] = []
    sc_str = str(staff_code)
    for entry in (cascade_entries or []):
        for alloc in entry.get("allocations", []):
            if str(alloc.get("to_code", "")) != sc_str:
                continue
            # This allocation is ours
            try:
                amount = float(alloc.get("amount") or 0.0)
            except (TypeError, ValueError):
                amount = 0.0
            try:
                stretch_pct = float(alloc.get("stretch_pct") or 0.0)
            except (TypeError, ValueError):
                stretch_pct = 0.0
            base = derive_base_for_allocation(alloc)
            out.append(DualViewEntry(
                staff_code=sc_str,
                period=str(entry.get("period", period)),
                kpi=str(entry.get("kpi", "")),
                base_amount=base,
                stretch_pct=stretch_pct,
                stretch_amount=max(0.0, amount - base),
                effective_amount=amount,
                has_stretch=stretch_pct > 0,
                from_code=str(entry.get("from_code", "")),
                from_name=str(entry.get("from_name", "")),
            ))

    # If a staff has multiple inflows for the same KPI (rare — co-KPI pairing),
    # we keep them separate. Caller decides how to aggregate.
    return out


def get_dual_view_summary(
    staff_code: str,
    period: str,
    cascade_entries: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Convenience rollup: total base, total stretch across all KPIs."""
    entries = compute_dual_view(staff_code, period, cascade_entries)
    total_base = sum(e.base_amount for e in entries)
    total_eff = sum(e.effective_amount for e in entries)
    with_stretch = [e for e in entries if e.has_stretch]
    return {
        "staff_code": str(staff_code),
        "period": str(period),
        "kpi_count": len(entries),
        "stretched_kpi_count": len(with_stretch),
        "total_base": total_base,
        "total_effective": total_eff,
        "total_stretch": total_eff - total_base,
        "by_kpi": {e.kpi: e.to_dict() for e in entries},
    }


# ════════════════════════════════════════════════════════════════════
# Public API — Summary
# ════════════════════════════════════════════════════════════════════

def summarize_cascade_buffer(
    kpi: str,
    period: str,
    cascade_entries: Optional[List[Dict[str, Any]]] = None,
) -> BufferSummary:
    """Roll up buffer usage across all cascade allocations for a KPI/period.

    Args:
      kpi, period: scope
      cascade_entries: optional pre-loaded entries (each must have
        'kpi', 'period', 'allocations'). If None, load from target_cascade.json.

    Returns BufferSummary with cap utilization and per-allocation stats.
    """
    cap = get_buffer_cap(kpi)
    cap_pct = cap.max_stretch_pct if cap else 0.0
    cap_by = cap.set_by if cap else ""

    # Load entries if not provided
    if cascade_entries is None:
        try:
            cascade_file = DATA_DIR / "target_cascade.json"
            if cascade_file.exists():
                raw = json.loads(cascade_file.read_text(encoding="utf-8"))
                cascade_entries = []
                for k, v in raw.items():
                    if k.startswith("_") or not isinstance(v, dict):
                        continue
                    if "from_code" not in v:
                        continue
                    if v.get("kpi") == kpi and v.get("period") == period:
                        cascade_entries.append(v)
            else:
                cascade_entries = []
        except Exception:  # noqa: BLE001
            cascade_entries = []

    # Walk every allocation
    total = 0
    with_stretch = 0
    stretches: List[float] = []
    notes: List[str] = []

    for entry in (cascade_entries or []):
        for alloc in entry.get("allocations", []):
            total += 1
            sp = alloc.get("stretch_pct")
            if sp is None:
                continue
            try:
                sp_f = float(sp)
            except (TypeError, ValueError):
                continue
            if sp_f > 0:
                with_stretch += 1
                stretches.append(sp_f)
                if cap_pct > 0 and sp_f > cap_pct + 1e-9:
                    notes.append(
                        f"VIOLATION: {alloc.get('to_name', '?')} stretch "
                        f"{sp_f*100:.1f}% exceeds cap {cap_pct*100:.1f}%"
                    )

    max_observed = max(stretches) if stretches else 0.0
    avg = (sum(stretches) / len(stretches)) if stretches else 0.0
    cap_util = (max_observed / cap_pct) if cap_pct > 0 else 0.0

    return BufferSummary(
        kpi=str(kpi),
        period=str(period),
        cap_pct=cap_pct,
        cap_set_by=cap_by,
        total_allocations=total,
        allocations_with_stretch=with_stretch,
        max_stretch_observed_pct=max_observed,
        avg_stretch_pct=avg,
        cap_utilization_pct=cap_util,
        notes=notes,
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ cascade_buffer_engine self-test ─")
    import tempfile
    global BUFFER_CAPS_FILE
    _orig = BUFFER_CAPS_FILE
    tmp_dir = Path(tempfile.mkdtemp())
    BUFFER_CAPS_FILE = tmp_dir / "caps_test.json"
    try:
        # No caps initially
        assert get_buffer_cap("PBT") is None
        assert get_all_buffer_caps() == []
        print("  ✓ No caps initially")

        # Set a cap
        cfg = set_buffer_cap("PBT", 0.20, "MD001", note="Q1 review")
        assert cfg is not None
        assert cfg.max_stretch_pct == 0.20
        assert cfg.set_by == "MD001"
        print(f"  ✓ Set cap: {cfg.kpi} @ {cfg.max_stretch_pct*100:.0f}%")

        # Retrieve
        got = get_buffer_cap("PBT")
        assert got is not None and got.max_stretch_pct == 0.20
        print(f"  ✓ Retrieved: {got.set_by}")

        # Reject invalid input
        assert set_buffer_cap("PBT", 0.99, "MD001") is None  # exceeds absolute max
        assert set_buffer_cap("PBT", -0.1, "MD001") is None  # negative
        assert set_buffer_cap("", 0.1, "MD001") is None      # empty KPI
        assert set_buffer_cap("PBT", 0.1, "") is None        # no set_by
        assert set_buffer_cap("PBT", "abc", "MD001") is None # non-numeric
        print("  ✓ Validation rejects invalid inputs (5 cases)")

        # Validate proposals
        v1 = validate_buffer("PBT", 0.15)
        assert v1.ok
        print(f"  ✓ Validate ok at 15% under 20% cap")

        v2 = validate_buffer("PBT", 0.25)
        assert not v2.ok
        assert "exceeds MD cap" in v2.reason
        print(f"  ✓ Validate fails at 25% over 20% cap: {v2.reason[:50]}")

        v3 = validate_buffer("UNCAPPED_KPI", 0.10)
        assert not v3.ok
        assert "no cap configured" in v3.reason
        print(f"  ✓ Validate fails on uncapped KPI with non-zero proposal")

        v4 = validate_buffer("UNCAPPED_KPI", 0.0)
        assert v4.ok
        print(f"  ✓ Validate ok on uncapped KPI with 0 proposal")

        # Math helpers
        assert compute_effective_amount(100, 0.20) == 120.0
        assert compute_effective_amount(100, 0) == 100.0
        assert extract_base_from_amount(120, 0.20) == 100.0
        assert extract_base_from_amount(100, 0) == 100.0
        print("  ✓ Math helpers correct")

        # Summary
        entries = [{
            "kpi": "PBT", "period": "2026",
            "allocations": [
                {"to_name": "A", "amount": 100, "stretch_pct": 0.10},
                {"to_name": "B", "amount": 200, "stretch_pct": 0.15},
                {"to_name": "C", "amount": 50, "stretch_pct": 0.0},
                {"to_name": "D", "amount": 75},  # no stretch field
            ]
        }]
        summary = summarize_cascade_buffer("PBT", "2026", entries)
        assert summary.total_allocations == 4
        assert summary.allocations_with_stretch == 2
        assert summary.max_stretch_observed_pct == 0.15
        assert summary.cap_pct == 0.20
        assert abs(summary.cap_utilization_pct - 0.75) < 1e-6  # 0.15 / 0.20
        print(f"  ✓ Summary: {summary.allocations_with_stretch}/{summary.total_allocations} with stretch, "
              f"util {summary.cap_utilization_pct*100:.0f}%")

        # Summary detects violations
        entries_violation = [{
            "kpi": "PBT", "period": "2026",
            "allocations": [
                {"to_name": "BadActor", "amount": 100, "stretch_pct": 0.30},  # over 20%
            ]
        }]
        summary2 = summarize_cascade_buffer("PBT", "2026", entries_violation)
        assert len(summary2.notes) == 1
        assert "VIOLATION" in summary2.notes[0]
        print(f"  ✓ Summary detects violations")

        # Remove cap
        assert remove_buffer_cap("PBT", "MD001") is True
        assert get_buffer_cap("PBT") is None
        print("  ✓ Remove works")

        # ── v10.415 — apply_stretch_to_allocations ──
        set_buffer_cap("PBT", 0.20, "MD")
        existing = [
            {"to_code": "100001", "to_name": "Alice", "amount": 100.0},
            {"to_code": "100002", "to_name": "Bob",   "amount": 200.0},
            {"to_code": "100003", "to_name": "Carol", "amount": 150.0, "stretch_pct": 0.10},
        ]
        result = apply_stretch_to_allocations(
            existing,
            {"100001": 0.10, "100002": 0.30, "100003": 0.05},  # Bob exceeds
            "PBT",
        )
        assert result.cap_pct == 0.20
        assert len(result.violations) == 1
        assert result.violations[0]["to_code"] == "100002"
        # Alice: 100 → 110
        alice = next(a for a in result.new_allocations if a["to_code"] == "100001")
        assert abs(alice["amount"] - 110.0) < 1e-6
        assert alice["stretch_pct"] == 0.10
        # Bob: violation, unchanged
        bob = next(a for a in result.new_allocations if a["to_code"] == "100002")
        assert bob["amount"] == 200.0
        # Carol: had stretch 0.10 (base ≈ 136.36), now 0.05 → ≈ 143.18
        carol = next(a for a in result.new_allocations if a["to_code"] == "100003")
        assert abs(carol["stretch_pct"] - 0.05) < 1e-9
        carol_base = 150.0 / 1.10
        expected_carol = carol_base * 1.05
        assert abs(carol["amount"] - expected_carol) < 1e-6
        print(f"  ✓ apply_stretch: 2 updated, 1 violation; Carol base re-derived correctly")

        # Cascade stretch breakdown
        entries = [
            {"kpi": "PBT", "allocations": result.new_allocations},
        ]
        breakdown = cascade_stretch_breakdown(entries)
        assert "total_base" in breakdown
        assert "total_effective" in breakdown
        assert breakdown["total_effective"] > breakdown["total_base"]
        assert "PBT" in breakdown["per_kpi"]
        print(f"  ✓ cascade_stretch_breakdown: total_eff {breakdown['total_effective']:.1f} > base {breakdown['total_base']:.1f}")

        # Cleanup cap for downstream tests
        remove_buffer_cap("PBT", "MD")

        # ── v10.417 — dual-view (F5) ──
        # Build a synthetic cascade and verify dual-view extraction
        synthetic = [
            {
                "from_code": "100001", "from_name": "Alice Boss",
                "kpi": "PBT", "period": "2026",
                "allocations": [
                    {"to_code": "200001", "to_name": "Bob",
                     "amount": 110.0, "stretch_pct": 0.10, "base_amount": 100.0},
                    {"to_code": "200002", "to_name": "Carol",
                     "amount": 200.0},  # no stretch
                ],
            },
        ]
        dv = compute_dual_view("200001", "2026", synthetic)
        assert len(dv) == 1
        assert dv[0].kpi == "PBT"
        assert dv[0].has_stretch is True
        assert abs(dv[0].base_amount - 100.0) < 1e-6
        assert abs(dv[0].stretch_amount - 10.0) < 1e-6
        assert dv[0].effective_amount == 110.0
        assert dv[0].from_name == "Alice Boss"
        print(f"  ✓ Dual-view (stretched): base {dv[0].base_amount:.2f}, stretch {dv[0].stretch_amount:.2f}")

        dv2 = compute_dual_view("200002", "2026", synthetic)
        assert len(dv2) == 1
        assert dv2[0].has_stretch is False
        assert dv2[0].base_amount == 200.0
        assert dv2[0].stretch_amount == 0.0
        print(f"  ✓ Dual-view (no stretch): base = effective = {dv2[0].base_amount}")

        # Summary rollup
        sm = get_dual_view_summary("200001", "2026", synthetic)
        assert sm["kpi_count"] == 1
        assert sm["stretched_kpi_count"] == 1
        assert abs(sm["total_base"] - 100.0) < 1e-6
        assert abs(sm["total_stretch"] - 10.0) < 1e-6
        print(f"  ✓ Dual-view summary: {sm['stretched_kpi_count']}/{sm['kpi_count']} stretched")

        # Zero streamlit imports
        import re
        this_file = Path(__file__).read_text()
        streamlit_imports = re.findall(
            r'^\s*(?:import\s+streamlit|from\s+streamlit)\b',
            this_file, re.MULTILINE,
        )
        assert len(streamlit_imports) == 0
        print("  ✓ Zero streamlit imports (React-ready)")

        print("✓ self_test passed")
    finally:
        BUFFER_CAPS_FILE = _orig
        try:
            (tmp_dir / "caps_test.json").unlink(missing_ok=True)
            tmp_dir.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    self_test()
