"""
A2Z Daily Log — branch reconciliation checker (additive, new module).

Catches OVER-REPORTING: when the sum of individual self-reported quantitative activities in a branch
exceeds the branch's actual control total for that metric+day, flag an anomaly.

Control totals come from a PROVIDER so the source can change without touching the checker:
  * today  -> manual store (data/branch_control_totals.json), a manager enters per-metric branch
              actuals per day (group servers dump EOD, so real-time auto-fetch isn't available yet)
  * later  -> a CBS EOD-dump adapter implementing the same control_totals_for(branch, date) signature

Anomaly rule (confirmed): flag ONLY when reported_sum > control_total (over-report). Under-reporting
is not an anomaly. Only metrics with an entered control total are checked; others are silent.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

from utils.core import DATA_DIR
from utils.branch_log import metric_keys

_STORE = Path(DATA_DIR) / "branch_control_totals.json"


def _key(branch: str, day: str) -> str:
    return f"{str(branch).strip()}|{str(day).strip()}"


# ── manual control-total store (the provider, today) ──────────────────────
def _load_store() -> dict:
    try:
        if _STORE.exists():
            return json.loads(_STORE.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


def _save_store(data: dict) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(_STORE.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, _STORE)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def set_control_totals(branch: str, day: str, totals: dict) -> dict:
    """Manager/admin sets branch control totals for a metric map on a given day.

    Only known metric keys with numeric values are stored. Merges with any existing entry for that
    branch+day (so partial updates are fine). Returns the stored map for that branch+day.
    """
    valid = set(metric_keys())
    store = _load_store()
    entry = dict(store.get(_key(branch, day), {}))
    for k, v in (totals or {}).items():
        if k in valid:
            try:
                entry[k] = float(v or 0)
            except (TypeError, ValueError):
                continue
    store[_key(branch, day)] = entry
    _save_store(store)
    return entry


def control_totals_for(branch: str, day: str) -> dict:
    """Provider: return {metric: actual} branch control totals for a branch+day.

    Today this reads the manual store. A CBS EOD adapter can replace this function's body (or be
    chosen here) without changing any caller — the checker only depends on this signature.
    """
    return dict(_load_store().get(_key(branch, day), {}))


# ── the checker (pure) ────────────────────────────────────────────────────
def reconcile(logs: list, control: dict) -> dict:
    """Compare summed individual reports against branch control totals for ONE branch+day.

    Args:
        logs    : list of day-log dicts for a single branch+day (each has staff + metric fields)
        control : {metric: actual} control totals for that branch+day (from control_totals_for)

    Returns, for each metric that has a control total:
        { metric: { 'reported_sum': float, 'control_total': float, 'over_by': float,
                    'anomaly': bool, 'contributors': [{'staff_code','staff_name','reported'}] } }
    anomaly = reported_sum > control_total. Metrics with no control total are omitted (not checked).
    """
    result: dict = {}
    if not control:
        return result
    for metric, ctrl in control.items():
        try:
            ctrl_val = float(ctrl or 0)
        except (TypeError, ValueError):
            continue
        reported_sum = 0.0
        contributors = []
        for l in logs:
            try:
                v = float(l.get(metric, 0) or 0)
            except (TypeError, ValueError):
                v = 0.0
            if v:
                reported_sum += v
                contributors.append({
                    "staff_code": str(l.get("staff_code", "")),
                    "staff_name": str(l.get("staff_name", "")),
                    "reported": v,
                })
        reported_sum = round(reported_sum, 2)
        over_by = round(reported_sum - ctrl_val, 2)
        result[metric] = {
            "reported_sum": reported_sum,
            "control_total": ctrl_val,
            "over_by": over_by,
            "anomaly": reported_sum > ctrl_val,
            "contributors": sorted(contributors, key=lambda c: c["reported"], reverse=True),
        }
    return result


def reconcile_branch_day(logs_all: list, branch: str, day: str) -> dict:
    """Convenience: filter logs to a branch+day, pull control totals, and reconcile.

    'branch' matches the log's `unit` field (v1). Returns the same shape as reconcile(), plus a
    top-level 'branch'/'date' and an 'anomaly_count'.
    """
    logs = [l for l in logs_all
            if str(l.get("unit", "")) == str(branch) and str(l.get("log_date", "")) == str(day)]
    control = control_totals_for(branch, day)
    metrics = reconcile(logs, control)
    anomaly_count = sum(1 for m in metrics.values() if m["anomaly"])
    return {
        "branch": branch,
        "date": day,
        "metrics": metrics,
        "anomaly_count": anomaly_count,
        "log_count": len(logs),
    }
