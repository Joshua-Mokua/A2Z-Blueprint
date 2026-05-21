"""utils.strategy_communication — Strategy Communication Engine
(Standard ENH-152, v10.140). Phase 1 Strategy Module — thirteenth engine.

Per Continuation.docx §Standard #152 (Eco Bank QA spec):
    StrategyCommunicationEngine — automated multi-channel strategy
    communication. Distribute strategy updates to executives,
    managers, and staff with role-personalized messaging. Collect
    feedback and analyze sentiment.

This is a Category D standard. Per Rule 7 (No silent ML predictions):

  1. Audience segmentation is rule-based on users.json employment_type
     + role/title fields — same input → same segmentation
  2. Message personalization uses templates per audience tier — no
     fabricated content
  3. Delivery channels are CONFIGURABLE adapters (callable hooks):
     send_email_fn, send_slack_fn, send_app_notification_fn — not
     real network calls. Output explicitly tags delivery_status:
     "prepared" when no adapters injected, "sent" only when adapter
     succeeds, "failed" on adapter exception
  4. Sentiment analysis is rule-based (positive/negative keyword
     scan); LLM hook (ai_sentiment_fn) opt-in with basis="llm" tag

WHAT THIS MODULE SHIPS
----------------------
1. StrategyCommunicationEngine class with:
   - distribute_strategy_update(update) — full pipeline: segment +
     personalize + dispatch + collect feedback + sentiment
   - segment_audience() — categorize users into executives/managers/staff
   - prepare_executive_message(update) — detailed report tier
   - prepare_manager_message(update)   — Slack-style tier
   - prepare_staff_message(update)     — app notification tier
   - collect_feedback(update_id) — load from data/strategy_feedback.json
   - analyze_sentiment(comments) — rule-based or LLM

2. Audience segmentation rules (read-only from users.json):
   - Executives: role/title contains CEO/CFO/CRO/CTO/MD/Director/Chief
   - Managers:   role/title contains Manager/Head OR employment_type=
     MANAGEMENT (exclusive of executives)
   - Staff:      employment_type=STAFF (exclusive of above)

3. Channel adapters injectable per environment:
   - send_email_fn(recipients, subject, content, attachments)
   - send_slack_fn(channel, message, recipients)
   - send_app_notification_fn(recipients, title, body, link)

HONESTY DISCIPLINE
------------------
- delivery_status defaults to "prepared" when no adapters injected;
  engine does NOT pretend messages were sent
- "sent" status emitted only when adapter callable returned True
- "failed" status with adapter exception detail when adapter raises
- Recipients counted only from real users.json data, not fabricated
- Feedback file must exist; engine returns no_feedback when absent
  rather than fabricating responses

RELATED STANDARDS
-----------------
- ENH-149 Stakeholder Engagement — provides pulse + campaign data
- ENH-150 Strategy Health Engine — provides update content
- ENH-153 Daily Strategy Integration — personal scorecards
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger("a2z.strategy_communication")


# ════════════════════════════════════════════════════════════════════
# Audience tier constants
# ════════════════════════════════════════════════════════════════════

TIER_EXECUTIVE = "executive"
TIER_MANAGER = "manager"
TIER_STAFF = "staff"

EXECUTIVE_KEYWORDS = ("CEO", "CFO", "CRO", "CTO", "MD", "Director",
                      "Chief", "Head of")
MANAGER_KEYWORDS = ("Manager", "Lead", "Supervisor")

# Default channels per tier
DEFAULT_CHANNELS = {
    TIER_EXECUTIVE: ("email",),
    TIER_MANAGER:   ("slack", "email"),
    TIER_STAFF:     ("app_notification",),
}

# Delivery status enum
DELIVERY_PREPARED = "prepared"
DELIVERY_SENT = "sent"
DELIVERY_FAILED = "failed"


# ════════════════════════════════════════════════════════════════════
# StrategyCommunicationEngine
# ════════════════════════════════════════════════════════════════════

class StrategyCommunicationEngine:
    """Automated multi-channel strategy communication.

    Caller pattern:

        from utils.strategy_communication import StrategyCommunicationEngine

        engine = StrategyCommunicationEngine(
            send_email_fn=my_smtp_adapter,
            send_slack_fn=my_slack_adapter)

        result = engine.distribute_strategy_update({
            "id": "UPD-2025-Q4-001",
            "title": "Q4 Strategy Progress",
            "executive_summary": "...",
            "manager_summary": "...",
            "staff_summary": "...",
            "detailed_report_path": "reports/Q4_2025.pdf",
            "dashboard_link": "https://a2z/dashboard",
        })
    """

    def __init__(self,
                 data_dir: Optional[Path] = None,
                 send_email_fn: Optional[Callable] = None,
                 send_slack_fn: Optional[Callable] = None,
                 send_app_notification_fn: Optional[Callable] = None,
                 ai_sentiment_fn: Optional[Callable] = None):
        if data_dir is None:
            here = Path(__file__).resolve().parent
            data_dir = here.parent / "data"
        self.data_dir = data_dir
        self.send_email_fn = send_email_fn
        self.send_slack_fn = send_slack_fn
        self.send_app_notification_fn = send_app_notification_fn
        self.ai_sentiment_fn = ai_sentiment_fn
        self._users_cache: Optional[List[Dict]] = None

    # ── Data loaders ──

    def _load_users(self) -> List[Dict[str, Any]]:
        if self._users_cache is not None:
            return self._users_cache
        path = self.data_dir / "users.json"
        if not path.exists():
            self._users_cache = []
            return self._users_cache
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            # users.json may be: list of dicts, dict {username: dict}, or
            # dict with "users" key
            if isinstance(data, list):
                self._users_cache = data
            elif isinstance(data, dict):
                if "users" in data and isinstance(data["users"], list):
                    self._users_cache = data["users"]
                else:
                    # Dict keyed by username — flatten to list
                    self._users_cache = [
                        {**v, "username": k}
                        for k, v in data.items()
                        if isinstance(v, dict)
                    ]
            else:
                self._users_cache = []
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"users.json unreadable: {e}")
            self._users_cache = []
        return self._users_cache

    # ── Audience segmentation ──

    def _classify_user_tier(self, user: Dict) -> str:
        """Classify user into executive / manager / staff tier.

        Uses band (E1=Executive Director, E2-E3=Senior, M=Management,
        A1-A4=Associate/Staff) when available, else role keywords,
        else employment_type.
        """
        role = (user.get("role") or user.get("title") or "")
        band = (user.get("band") or "").upper()
        emp_type = (user.get("employment_type") or "").upper()

        # Band-based segmentation (primary in Eco Bank schema)
        if band.startswith("E"):
            return TIER_EXECUTIVE
        if band.startswith("M"):
            return TIER_MANAGER

        # Executive check (most specific)
        for kw in EXECUTIVE_KEYWORDS:
            if kw.lower() in role.lower():
                return TIER_EXECUTIVE

        # Management
        if emp_type == "MANAGEMENT":
            return TIER_MANAGER
        for kw in MANAGER_KEYWORDS:
            if kw.lower() in role.lower():
                return TIER_MANAGER

        # Staff (default for A-band or unclassified)
        return TIER_STAFF

    def segment_audience(self) -> Dict[str, List[Dict[str, Any]]]:
        """Segment users.json into 3 tiers.

        Returns:
            {
              "executive": [...],
              "manager":   [...],
              "staff":     [...],
            }
        """
        users = self._load_users()
        segments = {TIER_EXECUTIVE: [], TIER_MANAGER: [], TIER_STAFF: []}
        for u in users:
            tier = self._classify_user_tier(u)
            segments[tier].append({
                "staff_code":  u.get("staff_code") or u.get("id")
                                or u.get("username"),
                "name":        u.get("full_name") or u.get("name"),
                "role":        u.get("role") or u.get("title"),
                "department":  u.get("department"),
                "email":       u.get("email"),
                "band":        u.get("band"),
            })
        return segments

    # ── Message preparation ──

    def prepare_executive_message(
            self, update: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "tier":        TIER_EXECUTIVE,
            "channel":     "email",
            "subject":     f"Strategy Update: {update.get('title', '')}",
            "content":     update.get("executive_summary",
                                       "No executive summary provided."),
            "attachments": [update.get("detailed_report_path")]
            if update.get("detailed_report_path") else [],
        }

    def prepare_manager_message(
            self, update: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "tier":      TIER_MANAGER,
            "channel":   "slack",
            "channel_name": "#strategy-updates",
            "message":   (
                f"📢 {update.get('title', '')}\n"
                f"{update.get('manager_summary', 'No manager summary.')}"
                + (f"\n[Read more]({update['dashboard_link']})"
                   if update.get("dashboard_link") else "")),
        }

    def prepare_staff_message(
            self, update: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "tier":  TIER_STAFF,
            "channel": "app_notification",
            "title": "Strategy Progress Update",
            "body":  update.get("staff_summary", "Strategy update available."),
            "link":  update.get("dashboard_link", ""),
        }

    # ── Delivery dispatchers ──

    def _dispatch_executive(
            self,
            recipients: List[Dict],
            message: Dict) -> Dict[str, Any]:
        if self.send_email_fn is None:
            return {
                "delivery_status":   DELIVERY_PREPARED,
                "n_recipients":      len(recipients),
                "channel":           "email",
                "fallback_reason":   ("No send_email_fn adapter injected; "
                                       "message prepared but not dispatched."),
            }
        try:
            ok = self.send_email_fn(
                recipients=recipients,
                subject=message["subject"],
                content=message["content"],
                attachments=message.get("attachments", []))
            return {
                "delivery_status": DELIVERY_SENT if ok else DELIVERY_FAILED,
                "n_recipients":    len(recipients),
                "channel":         "email",
            }
        except Exception as e:
            logger.warning(f"send_email_fn raised: {e}")
            return {
                "delivery_status":  DELIVERY_FAILED,
                "n_recipients":     len(recipients),
                "channel":          "email",
                "error":            f"{type(e).__name__}: {e}",
            }

    def _dispatch_manager(
            self,
            recipients: List[Dict],
            message: Dict) -> Dict[str, Any]:
        if self.send_slack_fn is None:
            return {
                "delivery_status":   DELIVERY_PREPARED,
                "n_recipients":      len(recipients),
                "channel":           "slack",
                "fallback_reason":   ("No send_slack_fn adapter injected; "
                                       "message prepared but not dispatched."),
            }
        try:
            ok = self.send_slack_fn(
                channel=message.get("channel_name", "#strategy-updates"),
                message=message["message"],
                recipients=recipients)
            return {
                "delivery_status": DELIVERY_SENT if ok else DELIVERY_FAILED,
                "n_recipients":    len(recipients),
                "channel":         "slack",
            }
        except Exception as e:
            logger.warning(f"send_slack_fn raised: {e}")
            return {
                "delivery_status":  DELIVERY_FAILED,
                "n_recipients":     len(recipients),
                "channel":          "slack",
                "error":            f"{type(e).__name__}: {e}",
            }

    def _dispatch_staff(
            self,
            recipients: List[Dict],
            message: Dict) -> Dict[str, Any]:
        if self.send_app_notification_fn is None:
            return {
                "delivery_status":   DELIVERY_PREPARED,
                "n_recipients":      len(recipients),
                "channel":           "app_notification",
                "fallback_reason":   ("No send_app_notification_fn "
                                       "adapter injected; message "
                                       "prepared but not dispatched."),
            }
        try:
            ok = self.send_app_notification_fn(
                recipients=recipients,
                title=message["title"],
                body=message["body"],
                link=message.get("link", ""))
            return {
                "delivery_status": DELIVERY_SENT if ok else DELIVERY_FAILED,
                "n_recipients":    len(recipients),
                "channel":         "app_notification",
            }
        except Exception as e:
            logger.warning(f"send_app_notification_fn raised: {e}")
            return {
                "delivery_status":  DELIVERY_FAILED,
                "n_recipients":     len(recipients),
                "channel":          "app_notification",
                "error":            f"{type(e).__name__}: {e}",
            }

    # ── Feedback collection ──

    def collect_feedback(
            self,
            update_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load feedback from data/strategy_feedback.json.

        Schema:
            [
                {
                    "update_id":      str,
                    "respondent":     str,
                    "department":     str,
                    "comment":        str,
                    "rating":         int (1-5, optional),
                    "submitted_at":   ISO-8601,
                },
                ...
            ]

        Filters by update_id when provided; otherwise returns all.
        Returns empty list when file absent (no fabrication).
        """
        path = self.data_dir / "strategy_feedback.json"
        if not path.exists():
            return []
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            if update_id:
                return [r for r in data
                        if r.get("update_id") == update_id]
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"strategy_feedback.json unreadable: {e}")
            return []

    # ── Sentiment analysis ──

    def analyze_sentiment(
            self,
            feedback: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze sentiment of feedback comments.

        Rule-based by default; LLM hook optional.
        """
        if not feedback:
            return {
                "sentiment":      None,
                "n_comments":     0,
                "basis":          "rule_based",
                "fallback_reason": "No feedback to analyze.",
            }

        comments = [r.get("comment", "") for r in feedback
                    if r.get("comment")]
        if self.ai_sentiment_fn is not None:
            try:
                ai_result = self.ai_sentiment_fn(comments)
                return {
                    "sentiment":      ai_result.get("sentiment"),
                    "themes":         ai_result.get("themes", []),
                    "n_comments":     len(comments),
                    "basis":          "llm",
                    "fallback_reason": None,
                }
            except Exception as e:
                logger.warning(
                    f"ai_sentiment_fn raised: {e}; falling back")

        # Rule-based
        positive_kw = {"good", "great", "excellent", "love", "support",
                       "appreciate", "value", "engaged", "positive",
                       "supported", "empowered", "useful", "helpful"}
        negative_kw = {"bad", "poor", "frustrated", "ignored",
                       "disconnected", "lost", "confused", "unclear",
                       "unsupported", "stressful", "useless", "vague"}
        pos = neg = 0
        for c in comments:
            words = c.lower().split()
            pos += sum(1 for w in words if w in positive_kw)
            neg += sum(1 for w in words if w in negative_kw)

        if pos + neg == 0:
            sentiment = "neutral"
        elif pos > neg:
            sentiment = "positive"
        elif neg > pos:
            sentiment = "negative"
        else:
            sentiment = "mixed"

        # Average rating if available
        ratings = [r.get("rating") for r in feedback
                   if isinstance(r.get("rating"), (int, float))]
        avg_rating = round(sum(ratings) / len(ratings), 2) if ratings else None

        return {
            "sentiment":      sentiment,
            "n_comments":     len(comments),
            "positive_hits":  pos,
            "negative_hits":  neg,
            "avg_rating":     avg_rating,
            "basis":          "rule_based",
            "fallback_reason": None,
        }

    # ── Main API ──

    def distribute_strategy_update(
            self,
            update: Dict[str, Any]) -> Dict[str, Any]:
        """Full distribution pipeline.

        Args:
            update: dict with id, title, executive_summary,
                manager_summary, staff_summary, detailed_report_path,
                dashboard_link

        Returns:
            {
              "update_id":           str,
              "audience_segments":   {tier -> n},
              "deliveries":          {tier -> {delivery_status, ...}},
              "n_total_recipients":  int,
              "n_delivered":         int (sum across "sent" status),
              "n_prepared":          int (sum across "prepared" status),
              "n_failed":            int,
              "feedback":            {n_comments, sentiment, ...},
              "generated_at":        ISO-8601,
              "basis":               "rule_based" | "rule_based+llm",
            }
        """
        segments = self.segment_audience()

        # Prepare messages
        exec_msg = self.prepare_executive_message(update)
        mgr_msg = self.prepare_manager_message(update)
        staff_msg = self.prepare_staff_message(update)

        # Dispatch
        exec_delivery = self._dispatch_executive(
            segments[TIER_EXECUTIVE], exec_msg)
        mgr_delivery = self._dispatch_manager(
            segments[TIER_MANAGER], mgr_msg)
        staff_delivery = self._dispatch_staff(
            segments[TIER_STAFF], staff_msg)

        deliveries = {
            TIER_EXECUTIVE: exec_delivery,
            TIER_MANAGER:   mgr_delivery,
            TIER_STAFF:     staff_delivery,
        }

        n_total = sum(len(s) for s in segments.values())
        n_delivered = sum(
            d["n_recipients"] for d in deliveries.values()
            if d["delivery_status"] == DELIVERY_SENT)
        n_prepared = sum(
            d["n_recipients"] for d in deliveries.values()
            if d["delivery_status"] == DELIVERY_PREPARED)
        n_failed = sum(
            d["n_recipients"] for d in deliveries.values()
            if d["delivery_status"] == DELIVERY_FAILED)

        # Feedback
        feedback = self.collect_feedback(update.get("id"))
        sentiment_result = self.analyze_sentiment(feedback)

        bases = ["rule_based"]
        if sentiment_result.get("basis") == "llm":
            bases.append("llm")
        basis_label = "+".join(bases)

        return {
            "update_id":           update.get("id"),
            "update_title":        update.get("title"),
            "audience_segments":   {
                t: len(s) for t, s in segments.items()},
            "deliveries":          deliveries,
            "messages":            {
                TIER_EXECUTIVE: exec_msg,
                TIER_MANAGER:   mgr_msg,
                TIER_STAFF:     staff_msg,
            },
            "n_total_recipients":  n_total,
            "n_delivered":         n_delivered,
            "n_prepared":          n_prepared,
            "n_failed":            n_failed,
            "feedback":            sentiment_result,
            "feedback_n_total":    len(feedback),
            "generated_at":        datetime.now(
                timezone.utc).isoformat(),
            "basis":               basis_label,
        }


# ════════════════════════════════════════════════════════════════════
# Module-level convenience wrapper
# ════════════════════════════════════════════════════════════════════

def distribute_strategy_update(update: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience wrapper — instantiate engine and run."""
    return StrategyCommunicationEngine().distribute_strategy_update(update)
