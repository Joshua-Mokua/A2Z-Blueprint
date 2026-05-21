"""utils.cost_allocation — Dynamic Cost Allocation Engine + Driver Library
(Standards #25 + #26, v5.49). Volume Three.

Per the master spec, two related deliverables:

STANDARD #25: Dynamic Cost Allocation Engine
---------------------------------------------
SQL schema for the cost allocation rules table:

    CREATE TABLE finance.cost_allocation_rules (
        cost_item VARCHAR(200), allocation_method VARCHAR(50),
        driver_1 VARCHAR(50), driver_1_weight DECIMAL(5,2)
    );

STANDARD #26: Allocation Driver Library
----------------------------------------
DRIVERS catalog mapping driver names to SQL fragments:

    DRIVERS = {
        "staff_count_by_segment": "COUNT(staff_code) WHERE segment = target",
        "loan_portfolio_value":   "SUM(outstanding_balance) WHERE customer_segment = target",
        "deposit_balance":        "SUM(balance) WHERE customer_segment = target",
    }

WHY THESE TWO BELONG TOGETHER
------------------------------
The schema (#25) defines the rule structure: each cost item has an
allocation method and one or more drivers with weights. The driver
library (#26) is the catalog of valid drivers a rule can reference.
A cost_allocation_rules row pointing at a driver_1 name that's NOT
in the DRIVERS catalog is a misconfiguration. v5.49 ships both
together so consistency between rule data and driver catalog can
be enforced at validation time.

THE DRIVERS CATALOG — EXTENDED WITH HONEST METADATA
----------------------------------------------------
The spec gives only the SQL fragment. v5.49 extends each driver
entry with:

  sql:           the spec's SQL fragment (verbatim)
  unit:          what the driver measures (e.g. "count", "KES")
  staleness_max_days: data freshness expectation
  description:   human-readable purpose
  required_fields: which columns must exist for the SQL to work

This metadata is needed for production use — a cost allocation rule
that points at a driver computed from stale data should be flagged.

VALIDATION
----------
validate_rule(rule) checks a cost_allocation_rules row:
  - cost_item is non-empty
  - allocation_method is one of ALLOCATION_METHODS
  - driver_1 is in DRIVERS
  - driver_1_weight is in (0, 1]
  - if driver_2 supplied, same checks; weights sum to 1.0
  - returns dict with valid:bool, errors:list

build_rules_table_ddl() returns the spec-exact CREATE TABLE statement
plus reasonable indexes for production use.

WHAT'S NOT HERE
---------------
- The actual cost allocation COMPUTATION is the rules engine that
  applies these rules to GL costs. That belongs in a separate runtime
  module that READS this catalog. v5.49 ships the catalog + validation
  only — the compute engine is downstream work.
- This is a configuration layer; no #11 honesty inheritance applies
  (it doesn't aggregate financial outputs). When the compute engine
  ships, it will need #11 inheritance like #23/#24 do.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────
# Standard #26 — DRIVERS catalog
# ─────────────────────────────────────────────────────────────────────

# The spec provides 3 drivers; v5.49 ships those 3 with verbatim SQL plus
# enriched metadata. Production deployments add new drivers by extending
# this dict (or via DB-backed catalog).
DRIVERS: Dict[str, Dict[str, Any]] = {
    "staff_count_by_segment": {
        "sql":                 "COUNT(staff_code) WHERE segment = target",
        "unit":                "count",
        "staleness_max_days":  7,
        "description":         "Number of staff serving the target segment",
        "required_fields":     ["staff_code", "segment"],
    },
    "loan_portfolio_value": {
        "sql":                 "SUM(outstanding_balance) WHERE customer_segment = target",
        "unit":                "KES",
        "staleness_max_days":  1,
        "description":         "Total outstanding loan principal in segment",
        "required_fields":     ["outstanding_balance", "customer_segment"],
    },
    "deposit_balance": {
        "sql":                 "SUM(balance) WHERE customer_segment = target",
        "unit":                "KES",
        "staleness_max_days":  1,
        "description":         "Total deposit balance in segment",
        "required_fields":     ["balance", "customer_segment"],
    },
}


# ─────────────────────────────────────────────────────────────────────
# Standard #25 — Cost allocation rule schema
# ─────────────────────────────────────────────────────────────────────

# Allocation methods that a rule can declare. Direct = identifiable to
# segment without a driver. Driver-based = use one or more drivers
# with weights. ABC (activity-based costing) is a special multi-driver
# combination.
ALLOCATION_METHODS: Tuple[str, ...] = (
    "direct",
    "driver_based",
    "activity_based_costing",
    "equal_split",
)

# Maximum number of drivers a rule can reference (rule schema fields
# driver_1, driver_2, ..., driver_N). v5.49 ships 2 driver slots
# matching the spec's pattern of driver_1 + (implicit) driver_2.
MAX_DRIVERS_PER_RULE = 2


def build_rules_table_ddl() -> str:
    """Return the CREATE TABLE statement for finance.cost_allocation_rules.

    Spec-exact for the columns the spec quotes; adds reasonable
    production columns (id, audit) and indexes.
    """
    return """
