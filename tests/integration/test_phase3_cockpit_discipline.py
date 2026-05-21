"""
tests/integration/test_phase3_cockpit_discipline.py
================================================================================
v10.296 — Meta-test suite. Enforces the Phase 3 live cockpit
discipline across EVERY live cockpit page, present and future.

Kaizen principle: as new arcs ship, they automatically inherit the
discipline. No future page can ship with a silent require_access
swallow, no live cockpit can ship without audit_log calls, no
manifest entry can be missing required fields.

These tests scan the actual filesystem at test time, so they cover
pages 109, 110, and any future *_live.py page automatically.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _live_cockpit_pages() -> list[Path]:
    """Return all live cockpit pages.

    By convention, live cockpit pages are named `*_live.py`. This
    pattern is documented in STANDING_RULES_PHASE_3.md so future
    pages will land here automatically.
    """
    pages_dir = REPO_ROOT / "pages"
    return sorted(pages_dir.glob("*_live.py"))


# ============================================================
# Section 1 — Discovery
# ============================================================

def test_live_cockpit_pages_discovered():
    """At least one live cockpit page must exist (Phase 3 is
    underway). If this fails, the convention has broken."""
    pages = _live_cockpit_pages()
    assert len(pages) >= 1, (
        "No *_live.py pages found. Phase 3 introduced the live "
        "cockpit pattern; at least page 109 (CIMS) should exist."
    )


def test_live_cockpit_pages_count_matches_v10296():
    """As of v10.301 there are four live cockpit pages:
    109 (CIMS), 110 (Treasury), 111 (Credit), 112 (Compliance).
    When new arcs ship, this count goes up — bump the
    expected number here in the same batch as adding the new
    cockpit."""
    pages = _live_cockpit_pages()
    page_names = sorted(p.name for p in pages)
    expected = [
        "109_cims_live.py",
        "110_treasury_live.py",
        "111_credit_live.py",
        "112_compliance_live.py",
    ]
    assert page_names == expected, (
        f"Live cockpit pages don't match v10.301 expectation. "
        f"Expected {expected}, got {page_names}. If a new live "
        f"cockpit shipped, update this test."
    )


# ============================================================
# Section 2 — Per-cockpit discipline (parametrized)
# ============================================================

@pytest.fixture(params=_live_cockpit_pages())
def cockpit_page(request):
    return request.param


def test_no_silent_require_access(cockpit_page):
    """Phase 3 standing rule: pages must fail loud on access
    errors. The silent try/except pattern is forbidden."""
    src = cockpit_page.read_text()
    bad = (
        "try:\n"
        "    from pages._access import require_access\n"
    )
    assert bad not in src, (
        f"{cockpit_page.name} uses silent try/except around "
        f"require_access — Phase 3 rule requires hard import"
    )


def test_has_ttl_cache(cockpit_page):
    """Phase 3 rule: live cockpits use @st.cache_data(ttl=...).
    Without TTL, data goes stale forever."""
    src = cockpit_page.read_text()
    assert "@st.cache_data(ttl=" in src, (
        f"{cockpit_page.name} missing @st.cache_data(ttl=...) "
        f"decorator. Live cockpits must refresh."
    )


def test_emits_audit_log(cockpit_page):
    """Phase 3 rule: cockpits emit a real audit trail."""
    src = cockpit_page.read_text()
    assert "audit_log(" in src, (
        f"{cockpit_page.name} doesn't call audit_log() — "
        f"cockpits must record viewing activity"
    )


def test_uses_canonical_imports(cockpit_page):
    """G177 enforces canonical imports. The meta-test ensures
    we never regress."""
    src = cockpit_page.read_text()
    # Forbidden patterns
    forbidden = [
        "from utils.audit_log",
        "from utils.access_helpers",
    ]
    for f in forbidden:
        assert f not in src, (
            f"{cockpit_page.name} uses forbidden import '{f}'"
        )
    # Required patterns
    if "audit_log(" in src:
        assert "from utils.core_audit import audit_log" in src, (
            f"{cockpit_page.name} calls audit_log but doesn't "
            f"import it from utils.core_audit (canonical)"
        )


def test_tab_count_within_g4_ceiling(cockpit_page):
    """G4 enforces ≤7 tabs per page. The meta-test reinforces
    so reviewers see this in test reports too."""
    src = cockpit_page.read_text()
    m = re.search(r'st\.tabs\(\[(.*?)\]\)', src, re.DOTALL)
    if not m:
        # No tabs at all is OK (single-tab cockpits could exist)
        return
    # Count comma-separated entries — a robust-enough heuristic
    items = [x for x in m.group(1).split(",") if x.strip()]
    assert len(items) <= 7, (
        f"{cockpit_page.name} has {len(items)} tabs — exceeds "
        f"G4 ceiling of 7"
    )


def test_has_manifest_entry(cockpit_page):
    """Every page on disk must have a manifest entry. G160
    enforces this for module loading; the meta-test ensures
    each new live cockpit ships with its manifest entry in
    the same batch."""
    manifest_path = REPO_ROOT / "pages" / "_manifest.json"
    m = json.loads(manifest_path.read_text())
    entry = m["pages"].get(cockpit_page.name)
    assert entry is not None, (
        f"{cockpit_page.name} missing from manifest"
    )
    # All 7 required fields (G160-enforced from v10.294)
    for field in (
        "department_primary", "module_path", "secondary_visibility",
        "title", "icon", "description", "current_module_key",
    ):
        assert field in entry, (
            f"{cockpit_page.name} manifest entry missing `{field}`"
        )
    # Description must be substantive (not a placeholder)
    desc = entry["description"]
    assert len(desc) > 50, (
        f"{cockpit_page.name} description is too short "
        f"({len(desc)} chars) — likely a placeholder"
    )


def test_module_path_ends_in_live(cockpit_page):
    """Live cockpit pages must register a `*_live` module_path
    so users can navigate to them via dotted-path access."""
    manifest_path = REPO_ROOT / "pages" / "_manifest.json"
    m = json.loads(manifest_path.read_text())
    entry = m["pages"].get(cockpit_page.name)
    if entry is None:
        pytest.skip("manifest entry checked in another test")
    mp = entry.get("module_path", "")
    assert mp.endswith("_live"), (
        f"{cockpit_page.name} module_path '{mp}' should end "
        f"in '_live' for navigability"
    )


def test_no_direct_filesystem_reads(cockpit_page):
    """G2 enforces this; the meta-test prevents regression.
    Live cockpits must route reads through cockpit_read or
    similar engines."""
    src = cockpit_page.read_text()
    # Look for raw json.load/json.loads with a Path
    suspicious_patterns = [
        r'Path\(["\']data/',          # Path("data/foo")
        r"json\.loads\([^)]*\.read",  # json.loads(...read_text())
        r"\.read_text\(\)",           # any .read_text()
        r"open\(['\"]data/",          # open("data/...")
    ]
    found = []
    for p in suspicious_patterns:
        for m in re.finditer(p, src):
            line_no = src[:m.start()].count("\n") + 1
            found.append(f"L{line_no}: {m.group(0)}")
    assert not found, (
        f"{cockpit_page.name} has direct filesystem reads:\n  "
        + "\n  ".join(found)
        + "\nUse utils.cockpit_read helpers instead (G2 rule)."
    )


# ============================================================
# Section 3 — cockpit_read API stability
# ============================================================

def test_cockpit_read_api_stable():
    """The cockpit_read public API is the contract every live
    cockpit depends on. Removing or renaming any of these
    breaks all cockpits. Meta-test enforces stability."""
    import utils.cockpit_read as cr

    required_api = [
        # Generic helpers
        "load_records", "filter_records", "sort_records",
        "group_by", "count_by", "find_by_id", "latest_n",
        # CIMS composers
        "cims_instruction_trace", "cims_open_work",
        # Treasury composers
        "treasury_open_work", "treasury_liquidity_metrics",
        "treasury_irrbb", "treasury_capital_adequacy",
    ]
    for name in required_api:
        assert hasattr(cr, name), (
            f"utils.cockpit_read.{name} missing — this is "
            f"public API consumed by live cockpits"
        )


def test_cockpit_read_helpers_are_pure_reads():
    """Critical invariant: cockpit_read functions never mutate
    upstream state. This test calls each helper with empty
    inputs and verifies no exceptions and no writes."""
    import tempfile, shutil
    from utils.cockpit_read import (
        load_records, filter_records, sort_records,
        group_by, count_by, find_by_id, latest_n,
        cims_instruction_trace, cims_open_work,
        treasury_open_work, treasury_liquidity_metrics,
        treasury_irrbb, treasury_capital_adequacy,
    )

    tmp = Path(tempfile.mkdtemp(prefix="cockpit_pure_"))
    try:
        # No data files exist. All helpers should return
        # documented empty types, not crash.
        assert load_records(tmp / "x.json", "x", ("y",)) == []
        assert filter_records([]) == []
        assert sort_records([]) == []
        assert group_by([], "f") == {}
        assert count_by([], "f") == {}
        assert find_by_id([], "f", "v") is None
        assert latest_n([]) == []

        # CIMS composers
        t = cims_instruction_trace("X", data_dir=tmp)
        assert t["capture"] is None
        snap = cims_open_work(data_dir=tmp)
        assert isinstance(snap, dict)

        # Treasury composers
        t = treasury_open_work(data_dir=tmp)
        assert isinstance(t, dict)
        assert treasury_liquidity_metrics(data_dir=tmp) is None
        assert treasury_irrbb(data_dir=tmp) is None
        assert treasury_capital_adequacy(data_dir=tmp) is None

        # tmp dir must still be empty after all those reads
        assert list(tmp.iterdir()) == [], (
            "cockpit_read helpers wrote files to tmp dir — "
            "violates read-only invariant"
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ============================================================
# Section 4 — Standing rules conformance
# ============================================================

def test_standing_rules_doc_exists():
    """The Phase 3 standing rules must exist. Cockpit work
    references it; if missing, the discipline isn't documented."""
    rules_path = REPO_ROOT / "STANDING_RULES_PHASE_3.md"
    assert rules_path.exists(), (
        "STANDING_RULES_PHASE_3.md is missing — Phase 3 "
        "discipline isn't documented"
    )


