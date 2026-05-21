"""
Phase 2A — SWIFT Operational Cockpit (pages/99)
=================================================================
v10.283 — covers Standard #272 (SWIFT Integration, single)

Audience: Trade finance ops, SWIFT operators, compliance.

The TradeFinanceSwiftEngine was built in v10.72 with smoke-test
integration in pages/46_trade_finance.py. This page is its
dedicated operational cockpit: paste in raw MT block 4, parse,
validate per message type, and (for MT700) cross-check against
a TradeInstrument record from ENH-269.

Tab map (5 tabs):
  1. Parse & Validate           — paste MT body, choose type, validate
  2. MT700 Cross-Check          — validate then compare against instrument
  3. Field Findings             — drill into individual field outcomes
  4. Validation History         — recent validations log
  5. Reference                  — message-type reference and framework refs

Per Rule 7, this page never sends MT messages over SWIFTNet,
never auto-corrects malformed fields. Diagnostic only.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available


from utils.core_audit import audit_log
from utils.trade_finance_swift import (
    TradeFinanceSwiftEngine,
    SwiftMessageType, FieldStatus,
    MessageValidationOutcome, CrossCheckOutcome,
)

try:
    from pages._access import require_access
    require_access("trade_finance.swift_cockpit")
except Exception:
    pass


@st.cache_resource
def _engine():
    return TradeFinanceSwiftEngine()


_VALIDATORS = {
    SwiftMessageType.MT700: "validate_mt700_structure",
    SwiftMessageType.MT707: "validate_mt707_structure",
    SwiftMessageType.MT760: "validate_mt760_structure",
    SwiftMessageType.MT103: "validate_mt103_structure",
}

_TYPE_LABELS = {
    SwiftMessageType.MT700: "MT700 — Issue of LC",
    SwiftMessageType.MT707: "MT707 — LC Amendment",
    SwiftMessageType.MT760: "MT760 — Guarantee/Standby Issuance",
    SwiftMessageType.MT103: "MT103 — Customer Credit Transfer",
}


def _outcome_badge(outcome: MessageValidationOutcome) -> str:
    if outcome == MessageValidationOutcome.VALID:
        return "✅ VALID"
    if outcome == MessageValidationOutcome.WARNING:
        return "⚠️ WARNING"
    return "❌ INVALID"


def _cross_outcome_badge(outcome: CrossCheckOutcome) -> str:
    if outcome == CrossCheckOutcome.ALIGNED:
        return "✅ ALIGNED"
    if outcome == CrossCheckOutcome.DIVERGENT:
        return "❌ DIVERGENT"
    return "❓ UNCHECKABLE"


def _field_badge(status: FieldStatus) -> str:
    if status == FieldStatus.PRESENT:
        return "✅ PRESENT"
    if status == FieldStatus.MISSING_MANDATORY:
        return "❌ MISSING (mandatory)"
    if status == FieldStatus.MISSING_OPTIONAL:
        return "⚪ missing (optional)"
    if status == FieldStatus.MALFORMED:
        return "⚠️ MALFORMED"
    return "❓ UNEXPECTED"


def main():
    st.title("📡 SWIFT Operational Cockpit")
    st.caption(
        "v10.283 · Standard #272 · MT700/707/760/103 validation + "
        "MT700 cross-check against TradeInstrument · "
        "Diagnostic only (Rule 7)"
    )

    eng = _engine()
    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    # Per-session validation cache so tab 2/3 see results from tab 1
    if "swift_last_parsed" not in st.session_state:
        st.session_state["swift_last_parsed"] = None
    if "swift_last_validation" not in st.session_state:
        st.session_state["swift_last_validation"] = None
    if "swift_history" not in st.session_state:
        st.session_state["swift_history"] = []

    tabs = st.tabs([
        "📥 Parse & Validate",
        "🔁 MT700 Cross-Check",
        "🔍 Field Findings",
        "📋 Validation History",
        "📚 Reference",
    ])

    # =========================================================
    # Tab 1: Parse & Validate
    # =========================================================
    with tabs[0]:
        st.subheader("Parse SWIFT MT message and validate structure")
        st.caption(
            "Paste raw MT block 4 body (the {:NN[X]:value} field "
            "block). Wrapper '{4:...-}' is auto-stripped. "
            "Engine returns parsed fields + completeness % + "
            "outcome (VALID/WARNING/INVALID) per message type."
        )

        msg_type_label = st.selectbox(
            "Message type",
            options=list(SwiftMessageType),
            format_func=lambda mt: _TYPE_LABELS[mt],
        )

        raw_body = st.text_area(
            "Raw MT block 4 body",
            height=240,
            placeholder=(
                ":27:1/1\n"
                ":40A:IRREVOCABLE\n"
                ":20:LC-2026-001\n"
                ":31C:260301\n"
                ":31D:260601KENYA\n"
                ":50:ABC TRADERS LTD\n"
                "..."
            ),
        )

        col1, col2 = st.columns([1, 1])
        with col1:
            parse_btn = st.button(
                "Parse + Validate", type="primary",
                use_container_width=True,
            )
        with col2:
            clear_btn = st.button(
                "Clear cache", use_container_width=True,
            )

        if clear_btn:
            st.session_state["swift_last_parsed"] = None
            st.session_state["swift_last_validation"] = None
            audit_log(
                action="swift_cockpit_clear_cache",
                username=actor,
                module="swift_cockpit",
            )
            st.info("Cache cleared")

        if parse_btn:
            if not raw_body.strip():
                st.error("Paste an MT body first")
            else:
                try:
                    parsed = eng.parse_message(msg_type_label, raw_body)
                    st.session_state["swift_last_parsed"] = parsed
                    audit_log(
                        action="swift_parse_message",
                        username=actor,
                        module="swift_cockpit",
                    )
                    validator_name = _VALIDATORS[msg_type_label]
                    validator = getattr(eng, validator_name)
                    validation = validator(parsed)
                    st.session_state["swift_last_validation"] = validation
                    st.session_state["swift_history"].append({
                        "at": datetime.utcnow().isoformat(),
                        "actor": actor,
                        "message_type": msg_type_label.value,
                        "outcome": validation.outcome.value,
                        "completeness_pct": float(
                            validation.completeness_pct,
                        ),
                        "finding_count": len(validation.findings),
                    })
                    if len(st.session_state["swift_history"]) > 50:
                        st.session_state["swift_history"] = (
                            st.session_state["swift_history"][-50:]
                        )
                    audit_log(
                        action=f"swift_{validator_name}",
                        username=actor,
                        module="swift_cockpit",
                    )
                    cols = st.columns(3)
                    cols[0].metric(
                        "Outcome", _outcome_badge(validation.outcome),
                    )
                    cols[1].metric(
                        "Completeness",
                        f"{validation.completeness_pct}%",
                    )
                    cols[2].metric(
                        "Findings", len(validation.findings),
                    )
                    if validation.framework_refs:
                        st.caption(
                            "Framework: "
                            + " · ".join(validation.framework_refs),
                        )
                except ValueError as exc:
                    st.error(str(exc))
                    audit_log(
                        action="swift_parse_message",
                        username=actor,
                        module="swift_cockpit",
                    )

        # Display parsed fields if available
        parsed = st.session_state.get("swift_last_parsed")
        if parsed:
            with st.expander(
                f"📑 Parsed fields ({len(parsed.fields)})",
                expanded=False,
            ):
                for f in parsed.fields:
                    val = f.value if len(f.value) <= 80 \
                        else f.value[:77] + "..."
                    st.text(f":{f.tag}: {val}")

    # =========================================================
    # Tab 2: MT700 Cross-Check
    # =========================================================
    with tabs[1]:
        st.subheader("MT700 cross-check against TradeInstrument")
        st.caption(
            "Compare a parsed MT700 against a TradeInstrument record "
            "from ENH-269. Surfaces ALIGNED / DIVERGENT / UNCHECKABLE "
            "per matched field."
        )

        parsed = st.session_state.get("swift_last_parsed")
        if not parsed:
            st.info(
                "Parse an MT700 in Tab 1 first, then return here.",
            )
        elif parsed.message_type != SwiftMessageType.MT700:
            st.warning(
                f"Last parsed message is "
                f"{parsed.message_type.value}, not MT700. "
                "Cross-check is MT700-only.",
            )
        else:
            with st.form("xcheck_form"):
                st.write("Paste TradeInstrument fields to compare:")
                inst_id = st.text_input("instrument_id (matches :20:)")
                currency = st.text_input("currency (matches :32B: ccy)")
                amount = st.text_input("amount_kes (matches :32B: amt)")
                applicant = st.text_input(
                    "applicant (substring match :50:)",
                )
                beneficiary = st.text_input(
                    "beneficiary (substring match :59:)",
                )
                if st.form_submit_button(
                    "Run cross_check_mt700_against_instrument",
                ):
                    # Build a minimal instrument-like object
                    class _MockInstrument:
                        pass

                    inst = _MockInstrument()
                    inst.instrument_id = inst_id
                    inst.currency = currency
                    try:
                        inst.amount_kes = (
                            Decimal(amount) if amount else Decimal("0")
                        )
                    except Exception:
                        inst.amount_kes = Decimal("0")
                    inst.applicant = applicant
                    inst.beneficiary = beneficiary

                    try:
                        report = eng.cross_check_mt700_against_instrument(
                            parsed, inst,
                        )
                        audit_log(
                            action="swift_cross_check_mt700",
                            username=actor,
                            module="swift_cockpit",
                        )
                        cols = st.columns(2)
                        cols[0].metric(
                            "Overall outcome",
                            _cross_outcome_badge(report.overall_outcome),
                        )
                        cols[1].metric(
                            "Findings", len(report.findings),
                        )
                        st.markdown("**Per-field outcomes:**")
                        for fnd in report.findings:
                            badge = _cross_outcome_badge(fnd.outcome)
                            label = fnd.field_label or fnd.field_tag
                            st.write(
                                f"• `{label}`: {badge} — "
                                f"{fnd.description}",
                            )
                            if (fnd.mt_value or fnd.instrument_value) \
                                    and fnd.outcome != \
                                    CrossCheckOutcome.ALIGNED:
                                st.caption(
                                    f"   MT: `{fnd.mt_value}` · "
                                    f"Instrument: "
                                    f"`{fnd.instrument_value}`",
                                )
                    except (ValueError, AttributeError) as exc:
                        st.error(str(exc))
                        audit_log(
                            action="swift_cross_check_mt700",
                            username=actor,
                            module="swift_cockpit",
                        )

    # =========================================================
    # Tab 3: Field Findings
    # =========================================================
    with tabs[2]:
        st.subheader("Field-by-field findings")

        validation = st.session_state.get("swift_last_validation")
        if not validation:
            st.info(
                "No validation in this session. "
                "Run Tab 1 first.",
            )
        else:
            cols = st.columns(5)
            counts = {fs: 0 for fs in FieldStatus}
            for fnd in validation.findings:
                counts[fnd.status] = counts.get(fnd.status, 0) + 1
            for i, fs in enumerate(FieldStatus):
                cols[i].metric(fs.value, counts[fs])

            sev_filter = st.multiselect(
                "Filter by status",
                options=list(FieldStatus),
                default=[
                    FieldStatus.MISSING_MANDATORY,
                    FieldStatus.MALFORMED,
                ],
                format_func=lambda fs: fs.value,
            )

            shown = [
                f for f in validation.findings
                if not sev_filter or f.status in sev_filter
            ]
            st.caption(f"Showing {len(shown)}/{len(validation.findings)}")
            for f in shown:
                badge = _field_badge(f.status)
                tag = f":{f.tag}:" if f.tag else "(no tag)"
                fname = f" [{f.field_name}]" if f.field_name else ""
                st.write(f"• {tag}{fname} — {badge} — {f.description}")

    # =========================================================
    # Tab 4: Validation History
    # =========================================================
    with tabs[3]:
        st.subheader("Recent validations (this session)")
        history = st.session_state.get("swift_history", [])
        if not history:
            st.info("No validations recorded yet.")
        else:
            st.metric("Validations recorded", len(history))
            for entry in reversed(history[-20:]):
                outcome = entry["outcome"]
                badge = (
                    "✅" if outcome == "VALID" else
                    "⚠️" if outcome == "WARNING" else
                    "❌"
                )
                st.write(
                    f"• {badge} {entry['at'][:19]} · "
                    f"MT{entry['message_type']} · {outcome} · "
                    f"completeness {entry['completeness_pct']}% · "
                    f"{entry['finding_count']} findings · "
                    f"by {entry['actor']}",
                )

    # =========================================================
    # Tab 5: Reference
    # =========================================================
    with tabs[4]:
        st.subheader("Message-type reference")
        st.markdown(
            """
