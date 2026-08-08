#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 3f - the grid stops deciding its own hierarchy.

THE MISTAKE (mine). /history-grid carried its own scope rules:

    if _is_admin(user):      -> everything
    elif _is_manager(user):  -> subtree     (_is_manager matched the SUBSTRING
    else:                    -> self         "head" or "manager" in the role)

That is a second, weaker hierarchy sitting beside the real one. It also called
get_visible_staff_codes with a stripped-down dict carrying only staff_code,
role and is_admin - but core_audit.get_visible_staff also reads full_name,
unit, department and can_view_all, and degrades toward self-only when they are
missing. A Head of Branches therefore landed on "subtree".

THE FIX. Scope is now ONE call to get_visible_staff_codes - the same engine the
Pipeline, Referrals and BSC use - with a fully enriched caller context. That
engine already knows:

    * admins and the MD
    * _ALL_VIEW_ROLES, which since 2026-08-07 includes "head of branches",
      "head, branches", "head of branch", "head branches" - MD-equivalent
      visibility, because every deal lives in a branch
    * register root roles, derived from the roster itself
    * data custodian roles (Finance / HR)
    * Head-Office SEGMENT scope, so CIB / CCB / Consumer / Commercial heads see
      their whole department book across branch and head office
    * the REPORTING_TREE walk for everyone else

No hierarchy is defined in this endpoint any more. If REPORTING_TREE or the role
sets change, the grid follows automatically - no duplicate-logic drift, and no
new tree invented that would later be pushed to the pilot.

Also: the roster fill reuses that single scope set instead of re-deciding, and
scope_tier is derived from what the engine RETURNED, with visible_staff added to
the response so the count is auditable from the client.

Verified: py_compile clean; the grid no longer references _is_admin/_is_manager;
exactly one row loop remains.

Usage (from project root, .venv active):
    python scripts\\patch_p3f_canonical_scope.py            # dry run
    python scripts\\patch_p3f_canonical_scope.py --apply    # write + .pre_p3f backup
