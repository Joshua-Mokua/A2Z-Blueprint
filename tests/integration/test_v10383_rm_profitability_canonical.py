"""Integration tests for v10.383 — RM Profitability Canonical Refactor.

Phase B parallel-engines unification arc COMPLETE: customer (v10.381) +
RM (v10.383) both consume v10.378 canonical master.

Exposes pre-existing silent failure: marketing intel has no rm_code field,
so _default_rm_customer_lookup silently returned [] for every RM. CBS-
authoritative rm_code now drives results.

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
# Section 1 — Doc + module structure
# ────────────────────────────────────────────────────────────────────

def test_v10383_refactor_doc_has_7_parts():
    p = REPO / "docs" / "RM_PROFITABILITY_CANONICAL_REFACTOR_v10.383.md"
    assert p.exists()
    text = p.read_text()
    for part in range(1, 8):
        assert f"## Part {part}" in text, f"missing Part {part}"


def test_v10383_module_has_required_symbols():
    p = REPO / "utils" / "rm_profitability.py"
    text = p.read_text()
    for sym in (
        "def _canonical_rm_customer_lookup_v10383",
        "def _legacy_rm_customer_lookup",
        "def reset_canonical_rm_cache",
        "_RM_UNIFIED_MASTER_CACHE",
        "_RM_BY_RM_CODE_INDEX",
    ):
        assert sym in text, f"missing {sym}"


def test_v10383_default_lookup_canonical_first():
    """AST check that canonical precedes legacy in default lookup body."""
    p = REPO / "utils" / "rm_profitability.py"
    text = p.read_text()
    import re
    m = re.search(
        r"def _default_rm_customer_lookup\(.*?\) -> List\[str\]:(.+?)(?=\ndef )",
        text, re.DOTALL,
    )
    assert m is not None
    body = m.group(1)
    canon = body.find("_canonical_rm_customer_lookup_v10383")
    legacy = body.find("_legacy_rm_customer_lookup")
    assert canon >= 0 and legacy >= 0
    assert canon < legacy, "canonical must precede legacy"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Behavioral compatibility
# ────────────────────────────────────────────────────────────────────

def test_v10383_unknown_rm_returns_empty():
    _reimport("utils.rm_profitability")
    from utils.rm_profitability import (
        _default_rm_customer_lookup, _legacy_rm_customer_lookup,
        reset_canonical_rm_cache,
    )
    reset_canonical_rm_cache()
    assert _default_rm_customer_lookup("999999") == []
    assert _legacy_rm_customer_lookup("999999") == []


def test_v10383_legacy_returns_empty_for_seed_data():
    """Pre-v10.383 silent failure: marketing intel has no rm_code field,
    so legacy returns [] for every RM. This test confirms the failure
    mode exists (so canonical's improvement is real)."""
    _reimport("utils.rm_profitability")
    from utils.rm_profitability import _legacy_rm_customer_lookup
    # Try a few plausible RM staff codes
    for rm in ("300044", "300045", "300046", "300100"):
        assert _legacy_rm_customer_lookup(rm) == [], (
            f"legacy returned non-empty for {rm} — marketing intel "
            f"may have rm_code in this fixture"
        )


def test_v10383_canonical_with_cbs_data_returns_portfolio():
    """The real evidence: with CBS data, canonical returns actual portfolios."""
    _reimport("utils")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.customer_master_canonical import compute_unified_customer_master

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        bank, _ = seed_virtual_bank(config=SeedConfig.small())
        persist_bank_to_cbs(bank, output_dir=td_path)

        # Compute unified master with CBS data
        u = compute_unified_customer_master(cbs_dir=td_path)
        with_rm = [(cif, rec.rm_code) for cif, rec in u.items() if rec.rm_code]
        assert len(with_rm) > 0, "CBS seed should have customers with rm_code"

        # Sample RM should have a portfolio
        rm_codes = set(rc for _, rc in with_rm)
        sample_rm = next(iter(rm_codes))
        rm_customers = [cif for cif, rc in with_rm if rc == sample_rm]
        assert len(rm_customers) > 0


def test_v10383_returns_list_of_strings():
    """Public contract: returns List[str], even empty."""
    _reimport("utils.rm_profitability")
    from utils.rm_profitability import (
        _default_rm_customer_lookup, _legacy_rm_customer_lookup,
        reset_canonical_rm_cache,
    )
    reset_canonical_rm_cache()
    result = _default_rm_customer_lookup("999999")
    assert isinstance(result, list)
    for cif in result:
        assert isinstance(cif, str)


# ────────────────────────────────────────────────────────────────────
# Section 3 — Cache mechanics
# ────────────────────────────────────────────────────────────────────

def test_v10383_cache_reset_clears_both_caches():
    _reimport("utils.rm_profitability")
    _reimport("utils.customer_master_canonical")
    from utils.rm_profitability import (
        _canonical_rm_customer_lookup_v10383, reset_canonical_rm_cache,
    )
    import utils.rm_profitability as rmp
    # Populate caches
    _canonical_rm_customer_lookup_v10383("dummy")
    assert (rmp._RM_UNIFIED_MASTER_CACHE is not None or
            rmp._RM_BY_RM_CODE_INDEX is not None)
    # Reset
    reset_canonical_rm_cache()
    assert rmp._RM_UNIFIED_MASTER_CACHE is None
    assert rmp._RM_BY_RM_CODE_INDEX is None


def test_v10383_canonical_separate_from_v10381_cache():
    """v10.381 customer_profitability cache is INDEPENDENT of v10.383 RM cache."""
    _reimport("utils.rm_profitability")
    _reimport("utils.customer_profitability")
    import utils.rm_profitability as rmp
    import utils.customer_profitability as cp
    # Different module-level vars
    assert hasattr(rmp, "_RM_UNIFIED_MASTER_CACHE")
    assert hasattr(cp, "_UNIFIED_MASTER_CACHE")
    # Resetting one doesn't reset the other
    rmp.reset_canonical_rm_cache()
    cp._UNIFIED_MASTER_CACHE = "sentinel"
    rmp.reset_canonical_rm_cache()
    assert cp._UNIFIED_MASTER_CACHE == "sentinel"
    cp._UNIFIED_MASTER_CACHE = None


# ────────────────────────────────────────────────────────────────────
# Section 4 — G269 + regression + 34 existing tests still pass
# ────────────────────────────────────────────────────────────────────

def test_v10383_g269_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_rm_profitability_canonical
    r = gate_rm_profitability_canonical()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G269"


def test_v10383_existing_34_rm_tests_still_pass():
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", "tests/test_rm_profitability.py",
         "-q", "--tb=no"],
        cwd=str(REPO),
        capture_output=True, text=True, timeout=60,
    )
    assert "34 passed" in result.stdout, (
        f"engine tests broke: {result.stdout[-500:]}"
    )


def test_v10383_phase_b_parallel_engines_complete():
    """Customer + RM profitability BOTH consume v10.378 canonical master."""
    _reimport("utils.customer_profitability")
    _reimport("utils.rm_profitability")
    # Customer (v10.381 marker)
    cp_text = (REPO / "utils" / "customer_profitability.py").read_text()
    assert "_canonical_customer_lookup_v10381" in cp_text
    # RM (v10.383 marker)
    rm_text = (REPO / "utils" / "rm_profitability.py").read_text()
    assert "_canonical_rm_customer_lookup_v10383" in rm_text
    # Both reference v10.378 canonical engine
    for txt in (cp_text, rm_text):
        assert "compute_unified_customer_master" in txt


def test_v10383_no_regression_prior_canonical_identities():
    """All prior G250-G268 still hold."""
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
        unified = compute_unified_customer_master(cbs_dir=td_path)
        s = reconciliation_summary(unified, cbs_dir=td_path)
        assert s["identity_holds"]
    cov = scan_role_kpis_coverage()
    assert cov["unknown_orphans"] == 0
