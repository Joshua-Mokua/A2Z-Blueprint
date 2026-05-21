"""
================================================================================
A2Z MIS 360 — Standards #316 + #320: Mobile Briefing + Secure Board Portal
================================================================================

Risk classification: Cat C (executive content delivery + access control)

Combined module:
    #316: Mobile-first executive view: critical KPIs, alerts, approvals,
          briefing pack. Offline support for travel.
    #320: Secure board portal: meeting packs, papers, voting, action items,
          minutes. Annotation + private notes.

Standards consolidated because both deliver pre-curated executive content
through controlled-access channels (mobile briefing for daily ops,
board portal for governance) — same access-control + content-curation
mechanics, different audiences.

Public API (#316 mobile briefing):
    register_briefing_pack(pack_data, actor, reason)
    add_section_to_pack(pack_id, section_data, actor)
    publish_pack(pack_id, actor, reason)
    fetch_pack_for_role(pack_id, viewer_role)

Public API (#320 board portal):
    register_board_meeting(meeting_data, actor, reason)
    add_paper_to_meeting(meeting_id, paper_data, actor)
    record_vote(meeting_id, paper_id, board_member, vote, actor)
    record_action_item(meeting_id, action_data, actor)
    publish_minutes(meeting_id, minutes_text, actor, reason)
    fetch_meeting_for_member(meeting_id, board_member)

BRIEFING_PACK_STATES byte-for-byte (4): DRAFT, PUBLISHED, ARCHIVED, EXPIRED
BRIEFING_SECTION_TYPES byte-for-byte (5):
    KPI_SNAPSHOT, ALERT_DIGEST, PENDING_APPROVAL, NARRATIVE, ACTION_ITEMS

BOARD_MEETING_STATES byte-for-byte (5):
    SCHEDULED, IN_PROGRESS, COMPLETED, CANCELLED, ARCHIVED

BOARD_VOTE_OUTCOMES byte-for-byte (4):
    APPROVE, REJECT, ABSTAIN, RECUSED

BOARD_PAPER_TYPES byte-for-byte (6):
    STRATEGIC, FINANCIAL, RISK, COMPLIANCE, AUDIT, OTHER

ACTION_ITEM_STATES byte-for-byte (4): PENDING, IN_PROGRESS, COMPLETED, CANCELLED

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


BRIEFING_PACK_STATES: Tuple[str, ...] = (
    "DRAFT", "PUBLISHED", "ARCHIVED", "EXPIRED",
)

BRIEFING_SECTION_TYPES: Tuple[str, ...] = (
    "KPI_SNAPSHOT", "ALERT_DIGEST", "PENDING_APPROVAL",
    "NARRATIVE", "ACTION_ITEMS",
)

BOARD_MEETING_STATES: Tuple[str, ...] = (
    "SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED", "ARCHIVED",
)

BOARD_VOTE_OUTCOMES: Tuple[str, ...] = (
    "APPROVE", "REJECT", "ABSTAIN", "RECUSED",
)

BOARD_PAPER_TYPES: Tuple[str, ...] = (
    "STRATEGIC", "FINANCIAL", "RISK", "COMPLIANCE", "AUDIT", "OTHER",
)

ACTION_ITEM_STATES: Tuple[str, ...] = (
    "PENDING", "IN_PROGRESS", "COMPLETED", "CANCELLED",
)


class CommandCentreMobileBoardEngine:
    """Mobile briefing packs (#316) + secure board portal (#320)."""

    def __init__(
        self,
        packs_path: Optional[Path] = None,
        meetings_path: Optional[Path] = None,
        papers_path: Optional[Path] = None,
        votes_path: Optional[Path] = None,
        actions_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.packs_path = packs_path or base / "briefing_packs.json"
        self.meetings_path = meetings_path or base / "board_meetings.json"
        self.papers_path = papers_path or base / "board_papers.json"
        self.votes_path = votes_path or base / "board_votes.json"
        self.actions_path = actions_path or base / "board_actions.json"

    def _load(self, path: Path, table: str, idx: Tuple[str, ...]) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(path, table=table, index_cols=idx)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, path: Path, records: List[Dict[str, Any]],
                table: str, pk: str) -> bool:
        try:
            from utils.db import db as _db
            path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(path, data=records, table=table, pk_col=pk)
            return True
        except Exception:
            return False

    # ── #316 Mobile Briefing Pack ─────────────────────────────────

    def register_briefing_pack(
        self, pack_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("pack_id", "pack_name", "for_role"):
            if f not in pack_data or not pack_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        records = self._load(self.packs_path, "briefing_packs", ("pack_id",))
        if any(r.get("pack_id") == pack_data["pack_id"] for r in records):
            return {"registered": False, "error": "duplicate_pack_id"}
        record = {
            "pack_id": pack_data["pack_id"],
            "pack_name": pack_data["pack_name"],
            "for_role": pack_data["for_role"],
            "title": pack_data.get("title", ""),
            "as_of_date": pack_data.get(
                "as_of_date", datetime.utcnow().date().isoformat(),
            ),
            "expires_at": pack_data.get("expires_at"),
            "sections": [],
            "state": "DRAFT",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.packs_path, records,
                          "briefing_packs", "pack_id")
        return {"registered": ok, "pack_id": pack_data["pack_id"]}

    def add_section_to_pack(
        self, pack_id: str, section_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"added": False, "error": "actor_required"}
        for f in ("section_id", "section_type", "title"):
            if f not in section_data or not section_data[f]:
                return {"added": False, "error": f"missing_field:{f}"}
        if section_data["section_type"] not in BRIEFING_SECTION_TYPES:
            return {"added": False,
                       "error": f"invalid_section_type:{section_data['section_type']}"}
        records = self._load(self.packs_path, "briefing_packs", ("pack_id",))
        for r in records:
            if r.get("pack_id") == pack_id:
                if r["state"] != "DRAFT":
                    return {"added": False,
                               "error": f"pack_not_editable:{r['state']}"}
                section = {
                    "section_id": section_data["section_id"],
                    "section_type": section_data["section_type"],
                    "title": section_data["title"],
                    "content": section_data.get("content", ""),
                    "data_payload": section_data.get("data_payload", {}),
                    "added_by": actor,
                    "added_at": datetime.utcnow().isoformat(),
                }
                r.setdefault("sections", []).append(section)
                ok = self._save(self.packs_path, records,
                                  "briefing_packs", "pack_id")
                return {"added": ok, "section_id": section_data["section_id"]}
        return {"added": False, "error": "pack_not_found"}

    def publish_pack(
        self, pack_id: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"published": False, "error": "actor_and_reason_required"}
        records = self._load(self.packs_path, "briefing_packs", ("pack_id",))
        for r in records:
            if r.get("pack_id") == pack_id:
                if r["state"] != "DRAFT":
                    return {"published": False,
                               "error": f"pack_not_in_draft:{r['state']}"}
                if not r.get("sections"):
                    return {"published": False,
                               "error": "pack_has_no_sections"}
                r["state"] = "PUBLISHED"
                r["published_by"] = actor
                r["published_at"] = datetime.utcnow().isoformat()
                r["publish_reason"] = reason
                ok = self._save(self.packs_path, records,
                                  "briefing_packs", "pack_id")
                return {"published": ok}
        return {"published": False, "error": "pack_not_found"}

    def fetch_pack_for_role(
        self, pack_id: str, viewer_role: str,
    ) -> Dict[str, Any]:
        if not viewer_role:
            return {"available": False, "error": "viewer_role_required"}
        records = self._load(self.packs_path, "briefing_packs", ("pack_id",))
        for r in records:
            if r.get("pack_id") == pack_id:
                if r["for_role"] != viewer_role:
                    return {"available": False, "error": "access_denied"}
                if r["state"] not in ("PUBLISHED",):
                    return {"available": False,
                               "error": f"pack_state_not_viewable:{r['state']}"}
                return {
                    "available": True,
                    "pack_id": pack_id,
                    "pack_name": r["pack_name"],
                    "title": r.get("title", ""),
                    "as_of_date": r.get("as_of_date", ""),
                    "section_count": len(r.get("sections", [])),
                    "sections": r.get("sections", []),
                }
        return {"available": False, "error": "pack_not_found"}

    # ── #320 Board Portal ──────────────────────────────────────────

    def register_board_meeting(
        self, meeting_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("meeting_id", "meeting_name", "scheduled_for", "board_members"):
            if f not in meeting_data or meeting_data[f] in (None, "", []):
                return {"registered": False, "error": f"missing_field:{f}"}
        records = self._load(self.meetings_path,
                                "board_meetings", ("meeting_id",))
        if any(r.get("meeting_id") == meeting_data["meeting_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_meeting_id"}
        record = {
            "meeting_id": meeting_data["meeting_id"],
            "meeting_name": meeting_data["meeting_name"],
            "scheduled_for": meeting_data["scheduled_for"],
            "board_members": list(meeting_data["board_members"]),
            "papers": [],
            "minutes": None,
            "state": "SCHEDULED",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.meetings_path, records,
                          "board_meetings", "meeting_id")
        return {"registered": ok, "meeting_id": meeting_data["meeting_id"]}

    def add_paper_to_meeting(
        self, meeting_id: str, paper_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"added": False, "error": "actor_required"}
        for f in ("paper_id", "paper_title", "paper_type"):
            if f not in paper_data or not paper_data[f]:
                return {"added": False, "error": f"missing_field:{f}"}
        if paper_data["paper_type"] not in BOARD_PAPER_TYPES:
            return {"added": False,
                       "error": f"invalid_paper_type:{paper_data['paper_type']}"}
        records = self._load(self.meetings_path,
                                "board_meetings", ("meeting_id",))
        for r in records:
            if r.get("meeting_id") == meeting_id:
                if r["state"] not in ("SCHEDULED", "IN_PROGRESS"):
                    return {"added": False,
                               "error": f"meeting_not_active:{r['state']}"}
                paper = {
                    "paper_id": paper_data["paper_id"],
                    "paper_title": paper_data["paper_title"],
                    "paper_type": paper_data["paper_type"],
                    "summary": paper_data.get("summary", ""),
                    "document_url": paper_data.get("document_url", ""),
                    "voting_required": paper_data.get(
                        "voting_required", False,
                    ),
                    "added_by": actor,
                    "added_at": datetime.utcnow().isoformat(),
                }
                r.setdefault("papers", []).append(paper)
                ok = self._save(self.meetings_path, records,
                                  "board_meetings", "meeting_id")
                return {"added": ok, "paper_id": paper_data["paper_id"]}
        return {"added": False, "error": "meeting_not_found"}

    def record_vote(
        self, meeting_id: str, paper_id: str,
        board_member: str, vote: str, actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        if vote not in BOARD_VOTE_OUTCOMES:
            return {"recorded": False, "error": f"invalid_vote:{vote}"}
        # Verify member is registered to this meeting
        meetings = self._load(self.meetings_path,
                                    "board_meetings", ("meeting_id",))
        meeting = next((m for m in meetings
                            if m.get("meeting_id") == meeting_id), None)
        if meeting is None:
            return {"recorded": False, "error": "meeting_not_found"}
        if board_member not in meeting.get("board_members", []):
            return {"recorded": False, "error": "member_not_registered"}
        # Verify paper is on the meeting
        if not any(p.get("paper_id") == paper_id
                       for p in meeting.get("papers", [])):
            return {"recorded": False, "error": "paper_not_on_meeting"}

        votes = self._load(self.votes_path, "board_votes", ("vote_id",))
        # Reject duplicate votes (one per member per paper)
        if any(v.get("meeting_id") == meeting_id
                  and v.get("paper_id") == paper_id
                  and v.get("board_member") == board_member
                  for v in votes):
            return {"recorded": False, "error": "duplicate_vote"}

        vote_id = (f"VOTE-{meeting_id}-{paper_id}-{board_member}-"
                       f"{int(datetime.utcnow().timestamp() * 1000)}")
        votes.append({
            "vote_id": vote_id,
            "meeting_id": meeting_id,
            "paper_id": paper_id,
            "board_member": board_member,
            "vote": vote,
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.votes_path, votes, "board_votes", "vote_id")
        return {"recorded": ok, "vote_id": vote_id}

    def record_action_item(
        self, meeting_id: str, action_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("action_id", "description", "owner", "due_date"):
            if f not in action_data or not action_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        actions = self._load(self.actions_path,
                                  "board_actions", ("action_id",))
        if any(a.get("action_id") == action_data["action_id"] for a in actions):
            return {"recorded": False, "error": "duplicate_action_id"}
        action = {
            "action_id": action_data["action_id"],
            "meeting_id": meeting_id,
            "description": action_data["description"],
            "owner": action_data["owner"],
            "due_date": action_data["due_date"],
            "state": "PENDING",
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        actions.append(action)
        ok = self._save(self.actions_path, actions,
                          "board_actions", "action_id")
        return {"recorded": ok, "action_id": action_data["action_id"]}

    def publish_minutes(
        self, meeting_id: str, minutes_text: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"published": False, "error": "actor_and_reason_required"}
        if not minutes_text or not minutes_text.strip():
            return {"published": False, "error": "empty_minutes"}
        records = self._load(self.meetings_path,
                                "board_meetings", ("meeting_id",))
        for r in records:
            if r.get("meeting_id") == meeting_id:
                r["minutes"] = {
                    "text": minutes_text,
                    "published_by": actor,
                    "published_at": datetime.utcnow().isoformat(),
                    "publish_reason": reason,
                }
                if r["state"] == "IN_PROGRESS":
                    r["state"] = "COMPLETED"
                ok = self._save(self.meetings_path, records,
                                  "board_meetings", "meeting_id")
                return {"published": ok}
        return {"published": False, "error": "meeting_not_found"}

    def fetch_meeting_for_member(
        self, meeting_id: str, board_member: str,
    ) -> Dict[str, Any]:
        if not board_member:
            return {"available": False, "error": "board_member_required"}
        records = self._load(self.meetings_path,
                                "board_meetings", ("meeting_id",))
        for r in records:
            if r.get("meeting_id") == meeting_id:
                if board_member not in r.get("board_members", []):
                    return {"available": False, "error": "access_denied"}
                # Include all votes for context
                votes = self._load(self.votes_path,
                                         "board_votes", ("vote_id",))
                meeting_votes = [v for v in votes
                                       if v.get("meeting_id") == meeting_id]
                actions = self._load(self.actions_path,
                                           "board_actions", ("action_id",))
                meeting_actions = [a for a in actions
                                          if a.get("meeting_id") == meeting_id]
                return {
                    "available": True,
                    "meeting_id": meeting_id,
                    "meeting_name": r["meeting_name"],
                    "scheduled_for": r["scheduled_for"],
                    "state": r["state"],
                    "papers": r.get("papers", []),
                    "votes": meeting_votes,
                    "actions": meeting_actions,
                    "minutes": r.get("minutes"),
                }
        return {"available": False, "error": "meeting_not_found"}


def _self_test() -> None:
    import tempfile

    assert "PUBLISHED" in BRIEFING_PACK_STATES
    assert "KPI_SNAPSHOT" in BRIEFING_SECTION_TYPES
    assert "APPROVE" in BOARD_VOTE_OUTCOMES
    assert "STRATEGIC" in BOARD_PAPER_TYPES
    assert "PENDING" in ACTION_ITEM_STATES

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CommandCentreMobileBoardEngine(
            packs_path=Path(tmpdir) / "p.json",
            meetings_path=Path(tmpdir) / "m.json",
            papers_path=Path(tmpdir) / "pp.json",
            votes_path=Path(tmpdir) / "v.json",
            actions_path=Path(tmpdir) / "a.json",
        )
        # Briefing pack (#316)
        # Test 1: register pack
        r = engine.register_briefing_pack(
            {"pack_id": "PACK-MD-DAILY",
             "pack_name": "MD Daily Briefing",
             "for_role": "MD",
             "title": "Daily Brief — May 7"},
            actor="cdo", reason="daily MD pack",
        )
        assert r["registered"]
        # Test 2: add sections
        r = engine.add_section_to_pack(
            "PACK-MD-DAILY",
            {"section_id": "S1", "section_type": "KPI_SNAPSHOT",
             "title": "Top KPIs", "content": "NPL 5.2%; Deposits +3%"},
            actor="cdo",
        )
        assert r["added"]
        r = engine.add_section_to_pack(
            "PACK-MD-DAILY",
            {"section_id": "S2", "section_type": "ALERT_DIGEST",
             "title": "Active alerts", "content": "3 critical, 5 high"},
            actor="cdo",
        )
        assert r["added"]
        # Test 3: invalid section type
        r = engine.add_section_to_pack(
            "PACK-MD-DAILY",
            {"section_id": "S3", "section_type": "INVALID", "title": "Z"},
            actor="cdo",
        )
        assert not r["added"]
        # Test 4: publish empty pack
        r = engine.register_briefing_pack(
            {"pack_id": "PACK-EMPTY", "pack_name": "Empty",
             "for_role": "MD"},
            actor="cdo", reason="r",
        )
        r = engine.publish_pack("PACK-EMPTY", actor="cdo", reason="x")
        assert not r["published"]
        # Test 5: publish populated pack
        r = engine.publish_pack("PACK-MD-DAILY", actor="cdo", reason="ready")
        assert r["published"]
        # Test 6: fetch by correct role
        r = engine.fetch_pack_for_role("PACK-MD-DAILY", "MD")
        assert r["available"]
        assert r["section_count"] == 2
        # Test 7: fetch by wrong role
        r = engine.fetch_pack_for_role("PACK-MD-DAILY", "BRANCH_MGR")
        assert not r["available"]
        # Test 8: cannot edit published pack
        r = engine.add_section_to_pack(
            "PACK-MD-DAILY",
            {"section_id": "S99", "section_type": "NARRATIVE", "title": "X"},
            actor="cdo",
        )
        assert not r["added"]

        # Board portal (#320)
        # Test 9: register meeting
        r = engine.register_board_meeting(
            {"meeting_id": "BM-2026-Q2",
             "meeting_name": "Board Q2 Meeting",
             "scheduled_for": "2026-06-30T09:00:00",
             "board_members": ["MEM-1", "MEM-2", "MEM-3"]},
            actor="secretary", reason="quarterly board",
        )
        assert r["registered"]
        # Test 10: add paper
        r = engine.add_paper_to_meeting(
            "BM-2026-Q2",
            {"paper_id": "PAP-RISK-Q2", "paper_title": "Risk Review Q2",
             "paper_type": "RISK", "voting_required": True,
             "summary": "Quarterly risk review"},
            actor="cro",
        )
        assert r["added"]
        # Test 11: invalid paper type
        r = engine.add_paper_to_meeting(
            "BM-2026-Q2",
            {"paper_id": "X", "paper_title": "Y", "paper_type": "INVALID"},
            actor="x",
        )
        assert not r["added"]
        # Test 12: vote
        r = engine.record_vote(
            "BM-2026-Q2", "PAP-RISK-Q2", "MEM-1", "APPROVE",
            actor="secretary",
        )
        assert r["recorded"]
        # Test 13: invalid vote outcome
        r = engine.record_vote(
            "BM-2026-Q2", "PAP-RISK-Q2", "MEM-2", "MAYBE",
            actor="secretary",
        )
        assert not r["recorded"]
        # Test 14: duplicate vote
        r = engine.record_vote(
            "BM-2026-Q2", "PAP-RISK-Q2", "MEM-1", "REJECT",
            actor="secretary",
        )
        assert not r["recorded"]
        # Test 15: vote by non-member
        r = engine.record_vote(
            "BM-2026-Q2", "PAP-RISK-Q2", "MEM-99", "APPROVE",
            actor="secretary",
        )
        assert not r["recorded"]
        # Test 16: action item
        r = engine.record_action_item(
            "BM-2026-Q2",
            {"action_id": "ACT-1", "description": "Review IFRS9 model",
             "owner": "CRO", "due_date": "2026-08-31"},
            actor="secretary",
        )
        assert r["recorded"]
        # Test 17: minutes
        r = engine.publish_minutes(
            "BM-2026-Q2", "Minutes content...",
            actor="secretary", reason="finalized",
        )
        assert r["published"]
        # Test 18: fetch meeting
        r = engine.fetch_meeting_for_member("BM-2026-Q2", "MEM-1")
        assert r["available"]
        assert len(r["votes"]) >= 1
        assert len(r["actions"]) >= 1
        assert r["minutes"] is not None
        # Test 19: fetch meeting access denied
        r = engine.fetch_meeting_for_member("BM-2026-Q2", "MEM-99")
        assert not r["available"]

    print("  ✅ command_centre_mobile_board self-test PASS")


if __name__ == "__main__":
    _self_test()
