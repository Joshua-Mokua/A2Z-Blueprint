"""utils/teller_activity_generator.py — Generate simulated Teller
activity for BSC demo (v10.317).

Drives 244 Tellers across 4 quarters of simulated operational
activity, submitting KPI actuals via the verified bsc_engine path.

Closes the "live numbers" gap for the cascade demo. After running
this generator, every Branch Manager's dashboard shows real numbers
rolling up from their Tellers through the corrected hierarchy
(v10.316): Teller → Branch Operations Supervisor → Branch Operations
Manager → Branch Manager → Area Manager → Head of Branches → Chief
Retail Banking Officer → MD.

Design principles:
  - **Deterministic**: same staff_code + period → same value. Re-running
    is safe — submissions are upserted by the bsc_engine.
  - **Realistic distribution**: 10/30/40/20 split across performance
    bands; small quarter-over-quarter drift; ~5% band movement.
  - **Discipline-compliant**: every submission tagged source_module=
    'teller_activity_generator' for traceability and filtered cleanup.
  - **Config-driven**: targets, distributions, noise, drift all live
    in data/teller_activity_config.json (admin-editable).
  - **Idempotent**: bsc_engine.submit uses upsert keying so re-runs
    produce identical state.

Per Rule 7 (engines diagnostic-only EXCEPT in dedicated batches):
this generator IS a producer — it explicitly submits BSC actuals.
It's the first batch where that's intentional. Submissions are tagged
for filtering so future generators or wipes can target this data.

Shipped: v10.317.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CONFIG_FILENAME = "teller_activity_config.json"
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
class KpiTarget:
    kpi_id: str
    target: float
    scale: str
    noise_pct: float
    direction: str


@dataclass(frozen=True)
class GeneratorConfig:
    bands: List[PerformanceBand]
    kpi_targets: Dict[str, KpiTarget]
    drift_pct_per_quarter: float
    max_drift_pct: float
    band_stay_pct: int
    band_move_up_pct: int
    band_move_down_pct: int
    source_module: str
    metadata_template: Dict[str, Any]
    schema_version: str


def load_generator_config() -> GeneratorConfig:
    """Load and parse data/teller_activity_config.json via canonical
    db.load_json path."""
    from utils.db import db
    raw = db.load_json(CONFIG_PATH, default=None)
    if raw is None:
        raise RuntimeError(
            f"{CONFIG_FILENAME} not found"
        )

    # Validate band shares sum to 1.0
    bands_raw = raw.get("performance_bands", {})
    bands: List[PerformanceBand] = []
    total_share = 0.0
    for name, spec in bands_raw.items():
        if name.startswith("_"):
            continue
        share = float(spec.get("share", 0))
        total_share += share
        fr = spec.get("factor_range", [1.0, 1.0])
        bands.append(PerformanceBand(
            name=name,
            share=share,
            factor_min=float(fr[0]),
            factor_max=float(fr[1]),
        ))
    if abs(total_share - 1.0) > 0.001:
        raise ValueError(
            f"performance_bands shares sum to {total_share}, "
            f"expected 1.0"
        )

    # KPI targets
    kpis_raw = raw.get("kpi_targets", {})
    kpi_targets: Dict[str, KpiTarget] = {}
    for kpi_id, spec in kpis_raw.items():
        if kpi_id.startswith("_"):
            continue
        kpi_targets[kpi_id] = KpiTarget(
            kpi_id=kpi_id,
            target=float(spec.get("target", 0)),
            scale=str(spec.get("scale", "0-100")),
            noise_pct=float(spec.get("noise_pct", 5)),
            direction=str(spec.get("direction", "higher")),
        )

    qd = raw.get("quarter_drift", {})
    bm = raw.get("band_movement", {})
    sim = raw.get("_simulation_metadata", {})

    return GeneratorConfig(
        bands=bands,
        kpi_targets=kpi_targets,
        drift_pct_per_quarter=float(
            qd.get("drift_pct_per_quarter", 0)),
        max_drift_pct=float(qd.get("max_drift_pct", 5)),
        band_stay_pct=int(bm.get("stay_pct", 90)),
        band_move_up_pct=int(bm.get("move_up_pct", 5)),
        band_move_down_pct=int(bm.get("move_down_pct", 5)),
        source_module=str(
            sim.get("source_module", "teller_activity_generator")),
        metadata_template=dict(
            sim.get("metadata_template", {})),
        schema_version=raw.get("_schema_version", "unknown"),
    )


# ════════════════════════════════════════════════════════════════════
# Determinism helpers
# ════════════════════════════════════════════════════════════════════

def _hash_pct(*parts: str) -> float:
    """Deterministic hash → percentage in [0, 1) for a tuple of
    string parts. Same inputs always produce the same output."""
    key = "|".join(str(p) for p in parts)
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()
    n = int(h[:8], 16)
    return n / 0xFFFFFFFF


def _quarter_index(period: str) -> int:
    """Convert period like '2025-Q3' or '2026-Q1' to a monotonic
    integer for drift calculations."""
    if "Q" not in period:
        return 0
    year_str, q_str = period.split("-Q")
    try:
        return int(year_str) * 4 + int(q_str) - 1
    except (ValueError, IndexError):
        return 0


# ════════════════════════════════════════════════════════════════════
# Performance band assignment
# ════════════════════════════════════════════════════════════════════

def performance_band(
    staff_code: str,
    period: str,
    cfg: Optional[GeneratorConfig] = None,
) -> PerformanceBand:
    """Determine a Teller's performance band for a given period.

    Base band is deterministic from staff_code. Quarter-over-quarter
    movement (per config) shifts ~5% of Tellers up/down each quarter.
    """
    if cfg is None:
        cfg = load_generator_config()

    # Base band assignment from staff_code
    base_pct = _hash_pct(staff_code, "base_band")
    cumulative = 0.0
    base_idx = 0
    for i, band in enumerate(cfg.bands):
        cumulative += band.share
        if base_pct < cumulative:
            base_idx = i
            break

    # Quarter movement (deterministic, depends on staff + period)
    move_pct = _hash_pct(staff_code, period, "band_movement")
    stay_threshold = cfg.band_stay_pct / 100.0
    move_up_threshold = stay_threshold + (
        cfg.band_move_up_pct / 100.0)

    idx = base_idx
    if move_pct < stay_threshold:
        pass  # stay
    elif move_pct < move_up_threshold:
        idx = max(0, base_idx - 1)  # move up (lower index = better)
    else:
        idx = min(len(cfg.bands) - 1, base_idx + 1)  # move down

    return cfg.bands[idx]


# ════════════════════════════════════════════════════════════════════
# KPI value generation
# ════════════════════════════════════════════════════════════════════

def kpi_value(
    staff_code: str,
    kpi_id: str,
    period: str,
    cfg: Optional[GeneratorConfig] = None,
) -> Optional[float]:
    """Compute the deterministic KPI value for a Teller in a period.

    Algorithm:
      1. Get the Teller's performance band for this period
      2. Pick the performance factor (deterministic within band range)
      3. Apply target × factor × (1 + drift)
      4. Add small noise (deterministic, bounded by noise_pct)
      5. Clamp to scale's valid range

    Returns None if kpi_id isn't in the generator's config (caller
    should skip that KPI for the Teller).
    """
    if cfg is None:
        cfg = load_generator_config()

    target_spec = cfg.kpi_targets.get(kpi_id)
    if not target_spec:
        return None

    band = performance_band(staff_code, period, cfg)

    # Performance factor — deterministic within band range
    factor_pct = _hash_pct(staff_code, kpi_id, period, "factor")
    factor = band.factor_min + (
        band.factor_max - band.factor_min) * factor_pct

    # Drift (small quarter-over-quarter improvement, capped)
    q_idx = _quarter_index(period)
    base_q_idx = _quarter_index("2025-Q3")  # baseline quarter
    drift_quarters = max(0, q_idx - base_q_idx)
    drift = min(
        cfg.drift_pct_per_quarter * drift_quarters / 100.0,
        cfg.max_drift_pct / 100.0,
    )

    # Noise — small Gaussian-ish via hash
    noise_pct_value = _hash_pct(staff_code, kpi_id, period, "noise")
    noise_signed = (noise_pct_value - 0.5) * 2  # -1 to +1
    noise_factor = noise_signed * (target_spec.noise_pct / 100.0)

    raw_value = (
        target_spec.target * factor *
        (1.0 + drift) * (1.0 + noise_factor)
    )

    # Clamp to scale range
    raw_value = max(0.0, raw_value)
    if target_spec.scale == "1-5":
        raw_value = min(5.0, max(1.0, raw_value))
    elif target_spec.scale == "0-100":
        raw_value = min(100.0, raw_value)
    else:
        # Custom scale — leave as-is
        pass

    return round(raw_value, 2)


# ════════════════════════════════════════════════════════════════════
# Generation API
# ════════════════════════════════════════════════════════════════════

@dataclass
class GenerationResult:
    period: str
    tellers_processed: int
    kpis_submitted: int
    kpis_skipped: int
    submit_failures: int
    errors: List[Tuple[str, str, str]]  # (staff_code, kpi_id, reason)


def _list_active_tellers() -> List[Any]:
    """Return all active Tellers from the staff universe."""
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    return sorted(
        [s for s in u.values() if s.role == "Teller"],
        key=lambda s: s.staff_code,
    )


def generate_quarter(
    period: str,
    dry_run: bool = False,
    cfg: Optional[GeneratorConfig] = None,
) -> GenerationResult:
    """Generate and submit BSC actuals for all active Tellers for one
    quarter.

    Args:
        period: 'YYYY-QN' format (e.g. '2026-Q2')
        dry_run: If True, compute values but don't submit
        cfg: Optional pre-loaded config (otherwise loaded from disk)

    Returns:
        GenerationResult with counts and any errors.
    """
    if cfg is None:
        cfg = load_generator_config()

    if dry_run:
        submit_fn = None
    else:
        from utils.bsc_engine import submit as submit_fn

    tellers = _list_active_tellers()
    submitted = 0
    skipped = 0
    failures = 0
    errors: List[Tuple[str, str, str]] = []

    metadata_base = {
        **cfg.metadata_template,
        "period": period,
    }

    for teller in tellers:
        for kpi_id in cfg.kpi_targets:
            value = kpi_value(
                teller.staff_code, kpi_id, period, cfg)
            if value is None:
                skipped += 1
                continue

            if dry_run:
                submitted += 1
                continue

            band = performance_band(
                teller.staff_code, period, cfg)
            metadata = {
                **metadata_base,
                "performance_band": band.name,
                "department": teller.department,
            }

            try:
                ok, msg = submit_fn(
                    staff_code=teller.staff_code,
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
                        (teller.staff_code, kpi_id, msg[:60]))
            except Exception as exc:  # noqa: BLE001
                failures += 1
                errors.append(
                    (teller.staff_code, kpi_id, str(exc)[:60]))

    return GenerationResult(
        period=period,
        tellers_processed=len(tellers),
        kpis_submitted=submitted,
        kpis_skipped=skipped,
        submit_failures=failures,
        errors=errors,
    )


def generate_history(
    periods: Optional[List[str]] = None,
    dry_run: bool = False,
) -> Dict[str, GenerationResult]:
    """Generate BSC actuals for multiple quarters.

    Default: last 4 quarters ending 2026-Q2 (most recent demo period).
    """
    if periods is None:
        periods = ["2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]

    cfg = load_generator_config()
    results: Dict[str, GenerationResult] = {}
    for period in periods:
        results[period] = generate_quarter(
            period, dry_run=dry_run, cfg=cfg)
    return results


# ════════════════════════════════════════════════════════════════════
# Reporting / inspection
# ════════════════════════════════════════════════════════════════════

def coverage_report(
    period: str = "2026-Q1",
    cfg: Optional[GeneratorConfig] = None,
) -> Dict[str, Any]:
    """Compute what coverage the generator would produce for a period
    (without submitting). Useful for previewing and validation."""
    if cfg is None:
        cfg = load_generator_config()
    tellers = _list_active_tellers()

    band_counts: Dict[str, int] = {b.name: 0 for b in cfg.bands}
    for t in tellers:
        band = performance_band(t.staff_code, period, cfg)
        band_counts[band.name] += 1

    sample_values: Dict[str, List[float]] = {}
    for kpi_id in cfg.kpi_targets:
        values = []
        for t in tellers[:20]:  # sample first 20 deterministically
            v = kpi_value(t.staff_code, kpi_id, period, cfg)
            if v is not None:
                values.append(v)
        sample_values[kpi_id] = values

    return {
        "period": period,
        "tellers_count": len(tellers),
        "kpis_per_teller": len(cfg.kpi_targets),
        "total_submissions_expected": len(tellers) * len(cfg.kpi_targets),
        "band_distribution": band_counts,
        "kpi_value_samples": sample_values,
    }


SPEC_DEVIATION_NOTE = (
    "This module is a PRODUCER, not diagnostic. It explicitly "
    "submits BSC actuals to the bsc_engine for the cascade demo. "
    "Every submission is tagged source_module='teller_activity_"
    "generator' for filtering / cleanup. Values are deterministic "
    "(same staff + period → same value); re-runs are idempotent "
    "via the bsc_engine's upsert keying. This is the first batch "
    "where Rule 7 (engines diagnostic-only) is intentionally "
    "loosened — and only inside this clearly-scoped generator."
)
