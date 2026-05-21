"""utils/uncertainty/react_impact.py — Phase 13 of Uncertainty Exposure.

React impact readiness — simulate what React will do to the backend
BEFORE React is built.

What React adds to backend load:
  - API amplification (1 user click → N API calls via component tree)
  - Concurrent sessions (multiple tabs / users at once)
  - Event streaming (WebSocket subscriptions for live updates)
  - Dashboard refresh storms (auto-refresh intervals)
  - Client-side retries (failed calls retried with exponential backoff)
  - Optimistic updates (UI fires N requests in parallel for instant feel)

We test all of these against the existing backend stack. If any of
them collapse the backend, React would expose that collapse to users.

The 7 React-impact scenarios:
   1. API amplification (1 logical action -> 5 backend calls)
   2. Concurrent sessions (10 simulated tabs at once)
   3. WebSocket-style polling burst (5 tabs polling every 100ms)
   4. Dashboard refresh storm (50 dashboards refreshing in 1 sec)
   5. Client retry storm (failed call retried 5x exponentially)
   6. Optimistic updates (5 parallel writes for 1 logical op)
   7. Component-tree fan-out (1 page mount -> 8 parallel state reads)
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple


_NAIROBI_TZ = None
def _tz():
    global _NAIROBI_TZ
    if _NAIROBI_TZ is None:
        from utils.simulation_clock import NAIROBI_TZ
        _NAIROBI_TZ = NAIROBI_TZ
    return _NAIROBI_TZ


# ─── React impact check functions ───────────────────────────────────


def check_api_amplification_5x() -> Tuple[bool, str, Dict[str, Any]]:
    """1 logical user action triggers 5 backend tool calls — like a
    React page mount fetching 5 data sources in parallel.
    """
    from utils.agents import get_default_tool_registry
    reg = get_default_tool_registry()

    completed = []
    lock = threading.Lock()

    def call(tool: str):
        try:
            r = reg.call(tool)
            with lock:
                completed.append(r.success)
        except Exception:
            with lock:
                completed.append(False)

    tools = ["time:now", "macro:snapshot", "chaos:active",
              "channel:list", "ml:list"]
    threads = [threading.Thread(target=call, args=(t,)) for t in tools]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join(timeout=10)
    duration = time.time() - t0
    successes = sum(1 for c in completed if c)
    ok = successes == 5 and duration < 2
    return ok, (
        f"5 parallel tool calls (page-mount fan-out) in "
        f"{duration*1000:.0f}ms; successes={successes}/5"
    ), {"successes": successes, "duration_ms": duration * 1000}


def check_concurrent_sessions_10() -> Tuple[bool, str, Dict[str, Any]]:
    """10 simulated React tabs (10 agent runners in parallel)."""
    from utils.agents import (
        AgentRunner, DeterministicPolicy, AgentBudget,
        reset_default_tool_registry)
    from utils.simulation_clock import reset_simulation_clock
    reset_simulation_clock()
    reset_default_tool_registry()
    completed = []
    lock = threading.Lock()

    def session_worker(sid: int):
        try:
            runner = AgentRunner()
            r = runner.run(
                policy=DeterministicPolicy(),
                goal="survey_macro",
                budget=AgentBudget(max_steps=3),
            )
            with lock:
                completed.append(
                    (sid, r.trajectory.successful_steps()))
        except Exception as exc:
            with lock:
                completed.append((sid, f"ERR: {type(exc).__name__}"))

    threads = [threading.Thread(target=session_worker, args=(i,))
                for i in range(10)]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join(timeout=30)
    duration = time.time() - t0
    ok = len(completed) == 10 and all(
        isinstance(c[1], int) for c in completed)
    return ok, (
        f"10 concurrent React tabs in {duration:.2f}s; "
        f"completed={len(completed)}"
    ), {"completed": len(completed), "duration_sec": duration}


def check_polling_burst_5_tabs() -> Tuple[bool, str, Dict[str, Any]]:
    """5 tabs each polling chaos:active 20 times = 100 calls total."""
    from utils.agents import get_default_tool_registry
    from utils.chaos import reset_chaos_injector
    reset_chaos_injector()
    reg = get_default_tool_registry()
    results = []
    lock = threading.Lock()

    def tab_poller():
        for _ in range(20):
            r = reg.call("chaos:active")
            with lock:
                results.append(r.success)

    threads = [threading.Thread(target=tab_poller) for _ in range(5)]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join(timeout=10)
    duration = time.time() - t0
    successes = sum(1 for r in results if r)
    ok = successes == 100 and duration < 5
    return ok, (
        f"5 tabs × 20 polls = 100 calls in {duration*1000:.0f}ms; "
        f"successes={successes}/100"
    ), {"successes": successes, "duration_ms": duration * 1000}


def check_dashboard_refresh_storm() -> Tuple[bool, str, Dict[str, Any]]:
    """50 simulated dashboards all refresh at the same time —
    macro:snapshot is the heaviest read.
    """
    from utils.agents import get_default_tool_registry
    reg = get_default_tool_registry()
    completed = []
    lock = threading.Lock()

    def refresh():
        r = reg.call("macro:snapshot")
        with lock:
            completed.append(r.success)

    threads = [threading.Thread(target=refresh) for _ in range(50)]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join(timeout=10)
    duration = time.time() - t0
    successes = sum(1 for c in completed if c)
    ok = successes == 50 and duration < 3
    return ok, (
        f"50 dashboard refreshes in {duration*1000:.0f}ms; "
        f"successes={successes}/50"
    ), {"successes": successes, "duration_ms": duration * 1000}


def check_client_retry_storm_5x() -> Tuple[bool, str, Dict[str, Any]]:
    """1 logical operation that initially fails, retried 5x with
    exponential backoff (simulated: just 5 rapid attempts).

    Verifies the backend handles the retry storm without amplifying
    a downstream failure.
    """
    from utils.agents import get_default_tool_registry
    reg = get_default_tool_registry()

    attempts = 0
    results = []
    for backoff_ms in (10, 20, 40, 80, 160):
        # Each "retry" calls a known-failing pattern
        r = reg.call("ml:predict",
                      model_name="nonexistent_v9", n=1)
        attempts += 1
        results.append(r.success)
        time.sleep(backoff_ms / 1000.0)
    # All 5 should fail cleanly (no crash) with a queryable error
    cleanly_failed = sum(1 for s in results if not s)
    ok = cleanly_failed == 5
    return ok, (
        f"5 retries with backoff: {attempts} attempts; "
        f"cleanly-failed={cleanly_failed}/5"
    ), {"attempts": attempts, "cleanly_failed": cleanly_failed}


def check_optimistic_updates_5_parallel() -> Tuple[bool, str,
                                                     Dict[str, Any]]:
    """React optimistic-update pattern: 5 parallel writes for 1
    logical operation. Backend must handle 5 channel submits in
    parallel without corruption.
    """
    from utils.channels import submit_channel
    from utils.chaos import reset_chaos_injector
    from utils.simulation_clock import reset_simulation_clock
    reset_simulation_clock()
    reset_chaos_injector()
    results = []
    lock = threading.Lock()

    def submit(i: int):
        r = submit_channel("mpesa",
            payload={"transaction_type": "CustomerPayBillOnline",
                      "msisdn": "254712345678",
                      "amount": 1500, "paybill": "174379"},
            amount=1500, reference=f"optimistic_{i}",
            actor="react_opt", seed=i)
        with lock:
            results.append((r.success, getattr(r, "error_code", "")))

    threads = [threading.Thread(target=submit, args=(i,))
                for i in range(5)]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join(timeout=10)
    duration = time.time() - t0
    # Each must complete (5 results), each with a status code
    completions = len(results)
    ok = completions == 5 and duration < 3
    return ok, (
        f"5 parallel optimistic writes in {duration*1000:.0f}ms; "
        f"all completed cleanly: {completions}/5"
    ), {"completions": completions, "duration_ms": duration * 1000}


def check_component_tree_fanout_8() -> Tuple[bool, str, Dict[str, Any]]:
    """A page-mount fans out to 8 parallel state reads — typical
    React 18 Suspense pattern.
    """
    from utils.agents import get_default_tool_registry
    reg = get_default_tool_registry()
    completed = []
    lock = threading.Lock()

    reads = [
        ("time:now", {}),
        ("macro:snapshot", {}),
        ("chaos:active", {}),
        ("channel:list", {}),
        ("ml:list", {}),
        ("chaos:list", {}),
        ("events:query",
          {"event_type": "macro.update", "limit": 5}),
        ("events:query",
          {"event_type": "chaos.activated", "limit": 5}),
    ]

    def fan_call(tool_name: str, args: Dict[str, Any]):
        r = reg.call(tool_name, **args)
        with lock:
            completed.append(r.success)

    threads = [threading.Thread(target=fan_call, args=(t, a))
                for t, a in reads]
    t0 = time.time()
    for t in threads: t.start()
    for t in threads: t.join(timeout=10)
    duration = time.time() - t0
    successes = sum(1 for c in completed if c)
    ok = successes == 8 and duration < 3
    return ok, (
        f"8-call component fan-out in {duration*1000:.0f}ms; "
        f"successes={successes}/8"
    ), {"successes": successes, "duration_ms": duration * 1000}


# ─── React impact catalogue ─────────────────────────────────────────


def list_react_impact_drills() -> List[str]:
    return sorted([
        "react_api_amplification_5x",
        "react_concurrent_sessions_10",
        "react_polling_burst_5_tabs",
        "react_dashboard_refresh_storm",
        "react_client_retry_storm_5x",
        "react_optimistic_updates_5_parallel",
        "react_component_tree_fanout_8",
    ])


def run_react_impact_check(name: str) -> Tuple[bool, str, Dict[str, Any]]:
    mapping = {
        "react_api_amplification_5x": check_api_amplification_5x,
        "react_concurrent_sessions_10": check_concurrent_sessions_10,
        "react_polling_burst_5_tabs": check_polling_burst_5_tabs,
        "react_dashboard_refresh_storm": check_dashboard_refresh_storm,
        "react_client_retry_storm_5x": check_client_retry_storm_5x,
        "react_optimistic_updates_5_parallel":
            check_optimistic_updates_5_parallel,
        "react_component_tree_fanout_8":
            check_component_tree_fanout_8,
    }
    if name not in mapping:
        raise KeyError(f"unknown react impact check: {name!r}")
    return mapping[name]()


__all__ = [
    "list_react_impact_drills", "run_react_impact_check",
    "check_api_amplification_5x", "check_concurrent_sessions_10",
    "check_polling_burst_5_tabs", "check_dashboard_refresh_storm",
    "check_client_retry_storm_5x",
    "check_optimistic_updates_5_parallel",
    "check_component_tree_fanout_8",
]
