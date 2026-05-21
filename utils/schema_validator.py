"""
utils/schema_validator.py — Data Schema Lock (v10.342, Option D).

Validates protected data files against schemas in data/_schemas/. Used
by the audit gate G230 and (optionally) by producers writing protected
files. Light JSON Schema subset implemented in pure stdlib — no jsonschema
dependency required.

Public API:
    list_protected_files()         -> [filename, ...]
    load_schema(filename)          -> schema dict | None
    validate_file(filename)        -> {valid, errors, file, schema_version}
    validate_value(value, schema)  -> {valid, errors}
    register_schema(name, schema)  -> add a new schema in memory (tests)

Supported JSON Schema keywords (subset):
    type, required, properties, additionalProperties, items, minItems,
    maxItems, minLength, minimum, maximum, enum, pattern, oneOf

Not supported (intentionally — keeps the validator lightweight):
    $ref, $schema (cosmetic), allOf, anyOf, not, format, dependencies

The subset is sufficient for every schema currently in data/_schemas/.
If a future schema needs anyOf or $ref, expand here (and add tests).

Shipped: v10.342 — Option D harmonization arc.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
_SCHEMAS_DIR = _ROOT / "data" / "_schemas"
_DATA_DIR = _ROOT / "data"


# ────────────────────────────────────────────────────────────────────
# Schema discovery
# ────────────────────────────────────────────────────────────────────

def list_protected_files() -> List[str]:
    """Return filenames of every data file with a registered schema."""
    if not _SCHEMAS_DIR.exists():
        return []
    return sorted([
        p.name.replace(".schema.json", ".json")
        for p in _SCHEMAS_DIR.glob("*.schema.json")
        if not p.name.startswith("_")
    ])


def load_schema(filename: str) -> Optional[Dict[str, Any]]:
    """Load the schema for a data filename (e.g. 'bank_targets.json')."""
    schema_path = _SCHEMAS_DIR / f"{filename.replace('.json', '')}.schema.json"
    if not schema_path.exists():
        return None
    try:
        from utils.db import db as _db
        return _db.load_json(schema_path, default=None)
    except Exception:
        return None


# ────────────────────────────────────────────────────────────────────
# Validation primitives
# ────────────────────────────────────────────────────────────────────

_TYPE_MAP = {
    "object":  dict,
    "array":   list,
    "string":  str,
    "number":  (int, float),
    "integer": int,
    "boolean": bool,
    "null":    type(None),
}


def _check_type(value: Any, json_type: str) -> bool:
    """JSON Schema type check, with Python boolean handled separately
    (booleans are also ints in Python, but JSON Schema says no)."""
    expected = _TYPE_MAP.get(json_type)
    if expected is None:
        return False
    if json_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if json_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if json_type == "boolean":
        return isinstance(value, bool)
    return isinstance(value, expected)


def _validate_node(value: Any, schema: Dict[str, Any], path: str) -> List[str]:
    """Recursive node validator. Returns list of error strings."""
    errors: List[str] = []

    # oneOf: at least one branch must match (we accept first match)
    if "oneOf" in schema:
        branch_errors = []
        matched = False
        for branch in schema["oneOf"]:
            be = _validate_node(value, branch, path)
            if not be:
                matched = True
                break
            branch_errors.append(be)
        if not matched:
            errors.append(
                f"{path}: did not match any oneOf branch "
                f"({len(schema['oneOf'])} branches tried)"
            )
        return errors

    # type check
    schema_type = schema.get("type")
    if schema_type:
        types = schema_type if isinstance(schema_type, list) else [schema_type]
        if not any(_check_type(value, t) for t in types):
            errors.append(
                f"{path}: expected type {schema_type}, got "
                f"{type(value).__name__}"
            )
            # Type mismatch — further checks would be noisy, return early
            return errors

    # enum
    if "enum" in schema and value not in schema["enum"]:
        errors.append(
            f"{path}: value {value!r} not in enum {schema['enum']}"
        )

    # number bounds
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: {value} < minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: {value} > maximum {schema['maximum']}")

    # string bounds
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(
                f"{path}: string length {len(value)} < "
                f"minLength {schema['minLength']}"
            )
        if "pattern" in schema:
            try:
                if not re.search(schema["pattern"], value):
                    errors.append(
                        f"{path}: {value!r} does not match pattern "
                        f"{schema['pattern']!r}"
                    )
            except re.error as exc:
                errors.append(f"{path}: bad regex {schema['pattern']!r}: {exc}")

    # object validation
    if isinstance(value, dict):
        for req in schema.get("required", []):
            if req not in value:
                errors.append(f"{path}: missing required key {req!r}")
        props = schema.get("properties", {})
        addl = schema.get("additionalProperties", True)
        for k, v in value.items():
            sub_path = f"{path}.{k}" if path else k
            if k in props:
                errors.extend(_validate_node(v, props[k], sub_path))
            elif addl is False:
                errors.append(f"{path}: unexpected property {k!r}")
            elif isinstance(addl, dict):
                # additionalProperties as a sub-schema
                errors.extend(_validate_node(v, addl, sub_path))

    # array validation
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(
                f"{path}: array length {len(value)} < "
                f"minItems {schema['minItems']}"
            )
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(
                f"{path}: array length {len(value)} > "
                f"maxItems {schema['maxItems']}"
            )
        item_schema = schema.get("items")
        if item_schema:
            for i, item in enumerate(value):
                errors.extend(_validate_node(
                    item, item_schema, f"{path}[{i}]"
                ))

    return errors


def validate_value(value: Any, schema: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a value against a schema. Returns {valid, errors}."""
    errors = _validate_node(value, schema, "")
    return {"valid": len(errors) == 0, "errors": errors}


