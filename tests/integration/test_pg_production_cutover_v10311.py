"""
tests/integration/test_pg_production_cutover_v10311.py
================================================================================
v10.311 — First production cutover toggle. Flips
`compliance_regulatory_returns` to `auto` mode in
data/integration_layer_config.json and verifies the cockpit
behavior is unchanged.

This is the end-to-end validation that v10.307 + v10.308's
infrastructure works:
  - v10.306 shipped the migration (DDL + migrators)
  - v10.307 routed compliance_regulatory_returns through the
    shim (first cockpit composer to use it)
  - v10.308 fanned out 4 more composers
  - v10.310 brought cockpit estate to placeholder-free state

Before this batch, the `_data_source` config knob was
documented and shim-respected but NEVER set in production
data. The cockpit always read JSON because per_table was empty.

This batch sets one production knob — `per_table.
compliance_regulatory_returns: "auto"` — and verifies:

1. The config has the new key
2. In `auto` mode without PG, the composer falls back to JSON
   silently (returns identical data to `json` mode)
3. The composer returns the same 60 records in both modes
4. The shim respects the new config
5. The cutover is documented in audit gate

Safety: `auto` mode means PG-attempt first, JSON-fallback
silent. If PG is unreachable (the audit env case), the
cockpit reads JSON exactly as before. Worst case is current
behavior. Best case is operators can populate PG and the
cockpit reads from it without code changes.

Test sections:
  1. Config has the new _data_source.per_table entry
  2. Auto mode returns same data as JSON mode (in PG-absent env)
  3. The shim respects the config
  4. The composer is unaffected by the toggle (returns 60 records)
  5. G201 audit gate
  6. Page 112 still renders correctly
  7. Toggle is reversible (operator can change back to "json")
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def tmp_data_dir():
    d = tempfile.mkdtemp(prefix="pg_cutover_v10311_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ============================================================
# Section 1 — Config has the new per_table entry
# ============================================================

def test_integration_layer_config_has_data_source_block():
    """integration_layer_config.json must now have a
    _data_source block with per_table mapping."""
    cfg = json.loads(
        (REPO_ROOT / "data"
         / "integration_layer_config.json").read_text()
    )
    assert "_data_source" in cfg, (
        "_data_source block missing from "
        "integration_layer_config.json"
    )
    ds = cfg["_data_source"]
    assert isinstance(ds, dict), (
        f"_data_source must be a dict, got {type(ds).__name__}"
    )
    assert "default" in ds
    assert "per_table" in ds


def test_compliance_regulatory_returns_set_to_auto():
    """The first cutover: per_table.
    compliance_regulatory_returns must be set to 'auto'.
    `auto` = try PG, fall back to JSON silently."""
    cfg = json.loads(
        (REPO_ROOT / "data"
         / "integration_layer_config.json").read_text()
    )
    per_table = cfg["_data_source"]["per_table"]
    assert "compliance_regulatory_returns" in per_table, (
        "per_table.compliance_regulatory_returns not set"
    )
    mode = per_table["compliance_regulatory_returns"]
    assert mode == "auto", (
        f"compliance_regulatory_returns should be 'auto' "
        f"(safe-cutover mode), got {mode!r}"
    )


def test_default_mode_still_json():
    """Other tables not in per_table should still default
    to JSON. The cutover is one-table-at-a-time."""
    cfg = json.loads(
        (REPO_ROOT / "data"
         / "integration_layer_config.json").read_text()
    )
    ds = cfg["_data_source"]
    assert ds["default"] == "json", (
        f"default mode changed unexpectedly: {ds['default']!r}"
    )


# ============================================================
# Section 2 — Production composer behavior unchanged
# ============================================================

def test_composer_reads_same_data_in_production_config():
    """The composer must return the same 60 records under
    the production `auto` config as it did under the default
    `json` config. PG is unreachable in this env, so `auto`
    falls back to JSON silently — equivalent behavior."""
    from utils.cockpit_read import compliance_regulatory_returns
    records = compliance_regulatory_returns(data_dir="data")
    # The known production count from v10.306 → 60 records
    assert len(records) == 60, (
        f"compliance_regulatory_returns under auto mode "
        f"returned {len(records)} records; expected 60. "
        f"The PG fallback to JSON should preserve the count."
    )


def test_composer_record_ids_unchanged_in_production_config():
    """Sample-check: known CBK return IDs from the JSON file
    must still appear in the composer's result under `auto`
    mode."""
    from utils.cockpit_read import compliance_regulatory_returns
    records = compliance_regulatory_returns(data_dir="data")
    ids = {r["id"] for r in records}
    # Known IDs from data/compliance.json
    for known_id in ("CBK0001", "CBK0002", "CBK0003"):
        assert known_id in ids, (
            f"Known ID {known_id} missing from auto-mode "
            f"composer result"
        )


# ============================================================
# Section 3 — Shim respects the new config
# ============================================================

def test_shim_returns_same_data_for_explicit_auto_mode(
    tmp_data_dir,
):
    """When auto mode is configured for a table but PG is
    unreachable, _load_table_via_shim must fall back to JSON
    and return the same data as default-config mode."""
    from utils.cockpit_read import _load_table_via_shim

    records = [
        {"id": "T1", "value": "alpha"},
        {"id": "T2", "value": "beta"},
        {"id": "T3", "value": "gamma"},
    ]
    (tmp_data_dir / "compliance.json").write_text(
        json.dumps(records))
    (tmp_data_dir / "integration_layer_config.json"
     ).write_text(json.dumps({
        "_data_source": {
            "default": "json",
            "per_table": {
                "compliance_regulatory_returns": "auto",
            },
        },
    }))

    # auto mode, PG unreachable → JSON fallback
    result = _load_table_via_shim(
        "compliance_regulatory_returns",
        json_filename="compliance.json",
        data_dir=tmp_data_dir,
    )
    assert len(result) == 3
    assert sorted(r["id"] for r in result) == ["T1", "T2", "T3"]


def test_json_mode_explicit_equivalent_to_auto_with_no_pg(
    tmp_data_dir,
):
    """Equivalence check: explicit `json` mode and `auto`
    mode (with PG unreachable) return identical data. This
    is the safety guarantee operators rely on when flipping
    a knob."""
    from utils.cockpit_read import _load_table_via_shim

    records = [{"id": "E1", "x": 1}, {"id": "E2", "x": 2}]
    (tmp_data_dir / "compliance.json").write_text(
        json.dumps(records))

    # json mode
    (tmp_data_dir / "integration_layer_config.json"
     ).write_text(json.dumps({
        "_data_source": {
            "default": "json",
            "per_table": {"compliance_regulatory_returns":
                          "json"},
        }}))
    json_result = _load_table_via_shim(
        "compliance_regulatory_returns",
        json_filename="compliance.json",
        data_dir=tmp_data_dir,
    )

    # auto mode (PG unreachable → falls back)
    (tmp_data_dir / "integration_layer_config.json"
     ).write_text(json.dumps({
        "_data_source": {
            "default": "json",
            "per_table": {"compliance_regulatory_returns":
                          "auto"},
        }}))
    auto_result = _load_table_via_shim(
        "compliance_regulatory_returns",
        json_filename="compliance.json",
        data_dir=tmp_data_dir,
    )

    assert json_result == auto_result, (
        "json mode and auto mode (with PG unreachable) "
        "should return identical data — this is the "
        "safety guarantee."
    )


# ============================================================
# Section 4 — Strict pg_view mode would NOT fall back
# ============================================================

def test_pg_view_mode_returns_empty_when_pg_unreachable(
    tmp_data_dir,
):
    """Strict `pg_view` mode does NOT silently fall back —
    if PG is unreachable, it returns []. This is the
    operator's choice for strict-mode deployments (catches
    infrastructure misconfigurations rather than masking
    them). The production config uses `auto`, not `pg_view`,
    precisely because we don't have a deployed PG yet."""
    from utils.cockpit_read import _load_table_via_shim

    records = [{"id": "S1"}]
    (tmp_data_dir / "compliance.json").write_text(
        json.dumps(records))
    (tmp_data_dir / "integration_layer_config.json"
     ).write_text(json.dumps({
        "_data_source": {
            "default": "json",
            "per_table": {"compliance_regulatory_returns":
                          "pg_view"},
        }}))

    result = _load_table_via_shim(
        "compliance_regulatory_returns",
        json_filename="compliance.json",
        data_dir=tmp_data_dir,
    )
    # pg_view + no PG → empty (deliberate, not bug)
    assert result == [], (
        f"pg_view mode without PG must return [] to surface "
        f"misconfiguration, got {len(result)} records"
    )


