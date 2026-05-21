"""utils/state_backend.py — Multi-process state backend abstraction (v9.6).

Per docs/A2Z_V8_RETROSPECTIVE_FINAL_AND_V9_PLAN.md Part 7, the v9.x main track
includes Redis-backed state to support multi-Streamlit-process deployments.
v8.x state (circuit breaker, retry telemetry, latency, alert history, dedup)
is in-memory or JSON-file, which means:
- Two Streamlit processes don't share circuit state (one trips, other doesn't)
- File-write races on JSON persistence
- Per-process retry counter divergence

This module ships the abstraction. Circuit state migrates first (v9.6); retry
telemetry + latency (v9.7); alert history + dedup (v9.8). Each migration:
- Preserves the public function signature (no caller code changes)
- Goes through StateBackend interface
- Falls back gracefully to InMemoryBackend if Redis unavailable

# Backend selection

The default backend is selected at module load:
1. If env var `A2Z_REDIS_URL` is set AND redis-py is importable AND ping
   succeeds: use RedisBackend
2. Otherwise: use InMemoryBackend (matches v8.x behavior exactly)

Operators flip to Redis by setting `A2Z_REDIS_URL=redis://host:6379/0`.

# Honest scope

What this module ships (v9.6 scaffold):
- Abstract StateBackend interface (ABC)
- InMemoryBackend (production default; thread-safe; matches v8.x semantics)
- RedisBackend (used when A2Z_REDIS_URL set; graceful degradation on failure)
- Backend selection helper get_default_backend()
- Self-test demonstrating both backends pass the same contract

What this module does NOT ship:
- Redis cluster / sentinel support (single-instance only)
- Cross-DC replication
- Backup / restore tooling
- Encryption at rest (Redis ACL / AUTH config — operator concern)
- Schema versioning across upgrades
- Migration from in-memory state to Redis state at runtime

These are operational concerns or v9.7+ candidates.
"""
from __future__ import annotations
import os
import json
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


# ════════════════════════════════════════════════════════════════════
# Abstract interface
# ════════════════════════════════════════════════════════════════════

class StateBackend(ABC):
    """Abstract multi-process state backend.
    
    Operations are designed to map cleanly to Redis primitives (HGET, HSET,
    HINCRBY, RPUSH, LRANGE, LTRIM, etc.) while remaining Pythonic. The
    InMemoryBackend implements them with thread-safe dicts/lists; the
    RedisBackend implements them with redis-py calls.
    """

    # ── Hash operations (per-endpoint dict-of-dicts patterns) ────────
    @abstractmethod
    def hash_get(self, key: str, field: str) -> Optional[Any]:
        """Get a single field from a hash. Returns None if missing."""

    @abstractmethod
    def hash_set(self, key: str, field: str, value: Any) -> None:
        """Set a single field on a hash. Creates hash if missing."""

    @abstractmethod
    def hash_get_all(self, key: str) -> Dict[str, Any]:
        """Get all fields from a hash. Returns empty dict if missing."""

    @abstractmethod
    def hash_incr(self, key: str, field: str, amount: int = 1) -> int:
        """Atomically increment a numeric hash field. Returns new value.
        
        Critical for retry counters where multi-process atomicity matters.
        """

    @abstractmethod
    def hash_delete(self, key: str) -> None:
        """Delete an entire hash. No-op if missing."""

    # ── List operations (rolling windows, alert history) ─────────────
    @abstractmethod
    def list_append(self, key: str, value: Any,
                    max_length: Optional[int] = None) -> int:
        """Append to right end of list. Optionally truncate to max_length
        (FIFO from left). Returns new list length.
        """

    @abstractmethod
    def list_range(self, key: str, start: int = 0,
                   stop: int = -1) -> List[Any]:
        """Get range of list elements. Inclusive stop; -1 = end."""

    @abstractmethod
    def list_length(self, key: str) -> int:
        """Return current length of list. 0 if missing."""

    @abstractmethod
    def list_clear(self, key: str) -> None:
        """Remove the list entirely. No-op if missing."""

    # ── Set operations (dedup keys with TTL) ─────────────────────────
    @abstractmethod
    def set_add(self, key: str, value: str,
                ttl_seconds: Optional[int] = None) -> bool:
        """Add value to a set; optionally with key-level TTL. Returns True
        if newly added, False if already present.
        """

    @abstractmethod
    def set_contains(self, key: str, value: str) -> bool:
        """Test set membership."""

    # ── Scalar operations ────────────────────────────────────────────
    @abstractmethod
    def scalar_get(self, key: str) -> Optional[Any]:
        """Get a scalar value. Returns None if missing."""

    @abstractmethod
    def scalar_set(self, key: str, value: Any,
                   ttl_seconds: Optional[int] = None) -> None:
        """Set a scalar value with optional TTL."""

    @abstractmethod
    def scalar_delete(self, key: str) -> None:
        """Delete a scalar key. No-op if missing."""

    # ── Discovery / inspection ───────────────────────────────────────
    @abstractmethod
    def keys_matching(self, prefix: str) -> List[str]:
        """List all keys with the given prefix. Used for hash discovery
        (e.g. all per-endpoint circuit state keys).
        """

    # ── Health and metadata ──────────────────────────────────────────
    @abstractmethod
    def ping(self) -> bool:
        """Return True if backend is healthy."""

    @abstractmethod
    def is_remote(self) -> bool:
        """True if backend is multi-process-shared (e.g. Redis); False if
        per-process (e.g. in-memory).
        """

    @abstractmethod
    def backend_name(self) -> str:
        """Human-readable backend identifier for diagnostics."""


