"""
Branch Manager Activity Generator — v10.329

Per banking convention, branch performance IS the Branch Manager's performance.
PBT, NFI, NPL Ratio, PAR, CIR are at branch level and ARE the Branch Manager's
own KPIs (not recursive team aggregates).

This generator produces deterministic BSC actuals for 94 Branch Managers
(94 branches total — 13 Senior, 81 standard). Each BM gets a full 21-KPI
scorecard reflecting their branch's strategic + operational performance.

Mirrors v10.317 Teller / v10.327 Credit / v10.328 Support Function generators.

Design principles:
  - Deterministic — hash(staff_code, kpi_id, period) → reproducible value
  - Direction-aware — lower-is-better KPIs (NPL, PAR, dormancy) INVERT band factor
  - Idempotent — re-running overwrites prior submissions for same period
  - Audit-logged — every batch write tagged `source_module='branch_manager_generator'`

Canonical imports per platform standing rules.
Streamlit-dependent imports are deferred to function bodies to allow
this module to be importable in headless scripts.
"""

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent
_CONFIG_PATH = _ROOT / "data" / "branch_manager_config.json"


# ────────────────────────────────────────────────────────────────────
# Config + staff resolution
# ────────────────────────────────────────────────────────────────────

def load_config() -> Dict[str, Any]:
    """Load branch_manager_config.json via canonical db helper."""
    try:
        from utils.db import db
        cfg = db.load_json(_CONFIG_PATH, default={}) or {}
    except Exception:  # noqa: BLE001
        cfg = {}
    return cfg


def find_branch_managers() -> List[Tuple[str, str]]:
    """Return list of (staff_code, role) for all Branch Managers.

    Filter excludes 'Assistant Branch Manager' / 'Asst Branch Manager'
    which are operational deputies, not BM scorecard holders.
    """
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    bms = []
    for r in u.values():
        role = r.role or ""
        if "Branch Manager" not in role:
            continue
        if "Assistant" in role or "Asst" in role:
            continue
        if not r.active:
            continue
        bms.append((r.staff_code, role))
    return bms


# ────────────────────────────────────────────────────────────────────
# Deterministic value generation
# ────────────────────────────────────────────────────────────────────

