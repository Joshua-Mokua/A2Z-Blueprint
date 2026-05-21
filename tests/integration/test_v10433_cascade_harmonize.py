"""Integration tests for v10.433 — cascade-BSC harmonization to 100%."""

import re
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10433_engine_exists():
    path = REPO / "utils" / "cascade_bsc_harmonize_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def fix_staff_productivity_bank_target",
        "def prune_obsolete_cascade_kpis",
        "def supplement_bsc_from_cascade",
        "def renormalize_after_supplement",
        "def align_bsc_targets_to_cascade",
        "def harmonize_all",
        "class StageAResult",
        "class StageBResult",
        "class StageCResult",
        "class StageDResult",
        "class StageEResult",
        "class HarmonizeAllResult",
        "BSC_SCORE_KPIS",
        "_resolve_canonical_name",
        "_build_role_kpi_universe",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10433_zero_streamlit():
    text = (REPO / "utils" / "cascade_bsc_harmonize_engine.py").read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10433_safety_dry_run_default():
    text = (REPO / "utils" / "cascade_bsc_harmonize_engine.py").read_text()
    # All public functions must default dry_run=True
    for fn_name in (
        "fix_staff_productivity_bank_target",
        "prune_obsolete_cascade_kpis",
        "supplement_bsc_from_cascade",
        "renormalize_after_supplement",
        "align_bsc_targets_to_cascade",
        "harmonize_all",
    ):
        # Look for `def fn_name(\n    dry_run: bool = True,`
        pattern = rf"def {fn_name}\(\s*dry_run: bool = True"
        assert re.search(pattern, text), f"{fn_name} not dry_run=True default"


def test_v10433_bsc_score_kpis_constant():
    for k in list(sys.modules):
        if "cascade_bsc_harmonize_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_harmonize_engine import BSC_SCORE_KPIS
    assert "Staff Productivity" in BSC_SCORE_KPIS
    assert "CX Score" in BSC_SCORE_KPIS
    assert len(BSC_SCORE_KPIS) == 7


def test_v10433_stage_a_is_noop_now():
    """v10.320 deliberately set bank_targets Staff Productivity to 85.0.
    Stage A should NOT change it (no-op)."""
    from utils.cascade_bsc_harmonize_engine import fix_staff_productivity_bank_target
    r = fix_staff_productivity_bank_target(dry_run=True)
    assert not r.needed_fix


def test_v10433_stage_b_idempotent_on_clean_state():
    """Running Stage B again on a clean state = 0 changes."""
    from utils.cascade_bsc_harmonize_engine import prune_obsolete_cascade_kpis
    r = prune_obsolete_cascade_kpis(dry_run=True)
    # After live migration applied, dry-run should show 0 changes
    assert r.cascade_entries_pruned == 0


def test_v10433_stage_c_idempotent_on_clean_state():
    """Stage C dry-run on clean state = no new rows."""
    from utils.cascade_bsc_harmonize_engine import supplement_bsc_from_cascade
    r = supplement_bsc_from_cascade(dry_run=True)
    assert r.bsc_rows_added == 0


def test_v10433_stage_e_idempotent_on_clean_state():
    """Stage E dry-run on clean state = no realignments."""
    from utils.cascade_bsc_harmonize_engine import align_bsc_targets_to_cascade
    r = align_bsc_targets_to_cascade(dry_run=True)
    assert r.rows_aligned == 0


def test_v10433_360_audit_at_100_harmony():
    """Post-migration: 360 audit should show 100% harmony."""
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    m = cascade_bsc_360_audit()
    assert m.overall_harmony_pct == 100.0
    assert m.stages_passing == 5


def test_v10433_bsc_rescue_health_still_100():
    """BSC rescue health must not regress from harmonization."""
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    h = bsc_full_audit()
    assert h.overall_health_pct == 100.0


def test_v10433_360_engine_has_bsc_score_kpis():
    """360 engine must skip BSC-score KPIs in bank-vs-MD compare."""
    text = (REPO / "utils" / "cascade_bsc_360_engine.py").read_text()
    assert "BSC_SCORE_KPIS" in text
    assert "bsc_score_kpis_skipped" in text


def test_v10433_360_engine_canonical_resolver():
    """360 Stage 3 must use canonical name resolution."""
    text = (REPO / "utils" / "cascade_bsc_360_engine.py").read_text()
    assert "name_to_canonical" in text


def test_v10433_canonical_resolve_product_book():
    """PRODUCT_BOOK_ACHIEVEMENT (cascade ID) → 'Product Book Achievement' (BSC name)."""
    import json
    from utils.cascade_bsc_harmonize_engine import _build_kpi_universe, _resolve_canonical_name
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    universe, name_to_meta = _build_kpi_universe(lib)
    resolved = _resolve_canonical_name(
        "PRODUCT_BOOK_ACHIEVEMENT", universe, name_to_meta, lib,
    )
    assert resolved == "Product Book Achievement"


def test_v10433_role_kpi_universe_built():
    """_build_role_kpi_universe returns dict role -> canonical KPI names."""
    import json
    from utils.cascade_bsc_harmonize_engine import _build_role_kpi_universe
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    role_universe = _build_role_kpi_universe(lib)
    assert "Managing Director" in role_universe
    md_kpis = role_universe["Managing Director"]
    # MD's role_kpis should resolve to canonical names
    assert "PBT" in md_kpis  # PBT is both name and id, so resolves to itself


def test_v10433_admin_panel_has_harmonize():
    text = (REPO / "utils" / "bsc_admin_panel.py").read_text()
    assert "def render_harmonize_panel" in text


def test_v10433_admin_page_wires_harmonize_panel():
    text = (REPO / "pages" / "7_admin.py").read_text()
    assert "render_harmonize_panel" in text


def test_v10433_admin_page_syntax_valid():
    import ast
    text = (REPO / "pages" / "7_admin.py").read_text()
    ast.parse(text)


def test_v10433_api_endpoints_registered():
    text = (REPO / "utils" / "api.py").read_text()
    assert "/api/v1/harmonize/all" in text
    assert "/api/v1/harmonize/stage" in text


def test_v10433_dataclasses_json_serializable():
    import json
    from utils.cascade_bsc_harmonize_engine import (
        fix_staff_productivity_bank_target, prune_obsolete_cascade_kpis,
        supplement_bsc_from_cascade, renormalize_after_supplement,
        align_bsc_targets_to_cascade, harmonize_all,
    )
    for fn in (
        fix_staff_productivity_bank_target, prune_obsolete_cascade_kpis,
        supplement_bsc_from_cascade, renormalize_after_supplement,
        align_bsc_targets_to_cascade, harmonize_all,
    ):
        r = fn(dry_run=True)
        json.dumps(r.to_dict())


def test_v10433_cascade_entries_narrowed():
    """Post-migration: cascade should have ~5050 entries (down from 24024)."""
    import json
    with open(REPO / "data" / "target_cascade.json") as f:
        cascade = json.load(f)
    real_entries = [k for k in cascade if not k.startswith("_")]
    assert 4000 <= len(real_entries) <= 6000, (
        f"Cascade should be ~5050 post-narrowing, got {len(real_entries)}"
    )


def test_v10433_cascade_has_role_aware_pruned_stamp():
    """Cascade should have v10.433 stamp."""
    import json
    with open(REPO / "data" / "target_cascade.json") as f:
        cascade = json.load(f)
    assert "_v10433_role_aware_pruned" in cascade


def test_v10433_g319_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10433_cascade_harmonize
    r = gate_v10433_cascade_harmonize()
    assert r["passed"], r.get("violations")
