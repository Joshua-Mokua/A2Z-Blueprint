"""utils/cbs_baseline.py — CBS Baseline Snapshot for YoY Growth Tracking.

A baseline is a frozen snapshot of CBS state as of a specific date (typically
the prior year's closing date, e.g. 2025-12-31). Once captured, it does not
change — subsequent actuals computations compare against this fixed reference
to produce YoY growth deltas.

WHY A BASELINE
--------------
The BSC tracks Annual Target (e.g. "grow deposits by 12%") against actuals.
Without a fixed baseline, "growth" becomes ambiguous — measured against what?
The baseline captures the closing position at year-end so growth metrics have
an unambiguous denominator throughout the new fiscal year.

DUAL-SHAPE SUPPORT
------------------
When accounts.csv is available in cbs_dir (Joshua's production environment),
the baseline includes per-RM and per-branch breakdowns derived from
utils.actuals_engine. When only the bank-level aggregates (deposits_aggregate,
loans_aggregate, etc.) are present (sandbox / partial-data environments), the
baseline still captures bank-wide totals — per-RM sections are empty but the
file is structurally valid.

PATTERN
-------
- Baseline file path: data/cbs_baseline_<YYYY>_<MMM>_<DD>.json
- One per snapshot date; never overwritten
- load_baseline() returns the most recent
- compare() produces growth deltas with safe division (avoids /0)
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"
BASELINE_PREFIX = "cbs_baseline_"
BASELINE_SUFFIX = ".json"
SCHEMA_VERSION = "1.0"


def _resolve_cbs_dir() -> Path:
    """Resolve the CBS directory the same way actuals_engine does."""
    from utils.actuals_engine import get_cbs_paths
    cbs_dir, _ = get_cbs_paths()
    return cbs_dir


def _load_bank_aggregates_from_json(cbs_dir: Path) -> Dict[str, Any]:
    """Fallback when accounts.csv is missing — read the bank-level JSON
    aggregates that exist in every CBS deployment."""
    out: Dict[str, Any] = {}
    for name in (
        "deposits_aggregate", "loans_aggregate", "npl_aggregate",
        "customer_aggregate", "dormant_aggregate",
    ):
        p = cbs_dir / f"{name}.json"
        if p.exists():
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
                # Strip the meta fields, keep the data
                out[name] = {
                    k: v for k, v in payload.items()
                    if not k.startswith("_")
                }
            except Exception:
                pass
    return out


def snapshot_baseline(
    cbs_dir: Optional[Path] = None,
    as_of_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Compose a baseline snapshot dict from current CBS state.

    Args:
      cbs_dir: directory containing CBS files. Defaults to actuals_engine's
        resolution path.
      as_of_date: the date this snapshot represents (typically year-end).
        Defaults to today.

    Returns:
      A dict structured per the cbs_baseline schema:
        - _doc, _schema_version, snapshot_date, snapshot_generated_at
        - source_cbs_files: list of files actually read
        - bank_aggregates: bank-wide totals
        - per_rm: rm_code → metrics dict (empty if accounts.csv absent)
        - per_branch: branch_code → metrics dict (empty if accounts.csv absent)
        - per_segment: from bank-level aggregates (always populated where available)
    """
    if cbs_dir is None:
        cbs_dir = _resolve_cbs_dir()
    if as_of_date is None:
        as_of_date = date.today()

    # Import lazily to avoid a hard dependency when this module is imported
    # before actuals_engine is needed
    from utils.actuals_engine import (
        aggregate_cbs_by_rm, aggregate_cbs_by_branch, compute_bank_aggregates,
    )

    sources: List[str] = []
    per_rm: Dict[str, Any] = {}
    per_branch: Dict[str, Any] = {}
    bank_from_csv: Dict[str, Any] = {}

    accounts_csv = None
    for name in ("accounts.csv", "cbs_accounts.csv"):
        p = cbs_dir / name
        if p.exists():
            accounts_csv = p
            sources.append(name)
            break

    if accounts_csv is not None:
        try:
            per_rm = aggregate_cbs_by_rm(cbs_dir) or {}
        except Exception:
            per_rm = {}
        try:
            per_branch = aggregate_cbs_by_branch(cbs_dir) or {}
        except Exception:
            per_branch = {}
        try:
            bank_from_csv = compute_bank_aggregates(cbs_dir) or {}
        except Exception:
            bank_from_csv = {}

    # Always also read the bank-level JSON aggregates — they're authoritative
    # for some segment / product breakdowns even when accounts.csv exists
    bank_from_json = _load_bank_aggregates_from_json(cbs_dir)
    sources.extend(
        f"{name}.json" for name in (
            "deposits_aggregate", "loans_aggregate", "npl_aggregate",
            "customer_aggregate", "dormant_aggregate",
        ) if (cbs_dir / f"{name}.json").exists()
    )

    # Merge bank-level: CSV-derived takes precedence (live computation),
    # JSON aggregates fill gaps
    bank_aggregates: Dict[str, Any] = dict(bank_from_json)
    if bank_from_csv:
        bank_aggregates["from_accounts_csv"] = bank_from_csv

    return {
        "_doc": (
            f"CBS baseline snapshot for YoY growth tracking. Frozen at "
            f"{as_of_date.isoformat()}; do not modify."
        ),
        "_schema_version": SCHEMA_VERSION,
        "snapshot_date": as_of_date.isoformat(),
        "snapshot_generated_at": datetime.now(timezone.utc).isoformat(),
        "source_cbs_files": sources,
        "bank_aggregates": bank_aggregates,
        "per_rm": per_rm,
        "per_branch": per_branch,
        "summary": {
            "rm_count": len(per_rm),
            "branch_count": len(per_branch),
            "source_count": len(sources),
            "has_account_level_data": accounts_csv is not None,
        },
    }


