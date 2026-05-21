"""utils/trade_finance_compliance.py — v10.73: TF compliance.

ENH-274 — Trade Finance Compliance Engine. Cat B —
trade_finance arc 4/N.

Diagnostic sanctions + dual-use + restricted-port screening
engine for trade finance instruments. Surfaces compliance
exposure across 5 dimensions:

  1. Party screening — applicant + beneficiary + advising bank
     against caller-supplied sanctions lists (OFAC SDN, UN
     Consolidated, EU Restrictive Measures, UK HMT)
  2. Country screening — country of applicant / beneficiary /
     transit against embargo lists
  3. Port screening — ports of loading / discharge against
     restricted-port lists
  4. Vessel screening — vessel name / IMO number against
     designated-vessel lists
  5. Goods screening — description against dual-use /
     prohibited goods keyword lists (Wassenaar, EU Regulation
     2021/821, Kenyan Strategic Trade Authorisation)

Operates with caller-supplied lists. Engine does NOT bundle
sanctions data — that data is operationally maintained outside
the engine and updated weekly/daily. Engine performs:
  - exact-match screening (identifier == identifier)
  - normalized substring matching for free-text fields
    (party names, vessel names, goods descriptions)
  - aliased-term expansion via caller-supplied AliasMap

Per Rule 7, engine NEVER:
  - blocks transactions
  - reports to OFAC / KFIU / FRC (these are operator duties)
  - freezes assets or accounts
  - submits SARs (Suspicious Activity Reports)
  - amends sanctions lists
  - mutates inputs
  - decides true vs false positive (caller adjudicates)

Per Rule 1, every Hit surfaces dimension + matched_term +
source_list + severity + matched_field + framework refs.

Pure stdlib (frozen dataclasses + enums). String matching
case-insensitive on lowercased + whitespace-collapsed forms.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

SPEC_DEVIATION_NOTE = (
    "TradeFinanceComplianceEngine implements ENH-274 — "
    "diagnostic sanctions + dual-use + restricted-port "
    "screening across 5 dimensions. Caller supplies sanctions "
    "list data; engine performs matching only. Pure stdlib. "
    "Per Rule 1, every hit surfaces dimension + matched term "
    "+ source list + severity + framework refs. Per Rule 7, "
    "engine DIAGNOSTIC ONLY — never blocks transactions; never "
    "reports to OFAC/KFIU/FRC; never freezes assets; never "
    "submits SARs; never amends sanctions lists; never decides "
    "true vs false positive (caller adjudicates); never "
    "mutates inputs."
)


# ════════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════════

class ScreeningDimension(Enum):
    PARTY = "PARTY"
    COUNTRY = "COUNTRY"
    PORT = "PORT"
    VESSEL = "VESSEL"
    GOODS = "GOODS"


class HitSeverity(Enum):
    """Caller-attributed severity by source list authority."""
    CRITICAL = "CRITICAL"   # OFAC SDN, UN Consolidated
    HIGH = "HIGH"           # EU Restrictive, UK HMT
    MEDIUM = "MEDIUM"       # internal watchlist
    LOW = "LOW"             # internal review-only
    INFO = "INFO"           # informational match


class ScreeningOutcome(Enum):
    CLEAR = "CLEAR"                           # 0 hits
    REVIEW_NEEDED = "REVIEW_NEEDED"            # ≥1 LOW/MEDIUM/INFO
    SENIOR_APPROVAL = "SENIOR_APPROVAL"        # ≥1 HIGH
    BLOCK_RECOMMENDED = "BLOCK_RECOMMENDED"   # ≥1 CRITICAL


class MatchType(Enum):
    EXACT = "EXACT"
    NORMALIZED = "NORMALIZED"
    SUBSTRING = "SUBSTRING"
    ALIAS = "ALIAS"


# ════════════════════════════════════════════════════════════════════════
# Input dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class SanctionsListEntry:
    """One row of a sanctions list."""
    list_id: str             # e.g. "OFAC_SDN"
    list_authority: str      # e.g. "U.S. Treasury OFAC"
    entry_id: str            # unique within list
    entity_type: str         # PERSON / ENTITY / VESSEL / etc.
    name: str                # primary name
    aliases: Tuple[str, ...] = ()
    country: Optional[str] = None
    severity: HitSeverity = HitSeverity.CRITICAL

    def __post_init__(self) -> None:
        if not self.list_id:
            raise ValueError("list_id must be non-empty")
        if not self.entry_id:
            raise ValueError("entry_id must be non-empty")
        if not self.name:
            raise ValueError("name must be non-empty")


@dataclass(frozen=True)
class CountryEmbargo:
    country_code: str        # ISO-3166-alpha-2
    list_id: str
    list_authority: str
    severity: HitSeverity = HitSeverity.CRITICAL
    notes: str = ""

    def __post_init__(self) -> None:
        if (
            not self.country_code
            or len(self.country_code) != 2
        ):
            raise ValueError(
                "country_code must be 2-letter ISO code")
        if not self.list_id:
            raise ValueError("list_id must be non-empty")


@dataclass(frozen=True)
class RestrictedPort:
    port_code: str           # UN/LOCODE preferred
    port_name: str
    list_id: str
    list_authority: str
    severity: HitSeverity = HitSeverity.HIGH


@dataclass(frozen=True)
class DesignatedVessel:
    imo_number: Optional[str]
    vessel_name: str
    list_id: str
    list_authority: str
    severity: HitSeverity = HitSeverity.CRITICAL


@dataclass(frozen=True)
class ProhibitedGoodsKeyword:
    """Keyword/phrase indicating dual-use or prohibited."""
    keyword: str
    category: str            # e.g. "DUAL_USE_NUCLEAR"
    list_id: str
    list_authority: str
    severity: HitSeverity = HitSeverity.HIGH


@dataclass(frozen=True)
class TradeFinanceParty:
    """One party to a trade finance instrument for screening."""
    party_id: str
    party_role: str          # APPLICANT/BENEFICIARY/etc.
    name: str
    country: Optional[str] = None    # ISO-3166-alpha-2
    aliases: Tuple[str, ...] = ()


@dataclass(frozen=True)
class TradeFinanceShipment:
    """Shipping detail for screening."""
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    transit_countries: Tuple[str, ...] = ()
    vessel_name: Optional[str] = None
    vessel_imo: Optional[str] = None
    description_of_goods: str = ""


# ════════════════════════════════════════════════════════════════════════
# Output dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ScreeningHit:
    dimension: ScreeningDimension
    matched_field_label: str   # e.g. "applicant.name"
    matched_value: str         # the input string that matched
    matched_against: str       # the sanctions entry that matched
    source_list_id: str
    source_list_authority: str
    match_type: MatchType
    severity: HitSeverity
    description: str
    framework_refs: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ScreeningReport:
    instrument_id: str
    hits: Tuple[ScreeningHit, ...]
    outcome: ScreeningOutcome
    by_dimension: Dict[str, int]
    by_severity: Dict[str, int]
    framework_refs: Tuple[str, ...] = ()


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class TradeFinanceComplianceEngine:
    """Diagnostic compliance screening engine."""

    @staticmethod
    def _normalize(s: str) -> str:
        """Lowercase, collapse whitespace, strip punctuation."""
        s = s.lower()
        s = re.sub(r"[^\w\s]", " ", s)
        s = re.sub(r"\s+", " ", s)
        return s.strip()

    def _match_party_against_list(
        self,
        party: TradeFinanceParty,
        sanctions_list: Sequence[SanctionsListEntry],
    ) -> List[ScreeningHit]:
        hits: List[ScreeningHit] = []
        norm_name = self._normalize(party.name)
        norm_aliases = {
            self._normalize(a) for a in party.aliases}
        all_party_terms = {norm_name} | norm_aliases
        for entry in sanctions_list:
            norm_entry = self._normalize(entry.name)
            entry_aliases = {
                self._normalize(a) for a in entry.aliases}
            entry_all = {norm_entry} | entry_aliases
            # Exact match (after normalization)
            common = all_party_terms & entry_all
            if common:
                match_type = (
                    MatchType.NORMALIZED
                    if norm_name == norm_entry
                    else MatchType.ALIAS)
                hits.append(ScreeningHit(
                    dimension=ScreeningDimension.PARTY,
                    matched_field_label=(
                        f"{party.party_role}.name"),
                    matched_value=party.name,
                    matched_against=entry.name,
                    source_list_id=entry.list_id,
                    source_list_authority=(
                        entry.list_authority),
                    match_type=match_type,
                    severity=entry.severity,
                    description=(
                        f"{party.party_role} '{party.name}' "
                        f"matches sanctions entry "
                        f"'{entry.name}' on "
                        f"{entry.list_authority} "
                        f"({entry.list_id}); operator "
                        f"adjudicates true/false positive"),
                    framework_refs=(
                        "ENH-274 §screen_party",
                        f"Source: {entry.list_authority}",
                        "Per Rule 7 — never blocks; surfaces "
                        "for operator adjudication",)))
                continue
            # Substring match (party name fully contains entry
            # name or vice versa, both ≥4 chars to avoid false
            # positives on short fragments)
            if (
                len(norm_name) >= 4 and len(norm_entry) >= 4
                and (
                    norm_entry in norm_name
                    or norm_name in norm_entry)
            ):
                hits.append(ScreeningHit(
                    dimension=ScreeningDimension.PARTY,
                    matched_field_label=(
                        f"{party.party_role}.name"),
                    matched_value=party.name,
                    matched_against=entry.name,
                    source_list_id=entry.list_id,
                    source_list_authority=(
                        entry.list_authority),
                    match_type=MatchType.SUBSTRING,
                    severity=entry.severity,
                    description=(
                        f"{party.party_role} '{party.name}' "
                        f"substring-matches sanctions entry "
                        f"'{entry.name}'; LOW-confidence — "
                        f"operator adjudicates"),
                    framework_refs=(
                        "ENH-274 §screen_party",
                        f"Source: {entry.list_authority}",
                        "Per Rule 7 — never blocks",)))
        return hits

    def screen_party(
        self,
        party: TradeFinanceParty,
        sanctions_list: Sequence[SanctionsListEntry],
    ) -> Tuple[ScreeningHit, ...]:
        return tuple(
            self._match_party_against_list(
                party, sanctions_list))

    def screen_country(
        self,
        country_code: str,
        country_role: str,
        embargoes: Sequence[CountryEmbargo],
    ) -> Tuple[ScreeningHit, ...]:
        if not country_code:
            return ()
        target = country_code.upper()
        hits: List[ScreeningHit] = []
        for emb in embargoes:
            if emb.country_code.upper() == target:
                hits.append(ScreeningHit(
                    dimension=ScreeningDimension.COUNTRY,
                    matched_field_label=country_role,
                    matched_value=country_code,
                    matched_against=emb.country_code,
                    source_list_id=emb.list_id,
                    source_list_authority=emb.list_authority,
                    match_type=MatchType.EXACT,
                    severity=emb.severity,
                    description=(
                        f"{country_role} '{country_code}' is "
                        f"on {emb.list_authority} embargo list "
                        f"({emb.list_id})"
                        + (f": {emb.notes}" if emb.notes
                           else "")),
                    framework_refs=(
                        "ENH-274 §screen_country",
                        f"Source: {emb.list_authority}",
                        "Per Rule 7 — never blocks",)))
        return tuple(hits)

    def screen_port(
        self,
        port: str,
        port_role: str,
        restricted_ports: Sequence[RestrictedPort],
    ) -> Tuple[ScreeningHit, ...]:
        if not port:
            return ()
        norm_port = self._normalize(port)
        hits: List[ScreeningHit] = []
        for rp in restricted_ports:
            if (
                rp.port_code.upper() == port.upper()
                or self._normalize(rp.port_name) == norm_port
            ):
                hits.append(ScreeningHit(
                    dimension=ScreeningDimension.PORT,
                    matched_field_label=port_role,
                    matched_value=port,
                    matched_against=(
                        f"{rp.port_code} ({rp.port_name})"),
                    source_list_id=rp.list_id,
                    source_list_authority=rp.list_authority,
                    match_type=MatchType.EXACT,
                    severity=rp.severity,
                    description=(
                        f"{port_role} '{port}' is on "
                        f"{rp.list_authority} restricted-port "
                        f"list ({rp.list_id})"),
                    framework_refs=(
                        "ENH-274 §screen_port",
                        f"Source: {rp.list_authority}",
                        "Per Rule 7 — never blocks",)))
        return tuple(hits)

    def screen_vessel(
        self,
        vessel_name: Optional[str],
        vessel_imo: Optional[str],
        designated_vessels: Sequence[DesignatedVessel],
    ) -> Tuple[ScreeningHit, ...]:
        if not vessel_name and not vessel_imo:
            return ()
        hits: List[ScreeningHit] = []
        norm_name = (
            self._normalize(vessel_name) if vessel_name else "")
        for dv in designated_vessels:
            # IMO match (most reliable)
            if (
                vessel_imo is not None
                and dv.imo_number is not None
                and dv.imo_number == vessel_imo
            ):
                hits.append(ScreeningHit(
                    dimension=ScreeningDimension.VESSEL,
                    matched_field_label="vessel.imo",
                    matched_value=vessel_imo,
                    matched_against=(
                        f"{dv.vessel_name} (IMO "
                        f"{dv.imo_number})"),
                    source_list_id=dv.list_id,
                    source_list_authority=dv.list_authority,
                    match_type=MatchType.EXACT,
                    severity=dv.severity,
                    description=(
                        f"vessel IMO {vessel_imo} is on "
                        f"{dv.list_authority} designated-vessel "
                        f"list"),
                    framework_refs=(
                        "ENH-274 §screen_vessel",
                        f"Source: {dv.list_authority}",
                        "Per Rule 7 — never blocks",)))
                continue
            # Name match (fallback)
            if (
                norm_name
                and self._normalize(dv.vessel_name)
                == norm_name
            ):
                hits.append(ScreeningHit(
                    dimension=ScreeningDimension.VESSEL,
                    matched_field_label="vessel.name",
                    matched_value=vessel_name or "",
                    matched_against=dv.vessel_name,
                    source_list_id=dv.list_id,
                    source_list_authority=dv.list_authority,
                    match_type=MatchType.NORMALIZED,
                    severity=dv.severity,
                    description=(
                        f"vessel name '{vessel_name}' "
                        f"normalized-matches "
                        f"{dv.list_authority} designated-"
                        f"vessel '{dv.vessel_name}'; verify "
                        f"IMO before adjudicating"),
                    framework_refs=(
                        "ENH-274 §screen_vessel",
                        f"Source: {dv.list_authority}",
                        "Per Rule 7 — never blocks",)))
        return tuple(hits)

    def screen_goods(
        self,
        description: str,
        keywords: Sequence[ProhibitedGoodsKeyword],
    ) -> Tuple[ScreeningHit, ...]:
        if not description:
            return ()
        norm_desc = self._normalize(description)
        hits: List[ScreeningHit] = []
        for kw in keywords:
            norm_kw = self._normalize(kw.keyword)
            if not norm_kw:
                continue
            # Word-boundary substring (whole-word match)
            pattern = (
                r"\b" + re.escape(norm_kw) + r"\b")
            if re.search(pattern, norm_desc):
                hits.append(ScreeningHit(
                    dimension=ScreeningDimension.GOODS,
                    matched_field_label=(
                        "description_of_goods"),
                    matched_value=description[:100],
                    matched_against=kw.keyword,
                    source_list_id=kw.list_id,
                    source_list_authority=kw.list_authority,
                    match_type=MatchType.SUBSTRING,
                    severity=kw.severity,
                    description=(
                        f"description contains "
                        f"'{kw.keyword}' (category "
                        f"{kw.category}) flagged on "
                        f"{kw.list_authority} ({kw.list_id})"),
                    framework_refs=(
                        "ENH-274 §screen_goods",
                        f"Source: {kw.list_authority}",
                        "Per Rule 7 — never blocks; never "
                        "decides true/false positive",)))
        return tuple(hits)

    def screen_instrument(
        self,
        instrument_id: str,
        parties: Sequence[TradeFinanceParty],
        shipment: Optional[TradeFinanceShipment],
        sanctions_list: Sequence[SanctionsListEntry] = (),
        country_embargoes: Sequence[CountryEmbargo] = (),
        restricted_ports: Sequence[RestrictedPort] = (),
        designated_vessels: Sequence[DesignatedVessel] = (),
        prohibited_keywords: Sequence[
            ProhibitedGoodsKeyword] = (),
    ) -> ScreeningReport:
        all_hits: List[ScreeningHit] = []
        # Party screening
        for p in parties:
            all_hits.extend(
                self.screen_party(p, sanctions_list))
            if p.country:
                all_hits.extend(
                    self.screen_country(
                        p.country,
                        f"{p.party_role}.country",
                        country_embargoes))
        # Shipment screening
        if shipment is not None:
            if shipment.port_of_loading:
                all_hits.extend(
                    self.screen_port(
                        shipment.port_of_loading,
                        "port_of_loading",
                        restricted_ports))
            if shipment.port_of_discharge:
                all_hits.extend(
                    self.screen_port(
                        shipment.port_of_discharge,
                        "port_of_discharge",
                        restricted_ports))
            for c in shipment.transit_countries:
                all_hits.extend(
                    self.screen_country(
                        c, "transit_country",
                        country_embargoes))
            all_hits.extend(
                self.screen_vessel(
                    shipment.vessel_name,
                    shipment.vessel_imo,
                    designated_vessels))
            all_hits.extend(
                self.screen_goods(
                    shipment.description_of_goods,
                    prohibited_keywords))
        # Outcome
        outcome = ScreeningOutcome.CLEAR
        if any(
            h.severity == HitSeverity.CRITICAL
            for h in all_hits
        ):
            outcome = ScreeningOutcome.BLOCK_RECOMMENDED
        elif any(
            h.severity == HitSeverity.HIGH for h in all_hits
        ):
            outcome = ScreeningOutcome.SENIOR_APPROVAL
        elif all_hits:
            outcome = ScreeningOutcome.REVIEW_NEEDED
        # Aggregates
        by_dimension: Dict[str, int] = {
            d.value: 0 for d in ScreeningDimension}
        by_severity: Dict[str, int] = {
            s.value: 0 for s in HitSeverity}
        for h in all_hits:
            by_dimension[h.dimension.value] += 1
            by_severity[h.severity.value] += 1
        return ScreeningReport(
            instrument_id=instrument_id,
            hits=tuple(all_hits),
            outcome=outcome,
            by_dimension=by_dimension,
            by_severity=by_severity,
            framework_refs=(
                "ENH-274 §screen_instrument",
                "Per Rule 7 — never blocks; never reports to "
                "OFAC / KFIU / FRC; never freezes assets; "
                "never submits SARs; operator adjudicates",
            ),
        )


# ════════════════════════════════════════════════════════════════════════
# Self-tests
# ════════════════════════════════════════════════════════════════════════

def _test_normalize_basics():
    eng = TradeFinanceComplianceEngine()
    assert eng._normalize("Hello, World!") == "hello world"
    assert eng._normalize(
        "  ACME  Imports  Ltd. ") == "acme imports ltd"


def _test_party_exact_match():
    eng = TradeFinanceComplianceEngine()
    party = TradeFinanceParty(
        party_id="P1", party_role="APPLICANT",
        name="ACME IMPORTS LTD")
    sanctions = (
        SanctionsListEntry(
            list_id="OFAC_SDN",
            list_authority="U.S. Treasury OFAC",
            entry_id="OFAC-001",
            entity_type="ENTITY",
            name="Acme Imports Ltd",
            severity=HitSeverity.CRITICAL),
    )
    hits = eng.screen_party(party, sanctions)
    assert len(hits) == 1
    assert hits[0].severity == HitSeverity.CRITICAL
    assert hits[0].source_list_id == "OFAC_SDN"


def _test_party_alias_match():
    eng = TradeFinanceComplianceEngine()
    party = TradeFinanceParty(
        party_id="P1", party_role="APPLICANT",
        name="The Big Corp")
    sanctions = (
        SanctionsListEntry(
            list_id="UN_CONS",
            list_authority="UN Consolidated",
            entry_id="UN-001",
            entity_type="ENTITY",
            name="Big Corporation",
            aliases=("The Big Corp", "TBC Holdings"),
            severity=HitSeverity.CRITICAL),
    )
    hits = eng.screen_party(party, sanctions)
    assert len(hits) >= 1
    # Should have matched on alias
    assert any(
        h.match_type == MatchType.ALIAS for h in hits)


def _test_party_no_false_positive_on_short_substring():
    eng = TradeFinanceComplianceEngine()
    party = TradeFinanceParty(
        party_id="P1", party_role="APPLICANT",
        name="Acme Industries Limited")
    # Short ENTITY (3 chars) shouldn't substring-match
    sanctions = (
        SanctionsListEntry(
            list_id="X", list_authority="X",
            entry_id="X-001", entity_type="ENTITY",
            name="Inc"),
    )
    hits = eng.screen_party(party, sanctions)
    assert len(hits) == 0


def _test_country_embargo_match():
    eng = TradeFinanceComplianceEngine()
    embargoes = (
        CountryEmbargo(
            country_code="XX", list_id="UN_EMB",
            list_authority="UN Security Council",
            severity=HitSeverity.CRITICAL,
            notes="comprehensive embargo"),
    )
    hits = eng.screen_country("XX", "applicant.country", embargoes)
    assert len(hits) == 1
    assert hits[0].severity == HitSeverity.CRITICAL


def _test_country_no_match():
    eng = TradeFinanceComplianceEngine()
    embargoes = (
        CountryEmbargo(
            country_code="XX", list_id="UN_EMB",
            list_authority="UN", severity=HitSeverity.CRITICAL),
    )
    hits = eng.screen_country("KE", "applicant.country", embargoes)
    assert len(hits) == 0


def _test_country_validates_iso_code():
    try:
        CountryEmbargo(
            country_code="USA", list_id="X",
            list_authority="X")
        assert False
    except ValueError:
        pass


def _test_port_match():
    eng = TradeFinanceComplianceEngine()
    ports = (
        RestrictedPort(
            port_code="XXYYY", port_name="Restricted Port",
            list_id="OFAC_PORTS",
            list_authority="OFAC",
            severity=HitSeverity.HIGH),
    )
    hits = eng.screen_port(
        "XXYYY", "port_of_loading", ports)
    assert len(hits) == 1
    assert hits[0].severity == HitSeverity.HIGH


def _test_vessel_imo_match():
    eng = TradeFinanceComplianceEngine()
    vessels = (
        DesignatedVessel(
            imo_number="9123456",
            vessel_name="Some Vessel",
            list_id="OFAC_VESSEL",
            list_authority="OFAC",
            severity=HitSeverity.CRITICAL),
    )
    hits = eng.screen_vessel("Other Name", "9123456", vessels)
    assert len(hits) == 1
    assert hits[0].match_type == MatchType.EXACT
    assert hits[0].matched_field_label == "vessel.imo"


def _test_vessel_name_match_when_no_imo():
    eng = TradeFinanceComplianceEngine()
    vessels = (
        DesignatedVessel(
            imo_number=None,
            vessel_name="MV BLACKLIST",
            list_id="OFAC_VESSEL",
            list_authority="OFAC",
            severity=HitSeverity.CRITICAL),
    )
    hits = eng.screen_vessel("MV Blacklist", None, vessels)
    assert len(hits) == 1
    assert hits[0].match_type == MatchType.NORMALIZED


def _test_vessel_no_imo_no_name_skips():
    eng = TradeFinanceComplianceEngine()
    vessels = (
        DesignatedVessel(
            imo_number="123", vessel_name="X",
            list_id="X", list_authority="X"),
    )
    assert eng.screen_vessel(None, None, vessels) == ()


def _test_goods_keyword_match():
    eng = TradeFinanceComplianceEngine()
    keywords = (
        ProhibitedGoodsKeyword(
            keyword="centrifuge",
            category="DUAL_USE_NUCLEAR",
            list_id="WASSENAAR",
            list_authority="Wassenaar Arrangement",
            severity=HitSeverity.HIGH),
    )
    hits = eng.screen_goods(
        "10 industrial centrifuge units for laboratory use",
        keywords)
    assert len(hits) == 1
    assert hits[0].severity == HitSeverity.HIGH


def _test_goods_keyword_word_boundary():
    eng = TradeFinanceComplianceEngine()
    keywords = (
        ProhibitedGoodsKeyword(
            keyword="ant",
            category="X", list_id="X",
            list_authority="X"),
    )
    # "antibiotic" should NOT match "ant" — word boundaries
    hits = eng.screen_goods(
        "antibiotic medication 500mg", keywords)
    assert len(hits) == 0


def _test_goods_empty_description_returns_no_hit():
    eng = TradeFinanceComplianceEngine()
    keywords = (
        ProhibitedGoodsKeyword(
            keyword="x", category="x",
            list_id="x", list_authority="x"),
    )
    assert eng.screen_goods("", keywords) == ()


def _test_screen_instrument_clear():
    eng = TradeFinanceComplianceEngine()
    party = TradeFinanceParty(
        party_id="P1", party_role="APPLICANT",
        name="Clean Co", country="KE")
    shipment = TradeFinanceShipment(
        port_of_loading="KEMBA",
        port_of_discharge="GBLON",
        description_of_goods="cement bags 100MT")
    report = eng.screen_instrument(
        "INST-1", parties=(party,), shipment=shipment)
    assert report.outcome == ScreeningOutcome.CLEAR
    assert len(report.hits) == 0


def _test_screen_instrument_block_on_critical():
    eng = TradeFinanceComplianceEngine()
    party = TradeFinanceParty(
        party_id="P1", party_role="APPLICANT",
        name="Blacklisted Corp", country="KE")
    sanctions = (
        SanctionsListEntry(
            list_id="OFAC_SDN",
            list_authority="OFAC", entry_id="X",
            entity_type="ENTITY",
            name="Blacklisted Corp",
            severity=HitSeverity.CRITICAL),
    )
    report = eng.screen_instrument(
        "INST-1", parties=(party,), shipment=None,
        sanctions_list=sanctions)
    assert report.outcome == (
        ScreeningOutcome.BLOCK_RECOMMENDED)
    assert report.by_severity["CRITICAL"] >= 1


def _test_screen_instrument_review_on_low():
    eng = TradeFinanceComplianceEngine()
    party = TradeFinanceParty(
        party_id="P1", party_role="APPLICANT",
        name="Sample Corp")
    keywords = (
        ProhibitedGoodsKeyword(
            keyword="centrifuge",
            category="DUAL_USE",
            list_id="W", list_authority="W",
            severity=HitSeverity.LOW),
    )
    shipment = TradeFinanceShipment(
        description_of_goods="laboratory centrifuge")
    report = eng.screen_instrument(
        "INST-1", parties=(party,), shipment=shipment,
        prohibited_keywords=keywords)
    assert report.outcome == ScreeningOutcome.REVIEW_NEEDED


def _test_screen_instrument_aggregates_by_dimension():
    eng = TradeFinanceComplianceEngine()
    party = TradeFinanceParty(
        party_id="P1", party_role="APPLICANT",
        name="Sample", country="XX")
    sanctions = (
        SanctionsListEntry(
            list_id="OFAC_SDN",
            list_authority="OFAC", entry_id="X",
            entity_type="ENTITY", name="Sample",
            severity=HitSeverity.CRITICAL),
    )
    embargoes = (
        CountryEmbargo(
            country_code="XX", list_id="UN",
            list_authority="UN",
            severity=HitSeverity.CRITICAL),
    )
    report = eng.screen_instrument(
        "INST-1", parties=(party,), shipment=None,
        sanctions_list=sanctions,
        country_embargoes=embargoes)
    assert report.by_dimension["PARTY"] == 1
    assert report.by_dimension["COUNTRY"] == 1


def _test_engine_does_not_mutate_inputs():
    eng = TradeFinanceComplianceEngine()
    party = TradeFinanceParty(
        party_id="P1", party_role="APPLICANT",
        name="X", country="KE",
        aliases=("Y",))
    sanctions = (
        SanctionsListEntry(
            list_id="X", list_authority="X",
            entry_id="X", entity_type="ENTITY", name="Z"),
    )
    eng.screen_party(party, sanctions)
    assert party.name == "X"
    assert party.aliases == ("Y",)


def _test_full_provenance():
    eng = TradeFinanceComplianceEngine()
    party = TradeFinanceParty(
        party_id="P1", party_role="APPLICANT",
        name="ACME LTD")
    sanctions = (
        SanctionsListEntry(
            list_id="OFAC_SDN",
            list_authority="OFAC", entry_id="X",
            entity_type="ENTITY", name="ACME LTD",
            severity=HitSeverity.CRITICAL),
    )
    hits = eng.screen_party(party, sanctions)
    assert any(
        "ENH-274" in r for r in hits[0].framework_refs)
    assert any(
        "OFAC" in r for r in hits[0].framework_refs)
    assert any(
        "Rule 7" in r for r in hits[0].framework_refs)


def self_test() -> None:
    tests = [
        _test_normalize_basics,
        _test_party_exact_match,
        _test_party_alias_match,
        _test_party_no_false_positive_on_short_substring,
        _test_country_embargo_match,
        _test_country_no_match,
        _test_country_validates_iso_code,
        _test_port_match,
        _test_vessel_imo_match,
        _test_vessel_name_match_when_no_imo,
        _test_vessel_no_imo_no_name_skips,
        _test_goods_keyword_match,
        _test_goods_keyword_word_boundary,
        _test_goods_empty_description_returns_no_hit,
        _test_screen_instrument_clear,
        _test_screen_instrument_block_on_critical,
        _test_screen_instrument_review_on_low,
        _test_screen_instrument_aggregates_by_dimension,
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
            f"✗ trade_finance_compliance self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ trade_finance_compliance self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
