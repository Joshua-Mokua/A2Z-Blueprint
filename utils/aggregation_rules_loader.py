"""utils/aggregation_rules_loader.py — v10.110.

Loads aggregation rule definitions from data/aggregation_rules.json
and registers them with utils.kpi_aggregation_rules.REGISTRY. This
externalizes the bank-specific rule data (which fields, which status
values, which periods) from the universal pattern engine (the 6
archetypes + compute_rule logic).

THE CONFIGURABLE/HARD-CODED BOUNDARY
────────────────────────────────────
Hard-coded (universal — same for every bank):
  - The 6 archetypal patterns: COUNT, SUM, PERCENTAGE, TAT_DAYS,
    RATIO, BOOL_FRACTION.
  - compute_rule() — the engine that applies a pattern to a row list.
  - The ownership union rule (role_kpis ∪ cascade-locked).
  - The audit gate logic (G143).

Configurable per-bank (via admin Module Config Centre):
  - Rule definitions in data/aggregation_rules.json:
      * Which KPI a rule produces actuals for (kpi_id)
      * Which operational table to read from (source_table)
      * Which fields are the staff identifier, value, period
      * Which predicate decides which rows participate
      * Which status values count as "approved", "decided", etc.
      * Whether a rule is active in this deployment
      * Whether a BOOL_FRACTION result should be inverted
  - Field overrides in data/integration_layer_config.json:
      * Per-bank schema name mapping (loan_applications.rm_code at
        Eco Bank may be loan_applications.officer_id at another bank)
  - Status vocabularies for predicate value lists.

PREDICATE DSL
─────────────
Predicates in JSON are dicts with a "type" key. Supported types:

  field_eq        Field equals a value.
                  {"type": "field_eq", "field": "status",
                   "value": "approved"}

  field_in        Field's value is in a list.
                  {"type": "field_in", "field": "status",
                   "values": ["approved", "declined"]}

  field_not_in    Field's value is NOT in a list.
                  {"type": "field_not_in", "field": "stage",
                   "values": ["Closed Won", "Closed Lost"]}

  field_truthy    bool(field) — used for "row exists" checks.
                  {"type": "field_truthy", "field": "id"}

  field_is_true   Field is exactly True (not 1, not "true" string).
                  {"type": "field_is_true", "field": "converted"}

  field_is_numeric  isinstance(field, (int, float)).
                  {"type": "field_is_numeric", "field": "tat_days"}

  field_le_field    Field <= other field, both numeric.
                  {"type": "field_le_field",
                   "field": "tat_days",
                   "compare_field": "sla_target_days"}

  field_le_value    Field <= literal numeric value (v10.119).
                  {"type": "field_le_value",
                   "field": "pct_budget_used",
                   "value": 100}

  field_ge_value    Field >= literal numeric value (v10.119).
                  {"type": "field_ge_value",
                   "field": "pct_complete",
                   "value": 100}

  all              All sub-predicates true (AND).
                  {"type": "all", "of": [pred1, pred2, ...]}

  any              Any sub-predicate true (OR).
                  {"type": "any", "of": [pred1, pred2, ...]}

STAFF FIELD EXTRACTORS
──────────────────────
Specified per-rule for nested fields:

  {"type": "nested", "path": "legal_officer.code"}

Resolves dotted paths like "legal_officer.code" or
"decision.authority.code".

INVERT FLAG
───────────
For BOOL_FRACTION rules whose bool_field captures the OPPOSITE of
what the KPI semantically rewards, set invert: true. The rule's
output becomes (100 - x). Example: K014 AML/CFT Compliance Score
(direction:higher) wired to compliance_flag (where True = problem).
With invert:true the rule emits "% clean" matching the library
direction.

INVALID JSON HANDLING
─────────────────────
If aggregation_rules.json fails to load or compile, the loader logs
a warning and registers no rules — the CBS pathway still works. This
prevents a syntax error from breaking the whole platform.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ─── Predicate compilation ─────────────────────────────────────────────

class PredicateCompileError(Exception):
    """Raised when a JSON predicate cannot be compiled to a callable."""


def compile_predicate(spec: Optional[dict]) -> Optional[Callable[[dict], bool]]:
    """Compile a JSON predicate spec to a callable. Returns None when
    spec is None — useful for optional predicate fields. Raises
    PredicateCompileError for malformed specs.

    Supported types: field_eq, field_in, field_not_in, field_truthy,
    field_is_true, field_is_numeric, field_le_field, all, any.
    """
    if spec is None:
        return None
    if not isinstance(spec, dict):
        raise PredicateCompileError(
            f"predicate must be a dict, got {type(spec).__name__}")

    t = spec.get("type")
    if not t:
        raise PredicateCompileError(
            f"predicate missing 'type' key: {spec}")

    # ─── Leaf predicates ───
    if t == "field_eq":
        f = spec["field"]
        v = spec["value"]
        return lambda r: r.get(f) == v

    if t == "field_in":
        f = spec["field"]
        vs = spec["values"]
        if not isinstance(vs, list):
            raise PredicateCompileError(
                f"field_in 'values' must be a list, got {type(vs).__name__}")
        vs_set = set(vs)
        return lambda r: r.get(f) in vs_set

    if t == "field_not_in":
        f = spec["field"]
        vs = spec["values"]
        if not isinstance(vs, list):
            raise PredicateCompileError(
                f"field_not_in 'values' must be a list, got "
                f"{type(vs).__name__}")
        vs_set = set(vs)
        return lambda r: r.get(f) not in vs_set

    # v10.111: field_in_named — references a named list from
    # data/integration_layer_config.json::status_vocabulary. Single
    # source of truth for status enums, so banks update vocabulary
    # in one place and every rule that uses that list picks up the
    # change automatically.
    if t == "field_in_named":
        f = spec["field"]
        list_name = spec["list_name"]
        # Resolve the list NOW from current vocabulary; the loader
        # bakes this in. Admins must call refresh_overrides_cache()
        # AND reload rules after editing vocabulary.
        vocab = _load_status_vocabulary()
        vs = vocab.get(list_name)
        if vs is None:
            raise PredicateCompileError(
                f"field_in_named: list_name {list_name!r} not found "
                f"in status_vocabulary; available lists: "
                f"{sorted(vocab.keys())}")
        vs_set = set(vs)
        return lambda r: r.get(f) in vs_set

    if t == "field_truthy":
        f = spec["field"]
        return lambda r: bool(r.get(f))

    if t == "field_is_true":
        f = spec["field"]
        return lambda r: r.get(f) is True

    if t == "field_is_numeric":
        f = spec["field"]
        return lambda r: isinstance(r.get(f), (int, float))

    if t == "field_le_field":
        f = spec["field"]
        cf = spec["compare_field"]
        def _le(r, _f=f, _cf=cf):
            v1 = r.get(_f)
            v2 = r.get(_cf)
            if not isinstance(v1, (int, float)):
                return False
            if not isinstance(v2, (int, float)):
                return False
            return v1 <= v2
        return _le

    # v10.119: field_le_value — compares numeric field to a literal
    # value. Closes the gap where field_le_field couldn't handle
    # comparisons against constants (e.g., pct_budget_used <= 100).
    # Avoids the sentinel-field workaround pattern that v10.119
    # initially attempted. Returns False if the field is missing or
    # non-numeric (consistent with field_le_field semantics).
    if t == "field_le_value":
        f = spec["field"]
        v = spec["value"]
        if not isinstance(v, (int, float)):
            raise ValueError(
                f"field_le_value: 'value' must be numeric, got "
                f"{type(v).__name__}: {v!r}")
        def _lev(r, _f=f, _val=v):
            x = r.get(_f)
            if not isinstance(x, (int, float)):
                return False
            return x <= _val
        return _lev

    # v10.119: field_ge_value — symmetric to field_le_value. Used
    # by K037 Milestones Completed (pct_complete >= 100) and other
    # threshold-based predicates. Returns False if the field is
    # missing or non-numeric.
    if t == "field_ge_value":
        f = spec["field"]
        v = spec["value"]
        if not isinstance(v, (int, float)):
            raise ValueError(
                f"field_ge_value: 'value' must be numeric, got "
                f"{type(v).__name__}: {v!r}")
        def _gev(r, _f=f, _val=v):
            x = r.get(_f)
            if not isinstance(x, (int, float)):
                return False
            return x >= _val
        return _gev

    # v10.115: date_le_field — compares ISO-formatted date strings
    # ("YYYY-MM-DD") via lexical compare, which is correct for that
    # format. Used when one of the fields is a date string rather
    # than numeric (e.g., actual_end_date <= planned_end_date for
    # K036 strict on-time semantics). Empty-string and None values
    # return False (i.e., row excluded — date not yet known).
    if t == "date_le_field":
        f = spec["field"]
        cf = spec["compare_field"]
        def _date_le(r, _f=f, _cf=cf):
            v1 = r.get(_f)
            v2 = r.get(_cf)
            if not isinstance(v1, str) or not v1:
                return False
            if not isinstance(v2, str) or not v2:
                return False
            return v1 <= v2
        return _date_le

    # ─── Composite predicates ───
    if t == "all":
        of = spec.get("of") or []
        compiled = [compile_predicate(p) for p in of]
        # None entries (shouldn't happen for sub-preds but defensive)
        compiled = [c for c in compiled if c is not None]
        if not compiled:
            return lambda r: True
        return lambda r: all(c(r) for c in compiled)

    if t == "any":
        of = spec.get("of") or []
        compiled = [compile_predicate(p) for p in of]
        compiled = [c for c in compiled if c is not None]
        if not compiled:
            return lambda r: False
        return lambda r: any(c(r) for c in compiled)

    raise PredicateCompileError(f"unknown predicate type: {t!r}")


# ─── Staff-field extractor compilation ──────────────────────────────────

def compile_staff_extractor(spec: Optional[dict]) -> Optional[Callable]:
    """Compile a JSON staff_field_extractor spec to a callable.

    Supported types:
      nested      — {"type": "nested", "path": "a.b.c"} dotted-path
                    traversal, handling None at any level.
      name_lookup — v10.111. {"type": "name_lookup",
                    "name_field": "assigned_to"} — read the named
                    field as a full-name string and resolve it to a
                    staff_code via utils.staff_name_resolver. Returns
                    None on miss (and increments resolution metrics).
    """
    if spec is None:
        return None
    if not isinstance(spec, dict):
        raise PredicateCompileError(
            f"staff_field_extractor must be a dict")
    t = spec.get("type")
    if t == "nested":
        path = spec.get("path")
        if not path or not isinstance(path, str):
            raise PredicateCompileError(
                "nested extractor requires string 'path'")
        parts = path.split(".")

        def _extract(row, _parts=parts):
            cur = row
            for p in _parts:
                if not isinstance(cur, dict):
                    return None
                cur = cur.get(p)
            return cur
        return _extract

    # v10.111: name_lookup — for tables (aml_alerts, incidents,
    # agent_fraud_alerts) that record assignees by full name.
    if t == "name_lookup":
        name_field = spec.get("name_field")
        if not name_field or not isinstance(name_field, str):
            raise PredicateCompileError(
                "name_lookup extractor requires string 'name_field'")
        # Lazy-import to avoid load-time cycle
        from utils.staff_name_resolver import name_to_code

        def _name_extract(row, _f=name_field):
            return name_to_code(row.get(_f))
        return _name_extract

    # v10.113: role_lookup — for tables (agent_fraud_alerts) that
    # record assignees by role title rather than person name.
    # Resolves via the 3-layer staff_role_resolver (pinned → alias
    # → direct match).
    if t == "role_lookup":
        role_field = spec.get("role_field")
        if not role_field or not isinstance(role_field, str):
            raise PredicateCompileError(
                "role_lookup extractor requires string 'role_field'")
        from utils.staff_role_resolver import role_to_code

        def _role_extract(row, _f=role_field):
            return role_to_code(row.get(_f))
        return _role_extract

    raise PredicateCompileError(
        f"unknown staff_field_extractor type: {t!r}")


# ─── Rule loading ─────────────────────────────────────────────────────

def _data_dir() -> Path:
    """Resolve the repo's data/ directory regardless of cwd."""
    here = Path(__file__).resolve().parent
    return here.parent / "data"


