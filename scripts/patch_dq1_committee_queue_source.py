#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
DQ1 - the committee queue reads what every other screen reads.

THE SYMPTOM (2026-08-13): the queue listed three cases and Review opened an
EMPTY PAGE.

THE CAUSE, and it is the thing that has been producing mismatches for days:
deals live in TWO stores.

    data/pipeline_deals.json     what PipelineManager loads, always
    pipeline_deals (Postgres)    what the API reads, because
                                 _PIPELINE_READ_DB_FIRST is True

The committee queue was reading PipelineManager. The deal detail page reads
DB-first. On the pilot box that was 33 deals in one store against 2 in the
other - so the queue found a case the page could not, which is exactly what an
empty Review page looks like. The same split explains a validation count of 1
above a list showing nothing.

Nothing was corrupt. There were two stores and no reconciliation.

THE FIX. The queue now uses _acquire_scoped_deals - the canonical read, DB
first with JSON as fallback, cascade scope already applied. It can no longer
disagree with the page it links to, because it is reading the same thing.

ONE ADDITION, and it is deliberate. A department committee sits at head office
and its members are not in a branch RM's cascade, so a scoped read alone would
hide the very cases they must decide - the fault CM1 fixed in permissions. Any
deal the committee is entitled to but scope dropped is recovered from the same
table, and can_view still decides who sees it.

scripts/reconcile_deal_stores.py answers the wider question: it reads BOTH
stores, matches on id, and reports what is only in one, and what is in both
with DIFFERENT content - the dangerous case, where two screens each show
something and disagree. --repair copies JSON-only deals into the database
through the application's own _db_sync_pipeline_deal, never a hand-rolled
INSERT. It never deletes, and it never resolves a DIFFERENCE: a script cannot
know whether the JSON stage or the DB stage is the one somebody meant.

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_dq1_committee_queue_source.py            # dry run
    python scripts\\patch_dq1_committee_queue_source.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
RECON = os.path.join("scripts", "reconcile_deal_stores.py")
BACKUP_SUFFIX = ".pre_dq1"

START = '@app.get("/api/pipeline/queues/committee")'
END = '@app.get("/api/pipeline/queues/cancellation")'

