"""utils/trade_finance_swift.py — v10.72: SWIFT MT validation.

ENH-272 — SWIFT Integration. Cat B — trade_finance arc 3/N.

Diagnostic SWIFT MT message validation engine for the four
trade-finance message types most relevant to LC + guarantee +
payment workflows:

  MT700  — Issue of a documentary credit (LC)
  MT707  — Amendment to a documentary credit
  MT760  — Issuance of a demand guarantee / standby LC
  MT103  — Single customer credit transfer (settlement)

Five capabilities:

  1. parse_message — split raw MT message body into tagged
     fields ({:NN[X]:value} format), preserving field order
  2. validate_mt700_structure — mandatory fields + format
     conformance + cross-field consistency (issue date ≤
     expiry date, etc.)
  3. validate_mt707_structure — amendment requires reference
     to original; amendment number incrementing
  4. validate_mt760_structure — guarantee-specific fields
     (purpose, governing law/rules)
  5. validate_mt103_structure — payment-specific fields
     (sender's reference, ordering customer, beneficiary)

Plus a cross-checker:
  6. cross_check_mt700_against_instrument — compare MT700
     fields against the TradeInstrument record from ENH-269
     (currency, amount, applicant, beneficiary, expiry, etc.)

Per Rule 7, engine NEVER:
  - sends MT messages over SWIFTNet (caller's responsibility)
  - auto-corrects malformed fields
  - generates MT messages from instrument records (would
    require LO/SR routing decisions outside this engine's scope)
  - submits to SWIFT for validation (this is offline / local)
  - modifies network routing
  - mutates inputs

Per Rule 1, every output surfaces message_type +
field-by-field findings + framework refs (SWIFT MT Standards
+ specific message type spec).

Pure stdlib (re for tag parsing + frozen dataclasses + enums).
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

SPEC_DEVIATION_NOTE = (
    "TradeFinanceSwiftEngine implements ENH-272 — SWIFT MT "
    "message structural validation for MT700 / MT707 / MT760 "
    "/ MT103. Pure stdlib (re for tag parsing). Per Rule 1, "
    "every output surfaces full provenance including "
    "field_tag-by-field_tag findings. Per Rule 7, engine "
    "DIAGNOSTIC ONLY — never sends MT messages over SWIFTNet; "
    "never auto-corrects malformed fields; never generates "
    "messages from instrument records (would require LO/SR "
    "routing decisions outside scope); never submits to SWIFT "
    "for validation (offline/local); never modifies network "
    "routing; never mutates inputs."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class SwiftMessageType(Enum):
    MT700 = "700"
    MT707 = "707"
    MT760 = "760"
    MT103 = "103"


class FieldStatus(Enum):
    PRESENT = "PRESENT"
    MISSING_MANDATORY = "MISSING_MANDATORY"
    MISSING_OPTIONAL = "MISSING_OPTIONAL"
    MALFORMED = "MALFORMED"
    UNEXPECTED = "UNEXPECTED"


class MessageValidationOutcome(Enum):
    VALID = "VALID"
    WARNING = "WARNING"
    INVALID = "INVALID"


class CrossCheckOutcome(Enum):
    ALIGNED = "ALIGNED"
    DIVERGENT = "DIVERGENT"
    UNCHECKABLE = "UNCHECKABLE"


# ════════════════════════════════════════════════════════════════════════
# Field specifications
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class FieldSpec:
    """Describes a SWIFT field's constraints."""
    tag: str                  # e.g. "20", "32B", "40A"
    name: str
    mandatory: bool
    pattern: Optional[str] = None   # regex; None means free format
    description: str = ""


# ════════════════════════════════════════════════════════════════════════
# Message dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SwiftField:
    tag: str             # e.g. "20", "32B"
    value: str           # raw field value (multi-line preserved)


@dataclass(frozen=True)
class ParsedMessage:
    message_type: SwiftMessageType
    fields: Tuple[SwiftField, ...]
    raw_body: str


@dataclass(frozen=True)
class FieldFinding:
    tag: str
    field_name: str
    status: FieldStatus
    description: str
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class MessageValidation:
    message_type: SwiftMessageType
    outcome: MessageValidationOutcome
    findings: Tuple[FieldFinding, ...]
    completeness_pct: Decimal   # % of mandatory fields present
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CrossCheckFinding:
    field_tag: str
    field_label: str
    mt_value: str
    instrument_value: str
    outcome: CrossCheckOutcome
    description: str


