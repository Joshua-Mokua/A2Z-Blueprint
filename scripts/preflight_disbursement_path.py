#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Walk the path from committee to disbursed and say what will stop a case.

Every fault this fortnight was invisible until somebody tried. This checks
each gate on the way to a disbursement while there is still time to fix it.

    python scripts/preflight_disbursement_path.py

Read only.
"""
import os
import sys

sys.path.insert(0, os.getcwd())

OK, BAD = "ok", "***"


def main():
    from utils.core import UserManager
    users = [dict(v, username=k) for k, v in (UserManager().users or {}).items()
             if v.get("active")]
    problems = []

    def check(label, passed, detail=""):
        print("  %-4s %-46s %s" % (OK if passed else BAD, label, detail))
        if not passed:
            problems.append((label, detail))

    print("=" * 92)
    print("THE PATH FROM COMMITTEE TO DISBURSED")
    print("=" * 92)

    # 1. A committee recommendation must show on the case.
    try:
        s = open(os.path.join("utils", "api.py"), encoding="utf-8").read()
        check("a committee recommendation marks the case",
              "AND SAY SO ON THE CREDIT CASE" in s,
              "" if "AND SAY SO ON THE CREDIT CASE" in s
              else "CS2 not applied - credit risk can be pointed at nothing")
        check("only a DEPARTMENT committee sends it to credit risk",
              "ONLY A DEPARTMENT COMMITTEE SENDS" in s,
              "" if "ONLY A DEPARTMENT COMMITTEE SENDS" in s
              else "CS3 not applied - branch cases will land on credit risk")
        check("a committee cannot strand an unsubmitted deal",
              "NOT WITHOUT A CREDIT CASE" in s,
              "" if "NOT WITHOUT A CREDIT CASE" in s
              else "CA1 not applied - see D0644")
    except Exception as exc:
        check("could read utils/api.py", False, str(exc)[:50])

    # 2. Credit risk can see and decide.
    try:
        from utils.api_lms_scope import get_pool_visibility_config, _role_sees_pool
        cfg = get_pool_visibility_config()
        cr = [u for u in users if "credit risk" in str(u.get("role", "")).lower()]
        check("somebody holds a credit risk role", bool(cr),
              "" if cr else "nobody will decide these cases")
        if cr:
            role = str(cr[0].get("role"))
            check("credit risk sees the pool", _role_sees_pool(role, cfg["roles"]),
                  "" if _role_sees_pool(role, cfg["roles"])
                  else "add the role: add_pool_role.py")
            per = (cfg.get("role_statuses") or {})
            narrowed = [v for k, v in per.items()
                        if str(k).lower() in role.lower()]
            want = "committee_recommended"
            has = bool(narrowed) and any(want in [str(x).lower() for x in n]
                                         for n in narrowed)
            check("credit risk is pointed at committee_recommended", has,
                  "" if has else "set_pool_statuses_for_role.py --role "
                                 "\"credit risk\" --statuses committee_recommended")
    except Exception as exc:
        check("could read the pool config", False, str(exc)[:50])

    try:
        s = open(os.path.join("utils", "api_lms_routes.py"), encoding="utf-8").read()
        check("the assigned analyst can record a decision",
              "no manager step in that flow" in s,
              "" if "no manager step in that flow" in s
              else "DC1 not applied - the buttons will 403")
    except Exception:
        pass

    # 3. The conditions the decision carries.
    try:
        import json
        d = json.load(open(os.path.join("data", "lms_config.json"),
                           encoding="utf-8"))
        lib = d.get("condition_library") or {}
        n = len(lib.get("pre_approval") or []) + len(lib.get("pre_disbursement") or [])
        check("the condition library is seeded", n > 0,
              "%d conditions" % n if n else
              "set_condition_library.py --seed - credit admin gets no tick-list")
    except Exception as exc:
        check("could read lms_config", False, str(exc)[:50])

    # 4. Credit admin can see and work the case.
    try:
        from utils.api_credit_admin_scope import _is_credit_admin_department_role
        ca = [u for u in users
              if _is_credit_admin_department_role({"role": str(u.get("role", ""))})]
        check("somebody matches a credit admin role", bool(ca),
              "%d people" % len(ca) if ca else
              "nobody can see a credit admin case")
        head = [u for u in users if "cad" in str(u.get("role", "")).lower()]
        if head:
            ok = _is_credit_admin_department_role({"role": str(head[0].get("role"))})
            check("Head, CAD matches", ok,
                  "" if ok else "CAD1 not applied")
    except Exception as exc:
        check("could read the credit admin scope", False, str(exc)[:50])

    # 5. TROPS can see and disburse.
    try:
        import json
        ps = json.load(open(os.path.join("data", "pipeline_settings.json"),
                            encoding="utf-8"))
        roles = [str(r).lower() for r in (ps.get("disbursement_roles")
                                          or ["Treasury Back Office"])]
        can = [u for u in users
               if any(r in str(u.get("role", "")).lower() for r in roles)
               or any(k in str(u.get("role", "")).lower()
                      for k in ("chief", "managing", "director"))
               or u.get("is_admin")]
        check("somebody can complete a disbursement", bool(can),
              "%d people" % len(can) if can else
              "set_disbursement_roles.py --add trops - NOBODY can disburse")
        s = open(os.path.join("utils", "api_credit_admin_scope.py"),
                 encoding="utf-8").read()
        check("TROPS can see credit admin cases", "_re_trops" in s,
              "" if "_re_trops" in s else "TR1 not applied")
    except Exception as exc:
        check("could read the disbursement roles", False, str(exc)[:50])

    # 6. The database can hold what they do.
    try:
        from utils.db import db
        ok = False
        try:
            with db.conn() as c:
                cur = c.cursor()
                cur.execute("SELECT to_regclass('credit_admin')")
                ok = cur.fetchone()[0] is not None
        except Exception:
            ok = False
        check("the credit_admin table exists", ok,
              "" if ok else "apply_credit_admin_schema.py - cases will live "
                            "only in JSON")
    except Exception:
        check("could not check the database", False, "check by hand")

    # 7. The funnel and the cases agree.
    try:
        s = open(os.path.join("utils", "core.py"), encoding="utf-8").read()
        check("a deal's stage follows its case",
              "WHERE A CASE STANDS, AND WHERE ITS DEAL SHOULD" in s,
              "" if "WHERE A CASE STANDS, AND WHERE ITS DEAL SHOULD" in s
              else "SOT1 not applied - the funnel will drift again")
    except Exception:
        pass

    print("\n" + "=" * 92)
    if not problems:
        print("Every gate on the path is open. Walk one case through and watch it.")
        print("=" * 92)
        return 0
    print("THESE WILL STOP A CASE: %d" % len(problems))
    print("=" * 92)
    for label, detail in problems:
        print("  %-46s %s" % (label, detail))
    print("\n  Each is a command, not a build. Fix them before the first case")
    print("  moves rather than while somebody is waiting on it.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
