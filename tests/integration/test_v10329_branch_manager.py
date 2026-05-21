"""Integration tests for v10.329 — Branch Manager Activity Generator.

Per banking convention, branch performance IS the Branch Manager's
performance. PBT, NPL Ratio, PAR, CIR are branch-level KPIs that ARE
the BM's own scorecard (not recursive team aggregates).

15 tests across 6 sections (module-level functions for sweep compat).
"""

import json
import sys
from pathlib import Path


REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Module surface + config integrity
# ────────────────────────────────────────────────────────────────────

def test_v10329_module_imports_and_surface():
    """The generator module exposes the required public surface."""
    for k in list(sys.modules):
        if k.startswith("utils.branch_manager_generator"):
            del sys.modules[k]
    from utils import branch_manager_generator as bmg
    assert hasattr(bmg, "generate_for_period")
    assert hasattr(bmg, "find_branch_managers")
    assert hasattr(bmg, "get_branch_manager_count")
    assert hasattr(bmg, "load_config")
    assert hasattr(bmg, "list_role_kpis")


def test_v10329_config_has_both_bm_roles_with_21_kpis():
    """Config covers Branch Manager + Senior Branch Manager with 21 KPIs each."""
    cfg = json.loads(
        (REPO / "data" / "branch_manager_config.json").read_text()
    )
    roles = cfg.get("roles", {})
    assert "Branch Manager" in roles
    assert "Senior Branch Manager" in roles
    for role in ("Branch Manager", "Senior Branch Manager"):
        kpis = roles[role].get("kpis", [])
        assert len(kpis) == 21, (
            f"{role} should have 21 KPIs, got {len(kpis)}"
        )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Generator runtime + idempotency
# ────────────────────────────────────────────────────────────────────

def test_v10329_find_branch_managers_returns_active_pool():
    """≥80 active Branch Managers (8 Senior + 86 standard expected)."""
    for k in list(sys.modules):
        if k.startswith("utils.branch_manager_generator"):
            del sys.modules[k]
    from utils.branch_manager_generator import find_branch_managers
    bms = find_branch_managers()
    assert len(bms) >= 80, f"Expected ≥80 BMs, got {len(bms)}"
    senior = [b for b in bms if b[1] == "Senior Branch Manager"]
    standard = [b for b in bms if b[1] == "Branch Manager"]
    assert len(senior) >= 5
    assert len(standard) >= 70


def test_v10329_dry_run_does_not_modify_actuals():
    """Dry-run mode produces summary but does not write to BSC store."""
    for k in list(sys.modules):
        if k.startswith("utils.branch_manager_generator"):
            del sys.modules[k]
    from utils.branch_manager_generator import generate_for_period
    actuals_path = REPO / "data" / "bsc_actuals_2026-Q2.json"
    before = actuals_path.read_bytes()
    result = generate_for_period("2026-Q2", dry_run=True)
    after = actuals_path.read_bytes()
    assert before == after, "Dry-run modified the actuals file"
    assert result["kpis_submitted"] > 0


def test_v10329_idempotent_upsert():
    """Running the generator twice on the same period produces stable count."""
    for k in list(sys.modules):
        if k.startswith("utils.branch_manager_generator"):
            del sys.modules[k]
    from utils.branch_manager_generator import generate_for_period
    actuals_path = REPO / "data" / "bsc_actuals_2026-Q2.json"
    r1 = generate_for_period("2026-Q2", dry_run=False)
    actuals_1 = json.loads(actuals_path.read_text())
    bm_count_1 = sum(
        1 for a in actuals_1
        if a.get("source_module") == "branch_manager_generator"
    )
    r2 = generate_for_period("2026-Q2", dry_run=False)
    actuals_2 = json.loads(actuals_path.read_text())
    bm_count_2 = sum(
        1 for a in actuals_2
        if a.get("source_module") == "branch_manager_generator"
    )
    assert bm_count_1 == bm_count_2, (
        f"Idempotency violated: {bm_count_1} → {bm_count_2}"
    )
    assert r1["kpis_submitted"] == r2["kpis_submitted"]


# ────────────────────────────────────────────────────────────────────
# Section 3 — KPI canonical resolution
# ────────────────────────────────────────────────────────────────────