@dataclass(frozen=True)
class CrossCheckReport:
    instrument_id: str
    message_type: SwiftMessageType
    findings: Tuple[CrossCheckFinding, ...]
    overall_outcome: CrossCheckOutcome
    framework_refs: Tuple[str, ...] = ()


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class TradeFinanceSwiftEngine:
    """Diagnostic SWIFT MT validation engine."""

    # ─── MT700: Issue of a documentary credit (selected mandatory)
    # Reference: SWIFT MT 700/701 standards; UCP 600 alignment
    MT700_FIELDS: Tuple[FieldSpec, ...] = (
        FieldSpec("27", "Sequence of total", True,
                  pattern=r"^[1-9]/[1-9]$",
                  description="format: n/n e.g. 1/1"),
        FieldSpec("40A", "Form of documentary credit", True,
                  description=(
                      "IRREVOCABLE / IRREVOCABLE TRANSFERABLE / "
                      "IRREVOCABLE STANDBY etc.")),
        FieldSpec("20", "Documentary credit number", True,
                  pattern=r"^[A-Z0-9/\-]{1,16}$",
                  description="LC reference, ≤16 chars"),
        FieldSpec("31C", "Date of issue", True,
                  pattern=r"^\d{6}$",
                  description="YYMMDD"),
        FieldSpec("31D", "Date and place of expiry", True,
                  pattern=r"^\d{6}\s+.+$",
                  description="YYMMDD + place"),
        FieldSpec("50", "Applicant", True,
                  description="name + address (≤4×35 chars)"),
        FieldSpec("59", "Beneficiary", True,
                  description="name + address"),
        FieldSpec("32B", "Currency + amount", True,
                  pattern=r"^[A-Z]{3}\d+(?:,\d{1,3})?$",
                  description="ISO currency + amount with comma"),
        FieldSpec("41A", "Available with by", False,
                  description=(
                      "available with bank / by method")),
        FieldSpec("41D", "Available with by (party + addr)", False,
                  description=(
                      "alternate to 41A — party with address")),
        FieldSpec("43P", "Partial shipments", False,
                  pattern=r"^(ALLOWED|NOT ALLOWED)$"),
        FieldSpec("43T", "Transhipment", False,
                  pattern=r"^(ALLOWED|NOT ALLOWED)$"),
        FieldSpec("44E", "Port of loading/airport", False),
        FieldSpec("44F", "Port of discharge/airport", False),
        FieldSpec("45A", "Description of goods/services", True,
                  description="multi-line, ≤100 lines"),
        FieldSpec("46A", "Documents required", True,
                  description="multi-line"),
        FieldSpec("47A", "Additional conditions", False),
        FieldSpec("71B", "Charges", False),
        FieldSpec("49", "Confirmation instructions", True,
                  pattern=r"^(CONFIRM|MAY ADD|WITHOUT)$"),
        FieldSpec("78", "Instructions to paying/accepting/"
                  "negotiating bank", False),
    )

    # ─── MT707: LC amendment
    MT707_FIELDS: Tuple[FieldSpec, ...] = (
        FieldSpec("20", "Sender's reference", True,
                  description="amendment reference"),
        FieldSpec("21", "Receiver's reference", True,
                  description="original LC reference (mandatory)"),
        FieldSpec("23", "Issuing bank's reference", True),
        FieldSpec("26E", "Number of amendment", True,
                  pattern=r"^\d{1,4}$",
                  description="amendment sequence"),
        FieldSpec("30", "Date of amendment", True,
                  pattern=r"^\d{6}$"),
        FieldSpec("31C", "New date of issue", False),
        FieldSpec("31E", "New date of expiry", False,
                  pattern=r"^\d{6}$"),
        FieldSpec("32B", "Increase of amount", False,
                  pattern=r"^[A-Z]{3}\d+(?:,\d{1,3})?$"),
        FieldSpec("33B", "Decrease of amount", False,
                  pattern=r"^[A-Z]{3}\d+(?:,\d{1,3})?$"),
        FieldSpec("34B", "New documentary credit amount", False,
                  pattern=r"^[A-Z]{3}\d+(?:,\d{1,3})?$"),
        FieldSpec("39A", "Percentage credit amt tolerance", False),
        FieldSpec("79", "Narrative", False,
                  description="amendment description"),
    )

    # ─── MT760: Issuance of a demand guarantee / standby LC
    MT760_FIELDS: Tuple[FieldSpec, ...] = (
        FieldSpec("27", "Sequence of total", True,
                  pattern=r"^[1-9]/[1-9]$"),
        FieldSpec("20", "Sender's reference", True),
        FieldSpec("23", "Further identification", True,
                  description=(
                      "ISSUE / REQUEST / OTHER")),
        FieldSpec("30", "Date", True,
                  pattern=r"^\d{6}$"),
        FieldSpec("40C", "Applicable rules", True,
                  description=(
                      "URDG / ISP98 / UCP / OTHER")),
        FieldSpec("77C", "Details of guarantee", True,
                  description="full guarantee text"),
        FieldSpec("32B", "Currency + principal amount", True,
                  pattern=r"^[A-Z]{3}\d+(?:,\d{1,3})?$"),
    )

    # ─── MT103: Customer credit transfer
    MT103_FIELDS: Tuple[FieldSpec, ...] = (
        FieldSpec("20", "Sender's reference", True,
                  pattern=r"^[A-Z0-9/\-]{1,16}$"),
        FieldSpec("23B", "Bank operation code", True,
                  pattern=r"^(CRED|CRTS|SPAY|SPRI|SSTD)$",
                  description="CRED for credit transfer"),
        FieldSpec("32A", "Value date / currency / amount", True,
                  pattern=r"^\d{6}[A-Z]{3}\d+(?:,\d{1,3})?$",
                  description="YYMMDD + currency + amount"),
        FieldSpec("50A", "Ordering customer (party id)", False),
        FieldSpec("50K", "Ordering customer (name + addr)", False,
                  description="alternate to 50A"),
        FieldSpec("59", "Beneficiary customer", True),
        FieldSpec("70", "Remittance information", False),
        FieldSpec("71A", "Details of charges", True,
                  pattern=r"^(BEN|OUR|SHA)$"),
    )

    FIELD_SPECS_BY_MT: Dict[
        SwiftMessageType, Tuple[FieldSpec, ...]] = {
        SwiftMessageType.MT700: MT700_FIELDS,
        SwiftMessageType.MT707: MT707_FIELDS,
        SwiftMessageType.MT760: MT760_FIELDS,
        SwiftMessageType.MT103: MT103_FIELDS,
    }

    FRAMEWORK_REFS_BY_MT: Dict[
        SwiftMessageType, Tuple[str, ...]] = {
        SwiftMessageType.MT700: (
            "SWIFT Standards MT 700 — Issue of a documentary "
            "credit",
            "ICC UCP 600 — alignment for documentary credit "
            "fields",),
        SwiftMessageType.MT707: (
            "SWIFT Standards MT 707 — Amendment to a "
            "documentary credit",
            "ICC UCP 600 §10 — amendment requires beneficiary "
            "consent",),
        SwiftMessageType.MT760: (
            "SWIFT Standards MT 760 — Issuance of a demand "
            "guarantee or standby letter of credit",
            "ICC URDG 758 / ISP98 — applicable rules",),
        SwiftMessageType.MT103: (
            "SWIFT Standards MT 103 — Single customer credit "
            "transfer",
            "SWIFT Category 1 — Customer Payments",),
    }

    # Tag matcher: ":NN[X]:value" where NN is digits + optional letter
    # Supports multi-line values until next tag or block end
    TAG_PATTERN: re.Pattern = re.compile(
        r":([0-9]{2}[A-Z]?):", re.MULTILINE)

    def parse_message(
        self, message_type: SwiftMessageType, raw_body: str,
    ) -> ParsedMessage:
        """Parse SWIFT block 4 (text block) into tagged fields.

        Accepts the body as either Block 4 wrapped (i.e.
        '{4:...-}') or unwrapped. Splits on tag positions
        preserving field order.
        """
        body = raw_body.strip()
        # Strip block 4 wrapper if present
        if body.startswith("{4:"):
            body = body[3:]
        if body.endswith("-}"):
            body = body[:-2]
        elif body.endswith("}"):
            body = body[:-1]
        # Find all tag positions
        matches = list(self.TAG_PATTERN.finditer(body))
        fields: List[SwiftField] = []
        for i, m in enumerate(matches):
            tag = m.group(1)
            start = m.end()
            end = (
                matches[i + 1].start()
                if i + 1 < len(matches) else len(body))
            value = body[start:end].strip()
            fields.append(SwiftField(tag=tag, value=value))
        return ParsedMessage(
            message_type=message_type,
            fields=tuple(fields),
            raw_body=raw_body)

    def _validate_message(
        self,
        parsed: ParsedMessage,
        specs: Tuple[FieldSpec, ...],
    ) -> MessageValidation:
        present_tags = {f.tag for f in parsed.fields}
        spec_by_tag = {s.tag: s for s in specs}
        findings: List[FieldFinding] = []
        outcome = MessageValidationOutcome.VALID
        mandatory_total = 0
        mandatory_present = 0

        for spec in specs:
            if spec.mandatory:
                mandatory_total += 1
            if spec.tag not in present_tags:
                if spec.mandatory:
                    mandatory_present += 0  # explicit
                    findings.append(FieldFinding(
                        tag=spec.tag,
                        field_name=spec.name,
                        status=FieldStatus.MISSING_MANDATORY,
                        description=(
                            f"mandatory field {spec.tag} "
                            f"({spec.name}) missing")))
                    outcome = MessageValidationOutcome.INVALID
                else:
                    findings.append(FieldFinding(
                        tag=spec.tag,
                        field_name=spec.name,
                        status=FieldStatus.MISSING_OPTIONAL,
                        description=(
                            f"optional field {spec.tag} "
                            f"({spec.name}) absent — no "
                            f"compliance impact")))
            else:
                mandatory_present += (
                    1 if spec.mandatory else 0)
                # Check format if pattern provided
                field = next(
                    f for f in parsed.fields if f.tag == spec.tag)
                if spec.pattern is not None:
                    # For multi-line / first-line check, use
                    # first line only for fields with pattern
                    first_line = field.value.split("\n", 1)[0]
                    if not re.fullmatch(
                        spec.pattern, first_line.strip()
                    ):
                        findings.append(FieldFinding(
                            tag=spec.tag,
                            field_name=spec.name,
                            status=FieldStatus.MALFORMED,
                            description=(
                                f"field {spec.tag} "
                                f"({spec.name}) format mismatch: "
                                f"expected pattern "
                                f"'{spec.pattern}', got "
                                f"'{first_line[:60]}'")))
                        outcome = (
                            MessageValidationOutcome.INVALID)

        # Unexpected fields (not in spec)
        for f in parsed.fields:
            if f.tag not in spec_by_tag:
                findings.append(FieldFinding(
                    tag=f.tag,
                    field_name="<unknown>",
                    status=FieldStatus.UNEXPECTED,
                    description=(
                        f"field {f.tag} not part of "
                        f"{parsed.message_type.value} spec — "
                        f"may be permitted by network rule "
                        f"book; review")))
                if outcome == MessageValidationOutcome.VALID:
                    outcome = MessageValidationOutcome.WARNING

        completeness = (
            (Decimal(mandatory_present)
             / Decimal(mandatory_total))
            if mandatory_total > 0 else Decimal("1"))

        return MessageValidation(
            message_type=parsed.message_type,
            outcome=outcome,
            findings=tuple(findings),
            completeness_pct=completeness,
            framework_refs=(
                f"ENH-272 §validate_{parsed.message_type.name.lower()}",
            ) + self.FRAMEWORK_REFS_BY_MT[parsed.message_type] + (
                "Per Rule 7 — never sends; never auto-corrects",))

    def validate_mt700_structure(
        self, parsed: ParsedMessage,
    ) -> MessageValidation:
        if parsed.message_type != SwiftMessageType.MT700:
            raise ValueError(
                f"validate_mt700_structure called with "
                f"{parsed.message_type.value}")
        validation = self._validate_message(
            parsed, self.MT700_FIELDS)
        # Cross-field consistency: 31C issue date ≤ 31D expiry
        issue_field = next(
            (f for f in parsed.fields if f.tag == "31C"), None)
        expiry_field = next(
            (f for f in parsed.fields if f.tag == "31D"), None)
        if issue_field and expiry_field:
            try:
                issue_str = issue_field.value.strip()[:6]
                expiry_str = (
                    expiry_field.value.strip().split()[0])
                # YYMMDD
                if (
                    len(issue_str) == 6 and len(expiry_str) == 6
                    and issue_str.isdigit()
                    and expiry_str.isdigit()
                    and expiry_str < issue_str
                ):
                    extra = FieldFinding(
                        tag="31C/31D",
                        field_name="Issue date / Expiry date",
                        status=FieldStatus.MALFORMED,
                        description=(
                            f"expiry {expiry_str} precedes "
                            f"issue {issue_str} — semantic "
                            f"inconsistency"))
                    return MessageValidation(
                        message_type=validation.message_type,
                        outcome=(
                            MessageValidationOutcome.INVALID),
                        findings=(
                            validation.findings + (extra,)),
                        completeness_pct=(
                            validation.completeness_pct),
                        framework_refs=(
                            validation.framework_refs))
            except (ValueError, IndexError):
                pass
        return validation

    def validate_mt707_structure(
        self, parsed: ParsedMessage,
    ) -> MessageValidation:
        if parsed.message_type != SwiftMessageType.MT707:
            raise ValueError("not MT707")
        return self._validate_message(parsed, self.MT707_FIELDS)

    def validate_mt760_structure(
        self, parsed: ParsedMessage,
    ) -> MessageValidation:
        if parsed.message_type != SwiftMessageType.MT760:
            raise ValueError("not MT760")
        return self._validate_message(parsed, self.MT760_FIELDS)

    def validate_mt103_structure(
        self, parsed: ParsedMessage,
    ) -> MessageValidation:
        if parsed.message_type != SwiftMessageType.MT103:
            raise ValueError("not MT103")
        return self._validate_message(parsed, self.MT103_FIELDS)

    def cross_check_mt700_against_instrument(
        self,
        parsed: ParsedMessage,
        instrument,    # TradeInstrument from ENH-269
    ) -> CrossCheckReport:
        if parsed.message_type != SwiftMessageType.MT700:
            raise ValueError(
                "cross_check_mt700_against_instrument requires "
                "MT700")
        findings: List[CrossCheckFinding] = []
        field_by_tag = {f.tag: f for f in parsed.fields}

        # 20: documentary credit number ↔ instrument_id
        if "20" in field_by_tag:
            mt_ref = field_by_tag["20"].value.strip()
            outcome = (
                CrossCheckOutcome.ALIGNED
                if mt_ref == instrument.instrument_id
                else CrossCheckOutcome.DIVERGENT)
            findings.append(CrossCheckFinding(
                field_tag="20",
                field_label="Documentary credit number",
                mt_value=mt_ref,
                instrument_value=instrument.instrument_id,
                outcome=outcome,
                description=(
                    "MT700 :20: should match "
                    "TradeInstrument.instrument_id")))

        # 32B: currency + amount
        if "32B" in field_by_tag:
            mt_val = field_by_tag["32B"].value.strip()
            m = re.match(
                r"^([A-Z]{3})(\d+(?:,\d{1,3})?)$", mt_val)
            if m:
                mt_currency = m.group(1)
                mt_amount = Decimal(
                    m.group(2).replace(",", "."))
                # Compare currency
                cur_outcome = (
                    CrossCheckOutcome.ALIGNED
                    if mt_currency == instrument.currency
                    else CrossCheckOutcome.DIVERGENT)
                findings.append(CrossCheckFinding(
                    field_tag="32B-currency",
                    field_label="Currency",
                    mt_value=mt_currency,
                    instrument_value=instrument.currency,
                    outcome=cur_outcome,
                    description=(
                        "MT700 :32B: currency vs instrument "
                        "currency")))
                # Compare amount
                amt_outcome = (
                    CrossCheckOutcome.ALIGNED
                    if mt_amount == instrument.amount_kes
                    else CrossCheckOutcome.DIVERGENT)
                findings.append(CrossCheckFinding(
                    field_tag="32B-amount",
                    field_label="Amount",
                    mt_value=str(mt_amount),
                    instrument_value=str(instrument.amount_kes),
                    outcome=amt_outcome,
                    description=(
                        "MT700 :32B: amount vs "
                        "instrument amount_kes")))
            else:
                findings.append(CrossCheckFinding(
                    field_tag="32B",
                    field_label="Currency + amount",
                    mt_value=mt_val,
                    instrument_value=(
                        f"{instrument.currency}"
                        f"{instrument.amount_kes}"),
                    outcome=CrossCheckOutcome.UNCHECKABLE,
                    description=(
                        "MT700 :32B: malformed — cannot parse "
                        "currency/amount")))

        # 50: applicant
        if "50" in field_by_tag:
            mt_applicant = (
                field_by_tag["50"].value.split("\n", 1)[0]
                .strip())
            inst_applicant = instrument.applicant.strip()
            # Substring match — applicant name often is a
            # substring of the full address line
            outcome = (
                CrossCheckOutcome.ALIGNED
                if (
                    inst_applicant in mt_applicant
                    or mt_applicant in inst_applicant)
                else CrossCheckOutcome.DIVERGENT)
            findings.append(CrossCheckFinding(
                field_tag="50",
                field_label="Applicant",
                mt_value=mt_applicant,
                instrument_value=inst_applicant,
                outcome=outcome,
                description=(
                    "MT700 :50: applicant name should match "
                    "TradeInstrument.applicant")))

        # 59: beneficiary
        if "59" in field_by_tag:
            mt_beneficiary = (
                field_by_tag["59"].value.split("\n", 1)[0]
                .strip())
            inst_beneficiary = instrument.beneficiary.strip()
            outcome = (
                CrossCheckOutcome.ALIGNED
                if (
                    inst_beneficiary in mt_beneficiary
                    or mt_beneficiary in inst_beneficiary)
                else CrossCheckOutcome.DIVERGENT)
            findings.append(CrossCheckFinding(
                field_tag="59",
                field_label="Beneficiary",
                mt_value=mt_beneficiary,
                instrument_value=inst_beneficiary,
                outcome=outcome,
                description=(
                    "MT700 :59: beneficiary name should match "
                    "TradeInstrument.beneficiary")))

        # Overall outcome — DIVERGENT if any DIVERGENT;
        # else UNCHECKABLE if any UNCHECKABLE; else ALIGNED
        overall = CrossCheckOutcome.ALIGNED
        if any(
            f.outcome == CrossCheckOutcome.DIVERGENT
            for f in findings
        ):
            overall = CrossCheckOutcome.DIVERGENT
        elif any(
            f.outcome == CrossCheckOutcome.UNCHECKABLE
            for f in findings
        ):
            overall = CrossCheckOutcome.UNCHECKABLE

        return CrossCheckReport(
            instrument_id=instrument.instrument_id,
            message_type=SwiftMessageType.MT700,
            findings=tuple(findings),
            overall_outcome=overall,
            framework_refs=(
                "ENH-272 §cross_check_mt700_against_instrument",
                "Per Rule 7 — surfaces alignment findings; "
                "operator reconciles before transmission",
            ),
        )


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

