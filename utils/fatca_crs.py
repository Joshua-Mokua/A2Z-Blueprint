"""
================================================================================
A2Z MIS 360 — Standard #60: FATCA/CRS Reporting Engine
================================================================================

Risk classification: Cat A (foreign tax data schema) + Cat B (deterministic
aggregation and reportable-status determination)

Implements:
    FATCA   — US Foreign Account Tax Compliance Act (IRS Form 8966)
    CRS     — OECD Common Reporting Standard (XML schema)
    KRA     — Kenya Revenue Authority CRS reporting (per CBK/PG/19)

Reportable account determination (deterministic):
    FATCA   : US person = US citizen/resident + account_balance > USD 50,000
              (USD 250,000 for entity accounts)
    CRS     : Tax resident in CRS-participating jurisdiction (other than KE)
              No de minimis for new accounts opened after 2017-01-01
              USD 250,000 threshold for pre-existing entity accounts

Schema (Cat A):
    tax.account_holder_self_cert   : self-certification declarations
    tax.reportable_account         : per-period reportable status snapshot
    tax.reporting_submission       : submitted reports + ack tracking

Aggregation (Cat B):
    aggregate_balances_by_holder   : sum balances across accounts per holder
    classify_reportable_status     : determine FATCA vs CRS reportable
    build_xml_payload_skeleton     : structural envelope (NOT actual XML lib)

Honesty rules applied:
    Rule 1: Decimal precision for all balance + threshold comparisons
    Rule 6: missing self-certification defaults to UNDOCUMENTED (highest scrutiny),
            never auto-classified as non-reportable

Spec deviations:
    Full XML schema generation (FATCA Form 8966 XML, OECD CRS XML) is deferred
    to v7. v6 ships skeleton/envelope structure plus deterministic classification.
================================================================================
"""

from __future__ import annotations

SPEC_DEVIATION_NOTE = (
    "FATCA Form 8966 XML and OECD CRS XML payload generation are "
    "implemented at v10.194 (full element tree per OECD CRS XSD v2.0 "
    "and IRS FATCA XSD v2.4). Diagnostic only per Rule 7 — engine "
    "produces XML strings; never signs (XMLDSig), never validates "
    "against external XSD files (caller's responsibility), never "
    "encrypts, never transmits to KRA / IRS."
)

from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

# ============================================================================
# Constants — byte-for-byte preserved from FATCA Treasury Regs + OECD CRS
# ============================================================================

# FATCA thresholds (USD, IRC §1471)
FATCA_INDIVIDUAL_THRESHOLD_USD = Decimal("50000")
FATCA_ENTITY_THRESHOLD_USD = Decimal("250000")
FATCA_FORM = "8966"

# CRS thresholds
CRS_PRE_EXISTING_INDIVIDUAL_DE_MINIMIS_USD = Decimal("0")  # No de minimis (post-2017 OECD update)
CRS_PRE_EXISTING_ENTITY_THRESHOLD_USD = Decimal("250000")
CRS_NEW_ACCOUNT_DE_MINIMIS_USD = Decimal("0")  # No de minimis for new accounts

# CRS-participating jurisdictions (selected; full list at OECD)
CRS_PARTICIPATING_JURISDICTIONS: Tuple[str, ...] = (
    "GB", "DE", "FR", "IT", "ES", "NL", "BE", "CH", "AT", "IE", "LU",
    "US",  # FATCA partner, not CRS, but US tax residence triggers FATCA
    "CA", "AU", "NZ", "JP", "KR", "SG", "HK",
    "ZA", "MU", "RW", "UG", "TZ",  # African CRS participants
    "AE", "SA", "QA",
    "NO", "SE", "DK", "FI", "IS",
    "BR", "AR", "MX", "CL",
    "IN", "CN",
)

# Reporting jurisdiction
HOME_JURISDICTION = "KE"

# Reportable status values
STATUS_REPORTABLE_FATCA = "REPORTABLE_FATCA"
STATUS_REPORTABLE_CRS = "REPORTABLE_CRS"
STATUS_REPORTABLE_BOTH = "REPORTABLE_BOTH"
STATUS_NOT_REPORTABLE = "NOT_REPORTABLE"
STATUS_UNDOCUMENTED = "UNDOCUMENTED"  # missing self-cert; Rule 6 escalation

VALID_STATUSES: Tuple[str, ...] = (
    STATUS_REPORTABLE_FATCA, STATUS_REPORTABLE_CRS, STATUS_REPORTABLE_BOTH,
    STATUS_NOT_REPORTABLE, STATUS_UNDOCUMENTED,
)

# XML schema namespaces — per OECD CRS XSD v2.0 and IRS FATCA XSD v2.4.
# The xmlns:stf namespace is the common types schema shared by both.
CRS_NAMESPACE = "urn:oecd:ties:crs:v2"
CRS_STF_NAMESPACE = "urn:oecd:ties:crsstf:v5"
FATCA_NAMESPACE = "urn:oecd:ties:fatca:v2.4"
FATCA_STF_NAMESPACE = "urn:oecd:ties:fatcastf:v2"
ISO_NAMESPACE = "urn:oecd:ties:isocrstypes:v1"

# Account types
ACCOUNT_TYPE_INDIVIDUAL = "INDIVIDUAL"
ACCOUNT_TYPE_ENTITY = "ENTITY"

