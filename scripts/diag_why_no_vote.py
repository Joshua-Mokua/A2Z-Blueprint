#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Why can this person not vote on this deal? One command, every reason.

FROM THE PILOT (2026-08-18): a deal submitted at Fortis showed "Locked - with
Credit", did not appear in Manager Queues, and its committee journey listed
only the Consumer department committee with no branch committee at all.

Three symptoms, and they could come from eight different causes. Chasing them
one at a time by screenshot has cost this project more time than any bug in it.
So this asks the running code, on the real deal, and prints every answer at
once.

    python scripts\\diag_why_no_vote.py --deal D8477 --user KE439

IT ALSO CHECKS WHICH CODE IS RUNNING. Half the faults reported this fortnight
were a correct fix that had not been deployed - the source was right, the
browser or the server was serving yesterday's. That check is first, because
nothing below it means anything if the answer is "you are running the old
build".

Read only.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.getcwd())


def main():
    deal_id = user_ref = ""
    for flag in ("--deal", "--user"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if flag == "--deal":
                    deal_id = sys.argv[i + 1].strip()
                else:
                    user_ref = sys.argv[i + 1].strip()
    if not deal_id:
        print("ABORT: --deal <id> is required, e.g. --deal D8477")
        return 1

    import utils.api as A
    from utils.core import PipelineManager, UserManager

    # ── 0. WHICH CODE IS RUNNING ────────────────────────────────────────────
    print("=" * 78)
    print("0. IS THIS BOX RUNNING THE CURRENT CODE")
    print("=" * 78)
    src = open(os.path.join("utils", "api.py"), encoding="utf-8").read()
    checks = [
        ("the gate says who may vote (GV1)", '"can_vote": _can_vote'),
        ("a future committee cannot block (GT1)", "ONLY THE COMMITTEES THIS CASE HAS REACHED"),
        ("the memo is not demanded early (CR1)", "THE MEMO IS NEEDED LATER"),
        ("the branch keeps its case (LK1)", "branch keeps the case while their committee"),
    ]
    stale = []
    for label, marker in checks:
        have = marker in src
        print("  %-46s %s" % (label, "yes" if have else "*** MISSING ***"))
        if not have:
            stale.append(label)

    bar = os.path.join("frontend", "web", "src", "pages", "PipelineDealDetail.tsx")
    if os.path.isfile(bar):
        b = open(bar, encoding="utf-8").read()
        # THE STRING ALSO APPEARS IN THE COMMENT EXPLAINING THE RULING, so
        # searching the file finds it on CURRENT code and cries wolf. Alex hit
        # this on the first run. Look for the JSX that renders it, not the
        # prose about it.
        old = ('<span className="font-semibold">Locked — with Credit.</span>' in b
               or '>Locked — with Credit.<' in b)
        print("  %-46s %s" % ("the stage-aware lock banner",
                              "*** OLD WORDING STILL IN SOURCE ***" if old else "yes"))
        if old:
            stale.append("the frontend source is old")

    dist = os.path.join("frontend", "web", "dist")
    if os.path.isdir(dist):
        import glob
        hits = 0
        for f in glob.glob(os.path.join(dist, "assets", "*.js")):
            try:
                if "Locked" in open(f, encoding="utf-8", errors="ignore").read():
                    txt = open(f, encoding="utf-8", errors="ignore").read()
                    if "with Credit." in txt:
                        hits += 1
            except Exception:
                pass
        print("  %-46s %s" % ("the BUILT bundle",
                              "*** STILL CARRIES THE OLD BANNER ***" if hits
                              else "rebuilt"))
        if hits:
            stale.append("the built bundle is old - run pnpm build")

    if stale:
        print("\n  *** STOP HERE. This box is running older code:")
        for s in stale:
            print("      - %s" % s)
        print("\n      python scripts\\... nothing below will mean anything")
        print("      until the server is restarted and the frontend rebuilt:")
        print("        pushd frontend\\web && pnpm install && pnpm build && popd")
        print("        then restart uvicorn")
        print("\n  Continuing anyway, so you can see the data too.\n")

    # ── 1. THE DEAL ─────────────────────────────────────────────────────────
    pm = PipelineManager()
    deal = pm.get_deal(deal_id)
    if not deal:
        print("ABORT: no deal %r in the pipeline store." % deal_id)
        return 1

    print("=" * 78)
    print("1. THE DEAL")
    print("=" * 78)
    for k in ("id", "client_name", "stage", "branch", "unit", "client_type",
              "product_type", "product", "staff_code", "manager_validated",
              "lms_application_id", "locked"):
        print("  %-24s %s" % (k, deal.get(k)))

    stage = str(deal.get("stage", "") or "")
    at_committee = "committee" in stage.lower()
    print("\n  at a committee stage?    %s" % ("yes" if at_committee else "NO"))
    if not at_committee:
        print("  *** The committee queue lists cases AT OR PAST a committee")
        print("      stage. A deal at %r has not reached one, so it will not" % stage)
        print("      appear there and nobody can vote on it yet.")

    try:
        locked = A._deal_locked(deal)
        print("  locked by the rule?      %s" % locked)
        if locked and at_committee:
            print("  *** Locked while at a BRANCH committee stage - LK1 should")
            print("      prevent that. This box is running the old rule.")
    except Exception as exc:
        print("  locked by the rule?      could not evaluate: %s" % str(exc)[:40])

    # ── 2. WHICH COMMITTEES ─────────────────────────────────────────────────
    print("\n" + "=" * 78)
    print("2. WHICH COMMITTEES THIS DEAL ROUTES TO")
    print("=" * 78)
    journey = A._effective_committee_journey(deal) or []
    print("  journey: %s" % (journey or "*** NONE ***"))
    if not journey:
        print("  *** The deal reaches NO committee. Nobody can vote because")
        print("      there is nobody to vote.")

    cfg = json.load(open(os.path.join("data", "lms_config.json"), encoding="utf-8"))
    pal = ((cfg.get("credit_workflow") or {}).get("committee_palette") or [])
    br = str(deal.get("branch") or deal.get("unit") or "").strip()
    match = [c for c in pal
             if str(c.get("branch", "")).strip().lower() == br.lower()]
    print("\n  the deal's branch        %r" % br)
    if not match:
        print("  *** NO committee in the palette has that branch. Branch names")
        print("      must match exactly. Palette branches include:")
        for c in [x for x in pal if str(x.get("kind", "")).lower() == "branch"][:8]:
            print("        %r" % str(c.get("branch")))
    else:
        c = match[0]
        mem = [m for m in (c.get("members") or []) if isinstance(m, dict)
               and (str(m.get("staff_code", "")).strip()
                    or str(m.get("name", "")).strip())]
        print("  its branch committee     %s (%s)" % (c.get("code"), c.get("name")))
        print("  members                  %d" % len(mem))
        print("  chair                    %s" % (c.get("chaired_by") or "*** NOBODY ***"))
        if str(c.get("code")) not in journey:
            print("  *** That committee is NOT in the deal's journey. The deal")
            print("      routes past its own branch committee.")

    # ── 3. THIS PERSON ──────────────────────────────────────────────────────
    if not user_ref:
        print("\n(Pass --user <staff code or login> to check a person too.)")
        return 0

    users = UserManager().users or {}
    key = None
    if user_ref in users:
        key = user_ref
    else:
        for k, v in users.items():
            if str(v.get("staff_code", "")).strip().lower() == user_ref.lower():
                key = k
                break
    if not key:
        print("\nABORT: no login %r and no record with that staff code." % user_ref)
        return 1
    rec = users[key]
    u = {"username": key, "staff_code": str(rec.get("staff_code", "") or ""),
         "full_name": str(rec.get("full_name", "") or ""),
         "role": str(rec.get("role", "") or ""),
         "is_admin": bool(rec.get("is_admin"))}

    print("\n" + "=" * 78)
    print("3. %s" % (u["full_name"] or key))
    print("=" * 78)
    print("  login       %s" % key)
    print("  staff code  %s" % u["staff_code"])
    print("  role        %s" % u["role"])
    print("  active      %s" % rec.get("active"))
    if not rec.get("active"):
        print("  *** INACTIVE. They cannot sign in at all.")

    on = []
    for c in pal:
        for m in (c.get("members") or []):
            if isinstance(m, dict) and str(m.get("staff_code", "")).strip() == u["staff_code"]:
                on.append(str(c.get("code")))
                break
        if str(c.get("chaired_by", "") or "").strip().lower() == u["full_name"].strip().lower():
            if str(c.get("code")) not in on:
                on.append(str(c.get("code")) + " (chair only, NOT on the roster)")
    print("  committees  %s" % (", ".join(on) or "*** NONE ***"))

    try:
        r = A.get_deal_committee_records(deal_id, user=u)
        gates = r.get("gates") or []
        print("\n  WHAT THE SCREEN WOULD RECEIVE:")
        if not gates:
            print("     no gates at all - no voting bench can be drawn")
        for g in gates:
            cv = g.get("can_vote")
            print("     %-14s can_vote=%-6s votes=%s/%s  %s"
                  % (g.get("code"), cv, g.get("votes_cast"), g.get("quorum"),
                     "" if cv else "<- no bench for this person"))
            if cv is None:
                print("        *** can_vote is ABSENT. The panel falls back to")
                print("            'owner or admin' - GV1 is not on this box.")
    except Exception as exc:
        print("\n  the committee records call FAILED: %s" % str(exc)[:70])

    try:
        # get_visible_staff_codes lives in api_pipeline_scope, not api. The
        # line that "assigned it to itself" was nonsense I left behind and it
        # raised an AttributeError every run.
        q = A.pipeline_queue_committee(u)
        ids = [str(c.get("deal_id")) for c in (q.get("cases") or [])]
        print("\n  their committee queue holds %d case(s)" % q.get("total", 0))
        print("  is THIS deal in it?  %s" % ("yes" if deal_id in ids else "NO"))
    except Exception as exc:
        print("\n  the queue call FAILED: %s" % str(exc)[:70])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\nUNHANDLED:")
        for ln in traceback.format_exc().strip().split("\n")[-8:]:
            print("   %s" % ln[:110])
        sys.exit(1)