"""
import os
import shutil
import sys

API = os.path.join("utils", "api_branch_log.py")
BACKUP_SUFFIX = ".pre_p3f"

SCOPE_NEW = r'''def branch_log_history_grid(days: int = 30, unit: str = "", include_missing: bool = True,
                            user: dict = Depends(get_current_user)):
    """Wide history grid: one row per staff per day with all metric columns, the daily index,
    target, variance, and the running CARRIED-FORWARD variance (per staff). Scope-aware:
    admin sees all; a manager sees their reporting subtree; everyone else sees themselves.

    Carried-forward variance is computed at read time per staff member (honouring admin reset
    markers and healing on validation) via utils.branch_log_analytics.carried_forward.
    """
    from utils.branch_log import metric_keys, fields_schema
    from utils.branch_log_analytics import carried_forward, deadline_time

    me = _identity(user)
    blm = BranchLogManager()
    logs = blm.get_history(days=days)
    if unit and unit != "All":
        logs = [l for l in logs if str(l.get("unit", "")) == unit]

    # SCOPE IS NOT DECIDED HERE. get_visible_staff_codes -> core_audit.
    # get_visible_staff is the same engine the Pipeline, Referrals and BSC use.
    # It already knows admins, the MD, _ALL_VIEW_ROLES (which includes Head of
    # Branches), register root roles, data custodians, Head-Office segment scope
    # for CIB/CCB/Consumer/Commercial, and the REPORTING_TREE walk.
    #
    # It reads full_name, unit, department and can_view_all from user_data - a
    # stripped-down dict silently degrades it toward self-only - so enrich the
    # caller context from the stored record before calling.
    _stored = {}
    try:
        from utils.core import UserManager
        _stored = UserManager().users.get(str(user.get("username", "")) or "") or {}
    except Exception:
        _stored = {}
    user_ctx = {
        "staff_code":   me.get("staff_code", "") or str(_stored.get("staff_code", "") or ""),
        "role":         me.get("role", "") or str(_stored.get("role", "") or ""),
        "full_name":    str(_stored.get("full_name", "") or me.get("staff_name", "") or ""),
        "unit":         me.get("unit", "") or str(_stored.get("unit", "") or ""),
        "department":   str(_stored.get("department", "") or ""),
        "is_admin":     bool(user.get("is_admin") or _stored.get("is_admin")),
        "can_view_all": bool(user.get("can_view_all") or _stored.get("can_view_all")),
    }
    from utils.staff_code import canon as _canon_scope
    try:
        from utils.api_pipeline_scope import get_visible_staff_codes
        visible = {_canon_scope(c) for c in get_visible_staff_codes(user_ctx)}
    except Exception:
        visible = set()
    visible.discard("")
    if not visible and user_ctx["staff_code"]:
        visible = {_canon_scope(user_ctx["staff_code"])}

    scoped = [l for l in logs if _canon_scope(l.get("staff_code")) in visible]

'''

FILL_NEW = r'''        dims = _dims
        # One scope decision per request, made above by the canonical engine.
        # Intersected with the roster so rows are only synthesised for people
        # who actually exist in staff_register.xlsx.
        scope_codes = {c for c in visible if c in dims} or set(visible)
        scope_codes.discard("")

'''

TIER_NEW = r'''        # Derived from what the engine RETURNED, so the chip reflects real
        # visibility rather than a role-string guess.
        "scope_tier": ("bank" if len(visible) >= max(len(_dims), 1)
                       else ("subtree" if len(visible) > 1 else "self")),
        "visible_staff": len(visible),
'''

OLD_SCOPE = """    if _is_admin(user):
        scoped = logs
    elif _is_manager(user):
        scoped = _subtree_logs(logs, user, me)
    else:
        scoped = [l for l in logs if str(l.get("staff_code")) == me["staff_code"]]"""

OLD_TIER = '        "scope_tier": "bank" if _is_admin(user) else ("subtree" if _is_manager(user) else "self"),'


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found. Run from the project root." % API)
        return 1
    api = open(API, encoding="utf-8").read()

    if "SCOPE IS NOT DECIDED HERE" in api:
        print("ABORT: Phase 3f looks applied already.")
        return 1
    if "_DIMS_CACHE" not in api or "include_missing" not in api:
        print("ABORT: apply patch_p3e_hotfix.py first.")
        return 1

    try:
        fn = api.index("def branch_log_history_grid(")
        api.index(OLD_SCOPE, fn)
    except ValueError:
        print("ABORT: expected scope block not found inside branch_log_history_grid.")
        return 1

    b = api.index("    # Group by staff so carried-forward runs per person", fn)
    api = api[:fn] + SCOPE_NEW + api[b:]
    print("  ok  scope -> get_visible_staff_codes with an enriched context")

    k = api.index("        dims = _dims")
    l = api.index("        # Working days in the window", k)
    api = api[:k] + FILL_NEW + api[l:]
    print("  ok  roster fill reuses that one scope set")

    fn2 = api.index("def branch_log_history_grid(")
    m = api.index(OLD_TIER, fn2)
    api = api[:m] + TIER_NEW + api[m + len(OLD_TIER):]
    print("  ok  scope_tier derived from the engine result")

    s = api.index("def branch_log_history_grid(")
    e = api.index('"deadline_time": deadline_time(),', s)
    head = api[s:e]
    if "_is_admin(user)" in head or "_is_manager(user)" in head:
        print("ABORT: post-check - the grid still calls _is_admin/_is_manager.")
        return 1
    if "get_visible_staff_codes" not in head:
        print("ABORT: post-check - the grid does not call the visibility engine.")
        return 1
    if head.count("for sc, staff_logs in by_staff.items():") != 1:
        print("ABORT: post-check - row loop count is not 1.")
        return 1
    print("  ok  post-checks: one row loop, no local hierarchy rules")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(api)
    print("APPLIED %s  (backup: %s)" % (API, os.path.basename(API) + BACKUP_SUFFIX))

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRestart uvicorn, then reload the History tab.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