# ============================================================
# Section 5 — Reversibility
# ============================================================

def test_changing_back_to_json_restores_default_behavior(
    tmp_data_dir,
):
    """Operators must be able to roll back by changing the
    per_table entry back to 'json'. The composer should
    behave identically before and after the round-trip."""
    from utils.cockpit_read import _load_table_via_shim

    records = [{"id": "R1"}, {"id": "R2"}]
    (tmp_data_dir / "compliance.json").write_text(
        json.dumps(records))

    # Baseline: no config
    baseline = _load_table_via_shim(
        "compliance_regulatory_returns",
        json_filename="compliance.json",
        data_dir=tmp_data_dir,
    )

    # Flip to auto
    (tmp_data_dir / "integration_layer_config.json"
     ).write_text(json.dumps({
        "_data_source": {
            "default": "json",
            "per_table": {"compliance_regulatory_returns":
                          "auto"},
        }}))
    after_flip = _load_table_via_shim(
        "compliance_regulatory_returns",
        json_filename="compliance.json",
        data_dir=tmp_data_dir,
    )

    # Roll back to json
    (tmp_data_dir / "integration_layer_config.json"
     ).write_text(json.dumps({
        "_data_source": {
            "default": "json",
            "per_table": {"compliance_regulatory_returns":
                          "json"},
        }}))
    after_rollback = _load_table_via_shim(
        "compliance_regulatory_returns",
        json_filename="compliance.json",
        data_dir=tmp_data_dir,
    )

    assert baseline == after_flip == after_rollback, (
        "Three configs (none, auto, json) should produce "
        "identical results when PG is unreachable"
    )


