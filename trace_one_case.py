#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Trace one real case end to end, and reproduce the exact failure. READ ONLY.

The code is live. If a user is still stuck, it is this case's data, not the
code. This looks at one case and tells you precisely why an action would fail -
including reproducing the committee-readiness call that is throwing 500, so its
traceback is captured here rather than hunted for in the console.

    python trace_one_case.py --app LMS00036
    python trace_one_case.py --app LMS00036 --as KE1300   (act as this person)

Read only. Nothing is written; the readiness call is made in a dry mode that
computes but does not save.
"""
import os
import sys
import traceback

sys.path.insert(0, os.getcwd())


def main():
    a = sys.argv
    app_id = a[a.index("--app") + 1] if "--app" in a else ""
    who = a[a.index("--as") + 1] if "--as" in a else ""
    if not app_id:
        print("--app LMS00036 [--as KE1300]")
        return 1

    from utils.api_lms_routes import _lam
    app = _lam().get(app_id)
    if not app:
        print("No application %r." % app_id)
        return 1

    print("=" * 84)
    print("CASE %s" % app_id)
    print("=" * 84)
    print("  client        %s" % app.get("client_name"))
    print("  status        %r" % app.get("status"))
    an = app.get("analyst") or {}
    print("  assigned to   %s" % ((an.get("name") or an.get("code")) if isinstance(an, dict) else "?"))
    deal_id = str(app.get("pipeline_deal_id") or "").strip()
    print("  pipeline deal %s" % (deal_id or "*** NONE"))

    if deal_id:
        from utils.core import PipelineManager
        d = PipelineManager().get_deal(deal_id)
        if not d:
            print("  *** the deal it points at does not exist - this alone breaks advance")
        else:
            cur = str(d.get("stage") or "")
            print("  deal stage    %r" % cur)
            import utils.api as A
            flow = [str(x) for x in (A._stage_flow_for(d.get("product_type")
                     or d.get("product", "")) or [])]
            print("  in the flow   %s" % ("yes" if cur in flow else "*** NO"))
            dept = [x for x in flow if "department" in x.lower() and "committee" in x.lower()]
            print("  dept cttee    %s" % (dept[0] if dept else "*** none in this flow"))

    # documents visible to the committee
    print("\n  DOCUMENTS THE COMMITTEE WOULD SEE")
    try:
        from utils.api_lms_routes import lms_application_documents_list as _docs
        # build a minimal caller
        from utils.core import UserManager
        users = UserManager().users or {}
        caller = next((dict(r, username=l) for l, r in users.items()
                       if str(r.get("staff_code", "")).strip() == who), None) \
            or {"is_admin": True, "staff_code": "SYS", "role": "admin"}
        res = _docs(app_id, caller)
        prov = res.get("provided") or []
        print("    provided: %d" % len(prov))
        for p in prov[:15]:
            print("       - %s" % (p.get("name") if isinstance(p, dict) else p))
        req = [r for r in (res.get("required") or [])]
        print("    required: %d" % len(req))
    except Exception:
        print("    (could not list documents:)")
        traceback.print_exc()

    # reproduce the readiness/recommend call to catch the 500
    if who:
        print("\n  REPRODUCING 'Recommend to committee' AS %s" % who)
        try:
            from utils.core import UserManager
            users = UserManager().users or {}
            caller = next((dict(r, username=l) for l, r in users.items()
                           if str(r.get("staff_code", "")).strip() == who), None)
            if not caller:
                print("    nobody has staff code %r" % who)
                return 1
            from utils.api_lms_routes import lms_committee_readiness
            # ── WHY THIS IS PATCHED AT THE CLASS LEVEL, NOT THE INSTANCE ──────
            # _lam() and PipelineManager() are both documented as "fresh
            # instance per call" (see _lam()'s own docstring). The original
            # version of this script patched .update/.save/.update_stage on
            # ONE instance it created itself - lms_committee_readiness (and
            # FX2's advance-on-ready code inside it) construct their OWN fresh
            # instances internally, which are never touched by that patch.
            # This is the exact same trap that made an earlier smoke test in
            # this session (SOT1) write a real change while believing it was
            # inert. Patching the CLASS attribute intercepts every instance,
            # however many get constructed.
            #
            # FX2's ready-path also writes through utils.api._write_deal(),
            # which is imported locally inside the route
            # (`from utils.api import _write_deal as _wd`) - a fresh lookup
            # at call time, so patching the module attribute before calling
            # is sufficient and does not need class-level tricks. Per its own
            # docstring it writes BOTH the JSON store and Postgres directly;
            # the original script did not touch this path at all.
            import utils.core as _core
            import utils.api as _api_mod
            _orig_lam_update = _core.LoanApplicationManager.update
            _orig_lam_save = _core.LoanApplicationManager.save
            _orig_pm_update_stage = _core.PipelineManager.update_stage
            _orig_write_deal = _api_mod._write_deal

            def _noop(*a, **k):
                return True

            try:
                _core.LoanApplicationManager.update = _noop
                _core.LoanApplicationManager.save = _noop
                _core.PipelineManager.update_stage = _noop
                _api_mod._write_deal = _noop
                payload = {"decision": "ready",
                           "opinion": "trace — not saved"}
                try:
                    from pydantic import BaseModel  # noqa
                except Exception:
                    pass
                res = lms_committee_readiness(app_id, payload, caller)
                print("    OK — it would succeed. Result: %s"
                      % (str(res)[:80] if res else "(none)"))
            finally:
                _core.LoanApplicationManager.update = _orig_lam_update
                _core.LoanApplicationManager.save = _orig_lam_save
                _core.PipelineManager.update_stage = _orig_pm_update_stage
                _api_mod._write_deal = _orig_write_deal
        except Exception:
            print("    *** THIS IS THE 500. Traceback:")
            print("    " + "-" * 70)
            for line in traceback.format_exc().splitlines():
                print("    " + line)
            print("    " + "-" * 70)
            print("    Send these lines - the failing line is named above.")
            return 1
    else:
        print("\n  (pass --as KE1300 to reproduce Catherine's Recommend and")
        print("   capture the 500 traceback here.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
