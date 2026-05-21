"""utils/api_telemetry.py — API call latency telemetry.

Per Joshua Master Prompt Phase O2:
    'API telemetry' — p50/p95/p99 per endpoint.

Lightweight in-process telemetry that:
  - Captures (endpoint, method, status_code, duration_ms, timestamp)
  - Persists to JSONL (mode-aware via O8) at api_telemetry.jsonl
  - Provides decorator `@track_api_call(endpoint)` for instrumented funcs
  - Computes p50/p95/p99/mean/max per endpoint

This is the source dataset for the operational heatmap's bottleneck
view of API endpoints (vs the existing bottleneck view of event chains).
"""

from __future__ import annotations

import functools
import json
import time
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, List, Optional

REPO = Path(__file__).parent.parent
TELEMETRY_FILENAME = "api_telemetry.jsonl"


@dataclass
class APICallRecord:
    timestamp: str
    endpoint: str
    method: str
    status_code: int
    duration_ms: float
    actor: str = "system"
    environment: str = "dev"
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _telemetry_path() -> Path:
    try:
        from utils.environment import environment_paths
        data_root = environment_paths()["data_root"]
    except ImportError:
        data_root = REPO / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    return data_root / TELEMETRY_FILENAME


_lock = Lock()


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────

def record_call(
    *,
    endpoint: str,
    duration_ms: float,
    method: str = "GET",
    status_code: int = 200,
    actor: str = "system",
    correlation_id: Optional[str] = None,
) -> None:
    """Record a single API call's latency and outcome."""
    timestamp = datetime.now(timezone.utc).isoformat()
    try:
        from utils.environment import get_environment
        env = get_environment().value
    except ImportError:
        env = "dev"
    rec = APICallRecord(
        timestamp=timestamp, endpoint=endpoint, method=method,
        status_code=status_code, duration_ms=float(duration_ms),
        actor=actor, environment=env, correlation_id=correlation_id,
    )
    with _lock:
        try:
            with open(_telemetry_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec.to_dict(), separators=(",", ":"))
                        + "\n")
        except Exception:
            pass


def track_api_call(endpoint: str, *, method: str = "GET",
                    actor: Optional[str] = None):
    """Decorator that records latency + status of the wrapped function.

    Example:
        @track_api_call("/v1/bsc/scores", method="GET")
        def list_scores(...): ...
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            status = 200
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception:
                status = 500
                raise
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                try:
                    record_call(
                        endpoint=endpoint, method=method,
                        status_code=status,
                        duration_ms=duration_ms,
                        actor=actor or "system",
                    )
                except Exception:
                    pass
        return wrapper
    return decorator


def _percentile(values: List[float], p: float) -> Optional[float]:
    if not values: return None
    s = sorted(values)
    if len(s) == 1: return s[0]
    rank = (p / 100.0) * (len(s) - 1)
    lo = int(rank); hi = min(lo + 1, len(s) - 1)
    frac = rank - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def get_latency_distribution(endpoint: str,
                              *, since: Optional[str] = None,
                              until: Optional[str] = None,
                              method: Optional[str] = None
                              ) -> Dict[str, Any]:
    """p50/p95/p99 + count for an endpoint."""
    records = _load_records()
    durations: List[float] = []
    for r in records:
        if r.endpoint != endpoint: continue
        if method and r.method != method: continue
        if since and r.timestamp < since: continue
        if until and r.timestamp > until: continue
        durations.append(r.duration_ms)
    return {
        "endpoint": endpoint, "method": method,
        "count": len(durations),
        "p50_ms": _percentile(durations, 50),
        "p95_ms": _percentile(durations, 95),
        "p99_ms": _percentile(durations, 99),
        "mean_ms": (sum(durations) / len(durations) if durations else None),
        "max_ms": max(durations) if durations else None,
    }


def get_telemetry_summary(*, since: Optional[str] = None,
                           hours_back: int = 24) -> Dict[str, Any]:
    """Summary: per-endpoint counts + latency stats + error rate."""
    records = _load_records()
    if not since and hours_back:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        since = cutoff.isoformat()

    by_ep: Dict[str, List[APICallRecord]] = defaultdict(list)
    for r in records:
        if since and r.timestamp < since: continue
        by_ep[r.endpoint].append(r)

    out_ep: Dict[str, Any] = {}
    for ep, recs in by_ep.items():
        durations = [r.duration_ms for r in recs]
        errors = sum(1 for r in recs if r.status_code >= 500)
        out_ep[ep] = {
            "count": len(recs),
            "error_count": errors,
            "error_rate": (errors / len(recs)) if recs else 0,
            "p50_ms": _percentile(durations, 50),
            "p95_ms": _percentile(durations, 95),
            "p99_ms": _percentile(durations, 99),
            "mean_ms": (sum(durations) / len(durations)
                        if durations else None),
        }
    return {
        "since": since, "hours_back": hours_back,
        "total_calls": sum(len(v) for v in by_ep.values()),
        "endpoints": out_ep,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


def _load_records() -> List[APICallRecord]:
    path = _telemetry_path()
    if not path.exists(): return []
    out: List[APICallRecord] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    out.append(APICallRecord(**json.loads(line)))
                except Exception:
                    continue
    except Exception:
        return out
    return out


# ──────────────────────────────────────────────────────────────────────
# Self-tests
# ──────────────────────────────────────────────────────────────────────

def _test_record_call_persists():
    record_call(endpoint="/test/v10476/persist",
                 duration_ms=42.5, method="GET", status_code=200)
    dist = get_latency_distribution("/test/v10476/persist")
    assert dist["count"] >= 1


def _test_percentile_calculations():
    for _ in range(50):
        record_call(endpoint="/test/v10476/pct", duration_ms=10.0)
    record_call(endpoint="/test/v10476/pct", duration_ms=1000.0)
    dist = get_latency_distribution("/test/v10476/pct")
    assert dist["p50_ms"] is not None
    assert dist["p99_ms"] is not None
    assert dist["max_ms"] >= 1000


def _test_track_decorator():
    @track_api_call("/test/v10476/decorated")
    def handler(x):
        time.sleep(0.001)
        return x * 2
    out = handler(21)
    assert out == 42
    dist = get_latency_distribution("/test/v10476/decorated")
    assert dist["count"] >= 1


def _test_decorator_records_500_on_exception():
    @track_api_call("/test/v10476/err")
    def bad():
        raise ValueError("boom")
    try:
        bad()
    except ValueError:
        pass
    summary = get_telemetry_summary(hours_back=1)
    if "/test/v10476/err" in summary["endpoints"]:
        ep = summary["endpoints"]["/test/v10476/err"]
        assert ep["error_count"] >= 1


def _test_summary_well_formed():
    s = get_telemetry_summary(hours_back=24)
    for k in ("since", "total_calls", "endpoints", "as_of"):
        assert k in s


def self_test() -> None:
    _test_record_call_persists()
    _test_percentile_calculations()
    _test_track_decorator()
    _test_decorator_records_500_on_exception()
    _test_summary_well_formed()


__all__ = [
    "APICallRecord", "record_call", "track_api_call",
    "get_latency_distribution", "get_telemetry_summary",
    "TELEMETRY_FILENAME",
]


if __name__ == "__main__":
    import sys as _sys
    if str(REPO) not in _sys.path:
        _sys.path.insert(0, str(REPO))
    self_test()
    print("api_telemetry self-test passed")
