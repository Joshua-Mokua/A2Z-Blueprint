"""utils/bsc_engine.py — Central BSC Integration Engine.

Implements the addendum's mandatory Standards #1 (Universal BSC Data
Contract) and #2 (Central BSC Integration Engine). Every module that
contributes performance data to the bank's Balanced Scorecard MUST go
through this engine. No module is allowed to write directly to
`performance.actuals` or to `bsc_actuals_<period>.json`.

THE CONTRACT (Standard #1)
--------------------------
Every contribution has this shape:

    {
        "staff_code":    str,    # numeric staff code (matches users.json)
        "kpi_id":        str,    # K001-style or semantic (e.g. DEP_GROWTH)
        "value":         float,  # the actual measured value
        "period":        str,    # "YYYY-MM" or "YYYY-Q[1-4]"
        "source_module": str,    # which module produced this — required
    }

Modules use submit() for single contributions and submit_batch() for
bulk imports. Reads use get_actual().

THE PIPELINE (Standard #2)
--------------------------
Every submission flows through five stages:

    1. validate     — null/type/range/format checks (fail-closed)
    2. standardise  — normalise period, coerce types, lowercase keys
    3. enrich       — add timestamp, actor, idempotency hash
    4. persist      — atomic upsert to performance.actuals (PG) or JSON
    5. audit        — every submission emits an audit_log entry

Idempotency: submissions are keyed by (staff_code, kpi_id, period,
source_module). Replays update the existing record (last-write-wins).
This is correct for ETL: re-running yesterday's pipeline re-states
the same numbers without duplicating them.

USAGE
-----
    from utils.bsc_engine import submit, submit_batch, get_actual

    # Single submission
    ok, msg = submit(
        staff_code    = "300001",
        kpi_id        = "DEP_GROWTH",
        value         = 12.5,
        period        = "2026-04",
        source_module = "cbs_etl",
        actor         = "etl_runner",
    )

    # Bulk submission (returns dict with ok/rejected counts)
    result = submit_batch([
        {"staff_code": "300001", "kpi_id": "DEP_GROWTH", "value": 12.5,
         "period": "2026-04", "source_module": "cbs_etl"},
        ...
    ], source_module="cbs_etl", actor="etl_runner")

    # Read
    val = get_actual(staff_code="300001", kpi_id="DEP_GROWTH", period="2026-04")

VERIFICATION
------------
scripts/audit.py G8 (bsc_contract) detects:
    PASS — modules calling submit() with all 5 contract fields
    FAIL — modules writing directly to bsc_actuals or performance.actuals

Modules that bypass this engine fail the gate, not pass-vacuous as
before v5.18.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("a2z.bsc_engine")

# ── Paths & constants ─────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent / "data"

# Period format: YYYY-MM or YYYY-Q[1-4]
_PERIOD_RX_MONTH   = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_PERIOD_RX_QUARTER = re.compile(r"^(\d{4})-Q([1-4])$")

# Required contract fields. The audit gate G8 checks every submit() call
# passes these as keyword arguments — that's what makes the gate non-vacuous.
CONTRACT_FIELDS = {"staff_code", "kpi_id", "value", "period", "source_module"}

# Reasonable bounds. Any KPI whose value falls outside these is rejected.
# Banking KPIs use a range of units (counts, ratios, KES millions/billions),
# so the range is generous — we're catching obvious errors (NaN, infinity,
# negative billions for a count) not policy violations.
MIN_VALUE = -1e15
MAX_VALUE = 1e15


# ── Lazy resources ────────────────────────────────────────────────────────
# These are loaded on first use, NOT at import. The engine module can be
# imported in environments where streamlit/users.json don't exist yet
# (e.g. unit tests or the audit script).

_kpi_index: Optional[Dict[str, dict]] = None
_users_index: Optional[Dict[str, str]] = None  # staff_code → username
_kpi_index_loaded_at: Optional[float] = None
_users_index_loaded_at: Optional[float] = None
_INDEX_TTL_SECONDS = 300  # refresh every 5 min — KPI library / users rarely change


def _load_kpi_index() -> Dict[str, dict]:
    """Build a lookup table from kpi_id → kpi dict. Accepts both K001 and
    semantic IDs. Cached for 5 min."""
    global _kpi_index, _kpi_index_loaded_at
    import time as _t
    now = _t.time()
    if _kpi_index is not None and _kpi_index_loaded_at and (now - _kpi_index_loaded_at) < _INDEX_TTL_SECONDS:
        return _kpi_index

    idx: Dict[str, dict] = {}
    try:
        from utils.db import db as _a2z_db
        data = _a2z_db.load_json(DATA_DIR / "kpi_library.json", default={}) or {}
    except Exception as e:
        logger.warning(f"_load_kpi_index: {e}")
        data = {}

    # Index every KPI catalogue entry by both id (K001) and code (semantic)
    for kpi in data.get("kpis", []) or []:
        kid = kpi.get("id")
        if kid:
            idx[str(kid)] = kpi
        code = kpi.get("code")
        if code:
            idx[str(code)] = kpi

    # Also accept semantic IDs in active_kpis even if not in catalogue
    for sem in data.get("active_kpis", []) or []:
        if str(sem) not in idx:
            idx[str(sem)] = {"id": sem, "_origin": "active_kpis"}

    _kpi_index = idx
    _kpi_index_loaded_at = now
    return idx


def _load_users_index() -> Dict[str, str]:
    """staff_code → username lookup. Cached for 5 min."""
    global _users_index, _users_index_loaded_at
    import time as _t
    now = _t.time()
    if _users_index is not None and _users_index_loaded_at and (now - _users_index_loaded_at) < _INDEX_TTL_SECONDS:
        return _users_index

    idx: Dict[str, str] = {}
    try:
        from utils.db import db as _a2z_db
        users = _a2z_db.load_json(DATA_DIR / "users.json", default={}) or {}
    except Exception as e:
        logger.warning(f"_load_users_index: {e}")
        users = {}

    for username, u in users.items():
        sc = u.get("staff_code")
        if sc:
            idx[str(sc)] = username

    _users_index = idx
    _users_index_loaded_at = now
    return idx


def _refresh_indexes() -> None:
    """Force-refresh both lookup tables. Called by tests + by admin
    action when KPI library changes."""
    global _kpi_index, _users_index, _kpi_index_loaded_at, _users_index_loaded_at
    _kpi_index = None
    _users_index = None
    _kpi_index_loaded_at = None
    _users_index_loaded_at = None


# ── Validation (Standard #2 stage 1) ──────────────────────────────────────
def _coerce_value(v: Any) -> Optional[float]:
    """Coerce to float, rejecting NaN/Inf and out-of-range values."""
    if v is None:
        return None
    if isinstance(v, bool):  # bool is a subclass of int — disallow
        return None
    try:
        if isinstance(v, Decimal):
            f = float(v)
        else:
            f = float(v)
    except (TypeError, ValueError, InvalidOperation):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    if f < MIN_VALUE or f > MAX_VALUE:
        return None
    return f


def _normalise_period(p: Any) -> Optional[str]:
    """Accept 'YYYY-MM', 'YYYY-Q[1-4]'. Return canonical form or None."""
    if not isinstance(p, str):
        return None
    p = p.strip().upper()
    if _PERIOD_RX_MONTH.match(p):
        return p  # already canonical
    if _PERIOD_RX_QUARTER.match(p):
        return p
    return None


def validate(record: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate a single submission record. Returns (ok, error_message).

    This is exposed so callers (e.g. ETL preflight) can dry-run without
    side effects.
    """
    # Required keys present
    missing = CONTRACT_FIELDS - set(record.keys())
    if missing:
        return False, f"missing required field(s): {sorted(missing)}"

    staff_code    = record.get("staff_code")
    kpi_id        = record.get("kpi_id")
    value         = record.get("value")
    period        = record.get("period")
    source_module = record.get("source_module")

    # staff_code
    if not isinstance(staff_code, str) or not staff_code.strip():
        return False, "staff_code must be a non-empty string"
    users_idx = _load_users_index()
    if staff_code not in users_idx:
        return False, f"staff_code {staff_code!r} not found in users registry"

    # kpi_id
    if not isinstance(kpi_id, str) or not kpi_id.strip():
        return False, "kpi_id must be a non-empty string"
    kpi_idx = _load_kpi_index()
    if kpi_id not in kpi_idx:
        return False, f"kpi_id {kpi_id!r} not in kpi_library"

    # value
    coerced = _coerce_value(value)
    if coerced is None:
        return False, f"value {value!r} not a finite number in range"

    # period
    if _normalise_period(period) is None:
        return False, f"period {period!r} not in 'YYYY-MM' or 'YYYY-Q[1-4]' format"

    # source_module
    if not isinstance(source_module, str) or not source_module.strip():
        return False, "source_module must be a non-empty string"

    return True, ""