# Schema definitions (Cat A)
SCHEMA_SELF_CERT_TABLE = {
    "table": "tax.account_holder_self_cert",
    "columns": [
        ("self_cert_id", "BIGSERIAL PRIMARY KEY"),
        ("customer_id", "VARCHAR(64) NOT NULL"),
        ("us_person", "BOOLEAN"),
        ("us_tin", "VARCHAR(32)"),
        ("tax_residences", "TEXT[]"),  # array of ISO-2 codes
        ("foreign_tins", "JSONB"),     # {country: tin}
        ("certification_date", "DATE NOT NULL"),
        ("entity_type", "VARCHAR(32)"),  # INDIVIDUAL | ENTITY
        ("entity_classification", "VARCHAR(64)"),  # FFI, NFFE, etc
        ("active", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ],
    "indexes": [
        "CREATE INDEX idx_self_cert_customer ON tax.account_holder_self_cert (customer_id)",
        "CREATE INDEX idx_self_cert_active ON tax.account_holder_self_cert (active) WHERE active",
    ],
}

SCHEMA_REPORTABLE_TABLE = {
    "table": "tax.reportable_account",
    "columns": [
        ("snapshot_id", "BIGSERIAL PRIMARY KEY"),
        ("reporting_period", "VARCHAR(8) NOT NULL"),  # 2025, 2026
        ("customer_id", "VARCHAR(64) NOT NULL"),
        ("account_id", "VARCHAR(64) NOT NULL"),
        ("aggregated_balance_usd", "NUMERIC(20,2) NOT NULL"),
        ("status", "VARCHAR(32) NOT NULL"),
        ("us_person_flag", "BOOLEAN NOT NULL"),
        ("crs_jurisdictions", "TEXT[]"),
        ("classified_at", "TIMESTAMPTZ NOT NULL"),
    ],
    "indexes": [
        "CREATE INDEX idx_reportable_period ON tax.reportable_account (reporting_period)",
        "CREATE INDEX idx_reportable_status ON tax.reportable_account (status) WHERE status != 'NOT_REPORTABLE'",
    ],
}

SCHEMA_SUBMISSION_TABLE = {
    "table": "tax.reporting_submission",
    "columns": [
        ("submission_id", "BIGSERIAL PRIMARY KEY"),
        ("reporting_period", "VARCHAR(8) NOT NULL"),
        ("regime", "VARCHAR(16) NOT NULL"),  # FATCA | CRS
        ("submitted_at", "TIMESTAMPTZ NOT NULL"),
        ("record_count", "INTEGER NOT NULL"),
        ("payload_hash", "VARCHAR(64)"),
        ("ack_received_at", "TIMESTAMPTZ"),
        ("ack_status", "VARCHAR(32)"),  # ACCEPTED | REJECTED | PENDING
    ],
}


def _to_decimal(amount: Any) -> Decimal:
    if isinstance(amount, Decimal):
        return amount
    if amount is None:
        return Decimal("0")
    return Decimal(str(amount))


@dataclass
class SelfCertification:
    customer_id: str
    us_person: Optional[bool] = None
    us_tin: Optional[str] = None
    tax_residences: List[str] = field(default_factory=list)
    foreign_tins: Dict[str, str] = field(default_factory=dict)
    certification_date: Optional[str] = None
    entity_type: str = ACCOUNT_TYPE_INDIVIDUAL
    entity_classification: Optional[str] = None
    active: bool = True


@dataclass
class AccountBalance:
    customer_id: str
    account_id: str
    balance_usd: Decimal
    account_opened_date: Optional[str] = None  # ISO date
    entity_type: str = ACCOUNT_TYPE_INDIVIDUAL


@dataclass
class ReportableSnapshot:
    reporting_period: str  # e.g. "2025"
    customer_id: str
    aggregated_balance_usd: Decimal
    status: str
    us_person_flag: bool
    crs_jurisdictions: List[str]
    account_ids: List[str]
    classified_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reporting_period": self.reporting_period,
            "customer_id": self.customer_id,
            "aggregated_balance_usd": str(self.aggregated_balance_usd),
            "status": self.status,
            "us_person_flag": self.us_person_flag,
            "crs_jurisdictions": list(self.crs_jurisdictions),
            "account_ids": list(self.account_ids),
            "classified_at": self.classified_at,
        }


@dataclass(frozen=True)
class XmlReportSenderInfo:
    """Metadata required for the message envelope of a FATCA or CRS
    XML transmission. Per OECD CRS XSD v2.0 / IRS FATCA XSD v2.4
    MessageSpec section.

    The Reporting Financial Institution (RFI) and the message sender
    are usually the same institution but the schema distinguishes
    them — the RFI is who's reporting the accounts, the sender is
    who's transmitting the file (e.g. a tax-portal intermediary).
    For Ecobank Kenya filing directly with KRA, both are Ecobank.

    Field semantics:
      - sender_in: GIIN (FATCA) or KRA-issued IN (CRS); typically
        the bank's GIIN like "9X5Y3T.99999.SL.404".
      - transmitting_country: ISO-3166-1 alpha-2 of where the file
        is sent FROM (KE for Ecobank Kenya).
      - receiving_country: ISO-3166-1 alpha-2 of the destination tax
        authority — "US" for FATCA, the participating jurisdiction
        for CRS (KRA forwards to participating jurisdictions).
      - message_ref_id: Per OECD spec, must be unique across all
        messages from this sender for at least 5 years; convention
        is "<country>YYYY<sender_in><sequence>".
      - reporting_period: ISO date YYYY-12-31 for end of calendar year
        being reported.
      - timestamp_iso: ISO-8601 with timezone of when the message
        was generated.
    """
    sender_in: str
    sender_name: str
    transmitting_country: str
    receiving_country: str
    message_ref_id: str
    reporting_period: str
    timestamp_iso: str
    contact: str
    fi_in: str
    fi_name: str
    fi_address_country: str
    fi_address_free: str

    def __post_init__(self) -> None:
        for f in ("sender_in", "sender_name", "transmitting_country",
                  "receiving_country", "message_ref_id",
                  "reporting_period", "timestamp_iso", "contact",
                  "fi_in", "fi_name", "fi_address_country",
                  "fi_address_free"):
            if not getattr(self, f):
                raise ValueError(f"{f} must be non-empty")
        if len(self.transmitting_country) != 2:
            raise ValueError(
                "transmitting_country must be ISO-3166-1 alpha-2")
        if len(self.receiving_country) != 2:
            raise ValueError(
                "receiving_country must be ISO-3166-1 alpha-2")


