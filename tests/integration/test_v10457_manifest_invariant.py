"""Integration tests for v10.457 — Manifest Invariant Hotfix.

Per Joshua: KeyError 'current_module_key' at app.py:900.
Root cause: v10.448 + v10.454 added pages without registering them
completely in pages/_manifest.json.

v10.457 fixes manifest entries + adds gate to prevent future drift.
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def manifest():
    path = REPO / "pages" / "_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_v10457_manifest_present(manifest):
    assert "pages" in manifest
    assert len(manifest["pages"]) >= 130


def test_v10457_credit_approvals_has_module_key(manifest):
    """v10.448 page now has current_module_key."""
    entry = manifest["pages"].get("82_credit_approvals.py")
    assert entry is not None
    assert entry.get("current_module_key") == "approvals"


def test_v10457_chief_credit_centre_registered(manifest):
    """v10.454 NEW page now registered in manifest."""
    entry = manifest["pages"].get("85_chief_credit_centre.py")
    assert entry is not None
    assert entry.get("current_module_key") == "chief_centre"
    assert entry.get("department_primary") == "credit"
    assert entry.get("title") == "Chief Credit \u2014 360 Command Centre"


def test_v10457_every_entry_has_required_fields(manifest):
    """Invariant: every entry has title + icon + current_module_key + department_primary."""
    missing = []
    for fname, entry in manifest["pages"].items():
        for req in ("title", "icon", "current_module_key", "department_primary"):
            if req not in entry:
                missing.append(f"{fname}: {req}")
    assert missing == [], f"Manifest invariant broken: {missing[:5]}"


def test_v10457_chief_centre_pattern_consistent(manifest):
    """81 (HR) and 85 (Credit) chief centres share structure."""
    hr = manifest["pages"]["81_chief_hr_centre.py"]
    credit = manifest["pages"]["85_chief_credit_centre.py"]
    assert hr["current_module_key"] == credit["current_module_key"]
    assert hr["icon"] == credit["icon"]


def test_v10457_pages_in_department_works():
    """The function that crashed in app.py:900 now works for credit dept."""
    for k in list(sys.modules):
        if "page_manifest_loader" in k:
            del sys.modules[k]
    from utils.page_manifest_loader import pages_in_department
    credit_pages = pages_in_department("credit", include_secondary=False)
    assert len(credit_pages) > 0
    for fname, entry in credit_pages:
        # The exact access pattern from app.py:900
        _ = entry["title"]
        _ = entry["icon"]
        _ = entry["current_module_key"]  # must not raise


def test_v10457_backup_present():
    bdir = REPO / "data" / "_v10457_backups"
    assert bdir.exists()
    assert (bdir / "_manifest.json.before").exists()


# ── Upstream ────────────────────────────────────────────────────────

def test_v10457_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10457_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10457_5_module_audit_still_works():
    """v10.456 5-organ audit unaffected."""
    for k in list(sys.modules):
        if "module_doctrine_audit" in k:
            del sys.modules[k]
    from utils.module_doctrine_audit import all_modules_audit
    a = all_modules_audit()
    assert len(a.modules) == 5
    assert a.avg_doctrine_health_pct >= 65.0


def test_v10457_g343_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10457_manifest_invariant
    r = gate_v10457_manifest_invariant()
    assert r["passed"], r.get("violations")
