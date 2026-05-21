"""Integration tests for v10.490 — Uncertainty exposure phase 2."""

import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(autouse=True)
def _reset_all():
    for k in list(sys.modules):
        if any(s in k for s in ("uncertainty", "cert", "arena", "agents",
                                  "ml", "chaos", "channels",
                                  "simulation_clock", "tick_scheduler",
                                  "event_bus", "macro_", "scenarios")):
            del sys.modules[k]
    from utils.simulation_clock import reset_simulation_clock
    from utils.chaos import reset_chaos_injector
    from utils.macro_state import reset_macro_state
    from utils.ml import reset_model_registry
    from utils.agents import reset_default_tool_registry
    from utils.arena import reset_drill_ledger
    reset_simulation_clock(); reset_chaos_injector(); reset_macro_state()
    reset_model_registry(); reset_default_tool_registry()
    reset_drill_ledger()
    yield
    reset_simulation_clock(); reset_chaos_injector(); reset_macro_state()
    reset_model_registry(); reset_default_tool_registry()
    reset_drill_ledger()


# ── Module presence ─────────────────────────────────────────────────

def test_v10490_poisoning_module_exists():
    assert (REPO / "utils" / "uncertainty" / "poisoning.py").exists()


def test_v10490_adversarial_module_exists():
    assert (REPO / "utils" / "uncertainty" / "adversarial.py").exists()


def test_v10490_new_exports_visible():
    from utils.uncertainty import (
        list_poisoning_drills, run_poisoning_drill,
        list_adversarial_drills, run_adversarial_drill,
    )
    assert callable(run_poisoning_drill)
    assert callable(run_adversarial_drill)


# ── Counts ──────────────────────────────────────────────────────────

def test_v10490_has_10_poisoning_drills():
    from utils.uncertainty import list_poisoning_drills
    assert len(list_poisoning_drills()) == 10


def test_v10490_has_8_adversarial_drills():
    from utils.uncertainty import list_adversarial_drills
    assert len(list_adversarial_drills()) == 8


def test_v10490_total_51_drills():
    from utils.uncertainty import list_all_uncertainty_drills
    assert len(list_all_uncertainty_drills()) == 51


# ── Poisoning drill sampling ────────────────────────────────────────

def test_v10490_dp_malformed_payload():
    from utils.uncertainty import run_poisoning_drill
    r = run_poisoning_drill("dp_malformed_payload")
    assert r.passed, r.failure_reasons


def test_v10490_dp_negative_amount():
    from utils.uncertainty import run_poisoning_drill
    r = run_poisoning_drill("dp_negative_amount")
    assert r.passed, r.failure_reasons


def test_v10490_dp_wrong_type_correctly_partial():
    """Confirms channel system rejects wrong-type amounts."""
    from utils.uncertainty import run_poisoning_drill
    r = run_poisoning_drill("dp_wrong_type")
    assert r.passed
    # The 2 wrong-type submits should fail; recovery should pass
    assert r.successful_agent_steps == 1


def test_v10490_dp_unicode_bomb():
    from utils.uncertainty import run_poisoning_drill
    r = run_poisoning_drill("dp_unicode_bomb")
    assert r.passed, r.failure_reasons


def test_v10490_dp_injection_attempts():
    from utils.uncertainty import run_poisoning_drill
    r = run_poisoning_drill("dp_injection_attempts")
    assert r.passed, r.failure_reasons


def test_v10490_dp_oversized_payload():
    from utils.uncertainty import run_poisoning_drill
    r = run_poisoning_drill("dp_oversized_payload")
    assert r.passed, r.failure_reasons


def test_v10490_dp_cross_tenant_contamination():
    from utils.uncertainty import run_poisoning_drill
    r = run_poisoning_drill("dp_cross_tenant_contamination")
    assert r.passed, r.failure_reasons


def test_v10490_poisoning_unknown_raises():
    from utils.uncertainty import get_poisoning_drill
    with pytest.raises(KeyError):
        get_poisoning_drill("does_not_exist")


# ── Adversarial drill sampling ──────────────────────────────────────

def test_v10490_adv_prompt_injection():
    """5 prompt-injection narratives logged as data, not interpreted."""
    from utils.uncertainty import run_adversarial_drill
    r = run_adversarial_drill("adv_prompt_injection")
    assert r.passed, r.failure_reasons
    summary = r.trajectory.tool_call_summary()
    # 5 submits + 1 events:query = 6 steps
    assert summary.get("channel:submit", 0) == 5


def test_v10490_adv_instruction_override_correctly_partial():
    """Confirms tool registry refuses unknown destructive args."""
    from utils.uncertainty import run_adversarial_drill
    r = run_adversarial_drill("adv_instruction_override")
    assert r.passed
    # 3 bogus calls fail, only chaos:list succeeds
    assert r.successful_agent_steps == 1


def test_v10490_adv_hallucination_trap_correctly_partial():
    """Confirms ML registry refuses unknown models."""
    from utils.uncertainty import run_adversarial_drill
    r = run_adversarial_drill("adv_hallucination_trap")
    assert r.passed
    # 2 nonexistent models fail, ml:list succeeds
    assert r.successful_agent_steps == 1