**MT700 — Issue of a documentary credit (LC)**
Used by an issuing bank to advise an LC to a beneficiary's bank.
Mandatory tags include `:27:` (sequence), `:40A:` (form),
`:20:` (LC reference), `:31C:` (issue date), `:31D:` (expiry),
`:50:` (applicant), `:59:` (beneficiary), `:32B:` (currency+amount),
`:45A:` (description), `:46A:` (documents), `:49:` (confirmation).
Cross-field: `:31C:` (issue) ≤ `:31D:` (expiry).
Frameworks: SWIFT MT Standards + ICC UCP 600.

**MT707 — LC Amendment**
Mandatory tags include `:21:` (receiver's reference, links to
original LC), `:26E:` (amendment number, must increment).
Optional: new amount, new expiry. Frameworks: UCP 600.

**MT760 — Issuance of demand guarantee / standby LC**
Mandatory tags include `:40C:` (applicable rules — URDG/ISP98/UCP/
OTHER) and `:77C:` (details of guarantee).
Frameworks: ICC URDG 758 / ISP98.

**MT103 — Single customer credit transfer (settlement)**
Mandatory tags include `:23B:` (bank operation code),
`:32A:` (value-date+currency+amount), `:71A:` (details of charges
— BEN/OUR/SHA). Frameworks: SWIFT MT Standards.

---

**Rule 7 boundaries:** This engine never sends MT messages over
SWIFTNet, never auto-corrects malformed fields, never generates
messages from instrument records, never modifies network routing,
never mutates inputs. Operators submit messages through their
existing SWIFTNet connectivity layer; this cockpit is for
pre-send validation and post-receive forensic review only.
            """,
        )


main()
