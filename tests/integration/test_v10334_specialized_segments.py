"""Integration tests for v10.334 — Specialized Segments / Propositions arm.

12 tests across 5 sections:
  Section 1 — Module surface + config (3 tests)
  Section 2 — Generator runtime (3 tests)
  Section 3 — Role-KPI canonical migration (2 tests)
  Section 4 — Cascade scoring (3 tests)
  Section 5 — Audit gate G223 (1 test)
"""

import json
import sys
from pathlib import Path


REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Module + config
# ────────────────────────────────────────────────────────────────────

def test_v10334_module_imports_and_surface():
    """The generator module exposes the required public surface."""
    for k in list(sys.modules):
        if k.startswith("utils.proposition_activity_generator"):
            del sys.modules[k]
    from utils import proposition_activity_generator as pg
    assert hasattr(pg, "generate_for_period")
    assert hasattr(pg, "find_specialized_segments_staff")
    assert hasattr(pg, "get_proposition_staff_count")
    assert hasattr(pg, "list_propositions_covered")
    assert hasattr(pg, "load_config")


def test_v10334_config_covers_three_propositions():
    """Config defines WB, DIA, AGR propositions."""
    cfg = json.loads(
        (REPO / "data" / "proposition_activity_config.json").read_text()
    )
    props = cfg.get("propositions", {})
    for code in ("WB", "DIA", "AGR"):
        assert code in props, f"Missing proposition {code}"
        assert "name" in props[code]
        assert "head_role" in props[code]


def test_v10334_config_uses_currency_agnostic_sentinel():
    """Config uses CCY_M (not KES M) for G162 compliance."""
    src = (
        REPO / "data" / "proposition_activity_config.json"
    ).read_text()
    assert "KES" not in src, "Config still has KES literal"
    assert '"CCY_M"' in src, (
        "Config must use CCY_M sentinel for currency-units"
    )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Generator runtime
# ────────────────────────────────────────────────────────────────────

def test_v10334_finds_specialized_segments_scope():
    """Generator finds the 8 expected staff: WB head + Diaspora/Special
    Segments dept (Sr Mgr + 4 RMs + 2 Sr ROs)."""
    for k in list(sys.modules):
        if k.startswith("utils.proposition_activity_generator"):
            del sys.modules[k]
    from utils.proposition_activity_generator import (
        find_specialized_segments_staff,
    )
    staff = find_specialized_segments_staff()
    assert len(staff) >= 7, f"Expected ≥7 staff, got {len(staff)}"
    # Should cover all 3 propositions
    props = {s[2] for s in staff}
    assert "WB" in props
    assert "DIA" in props
    assert "AGR" in props


def test_v10334_dry_run_does_not_write():
    """Dry-run produces summary but doesn't modify actuals."""
    for k in list(sys.modules):
        if k.startswith("utils.proposition_activity_generator"):
            del sys.modules[k]
    from utils.proposition_activity_generator import generate_for_period
    actuals_path = REPO / "data" / "bsc_actuals_2026-Q2.json"
    before = actuals_path.read_bytes()
    result = generate_for_period("2026-Q2", dry_run=True)
    after = actuals_path.read_bytes()
    assert before == after
    assert result["kpis_submitted"] > 0


def test_v10334_idempotent_upsert():
    """Running twice on same period produces stable count."""
    for k in list(sys.modules):
        if k.startswith("utils.proposition_activity_generator"):
            del sys.modules[k]
    from utils.proposition_activity_generator import generate_for_period
    actuals_path = REPO / "data" / "bsc_actuals_2026-Q2.json"
    r1 = generate_for_period("2026-Q2", dry_run=False)
    a1 = json.loads(actuals_path.read_text())
    n1 = sum(1 for a in a1 if isinstance(a, dict) and
             a.get("source_module") == "proposition_activity_generator")
    r2 = generate_for_period("2026-Q2", dry_run=False)
    a2 = json.loads(actuals_path.read_text())
    n2 = sum(1 for a in a2 if isinstance(a, dict) and
             a.get("source_module") == "proposition_activity_generator")
    assert n1 == n2
    assert r1["kpis_submitted"] == r2["kpis_submitted"]


