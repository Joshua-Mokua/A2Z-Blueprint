"""utils/pillar_weights_canonical.py — v10.384 Canonical Pillar Weights Accessor.

Rescues the body's prioritization organ. Per Joshua's directive at v10.383
wrap-up: "after we need rescue body's prioritization organ".

The v10.382 deep review (PILLAR_WEIGHTS_ADMIN_MODULE_REVIEW_v10.382.md)
surfaced critical drift:

  Three storage locations for the same concept:
    1. kpi_library.json::pillar_weights  → CANONICAL (5 readers)
    2. kpi_library.json::pillars[].weight → SHADOW (read for structure)
    3. org_config.json::pillar_weights   → ORPHAN (written, NEVER read)

  Two admin UIs editing pillar weights:
    - Bank Identity tab → writes to org_config (ORPHAN — silent §5.4 failure)
    - KPI Library Pillar Weights tab → writes to kpi_library (CANONICAL)

v10.384 establishes a single canonical accessor:
    - `get_pillar_weights()` — reads from canonical location
    - `save_pillar_weights(...)` — writes to canonical + appends to history
    - `validate_pillar_weights(...)` — enforces sum=1.0 + all positive
    - `get_pillar_weights_history(...)` — recent changes
    - `migrate_orphan_pillar_weights(...)` — checks org_config orphan

Consumers can adopt this gradually. The existing direct reads of
`kpi_library.json::pillar_weights` still work (canonical location unchanged).

Module purity: leaf module — zero upward `utils.*` imports.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"
KPI_LIBRARY_PATH = DATA_DIR / "kpi_library.json"
ORG_CONFIG_PATH = DATA_DIR / "org_config.json"
HISTORY_PATH = DATA_DIR / "pillar_weights_history.json"

# Canonical pillars (the 4 BSC perspectives)
CANONICAL_PILLARS: List[str] = [
    "Financial",
    "Customer Focus",
    "Operational Excellence",
    "People & Learning",
]

# The Kaplan-Norton balanced default
DEFAULT_BALANCED_WEIGHTS: Dict[str, float] = {
    "Financial":              0.40,
    "Customer Focus":         0.25,
    "Operational Excellence": 0.25,
    "People & Learning":      0.10,
}

# Tolerance for sum-to-1.0 validation (handles float arithmetic)
SUM_TOLERANCE = 0.001


def _safe_load_json(path: Path, default: Any) -> Any:
    """Read JSON file, return default on any failure."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def get_pillar_weights() -> Dict[str, float]:
    """Return the canonical pillar weights.

    Reads from `kpi_library.json::pillar_weights`. If missing, returns
    `DEFAULT_BALANCED_WEIGHTS` (per Donella Meadows: balanced is the
    sustainable default).

    Returns a fresh dict — callers may modify it without affecting cache.
    """
    lib = _safe_load_json(KPI_LIBRARY_PATH, {})
    pw = lib.get("pillar_weights") if isinstance(lib, dict) else None
    if not isinstance(pw, dict):
        return dict(DEFAULT_BALANCED_WEIGHTS)
    # Normalise: ensure all 4 canonical pillars present
    result: Dict[str, float] = {}
    for pillar in CANONICAL_PILLARS:
        val = pw.get(pillar, DEFAULT_BALANCED_WEIGHTS[pillar])
        try:
            result[pillar] = float(val)
        except (TypeError, ValueError):
            result[pillar] = DEFAULT_BALANCED_WEIGHTS[pillar]
    return result


def validate_pillar_weights(weights: Dict[str, float]) -> Tuple[bool, str]:
    """Validate weights are well-formed for BSC scoring.

    Returns (ok, error_message). Rules:
      - Must contain all 4 CANONICAL_PILLARS
      - Each weight must be a non-negative number
      - Each weight must be > 0 (no killing a pillar — body needs all organs)
      - Sum must equal 1.0 within SUM_TOLERANCE
    """
    if not isinstance(weights, dict):
        return False, "weights must be a dict"
    missing = [p for p in CANONICAL_PILLARS if p not in weights]
    if missing:
        return False, f"missing pillars: {missing}"
    for pillar, val in weights.items():
        if pillar not in CANONICAL_PILLARS:
            return False, f"unknown pillar: {pillar!r}"
        try:
            v = float(val)
        except (TypeError, ValueError):
            return False, f"pillar {pillar!r} weight not numeric: {val!r}"
        if v <= 0:
            return False, (
                f"pillar {pillar!r} weight must be > 0 (got {v}); "
                f"a pillar with zero weight is a dead organ"
            )
        if v > 1:
            return False, f"pillar {pillar!r} weight > 1.0: {v}"
    total = sum(float(weights[p]) for p in CANONICAL_PILLARS)
    if abs(total - 1.0) > SUM_TOLERANCE:
        return False, f"weights sum to {total:.4f}, must be 1.0 ± {SUM_TOLERANCE}"
    return True, ""


