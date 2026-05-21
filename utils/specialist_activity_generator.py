"""
Specialist Activity Generator — v10.336

Brings Treasury, Trade Finance specialists, and Marketing departments into
the BSC cascade. These three subtrees previously had K-coded role_kpis with
no producer feeding them — staff existed in the universe but didn't score.

Scope (v10.336):
  - Treasury: 6 staff (Sr Mgr Treasury, 2x Corporate Sales Dealer,
    Manager Forex Trader, Treasury Dealer, Treasury Front Office Officer)
  - Trade Finance specialists: 10 staff (TF Back Office Manager, 2x Senior
    TF Officer, 2x TF Officer, 2x TF Operations Officer, 2x RM TF, 1x Sr RM TF)
  - Marketing: 4 staff (Head of Marketing, Marketing Assistant Manager,
    2x Marketing Officer)

Out of scope:
  - Head of Treasury (300164): already scores via support_function_generator
  - Head Corporates & TF (300017): already scores via products_to_bsc + pipeline_bridge

Mirrors v10.317 Teller / v10.327 Credit / v10.328 Support / v10.329 BM /
v10.334 Propositions. Same design principles:
  - Deterministic — hash(staff_code, period, kpi_id) → reproducible
  - Direction-aware — TAT INVERTED (lower-is-better)
  - Idempotent — re-runs upsert by (staff_code, kpi_id, source_module)
  - Scale-aware — currency-M bases → raw currency on output
  - Streamlit imports DEFERRED to function bodies (headless-safe)
  - Invalidates _ACTUALS_INDEX_CACHE after writes
  - audit_log() after batch completion

8th producer in the cascade chain (Teller, Pipeline, Credit, Support, BM,
Propositions, Products, Specialist).
"""

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent
_CONFIG_PATH = _ROOT / "data" / "specialist_activity_config.json"


# ────────────────────────────────────────────────────────────────────
# Config + scope resolution
# ────────────────────────────────────────────────────────────────────

def load_config() -> Dict[str, Any]:
    from utils.db import db as _db
    return _db.load_json(_CONFIG_PATH, default={}) or {}


def find_specialist_staff() -> List[Tuple[str, str, str]]:
    """Return list of (staff_code, role, department_code) for all staff
    covered by this generator.

    Excludes staff already covered by upstream producers:
      - Head of Treasury (300164) → support_function_generator
      - Head Corporates & Trade Finance (300017) → products_to_bsc

    Returns staff drawn from data/users.json (single source of truth for
    department membership). The generator does not need to query the
    hierarchy — it works off departmental affiliation.
    """
    from utils.db import db as _db
    users_path = _ROOT / "data" / "users.json"
    users = _db.load_json(users_path, default={}) or {}

    out: List[Tuple[str, str, str]] = []
    # Code already-covered staff explicitly to keep this deterministic.
    skip_codes = {"300164", "300017"}
    # Department label → department code (config key)
    dept_to_code = {
        "Treasury": "TREASURY",
        "Trade Finance": "TRADE_FINANCE",
        "Marketing": "MARKETING",
    }

    for username, u in users.items():
        if not isinstance(u, dict):
            continue
        code = str(u.get("staff_code") or username)
        if code in skip_codes:
            continue
        dept_label = u.get("department") or ""
        if dept_label not in dept_to_code:
            continue
        role = (u.get("role") or "").strip()
        if not role:
            continue
        out.append((code, role, dept_to_code[dept_label]))

    return out


# ────────────────────────────────────────────────────────────────────
# Deterministic value generation
# ────────────────────────────────────────────────────────────────────

def _stable_hash(staff_code: str, period: str, kpi_id: str) -> int:
    """Stable 8-byte hash → int for deterministic seeding."""
    h = hashlib.sha256(
        f"{staff_code}|{period}|{kpi_id}".encode("utf-8")
    ).digest()
    return int.from_bytes(h[:8], "big", signed=False)


def _band_for_staff(
    staff_code: str,
    role: str,
    config: Dict[str, Any],
    department: str,
) -> str:
    """Pick performance band deterministically. Heads use department
    head_band_weights if present; staff use standard performance_bands.
    """
    dept_cfg = config.get("departments", {}).get(department, {})
    is_head = role == dept_cfg.get("head_role")
    if is_head and "head_band_weights" in dept_cfg:
        weights = dept_cfg["head_band_weights"]
    else:
        weights = {
            b: config["performance_bands"][b]["weight"]
            for b in ("HIGH", "MID", "LOW")
        }

    h = _stable_hash(staff_code, "_band", department)
    r = (h % 100000) / 100000.0
    cum = 0.0
    for band in ("HIGH", "MID", "LOW"):
        cum += weights.get(band, 0)
        if r < cum:
            return band
    return "MID"


