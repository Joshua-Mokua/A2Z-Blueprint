"""utils/credit_activity_generator.py — Generate simulated Credit
team activity for the cascade demo (v10.327).

Drives the Credit Analysts (7), Credit Admin Officers (8), Credit
Monitoring (1+1 Supervisor), and Collections/DRU Officers (4+ Write-
Off Officers) under the Chief Credit Officer subtree, producing one
quarter of simulated operational activity per role.

Closes the "Credit team has no live numbers" gap for the cascade demo.
After running this generator, MD → CCO drill-down shows real activity
flowing up:

  Credit Analyst (CREDIT_APPROVAL_RATE, TAT_STANDARD, REWORK_RATE,
                  INIT_COUNT, COMPLIANCE_SCORE)
    → Senior Manager Credit Analysis
       → Chief Credit Officer
          → MD

  Credit Admin Officer (LOAN_DISBURSEMENT_TAT, INIT_STATUS,
                        INIT_COUNT, COMPLIANCE_SCORE, AUDIT_SCORE)
    → Asst Manager Credit Administration / Senior Manager
       → Chief Credit Officer

  Manager Credit Monitoring (NPL_RATIO, PAR, INIT_STATUS,
                              COMPLIANCE_SCORE)
    → Senior Manager Collections
       → Chief Credit Officer

  Collections Officer / Write-Off Officer (COLLECTION_THROUGHPUT,
                                            PAR, INIT_COUNT, COMPLIANCE)
    → Senior Manager Collections & Recoveries (DRU)
       → Chief Credit Officer

Design principles (mirrors v10.317 Teller Activity Generator):
  - **Deterministic**: same staff_code + period → same value
  - **Role-aware**: each role uses its own KPI set per config
  - **Idempotent**: re-runs produce identical state via upsert
  - **Discipline-compliant**: every submission tagged with
    source_module='credit_activity_generator' for traceability
  - **Direction-aware**: lower-is-better KPIs (TAT, NPL Ratio, PAR,
    Rework Rate) INVERT the band factor so high performers have
    SHORTER TAT / LOWER risk metrics

Per Rule 7 (engines diagnostic-only EXCEPT producer batches): this
generator IS a producer (like v10.317 Teller and v10.323 pipeline
bridge). Tagged submissions can be filtered or wiped.

Shipped: v10.327.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CONFIG_FILENAME = "credit_activity_config.json"
CONFIG_PATH = Path(__file__).parent.parent / "data" / CONFIG_FILENAME


# ════════════════════════════════════════════════════════════════════
# Config loading
# ════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PerformanceBand:
    name: str
    share: float
    factor_min: float
    factor_max: float


@dataclass(frozen=True)
class KpiSpec:
    kpi_id: str
    target: float
    noise_pct: float
    direction: str  # 'higher' or 'lower'
    scale: str


@dataclass(frozen=True)
class GeneratorConfig:
    bands: List[PerformanceBand]
    role_kpi_targets: Dict[str, Dict[str, KpiSpec]]
    drift_pct_per_quarter: float
    max_drift_pct: float
    stay_pct: int
    move_up_pct: int
    move_down_pct: int
    source_module: str
    metadata_template: Dict[str, Any]


def load_generator_config(
    path: Optional[Path] = None,
) -> GeneratorConfig:
    """Load credit_activity_config.json with sane fallbacks."""
    cfg_path = path or CONFIG_PATH
    try:
        from utils.db import db
        raw = db.load_json(cfg_path, default={}) or {}
    except Exception:  # noqa: BLE001
        raw = {}

    bands = []
    for name, b in (raw.get("performance_bands") or {}).items():
        if name.startswith("_"):
            continue
        rng = b.get("factor_range", [1.0, 1.0])
        bands.append(PerformanceBand(
            name=name,
            share=float(b.get("share", 0.0)),
            factor_min=float(rng[0]),
            factor_max=float(rng[1]),
        ))
    if not bands:
        bands = [PerformanceBand(
            "on_target", 1.0, 0.95, 1.05)]

    role_kpi_targets: Dict[str, Dict[str, KpiSpec]] = {}
    for role, kpis in (raw.get("role_kpi_targets") or {}).items():
        if role.startswith("_"):
            continue
        role_kpi_targets[role] = {}
        for kpi_id, spec in kpis.items():
            if kpi_id.startswith("_"):
                continue
            role_kpi_targets[role][kpi_id] = KpiSpec(
                kpi_id=kpi_id,
                target=float(spec.get("target", 0)),
                noise_pct=float(spec.get("noise_pct", 0)),
                direction=spec.get("direction", "higher"),
                scale=spec.get("scale", ""),
            )

    drift = raw.get("quarter_drift") or {}
    band_move = raw.get("band_movement") or {}

    return GeneratorConfig(
        bands=bands,
        role_kpi_targets=role_kpi_targets,
        drift_pct_per_quarter=float(
            drift.get("drift_pct_per_quarter", 0.0)),
        max_drift_pct=float(drift.get("max_drift_pct", 0.0)),
        stay_pct=int(band_move.get("stay_pct", 100)),
        move_up_pct=int(band_move.get("move_up_pct", 0)),
        move_down_pct=int(band_move.get("move_down_pct", 0)),
        source_module=raw.get(
            "source_module", "credit_activity_generator"),
        metadata_template=raw.get("metadata_template") or {},
    )


# ════════════════════════════════════════════════════════════════════
# Deterministic staff → band assignment
# ════════════════════════════════════════════════════════════════════

def _hash_int(*parts: str) -> int:
    """Deterministic int hash from string parts."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode())
    return int.from_bytes(h.digest()[:8], "big")


