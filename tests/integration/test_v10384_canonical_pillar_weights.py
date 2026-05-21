"""Integration tests for v10.384 — Canonical Pillar Weights Accessor.

Rescues the body's prioritization organ. v10.382 deep review surfaced
3 storage locations + 2 admin UIs (one ORPHAN — §5.4 silent failure).
v10.384 ships the canonical accessor + history + admin deprecation.

12 tests across 4 sections.
"""

import json
import sys
import tempfile
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Doc + module
# ────────────────────────────────────────────────────────────────────

def test_v10384_design_doc_has_7_parts():
    p = REPO / "docs" / "PILLAR_WEIGHTS_CANONICAL_v10.384.md"
    assert p.exists()
    text = p.read_text()
    for part in range(1, 8):
        assert f"## Part {part}" in text, f"missing Part {part}"


def test_v10384_module_has_required_exports():
    p = REPO / "utils" / "pillar_weights_canonical.py"
    text = p.read_text()
    for sym in (
        "def get_pillar_weights",
        "def save_pillar_weights",
        "def validate_pillar_weights",
        "def get_pillar_weights_history",
        "def detect_orphan_pillar_weights",
        "def health_check",
        "CANONICAL_PILLARS",
        "DEFAULT_BALANCED_WEIGHTS",
        "SUM_TOLERANCE",
    ):
        assert sym in text, f"missing {sym}"


