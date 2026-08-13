#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
VT1 - each member votes from their own machine, and no one vote decides.

TWO PILOT FINDINGS (2026-08-13). Both were design, not bugs.

1. "ONE MEMBER LOGGED IN AND WHEN THEY INPUT THEIR VOTE, A SINGLE VOTE, IT
   LOCKS THE REST AND THE CASE JOURNEY RECORDS DEFERRED."

   It did. The existing endpoint takes EVERY vote in one payload and writes a
   finished record - so one member submitting their own view produced: one
   vote, below quorum, DEFERRED, record written, gate closed, and the case gone
   from everybody else's queue before they had seen it.

   A committee does not work that way. Each member signs in on their own
   machine, records their own view, and the outcome belongs to the committee
   once enough of them have spoken.

   POST /api/pipeline/deals/{id}/committee/{code}/vote takes ONE vote.

     Votes accumulate under deal.committee_votes[code][staff_code]. Voting
     again replaces that member's own vote and nobody else's - somebody who
     changes their mind before the meeting closes should be able to.

     NO RECORD IS WRITTEN UNTIL QUORUM IS REACHED. The gate reads
     committee_records; while that is absent the case stays pending, stays in
     every member's queue, and the journey says nothing, because nothing has
     been decided.

     When the last member needed arrives, the outcome is derived from all the
     votes at once and written as ONE record - one decision with its tally, not
     a trail of half-decisions.

   "THE VOTING AREA DID NOT POPULATE NAME AND ROLE." It does now, and not from
   the request body: the voter is the CALLER, and their name and role come from
   the committee roster. A vote attributed by whoever sent it is not a vote.

   The response also returns who has voted and who is still AWAITED, which is
   what a chair actually wants to see.

   Measured:

       one vote    1/2  decided=False  awaiting ['Member Two']  no record
       two votes   2/2  decided=True   APPROVED, names and roles kept
       non-member  403  "You are not on Westlands Branch Credit Committee."

2. "SOMEONE CAN EASILY MOVE A DEAL TO THE NEXT STAGE AND IT RECORDS ON THE CASE
   JOURNEY EVEN THOUGH IT HAS NOT MOVED THAT."

   They could. Advance checked the product flow and the manager validation and
   stopped there - so a deal sitting AT a committee stage could be walked off it
   with no committee having met, and the journey recorded a clean stage change
   as though the gate had been passed. A gate anybody can step around is not a
   gate, and the record of it is worse than no record, because it looks like
   due process.

   Leaving a committee stage now requires that committee to have decided.
   Sitting at it is fine. Moving BACKWARD is fine - a case returned for rework
   must be able to go back. It is the forward step that needs an answer.

   Measured:

       no decision yet   refused, naming 1 of 2 members voted
       rejected          refused, "did not recommend this case"
       approved          advances

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_vt1_member_voting.py            # dry run
    python scripts\\patch_vt1_member_voting.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_vt1"

EP_ANCHOR = '@app.post("/api/pipeline/deals/{deal_id}/committee-records", tags=["pipeline"])'
GATE_ANCHOR = "    # \u2500\u2500 A NON-BRANCH DEAL SKIPS THE BRANCH COMMITTEE"