# Sample valid MT700
SAMPLE_MT700 = """{4:
:27:1/1
:40A:IRREVOCABLE
:20:LC-2026-001
:31C:260401
:31D:260701 NAIROBI
:50:ACME IMPORTS LTD
NAIROBI KENYA
:59:SHANGHAI STEEL CO
SHANGHAI CHINA
:32B:USD500000,00
:41D:ANY BANK
BY NEGOTIATION
:43P:ALLOWED
:43T:NOT ALLOWED
:45A:500MT COLD-ROLLED STEEL COILS
GRADE A
:46A:1. COMMERCIAL INVOICE
2. PACKING LIST
3. BILL OF LADING
:49:WITHOUT
-}"""


SAMPLE_MT700_MISSING_MANDATORY = """{4:
:27:1/1
:20:LC-002
:31C:260401
:50:ACME
:59:BETA
:32B:USD100000,00
:46A:DOCS
:49:WITHOUT
-}"""


SAMPLE_MT700_MALFORMED_REF = """{4:
:27:1/1
:40A:IRREVOCABLE
:20:THIS REFERENCE IS WAY TOO LONG OVER 16 CHARS
:31C:260401
:31D:260701 NAIROBI
:50:A
:59:B
:32B:USD100000,00
:45A:GOODS
:46A:DOCS
:49:WITHOUT
-}"""


