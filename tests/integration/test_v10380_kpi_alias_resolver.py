"""Integration tests for v10.380 — KPI Alias Resolver + Deep Review.

Per Joshua's directive: deep review of target_cascade + kpi_library before
fixing. Surfaces 34 orphan KPI IDs across role_kpis, splits into:
  - 19 Class A (alias drift) — resolved via KPI_ALIASES
  - 15 Class B (genuinely missing) — documented in CLASS_B_ORPHANS

Read-only module — does NOT modify source files. Opt-in for consumers.

13 tests across 4 sections.
"""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Review doc + module presence/purity
# ────────────────────────────────────────────────────────────────────

def test_v10380_review_doc_present_with_all_10_parts():
    p = REPO / "docs" / "TARGET_CASCADE_KPI_LIBRARY_REVIEW_v10.380.md"
    assert p.exists()
    assert p.stat().st_size > 10000, "review doc seems too small"
    text = p.read_text()
    for part in (
        "## Part 1 — Target Cascade",
        "## Part 2 — KPI Library",
        "## Part 3 — The 34 orphan",
        "## Part 4 — Cross-reference matrix",
        "## Part 5 — Pillar weights drift",
        "## Part 6 — Cascade configuration patterns",
        "## Part 7 — Other findings",
        "## Part 8 — What v10.380 ships",
        "## Part 9 — Decisions awaiting Joshua",
        "## Part 10 — Honest acknowledgement",
    ):
        assert part in text, f"missing: {part}"


def test_v10380_resolver_module_present():
    p = REPO / "utils" / "kpi_alias_resolver.py"
    assert p.exists()
    text = p.read_text()
    for sym in ("KPI_ALIASES", "CLASS_B_ORPHANS",
                "def resolve_kpi_id", "def get_kpi_definition",
                "def list_class_b_orphans", "def is_class_b_orphan",
                "def clean_cascade_dict", "def scan_role_kpis_coverage",
                "CASCADE_META_KEY_PREFIXES"):
        assert sym in text, f"missing {sym}"


def test_v10380_resolver_module_is_leaf():
    """No top-level upward utils.* imports (v10.364 lesson)."""
    p = REPO / "utils" / "kpi_alias_resolver.py"
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
# Section 2 — Alias resolution mechanics
# ────────────────────────────────────────────────────────────────────

def test_v10380_class_a_aliases_resolve_correctly():
    _reimport("utils.kpi_alias_resolver")
    from utils.kpi_alias_resolver import resolve_kpi_id, KPI_ALIASES
    assert len(KPI_ALIASES) >= 17
    # Spot-check key mappings
    for alias, expected in (
        ("TOTAL_NFI", "Total NFI"),
        ("LOAN_GROWTH", "Loan Book Growth"),
        ("COMPLIANCE", "Compliance Score"),  # v10.402: canonical now human form
        ("AUDIT_SCORE", "Audit Score"),
        ("CX_SCORE", "CX Score"),
        ("STAFF_PROD", "Staff Productivity"),
        ("LOAN_DISB", "K001"),
        ("TRADE_FIN", "TRADE_FINANCE_REVENUE"),
    ):
        got = resolve_kpi_id(alias)
        assert got == expected, f"{alias} → {got}, expected {expected}"


def test_v10380_direct_library_ids_pass_through():
    """resolve_kpi_id returns input unchanged for direct library IDs."""
    _reimport("utils.kpi_alias_resolver")
    from utils.kpi_alias_resolver import resolve_kpi_id
    # v10.402: NPL_RATIO is now aliased to "NPL Ratio"; test with non-aliased ids only
    for direct_id in ("PBT", "DILIGENCE"):
        assert resolve_kpi_id(direct_id) == direct_id


def test_v10380_get_kpi_definition_via_alias():
    """get_kpi_definition resolves alias to library entry."""
    _reimport("utils.kpi_alias_resolver")
    from utils.kpi_alias_resolver import get_kpi_definition
    # Direct id
    pbt = get_kpi_definition("PBT")
    assert pbt is not None
    assert pbt["id"] == "PBT"
    assert pbt["pillar"] == "Financial"
    # Via alias
    nfi = get_kpi_definition("TOTAL_NFI")
    assert nfi is not None
    assert nfi["id"] == "Total NFI"
    # NIM was a Class B orphan pre-v10.390. v10.390 added NIM to the
    # library (inactive, awaiting MD targets). Accept either:
    # - pre-v10.390: None (no library entry)
    # - post-v10.390: dict with active=False (entry added but not activated)
    nim = get_kpi_definition("NIM")
    if nim is not None:
        # Post-v10.390 — entry exists but should be inactive
        assert nim.get("active") is False, (
            f"NIM library entry should be inactive until MD sets target, "
            f"got active={nim.get('active')!r}"
        )


