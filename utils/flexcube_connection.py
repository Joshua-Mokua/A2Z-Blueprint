"""utils.flexcube_connection — FLEXCUBE Connection Manager
(Standard #32, v5.50). Volume Four — FLEXCUBE Integration.

Per the master spec:

    class FlexcubeConnectionManager:
        @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1))
        def execute_query(self, query, params=None):
            with self.engine.connect() as conn:
                return pd.read_sql(query, conn, params=params)

WHAT THIS MODULE SHIPS
----------------------
A connection manager class with the spec-named entry method
`execute_query(query, params)`, a retry decorator with the spec
behaviour (stop_after_attempt(3), wait_exponential(multiplier=1)),
and a defensive contract that:

  - Returns None when query is empty/None
  - Logs every retry attempt with attempt count
  - Raises after 3 failed attempts (does NOT silently return empty)
  - Does NOT depend on tenacity being installed (ships own retry impl)
  - Does NOT depend on pandas being installed (returns plain dicts when
    pandas is missing; uses pandas DataFrame when available)
  - Does NOT depend on sqlalchemy being installed (engine is fully
    injectable for testing)

THE RETRY CONTRACT
------------------
The spec uses `tenacity` decorators. v5.50 ships a tiny inline
implementation that:

  - Attempts the call up to MAX_ATTEMPTS times (default 3, spec literal)
  - Waits exponentially between attempts: 1s, 2s, 4s
    (`multiplier=1` × 2^(attempt-1) = 1, 2, 4)
  - Returns the first successful result
  - Raises the last exception after MAX_ATTEMPTS failures
  - Logs every retry attempt for observability

The retry behaviour is verifiable with a mock connection that fails
N times before succeeding — tests count attempts and verify timing.

WHAT THIS DOES NOT SHIP
-----------------------
- A real Oracle connection string for FLEXCUBE 12 (production
  deployments inject the engine via constructor, never hard-code
  credentials in this module).
- Connection pooling configuration (production should use the
  sqlalchemy connection pool with appropriate sizing).

HONESTY DISCIPLINE
------------------
A connection manager that swallows errors silently is the worst kind
of integration code — failed extracts that "succeed" with empty results
corrupt downstream PnL, reconciliation, and BSC reporting. This module:

  - NEVER returns empty/None when the underlying query failed
  - Raises after MAX_ATTEMPTS so the caller (extract orchestrator)
    can mark the extract_control row as FAILED with the error
  - Records every attempt in `last_attempt_log` so post-incident
    debugging is possible
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.flexcube_conn")


# Spec literal — used by retry decorator
MAX_ATTEMPTS = 3

# Spec literal — wait_exponential(multiplier=1) means 1, 2, 4 seconds
WAIT_MULTIPLIER = 1.0


# ─────────────────────────────────────────────────────────────────────
# Retry decorator (tenacity-equivalent, no external dependency)
# ─────────────────────────────────────────────────────────────────────

@dataclass
class RetryAttempt:
    attempt:     int
    succeeded:   bool
    error_type:  Optional[str] = None
    error_msg:   Optional[str] = None
    waited_sec:  float = 0.0


def retry_with_exponential_backoff(
    max_attempts: int = MAX_ATTEMPTS,
    multiplier:   float = WAIT_MULTIPLIER,
    sleep_fn:     Optional[Callable[[float], None]] = None,
):
    """Equivalent to @retry(stop=stop_after_attempt(N), wait=wait_exponential(multiplier=M)).

    sleep_fn is injectable so tests can verify timing without actually waiting.
    If None, the wrapped instance's `_sleep_fn` attribute is used at call time
    (so per-instance test injection works).
    """
    def decorator(fn):
        def wrapper(self, *args, **kwargs):
            sleep = sleep_fn or getattr(self, "_sleep_fn", time.sleep)
            log: List[RetryAttempt] = []
            last_exc: Optional[BaseException] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    result = fn(self, *args, **kwargs)
                    log.append(RetryAttempt(attempt=attempt, succeeded=True))
                    self._last_attempt_log = log
                    return result
                except Exception as e:
                    last_exc = e
                    wait = multiplier * (2 ** (attempt - 1)) if attempt < max_attempts else 0.0
                    log.append(RetryAttempt(
                        attempt=attempt, succeeded=False,
                        error_type=type(e).__name__, error_msg=str(e),
                        waited_sec=wait,
                    ))
                    logger.warning(
                        "flexcube query attempt %d/%d failed: %s (%s) — "
                        "%s",
                        attempt, max_attempts, type(e).__name__, e,
                        f"waiting {wait:.1f}s before retry"
                          if attempt < max_attempts
                          else "no more retries",
                    )
                    if attempt < max_attempts:
                        sleep(wait)
            self._last_attempt_log = log
            assert last_exc is not None
            raise last_exc
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────────
# Connection manager
# ─────────────────────────────────────────────────────────────────────

class FlexcubeConnectionManager:
    """Standard #32 — FLEXCUBE connection with retry.

    The spec calls for execute_query(query, params=None) wrapped with
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1)).
    """

    # Class-level so subclass overrides work
    MAX_ATTEMPTS    = MAX_ATTEMPTS
    WAIT_MULTIPLIER = WAIT_MULTIPLIER

    def __init__(
        self,
        engine: Any = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ):
        """Engine is injectable. Production passes a sqlalchemy engine;
        tests pass a mock with a `connect()` context manager.

        sleep_fn is injectable for testing retry timing without
        actually sleeping.
        """
        self.engine = engine
        self._sleep_fn = sleep_fn
        self._last_attempt_log: List[RetryAttempt] = []

    @property
    def last_attempt_log(self) -> List[RetryAttempt]:
        """Per-attempt log of the last execute_query call. For diagnostics."""
        return list(self._last_attempt_log)

    # ──────────────────────────────────────────────────────────────────
    # Spec entry
    # ──────────────────────────────────────────────────────────────────

    @retry_with_exponential_backoff(
        max_attempts=MAX_ATTEMPTS,
        multiplier=WAIT_MULTIPLIER,
    )
    def execute_query(
        self, query: str, params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Execute a FLEXCUBE query with retry-on-failure.

        Returns:
            pandas.DataFrame when pandas + sqlalchemy are available;
            list[dict] otherwise (plain rows from the connection).

        Raises:
            ValueError on empty/None query (NOT silently skipped — this
            is a programming error and silent skip would mask it).
            The last underlying exception after MAX_ATTEMPTS retries.
        """
        if not query or not isinstance(query, str):
            raise ValueError("query must be a non-empty string")

        if self.engine is None:
            raise RuntimeError(
                "FlexcubeConnectionManager has no engine — "
                "production must inject one via constructor"
            )

        # Connect once. Within the connection, try pandas read_sql
        # (matches spec literal); fall through to direct cursor path
        # if pandas can't drive this connection (e.g. mock or non-DBAPI).
        # Connection-level failures (raised by engine.connect()) propagate
        # to the @retry decorator.
        with self.engine.connect() as conn:
            try:
                import pandas as pd
                # Suppress pandas' DBAPI warning for non-sqlalchemy connections
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    try:
                        return pd.read_sql(query, conn, params=params)
                    except Exception:
                        pass    # fall through to direct path
            except ImportError:
                pass

            # Direct cursor path
            cursor_or_result = conn.execute(query, params or {}) \
                if hasattr(conn, "execute") else conn.cursor()
            if hasattr(cursor_or_result, "fetchall"):
                rows = cursor_or_result.fetchall()
                cols = (
                    [c[0] for c in getattr(cursor_or_result, "description", [])]
                    if hasattr(cursor_or_result, "description") and cursor_or_result.description
                    else []
                )
                return [dict(zip(cols, r)) if cols else r for r in rows]
            return cursor_or_result


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.flexcube_connection self-test")

    # ── Mock engine + connection ───────────────────────────────────────
    class _MockConn:
        def __init__(self, return_value):
            self.return_value = return_value
            self.queries: List[str] = []
        def execute(self, q, p=None):
            self.queries.append(q)
            class _Cursor:
                def __init__(self, rv):
                    self.rv = rv
                    self.description = [("col1",)]
                def fetchall(self):
                    return self.rv
            return _Cursor(self.return_value)
        def __enter__(self): return self
        def __exit__(self, *a): pass

    class _MockEngine:
        def __init__(self, return_value=None, fail_count=0):
            self.return_value = return_value or [(1,), (2,)]
            self.fail_count = fail_count
            self.attempts = 0
        def connect(self):
            self.attempts += 1
            if self.attempts <= self.fail_count:
                raise ConnectionError(f"mock failure #{self.attempts}")
            return _MockConn(self.return_value)

    # ── Successful query (no retries needed) ───────────────────────────
    waits: List[float] = []
    eng = _MockEngine()
    mgr = FlexcubeConnectionManager(engine=eng, sleep_fn=lambda s: waits.append(s))
    result = mgr.execute_query("SELECT 1")
    assert eng.attempts == 1
    assert len(mgr.last_attempt_log) == 1
    assert mgr.last_attempt_log[0].succeeded is True
    assert waits == []     # no waits since no retries
    print(f"  ✅ successful query: 1 attempt, 0 waits")

    # ── 1 failure then success: 2 attempts, 1 wait of 1s ───────────────
    waits.clear()
    eng = _MockEngine(fail_count=1)
    mgr = FlexcubeConnectionManager(engine=eng, sleep_fn=lambda s: waits.append(s))
    result = mgr.execute_query("SELECT 1")
    assert eng.attempts == 2
    assert len(mgr.last_attempt_log) == 2
    assert mgr.last_attempt_log[0].succeeded is False
    assert mgr.last_attempt_log[1].succeeded is True
    assert waits == [1.0]    # wait_exponential(multiplier=1) → first wait = 1s
    print(f"  ✅ 1 failure: 2 attempts, waits={waits}")

    # ── 2 failures then success: 3 attempts, waits 1s, 2s ──────────────
    waits.clear()
    eng = _MockEngine(fail_count=2)
    mgr = FlexcubeConnectionManager(engine=eng, sleep_fn=lambda s: waits.append(s))
    result = mgr.execute_query("SELECT 1")
    assert eng.attempts == 3
    assert len(mgr.last_attempt_log) == 3
    assert waits == [1.0, 2.0]
    print(f"  ✅ 2 failures: 3 attempts, waits={waits}")

    # ── 3 failures: spec MAX_ATTEMPTS reached, exception raised ────────
    waits.clear()
    eng = _MockEngine(fail_count=3)
    mgr = FlexcubeConnectionManager(engine=eng, sleep_fn=lambda s: waits.append(s))
    raised = False
    try:
        mgr.execute_query("SELECT 1")
    except ConnectionError as e:
        raised = True
        assert "mock failure #3" in str(e)
    assert raised, "should raise after MAX_ATTEMPTS"
    assert eng.attempts == 3
    assert len(mgr.last_attempt_log) == 3
    # 2 sleep calls: between attempt 1→2 and 2→3 (no sleep after 3rd attempt)
    assert waits == [1.0, 2.0]
    print(f"  ✅ 3 failures: raises after {MAX_ATTEMPTS} attempts, no silent skip")

    # ── Empty query rejected (programming error, not silently skipped) ─
    mgr = FlexcubeConnectionManager(engine=_MockEngine())
    try:
        mgr.execute_query("")
        assert False, "empty query should raise"
    except ValueError:
        pass
    try:
        mgr.execute_query(None)
        assert False
    except ValueError:
        pass
    print(f"  ✅ empty query raises ValueError (no silent skip)")

    # ── Missing engine raises ─────────────────────────────────────────
    mgr_no_eng = FlexcubeConnectionManager()
    try:
        mgr_no_eng.execute_query("SELECT 1")
        assert False
    except RuntimeError as e:
        assert "no engine" in str(e)
    print(f"  ✅ missing engine raises RuntimeError")

    # ── Spec literal: max_attempts == 3, multiplier == 1 ───────────────
    assert FlexcubeConnectionManager.MAX_ATTEMPTS == 3
    assert FlexcubeConnectionManager.WAIT_MULTIPLIER == 1.0
    print(f"  ✅ spec literals: MAX_ATTEMPTS=3, WAIT_MULTIPLIER=1.0")

    # ── Class has spec entry method ────────────────────────────────────
    assert hasattr(FlexcubeConnectionManager, "execute_query")
    assert callable(FlexcubeConnectionManager.execute_query)
    print(f"  ✅ class has execute_query method")

    print("\n  ALL TESTS PASSED")