def test_v10384_module_is_leaf():
    """No top-level upward utils.* imports."""
    p = REPO / "utils" / "pillar_weights_canonical.py"
    import ast
    tree = ast.parse(p.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (node.module and node.module.startswith("utils") and
                    node.col_offset == 0):
                raise AssertionError(
                    f"top-level upward utils.* import: {node.module}"
                )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Canonical accessor behavior
# ────────────────────────────────────────────────────────────────────

def test_v10384_get_returns_all_4_pillars():
    _reimport("utils.pillar_weights_canonical")
    from utils.pillar_weights_canonical import (
        get_pillar_weights, CANONICAL_PILLARS,
    )
    pw = get_pillar_weights()
    assert isinstance(pw, dict)
    for p in CANONICAL_PILLARS:
        assert p in pw
        assert isinstance(pw[p], float)


def test_v10384_get_returns_sum_one():
    """Canonical weights must sum to 1.0 (within tolerance)."""
    _reimport("utils.pillar_weights_canonical")
    from utils.pillar_weights_canonical import (
        get_pillar_weights, SUM_TOLERANCE,
    )
    pw = get_pillar_weights()
    total = sum(pw.values())
    assert abs(total - 1.0) <= SUM_TOLERANCE


def test_v10384_validate_accepts_balanced_default():
    _reimport("utils.pillar_weights_canonical")
    from utils.pillar_weights_canonical import (
        validate_pillar_weights, DEFAULT_BALANCED_WEIGHTS,
    )
    ok, err = validate_pillar_weights(DEFAULT_BALANCED_WEIGHTS)
    assert ok, err


def test_v10384_validate_rejects_zero_weight():
    """Zero pillar = dead organ. Constitution §12 Flow Principle violation."""
    _reimport("utils.pillar_weights_canonical")
    from utils.pillar_weights_canonical import (
        validate_pillar_weights, DEFAULT_BALANCED_WEIGHTS,
    )
    zero = dict(DEFAULT_BALANCED_WEIGHTS)
    zero["Financial"] = 0.0
    zero["Customer Focus"] = 0.65  # patch sum to 1.0
    ok, err = validate_pillar_weights(zero)
    assert not ok
    assert "> 0" in err or "dead organ" in err.lower()


def test_v10384_validate_rejects_sum_not_one():
    _reimport("utils.pillar_weights_canonical")
    from utils.pillar_weights_canonical import (
        validate_pillar_weights, CANONICAL_PILLARS,
    )
    bad = {p: 0.30 for p in CANONICAL_PILLARS}  # sum = 1.20
    ok, err = validate_pillar_weights(bad)
    assert not ok
    assert "sum" in err.lower()


# ────────────────────────────────────────────────────────────────────
# Section 3 — Orphan detection + history + admin notice
# ────────────────────────────────────────────────────────────────────

def test_v10384_orphan_detection_runs_on_real_data():
    """detect_orphan_pillar_weights runs cleanly; result is dict or None."""
    _reimport("utils.pillar_weights_canonical")
    from utils.pillar_weights_canonical import detect_orphan_pillar_weights
    result = detect_orphan_pillar_weights()
    assert result is None or isinstance(result, dict)


def test_v10384_history_appended_on_save():
    """save_pillar_weights appends to history. Use a tempdir for isolation."""
    import shutil
    _reimport("utils.pillar_weights_canonical")
    import utils.pillar_weights_canonical as pwc
    # Backup originals
    orig_kpi = pwc.KPI_LIBRARY_PATH
    orig_history = pwc.HISTORY_PATH

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        sandbox_kpi = td_path / "kpi_library.json"
        sandbox_hist = td_path / "pillar_weights_history.json"
        # Seed canonical
        sandbox_kpi.write_text(json.dumps({
            "pillar_weights": {
                "Financial": 0.40, "Customer Focus": 0.25,
                "Operational Excellence": 0.25, "People & Learning": 0.10,
            },
            "kpis": [], "role_kpis": {}, "active_kpis": [],
        }))
        pwc.KPI_LIBRARY_PATH = sandbox_kpi
        pwc.HISTORY_PATH = sandbox_hist

        try:
            ok, _ = pwc.save_pillar_weights(
                {"Financial": 0.50, "Customer Focus": 0.20,
                 "Operational Excellence": 0.20, "People & Learning": 0.10},
                actor="test_actor",
                reason="testing history capture",
            )
            assert ok
            assert sandbox_hist.exists()
            hist = json.loads(sandbox_hist.read_text())
            assert len(hist) == 1
            entry = hist[0]
            assert entry["changed_by"] == "test_actor"
            assert entry["old_weights"]["Financial"] == 0.40
            assert entry["new_weights"]["Financial"] == 0.50
            assert "testing" in entry["reason"]
        finally:
            pwc.KPI_LIBRARY_PATH = orig_kpi
            pwc.HISTORY_PATH = orig_history


def test_v10384_save_validates_before_writing():
    """Bad weights are rejected and don't touch the file."""
    _reimport("utils.pillar_weights_canonical")
    import utils.pillar_weights_canonical as pwc

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        sandbox_kpi = td_path / "kpi_library.json"
        sandbox_hist = td_path / "pillar_weights_history.json"
        sandbox_kpi.write_text(json.dumps({
            "pillar_weights": {
                "Financial": 0.40, "Customer Focus": 0.25,
                "Operational Excellence": 0.25, "People & Learning": 0.10,
            }
        }))
        orig_kpi = pwc.KPI_LIBRARY_PATH
        orig_hist = pwc.HISTORY_PATH
        pwc.KPI_LIBRARY_PATH = sandbox_kpi
        pwc.HISTORY_PATH = sandbox_hist
        try:
            # Try to save bad weights (sum != 1.0)
            ok, err = pwc.save_pillar_weights(
                {"Financial": 0.50, "Customer Focus": 0.50,
                 "Operational Excellence": 0.50, "People & Learning": 0.50},
                actor="test",
            )
            assert not ok
            assert "sum" in err.lower() or "validation" in err.lower()
            # History should be empty (no write happened)
            assert not sandbox_hist.exists() or json.loads(sandbox_hist.read_text()) == []
            # Canonical should be unchanged
            stored = json.loads(sandbox_kpi.read_text())
            assert stored["pillar_weights"]["Financial"] == 0.40
        finally:
            pwc.KPI_LIBRARY_PATH = orig_kpi
            pwc.HISTORY_PATH = orig_hist


def test_v10384_admin_has_rescue_marker():
    """The Bank Identity admin tab must reference the prioritization rescue.

    Pre-v10.388: deprecation notice (Deprecated + v10.384).
    Post-v10.388: redirect notice (Pillar weights moved + v10.388).
    Either marks the rescue properly.
    """
    p = REPO / "pages" / "7_admin.py"
    assert p.exists()
    text = p.read_text()
    has_v10384_deprecation = (
        "v10.384" in text and ("Deprecated" in text or "DEPRECATED" in text)
    )
    has_v10388_redirect = (
        "v10.388" in text and "Pillar weights moved" in text
    )
    assert has_v10384_deprecation or has_v10388_redirect, (
        "neither v10.384 deprecation notice nor v10.388 redirect "
        "notice present in admin page"
    )
    # Always require pointing to the canonical home (text or KPI Library tab)
    assert ("kpi_library.json::pillar_weights" in text or
            "KPI Library" in text), (
        "admin rescue marker should point to canonical store or KPI Library tab"
    )


# ────────────────────────────────────────────────────────────────────
# Section 4 — G270 + regression
# ────────────────────────────────────────────────────────────────────

def test_v10384_g270_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_canonical_pillar_weights
    r = gate_canonical_pillar_weights()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G270"


def test_v10384_no_regression_prior_canonical():
    """All Phase B canonical identities (v10.378+) still hold."""
    _reimport("utils")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.customer_master_canonical import (
        compute_unified_customer_master, reconciliation_summary,
    )
    from utils.kpi_alias_resolver import scan_role_kpis_coverage
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bp = float(compute_pbt_from_cbs(td_path).pbt)
        assert bp != 0
        unified = compute_unified_customer_master(cbs_dir=td_path)
        s = reconciliation_summary(unified, cbs_dir=td_path)
        assert s["identity_holds"]
    cov = scan_role_kpis_coverage()
    assert cov["unknown_orphans"] == 0