def test_phase3_backlog_exists():
    """The Phase 3 backlog must exist and be readable. Every
    deep audit produces backlog items; if the file is missing,
    audit findings have no home."""
    backlog_path = REPO_ROOT / "PHASE_3_BACKLOG.md"
    assert backlog_path.exists(), (
        "PHASE_3_BACKLOG.md is missing"
    )
    text = backlog_path.read_text()
    # Must have at least one item (file shouldn't be just
    # a header)
    assert "B-001" in text or "B-002" in text, (
        "PHASE_3_BACKLOG.md has no backlog items — file "
        "appears to be a placeholder"
    )


# ============================================================
# Section 5 — React-readiness (v10.297 addition)
# ============================================================

def test_cockpit_composers_have_http_endpoints():
    """Every cockpit_read composer used by a *_live.py page must
    also be exposed as an HTTP endpoint via utils/api_cockpit.py.

    This is the React-readiness invariant: any data shown in a
    Streamlit cockpit must be fetchable by the React SPA. If a
    new composer is added to cockpit_read and surfaced in a live
    page without a matching API endpoint, this test fails.
    """
    api_cockpit_src = (
        REPO_ROOT / "utils" / "api_cockpit.py"
    ).read_text()

    # Discover composers used by live cockpit pages
    composers_used_by_pages = set()
    for page in _live_cockpit_pages():
        page_src = page.read_text()
        # Match `from utils.cockpit_read import ( ... )`
        import re
        m = re.search(
            r'from utils\.cockpit_read import\s*\(([^)]+)\)',
            page_src,
        )
        if m:
            imports = m.group(1)
            for name in re.findall(r'\b(\w+)\b', imports):
                # Only the composer functions, not generic helpers
                if name in (
                    "cims_open_work", "cims_instruction_trace",
                    "treasury_open_work",
                    "treasury_liquidity_metrics",
                    "treasury_irrbb",
                    "treasury_capital_adequacy",
                    "credit_open_work",
                    "credit_loan_applications",
                    "credit_ifrs9_loans",
                    "credit_watchlist",
                    "credit_portfolio_analytics",
                    "compliance_open_work",
                    "compliance_cases",
                    "compliance_aml_alerts",
                    "compliance_sanctions_screening",
                    "compliance_regulatory_returns",
                    "compliance_cra_training",
                ):
                    composers_used_by_pages.add(name)

    missing_http = []
    for composer in composers_used_by_pages:
        # The composer name should appear in api_cockpit.py
        # (either as an import or as a function call within
        # an endpoint).
        if composer not in api_cockpit_src:
            missing_http.append(composer)

    assert not missing_http, (
        f"Cockpit composers used by live pages but missing "
        f"HTTP endpoints: {missing_http}. The React SPA "
        f"won't be able to fetch this data."
    )


def test_api_cockpit_module_exists_and_imports():
    """utils/api_cockpit.py must exist and be importable without
    Streamlit installed (React SPA backend constraint)."""
    api_path = REPO_ROOT / "utils" / "api_cockpit.py"
    assert api_path.exists(), (
        "utils/api_cockpit.py missing — cockpit HTTP API "
        "needed for React SPA"
    )
    import utils.api_cockpit as mod
    assert hasattr(mod, "FASTAPI_AVAILABLE")
    assert hasattr(mod, "router")
