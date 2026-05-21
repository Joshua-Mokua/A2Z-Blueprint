"""
Proposition Activity Generator — v10.334

Brings the Specialized Segments / Propositions arm to life in the BSC
cascade. Each proposition has a head whose scorecard reflects segment
performance (per banking convention — segment performance = segment
owner's performance).

Scope (v10.334):
  - WB (Women Banking): Head Of Women Banking — 2,737 customers
  - DIA (Diaspora): Sr Mgr Diaspora Banking — 780 customers
  - AGR (Agribusiness): shares head with DIA — 763 customers
  - 5 staff under Sr Mgr Diaspora (Diaspora + Agribusiness RMs + Sr RO)

Out of scope (already covered by other generators):
  - SME, GOV, TF: covered by pipeline_to_bsc (v10.323)
  - BNC: covered by pipeline_to_bsc
  - DFS: covered by support_function_generator (v10.328)

Mirrors v10.317 Teller / v10.327 Credit / v10.328 Support / v10.329 BM
generators. Same design principles:
  - Deterministic — hash(staff_code, period, kpi_id) → reproducible
  - Direction-aware — NPL/PAR/dormancy INVERTED (lower-is-better)
  - Idempotent — re-runs upsert
  - Scale-aware — currency-M bases → raw currency on output

Streamlit imports deferred to function bodies (headless-safe).
"""

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent
_CONFIG_PATH = _ROOT / "data" / "proposition_activity_config.json"


# ────────────────────────────────────────────────────────────────────
# Config + scope resolution
# ────────────────────────────────────────────────────────────────────

def load_config() -> Dict[str, Any]:
    from utils.db import db as _db
    return _db.load_json(_CONFIG_PATH, default={}) or {}


def find_specialized_segments_staff() -> List[Tuple[str, str, str]]:
    """Return list of (staff_code, role, proposition_code) for all
    staff covered by this generator.

    Scope: Head Women Banking (WB) + entire Diaspora & Special
    Segments department (covers DIA, AGR via shared head).
    """
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    out: List[Tuple[str, str, str]] = []

    for r in u.values():
        if not r.active:
            continue
        role = r.role or ""

        # Head of Women Banking — sole WB representative
        if r.staff_code == "300013" or "Women Banking" in role:
            out.append((r.staff_code, role, "WB"))
            continue

        # Diaspora & Special Segments department staff
        if r.department == "Diaspora & Special Segments":
            # Sr Mgr Diaspora heads both DIA and AGR — primary tag is DIA
            if "Senior Manager Diaspora" in role:
                out.append((r.staff_code, role, "DIA"))
            elif "Diaspora" in role:
                out.append((r.staff_code, role, "DIA"))
            elif "Agribusiness" in role:
                out.append((r.staff_code, role, "AGR"))
            else:
                # Unknown special-segments role — tag generic
                out.append((r.staff_code, role, "SS"))

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
    proposition: str,
) -> str:
    """Pick performance band deterministically. Heads use proposition
    head_band_weights if present; staff use standard performance_bands
    weights.
    """
    is_head = any(
        role == cfg.get("head_role")
        for cfg in config.get("propositions", {}).values()
    )
    if is_head:
        for cfg in config["propositions"].values():
            if cfg.get("head_role") == role:
                weights = cfg.get("head_band_weights", {})
                break
        else:
            weights = {
                b: config["performance_bands"][b]["weight"]
                for b in ("HIGH", "MID", "LOW")
            }
    else:
        weights = {
            b: config["performance_bands"][b]["weight"]
            for b in ("HIGH", "MID", "LOW")
        }

    h = _stable_hash(staff_code, "_band", proposition)
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
        value = max(Decimal("0"), min(Decimal("100"), value))

    if unit == "count":
        return value.quantize(Decimal("1"))
    return value.quantize(Decimal("0.01"))


# ────────────────────────────────────────────────────────────────────
# Generation entry point
# ────────────────────────────────────────────────────────────────────

def generate_for_period(
    period: str,
    username: str = "system_proposition_generator",
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Generate BSC actuals for all specialized-segments staff for one
    period.

    Returns summary dict:
        {
            "period": "2026-Q2",
            "staff_processed": 8,
            "kpis_submitted": 64,
            "failures": [],
            "by_proposition": {"WB": 1, "DIA": 5, "AGR": 2},
            "by_band": {"HIGH": 3, "MID": 4, "LOW": 1},
        }
    """
    config = load_config()
    staff_list = find_specialized_segments_staff()

    actuals_path = _ROOT / "data" / f"bsc_actuals_{period}.json"
    existing: List[Dict[str, Any]] = []
    if actuals_path.exists():
        from utils.db import db as _db
        existing = _db.load_json(actuals_path, default=[]) or []
        if not isinstance(existing, list):
            existing = existing.get("actuals", [])

    # Index existing by (staff_code, kpi_id, source) for idempotent upsert
    existing_by_key: Dict[Tuple[str, str], int] = {}
    for i, a in enumerate(existing):
        if not isinstance(a, dict):
            continue
        if a.get("source_module") == "proposition_activity_generator":
            key = (a.get("staff_code"), a.get("kpi_id"))
            existing_by_key[key] = i

    submitted = 0
    failures: List[Dict[str, Any]] = []
    by_prop: Dict[str, int] = {}
    by_band: Dict[str, int] = {"HIGH": 0, "MID": 0, "LOW": 0}

    ts = datetime.now(timezone.utc).isoformat()
    role_cfgs = config.get("role_kpi_bases", {})

    for staff_code, role, prop in staff_list:
        role_cfg = role_cfgs.get(role)
        if not role_cfg:
            failures.append({
                "staff_code": staff_code,
                "role": role,
                "reason": "no_role_config",
            })
            continue

        band = _band_for_staff(staff_code, role, config, prop)
        by_band[band] += 1
        by_prop[prop] = by_prop.get(prop, 0) + 1

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
                "actual_id": f"PRG_{staff_code}_{kpi_id}_{period}",
                "staff_code": staff_code,
                "kpi_id": kpi_id,
                "period": period,
                "value": float(value),
                "submitted_by": username,
                "submitted_at": ts,
                "source_module": "proposition_activity_generator",
                "_v10334_band": band,
                "_v10334_role": role,
                "_v10334_proposition": prop,
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
        # Invalidate the BSC actuals cache for this period
        try:
            from utils.bsc_engine import invalidate_actuals_index
            invalidate_actuals_index(period)
        except Exception:
            pass
        # Audit log
        try:
            from utils.core_audit import audit_log
            audit_log(
                "PROPOSITION_BATCH_GENERATED",
                username,
                f"period={period} staff={len(staff_list)} "
                f"submitted={submitted} failures={len(failures)}",
                "proposition_activity_generator",
                None,
                {
                    "period": period,
                    "staff_count": len(staff_list),
                    "submitted": submitted,
                    "failures": len(failures),
                    "by_proposition": by_prop,
                },
            )
        except Exception:
            pass

    return {
        "period": period,
        "staff_processed": len(staff_list),
        "kpis_submitted": submitted,
        "failures": failures,
        "by_proposition": by_prop,
        "by_band": by_band,
    }


def get_proposition_staff_count() -> int:
    """Helper for G223 audit gate — count of staff covered."""
    return len(find_specialized_segments_staff())


def list_propositions_covered() -> List[str]:
    """Return proposition codes covered by this generator."""
    config = load_config()
    return list(config.get("propositions", {}).keys())