# ════════════════════════════════════════════════════════════════════
# In-memory implementation (default; matches v8.x semantics exactly)
# ════════════════════════════════════════════════════════════════════

class InMemoryBackend(StateBackend):
    """Single-process, thread-safe in-memory backend.
    
    Default backend when no A2Z_REDIS_URL is configured. Preserves v8.x
    behavior exactly — no semantic difference from the pre-v9.6 code.
    """

    def __init__(self) -> None:
        self._hashes: Dict[str, Dict[str, Any]] = {}
        self._lists: Dict[str, List[Any]] = {}
        self._sets: Dict[str, set] = {}
        self._scalars: Dict[str, Any] = {}
        self._set_expiries: Dict[str, float] = {}  # key → unix expiry
        self._scalar_expiries: Dict[str, float] = {}
        self._lock = threading.RLock()

    def _expire_if_needed(self, key: str, expiries: Dict[str, float],
                         storage: Dict[str, Any]) -> None:
        """Helper: evict an expired key. Caller must hold the lock."""
        exp = expiries.get(key)
        if exp is not None and time.time() >= exp:
            storage.pop(key, None)
            expiries.pop(key, None)

    # ── Hash ─────────────────────────────────────────────────────────
    def hash_get(self, key: str, field: str) -> Optional[Any]:
        with self._lock:
            h = self._hashes.get(key)
            if h is None:
                return None
            return h.get(field)

    def hash_set(self, key: str, field: str, value: Any) -> None:
        with self._lock:
            self._hashes.setdefault(key, {})[field] = value

    def hash_get_all(self, key: str) -> Dict[str, Any]:
        with self._lock:
            h = self._hashes.get(key)
            return dict(h) if h else {}

    def hash_incr(self, key: str, field: str, amount: int = 1) -> int:
        with self._lock:
            h = self._hashes.setdefault(key, {})
            current = h.get(field, 0)
            if not isinstance(current, (int, float)):
                raise TypeError(
                    f"hash_incr on non-numeric field {key}.{field}")
            new_value = int(current) + amount
            h[field] = new_value
            return new_value

    def hash_delete(self, key: str) -> None:
        with self._lock:
            self._hashes.pop(key, None)

    # ── List ─────────────────────────────────────────────────────────
    def list_append(self, key: str, value: Any,
                    max_length: Optional[int] = None) -> int:
        with self._lock:
            lst = self._lists.setdefault(key, [])
            lst.append(value)
            if max_length is not None and len(lst) > max_length:
                # FIFO truncation from left
                del lst[: len(lst) - max_length]
            return len(lst)

    def list_range(self, key: str, start: int = 0,
                   stop: int = -1) -> List[Any]:
        with self._lock:
            lst = self._lists.get(key)
            if lst is None:
                return []
            if stop == -1:
                return list(lst[start:])
            # Redis LRANGE stop is inclusive
            return list(lst[start: stop + 1])

    def list_length(self, key: str) -> int:
        with self._lock:
            lst = self._lists.get(key)
            return len(lst) if lst else 0

    def list_clear(self, key: str) -> None:
        with self._lock:
            self._lists.pop(key, None)

    # ── Set ──────────────────────────────────────────────────────────
    def set_add(self, key: str, value: str,
                ttl_seconds: Optional[int] = None) -> bool:
        with self._lock:
            self._expire_if_needed(key, self._set_expiries, self._sets)
            s = self._sets.setdefault(key, set())
            newly_added = value not in s
            s.add(value)
            if ttl_seconds is not None:
                self._set_expiries[key] = time.time() + ttl_seconds
            return newly_added

    def set_contains(self, key: str, value: str) -> bool:
        with self._lock:
            self._expire_if_needed(key, self._set_expiries, self._sets)
            s = self._sets.get(key)
            return s is not None and value in s

    # ── Scalar ───────────────────────────────────────────────────────
    def scalar_get(self, key: str) -> Optional[Any]:
        with self._lock:
            self._expire_if_needed(key, self._scalar_expiries,
                                    self._scalars)
            return self._scalars.get(key)

    def scalar_set(self, key: str, value: Any,
                   ttl_seconds: Optional[int] = None) -> None:
        with self._lock:
            self._scalars[key] = value
            if ttl_seconds is not None:
                self._scalar_expiries[key] = time.time() + ttl_seconds

    def scalar_delete(self, key: str) -> None:
        with self._lock:
            self._scalars.pop(key, None)
            self._scalar_expiries.pop(key, None)

    # ── Discovery ────────────────────────────────────────────────────
    def keys_matching(self, prefix: str) -> List[str]:
        with self._lock:
            results = set()
            for k in self._hashes.keys():
                if k.startswith(prefix):
                    results.add(k)
            for k in self._lists.keys():
                if k.startswith(prefix):
                    results.add(k)
            for k in self._scalars.keys():
                if k.startswith(prefix):
                    results.add(k)
            for k in self._sets.keys():
                if k.startswith(prefix):
                    results.add(k)
            return sorted(results)

    # ── Health ───────────────────────────────────────────────────────
    def ping(self) -> bool:
        return True

    def is_remote(self) -> bool:
        return False

    def backend_name(self) -> str:
        return "in_memory"