CREATE TABLE IF NOT EXISTS finance.cost_allocation_rules (
    id              SERIAL PRIMARY KEY,
    cost_item       VARCHAR(200) NOT NULL,
    allocation_method VARCHAR(50) NOT NULL,
    driver_1        VARCHAR(50),
    driver_1_weight DECIMAL(5,2),
    driver_2        VARCHAR(50),
    driver_2_weight DECIMAL(5,2),
    active          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      VARCHAR(50),
    notes           TEXT
);

CREATE INDEX IF NOT EXISTS idx_cost_allocation_rules_cost_item
    ON finance.cost_allocation_rules (cost_item)
    WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS idx_cost_allocation_rules_method
    ON finance.cost_allocation_rules (allocation_method)
    WHERE active = TRUE;
""".strip()


def validate_rule(rule: dict) -> Dict[str, Any]:
    """Validate a single cost_allocation_rules row.

    Returns:
        {
          "valid":  bool,
          "errors": list[str],
          "rule":   dict (the input echoed back),
        }

    Checks:
      - cost_item non-empty
      - allocation_method is in ALLOCATION_METHODS
      - For driver-based methods: driver_1 references DRIVERS
      - Weights are 0 < w ≤ 1 and (if multiple) sum to 1.0 ± 0.01
    """
    errors: List[str] = []
    if not isinstance(rule, dict):
        return {"valid": False, "errors": ["rule must be a dict"], "rule": rule}

    cost_item = rule.get("cost_item", "")
    if not cost_item or not isinstance(cost_item, str):
        errors.append("cost_item must be a non-empty string")

    method = rule.get("allocation_method", "")
    if method not in ALLOCATION_METHODS:
        errors.append(
            f"allocation_method {method!r} not in {ALLOCATION_METHODS}"
        )

    # Direct allocation doesn't need drivers
    needs_drivers = method in ("driver_based", "activity_based_costing")
    if needs_drivers:
        d1 = rule.get("driver_1")
        if not d1:
            errors.append(f"method {method!r} requires driver_1")
        elif d1 not in DRIVERS:
            errors.append(
                f"driver_1 {d1!r} not in DRIVERS catalog "
                f"({list(DRIVERS.keys())})"
            )

        w1 = rule.get("driver_1_weight")
        if w1 is None:
            errors.append("driver_1_weight required for driver-based method")
        else:
            try:
                w1f = float(w1)
                if not (0 < w1f <= 1):
                    errors.append(f"driver_1_weight {w1f} must be in (0, 1]")
            except (TypeError, ValueError):
                errors.append(f"driver_1_weight {w1!r} not numeric")

        d2 = rule.get("driver_2")
        w2 = rule.get("driver_2_weight")
        if d2:
            if d2 not in DRIVERS:
                errors.append(
                    f"driver_2 {d2!r} not in DRIVERS catalog"
                )
            if w2 is None:
                errors.append("driver_2_weight required when driver_2 set")
            else:
                try:
                    w2f = float(w2)
                    if not (0 < w2f <= 1):
                        errors.append(f"driver_2_weight {w2f} must be in (0, 1]")
                except (TypeError, ValueError):
                    errors.append(f"driver_2_weight {w2!r} not numeric")

            # Weights should sum to 1.0
            if w1 is not None and w2 is not None:
                try:
                    s = float(w1) + float(w2)
                    if abs(s - 1.0) > 0.01:
                        errors.append(
                            f"driver weights sum to {s:.4f}, expected 1.00 (±0.01)"
                        )
                except (TypeError, ValueError):
                    pass    # already covered above

    return {"valid": len(errors) == 0, "errors": errors, "rule": rule}


def validate_rules(rules: List[dict]) -> Dict[str, Any]:
    """Validate a batch of cost allocation rules.

    Returns:
        {
          "total":       int,
          "valid_count": int,
          "invalid_count": int,
          "results":     list of per-rule validation results,
        }
    """
    results = [validate_rule(r) for r in rules]
    valid_count = sum(1 for r in results if r["valid"])
    return {
        "total":         len(results),
        "valid_count":   valid_count,
        "invalid_count": len(results) - valid_count,
        "results":       results,
    }


# ─────────────────────────────────────────────────────────────────────
# Driver library accessors
# ─────────────────────────────────────────────────────────────────────

def list_drivers() -> List[str]:
    return list(DRIVERS.keys())


def get_driver(name: str) -> Optional[dict]:
    return DRIVERS.get(name)


def driver_sql(name: str) -> Optional[str]:
    """Return the SQL fragment for a driver, or None if unknown."""
    d = DRIVERS.get(name)
    return d.get("sql") if d else None


def validate_driver_catalog() -> Dict[str, Any]:
    """Verify every driver in DRIVERS has the required metadata fields.

    Used to guard against incomplete catalog entries.
    """
    errors: List[str] = []
    required_keys = {"sql", "unit", "staleness_max_days", "description", "required_fields"}
    for name, entry in DRIVERS.items():
        if not isinstance(entry, dict):
            errors.append(f"driver {name!r} entry is not a dict")
            continue
        missing = required_keys - set(entry.keys())
        if missing:
            errors.append(f"driver {name!r} missing keys: {sorted(missing)}")
        sql = entry.get("sql", "")
        if not isinstance(sql, str) or not sql.strip():
            errors.append(f"driver {name!r} has empty sql")
        rf = entry.get("required_fields")
        if not isinstance(rf, list) or not rf:
            errors.append(f"driver {name!r} required_fields must be non-empty list")
    return {"valid": len(errors) == 0, "errors": errors,
            "driver_count": len(DRIVERS)}


# ─────────────────────────────────────────────────────────────────────
# DDL parser/checker — verify the spec-named columns are present
# ─────────────────────────────────────────────────────────────────────

def ddl_contains_required_columns(ddl: str) -> Dict[str, Any]:
    """Verify that the DDL contains the spec-required columns.

    Returns: {"valid": bool, "missing": list[str], "found": list[str]}
    """
    required = ["cost_item", "allocation_method", "driver_1", "driver_1_weight"]
    found = []
    missing = []
    lower = (ddl or "").lower()
    for col in required:
        if col.lower() in lower:
            found.append(col)
        else:
            missing.append(col)
    return {"valid": len(missing) == 0, "missing": missing, "found": found}


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.cost_allocation self-test")

    # ── DRIVERS catalog has spec-required keys ────────────────────────
    for k in ("staff_count_by_segment", "loan_portfolio_value", "deposit_balance"):
        assert k in DRIVERS, f"missing spec key {k!r}"
    print(f"  ✅ DRIVERS has all 3 spec-required keys")

    # ── Spec SQL fragments preserved verbatim ─────────────────────────
    assert DRIVERS["staff_count_by_segment"]["sql"] == \
        "COUNT(staff_code) WHERE segment = target"
    assert DRIVERS["loan_portfolio_value"]["sql"] == \
        "SUM(outstanding_balance) WHERE customer_segment = target"
    assert DRIVERS["deposit_balance"]["sql"] == \
        "SUM(balance) WHERE customer_segment = target"
    print(f"  ✅ all 3 SQL fragments verbatim from spec")

    # ── Catalog validates ─────────────────────────────────────────────
    v = validate_driver_catalog()
    assert v["valid"], f"catalog invalid: {v['errors']}"
    assert v["driver_count"] == 3
    print(f"  ✅ driver catalog validation: {v['driver_count']} drivers, all complete")

    # ── DDL has spec columns ──────────────────────────────────────────
    ddl = build_rules_table_ddl()
    check = ddl_contains_required_columns(ddl)
    assert check["valid"], f"missing: {check['missing']}"
    print(f"  ✅ DDL has all 4 spec columns: {check['found']}")

    # ── Rule validation: valid rule passes ────────────────────────────
    good_rule = {
        "cost_item":       "Branch IT support",
        "allocation_method": "driver_based",
        "driver_1":        "staff_count_by_segment",
        "driver_1_weight": 1.0,
    }
    r = validate_rule(good_rule)
    assert r["valid"], f"good rule failed: {r['errors']}"
    print(f"  ✅ good rule validates")

    # ── Two-driver rule with weights summing to 1.0 ───────────────────
    two_driver_rule = {
        "cost_item":       "Compliance overhead",
        "allocation_method": "activity_based_costing",
        "driver_1":        "loan_portfolio_value",
        "driver_1_weight": 0.6,
        "driver_2":        "deposit_balance",
        "driver_2_weight": 0.4,
    }
    r = validate_rule(two_driver_rule)
    assert r["valid"], f"two-driver rule failed: {r['errors']}"
    print(f"  ✅ two-driver rule validates")

    # ── Rule with unknown driver fails ────────────────────────────────
    bad = {"cost_item": "X", "allocation_method": "driver_based",
           "driver_1": "made_up_driver", "driver_1_weight": 1.0}
    r = validate_rule(bad)
    assert not r["valid"]
    assert any("not in DRIVERS catalog" in e for e in r["errors"])
    print(f"  ✅ unknown driver rejected")

    # ── Rule with weights not summing to 1 fails ──────────────────────
    bad_weights = {
        "cost_item": "X", "allocation_method": "driver_based",
        "driver_1": "deposit_balance", "driver_1_weight": 0.7,
        "driver_2": "loan_portfolio_value", "driver_2_weight": 0.5,
    }
    r = validate_rule(bad_weights)
    assert not r["valid"]
    assert any("sum to" in e for e in r["errors"])
    print(f"  ✅ weight-sum violation caught")

    # ── Direct allocation doesn't need drivers ────────────────────────
    direct = {"cost_item": "Direct salaries", "allocation_method": "direct"}
    r = validate_rule(direct)
    assert r["valid"]
    print(f"  ✅ direct allocation valid without drivers")

    # ── Empty cost_item fails ─────────────────────────────────────────
    r = validate_rule({"cost_item": "", "allocation_method": "direct"})
    assert not r["valid"]
    print(f"  ✅ empty cost_item rejected")

    # ── Invalid method rejected ───────────────────────────────────────
    r = validate_rule({"cost_item": "X", "allocation_method": "magic"})
    assert not r["valid"]
    print(f"  ✅ invalid allocation_method rejected")

    # ── Zero weight rejected ──────────────────────────────────────────
    r = validate_rule({"cost_item": "X", "allocation_method": "driver_based",
                        "driver_1": "deposit_balance", "driver_1_weight": 0.0})
    assert not r["valid"]
    print(f"  ✅ zero weight rejected")

    # ── Batch validation ──────────────────────────────────────────────
    batch = validate_rules([good_rule, two_driver_rule, bad, direct])
    assert batch["total"] == 4
    assert batch["valid_count"] == 3
    assert batch["invalid_count"] == 1
    print(f"  ✅ batch validation: {batch['valid_count']}/{batch['total']} valid")

    # ── driver_sql accessor ───────────────────────────────────────────
    assert driver_sql("deposit_balance") == \
        "SUM(balance) WHERE customer_segment = target"
    assert driver_sql("nonexistent") is None
    print(f"  ✅ driver_sql accessor works")

    print("\n  ALL TESTS PASSED")


# ════════════════════════════════════════════════════════════════════
# v10.339 — Rule CRUD + Compute Engine (Standard #25 extension)
# ════════════════════════════════════════════════════════════════════
#
# Standards #25 + #26 above ship the SCHEMA + validator + driver catalog.
# This section adds the runtime: load/save/upsert/delete rules from
# data/cost_allocation_rules.json, and apply_rules() that walks GL cost
# items, matches each to a rule, applies the rule's method+drivers, and
# produces per-segment allocations.
#
# Admin UI in pages/7_admin.py (Performance → Cost Matrix) is the
# editing surface. The compute engine is callable from sbu_pnl_rollup
# to replace the v10.338 proxy indirect-cost split.

from pathlib import Path
from decimal import Decimal
from typing import Iterable

_RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "cost_allocation_rules.json"


# ────────────────────────────────────────────────────────────────────
# CRUD
# ────────────────────────────────────────────────────────────────────

def load_rules() -> List[Dict[str, Any]]:
    """Load active+inactive rules from data/cost_allocation_rules.json."""
    from utils.db import db as _db
    blob = _db.load_json(_RULES_PATH, default={"rules": []}) or {"rules": []}
    rules = blob.get("rules", [])
    if not isinstance(rules, list):
        return []
    return [r for r in rules if isinstance(r, dict)]


def load_active_rules() -> List[Dict[str, Any]]:
    """Filter to rules with active=True (default true if field missing)."""
    return [r for r in load_rules() if r.get("active", True)]


def save_rules(rules: List[Dict[str, Any]],
               username: str = "system") -> Dict[str, Any]:
    """Atomically save the full rules list.

    Validates every rule first. Refuses to save if any rule is invalid
    (fail-closed). Returns {saved: bool, errors: list, count: int}.
    """
    from utils.db import db as _db
    batch = validate_rules(rules)
    if batch["invalid_count"] > 0:
        return {
            "saved":  False,
            "errors": batch["errors"],
            "count":  batch["total"],
        }

    blob = {
        "_schema_version": "v10.339",
        "_last_updated_by": username,
        "_last_updated_iso": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "rules": rules,
    }

    # v10.342 — schema-lock validation before write. If the schema is
    # registered (which it is for cost_allocation_rules.json), an
    # attempted write that breaks the lock is refused here, BEFORE
    # the file is touched. Fail-closed.
    try:
        from utils.schema_validator import validate_before_save
        check = validate_before_save("cost_allocation_rules.json", blob)
        if not check.get("valid", True):
            return {
                "saved":  False,
                "errors": [f"schema: {e}" for e in check.get("errors", [])[:10]],
                "count":  len(rules),
            }
    except Exception:
        pass  # validator not yet wired in old code paths — don't block

    _db.save_json(_RULES_PATH, blob)

    try:
        from utils.core_audit import audit_log
        audit_log(
            "COST_RULES_SAVED",
            username,
            f"saved {len(rules)} rules ({sum(1 for r in rules if r.get('active', True))} active)",
            "cost_allocation",
            None,
            {"count": len(rules)},
        )
    except Exception:
        pass

    return {"saved": True, "errors": [], "count": len(rules)}


def upsert_rule(rule: Dict[str, Any],
                username: str = "system") -> Dict[str, Any]:
    """Insert or update a rule by rule_id. Validates first.

    Returns {saved: bool, op: 'insert'|'update', errors: list}.
    """
    rid = rule.get("rule_id", "").strip()
    if not rid:
        return {"saved": False, "op": "noop", "errors": ["rule_id is required"]}

    check = validate_rule(rule)
    if not check["valid"]:
        return {"saved": False, "op": "noop", "errors": check["errors"]}

    rules = load_rules()
    op = "insert"
    found = False
    for i, r in enumerate(rules):
        if r.get("rule_id") == rid:
            rules[i] = rule
            op = "update"
            found = True
            break
    if not found:
        rules.append(rule)

    out = save_rules(rules, username=username)
    return {"saved": out["saved"], "op": op, "errors": out["errors"]}


def delete_rule(rule_id: str, username: str = "system") -> Dict[str, Any]:
    """Remove a rule by rule_id. Returns {deleted: bool}."""
    rules = load_rules()
    new_rules = [r for r in rules if r.get("rule_id") != rule_id]
    if len(new_rules) == len(rules):
        return {"deleted": False, "reason": "rule_id not found"}
    out = save_rules(new_rules, username=username)
    return {"deleted": out["saved"], "errors": out["errors"]}


# ────────────────────────────────────────────────────────────────────
# Compute engine
# ────────────────────────────────────────────────────────────────────

def _equal_split(amount: Decimal,
                 segment_codes: List[str]) -> Dict[str, Decimal]:
    """Divide amount equally across the supplied segments."""
    if not segment_codes:
        return {}
    n = Decimal(len(segment_codes))
    per = (amount / n).quantize(Decimal("0.01"))
    out = {s: per for s in segment_codes}
    # Reconcile rounding into the last bucket so totals reconcile
    total = sum(out.values())
    delta = amount - total
    if delta != 0 and segment_codes:
        out[segment_codes[-1]] += delta
    return out


def _driver_based(
    amount: Decimal,
    rule: Dict[str, Any],
    driver_values: Dict[str, Dict[str, Decimal]],
) -> Dict[str, Decimal]:
    """Apply driver_based method.

    driver_values: {driver_name: {segment_code: driver_value}}.
    For each driver referenced by the rule (driver_1, driver_2), compute
    per-segment share of the driver, multiply by driver_weight, sum
    across drivers, multiply by amount.
    """
    out: Dict[str, Decimal] = {}
    drivers_used: List[Tuple[str, Decimal]] = []

    for slot in (1, 2):
        dname = rule.get(f"driver_{slot}")
        if not dname:
            continue
        weight = rule.get(f"driver_{slot}_weight")
        if weight is None:
            continue
        drivers_used.append((dname, Decimal(str(weight))))

    if not drivers_used:
        return out

    # Per-segment combined weight = sum_over_drivers(weight * share_in_driver)
    per_segment_weight: Dict[str, Decimal] = {}
    for dname, dweight in drivers_used:
        seg_values = driver_values.get(dname, {})
        total = sum((v for v in seg_values.values() if v is not None),
                    Decimal("0"))
        if total <= 0:
            continue
        for seg, v in seg_values.items():
            if v is None:
                continue
            share = (Decimal(str(v)) / total) * dweight
            per_segment_weight[seg] = (
                per_segment_weight.get(seg, Decimal("0")) + share
            )

    total_w = sum(per_segment_weight.values(), Decimal("0"))
    if total_w <= 0:
        return out

    # Normalise (drivers may not sum to 1.0 exactly due to missing data)
    for seg, w in per_segment_weight.items():
        out[seg] = (amount * w / total_w).quantize(Decimal("0.01"))

    # Reconcile rounding into the largest bucket
    allocated = sum(out.values(), Decimal("0"))
    delta = amount - allocated
    if delta != 0 and out:
        top_seg = max(out, key=lambda s: out[s])
        out[top_seg] += delta

    return out


def apply_rules(
    rules: Optional[List[Dict[str, Any]]] = None,
    driver_values: Optional[Dict[str, Dict[str, Decimal]]] = None,
    segment_codes: Optional[List[str]] = None,
) -> Dict[str, Dict[str, float]]:
    """Apply all active rules and return per-segment allocations.

    Args:
        rules: rule list. Defaults to load_active_rules().
        driver_values: {driver_name: {segment: value}}. Defaults to a
            built-in lookup that reads customer + balance sheet data.
        segment_codes: list of segments for equal_split. Defaults to
            canonical 7 codes from segment_classifier.

    Returns:
        {cost_item: {segment_code: amount_kes}, ...}
        with an "_unmapped" key for direct rules (caller resolves these
        from per-customer data, NOT from the matrix).
    """
    rules = rules if rules is not None else load_active_rules()
    if segment_codes is None:
        try:
            from utils.segment_classifier import all_segment_codes
            segment_codes = all_segment_codes()
        except Exception:
            segment_codes = ["AFFLUENT", "CORE_MIDDLE", "MASS",
                              "MICRO", "SMALL", "MEDIUM", "CORPORATE"]
    if driver_values is None:
        driver_values = _default_driver_values(segment_codes)

    allocations: Dict[str, Dict[str, float]] = {}

    for rule in rules:
        cost_item = rule.get("cost_item", "")
        method = rule.get("allocation_method", "")
        # Annual amount → quarterly slice (the rollup engine works
        # quarterly). Future enhancement: per-period amounts.
        annual = Decimal(str(rule.get("annual_amount_kes_b", 0))) * Decimal("1000000000")
        quarterly = (annual / Decimal("4")).quantize(Decimal("0.01"))

        if method == "direct":
            # NOT allocated by the matrix — surfaced for the caller
            allocations.setdefault("_direct", {})[cost_item] = float(quarterly)
            continue

        if method == "equal_split":
            split = _equal_split(quarterly, segment_codes)
            allocations[cost_item] = {s: float(v) for s, v in split.items()}
            continue

        if method == "driver_based":
            split = _driver_based(quarterly, rule, driver_values)
            allocations[cost_item] = {s: float(v) for s, v in split.items()}
            continue

        if method == "activity_based_costing":
            # v10.339 placeholder — admin can configure, compute deferred
            allocations.setdefault("_unsupported", {})[cost_item] = float(quarterly)
            continue

    return allocations


def _default_driver_values(
    segment_codes: List[str],
) -> Dict[str, Dict[str, Decimal]]:
    """Compute current driver values from the customer + cascade data.

    Drivers supported:
        staff_count_by_segment  → from cascade (RM scoring counts as proxy)
        loan_portfolio_value    → from segment_balance_sheet
        deposit_balance         → from segment_balance_sheet
    """
    out: Dict[str, Dict[str, Decimal]] = {
        "staff_count_by_segment": {},
        "loan_portfolio_value":   {},
        "deposit_balance":        {},
    }

    # Loan + deposit balances from the balance-sheet engine
    try:
        from utils.segment_balance_sheet import balance_sheet_by_segment
        bs = balance_sheet_by_segment("2026-Q2")
        for seg in segment_codes:
            b = bs.get(seg, {})
            out["loan_portfolio_value"][seg] = Decimal(
                str(b.get("loan_balance", 0))
            )
            out["deposit_balance"][seg] = Decimal(
                str(b.get("deposit_balance", 0))
            )
    except Exception:
        pass

    # Staff count proxy — use customer count for now (until a real
    # staff-by-segment map exists; admin can wire this when ready).
    # v10.340 — Bypass sbu_pnl_rollup to avoid recursion (rollup now
    # calls apply_rules which calls back here). Read customer data
    # directly + count by segment.
    try:
        from utils.db import db as _db
        from pathlib import Path as _Path
        _data_dir = _Path(__file__).resolve().parent.parent / "data"
        indiv = _db.load_json(_data_dir / "customer_intelligence.json", default={}) or {}
        biz   = _db.load_json(_data_dir / "customer_intelligence_business.json", default={}) or {}
        seg_counts: Dict[str, int] = {}
        for rec in indiv.values():
            if isinstance(rec, dict):
                s = rec.get("segment_code") or "UNCLASSIFIED"
                seg_counts[s] = seg_counts.get(s, 0) + 1
        for rec in biz.values():
            if isinstance(rec, dict):
                s = rec.get("segment_code") or "UNCLASSIFIED"
                seg_counts[s] = seg_counts.get(s, 0) + 1
        for seg in segment_codes:
            out["staff_count_by_segment"][seg] = Decimal(str(seg_counts.get(seg, 0)))
    except Exception:
        pass

    return out


def reconciliation_report(
    rules: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Summarise the rule set + total quarterly allocation.

    Returns:
        {
          rule_count, active_count, total_annual_kes_b,
          total_quarterly_kes_m, by_method: {method: amount},
          coverage: {segment: amount}, direct_total_kes_m,
        }
    """
    rules = rules if rules is not None else load_active_rules()
    by_method: Dict[str, float] = {}
    total_annual = Decimal("0")
    for r in rules:
        ann = Decimal(str(r.get("annual_amount_kes_b", 0))) * Decimal("1000000000")
        m = r.get("allocation_method", "")
        by_method[m] = by_method.get(m, 0) + float(ann)
        total_annual += ann

    allocations = apply_rules(rules=rules)
    coverage: Dict[str, float] = {}
    for cost_item, dist in allocations.items():
        if cost_item.startswith("_"):
            continue
        for seg, amt in dist.items():
            coverage[seg] = coverage.get(seg, 0) + amt

    direct_total = sum(
        allocations.get("_direct", {}).values()
    )

    return {
        "rule_count":            len(rules),
        "active_count":          sum(1 for r in rules if r.get("active", True)),
        "total_annual_kes_b":    float(total_annual / Decimal("1000000000")),
        "total_quarterly_kes_m": float(total_annual / Decimal("4") / Decimal("1000000")),
        "by_method":             {k: v for k, v in by_method.items()},
        "coverage_by_segment":   coverage,
        "direct_quarterly_kes_m": float(direct_total / 1e6) if direct_total else 0,
    }