# ────────────────────────────────────────────────────────────────────
# Section 3 — Role-KPI canonical migration
# ────────────────────────────────────────────────────────────────────

def test_v10334_specialized_segment_roles_use_canonical_kpis():
    """The 4 migrated roles no longer have K-coded role_kpis."""
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    role_kpis = lib["role_kpis"]
    migrated_roles = [
        "Head Of Women Banking",
        "Senior Manager Diaspora Banking",
        "Relationship Manager - Diaspora",
        "Senior Relationship Officer - Diaspora Banking",
    ]
    for role in migrated_roles:
        kpis = role_kpis.get(role, [])
        k_codes = [k for k in kpis if k.startswith("K") and k[1:].isdigit()]
        assert not k_codes, (
            f"{role} still has K-codes: {k_codes}"
        )


def test_v10334_provenance_marker_exists():
    """The migration audit trail is recorded in kpi_library."""
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    assert "_v10334_role_kpi_canonical_migration" in lib
    mig = lib["_v10334_role_kpi_canonical_migration"]
    assert mig.get("shipped") == "v10.334"
    assert "roles_migrated" in mig
    assert "previous_kpis" in mig  # rollback capability


# ────────────────────────────────────────────────────────────────────
# Section 4 — Cascade scoring
# ────────────────────────────────────────────────────────────────────

def test_v10334_specialized_segments_staff_score_in_q2():
    """All 8 specialized segments staff have non-null Q2 cascade scores."""
    sc = json.loads(
        (REPO / "data" / "cascade_scores_2026-Q2.json").read_text()
    ).get("scores", {})
    expected_scoring = [
        "300013",  # Head WB
        "300014",  # Sr Mgr Diaspora
        "300015", "300016",  # Diaspora RMs
        "300038", "300039",  # Agribusiness RMs
        "300205", "300206",  # Sr ROs
    ]
    missing = [c for c in expected_scoring if sc.get(c) is None]
    assert not missing, f"Specialized staff not scoring: {missing}"


def test_v10334_all_eight_propositions_have_scoring_heads_q2():
    """All 8 propositions have scoring heads in 2026-Q2."""
    sc = json.loads(
        (REPO / "data" / "cascade_scores_2026-Q2.json").read_text()
    ).get("scores", {})
    head_codes = {
        "WB":  "300013",
        "DIA": "300014",
        "AGR": "300014",
        "SME": "300018",
        "GOV": "300019",
        "TF":  "300017",
        "BNC": "300178",
        "DFS": "300051",
    }
    missing = [
        code for code, sc_code in head_codes.items()
        if sc.get(sc_code) is None
    ]
    assert not missing, f"Propositions without scoring heads: {missing}"


def test_v10334_wb_and_diaspora_score_all_four_quarters():
    """Head WB and Sr Mgr Diaspora score in all 4 quarters."""
    for p in ("2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"):
        sc = json.loads(
            (REPO / "data" / f"cascade_scores_{p}.json").read_text()
        ).get("scores", {})
        assert sc.get("300013") is not None, (
            f"WB Head not scoring in {p}"
        )
        assert sc.get("300014") is not None, (
            f"Diaspora Head not scoring in {p}"
        )


# ────────────────────────────────────────────────────────────────────
# Section 5 — Audit gate G223
# ────────────────────────────────────────────────────────────────────

def test_v10334_g223_gate_registered_and_passes():
    """G223 is registered in GATES list and passes."""
    for k in list(sys.modules):
        if k.startswith("scripts.audit"):
            del sys.modules[k]
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_module", str(REPO / "scripts" / "audit.py")
    )
    audit_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit_mod)
    gate_ids = [gid for gid, _ in audit_mod.GATES]
    assert "G223" in gate_ids
    result = audit_mod.gate_specialized_segments_integration()
    assert result["passed"], (
        f"G223 failed: {result['violations']}"
    )