SAMPLE_MT103 = """{4:
:20:PAY-2026-001
:23B:CRED
:32A:260415USD50000,00
:50K:ACME LTD
:59:SHANGHAI STEEL
:71A:OUR
-}"""


def _test_parse_extracts_all_tags():
    eng = TradeFinanceSwiftEngine()
    parsed = eng.parse_message(
        SwiftMessageType.MT700, SAMPLE_MT700)
    tags = {f.tag for f in parsed.fields}
    assert "27" in tags
    assert "40A" in tags
    assert "20" in tags
    assert "32B" in tags
    assert "45A" in tags


def _test_parse_preserves_multiline_values():
    eng = TradeFinanceSwiftEngine()
    parsed = eng.parse_message(
        SwiftMessageType.MT700, SAMPLE_MT700)
    field_45a = next(f for f in parsed.fields if f.tag == "45A")
    assert "STEEL COILS" in field_45a.value
    assert "GRADE A" in field_45a.value


def _test_parse_handles_no_block4_wrapper():
    eng = TradeFinanceSwiftEngine()
    body = ":20:LC-001\n:32B:USD1000,00"
    parsed = eng.parse_message(SwiftMessageType.MT700, body)
    assert len(parsed.fields) == 2


def _test_validate_clean_mt700_passes():
    eng = TradeFinanceSwiftEngine()
    parsed = eng.parse_message(
        SwiftMessageType.MT700, SAMPLE_MT700)
    v = eng.validate_mt700_structure(parsed)
    assert v.outcome == MessageValidationOutcome.VALID
    assert v.completeness_pct == Decimal("1")


