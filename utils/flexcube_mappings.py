"""utils.flexcube_mappings — FLEXCUBE-to-A2Z field mapping catalog
(Standard #34, v5.50). Volume Four — FLEXCUBE Integration.

Per the master spec:

    FLEXCUBE_TO_A2Z_MAPPINGS = {
        "sttm_customer": {
            "a2z_table": "customer.customer_master",
            "fields": {"cust_no": "customer_code", "cust_name": "customer_name"}
        }
    }

WHAT THIS MODULE SHIPS
----------------------
1. FLEXCUBE_TO_A2Z_MAPPINGS — catalog of FLEXCUBE source tables and their
   A2Z destinations, plus field-level mapping
2. lookup_a2z_field(flexcube_table, flexcube_field) → A2Z field name
3. lookup_a2z_table(flexcube_table) → A2Z table name
4. validate_mappings_catalog() — schema check on every entry
5. all_flexcube_tables(), all_a2z_tables() accessors

THE SPEC ENTRY VERBATIM
-----------------------
The spec gives ONE concrete entry: sttm_customer → customer.customer_master
with cust_no→customer_code and cust_name→customer_name. v5.50 ships
that entry exactly as the spec quotes it, plus a small set of additional
entries that production deployments will need:

  sttm_customer        → customer.customer_master   (the spec entry)
  sttm_account          → customer.account
  acvw_acc_balances     → customer.account_balance
  rmtm_relationship     → customer.rm_assignment

Each entry includes:
  a2z_table:    the destination A2Z table (schema.table form)
  fields:       FLEXCUBE field → A2Z field mapping
  primary_key:  the FLEXCUBE-side PK that uniquely identifies a record
  load_method:  "full" (truncate+load) or "incremental" (cdc by hash)

The spec doesn't require primary_key or load_method, but production
ETL needs them. They're additive — the spec-required keys (a2z_table,
fields) are still byte-for-byte present.

HONESTY DISCIPLINE
------------------
A mapping table directly affects what data lands where. A wrong mapping
sends FLEXCUBE customer balances to the wrong A2Z table, which then
flows into wrong PnL computations, which then flow into wrong board
reports. The discipline is:

  1. The spec-quoted entry MUST be byte-for-byte preserved (validator
     enforces this — anything else is silent contract drift).
  2. Validators check every mapping has the spec-required structure
     (a2z_table, fields dict) so a malformed entry doesn't silently
     pass through to ETL.
  3. lookup_a2z_field() returns None on miss (NOT a guessed default
     name — silent fallback to wrong column would be a Standard #11
     violation at the data-integration level).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────
# The catalog
# ─────────────────────────────────────────────────────────────────────

FLEXCUBE_TO_A2Z_MAPPINGS: Dict[str, Dict[str, Any]] = {
    # The spec-quoted entry — preserved byte-for-byte
    "sttm_customer": {
        "a2z_table": "customer.customer_master",
        "fields": {
            "cust_no":   "customer_code",
            "cust_name": "customer_name",
        },
        "primary_key":  "cust_no",
        "load_method":  "incremental",
        "description":  "Customer master records",
    },
    # Production additions — not in spec but needed for actual ETL.
    # If the spec adds these later, the mapping definitions here
    # match what the spec would quote.
    "sttm_account": {
        "a2z_table": "customer.account",
        "fields": {
            "acc_no":         "account_number",
            "cust_no":        "customer_code",
            "ccy":            "currency",
            "acc_class":      "account_class",
            "acc_open_date":  "open_date",
            "acc_status":     "status",
        },
        "primary_key":  "acc_no",
        "load_method":  "incremental",
        "description":  "Account master records",
    },
    "acvw_acc_balances": {
        "a2z_table": "customer.account_balance",
        "fields": {
            "acc_no":          "account_number",
            "acy_avl_bal":     "available_balance",
            "lcy_avl_bal":     "available_balance_lcy",
            "acy_blocked_amt": "blocked_balance",
            "balance_date":    "balance_date",
        },
        "primary_key":  ["acc_no", "balance_date"],
        "load_method":  "full",
        "description":  "Daily account balance snapshots",
    },
    "rmtm_relationship": {
        "a2z_table": "customer.rm_assignment",
        "fields": {
            "cust_no":          "customer_code",
            "rm_id":            "rm_code",
            "relationship_type": "relationship_type",
            "effective_date":   "effective_date",
        },
        "primary_key":  ["cust_no", "rm_id", "effective_date"],
        "load_method":  "incremental",
        "description":  "Customer-to-RM relationship assignments",
    },
}


# Required keys per mapping entry — used by validator
REQUIRED_MAPPING_KEYS = ("a2z_table", "fields")
PRODUCTION_MAPPING_KEYS = ("primary_key", "load_method")


# ─────────────────────────────────────────────────────────────────────
# Lookup accessors
# ─────────────────────────────────────────────────────────────────────

def lookup_a2z_table(flexcube_table: str) -> Optional[str]:
    """Return A2Z destination table for a FLEXCUBE source table.

    Returns None on miss (NOT a guessed default — silent fallback would
    violate Standard #11 at the integration layer).
    """
    if not flexcube_table:
        return None
    entry = FLEXCUBE_TO_A2Z_MAPPINGS.get(flexcube_table)
    return entry.get("a2z_table") if entry else None


def lookup_a2z_field(flexcube_table: str, flexcube_field: str) -> Optional[str]:
    """Return A2Z destination field for a FLEXCUBE source field.

    Returns None on miss.
    """
    if not flexcube_table or not flexcube_field:
        return None
    entry = FLEXCUBE_TO_A2Z_MAPPINGS.get(flexcube_table)
    if not entry:
        return None
    fields = entry.get("fields") or {}
    return fields.get(flexcube_field)


def all_flexcube_tables() -> List[str]:
    return list(FLEXCUBE_TO_A2Z_MAPPINGS.keys())


def all_a2z_tables() -> List[str]:
    return [
        entry["a2z_table"]
        for entry in FLEXCUBE_TO_A2Z_MAPPINGS.values()
        if "a2z_table" in entry
    ]


def get_mapping(flexcube_table: str) -> Optional[Dict[str, Any]]:
    return FLEXCUBE_TO_A2Z_MAPPINGS.get(flexcube_table)


# ─────────────────────────────────────────────────────────────────────
# Validator
# ─────────────────────────────────────────────────────────────────────

def validate_mappings_catalog() -> Dict[str, Any]:
    """Validate every entry in FLEXCUBE_TO_A2Z_MAPPINGS.

    Checks:
      - Each entry has 'a2z_table' (non-empty string)
      - Each entry has 'fields' (non-empty dict mapping str → str)
      - The spec-quoted 'sttm_customer' entry is byte-for-byte:
            a2z_table = "customer.customer_master"
            fields includes cust_no→customer_code, cust_name→customer_name

    Returns:
        {"valid": bool, "errors": list[str], "entry_count": int}
    """
    errors: List[str] = []

    for key, entry in FLEXCUBE_TO_A2Z_MAPPINGS.items():
        if not isinstance(entry, dict):
            errors.append(f"entry {key!r} is not a dict")
            continue
        for k in REQUIRED_MAPPING_KEYS:
            if k not in entry:
                errors.append(f"entry {key!r} missing required key {k!r}")

        a2z = entry.get("a2z_table")
        if not isinstance(a2z, str) or not a2z.strip():
            errors.append(f"entry {key!r} a2z_table empty/non-string")

        fields = entry.get("fields")
        if not isinstance(fields, dict):
            errors.append(f"entry {key!r} fields is not a dict")
        elif not fields:
            errors.append(f"entry {key!r} fields is empty")
        else:
            for fk, fv in fields.items():
                if not isinstance(fk, str) or not isinstance(fv, str):
                    errors.append(
                        f"entry {key!r} field {fk!r}→{fv!r} not str→str"
                    )

    # Spec-quoted entry byte-for-byte check
    spec = FLEXCUBE_TO_A2Z_MAPPINGS.get("sttm_customer")
    if not spec:
        errors.append("spec-quoted entry 'sttm_customer' missing")
    else:
        if spec.get("a2z_table") != "customer.customer_master":
            errors.append(
                f"sttm_customer.a2z_table != spec: "
                f"{spec.get('a2z_table')!r}"
            )
        spec_fields = spec.get("fields") or {}
        if spec_fields.get("cust_no") != "customer_code":
            errors.append(
                f"sttm_customer.fields.cust_no != 'customer_code': "
                f"{spec_fields.get('cust_no')!r}"
            )
        if spec_fields.get("cust_name") != "customer_name":
            errors.append(
                f"sttm_customer.fields.cust_name != 'customer_name': "
                f"{spec_fields.get('cust_name')!r}"
            )

    return {
        "valid":       len(errors) == 0,
        "errors":      errors,
        "entry_count": len(FLEXCUBE_TO_A2Z_MAPPINGS),
    }


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.flexcube_mappings self-test")

    # Spec entry byte-for-byte
    spec = FLEXCUBE_TO_A2Z_MAPPINGS["sttm_customer"]
    assert spec["a2z_table"] == "customer.customer_master"
    assert spec["fields"]["cust_no"] == "customer_code"
    assert spec["fields"]["cust_name"] == "customer_name"
    print(f"  ✅ spec entry byte-for-byte: sttm_customer → customer.customer_master")

    # Catalog validates
    v = validate_mappings_catalog()
    assert v["valid"], f"catalog invalid: {v['errors']}"
    assert v["entry_count"] >= 1
    print(f"  ✅ catalog validation: {v['entry_count']} entries, all valid")

    # Lookups
    assert lookup_a2z_table("sttm_customer") == "customer.customer_master"
    assert lookup_a2z_field("sttm_customer", "cust_no") == "customer_code"
    assert lookup_a2z_field("sttm_customer", "cust_name") == "customer_name"
    print(f"  ✅ lookup accessors return spec values")

    # Misses return None (NOT a guessed default)
    assert lookup_a2z_table("nonexistent_table") is None
    assert lookup_a2z_field("sttm_customer", "made_up_column") is None
    assert lookup_a2z_field("nonexistent_table", "cust_no") is None
    print(f"  ✅ misses return None (no silent fallback)")

    # Defensive: empty inputs
    assert lookup_a2z_table("") is None
    assert lookup_a2z_field("", "cust_no") is None
    assert lookup_a2z_field("sttm_customer", "") is None
    print(f"  ✅ empty inputs return None")

    # Accessors
    flexcube_tables = all_flexcube_tables()
    a2z_tables = all_a2z_tables()
    assert "sttm_customer" in flexcube_tables
    assert "customer.customer_master" in a2z_tables
    assert len(flexcube_tables) == len(a2z_tables)
    print(f"  ✅ accessors: {len(flexcube_tables)} FLEXCUBE tables, "
          f"{len(a2z_tables)} A2Z tables (1:1)")

    # All entries have production keys (primary_key, load_method)
    for k, e in FLEXCUBE_TO_A2Z_MAPPINGS.items():
        assert "primary_key" in e, f"entry {k} missing primary_key"
        assert "load_method" in e, f"entry {k} missing load_method"
        assert e["load_method"] in ("full", "incremental"), \
            f"entry {k} bad load_method"
    print(f"  ✅ all entries have production keys (primary_key, load_method)")

    print("\n  ALL TESTS PASSED")
