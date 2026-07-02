#!/usr/bin/env python3
"""scripts/apply_committee_capture_backend.py — 4b-4: committee decision capture.

For each committee gate in a deal's journey, record the decision ON THE DEAL
(pre-submission). The committee's recording_mode (from the 4b-1 palette) decides:
  - "voting": capture per-member votes {name, role, vote(YES|NO|ABSTAIN)}; the
    outcome is derived from the committee's voting_rule.
  - "single": one authorized user records the outcome directly.

Stored under deal['committee_records'][code] = {outcome, mode, votes[], recorded_by,
recorded_at, note}. Outcome in {APPROVED, REJECTED, DEFERRED}.

Endpoints:
  GET  /api/pipeline/deals/{id}/committee-records   -> journey + recorded decisions
  POST /api/pipeline/deals/{id}/committee-records    -> record one {code, outcome?,
        votes?, note?}

SAFE: .pre_cmtecap backup. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
BAK = API.with_suffix(".py.pre_cmtecap")
MARKER = "# === COMMITTEE DECISION CAPTURE (4b-4) ==="

BLOCK = r'''

# === COMMITTEE DECISION CAPTURE (4b-4) ===
_COMMITTEE_OUTCOMES = ("APPROVED", "REJECTED", "DEFERRED")


def _derive_outcome_from_votes(votes: list, voting_rule: str) -> str:
    """Derive APPROVED/REJECTED from per-member votes and the voting rule.
    YES/NO counted; ABSTAIN/RECUSED excluded from the base. Ties -> REJECTED."""
    yes = sum(1 for v in votes if str(v.get("vote", "")).upper() == "YES")
    no = sum(1 for v in votes if str(v.get("vote", "")).upper() == "NO")
    base = yes + no
    if base == 0:
        return "DEFERRED"
    rule = str(voting_rule or "SIMPLE_MAJORITY")
    if rule == "UNANIMOUS":
        return "APPROVED" if no == 0 and yes > 0 else "REJECTED"
    if rule == "SUPERMAJORITY_TWO_THIRDS":
        return "APPROVED" if (yes / base) >= (2.0 / 3.0) else "REJECTED"
    # SIMPLE_MAJORITY (and default): > 50%, ties -> REJECTED
    return "APPROVED" if yes > no else "REJECTED"


def _committee_by_code(code: str) -> dict:
    for c in _read_committee_palette():
        if str(c.get("code")) == code:
            return c
    return {}


@app.get("/api/pipeline/deals/{deal_id}/committee-records", tags=["pipeline"])
def get_deal_committee_records(deal_id: str, user: dict = Depends(get_current_user)):
    """The deal's effective journey with each gate's palette def + recorded decision."""
    from utils.api_pipeline_scope import get_visible_staff_codes
    from utils.api_pipeline_permissions import resolve_deal_permissions
    from utils.core import PipelineManager as _PM
    pm = _PM()
    deal = _get_or_hydrate_deal(pm, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    visible = get_visible_staff_codes(user)
    if not resolve_deal_permissions(deal, user, visible).get("can_view"):
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    codes = _effective_committee_journey(deal)
    records = deal.get("committee_records", {}) or {}
    gates = []
    for code in codes:
        c = _committee_by_code(code)
        gates.append({
            "code": code,
            "name": c.get("name", code),
            "recording_mode": c.get("recording_mode", "voting"),
            "voting_rule": c.get("voting_rule", "SIMPLE_MAJORITY"),
            "members": c.get("members", []),
            "record": records.get(code),
        })
    return {"gates": gates, "cr_only": len(codes) == 0}


@app.post("/api/pipeline/deals/{deal_id}/committee-records", tags=["pipeline"])
def record_deal_committee_decision(deal_id: str, payload: dict = Body(default_factory=dict),
                                   user: dict = Depends(get_current_user)):
    """Record one committee gate's decision on the deal."""
    from utils.api_pipeline_scope import get_visible_staff_codes
    from utils.api_pipeline_permissions import resolve_deal_permissions
    from utils.core import PipelineManager as _PM
    from datetime import datetime as _dt
    pm = _PM()
    deal = _get_or_hydrate_deal(pm, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")
    visible = get_visible_staff_codes(user)
    if not resolve_deal_permissions(deal, user, visible).get("can_view"):
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")

    code = str(payload.get("code", "")).strip()
    if not code:
        raise HTTPException(status_code=400, detail="committee code is required")
    journey = _effective_committee_journey(deal)
    if code not in journey:
        raise HTTPException(status_code=400,
            detail=f"'{code}' is not in this deal's committee journey")
    committee = _committee_by_code(code)
    mode = str(committee.get("recording_mode", "voting"))
    note = str(payload.get("note", "") or "")

    if mode == "voting":
        votes = payload.get("votes") or []
        if not isinstance(votes, list) or not votes:
            raise HTTPException(status_code=400, detail="voting committee requires votes[]")
        clean_votes = []
        for v in votes:
            if not isinstance(v, dict):
                continue
            vote = str(v.get("vote", "")).upper()
            if vote not in ("YES", "NO", "ABSTAIN", "RECUSED"):
                raise HTTPException(status_code=400, detail=f"invalid vote '{vote}'")
            clean_votes.append({"name": str(v.get("name", "")).strip(),
                                "role": str(v.get("role", "")).strip(), "vote": vote})
        outcome = _derive_outcome_from_votes(clean_votes, committee.get("voting_rule"))
        record = {"outcome": outcome, "mode": "voting", "votes": clean_votes, "note": note}
    else:
        outcome = str(payload.get("outcome", "")).upper()
        if outcome not in _COMMITTEE_OUTCOMES:
            raise HTTPException(status_code=400,
                detail=f"outcome must be one of {_COMMITTEE_OUTCOMES}")
        record = {"outcome": outcome, "mode": "single", "votes": [], "note": note}

    record["recorded_by"] = str(user.get("username", "") or "")
    record["recorded_at"] = _dt.now().isoformat(timespec="seconds")

    records = dict(deal.get("committee_records", {}) or {})
    records[code] = record
    pm.update_deal(deal_id, {"committee_records": records}, str(user.get("username", "") or ""))
    _audit("API_DEAL_COMMITTEE_RECORD", user, f"deal={deal_id}|code={code}|outcome={record['outcome']}")
    return {"status": "recorded", "code": code, "record": record}
# === END COMMITTEE DECISION CAPTURE ===
'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, API); BAK.unlink(); print("  reverted api.py from .pre_cmtecap")
    else:
        print("  no .pre_cmtecap backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = API.read_text(encoding="utf-8")
    if MARKER in s:
        print("  already applied."); return
    if "_effective_committee_journey" not in s:
        print("  ERROR: 4b-2 (journey resolver) must be applied first."); sys.exit(1)
    if dry:
        print(f"  --dry-run: would append committee capture endpoints ({len(BLOCK)} chars)."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    API.write_text(s.rstrip() + "\n" + BLOCK + "\n", encoding="utf-8")
    print("  appended committee capture endpoints. Restart API.")

if __name__ == "__main__":
    main()