# ════════════════════════════════════════════════════════════════════
# Redis implementation (when A2Z_REDIS_URL is set)
# ════════════════════════════════════════════════════════════════════

class RedisBackend(StateBackend):
    """Redis-backed multi-process state backend.
    
    Used when A2Z_REDIS_URL env var is set and redis-py is importable.
    Falls back to InMemoryBackend on any connection error via the
    get_default_backend() selection helper.
    
    Key naming convention: prefix all A2Z keys with "a2z:" to namespace
    Redis usage if shared with other applications. Subkeys further
    namespace by domain: a2z:circuit:* / a2z:retry:* / a2z:latency:*
    / a2z:alert_history / a2z:dedup:* etc.
    
    Values are JSON-serialized at write, deserialized at read. Numeric
    counters use Redis HINCRBY for atomicity.

    # v9.11 — Production hardening

    Connection configuration honors several environment variables for
    operations tuning without code changes:
        A2Z_REDIS_URL                (required) — connection URL
            Format: redis://[user:pass@]host:port/db
                    rediss://...     (TLS — redis-py auto-detects)
        A2Z_REDIS_MAX_CONNECTIONS    (default 50) — pool size
        A2Z_REDIS_SOCKET_TIMEOUT     (default 5.0) — read/write timeout, seconds
        A2Z_REDIS_CONNECT_TIMEOUT    (default 5.0) — connection establishment, seconds
        A2Z_REDIS_HEALTH_CHECK_INTERVAL (default 30) — TCP keepalive ping, seconds
        A2Z_REDIS_KEY_PREFIX         (default "a2z:") — global key namespace

    URL parsing supports:
        - Plain Redis: redis://host:6379/0
        - TLS: rediss://host:6380/0 (redis-py validates cert by default)
        - ACL auth: redis://username:password@host:6379/0 (Redis 6+)
        - Sentinel / Cluster: NOT supported in this implementation (single-instance only)

    Resilience patterns:
        - Connection pool with explicit max_connections (prevents fd exhaustion
          under load)
        - Per-call socket timeout (prevents hung calls from blocking the
          process indefinitely)
        - Health check interval pings idle connections (detects silent
          network drops)
        - retry_on_timeout=True for transient network issues
    """

    KEY_PREFIX = "a2z:"

    # v9.11 production-hardening defaults
    DEFAULT_MAX_CONNECTIONS = 50
    DEFAULT_SOCKET_TIMEOUT = 5.0
    DEFAULT_CONNECT_TIMEOUT = 5.0
    DEFAULT_HEALTH_CHECK_INTERVAL = 30

    def __init__(
        self,
        url: str,
        key_prefix: str = "a2z:",
        max_connections: Optional[int] = None,
        socket_timeout: Optional[float] = None,
        connect_timeout: Optional[float] = None,
        health_check_interval: Optional[int] = None,
    ) -> None:
        """Initialize a production-hardened Redis client.

        Args mirror env-var configuration; explicit args win, env vars are
        consulted as fallback, hardcoded defaults are last resort.
        """
        try:
            import redis  # type: ignore
            import redis.connection  # type: ignore  # for ConnectionPool
        except ImportError:
            raise RuntimeError(
                "redis-py not installed; pip install redis to use RedisBackend")

        # Resolve configuration: explicit arg → env var → default
        env = os.environ
        resolved_max_conn = max_connections or int(
            env.get("A2Z_REDIS_MAX_CONNECTIONS",
                    self.DEFAULT_MAX_CONNECTIONS))
        resolved_socket_timeout = socket_timeout or float(
            env.get("A2Z_REDIS_SOCKET_TIMEOUT",
                    self.DEFAULT_SOCKET_TIMEOUT))
        resolved_connect_timeout = connect_timeout or float(
            env.get("A2Z_REDIS_CONNECT_TIMEOUT",
                    self.DEFAULT_CONNECT_TIMEOUT))
        resolved_health_check = health_check_interval or int(
            env.get("A2Z_REDIS_HEALTH_CHECK_INTERVAL",
                    self.DEFAULT_HEALTH_CHECK_INTERVAL))

        # ConnectionPool provides:
        # - Explicit max_connections (prevents fd exhaustion)
        # - Connection re-use across calls (avoids handshake overhead)
        # - Per-pool authentication (URL-encoded user:pass parsed automatically)
        pool = redis.ConnectionPool.from_url(
            url,
            decode_responses=True,
            max_connections=resolved_max_conn,
            socket_timeout=resolved_socket_timeout,
            socket_connect_timeout=resolved_connect_timeout,
            health_check_interval=resolved_health_check,
            retry_on_timeout=True,
        )
        self._redis = redis.Redis(connection_pool=pool)
        self._pool = pool
        self._key_prefix = key_prefix
        self._url = url
        self._max_connections = resolved_max_conn
        self._socket_timeout = resolved_socket_timeout
        self._connect_timeout = resolved_connect_timeout
        self._health_check_interval = resolved_health_check

    def _k(self, key: str) -> str:
        """Apply the configured key prefix."""
        return f"{self._key_prefix}{key}"

    def _serialize(self, value: Any) -> str:
        return json.dumps(value, default=str)

    def _deserialize(self, raw: Optional[str]) -> Any:
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # Fallback: return raw string (tolerates legacy/non-JSON values)
            return raw

    # v9.11 — Connection pool inspection (operator diagnostics)
    def get_connection_config(self) -> Dict[str, Any]:
        """Return the current connection-pool configuration. v9.11.

        Used by admin UI + redis_admin.py CLI to display effective config.
        Does not expose credentials — URL is masked.
        """
        # Mask credentials in URL for safe display
        masked_url = self._url
        try:
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(self._url)
            if parsed.username or parsed.password:
                netloc = parsed.hostname or ""
                if parsed.port:
                    netloc = f"{netloc}:{parsed.port}"
                if parsed.username:
                    netloc = f"{parsed.username}:****@{netloc}"
                masked_url = urlunparse(
                    (parsed.scheme, netloc, parsed.path,
                     parsed.params, parsed.query, parsed.fragment))
        except Exception:
            masked_url = "(masked)"
        return {
            "url": masked_url,
            "key_prefix": self._key_prefix,
            "max_connections": self._max_connections,
            "socket_timeout_seconds": self._socket_timeout,
            "connect_timeout_seconds": self._connect_timeout,
            "health_check_interval_seconds": self._health_check_interval,
            "tls_enabled": self._url.startswith("rediss://"),
            "auth_enabled": bool(
                "@" in self._url and self._url.split("://", 1)[-1].split("@")[0]),
        }

    # ── Hash ─────────────────────────────────────────────────────────
    def hash_get(self, key: str, field: str) -> Optional[Any]:
        raw = self._redis.hget(self._k(key), field)
        return self._deserialize(raw)

    def hash_set(self, key: str, field: str, value: Any) -> None:
        self._redis.hset(self._k(key), field, self._serialize(value))

    def hash_get_all(self, key: str) -> Dict[str, Any]:
        raw_dict = self._redis.hgetall(self._k(key))
        return {k: self._deserialize(v) for k, v in raw_dict.items()}

    def hash_incr(self, key: str, field: str, amount: int = 1) -> int:
        # HINCRBY is atomic across processes — the v9.x guarantee
        return int(self._redis.hincrby(self._k(key), field, amount))

    def hash_delete(self, key: str) -> None:
        self._redis.delete(self._k(key))

    # ── List ─────────────────────────────────────────────────────────
    def list_append(self, key: str, value: Any,
                    max_length: Optional[int] = None) -> int:
        full_key = self._k(key)
        new_len = int(self._redis.rpush(full_key, self._serialize(value)))
        if max_length is not None and new_len > max_length:
            # LTRIM keeps the rightmost max_length elements
            self._redis.ltrim(full_key, -max_length, -1)
            new_len = max_length
        return new_len

    def list_range(self, key: str, start: int = 0,
                   stop: int = -1) -> List[Any]:
        raw_list = self._redis.lrange(self._k(key), start, stop)
        return [self._deserialize(v) for v in raw_list]

    def list_length(self, key: str) -> int:
        return int(self._redis.llen(self._k(key)))

    def list_clear(self, key: str) -> None:
        self._redis.delete(self._k(key))

    # ── Set ──────────────────────────────────────────────────────────
    def set_add(self, key: str, value: str,
                ttl_seconds: Optional[int] = None) -> bool:
        full_key = self._k(key)
        added = bool(self._redis.sadd(full_key, value))
        if ttl_seconds is not None:
            self._redis.expire(full_key, ttl_seconds)
        return added

    def set_contains(self, key: str, value: str) -> bool:
        return bool(self._redis.sismember(self._k(key), value))

    # ── Scalar ───────────────────────────────────────────────────────
    def scalar_get(self, key: str) -> Optional[Any]:
        raw = self._redis.get(self._k(key))
        return self._deserialize(raw)

    def scalar_set(self, key: str, value: Any,
                   ttl_seconds: Optional[int] = None) -> None:
        full_key = self._k(key)
        if ttl_seconds is not None:
            self._redis.set(full_key, self._serialize(value), ex=ttl_seconds)
        else:
            self._redis.set(full_key, self._serialize(value))

    def scalar_delete(self, key: str) -> None:
        self._redis.delete(self._k(key))

    # ── Discovery ────────────────────────────────────────────────────
    def keys_matching(self, prefix: str) -> List[str]:
        # SCAN-based to avoid blocking on large keyspaces
        full_prefix = self._k(prefix)
        results = []
        cursor = 0
        while True:
            cursor, batch = self._redis.scan(
                cursor=cursor, match=f"{full_prefix}*", count=100)
            results.extend(
                k[len(self._key_prefix):] for k in batch)  # strip prefix
            if cursor == 0:
                break
        return sorted(results)

    # ── Health ───────────────────────────────────────────────────────
    def ping(self) -> bool:
        try:
            return bool(self._redis.ping())
        except Exception:
            return False

    def is_remote(self) -> bool:
        return True

    def backend_name(self) -> str:
        return f"redis ({self._url})"


