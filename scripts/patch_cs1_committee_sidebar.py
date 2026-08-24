#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
CS1 - a seated committee member can reach the committee.

FOUND 2026-08-22, checking the eight official members the bank named:

    B1 Consumer   Jane Jelagat Atugah    Head of Consumer          NO
                  Robert Githaiga Maingi Head, Digital Channels    NO
                  Lunar Magero           Head of Sales             NO
                  Esther Wambui Mbano    Asset Product Manager     NO
    B2 Commercial Victor Mutabari Mbaabu Head EFS                  NO
                  Upendo Mutave Wambua   Head, SME                 NO
                  Livingstone Maina Kagio Head, Local Corporates   NO
                  Joshua Muthama         Head of Branches          NO

EIGHT OF EIGHT. Every one seated, sent cases, and unable to open the screen
where the committee lives.

THE CAUSE: the Department Review menu entry is gated on isCreditStaff, which
tests the ROLE STRING for credit|analys|underwrit|recover|collection|treasur|
disburs. "Head of Consumer" contains none of them. Nor should it - these are
business heads, and that is exactly who sits on a credit committee in a bank.
The committee is a governance body drawn from the business, not a department of
credit staff.

So the gate asks the wrong question. It asks what somebody's job is called,
when what matters is whether they have been seated on a committee.

WHAT THIS ADDS:

    GET /api/lms/committee/mine   ->  {"on_committee": true, "committees":
                                       [{"code": "B1", "name": "...",
                                         "is_chair": true}]}

    Sidebar shows Department Review when isCreditStaff OR on_committee.

THE SERVER GATE IS UNCHANGED. The vote endpoint already refuses a non-member
with a 403, and it still will. Hiding a menu entry was never the permission -
this only stops hiding it from people who are entitled to it.

WHY NOT WIDEN THE ROLE REGEX: because "Head" would let every manager in the
bank into Department Review, and because the next committee will be drawn from
people with titles nobody predicted. Membership is a fact in the config; a job
title is a guess about it.

NO AUTHENTICATION FILE IS TOUCHED. AuthProvider.tsx, types/auth.ts and Login
are all in the release DELTA and must never move - so the sidebar asks the
server directly rather than the user object growing a field.

Usage (from project root, .venv active):
    python scripts\patch_cs1_committee_sidebar.py            # dry run
    python scripts\patch_cs1_committee_sidebar.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api_lms_routes.py")
BAR = os.path.join("frontend", "web", "src", "components", "Sidebar.tsx")
CLI = os.path.join("frontend", "web", "src", "lib", "api.ts")
BACKUP_SUFFIX = ".pre_cs1"

API_ANCHOR = '''@router.get("/committee/tiers")'''

API_BLOCK = '''@router.get("/committee/mine")
def lms_my_committees(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Which credit committees, if any, this person sits on.

    The sidebar needs this because the Department Review entry was gated on
    the ROLE STRING - credit, analyst, underwriter and so on - and the eight
    people the bank actually seated are business heads: Head of Consumer, Head
    of SME, Head of Branches. Not one of them could open the screen where the
    committee lives.

    A committee is a governance body drawn from the business. Asking what
    somebody's job is called is the wrong question; whether they have been
    seated is the right one, and it is a fact in the config rather than a
    guess about a title.

    This grants no permission. The vote endpoint refuses a non-member with a
    403 and continues to.
    """
    from utils.api_lms_config import get_lms_config
    cfg = get_lms_config() or {}
    pal = (cfg.get("credit_workflow") or {}).get("committee_palette") or []

    code = str(user.get("staff_code", "") or "").strip().lower()
    name = str(user.get("full_name", "") or "").strip().lower()

    def _digits(v):
        import re as _re
        m = _re.match(r"^([A-Za-z]*)0*(\\d+)$", str(v or "").strip())
        return ("%s%s" % (m.group(1).upper(), m.group(2))) if m else ""

    want = _digits(code)
    mine = []
    for c in pal:
        for m in (c.get("members") or []):
            if not isinstance(m, dict):
                continue
            mc = str(m.get("staff_code", "") or "").strip()
            mn = str(m.get("name", "") or "").strip().lower()
            # KE0539 and KE539 are the same person - the padding was for DSA
            # codes and was never meant to split anybody in two.
            same = ((code and mc.lower() == code)
                    or (want and _digits(mc) == want)
                    or (name and mn == name))
            if same:
                mine.append({
                    "code": c.get("code"),
                    "name": c.get("name"),
                    "is_chair": (str(c.get("chaired_by", "") or "").strip().lower()
                                 == mn),
                })
                break

    return {"on_committee": bool(mine), "committees": mine}


'''

