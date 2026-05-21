"""Integration tests for v10.360 — Branch single source of truth.

Joshua's ask: "with our initial tests we had more branches and structure
i guess there are two sets of bank data that we needed to determine
which rich for our use. then if possible discard one set so that we
have 1 maintained even for future uses when testing"

The two sources:
- utils.core.BRANCH_REGION — hardcoded 21-entry dict (legacy)
- data/org_config.json::branches[] — 94-entry rich list (canonical)

v10.360 unifies on org_config. BRANCH_REGION + ECOBANK_BRANCHES are
now dynamically derived. G246 audit gate locks the unification.

11 tests across 4 sections:
  Section 1 — Source migration (3 tests)
  Section 2 — Runtime behaviour (4 tests)
  Section 3 — Backwards compatibility (2 tests)
  Section 4 — G246 gate (2 tests)
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
# Section 1 — Source migration
# ────────────────────────────────────────────────────────────────────

def test_v10360_core_branch_region_is_dynamic():
    """utils/core.py no longer has a 21-entry static dict literal."""
    core_text = (REPO / "utils" / "core.py").read_text()
    assert "_build_branch_region_from_org_config" in core_text, (
        "Missing _build_branch_region_from_org_config helper"
    )
    assert "BRANCH_REGION: dict = _build_branch_region_from_org_config()" in core_text, (
        "BRANCH_REGION must be assigned from the dynamic builder"
    )


def test_v10360_seed_module_reads_org_config():
    """utils/virtual_bank_seed.py reads from org_config, not a static list."""
    seed_text = (REPO / "utils" / "virtual_bank_seed.py").read_text()
    assert "def get_ecobank_branches" in seed_text
    assert "org_config.json" in seed_text


def test_v10360_org_config_has_branches():
    """The canonical source — data/org_config.json — has branches."""
    org = json.loads((REPO / "data" / "org_config.json").read_text())
    branches = org.get("branches", [])
    assert len(branches) >= 21, (
        f"org_config has only {len(branches)} branches (expected ≥21)"
    )
    # Required fields per the schema
    for b in branches[:5]:
        assert "name" in b
        assert "region" in b


# ────────────────────────────────────────────────────────────────────
# Section 2 — Runtime behaviour
# ────────────────────────────────────────────────────────────────────

def test_v10360_get_ecobank_branches_returns_org_config():
    _reimport("utils.virtual_bank_seed")
    from utils.virtual_bank_seed import get_ecobank_branches
    branches = get_ecobank_branches()
    # Should match org_config active count
    org = json.loads((REPO / "data" / "org_config.json").read_text())
    expected_count = len([
        b for b in org["branches"]
        if b.get("active", True) and b.get("name")
    ])
    assert len(branches) == expected_count


def test_v10360_ecobank_branches_module_constant_populated():
    _reimport("utils.virtual_bank_seed")
    from utils.virtual_bank_seed import ECOBANK_BRANCHES
    assert isinstance(ECOBANK_BRANCHES, dict)
    assert len(ECOBANK_BRANCHES) >= 21


def test_v10360_regions_match_org_config():
    """Regions in get_ecobank_branches must match org_config's region set."""
    _reimport("utils.virtual_bank_seed")
    from utils.virtual_bank_seed import get_ecobank_branches
    branches = get_ecobank_branches()
    regions = set(branches.values())

    org = json.loads((REPO / "data" / "org_config.json").read_text())
    expected_regions = {
        b.get("region", "Other")
        for b in org["branches"]
        if b.get("active", True)
    }
    assert regions == expected_regions, (
        f"Region mismatch: got {regions}, expected {expected_regions}"
    )


def test_v10360_seeder_uses_all_branches_by_default():
    """SeedConfig.n_branches=0 means 'use all available branches'."""
    _reimport("utils.virtual_bank_seed")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig, ECOBANK_BRANCHES
    bank, result = seed_virtual_bank(config=SeedConfig.small())
    assert result.n_branches == len(ECOBANK_BRANCHES), (
        f"Seeder produced {result.n_branches} branches; "
        f"ECOBANK_BRANCHES has {len(ECOBANK_BRANCHES)}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 3 — Backwards compatibility
# ────────────────────────────────────────────────────────────────────

def test_v10361_no_hardcoded_fallback():
    """v10.361 — per Rule N1, the seed module must NOT carry a hardcoded
    fallback branch list. Missing config returns empty dict instead."""
    seed_text = (REPO / "utils" / "virtual_bank_seed.py").read_text()
    import re
    # No _FALLBACK_BRANCHES assignment permitted
    assert not re.search(
        r"^_FALLBACK_BRANCHES\s*[:=]\s*(?:Dict\[[^\]]+\]\s*)?=",
        seed_text, re.MULTILINE
    ), "v10.361: _FALLBACK_BRANCHES assignment must be deleted"
    # And utils/core.py too
    core_text = (REPO / "utils" / "core.py").read_text()
    assert not re.search(
        r"^_BRANCH_REGION_FALLBACK\s*[:=]\s*(?:dict\s*)?=",
        core_text, re.MULTILINE
    ), "v10.361: _BRANCH_REGION_FALLBACK assignment must be deleted"


def test_v10360_seeder_self_test_passes():
    """v10.358 self_test still passes under v10.360 dynamic branch count."""
    _reimport("utils.virtual_bank_seed")
    from utils.virtual_bank_seed import self_test
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        self_test()
    assert "self-test passed" in buf.getvalue()


# ────────────────────────────────────────────────────────────────────
# Section 4 — G246 audit gate
# ────────────────────────────────────────────────────────────────────

def test_v10360_g246_gate_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_branch_single_source
    result = gate_branch_single_source()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G246"


def test_v10360_g246_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G246", gate_branch_single_source)' in text