# ════════════════════════════════════════════════════════════════════
# Backend selection
# ════════════════════════════════════════════════════════════════════

_DEFAULT_BACKEND: Optional[StateBackend] = None
_BACKEND_LOCK = threading.Lock()


def get_default_backend() -> StateBackend:
    """Return the default backend, selecting based on environment.
    
    Selection logic:
    1. If A2Z_REDIS_URL env var is set:
       - Try to construct RedisBackend (honors all v9.11 env-var tunables)
       - If construction or initial ping succeeds → use Redis
       - Otherwise → fall back to InMemoryBackend with diagnostic
    2. Otherwise → InMemoryBackend (matches v8.x behavior exactly)
    
    v9.11: RedisBackend reads its tuning env vars directly in __init__.
    The diagnostic message on URL failure masks credentials.
    
    Memoized: subsequent calls return the same backend instance.
    """
    global _DEFAULT_BACKEND
    if _DEFAULT_BACKEND is not None:
        return _DEFAULT_BACKEND

    with _BACKEND_LOCK:
        if _DEFAULT_BACKEND is not None:
            return _DEFAULT_BACKEND

        redis_url = os.environ.get("A2Z_REDIS_URL", "").strip()
        key_prefix = os.environ.get("A2Z_REDIS_KEY_PREFIX", "a2z:")
        if redis_url:
            try:
                backend = RedisBackend(redis_url, key_prefix=key_prefix)
                if backend.ping():
                    _DEFAULT_BACKEND = backend
                    return _DEFAULT_BACKEND
                # Ping failed — mask URL in diagnostic
                _masked = redis_url.split("@")[-1] if "@" in redis_url else redis_url
                print(f"[state_backend] Redis at {_masked} unreachable; "
                      f"falling back to in-memory", flush=True)
            except Exception as e:
                print(f"[state_backend] Redis init failed "
                      f"({type(e).__name__}: {e}); "
                      f"falling back to in-memory", flush=True)

        _DEFAULT_BACKEND = InMemoryBackend()
        return _DEFAULT_BACKEND