def test_v10329_all_21_bm_kpis_resolve_canonical():
    """All 21 Branch Manager role_kpis resolve to defined canonical KPIs."""
    for k in list(sys.modules):
        if k.startswith("utils.bsc_score_computation"):
            del sys.modules[k]
    from utils.bsc_score_computation import resolve_role_kpis
    resolutions = resolve_role_kpis("Branch Manager")
    assert len(resolutions) == 21
    undefined = [r.role_kpi_ref for r in resolutions if not r.defined]
    assert not undefined, f"Undefined KPIs: {undefined}"


def test_v10329_npl_ratio_added_to_canonical():
    """NPL_RATIO and NEW_ACCOUNTS are now canonical KPI definitions."""
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    ids = {k.get("id") for k in lib.get("kpis", [])}
    assert "NPL_RATIO" in ids
    assert "NEW_ACCOUNTS" in ids
    npl = next(k for k in lib["kpis"] if k.get("id") == "NPL_RATIO")
    assert npl["direction"] == "lower"
    assert npl["pillar"] == "Financial"


def test_v10329_compliance_alias_resolves():
    """COMPLIANCE role_kpi ref aliases to COMPLIANCE_SCORE canonical."""
    for k in list(sys.modules):
        if k.startswith("utils.bsc_score_computation"):
            del sys.modules[k]
    from utils.bsc_score_computation import KPI_ID_ALIASES
    assert KPI_ID_ALIASES.get("COMPLIANCE") == "COMPLIANCE_SCORE"


# ────────────────────────────────────────────────────────────────────
# Section 4 — Scale + direction-awareness
# ────────────────────────────────────────────────────────────────────

def test_v10329_kes_m_bases_scale_to_raw_kes():
    """PBT base 65 (KES M) produces a value in the 40M-100M range."""
    for k in list(sys.modules):
        if k.startswith("utils.branch_manager_generator"):
            del sys.modules[k]
    from utils.branch_manager_generator import _value_for, load_config
    cfg = load_config()
    pbt_spec = next(
        k for k in cfg["roles"]["Branch Manager"]["kpis"]
        if k["id"] == "PBT"
    )
    value = _value_for("300277", "2026-Q2", pbt_spec, "MID", cfg)
    assert 40_000_000 < float(value) < 100_000_000, (
        f"PBT value {value} not in expected range"
    )


def test_v10329_lower_is_better_inversion_for_npl():
    """HIGH-band BM produces LOWER NPL_RATIO than LOW-band BM."""
    for k in list(sys.modules):
        if k.startswith("utils.branch_manager_generator"):
            del sys.modules[k]
    from utils.branch_manager_generator import _value_for, load_config
    cfg = load_config()
    npl_spec = next(
        k for k in cfg["roles"]["Branch Manager"]["kpis"]
        if k["id"] == "NPL_RATIO"
    )
    high = _value_for("BM_HIGH_TEST", "2026-Q2", npl_spec, "HIGH", cfg)
    low = _value_for("BM_HIGH_TEST", "2026-Q2", npl_spec, "LOW", cfg)
    assert float(high) < float(low), (
        f"HIGH-band BM should have LOWER NPL (high={high}, low={low})"
    )


def test_v10329_score_5_clamping():
    """CX Score values stay within [1, 5] range across bands and staff."""
    for k in list(sys.modules):
        if k.startswith("utils.branch_manager_generator"):
            del sys.modules[k]
    from utils.branch_manager_generator import _value_for, load_config
    cfg = load_config()
    cx_spec = next(
        k for k in cfg["roles"]["Branch Manager"]["kpis"]
        if k["id"] == "CX Score"
    )
    for band in ("HIGH", "MID", "LOW"):
        for staff in ("300277", "300291", "300305"):
            v = float(_value_for(staff, "2026-Q2", cx_spec, band, cfg))
            assert 1.0 <= v <= 5.0, (
                f"CX Score {v} out of [1,5] for {staff}/{band}"
            )


# ────────────────────────────────────────────────────────────────────
# Section 5 — Cascade integration
# ────────────────────────────────────────────────────────────────────