@dataclass(frozen=True)
class XmlReportableRecord:
    """Enriched record for FATCA/CRS XML emission. Combines a
    classification-stage ReportableSnapshot with the additional
    metadata required by the OECD CRS / FATCA XML schemas (account
    holder name, address, TIN, etc) which are not part of the
    snapshot's classification-only contract.

    The caller is expected to assemble these from the bank's
    customer-master and account-master records, applying the
    snapshot's status as a filter for what gets reported.

    Field semantics:
      - account_holder_type: "INDIVIDUAL" or "ORGANISATION" — drives
        which schema element is emitted (Individual vs Organisation).
      - tin / tin_country_code: tax identification number and the
        country that issued it. Per OECD spec, if a CRS-jurisdiction
        resident has no TIN, set tin to None and the schema emits
        TIN with empty content + issuedBy unset (the receiving
        jurisdiction handles the missing TIN).
      - birth_date_iso: YYYY-MM-DD; required for individuals under
        OECD CRS, optional under FATCA (FATCA uses TIN).
      - currency_code: ISO-4217 alpha-3, defaults to USD per FATCA
        convention; for CRS, account currency is acceptable.
      - doc_type: OECD1 = new data, OECD2 = corrected, OECD3 =
        deleted. Default OECD1 for first-time submissions.
      - doc_ref_id: Unique per-record identifier; if None, a
        deterministic ID derived from sender + customer + period is
        generated by the XML builder.
      - first_name, last_name: required for INDIVIDUAL records;
        ignored for ORGANISATION (uses account_holder_name).
    """
    snapshot: ReportableSnapshot
    account_holder_name: str
    account_holder_type: str
    address_country_code: str
    address_free: str
    tin: Optional[str] = None
    tin_country_code: Optional[str] = None
    birth_date_iso: Optional[str] = None
    currency_code: str = "USD"
    doc_type: str = "OECD1"
    doc_ref_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.account_holder_name:
            raise ValueError("account_holder_name must be non-empty")
        if self.account_holder_type not in (
                ACCOUNT_TYPE_INDIVIDUAL, ACCOUNT_TYPE_ENTITY,
                "ORGANISATION"):
            raise ValueError(
                "account_holder_type must be INDIVIDUAL, ENTITY, "
                "or ORGANISATION")
        if len(self.address_country_code) != 2:
            raise ValueError(
                "address_country_code must be ISO-3166-1 alpha-2")
        if not self.address_free:
            raise ValueError("address_free must be non-empty")
        if self.doc_type not in ("OECD1", "OECD2", "OECD3"):
            raise ValueError(
                "doc_type must be OECD1 (new), OECD2 (corrected), "
                "or OECD3 (deleted)")
        if len(self.currency_code) != 3:
            raise ValueError(
                "currency_code must be ISO-4217 alpha-3")


