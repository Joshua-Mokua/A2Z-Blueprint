"""Phase 3 (credit-factory hardening) — BSC owner attribution.

Asserts emit_bsc_for() credits the deal OWNER (not just the caller), dedupes,
and is resilient (best-effort). update_bsc_from_modules is monkeypatched so the
test runs without DB/streamlit.
"""
import sys, types, importlib


def _install_fake_core(calls):
    """Inject a fake utils.core.update_bsc_from_modules that records calls."""
    core = types.ModuleType("utils.core")
    def update_bsc_from_modules(username, period="Feb 2026"):
        calls.append(username)
        return {"username": username}
    core.update_bsc_from_modules = update_bsc_from_modules
    sys.modules["utils.core"] = core


def test_emit_bsc_for_credits_owner_and_caller_dedup_and_blank_safe():
    calls = []
    _install_fake_core(calls)
    # Fresh import of the bridge against the fake core
    sys.modules.pop("utils.api_bsc_bridge", None)
    bridge = importlib.import_module("utils.api_bsc_bridge")

    # owner + caller -> both credited, order preserved
    assert bridge.emit_bsc_for(["frank0731", "immaculate0716"]) is True
    assert calls == ["frank0731", "immaculate0716"]

    # dedup: same owner==caller credited once
    calls.clear()
    assert bridge.emit_bsc_for(["frank0731", "frank0731"]) is True
    assert calls == ["frank0731"]

    # blanks/None skipped
    calls.clear()
    assert bridge.emit_bsc_for([None, "", "  ", "frank0731"]) is True
    assert calls == ["frank0731"]

    # all-blank -> no calls, returns False (nothing credited)
    calls.clear()
    assert bridge.emit_bsc_for([None, "", "  "]) is False
    assert calls == []

    # string convenience form
    calls.clear()
    assert bridge.emit_bsc_for("frank0731") is True
    assert calls == ["frank0731"]


def test_emit_bsc_for_is_best_effort_on_recompute_error():
    calls = []
    core = types.ModuleType("utils.core")
    def boom(username, period="Feb 2026"):
        calls.append(username)
        raise RuntimeError("bsc engine down")
    core.update_bsc_from_modules = boom
    sys.modules["utils.core"] = core
    sys.modules.pop("utils.api_bsc_bridge", None)
    bridge = importlib.import_module("utils.api_bsc_bridge")

    # Must not raise; returns False because every recompute failed
    assert bridge.emit_bsc_for(["frank0731", "immaculate0716"]) is False
    assert calls == ["frank0731", "immaculate0716"]  # both attempted
