#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
SEG1 - the Consumer credit analyst can submit to the DCC again.

RULING (2026-08-12): Catherine, the Consumer credit analyst, could open a case
and had no way to send it on. "There was to be a differentiator between the one
for the credit analyst and the department analyst, in that Catherine is to also
be able to attach a few documents, then submit to Department Credit Committee
stage once she recommends."

THE PANEL ALREADY EXISTED. SubmitToDccPanel is in the page, gated on
`can_submit_to_dcc`. The permission was the fault, and it is a precise one:

    _analyst_segment(role, staff_code)

Its own docstring says role alone is ambiguous - "Credit Analyst" spans Consumer
and Commercial, and the DEPARTMENT disambiguates. Both call sites in
api_lms_permissions.py passed the ROLE ONLY:

    _analyst_segment(_role)                              <- self-pick
    _analyst_segment(str(user.get("role", "") or ""))    <- submit to DCC

So every plain "Credit Analyst" resolved to "" - which is FALSY, so the gate
closed and nothing was logged. Catherine's role reads "Credit Analyst", so she
lost the ability to refer a case onward, silently.

Measured before the fix:

    Credit Analyst              -> ''            panel hidden
    Consumer Credit Analyst     -> 'consumer'    panel shown
    Commercial Credit Analyst   -> 'commercial'  panel shown

Only the people whose title happens to spell out their segment worked. That is
why it looked intermittent rather than broken.

THE SAME DEFECT PATTERN AS THE OTHERS THIS WEEK: a function that needs two
arguments called with one, returning a falsy default that a gate reads as "no".
The guard pattern in OPERATIONAL_PROTOCOL says check the DEFINITION, not the
name - this is the argument-list version of it.

SO IT NO LONGER FAILS SILENTLY. Called without a staff code, _analyst_segment
now WARNS that the segment cannot be resolved and the caller will be treated as
having none. It still returns "" - raising would take down a page over a
permission hint - but the next person gets a thread to pull instead of a blank
screen.

scripts/diag_identity.py --segments lists every analyst login with the segment
it resolves to, so the fix can be proved rather than hoped for.

Verified: py_compile clean; both call sites now pass the staff code, checked by
balancing brackets rather than by a regex that stopped at the first one.

Usage (from project root, .venv active):
    python scripts\patch_seg1_analyst_segment.py            # dry run
    python scripts\patch_seg1_analyst_segment.py --apply