IMP_OLD = '''import { displayName } from "../lib/names";'''
IMP_NEW = '''import { useEffect, useState } from 'react';
import { displayName } from "../lib/names";'''

TYPE_OLD = '''  visibleFor?: (isMgr: boolean, isAdmin: boolean, isCfgAdmin: boolean, isAdminOrMd: boolean, isCreditStaff: boolean) => boolean;'''
TYPE_NEW = '''  // onCommittee is last and OPTIONAL, so every existing entry that takes
  // five arguments still satisfies the type. Adding it as required would have
  // meant editing thirty menu entries that do not care about it.
  visibleFor?: (isMgr: boolean, isAdmin: boolean, isCfgAdmin: boolean, isAdminOrMd: boolean, isCreditStaff: boolean, onCommittee?: boolean) => boolean;'''

BAR_IMP_API_OLD = '''import { isManager } from '@/lib/role';'''
BAR_IMP_API_NEW = '''import { isManager } from '@/lib/role';
import { fetchMyCommittees } from '@/lib/api';'''

BAR_OLD = '''  const isCreditStaff = isAdminOrMd || /credit|analys|underwrit|recover|collection|treasur|disburs/i.test(user?.role ?? '');'''

BAR_NEW = '''  const isCreditStaff = isAdminOrMd || /credit|analys|underwrit|recover|collection|treasur|disburs/i.test(user?.role ?? '');

  // ── A SEATED COMMITTEE MEMBER CAN REACH THE COMMITTEE ────────────────────
  // The rule above asks what somebody's job is CALLED. The eight people the
  // bank seated on its Consumer and Commercial credit committees are business
  // heads - Head of Consumer, Head of SME, Head of Branches - and not one of
  // their titles contains a word in that list. All eight were seated, sent
  // cases, and unable to open the screen where the committee lives.
  //
  // A committee is a governance body drawn from the business. Membership is a
  // fact in the config; a job title is a guess about it.
  //
  // This hides nothing new and grants nothing: the vote endpoint refuses a
  // non-member with a 403 either way.
  const [onCommittee, setOnCommittee] = useState(false);
  useEffect(() => {
    let alive = true;
    fetchMyCommittees()
      .then((r) => { if (alive) setOnCommittee(Boolean(r?.on_committee)); })
      // A sidebar must render even when this call fails. Falling back to the
      // role rule is the old behaviour, which is wrong for eight people but
      // not broken for anybody.
      .catch(() => { if (alive) setOnCommittee(false); });
    return () => { alive = false; };
  }, [user?.username]);'''

BAR_USE_OLD = '''visibleFor: (_m, _a, _c, _md, credit) => credit },
    ],
  },
  {
    label: 'Credit Intelligence (CIS)','''

BAR_USE_NEW = '''visibleFor: (_m, _a, _c, _md, credit, committee) => credit || Boolean(committee) },
    ],
  },
  {
    label: 'Credit Intelligence (CIS)','''

BAR_CALL_OLD = '''item.visibleFor(isMgr, isAdmin, isCfgAdmin, isAdminOrMd, isCreditStaff)'''
BAR_CALL_NEW = '''item.visibleFor(isMgr, isAdmin, isCfgAdmin, isAdminOrMd, isCreditStaff, onCommittee)'''

