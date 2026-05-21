"""Integration tests for v10.386 — KPI Library Pillar Weights admin canonical save.

First Phase C execution batch. The KPI Library → Pillar Weights admin
tab now uses save_pillar_weights() (v10.384 canonical accessor) with
validation + history + audit-log. Bundles v10.387 (History view) since
accessor already exposed get_pillar_weights_history.

10 tests across 3 sections.
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
# Section 1 — Doc + admin page structure
# ────────────────────────────────────────────────────────────────────

def test_v10386_design_doc_has_7_parts():
    p = REPO / "docs" / "PILLAR_WEIGHTS_ADMIN_MIGRATION_v10.386.md"
    assert p.exists()
    text = p.read_text()
    for part in range(1, 8):
        assert f"## Part {part}" in text, f"missing Part {part}"


def test_v10386_admin_parses_cleanly():
    """pages/7_admin.py still parses after the refactor."""
    import ast
    p = REPO / "pages" / "7_admin.py"
    ast.parse(p.read_text())


def test_v10386_admin_imports_canonical_accessor():
    p = REPO / "pages" / "7_admin.py"
    text = p.read_text()
    for sym in ("save_pillar_weights", "get_pillar_weights_history",
                "CANONICAL_PILLARS"):
        assert sym in text, f"admin doesn't import {sym}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Specific refactor behavior
# ────────────────────────────────────────────────────────────────────

def test_v10386_kpi_library_tab_calls_canonical_save():
    """The KPI Library tab block must call save_pillar_weights, not
    set _lib[\"pillar_weights\"] directly."""
    p = REPO / "pages" / "7_admin.py"
    text = p.read_text()
    # Find the KPI Library tab section
    import re
    m = re.search(
        r'elif "Pillar weights" in _kl_view:(.+?)(?=\n        elif |\n        # ══)',
        text, re.DOTALL,
    )
    assert m is not None, "KPI Library Pillar Weights block not found"
    block = m.group(1)
    assert "save_pillar_weights" in block, "block doesn't call canonical save"
    # The old direct write should NOT appear in this block
    assert '_lib["pillar_weights"] = _new_pw' not in block, (
        "block still has old direct write"
    )


def test_v10386_save_passes_actor_and_reason():
    """The save call must use kwargs actor= and reason=."""
    p = REPO / "pages" / "7_admin.py"
    text = p.read_text()
    assert "actor=uname" in text or "actor= uname" in text, (
        "save call missing actor= kwarg"
    )
    assert "reason=" in text, "save call missing reason= kwarg"


def test_v10386_admin_has_reason_text_input():
    p = REPO / "pages" / "7_admin.py"
    text = p.read_text()
    # The reason input field should be present
    assert "pw_reason" in text, "no reason text_input"
    assert "Reason for change" in text or "reason for change" in text.lower()


def test_v10386_admin_renders_history():
    """Recent history (last 5 changes) should be rendered."""
    p = REPO / "pages" / "7_admin.py"
    text = p.read_text()
    assert "get_pillar_weights_history" in text
    assert "_pw_history(limit=5)" in text or "history(limit=5)" in text
    assert "Recent history" in text or "recent history" in text.lower()


def test_v10386_bank_identity_tab_redirect_notice_present():
    """The Bank Identity tab pre-v10.388 had a deprecation warning. v10.388
    replaced it with a redirect 'Pillar weights moved' notice. Either is
    acceptable evidence that v10.386 was followed by v10.388 cleanup.
    """
    p = REPO / "pages" / "7_admin.py"
    text = p.read_text()
    # Pre-v10.388: deprecation notice present (Deprecated + v10.384)
    # Post-v10.388: redirect notice present (Pillar weights moved + v10.388)
    has_deprecation = "Deprecated" in text and "v10.384" in text
    has_redirect = "Pillar weights moved" in text and "v10.388" in text
    assert has_deprecation or has_redirect, (
        "neither v10.384 deprecation notice nor v10.388 redirect "
        "notice found in admin page"
    )


# ────────────────────────────────────────────────────────────────────
# Section 3 — G272 + canonical accessor behavior + no regression
# ────────────────────────────────────────────────────────────────────

def test_v10386_g272_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_v10386_admin_canonical_save
    r = gate_v10386_admin_canonical_save()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G272"


def test_v10386_canonical_save_still_validates_and_appends_history():
    """The canonical save (called by the admin) still works correctly."""
    _reimport("utils.pillar_weights_canonical")
    import utils.pillar_weights_canonical as pwc

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        sandbox_kpi = td_path / "kpi_library.json"
        sandbox_hist = td_path / "pillar_weights_history.json"
        sandbox_kpi.write_text(json.dumps({
            "pillar_weights": {
                "Financial": 0.40, "Customer Focus": 0.25,
                "Operational Excellence": 0.25, "People & Learning": 0.10,
            }
        }))

        orig_kpi = pwc.KPI_LIBRARY_PATH
        orig_hist = pwc.HISTORY_PATH
        pwc.KPI_LIBRARY_PATH = sandbox_kpi
        pwc.HISTORY_PATH = sandbox_hist

        try:
            # Simulate admin save with reason
            ok, msg = pwc.save_pillar_weights(
                {"Financial": 0.50, "Customer Focus": 0.20,
                 "Operational Excellence": 0.20, "People & Learning": 0.10},
                actor="admin_test_user",
                reason="Return to balanced posture after crisis",
            )
            assert ok, msg
            # History captured
            hist = json.loads(sandbox_hist.read_text())
            assert len(hist) == 1
            assert hist[0]["changed_by"] == "admin_test_user"
            assert "balanced" in hist[0]["reason"]
            # Reject bad weights
            ok2, msg2 = pwc.save_pillar_weights(
                {"Financial": 0, "Customer Focus": 0.40,
                 "Operational Excellence": 0.30, "People & Learning": 0.30},
                actor="test",
            )
            assert not ok2
            assert "> 0" in msg2 or "dead organ" in msg2.lower()
        finally:
            pwc.KPI_LIBRARY_PATH = orig_kpi
            pwc.HISTORY_PATH = orig_hist
