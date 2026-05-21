"""Integration tests for v10.438 — HR Rescue Batch 2: wire #14 + #17."""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10438_lms_imports_peer_learning():
    t = (REPO / "pages" / "42_lms.py").read_text()
    assert "from utils.peer_learning" in t


def test_v10438_lms_has_peer_learning_cards_tab():
    t = (REPO / "pages" / "42_lms.py").read_text()
    assert "Peer Learning Cards" in t


def test_v10438_lms_has_skill_matching_tab():
    t = (REPO / "pages" / "42_lms.py").read_text()
    assert "Skill Matching" in t


def test_v10438_lms_uses_list_cards_for_staff():
    t = (REPO / "pages" / "42_lms.py").read_text()
    assert "list_cards_for_staff" in t


def test_v10438_lms_uses_match_for_skill():
    t = (REPO / "pages" / "42_lms.py").read_text()
    assert "match_for_skill" in t


def test_v10438_lms_uses_peer_learning_network():
    t = (REPO / "pages" / "42_lms.py").read_text()
    assert "PeerLearningNetwork" in t


def test_v10438_lms_syntax_valid():
    import ast
    ast.parse((REPO / "pages" / "42_lms.py").read_text())


def test_v10438_people_imports_gamification():
    t = (REPO / "pages" / "2_people.py").read_text()
    assert "from utils.gamification" in t


def test_v10438_people_has_recognition_section():
    t = (REPO / "pages" / "2_people.py").read_text()
    assert "Recognition" in t


def test_v10438_people_uses_list_badges_for_staff():
    t = (REPO / "pages" / "2_people.py").read_text()
    assert "list_badges_for_staff" in t


def test_v10438_people_uses_gamification_engine():
    t = (REPO / "pages" / "2_people.py").read_text()
    assert "GamificationEngine" in t


def test_v10438_people_syntax_valid():
    import ast
    ast.parse((REPO / "pages" / "2_people.py").read_text())


def test_v10438_hr_audit_wiring_50_pct():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import audit_engine_wiring
    ew = audit_engine_wiring()
    assert ew.wiring_coverage_pct >= 50.0


def test_v10438_peer_learning_wired_in_lms():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import audit_engine_wiring
    ew = audit_engine_wiring()
    wired = [w["engine"] for w in ew.wired_engines]
    assert "peer_learning" in wired


def test_v10438_gamification_wired_in_people():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import audit_engine_wiring
    ew = audit_engine_wiring()
    wired = [w["engine"] for w in ew.wired_engines]
    assert "gamification" in wired


def test_v10438_hr_health_improved():
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import hr_full_audit
    a = hr_full_audit()
    assert a.hr_health_pct >= 60.0


def test_v10438_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    m = cascade_bsc_360_audit()
    assert m.overall_harmony_pct == 100.0


def test_v10438_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    h = bsc_full_audit()
    assert h.overall_health_pct == 100.0


def test_v10438_g324_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10438_hr_wire_lms_recognition
    r = gate_v10438_hr_wire_lms_recognition()
    assert r["passed"], r.get("violations")