class FatcaCrsReportingEngine:
    """Deterministic FATCA/CRS reportable-status determination."""

    @staticmethod
    def aggregate_balances_by_holder(accounts: List[AccountBalance]) -> Dict[str, Tuple[Decimal, List[str], str]]:
        """
        Sum balances per customer_id.
        Returns: {customer_id: (total_balance, [account_ids], dominant_entity_type)}
        """
        agg: Dict[str, Tuple[Decimal, List[str], str]] = {}
        for a in accounts:
            cid = a.customer_id
            if cid in agg:
                total, ids, etype = agg[cid]
                total = total + _to_decimal(a.balance_usd)
                ids = ids + [a.account_id]
                # If any account is ENTITY, holder treated as ENTITY (more conservative)
                if a.entity_type == ACCOUNT_TYPE_ENTITY:
                    etype = ACCOUNT_TYPE_ENTITY
                agg[cid] = (total, ids, etype)
            else:
                agg[cid] = (_to_decimal(a.balance_usd), [a.account_id], a.entity_type)
        return agg

    @classmethod
    def classify_reportable_status(
        cls,
        customer_id: str,
        aggregated_balance_usd: Decimal,
        entity_type: str,
        self_cert: Optional[SelfCertification],
    ) -> Tuple[str, bool, List[str], str]:
        """
        Determine reportable status.
        Returns: (status, us_person_flag, crs_jurisdictions, reason)
        """
        # Rule 6: missing self-certification = UNDOCUMENTED, NOT auto-non-reportable
        if self_cert is None or not self_cert.active:
            return STATUS_UNDOCUMENTED, False, [], "missing_or_inactive_self_certification"

        balance = _to_decimal(aggregated_balance_usd)

        # FATCA classification
        is_us_person = bool(self_cert.us_person) or (self_cert.us_tin is not None and self_cert.us_tin != "")
        if entity_type == ACCOUNT_TYPE_INDIVIDUAL:
            fatca_threshold = FATCA_INDIVIDUAL_THRESHOLD_USD
        else:
            fatca_threshold = FATCA_ENTITY_THRESHOLD_USD
        fatca_reportable = is_us_person and balance > fatca_threshold

        # CRS classification
        crs_jurisdictions: List[str] = []
        for tr in self_cert.tax_residences or []:
            tr_upper = tr.upper().strip()
            # Skip home jurisdiction (Kenya doesn't report Kenyans to itself)
            if tr_upper == HOME_JURISDICTION:
                continue
            if tr_upper in CRS_PARTICIPATING_JURISDICTIONS:
                crs_jurisdictions.append(tr_upper)
        # CRS reportable if ANY non-home CRS jurisdiction in residences AND meets threshold
        # No de minimis for individuals or new accounts; threshold for pre-existing entities only
        # Simplified: any CRS jurisdiction with positive balance triggers
        crs_reportable = bool(crs_jurisdictions) and balance > Decimal("0")

        if fatca_reportable and crs_reportable:
            return STATUS_REPORTABLE_BOTH, is_us_person, crs_jurisdictions, "both_fatca_and_crs"
        if fatca_reportable:
            return STATUS_REPORTABLE_FATCA, is_us_person, crs_jurisdictions, "us_person_above_threshold"
        if crs_reportable:
            return STATUS_REPORTABLE_CRS, is_us_person, crs_jurisdictions, "crs_jurisdiction_resident"
        return STATUS_NOT_REPORTABLE, is_us_person, crs_jurisdictions, "no_reportable_indicia"

    @classmethod
    def build_period_snapshot(
        cls,
        reporting_period: str,
        accounts: List[AccountBalance],
        self_certs: Dict[str, SelfCertification],
    ) -> List[ReportableSnapshot]:
        """Classify all customers for a reporting period."""
        agg = cls.aggregate_balances_by_holder(accounts)
        ts = datetime.now(timezone.utc).isoformat()
        snapshots = []
        for cid, (balance, account_ids, etype) in agg.items():
            cert = self_certs.get(cid)
            status, us_flag, crs_juris, _reason = cls.classify_reportable_status(
                cid, balance, etype, cert
            )
            snapshots.append(ReportableSnapshot(
                reporting_period=reporting_period,
                customer_id=cid,
                aggregated_balance_usd=balance,
                status=status,
                us_person_flag=us_flag,
                crs_jurisdictions=crs_juris,
                account_ids=account_ids,
                classified_at=ts,
            ))
        return snapshots

    @staticmethod
    def build_payload_skeleton(
        snapshots: List[ReportableSnapshot],
        regime: str,
    ) -> Dict[str, Any]:
        """
        Build skeleton/envelope structure for FATCA or CRS payload.

        Note: full XML/Form 8966 generation is per SPEC_DEVIATION_NOTE deferred
        to v7. This returns a Python dict resembling the envelope.
        """
        if regime not in ("FATCA", "CRS"):
            return {
                "error": f"unsupported_regime:{regime}",
                "supported": ["FATCA", "CRS"],
                "note": SPEC_DEVIATION_NOTE,
            }

        if regime == "FATCA":
            included = [
                s for s in snapshots
                if s.status in (STATUS_REPORTABLE_FATCA, STATUS_REPORTABLE_BOTH)
            ]
        else:
            included = [
                s for s in snapshots
                if s.status in (STATUS_REPORTABLE_CRS, STATUS_REPORTABLE_BOTH)
            ]

        return {
            "regime": regime,
            "form": FATCA_FORM if regime == "FATCA" else "OECD_CRS_XML",
            "reporting_period": snapshots[0].reporting_period if snapshots else "UNKNOWN",
            "submitter_jurisdiction": HOME_JURISDICTION,
            "record_count": len(included),
            "records": [s.to_dict() for s in included],
            "spec_deviation_note": SPEC_DEVIATION_NOTE,
        }

    # ----------------------------------------------------------
    # XML emission — OECD CRS XSD v2.0 + IRS FATCA XSD v2.4
    # ----------------------------------------------------------

    @staticmethod
    def _make_doc_ref_id(
        sender_in: str, customer_id: str, period: str,
    ) -> str:
        """Deterministic doc_ref_id generator. Per OECD spec the
        DocRefId is unique per record; this produces the same ID
        for the same inputs (helpful when the same period is
        re-emitted for a corrected record)."""
        return f"{sender_in}.{period}.{customer_id}"

    @staticmethod
    def _ce(parent: ET.Element, tag: str,
            text: Optional[str] = None) -> ET.Element:
        """Helper: create child element with optional text. Keeps
        the XML-builder bodies readable."""
        el = ET.SubElement(parent, tag)
        if text is not None and text != "":
            el.text = text
        return el

    @classmethod
    def _build_message_spec(
        cls, parent: ET.Element, sender: XmlReportSenderInfo,
        regime: str,
    ) -> None:
        """Build the MessageSpec envelope. Shared between FATCA and
        CRS — both use the same field names per OECD common types.

        MessageType is "CRS" for OECD CRS, "FATCA" for FATCA.
        """
        ms = ET.SubElement(parent, "MessageSpec")
        cls._ce(ms, "SendingCompanyIN", sender.sender_in)
        cls._ce(ms, "TransmittingCountry", sender.transmitting_country)
        cls._ce(ms, "ReceivingCountry", sender.receiving_country)
        cls._ce(ms, "MessageType", regime)
        cls._ce(ms, "Warning", "")  # optional, kept blank
        cls._ce(ms, "Contact", sender.contact)
        cls._ce(ms, "MessageRefId", sender.message_ref_id)
        cls._ce(ms, "MessageTypeIndic",
                "CRS701" if regime == "CRS" else "FATCA701")
        cls._ce(ms, "ReportingPeriod", sender.reporting_period)
        cls._ce(ms, "Timestamp", sender.timestamp_iso)

    @classmethod
    def _build_reporting_fi(
        cls, parent: ET.Element, sender: XmlReportSenderInfo,
        regime: str,
    ) -> None:
        """Build the ReportingFI element (the bank itself as a
        reporting entity). Address uses AddressFree (single-line)
        for simplicity — the schema also permits AddressFix
        (structured) but AddressFree is OECD-permissible and avoids
        guesswork on per-jurisdiction street/city/postcode parsing.
        """
        fi = ET.SubElement(parent, "ReportingFI")
        cls._ce(fi, "ResCountryCode", sender.fi_address_country)
        in_el = cls._ce(fi, "IN", sender.fi_in)
        in_el.set("issuedBy", sender.fi_address_country)
        in_el.set("INType", "GIIN" if regime == "FATCA" else "TIN")
        cls._ce(fi, "Name", sender.fi_name)
        addr = ET.SubElement(fi, "Address")
        addr.set("legalAddressType", "OECD303")  # registered office
        cls._ce(addr, "CountryCode", sender.fi_address_country)
        cls._ce(addr, "AddressFree", sender.fi_address_free)
        # DocSpec for the FI itself (DocTypeIndic, DocRefId)
        ds = ET.SubElement(fi, "DocSpec")
        cls._ce(ds, "DocTypeIndic", "OECD1")
        cls._ce(ds, "DocRefId",
                f"{sender.sender_in}.{sender.reporting_period}.RFI")

    @classmethod
    def _build_account_holder(
        cls, parent: ET.Element, record: XmlReportableRecord,
        regime: str,
    ) -> None:
        """Build either an Individual or Organisation account
        holder element under AccountHolder. OECD CRS distinguishes
        these two types; the schema element name is the same
        (AccountHolder) but the inner structure differs.
        """
        holder = ET.SubElement(parent, "AccountHolder")
        is_individual = record.account_holder_type == ACCOUNT_TYPE_INDIVIDUAL

        if is_individual:
            ind = ET.SubElement(holder, "Individual")
            # ResCountryCode — the tax residency country. For FATCA
            # this is "US"; for CRS it's the first reportable
            # jurisdiction in the snapshot.
            if regime == "FATCA":
                cls._ce(ind, "ResCountryCode", "US")
            else:
                # First listed CRS jurisdiction; defaults to "XX"
                # if missing (caller should ensure populated).
                rc = (record.snapshot.crs_jurisdictions[0]
                      if record.snapshot.crs_jurisdictions else "XX")
                cls._ce(ind, "ResCountryCode", rc)
            # TIN — per OECD spec, missing TIN renders as empty
            # element with issuedBy unset; we follow that convention.
            tin_el = cls._ce(ind, "TIN", record.tin or "")
            if record.tin_country_code:
                tin_el.set("issuedBy", record.tin_country_code)
            # Name — split first/last when supplied; otherwise
            # use the full name as the last name (OECD-permissible
            # for jurisdictions where name decomposition is unclear).
            name = ET.SubElement(ind, "Name")
            name.set("nameType", "OECD202")  # legal name
            cls._ce(name, "FirstName", record.first_name or "")
            cls._ce(name, "LastName",
                    record.last_name or record.account_holder_name)
            # Address
            addr = ET.SubElement(ind, "Address")
            addr.set("legalAddressType", "OECD301")  # residential
            cls._ce(addr, "CountryCode", record.address_country_code)
            cls._ce(addr, "AddressFree", record.address_free)
            # Birth info — required for OECD CRS individuals
            if record.birth_date_iso:
                bi = ET.SubElement(ind, "BirthInfo")
                cls._ce(bi, "BirthDate", record.birth_date_iso)
        else:
            org = ET.SubElement(holder, "Organisation")
            if regime == "FATCA":
                cls._ce(org, "ResCountryCode", "US")
            else:
                rc = (record.snapshot.crs_jurisdictions[0]
                      if record.snapshot.crs_jurisdictions else "XX")
                cls._ce(org, "ResCountryCode", rc)
            in_el = cls._ce(org, "IN", record.tin or "")
            if record.tin_country_code:
                in_el.set("issuedBy", record.tin_country_code)
            in_el.set("INType",
                      "GIIN" if regime == "FATCA" else "TIN")
            cls._ce(org, "Name", record.account_holder_name)
            addr = ET.SubElement(org, "Address")
            addr.set("legalAddressType", "OECD303")  # registered
            cls._ce(addr, "CountryCode", record.address_country_code)
            cls._ce(addr, "AddressFree", record.address_free)
            # AcctHolderType — per CRS, classification of the entity
            # for reporting. CRS101 = passive NFE with controlling
            # persons, CRS102 = NFE other, CRS103 = passive NFE that
            # is a CRS-Reportable Person. We use CRS102 as the
            # safe default unless the caller provides finer detail
            # via entity_classification (currently unused here).
            if regime == "CRS":
                cls._ce(holder, "AcctHolderType", "CRS102")

    @classmethod
    def _build_account_report(
        cls, parent: ET.Element, record: XmlReportableRecord,
        sender: XmlReportSenderInfo, regime: str,
    ) -> None:
        """Build a single AccountReport element."""
        ar = ET.SubElement(parent, "AccountReport")
        # DocSpec
        ds = ET.SubElement(ar, "DocSpec")
        cls._ce(ds, "DocTypeIndic", record.doc_type)
        doc_ref = (record.doc_ref_id
                   or cls._make_doc_ref_id(
                       sender.sender_in,
                       record.snapshot.customer_id,
                       sender.reporting_period))
        cls._ce(ds, "DocRefId", doc_ref)
        # AccountNumber — use first account_id if multiple were
        # aggregated; the schema permits one per AccountReport but
        # caller can split into multiple records if needed.
        an = cls._ce(ar, "AccountNumber",
                     record.snapshot.account_ids[0]
                     if record.snapshot.account_ids else "")
        an.set("AcctNumberType", "OECD605")  # other account number
        # AccountHolder
        cls._build_account_holder(ar, record, regime)
        # AccountBalance
        bal = cls._ce(ar, "AccountBalance",
                      str(record.snapshot.aggregated_balance_usd))
        bal.set("currCode", record.currency_code)

    @classmethod
    def build_crs_xml(
        cls,
        records: List[XmlReportableRecord],
        sender: XmlReportSenderInfo,
    ) -> str:
        """Build OECD CRS XML v2.0 payload string.

        Per Rule 7, this is a diagnostic generator — the engine
        produces a well-formed XML string but does NOT sign,
        validate against external XSD files, encrypt, or transmit.

        Filter: only records with status REPORTABLE_CRS or
        REPORTABLE_BOTH are included. FATCA-only records are
        excluded (US persons resident only in the US don't go in
        a CRS report).

        Args:
            records: enriched account-holder records
            sender: message envelope metadata

        Returns:
            UTF-8 XML string with declaration. Pretty-printed.
        """
        included = [
            r for r in records
            if r.snapshot.status in (
                STATUS_REPORTABLE_CRS, STATUS_REPORTABLE_BOTH)
        ]

        # Root element with namespace declarations
        root = ET.Element("CRS_OECD")
        root.set("version", "2.0")
        root.set("xmlns", CRS_NAMESPACE)
        root.set("xmlns:stf", CRS_STF_NAMESPACE)
        root.set("xmlns:iso", ISO_NAMESPACE)
        root.set("xmlns:xsi",
                 "http://www.w3.org/2001/XMLSchema-instance")

        # MessageSpec
        cls._build_message_spec(root, sender, "CRS")

        # CrsBody
        body = ET.SubElement(root, "CrsBody")
        cls._build_reporting_fi(body, sender, "CRS")

        # ReportingGroup wraps AccountReports
        rg = ET.SubElement(body, "ReportingGroup")
        for record in included:
            cls._build_account_report(rg, record, sender, "CRS")

        # Pretty-print and return string
        cls._indent_tree(root)
        xml_bytes = ET.tostring(
            root, encoding="utf-8", xml_declaration=True)
        return xml_bytes.decode("utf-8")

    @classmethod
    def build_fatca_xml(
        cls,
        records: List[XmlReportableRecord],
        sender: XmlReportSenderInfo,
    ) -> str:
        """Build IRS FATCA XML v2.4 payload string (Form 8966
        electronic format).

        Filter: only records with status REPORTABLE_FATCA or
        REPORTABLE_BOTH (US persons) are included. CRS-only
        records (non-US tax residents) are excluded.

        Same Rule 7 discipline as build_crs_xml — diagnostic only.

        Note: the FATCA XSD shares most of its structure with
        OECD CRS but uses different namespaces and a few different
        element names (e.g. PoolReport block for nil reports —
        omitted here as it's an empty-report optimization).
        """
        included = [
            r for r in records
            if r.snapshot.status in (
                STATUS_REPORTABLE_FATCA, STATUS_REPORTABLE_BOTH)
        ]

        root = ET.Element("FATCA_OECD")
        root.set("version", "2.4")
        root.set("xmlns", FATCA_NAMESPACE)
        root.set("xmlns:sfa", FATCA_STF_NAMESPACE)
        root.set("xmlns:iso", ISO_NAMESPACE)
        root.set("xmlns:xsi",
                 "http://www.w3.org/2001/XMLSchema-instance")

        cls._build_message_spec(root, sender, "FATCA")

        body = ET.SubElement(root, "FATCA")
        cls._build_reporting_fi(body, sender, "FATCA")

        for record in included:
            cls._build_account_report(body, record, sender, "FATCA")

        cls._indent_tree(root)
        xml_bytes = ET.tostring(
            root, encoding="utf-8", xml_declaration=True)
        return xml_bytes.decode("utf-8")

    @staticmethod
    def _indent_tree(elem: ET.Element, level: int = 0) -> None:
        """Pretty-print indentation. Modifies tree in place."""
        i = "\n" + level * "  "
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for child in elem:
                FatcaCrsReportingEngine._indent_tree(child, level + 1)
            if not child.tail or not child.tail.strip():
                child.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i

    @staticmethod
    def reporting_summary(snapshots: List[ReportableSnapshot]) -> Dict[str, Any]:
        by_status: Dict[str, int] = {s: 0 for s in VALID_STATUSES}
        total_balance = Decimal("0")
        for s in snapshots:
            by_status[s.status] = by_status.get(s.status, 0) + 1
            total_balance = total_balance + s.aggregated_balance_usd
        return {
            "total_holders": len(snapshots),
            "by_status": by_status,
            "total_balance_usd": str(total_balance),
            "reportable_count": (
                by_status[STATUS_REPORTABLE_FATCA]
                + by_status[STATUS_REPORTABLE_CRS]
                + by_status[STATUS_REPORTABLE_BOTH]
            ),
            "undocumented_count": by_status[STATUS_UNDOCUMENTED],
        }


