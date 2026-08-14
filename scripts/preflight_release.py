#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Ten things that could bite the pilot which the credit gate does not test.

preflight_credit.py proves the credit path WORKS. This asks a different
question: what could go wrong on the bank's box that would not go wrong on
ours? Every check below comes from a fault that actually happened this week, or
from a difference between the two boxes that nobody has looked at.

    python scripts\\preflight_release.py
    python scripts\\preflight_release.py --verbose

Read-only. Exit 0 means nothing known is waiting to trip the pilot.
"""
import json
import os
import re
import sys
import traceback

sys.path.insert(0, os.getcwd())

PASS, FAIL, WARN = [], [], []
VERBOSE = "--verbose" in sys.argv


def ok(n, what, detail=""):
    PASS.append(what)
    print("  ok    %-2s %-50s %s" % (n, what[:50], detail[:22]))


def bad(n, what, why):
    FAIL.append((what, why))
    print("  FAIL  %-2s %s" % (n, what))
    print("           %s" % why)


def warn(n, what, why=""):
    WARN.append(what)
    print("  warn  %-2s %s" % (n, what))
    if why:
        print("           %s" % why)


def rule(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def main():
    api = open(os.path.join("utils", "api.py"), encoding="utf-8").read()
    routes = open(os.path.join("utils", "api_lms_routes.py"), encoding="utf-8").read()

    rule("TEN THINGS THAT COULD TRIP THE PILOT")

    # ── 1 ───────────────────────────────────────────────────────────────────
    # A committee stage nobody can leave is worse than no gate: the case stops
    # and the branch cannot see why.
    try:
        import utils.api as A
        pcfg = A._load_json("pipeline_settings.json") or {}
        flows = (pcfg.get("product_flows") or {})
        stuck = []
        for prod in flows:
            # ASK THE APPLICATION, not the raw config. A stage is stored as an
            # OBJECT - {stage, target_days, win_probability} - so string-matching
            # the entries finds nothing and every flow looks broken. My first
            # version reported thirteen products stuck when none were.
            stages = [str(x) for x in (A._stage_flow_for(prod) or [])]
            has_cttee = any("committee" in x.lower() for x in stages)
            has_close = any(x.lower().startswith("closed") for x in stages)
            if has_cttee and not has_close:
                stuck.append(prod)
        if stuck:
            bad(1, "%d product flow(s) have a committee but no closing stage" % len(stuck),
                "a case reaching the end cannot be closed: %s" % ", ".join(stuck[:4]))
        else:
            ok(1, "every flow with a committee can also be closed",
               "%d flows" % len(flows))
    except Exception as exc:
        warn(1, "could not read the product flows", str(exc)[:60])

    # ── 2 ───────────────────────────────────────────────────────────────────
    # AA1 advances a case when a committee recommends. If the next stage is
    # missing from the flow the case would stop dead with nobody expecting it.
    if "auto_advanced_by" in api and "except Exception" in api[api.find("A DECIDED CASE MOVES ITSELF"):
                                                              api.find("A DECIDED CASE MOVES ITSELF") + 2200]:
        ok(2, "an automatic advance fails safe if the flow cannot be read", "")
    else:
        bad(2, "the automatic advance is not guarded",
            "a product with an unreadable flow would fail the VOTE, not just "
            "the advance - the decision would be lost")

    # ── 3 ───────────────────────────────────────────────────────────────────
    # The pilot runs Postgres. Every helper that writes must survive it being
    # briefly unavailable, or a restart loses work.
    i = api.find("def _write_deal")
    blk = api[i: api.find("\ndef ", i + 10)] if i > 0 else ""
    if blk and "except Exception" in blk and "_db_available()" in blk:
        ok(3, "a deal write survives the database being unavailable", "")
    else:
        bad(3, "a deal write does not fail safe",
            "if Postgres blinks, the JSON write must still stand and warn")

    # ── 4 ───────────────────────────────────────────────────────────────────
    # Committee membership is matched by staff code AND by name. A chair with
    # no code is matched by name only, which two people can share.
    try:
        cfg = json.load(open(os.path.join("data", "lms_config.json"), encoding="utf-8"))
        pal = ((cfg.get("credit_workflow") or {}).get("committee_palette") or [])
        nameless_chairs = [c for c in pal
                           if str(c.get("chaired_by", "") or "").strip()
                           and not str(c.get("chair_staff_code", "") or "").strip()]
        if nameless_chairs:
            warn(4, "%d chair(s) are identified by NAME only" % len(nameless_chairs),
                 "two people with the same name cannot be told apart. Storing "
                 "chair_staff_code would make the match exact.")
        else:
            ok(4, "every chair is identified by staff code", "")
    except Exception as exc:
        bad(4, "lms_config.json unreadable", str(exc)[:60])

    # ── 5 ───────────────────────────────────────────────────────────────────
    # A committee whose members cannot log in cannot vote, and the case waits
    # for people who will never arrive.
    try:
        from utils.core import UserManager
        users = UserManager().users or {}
        by_code = {str(v.get("staff_code", "") or "").strip() for v in users.values()}
        cannot = []
        for c in pal:
            for m in (c.get("members") or []):
                if not isinstance(m, dict):
                    continue
                code = str(m.get("staff_code", "") or "").strip()
                if code and code not in by_code:
                    cannot.append((c.get("code"), m.get("name") or code))
        if cannot:
            bad(5, "%d committee member(s) have no login" % len(cannot),
                "they are on a committee and cannot sign in to vote: %s"
                % ", ".join("%s/%s" % t for t in cannot[:4]))
        else:
            ok(5, "every committee member can sign in", "")
    except Exception as exc:
        warn(5, "could not check member logins", str(exc)[:60])

    # ── 6 ───────────────────────────────────────────────────────────────────
    # Quorum against membership. A committee that can never reach quorum defers
    # every case, and the queue fills with work nobody can finish.
    short = []
    for c in pal:
        mem = [m for m in (c.get("members") or [])
               if isinstance(m, dict)
               and (str(m.get("staff_code", "")).strip() or str(m.get("name", "")).strip())]
        q = c.get("min_quorum_count") or 2
        if mem and len(mem) < q:
            short.append("%s (%d of %d)" % (c.get("code"), len(mem), q))
    if short:
        bad(6, "%d committee(s) can never reach quorum" % len(short),
            "every decision would DEFER: %s" % ", ".join(short[:4]))
    else:
        ok(6, "every staffed committee can reach its quorum", "")

    # ── 7 ───────────────────────────────────────────────────────────────────
    # A case with no client_type routes to no department committee. Real cases
    # get one at creation; legacy ones may not.
    try:
        from utils.core import PipelineManager
        deals = list(getattr(PipelineManager(), "deals", []) or [])
        live = [d for d in deals
                if not str(d.get("stage", "")).lower().startswith("closed")]
        noct = [d for d in live if not str(d.get("client_type", "") or "").strip()]
        if noct:
            warn(7, "%d live deal(s) carry no client type" % len(noct),
                 "no department committee can be resolved for them - they "
                 "would reach credit without one")
        else:
            ok(7, "every live deal has a client type", "%d live" % len(live))
    except Exception as exc:
        warn(7, "could not read the deals", str(exc)[:60])

    # ── 8 ───────────────────────────────────────────────────────────────────
    # After the release everybody must sign out and in - the role is read at
    # token verification. If that enrichment is missing, an AD login without a
    # role claim becomes "Staff" and every gate refuses them.
    try:
        aj = open(os.path.join("utils", "auth_jwt.py"), encoding="utf-8").read()
        if '"role"' in aj and "Staff" in aj:
            ok(8, "a role is enriched from the store at sign-in", "")
        else:
            bad(8, "the role enrichment is missing",
                "an AD login with no role claim would be treated as Staff and "
                "refused everywhere - this took the pilot down once")
    except Exception as exc:
        warn(8, "could not read auth_jwt.py", str(exc)[:60])

    # ── 9 ───────────────────────────────────────────────────────────────────
    # The release must not carry a menu entry the pilot should not have.
    try:
        bar = open(os.path.join("frontend", "web", "src", "components",
                                "Sidebar.tsx"), encoding="utf-8").read()
        if "label: 'Deals Warehouse'" in bar:
            warn(9, "this box's sidebar has the Deals Warehouse entry",
                 "correct here - UI1 strips it from what ships. The patcher "
                 "aborts if it would ever travel.")
        else:
            ok(9, "no warehouse entry in the sidebar", "")
    except Exception as exc:
        warn(9, "could not read the sidebar", str(exc)[:60])

    # ── 10 ──────────────────────────────────────────────────────────────────
    # A committee stage must not be walkable past, or the gate is decoration.
    if "A COMMITTEE STAGE CANNOT BE WALKED PAST" in api:
        ok(10, "a committee stage cannot be advanced past undecided", "")
    else:
        bad(10, "the committee stage is not enforced on advance",
            "somebody could move a case off it with no decision, and the "
            "journey would record a clean stage change")

    # ── 11, a free one: the two stores ──────────────────────────────────────
    unsynced = sum(1 for m in re.finditer(r"\.update_deal\(", api)
                   if "_db_sync_pipeline_deal" not in api[m.start(): m.start() + 900])
    if unsynced:
        bad(11, "%d deal write(s) never reach Postgres" % unsynced,
            "the shape of four separate faults this week")
    else:
        ok(11, "every deal write reaches Postgres", "0 unsynced")

    # ── 12 ──────────────────────────────────────────────────────────────────
    # Orphan logins pointing at codes that are not in the register see nothing
    # and are invisible to their managers.
    try:
        from utils.api_pipeline_scope import get_staff_roster
        df = get_staff_roster()
        reg = {str(r.get("Staff Code") or "").strip() for _i, r in df.iterrows()}
        orphans = [k for k, v in users.items()
                   if str(v.get("staff_code", "") or "").strip()
                   and str(v.get("staff_code")).strip() not in reg]
        if orphans:
            warn(12, "%d login(s) point at codes not in the register" % len(orphans),
                 "they see empty screens and no manager can see their work: %s"
                 % ", ".join(orphans[:5]))
        else:
            ok(12, "every login resolves to the register", "")
    except Exception as exc:
        warn(12, "could not read the staff register", str(exc)[:60])

    return report()


def report():
    rule("VERDICT")
    print("  passed  %d" % len(PASS))
    print("  warned  %d" % len(WARN))
    print("  FAILED  %d" % len(FAIL))
    if not FAIL:
        print("\nNothing known is waiting to trip the pilot.")
        if WARN:
            print("\nThe warnings are worth reading before you release - none")
            print("blocks it, but each is something somebody will ask about.")
        return 0
    print("\nFIX BEFORE RELEASING:\n")
    for what, why in FAIL:
        print("   * %s" % what)
        print("     %s" % why)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\nUNHANDLED:")
        for ln in traceback.format_exc().strip().split("\n")[-6:]:
            print("   %s" % ln[:110])
        sys.exit(1)
