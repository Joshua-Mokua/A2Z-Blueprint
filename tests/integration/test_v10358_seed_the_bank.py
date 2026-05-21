"""Integration tests for v10.358 — Seed-the-Bank Helper.

Closes the v10.357 readiness-audit blocker: empty VirtualBankCore meant
0 transactions generated in the boot probe. v10.358 adds a deterministic
seeder that populates the bank from data/users.json + ECOBANK_BRANCHES.

14 tests across 5 sections:
  Section 1 — Module + config (3 tests)
  Section 2 — Seeder mechanics (4 tests)
  Section 3 — Determinism (2 tests)
  Section 4 — Readiness audit integration (3 tests)
  Section 5 — G244 audit gate (2 tests)
"""

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
# Section 1 — Module + config
# ────────────────────────────────────────────────────────────────────

def test_v10358_module_present():
    path = REPO / "utils" / "virtual_bank_seed.py"
    assert path.exists()
    text = path.read_text()
    for sym in (
        "def seed_virtual_bank",
        "def format_seed_summary",
        "def self_test",
        "class SeedConfig",
        "class SeedResult",
        "ECOBANK_BRANCHES",
    ):
        assert sym in text, f"Missing: {sym}"


def test_v10358_ecobank_branches_has_21():
    """v10.360 update: ECOBANK_BRANCHES is now sourced from org_config.json
    (94 branches, the unified single source of truth). The legacy 21-entry
    hardcoded BRANCH_REGION was deprecated in favour of the richer
    org_config branches[] list. Test name kept for git history continuity.
    """
    _reimport("utils.virtual_bank_seed")
    from utils.virtual_bank_seed import ECOBANK_BRANCHES
    assert len(ECOBANK_BRANCHES) >= 21, (
        f"ECOBANK_BRANCHES has {len(ECOBANK_BRANCHES)} — must be ≥21 "
        f"(legacy minimum). Single source of truth is data/org_config.json."
    )
    # Smoke check: well-known branches still present. org_config uses
    # locality names (e.g. "Mombasa Kenyatta Avenue", "Westlands", "JKIA")
    # rather than "Branch"-suffixed names. Check by substring.
    all_names_lower = " ".join(ECOBANK_BRANCHES.keys()).lower()
    for keyword in ("mombasa", "westlands", "eldoret"):
        assert keyword in all_names_lower, (
            f"Expected {keyword!r} in some branch name; available: "
            f"{list(ECOBANK_BRANCHES.keys())[:10]}"
        )
    # Regions: must be ≥ 3 (legacy minimum); org_config has 7
    regions = set(ECOBANK_BRANCHES.values())
    assert len(regions) >= 3, f"Expected ≥3 regions, got {regions}"


def test_v10358_seed_configs_have_sensible_defaults():
    _reimport("utils.virtual_bank_seed")
    from utils.virtual_bank_seed import SeedConfig
    small = SeedConfig.small()
    medium = SeedConfig.medium()
    large = SeedConfig.large()
    # Small ≤ medium ≤ large
    assert small.n_customers <= medium.n_customers <= large.n_customers
    # Small is suitable for unit testing (≤500 customers)
    assert small.n_customers <= 500
    # Segment mix sums to ~1.0 in all configs
    for cfg in (small, medium, large):
        s = sum(cfg.segment_mix.values())
        assert abs(s - 1.0) < 0.01, f"{cfg.config_id} segment_mix sums to {s}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Seeder mechanics
# ────────────────────────────────────────────────────────────────────

def test_v10358_seed_returns_populated_bank():
    _reimport("utils.virtual_bank_seed")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig, ECOBANK_BRANCHES
    bank, result = seed_virtual_bank(config=SeedConfig.small())
    assert result.n_customers == 100
    # v10.360: n_branches now reflects ECOBANK_BRANCHES count (94 from
    # org_config or 5 from fallback); was hardcoded 21 pre-v10.360
    assert result.n_branches == len(ECOBANK_BRANCHES)
    assert result.n_accounts == 200
    assert result.n_loans == 30
    assert result.n_rms > 0
    assert result.total_deposits_kes > 0
    assert result.total_loans_kes > 0


def test_v10358_seed_self_test_passes():
    _reimport("utils.virtual_bank_seed")
    from utils.virtual_bank_seed import self_test
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        self_test()
    assert "self-test passed" in buf.getvalue()