def _period_index(period: str) -> int:
    """Period 'YYYY-QN' → integer index for drift computation."""
    try:
        year, q = period.split("-Q")
        return int(year) * 4 + int(q)
    except Exception:  # noqa: BLE001
        return 0


def performance_band(
    staff_code: str, period: str, cfg: GeneratorConfig,
) -> PerformanceBand:
    """Deterministically assign a performance band per
    (staff_code, period) with small quarter-over-quarter movement."""
    base_h = _hash_int("band_base", staff_code) % 10000
    base_pct = base_h / 100.0  # 0-100

    bands_sorted = sorted(
        cfg.bands, key=lambda b: -b.share
        if b.share else 0)  # highest-share first
    # Cumulative share
    cum = 0.0
    base_band = bands_sorted[-1]
    for b in bands_sorted:
        cum += b.share * 100
        if base_pct < cum:
            base_band = b
            break

    # Movement per quarter
    period_h = _hash_int(staff_code, period) % 100
    if period_h < cfg.stay_pct:
        return base_band
    elif period_h < cfg.stay_pct + cfg.move_up_pct:
        # move up one band if possible
        idx = bands_sorted.index(base_band)
        return bands_sorted[max(0, idx - 1)]
    else:
        idx = bands_sorted.index(base_band)
        return bands_sorted[min(len(bands_sorted) - 1, idx + 1)]


def kpi_value(
    staff_code: str, role: str, kpi_id: str, period: str,
    cfg: GeneratorConfig,
) -> Optional[float]:
    """Compute the deterministic value for one (staff, role, KPI,
    period). Returns None if no spec for this role/KPI."""
    role_kpis = cfg.role_kpi_targets.get(role)
    if not role_kpis:
        return None
    spec = role_kpis.get(kpi_id)
    if not spec:
        return None

    band = performance_band(staff_code, period, cfg)

    # Pick factor deterministically within band's range
    fh = _hash_int(staff_code, kpi_id, period) % 10000
    factor_pct = fh / 10000.0
    factor = (band.factor_min
               + factor_pct * (band.factor_max - band.factor_min))

    # For lower-is-better KPIs, invert: high performers have
    # SHORTER TAT / LOWER NPL.
    if spec.direction == "lower":
        # Convert factor: 1.20 (high perf) → 0.80 (20% better)
        factor = 2 - factor

    # Quarter drift (small improvement over time)
    p_idx = _period_index(period)
    # Use a synthetic anchor period to compute relative drift
    anchor = _period_index("2025-Q3")
    drift_quarters = p_idx - anchor
    drift = min(
        cfg.max_drift_pct,
        drift_quarters * cfg.drift_pct_per_quarter)
    if spec.direction == "higher":
        factor *= 1 + drift / 100
    else:
        factor *= 1 - drift / 100

    base = spec.target * factor

    # Noise
    nh = _hash_int(staff_code, kpi_id, period, "noise") % 10000
    noise_pct = ((nh / 10000.0) - 0.5) * 2 * spec.noise_pct
    value = base * (1 + noise_pct / 100)

    return round(max(0.0, value), 2)


# ════════════════════════════════════════════════════════════════════
# Staff selection
# ════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CreditStaff:
    staff_code: str
    role: str
    department: str
    manager_code: Optional[str]