def reset_default_backend() -> None:
    """Reset the memoized default backend. Test-only utility — production
    code should not call this. Allows tests to inject different backends.
    """
    global _DEFAULT_BACKEND
    with _BACKEND_LOCK:
        _DEFAULT_BACKEND = None


def force_in_memory_backend() -> InMemoryBackend:
    """Force the default backend to be InMemoryBackend. Test utility.
    Returns the freshly-installed backend.
    """
    global _DEFAULT_BACKEND
    with _BACKEND_LOCK:
        _DEFAULT_BACKEND = InMemoryBackend()
        return _DEFAULT_BACKEND


def force_backend(backend: StateBackend) -> None:
    """Inject a specific backend instance. Test utility — used by
    behavioral tests that want to verify multi-process semantics by
    sharing a single InMemoryBackend across two simulated 'processes'.
    """
    global _DEFAULT_BACKEND
    with _BACKEND_LOCK:
        _DEFAULT_BACKEND = backend


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def _self_test() -> None:
    """Verify the InMemoryBackend implements the contract correctly."""
    print("=== state_backend self-test (InMemoryBackend) ===")
    b = InMemoryBackend()

    # Hash
    b.hash_set("circuit:loans", "consecutive_failures", 0)
    b.hash_set("circuit:loans", "tripped_until", 0.0)
    assert b.hash_get("circuit:loans", "consecutive_failures") == 0
    assert b.hash_incr("circuit:loans", "consecutive_failures", 1) == 1
    assert b.hash_incr("circuit:loans", "consecutive_failures", 1) == 2
    full = b.hash_get_all("circuit:loans")
    assert full["consecutive_failures"] == 2
    assert full["tripped_until"] == 0.0

    # List with truncation
    for i in range(15):
        b.list_append("alerts", {"id": i}, max_length=10)
    assert b.list_length("alerts") == 10
    rng = b.list_range("alerts")
    assert rng[0]["id"] == 5  # FIFO truncated 0..4
    assert rng[-1]["id"] == 14

    # Set with TTL
    assert b.set_add("dedup:topic1", "key_a", ttl_seconds=60) is True
    assert b.set_add("dedup:topic1", "key_a") is False
    assert b.set_contains("dedup:topic1", "key_a")

    # Scalar
    b.scalar_set("config:version", "v9.6")
    assert b.scalar_get("config:version") == "v9.6"

    # Discovery
    keys = b.keys_matching("circuit:")
    assert "circuit:loans" in keys

    # Health
    assert b.ping() is True
    assert b.is_remote() is False
    assert b.backend_name() == "in_memory"

    # Cleanup
    b.hash_delete("circuit:loans")
    assert b.hash_get_all("circuit:loans") == {}

    print("✓ all assertions passed")


if __name__ == "__main__":
    _self_test()
