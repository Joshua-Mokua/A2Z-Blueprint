#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Close the committee cases that are already fully voted. DRY RUN by default.

FROM THE BANK (2026-09-04): "on the committees, can the deals that were
initially there now progress?"

NOT ON THEIR OWN. The decision gate lives inside the VOTE endpoint - it runs
when somebody casts a vote, looks at everything cast so far, and closes the
decision if quorum and authority are satisfied.

A case where EVERYONE HAS ALREADY VOTED has nothing left to trigger it. Turning
off chair_vote_required with CV3 changed the rule, but no vote will arrive to
apply it, so those cases sit exactly where they were.

    python scripts\close_waiting_committees.py
    python scripts\close_waiting_committees.py --apply

This re-runs the gate over cases that are already waiting, using the CURRENT
configuration. It casts no votes and changes nobody's vote - it only asks, of
the votes already recorded, whether the decision can now close.

WHAT IT WILL NOT DO:

    it will not close a case short of QUORUM        not enough people have
                                                    spoken, and that has not
                                                    changed
    it will not close one still awaiting a chair    where chair_vote_required
                                                    is still true and neither
                                                    the chair nor a deputy has
                                                    voted
    it will not invent or alter a vote              the outcome comes from what
                                                    was already cast

EVERY CLOSURE IS AUDITED as a sweep rather than as a vote, so a case closed
here is distinguishable from one closed by somebody pressing a button.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())


def main():
    apply = "--apply" in sys.argv
    only = ""
    if "--committee" in sys.argv:
        i = sys.argv.index("--committee")
        if i + 1 < len(sys.argv):
            only = sys.argv[i + 1].strip().upper()

    import json
    from utils.core import PipelineManager
    import utils.api as A

    cfg = json.load(open(os.path.join("data", "lms_config.json"),
                         encoding="utf-8"))
    pal = (cfg.get("credit_workflow") or {}).get("committee_palette") or []
    by_code = {str(c.get("code", "")).upper(): c for c in pal}

    pm = PipelineManager()
    deals = pm.deals or []

    print("=" * 84)
    print("COMMITTEE CASES ALREADY VOTED, WAITING TO CLOSE")
    print("=" * 84)

    ready, waiting = [], []
    for d in deals:
        recs = d.get("committee_records") or {}
        votes_by = d.get("committee_votes") or {}
        for code, cast in (votes_by.items() if isinstance(votes_by, dict) else []):
            code_u = str(code).upper()
            if only and code_u != only:
                continue
            if (recs.get(code) or {}).get("outcome"):
                continue                      # already decided
            c = by_code.get(code_u)
            if not c:
                continue
            vlist = list(cast.values()) if isinstance(cast, dict) else list(cast or [])
            attended = len(vlist)
            quorum = int(c.get("min_quorum_count") or c.get("quorum") or 0) or 1
            req = c.get("chair_vote_required", True)
            chair = str(c.get("chaired_by", "") or "").strip().lower()
            deps = {str(m.get("name", "")).strip().lower()
                    for m in (c.get("members") or [])
                    if isinstance(m, dict) and m.get("deputy_chair")}
            spoke = {str(v.get("name", "") or "").strip().lower() for v in vlist}
            authority = True if not req else (chair in spoke or bool(deps & spoke))

            row = (d, code_u, attended, quorum, req, authority)
            if attended >= quorum and authority:
                ready.append(row)
            else:
                waiting.append(row)

    if not ready and not waiting:
        print("  No committee case is waiting.")
        return 0

    if ready:
        print("\n  CAN CLOSE NOW  (%d)" % len(ready))
        print("     %-10s %-24s %-5s %-9s %s"
              % ("DEAL", "CLIENT", "CTTE", "VOTES", "WHY IT CAN"))
        for d, code, att, q, req, _a in ready:
            print("     %-10s %-24s %-5s %d/%-7d %s"
                  % (str(d.get("id"))[:10], str(d.get("client_name"))[:24],
                     code, att, q,
                     "quorum met, chair not required" if not req
                     else "quorum met, chair or deputy voted"))
    if waiting:
        print("\n  STILL WAITING  (%d)" % len(waiting))
        for d, code, att, q, req, auth in waiting[:10]:
            why = ("only %d of %d have voted" % (att, q)) if att < q else \
                  "awaiting the chair or a named deputy"
            print("     %-10s %-24s %-5s %s"
                  % (str(d.get("id"))[:10], str(d.get("client_name"))[:24],
                     code, why))
        if len(waiting) > 10:
            print("     ... and %d more" % (len(waiting) - 10))

    if not ready:
        print("\n  Nothing to close.")
        return 0
    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        print("\n  No vote is cast or altered. The outcome comes from the votes")
        print("  already recorded.")
        return 0

    closed = 0
    for d, code, _att, _q, _req, _a in ready:
        try:
            votes = (d.get("committee_votes") or {}).get(code) \
                or (d.get("committee_votes") or {}).get(code.lower()) or {}
            vlist = list(votes.values()) if isinstance(votes, dict) else list(votes)
            c = by_code.get(code)
            outcome = A._derive_outcome_from_votes(vlist, c.get("voting_rule"), c)
            recs = dict(d.get("committee_records") or {})
            recs[code] = {"outcome": outcome, "mode": "voting", "votes": vlist,
                          "closed_by": "sweep",
                          "closed_at": datetime.now().isoformat(timespec="seconds")}
            d["committee_records"] = recs
            closed += 1
            print("     closed %-10s %-5s -> %s" % (str(d.get("id"))[:10], code, outcome))
        except Exception as exc:
            print("     FAILED %-10s %-5s %s" % (str(d.get("id"))[:10], code,
                                                 str(exc)[:44]))
    if closed:
        pm._save_deals()
    print("\nclosed %d case(s). RESTART UVICORN." % closed)
    print("\nEach is recorded as closed_by 'sweep', so it is distinguishable")
    print("from one closed by somebody pressing a button.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