def test_v10329_bm_actuals_in_bsc_store_q2():
    """At least 1800 Branch Manager actuals tagged correctly in Q2 BSC store."""
    actuals = json.loads(
        (REPO / "data" / "bsc_actuals_2026-Q2.json").read_text()
    )
    bm_actuals = [
        a for a in actuals
        if a.get("source_module") == "branch_manager_generator"
    ]
    assert len(bm_actuals) >= 1800, (
        f"Expected ≥1800 BM actuals, got {len(bm_actuals)}"
    )
    for a in bm_actuals[:5]:
        assert "_v10329_band" in a
        assert "_v10329_role" in a


def test_v10329_bms_have_computed_q2_scores():
    """≥80 Branch Managers have non-null cascade scores in Q2."""
    for k in list(sys.modules):
        if k.startswith("utils.virtual_bank"):
            del sys.modules[k]
    from utils.virtual_bank import staff_universe
    u = staff_universe()
    bm_codes = {
        r.staff_code for r in u.values()
        if "Branch Manager" in r.role
        and "Assistant" not in r.role
        and "Asst" not in r.role
        and r.active
    }
    scores = json.loads(
        (REPO / "data" / "cascade_scores_2026-Q2.json").read_text()
    ).get("scores", {})
    scoring = sum(1 for c in bm_codes if scores.get(c) is not None)
    assert scoring >= 80, (
        f"Only {scoring} of {len(bm_codes)} BMs have Q2 scores"
    )


# ────────────────────────────────────────────────────────────────────
# Section 6 — Determinism + band distribution
# ────────────────────────────────────────────────────────────────────

def test_v10329_deterministic_value_generation():
    """Same (staff, period, kpi) produces identical value on repeated calls."""
    for k in list(sys.modules):
        if k.startswith("utils.branch_manager_generator"):
            del sys.modules[k]
    from utils.branch_manager_generator import _value_for, load_config
    cfg = load_config()
    pbt_spec = next(
        k for k in cfg["roles"]["Branch Manager"]["kpis"]
        if k["id"] == "PBT"
    )
    v1 = _value_for("300277", "2026-Q2", pbt_spec, "MID", cfg)
    v2 = _value_for("300277", "2026-Q2", pbt_spec, "MID", cfg)
    v3 = _value_for("300277", "2026-Q2", pbt_spec, "MID", cfg)
    assert v1 == v2 == v3, f"Non-deterministic: {v1}, {v2}, {v3}"


def test_v10329_band_distribution_within_tolerance():
    """Band assignment respects config weights — HIGH/MID/LOW within tolerance."""
    for k in list(sys.modules):
        if k.startswith("utils.branch_manager_generator"):
            del sys.modules[k]
    from utils.branch_manager_generator import generate_for_period
    result = generate_for_period("2026-Q2", dry_run=True)
    dist = result["band_distribution"]
    total = sum(dist.values())
    high_pct = dist["HIGH"] / total
    mid_pct = dist["MID"] / total
    low_pct = dist["LOW"] / total
    # Config: standard BM 25/55/20 + senior 35/55/10
    # Blend across 86 standard + 8 senior gives roughly HIGH 26%, MID 55%, LOW 19%
    assert 0.18 <= high_pct <= 0.35, f"HIGH band {high_pct:.2%} off range"
    assert 0.40 <= mid_pct <= 0.65, f"MID band {mid_pct:.2%} off range"
    assert 0.12 <= low_pct <= 0.30, f"LOW band {low_pct:.2%} off range"


# ────────────────────────────────────────────────────────────────────
# Section 7 — Audit gate G220 wired
# ────────────────────────────────────────────────────────────────────

def test_v10329_g220_gate_function_exists():
    """G220 gate is registered in scripts/audit.py."""
    for k in list(sys.modules):
        if k.startswith("scripts.audit"):
            del sys.modules[k]
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_module", str(REPO / "scripts" / "audit.py")
    )
    audit_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit_mod)
    assert hasattr(audit_mod, "gate_branch_manager_integration")
    # G220 in GATES list
    gate_ids = [gid for gid, _ in audit_mod.GATES]
    assert "G220" in gate_ids