# ────────────────────────────────────────────────────────────────────
# File-level validation
# ────────────────────────────────────────────────────────────────────

def validate_file(filename: str) -> Dict[str, Any]:
    """Validate data/<filename> against its schema.

    Returns: {
        file: str,                  # filename
        schema_version: str | None, # _lock_version from schema
        valid: bool,
        errors: list[str],
        error_count: int,
        protected: bool,            # False if no schema exists
    }
    """
    schema = load_schema(filename)
    if schema is None:
        return {
            "file":           filename,
            "schema_version": None,
            "valid":          True,
            "errors":         [],
            "error_count":    0,
            "protected":      False,
        }

    data_path = _DATA_DIR / filename
    if not data_path.exists():
        return {
            "file":           filename,
            "schema_version": schema.get("_lock_version"),
            "valid":          False,
            "errors":         [f"data file {filename!r} not found"],
            "error_count":    1,
            "protected":      True,
        }

    try:
        from utils.db import db as _db
        data = _db.load_json(data_path, default=None)
        if data is None:
            raise ValueError("load returned None")
    except Exception as exc:
        return {
            "file":           filename,
            "schema_version": schema.get("_lock_version"),
            "valid":          False,
            "errors":         [f"JSON parse error: {exc}"],
            "error_count":    1,
            "protected":      True,
        }

    result = validate_value(data, schema)
    return {
        "file":           filename,
        "schema_version": schema.get("_lock_version"),
        "valid":          result["valid"],
        "errors":         result["errors"][:25],  # cap noisy output
        "error_count":    len(result["errors"]),
        "protected":      True,
    }


def validate_all_protected() -> Dict[str, Any]:
    """Validate every protected data file. Returns summary + per-file detail."""
    protected = list_protected_files()
    results = [validate_file(f) for f in protected]
    valid_count = sum(1 for r in results if r["valid"])
    return {
        "protected_count": len(protected),
        "valid_count":     valid_count,
        "invalid_count":   len(protected) - valid_count,
        "files":           results,
    }


# ────────────────────────────────────────────────────────────────────
# Write-time hook (optional — producers can use this before save)
# ────────────────────────────────────────────────────────────────────

def validate_before_save(filename: str, value: Any) -> Dict[str, Any]:
    """Validate a value about to be written to data/<filename>.

    Producers (e.g. admin UI save handlers) can call this to refuse
    a write that would break the schema. Returns the same shape as
    validate_value.
    """
    schema = load_schema(filename)
    if schema is None:
        return {"valid": True, "errors": [], "protected": False}
    result = validate_value(value, schema)
    result["protected"] = True
    return result