# ── Enrichment (stage 3) ──────────────────────────────────────────────────
def _idempotency_hash(staff_code: str, kpi_id: str, period: str, source_module: str) -> str:
    """Stable hash for upsert keying. Same 4 inputs → same hash. Replays
    of the same submission update rather than duplicate."""
    h = hashlib.sha256()
    h.update(f"{staff_code}|{kpi_id}|{period}|{source_module}".encode("utf-8"))
    return h.hexdigest()[:16]


def _enrich(record: Dict[str, Any], actor: Optional[str], metadata: Optional[Dict]) -> Dict[str, Any]:
    """Add timestamp, actor, idempotency hash. Returns a NEW dict (does
    not mutate caller's record)."""
    period = _normalise_period(record["period"])
    enriched = {
        "staff_code":    str(record["staff_code"]).strip(),
        "kpi_id":        str(record["kpi_id"]).strip(),
        "value":         _coerce_value(record["value"]),
        "period":        period,
        "source_module": str(record["source_module"]).strip(),
        "submitted_at":  datetime.now(timezone.utc).isoformat(),
        "actor":         (actor or "system").strip() if isinstance(actor, str) else "system",
        "idem_hash":     _idempotency_hash(
            str(record["staff_code"]),
            str(record["kpi_id"]),
            period,
            str(record["source_module"]),
        ),
    }
    if metadata and isinstance(metadata, dict):
        # Filter metadata to flat scalar values to keep the JSONB tidy.
        enriched["metadata"] = {
            str(k): v for k, v in metadata.items()
            if isinstance(v, (str, int, float, bool)) or v is None
        }
    return enriched