def _value_for(
    staff_code: str,
    period: str,
    kpi_id: str,
    kpi_spec: Dict[str, Any],
    band: str,
    config: Dict[str, Any],
) -> Decimal:
    """Compute deterministic actual value for one (staff, period, kpi)."""
    base = Decimal(str(kpi_spec["base"]))
    direction = kpi_spec.get("direction", "higher")
    unit = kpi_spec.get("unit", "")
    band_cfg = config["performance_bands"][band]

    # currency-M → raw currency units
    if unit == "CCY_M":
        base = base * Decimal("1000000")

    # Deterministic factor within band range
    h = _stable_hash(staff_code, period, kpi_id)
    factor_lo, factor_hi = band_cfg["factor_range"]
    factor_span = factor_hi - factor_lo
    factor = factor_lo + ((h % 1000) / 1000.0) * factor_span

    # Small noise
    noise_pct = config.get("noise_range_pct", 0.04)
    noise_h = _stable_hash(staff_code, period, kpi_id + ":noise")
    noise = ((noise_h % 1000) / 1000.0 - 0.5) * 2.0 * noise_pct
    factor *= (1.0 + noise)

    # Direction-aware inversion
    if direction == "lower":
        factor = 1.0 / factor

    value = base * Decimal(str(factor))

    # Scale-aware clamping
    if unit == "score_5":
        value = max(Decimal("1.0"), min(Decimal("5.0"), value))
    elif unit == "score_100":
        value = max(Decimal("0"), min(Decimal("100"), value))
    elif unit == "%":
        value = max(Decimal("0"), min(Decimal("500"), value))  # ROI can exceed 100%

    if unit == "count":
        return value.quantize(Decimal("1"))
    return value.quantize(Decimal("0.01"))


# ────────────────────────────────────────────────────────────────────
# Generation entry point
# ────────────────────────────────────────────────────────────────────

def generate_for_period(
    period: str,
    username: str = "system_specialist_generator",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Generate BSC actuals for all specialist-department staff for one
    period.

    Returns summary dict with counts and per-department breakdown.
    """
    config = load_config()
    staff_list = find_specialist_staff()

    actuals_path = _ROOT / "data" / f"bsc_actuals_{period}.json"
    existing: List[Dict[str, Any]] = []
    if actuals_path.exists():
        from utils.db import db as _db
        raw = _db.load_json(actuals_path, default=[]) or []
        if isinstance(raw, list):
            existing = raw
        elif isinstance(raw, dict):
            existing = raw.get("actuals", [])

    # Index existing by (staff_code, kpi_id) within this source for upsert
    existing_by_key: Dict[Tuple[str, str], int] = {}
    for i, a in enumerate(existing):
        if not isinstance(a, dict):
            continue
        if a.get("source_module") == "specialist_activity_generator":
            key = (a.get("staff_code"), a.get("kpi_id"))
            existing_by_key[key] = i

    submitted = 0
    failures: List[Dict[str, Any]] = []
    by_dept: Dict[str, int] = {}
    by_band: Dict[str, int] = {"HIGH": 0, "MID": 0, "LOW": 0}

    ts = datetime.now(timezone.utc).isoformat()
    role_cfgs = config.get("role_kpi_bases", {})

    for staff_code, role, dept in staff_list:
        role_cfg = role_cfgs.get(role)
        if not role_cfg:
            failures.append({
                "staff_code": staff_code,
                "role": role,
                "reason": "no_role_config",
            })
            continue

        band = _band_for_staff(staff_code, role, config, dept)
        by_band[band] += 1
        by_dept[dept] = by_dept.get(dept, 0) + 1

        for kpi_id, kpi_spec in role_cfg["kpi_bases"].items():
            try:
                value = _value_for(
                    staff_code, period, kpi_id, kpi_spec, band, config
                )
            except Exception as exc:
                failures.append({
                    "staff_code": staff_code,
                    "kpi_id": kpi_id,
                    "reason": f"compute_error: {exc}",
                })
                continue

            actual_record = {
                "actual_id": f"SAG_{staff_code}_{kpi_id}_{period}",
                "staff_code": staff_code,
                "kpi_id": kpi_id,
                "period": period,
                "value": float(value),
                "submitted_by": username,
                "submitted_at": ts,
                "source_module": "specialist_activity_generator",
                "_v10336_band": band,
                "_v10336_role": role,
                "_v10336_department": dept,
            }

            key = (staff_code, kpi_id)
            if key in existing_by_key:
                existing[existing_by_key[key]] = actual_record
            else:
                existing.append(actual_record)
                existing_by_key[key] = len(existing) - 1

            submitted += 1

    if not dry_run:
        actuals_path.write_text(
            json.dumps(existing, indent=2), encoding="utf-8"
        )
        try:
            from utils.bsc_engine import invalidate_actuals_index
            invalidate_actuals_index(period)
        except Exception:
            pass
        # Audit log
        try:
            from utils.core_audit import audit_log
            audit_log(
                "SPECIALIST_BATCH_GENERATED",
                username,
                f"period={period} staff={len(staff_list)} "
                f"submitted={submitted} failures={len(failures)}",
                "specialist_activity_generator",
                None,
                {
                    "period": period,
                    "staff_count": len(staff_list),
                    "submitted": submitted,
                    "failures": len(failures),
                    "by_department": by_dept,
                },
            )
        except Exception:
            pass

    return {
        "period": period,
        "staff_processed": len(staff_list),
        "kpis_submitted": submitted,
        "failures": failures,
        "by_department": by_dept,
        "by_band": by_band,
    }


def get_specialist_staff_count() -> int:
    """Helper for G225 audit gate — count of staff covered."""
    return len(find_specialist_staff())


def list_departments_covered() -> List[str]:
    """Return department codes covered by this generator."""
    config = load_config()
    return list(config.get("departments", {}).keys())
