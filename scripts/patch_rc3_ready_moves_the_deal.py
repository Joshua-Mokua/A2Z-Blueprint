#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Marking a case ready for committee moves the deal to the committee stage.

Setting readiness changes the application and nothing else. Committee
visibility follows the DEAL's stage, so a case the analyst has finished stays
where it was and the committee never sees it. D0744 sat at Documentation with
Catherine's recommendation on the case.

This advances the deal to the next committee stage in its own flow when the
verdict is 'ready'. It uses the same _write_deal helper and PipelineManager
pattern the decline path in this module already uses.

    python scripts/patch_rc3_ready_moves_the_deal.py            # dry run
    python scripts/patch_rc3_ready_moves_the_deal.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_lms_routes.py")


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "READY MEANS THE DEAL MOVES TOO" in s:
        print("Already applied.")
        return 1

    # Land immediately before the readiness route's return, whatever it is.
    i = s.find("def lms_committee_readiness")
    if i < 0:
        print("The readiness route is not in this file.")
        return 1
    j = s.index("\n@router.", i + 10)
    body = s[i:j]

    ret = body.rfind("\n    return ")
    if ret < 0:
        print("Could not find the route's return.")
        return 1

    block = '''
    # ── READY MEANS THE DEAL MOVES TOO ──────────────────────────────────────
    # Setting readiness changed the application and nothing else. Committee
    # visibility follows the DEAL's stage, so a case the analyst had finished
    # stayed where it was and the committee never saw it - D0744 sat at
    # Documentation with a recommendation on the case.
    #
    # Same pattern as the decline path above: PipelineManager, _write_deal,
    # and a failure that is logged rather than swallowed.
    if str(decision).strip().lower() == "ready":
        try:
            app_now = lam.get(app_id) or {}
            deal_id = str(app_now.get("pipeline_deal_id") or "")
            if deal_id:
                from utils.api import _write_deal as _wd, _stage_flow_for
                from utils.core import PipelineManager as _PM
                pm = _PM()
                d = pm.get_deal(deal_id)
                if d and not str(d.get("stage", "")).lower().startswith("closed"):
                    flow = [str(x) for x in (_stage_flow_for(
                        d.get("product_type") or d.get("product", "")) or [])]
                    cur = str(d.get("stage", "") or "")
                    target = ""
                    # The next COMMITTEE stage ahead of where the deal stands.
                    if cur in flow:
                        for nxt in flow[flow.index(cur) + 1:]:
                            if "committee" in nxt.lower():
                                target = nxt
                                break
                    if target and target != cur:
                        _wd(pm, deal_id, {
                            "stage": target,
                            "advanced_reason": ("the analyst marked this ready "
                                                "for committee"),
                        }, str(user.get("username", "") or ""))
                        audit_log("LMS_READY_ADVANCED_DEAL",
                                  str(user.get("username", "") or ""),
                                  "%s|%s: %s -> %s" % (app_id, deal_id, cur, target))
        except Exception as exc:
            # Never fail the readiness verdict over the deal's stage - but say
            # so, or the committee waits for something nobody knows is stuck.
            audit_log("LMS_READY_ADVANCE_FAILED",
                      str(user.get("username", "") or ""),
                      "%s|%s: %s" % (app_id, type(exc).__name__, str(exc)[:70]))
'''

    new_body = body[:ret] + block + body[ret:]
    s = s[:i] + new_body + s[j:]

    # The helpers this uses must be the ones this module actually has.
    if "_pm()" in block:
        print("Uses _pm(), which does not exist in this codebase.")
        return 1
    if "_dt." in block:
        print("Uses _dt, which is not imported here.")
        return 1
    for name in ("_write_deal", "PipelineManager", "audit_log"):
        if name not in block:
            print("Does not use %s - check it matches the decline path." % name)
            return 1
    if "audit_log(\"LMS_READY_ADVANCE_FAILED\"" not in block:
        print("A failure would be silent.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("Ready now advances the deal to its next committee stage.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("Check the route's local names first: this assumes `decision`,")
        print("`lam`, `app_id` and `user` are in scope, as the decline path has.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_rc3")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. D0744 needs moving to its committee stage by hand")
    print("once - this fixes the next one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