def _list_credit_staff() -> List[CreditStaff]:
    """All Credit team staff under the CCO subtree."""
    from utils.virtual_bank import staff_universe
    from utils.manager_rollup import _all_subordinate_codes

    u = staff_universe()
    cco_subs = set(_all_subordinate_codes("EXEC-CCO-001"))
    cco_subs.add("EXEC-CCO-001")

    cfg = load_generator_config()
    supported_roles = set(cfg.role_kpi_targets.keys())

    out: List[CreditStaff] = []
    for code in sorted(cco_subs):
        if code not in u:
            continue
        s = u[code]
        if s.role in supported_roles:
            out.append(CreditStaff(
                staff_code=s.staff_code,
                role=s.role,
                department=s.department or "Credit",
                manager_code=s.manager_code,
            ))
    return out


# ════════════════════════════════════════════════════════════════════
# Generation API
# ════════════════════════════════════════════════════════════════════

@dataclass
class GenerationResult:
    period: str
    staff_processed: int
    kpis_submitted: int
    kpis_skipped: int
    submit_failures: int
    errors: List[Tuple[str, str, str]]


def generate_quarter(
    period: str,
    dry_run: bool = False,
    cfg: Optional[GeneratorConfig] = None,
) -> GenerationResult:
    """Generate and submit BSC actuals for all Credit team staff
    for one quarter.

    Args:
        period: 'YYYY-QN' format (e.g. '2026-Q2')
        dry_run: If True, compute values but don't submit
        cfg: Optional pre-loaded config

    Returns:
        GenerationResult with counts and any errors.
    """
    if cfg is None:
        cfg = load_generator_config()

    if dry_run:
        submit_fn = None
    else:
        from utils.bsc_engine import submit as submit_fn

    staff = _list_credit_staff()
    submitted = 0
    skipped = 0
    failures = 0
    errors: List[Tuple[str, str, str]] = []

    metadata_base = {
        **cfg.metadata_template,
        "period": period,
    }

    for cs in staff:
        role_kpis = cfg.role_kpi_targets.get(cs.role, {})
        for kpi_id in role_kpis:
            value = kpi_value(
                cs.staff_code, cs.role, kpi_id, period, cfg)
            if value is None:
                skipped += 1
                continue

            if dry_run:
                submitted += 1
                continue

            band = performance_band(cs.staff_code, period, cfg)
            metadata = {
                **metadata_base,
                "performance_band": band.name,
                "department": cs.department,
                "role": cs.role,
            }

            try:
                ok, msg = submit_fn(
                    staff_code=cs.staff_code,
                    kpi_id=kpi_id,
                    value=Decimal(str(value)),
                    period=period,
                    source_module=cfg.source_module,
                    actor=cfg.source_module,
                    metadata=metadata,
                )
                if ok:
                    submitted += 1
                else:
                    failures += 1
                    errors.append(
                        (cs.staff_code, kpi_id, msg[:60]))
            except Exception as exc:  # noqa: BLE001
                failures += 1
                errors.append(
                    (cs.staff_code, kpi_id, str(exc)[:60]))

    return GenerationResult(
        period=period,
        staff_processed=len(staff),
        kpis_submitted=submitted,
        kpis_skipped=skipped,
        submit_failures=failures,
        errors=errors,
    )


def generate_history(
    periods: Optional[List[str]] = None,
    dry_run: bool = False,
) -> List[GenerationResult]:
    """Generate activity for multiple periods (defaults to last 4
    quarters)."""
    if periods is None:
        periods = ["2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]
    cfg = load_generator_config()
    return [generate_quarter(p, dry_run=dry_run, cfg=cfg)
            for p in periods]


# CLI for ad-hoc generation
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate Credit team activity for BSC demo")
    parser.add_argument("--period", default="2026-Q2",
                         help="Period YYYY-QN")
    parser.add_argument("--all-quarters", action="store_true",
                         help="Generate Q3 2025 through Q2 2026")
    parser.add_argument("--dry-run", action="store_true",
                         help="Compute but don't submit")
    args = parser.parse_args()

    if args.all_quarters:
        results = generate_history(dry_run=args.dry_run)
        for r in results:
            print(f"  {r.period}: {r.kpis_submitted} submitted "
                   f"({r.staff_processed} staff)")
    else:
        r = generate_quarter(args.period, dry_run=args.dry_run)
        print(f"Generated for {r.period}:")
        print(f"  Staff processed: {r.staff_processed}")
        print(f"  KPIs submitted: {r.kpis_submitted}")
        print(f"  KPIs skipped: {r.kpis_skipped}")
        print(f"  Failures: {r.submit_failures}")
        for sc, kpi, msg in r.errors[:5]:
            print(f"    {sc}/{kpi}: {msg}")
