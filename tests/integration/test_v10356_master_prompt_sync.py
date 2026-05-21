"""Integration tests for v10.356 — Master Prompt Sync (v4.0) + cycle-break correction.

Two-part batch:
  Part 1: Master prompt resync from v3.9 (v10.115) to v4.0 (v10.355).
          240 versions of accumulated drift folded into the canonical
          State-of-Play. G242 audit gate locks the lockstep going forward.
  Part 2: Cycle-break correction. v10.355 placed refresh_yoy() inside
          actuals_engine.compute_actuals_from_cbs which created an
          actuals_engine → live_actuals → cbs_baseline → actuals_engine
          cycle that G128 flagged. v10.356 inverts: callers orchestrate.

12 tests across 5 sections:
  Section 1 — Master Prompt v4.0 file (3 tests)
  Section 2 — Constitution preserved (3 tests)
  Section 3 — State-of-Play current (2 tests)
  Section 4 — G242 gate (2 tests)
  Section 5 — Cycle break verified (2 tests)
"""

import re
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
# Section 1 — Master Prompt v4.0 file
# ────────────────────────────────────────────────────────────────────

def test_v10356_master_prompt_v40_exists():
    path = REPO / "docs" / "Master_Prompt_v4.0.md"
    assert path.exists(), "Master_Prompt_v4.0.md must exist after the sync"


def test_v10356_master_prompt_v40_is_newest():
    """No higher-numbered master prompt should exist (we're the newest)."""
    prompts = sorted((REPO / "docs").glob("Master_Prompt_v*.md"))
    def parse_ver(p):
        m = re.match(r"Master_Prompt_v(\d+)\.(\d+)\.md", p.name)
        return (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    newest = max(prompts, key=parse_ver)
    assert newest.name == "Master_Prompt_v4.0.md"


def test_v10356_master_prompt_v40_substantive():
    """File is real content, not a stub."""
    path = REPO / "docs" / "Master_Prompt_v4.0.md"
    text = path.read_text()
    assert len(text) > 20000, f"Master prompt too short ({len(text)} chars) — looks like stub"
    # Must have major sections
    for marker in ("# A2Z MIS 360 — Master prompt (v4.0)",
                   "## 🎯 Core objective",
                   "## 🌐 Systems Thinking Layer",
                   "## 📍 State of play",
                   "## 🔴 Mandatory execution standards",
                   "## 🚦 Anti-drift discipline",
                   "## ✅ Quality gates"):
        assert marker in text, f"Missing section: {marker}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Constitution preserved
# ────────────────────────────────────────────────────────────────────

def test_v10356_one_question_present_verbatim():
    """Charter §1 'One Question' must be verbatim."""
    text = (REPO / "docs" / "Master_Prompt_v4.0.md").read_text()
    assert "Is the bank on track to achieve its strategic goals, and if not, what should I do about it?" in text


def test_v10356_eleven_mandatory_standards_present():
    text = (REPO / "docs" / "Master_Prompt_v4.0.md").read_text()
    standards = [
        "Universal BSC data contract",
        "Central BSC integration engine",
        "Module factory standard",
        "ETL & data pipeline discipline",
        "Reconciliation & data integrity",
        "Audit, logging & traceability",
        "Data quality & validation layer",
        "No-JSON policy",
        "Frontend separation principle",
        "System control & consistency check",
        "Financial accounting honesty",
    ]
    missing = [s for s in standards if s not in text]
    assert not missing, f"Missing: {missing}"


def test_v10356_football_team_test_preserved():
    """Charter §2 acceptance criterion."""
    text = (REPO / "docs" / "Master_Prompt_v4.0.md").read_text()
    assert "Football Team Test" in text
    assert "impact of a teller's action on the bank's ROE" in text


# ────────────────────────────────────────────────────────────────────
# Section 3 — State-of-Play current
# ────────────────────────────────────────────────────────────────────

def test_v10356_references_current_batch():
    """The master prompt must reference v10.355 (or newer)."""
    text = (REPO / "docs" / "Master_Prompt_v4.0.md").read_text()
    found = sorted({int(m.group(1)) for m in re.finditer(r"v10\.(\d+)", text)})
    assert max(found) >= 355, f"Newest batch referenced: v10.{max(found)} — should be ≥355"


def test_v10356_acknowledges_drift_recovery():
    """The version history must acknowledge the 240-version drift."""
    text = (REPO / "docs" / "Master_Prompt_v4.0.md").read_text()
    assert "drift" in text.lower()
    assert "240" in text or "v3.9" in text


# ────────────────────────────────────────────────────────────────────
# Section 4 — G242 gate
# ────────────────────────────────────────────────────────────────────

def test_v10356_g242_gate_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_master_prompt_sync
    result = gate_master_prompt_sync()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G242"


def test_v10356_g242_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G242", gate_master_prompt_sync)' in text


# ────────────────────────────────────────────────────────────────────
# Section 5 — Cycle break verified
# ────────────────────────────────────────────────────────────────────

def test_v10356_actuals_engine_does_not_import_live_actuals():
    """v10.356 inverted the v10.355 wiring to break the import cycle."""
    text = (REPO / "utils" / "actuals_engine.py").read_text()
    assert "from utils.live_actuals import" not in text
    assert "import utils.live_actuals" not in text


def test_v10356_g128_passes():
    """G128 (structural audit) must pass — verifies the cycle is gone."""
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    import audit as A
    fn = dict(A.GATES).get("G128")
    assert fn is not None, "G128 must be registered"
    result = fn()
    assert result.get("passed"), (
        f"G128 must pass — circular import was introduced in v10.355 and "
        f"fixed in v10.356. Violations: {result.get('violations', [])[:3]}"
    )
