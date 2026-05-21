"""utils/support_function_generator.py — Generate simulated activity
for the 7 support-function Chiefs (v10.328).

Closes the 'rest of the bank has no live numbers' gap. Mirrors the
v10.317 Teller / v10.327 Credit patterns: deterministic, role-aware,
idempotent, direction-aware activity generator.

Covers the 7 remaining Chiefs that aren't sales/credit:

  * Chief Operating Officer (43 staff) — Contact Centre, Operations,
    Clearing, Reconciliation, Procurement, Facilities, Cash Centre
  * Chief Financial Officer (11 staff) — Finance Officers, Business
    Analytics, Financial Controller, MLRO
  * Chief Risk Officer (3 staff) — Compliance Senior Manager, Risk
    Manager, Regulatory Compliance Officer
  * Chief Information Officer (125 staff) — Digital Channels, PHP
    Developers, Core Banking Support, ICT Support, Cyber Security,
    Business Analysts
  * Chief Human Resource Officer (7 staff) — HR Business Partners,
    HR Officer Admin
  * Chief Internal Auditor (0 staff) — personal scorecard only since
    no subtree exists
  * Chief Compliance Officer (4 staff) — Legal Officers, Manager-Legal

After running this generator, MD → each of these Chiefs drill-down
shows real activity flowing up.

Design principles (mirrors v10.317 + v10.327):
  - **Deterministic**: same staff_code + role + kpi + period → same value
  - **Role-aware**: each role uses its own KPI set per config
  - **Idempotent**: re-runs produce identical state via upsert
  - **Discipline-compliant**: every submission tagged with
    source_module='support_function_generator' for traceability
  - **Direction-aware**: lower-is-better KPIs (TAT, Incident Count,
    Breach Rate, Cash Difference) INVERT the band factor

Per Rule 7 (engines diagnostic-only EXCEPT producer batches): this
generator IS a producer (like v10.317 Teller, v10.323 pipeline bridge,
v10.327 Credit). Tagged submissions can be filtered or wiped.

Shipped: v10.328.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CONFIG_PATH = Path(__file__).parent.parent / "data" / "support_function_config.json"


# ════════════════════════════════════════════════════════════════════
# Configuration
# ════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PerformanceBand:
    name: str
    share: float
    factor_range: Tuple[float, float]


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
    chiefs: List[str]


def load_generator_config(
    path: Optional[Path] = None,
) -> GeneratorConfig:
    """Load support_function_config.json with sane fallbacks."""
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
            factor_range=(float(rng[0]), float(rng[1])),
        ))
    if not bands:
        # Fallback bands
        bands = [
            PerformanceBand("HIGH", 0.25, (1.10, 1.25)),
            PerformanceBand("MID", 0.55, (0.90, 1.10)),
            PerformanceBand("LOW", 0.20, (0.70, 0.90)),
        ]

    role_kpis: Dict[str, Dict[str, KpiSpec]] = {}
    for role, kpis_dict in (raw.get("role_kpi_targets") or {}).items():
        if role.startswith("_"):
            continue
        role_kpis[role] = {}
        for kpi_id, spec in kpis_dict.items():
            role_kpis[role][kpi_id] = KpiSpec(
                kpi_id=kpi_id,
                target=float(spec.get("target", 100.0)),
                noise_pct=float(spec.get("noise_pct", 0.10)),
                direction=str(spec.get("direction", "higher")),
                scale=str(spec.get("scale", "score")),
            )

    chiefs = raw.get("chiefs") or [
        "EXEC-COO-001", "EXEC-CFO-001", "EXEC-CRSO-001",
        "EXEC-CIO-001", "EXEC-CHRO-001", "EXEC-CIA-001",
        "EXEC-CCMP-001",
    ]

    return GeneratorConfig(
        bands=bands,
        role_kpi_targets=role_kpis,
        chiefs=chiefs,
    )


# ════════════════════════════════════════════════════════════════════
# Deterministic value generation
# ════════════════════════════════════════════════════════════════════

def _hash_int(*parts: str) -> int:
    """Stable hash of string parts to int."""
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def _period_index(period: str) -> int:
    """2025-Q3 → 3, 2026-Q1 → 5, etc."""
    try:
        year_str, q_str = period.split("-Q")
        return int(year_str) * 4 + int(q_str)
    except Exception:  # noqa: BLE001
        return 0


def performance_band(
    staff_code: str, cfg: GeneratorConfig,
) -> PerformanceBand:
    """Assign a stable performance band to each staff."""
    if not cfg.bands:
        return PerformanceBand("MID", 1.0, (1.0, 1.0))
    h = _hash_int(staff_code, "band") / (16**16)
    cumulative = 0.0
    for band in cfg.bands:
        cumulative += band.share
        if h <= cumulative:
            return band
    return cfg.bands[-1]


def kpi_value(
    staff_code: str, role: str, kpi_id: str, period: str,
    cfg: GeneratorConfig,
) -> Optional[float]:
    """Compute the deterministic value for one (staff, role, KPI,
    period) tuple.

    Direction-aware: for 'lower' direction KPIs (TAT, incident count,
    breach rate), the band factor INVERTS — high-band staff produce
    LOWER values (better outcomes), low-band staff produce HIGHER
    values (worse outcomes).
    """
    role_spec = cfg.role_kpi_targets.get(role)
    if not role_spec:
        return None
    spec = role_spec.get(kpi_id)
    if not spec:
        return None

    band = performance_band(staff_code, cfg)
    # Pick a stable factor within the band's range
    factor_seed = _hash_int(
        staff_code, role, kpi_id, period, "factor")
    pct_in_range = (factor_seed % 10000) / 10000.0
    lo, hi = band.factor_range
    factor = lo + (hi - lo) * pct_in_range

    # Direction awareness
    if spec.direction == "lower":
        # Invert: high performers produce LOWER values
        # Convert factor to its reciprocal-like form so that
        # band 1.20 maps to 0.83, band 0.80 maps to 1.25
        adjusted_factor = 2.0 - factor
    else:
        adjusted_factor = factor

    # Noise per period
    noise_seed = _hash_int(
        staff_code, role, kpi_id, period, "noise")
    noise_pct = ((noise_seed % 10000) / 10000.0 - 0.5) * 2 * spec.noise_pct

    value = spec.target * adjusted_factor * (1.0 + noise_pct)

    # Clamp non-negative
    if value < 0:
        value = 0.0

    # Cap percentages at 100
    if spec.scale == "pct" and value > 100:
        value = 100.0

    # Cap CX Score at 5
    if spec.scale == "score_5":
        if value > 5.0:
            value = 5.0
        elif value < 1.0:
            value = 1.0

    return round(value, 2)


# ════════════════════════════════════════════════════════════════════
# Staff enumeration
# ════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SupportStaff:
    staff_code: str
    role: str
    department: str
    manager_code: Optional[str]
    chief_code: str


def _chief_of(staff_code: str, universe: Dict[str, Any],
              chiefs: set) -> Optional[str]:
    """Walk up the manager chain to find which Chief this staff
    rolls up to."""
    code = staff_code
    depth = 0
    while code in universe and depth < 10:
        if code in chiefs:
            return code
        mgr = universe[code].manager_code
        if not mgr or mgr == code:
            return None
        code = mgr
        depth += 1
    return None


def _list_support_staff() -> List[SupportStaff]:
    """All staff under one of the 7 support-function Chief subtrees."""
    from utils.virtual_bank import staff_universe
    from utils.manager_rollup import _all_subordinate_codes

    cfg = load_generator_config()
    chiefs = set(cfg.chiefs)
    supported_roles = set(cfg.role_kpi_targets.keys())

    u = staff_universe()

    # Build all subtrees + include the Chiefs themselves
    all_subs: Dict[str, str] = {}  # staff_code -> chief_code
    for chief_code in cfg.chiefs:
        if chief_code in u:
            all_subs[chief_code] = chief_code
            for sc in _all_subordinate_codes(chief_code):
                # Avoid double-counting (some staff may appear in
                # multiple subtrees if hierarchy synthesis has loops)
                if sc not in all_subs:
                    all_subs[sc] = chief_code

    out: List[SupportStaff] = []
    for code, chief in sorted(all_subs.items()):
        if code not in u:
            continue
        s = u[code]
        if s.role in supported_roles:
            out.append(SupportStaff(
                staff_code=s.staff_code,
                role=s.role,
                department=s.department or "Support",
                manager_code=s.manager_code,
                chief_code=chief,
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
    errors: List[Tuple[str, str, str]] = field(default_factory=list)


def generate_quarter(
    period: str,
    dry_run: bool = False,
    cfg: Optional[GeneratorConfig] = None,
) -> GenerationResult:
    """Generate and submit BSC actuals for all support-function staff
    for one quarter."""
    if cfg is None:
        cfg = load_generator_config()

    submit_fn = None
    if not dry_run:
        from utils.bsc_engine import submit as submit_fn

    staff = _list_support_staff()
    submitted = 0
    skipped = 0
    failures = 0
    errors: List[Tuple[str, str, str]] = []

    for s in staff:
        role_spec = cfg.role_kpi_targets.get(s.role, {})
        for kpi_id in role_spec.keys():
            v = kpi_value(
                s.staff_code, s.role, kpi_id, period, cfg)
            if v is None:
                skipped += 1
                continue
            if dry_run:
                submitted += 1
                continue
            try:
                from decimal import Decimal
                ok, msg = submit_fn(
                    staff_code=s.staff_code,
                    kpi_id=kpi_id,
                    value=Decimal(str(v)),
                    period=period,
                    source_module="support_function_generator",
                    actor="support_function_generator",
                    metadata={
                        "role": s.role,
                        "chief": s.chief_code,
                        "department": s.department,
                    },
                )
                if ok:
                    submitted += 1
                else:
                    failures += 1
                    errors.append(
                        (s.staff_code, kpi_id, str(msg)[:120]))
            except Exception as exc:  # noqa: BLE001
                failures += 1
                errors.append(
                    (s.staff_code, kpi_id, str(exc)[:120]))

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
    """Run the generator for multiple periods."""
    if not periods:
        periods = ["2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]
    cfg = load_generator_config()
    out = []
    for p in periods:
        out.append(generate_quarter(p, dry_run=dry_run, cfg=cfg))
    return out