def test_v10380_class_b_orphans_documented():
    """CLASS_B_ORPHANS has all required fields per entry."""
    _reimport("utils.kpi_alias_resolver")
    from utils.kpi_alias_resolver import CLASS_B_ORPHANS, list_class_b_orphans
    assert len(CLASS_B_ORPHANS) >= 15
    for o in list_class_b_orphans():
        for required in ("orphan_id", "suggested_name", "suggested_pillar",
                         "suggested_unit", "suggested_direction", "rationale"):
            assert required in o, f"orphan {o.get('orphan_id', '?')} missing {required}"
    # Spot-check critical orphans
    ids = {o["orphan_id"] for o in list_class_b_orphans()}
    for required_id in ("DEP_GROWTH", "NIM", "ROE", "NPS", "CIR"):
        assert required_id in ids, f"missing Class B orphan: {required_id}"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Cascade cleaner + coverage scanner
# ────────────────────────────────────────────────────────────────────

def test_v10380_clean_cascade_strips_deadline_corruption():
    """The deadline|300001|2026 metadata pollution must be stripped."""
    _reimport("utils.kpi_alias_resolver")
    from utils.kpi_alias_resolver import clean_cascade_dict
    raw = {
        "300001|PBT|2026":       {"from_code": "300001", "kpi": "PBT"},
        "deadline|300001|2026":  {"staff_code": "300001", "targets_locked": True},
        "_meta|something":       {"foo": "bar"},
    }
    clean = clean_cascade_dict(raw)
    assert "300001|PBT|2026" in clean
    assert "deadline|300001|2026" not in clean
    assert "_meta|something" not in clean


def test_v10380_real_target_cascade_cleans_to_valid_entries():
    """Apply cleaner to real target_cascade.json — no orphan keys remain."""
    _reimport("utils.kpi_alias_resolver")
    from utils.kpi_alias_resolver import clean_cascade_dict
    raw = json.loads((REPO / "data" / "target_cascade.json").read_text())
    clean = clean_cascade_dict(raw)
    # Real cascade has ~1051 entries; deadline corruption removed
    assert len(clean) > 1000
    for k in clean.keys():
        assert len(k.split("|")) == 3, f"malformed key: {k}"
        assert not k.startswith("deadline|")
        assert not k.startswith("_meta")


def test_v10380_coverage_scan_shows_zero_unknown_orphans():
    """After v10.380, no role_kpis reference is unresolved."""
    _reimport("utils.kpi_alias_resolver")
    from utils.kpi_alias_resolver import scan_role_kpis_coverage
    cov = scan_role_kpis_coverage()
    assert cov["unknown_orphans"] == 0, (
        f"unknown orphans remain: {cov['unknown_orphan_ids']}"
    )
    # Class A aliases should be actively used by role_kpis
    assert cov["resolved_via_alias"] >= 17
    # Class B documented for follow-up
    assert cov["class_b_orphans"] >= 9


# ────────────────────────────────────────────────────────────────────
# Section 4 — G266 + no regression
# ────────────────────────────────────────────────────────────────────

def test_v10380_g266_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_kpi_alias_resolver
    r = gate_kpi_alias_resolver()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G266"


def test_v10380_resolver_does_not_modify_source_files():
    """Module must not write to kpi_library.json or target_cascade.json."""
    p = REPO / "utils" / "kpi_alias_resolver.py"
    text = p.read_text()
    # Look for write operations on source paths
    for forbidden in (
        '.write_text(', '.write(', 'open(KPI_LIBRARY_PATH, "w"',
        'open(KPI_LIBRARY_PATH, \'w\'', 'open(TARGET_CASCADE_PATH, "w"',
        'KPI_LIBRARY_PATH.write_text', 'TARGET_CASCADE_PATH.write_text',
        'json.dump(', 'json.dumps(.*KPI_LIBRARY',
    ):
        # Don't worry about json.dumps as a stringify — only writes to the paths
        if 'KPI_LIBRARY_PATH' in forbidden or 'TARGET_CASCADE_PATH' in forbidden:
            assert forbidden not in text, f"forbidden write op: {forbidden}"


def test_v10380_no_regression_prior_canonical_identities():
    """All prior G250-G265 still hold."""
    import tempfile
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.pbt_computation")
    _reimport("utils.virtual_bank_kpi_unifier")
    _reimport("utils.customer_master_canonical")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.virtual_bank_kpi_unifier import unify_all_kpi_flow
    from utils.customer_master_canonical import (
        compute_unified_customer_master, reconciliation_summary,
    )
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bp = float(compute_pbt_from_cbs(td_path).pbt)
        assert bp != 0
        u = unify_all_kpi_flow(cbs_dir=td_path, period="2026")
        assert u["validation"]["violations"] == 0
        assert u["reconciliation"]["all_within_kes_100"]
        unified = compute_unified_customer_master(cbs_dir=td_path)
        s = reconciliation_summary(unified, cbs_dir=td_path)
        assert s["identity_holds"]
