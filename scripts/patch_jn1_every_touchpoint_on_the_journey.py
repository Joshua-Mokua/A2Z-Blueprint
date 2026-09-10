#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Every handover writes a line on the case journey.

The journey is what an analyst, a committee member and an auditor read. This
week's handovers all wrote to the audit log and none wrote to the journey - so
a case could be asked about, answered, sent back by credit admin and re-valued
with nothing on it to say so.

Wires four of them to handover.journey():

    seek input           who asked whom, and the question
    the answer           who answered, their stance, and why
    credit admin's ask   what they need and from whom
    an amended value     from what, to what, and why

handover.send_back and bring_back already write theirs.

    python scripts/patch_jn1_every_touchpoint_on_the_journey.py            # dry run
    python scripts/patch_jn1_every_touchpoint_on_the_journey.py --apply
"""
import os
import shutil
import sys

LMS = os.path.join("utils", "api_lms_routes.py")
CAD = os.path.join("utils", "api_credit_admin_routes.py")
API = os.path.join("utils", "api.py")

# (file, label, anchor that must appear exactly once, what to insert after it,
#  a marker unique to THIS wire's call block, checked quoted so it can't match
#  an unrelated field name elsewhere in a 13k-line file - "an amended value"'s
#  own second-line check false-positived on api.py's unrelated _app_id line
#  from the committee-vote function, and value_amended (no quotes) matches the
#  pre-existing value_amended_at/value_amended_by field names on the same deal)
WIRES = [
    (LMS, "seek input", '"input_sought"',
     '    audit_log("LMS_INPUT_SOUGHT", str(user.get("username", "") or ""),\n'
     '              "%s|from=%s|%s" % (app_id, to_code, question[:60]))',
     '\n    from utils.handover import journey as _journey\n'
     '    _journey(app_id, "input_sought", user,\n'
     '             "Asked %s for input: %s" % (to_name or to_code, question),\n'
     '             to=to_code)'),
    (LMS, "the answer", '"input_given"',
     '    audit_log("LMS_INPUT_GIVEN", str(user.get("username", "") or ""),\n'
     '              "%s|%s|%s" % (app_id, stance or "commented", answer[:60]))',
     '\n    from utils.handover import journey as _journey\n'
     '    _journey(app_id, "input_given", user,\n'
     '             "%s: %s" % ({"supports": "Supports it",\n'
     '                          "opposes": "Does not support it"}.get(\n'
     '                              stance or "", "Commented"), answer),\n'
     '             stance=stance or "commented")'),
    (CAD, "credit admin's ask", '"credit_admin_asked"',
     '    audit_log("CREDIT_ADMIN_ASKED_BRANCH",\n'
     '              str(user.get("username", "") or ""),\n'
     '              "%s|to=%s|%s" % (case_id, ",".join(p["code"] for p in to), what[:60]))',
     '\n    try:\n'
     '        _app_id = str(case.get("application_id") or case.get("app_id") or "")\n'
     '        if _app_id:\n'
     '            from utils.handover import journey as _journey\n'
     '            _journey(_app_id, "credit_admin_asked", user,\n'
     '                     "Credit admin needs: %s (from %s)"\n'
     '                     % (what, ", ".join(p["name"] or p["code"] for p in to)),\n'
     '                     to=[p["code"] for p in to])\n'
     '    except Exception:\n'
     '        pass'),
    (API, "an amended value", '"value_amended"',
     '    _audit("API_DEAL_AMEND_VALUE", user,\n'
     '           f"deal_id={deal_id}|{old_f:.0f}->{new_value:.0f}|{reason[:80]}")',
     '\n    try:\n'
     '        _app_id = str(deal.get("lms_application_id") or "").strip()\n'
     '        if _app_id:\n'
     '            from utils.handover import journey as _journey\n'
     '            _journey(_app_id, "value_amended", user,\n'
     '                     "Value %s -> %s: %s"\n'
     '                     % (format(int(old_f), ","), format(int(new_value), ","),\n'
     '                        reason),\n'
     '                     was=old_f, now=new_value)\n'
     '    except Exception:\n'
     '        pass'),
]


def main():
    apply = "--apply" in sys.argv
    srcs = {}
    for f in (LMS, CAD, API):
        if not os.path.isfile(f):
            print("%s not found." % f)
            return 1
        srcs[f] = open(f, encoding="utf-8").read()
    if not os.path.isfile(os.path.join("utils", "handover.py")):
        print("utils/handover.py is not here - HV1 first.")
        return 1
    if "def journey(" not in open(os.path.join("utils", "handover.py"),
                                   encoding="utf-8").read():
        print("utils/handover.py has no journey() - copy the newer one in.")
        return 1

    done, missed, already = [], [], []
    for f, label, marker, anchor, call in WIRES:
        s = srcs[f]
        if marker in s:
            already.append(label)
            continue
        if s.count(anchor) != 1:
            missed.append((label, s.count(anchor)))
            continue
        srcs[f] = s.replace(anchor, anchor + call, 1)
        done.append(label)

    for l in done:
        print("  wired    %s" % l)
    for l in already:
        print("  already  %s" % l)
    for l, n in missed:
        print("  MISSED   %s (anchor matched %d)" % (l, n))
    if not done and not already:
        print("\nNothing wired.")
        return 1

    import ast
    for f, s in srcs.items():
        try:
            ast.parse(s)
        except SyntaxError as exc:
            print("%s would not parse - line %s: %s" % (f, exc.lineno, exc.msg))
            return 1

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    for f, s in srcs.items():
        if s != open(f, encoding="utf-8").read():
            shutil.copy2(f, f + ".pre_jn1")
            open(f, "w", encoding="utf-8", newline="").write(s)
            print("Applied %s" % f)
    import py_compile
    for f in srcs:
        py_compile.compile(f, doraise=True)
    print("  all compile")
    print("\nRestart uvicorn. Every handover from now on is on the journey.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