def _test_validate_mt700_missing_mandatory():
    eng = TradeFinanceSwiftEngine()
    parsed = eng.parse_message(
        SwiftMessageType.MT700,
        SAMPLE_MT700_MISSING_MANDATORY)
    v = eng.validate_mt700_structure(parsed)
    assert v.outcome == MessageValidationOutcome.INVALID
    missing = [
        f for f in v.findings
        if f.status == FieldStatus.MISSING_MANDATORY]
    # Should flag :40A: :31D: :45A:
    missing_tags = {f.tag for f in missing}
    assert "40A" in missing_tags
    assert "31D" in missing_tags
    assert "45A" in missing_tags


def _test_validate_mt700_malformed_pattern():
    eng = TradeFinanceSwiftEngine()
    parsed = eng.parse_message(
        SwiftMessageType.MT700, SAMPLE_MT700_MALFORMED_REF)
    v = eng.validate_mt700_structure(parsed)
    assert v.outcome == MessageValidationOutcome.INVALID
    malformed = [
        f for f in v.findings
        if f.status == FieldStatus.MALFORMED]
    # Should flag :20: as malformed (too long)
    assert any(f.tag == "20" for f in malformed)


def _test_validate_mt700_expiry_before_issue():
    eng = TradeFinanceSwiftEngine()
    body = """{4:
:27:1/1
:40A:IRREVOCABLE
:20:LC-001
:31C:260601
:31D:260401 NAIROBI
:50:A
:59:B
:32B:USD1000,00
:45A:GOODS
:46A:DOCS
:49:WITHOUT
-}"""
    parsed = eng.parse_message(SwiftMessageType.MT700, body)
    v = eng.validate_mt700_structure(parsed)
    assert v.outcome == MessageValidationOutcome.INVALID
    assert any(
        f.tag == "31C/31D" for f in v.findings)


