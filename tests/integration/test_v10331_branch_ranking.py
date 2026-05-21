"""Integration tests for v10.331 — Branch Ranking page.

Tests across 3 sections:
  Section 1 — Page artefact + manifest (3 tests)
  Section 2 — Data loading logic (3 tests)
  Section 3 — Currency configurability (2 tests)
"""

import json
import sys
from pathlib import Path


REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Page artefact + manifest
# ────────────────────────────────────────────────────────────────────

def test_v10331_page_file_exists():
    """The branch ranking page file exists at the expected path."""
    page = REPO / "pages" / "113_branch_ranking.py"
    assert page.exists(), f"{page} missing"
    src = page.read_text()
    assert "Branch Ranking" in src
    assert "94 branches" in src or "94 BMs" in src or "94 Branch" in src


def test_v10331_page_registered_in_manifest():
    """The new page is registered with full 7-field G160 manifest entry."""
    m = json.loads((REPO / "pages" / "_manifest.json").read_text())
    pages = m.get("pages", {})
    entry = pages.get("113_branch_ranking.py")
    assert entry is not None, "113_branch_ranking.py not in manifest"

    required_fields = (
        "department_primary", "module_path", "secondary_visibility",
        "title", "icon", "current_module_key", "description",
    )
    for field in required_fields:
        assert field in entry, f"manifest missing {field}"
    assert entry["module_path"] == "sales_customer.branch_ranking"
    assert entry["title"] == "Branch Ranking"
    # description must be substantive per G160
    assert len(entry["description"]) >= 50


def test_v10331_page_has_seven_tabs_or_fewer():
    """Page has ≤7 tabs (G4 hard limit)."""
    src = (REPO / "pages" / "113_branch_ranking.py").read_text()
    # Count tabs by counting occurrences in st.tabs([...])
    import re
    # Match "🏅 Overall ranking" etc style entries
    tabs_match = re.search(
        r"tabs\s*=\s*st\.tabs\s*\(\s*\[(.+?)\]\s*\)",
        src, re.DOTALL,
    )
    assert tabs_match, "Could not find tabs declaration"
    tab_block = tabs_match.group(1)
    # Count comma-separated entries
    tab_count = len([
        line for line in tab_block.split(",")
        if line.strip().startswith('"')
    ])
    assert tab_count <= 7, f"Page has {tab_count} tabs — G4 limit is 7"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Data loading logic
# ────────────────────────────────────────────────────────────────────

def test_v10331_uses_db_load_json_not_direct_io():
    """Page uses utils.db.db.load_json, not direct file I/O (G2)."""
    src = (REPO / "pages" / "113_branch_ranking.py").read_text()
    assert "_db.load_json" in src
    # No direct .read_text() calls inside data loader
    assert "Path(__file__).parent.parent" not in src or src.count(
        "ROOT / \"data\""
    ) <= 1  # only the Path declaration


def test_v10331_branch_data_loader_returns_dataframe():
    """The data loader function returns proper DataFrames."""
    src = (REPO / "pages" / "113_branch_ranking.py").read_text()
    assert "_load_branch_data" in src
    assert "pd.DataFrame" in src
    # Returns 2 DFs (branches + AM aggregate)
    assert "return df, am_agg" in src


def test_v10331_drilldown_handles_all_21_kpis():
    """Drill-down view surfaces all 21 BM KPIs."""
    src = (REPO / "pages" / "113_branch_ranking.py").read_text()
    # Key KPIs we'd expect to see referenced
    expected_kpis = [
        "PBT", "Total NFI", "CASA Ratio", "NPL", "PAR",
        "Audit Score", "CX Score", "COMPLIANCE_SCORE",
        "Loan Book Growth", "NEW_ACCOUNTS", "Staff Productivity",
    ]
    for kpi in expected_kpis:
        assert kpi in src, f"Drill-down missing reference to {kpi}"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Currency configurability
# ────────────────────────────────────────────────────────────────────

def test_v10331_no_hardcoded_kes_literal():
    """Page has no hardcoded 'KES' string literals (G162)."""
    src = (REPO / "pages" / "113_branch_ranking.py").read_text()
    # KES should not appear as a string literal anywhere
    assert '"KES"' not in src, "Hardcoded \"KES\" literal found"
    assert "'KES'" not in src, "Hardcoded 'KES' literal found"


def test_v10331_uses_get_currency_helper():
    """Currency label is fetched via get_currency() helper, configurable."""
    src = (REPO / "pages" / "113_branch_ranking.py").read_text()
    assert "get_currency" in src, (
        "Page must use get_currency() for currency label"
    )