# ── Persistence (stage 4) ─────────────────────────────────────────────────
def _file_for_period(period: str) -> Path:
    """One JSON file per period (so reading one month doesn't load the
    whole bank's history). Format: data/bsc_actuals_<period>.json."""
    safe = period.replace("/", "_")
    return DATA_DIR / f"bsc_actuals_{safe}.json"


def _persist(enriched: Dict[str, Any]) -> Tuple[bool, str]:
    """Upsert one enriched record. Returns (ok, "created"|"updated").

    Routed through a2z_db.save_json so the dual-mode PG/JSON pattern
    applies. When TABLE_USE_DB["bsc_actuals"] flips True the records
    will land in performance.actuals automatically.
    """
    period = enriched["period"]
    fpath = _file_for_period(period)
    try:
        from utils.db import db as _a2z_db
        existing = _a2z_db.load_json(fpath, default=[]) or []
    except Exception as e:
        logger.error(f"_persist: load failed for {fpath}: {e}")
        return False, f"persistence load failed: {e}"

    # Find by idempotency hash
    found_idx = None
    for i, rec in enumerate(existing):
        if rec.get("idem_hash") == enriched["idem_hash"]:
            found_idx = i
            break

    op = "updated" if found_idx is not None else "created"
    if found_idx is not None:
        existing[found_idx] = enriched
    else:
        existing.append(enriched)

    try:
        from utils.db import db as _a2z_db
        # dual_save handles atomic write + PG mirror when migrated
        _a2z_db.save_json(fpath, existing)
    except Exception as e:
        logger.error(f"_persist: save failed for {fpath}: {e}")
        return False, f"persistence save failed: {e}"

    return True, op


# ── Audit (stage 5) ───────────────────────────────────────────────────────
def _audit(action: str, actor: str, detail: str) -> None:
    """Emit an audit log entry. Failures are swallowed — audit logging
    must never block the primary write path."""
    try:
        from utils.core import audit_log
        audit_log(action, actor, detail, module="bsc_engine")
    except Exception as e:
        logger.debug(f"audit_log failed (non-fatal): {e}")