def load_rules_from_json(
        path: Optional[Path] = None,
        clear_registry: bool = True) -> dict:
    """Load rules from JSON, compile predicates, register them.

    Returns a status dict:
        {
          "loaded":       int,    # rules successfully registered
          "skipped":      int,    # rules with active:false
          "failed":       int,    # rules that failed to compile
          "errors":       list,   # error strings
          "path":         Path,
          "version":      str,    # JSON file's version field
        }

    If clear_registry=True (default), clears utils.kpi_aggregation_rules
    .REGISTRY before loading. Set False to add to existing rules.
    """
    if path is None:
        path = _data_dir() / "aggregation_rules.json"

    out = {"loaded": 0, "skipped": 0, "failed": 0,
           "errors": [], "path": path, "version": None}

    if not path.exists():
        out["errors"].append(f"File not found: {path}")
        return out

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        out["errors"].append(
            f"JSON load failed: {type(e).__name__}: {e}")
        return out

    out["version"] = data.get("version")
    rules_data = data.get("rules", []) or []

    # Import lazily to avoid import-time cycles
    from utils import kpi_aggregation_rules as _agg
    if clear_registry:
        _agg.REGISTRY.clear()

    for idx, spec in enumerate(rules_data):
        try:
            kid = spec.get("kpi_id", f"<idx={idx}>")
            if not spec.get("active", True):
                out["skipped"] += 1
                continue

            # Compile callable fields
            predicate = compile_predicate(spec.get("predicate"))
            num_pred = compile_predicate(spec.get("numerator_pred"))
            den_pred = compile_predicate(spec.get("denominator_pred"))
            extractor = compile_staff_extractor(
                spec.get("staff_field_extractor"))

            rule = _agg.AggregationRule(
                kpi_id=spec["kpi_id"],
                source_table=spec["source_table"],
                pattern=spec["pattern"],
                description=spec.get("description", ""),
                predicate=predicate,
                numerator_pred=num_pred,
                denominator_pred=den_pred,
                value_field=spec.get("value_field"),
                start_field=spec.get("start_field"),
                end_field=spec.get("end_field"),
                numerator_field=spec.get("numerator_field"),
                denominator_field=spec.get("denominator_field"),
                bool_field=spec.get("bool_field"),
                period_field=spec.get("period_field"),
                staff_field=spec.get("staff_field"),
                staff_field_extractor=extractor,
                decimals=spec.get("decimals", 2),
                invert=bool(spec.get("invert", False)),
            )

            _agg.register(rule)
            out["loaded"] += 1
        except Exception as e:
            out["failed"] += 1
            out["errors"].append(
                f"Rule {kid}: {type(e).__name__}: {e}")
            logger.warning(
                f"Aggregation rule {kid} failed to load: {e}")

    return out