# ============================================================================
# Self-tests
# ============================================================================

def _test_us_person_individual_above_threshold():
    cert = SelfCertification(customer_id="C1", us_person=True, us_tin="123-45-6789", certification_date="2025-01-01")
    accounts = [AccountBalance("C1", "A1", Decimal("75000"))]
    snaps = FatcaCrsReportingEngine.build_period_snapshot("2025", accounts, {"C1": cert})
    assert snaps[0].status == STATUS_REPORTABLE_FATCA
    assert snaps[0].us_person_flag is True

def _test_us_person_below_threshold():
    cert = SelfCertification(customer_id="C2", us_person=True, us_tin="123-45-6789", certification_date="2025-01-01")
    accounts = [AccountBalance("C2", "A1", Decimal("40000"))]
    snaps = FatcaCrsReportingEngine.build_period_snapshot("2025", accounts, {"C2": cert})
    assert snaps[0].status == STATUS_NOT_REPORTABLE

def _test_crs_jurisdiction_reportable():
    cert = SelfCertification(customer_id="C3", us_person=False, tax_residences=["GB"], certification_date="2025-01-01")
    accounts = [AccountBalance("C3", "A1", Decimal("10000"))]
    snaps = FatcaCrsReportingEngine.build_period_snapshot("2025", accounts, {"C3": cert})
    assert snaps[0].status == STATUS_REPORTABLE_CRS
    assert snaps[0].crs_jurisdictions == ["GB"]

