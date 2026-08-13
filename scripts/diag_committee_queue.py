#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Why is this case not in that person's committee queue? READ ONLY.

Walks the queue's own logic for a named person and reports, deal by deal, the
first reason each one was dropped. Guessing at this has cost time twice; the
list is short and the answer is always one of five things.

    python scripts\\diag_committee_queue.py --user joyce
    python scripts\\diag_committee_queue.py --user joyce --deal SIMBCC01
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    who = ""
    deal_filter = ""
    if "--user" in sys.argv:
        i = sys.argv.index("--user")
        if i + 1 < len(sys.argv):
            who = sys.argv[i + 1].strip()
    if "--deal" in sys.argv:
        i = sys.argv.index("--deal")
        if i + 1 < len(sys.argv):
            deal_filter = sys.argv[i + 1].strip()
    if not who:
        print("ABORT: --user <username or staff code> is required.")
        return 1

    try:
        from utils.core import UserManager, PipelineManager
        from utils.api_pipeline_permissions import resolve_deal_permissions
        import utils.api as A
    except Exception as exc:
        print("ABORT: cannot load the application: %s" % exc)
        return 1

    # ── WHO ─────────────────────────────────────────────────────────────────
    users = UserManager().users or {}
    # MATCH ON ANY OF THE THREE THINGS somebody might know: the login key, the
    # staff code, or a piece of the name. Requiring an exact login key means
    # asking for the one identifier nobody remembers.
    rec, uname = None, ""
    w = who.lower()
    for k, v in users.items():
        if k.lower() == w or str(v.get("staff_code", "")).lower() == w:
            rec, uname = v, k
            break
    if not rec:
        hits = [(k, v) for k, v in users.items()
                if w in k.lower()
                or w in str(v.get("full_name", "") or v.get("name", "") or "").lower()]
        if len(hits) == 1:
            uname, rec = hits[0]
        elif len(hits) > 1:
            print("Several people match %r - name one:" % who)
            for k, v in hits[:12]:
                print("   login %-22s %-28s %s"
                      % (k, str(v.get("full_name") or v.get("name") or "")[:28],
                         v.get("staff_code")))
            return 1
    if not rec:
        print("ABORT: nobody matches %r by login, staff code or name." % who)
        return 1
    user = {"username": uname, "staff_code": rec.get("staff_code"),
            "role": rec.get("role"), "full_name": rec.get("full_name") or rec.get("name")}
    print("=" * 76)
    print("COMMITTEE QUEUE TRACE")
    print("=" * 76)
    print("  login       %s" % uname)
    print("  staff_code  %r" % user["staff_code"])
    print("  full_name   %r" % user["full_name"])
    print("  role        %r" % user["role"])

    # ── WHICH COMMITTEES ────────────────────────────────────────────────────
    cfg = json.load(open(os.path.join("data", "lms_config.json"), encoding="utf-8"))
    pal = ((cfg.get("credit_workflow") or {}).get("committee_palette") or [])
    me = str(user["staff_code"] or "").strip()
    myname = str(user["full_name"] or "").strip().lower()
    mine = []
    for c in pal:
        mem = c.get("members") or []
        codes = {str(m.get("staff_code", "") or "").strip() for m in mem if isinstance(m, dict)}
        names = {str(m.get("name", "") or "").strip().lower() for m in mem if isinstance(m, dict)}
        chair = str(c.get("chaired_by", "") or "").strip().lower()
        how = ""
        if me and me in codes:
            how = "member (staff code)"
        elif myname and myname in names:
            how = "member (name)"
        elif myname and myname == chair:
            how = "chair"
        if how:
            mine.append((c, how))
    print("\n  COMMITTEES THIS PERSON IS ON: %d" % len(mine))
    for c, how in mine:
        print("     %-12s %-44s %s" % (c.get("code"), str(c.get("name"))[:44], how))
    if not mine:
        print("     none - so the queue is empty no matter what deals exist.")
        print("     Their name must match a member entry or chaired_by EXACTLY,")
        print("     or their staff code must be in the members list.")
        return 1
    my_codes = {str(c.get("code")) for c, _ in mine}

    # ── WHERE THE DEALS ARE READ FROM ───────────────────────────────────────
    print("\n  DEAL SOURCE")
    db_first = getattr(A, "_PIPELINE_READ_DB_FIRST", None)
    print("     _PIPELINE_READ_DB_FIRST = %r" % db_first)
    pm = PipelineManager()
    json_deals = list(getattr(pm, "deals", []) or [])
    print("     PipelineManager sees %d deal(s)" % len(json_deals))
    try:
        scoped = A._acquire_scoped_deals(user)
        print("     _acquire_scoped_deals sees %d for this person" % len(scoped))
        if db_first and len(json_deals) != len(scoped):
            print("     *** THE TWO SOURCES DISAGREE. The committee queue reads")
            print("         PipelineManager (the JSON store); most other screens")
            print("         read DB-first. A deal written to one is invisible to")
            print("         the other, which is exactly how a count and a list")
            print("         end up disagreeing.")
    except Exception as exc:
        print("     _acquire_scoped_deals failed: %s" % str(exc)[:60])

    # ── DEAL BY DEAL ────────────────────────────────────────────────────────
    print("\n  WHY EACH DEAL IS IN OR OUT")
    try:
        from utils.api_pipeline_scope import get_visible_staff_codes
        visible = set(get_visible_staff_codes(user))
    except Exception:
        visible = set()
    print("     visible staff codes: %d" % len(visible))

    shown = 0
    for d in json_deals:
        did = str(d.get("id"))
        if deal_filter and did != deal_filter:
            continue
        reasons = []
        if str(d.get("stage", "")).lower().startswith("closed"):
            reasons.append("stage is closed")
        try:
            journey = A._effective_committee_journey(d)
        except Exception as exc:
            journey = []
            reasons.append("journey error: %s" % str(exc)[:40])
        overlap = [c for c in journey if c in my_codes]
        if not overlap:
            reasons.append("journey %s does not include any of this person's committees"
                           % (journey or "[]"))
        already = [c for c in overlap if (d.get("committee_records") or {}).get(c)]
        if overlap and len(already) == len(overlap):
            reasons.append("already decided by this committee")
        try:
            cv = resolve_deal_permissions(d, user, visible).get("can_view")
        except Exception as exc:
            cv = False
            reasons.append("permission error: %s" % str(exc)[:40])
        if not cv:
            reasons.append("can_view is False")

        if not reasons:
            print("     IN   %-10s %-24s %s" % (did, str(d.get("client_name"))[:24], overlap))
            shown += 1
        elif deal_filter or did.startswith(("SIM", "TEST")):
            print("     out  %-10s %-24s %s"
                  % (did, str(d.get("client_name"))[:24], reasons[0]))
            for r in reasons[1:]:
                print("          %-36s %s" % ("", r))

    print("\n  %d deal(s) would appear in the queue." % shown)
    if not shown:
        print("  Every reason above is a different fix - read the first one.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