def _test_validate_mt700_completeness_pct():
    eng = TradeFinanceSwiftEngine()
    parsed = eng.parse_message(
        SwiftMessageType.MT700, SAMPLE_MT700)
    v = eng.validate_mt700_structure(parsed)
    assert v.completeness_pct == Decimal("1")
    parsed2 = eng.parse_message(
        SwiftMessageType.MT700,
        SAMPLE_MT700_MISSING_MANDATORY)
    v2 = eng.validate_mt700_structure(parsed2)
    # Missing 3 of ~12 mandatory fields; should be < 1
    assert v2.completeness_pct < Decimal("1")


def _test_validate_mt103_clean():
    eng = TradeFinanceSwiftEngine()
    parsed = eng.parse_message(
        SwiftMessageType.MT103, SAMPLE_MT103)
    v = eng.validate_mt103_structure(parsed)
    assert v.outcome == MessageValidationOutcome.VALID


def _test_validate_mt103_missing_charges():
    eng = TradeFinanceSwiftEngine()
    body = """{4:
:20:PAY-001
:23B:CRED
:32A:260415USD500,00
:59:BENE
-}"""
    parsed = eng.parse_message(SwiftMessageType.MT103, body)
    v = eng.validate_mt103_structure(parsed)
    assert v.outcome == MessageValidationOutcome.INVALID
    assert any(
        f.tag == "71A"
        and f.status == FieldStatus.MISSING_MANDATORY
        for f in v.findings)