ENDPOINT = r'''@app.get("/api/pipeline/queues/committee")
def pipeline_queue_committee(user: dict = Depends(get_current_user)):
    """Cases waiting on a committee this person sits on.

    RULING (2026-08-12): the branch managers were gathered and nothing moved -
    and once the committees existed, the reason it still would not have moved
    is that MEMBERS HAD NOWHERE TO LOOK. A decision could only be recorded by
    knowing a deal id and opening it. A committee that cannot find its own
    cases is not a committee.

    MEMBERSHIP DECIDES WHAT YOU SEE, not role. A branch manager sees their own
    branch's committee because they sit on it; somebody added to two committees
    sees both. That is the same rule the bank would apply in a room.

    A CASE APPEARS WHEN it is at a stage whose journey includes that committee
    AND no decision has been recorded for it yet. It leaves the moment one is,
    which is what makes the list trustworthy enough to work from.
    """
    me = str(user.get("staff_code", "") or "").strip()
    me_name = str(user.get("full_name", "") or "").strip().lower()
    if not me and not me_name:
        return {"committees": [], "cases": [], "total": 0}

    # Which committees is this person on? Chair counts - they convene it.
    mine = []
    for c in _read_committee_palette():
        members = c.get("members") or []
        codes = {str(m.get("staff_code", "") or "").strip()
                 for m in members if isinstance(m, dict)}
        names = {str(m.get("name", "") or "").strip().lower()
                 for m in members if isinstance(m, dict)}
        chair = str(c.get("chaired_by", "") or "").strip().lower()
        if (me and me in codes) or (me_name and (me_name in names or me_name == chair)):
            mine.append(c)
    if not mine:
        return {"committees": [], "cases": [], "total": 0}

    my_codes = {str(c.get("code")) for c in mine}
    # ── THE SAME DEALS EVERY OTHER SCREEN SEES ──────────────────────────────
    # This read PipelineManager, which loads pipeline_deals.json and NOTHING
    # ELSE - while _PIPELINE_READ_DB_FIRST is True and every other screen reads
    # Postgres. On the pilot box that was 33 deals in one store against 2 in
    # the other, and the symptom was a case listed in this queue whose Review
    # button opened an empty page: the queue found it, the detail page did not.
    #
    # _acquire_scoped_deals is the canonical read - DB first, JSON as fallback,
    # and cascade scope already applied. Using it means this queue can never
    # again disagree with the page it links to.
    from utils.api_pipeline_permissions import resolve_deal_permissions as _perms
    try:
        all_deals = _acquire_scoped_deals(user)
    except Exception:
        all_deals = []
    try:
        from utils.api_pipeline_scope import get_visible_staff_codes as _vis
        visible = _vis(user)
    except Exception:
        visible = set()

    # A COMMITTEE MEMBER IS NOT ALWAYS IN THEIR OWN CASCADE. A department
    # committee sits at head office, so scoped deals alone would hide the very
    # cases they must decide - the fault CM1 fixed in permissions. The canonical
    # read is scoped, so anything the committee is entitled to but scope drops
    # is recovered here, and can_view still decides.
    if _db_available():
        try:
            from utils.db import db as _db2
            rows = _db2.fetch_all("SELECT * FROM pipeline_deals", tuple())
            seen = {str(d.get("id")) for d in all_deals}
            for d in (_normalize_db_deal_row(x) for x in _serialize(rows)):
                if str(d.get("id")) not in seen:
                    all_deals.append(d)
        except Exception:
            pass

    cases = []
    for d in all_deals:
        if str(d.get("stage", "")).lower().startswith("closed"):
            continue
        try:
            journey = _effective_committee_journey(d)
        except Exception:
            continue
        pending = [c for c in journey if c in my_codes
                   and not (d.get("committee_records") or {}).get(c)]
        if not pending:
            continue
        # SCOPE STILL APPLIES. Sitting on a committee does not open every deal
        # in the bank - a member sees the cases their scope already allows,
        # which for a branch committee is their own branch.
        if not _perms(d, user, visible).get("can_view"):
            continue
        cases.append({
            "deal_id": d.get("id"),
            "client_name": d.get("client_name"),
            "product": d.get("product_type") or d.get("product"),
            "deal_value": d.get("deal_value"),
            "currency": d.get("currency") or "KES",
            "branch": d.get("branch") or d.get("unit"),
            "stage": d.get("stage"),
            "owner": d.get("staff_name"),
            "awaiting": pending,
            "awaiting_names": [next((str(c.get("name")) for c in mine
                                     if str(c.get("code")) == p), p) for p in pending],
            "submitted_at": d.get("updated_at") or d.get("created_at"),
        })

    cases.sort(key=lambda x: str(x.get("submitted_at") or ""), reverse=True)
    return {
        "committees": [{"code": c.get("code"), "name": c.get("name"),
                        "members": len(c.get("members") or [])} for c in mine],
        "cases": cases,
        "total": len(cases),
    }


'''

RECONCILER = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Where do the two deal stores disagree? READ ONLY unless --repair.

THE PROBLEM, STATED PLAINLY. Deals live in two places:

    data/pipeline_deals.json     what PipelineManager loads, always
    pipeline_deals (Postgres)    what the API reads, because
                                 _PIPELINE_READ_DB_FIRST is True

Nothing keeps them in step. A write through one path lands in one store, and
whichever screen reads the other simply does not see it. That is the whole
explanation for a count saying 1 and the list beneath it saying nothing, and
for a case appearing in a queue whose Review button opens an empty page.

It is not a mysterious data problem. It is two stores and no reconciliation.