def test_v10490_adv_regulator_deception():
    """Spoofed-actor RTGS+SWIFT logged with full audit trail."""
    from utils.uncertainty import run_adversarial_drill
    r = run_adversarial_drill("adv_regulator_deception")
    assert r.passed, r.failure_reasons


def test_v10490_adv_financial_manipulation_smurfing():
    """3 just-below-threshold transfers all submitted and audited."""
    from utils.uncertainty import run_adversarial_drill
    r = run_adversarial_drill("adv_financial_manipulation")
    assert r.passed
    summary = r.trajectory.tool_call_summary()
    assert summary.get("channel:submit", 0) == 3


def test_v10490_adv_escalation_bypass():
    """10M KES + 500K USD direct submits logged for governance."""
    from utils.uncertainty import run_adversarial_drill
    r = run_adversarial_drill("adv_escalation_bypass")
    assert r.passed, r.failure_reasons


def test_v10490_adv_hidden_bias_exposure_all_5_equal():
    """5 transactions with different demographic names all succeed identically."""
    from utils.uncertainty import run_adversarial_drill
    r = run_adversarial_drill("adv_hidden_bias_exposure")
    assert r.passed
    summary = r.trajectory.tool_call_summary()
    # All 5 submits should be successful (no bias)
    assert summary.get("channel:submit", 0) == 5
    assert r.successful_agent_steps == 6  # 5 submits + 1 query


def test_v10490_adversarial_unknown_raises():
    from utils.uncertainty import get_adversarial_drill
    with pytest.raises(KeyError):
        get_adversarial_drill("does_not_exist")


# ── Policy factory callability ──────────────────────────────────────

def test_v10490_each_poisoning_policy_instantiable():
    from utils.uncertainty import (
        list_poisoning_drills, get_poisoning_policy_factory)
    for name in list_poisoning_drills():
        pc = get_poisoning_policy_factory(name)
        instance = pc()
        assert hasattr(instance, "choose")


def test_v10490_each_adversarial_policy_instantiable():
    from utils.uncertainty import (
        list_adversarial_drills, get_adversarial_policy_factory)
    for name in list_adversarial_drills():
        pc = get_adversarial_policy_factory(name)
        instance = pc()
        assert hasattr(instance, "choose")


# ── Full battery cumulative ─────────────────────────────────────────

def test_v10490_full_battery_all_18_new_pass():
    """Run all 18 v10.490 drills."""
    from utils.uncertainty import (
        list_poisoning_drills, run_poisoning_drill,
        list_adversarial_drills, run_adversarial_drill,
    )
    failures = []
    for name in list_poisoning_drills():
        r = run_poisoning_drill(name)
        if not r.passed:
            failures.append((name, r.failure_reasons))
    for name in list_adversarial_drills():
        r = run_adversarial_drill(name)
        if not r.passed:
            failures.append((name, r.failure_reasons))
    assert not failures, failures


# ── Reproducibility ─────────────────────────────────────────────────

def test_v10490_poisoning_drill_reproducible():
    from utils.uncertainty import run_poisoning_drill
    r1 = run_poisoning_drill("dp_unicode_bomb")
    r2 = run_poisoning_drill("dp_unicode_bomb")
    assert r1.agent_steps == r2.agent_steps
    assert r1.successful_agent_steps == r2.successful_agent_steps


def test_v10490_adversarial_drill_reproducible():
    from utils.uncertainty import run_adversarial_drill
    r1 = run_adversarial_drill("adv_prompt_injection")
    r2 = run_adversarial_drill("adv_prompt_injection")
    assert r1.agent_steps == r2.agent_steps
    assert r1.successful_agent_steps == r2.successful_agent_steps


# ── Cross-batch (v10.489 + v10.490) ─────────────────────────────────

def test_v10490_cumulative_51_drills_named():
    from utils.uncertainty import list_all_uncertainty_drills
    names = list_all_uncertainty_drills()
    assert len(names) == 51
    bs_count = sum(1 for n in names if n.startswith("bs_"))
    ir_count = sum(1 for n in names if n.startswith("ir_"))
    tc_count = sum(1 for n in names if n.startswith("tc_"))
    dp_count = sum(1 for n in names if n.startswith("dp_"))
    adv_count = sum(1 for n in names if n.startswith("adv_"))
    assert bs_count == 15
    assert ir_count == 8
    assert tc_count == 10
    assert dp_count == 10
    assert adv_count == 8


# ── G376 + cumulative regression ────────────────────────────────────

def test_v10490_g376_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10490_uncertainty_exposure_phase2
    r = gate_v10490_uncertainty_exposure_phase2()
    assert r["passed"], r.get("violations")


def test_v10490_prior_gates_preserved():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import (
        gate_v10489_uncertainty_exposure_phase1,
        gate_v10488_championship_readiness,
        gate_v10487_olympic_certification,
    )
    for gate in (gate_v10489_uncertainty_exposure_phase1,
                  gate_v10488_championship_readiness,
                  gate_v10487_olympic_certification):
        assert gate()["passed"], f"{gate.__name__} regressed"


def test_v10490_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9
