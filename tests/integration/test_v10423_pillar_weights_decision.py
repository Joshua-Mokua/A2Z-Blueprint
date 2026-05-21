"""Integration tests for v10.423 — pillar weights decision (Kaplan-Norton 40/25/25/10)."""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


EXPECTED = {
    "Financial": 0.40,
    "Customer Focus": 0.25,
    "Operational Excellence": 0.25,
    "People & Learning": 0.10,
}
TOLERANCE = 0.001


def _load_lib():
    return json.loads((REPO / "data" / "kpi_library.json").read_text())


def test_v10423_pillar_weights_match_kaplan_norton():
    lib = _load_lib()
    pw = lib.get("pillar_weights", {})
    for pillar, target in EXPECTED.items():
        assert pillar in pw, f"Missing pillar: {pillar}"
        assert abs(pw[pillar] - target) < TOLERANCE, (
            f"{pillar}: {pw[pillar]} != {target}"
        )


def test_v10423_pillar_weights_sum_to_one():
    lib = _load_lib()
    total = sum(lib.get("pillar_weights", {}).values())
    assert abs(total - 1.0) < TOLERANCE, f"Sum = {total}, expected 1.0"


def test_v10423_no_dead_organs():
    """All 4 canonical pillars must be present with non-zero weights."""
    lib = _load_lib()
    pw = lib.get("pillar_weights", {})
    for pillar in EXPECTED:
        assert pw.get(pillar, 0) > 0, f"{pillar} has dead-organ weight"


def test_v10423_history_records_change():
    history_path = REPO / "data" / "pillar_weights_history.json"
    assert history_path.exists(), "pillar_weights_history.json missing"

    history = json.loads(history_path.read_text())
    entries = history if isinstance(history, list) else history.get("entries", [])
    # Must contain a v10.423 reasoning entry
    matches = [
        e for e in entries
        if "v10.423" in str(e.get("reason", ""))
        or "kaplan" in str(e.get("reason", "")).lower()
    ]
    assert len(matches) > 0, "No v10.423 / Kaplan-Norton entry in history"


def test_v10423_canonical_save_path_loadable():
    for k in list(sys.modules):
        if "pillar_weights_canonical" in k:
            del sys.modules[k]
    from utils.pillar_weights_canonical import (
        get_pillar_weights, save_pillar_weights, CANONICAL_PILLARS,
    )
    assert set(CANONICAL_PILLARS) == set(EXPECTED.keys())
    # Read returns same values
    current = get_pillar_weights()
    for pillar, target in EXPECTED.items():
        assert abs(current[pillar] - target) < TOLERANCE


def test_v10423_admin_editor_present_in_admin_page():
    text = (REPO / "pages" / "7_admin.py").read_text()
    # Admin UI for pillar weights present
    assert "Pillar weights" in text
    # Wires to canonical save path
    assert "pillar_weights_canonical" in text
    assert "save_pillar_weights" in text


def test_v10423_default_fallback_uses_kaplan_norton():
    """The hardcoded fallback in admin code should also use 40/25/25/10
    (so admins editing on a fresh library see the right defaults)."""
    text = (REPO / "pages" / "7_admin.py").read_text()
    # The fallback constants should reflect the new standard
    assert '"Financial":0.40' in text or '"Financial": 0.40' in text, (
        "Admin default fallback should be 0.40 for Financial"
    )


def test_v10423_g309_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10423_pillar_weights_decision
    r = gate_v10423_pillar_weights_decision()
    assert r["passed"], r.get("violations")