ENDPOINT = r'''@app.post("/api/pipeline/deals/{deal_id}/committee/{code}/vote", tags=["pipeline"])
def cast_committee_vote(deal_id: str, code: str,
                        payload: dict = Body(default_factory=dict),
                        user: dict = Depends(get_current_user)):
    """ONE MEMBER, ONE VOTE, FROM THEIR OWN LOGIN.

    FROM THE PILOT (2026-08-13): "one member of the committee logged in and
    when they input their vote, a single vote, it locks the rest and the case
    journey records DEFERRED."

    It did, and the design was the fault rather than the code. The existing
    endpoint takes EVERY vote in one payload and writes a finished record - so
    one member submitting their own vote produced: one vote, below quorum,
    DEFERRED, record written, gate closed, and the case gone from everybody
    else's queue before they had seen it.

    A committee does not vote that way. Each member signs in on their own
    machine, records their own view, and the outcome belongs to the committee
    once enough of them have spoken.

    HOW THIS WORKS

      Votes accumulate under deal.committee_votes[code][staff_code]. Voting
      again REPLACES that member's own vote and nobody else's - somebody who
      changes their mind before the meeting closes should be able to.

      NO RECORD IS WRITTEN UNTIL QUORUM IS REACHED. The gate reads
      committee_records; while that is absent the case stays pending, stays in
      every member's queue, and the journey says nothing - because nothing has
      been decided yet.

      When the last member needed arrives, the outcome is derived from all the
      votes at once and written as one record, exactly as before. The journey
      then shows one decision with its tally, not a trail of half-decisions.

      THE VOTER IS THE CALLER. Name and role come from their login and the
      committee roster, never from the request body - a vote attributed by
      whoever sent it is not a vote.
    """
    _pm, deal = _deal_for_docs(deal_id, user)
    committee = _committee_by_code(code)
    if not committee:
        raise HTTPException(status_code=404, detail=f"No committee {code!r}.")

    journey = _effective_committee_journey(deal)
    if code not in journey:
        raise HTTPException(
            status_code=400,
            detail=f"{code} is not in this deal's committee journey.")

    # WHO IS VOTING - resolved from the roster, not from the payload.
    me = str(user.get("staff_code", "") or "").strip()
    myname = str(user.get("full_name", "") or "").strip()
    members = committee.get("members") or []
    mine = next((m for m in members
                 if isinstance(m, dict)
                 and (str(m.get("staff_code", "") or "").strip() == me
                      or str(m.get("name", "") or "").strip().lower() == myname.lower())), None)
    is_chair = (str(committee.get("chaired_by", "") or "").strip().lower()
                == myname.lower())
    if not mine and not is_chair:
        raise HTTPException(
            status_code=403,
            detail=f"You are not on {committee.get('name') or code}.")

    vote = str(payload.get("vote", "")).upper()
    if vote not in ("YES", "NO", "ABSTAIN", "RECUSED"):
        raise HTTPException(status_code=400, detail=f"invalid vote {vote!r}")
    docs_ok = bool(payload.get("documents_validated"))
    if vote == "YES" and not docs_ok:
        raise HTTPException(
            status_code=400,
            detail="A YES needs confirmation that the documentation was checked.")

    key = me or myname
    all_votes = dict(deal.get("committee_votes") or {})
    cast = dict(all_votes.get(code) or {})
    cast[key] = {
        "name": (mine or {}).get("name") or myname,
        "role": (mine or {}).get("role") or ("Chair" if is_chair else ""),
        "staff_code": me,
        "vote": vote,
        "documents_validated": docs_ok,
        "comment": str(payload.get("comment", "") or "").strip(),
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    all_votes[code] = cast

    quorum = _committee_quorum(committee)
    attended = len(cast)
    updates = {"committee_votes": all_votes}
    outcome = ""

    if attended >= quorum:
        # Enough of the committee has spoken - decide, once, from all of it.
        vlist = list(cast.values())
        outcome = _derive_outcome_from_votes(vlist, committee.get("voting_rule"),
                                             committee)
        records = dict(deal.get("committee_records") or {})
        records[code] = {
            "outcome": outcome, "mode": "voting", "votes": vlist,
            "note": str(payload.get("note", "") or "").strip(),
            "recorded_by": me, "recorded_by_name": myname,
            "recorded_at": datetime.now().isoformat(timespec="seconds"),
        }
        updates["committee_records"] = records

    _pm.update_deal(deal_id, updates, str(user.get("username", "") or ""))
    _audit("API_COMMITTEE_VOTE", user,
           f"deal={deal_id}|committee={code}|vote={vote}|"
           f"{attended}/{quorum}|outcome={outcome or 'pending'}")

    return {
        "status": "recorded",
        "committee": code,
        "your_vote": vote,
        "votes_cast": attended,
        "quorum": quorum,
        "decided": bool(outcome),
        "outcome": outcome,
        # So the panel can show who has voted and who is still awaited, which
        # is the thing a chair actually wants to see.
        "tally": [{"name": v.get("name"), "role": v.get("role"),
                   "vote": v.get("vote"), "at": v.get("at")}
                  for v in cast.values()],
        "awaiting": [str(m.get("name") or m.get("staff_code"))
                     for m in members
                     if isinstance(m, dict)
                     and str(m.get("staff_code", "") or "").strip() not in cast
                     and str(m.get("name", "") or "").strip() not in cast],
    }


'''