def _append_history(old_weights: Dict[str, float],
                    new_weights: Dict[str, float],
                    actor: str,
                    reason: str) -> None:
    """Append a change record to pillar_weights_history.json.

    Per constitution §8.1 (audit traceability) — every change to a
    body-prioritization parameter must be auditable with OLD/NEW values.
    """
    history = _safe_load_json(HISTORY_PATH, [])
    if not isinstance(history, list):
        history = []
    history.append({
        "changed_at":  datetime.now(timezone.utc).isoformat(),
        "changed_by":  actor or "unknown",
        "reason":      reason or "",
        "old_weights": dict(old_weights),
        "new_weights": dict(new_weights),
    })
    # Cap history at 100 entries; keep most recent
    if len(history) > 100:
        history = history[-100:]
    HISTORY_PATH.write_text(json.dumps(history, indent=2), encoding="utf-8")


def save_pillar_weights(new_weights: Dict[str, float],
                        actor: str = "unknown",
                        reason: str = "") -> Tuple[bool, str]:
    """Validate + persist new pillar weights to the canonical location.

    On success: writes to kpi_library.json::pillar_weights AND appends
    to pillar_weights_history.json with the OLD and NEW values.

    Returns (ok, message). Does NOT modify org_config.json (the orphan).

    Args:
      new_weights: dict mapping pillar name → weight (must validate)
      actor: identifier for audit trail (e.g. username)
      reason: optional explanation captured in history
    """
    # 1. Validate
    ok, err = validate_pillar_weights(new_weights)
    if not ok:
        return False, f"validation failed: {err}"

    # 2. Read current canonical state
    lib = _safe_load_json(KPI_LIBRARY_PATH, {})
    if not isinstance(lib, dict):
        return False, "kpi_library.json corrupt — refusing to overwrite"

    old_weights = get_pillar_weights()

    # 3. Update canonical location
    lib["pillar_weights"] = {p: float(new_weights[p]) for p in CANONICAL_PILLARS}

    # 4. Persist
    try:
        KPI_LIBRARY_PATH.write_text(
            json.dumps(lib, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        return False, f"write failed: {exc}"

    # 5. Audit-log via history file
    _append_history(old_weights, new_weights, actor=actor, reason=reason)

    return True, "saved"


def get_pillar_weights_history(limit: int = 10) -> List[Dict[str, Any]]:
    """Return the most recent pillar-weight changes (newest first).

    Args:
      limit: max number of entries to return (default 10).

    Each entry has: changed_at, changed_by, reason, old_weights, new_weights.
    """
    history = _safe_load_json(HISTORY_PATH, [])
    if not isinstance(history, list):
        return []
    # Newest first
    return list(reversed(history[-limit:]))


def detect_orphan_pillar_weights() -> Optional[Dict[str, float]]:
    """Check org_config.json for orphan pillar_weights.

    Pre-v10.384, the admin Bank Identity tab wrote here — but no consumer
    reads from this location. v10.384 surfaces the orphan so operators
    can decide whether to migrate it to canonical or discard it.

    Returns the orphan weights dict if found, None otherwise.
    """
    org = _safe_load_json(ORG_CONFIG_PATH, {})
    if not isinstance(org, dict):
        return None
    pw = org.get("pillar_weights")
    if not isinstance(pw, dict):
        return None
    # Return only if at least one canonical pillar present
    if not any(p in pw for p in CANONICAL_PILLARS):
        return None
    result: Dict[str, float] = {}
    for pillar in CANONICAL_PILLARS:
        val = pw.get(pillar)
        if val is None:
            continue
        try:
            result[pillar] = float(val)
        except (TypeError, ValueError):
            continue
    return result if result else None


def health_check() -> Dict[str, Any]:
    """Diagnostic snapshot of the pillar weights organ.

    Returns:
      {
        'canonical_weights':    current canonical state
        'canonical_sum':        sum (should be 1.0)
        'canonical_valid':      bool
        'is_balanced':          bool (matches DEFAULT_BALANCED_WEIGHTS within 1%)
        'orphan_detected':      org_config weights if present (else None)
        'orphan_matches_canonical': bool
        'history_entries':      count of pillar_weights_history.json entries
        'shadow_pillars_field': True if kpi_library.pillars[] has .weight
      }
    """
    canonical = get_pillar_weights()
    canonical_ok, _ = validate_pillar_weights(canonical)
    canonical_sum = sum(canonical.values())
    is_balanced = all(
        abs(canonical.get(p, 0) - DEFAULT_BALANCED_WEIGHTS[p]) <= 0.01
        for p in CANONICAL_PILLARS
    )
    orphan = detect_orphan_pillar_weights()
    orphan_match = (orphan == canonical) if orphan else None

    history = _safe_load_json(HISTORY_PATH, [])
    h_count = len(history) if isinstance(history, list) else 0

    lib = _safe_load_json(KPI_LIBRARY_PATH, {})
    shadow_pillars = False
    if isinstance(lib, dict) and isinstance(lib.get("pillars"), list):
        for p in lib["pillars"]:
            if isinstance(p, dict) and "weight" in p:
                shadow_pillars = True
                break

    return {
        "canonical_weights":        canonical,
        "canonical_sum":            round(canonical_sum, 6),
        "canonical_valid":          canonical_ok,
        "is_balanced":              is_balanced,
        "orphan_detected":          orphan,
        "orphan_matches_canonical": orphan_match,
        "history_entries":          h_count,
        "shadow_pillars_field":     shadow_pillars,
    }


def self_test() -> None:
    """v10.384 self_test."""
    tests = 0

    # Test 1: get_pillar_weights returns dict with all 4 canonical pillars
    pw = get_pillar_weights()
    assert isinstance(pw, dict)
    for p in CANONICAL_PILLARS:
        assert p in pw
    tests += 1

    # Test 2: returned weights sum to 1.0 (canonical state)
    total = sum(pw.values())
    assert abs(total - 1.0) <= SUM_TOLERANCE, f"sum {total} != 1.0"
    tests += 1

    # Test 3: validate accepts balanced default
    ok, err = validate_pillar_weights(DEFAULT_BALANCED_WEIGHTS)
    assert ok, f"balanced default rejected: {err}"
    tests += 1

    # Test 4: validate rejects sum != 1.0
    bad = {p: 0.30 for p in CANONICAL_PILLARS}  # sums to 1.20
    ok, err = validate_pillar_weights(bad)
    assert not ok
    assert "sum" in err.lower()
    tests += 1

    # Test 5: validate rejects missing pillar
    incomplete = {p: 0.25 for p in CANONICAL_PILLARS[:3]}
    ok, _ = validate_pillar_weights(incomplete)
    assert not ok
    tests += 1

    # Test 6: validate rejects zero/negative weight
    zeroed = dict(DEFAULT_BALANCED_WEIGHTS)
    zeroed["Financial"] = 0
    zeroed["Customer Focus"] = 0.65
    ok, err = validate_pillar_weights(zeroed)
    assert not ok
    assert "> 0" in err or "dead organ" in err
    tests += 1

    # Test 7: validate rejects unknown pillar
    bad_pillar = dict(DEFAULT_BALANCED_WEIGHTS)
    bad_pillar["UnknownPillar"] = 0.0
    ok, _ = validate_pillar_weights(bad_pillar)
    # Will fail either because sum or unknown
    assert not ok
    tests += 1

    # Test 8: health_check returns expected shape
    hc = health_check()
    for required in ("canonical_weights", "canonical_sum", "canonical_valid",
                     "is_balanced", "orphan_detected",
                     "orphan_matches_canonical", "history_entries",
                     "shadow_pillars_field"):
        assert required in hc, f"health_check missing {required}"
    tests += 1

    # Test 9: orphan detection (org_config.json may or may not have pillar_weights —
    # both outcomes are acceptable; just confirm function runs)
    orphan = detect_orphan_pillar_weights()
    assert orphan is None or isinstance(orphan, dict)
    tests += 1

    # Test 10: history retrieval works (even when empty)
    hist = get_pillar_weights_history()
    assert isinstance(hist, list)
    tests += 1

    print(f"✓ pillar_weights_canonical self_test passed ({tests} tests)")
    print(f"  Canonical weights: {pw}")
    print(f"  Sum: {sum(pw.values()):.4f}")
    print(f"  is_balanced: {hc['is_balanced']}")
    print(f"  orphan_detected: {hc['orphan_detected']}")
    print(f"  shadow_pillars_field: {hc['shadow_pillars_field']}")
    print(f"  history_entries: {hc['history_entries']}")


if __name__ == "__main__":
    import sys as _sys
    _repo = Path(__file__).resolve().parent.parent
    if str(_repo) not in _sys.path:
        _sys.path.insert(0, str(_repo))
    self_test()
