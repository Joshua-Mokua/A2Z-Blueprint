#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""When a committee recommends, say so on the credit case.

A committee close writes its outcome onto the DEAL and advances the deal's
stage. It never touches the application. So a case stays at
'referred_to_committee' whether the committee has met or not, and nothing
downstream can tell the difference.

That is why credit risk cannot be pointed at a status: there is no status that
means "the committee recommended this". Korir was narrowed to 'approved', which
nothing ever reaches, so he kept seeing the analysts' fresh submissions
instead.

Sets the application to 'committee_recommended' when a committee closes with an
approval. Nothing else changes - the deal, its stage and the committee record
are written exactly as before.

    python scripts/patch_cs2_committee_approval_shows_on_the_case.py            # dry run
    python scripts/patch_cs2_committee_approval_shows_on_the_case.py --apply

Then point credit risk at it:
    python scripts/set_pool_statuses_for_role.py --role "credit risk" \
        --statuses committee_recommended --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")

OLD = '        updates["committee_records"] = records'

NEW = '''        updates["committee_records"] = records

        # ── AND SAY SO ON THE CREDIT CASE ────────────────────────────────────
        # The committee's outcome was written onto the deal and nowhere else,
        # so a case read 'referred_to_committee' whether the committee had met
        # or not. Nothing downstream could tell a recommended case from one still
        # waiting, and credit risk could not be pointed at a status because
        # there was no status that meant "the committee recommended this".
        #
        # Best effort: a committee decision must never fail because the case
        # could not be updated. But it is recorded either way.
        if str(outcome).upper() in ("APPROVED", "RECOMMENDED", "SUPPORTED"):
            _app_id = str(deal.get("lms_application_id") or "").strip()
            if _app_id:
                try:
                    from utils.api_lms_routes import _lam as _lam_for_cttee
                    _lam_for_cttee().update(_app_id, {
                        "status": "committee_recommended",
                        "committee_recommended_by": code,
                        "committee_recommended_at": _dt_now_iso(),
                    })
                    _audit("API_COMMITTEE_CASE_APPROVED", user,
                           f"app={_app_id}|committee={code}|deal={deal_id}")
                except Exception as _exc:
                    logger.warning(
                        "committee %s approved %s but the case %s was not "
                        "updated: %s", code, deal_id, _app_id, _exc)'''

HELPER_ANCHOR = "def _derive_outcome_from_votes"
HELPER = '''def _dt_now_iso() -> str:
    """Timestamp for a committee recommendation written onto a case."""
    import datetime as _d
    return _d.datetime.now().isoformat(timespec="seconds")


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "AND SAY SO ON THE CREDIT CASE" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The committee record write matched %d times." % s.count(OLD))
        return 1
    if s.count(HELPER_ANCHOR) != 1:
        print("Could not place the timestamp helper.")
        return 1

    s = s.replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)
    s = s.replace(OLD, NEW, 1)

    if "logger.warning" not in NEW:
        print("A failed case update would be silent.")
        return 1
    if 'if str(outcome).upper() in' not in NEW:
        print("A declined case would be marked approved.")
        return 1
    # _lam must exist where we import it from.
    r = os.path.join("utils", "api_lms_routes.py")
    if os.path.isfile(r) and "def _lam(" not in open(r, encoding="utf-8").read():
        print("_lam is not in api_lms_routes - check the import before applying.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("A committee recommendation now shows on the case as committee_approved.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_cs2")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nThis marks approvals FROM NOW ON. The five already approved keep")
    print("their old status - backfill them with:")
    print("   python scripts/mark_already_approved_cases.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