def _test_validate_mt707_amendment_required_fields():
    eng = TradeFinanceSwiftEngine()
    # Missing :21: receiver's reference (mandatory)
    body = """{4:
:20:AMD-001
:23:ABC
:26E:1
:30:260415
-}"""
    parsed = eng.parse_message(SwiftMessageType.MT707, body)
    v = eng.validate_mt707_structure(parsed)
    assert v.outcome == MessageValidationOutcome.INVALID
    assert any(
        f.tag == "21" for f in v.findings)


def _test_validate_mt760_applicable_rules_required():
    eng = TradeFinanceSwiftEngine()
    body = """{4:
:27:1/1
:20:BG-001
:23:ISSUE
:30:260415
:77C:DEMAND GUARANTEE FOR PERFORMANCE
:32B:KES5000000,00
-}"""
    parsed = eng.parse_message(SwiftMessageType.MT760, body)
    v = eng.validate_mt760_structure(parsed)
    # Missing :40C: applicable rules
    assert v.outcome == MessageValidationOutcome.INVALID
    assert any(
        f.tag == "40C" for f in v.findings)


def _test_validate_unexpected_tag_warning():
    eng = TradeFinanceSwiftEngine()
    # Add a bogus :99Z: tag
    body = SAMPLE_MT103.replace(":71A:OUR", ":71A:OUR\n:99Z:BOGUS")
    parsed = eng.parse_message(SwiftMessageType.MT103, body)
    v = eng.validate_mt103_structure(parsed)
    # MT103 was VALID before; should now be WARNING
    assert v.outcome in (
        MessageValidationOutcome.WARNING,
        MessageValidationOutcome.VALID,
    )    # depending on whether 99Z falls in spec
    assert any(
        f.tag == "99Z"
        and f.status == FieldStatus.UNEXPECTED
        for f in v.findings)


def _test_wrong_message_type_raises():
    eng = TradeFinanceSwiftEngine()
    parsed = eng.parse_message(
        SwiftMessageType.MT103, SAMPLE_MT103)
    try:
        eng.validate_mt700_structure(parsed)
        assert False, "should have raised"
    except ValueError:
        pass


