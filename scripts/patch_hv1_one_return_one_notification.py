#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Every desk sends work back the same way, and tells people the same way.

There were three returns and three notification helpers. A fix to one missed
the others, and a fortnight of reports came from that split.

utils/handover.py is now the single path. This rewires the desks onto it:

    the analyst's return (committee-readiness, decision='rework')
    credit admin's request to the branch
    the resubmission that brings a case back

and removes _tell and _ca_tell, which did the same job twice.

Copy handover.py into utils/ first.

    python scripts/patch_hv1_one_return_one_notification.py            # dry run
    python scripts/patch_hv1_one_return_one_notification.py --apply
"""
import os
import re
import shutil
import sys

LMS = os.path.join("utils", "api_lms_routes.py")
CAD = os.path.join("utils", "api_credit_admin_routes.py")
MODULE = os.path.join("utils", "handover.py")


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MODULE):
        print("%s is not there yet." % MODULE)
        print("Copy handover.py into utils\\ first.")
        return 1
    for f in (LMS, CAD):
        if not os.path.isfile(f):
            print("%s not found." % f)
            return 1

    lms = open(LMS, encoding="utf-8").read()
    cad = open(CAD, encoding="utf-8").read()
    if "from utils.handover import" in lms:
        print("Already applied.")
        return 1

    changed = []

    # ── 1. The analyst's return goes through send_back ──────────────────────
    m = re.search(
        r"\n    # ── AND REWORK MEANS RETURNED ─.*?(?=\n    # ── READY MEANS SUBMITTED)",
        lms, re.S)
    if m:
        lms = lms[:m.start()] + '''
    # ── AND REWORK MEANS RETURNED ────────────────────────────────────────────
    # One return path for every desk - see utils/handover.py. This used to
    # carry its own copy of the logic, and credit admin carried another.
    if decision == "rework":
        try:
            from utils.handover import send_back
            _res = send_back(
                app_id,
                to=payload.get("return_to"),
                reason=(str(payload.get("opinion", "") or "").strip()
                        or "Returned for rework"),
                user=user,
                asked_from="analyst",
                reasons=payload.get("reasons") or [])
            _updates.update({k: v for k, v in {
                "status": "returned",
                "froze_at_stage": _res.get("froze_at_stage") or "",
            }.items() if v or k == "status"})
        except ValueError as _ve:
            raise HTTPException(status_code=400, detail=str(_ve))
        except Exception as _exc:
            audit_log("LMS_REWORK_SEND_BACK_FAILED",
                      str(user.get("username", "") or ""),
                      "%s|%s" % (app_id, str(_exc)[:60]))
''' + lms[m.end():]
        changed.append("the analyst's return now calls send_back")
    else:
        print("  RW3's block not found - apply patch_rw3 first, or this")
        print("  would leave two return paths again.")
        return 1

    # ── 2. Remove _tell, use notify ──────────────────────────────────────────
    t = re.search(r"\ndef _tell\(.*?(?=\ndef |\n@router)", lms, re.S)
    if t:
        lms = lms[:t.start()] + "\n" + lms[t.end():]
        changed.append("_tell removed")
    lms = lms.replace("    _tell(", "    _hv_notify(")
    if "_hv_notify" in lms:
        lms = lms.replace(
            "from utils.core_audit import audit_log",
            "from utils.core_audit import audit_log\n"
            "from utils.handover import notify as _hv_notify", 1)
        changed.append("notifications go through handover.notify")

    # ── 3. Credit admin's request uses the same helper ──────────────────────
    c = re.search(r"\ndef _ca_tell\(.*?(?=\n@router)", cad, re.S)
    if c:
        cad = cad[:c.start()] + "\n" + cad[c.end():]
        cad = cad.replace("        _ca_tell(", "        _hv_notify(")
        cad = cad.replace(
            "from utils.core_audit import audit_log",
            "from utils.core_audit import audit_log\n"
            "from utils.handover import notify as _hv_notify", 1)
        changed.append("credit admin uses the same notify")

    for label in changed:
        print("  %s" % label)
    if not changed:
        print("Nothing to change.")
        return 1

    if "_tell(" in lms.replace("_hv_notify(", ""):
        print("_tell survives somewhere.")
        return 1
    if "_ca_tell(" in cad.replace("_hv_notify(", ""):
        print("_ca_tell survives somewhere.")
        return 1
    import ast
    for name, src in ((LMS, lms), (CAD, cad)):
        try:
            ast.parse(src)
        except SyntaxError as exc:
            print("%s would not parse - line %s: %s" % (name, exc.lineno, exc.msg))
            return 1
    print("\n  one return path, one notification, both desks")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    for path, src in ((LMS, lms), (CAD, cad)):
        shutil.copy2(path, path + ".pre_hv1")
        open(path, "w", encoding="utf-8", newline="").write(src)
        print("Applied %s" % path)
    import py_compile
    for path in (LMS, CAD, MODULE):
        try:
            py_compile.compile(path, doraise=True)
        except Exception as exc:
            print("  FAIL %s: %s" % (path, str(exc)[:70]))
            return 1
    print("  all three compile")
    print("\nRestart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
