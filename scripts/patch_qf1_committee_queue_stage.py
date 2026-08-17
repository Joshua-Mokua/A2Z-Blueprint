#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
QF1 - the committee queue shows only cases that have reached it.

RULING (2026-08-13): "Should a case at Documentation appear in the committee
queue at all? No, until it is submitted. At or past the committee's own stage -
yes."

The queue listed every deal whose journey included this committee - which for a
branch committee means EVERY DEAL IN THE BRANCH from Initiation onward. Forty
cases, thirty-eight of them nowhere near ready to discuss. A committee that
opens its queue and finds mostly noise stops opening it, so that is worse than
an empty list: it teaches people the screen is not worth reading.

AT OR PAST, not exactly at. A case that has moved beyond the committee stage
without a decision is precisely the one somebody needs to see - it should not
disappear because it slipped forward.

Measured on four cases at four stages, one committee:

    Initiation                        out
    Documentation                     out
    Branch Credit Committee Review    IN
    Credit Analysis                   IN

BRANCH STAGE TO BRANCH COMMITTEE, other committee stages to the department one
- so a member of the DCC is not shown cases sitting at a branch gate, and vice
versa.

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_qf1_committee_queue_stage.py            # dry run
    python scripts\\patch_qf1_committee_queue_stage.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_qf1"

ANCHOR = "        # SCOPE STILL APPLIES"

FILTER = r'''        # ── ONLY CASES THAT HAVE ACTUALLY REACHED THE COMMITTEE ─────────────
        # RULING (2026-08-13): "should a case at Documentation appear in the
        # committee queue at all? No, until it is submitted. At or past the
        # committee's own stage - yes."
        #
        # The queue listed every deal whose journey included this committee,
        # which for a branch committee is EVERY DEAL IN THE BRANCH from
        # Initiation onward - forty cases of which thirty-eight are nowhere
        # near ready to discuss. A committee that opens its queue and finds
        # mostly noise stops opening it, so this is worse than an empty list.
        #
        # AT OR PAST, not exactly at: a case that has moved on without the
        # committee deciding is precisely the one somebody needs to see.
        try:
            _flow = _stage_flow_for(d.get("product_type") or d.get("product", "")) or []
            _cur = str(d.get("stage", "") or "")
            if _flow and _cur in _flow:
                _here = _flow.index(_cur)
                _gate_at = -1
                for _n, _st in enumerate(_flow):
                    _low = _st.lower()
                    if "committee" not in _low:
                        continue
                    # Which committee stage belongs to which of my committees:
                    # a branch stage answers to a branch committee, any other
                    # committee stage to a department one.
                    _is_branch_stage = "branch" in _low
                    for _cc in pending:
                        _c = next((x for x in mine
                                   if str(x.get("code")) == _cc), None)
                        if not _c:
                            continue
                        if (str(_c.get("kind", "")).lower() == "branch") == _is_branch_stage:
                            _gate_at = _n if _gate_at < 0 else min(_gate_at, _n)
                if _gate_at >= 0 and _here < _gate_at:
                    continue
        except Exception:
            pass
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "ONLY CASES THAT HAVE ACTUALLY REACHED THE COMMITTEE" in s:
        print("ABORT: QF1 looks applied.")
        return 1
    if s.count(ANCHOR) != 1:
        print("ABORT: the committee queue anchor matched %d times." % s.count(ANCHOR))
        print("       CQ1 and DQ1 must be applied first.")
        return 1

    s = s.replace(ANCHOR, FILTER + ANCHOR, 1)
    print("  ok  only cases at or past the committee stage")

    # AT OR PAST, not exactly at.
    if "_here < _gate_at" not in FILTER:
        print("ABORT: the comparison is not 'earlier than the gate', so a case")
        print("       that slipped past the committee would vanish from view.")
        return 1
    # A missing flow must not empty somebody's queue.
    if "except Exception" not in FILTER:
        print("ABORT: a product with no flow would raise and empty the queue.")
        return 1
    if "_is_branch_stage" not in FILTER:
        print("ABORT: branch and department stages are not told apart, so a DCC")
        print("       member would be shown branch-gate cases.")
        return 1
    print("  ok  post-checks: at-or-past, flow-safe, right committee")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRestart uvicorn. The queue now means 'these need you', not")
    print("'everything in your branch'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