"""
import os
import re
import shutil
import sys

PERM = os.path.join("utils", "api_lms_permissions.py")
SCOPE = os.path.join("utils", "api_lms_scope.py")
DIAG = os.path.join("scripts", "diag_identity.py")
BACKUP_SUFFIX = ".pre_seg1"

SELF_PICK_OLD = "                _seg = _analyst_segment(_role)"
DCC_OLD = '            if _da.get("enabled") and _analyst_segment(str(user.get("role", "") or "")):'
AMB_OLD = '''    if "credit analyst" in rl:
        dept = _staff_department(staff_code).lower()'''

SELF_PICK = r'''                # ROLE ALONE IS AMBIGUOUS. _analyst_segment's own docstring
                # says so: "Credit Analyst" spans Consumer and Commercial, and
                # the DEPARTMENT is what disambiguates. Called with the role
                # only, it returns "" for every plain "Credit Analyst" - and ""
                # is falsy, so the branch silently took the wrong path with no
                # error anywhere.
                _seg = _analyst_segment(_role, str(user.get("staff_code", "") or ""))'''

DCC = r'''    # ── can_submit_to_dcc ──
    # The assigned Department Analyst (segment-specific) voices support and
    # submits the case to the Department Credit Committee. They CANNOT decide —
    # this only refers the case onward. Gated: the Department Analyst layer must
    # be enabled and the caller must be a segment-specific analyst assigned to an
    # 'assigned' case. Completeness (Call-Back Memo + PEP) is enforced at the
    # endpoint, not here.
    can_submit_to_dcc = False
    try:
        if is_assigned_analyst and status == "assigned" and not app.get("dcc_outcome"):
            from utils.api_lms_scope import _analyst_segment
            from utils.api_lms_mutations import get_credit_workflow_config
            _da = (get_credit_workflow_config() or {}).get("department_analyst") or {}
            # Same defect here, and this is the one the pilot hit: Catherine is
            # a Consumer Credit Analyst whose role reads "Credit Analyst", so
            # this resolved to "" and can_submit_to_dcc stayed False. She could
            # analyse a case and had no way to send it on.
            if _da.get("enabled") and _analyst_segment(
                    str(user.get("role", "") or ""),
                    str(user.get("staff_code", "") or "")):
                can_submit_to_dcc = True
    except Exception:
        can_submit_to_dcc = False

'''

AMBIGUOUS = r'''    if "credit analyst" in rl:
        # THE AMBIGUOUS CASE, and the one that bit the pilot. "Credit Analyst"
        # spans Consumer and Commercial, so only the department can tell them
        # apart - and a caller that forgets the staff code gets "" here, which
        # is falsy and silently takes every gated branch the wrong way. It cost
        # a Consumer analyst her ability to submit to the DCC, with no error
        # raised anywhere.
        #
        # Now it says so in the log rather than shrugging. Still returns "" -
        # raising would take down a page over a permission hint - but the next
        # person gets a thread to pull instead of a blank screen.
        if not str(staff_code or "").strip():
            logger.warning(
                "_analyst_segment(%r) called without a staff_code: the segment "
                "cannot be resolved from the role alone, so this caller will be "
                "treated as having NO segment.", role)
'''

DIAG_SRC = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Does every login point at the right person? READ ONLY. Exit 1 on a mismatch.

RULING (2026-08-12): "a staff named Joshua Kyuma was seeing his profile on all
the pages, but on the balanced scorecard he was seeing that of Joshua Muthama.
Probably the issue is on the staff payroll, which we might have guessed for
Joshua sometime."

WHY THIS SHOWS UP ONLY ON THE SCORECARD. Most pages display the name carried in
the SESSION, which is right. The scorecard resolves the person by STAFF CODE and
looks them up in the register - so a user record carrying the wrong code shows
the correct name everywhere and the wrong scorecard in one place. The
inconsistency is invisible until somebody opens their own scorecard and does not
recognise the numbers.

That makes it a bad class of bug: silent, and wrong in the direction of somebody
seeing another person's performance.

WHAT THIS CHECKS, for every login:

    the staff code on the user record exists in the register
    the name on the user record matches the name against that code
    no two logins share a staff code
    no two register rows share a staff code
    people who share a SURNAME or a FIRST NAME are listed, because that is
        where a guessed code does its damage and nobody notices

IT NAMES THE CORRECTION rather than making it - a script that rewrites identity
records unattended is not something to run on a payroll.

    python scripts\\diag_identity.py
    python scripts\\diag_identity.py --name Joshua
"""
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.getcwd())


def check_analyst_segments():
    """Can every credit analyst be told apart by segment?

    A Consumer and a Commercial analyst can share the role "Credit Analyst",
    so the DEPARTMENT is the only thing that separates them. An analyst whose
    segment does not resolve is treated as having none - which quietly removes
    their ability to submit a case to the Department Credit Committee.
    """
    from utils.core import UserManager
    from utils.api_lms_scope import _analyst_segment
    users = UserManager().users or {}
    rows = []
    for uname, u in users.items():
        role = str(u.get("role") or "")
        if "analyst" not in role.lower():
            continue
        code = str(u.get("staff_code") or "")
        rows.append((uname, role, code,
                     _analyst_segment(role, code),
                     _analyst_segment(role)))
    if not rows:
        print("  no analyst logins found")
        return
    print("  %-18s %-30s %-9s %-11s %s"
          % ("login", "role", "code", "segment", "was (role only)"))
    for uname, role, code, seg, old in sorted(rows):
        flag = "  " if seg else "**"
        print("  %s%-16s %-30s %-9s %-11s %s"
              % (flag, uname[:16], role[:30], code[:9], seg or "NONE",
                 old or "NONE"))
    broken = [r for r in rows if not r[3]]
    if broken:
        print("\n  %d analyst(s) resolve to NO segment even with their staff code."
              % len(broken))
        print("  They cannot submit to the Department Credit Committee. Check")
        print("  their Department in the register reads Consumer, Commercial or")
        print("  Corporate.")


