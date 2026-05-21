"""
Branch Staff Activity Generator — v10.337

Brings 490 retail branch staff (142 Customer Service Officers + 348
branch sales staff) into the BSC cascade. Largest single department
gap before this batch — branch performance was scored at the BM
level (v10.329) but individual branch staff didn't have their own
scorecards.

This generator deliberately splits coverage with pipeline_to_bsc:
  - pipeline_to_bsc owns SALES KPIs (DISB_RETAIL, DISB_MSME,
    Total NFI, plus v10.337 activity KPIs PIPELINE_DEALS_WON,
    PIPELINE_CONVERSION_RATE, NEW_CUSTOMERS_ACQUIRED)
  - this generator owns OPERATIONAL / QUALITY KPIs (CX Score,
    Audit Score, COMPLIANCE_SCORE, Staff Productivity) for sales
    roles, AND the full service scorecard for CSOs

The two paths interlock — sales staff's scorecard is composed
from both. No KPI is submitted by both producers (avoids the
last-write-wins ambiguity the v10.335 multi-category aggregation
pattern flagged).

Scope (v10.337):
  - CUSTOMER_SERVICE bucket: Customer Service Officer (142 staff)
  - BRANCH_SALES bucket: 5 roles (BB / PB / BRM / BSRO / DSR) — 348 staff

Mirrors v10.317 Teller / v10.327 Credit / v10.328 Support /
v10.329 BM / v10.334 Propositions / v10.336 Specialist generators.
Same design principles:
  - Deterministic — hash(staff_code, period, kpi_id)
  - Direction-aware — dormancy + TAT INVERTED
  - Idempotent — re-runs upsert
  - Reads via utils.db (G2-clean)
  - Streamlit imports DEFERRED to function bodies (headless-safe)

9th producer in the cascade chain.
"""

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent
_CONFIG_PATH = _ROOT / "data" / "branch_staff_config.json"


# ────────────────────────────────────────────────────────────────────
# Config + scope resolution
# ────────────────────────────────────────────────────────────────────

def load_config() -> Dict[str, Any]:
    from utils.db import db as _db
    return _db.load_json(_CONFIG_PATH, default={}) or {}


def find_branch_staff() -> List[Tuple[str, str, str]]:
    """Return list of (staff_code, role, bucket_code) for all branch
    staff covered by this generator.

    Two buckets:
      - CUSTOMER_SERVICE: Customer Service Officer
      - BRANCH_SALES: BB / PB / BRM / BSRO / DSR
    """
    from utils.db import db as _db
    users_path = _ROOT / "data" / "users.json"
    users = _db.load_json(users_path, default={}) or {}

    cs_roles = {"Customer Service Officer"}
    sales_roles = {
        "Relationship Officer-Business Banker",
        "Relationship Officer-Personal Banker",
        "Branch Relationship Manager",
        "Branch Senior Relationship Officer",
        "Direct Sales Representative - Assets & Liabilities",
    }

    out: List[Tuple[str, str, str]] = []
    for username, u in users.items():
        if not isinstance(u, dict):
            continue
        code = str(u.get("staff_code") or username)
        role = (u.get("role") or "").strip()
        if not role:
            continue
        if role in cs_roles:
            out.append((code, role, "CUSTOMER_SERVICE"))
        elif role in sales_roles:
            out.append((code, role, "BRANCH_SALES"))

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
    bucket: str,
    config: Dict[str, Any],
) -> str:
    """Pick performance band deterministically by hash."""
    weights = {
        b: config["performance_bands"][b]["weight"]
        for b in ("HIGH", "MID", "LOW")
    }
    h = _stable_hash(staff_code, "_band", bucket)
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

    if unit == "CCY_M":
        base = base * Decimal("1000000")

    h = _stable_hash(staff_code, period, kpi_id)
    factor_lo, factor_hi = band_cfg["factor_range"]
    factor_span = factor_hi - factor_lo
    factor = factor_lo + ((h % 1000) / 1000.0) * factor_span

    noise_pct = config.get("noise_range_pct", 0.05)
    noise_h = _stable_hash(staff_code, period, kpi_id + ":noise")
    noise = ((noise_h % 1000) / 1000.0 - 0.5) * 2.0 * noise_pct
    factor *= (1.0 + noise)

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

    if unit == "count":
        return value.quantize(Decimal("1"))
    return value.quantize(Decimal("0.01"))


# ────────────────────────────────────────────────────────────────────
# Generation entry point
# ────────────────────────────────────────────────────────────────────

def generate_for_period(
    period: str,
    username: str = "system_branch_staff_generator",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Generate BSC actuals for all branch staff for one period.

    Returns summary dict with counts and per-bucket breakdown.
    """
    config = load_config()
    staff_list = find_branch_staff()

    from utils.db import db as _db
    actuals_path = _ROOT / "data" / f"bsc_actuals_{period}.json"
    raw = _db.load_json(actuals_path, default=[]) or []
    if isinstance(raw, list):
        existing = raw
    elif isinstance(raw, dict):
        existing = raw.get("actuals", [])
    else:
        existing = []

    existing_by_key: Dict[Tuple[str, str], int] = {}
    for i, a in enumerate(existing):
        if not isinstance(a, dict):
            continue
        if a.get("source_module") == "branch_staff_generator":
            key = (a.get("staff_code"), a.get("kpi_id"))
            existing_by_key[key] = i

    submitted = 0
    failures: List[Dict[str, Any]] = []
    by_bucket: Dict[str, int] = {}
    by_band: Dict[str, int] = {"HIGH": 0, "MID": 0, "LOW": 0}

    ts = datetime.now(timezone.utc).isoformat()
    role_cfgs = config.get("role_kpi_bases", {})

    for staff_code, role, bucket in staff_list:
        role_cfg = role_cfgs.get(role)
        if not role_cfg:
            failures.append({
                "staff_code": staff_code,
                "role": role,
                "reason": "no_role_config",
            })
            continue

        band = _band_for_staff(staff_code, bucket, config)
        by_band[band] += 1
        by_bucket[bucket] = by_bucket.get(bucket, 0) + 1

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
                "actual_id": f"BSG_{staff_code}_{kpi_id}_{period}",
                "staff_code": staff_code,
                "kpi_id": kpi_id,
                "period": period,
                "value": float(value),
                "submitted_by": username,
                "submitted_at": ts,
                "source_module": "branch_staff_generator",
                "_v10337_band": band,
                "_v10337_role": role,
                "_v10337_bucket": bucket,
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
        try:
            from utils.core_audit import audit_log
            audit_log(
                "BRANCH_STAFF_BATCH_GENERATED",
                username,
                f"period={period} staff={len(staff_list)} "
                f"submitted={submitted} failures={len(failures)}",
                "branch_staff_generator",
                None,
                {
                    "period": period,
                    "staff_count": len(staff_list),
                    "submitted": submitted,
                    "failures": len(failures),
                    "by_bucket": by_bucket,
                },
            )
        except Exception:
            pass

    return {
        "period": period,
        "staff_processed": len(staff_list),
        "kpis_submitted": submitted,
        "failures": failures,
        "by_bucket": by_bucket,
        "by_band": by_band,
    }


def get_branch_staff_count() -> int:
    """Helper for G226 audit gate."""
    return len(find_branch_staff())


def list_buckets_covered() -> List[str]:
    """Return bucket codes covered by this generator."""
    config = load_config()
    return list(config.get("buckets", {}).keys())