def test_v10358_seed_uses_real_rm_codes_when_users_available():
    """If users.json exists with active RMs, the seeder pulls real codes."""
    _reimport("utils.virtual_bank_seed")
    from utils.virtual_bank_seed import _select_rms_from_users
    rms = _select_rms_from_users(rm_pool_size=10)
    # Either we got real staff codes (starting with 3) or synthetic fallbacks
    real = [r for r in rms if not r.startswith("RM_")]
    if (REPO / "data" / "users.json").exists():
        assert len(real) > 0, "users.json present but no real RMs returned"


def test_v10358_seed_referential_integrity():
    """Every account's CIF matches a customer; every loan's CIF too;
    every branch_code referenced by customers is a real seeded branch."""
    _reimport("utils.virtual_bank_seed")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    bank, result = seed_virtual_bank(config=SeedConfig.small())
    customer_cifs = {c.cif for c in bank.all_customers()}
    branch_codes = {b.branch_code for b in bank.all_branches()}
    # Accounts
    for a in bank.all_accounts():
        assert a.cif in customer_cifs, f"Orphan account: {a.account_no}"
        assert a.branch_code in branch_codes, f"Bad branch on account: {a.account_no}"
    # Loans
    for l in bank.all_loans():
        assert l.cif in customer_cifs, f"Orphan loan: {l.loan_id}"
        assert l.branch_code in branch_codes, f"Bad branch on loan: {l.loan_id}"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Determinism (same seed → same totals)
# ────────────────────────────────────────────────────────────────────

def test_v10358_determinism_same_seed():
    _reimport("utils.virtual_bank_seed")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    _, r1 = seed_virtual_bank(config=SeedConfig.small())
    _, r2 = seed_virtual_bank(config=SeedConfig.small())
    assert r1.total_deposits_kes == r2.total_deposits_kes
    assert r1.total_loans_kes == r2.total_loans_kes
    assert r1.n_accounts == r2.n_accounts


def test_v10358_different_seeds_differ():
    """Different base_seed → different totals (sanity, not strict)."""
    _reimport("utils.virtual_bank_seed")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    cfg1 = SeedConfig.small()
    cfg1.base_seed = "v10358_seed_A"
    cfg2 = SeedConfig.small()
    cfg2.base_seed = "v10358_seed_B"
    _, r1 = seed_virtual_bank(config=cfg1)
    _, r2 = seed_virtual_bank(config=cfg2)
    # At least one of (deposits, loans) should differ — full collision
    # would suggest the seed isn't actually feeding into the index.
    differs = (
        r1.total_deposits_kes != r2.total_deposits_kes
        or r1.total_loans_kes != r2.total_loans_kes
    )
    assert differs, "Different seeds produced identical totals — seed not propagating"


# ────────────────────────────────────────────────────────────────────
# Section 4 — Readiness audit integration
# ────────────────────────────────────────────────────────────────────

def test_v10358_readiness_boot_probe_generates_transactions():
    """With v10.358 seeding in place, the boot probe must generate
    transactions where v10.357 generated 0."""
    _reimport("utils.virtual_bank_readiness")
    from utils.virtual_bank_readiness import _probe_boot
    probe = _probe_boot()
    assert probe.error is None or "seed step failed" not in (probe.error or ""), (
        f"Seed step failed: {probe.error}"
    )
    assert probe.run_executed
    assert probe.final_customers > 0, (
        f"Expected seeded customers, got {probe.final_customers}"
    )
    # 5 days × ~100 customers should produce >100 transactions
    assert probe.final_transactions > 100, (
        f"Expected >100 txns from seeded bank, got {probe.final_transactions}"
    )


def test_v10358_readiness_no_longer_notes_empty_bank():
    """The v10.357 'empty bank' note should not appear when seeding works."""
    _reimport("utils.virtual_bank_readiness")
    from utils.virtual_bank_readiness import capture_readiness_report
    r = capture_readiness_report()
    empty_note = any("empty VirtualBankCore" in n for n in r.notes)
    assert not empty_note, f"Empty-bank note still present in: {r.notes}"


def test_v10358_readiness_g243_still_green():
    """G243 must still pass — v10.358 doesn't regress the readiness baseline."""
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    import audit as A
    fn = dict(A.GATES)["G243"]
    result = fn()
    assert result["passed"], f"G243 regressed: {result.get('violations')}"


# ────────────────────────────────────────────────────────────────────
# Section 5 — G244 audit gate
# ────────────────────────────────────────────────────────────────────

def test_v10358_g244_gate_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_seed_determinism
    result = gate_seed_determinism()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G244"


def test_v10358_g244_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G244", gate_seed_determinism)' in text