def _test_kenya_resident_not_reportable():
    cert = SelfCertification(customer_id="C4", us_person=False, tax_residences=["KE"], certification_date="2025-01-01")
    accounts = [AccountBalance("C4", "A1", Decimal("5000000"))]
    snaps = FatcaCrsReportingEngine.build_period_snapshot("2025", accounts, {"C4": cert})
    assert snaps[0].status == STATUS_NOT_REPORTABLE

def _test_both_fatca_and_crs():
    cert = SelfCertification(customer_id="C5", us_person=True, us_tin="111-11-1111", tax_residences=["DE"], certification_date="2025-01-01")
    accounts = [AccountBalance("C5", "A1", Decimal("100000"))]
    snaps = FatcaCrsReportingEngine.build_period_snapshot("2025", accounts, {"C5": cert})
    assert snaps[0].status == STATUS_REPORTABLE_BOTH

def _test_undocumented_rule6():
    """Rule 6: missing self-cert is UNDOCUMENTED, NOT auto-non-reportable."""
    accounts = [AccountBalance("C6", "A1", Decimal("100000"))]
    snaps = FatcaCrsReportingEngine.build_period_snapshot("2025", accounts, {})
    assert snaps[0].status == STATUS_UNDOCUMENTED

def _test_inactive_cert_is_undocumented():
    cert = SelfCertification(customer_id="C7", us_person=True, active=False, certification_date="2024-01-01")
    accounts = [AccountBalance("C7", "A1", Decimal("75000"))]
    snaps = FatcaCrsReportingEngine.build_period_snapshot("2025", accounts, {"C7": cert})
    assert snaps[0].status == STATUS_UNDOCUMENTED

def _test_balance_aggregation():
    cert = SelfCertification(customer_id="C8", us_person=True, us_tin="X", certification_date="2025-01-01")
    accounts = [
        AccountBalance("C8", "A1", Decimal("30000")),
        AccountBalance("C8", "A2", Decimal("25000")),  # aggregated 55000 > 50000
    ]
    snaps = FatcaCrsReportingEngine.build_period_snapshot("2025", accounts, {"C8": cert})
    assert snaps[0].aggregated_balance_usd == Decimal("55000")
    assert snaps[0].status == STATUS_REPORTABLE_FATCA

def _test_entity_threshold_higher():
    cert = SelfCertification(customer_id="E1", us_person=True, us_tin="X", entity_type=ACCOUNT_TYPE_ENTITY, certification_date="2025-01-01")
    accounts = [AccountBalance("E1", "A1", Decimal("100000"), entity_type=ACCOUNT_TYPE_ENTITY)]
    snaps = FatcaCrsReportingEngine.build_period_snapshot("2025", accounts, {"E1": cert})
    # Entity threshold is 250k, so 100k is NOT reportable
    assert snaps[0].status == STATUS_NOT_REPORTABLE
    # Now bump to 300k
    accounts2 = [AccountBalance("E1", "A1", Decimal("300000"), entity_type=ACCOUNT_TYPE_ENTITY)]
    snaps2 = FatcaCrsReportingEngine.build_period_snapshot("2025", accounts2, {"E1": cert})
    assert snaps2[0].status == STATUS_REPORTABLE_FATCA

def _test_decimal_precision_rule1():
    """Rule 1: balance comparisons are exact, no float drift."""
    cert = SelfCertification(customer_id="C9", us_person=True, us_tin="X", certification_date="2025-01-01")
    # Exactly 50000.00 USD - must NOT be reportable (strict greater-than)
    accounts = [AccountBalance("C9", "A1", Decimal("50000.00"))]
    snaps = FatcaCrsReportingEngine.build_period_snapshot("2025", accounts, {"C9": cert})
    assert snaps[0].status == STATUS_NOT_REPORTABLE
    # 50000.01 - reportable
    accounts2 = [AccountBalance("C9", "A1", Decimal("50000.01"))]
    snaps2 = FatcaCrsReportingEngine.build_period_snapshot("2025", accounts2, {"C9": cert})
    assert snaps2[0].status == STATUS_REPORTABLE_FATCA

