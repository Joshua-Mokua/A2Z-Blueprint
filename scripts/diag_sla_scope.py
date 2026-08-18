"""Diagnose the SLA-violations READ scope for a given user (default: immaculate0716).

Runs entirely against the live data/code in this checkout — no API server needed.
Answers: (1) what scope does this user resolve to, (2) which all-view trigger (if any)
fires, (3) how many violation-eligible deals are visible to them ONLY via the
portfolio-owner OR-clause (by design) vs a genuine over-grant where neither the deal's
staff_code nor its portfolio_owner_code is in their visible set.

    .venv\\Scripts\\activate
    python scripts\\diag_sla_scope.py            # immaculate0716
    python scripts\\diag_sla_scope.py william001 # compare against MD/admin
"""
import sys


def main():
    username = sys.argv[1] if len(sys.argv) > 1 else "immaculate0716"

    from utils.core import UserManager
    from utils.api_pipeline_scope import (
        get_visible_staff_codes, filter_deals_by_visible_codes, get_staff_roster,
    )
    from utils.core_audit import _ALL_VIEW_ROLES, REPORTING_TREE, _register_root_roles

    um = UserManager()
    user = dict(um.users.get(username) or {})
    if not user:
        print(f"!! no user record for {username!r}")
        return
    user.setdefault("username", username)
    role = str(user.get("role", "") or "")
    role_l = role.lower().strip()

    print(f"== USER {username} ==")
    print(f"  role        : {role!r}")
    print(f"  staff_code  : {user.get('staff_code')!r}")
    print(f"  unit        : {user.get('unit')!r}")
    print(f"  is_admin    : {user.get('is_admin')}")
    print(f"  can_view_all: {user.get('can_view_all')}")

    # --- which all-view trigger (if any) fires ---
    try:
        root_roles = set(_register_root_roles())
    except Exception:
        root_roles = set()
    tree_cfg = REPORTING_TREE.get(role) or next(
        (REPORTING_TREE[k] for k in REPORTING_TREE if k.lower() == role_l), None)
    tree_roles_is_none = bool(tree_cfg) and tree_cfg.get("tree_roles") is None

    print("\n== ALL-VIEW TRIGGER CHECK ==")
    print(f"  is_admin flag           : {bool(user.get('is_admin'))}")
    print(f"  'admin' substring in role: {'admin' in role_l}   <-- substring path")
    print(f"  role in _ALL_VIEW_ROLES  : {role_l in set(_ALL_VIEW_ROLES)}")
    print(f"  role in root roles       : {role_l in root_roles}")
    print(f"  REPORTING_TREE tree_roles is None (=> ALL rows): {tree_roles_is_none}")

    roster = get_staff_roster()
    roster_n = len(roster) if roster is not None else 0
    visible = get_visible_staff_codes(user)
    print("\n== RESOLVED SCOPE ==")
    print(f"  full roster size : {roster_n}")
    print(f"  visible codes    : {len(visible)}")
    verdict = "ALL-VIEW (sees entire roster)" if roster_n and len(visible) >= roster_n \
        else "scoped subtree" if len(visible) > 1 else "self-only"
    print(f"  verdict          : {verdict}")

    # --- quantify the leak against actual deals ---
    try:
        from utils.api import _all_pipeline_deals  # type: ignore
        deals = _all_pipeline_deals()
    except Exception:
        from utils.core import PipelineManager
        deals = PipelineManager().get_deals()
    elig = filter_deals_by_visible_codes(deals, visible)
    via_staff = via_portfolio_only = neither = 0
    for d in elig:
        sc = str(d.get("staff_code", "") or "")
        po = str(d.get("portfolio_owner_code", "") or "")
        if sc in visible:
            via_staff += 1
        elif po and po in visible:
            via_portfolio_only += 1
        else:
            neither += 1
    print("\n== VISIBLE DEALS (violation-eligible population) ==")
    print(f"  total visible deals          : {len(elig)} of {len(deals)}")
    print(f"  via own/sub staff_code       : {via_staff}")
    print(f"  via portfolio_owner ONLY     : {via_portfolio_only}  (by design, Section 15.4)")
    print(f"  via NEITHER (TRUE LEAK)      : {neither}  <-- should be 0")
    if neither:
        print("  !! genuine over-grant: deals slipped the filter — investigate get_visible_staff")


if __name__ == "__main__":
    main()