CLI_ANCHOR = '''export async function fetchWarehouseShelves('''

CLI_BLOCK = '''/** Which credit committees this person sits on.
 *
 *  The sidebar needs it because the Department Review entry is gated on the
 *  role string, and the eight people the bank seated on its Consumer and
 *  Commercial committees are business heads whose titles contain no credit
 *  word at all. Membership is a fact; a job title is a guess about it.
 */
export async function fetchMyCommittees(): Promise<{
  on_committee: boolean;
  committees: { code: string; name: string; is_chair: boolean }[];
}> {
  return getJson<{
    on_committee: boolean;
    committees: { code: string; name: string; is_chair: boolean }[];
  }>('/lms/committee/mine');
}

'''


def main():
    apply = "--apply" in sys.argv
    for f in (API, BAR, CLI):
        if not os.path.isfile(f):
            print("ABORT: %s not found." % f)
            return 1

    a = open(API, encoding="utf-8").read()
    b = open(BAR, encoding="utf-8").read()
    c = open(CLI, encoding="utf-8").read()
    if "/committee/mine" in a and "A SEATED COMMITTEE MEMBER CAN REACH" in b:
        print("ABORT: CS1 looks applied.")
        return 1
    for nm, src, anch, n in (("the api", a, API_ANCHOR, 1),
                             ("the sidebar", b, BAR_OLD, 1),
                             ("the sidebar gate", b, BAR_USE_OLD, 1),
                             ("the sidebar call", b, BAR_CALL_OLD, 1),
                             ("the client", c, CLI_ANCHOR, 1),
                             ("the sidebar imports", b, IMP_OLD, 1),
                             ("the role import", b, BAR_IMP_API_OLD, 1),
                             ("the NavItem type", b, TYPE_OLD, 1)):
        if src.count(anch) != n:
            print("ABORT: %s anchor matched %d times, expected %d."
                  % (nm, src.count(anch), n))
            return 1

    a = a.replace(API_ANCHOR, API_BLOCK + API_ANCHOR, 1)
    b = (b.replace(TYPE_OLD, TYPE_NEW, 1)
          .replace(IMP_OLD, IMP_NEW, 1)
          .replace(BAR_IMP_API_OLD, BAR_IMP_API_NEW, 1)
          .replace(BAR_OLD, BAR_NEW, 1)
          .replace(BAR_USE_OLD, BAR_USE_NEW, 1)
          .replace(BAR_CALL_OLD, BAR_CALL_NEW, 1))
    c = c.replace(CLI_ANCHOR, CLI_BLOCK + CLI_ANCHOR, 1)
    print("  ok  the server reports membership; the sidebar honours it")

    if "import { useEffect, useState } from 'react'" not in b:
        print("ABORT: the React hooks are not imported in the sidebar.")
        return 1
    if "onCommittee?: boolean" not in b:
        print("ABORT: the NavItem type still takes five arguments, so the")
        print("       sixth would not typecheck.")
        return 1
    if "fetchMyCommittees" not in b:
        print("ABORT: the client call is missing.")
        return 1
    if "403" not in API_BLOCK:
        print("ABORT: the docstring must say the server gate is unchanged -")
        print("       a menu entry is not a permission and the next reader")
        print("       must not mistake this for one.")
        return 1
    for must in ("AuthProvider", "types/auth"):
        if must in API_BLOCK or must in BAR_NEW:
            print("ABORT: this touches an authentication file.")
            return 1
    import ast
    try:
        ast.parse(a)
    except SyntaxError as exc:
        print("ABORT: the api would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    if b.count("{") != b.count("}") or b.count("(") != b.count(")"):
        print("ABORT: the sidebar braces are unbalanced.")
        return 1
    print("  ok  post-checks: no auth file touched, balanced, gate documented")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, src in ((API, a), (BAR, b), (CLI, c)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(src)
        print("APPLIED %s" % path)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