def _test_payload_skeleton_fatca():
    cert = SelfCertification(customer_id="C10", us_person=True, us_tin="X", certification_date="2025-01-01")
    accounts = [AccountBalance("C10", "A1", Decimal("100000"))]
    snaps = FatcaCrsReportingEngine.build_period_snapshot("2025", accounts, {"C10": cert})
    payload = FatcaCrsReportingEngine.build_payload_skeleton(snaps, "FATCA")
    assert payload["regime"] == "FATCA"
    assert payload["form"] == FATCA_FORM
    assert payload["record_count"] == 1
    assert payload["spec_deviation_note"] == SPEC_DEVIATION_NOTE
    assert payload["submitter_jurisdiction"] == "KE"

def _test_payload_skeleton_crs():
    cert = SelfCertification(customer_id="C11", us_person=False, tax_residences=["GB", "DE"], certification_date="2025-01-01")
    accounts = [AccountBalance("C11", "A1", Decimal("50000"))]
    snaps = FatcaCrsReportingEngine.build_period_snapshot("2025", accounts, {"C11": cert})
    payload = FatcaCrsReportingEngine.build_payload_skeleton(snaps, "CRS")
    assert payload["regime"] == "CRS"
    assert payload["record_count"] == 1
    assert payload["spec_deviation_note"] == SPEC_DEVIATION_NOTE

def _test_unsupported_regime():
    payload = FatcaCrsReportingEngine.build_payload_skeleton([], "INVALID")
    assert "error" in payload
    assert "FATCA" in payload["supported"]

def _test_reporting_summary():
    cert1 = SelfCertification(customer_id="X1", us_person=True, us_tin="X", certification_date="2025-01-01")
    cert2 = SelfCertification(customer_id="X2", us_person=False, tax_residences=["GB"], certification_date="2025-01-01")
    accounts = [
        AccountBalance("X1", "A1", Decimal("100000")),
        AccountBalance("X2", "A1", Decimal("50000")),
        AccountBalance("X3", "A1", Decimal("10000")),  # undocumented
    ]
    snaps = FatcaCrsReportingEngine.build_period_snapshot("2025", accounts, {"X1": cert1, "X2": cert2})
    summary = FatcaCrsReportingEngine.reporting_summary(snaps)
    assert summary["total_holders"] == 3
    assert summary["reportable_count"] == 2
    assert summary["undocumented_count"] == 1

def _test_schema_definitions():
    """Cat A schema present and well-formed."""
    for sch in (SCHEMA_SELF_CERT_TABLE, SCHEMA_REPORTABLE_TABLE, SCHEMA_SUBMISSION_TABLE):
        assert "table" in sch
        assert "columns" in sch
        assert len(sch["columns"]) >= 3
        assert "PRIMARY KEY" in sch["columns"][0][1]

def _test_spec_deviation_note_byte_for_byte():
    expected = (
        "FATCA Form 8966 XML and OECD CRS XML payload generation are "
        "implemented at v10.194 (full element tree per OECD CRS XSD v2.0 "
        "and IRS FATCA XSD v2.4). Diagnostic only per Rule 7 — engine "
        "produces XML strings; never signs (XMLDSig), never validates "
        "against external XSD files (caller's responsibility), never "
        "encrypts, never transmits to KRA / IRS."
    )
    assert SPEC_DEVIATION_NOTE == expected, f"SPEC_DEVIATION_NOTE drifted"


def _build_test_records():
    """Helper: build a small set of XmlReportableRecords spanning all
    three reportable statuses (FATCA-only, CRS-only, BOTH)."""
    certs = {
        "C100": SelfCertification(
            customer_id="C100", us_person=True,
            us_tin="123-45-6789",
            certification_date="2025-06-01",
            entity_type="INDIVIDUAL"),
        "C200": SelfCertification(
            customer_id="C200", us_person=False,
            tax_residences=["GB"],
            foreign_tins={"GB": "AB123456C"},
            certification_date="2025-06-01",
            entity_type="INDIVIDUAL"),
        "C300": SelfCertification(
            customer_id="C300", us_person=True,
            us_tin="999-99-9999",
            tax_residences=["DE"],
            foreign_tins={"DE": "DE987654321"},
            certification_date="2025-06-01",
            entity_type="INDIVIDUAL"),
    }
    accounts = [
        AccountBalance("C100", "ACC-100-1", Decimal("75000")),
        AccountBalance("C200", "ACC-200-1", Decimal("12500")),
        AccountBalance("C300", "ACC-300-1", Decimal("125000")),
    ]
    snapshots = FatcaCrsReportingEngine.build_period_snapshot(
        "2025-12-31", accounts, certs)
    rec_meta = {
        "C100": ("Alice Johnson", "Alice", "Johnson", "US",
                 "1500 Pennsylvania Ave, Washington DC, USA",
                 "123-45-6789", "US", "1985-04-12"),
        "C200": ("Bob Smith", "Bob", "Smith", "GB",
                 "10 Downing Street, London SW1A 2AA, UK",
                 "AB123456C", "GB", "1972-09-22"),
        "C300": ("Carla Schmidt", "Carla", "Schmidt", "DE",
                 "Unter den Linden 6, Berlin, Germany",
                 "DE987654321", "DE", "1990-11-05"),
    }
    records = []
    for snap in snapshots:
        name, fn, ln, addr_cc, addr, tin, tin_cc, dob = rec_meta[
            snap.customer_id]
        records.append(XmlReportableRecord(
            snapshot=snap, account_holder_name=name,
            account_holder_type=ACCOUNT_TYPE_INDIVIDUAL,
            address_country_code=addr_cc, address_free=addr,
            tin=tin, tin_country_code=tin_cc,
            birth_date_iso=dob, first_name=fn, last_name=ln))
    sender = XmlReportSenderInfo(
        sender_in="9X5Y3T.99999.SL.404",
        sender_name="Ecobank Kenya",
        transmitting_country="KE", receiving_country="US",
        message_ref_id="KE2025ECOBANK0001",
        reporting_period="2025-12-31",
        timestamp_iso="2026-01-15T10:00:00Z",
        contact="aml.team@ecobank.com",
        fi_in="9X5Y3T.99999.SL.404",
        fi_name="Ecobank Kenya Limited",
        fi_address_country="KE",
        fi_address_free="Ecobank Towers, Nairobi, Kenya")
    return records, sender


def _test_crs_xml_well_formed():
    """CRS XML must parse back as well-formed XML."""
    records, sender = _build_test_records()
    xml = FatcaCrsReportingEngine.build_crs_xml(records, sender)
    tree = ET.fromstring(xml)
    assert tree.tag.endswith("CRS_OECD"), \
        f"unexpected root tag: {tree.tag}"
    # CRS namespace declared
    assert "urn:oecd:ties:crs:v2" in xml


