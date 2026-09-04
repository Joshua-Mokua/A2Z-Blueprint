#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
FN2 - a deal that has gone to credit says so in the funnel.

FROM THE BANK (2026-09-04): "when a deal leaves the branch to the department
credit analyst and above, does it really show the movement in the funnel? I
have several cases submitted to the department credit analyst but the funnel is
not displaying as such."

IT ADVANCES THE DEAL, AND FAILS SILENTLY IN THREE WAYS:

    _flow = _stage_flow_for(product)
    _cur = deal["stage"]
    if _cur in _flow:                     <- 1. current stage not in the flow
        _idx = _flow.index(_cur)
        if 0 <= _idx < len(_flow) - 1:    <- 2. already at the last stage
            _next = _flow[_idx + 1]
            if not _next.startswith("closed"):
                pm.update_stage(...)
    except Exception:
        pass                              <- 3. anything at all

Every one of those leaves the deal where it was, with no record. The case moves
to the credit analyst, the officer sees it in Credit Analysis, and the funnel
still shows it sitting at the branch - two screens telling a manager different
things about the same deal, and neither of them wrong from where it stands.

The likeliest cause is the first: a deal on a stage its product's flow does not
define. That state already exists - it is why some deals cannot be closed.

WHAT THIS CHANGES: nothing about WHEN a deal advances. It records what
happened, so the gap is visible instead of silent.

    the stage moves       as before
    it did not move       an audit entry says which of the three reasons
    it threw             the exception is logged, not swallowed

WHY NOT FORCE THE ADVANCE: because a deal on a stage outside its flow has a
data problem, and inventing a stage for it would put a deal somewhere nobody
chose. The audit entry names the deal so it can be corrected.

THE SUBMISSION STILL SUCCEEDS EITHER WAY. Stage sync was best-effort by design
and stays that way - a case must not fail to reach credit because its funnel
position could not be worked out.

Usage (from project root, .venv active):
    python scripts\patch_fn2_funnel_follows_credit.py            # dry run
    python scripts\patch_fn2_funnel_follows_credit.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")

OLD = '''                if not _next.lower().startswith("closed"):
                    pm.update_stage(deal_id, _next,
                                    f"Auto-advanced on submit to credit (app {app_id}).",
                                    str(user.get("username", "")))
    except Exception:
        # Stage sync is best-effort — never fail a successful submission on it.
        pass'''

NEW = '''                if not _next.lower().startswith("closed"):
                    pm.update_stage(deal_id, _next,
                                    f"Auto-advanced on submit to credit (app {app_id}).",
                                    str(user.get("username", "")))
                    _moved = True
                else:
                    _why = ("the next stage is %r, which is a closing stage"
                            % _next)
            else:
                _why = ("the deal is already at the last stage of its flow "
                        "(%r)" % _cur)
        else:
            # THE LIKELIEST ONE. A deal sitting on a stage its product's flow
            # does not define cannot be advanced - the next stage cannot be
            # computed from a position that is not on the map. It is the same
            # state that stops some deals being closed.
            _why = ("the deal's stage %r is not in the %r flow"
                    % (_cur, deal.get("product_type") or deal.get("product", "")))
    except Exception as exc:
        # Stage sync is best-effort — never fail a successful submission on it.
        # But "best-effort" is not "unrecorded": a deal that reached credit and
        # did not move in the funnel leaves two screens telling a manager
        # different things about the same case.
        _why = "the stage sync raised: %s" % str(exc)[:120]
        logger.warning("submit-to-credit stage sync failed for %s: %s",
                       deal_id, exc)

    # ── SAY SO WHEN THE FUNNEL DID NOT MOVE ─────────────────────────────────
    # RULING (2026-09-04): "I have several cases submitted to the department
    # credit analyst but the funnel is not displaying as such."
    #
    # It was failing in three different ways and saying nothing in any of them.
    # The advance is still best-effort - a case must not fail to reach credit
    # because its funnel position could not be worked out - but it is no longer
    # silent, and the audit names the deal so it can be corrected.
    if not _moved:
        _audit("API_PIPELINE_STAGE_NOT_ADVANCED", user,
               f"deal_id={deal_id} app={app_id} reason={_why or 'unknown'}")
        logger.info("deal %s reached credit but did not advance: %s",
                    deal_id, _why or "unknown")'''

# Anchored on the comment above the block - the _stage_flow_for call itself
# appears twice in the file and the patch must land in the submit path.
INIT_OLD = '''    # never auto-advances into a terminal Closed stage.'''
INIT_NEW = '''    # never auto-advances into a terminal Closed stage.
    _moved = False
    _why = ""'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "SAY SO WHEN THE FUNNEL DID NOT MOVE" in s:
        print("ABORT: FN2 looks applied.")
        return 1
    for nm, anchor in (("the advance block", OLD), ("the flow lookup", INIT_OLD)):
        if s.count(anchor) != 1:
            print("ABORT: %s matched %d times." % (nm, s.count(anchor)))
            return 1

    s = s.replace(INIT_OLD, INIT_NEW, 1).replace(OLD, NEW, 1)
    print("  ok  a funnel that did not move is recorded, not swallowed")

    if "except Exception:\n        # Stage sync is best-effort" in s:
        print("ABORT: the silent except survives.")
        return 1
    if "_audit(\"API_PIPELINE_STAGE_NOT_ADVANCED\"" not in s:
        print("ABORT: nothing is recorded when the funnel does not move.")
        return 1
    # The submission must still succeed - this records, it does not refuse.
    i = s.index("SAY SO WHEN THE FUNNEL DID NOT MOVE")
    tail = s[i:i + 1400]
    if "raise HTTPException" in tail:
        print("ABORT: this would fail a submission whose stage could not be")
        print("       synced. A case must still reach credit.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: nothing swallowed, the submission still succeeds")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_fn2")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. Submit a case to credit, then look in the audit")
    print("log for API_PIPELINE_STAGE_NOT_ADVANCED - it names the reason.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