def baseline_file_for(as_of_date: date) -> Path:
    """Canonical filename for a baseline at a given date."""
    return DATA_DIR / f"{BASELINE_PREFIX}{as_of_date.strftime('%Y_%b_%d')}{BASELINE_SUFFIX}"


def save_baseline(baseline: Dict[str, Any], path: Optional[Path] = None) -> Path:
    """Save baseline JSON atomically. Writes TWO files:
      - `data/cbs_baseline_<date>.json` (dated archive — permanent)
      - `data/cbs_baseline.json` (canonical current — overwritten on each save)

    The canonical path is what the schema validator (G230) looks at.
    The dated archive preserves historical snapshots so load_baseline()
    can find them and YoY comparisons can reference older baselines.

    Validates against the schema before writing (Pattern Q). Raises
    ValueError if the baseline doesn't conform.

    Returns the dated archive path.
    """
    # Pattern Q — validate-before-save. Refuses to ship a malformed baseline.
    try:
        from utils.schema_validator import validate_before_save
        result = validate_before_save("cbs_baseline.json", baseline)
        if not result.get("valid"):
            errs = result.get("errors", [])
            raise ValueError(
                f"Refusing to save invalid baseline: "
                f"{len(errs)} schema error(s). First: {errs[:3]}"
            )
    except ImportError:
        pass  # validator not present (testing environment)

    if path is None:
        as_of = baseline.get("snapshot_date")
        if as_of:
            path = baseline_file_for(date.fromisoformat(as_of))
        else:
            path = baseline_file_for(date.today())

    path.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write of the dated archive
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(baseline, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)

    # Canonical current file — used by schema validator + default load
    canonical = DATA_DIR / "cbs_baseline.json"
    tmp2 = canonical.with_suffix(canonical.suffix + ".tmp")
    tmp2.write_text(json.dumps(baseline, indent=2, default=str), encoding="utf-8")
    tmp2.replace(canonical)

    return path


def list_baselines() -> List[Path]:
    """All baseline files in data/, sorted by name (which sorts by date
    since the prefix is YYYY_MMM_DD)."""
    if not DATA_DIR.exists():
        return []
    return sorted(DATA_DIR.glob(f"{BASELINE_PREFIX}*{BASELINE_SUFFIX}"))


def load_baseline(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load the specified baseline, or the most recent if path is None.

    Returns None if no baseline files exist.
    """
    if path is None:
        candidates = list_baselines()
        if not candidates:
            return None
        path = candidates[-1]
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_growth(current: float, baseline: float) -> Optional[float]:
    """YoY growth percentage. Returns None if baseline is zero (undefined)."""
    if baseline is None or baseline == 0:
        return None
    return (current - baseline) / baseline * 100.0


def compare_bank_aggregate(
    current_value: float,
    baseline: Dict[str, Any],
    metric_path: str,
) -> Tuple[float, Optional[float], Optional[float]]:
    """Compare a current metric against the baseline.

    Args:
      current_value: the current actual value
      baseline: a baseline dict loaded via load_baseline()
      metric_path: dotted path into baseline['bank_aggregates'],
        e.g. 'deposits_aggregate.total_deposits_kes'

    Returns:
      (current_value, baseline_value, growth_pct)
      growth_pct is None when the baseline is 0 (growth undefined).
    """
    parts = metric_path.split(".")
    node: Any = baseline.get("bank_aggregates", {})
    for p in parts:
        if not isinstance(node, dict):
            return current_value, None, None
        node = node.get(p)
    if isinstance(node, (int, float)):
        baseline_value = float(node)
    elif isinstance(node, str):
        try:
            baseline_value = float(node)
        except ValueError:
            return current_value, None, None
    else:
        return current_value, None, None
    return current_value, baseline_value, _safe_growth(current_value, baseline_value)


def compare_rm_metric(
    current_value: float,
    baseline: Dict[str, Any],
    rm_code: str,
    metric_key: str,
) -> Tuple[float, Optional[float], Optional[float]]:
    """Compare an RM-level metric against the baseline.

    Returns (current_value, baseline_value, growth_pct). Both baseline_value
    and growth_pct can be None if RM or metric are missing.
    """
    rms = baseline.get("per_rm", {})
    if not isinstance(rms, dict) or rm_code not in rms:
        return current_value, None, None
    rm_data = rms[rm_code]
    if not isinstance(rm_data, dict) or metric_key not in rm_data:
        return current_value, None, None
    baseline_value = float(rm_data[metric_key])
    return current_value, baseline_value, _safe_growth(current_value, baseline_value)