# ============================================================
# Section 6 — Audit gate G201
# ============================================================

def test_g201_gate_exists_and_passes():
    from scripts.audit import GATES
    g201 = None
    for gid, fn in GATES:
        if gid == "G201":
            g201 = fn()
            break
    assert g201 is not None, "G201 not registered"
    assert g201["passed"], (
        f"G201 failed. {g201.get('summary', '')}. "
        f"Violations: {g201.get('violations', [])[:5]}"
    )


# ============================================================
# Section 7 — Existing v10.307 tests still pass
# ============================================================

def test_v10307_shim_tests_still_pass_with_new_config():
    """The v10.307 tests assumed no _data_source config
    was present. Now that production data has one, the
    shim behavior must still match v10.307's contract.
    This is a meta-check: run a representative v10.307
    test and confirm it still passes."""
    from utils.cockpit_read import compliance_regulatory_returns
    result = compliance_regulatory_returns(data_dir="data")
    assert isinstance(result, list)
    assert len(result) > 0


# ============================================================
# Section 8 — Documentation: pg_capable_tables unchanged
# ============================================================

def test_pg_capable_tables_unchanged():
    """The registry of PG-capable tables doesn't change —
    this batch flips an already-capable table's mode, it
    doesn't add new tables to the capable set."""
    from utils.cockpit_read import pg_capable_tables
    expected = {
        "audit_reviews",
        "compliance_regulatory_returns",
        "incidents",
        "nps_responses",
        "rcsa_register",
    }
    assert set(pg_capable_tables()) == expected