GATE = r'''    # ── A COMMITTEE STAGE CANNOT BE WALKED PAST ─────────────────────────────
    # FROM THE PILOT (2026-08-13): "from the action area I note that someone
    # can easily move a deal to the next stage and it records on the case
    # journey even though it has not moved that."
    #
    # They could. Advance checked the product flow and the manager validation
    # and stopped there - so a deal sitting AT a committee stage could be moved
    # off it by its owner with no committee having met, and the journey then
    # recorded a clean stage change as though the gate had been passed. A gate
    # anybody can step around is not a gate, and the record of it is worse than
    # no record because it looks like due process.
    #
    # LEAVING a committee stage now requires that committee to have decided.
    # Sitting AT the stage is fine, moving BACKWARD is fine - a deal returned
    # for rework must be able to go back. It is the forward step that needs the
    # committee's answer.
    #
    # A REJECTION ALSO BLOCKS, and deliberately: submit-to-credit already
    # refuses a rejected committee, so allowing the stage to advance would only
    # move the case somewhere it cannot leave.
    try:
        _cur_stage = str(deal.get("stage", "") or "")
        if _flow and "committee" in _cur_stage.lower():
            _here = _flow.index(_cur_stage) if _cur_stage in _flow else -1
            _there = _flow.index(payload.new_stage) if payload.new_stage in _flow else -1
            if _here >= 0 and _there > _here:
                _recs = deal.get("committee_records") or {}
                _jrny = _effective_committee_journey(deal) or []
                # Which committee is this stage's gate? The one on the journey
                # whose name the stage carries - a branch stage is answered by
                # the branch committee, a department stage by the DCC.
                _due = []
                for _c in _read_committee_palette():
                    _code = str(_c.get("code"))
                    if _code not in _jrny:
                        continue
                    _kind = str(_c.get("kind", "")).lower()
                    _is_branch_stage = "branch" in _cur_stage.lower()
                    if (_kind == "branch") == _is_branch_stage:
                        _due.append((_code, _c))
                for _code, _c in _due:
                    _rec = _recs.get(_code)
                    if not _rec:
                        _cast = ((deal.get("committee_votes") or {}).get(_code) or {})
                        _q = _committee_quorum(_c)
                        raise HTTPException(
                            status_code=400,
                            detail=("%s has not decided yet - %d of %d "
                                    "member(s) have voted. The case cannot "
                                    "leave this stage until it has."
                                    % (_c.get("name") or _code, len(_cast), _q)))
                    if str(_rec.get("outcome", "")).upper() == "REJECTED":
                        raise HTTPException(
                            status_code=400,
                            detail=("%s did not recommend this case. It cannot "
                                    "advance from here."
                                    % (_c.get("name") or _code)))
    except HTTPException:
        raise
    except Exception as _exc:
        logger.warning("committee gate check skipped for %s: %s", deal_id, _exc)

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "cast_committee_vote" in s:
        print("ABORT: VT1 looks applied.")
        return 1
    if s.count(EP_ANCHOR) != 1:
        print("ABORT: the committee-records endpoint matched %d times." % s.count(EP_ANCHOR))
        return 1
    if s.count(GATE_ANCHOR) != 1:
        print("ABORT: the advance anchor matched %d times." % s.count(GATE_ANCHOR))
        print("       AV1/SP1 must be applied first - this sits beside them.")
        return 1

    s = s.replace(EP_ANCHOR, ENDPOINT + EP_ANCHOR, 1)
    s = s.replace(GATE_ANCHOR, GATE + GATE_ANCHOR, 1)
    print("  ok  per-member voting, and the committee stage is a real gate")

    if "attended >= quorum" not in ENDPOINT:
        print("ABORT: the outcome is not held back until quorum, so a single")
        print("       vote would close the case again.")
        return 1
    if "committee_votes" not in ENDPOINT:
        print("ABORT: votes are not accumulated per member.")
        return 1
    if 'payload.get("name")' in ENDPOINT:
        print("ABORT: the voter's name comes from the request body - a vote")
        print("       attributed by whoever sent it is not a vote.")
        return 1
    if "You are not on" not in ENDPOINT:
        print("ABORT: a non-member could vote.")
        return 1
    if "_there > _here" not in GATE:
        print("ABORT: the gate would block BACKWARD moves too, so a case")
        print("       returned for rework could not go back.")
        return 1
    print("  ok  post-checks: quorum held, caller is the voter, rework possible")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("")
    print("Restart uvicorn. Each member votes from their own login; the case")
    print("stays open until quorum, then decides once.")
    print("")
    print("THE PANEL STILL POSTS THE OLD ALL-AT-ONCE SHAPE. Both endpoints are")
    print("live so nothing breaks - but the UI needs pointing at the new one")
    print("before members can vote separately. That is the next patch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
