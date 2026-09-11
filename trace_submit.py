#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Why can this deal not be submitted? Traces every gate in _credit_submission_state.

Returned deals cannot resubmit. can_submit is an AND of seven conditions; this
prints each one for a real deal, so the exact false gate is named rather than
guessed.

    python trace_submit.py --deal D0644
    python trace_submit.py --deal D0644 --as CN020

Read only.
"""
import os
import sys
sys.path.insert(0, os.getcwd())


def main():
    a = sys.argv
    deal_id = a[a.index("--deal") + 1] if "--deal" in a else ""
    who = a[a.index("--as") + 1] if "--as" in a else ""
    if not deal_id:
        print("--deal D0644 [--as CN020]")
        return 1

    from utils.core import PipelineManager, UserManager
    d = PipelineManager().get_deal(deal_id)
    if not d:
        print("No deal %r." % deal_id)
        return 1
    user = None
    if who:
        users = UserManager().users or {}
        user = next((dict(r, username=l) for l, r in users.items()
                     if str(r.get("staff_code", "")).strip() == who), None)
    if not user:
        user = {"staff_code": str(d.get("staff_code") or ""),
                "full_name": str(d.get("staff_name") or ""),
                "role": "", "username": "trace", "is_admin": False}

    print("=" * 84)
    print("SUBMIT TRACE — %s" % deal_id)
    print("=" * 84)
    print("  client        %s" % d.get("client_name"))
    print("  stage         %r" % d.get("stage"))
    print("  owner         %s" % d.get("staff_code"))
    print("  acting as     %s (%s)" % (user.get("staff_code"), user.get("full_name")))

    import utils.api as A
    # The real signature is (deal, user, visible_codes) - every actual call
    # site (pipeline_credit_checklist, etc.) computes visible_codes via
    # get_visible_staff_codes(user) first. Missing here in the version as
    # given; without it this throws a TypeError before tracing anything.
    from utils.api_pipeline_scope import get_visible_staff_codes
    visible_codes = get_visible_staff_codes(user)
    try:
        st = A._credit_submission_state(d, user, visible_codes)
    except Exception:
        import traceback
        print("\n  *** _credit_submission_state THREW:")
        for l in traceback.format_exc().splitlines()[-10:]:
            print("    " + l)
        return 1

    # _credit_submission_state's actual return dict does NOT include
    # is_owner/is_admin_like/perms/can_view/terminal, and its "already" key
    # is really named "already_submitted" - these gates below would have
    # silently shown the wrong verdict on every run (already-submitted and
    # terminal permanently "ok", owner/admin and can_view permanently
    # "blocked") while can_submit itself (read straight from the dict)
    # stayed correct. Recomputed here with the exact same logic the
    # function uses internally, since the dict never exposes them.
    from utils.api_pipeline_permissions import resolve_deal_permissions
    my_code = str(user.get("staff_code", "") or "").strip()
    is_owner = A._same_staff_code(my_code, str(d.get("staff_code", "") or "").strip())
    is_admin_like = bool(user.get("is_admin")) or "admin" in str(user.get("role", "")).lower()
    can_view = resolve_deal_permissions(d, user, visible_codes).get("can_view", False)
    terminal = str(d.get("stage", "")) in ("Closed Won", "Closed Lost")

    print("\n  EACH GATE (all must be true to submit):")
    gates = [
        ("owner or admin", is_owner or is_admin_like),
        ("not already submitted", not st.get("already_submitted")),
        ("not terminal (closed)", not terminal),
        ("stage_ok (at doc stage or Rework)", st.get("stage_ok")),
        ("credit ok / not required", st.get("cr_ok") or not st.get("cr_required")),
        ("committee_ok", st.get("committee_ok")),
        ("manager_validated", st.get("manager_validated")),
        ("can_view", can_view),
    ]
    blocked = []
    for name, ok in gates:
        mark = "ok " if ok else "*** FALSE"
        print("    %s %s" % (mark, name))
        if not ok:
            blocked.append(name)

    _recomputed = all(ok for _, ok in gates)
    if _recomputed != bool(st.get("can_submit")):
        print("\n  *** WARNING: the gates above disagree with can_submit itself")
        print("      (recomputed=%s, can_submit=%s) - one of the recomputed" %
              (_recomputed, st.get("can_submit")))
        print("      gates above does not exactly match the real function's")
        print("      internal logic. Trust can_submit; treat the gate list as")
        print("      a lead, not a verdict, until this is reconciled.")

    print("\n  can_submit = %s" % st.get("can_submit"))
    if st.get("missing"):
        print("  missing documents: %s" % ", ".join(
            str(m.get("name") if isinstance(m, dict) else m) for m in st["missing"]))

    print("\n" + "=" * 84)
    if st.get("can_submit"):
        print("  This deal CAN be submitted. If the button is still dead, it is the")
        print("  browser (stale bundle - hard refresh) or a different acting user.")
    else:
        print("  BLOCKED BY: %s" % ", ".join(blocked or ["(see missing docs)"]))
        print("  That is the gate to fix. Each maps to one cause:")
        print("    stage_ok false      -> deal not at doc stage or Rework")
        print("    committee_ok false  -> a branch committee vote is still open,")
        print("                           or was reset when it returned")
        print("    manager_validated   -> the deal lost its validation flag on return")
        print("    already true        -> it thinks it is already in credit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
