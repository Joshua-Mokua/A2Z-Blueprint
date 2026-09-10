#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""The analyst's "return for rework" actually returns the case.

There are two return paths. /return-for-rework moves the case and the deal.
The department analysts do not use it - Department Review calls
committee-readiness with decision='rework', and that writes a readiness note
and NOTHING else:

    the status does not change
    the deal is not touched
    nobody is named to fix it
    no route back exists

So Catherine returns a case, it stays exactly where it was, and the owner
cannot submit because the deal never moved. Every rework reported stuck comes
through here.

    python scripts/patch_rw3_the_analysts_return_actually_returns.py            # dry run
    python scripts/patch_rw3_the_analysts_return_actually_returns.py --apply

It routes the rework branch through the same behaviour the other path has:
the case goes to 'returned', the returner is recorded so it comes back to
them, and the deal freezes at Rework remembering where it stood.
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_lms_routes.py")

OLD = '    _updates = {"committee_readiness": readiness}'

NEW = '''    _updates = {"committee_readiness": readiness}

    # ── AND REWORK MEANS RETURNED ────────────────────────────────────────────
    # This wrote a readiness note and stopped. The status did not change, the
    # deal was not touched, and nobody was named - so the case sat exactly
    # where it was and its owner could not submit, because submission needs
    # the deal at its document stage.
    #
    # The other return path (/return-for-rework) has always done this. The
    # analysts do not use that one.
    if decision == "rework":
        _me = str(user.get("staff_code", "") or "").strip()
        _myname = str(user.get("full_name", "") or "").strip()
        _updates["status"] = "returned"
        _updates["returned_by_code"] = _me
        _updates["returned_by_name"] = _myname
        _updates["returned_at"] = _dt_now_lms()
        _updates["rework_reasons"] = payload.get("reasons") or []

        # Whoever it is being sent to. One person or several; the owner if
        # nobody is named, because they are the one who submitted it.
        _raw = payload.get("return_to")
        _to = []
        if isinstance(_raw, (list, tuple)):
            _to = [{"code": str((x or {}).get("code", x) or "").strip(),
                    "name": str((x or {}).get("name", "") or "").strip()}
                   for x in _raw
                   if str((x or {}).get("code", x) or "").strip()]
        elif str(_raw or "").strip():
            _to = [{"code": str(_raw).strip(),
                    "name": str(payload.get("return_to_name", "") or "").strip()}]
        if _to:
            _updates["return_to"] = _to
            _updates["analyst"] = {"code": _to[0]["code"],
                                   "name": _to[0]["name"], "role": ""}

        # Freeze the deal where it stands and remember it, so the case comes
        # back HERE rather than climbing from the beginning.
        try:
            _did = str(app.get("pipeline_deal_id") or "").strip()
            if _did:
                from utils.core import PipelineManager as _PM_rw3
                from utils.api import _stage_flow_for as _flow_rw3, \\
                    _product_document_config as _pdc_rw3
                _pm3 = _PM_rw3()
                _d3 = _pm3.get_deal(_did)
                if _d3 and not str(_d3.get("stage", "")).lower().startswith("closed"):
                    _updates["froze_at_stage"] = str(_d3.get("stage", "") or "")
                    _fl3 = [str(x) for x in (_flow_rw3(
                        _d3.get("product_type") or _d3.get("product", "")) or [])]
                    _back3 = "Rework" if "Rework" in _fl3 else ""
                    if not _back3:
                        _docs3, _ds3 = _pdc_rw3(_d3)
                        _back3 = str(_ds3 or "").strip()
                    if _back3 and _back3 != _d3.get("stage"):
                        _pm3.update_stage(
                            _did, _back3,
                            "Returned for rework by %s." % (_myname or _me),
                            str(user.get("username", "") or ""))
        except Exception as _exc3:
            audit_log("LMS_REWORK_DEAL_NOT_MOVED",
                      str(user.get("username", "") or ""),
                      "%s|%s" % (app_id, str(_exc3)[:60]))'''

HELPER_ANCHOR = "def lms_committee_readiness"
HELPER = '''def _dt_now_lms() -> str:
    """Timestamp for a rework return."""
    import datetime as _d
    return _d.datetime.now().isoformat(timespec="seconds")


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "AND REWORK MEANS RETURNED" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The readiness update matched %d times." % s.count(OLD))
        return 1
    if s.count(HELPER_ANCHOR) != 1:
        print("Could not place the timestamp helper.")
        return 1

    s = s.replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)
    s = s.replace(OLD, NEW, 1)

    if '_updates["status"] = "returned"' not in NEW:
        print("The status would still not change.")
        return 1
    if "returned_by_code" not in NEW:
        print("Nothing would bring the case back to whoever returned it.")
        return 1
    if "froze_at_stage" not in NEW:
        print("The stage would not be remembered.")
        return 1
    if 'decision == "rework"' not in NEW:
        print("This would run on ready as well.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("The analyst's return now moves the case and the deal.")
    print("It names who has to act, and remembers where to come back to.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("\nRun add_rework_stage.py first, or it falls back to the")
        print("document stage - correct, but the case loses its place.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_rw3")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. Cases returned BEFORE this are still stuck -")
    print("free_stranded_deals.py moves them where they can be submitted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