# ─── Field-name override loading ──────────────────────────────────────

def load_field_overrides(
        path: Optional[Path] = None) -> dict[str, str]:
    """Load per-table field overrides from
    data/integration_layer_config.json. Returns a flat
    {table: field} map merged into STAFF_FIELD_BY_TABLE at runtime
    via staff_field_resolver.resolve_staff_field.

    Format:
        {
          "field_overrides": {
              "loan_applications": "officer_id",
              "pipeline":          "rm_code"
          }
        }
    """
    if path is None:
        path = _data_dir() / "integration_layer_config.json"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("field_overrides", {}) or {}
    except Exception as e:
        logger.warning(
            f"Failed to load field overrides from {path}: {e}")
        return {}


def _load_status_vocabulary(
        path: Optional[Path] = None) -> dict[str, list]:
    """v10.111 — load named status lists from
    data/integration_layer_config.json::status_vocabulary. Returns
    a {list_name: [values...]} map for the field_in_named DSL type.

    Used at predicate compile time, so admin edits to vocabulary
    require both refresh_overrides_cache() AND a rule reload to
    propagate.
    """
    if path is None:
        path = _data_dir() / "integration_layer_config.json"
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        vocab = data.get("status_vocabulary", {}) or {}
        # Defensive: ensure every value is a list of values
        return {k: list(v) for k, v in vocab.items() if isinstance(v, list)}
    except Exception as e:
        logger.warning(
            f"Failed to load status vocabulary from {path}: {e}")
        return {}