def _stable_hash(staff_code: str, period: str, kpi_id: str) -> int:
    """Stable 8-byte hash → int for deterministic seeding."""
    h = hashlib.sha256(f"{staff_code}|{period}|{kpi_id}".encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big", signed=False)


def _band_for_staff(staff_code: str, role: str, config: Dict[str, Any]) -> str:
    """Assign performance band deterministically.

    Senior Branch Managers skew HIGH (35%) reflecting flagship branches.
    Standard Branch Managers follow normal distribution (25/55/20).
    """
    if role == "Senior Branch Manager":
        weights = config["senior_bm_band_weights"]
    else:
        weights = {b: config["performance_bands"][b]["weight"]
                   for b in ("HIGH", "MID", "LOW")}

    # Hash to [0, 1) and pick by cumulative weight
    h = _stable_hash(staff_code, "_band", "_band")
    r = (h % 100000) / 100000.0
    cum = 0.0
    for band in ("HIGH", "MID", "LOW"):
        cum += weights[band]
        if r < cum:
            return band
    return "MID"


def _value_for(
    staff_code: str,
    period: str,
    kpi_spec: Dict[str, Any],
    band: str,
    config: Dict[str, Any],
) -> Decimal:
    """Compute deterministic actual value for one (staff, period, kpi).

    Unit handling:
      - 'CCY M' bases are multiplied by 1,000,000 to produce raw currency
        values that match the bank_targets / role_default_targets scale
      - '%' stays as percentage (0-100)
      - 'score_5' clamped to [1, 5]
      - 'score_100' clamped to [0, 100]
      - 'count' rounded to integer
    """
    base = Decimal(str(kpi_spec["base"]))
    direction = kpi_spec.get("direction", "higher")
    unit = kpi_spec.get("unit", "")
    band_cfg = config["performance_bands"][band]

    # Currency unit scaling — major-currency M (millions) → raw
    if unit == "CCY M":
        base = base * Decimal("1000000")

    # Deterministic factor within band range
    h = _stable_hash(staff_code, period, kpi_spec["id"])
    factor_lo, factor_hi = band_cfg["factor_range"]
    factor_span = factor_hi - factor_lo
    factor = factor_lo + ((h % 1000) / 1000.0) * factor_span

    # Add small noise within ±noise_range_pct
    noise_pct = config.get("noise_range_pct", 0.04)
    noise_h = _stable_hash(staff_code, period, kpi_spec["id"] + ":noise")
    noise = ((noise_h % 1000) / 1000.0 - 0.5) * 2.0 * noise_pct
    factor *= (1.0 + noise)

    # Direction-aware inversion: lower-is-better KPIs use 1.0/factor
    if direction == "lower":
        factor = 1.0 / factor

    value = base * Decimal(str(factor))

    # Scale-aware clamping
    if unit == "score_5":
        value = max(Decimal("1.0"), min(Decimal("5.0"), value))
    elif unit == "score_100":
        value = max(Decimal("0"), min(Decimal("100"), value))
    elif unit == "%":
        value = max(Decimal("0"), min(Decimal("100"), value))

    # Round to 2dp for currency/percentages, 0dp for counts
    if unit == "count":
        return value.quantize(Decimal("1"))
    return value.quantize(Decimal("0.01"))


# ────────────────────────────────────────────────────────────────────
# Generation entry point
# ────────────────────────────────────────────────────────────────────

def generate_for_period(
    period: str,
    username: str = "system_bm_generator",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Generate BSC actuals for all Branch Managers for one period.

    Returns summary dict:
        {
            "period": "2026-Q2",
            "branch_managers_processed": 94,
            "kpis_submitted": 1974,
            "failures": [...],
            "band_distribution": {"HIGH": 23, "MID": 52, "LOW": 19},
            "by_role": {"Branch Manager": 81, "Senior Branch Manager": 13}
        }
    """
    config = load_config()
    bms = find_branch_managers()

    actuals_path = _ROOT / "data" / f"bsc_actuals_{period}.json"

    from utils.db import db
    existing = db.load_json(actuals_path, default=[]) or []
    if not isinstance(existing, list):
        existing = existing.get("actuals", [])

    # Index existing by (staff_code, kpi_id) for idempotent upsert
    existing_by_key: Dict[Tuple[str, str], int] = {}
    for i, a in enumerate(existing):
        key = (a.get("staff_code"), a.get("kpi_id"))
        existing_by_key[key] = i

    submitted = 0
    failures: List[Dict[str, Any]] = []
    band_dist = {"HIGH": 0, "MID": 0, "LOW": 0}
    by_role: Dict[str, int] = {}

    ts = datetime.now(timezone.utc).isoformat()

    for staff_code, role in bms:
        role_cfg = config["roles"].get(role)
        if not role_cfg:
            failures.append({
                "staff_code": staff_code,
                "role": role,
                "reason": "no_role_config",
            })
            continue

        band = _band_for_staff(staff_code, role, config)
        band_dist[band] += 1
        by_role[role] = by_role.get(role, 0) + 1

        for kpi_spec in role_cfg["kpis"]:
            kpi_id = kpi_spec["id"]
            try:
                value = _value_for(staff_code, period, kpi_spec, band, config)
            except Exception as exc:
                failures.append({
                    "staff_code": staff_code,
                    "kpi_id": kpi_id,
                    "reason": f"value_compute_error: {exc}",
                })
                continue

            actual_record = {
                "actual_id": f"BMG_{staff_code}_{kpi_id}_{period}",
                "staff_code": staff_code,
                "kpi_id": kpi_id,
                "period": period,
                "value": float(value),
                "submitted_by": username,
                "submitted_at": ts,
                "source_module": "branch_manager_generator",
                "_v10329_band": band,
                "_v10329_role": role,
            }

            key = (staff_code, kpi_id)
            if key in existing_by_key:
                existing[existing_by_key[key]] = actual_record
            else:
                existing.append(actual_record)
                existing_by_key[key] = len(existing) - 1

            submitted += 1

    if not dry_run:
        db.save_json(actuals_path, existing)
        try:
            from utils.core_audit import audit_log
            audit_log(
                "BRANCH_MANAGER_BATCH_GENERATED",
                username,
                f"period={period} bms={len(bms)} submitted={submitted} "
                f"failures={len(failures)} bands={band_dist}",
                "branch_manager_generator",
                None,
                {
                    "period": period,
                    "branch_managers": len(bms),
                    "submitted": submitted,
                    "failures": len(failures),
                },
            )
        except Exception:
            # Tolerate audit_log failures in headless test contexts
            pass

    return {
        "period": period,
        "branch_managers_processed": len(bms),
        "kpis_submitted": submitted,
        "failures": failures,
        "band_distribution": band_dist,
        "by_role": by_role,
    }


def get_branch_manager_count() -> int:
    """Helper for G220 audit gate — count of active BMs."""
    return len(find_branch_managers())


def list_role_kpis(role: str) -> List[str]:
    """Helper — list KPI ids for a BM role from config."""
    cfg = load_config()
    role_cfg = cfg["roles"].get(role, {})
    return [k["id"] for k in role_cfg.get("kpis", [])]
