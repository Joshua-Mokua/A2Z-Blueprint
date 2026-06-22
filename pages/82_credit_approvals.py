"""pages/82_credit_approvals.py — Credit Approvals / Swim Lane.

v10.448 — Phase 3 of Joshua's Credit Module Revival doctrine.

Per the v10.446 diagnostic, the Approvals/Swim Lane flow stage had NO
DEDICATED PAGE — committee logic squatted inside 22_credit_analysis.py.
This page fills that gap as the formal home for:

  • Swim Lane visualization (apps in each of 19 lifecycle states)
  • Committee queue (apps awaiting decision, sorted by tier)
  • Vote capture (record CommitteeVote → evaluate_committee_decision)
  • Decision history (audit trail of past committee decisions)
  • Committee configuration (tier thresholds, required roles, quorum)

Wires utils/credit_workflow.py (ENH-125 + ENH-130 + ENH-CRD-R7).

Persistence: votes + decisions appended to data/committee_decisions.json
for audit + history. BSC trigger fires after every decision captured.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available


from pages._access import require_access
from pages._shared import load_shared_state
from utils.core_audit import audit_log
from utils.credit_workflow import (
    ALLOWED_TRANSITIONS,
    ApplicationState,
    AutomationDecision,
    AutomationPolicy,
    BRANCH_AUTO_DISBURSE_LIMIT_KES,
    BRANCH_FORWARD_LIMIT_KES,
    COMMITTEE_REQUIREMENTS,
    CommitteeRole,
    CommitteeVote,
    determine_branch_tier,
    determine_tier,
    evaluate_automation,
    evaluate_committee_decision,
    forwards_to_ho,
    is_branch_tier,
    is_terminal_state,
)

require_access("credit.approvals")


def _bsc_trigger(username: str, kpi: str = ""):
    """Non-blocking BSC update — called after every save action."""
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass


# ── Setup ─────────────────────────────────────────────────────────────
DATA = Path(__file__).parent.parent / "data"
DECISIONS_FILE = DATA / "committee_decisions.json"
APPS_FILE = DATA / "loan_applications.json"

um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role", "")
name = ud.get("full_name", "")
sc = str(ud.get("staff_code", ""))
is_admin = ud.get("is_admin", False)
is_credit_chief = "Chief Credit" in role
is_credit_committee_member = any(
    x in role for x in (
        "Chief Credit", "Chief Risk", "Chief Compliance", "Chief Executive",
        "Chief Financial", "Head of Credit", "Head of Risk", "Head Of Risk",
        "Director Consumer & Commercial Banking (CCB)", "Director Commercial",
    )
)

# Data status -> ApplicationState
STATUS_TO_LIFECYCLE = {
    "draft":        ApplicationState.DRAFT,
    "submitted":    ApplicationState.SUBMITTED,
    "completeness": ApplicationState.EKYC_PENDING,
    "assigned":     ApplicationState.BUREAU_PULL_PENDING,
    "analysis":     ApplicationState.DECISION_PENDING,
    "committee":    ApplicationState.COMMITTEE_PENDING,
    "approved":     ApplicationState.APPROVED,
    "credit_admin": ApplicationState.DOCUMENTATION_PENDING,
    "disbursed":    ApplicationState.DISBURSED,
    "declined":     ApplicationState.DECLINED,
    "returned":     ApplicationState.WITHDRAWN_BY_APPLICANT,
}

# Role string -> CommitteeRole
def _user_committee_role(user_role: str) -> CommitteeRole | None:
    r = user_role.lower()
    # ── Branch Credit Committee (v10.449) ────────────────────────────
    if "branch manager" in r:
        return CommitteeRole.BRANCH_MANAGER
    if "branch credit manager" in r or "credit manager" in r:
        return CommitteeRole.BRANCH_CREDIT_MANAGER
    if "branch operations manager" in r or "operations manager" in r:
        return CommitteeRole.BRANCH_OPERATIONS_MANAGER
    # ── Head Office Committee ────────────────────────────────────────
    if "chief credit" in r or "head of credit" in r:
        return CommitteeRole.HEAD_OF_CREDIT
    if "chief risk" in r or "head of risk" in r:
        return CommitteeRole.HEAD_OF_RISK
    if "chief compliance" in r or "head of compliance" in r:
        return CommitteeRole.HEAD_OF_COMPLIANCE
    if "chief financial" in r or "cfo" in r:
        return CommitteeRole.CFO
    if "chief executive" in r or "managing director" in r or "ceo" in r:
        return CommitteeRole.CEO
    if any(x in r for x in ("director retail", "director commercial",
                            "head of retail", "head of corporate",
                            "head of sme")):
        return CommitteeRole.HEAD_OF_BUSINESS
    if "board credit" in r:
        return CommitteeRole.BOARD_CREDIT_MEMBER
    return None


def _is_branch_role(committee_role: CommitteeRole | None) -> bool:
    return committee_role in (
        CommitteeRole.BRANCH_MANAGER,
        CommitteeRole.BRANCH_CREDIT_MANAGER,
        CommitteeRole.BRANCH_OPERATIONS_MANAGER,
    )


# Application origin detection: branch app vs HO app
# Heuristic: small amounts originated at a branch will appear with a
# branch field; for v10.449 we treat amount <= BRANCH_FORWARD_LIMIT_KES
# as branch-eligible.
def _is_branch_eligible(app: dict) -> bool:
    """An app is branch-eligible if (a) it has a branch field and
    (b) the amount is within branch authority (≤ BRANCH_FORWARD_LIMIT)."""
    try:
        amount = Decimal(str(app.get("amount", 0)))
    except Exception:
        return False
    return (
        amount > Decimal("0")
        and amount <= BRANCH_FORWARD_LIMIT_KES
        and bool(app.get("branch") or app.get("branch_code"))
    )


def _load_apps():
    if not APPS_FILE.exists():
        return []
    try:
        return json.loads(APPS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _load_decisions():
    if not DECISIONS_FILE.exists():
        return []
    try:
        return json.loads(DECISIONS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_decisions(decisions):
    DECISIONS_FILE.write_text(json.dumps(decisions, indent=2, default=str))


# ── Header ────────────────────────────────────────────────────────────
st.title("🏛️ Credit Approvals — Swim Lane & Committee")
st.caption(
    "Phase 3 of Credit Module Revival. Formal workflow for committee "
    "decisions. ENH-125 Digital Workflow + ENH-130 Committee Automation."
)

apps = _load_apps()
decisions = _load_decisions()

# Top-level metrics
in_committee = [a for a in apps if a.get("status") == "committee"]
in_analysis  = [a for a in apps if a.get("status") == "analysis"]
approved = [a for a in apps if a.get("status") in ("approved", "credit_admin", "disbursed")]

c1, c2, c3, c4 = st.columns(4)
c1.metric("📥 Awaiting committee", len(in_committee))
c2.metric("⚖️ In analysis (may refer)", len(in_analysis))
c3.metric("✅ Approved (total)", len(approved))
c4.metric("📜 Decisions logged", len(decisions))

# Tier distribution of committee queue
tier_counts = Counter()
for a in in_committee:
    try:
        tier_counts[determine_tier(Decimal(str(a.get("amount", 0))))] += 1
    except Exception:
        continue

if tier_counts:
    st.markdown("**Committee queue by tier:**")
    tc1, tc2, tc3, tc4 = st.columns(4)
    tc1.metric("TIER_1 (auto)", tier_counts.get("TIER_1", 0),
               help="Should not be at committee per policy")
    tc2.metric("TIER_2 (500K-5M)", tier_counts.get("TIER_2", 0))
    tc3.metric("TIER_3 (5M-50M)", tier_counts.get("TIER_3", 0))
    tc4.metric("TIER_4 (>50M, board)", tier_counts.get("TIER_4", 0))

st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────────────
tabs = st.tabs([
    "🏊 Swim Lane",
    "🤖 Credit Analyst",          # v10.449: scoring matrix approvals
    "🏢 Branch Credit Committee",
    "🏛️ Credit Committee (CCC)",  # v10.449: TIER_2 + TIER_3 (head office central)
    "⚖️ Board Credit Committee",   # v10.449: TIER_4 (board-level, BCC)
    "🗳️ Cast Vote",
    "📜 Decision History",
    "⚙️ Committee Configuration",
])


# ════════════════════════════════════════════════════════════════════
# TAB 1 — SWIM LANE VISUALIZATION
# ════════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader("Application lifecycle swim lane")
    st.caption(
        "Where every application sits in the 19-state machine. Each row "
        "is a state; the count shows how many applications are there right now."
    )

    lifecycle_counts = Counter()
    for a in apps:
        s = STATUS_TO_LIFECYCLE.get(a.get("status", ""))
        if s is not None:
            lifecycle_counts[s] += 1

    # Group states into swim lanes per flow stage
    SWIM_LANES = {
        "🟦 INTAKE": [ApplicationState.DRAFT, ApplicationState.SUBMITTED,
                     ApplicationState.EKYC_PENDING, ApplicationState.EKYC_FAILED],
        "🟧 ANALYSIS": [ApplicationState.BUREAU_PULL_PENDING,
                       ApplicationState.DECISION_PENDING],
        "🟪 COMMITTEE": [ApplicationState.REFERRED_TO_COMMITTEE,
                        ApplicationState.COMMITTEE_PENDING,
                        ApplicationState.COMMITTEE_APPROVED,
                        ApplicationState.COMMITTEE_DECLINED],
        "🟨 DECISION": [ApplicationState.APPROVED,
                       ApplicationState.CONDITIONALLY_APPROVED,
                       ApplicationState.DECLINED],
        "🟩 ADMIN": [ApplicationState.DOCUMENTATION_PENDING,
                    ApplicationState.DISBURSEMENT_PENDING,
                    ApplicationState.DISBURSED],
        "⚫ TERMINAL": [ApplicationState.WITHDRAWN_BY_APPLICANT,
                       ApplicationState.EXPIRED],
    }

    for lane_name, states in SWIM_LANES.items():
        lane_total = sum(lifecycle_counts.get(s, 0) for s in states)
        with st.expander(f"{lane_name} — {lane_total} application(s)",
                        expanded=(lane_total > 0)):
            rows = []
            for s in states:
                n = lifecycle_counts.get(s, 0)
                allowed = ALLOWED_TRANSITIONS.get(s, ())
                rows.append({
                    "State":      s.value,
                    "Apps here":  n,
                    "Terminal":   "✅" if is_terminal_state(s) else "—",
                    "Can go to":  ", ".join(t.value for t in allowed) or "(terminal)",
                })
            st.dataframe(pd.DataFrame(rows),
                        use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════
# TAB 2 — CREDIT ANALYST (Scoring Matrix Approval, v10.449)
# ════════════════════════════════════════════════════════════════════
# Per Joshua doctrine: "within the process there are limits approved
# by a scoring matrix". Credit Analyst approves within scoring-matrix
# bands. Above the matrix limits, escalates to Branch Credit Committee.
with tabs[1]:
    st.subheader("🤖 Credit Analyst — scoring matrix approvals")
    st.caption(
        "First level of credit approval. Credit Analysts review and "
        "approve loans within scoring-matrix limits. Above these "
        "thresholds, escalates to Branch Credit Committee."
    )

    analyst_eligible = []
    analyst_escalated = []
    for a in apps:
        if a.get("status") not in ("analysis", "submitted", "assigned"):
            continue
        try:
            amount = Decimal(str(a.get("amount", 0)))
        except Exception:
            continue
        if amount <= Decimal("500000"):
            analyst_eligible.append(a)
        elif amount <= BRANCH_FORWARD_LIMIT_KES:
            analyst_escalated.append(a)

    ac1, ac2 = st.columns(2)
    ac1.metric("📋 Within scoring matrix (≤ KES 500K)", len(analyst_eligible),
               help="Credit Analyst can approve directly per matrix bands")
    ac2.metric("⬆️ Above analyst limit (escalating)", len(analyst_escalated),
               help="Above KES 500K — escalates to Branch Credit Committee")

    st.markdown("---")
    st.markdown("##### Scoring Matrix Bands (Auto-Approval Limits)")
    st.caption(
        "Score from `utils/credit_risk_scoring.py` + `utils/credit_alt_scoring.py`. "
        "Within auto-limit, Credit Analyst approves with single signature."
    )
    matrix_rows = [
        {"Score band": "AAA (≥ 850)",   "PD ceiling": "≤ 1.0%",  "Auto-limit (KES)": "500,000", "Notes": "Top-tier; fast-track"},
        {"Score band": "AA  (750-849)", "PD ceiling": "≤ 2.0%",  "Auto-limit (KES)": "350,000", "Notes": "Strong credit"},
        {"Score band": "A   (650-749)", "PD ceiling": "≤ 4.0%",  "Auto-limit (KES)": "250,000", "Notes": "Acceptable; light analyst review"},
        {"Score band": "BBB (550-649)", "PD ceiling": "≤ 7.0%",  "Auto-limit (KES)": "150,000", "Notes": "Manual analyst sign-off + collateral"},
        {"Score band": "BB  (450-549)", "PD ceiling": "≤ 12.0%", "Auto-limit (KES)": "75,000",  "Notes": "Higher scrutiny; mitigants required"},
        {"Score band": "B   (350-449)", "PD ceiling": "≤ 20.0%", "Auto-limit (KES)": "30,000",  "Notes": "Escalation likely; analyst + supervisor"},
        {"Score band": "CCC (≤ 349)",   "PD ceiling": "> 20.0%", "Auto-limit (KES)": "0",       "Notes": "Decline default; manual override only"},
    ]
    st.dataframe(pd.DataFrame(matrix_rows),
                use_container_width=True, hide_index=True)
    st.caption(
        "**Source**: credit_risk_scoring + credit_alt_scoring engines. "
        "Above KES 500K the application moves to Branch Credit Committee tab."
    )

    if analyst_eligible:
        st.markdown("---")
        st.markdown(f"##### {len(analyst_eligible)} application(s) eligible for Credit Analyst decision")
        analyst_rows = [
            {
                "ID":         a.get("id", ""),
                "Client":     str(a.get("client_name", ""))[:30],
                "Product":    str(a.get("product", ""))[:25],
                "Amount":     f"KES {float(a.get('amount', 0)):,.0f}",
                "Score band": a.get("score_band", "(not scored)"),
                "Status":     a.get("status", ""),
                "RM":         str(a.get("rm_name", ""))[:20],
            }
            for a in sorted(analyst_eligible, key=lambda x: -float(x.get("amount", 0)))[:50]
        ]
        st.dataframe(pd.DataFrame(analyst_rows),
                    use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════
# TAB 3 — BRANCH CREDIT COMMITTEE (v10.449)
# ════════════════════════════════════════════════════════════════════
# Per Joshua doctrine: 'we missed out branch credit committee who as
# well sit and review loan applications of a certain limit. There are
# those they can approve at branch level and disburse but their approval
# process has to be documented, and there are those they can approve
# and still forward for further approval.'
with tabs[2]:
    st.subheader("🏢 Branch Credit Committee (BCC)")
    st.caption(
        "BCC members: Branch Manager + Branch Credit Manager + Branch "
        "Operations Manager. Authority limit defines whether BCC can "
        "approve-and-disburse autonomously OR must approve-and-forward "
        "to Head Office committee."
    )

    # Branch tier limits banner
    bcb1, bcb2 = st.columns(2)
    bcb1.metric(
        "🟢 BCC autonomy limit",
        f"≤ KES {float(BRANCH_AUTO_DISBURSE_LIMIT_KES)/1e6:.1f}M",
        help="At or below this amount the BCC can approve and disburse "
             "without head office involvement.",
    )
    bcb2.metric(
        "🟡 BCC + Forward limit",
        f"≤ KES {float(BRANCH_FORWARD_LIMIT_KES)/1e6:.1f}M",
        help="Up to this amount the BCC reviews and recommends, then "
             "forwards to HO TIER_2 committee for final approval.",
    )

    # Branch-eligible apps: at branch + amount in branch range
    branch_eligible_apps = [
        a for a in apps
        if _is_branch_eligible(a)
        and a.get("status") in ("submitted", "completeness", "assigned",
                                "analysis", "committee")
    ]
    if not branch_eligible_apps:
        st.info(
            "✅ No branch-eligible applications currently. Apps appear "
            "here when they have a branch assignment AND amount ≤ "
            f"KES {float(BRANCH_FORWARD_LIMIT_KES)/1e6:.0f}M."
        )
    else:
        # Group by branch authority outcome
        bcc_auto = []      # Branch can approve+disburse
        bcc_forward = []   # Branch approves+forwards
        for a in branch_eligible_apps:
            try:
                amt = Decimal(str(a.get("amount", 0)))
                btier = determine_branch_tier(amt)
            except Exception:
                continue
            if btier == "TIER_BRANCH_AUTO":
                bcc_auto.append(a)
            elif btier == "TIER_BRANCH_FWD":
                bcc_forward.append(a)

        m1, m2, m3 = st.columns(3)
        m1.metric("📥 Total branch-eligible", len(branch_eligible_apps))
        m2.metric("🟢 BCC autonomous (disburse)", len(bcc_auto))
        m3.metric("🟡 BCC + Forward to HO", len(bcc_forward))

        # Tab 2A — Autonomous tier (approve + disburse)
        st.markdown("---")
        st.markdown("##### 🟢 Autonomous tier — BCC approves AND disburses")
        st.caption(
            "Below KES 2M. BCC requires unanimous (100%) approval from "
            "Branch Manager + Branch Credit Manager. Documented per BCC "
            "policy. Branch handles disbursement directly."
        )
        if bcc_auto:
            auto_rows = []
            for a in bcc_auto:
                amt = Decimal(str(a.get("amount", 0)))
                auto_rows.append({
                    "ID":          a.get("id", ""),
                    "Client":      str(a.get("client_name", ""))[:30],
                    "Branch":      str(a.get("branch", a.get("branch_code", "")))[:20],
                    "Product":     str(a.get("product", ""))[:25],
                    "Amount (M)":  float(amt) / 1e6,
                    "Status":      a.get("status", ""),
                    "RM":          str(a.get("rm_name", ""))[:20],
                })
            st.dataframe(pd.DataFrame(auto_rows),
                        use_container_width=True, hide_index=True)
        else:
            st.info("No autonomous-tier applications pending.")

        # Tab 2B — Forward tier (approve + forward to HO)
        st.markdown("---")
        st.markdown("##### 🟡 Forward tier — BCC recommends, HO decides")
        st.caption(
            "KES 2M to 5M. BCC requires 3-member quorum (BM + BCM + BOM), "
            "≥ 67% approval. After BCC approves, the application moves "
            "to HO TIER_2 committee for final approval."
        )
        if bcc_forward:
            fwd_rows = []
            for a in bcc_forward:
                amt = Decimal(str(a.get("amount", 0)))
                fwd_rows.append({
                    "ID":          a.get("id", ""),
                    "Client":      str(a.get("client_name", ""))[:30],
                    "Branch":      str(a.get("branch", a.get("branch_code", "")))[:20],
                    "Product":     str(a.get("product", ""))[:25],
                    "Amount (M)":  float(amt) / 1e6,
                    "Status":      a.get("status", ""),
                    "Next step":   "BCC approve → HO TIER_2",
                })
            st.dataframe(pd.DataFrame(fwd_rows),
                        use_container_width=True, hide_index=True)
        else:
            st.info("No forward-tier applications pending.")

    # BCC decisions logged so far
    branch_decisions = [
        d for d in decisions
        if d.get("tier") in ("TIER_BRANCH_AUTO", "TIER_BRANCH_FWD")
    ]
    if branch_decisions:
        st.markdown("---")
        st.markdown(f"##### BCC decisions logged ({len(branch_decisions)})")
        bcc_dist = Counter(d.get("outcome") for d in branch_decisions)
        bd1, bd2, bd3, bd4 = st.columns(4)
        bd1.metric("Approved (disbursed)",
                   bcc_dist.get("APPROVED_AT_BRANCH", 0))
        bd2.metric("Approved (fwd to HO)",
                   bcc_dist.get("APPROVED_BRANCH_FORWARD_HO", 0))
        bd3.metric("Declined", bcc_dist.get("DECLINED", 0))
        bd4.metric("Pending quorum/tie",
                   sum(bcc_dist.get(o, 0) for o in ("NO_QUORUM", "TIE")))


# ════════════════════════════════════════════════════════════════════
# TAB 4 — CREDIT COMMITTEE (CCC, Head Office Central, v10.449)
# ════════════════════════════════════════════════════════════════════
# TIER_2 + TIER_3: Central Credit Committee at head office
with tabs[3]:
    st.subheader("🏛️ Credit Committee (CCC) — Head Office Central")
    st.caption(
        "Central Credit Committee reviews TIER_2 (KES 500K-5M) + TIER_3 "
        "(KES 5M-50M). Members: Head of Credit, Head of Risk, Head of "
        "Business, Head of Compliance. Approves amounts above branch "
        "authority but below board threshold."
    )

    ccc_queue = []
    for a in in_committee:
        try:
            amount = Decimal(str(a.get("amount", 0)))
            # CCC handles TIER_2 + TIER_3 (NOT branch-originated below 5M
            # which goes to Branch Committee tab)
            originated_branch = a.get("originated_at_branch", False)
            tier = determine_tier(amount, originated_at_branch=originated_branch)
            if tier in ("TIER_2", "TIER_3"):
                ccc_queue.append((a, amount, tier))
        except Exception:
            continue

    if not ccc_queue:
        st.success("✅ No applications currently awaiting Credit Committee.")
    else:
        ccc_rows = []
        for a, amount, tier in ccc_queue:
            req = COMMITTEE_REQUIREMENTS.get(tier, {})
            ccc_rows.append({
                "ID":        a.get("id", ""),
                "Client":    str(a.get("client_name", ""))[:30],
                "Product":   str(a.get("product", ""))[:25],
                "Amount (M)": float(amount) / 1e6,
                "Tier":      tier,
                "Quorum":    req.get("quorum", "—"),
                "Threshold": f"{req.get('approve_threshold_pct')}%",
                "Lane":      a.get("swim_lane", ""),
                "Submitted": str(a.get("application_date", ""))[:10],
                "RM":        str(a.get("rm_name", ""))[:20],
            })
        tier_order = {"TIER_3": 0, "TIER_2": 1}
        ccc_rows.sort(key=lambda r: (tier_order.get(r["Tier"], 9),
                                     -r["Amount (M)"]))
        cc1, cc2 = st.columns(2)
        cc1.metric("TIER_3 (KES 5M–50M)",
                   sum(1 for r in ccc_rows if r["Tier"] == "TIER_3"))
        cc2.metric("TIER_2 (KES 500K–5M)",
                   sum(1 for r in ccc_rows if r["Tier"] == "TIER_2"))
        st.dataframe(pd.DataFrame(ccc_rows),
                    use_container_width=True, hide_index=True)
        st.markdown(
            "**Next step**: members open **🗳️ Cast Vote** to record decision."
        )


# ════════════════════════════════════════════════════════════════════
# TAB 5 — BOARD CREDIT COMMITTEE (BCC, v10.449)
# ════════════════════════════════════════════════════════════════════
# TIER_4: Highest amounts (> KES 50M) require Board approval
with tabs[4]:
    st.subheader("⚖️ Board Credit Committee (BCC) — Board-level approvals")
    st.caption(
        "Board Credit Committee reviews TIER_4 (KES > 50M). Members: "
        "CEO/MD, CFO, Head of Risk, Head of Credit, Board Credit Member. "
        "Quorum 4 of 5; 80% approve threshold. This is the highest "
        "approval authority in the bank."
    )

    bcc_queue = []
    for a in in_committee:
        try:
            amount = Decimal(str(a.get("amount", 0)))
            tier = determine_tier(amount)
            if tier == "TIER_4":
                bcc_queue.append((a, amount))
        except Exception:
            continue

    bm1, bm2, bm3 = st.columns(3)
    bm1.metric("⚖️ Applications at BCC", len(bcc_queue))
    if bcc_queue:
        bm2.metric("Total exposure (KES M)",
                   f"{sum(float(amt)/1e6 for _, amt in bcc_queue):,.0f}")
        bm3.metric("Largest single (KES M)",
                   f"{max(float(amt)/1e6 for _, amt in bcc_queue):,.0f}")
    else:
        bm2.metric("Total exposure (KES M)", "—")
        bm3.metric("Largest single (KES M)", "—")

    st.markdown("---")
    if not bcc_queue:
        st.success(
            "✅ No applications currently awaiting Board Credit Committee. "
            "Apps above KES 50M land here."
        )
    else:
        bcc_rows = []
        for a, amount in bcc_queue:
            req = COMMITTEE_REQUIREMENTS["TIER_4"]
            bcc_rows.append({
                "ID":         a.get("id", ""),
                "Client":     str(a.get("client_name", ""))[:30],
                "Product":    str(a.get("product", ""))[:25],
                "Amount (M)": float(amount) / 1e6,
                "Quorum":     f"{req['quorum']}/{len(req['required_roles'])}",
                "Threshold":  f"{req['approve_threshold_pct']}%",
                "Lane":       a.get("swim_lane", ""),
                "Submitted":  str(a.get("application_date", ""))[:10],
                "RM":         str(a.get("rm_name", ""))[:20],
            })
        bcc_rows.sort(key=lambda r: -r["Amount (M)"])
        st.dataframe(pd.DataFrame(bcc_rows),
                    use_container_width=True, hide_index=True)

        st.markdown("---")
        st.warning(
            f"⚠️ **{len(bcc_queue)} application(s) require Board approval.** "
            f"BCC members (CEO/MD, CFO, Head of Risk, Head of Credit, "
            f"Board Credit Member) must convene to action these."
        )
        st.markdown(
            "**Next step**: BCC members open **🗳️ Cast Vote** tab to "
            "record their decision."
        )


# ════════════════════════════════════════════════════════════════════
# TAB 6 — CAST VOTE (gated to committee members)
# ════════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("Record a committee vote")

    user_role_enum = _user_committee_role(role)
    if not user_role_enum and not is_admin:
        st.warning(
            f"You are signed in as **{role}** which is not a recognised "
            f"committee role. Only chiefs, heads, branch managers, and "
            f"the MD can cast votes."
        )
        st.info(
            "Recognised roles: "
            "**Branch** = Branch Manager / Branch Credit Manager / "
            "Branch Operations Manager. "
            "**Head Office** = Chief Credit / Chief Risk / Chief "
            "Compliance / CFO / CEO/MD / Directors of Retail or "
            "Commercial / Head of Credit/Risk/Business / Board Credit Member"
        )
    else:
        # If admin and no role mapping, let them pick
        if is_admin and not user_role_enum:
            picked_role = st.selectbox(
                "Vote as role (admin):",
                [r.value for r in CommitteeRole],
            )
            user_role_enum = CommitteeRole(picked_role)

        is_branch_member = _is_branch_role(user_role_enum)
        st.caption(
            f"Voting as: **{user_role_enum.value}**  "
            f"{'(Branch Committee)' if is_branch_member else '(Head Office Committee)'}"
        )

        # Build the application pool the user can vote on
        if is_branch_member:
            # Branch members vote on branch-eligible apps in their branch
            user_branch = ud.get("branch") or ud.get("branch_code") or ""
            voteable_apps = [
                a for a in apps
                if _is_branch_eligible(a)
                and a.get("status") in ("submitted", "completeness",
                                       "assigned", "analysis", "committee")
                and (
                    not user_branch  # admin or unbranched user sees all
                    or str(a.get("branch", a.get("branch_code", ""))).strip()
                       == user_branch.strip()
                )
            ]
            if user_branch:
                st.caption(f"📍 Branch: **{user_branch}**")
        else:
            # HO members vote on apps in HO committee
            voteable_apps = in_committee

        if not voteable_apps:
            if is_branch_member:
                st.info("No branch-eligible applications pending in your branch.")
            else:
                st.info("No applications awaiting HO committee decision.")
            voteable_apps = []

        # Pick application
        app_options = {
            f"{a.get('id', '')} — {a.get('client_name', '')} (KES "
            f"{float(a.get('amount', 0))/1e6:.2f}M)": a.get("id", "")
            for a in voteable_apps
        }
        if not app_options:
            pass  # Already shown info message above
        else:
            picked_label = st.selectbox(
                "Application:", list(app_options.keys()), key="ca_app_pick"
            )
            picked_id = app_options[picked_label]
            picked_app = next((a for a in voteable_apps if a.get("id") == picked_id), None)

            if picked_app:
                amount = Decimal(str(picked_app.get("amount", 0)))
                # Determine tier with branch context if user is a branch member
                tier = determine_tier(
                    amount,
                    originated_at_branch=is_branch_member,
                )
                req = COMMITTEE_REQUIREMENTS.get(tier, {})
                fwds = forwards_to_ho(tier)
                st.markdown(
                    f"**Tier:** {tier} | **Quorum:** {req.get('quorum', '—')} | "
                    f"**Threshold to approve:** {req.get('approve_threshold_pct', '—')}%"
                    + (f"  \n🟡 **After branch approval, app forwards to HO TIER_2**" if fwds else "")
                    + (f"  \n🟢 **Branch can approve AND disburse directly**" if is_branch_tier(tier) and not fwds else "")
                )
                if user_role_enum not in req.get("required_roles", []):
                    st.warning(
                        f"⚠️ {user_role_enum.value} is not listed as a required "
                        f"role for {tier} but you can still record a vote — "
                        f"it just doesn't count toward quorum."
                    )

                vote_choice = st.radio(
                    "Decision:",
                    ["APPROVE", "DECLINE", "ABSTAIN"],
                    horizontal=True,
                    key="ca_vote_choice",
                )
                # Per Joshua: 'their approval process has to be documented'
                rat_label = (
                    "Rationale (REQUIRED for branch decisions — documented per BCC policy):"
                    if is_branch_member
                    else "Rationale (required for DECLINE):"
                )
                rationale = st.text_area(rat_label, key="ca_vote_rat")

                if st.button("📥 Record vote", type="primary",
                            key="ca_vote_submit"):
                    # Per Joshua doctrine: branch decisions MUST be documented.
                    rationale_required = (
                        vote_choice == "DECLINE" or is_branch_member
                    )
                    if rationale_required and not rationale.strip():
                        if is_branch_member:
                            st.error(
                                "❌ Rationale required for ALL branch committee "
                                "decisions (BCC documentation policy)."
                            )
                        else:
                            st.error("Rationale required for DECLINE")
                    else:
                        # Check if this user already voted on this app
                        existing_votes = [
                            v for d in decisions
                            if d.get("application_id") == picked_id
                            for v in d.get("votes", [])
                            if v.get("voter_id") == sc
                        ]
                        if existing_votes:
                            st.warning(
                                f"You already voted on {picked_id} — "
                                f"this will be added as a revision."
                            )
                        vote = CommitteeVote(
                            voter_role=user_role_enum,
                            voter_id=sc or uname,
                            decision=vote_choice,
                            timestamp=datetime.now().isoformat(),
                            rationale=rationale,
                        )

                        # Aggregate existing votes for this app + new vote
                        all_votes_for_app = []
                        for d in decisions:
                            if d.get("application_id") == picked_id:
                                for v in d.get("votes", []):
                                    if v.get("voter_id") != sc:  # exclude revised
                                        all_votes_for_app.append(
                                            CommitteeVote(
                                                voter_role=CommitteeRole(v["voter_role"]),
                                                voter_id=v["voter_id"],
                                                decision=v["decision"],
                                                timestamp=v["timestamp"],
                                                rationale=v.get("rationale", ""),
                                            )
                                        )
                        all_votes_for_app.append(vote)

                        # Committee ID encodes branch vs HO
                        committee_prefix = "BCC" if is_branch_member else "COMMITTEE"
                        branch_suffix = ""
                        if is_branch_member:
                            ub = ud.get("branch") or ud.get("branch_code") or "BR"
                            branch_suffix = f"_{ub}"
                        decision = evaluate_committee_decision(
                            application_id=picked_id,
                            committee_id=f"{committee_prefix}_{tier}{branch_suffix}_{date.today().isoformat()}",
                            amount_kes=amount,
                            votes=all_votes_for_app,
                            originated_at_branch=is_branch_member,
                        )

                        # Persist
                        record = {
                            "application_id": picked_id,
                            "client_name": picked_app.get("client_name", ""),
                            "amount": float(amount),
                            "tier": tier,
                            "committee_id": decision.committee_id,
                            "quorum_required": decision.quorum_required,
                            "quorum_present": decision.quorum_present,
                            "votes": [
                                {
                                    "voter_role": v.voter_role.value,
                                    "voter_id": v.voter_id,
                                    "decision": v.decision,
                                    "timestamp": v.timestamp,
                                    "rationale": v.rationale,
                                }
                                for v in all_votes_for_app
                            ],
                            "approve_count": decision.approve_count,
                            "decline_count": decision.decline_count,
                            "abstain_count": decision.abstain_count,
                            "outcome": decision.outcome,
                            "threshold_required_pct": float(
                                decision.threshold_required_pct
                            ),
                            "recorded_at": datetime.now().isoformat(),
                            "recorded_by": uname,
                        }
                        # Remove previous decision record for this app
                        decisions = [d for d in decisions
                                    if d.get("application_id") != picked_id]
                        decisions.append(record)
                        _save_decisions(decisions)
                        audit_log(
                            "COMMITTEE_VOTE",
                            uname,
                            f"{user_role_enum.value} voted {vote_choice} "
                            f"on {picked_id} ({tier}, outcome={decision.outcome})",
                        )
                        _bsc_trigger(uname, "K022")  # Credit decision KPI
                        if decision.outcome == "APPROVED":
                            st.success(
                                f"✅ Vote recorded. **Decision: APPROVED** "
                                f"({decision.approve_count}/{decision.approve_count + decision.decline_count} "
                                f"≥ {decision.threshold_required_pct}%)"
                            )
                        elif decision.outcome == "APPROVED_AT_BRANCH":
                            st.success(
                                f"✅ Vote recorded. **Decision: APPROVED AT BRANCH** "
                                f"— BCC can disburse this loan directly. "
                                f"({decision.approve_count}/{decision.approve_count + decision.decline_count})"
                            )
                        elif decision.outcome == "APPROVED_BRANCH_FORWARD_HO":
                            st.success(
                                f"✅ Vote recorded. **Decision: APPROVED — FORWARDED TO HEAD OFFICE** "
                                f"— BCC has approved at branch level. Application now moves "
                                f"to HO TIER_2 committee for final approval. "
                                f"({decision.approve_count}/{decision.approve_count + decision.decline_count})"
                            )
                        elif decision.outcome == "DECLINED":
                            st.error(
                                f"❌ Vote recorded. **Decision: DECLINED**"
                            )
                        elif decision.outcome == "TIE":
                            st.warning(
                                f"⚖️ Vote recorded. **Decision: TIE** "
                                f"— additional members needed to break tie."
                            )
                        else:
                            st.info(
                                f"📋 Vote recorded. **Decision: {decision.outcome}** "
                                f"— more votes needed for quorum "
                                f"({decision.quorum_present}/{decision.quorum_required})."
                            )


# ════════════════════════════════════════════════════════════════════
# TAB 7 — DECISION HISTORY
# ════════════════════════════════════════════════════════════════════
with tabs[6]:
    st.subheader("Past committee decisions")

    if not decisions:
        st.info("No committee decisions logged yet.")
    else:
        # Top metrics
        approved = [d for d in decisions if d.get("outcome") == "APPROVED"]
        declined = [d for d in decisions if d.get("outcome") == "DECLINED"]
        pending = [d for d in decisions if d.get("outcome") in ("NO_QUORUM", "TIE")]
        h1, h2, h3 = st.columns(3)
        h1.metric("Approved", len(approved))
        h2.metric("Declined", len(declined))
        h3.metric("Pending quorum/tie", len(pending))

        rows = []
        for d in sorted(decisions, key=lambda x: x.get("recorded_at", ""),
                       reverse=True)[:100]:
            rows.append({
                "App ID":         d.get("application_id", ""),
                "Client":         str(d.get("client_name", ""))[:30],
                "Amount (M)":     d.get("amount", 0) / 1e6,
                "Tier":           d.get("tier", ""),
                "Outcome":        d.get("outcome", ""),
                "Votes (A/D/Ab)": (
                    f"{d.get('approve_count', 0)}/"
                    f"{d.get('decline_count', 0)}/"
                    f"{d.get('abstain_count', 0)}"
                ),
                "Quorum":         f"{d.get('quorum_present', 0)}/{d.get('quorum_required', 0)}",
                "Recorded":       str(d.get("recorded_at", ""))[:19],
            })
        st.dataframe(pd.DataFrame(rows),
                    use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════════
# TAB 8 — COMMITTEE CONFIGURATION (read-only)
# ════════════════════════════════════════════════════════════════════
with tabs[7]:
    st.subheader("Committee tier configuration")
    st.caption(
        "Tier thresholds + required roles + approve threshold per amount band. "
        "Configured in `utils/credit_workflow.py::COMMITTEE_REQUIREMENTS`."
    )

    config_rows = []
    for tier, req in COMMITTEE_REQUIREMENTS.items():
        config_rows.append({
            "Tier": tier,
            "Quorum": req["quorum"],
            "Approve threshold (%)": float(req["approve_threshold_pct"]),
            "Required roles": ", ".join(r.value for r in req["required_roles"]),
        })
    st.dataframe(pd.DataFrame(config_rows),
                use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("##### Tier boundaries (amount-based)")
    st.markdown(
        "- **TIER_1**: ≤ 500K KES → automated, no committee required\n"
        "- **TIER_2**: 500K – 5M KES → 2 roles, 60% threshold\n"
        "- **TIER_3**: 5M – 50M KES → 4 roles, 75% threshold\n"
        "- **TIER_4**: > 50M KES → 5 roles incl CEO+CFO+Board, 80% threshold"
    )

    st.markdown("##### Roles recognised")
    role_rows = [{"Role": r.value} for r in CommitteeRole]
    st.dataframe(pd.DataFrame(role_rows),
                use_container_width=True, hide_index=True)