# ── Public API ────────────────────────────────────────────────────────────
def submit(
    staff_code:    str,
    kpi_id:        str,
    value:         Union[int, float, Decimal],
    period:        str,
    source_module: str,
    *,
    actor:    Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Submit one BSC contribution. Validates → enriches → persists → audits.

    Keyword arguments mirror the BSC data contract verbatim. The audit
    gate G8 detects this signature shape and counts it as compliant.

    Returns:
        (True,  "created"|"updated") on success
        (False, "<reason>")           on rejection (validation or persistence)
    """
    record = {
        "staff_code":    staff_code,
        "kpi_id":        kpi_id,
        "value":         value,
        "period":        period,
        "source_module": source_module,
    }

    # 1. validate
    ok, err = validate(record)
    if not ok:
        _audit("BSC_REJECTED", actor or source_module,
               f"{source_module} → {staff_code}/{kpi_id}/{period}: {err}")
        return False, err

    # 2-3. standardise + enrich
    enriched = _enrich(record, actor, metadata)

    # 4. persist
    ok, op = _persist(enriched)
    if not ok:
        _audit("BSC_PERSIST_FAILED", actor or source_module,
               f"{source_module} → {staff_code}/{kpi_id}/{period}: {op}")
        return False, op

    # 5. audit
    _audit(
        "BSC_SUBMIT",
        actor or source_module,
        f"{source_module}: {staff_code}/{kpi_id}/{period} = {enriched['value']} ({op})",
    )
    return True, op


def submit_batch(
    records:       List[Dict[str, Any]],
    source_module: str,
    *,
    actor: Optional[str] = None,
) -> Dict[str, Any]:
    """Bulk submission. Each record must contain the contract fields.
    The source_module argument overrides any per-record source_module
    so ETL jobs can stamp the whole batch.

    Returns:
        {
            "ok":       <int>,                 # accepted records
            "rejected": <int>,                 # rejected records
            "created":  <int>,
            "updated":  <int>,
            "errors":   [{"index": i, "error": "..."}, ...],
        }
    """
    summary = {"ok": 0, "rejected": 0, "created": 0, "updated": 0, "errors": []}
    if not isinstance(records, list):
        summary["errors"].append({"index": -1, "error": "records must be a list"})
        return summary

    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            summary["rejected"] += 1
            summary["errors"].append({"index": i, "error": "not a dict"})
            continue

        # Merge source_module — caller-level wins
        rec_with_src = {**rec, "source_module": source_module}
        try:
            ok, msg = submit(
                staff_code    = rec_with_src.get("staff_code"),
                kpi_id        = rec_with_src.get("kpi_id"),
                value         = rec_with_src.get("value"),
                period        = rec_with_src.get("period"),
                source_module = source_module,
                actor         = actor,
                metadata      = rec_with_src.get("metadata"),
            )
        except TypeError as e:
            ok, msg = False, f"submit signature error: {e}"

        if ok:
            summary["ok"] += 1
            if msg in ("created", "updated"):
                summary[msg] += 1
        else:
            summary["rejected"] += 1
            summary["errors"].append({"index": i, "error": msg})

    _audit(
        "BSC_BATCH",
        actor or source_module,
        f"{source_module} batch: ok={summary['ok']} rejected={summary['rejected']} "
        f"created={summary['created']} updated={summary['updated']}",
    )
    return summary


def get_actual(staff_code: str, kpi_id: str, period: str) -> Optional[Decimal]:
    """Read a single actual from the store. Returns None if not found.

    Reads ALL records for the period (one file) and picks the most
    recently submitted. Suitable for typical lookup; for analytics use
    get_actuals_for_period() instead.
    """
    period_n = _normalise_period(period)
    if period_n is None:
        return None

    fpath = _file_for_period(period_n)
    try:
        from utils.db import db as _a2z_db
        records = _a2z_db.load_json(fpath, default=[]) or []
    except Exception:
        return None

    matches = [r for r in records
               if r.get("staff_code") == str(staff_code).strip()
               and r.get("kpi_id") == str(kpi_id).strip()]
    if not matches:
        return None
    # Most recently submitted wins
    matches.sort(key=lambda r: r.get("submitted_at", ""), reverse=True)
    val = matches[0].get("value")
    try:
        return Decimal(str(val)) if val is not None else None
    except Exception:
        return None


def get_actuals_for_period(period: str, source_module: Optional[str] = None) -> List[Dict[str, Any]]:
    """All records for a period, optionally filtered by source_module.
    Used by 1_perform.py to assemble the BSC scorecard."""
    period_n = _normalise_period(period)
    if period_n is None:
        return []
    fpath = _file_for_period(period_n)
    try:
        from utils.db import db as _a2z_db
        records = _a2z_db.load_json(fpath, default=[]) or []
    except Exception:
        return []
    if source_module:
        records = [r for r in records if r.get("source_module") == source_module]
    return records


# ── Self-test (run directly) ─────────────────────────────────────────────
def _self_test() -> int:
    """Smoke test the engine. Returns exit code."""
    # We don't load real data — patch the indexes manually
    global _kpi_index, _users_index, _kpi_index_loaded_at, _users_index_loaded_at
    import time as _t
    _kpi_index = {"DEP_GROWTH": {"id": "DEP_GROWTH", "_origin": "test"}}
    _users_index = {"300001": "william001"}
    _kpi_index_loaded_at = _t.time()
    _users_index_loaded_at = _t.time()

    # Use a temp data dir to keep test data separate
    import tempfile
    global DATA_DIR
    real_data = DATA_DIR
    DATA_DIR = Path(tempfile.mkdtemp(prefix="bsc_test_"))

    failures = 0
    try:
        # Happy path
        ok, msg = submit("300001", "DEP_GROWTH", 12.5, "2026-04", "test", actor="tester")
        assert ok and msg == "created", f"happy path failed: {ok}/{msg}"
        print(f"  ✅ happy path: {msg}")

        # Replay = update
        ok, msg = submit("300001", "DEP_GROWTH", 13.7, "2026-04", "test", actor="tester")
        assert ok and msg == "updated", f"replay should update: {ok}/{msg}"
        print(f"  ✅ replay → update: {msg}")

        # Read back
        v = get_actual("300001", "DEP_GROWTH", "2026-04")
        assert v == Decimal("13.7"), f"expected 13.7, got {v}"
        print(f"  ✅ read back: {v}")

        # Validation rejects
        cases = [
            ({"staff_code": "999999", "kpi_id": "DEP_GROWTH", "value": 1, "period": "2026-04", "source_module": "test"}, "unknown user"),
            ({"staff_code": "300001", "kpi_id": "BOGUS",      "value": 1, "period": "2026-04", "source_module": "test"}, "unknown kpi"),
            ({"staff_code": "300001", "kpi_id": "DEP_GROWTH", "value": float("nan"), "period": "2026-04", "source_module": "test"}, "NaN value"),
            ({"staff_code": "300001", "kpi_id": "DEP_GROWTH", "value": 1, "period": "April 2026", "source_module": "test"}, "bad period"),
            ({"staff_code": "300001", "kpi_id": "DEP_GROWTH", "value": 1, "period": "2026-04", "source_module": ""},     "empty source"),
        ]
        for rec, label in cases:
            ok, err = validate(rec)
            assert not ok, f"{label} should reject"
            print(f"  ✅ rejects {label}: {err[:60]}")

        # Quarter periods
        ok, msg = submit("300001", "DEP_GROWTH", 50, "2026-Q2", "test")
        assert ok, f"quarter format should accept: {msg}"
        print(f"  ✅ quarter period accepted")

        # Batch
        batch = [
            {"staff_code": "300001", "kpi_id": "DEP_GROWTH", "value": 1.0, "period": "2026-05"},
            {"staff_code": "300001", "kpi_id": "DEP_GROWTH", "value": 2.0, "period": "2026-06"},
            {"staff_code": "BAD",    "kpi_id": "DEP_GROWTH", "value": 3.0, "period": "2026-07"},
        ]
        result = submit_batch(batch, source_module="test_etl", actor="etl_runner")
        assert result["ok"] == 2 and result["rejected"] == 1, f"unexpected batch result: {result}"
        print(f"  ✅ batch: ok={result['ok']} rejected={result['rejected']}")

        print("\n  ALL TESTS PASSED")
    except AssertionError as e:
        print(f"  ❌ FAIL: {e}")
        failures += 1
    finally:
        # Cleanup temp dir
        import shutil
        shutil.rmtree(DATA_DIR, ignore_errors=True)
        DATA_DIR = real_data

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(_self_test())
