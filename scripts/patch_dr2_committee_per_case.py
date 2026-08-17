#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
DR2 - the department committee is the one THIS case belongs to.

FOUND BY THE NAMING SCRIPT'S OWN WARNING (2026-08-15). Naming members to B2 and
B3 printed, three times: "the LMS roster is copied from B1, so it is left
alone." That was the system telling us something and it was worth reading.

credit_workflow.dcc is ONE COPY of ONE committee - whichever was last enabled,
which is B1. THREE endpoints read it:

    dcc/roster     what the voting panel renders
    dcc/vote       who is allowed to vote
    dcc/resolve    whose quorum and chair decide the outcome

So a Commercial case would have shown CONSUMER's voters, been judged against
Consumer's quorum, and required Consumer's chair - while the people actually
entitled to decide it appeared nowhere. Nobody would have noticed until a
Commercial case reached the gate, in front of the bank.

Same shape as every fault this fortnight: a single copy standing in for
something that varies, and three readers agreeing with each other and with
nothing else.

`_dcc_for_app` resolves from the CASE's client type against the palette, which
already knows. It falls back to the single copy when nothing matches, so a bank
with one department committee behaves exactly as before. A committee that is
NAMED BUT UNSTAFFED also falls back, rather than handing out a committee nobody
sits on.

Measured, with distinct people on each:

    Consumer / Individual / Personal  ->  Consumer committee
    Commercial                        ->  Commercial committee
    CIB / Large Corporate             ->  Corporate & Investment committee
    unknown or blank                  ->  the fallback

Verified: py_compile clean, the LMS router loads.

Usage (from project root, .venv active):
    python scripts\\patch_dr2_committee_per_case.py            # dry run
    python scripts\\patch_dr2_committee_per_case.py --apply
"""
import os
import shutil
import sys

ROUTES = os.path.join("utils", "api_lms_routes.py")
BACKUP_SUFFIX = ".pre_dr2"

OLD = '    dcc = (get_credit_workflow_config() or {}).get("dcc") or {}'
NEW = '    dcc = _dcc_for_app(app)'

HELPER = r'''
def _dcc_for_app(app: dict) -> dict:
    """The department committee THIS case belongs to.

    credit_workflow.dcc is ONE COPY of ONE committee - whichever was last
    enabled. Three endpoints read it: the roster the panel renders, the vote,
    and the resolution. So a Commercial case would show CONSUMER's voters, be
    judged against Consumer's quorum, and require Consumer's chair - while the
    people actually entitled to decide it appeared nowhere.

    The palette already knows which committee a case belongs to. Resolve from
    the CASE, and fall back to the single copy only when nothing matches - so a
    bank with one department committee behaves exactly as before.
    """
    cfg = get_credit_workflow_config() or {}
    dcc = dict(cfg.get("dcc") or {})

    seg = str((app or {}).get("client_type", "") or "").strip().lower()
    want = ""
    if "commercial" in seg:
        want = "commercial"
    elif seg == "cib" or "corporate" in seg or "investment" in seg:
        want = "corporate"
    elif ("consumer" in seg or "individual" in seg
          or seg in ("personal", "retail")):
        want = "consumer"
    if not want:
        return dcc

    for c in (cfg.get("committee_palette") or []):
        if str(c.get("kind", "")).lower() == "branch":
            continue
        if want not in str(c.get("name", "") or "").lower():
            continue
        members = [m for m in (c.get("members") or [])
                   if isinstance(m, dict)
                   and (str(m.get("staff_code", "")).strip()
                        or str(m.get("name", "")).strip())]
        if not members:
            # Named but unstaffed: keep the fallback rather than hand back a
            # committee nobody sits on.
            break
        return {
            "enabled": bool(dcc.get("enabled")),
            "name": c.get("name") or dcc.get("name"),
            "members": members,
            "chaired_by": c.get("chaired_by", ""),
            "chair_staff_code": c.get("chair_staff_code", ""),
            "voting_rule": c.get("voting_rule",
                                 dcc.get("voting_rule", "SIMPLE_MAJORITY")),
            "min_quorum_count": c.get("min_quorum_count"),
            "source_committee": c.get("code"),
        }
    return dcc

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(ROUTES):
        print("ABORT: %s not found." % ROUTES)
        return 1

    s = open(ROUTES, encoding="utf-8").read()
    if "_dcc_for_app" in s:
        print("ABORT: DR2 looks applied.")
        return 1
    n = s.count(OLD)
    if n != 3:
        print("ABORT: expected 3 call sites (roster, vote, resolve), found %d." % n)
        return 1

    i = s.index("\ndef lms_dcc_roster")
    i = s.rindex("\n@router.", 0, i)
    s = s[:i] + HELPER + s[i:]
    s = s.replace(OLD, NEW)
    print("  ok  one helper, 3 call site(s) resolve from the case")

    if "committee_palette" not in HELPER:
        print("ABORT: the helper does not consult the palette, so it could not")
        print("       find the right committee.")
        return 1
    if "return dcc" not in HELPER:
        print("ABORT: there is no fallback - a bank with one department")
        print("       committee would break.")
        return 1
    if "if not members" not in HELPER:
        print("ABORT: a NAMED BUT UNSTAFFED committee would be handed back, and")
        print("       a case sent there is invisible to everyone.")
        return 1
    if s.count(NEW) != 3:
        print("ABORT: %d call site(s) converted, expected 3." % s.count(NEW))
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: palette consulted, falls back, all three sites")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(ROUTES, ROUTES + BACKUP_SUFFIX)
    open(ROUTES, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % ROUTES)

    import py_compile
    try:
        py_compile.compile(ROUTES, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRestart uvicorn. A Commercial case now shows Commercial's voters.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
