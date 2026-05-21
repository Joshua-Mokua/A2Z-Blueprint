"""Integration tests for v10.473 — Phase O1 Stabilization & Wiring Completion.

Per Joshua Master Prompt (Enterprise Banking Digital Twin) Phase O1:
'No new expansion proceeds until enterprise wiring is complete, enterprise
actuals propagate correctly, KPI ecosystem is clean, and public interfaces
are certified.'

Validates B-100 through B-104 closure + G359.
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ── B-100: Period format normalisation ──────────────────────────────

def test_v10473_normalise_period_helper_exists():
    for k in list(sys.modules):
        if "virtual_bank_kpi_unifier" in k: del sys.modules[k]
    from utils.virtual_bank_kpi_unifier import _normalise_period
    assert callable(_normalise_period)


def test_v10473_normalise_period_accepts_yyyyqn():
    from utils.virtual_bank_kpi_unifier import _normalise_period
    assert _normalise_period("2026Q1") == "2026-Q1"
    assert _normalise_period("2026q3") == "2026-Q3"
    assert _normalise_period("2026Q4") == "2026-Q4"


def test_v10473_normalise_period_passthrough_canonical():
    from utils.virtual_bank_kpi_unifier import _normalise_period
    assert _normalise_period("2026") == "2026"
    assert _normalise_period("2026-Q1") == "2026-Q1"
    assert _normalise_period("2026-04") == "2026-04"
    assert _normalise_period("2026-04-15") == "2026-04-15"


def test_v10473_normalise_period_rejects_garbage():
    from utils.virtual_bank_kpi_unifier import _normalise_period
    with pytest.raises(ValueError):
        _normalise_period("garbage")
    with pytest.raises(ValueError):
        _normalise_period("")


def test_v10473_unify_bank_pbt_accepts_yyyyqn():
    """The originally-crashing call must now work."""
    for k in list(sys.modules):
        if "virtual_bank_kpi_unifier" in k: del sys.modules[k]
    from utils.virtual_bank_kpi_unifier import unify_bank_pbt
    rec = unify_bank_pbt(bank_pbt_value=100_000_000.0, period="2026Q1")
    assert rec.period == "2026-Q1"


# ── B-101: VB to live BSC actuals bridge ────────────────────────────

def test_v10473_vb_actuals_bridge_module_exists():
    assert (REPO / "utils" / "vb_actuals_bridge.py").exists()


def test_v10473_vb_actuals_bridge_exposes_required_api():
    from utils.vb_actuals_bridge import (
        refresh_actuals_from_virtual_bank,
        preview_actuals_from_virtual_bank,
        BridgeResult,
    )
    assert callable(refresh_actuals_from_virtual_bank)
    assert callable(preview_actuals_from_virtual_bank)


def test_v10473_vb_actuals_bridge_preview_dry_run():
    """Preview against repo cbs_data — must not write."""
    from utils.vb_actuals_bridge import preview_actuals_from_virtual_bank
    result = preview_actuals_from_virtual_bank()
    assert result.dry_run is True


def test_v10473_vb_actuals_bridge_self_tests_pass():
    from utils.vb_actuals_bridge import self_test
    self_test()  # raises on failure


# ── B-102: KPI library rationalisation ──────────────────────────────

def test_v10473_kpi_library_zero_active_unused():
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text(encoding="utf-8"))
    kpis = lib.get("kpis", [])
    role_kpis = lib.get("role_kpis", {})
    all_role_refs = set()
    for kl in role_kpis.values():
        if isinstance(kl, list):
            all_role_refs.update(str(k) for k in kl if isinstance(k, str))
    alias_targets_used = set()
    for k in kpis:
        if isinstance(k, dict):
            for a in (k.get("aliases") or []):
                if a in all_role_refs and k.get("id"):
                    alias_targets_used.add(k.get("id"))
    unused_active = [
        k.get("id") for k in kpis
        if isinstance(k, dict) and k.get("id") and not k.get("deprecated")
        and k.get("id") not in all_role_refs
        and k.get("id") not in alias_targets_used
    ]
    assert not unused_active, f"unused active KPIs: {unused_active[:10]}"


def test_v10473_kpi_library_has_deprecated_marker():
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text(encoding="utf-8"))
    deprecated = [k for k in lib.get("kpis", [])
                 if isinstance(k, dict) and k.get("deprecated")]
    assert len(deprecated) >= 50  # we deprecated 91
    # Each deprecated KPI has the v10.473 marker
    for k in deprecated:
        assert k.get("deprecated_v") == "v10.473"
        assert "deprecation_note" in k


# ── B-103: virtual_bank.py facade self-tests ────────────────────────

def test_v10473_virtual_bank_facade_has_self_test():
    text = (REPO / "utils" / "virtual_bank.py").read_text(encoding="utf-8")
    assert "def self_test(" in text
    assert text.count("def _test_") >= 15


def test_v10473_virtual_bank_facade_self_tests_pass():
    for k in list(sys.modules):
        if "virtual_bank" in k and "kpi_unifier" not in k:
            del sys.modules[k]
    from utils import virtual_bank as vb
    vb.reset_cache()
    vb.self_test()


def test_v10473_direct_reports_returns_chiefs_for_md():
    """Latent v10.314 bug surfaced + fixed: MD now has direct reports."""
    for k in list(sys.modules):
        if "virtual_bank" in k and "kpi_unifier" not in k:
            del sys.modules[k]
    from utils import virtual_bank as vb
    vb.reset_cache()
    reports = vb.direct_reports("300001")
    assert len(reports) >= 5, f"MD should have >=5 reports, got {len(reports)}"


def test_v10473_active_kpi_definitions_excludes_deprecated():
    """Latent v10.314 bug surfaced + fixed: deprecated KPIs excluded from active."""
    for k in list(sys.modules):
        if "virtual_bank" in k and "kpi_unifier" not in k:
            del sys.modules[k]
    from utils import virtual_bank as vb
    vb.reset_cache()
    active = vb.active_kpi_definitions()
    for kid, k in active.items():
        assert not k.get("deprecated"), f"{kid} deprecated but in active set"


# ── B-104: BSC submission path + staff_code hygiene ─────────────────

def test_v10473_all_departments_pass_bsc_submission():
    for k in list(sys.modules):
        if "virtual_bank" in k and "kpi_unifier" not in k:
            del sys.modules[k]
    from utils import virtual_bank as vb
    vb.reset_cache()
    rep = vb.verify_bsc_submission_path()
    assert rep.get("departments_failed", -1) == 0, (
        f"failures: {[(d, r) for d, r in rep.get('results', {}).items() if r.get('status') != 'OK']}"
    )


def test_v10473_hr_json_staff_codes_all_strings():
    hr = json.loads((REPO / "data" / "hr.json").read_text(encoding="utf-8"))
    records = hr if isinstance(hr, list) else list(hr.values())
    non_string = [r for r in records if isinstance(r, dict)
                  and r.get("staff_code") is not None
                  and not isinstance(r.get("staff_code"), str)]
    assert not non_string, f"non-string staff_codes: {[r.get('staff_code') for r in non_string[:5]]}"


def test_v10473_phantom_901xxx_records_deactivated():
    hr = json.loads((REPO / "data" / "hr.json").read_text(encoding="utf-8"))
    records = hr if isinstance(hr, list) else list(hr.values())
    active_phantoms = [r for r in records if isinstance(r, dict)
                       and str(r.get("staff_code", "")).startswith("9010")
                       and r.get("active")]
    assert not active_phantoms, f"active 901xxx phantoms: {[r.get('staff_code') for r in active_phantoms]}"


# ── G359 + regression ───────────────────────────────────────────────

def test_v10473_g359_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10473_o1_stabilization_complete
    r = gate_v10473_o1_stabilization_complete()
    assert r["passed"], r.get("violations")


def test_v10473_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9


def test_v10473_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k: del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct >= 99.9
