#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
DV2 - somebody can be added to the validation team while colleagues are away.

FROM THE BANK (2026-09-03): "adding a member to the validation committee - I
need that enabled from admin. I already have a request to add Osoro Hilda of
Kisumu branch to the validation team since most of the other members are away."

THERE IS NO VALIDATION TEAM TO ADD HER TO. Validation authority is DERIVED from
the register: branches_validated_by returns the branches whose Branch Manager
reports to you, or every branch if you hold an all-view role. There is no list
anywhere, so there is nothing an admin can edit.

That design is sound - authority follows the reporting line, which is how a
bank works - but it has no answer for cover. When the people who normally
validate Kisumu are away, the work stops, and the only way to move it is to
change somebody's reporting line in the register, which is a lie that outlives
the absence.

WHAT THIS ADDS: a delegation list in org_config.json, consulted IN ADDITION to
the hierarchy.

    "delegated_validators": [
      {"staff_code": "KE1234", "name": "Osoro Hilda",
       "branches": ["Kisumu"], "until": "2026-09-30",
       "reason": "cover while the regular validators are away",
       "added_by": "KE1158", "added_at": "2026-09-03"}
    ]

EVERY DELEGATION EXPIRES. `until` is required and enforced on read - a
delegation with no end date, or one that has passed, grants nothing. Cover for
an absence that quietly becomes permanent authority nobody remembers granting
is precisely what an auditor asks about.

IT ADDS, NEVER REMOVES. A delegation cannot take a branch away from the person
whose reporting line gives it to them.

THE REASON IS REQUIRED. In six months somebody will ask why Hilda could
validate Kisumu, and "it is in the config" is not an answer.

Usage (from project root, .venv active):
    python scripts\patch_dv2_delegated_validators.py            # dry run
    python scripts\patch_dv2_delegated_validators.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "org_validator.py")
BACKUP_SUFFIX = ".pre_dv2"

HELPER_ANCHOR = "def branches_validated_by(validator_code: str) -> dict:"

HELPER = '''def _delegated_branches(validator_code: str) -> list:
    """Branches this person may validate by DELEGATION, not by reporting line.

    Validation authority is derived from the register - you validate the
    branches whose Branch Manager reports to you. That is right, and it has no
    answer for cover: when the people who normally validate a branch are away,
    the work stops, and the only way to move it is to change a reporting line,
    which is a lie that outlives the absence.

    A delegation is an explicit, dated, reasoned exception. It ADDS branches
    and never removes them.

    EVERY DELEGATION EXPIRES. One with no `until`, or one that has passed,
    grants nothing - cover for an absence that quietly becomes permanent
    authority nobody remembers granting is what an auditor asks about.
    """
    import datetime as _dt
    vc = _s(validator_code)
    if not vc:
        return []
    try:
        from utils.api_branding import load_org_config
        rows = (load_org_config() or {}).get("delegated_validators") or []
    except Exception as exc:
        try:
            import logging
            logging.getLogger(__name__).warning(
                "could not read delegated_validators: %s", exc)
        except Exception:
            pass
        return []

    today = _dt.date.today().isoformat()
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        if _s(r.get("staff_code")) != vc:
            continue
        until = str(r.get("until") or "").strip()
        # No end date is not "for ever" - it is an incomplete delegation.
        if not until or until < today:
            continue
        for b in (r.get("branches") or []):
            b = str(b or "").strip()
            if b and b not in out:
                out.append(b)
    return out


'''

OLD_TAIL = '''    mine = sorted({b for b in bcol[mask].tolist() if b})
    return {"mode": "branch" if mine else "", "branches": mine, "all_view": False}'''

NEW_TAIL = '''    mine = sorted({b for b in bcol[mask].tolist() if b})

    # ── PLUS ANYTHING DELEGATED WHILE COLLEAGUES ARE AWAY ───────────────────
    # Added, never removed: a delegation cannot take a branch away from the
    # person whose reporting line gives it to them.
    for _b in _delegated_branches(vc):
        if _b not in mine:
            mine.append(_b)
    mine = sorted(mine)

    return {"mode": "branch" if mine else "", "branches": mine, "all_view": False}'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "_delegated_branches" in s:
        print("ABORT: DV2 looks applied.")
        return 1
    if s.count(HELPER_ANCHOR) != 1 or s.count(OLD_TAIL) != 1:
        print("ABORT: anchors matched %d / %d times."
              % (s.count(HELPER_ANCHOR), s.count(OLD_TAIL)))
        return 1

    s = s.replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)
    s = s.replace(OLD_TAIL, NEW_TAIL, 1)
    print("  ok  a dated delegation adds branches to a validator")

    if "until < today" not in HELPER or "not until" not in HELPER:
        print("ABORT: a delegation without an end date, or a lapsed one, would")
        print("       grant authority for ever. That is the thing an auditor")
        print("       asks about.")
        return 1
    if "if _b not in mine" not in NEW_TAIL:
        print("ABORT: the delegation must ADD, never replace what the")
        print("       reporting line already grants.")
        return 1
    if "logging" not in HELPER:
        print("ABORT: a failed config read must say so - silence here would")
        print("       revoke a delegation without anybody knowing.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: expires, adds only, failures are logged")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + BACKUP_SUFFIX)
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN, then add somebody with:")
    print("   python scripts\\delegate_validator.py --staff KE1234 \\")
    print("       --branches Kisumu --until 2026-09-30 --reason \"cover\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
