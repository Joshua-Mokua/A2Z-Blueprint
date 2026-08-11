#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Does the system actually hold together? READ ONLY. Exit 1 on any failure.

RULING (2026-08-11): "propose the best way to have wholesome test cases tying to
what we already have, so that when we release we are sure what we are
releasing."

WHY THIS EXISTS. Every patcher verifies ITSELF - anchors, post-checks, a replay.
Nothing verified the SYSTEM. That is how the funnel sat broken on the pilot for
days: every individual piece was green, and no single check asked whether a deal
could travel from an event through the journey into the analytics and come out
with the right number.

Each assertion below is a CLAIM MADE IN THE BUILD, checked against running code.
When one goes red, it names which claim broke rather than reporting a vague
failure.

    python scripts\\verify_scenario.py

Run it after scripts\\seed_scenario.py --apply, and as the last gate before a
release:  seed -> verify -> diag_deploy_check -> build -> push
"""
import os
import sys

sys.path.insert(0, os.getcwd())

PASS, FAIL, SKIP = "  ok  ", "  ***", "  --  "
_failures = []


def check(label, fn, why=""):
    """Run one assertion. A raised exception is a failure, not a crash - a
    verifier that dies on the first problem hides the rest."""
    try:
        ok, detail = fn()
    except Exception as exc:
        ok, detail = False, "raised %s: %s" % (type(exc).__name__, str(exc)[:60])
    print("%s%-52s %s" % (PASS if ok else FAIL, label, detail))
    if not ok:
        _failures.append((label, detail, why))
    return ok


def rule(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def main():
    try:
        from utils.core import PipelineManager
        from utils.origin_channels import channels, listing
        from utils.deal_origin import origin_of, stamp, credits_party, summarise
        from utils.pipeline_funnel import buckets_for, gates_for, gate_of
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    deals = list(getattr(PipelineManager(), "deals", []) or [])
    scen = [d for d in deals if str(d.get("id", "")).startswith("SCN")]

    rule("1. IS THERE A WORLD TO TEST?")
    check("scenario deals exist",
          lambda: (bool(scen), "%d found" % len(scen)),
          "run scripts\\seed_scenario.py --apply first")
    if not scen:
        print("\nNothing to verify. Seed the scenario first.")
        return 1

    for key in ("events", "partnership", "lead_gen"):
        check("channel %-12s has records" % key,
              lambda k=key: (bool(listing(k)), "%d" % len(listing(k))))

    rule("2. ATTRIBUTION - do the deals and the channels agree?")
    field = {"events": "event_id", "partnership": "mou_id", "lead_gen": "channel_id"}
    for key, f in field.items():
        tagged = [d for d in scen if str(d.get(f) or "").strip()]

        def _leads(k=key, ff=f, tg=tagged):
            from utils.origin_channels import attribution
            ids = {str(d.get(ff)) for d in tg}
            total = sum(attribution(k, i, deals)["leads"] for i in ids)
            return (total == len(tg),
                    "%d tagged, %d attributed" % (len(tg), total))
        check("%-12s every tagged deal is attributed" % key, _leads,
              "a deal pointing at a channel that does not count it means the "
              "source field and the attribution field have drifted apart")

        def _won(k=key, ff=f, tg=tagged):
            from utils.origin_channels import attribution
            ids = {str(d.get(ff)) for d in tg}
            got = sum(attribution(k, i, deals)["accounts"] for i in ids)
            want = sum(1 for d in tg if str(d.get("stage")) == "Closed Won")
            return (got == want, "%d won counted, %d actually won" % (got, want))
        check("%-12s accounts count ONLY closed-won" % key, _won,
              "counting before closure flatters every channel's return")

    rule("3. ORIGIN - is it evidence rather than a claim?")
    check("a referred EVENT deal stays an event",
          lambda: (stamp({"origin": "events"}, "referral", "X", "Y")["origin"]
                   == "events", "channel preserved"),
          "OR5: the referral is the branch, not a new origin")
    check("a referred SELF deal becomes a referral",
          lambda: (stamp({"origin": "self"}, "referral", "X", "Y")["origin"]
                   == "referral", "stamped"),
          "OR3: a deal with nothing better records how it arrived")
    check("a claimed prospect is always a warehouse deal",
          lambda: (stamp({"origin": "events"}, "warehouse", "X", "Y")["origin"]
                   == "warehouse", "stamped"),
          "the deal did not exist before the claim")
    check("only creditable origins yield a party",
          lambda: (not credits_party("events") and credits_party("referral"),
                   "events no, referral yes"),
          "a stale referrer on a self-created deal must not move an index")
    check("every scenario deal has a known origin",
          lambda: (all(origin_of(d) for d in scen), "all resolve"))

    rule("4. THE JOURNEY - is the funnel populated at every step?")

    def _covered():
        stages = {s for b in buckets_for("asset") for s in b.get("steps", [])}
        seen = {str(d.get("stage")) for d in scen}
        missing = sorted(stages - seen)
        return (not missing, "missing: %s" % ", ".join(missing[:3])
                if missing else "every loan stage has a deal")
    check("loan journey covered end to end", _covered,
          "a funnel with empty steps cannot be read for where work stalls")

    check("every bucket belongs to a gate",
          lambda: (all(gate_of(b["key"]) for b in buckets_for("asset")),
                   "all mapped"),
          "an unassigned bucket sits outside the architecture")
    check("the loan journey passes three gates",
          lambda: ([g["gate"] for g in gates_for("asset")]
                   == ["refining", "processing", "closure"], "in order"))

    rule("5. REPORTING - do the totals reconcile?")

    def _split():
        got = {b["origin"]: b["count"] for b in summarise(scen)}
        want = {}
        for d in scen:
            want[origin_of(d)] = want.get(origin_of(d), 0) + 1
        bad = [k for k in want if got.get(k, 0) != want[k]]
        return (not bad, "mismatch on %s" % bad if bad else "counts reconcile")
    check("origin split matches the deals", _split,
          "the analytics and the deal store disagreeing means one is lying")

    def _empty_visible():
        return (len([b for b in summarise(scen) if b["count"] == 0]) > 0,
                "empty origins still reported")
    check("origins with no deals are still shown", _empty_visible,
          "hiding an empty channel is how one dies unnoticed")

    def _roi():
        from utils.origin_channels import attribution
        pids = [r["id"] for r in listing("partnership")][:1]
        if not pids:
            return (True, "no partnerships to check")
        a = attribution("partnership", pids[0], deals)
        return (a["roi_pct"] is None,
                "partnership ROI is %s" % a["roi_pct"])
    check("a channel with no budget shows NO return", _roi,
          "a percentage over a budget nobody set is a fabricated number")

    rule("VERDICT")
    if not _failures:
        print("Everything holds. What you would release behaves as claimed.")
        return 0
    print("%d assertion(s) failed:\n" % len(_failures))
    for label, detail, why in _failures:
        print("   * %s" % label)
        print("     %s" % detail)
        if why:
            print("     why it matters: %s" % why)
        print("")
    print("Do not release until these are green - each one is a claim the")
    print("build makes, checked against the running code.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
