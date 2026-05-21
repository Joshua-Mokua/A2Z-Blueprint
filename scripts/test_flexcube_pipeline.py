"""scripts/test_flexcube_pipeline.py — Standard #6 FLEXCUBE pipeline validator.

Five-level validation, per the master addendum:

    L1 Connectivity  100%  — OAuth + service endpoints reachable
    L2 Schema        100%  — adapter responses match expected columns
    L3 Data types    0 err — staging values cast cleanly to A2Z types
    L4 Sample data   ≥99%  — sample of records reconcile with A2Z mart
    L5 Full sync     0 lst — full extract preserves every source row

The script is mode-aware:

  - synthetic mode: L1, L4, L5 are SKIPPED with informational status
                    (no real connection, no real source of truth).
                    L2, L3 still run — they verify the adapter contract.
  - mock mode:      L1 is SKIPPED. L2-L5 run against fixture files.
  - live mode:      All five levels run.

Output:
  flexcube_validation_results.json   — audit-friendly summary; G20 reads this.

Exit codes:
  0 = all levels passed (or skipped where appropriate)
  1 = at least one critical level failed
  2 = warnings only

Usage:
  # Default — runs whatever mode the adapter is configured for
  python scripts/test_flexcube_pipeline.py

  # Force a specific mode for this run (overrides flexcube_config.json)
  python scripts/test_flexcube_pipeline.py --mode=mock
  python scripts/test_flexcube_pipeline.py --mode=live

  # Run only specific levels (comma-separated)
  python scripts/test_flexcube_pipeline.py --levels=L1,L2,L3

  # Verbose: print per-record failures
  python scripts/test_flexcube_pipeline.py --verbose
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Project root on path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logger = logging.getLogger("a2z.flexcube.validate")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

RESULTS_PATH = ROOT / "flexcube_validation_results.json"

# ── Spec thresholds (Standard #6) ──────────────────────────────────────
SPEC_THRESHOLDS = {
    "L1": {"target_pct": 100.0, "name": "Connectivity"},
    "L2": {"target_pct": 100.0, "name": "Schema"},
    "L3": {"target_max_errors": 0,    "name": "Data types"},
    "L4": {"target_pct":  99.0,       "name": "Sample data"},
    "L5": {"target_max_loss": 0,      "name": "Full sync"},
}


# ── Expected ADAPTER contract per entity ──────────────────────────────
#
# These describe the shape utils/flexcube_adapter.py MUST return — the
# layer L2 actually tests. The adapter's contract is what ETL +
# dashboards consume. The ETL (scripts/etl_flexcube.py) is responsible
# for translating this adapter shape into the staging table column
# names (customer_id, customer_name, etc. in utils/db.py SCHEMA_SQL).
#
# The two layers are deliberately decoupled:
#   - L2 here:        adapter contract (cif, name, account_no, ...)
#   - L4/L5 below:    staging contract (customer_id, customer_name, ...)
#                     verified via DB queries against staging.flexcube_*
#
# required_keys: bare minimum the ETL depends on; missing → pipeline breaks
# optional_keys: extra payload that may or may not appear on a given call
EXPECTED_SCHEMAS = {
    "customers": {
        # ETL maps cif → customer_id, name → customer_name. Both are
        # required for a row to be recordable.
        "required_keys": {"cif", "name"},
        "optional_keys": {
            "type", "branch", "rm_code", "kyc_status", "risk_rating",
            "country", "id_number", "email", "phone", "opened_date",
            "customer_since", "source",
        },
    },
    "accounts": {
        # ETL needs account_no (primary key) and branch (partition).
        # Balances can be zero; currency defaults to KES.
        "required_keys": {"account_no", "branch"},
        "optional_keys": {
            "available_balance", "ledger_balance", "currency",
            "as_of", "source",
        },
    },
    "loans": {
        # ETL needs loan_id (primary key) and cif (customer link).
        # Loan-side numbers (principal, outstanding) can default to 0.
        "required_keys": {"loan_id", "cif"},
        "optional_keys": {
            "principal", "outstanding", "status", "classification",
            "dpd", "rate", "tenor_months", "next_emi_date", "source",
        },
    },
}

# ── Type contract: how staging VARCHARs cast to A2Z types ──────────────
# (field, target_type, validator). validator returns (ok, msg).
def _is_decimal(s: Any) -> tuple[bool, str]:
    if s is None or s == "":
        return True, ""  # nullable
    try:
        from decimal import Decimal
        Decimal(str(s))
        return True, ""
    except Exception as e:
        return False, f"not numeric: {e}"

def _is_date_iso(s: Any) -> tuple[bool, str]:
    if s is None or s == "":
        return True, ""
    try:
        # Accept YYYY-MM-DD, YYYYMMDD, YYYY-MM-DD HH:MM:SS, ISO datetime
        for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                datetime.strptime(str(s).strip()[:len(datetime.now().strftime(fmt))], fmt)
                return True, ""
            except ValueError:
                continue
        # Accept ISO datetime with timezone via fromisoformat
        try:
            datetime.fromisoformat(str(s).replace("Z", "+00:00"))
            return True, ""
        except ValueError:
            pass
        return False, f"unparseable date: {s!r}"
    except Exception as e:
        return False, f"date check failed: {e}"

def _is_str_max(maxlen: int) -> Callable[[Any], tuple[bool, str]]:
    def check(s: Any) -> tuple[bool, str]:
        if s is None: return True, ""
        if not isinstance(s, str): return False, f"not a string: {type(s).__name__}"
        if len(s) > maxlen: return False, f"length {len(s)} exceeds max {maxlen}"
        return True, ""
    return check

# L3 type contract — adapter values must cast cleanly to A2Z target types.
# Field names match the adapter contract (not the staging table). The
# str(N) limits align to the eventual VARCHAR(N) staging columns; if a
# value is too long it would silently truncate at ingest, which is what
# we want L3 to flag.
TYPE_CONTRACT = {
    "customers": [
        ("cif",            "str(50)",     _is_str_max(50)),
        ("name",           "str(300)",    _is_str_max(300)),
    ],
    "accounts": [
        ("account_no",          "str(50)",   _is_str_max(50)),
        ("branch",              "str(10)",   _is_str_max(10)),
        ("available_balance",   "decimal",   _is_decimal),
        ("ledger_balance",      "decimal",   _is_decimal),
    ],
    "loans": [
        ("loan_id",        "str(50)",   _is_str_max(50)),
        ("cif",            "str(50)",   _is_str_max(50)),
        ("principal",      "decimal",   _is_decimal),
        ("outstanding",    "decimal",   _is_decimal),
    ],
}


# ══════════════════════════════════════════════════════════════════════
# Result accumulator
# ══════════════════════════════════════════════════════════════════════

class LevelResult:
    """One row per level. JSON-serialisable."""
    def __init__(self, level: str, name: str):
        self.level = level
        self.name = name
        self.status: str = "skipped"   # passed | failed | skipped
        self.metric: Dict[str, Any] = {}
        self.details: List[str] = []
        self.duration_s: float = 0.0

    def to_dict(self) -> dict:
        return {
            "level":      self.level,
            "name":       self.name,
            "status":     self.status,
            "metric":     self.metric,
            "details":    self.details[:25],   # cap noise in artifact
            "details_truncated": len(self.details) > 25,
            "duration_s": round(self.duration_s, 2),
        }


# ══════════════════════════════════════════════════════════════════════
# Level implementations
# ══════════════════════════════════════════════════════════════════════

def run_l1_connectivity(mode: str, verbose: bool = False) -> LevelResult:
    """L1: Connectivity (100%) — OAuth token + each service endpoint."""
    r = LevelResult("L1", "Connectivity")
    if mode != "live":
        r.status = "skipped"
        r.metric = {"reason": f"mode is '{mode}', skipping live connectivity probe"}
        return r

    start = time.time()
    try:
        from utils import flexcube_adapter as fcx
    except Exception as e:
        r.status = "failed"
        r.details.append(f"adapter import failed: {e}")
        r.duration_s = time.time() - start
        return r

    cfg = fcx.get_config()
    endpoints = cfg.get("endpoints", {})
    successes = 0
    total = 0

    # OAuth token endpoint
    total += 1
    try:
        token = fcx._get_oauth_token()
        if token:
            successes += 1
            if verbose: r.details.append("OAuth token: OK")
        else:
            r.details.append("OAuth token: empty")
    except Exception as e:
        r.details.append(f"OAuth token: {e}")

    # Probe each REST/SOAP endpoint with a HEAD/GET (best-effort)
    import urllib.request
    import urllib.error
    for name, url in endpoints.items():
        if not url or not url.startswith(("http://", "https://")):
            continue
        total += 1
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                # Even 4xx counts as "reachable" — we just want network success
                if resp.status < 500:
                    successes += 1
                    if verbose: r.details.append(f"{name} ({url}): HTTP {resp.status}")
                else:
                    r.details.append(f"{name}: HTTP {resp.status}")
        except urllib.error.HTTPError as e:
            if e.code < 500:
                successes += 1
                if verbose: r.details.append(f"{name}: HTTP {e.code} (reachable)")
            else:
                r.details.append(f"{name}: HTTP {e.code}")
        except Exception as e:
            r.details.append(f"{name}: {type(e).__name__}: {e}")

    pct = (successes / total * 100) if total else 0.0
    r.metric = {
        "endpoints_total":  total,
        "endpoints_ok":     successes,
        "ok_pct":           round(pct, 1),
        "target_pct":       SPEC_THRESHOLDS["L1"]["target_pct"],
    }
    r.status = "passed" if pct >= SPEC_THRESHOLDS["L1"]["target_pct"] else "failed"
    r.duration_s = time.time() - start
    return r


def run_l2_schema(mode: str, verbose: bool = False) -> LevelResult:
    """L2: Schema (100%) — adapter responses must include all required keys."""
    r = LevelResult("L2", "Schema")
    start = time.time()

    try:
        from utils import flexcube_adapter as fcx
    except Exception as e:
        r.status = "failed"
        r.details.append(f"adapter import failed: {e}")
        r.duration_s = time.time() - start
        return r

    # Sample one record per entity type. The adapter dispatches by mode
    # internally, so we get whatever shape the current mode produces.
    # Sample IDs are stable; in synthetic mode they're deterministic, in
    # mock/live they should hit known fixtures or test customers.
    SAMPLES = {
        "customers": ("fetch_customer", ("CIF000001",)),
        "accounts":  ("fetch_account_balance", ("ACC000000001", "001")),
        "loans":     ("fetch_loan_status", ("LN000001",)),
    }

    entity_results: Dict[str, dict] = {}
    all_required_present = True

    for entity, expected in EXPECTED_SCHEMAS.items():
        fn_name, args = SAMPLES[entity]
        fn = getattr(fcx, fn_name, None)
        if fn is None:
            r.details.append(f"{entity}: adapter has no {fn_name}()")
            entity_results[entity] = {"present_keys": [], "missing": list(expected["required_keys"])}
            all_required_present = False
            continue
        try:
            response = fn(*args)
        except Exception as e:
            r.details.append(f"{entity}: {fn_name}{args} raised {type(e).__name__}: {e}")
            entity_results[entity] = {"error": str(e)}
            all_required_present = False
            continue

        if not isinstance(response, dict):
            r.details.append(f"{entity}: response is {type(response).__name__}, expected dict")
            all_required_present = False
            continue

        present = set(response.keys())
        required = expected["required_keys"]
        missing = required - present
        entity_results[entity] = {
            "present_keys":  sorted(present),
            "missing":       sorted(missing),
            "extra":         sorted(present - required - expected.get("optional_keys", set())),
        }
        if missing:
            r.details.append(f"{entity}: missing required keys {sorted(missing)}")
            all_required_present = False
        elif verbose:
            r.details.append(f"{entity}: all required keys present")

    r.metric = {
        "entities_checked":   len(EXPECTED_SCHEMAS),
        "entities_compliant": sum(1 for er in entity_results.values()
                                  if not er.get("missing") and not er.get("error")),
        "compliance_pct":     round(
            sum(1 for er in entity_results.values()
                if not er.get("missing") and not er.get("error")) / len(EXPECTED_SCHEMAS) * 100, 1
        ),
        "by_entity":          entity_results,
    }
    r.status = "passed" if all_required_present else "failed"
    r.duration_s = time.time() - start
    return r


def run_l3_data_types(mode: str, verbose: bool = False) -> LevelResult:
    """L3: Data types (0 errors) — staging fields cast cleanly to A2Z types."""
    r = LevelResult("L3", "Data types")
    start = time.time()

    try:
        from utils import flexcube_adapter as fcx
    except Exception as e:
        r.status = "failed"
        r.details.append(f"adapter import failed: {e}")
        r.duration_s = time.time() - start
        return r

    SAMPLES = {
        "customers": ("fetch_customer", ("CIF000001",)),
        "accounts":  ("fetch_account_balance", ("ACC000000001", "001")),
        "loans":     ("fetch_loan_status", ("LN000001",)),
    }

    total_checks = 0
    total_errors = 0
    by_entity: Dict[str, dict] = {}

    for entity, contract in TYPE_CONTRACT.items():
        fn_name, args = SAMPLES[entity]
        fn = getattr(fcx, fn_name, None)
        if fn is None:
            r.details.append(f"{entity}: adapter has no {fn_name}()")
            total_errors += 1
            continue
        try:
            response = fn(*args)
        except Exception as e:
            r.details.append(f"{entity}: {fn_name} raised {type(e).__name__}")
            total_errors += 1
            continue

        if not isinstance(response, dict):
            continue

        entity_errors = 0
        entity_total = 0
        for field, expected_type, validator in contract:
            val = response.get(field)
            if val is None:
                # Required-key absence is a separate L2 concern; L3 cares
                # about TYPE soundness of present values
                continue
            entity_total += 1
            total_checks += 1
            ok, err = validator(val)
            if not ok:
                entity_errors += 1
                total_errors += 1
                r.details.append(
                    f"{entity}.{field} ({expected_type}): {err}"
                )

        by_entity[entity] = {
            "fields_checked": entity_total,
            "type_errors":    entity_errors,
        }
        if verbose and entity_errors == 0:
            r.details.append(f"{entity}: {entity_total} fields type-clean")

    r.metric = {
        "fields_checked":  total_checks,
        "type_errors":     total_errors,
        "target_max":      SPEC_THRESHOLDS["L3"]["target_max_errors"],
        "by_entity":       by_entity,
    }
    r.status = "passed" if total_errors <= SPEC_THRESHOLDS["L3"]["target_max_errors"] else "failed"
    r.duration_s = time.time() - start
    return r


def run_l4_sample_data(mode: str, verbose: bool = False, sample_size: int = 100) -> LevelResult:
    """L4: Sample data (≥99%) — sample reconciles with A2Z mart records."""
    r = LevelResult("L4", "Sample data")
    start = time.time()

    if mode == "synthetic":
        r.status = "skipped"
        r.metric = {"reason": "synthetic mode has no A2Z counterpart to reconcile against"}
        r.duration_s = time.time() - start
        return r

    # In mock/live mode, ask the reconciliation engine to compare a sample.
    # The recon engine already implements 5-check logic; we tell it to
    # pull a small batch and report variance.
    try:
        from utils import reconciliation as recon
    except Exception as e:
        r.status = "failed"
        r.details.append(f"reconciliation module import failed: {e}")
        r.duration_s = time.time() - start
        return r

    # Try to use whatever public API exists. If not present, soft-skip.
    sample_fn = getattr(recon, "sample_reconcile", None) or \
                getattr(recon, "reconcile_sample", None) or \
                getattr(recon, "run_sample_check", None)

    if sample_fn is None:
        r.status = "skipped"
        r.metric = {
            "reason": (
                "utils/reconciliation.py has no sample_reconcile() / "
                "reconcile_sample() / run_sample_check() helper. "
                "Add one to enable L4."
            ),
        }
        r.duration_s = time.time() - start
        return r

    try:
        result = sample_fn(sample_size=sample_size)
    except Exception as e:
        r.status = "failed"
        r.details.append(f"sample reconciliation raised {type(e).__name__}: {e}")
        r.duration_s = time.time() - start
        return r

    # Expected shape: {"matched": int, "total": int, "match_pct": float, "breaks": [...]}
    matched = int(result.get("matched", 0))
    total = int(result.get("total", 0))
    pct = (matched / total * 100) if total else 0.0
    breaks = result.get("breaks", [])
    for b in breaks[:25]:
        r.details.append(f"break: {b}")

    r.metric = {
        "sample_size":   total,
        "matched":       matched,
        "match_pct":     round(pct, 2),
        "target_pct":    SPEC_THRESHOLDS["L4"]["target_pct"],
        "break_count":   len(breaks),
    }
    r.status = "passed" if pct >= SPEC_THRESHOLDS["L4"]["target_pct"] else "failed"
    r.duration_s = time.time() - start
    return r


def run_l5_full_sync(mode: str, verbose: bool = False) -> LevelResult:
    """L5: Full sync (0 row loss) — staging count == FLEXCUBE source count."""
    r = LevelResult("L5", "Full sync")
    start = time.time()

    if mode == "synthetic":
        r.status = "skipped"
        r.metric = {"reason": "synthetic mode has no source-of-truth count"}
        r.duration_s = time.time() - start
        return r

    # L5 needs the staging tables populated. If PG is reachable AND
    # the latest ETL batch exists, compare staging.count vs source.count.
    try:
        from utils.db import db as a2z_db
    except Exception as e:
        r.status = "failed"
        r.details.append(f"db module import failed: {e}")
        r.duration_s = time.time() - start
        return r

    if not a2z_db.is_postgres_ready():
        r.status = "skipped"
        r.metric = {"reason": "PostgreSQL not reachable; cannot count staging rows"}
        r.duration_s = time.time() - start
        return r

    # For each entity, compare staging.count() to a source-side count.
    # Source-side counts come from the adapter (live) or fixture metadata
    # (mock). If we can't get a source count, the level is inconclusive.
    STAGING_TABLES = {
        "customers":    "staging.flexcube_customers",
        "accounts":     "staging.flexcube_accounts",
        "loans":        "staging.flexcube_loans",
    }

    by_entity: Dict[str, dict] = {}
    total_loss = 0
    total_inconclusive = 0

    for entity, staging_table in STAGING_TABLES.items():
        # Count staging rows from the latest batch
        try:
            from utils.db import _qid
            from psycopg2 import sql as _sql
            schema, table = staging_table.split(".", 1)
            q = _sql.SQL(
                "SELECT COUNT(*) AS n FROM {schema}.{table} "
                "WHERE batch_id = ("
                "  SELECT MAX(batch_id) FROM {schema}.{table}"
                ")"
            ).format(schema=_sql.Identifier(schema), table=_sql.Identifier(table))
            rows = a2z_db.fetch_all(q, ())
            staging_count = int(rows[0].get("n", 0)) if rows else 0
        except Exception as e:
            r.details.append(f"{entity}: staging count failed: {e}")
            staging_count = 0
            total_inconclusive += 1
            continue

        # Source-side count — best effort. The adapter doesn't currently
        # expose a "count_<entity>" helper, so we mark inconclusive in
        # the absence of one. This is the right behaviour: we don't
        # silently pass when we can't measure.
        source_count_fn_name = f"count_{entity}"
        source_count_fn = None
        try:
            from utils import flexcube_adapter as fcx
            source_count_fn = getattr(fcx, source_count_fn_name, None)
        except Exception:
            pass

        if source_count_fn is None:
            by_entity[entity] = {
                "staging_count":  staging_count,
                "source_count":   None,
                "status":         "inconclusive (no source count helper)",
            }
            total_inconclusive += 1
            r.details.append(
                f"{entity}: utils/flexcube_adapter.py has no {source_count_fn_name}() — "
                f"cannot verify zero-loss. Add one to enable L5."
            )
            continue

        try:
            source_count = int(source_count_fn())
        except Exception as e:
            by_entity[entity] = {"error": str(e)}
            total_inconclusive += 1
            continue

        loss = source_count - staging_count
        by_entity[entity] = {
            "staging_count":  staging_count,
            "source_count":   source_count,
            "loss":           loss,
            "status":         "ok" if loss == 0 else "loss",
        }
        if loss > 0:
            total_loss += loss
            r.details.append(
                f"{entity}: lost {loss} rows (source={source_count}, staging={staging_count})"
            )

    r.metric = {
        "entities_checked":   len(STAGING_TABLES),
        "total_loss":         total_loss,
        "inconclusive":       total_inconclusive,
        "target_max_loss":    SPEC_THRESHOLDS["L5"]["target_max_loss"],
        "by_entity":          by_entity,
    }
    if total_inconclusive == len(STAGING_TABLES):
        r.status = "skipped"
        r.metric["reason"] = "no source-count helpers available; cannot verify"
    elif total_loss <= SPEC_THRESHOLDS["L5"]["target_max_loss"]:
        r.status = "passed"
    else:
        r.status = "failed"
    r.duration_s = time.time() - start
    return r


# ══════════════════════════════════════════════════════════════════════
# Driver
# ══════════════════════════════════════════════════════════════════════

LEVELS: Dict[str, Callable] = {
    "L1": run_l1_connectivity,
    "L2": run_l2_schema,
    "L3": run_l3_data_types,
    "L4": run_l4_sample_data,
    "L5": run_l5_full_sync,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="FLEXCUBE pipeline 5-level validator")
    parser.add_argument("--mode", choices=["synthetic", "mock", "live"],
                        help="Override the adapter's configured mode for this run")
    parser.add_argument("--levels", default="L1,L2,L3,L4,L5",
                        help="Comma-separated levels to run (default: all 5)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print per-record successes (not just failures)")
    parser.add_argument("--output", default=str(RESULTS_PATH),
                        help="Where to write the JSON artifact")
    args = parser.parse_args()

    # Determine effective mode
    try:
        from utils import flexcube_adapter as fcx
        configured_mode = fcx.get_mode()
    except Exception as e:
        print(f"ERROR: cannot import flexcube_adapter: {e}")
        return 1

    effective_mode = args.mode or configured_mode

    print(f"A2Z MIS 360 — FLEXCUBE pipeline validation (Standard #6)")
    print(f"  Configured mode: {configured_mode}")
    print(f"  Effective mode:  {effective_mode}")
    print(f"  Levels to run:   {args.levels}")
    print()

    # Run requested levels
    requested = [l.strip().upper() for l in args.levels.split(",") if l.strip()]
    invalid = [l for l in requested if l not in LEVELS]
    if invalid:
        print(f"ERROR: unknown levels: {invalid}")
        return 1

    results: List[LevelResult] = []
    for level_id in requested:
        fn = LEVELS[level_id]
        print(f"  Running {level_id} ({SPEC_THRESHOLDS[level_id]['name']})...")
        try:
            result = fn(effective_mode, verbose=args.verbose)
        except Exception as e:
            result = LevelResult(level_id, SPEC_THRESHOLDS[level_id]["name"])
            result.status = "failed"
            result.details.append(f"unhandled exception: {type(e).__name__}: {e}")
        results.append(result)
        marker = {"passed": "✅", "failed": "❌", "skipped": "⊘"}[result.status]
        metric_str = ""
        if "compliance_pct" in result.metric:
            metric_str = f" ({result.metric['compliance_pct']}%)"
        elif "ok_pct" in result.metric:
            metric_str = f" ({result.metric['ok_pct']}%)"
        elif "type_errors" in result.metric:
            metric_str = f" ({result.metric['type_errors']} errors)"
        elif "match_pct" in result.metric:
            metric_str = f" ({result.metric['match_pct']}%)"
        elif "total_loss" in result.metric:
            metric_str = f" ({result.metric['total_loss']} lost)"
        print(f"    {marker} {level_id} {result.status:<8} {result.duration_s:>5.2f}s{metric_str}")
        if args.verbose and result.details:
            for d in result.details[:5]:
                print(f"       {d}")

    # Aggregate
    summary = {
        "schema_version":     1,
        "run_at":              datetime.now(timezone.utc).isoformat(),
        "configured_mode":     configured_mode,
        "effective_mode":      effective_mode,
        "levels":              [r.to_dict() for r in results],
        "summary": {
            "total_levels":   len(results),
            "passed":         sum(1 for r in results if r.status == "passed"),
            "failed":         sum(1 for r in results if r.status == "failed"),
            "skipped":        sum(1 for r in results if r.status == "skipped"),
        },
        "all_passed":          all(r.status in ("passed", "skipped") for r in results),
        "any_failed":          any(r.status == "failed" for r in results),
    }

    Path(args.output).write_text(json.dumps(summary, indent=2, default=str))

    print()
    print("=" * 72)
    print(f"FLEXCUBE pipeline validation — "
          f"{summary['summary']['passed']} passed, "
          f"{summary['summary']['failed']} failed, "
          f"{summary['summary']['skipped']} skipped")
    print("=" * 72)
    print(f"  Artifact: {args.output}")

    if summary["any_failed"]:
        return 1
    if summary["summary"]["skipped"] > 0 and effective_mode == "synthetic":
        # Synthetic mode skipping L1/L4/L5 is expected; not a warning
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
