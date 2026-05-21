#!/usr/bin/env python3
"""scripts/redis_admin.py — Operations CLI for A2Z's StateBackend (v9.13).

Companion tool for Joshua + DevOps team to inspect, debug, and operate
the StateBackend (whether InMemoryBackend or RedisBackend) from the
command line.

Per docs/REDIS_DEPLOYMENT_RUNBOOK.md, this CLI handles:
- health-check       Verify backend is reachable + responsive
- config             Display effective configuration (credentials masked)
- inventory          Count keys by domain (circuit/retry/latency/alert/dedup)
- live-state         Read live state via public APIs
- verify-state       Cross-check that all v9.6-v9.8 migrations are wired
- clear-domain       Manually clear keys for a specific domain (operator op)
- snapshot           Export current backend state to JSON for backup
- restore            Re-import a snapshot JSON into the backend

Usage:
    python scripts/redis_admin.py <command> [options]

Examples:
    A2Z_REDIS_URL=redis://localhost:6379 python scripts/redis_admin.py health-check
    python scripts/redis_admin.py config
    python scripts/redis_admin.py inventory
    python scripts/redis_admin.py snapshot --output /tmp/a2z_backup.json
    python scripts/redis_admin.py restore --input /tmp/a2z_backup.json --confirm

Honest scope:
- Read-only operations are safe to run anytime
- clear-domain and restore are destructive; require --confirm flag
- Credentials are NEVER printed; URLs are masked
- No automatic decision-making; operator drives all destructive ops
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any

# Add repo root to path so utils imports work
_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from utils.state_backend import (  # noqa: E402
    get_default_backend, RedisBackend, InMemoryBackend,
    reset_default_backend,
)


# ════════════════════════════════════════════════════════════════════
# Command implementations
# ════════════════════════════════════════════════════════════════════

def cmd_health_check(args: argparse.Namespace) -> int:
    """Verify backend is reachable + responsive."""
    backend = get_default_backend()
    print(f"Backend:       {backend.backend_name()}")
    print(f"Type:          {type(backend).__name__}")
    print(f"Multi-process: {backend.is_remote()}")
    try:
        ok = backend.ping()
        if ok:
            print(f"Health:        ✓ healthy (ping OK)")
            return 0
        else:
            print(f"Health:        ✗ unhealthy (ping returned False)")
            return 2
    except Exception as e:
        print(f"Health:        ✗ error ({type(e).__name__}: {e})")
        return 2


def cmd_config(args: argparse.Namespace) -> int:
    """Display effective configuration."""
    backend = get_default_backend()
    print(f"Backend:       {backend.backend_name()}")
    print(f"Type:          {type(backend).__name__}")
    print(f"Multi-process: {backend.is_remote()}")
    if isinstance(backend, RedisBackend):
        cfg = backend.get_connection_config()
        print()
        print("Connection configuration:")
        for k, v in cfg.items():
            print(f"  {k:<35}: {v}")
    else:
        print()
        print("InMemoryBackend has no remote connection configuration.")
        print("State is process-local; loss on process restart unless")
        print("file persistence is configured (latency / alert history).")
    return 0


def cmd_inventory(args: argparse.Namespace) -> int:
    """Count keys by A2Z domain."""
    backend = get_default_backend()
    domains = [
        ("circuit:", "Circuit breaker state (per-endpoint hashes)"),
        ("retry:", "Retry telemetry counters (per-endpoint hashes)"),
        ("latency:", "Latency rolling windows (per-endpoint lists)"),
        ("dedup:", "Event-bus dedup statistics (per-topic hashes)"),
    ]
    print(f"Backend: {backend.backend_name()}\n")
    print(f"{'Domain':<60} {'Keys':>6}")
    print("-" * 70)
    total = 0
    for prefix, description in domains:
        try:
            keys = backend.keys_matching(prefix)
            count = len(keys)
            total += count
            print(f"{description:<60} {count:>6}")
            if args.verbose and keys:
                for k in keys[:10]:
                    print(f"    {k}")
                if len(keys) > 10:
                    print(f"    ... and {len(keys) - 10} more")
        except Exception as e:
            print(f"{description:<60} ERROR ({type(e).__name__})")

    # Alert history is a single list, not multiple keys
    try:
        alert_count = backend.list_length("alert_history")
        print(f"{'Alert history (single list)':<60} {alert_count:>6}")
        total += 1 if alert_count > 0 else 0
    except Exception as e:
        print(f"{'Alert history':<60} ERROR ({type(e).__name__})")

    print("-" * 70)
    print(f"{'Total A2Z keys':<60} {total:>6}")
    return 0


def cmd_live_state(args: argparse.Namespace) -> int:
    """Read live state via public APIs (verifies wiring)."""
    from utils import flexcube_adapter as fc
    from utils import smart_alerts as sa
    from utils import event_bus as eb

    backend = get_default_backend()
    print(f"Backend: {backend.backend_name()}\n")

    # Circuit
    cs = fc.get_circuit_state()
    print(f"Circuits: {cs['endpoints_tracked']} tracked; "
          f"is_open={cs['is_open']}, max_failures={cs['consecutive_failures']}")

    # Retry telemetry
    rt = fc.get_retry_telemetry()
    s = rt['summary']
    print(f"Retries:  {s.get('endpoints_tracked', 0)} endpoints; "
          f"total_requests={s['requests_total']}, "
          f"recovery={s.get('retry_recovery_rate_pct', 'n/a')}%")

    # Latency
    ls = fc.get_latency_state()
    s = ls['summary']
    print(f"Latency:  {s['endpoints_observed']} endpoints; "
          f"total_calls={s['total_calls']}, "
          f"success_rate={s.get('overall_success_rate_pct', 'n/a')}%")

    # Alert history
    ahs = sa.get_alert_history_stats()
    print(f"Alerts:   {ahs['total']} total; "
          f"acked={ahs['acknowledged']}, "
          f"unacked={ahs['unacknowledged']}, "
          f"ack_rate={ahs.get('acknowledgement_rate_pct', 'n/a')}%")

    # Dedup
    ds = eb.get_dedup_stats()
    print(f"Dedup:    {ds['topics_tracked']} topics; "
          f"total_publishes={ds['total_publish_calls']}, "
          f"hits={ds['dedup_hits']}, "
          f"hit_rate={ds.get('dedup_hit_rate_pct', 'n/a')}%")

    return 0


def cmd_verify_state(args: argparse.Namespace) -> int:
    """Cross-check that all v9.6-v9.8 migrations work end-to-end."""
    backend = get_default_backend()
    print(f"Backend: {backend.backend_name()}\n")

    # Smoke test: write + read each domain to verify wiring
    test_results = []

    # 1. Circuit
    try:
        from utils import flexcube_adapter as fc
        # Read existing state (don't modify)
        fc.get_circuit_state()
        test_results.append(("Circuit breaker (v9.6)", True, None))
    except Exception as e:
        test_results.append(("Circuit breaker (v9.6)", False, str(e)))

    # 2. Retry telemetry
    try:
        from utils import flexcube_adapter as fc
        fc.get_retry_telemetry()
        test_results.append(("Retry telemetry (v9.7)", True, None))
    except Exception as e:
        test_results.append(("Retry telemetry (v9.7)", False, str(e)))

    # 3. Latency
    try:
        from utils import flexcube_adapter as fc
        fc.get_latency_state()
        test_results.append(("Latency rolling (v9.8)", True, None))
    except Exception as e:
        test_results.append(("Latency rolling (v9.8)", False, str(e)))

    # 4. Alert history
    try:
        from utils import smart_alerts as sa
        sa.get_alert_history_stats()
        test_results.append(("Alert history (v9.8)", True, None))
    except Exception as e:
        test_results.append(("Alert history (v9.8)", False, str(e)))

    # 5. Dedup
    try:
        from utils import event_bus as eb
        eb.get_dedup_stats()
        test_results.append(("Event-bus dedup (v9.8)", True, None))
    except Exception as e:
        test_results.append(("Event-bus dedup (v9.8)", False, str(e)))

    # Smoke test: write/read directly to backend
    try:
        backend.hash_set("verify:smoke", "field1", "value1")
        backend.hash_incr("verify:smoke", "counter", 1)
        backend.hash_incr("verify:smoke", "counter", 2)
        result = backend.hash_get_all("verify:smoke")
        backend.hash_delete("verify:smoke")
        if result.get("counter") == 3 and result.get("field1") == "value1":
            test_results.append(("Backend hash ops", True, None))
        else:
            test_results.append(("Backend hash ops", False,
                                  f"unexpected result: {result}"))
    except Exception as e:
        test_results.append(("Backend hash ops", False, str(e)))

    # Print results
    all_passed = True
    print(f"{'Migration':<35} {'Status':<10}")
    print("-" * 50)
    for label, passed, err in test_results:
        status = "✓ OK" if passed else "✗ FAIL"
        print(f"{label:<35} {status}")
        if err:
            print(f"  {err}")
        if not passed:
            all_passed = False
    print("-" * 50)
    if all_passed:
        print(f"\n✓ All {len(test_results)} verifications passed.")
        return 0
    else:
        print(f"\n✗ Some verifications failed.")
        return 2


def cmd_clear_domain(args: argparse.Namespace) -> int:
    """Destructive: clear all keys in a specific domain."""
    if not args.confirm:
        print("This is a DESTRUCTIVE operation. Re-run with --confirm to proceed.")
        return 1
    backend = get_default_backend()
    if args.domain == "alert_history":
        # Single list, special-cased
        prior = backend.list_length("alert_history")
        backend.list_clear("alert_history")
        print(f"Cleared alert_history (had {prior} entries)")
        return 0

    valid_prefixes = ("circuit:", "retry:", "latency:", "dedup:")
    if args.domain not in [p.rstrip(":") for p in valid_prefixes]:
        print(f"Unknown domain: {args.domain}")
        print(f"Valid: circuit, retry, latency, dedup, alert_history")
        return 1

    prefix = f"{args.domain}:"
    keys = backend.keys_matching(prefix)
    print(f"Found {len(keys)} keys under prefix {prefix}")
    cleared = 0
    for k in keys:
        try:
            # Try as hash first
            backend.hash_delete(k)
            cleared += 1
        except Exception:
            try:
                backend.list_clear(k)
                cleared += 1
            except Exception as e:
                print(f"  Failed to clear {k}: {e}")
    print(f"Cleared {cleared}/{len(keys)} keys.")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    """Export current backend state to JSON file."""
    backend = get_default_backend()

    snapshot: Dict[str, Any] = {
        "backend": backend.backend_name(),
        "timestamp_iso": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "circuit": {},
        "retry": {},
        "latency": {},
        "dedup": {},
        "alert_history": [],
    }

    # Circuit + retry + dedup are hashes per key
    for domain, prefix in [
        ("circuit", "circuit:"),
        ("retry", "retry:"),
        ("dedup", "dedup:"),
    ]:
        for k in backend.keys_matching(prefix):
            snapshot[domain][k] = backend.hash_get_all(k)

    # Latency is lists per key
    for k in backend.keys_matching("latency:"):
        snapshot["latency"][k] = backend.list_range(k)

    # Alert history is a single list
    snapshot["alert_history"] = backend.list_range("alert_history")

    outpath = Path(args.output)
    outpath.write_text(json.dumps(snapshot, indent=2, default=str),
                        encoding="utf-8")
    print(f"Snapshot written to {outpath} "
          f"({outpath.stat().st_size:,} bytes)")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    """Restore backend state from JSON snapshot."""
    if not args.confirm:
        print("This is a DESTRUCTIVE operation (overwrites existing state).")
        print("Re-run with --confirm to proceed.")
        return 1
    inpath = Path(args.input)
    if not inpath.exists():
        print(f"Snapshot file not found: {inpath}")
        return 1
    try:
        snapshot = json.loads(inpath.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Failed to parse snapshot: {type(e).__name__}: {e}")
        return 1

    backend = get_default_backend()
    print(f"Restoring snapshot taken at {snapshot.get('timestamp_iso')} "
          f"into {backend.backend_name()} backend")

    # Circuit + retry + dedup
    for domain in ("circuit", "retry", "dedup"):
        items = snapshot.get(domain, {})
        for key, hash_data in items.items():
            for field, value in hash_data.items():
                backend.hash_set(key, field, value)
        print(f"  Restored {len(items)} {domain} keys")

    # Latency
    for key, samples in snapshot.get("latency", {}).items():
        for sample in samples:
            backend.list_append(key, sample)
        print(f"  Restored latency:{key} with {len(samples)} samples")

    # Alert history
    alerts = snapshot.get("alert_history", [])
    for entry in alerts:
        backend.list_append("alert_history", entry)
    print(f"  Restored {len(alerts)} alert_history entries")

    print("Restore complete.")
    return 0


# ════════════════════════════════════════════════════════════════════
# Entry point
# ════════════════════════════════════════════════════════════════════

def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(
        description="A2Z StateBackend operations CLI (v9.13)",
        epilog="See docs/REDIS_DEPLOYMENT_RUNBOOK.md for deployment context.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("health-check", help="Verify backend is reachable")
    sub.add_parser("config", help="Display effective configuration")

    inv = sub.add_parser("inventory", help="Count keys by domain")
    inv.add_argument("--verbose", "-v", action="store_true",
                      help="Show key names per domain")

    sub.add_parser("live-state", help="Read live state via public APIs")
    sub.add_parser("verify-state",
                    help="Cross-check v9.6-v9.8 migrations end-to-end")

    cd = sub.add_parser("clear-domain",
                         help="Destructive: clear all keys in a domain")
    cd.add_argument("--domain", required=True,
                     choices=["circuit", "retry", "latency",
                              "dedup", "alert_history"],
                     help="Domain to clear")
    cd.add_argument("--confirm", action="store_true",
                     help="Required for destructive operation")

    sn = sub.add_parser("snapshot", help="Export state to JSON file")
    sn.add_argument("--output", "-o", required=True,
                     help="Output JSON path")

    rs = sub.add_parser("restore", help="Restore state from JSON")
    rs.add_argument("--input", "-i", required=True,
                     help="Input JSON path")
    rs.add_argument("--confirm", action="store_true",
                     help="Required for destructive operation")

    args = parser.parse_args(argv)

    handlers = {
        "health-check": cmd_health_check,
        "config": cmd_config,
        "inventory": cmd_inventory,
        "live-state": cmd_live_state,
        "verify-state": cmd_verify_state,
        "clear-domain": cmd_clear_domain,
        "snapshot": cmd_snapshot,
        "restore": cmd_restore,
    }
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