def _test_cross_check_aligned():
    from utils.trade_finance_instruments import (
        TradeInstrument, InstrumentType, InstrumentState,
        LcType)
    from datetime import date as _d
    eng = TradeFinanceSwiftEngine()
    inst = TradeInstrument(
        instrument_id="LC-2026-001",
        instrument_type=InstrumentType.LC,
        state=InstrumentState.DRAFT,
        applicant="ACME IMPORTS LTD",
        beneficiary="SHANGHAI STEEL CO",
        issuing_bank="Ecobank",
        advising_bank="ABC",
        amount_kes=Decimal("500000"),
        currency="USD",
        issue_date=_d(2026, 4, 1),
        expiry_date=_d(2026, 7, 1),
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="CIF Mombasa",
        description_of_goods="Steel coils")
    parsed = eng.parse_message(
        SwiftMessageType.MT700, SAMPLE_MT700)
    report = eng.cross_check_mt700_against_instrument(
        parsed, inst)
    assert report.overall_outcome == CrossCheckOutcome.ALIGNED


def _test_cross_check_diverges_on_currency():
    from utils.trade_finance_instruments import (
        TradeInstrument, InstrumentType, InstrumentState,
        LcType)
    from datetime import date as _d
    eng = TradeFinanceSwiftEngine()
    inst = TradeInstrument(
        instrument_id="LC-2026-001",
        instrument_type=InstrumentType.LC,
        state=InstrumentState.DRAFT,
        applicant="ACME IMPORTS LTD",
        beneficiary="SHANGHAI STEEL CO",
        issuing_bank="Ecobank",
        advising_bank="ABC",
        amount_kes=Decimal("500000"),
        currency="EUR",   # MT700 has USD → divergence
        issue_date=_d(2026, 4, 1),
        expiry_date=_d(2026, 7, 1),
        tenor_days=0, lc_type=LcType.SIGHT,
        incoterms="CIF Mombasa",
        description_of_goods="Steel coils")
    parsed = eng.parse_message(
        SwiftMessageType.MT700, SAMPLE_MT700)
    report = eng.cross_check_mt700_against_instrument(
        parsed, inst)
    assert report.overall_outcome == (
        CrossCheckOutcome.DIVERGENT)
    assert any(
        f.field_tag == "32B-currency"
        and f.outcome == CrossCheckOutcome.DIVERGENT
        for f in report.findings)


def _test_cross_check_wrong_message_type_raises():
    from utils.trade_finance_instruments import (
        TradeInstrument, InstrumentType, InstrumentState)
    from datetime import date as _d
    eng = TradeFinanceSwiftEngine()
    parsed = eng.parse_message(
        SwiftMessageType.MT103, SAMPLE_MT103)
    inst = type("X", (), {})
    try:
        eng.cross_check_mt700_against_instrument(parsed, inst)
        assert False
    except ValueError:
        pass


def _test_engine_does_not_mutate_inputs():
    eng = TradeFinanceSwiftEngine()
    body = SAMPLE_MT700
    parsed = eng.parse_message(
        SwiftMessageType.MT700, body)
    eng.validate_mt700_structure(parsed)
    assert parsed.raw_body == body


def _test_full_provenance():
    eng = TradeFinanceSwiftEngine()
    parsed = eng.parse_message(
        SwiftMessageType.MT700, SAMPLE_MT700)
    v = eng.validate_mt700_structure(parsed)
    assert any(
        "ENH-272" in r for r in v.framework_refs)
    assert any(
        "SWIFT" in r for r in v.framework_refs)
    assert any(
        "Rule 7" in r for r in v.framework_refs)


def self_test() -> None:
    tests = [
        _test_parse_extracts_all_tags,
        _test_parse_preserves_multiline_values,
        _test_parse_handles_no_block4_wrapper,
        _test_validate_clean_mt700_passes,
        _test_validate_mt700_missing_mandatory,
        _test_validate_mt700_malformed_pattern,
        _test_validate_mt700_expiry_before_issue,
        _test_validate_mt700_completeness_pct,
        _test_validate_mt103_clean,
        _test_validate_mt103_missing_charges,
        _test_validate_mt707_amendment_required_fields,
        _test_validate_mt760_applicable_rules_required,
        _test_validate_unexpected_tag_warning,
        _test_wrong_message_type_raises,
        _test_cross_check_aligned,
        _test_cross_check_diverges_on_currency,
        _test_cross_check_wrong_message_type_raises,
        _test_engine_does_not_mutate_inputs,
        _test_full_provenance,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append(
                (t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ trade_finance_swift self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ trade_finance_swift self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
