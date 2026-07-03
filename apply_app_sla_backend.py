#!/usr/bin/env python3
"""scripts/apply_app_sla_backend.py — C-SLA: SLA status on LMS applications.

Attaches a compact SLA status to every LMS application (list + detail) so every
player sees, at a glance, whether the case has breached the customer promise as it
moves up the ladder. Reuses the existing business-day + due-soon helpers and the
same state vocabulary as deals (on_track / due_soon / breached).

App SLA basis: business days since application_date vs sla_target_days (default 10).
This is the case-age SLA; per-stage SLA tracking builds on top later.

Adds a helper in api.py and attaches sla to apps in the two lms list/detail routes.

SAFE: .pre_appsla backups on api.py + api_lms_routes.py. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
ROUTES = ROOT / "utils" / "api_lms_routes.py"
API_BAK = API.with_suffix(".py.pre_appsla")
ROUTES_BAK = ROUTES.with_suffix(".py.pre_appsla")
API_MARKER = "# === C-SLA: APPLICATION SLA STATUS ==="

API_BLOCK = r'''

# === C-SLA: APPLICATION SLA STATUS ===
def _app_sla_status(app: dict) -> dict:
    """Compact SLA status for an LMS application — the case-age customer promise.
    Reuses _business_days_since + _sla_due_soon_days + the deal state vocabulary
    (on_track / due_soon / breached). Terminal cases return {}."""
    if not isinstance(app, dict):
        return {}
    status = str(app.get("status", "") or "").lower()
    if status in ("disbursed", "declined", "closed"):
        return {}
    base_ts = app.get("application_date") or app.get("created_at") or app.get("last_updated")
    if not base_ts:
        return {}
    try:
        target = int(app.get("sla_target_days") or 10)
    except (TypeError, ValueError):
        target = 10
    elapsed = _business_days_since(base_ts)
    overdue = max(0, elapsed - target)
    remaining = target - elapsed
    cfg = _sla_config()
    if overdue > 0:
        state = "breached"
    elif remaining <= _sla_due_soon_days(cfg):
        state = "due_soon"
    else:
        state = "on_track"
    return {
        "state": state,
        "elapsed_business_days": elapsed,
        "target_days": target,
        "remaining_business_days": remaining,
        "overdue_business_days": overdue,
        "breached": overdue > 0,
    }


def _attach_sla_to_apps(apps: list) -> list:
    """Attach a compact SLA status to each application in a list response. Mutates."""
    if not apps:
        return apps
    for a in apps:
        if isinstance(a, dict):
            try:
                a["sla"] = _app_sla_status(a) or None
            except Exception:
                a["sla"] = None
    return apps
# === END C-SLA: APPLICATION SLA STATUS ===
'''

def patch_routes(s: str) -> str:
    """Attach SLA in the list endpoint + detail endpoint."""
    # list endpoint: attach to the returned apps (lazy import to avoid circular)
    list_anchor = '''    apps = filter_apps_by_visibility(
        lam.apps, visible_codes, caller_code,
        caller_role=str(user.get('role', '') or ''),
    )

    return {
        "applications": apps,'''
    if list_anchor in s and "_attach_sla_to_apps(apps)" not in s:
        s = s.replace(list_anchor, list_anchor.replace(
            "    return {\n        \"applications\": apps,",
            "    from utils.api import _attach_sla_to_apps as _attach_sla\n    _attach_sla(apps)\n    return {\n        \"applications\": apps,"), 1)
    # detail endpoint: attach to the single app
    detail_anchor = '''    return {
        "application": app,
        "permissions": permissions,
        "source": "loan_application_manager",
    }'''
    if detail_anchor in s and 'app["sla"] = _app_sla_status(app)' not in s:
        s = s.replace(detail_anchor,
            '''    try:
        from utils.api import _app_sla_status as _app_sla
        app["sla"] = _app_sla(app) or None
    except Exception:
        pass
    return {
        "application": app,
        "permissions": permissions,
        "source": "loan_application_manager",
    }''', 1)
    return s

def revert():
    for bak, tgt in ((API_BAK, API), (ROUTES_BAK, ROUTES)):
        if bak.exists():
            shutil.copy2(bak, tgt); bak.unlink(); print(f"  reverted {tgt.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    a = API.read_text(encoding="utf-8")
    r = ROUTES.read_text(encoding="utf-8")
    a_ch = API_MARKER not in a
    r_new = patch_routes(r)
    r_ch = r_new != r
    print(f"  api.py: {'change' if a_ch else 'skip'}")
    print(f"  api_lms_routes.py: {'change' if r_ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    if a_ch:
        if not API_BAK.exists(): API_BAK.write_text(a, encoding="utf-8")
        API.write_text(a.rstrip() + "\n" + API_BLOCK + "\n", encoding="utf-8")
    if r_ch:
        if not ROUTES_BAK.exists(): ROUTES_BAK.write_text(r, encoding="utf-8")
        ROUTES.write_text(r_new, encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()