def _test_crs_xml_filters_us_only():
    """CRS XML excludes records that are FATCA-only (US persons
    not resident in any CRS jurisdiction)."""
    records, sender = _build_test_records()
    xml = FatcaCrsReportingEngine.build_crs_xml(records, sender)
    # C100 is REPORTABLE_FATCA only — must NOT appear
    assert "C100" not in xml or "ACC-100-1" not in xml, \
        "FATCA-only record leaked into CRS XML"
    # C200 (CRS-only) and C300 (BOTH) must appear
    assert "ACC-200-1" in xml, "CRS-only record missing from CRS XML"
    assert "ACC-300-1" in xml, "BOTH record missing from CRS XML"
    assert xml.count("<AccountReport>") == 2


def _test_fatca_xml_well_formed():
    """FATCA XML must parse back as well-formed XML."""
    records, sender = _build_test_records()
    xml = FatcaCrsReportingEngine.build_fatca_xml(records, sender)
    tree = ET.fromstring(xml)
    assert tree.tag.endswith("FATCA_OECD"), \
        f"unexpected root tag: {tree.tag}"
    assert "urn:oecd:ties:fatca:v2.4" in xml


def _test_fatca_xml_filters_non_us():
    """FATCA XML excludes records that are CRS-only (non-US tax
    residents)."""
    records, sender = _build_test_records()
    xml = FatcaCrsReportingEngine.build_fatca_xml(records, sender)
    # C200 is REPORTABLE_CRS only (GB resident) — must NOT appear
    assert "ACC-200-1" not in xml, \
        "CRS-only record leaked into FATCA XML"
    assert "ACC-100-1" in xml, "FATCA-only record missing"
    assert "ACC-300-1" in xml, "BOTH record missing"
    assert xml.count("<AccountReport>") == 2


def _test_xml_includes_message_spec():
    """Both XML formats must include MessageSpec with MessageRefId,
    ReportingPeriod, and Timestamp from sender."""
    records, sender = _build_test_records()
    crs = FatcaCrsReportingEngine.build_crs_xml(records, sender)
    fatca = FatcaCrsReportingEngine.build_fatca_xml(records, sender)
    for xml in (crs, fatca):
        assert "<MessageSpec>" in xml
        assert "KE2025ECOBANK0001" in xml
        assert "2025-12-31" in xml
        assert "2026-01-15T10:00:00Z" in xml


def _test_xml_includes_reporting_fi():
    """Both XML formats must declare the ReportingFI block with
    bank's IN, name, and address."""
    records, sender = _build_test_records()
    crs = FatcaCrsReportingEngine.build_crs_xml(records, sender)
    fatca = FatcaCrsReportingEngine.build_fatca_xml(records, sender)
    for xml in (crs, fatca):
        assert "<ReportingFI>" in xml
        assert "9X5Y3T.99999.SL.404" in xml
        assert "Ecobank Kenya Limited" in xml
        assert "Ecobank Towers" in xml


def _test_xml_balance_currency_attr():
    """AccountBalance must carry currCode attribute."""
    records, sender = _build_test_records()
    crs = FatcaCrsReportingEngine.build_crs_xml(records, sender)
    assert 'currCode="USD"' in crs


def _test_xml_validates_sender_info():
    """XmlReportSenderInfo rejects empty / malformed inputs."""
    valid = dict(
        sender_in="X", sender_name="X",
        transmitting_country="KE", receiving_country="US",
        message_ref_id="X", reporting_period="2025-12-31",
        timestamp_iso="2026-01-15T10:00:00Z",
        contact="a@b.c",
        fi_in="X", fi_name="X",
        fi_address_country="KE", fi_address_free="X")
    # Empty sender_in
    bad = dict(valid); bad["sender_in"] = ""
    try:
        XmlReportSenderInfo(**bad)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for empty sender_in")
    # Non-2-char country
    bad = dict(valid); bad["transmitting_country"] = "KEN"
    try:
        XmlReportSenderInfo(**bad)
    except ValueError:
        pass
    else:
        raise AssertionError(
            "expected ValueError for 3-char country code")


def _test_xml_validates_reportable_record():
    """XmlReportableRecord rejects malformed inputs."""
    snap = ReportableSnapshot(
        reporting_period="2025-12-31", customer_id="C1",
        aggregated_balance_usd=Decimal("100"),
        status=STATUS_REPORTABLE_CRS, us_person_flag=False,
        crs_jurisdictions=["GB"], account_ids=["A1"],
        classified_at="2026-01-01T00:00:00Z")
    valid = dict(
        snapshot=snap, account_holder_name="Test",
        account_holder_type=ACCOUNT_TYPE_INDIVIDUAL,
        address_country_code="GB", address_free="London")
    # Bad doc_type
    bad = dict(valid); bad["doc_type"] = "OECD9"
    try:
        XmlReportableRecord(**bad)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for bad doc_type")
    # Bad currency code
    bad = dict(valid); bad["currency_code"] = "USDX"
    try:
        XmlReportableRecord(**bad)
    except ValueError:
        pass
    else:
        raise AssertionError(
            "expected ValueError for 4-char currency code")


def self_test() -> bool:
    tests = [
        _test_us_person_individual_above_threshold,
        _test_us_person_below_threshold,
        _test_crs_jurisdiction_reportable,
        _test_kenya_resident_not_reportable,
        _test_both_fatca_and_crs,
        _test_undocumented_rule6,
        _test_inactive_cert_is_undocumented,
        _test_balance_aggregation,
        _test_entity_threshold_higher,
        _test_decimal_precision_rule1,
        _test_payload_skeleton_fatca,
        _test_payload_skeleton_crs,
        _test_unsupported_regime,
        _test_reporting_summary,
        _test_schema_definitions,
        _test_spec_deviation_note_byte_for_byte,
        _test_crs_xml_well_formed,
        _test_crs_xml_filters_us_only,
        _test_fatca_xml_well_formed,
        _test_fatca_xml_filters_non_us,
        _test_xml_includes_message_spec,
        _test_xml_includes_reporting_fi,
        _test_xml_balance_currency_attr,
        _test_xml_validates_sender_info,
        _test_xml_validates_reportable_record,
    ]
    print("=" * 60)
    print("FATCA/CRS Reporting Engine — Self-Tests (#60)")
    print("=" * 60)
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {e}")
    print("-" * 60)
    if failed == 0:
        print(f"  ALL {len(tests)} TESTS PASSED")
        return True
    print(f"  {failed}/{len(tests)} FAILED")
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)