def main():
    focus = ""
    if "--name" in sys.argv:
        i = sys.argv.index("--name")
        if i + 1 < len(sys.argv):
            focus = sys.argv[i + 1].strip().lower()

    try:
        from utils.core import UserManager
        from utils.api_pipeline_scope import get_staff_roster
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    try:
        df = get_staff_roster()
    except Exception as exc:
        print("ABORT: staff register unavailable: %s" % exc)
        return 1

    reg = {}
    for _i, r in df.iterrows():
        code = str(r.get("Staff Code") or "").strip()
        if code:
            reg[code] = {"name": str(r.get("Staff Name") or "").strip(),
                         "role": str(r.get("Role") or "").strip(),
                         "unit": str(r.get("Unit") or "").strip()}

    users = UserManager().users or {}

    print("=" * 78)
    print("IDENTITY CHECK")
    print("=" * 78)
    print("  register  %d staff" % len(reg))
    print("  logins    %d" % len(users))

    problems = []

    # 1. Duplicate codes in the register itself.
    dupes = [c for c, n in Counter(
        str(r.get("Staff Code") or "").strip()
        for _i, r in df.iterrows()).items() if c and n > 1]
    if dupes:
        problems.append("register has duplicate staff codes: %s" % ", ".join(dupes[:6]))

    # 2. Two logins claiming one staff code. This is the shape that puts one
    #    person on another's scorecard.
    by_code = defaultdict(list)
    for uname, u in users.items():
        code = str(u.get("staff_code") or "").strip()
        if code:
            by_code[code].append(uname)
    shared = {c: names for c, names in by_code.items() if len(names) > 1}

    # 3. Name on the login vs name against its code.
    mismatches = []
    orphans = []
    for uname, u in users.items():
        code = str(u.get("staff_code") or "").strip()
        uname_full = str(u.get("full_name") or u.get("name") or "").strip()
        if not code:
            continue
        row = reg.get(code)
        if not row:
            orphans.append((uname, code, uname_full))
            continue
        a = " ".join(uname_full.lower().split())
        b = " ".join(row["name"].lower().split())
        if a and b and a != b:
            # Same person written two ways is not a mismatch worth shouting
            # about; a DIFFERENT SURNAME is.
            if set(a.split()) & set(b.split()):
                mismatches.append((uname, code, uname_full, row["name"], "partial"))
            else:
                mismatches.append((uname, code, uname_full, row["name"], "different"))

    print("\n" + "-" * 78)
    print("LOGINS WHOSE NAME DOES NOT MATCH THEIR STAFF CODE")
    print("-" * 78)
    if not mismatches:
        print("  none")
    for uname, code, shown, actual, kind in mismatches:
        flag = "***" if kind == "different" else "   "
        print("  %s %-16s code %-8s login says %-28s register says %s"
              % (flag, uname, code, shown[:28], actual[:28]))
        if kind == "different":
            problems.append("%s (code %s) is named %r but that code belongs to %r"
                            % (uname, code, shown, actual))

    if shared:
        print("\n" + "-" * 78)
        print("STAFF CODES CLAIMED BY MORE THAN ONE LOGIN")
        print("-" * 78)
        for code, names in shared.items():
            print("  *** %-8s %s   -> %s"
                  % (code, ", ".join(names), reg.get(code, {}).get("name", "not in register")))
            problems.append("code %s is claimed by %d logins" % (code, len(names)))

    if orphans:
        print("\n" + "-" * 78)
        print("LOGINS POINTING AT A CODE THAT IS NOT IN THE REGISTER")
        print("-" * 78)
        for uname, code, shown in orphans[:10]:
            print("      %-16s code %-8s %s" % (uname, code, shown[:30]))
        problems.append("%d login(s) point at a code not in the register" % len(orphans))

    # 4. WHERE A GUESS DOES ITS DAMAGE: people who share a name fragment.
    print("\n" + "-" * 78)
    print("PEOPLE SHARING A NAME - where a guessed code goes unnoticed")
    print("-" * 78)
    parts = defaultdict(list)
    for code, r in reg.items():
        for p in r["name"].split():
            if len(p) > 2:
                parts[p.lower()].append((code, r["name"], r["role"]))
    shown_any = False
    for part, people in sorted(parts.items()):
        if len(people) < 2:
            continue
        if focus and part != focus:
            continue
        if not focus and len(people) < 3:
            continue
        shown_any = True
        print("  %s (%d)" % (part.title(), len(people)))
        for code, nm, role in sorted(people)[:8]:
            login = ", ".join(by_code.get(code, [])) or "no login"
            print("      %-8s %-30s %-26s [%s]" % (code, nm[:30], role[:26], login))
    if not shown_any:
        print("  none to show")

    if "--segments" in sys.argv:
        print("\n" + "-" * 78)
        print("ANALYST SEGMENT RESOLUTION")
        print("-" * 78)
        try:
            check_analyst_segments()
        except Exception as exc:
            print("  could not check: %s" % exc)

    print("\n" + "=" * 78)
    if not problems:
        print("Every login resolves to the person it claims.")
        return 0
    print("%d PROBLEM(S):\n" % len(problems))
    for p in problems:
        print("   * %s" % p)
    print("")
    print("NOT corrected automatically. Rewriting identity records unattended is")
    print("not something to run against a payroll - fix the staff_code on the")
    print("login in users.json, or the row in the register, whichever is wrong.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
'''


def _calls(src):
    """Every _analyst_segment(...) call, with brackets balanced.

    A regex stops at the first ')' - which is inside user.get() - and reports a
    correct call as missing its argument. That happened while writing this.
    """
    flat = re.sub(r"\s+", " ", src)
    out, i = [], 0
    while True:
        i = flat.find("_analyst_segment(", i)
        if i < 0:
            return out
        d, j = 0, i + len("_analyst_segment")
        for k in range(j, len(flat)):
            if flat[k] == "(":
                d += 1
            elif flat[k] == ")":
                d -= 1
                if d == 0:
                    out.append(flat[i:k + 1])
                    i = k
                    break
        i += 1


def main():
    apply = "--apply" in sys.argv
    for p in (PERM, SCOPE):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1

    perm = open(PERM, encoding="utf-8").read()
    scope = open(SCOPE, encoding="utf-8").read()

    if "ROLE ALONE IS AMBIGUOUS" in perm:
        print("ABORT: SEG1 looks applied.")
        return 1
    if perm.count(SELF_PICK_OLD) != 1 or perm.count(DCC_OLD) != 1:
        print("ABORT: call sites matched %d / %d times."
              % (perm.count(SELF_PICK_OLD), perm.count(DCC_OLD)))
        return 1
    if scope.count(AMB_OLD) != 1:
        print("ABORT: the ambiguous branch matched %d times." % scope.count(AMB_OLD))
        return 1

    perm = perm.replace(SELF_PICK_OLD, SELF_PICK, 1)
    i = perm.index("    # ── can_submit_to_dcc ──")
    j = perm.index("    # ── can_hand_to_credit_analyst ──")
    perm = perm[:i] + DCC + perm[j:]
    scope = scope.replace(AMB_OLD, AMBIGUOUS + '        dept = _staff_department(staff_code).lower()', 1)
    if "\nimport logging\n" not in scope:
        anchor = "from __future__ import annotations\n"
        if anchor not in scope:
            print("ABORT: cannot place the logger - no __future__ import found.")
            return 1
        scope = scope.replace(
            anchor, anchor + "\nimport logging\n\nlogger = logging.getLogger(__name__)\n", 1)
    print("  ok  both call sites, and the ambiguous branch warns")

    # EVERY call must carry the staff code, checked with balanced brackets.
    bad = [c for c in _calls(perm) if "staff_code" not in c]
    if bad:
        print("ABORT: %d call(s) still pass the role only:" % len(bad))
        for c in bad:
            print("       %s" % c[:80])
        return 1
    print("  ok  %d call site(s), all carrying the staff code" % len(_calls(perm)))

    if "called without a staff_code" not in AMBIGUOUS:
        print("ABORT: the ambiguous case would still fail silently - which is")
        print("       how this cost a Consumer analyst her DCC submission with")
        print("       no error anywhere.")
        return 1

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((PERM, perm), (SCOPE, scope)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)
    open(DIAG, "w", encoding="utf-8", newline="").write(DIAG_SRC)
    print("APPLIED %s" % DIAG)

    import py_compile
    for path in (PERM, SCOPE):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("")
    print("Restart uvicorn, then prove it rather than hope:")
    print("  python scripts\\diag_identity.py --segments")
    print("")
    print("Every analyst login should show a segment. Any showing NONE has a")
    print("Department in the register that does not read Consumer, Commercial")
    print("or Corporate - and that is data, not code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
