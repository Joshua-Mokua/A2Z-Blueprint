"""Integration tests for v10.381 — Customer Profitability → Canonical Refactor.

Per Phase B roadmap: customer_profitability.py now consumes v10.378
unified customer master via _canonical_customer_lookup_v10381, with
_legacy_customer_intelligence_lookup as fallback. Public API unchanged;
all 42 existing engine tests pass.

12 tests across 4 sections.
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
# Section 1 — Docs present
# ────────────────────────────────────────────────────────────────────

def test_v10381_refactor_doc_has_7_parts():
    p = REPO / "docs" / "CUSTOMER_PROFITABILITY_CANONICAL_REFACTOR_v10.381.md"
    assert p.exists()
    text = p.read_text()
    for part in (
        "## Part 1 — Why this matters",
        "## Part 2 — Why the refactor is small",
        "## Part 3 — Module changes",
        "## Part 4 — Field compatibility",
        "## Part 5 — Verified compatibility",
        "## Part 6 — What v10.381 deliberately does NOT do",
        "## Part 7 — Honest acknowledgement",
    ):
        assert part in text, f"missing: {part}"


def test_v10381_recommendations_doc_has_all_8_decisions():
    p = REPO / "docs" / "V10380_DECISIONS_RECOMMENDATIONS_v10.381.md"
    assert p.exists()
    assert p.stat().st_size > 8000, "recommendations doc too small"
    text = p.read_text()
    for d in range(1, 9):
        assert f"## Decision {d}" in text, f"missing Decision {d}"
    # Body-system framing applied
    assert "body" in text.lower()
    assert "donella meadows" in text.lower() or "Donella Meadows" in text
    assert "flow principle" in text.lower() or "Flow Principle" in text


# ────────────────────────────────────────────────────────────────────
# Section 2 — Module structure
# ────────────────────────────────────────────────────────────────────

def test_v10381_module_has_required_symbols():
    p = REPO / "utils" / "customer_profitability.py"
    text = p.read_text()
    for sym in (
        "def _canonical_customer_lookup_v10381",
        "def _legacy_customer_intelligence_lookup",
        "def reset_canonical_customer_cache",
        "_UNIFIED_MASTER_CACHE",
    ):
        assert sym in text, f"missing {sym}"


def test_v10381_default_lookup_calls_canonical_first():
    """The default lookup body must invoke canonical before legacy."""
    p = REPO / "utils" / "customer_profitability.py"
    text = p.read_text()
    # Find _default_customer_lookup definition (the public one — first occurrence)
    import re
    m = re.search(
        r"def _default_customer_lookup\(.*?\) -> Optional\[dict\]:(.+?)(?=\ndef )",
        text, re.DOTALL,
    )
    assert m is not None, "_default_customer_lookup not found"
    body = m.group(1)
    # Canonical call must precede legacy call
    canonical_pos = body.find("_canonical_customer_lookup_v10381")
    legacy_pos = body.find("_legacy_customer_intelligence_lookup")
    assert canonical_pos >= 0, "canonical lookup not called from default"
    assert legacy_pos >= 0, "legacy fallback not called from default"
    assert canonical_pos < legacy_pos, (
        f"canonical must precede legacy in default lookup body; "
        f"got canonical@{canonical_pos} legacy@{legacy_pos}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 3 — Behavioral compatibility
# ────────────────────────────────────────────────────────────────────

def test_v10381_canonical_lookup_returns_segment():
    """Canonical lookup returns a dict with segment field for known CIFs."""
    _reimport("utils.customer_profitability")
    _reimport("utils.customer_master_canonical")
    from utils.customer_profitability import (
        _canonical_customer_lookup_v10381, reset_canonical_customer_cache,
    )
    reset_canonical_customer_cache()
    raw = json.loads((REPO / "data" / "customer_intelligence.json").read_text())
    real_cif = next(iter(raw.keys()))
    rec = _canonical_customer_lookup_v10381(real_cif)
    assert rec is not None
    assert "segment" in rec
    assert rec["segment"] is not None


def test_v10381_canonical_legacy_segment_matches():
    """Round-trip: segment from canonical matches segment from legacy."""
    _reimport("utils.customer_profitability")
    _reimport("utils.customer_master_canonical")
    from utils.customer_profitability import (
        _canonical_customer_lookup_v10381,
        _legacy_customer_intelligence_lookup,
        reset_canonical_customer_cache,
    )
    reset_canonical_customer_cache()
    raw = json.loads((REPO / "data" / "customer_intelligence.json").read_text())
    # Test multiple CIFs
    cifs = list(raw.keys())[:10]
    for cif in cifs:
        legacy = _legacy_customer_intelligence_lookup(cif)
        canonical = _canonical_customer_lookup_v10381(cif)
        assert legacy is not None, f"legacy missing for {cif}"
        assert canonical is not None, f"canonical missing for {cif}"
        assert legacy["segment"] == canonical["segment"], (
            f"segment mismatch for {cif}: "
            f"legacy={legacy['segment']!r} canonical={canonical['segment']!r}"
        )


def test_v10381_canonical_lookup_adds_provenance_fields():
    """Canonical lookup adds sources, enrichment_status, _field_lineage."""
    _reimport("utils.customer_profitability")
    _reimport("utils.customer_master_canonical")
    from utils.customer_profitability import (
        _canonical_customer_lookup_v10381, reset_canonical_customer_cache,
    )
    reset_canonical_customer_cache()
    raw = json.loads((REPO / "data" / "customer_intelligence.json").read_text())
    real_cif = next(iter(raw.keys()))
    rec = _canonical_customer_lookup_v10381(real_cif)
    assert "sources" in rec
    assert "enrichment_status" in rec
    assert "_field_lineage" in rec
    assert isinstance(rec["sources"], list)
    assert len(rec["_field_lineage"]) > 0


def test_v10381_unknown_customer_returns_none():
    _reimport("utils.customer_profitability")
    from utils.customer_profitability import (
        _canonical_customer_lookup_v10381,
        _legacy_customer_intelligence_lookup,
        _default_customer_lookup,
        reset_canonical_customer_cache,
    )
    reset_canonical_customer_cache()
    assert _canonical_customer_lookup_v10381("999999999") is None
    assert _legacy_customer_intelligence_lookup("999999999") is None
    assert _default_customer_lookup("999999999") is None


def test_v10381_cache_reset_clears_state():
    _reimport("utils.customer_profitability")
    _reimport("utils.customer_master_canonical")
    from utils.customer_profitability import (
        _canonical_customer_lookup_v10381, reset_canonical_customer_cache,
    )
    import utils.customer_profitability as cp
    raw = json.loads((REPO / "data" / "customer_intelligence.json").read_text())
    real_cif = next(iter(raw.keys()))
    # Populate cache
    _canonical_customer_lookup_v10381(real_cif)
    assert cp._UNIFIED_MASTER_CACHE is not None
    # Reset
    reset_canonical_customer_cache()
    assert cp._UNIFIED_MASTER_CACHE is None
    # Repopulate on next call
    _canonical_customer_lookup_v10381(real_cif)
    assert cp._UNIFIED_MASTER_CACHE is not None


# ────────────────────────────────────────────────────────────────────
# Section 4 — Engine integration + no regression
# ────────────────────────────────────────────────────────────────────

def test_v10381_default_lookup_uses_canonical_first():
    """The default returns canonical-shape (with sources field), not legacy-only."""
    _reimport("utils.customer_profitability")
    _reimport("utils.customer_master_canonical")
    from utils.customer_profitability import (
        _default_customer_lookup, reset_canonical_customer_cache,
    )
    reset_canonical_customer_cache()
    raw = json.loads((REPO / "data" / "customer_intelligence.json").read_text())
    real_cif = next(iter(raw.keys()))
    rec = _default_customer_lookup(real_cif)
    assert rec is not None
    # If canonical was used (vs legacy), 'sources' field should be present
    assert "sources" in rec, (
        "default lookup returned legacy shape; canonical-first may not be active"
    )


def test_v10381_g267_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_customer_profitability_canonical
    r = gate_customer_profitability_canonical()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G267"


def test_v10381_engine_42_existing_tests_still_pass():
    """All 42 existing customer_profitability tests pass with canonical lookup."""
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", "tests/test_customer_profitability.py",
         "-q", "--tb=no"],
        cwd=str(REPO),
        capture_output=True, text=True, timeout=60,
    )
    # Look for "42 passed" in output
    assert "42 passed" in result.stdout, (
        f"engine tests broke: {result.stdout[-500:]}"
    )


def test_v10381_no_regression_prior_canonical_identities():
    """Phase B canonical identities (G250-G266) still hold."""
    import tempfile
    _reimport("utils")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.virtual_bank_kpi_unifier import unify_all_kpi_flow
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
        u = unify_all_kpi_flow(cbs_dir=td_path, period="2026")
        assert u["validation"]["violations"] == 0
        assert u["reconciliation"]["all_within_kes_100"]
        unified = compute_unified_customer_master(cbs_dir=td_path)
        s = reconciliation_summary(unified, cbs_dir=td_path)
        assert s["identity_holds"]
    # v10.380 zero unknown orphans
    cov = scan_role_kpis_coverage()
    assert cov["unknown_orphans"] == 0