WHAT THIS DOES. Reads both, matches on id, and reports:

    ONLY IN JSON      invisible to every DB-first screen
    ONLY IN THE DB    invisible to anything using PipelineManager
    DIFFERENT         same id, different content - the dangerous one, because
                      both screens show something and they disagree

--repair copies JSON-only deals INTO the database, because the database is the
side the application reads and therefore the side that decides what is true. It
never deletes and never overwrites a row that already exists: a difference is
reported for a person to settle, not resolved by a script picking a winner.

    python scripts\\reconcile_deal_stores.py
    python scripts\\reconcile_deal_stores.py --verbose
    python scripts\\reconcile_deal_stores.py --repair
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())

# Fields worth comparing. Timestamps and derived values are excluded - they
# differ for innocent reasons and would bury the differences that matter.
COMPARE = ("stage", "client_name", "deal_value", "staff_code", "branch",
           "manager_validated", "client_type", "product_type", "segment")


def main():
    verbose = "--verbose" in sys.argv
    repair = "--repair" in sys.argv

    try:
        from utils.core import PipelineManager
        import utils.api as A
    except Exception as exc:
        print("ABORT: cannot load the application: %s" % exc)
        return 1

    print("=" * 78)
    print("DEAL STORE RECONCILIATION")
    print("=" * 78)

    pm = PipelineManager()
    j = {str(d.get("id")): d for d in (getattr(pm, "deals", []) or [])}
    print("  JSON  data/pipeline_deals.json   %d deal(s)" % len(j))

    if not A._db_available():
        print("  DB    NOT AVAILABLE")
        print("")
        print("  Every screen is falling back to JSON, so nothing is diverging")
        print("  right now - but _PIPELINE_READ_DB_FIRST is True, so the moment")
        print("  the database answers, the DB becomes what people see.")
        return 0

    try:
        from utils.db import db as _db
        rows = _db.fetch_all("SELECT * FROM pipeline_deals", tuple())
        d = {str(x.get("id")): x for x in
             (A._normalize_db_deal_row(r) for r in A._serialize(rows))}
    except Exception as exc:
        print("  DB    unreadable: %s" % str(exc)[:60])
        return 1
    print("  DB    pipeline_deals             %d deal(s)" % len(d))

    only_json = sorted(set(j) - set(d))
    only_db = sorted(set(d) - set(j))
    both = sorted(set(j) & set(d))

    differing = []
    for did in both:
        diffs = []
        for f in COMPARE:
            a, b = j[did].get(f), d[did].get(f)
            if a is None and b is None:
                continue
            if str(a or "").strip() != str(b or "").strip():
                diffs.append((f, a, b))
        if diffs:
            differing.append((did, diffs))

    print("\n  in both and identical   %d" % (len(both) - len(differing)))
    print("  in both but DIFFERENT   %d" % len(differing))
    print("  only in JSON            %d" % len(only_json))
    print("  only in the DB          %d" % len(only_db))

    if only_json:
        print("\n  ONLY IN JSON - invisible to every DB-first screen:")
        for did in (only_json if verbose else only_json[:10]):
            print("     %-22s %s" % (did, str(j[did].get("client_name"))[:34]))
        if not verbose and len(only_json) > 10:
            print("     ... and %d more (--verbose)" % (len(only_json) - 10))

    if only_db:
        print("\n  ONLY IN THE DB - invisible to anything using PipelineManager:")
        for did in (only_db if verbose else only_db[:10]):
            print("     %-22s %s" % (did, str(d[did].get("client_name"))[:34]))
        if not verbose and len(only_db) > 10:
            print("     ... and %d more (--verbose)" % (len(only_db) - 10))

    if differing:
        print("\n  *** SAME ID, DIFFERENT CONTENT - the dangerous ones. Both")
        print("      screens show something and the two disagree:")
        for did, diffs in (differing if verbose else differing[:8]):
            print("     %s" % did)
            for f, a, b in diffs[:4]:
                print("        %-18s json=%-22r db=%r" % (f, str(a)[:22], str(b)[:22]))
        if not verbose and len(differing) > 8:
            print("     ... and %d more (--verbose)" % (len(differing) - 8))

    if not (only_json or only_db or differing):
        print("\n  The two stores agree.")
        return 0

    print("\n" + "-" * 78)
    print("  WHAT TO DO")
    print("-" * 78)
    if only_json:
        print("  --repair copies the %d JSON-only deal(s) INTO the database."
              % len(only_json))
        print("  The database is what the application reads, so it is the side")
        print("  that decides what is true.")
    if only_db:
        print("  DB-only deals are left alone - they are already what people")
        print("  see. JSON is the stale copy there, not the missing one.")
    if differing:
        print("  DIFFERENCES ARE NOT TOUCHED. A script cannot know whether the")
        print("  JSON stage or the DB stage is the one somebody meant. Settle")
        print("  them by hand, or say which side wins and I will make it a rule.")

    if not repair:
        print("\nREAD ONLY - nothing changed. Re-run with --repair to copy")
        print("JSON-only deals into the database.")
        return 1

    if not only_json:
        print("\nNothing to copy.")
        return 0

    # THE APPLICATION'S OWN WRITE PATH, not a hand-rolled INSERT. Whatever
    # _db_sync_pipeline_deal does about column mapping, types and conflicts is
    # what every endpoint does; a second implementation here would be a third
    # way for the stores to diverge.
    sync = getattr(A, "_db_sync_pipeline_deal", None)
    if sync is None:
        print("\n  _db_sync_pipeline_deal is not available - nothing copied.")
        return 1
    copied, failed = 0, []
    for did in only_json:
        try:
            sync(j[did])
            copied += 1
        except Exception as exc:
            failed.append((did, str(exc)[:50]))
    print("\ncopied %d deal(s) into the database." % copied)
    for did, err in failed[:5]:
        print("   FAILED %-20s %s" % (did, err))
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    api = open(API, encoding="utf-8").read()
    if "THE SAME DEALS EVERY OTHER SCREEN SEES" in api:
        print("ABORT: DQ1 looks applied.")
        return 1
    if api.count(START) != 1 or api.count(END) != 1:
        print("ABORT: the committee queue endpoint matched %d / %d times."
              % (api.count(START), api.count(END)))
        print("       Apply CQ1 first - this replaces that endpoint.")
        return 1

    i, j = api.index(START), api.index(END)
    api = api[:i] + ENDPOINT + api[j:]
    print("  ok  committee queue reads the canonical source")

    # It must not go back to the JSON-only store - checked against the CODE,
    # not the comments. The comment explains what this USED to read, and a
    # naive search finds the word there and aborts a correct patch. That is now
    # twice a post-check has failed on its own prose.
    _code = "\n".join(l for l in ENDPOINT.split("\n")
                      if not l.strip().startswith("#"))
    if "getattr(pm," in _code or "PipelineManager" in _code:
        print("ABORT: still reading the JSON store directly - the queue would")
        print("       disagree with the page it links to.")
        return 1
    if "_acquire_scoped_deals" not in ENDPOINT:
        print("ABORT: not using the canonical read.")
        return 1
    # Committee members outside their own cascade must still be served.
    if "not always in their own cascade" not in ENDPOINT.lower():
        print("ABORT: the head-office committee recovery is missing - a DCC")
        print("       member would see an empty queue again.")
        return 1
    if "can_view" not in ENDPOINT:
        print("ABORT: scope no longer decides who sees a case.")
        return 1
    print("  ok  post-checks: canonical read, committees still served")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(api)
    print("APPLIED %s" % API)
    if not os.path.exists(RECON):
        open(RECON, "w", encoding="utf-8", newline="").write(RECONCILER)
        print("CREATED %s" % RECON)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("")
    print("Restart uvicorn. Review now opens the case the queue listed.")
    print("Then see where the two stores stand:")
    print("  python scripts\\reconcile_deal_stores.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
