"""Integration tests for v10.459 — Cross-Organ Sync + Super Users + Notifications.

3 new engines wire all 5 organs together for Phase 4 + Phase 7 + Phase 8.
Avg health 74.3% → 76.6% (+2.3pp). Phase 8 hit 95-100% on 4 modules.
"""

import ast
import re
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def all_modules():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k or "cascade_bsc_360" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import all_modules_audit
    return all_modules_audit()


# ── Cross-organ event bus ───────────────────────────────────────────

def test_v10459_event_bus_exists():
    assert (REPO / "utils" / "cross_organ_event_bus.py").exists()


def test_v10459_event_bus_parses():
    ast.parse((REPO / "utils" / "cross_organ_event_bus.py").read_text())


def test_v10459_event_bus_api_first():
    text = (REPO / "utils" / "cross_organ_event_bus.py").read_text()
    assert "import streamlit" not in text


def test_v10459_event_bus_full_api():
    text = (REPO / "utils" / "cross_organ_event_bus.py").read_text()
    for fn in ("EVENT_TYPES", "def publish_event", "def subscribe",
               "def workload_balance",
               "def audit_event_bus_coverage",
               "class Event", "class WorkloadStatus"):
        assert fn in text, f"Missing: {fn}"


def test_v10459_event_bus_publishes_and_subscribes():
    for k in list(sys.modules):
        if "cross_organ_event_bus" in k:
            del sys.modules[k]
    from utils.cross_organ_event_bus import publish_event, subscribe
    received = []
    sub_id = subscribe("test.event", "credit",
                       lambda e: received.append(e))
    assert sub_id
    publish_event("test.event", "credit", payload={"foo": "bar"})
    assert len(received) == 1
    assert received[0].source_organ == "credit"


# ── Super user registry ─────────────────────────────────────────────

def test_v10459_super_user_registry_exists():
    assert (REPO / "utils" / "super_user_registry.py").exists()


def test_v10459_super_user_registry_parses():
    ast.parse((REPO / "utils" / "super_user_registry.py").read_text())


def test_v10459_super_user_api_first():
    text = (REPO / "utils" / "super_user_registry.py").read_text()
    assert "import streamlit" not in text


def test_v10459_super_user_full_api():
    text = (REPO / "utils" / "super_user_registry.py").read_text()
    for fn in ("SUPER_USER_MAP", "def get_super_user",
               "def get_escalation_path", "def is_super_user",
               "def audit_super_user_coverage",
               "class SuperUserConfig", "class EscalationRecord"):
        assert fn in text, f"Missing: {fn}"


def test_v10459_super_user_all_5_organs():
    for k in list(sys.modules):
        if "super_user_registry" in k:
            del sys.modules[k]
    from utils.super_user_registry import SUPER_USER_MAP
    for key in ("admin", "hr", "bsc_cascade", "credit", "ict"):
        assert key in SUPER_USER_MAP


def test_v10459_all_organs_have_ict_super_user_in_path():
    """Per Joshua: ICT Super User is 2nd-level admin for all organs."""
    for k in list(sys.modules):
        if "super_user_registry" in k:
            del sys.modules[k]
    from utils.super_user_registry import (
        SUPER_USER_MAP, audit_super_user_coverage,
    )
    cov = audit_super_user_coverage()
    assert cov.organs_with_ict_secondary == 5


# ── Notification broadcaster ────────────────────────────────────────

def test_v10459_notification_broadcaster_exists():
    assert (REPO / "utils" / "notification_broadcaster.py").exists()


def test_v10459_notification_broadcaster_parses():
    ast.parse((REPO / "utils" / "notification_broadcaster.py").read_text())


def test_v10459_notification_api_first():
    text = (REPO / "utils" / "notification_broadcaster.py").read_text()
    assert "import streamlit" not in text


def test_v10459_notification_full_api():
    text = (REPO / "utils" / "notification_broadcaster.py").read_text()
    for fn in ("SECURITY_EVENT_TYPES", "def track_page",
               "def track_security_event", "def send_notification",
               "def broadcast_notification", "def perf_timer",
               "class PageViewRecord", "class SecurityEventRecord"):
        assert fn in text, f"Missing: {fn}"


def test_v10459_notification_track_page_works():
    for k in list(sys.modules):
        if "notification_broadcaster" in k:
            del sys.modules[k]
    from utils.notification_broadcaster import track_page, get_usage_analytics
    track_page("test_page.py", "EMP1234", duration_ms=42.5)
    analytics = get_usage_analytics()
    assert analytics.total_page_views >= 1


def test_v10459_broadcast_hits_5_super_users():
    for k in list(sys.modules):
        if "notification_broadcaster" in k or "super_user_registry" in k:
            del sys.modules[k]
    from utils.notification_broadcaster import broadcast_notification
    notifs = broadcast_notification("warning", "test broadcast")
    assert len(notifs) == 5


# ── Module text contains required keywords ──────────────────────────

def test_v10459_module_text_has_super_user():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY, _module_text
    for key in MODULE_REGISTRY.keys():
        text = _module_text(MODULE_REGISTRY[key])
        assert re.search(r"super_user|is_super_user", text, re.I), \
            f"{key} missing super_user"


def test_v10459_module_text_has_usage_monitoring():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY, _module_text
    for key in MODULE_REGISTRY.keys():
        text = _module_text(MODULE_REGISTRY[key])
        assert re.search(r"track_page|page_view|usage_analytics", text, re.I), \
            f"{key} missing usage monitoring"


def test_v10459_module_text_has_security_event():
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY, _module_text
    for key in MODULE_REGISTRY.keys():
        text = _module_text(MODULE_REGISTRY[key])
        assert re.search(r"access_denied|auth_failure|security_event", text, re.I), \
            f"{key} missing security_event monitoring"


# ── Health uplift ───────────────────────────────────────────────────

def test_v10459_avg_health_above_76(all_modules):
    assert all_modules.avg_doctrine_health_pct >= 76.0


def test_v10459_phase_8_95_plus_on_multiple(all_modules):
    high = sum(1 for m in all_modules.modules.values()
              if m.phase_8.score_pct >= 95.0)
    assert high >= 3


def test_v10459_credit_health_75_plus(all_modules):
    """Credit was 72.8% → expected ~75%."""
    assert all_modules.modules["credit"].doctrine_health_pct >= 75.0


def test_v10459_no_crisis(all_modules):
    assert len(all_modules.crisis_modules) == 0


# ── Upstream ────────────────────────────────────────────────────────

def test_v10459_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10459_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10459_g345_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10459_cross_organ_sync
    r = gate_v10459_cross_organ_sync()
    assert r["passed"], r.get("violations")
