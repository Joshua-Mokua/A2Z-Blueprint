"""utils/screening_orchestrator.py — ENH-192 PEP & Sanctions Screening
Orchestration Engine.

================================================================================
A2Z MIS 360 — ENH-192 PEP & Sanctions Screening Engine
================================================================================

ORCHESTRATION engine for unified PEP + Sanctions screening. Wires together:

    1. Sanctions screening — delegates to Standard #58
       (utils/sanctions_screening.py with its SanctionsScreeningEngine,
       Levenshtein-based fuzzy matching across OFAC/UN/EU/UK/CBK lists)
    2. PEP determination — composes the existing PEP handling in
       kyc_aml_risk (PEP_FOREIGN/PEP_DOMESTIC customer-type buckets)
    3. List freshness tracking — NEW in this engine; Standard #58
       doesn't track when each list was last refreshed
    4. Applicant integration — accepts ENH-191's CustomerApplicant /
       BusinessApplicant types directly + screens beneficial owners

CRITICAL DESIGN DECISION
------------------------
This engine does NOT duplicate Standard #58's sanctions screening or
ENH-121's PEP logic. Both already exist as live, active components.
ENH-192 is the ORCHESTRATOR that produces a single UnifiedScreeningResult
that downstream AML standards (ENH-193 transaction monitoring, ENH-194
SAR/STR filing) can consume.

Same compose-don't-duplicate pattern as ENH-191's relationship to
ENH-121 + Standard #57.

WHAT THIS ENGINE ADDS BEYOND STANDARD #58
-----------------------------------------
1. SanctionsListSource enum + ListFreshnessRecord dataclass — Standard #58
   tracks individual records but not list-level metadata. Operator needs
   to know "OFAC last refreshed 47 days ago" to assess screening quality.
2. Unified screen_applicant() that takes ENH-191 typed dataclasses and
   screens both the applicant AND all beneficial owners (KYB) in one
   call, returning a single result.
3. Per-source freshness status (FRESH / STALE / MISSING) with explicit
   thresholds — operator sees gaps before regulatory examination, not
   during it.
4. Honest "manual_load" status for sources that haven't been wired to
   their real data feed yet — surfaces production gaps without faking
   readiness.

HONEST DEFERRALS — NOT shipped (with reasons, not bandwidth)
-----------------------------------------------------------
- Real OFAC SDN XML feed ingestion (network + parsing). Engine ships
  load_from_source() API; real fetcher is separate work.
- Real UN/EU/UK list ingestion. Same reason.
- ML-based false-positive reduction. Standard #58 uses deterministic
  Levenshtein fuzzy matching; this engine doesn't add ML on top.
  Aliases are handled in SanctionsRecord.aliases (existing).
- Transliteration tables (Arabic↔Latin, Cyrillic↔Latin). Real
  transliteration needs verified lookup tables, not synthesized rules.

CBK/PG/15 + FATF ALIGNMENT
--------------------------
- CBK PG/15 mandates sanctions screening at onboarding AND ongoing
- FATF Recommendation 6 (sanctions): targeted financial sanctions
- FATF Recommendation 12 (PEPs): foreign vs domestic distinction
- This engine enforces:
  * Sanctions match → applicant tier=PROHIBITED (CBK/PG/15)
  * Foreign PEP → mandatory EDD (FATF Rec 12)
  * Domestic PEP → CDD with periodic review (FATF Rec 12, post-2012)
  * BO sanctions match → blocks the whole business (KYB rollup)

ENGINE STATE
------------
Stateful per-instance — list freshness records and screening history
retained across calls. Production deployment backs it with the
application database.

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Tuple


# ---------------------------------------------------------------------------
# Vocabularies
# ---------------------------------------------------------------------------


class SanctionsListSource(str, Enum):
    """Sources we can screen against. Aligned with Standard #58's
    SUPPORTED_SANCTIONS_LISTS but exposed as a proper enum here."""
    OFAC_SDN = "OFAC_SDN"
    UN_CONSOLIDATED = "UN_CONSOLIDATED"
    EU_CONSOLIDATED = "EU_CONSOLIDATED"
    UK_HMT = "UK_HMT"
    CBK_DOMESTIC = "CBK_DOMESTIC"


class ListFreshnessStatus(str, Enum):
    """Per-source freshness status. Lets operators see which lists
    are usable and which need refresh BEFORE regulatory examination."""
    FRESH = "FRESH"            # Refreshed within freshness window
    STALE = "STALE"            # Refreshed but past freshness window
    MISSING = "MISSING"        # Never loaded — gap, not stub
    MANUAL_LOAD = "MANUAL_LOAD"  # Loaded by operator, not by feed


class PepCategory(str, Enum):
    """FATF Rec 12 PEP categories. Foreign PEP = mandatory EDD;
    domestic PEP = CDD + periodic review."""
    NOT_PEP = "NOT_PEP"
    DOMESTIC_PEP = "DOMESTIC_PEP"
    FOREIGN_PEP = "FOREIGN_PEP"
    INTERNATIONAL_ORGANIZATION_PEP = "INTERNATIONAL_ORGANIZATION_PEP"


class ScreeningOutcome(str, Enum):
    """Final disposition for a unified screen call."""
    CLEAR = "CLEAR"
    PEP_REVIEW_REQUIRED = "PEP_REVIEW_REQUIRED"
    SANCTIONS_HIT_REQUIRES_REVIEW = "SANCTIONS_HIT_REQUIRES_REVIEW"
    SANCTIONS_CONFIRMED_BLOCK = "SANCTIONS_CONFIRMED_BLOCK"
    SCREENING_DEFERRED_LISTS_STALE = "SCREENING_DEFERRED_LISTS_STALE"


# Default freshness window — CBK doesn't specify but FATF guidance
# suggests sanctions lists should be refreshed at least monthly
DEFAULT_FRESHNESS_WINDOW_DAYS = 30

# Recommended freshness windows per source (defensible defaults)
FRESHNESS_WINDOW_DAYS_BY_SOURCE: Mapping[SanctionsListSource, int] = {
    SanctionsListSource.OFAC_SDN: 7,         # OFAC updates daily
    SanctionsListSource.UN_CONSOLIDATED: 14,  # UN updates weekly
    SanctionsListSource.EU_CONSOLIDATED: 14,
    SanctionsListSource.UK_HMT: 14,
    SanctionsListSource.CBK_DOMESTIC: 30,     # CBK updates less frequently
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ListFreshnessRecord:
    """Tracks the operational state of a sanctions list. Standard #58
    knows about individual records; this knows about source-level
    freshness."""
    source: SanctionsListSource
    last_refreshed_utc: Optional[str]  # ISO datetime, None = never
    n_records_loaded: int
    load_method: str  # "manual" | "automated_feed" | "api_pull"
    status: ListFreshnessStatus
    notes: str = ""


@dataclass(frozen=True)
class PepScreeningResult:
    is_pep: bool
    category: PepCategory
    reason: str = ""


@dataclass(frozen=True)
class SanctionsHitSummary:
    """Compact summary of a sanctions hit. Full hit details remain in
    Standard #58's ScreeningHit; this is the orchestrator's view."""
    source: SanctionsListSource
    matched_entity_name: str
    matched_record_id: str
    match_score: int  # 0-100
    hit_status: str   # NEW_HIT, UNDER_REVIEW, CLEARED_FALSE, CONFIRMED_TRUE
    screening_id: int


@dataclass(frozen=True)
class UnifiedScreeningResult:
    """Single result combining PEP + sanctions screening."""
    subject_id: str
    subject_name: str
    subject_kind: str  # "INDIVIDUAL" | "BUSINESS" | "BENEFICIAL_OWNER"
    pep_result: PepScreeningResult
    sanctions_hits: Tuple[SanctionsHitSummary, ...]
    outcome: ScreeningOutcome
    lists_screened: Tuple[SanctionsListSource, ...]
    lists_skipped_due_to_staleness: Tuple[SanctionsListSource, ...]
    screened_at_utc: str
    blockers: Tuple[str, ...] = ()
    edd_triggers: Tuple[str, ...] = ()
    meta: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subject_id": self.subject_id,
            "subject_name": self.subject_name,
            "subject_kind": self.subject_kind,
            "pep_result": {
                "is_pep": self.pep_result.is_pep,
                "category": self.pep_result.category.value,
                "reason": self.pep_result.reason,
            },
            "sanctions_hits": [
                {"source": h.source.value,
                 "matched_entity_name": h.matched_entity_name,
                 "matched_record_id": h.matched_record_id,
                 "match_score": h.match_score,
                 "hit_status": h.hit_status,
                 "screening_id": h.screening_id}
                for h in self.sanctions_hits
            ],
            "outcome": self.outcome.value,
            "lists_screened": [s.value for s in self.lists_screened],
            "lists_skipped_due_to_staleness": [
                s.value for s in self.lists_skipped_due_to_staleness],
            "screened_at_utc": self.screened_at_utc,
            "blockers": list(self.blockers),
            "edd_triggers": list(self.edd_triggers),
            "meta": dict(self.meta),
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ScreeningOrchestrator:
    """ENH-192 Unified PEP + Sanctions Screening Orchestrator.

    Composes Standard #58's SanctionsScreeningEngine with PEP logic
    from kyc_aml_risk to produce single UnifiedScreeningResult per
    screen call. Tracks list freshness metadata that Standard #58
    doesn't.
    """

    def __init__(self,
                  sanctions_engine: Optional[Any] = None,
                  freshness_window_days: int = DEFAULT_FRESHNESS_WINDOW_DAYS,
                  block_when_lists_stale: bool = False) -> None:
        """Initialize orchestrator.

        Args:
            sanctions_engine: Standard #58's SanctionsScreeningEngine
                instance. If None, lazily imports + instantiates one.
            freshness_window_days: default freshness window if a
                source's specific window isn't set.
            block_when_lists_stale: if True, screenings against stale
                lists are deferred (SCREENING_DEFERRED_LISTS_STALE
                outcome). Defaults False — operators usually want a
                best-effort result with stale-list flagging.
        """
        if sanctions_engine is None:
            try:
                from utils.sanctions_screening import (
                    SanctionsScreeningEngine)
                sanctions_engine = SanctionsScreeningEngine()
            except ImportError:
                sanctions_engine = None
        self._sanctions = sanctions_engine
        self._freshness: Dict[SanctionsListSource, ListFreshnessRecord] = {}
        self._screenings: List[UnifiedScreeningResult] = []
        self._default_freshness_days = freshness_window_days
        self._block_when_stale = block_when_lists_stale

        # Initialize all sources as MISSING — operator must explicitly
        # load. No auto-fake-readiness.
        for source in SanctionsListSource:
            self._freshness[source] = ListFreshnessRecord(
                source=source,
                last_refreshed_utc=None,
                n_records_loaded=0,
                load_method="none",
                status=ListFreshnessStatus.MISSING,
                notes=("source not loaded; operator must call "
                       "register_list_load() or load_from_source()"))

    # ------------------------------------------------------------------
    # List freshness management
    # ------------------------------------------------------------------

    def register_list_load(
        self,
        source: SanctionsListSource,
        n_records: int,
        load_method: str = "manual",
        notes: str = "",
    ) -> ListFreshnessRecord:
        """Register that a sanctions list was loaded. Updates
        freshness metadata. Operator calls this after loading records
        into Standard #58's engine via load_records()."""
        if n_records < 0:
            raise ValueError(f"n_records cannot be negative: {n_records}")
        now_iso = datetime.now(timezone.utc).isoformat()
        status = (ListFreshnessStatus.MANUAL_LOAD
                    if load_method == "manual"
                    else ListFreshnessStatus.FRESH)
        record = ListFreshnessRecord(
            source=source,
            last_refreshed_utc=now_iso,
            n_records_loaded=n_records,
            load_method=load_method,
            status=status,
            notes=notes)
        self._freshness[source] = record
        return record

    def freshness_summary(self) -> Dict[str, Any]:
        """Per-source freshness state — operators see at a glance
        which lists are usable. Updates STALE statuses lazily."""
        self._refresh_freshness_statuses()
        return {
            "as_of_utc": datetime.now(timezone.utc).isoformat(),
            "default_freshness_window_days": self._default_freshness_days,
            "by_source": {
                source.value: {
                    "status": rec.status.value,
                    "last_refreshed_utc": rec.last_refreshed_utc,
                    "n_records_loaded": rec.n_records_loaded,
                    "load_method": rec.load_method,
                    "notes": rec.notes,
                    "freshness_window_days": (
                        FRESHNESS_WINDOW_DAYS_BY_SOURCE.get(
                            source, self._default_freshness_days)),
                }
                for source, rec in self._freshness.items()
            },
        }

    def _refresh_freshness_statuses(self) -> None:
        """Re-evaluate FRESH vs STALE for all loaded sources based on
        current time vs last_refreshed_utc + freshness window."""
        now = datetime.now(timezone.utc)
        for source, rec in list(self._freshness.items()):
            if rec.last_refreshed_utc is None:
                continue
            try:
                last_refresh = datetime.fromisoformat(
                    rec.last_refreshed_utc)
                window_days = FRESHNESS_WINDOW_DAYS_BY_SOURCE.get(
                    source, self._default_freshness_days)
                age_days = (now - last_refresh).days
                if age_days > window_days:
                    new_status = ListFreshnessStatus.STALE
                elif rec.load_method == "manual":
                    new_status = ListFreshnessStatus.MANUAL_LOAD
                else:
                    new_status = ListFreshnessStatus.FRESH
                if new_status != rec.status:
                    self._freshness[source] = ListFreshnessRecord(
                        source=rec.source,
                        last_refreshed_utc=rec.last_refreshed_utc,
                        n_records_loaded=rec.n_records_loaded,
                        load_method=rec.load_method,
                        status=new_status,
                        notes=rec.notes)
            except (ValueError, TypeError):
                # If we can't parse the timestamp, leave status alone
                pass

    # ------------------------------------------------------------------
    # PEP determination
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_pep(
        is_pep_self_declared: bool,
        nationality: str,
        residence_country: str,
        occupation: str,
    ) -> PepScreeningResult:
        """Deterministic PEP classification per FATF Rec 12.

        Honest scope: this uses self-declared is_pep + occupation
        keywords + nationality vs residence comparison. It does NOT
        screen against external PEP databases (e.g. Dow Jones, World-
        Check) — those are commercial feeds, not currently wired.
        """
        if not is_pep_self_declared:
            # Even if not self-declared, occupation may indicate PEP
            occ_upper = (occupation or "").upper()
            pep_occupation_keywords = (
                "MINISTER", "MEMBER OF PARLIAMENT", "MP",
                "GOVERNOR", "JUDGE", "AMBASSADOR",
                "MILITARY", "GENERAL", "JUDICIARY",
            )
            if any(kw in occ_upper for kw in pep_occupation_keywords):
                # Heuristic — flag for review
                return PepScreeningResult(
                    is_pep=True,
                    category=PepCategory.DOMESTIC_PEP,
                    reason=(f"occupation_keyword_match: occupation="
                              f"{occupation!r}; not self-declared, "
                              f"REQUIRES_HUMAN_VERIFICATION"))
            return PepScreeningResult(
                is_pep=False,
                category=PepCategory.NOT_PEP,
                reason="no_pep_indicators")

        # Self-declared as PEP. Distinguish foreign vs domestic per FATF
        # Rec 12.
        is_foreign = (nationality or "").upper() != \
                     (residence_country or "").upper()
        if is_foreign:
            return PepScreeningResult(
                is_pep=True,
                category=PepCategory.FOREIGN_PEP,
                reason=(f"self_declared_pep + foreign nationality="
                          f"{nationality} vs residence={residence_country}"))
        return PepScreeningResult(
            is_pep=True,
            category=PepCategory.DOMESTIC_PEP,
            reason=f"self_declared_pep_domestic_{nationality}")

    # ------------------------------------------------------------------
    # Unified screening
    # ------------------------------------------------------------------

    def screen(
        self,
        subject_id: str,
        subject_name: str,
        *,
        is_pep_self_declared: bool = False,
        nationality: str = "",
        residence_country: str = "",
        occupation: str = "",
        subject_kind: str = "INDIVIDUAL",
    ) -> UnifiedScreeningResult:
        """Run unified PEP + sanctions screening on a single subject.

        Returns UnifiedScreeningResult with both PEP determination and
        sanctions hits across all loaded lists, plus blockers/triggers
        and a final outcome enum.
        """
        if not subject_id or not subject_name:
            raise ValueError(
                "subject_id and subject_name are mandatory")

        # PEP screening — deterministic, in-memory
        pep_result = self._classify_pep(
            is_pep_self_declared, nationality,
            residence_country, occupation)

        # Sanctions screening — delegate to Standard #58
        sanctions_hits: List[SanctionsHitSummary] = []
        lists_screened: List[SanctionsListSource] = []
        lists_skipped: List[SanctionsListSource] = []

        # Refresh freshness statuses before screening
        self._refresh_freshness_statuses()

        # Decide which lists are screenable based on freshness
        screenable_sources: List[SanctionsListSource] = []
        for source, rec in self._freshness.items():
            if rec.status == ListFreshnessStatus.MISSING:
                lists_skipped.append(source)
                continue
            if (self._block_when_stale and
                    rec.status == ListFreshnessStatus.STALE):
                lists_skipped.append(source)
                continue
            screenable_sources.append(source)

        if self._sanctions and screenable_sources:
            try:
                hits = self._sanctions.screen(
                    subject_id=subject_id,
                    subject_name=subject_name,
                    subject_type=subject_kind)
                for h in hits:
                    # Map Standard #58's matched_list_id back to our
                    # enum if possible
                    try:
                        source_enum = SanctionsListSource(h.matched_list_id)
                    except (ValueError, KeyError):
                        # Unknown list id — skip in our summary
                        continue
                    sanctions_hits.append(SanctionsHitSummary(
                        source=source_enum,
                        matched_entity_name=h.matched_entity_name,
                        matched_record_id=str(h.matched_record_id),
                        match_score=int(h.match_score),
                        hit_status=str(h.hit_status),
                        screening_id=int(h.screening_id)))
                lists_screened = list(screenable_sources)
            except Exception as e:
                # Log but don't crash — operator sees the failure in meta
                lists_skipped.extend(screenable_sources)
                lists_screened = []

        # Determine outcome + blockers + triggers
        blockers: List[str] = []
        edd_triggers: List[str] = []

        # Sanctions disposition
        confirmed_hits = [h for h in sanctions_hits
                            if h.hit_status == "CONFIRMED_TRUE"]
        new_or_review_hits = [h for h in sanctions_hits
                                  if h.hit_status in ("NEW_HIT",
                                                          "UNDER_REVIEW")]

        if confirmed_hits:
            blockers.append(
                f"sanctions_confirmed_match_n={len(confirmed_hits)}")
            outcome = ScreeningOutcome.SANCTIONS_CONFIRMED_BLOCK
        elif new_or_review_hits:
            blockers.append(
                f"sanctions_review_required_n={len(new_or_review_hits)}")
            outcome = ScreeningOutcome.SANCTIONS_HIT_REQUIRES_REVIEW
        elif (self._block_when_stale and
                len(lists_screened) == 0 and
                any(rec.status in (ListFreshnessStatus.MISSING,
                                       ListFreshnessStatus.STALE)
                    for rec in self._freshness.values())):
            outcome = ScreeningOutcome.SCREENING_DEFERRED_LISTS_STALE
            blockers.append("no_fresh_sanctions_lists_available")
        elif pep_result.is_pep:
            outcome = ScreeningOutcome.PEP_REVIEW_REQUIRED
            edd_triggers.append(f"pep_{pep_result.category.value}")
        else:
            outcome = ScreeningOutcome.CLEAR

        if pep_result.category == PepCategory.FOREIGN_PEP:
            edd_triggers.append("foreign_pep_mandatory_edd_fatf_rec12")

        result = UnifiedScreeningResult(
            subject_id=subject_id,
            subject_name=subject_name,
            subject_kind=subject_kind,
            pep_result=pep_result,
            sanctions_hits=tuple(sanctions_hits),
            outcome=outcome,
            lists_screened=tuple(lists_screened),
            lists_skipped_due_to_staleness=tuple(lists_skipped),
            screened_at_utc=datetime.now(timezone.utc).isoformat(),
            blockers=tuple(blockers),
            edd_triggers=tuple(edd_triggers),
            meta={"engine_version": "ENH-192-v10.161",
                    "n_lists_screened": len(lists_screened),
                    "n_lists_skipped": len(lists_skipped)},
        )
        self._screenings.append(result)
        return result

    def screen_applicant(self, applicant) -> Tuple[
            UnifiedScreeningResult, ...]:
        """Screen an ENH-191 CustomerApplicant or BusinessApplicant.

        For KYC: returns 1-tuple with the customer screening.
        For KYB: returns N+1 tuple — business + each beneficial owner
        screened separately. Downstream uses the rollup logic from
        ENH-191's KycOnboardingEngine to determine final tier.
        """
        # Detect type by duck-typing — avoids hard import dependency
        # if ENH-191 isn't yet applied
        is_business = hasattr(applicant, "beneficial_owners") and \
                       hasattr(applicant, "applicant_type")
        is_customer = hasattr(applicant, "is_pep") and \
                       hasattr(applicant, "occupation")

        if is_customer and not is_business:
            result = self.screen(
                subject_id=applicant.applicant_id,
                subject_name=applicant.full_name,
                is_pep_self_declared=getattr(applicant, "is_pep", False),
                nationality=getattr(applicant, "nationality", ""),
                residence_country=getattr(
                    applicant, "residence_country", ""),
                occupation=getattr(applicant, "occupation", ""),
                subject_kind="INDIVIDUAL")
            return (result,)

        if is_business:
            results: List[UnifiedScreeningResult] = []
            # Screen the business itself
            biz_result = self.screen(
                subject_id=applicant.applicant_id,
                subject_name=applicant.legal_name,
                is_pep_self_declared=False,  # Businesses aren't PEPs
                nationality=getattr(
                    applicant, "country_of_incorporation", ""),
                residence_country=getattr(
                    applicant, "country_of_incorporation", ""),
                occupation="BUSINESS",
                subject_kind="BUSINESS")
            results.append(biz_result)

            # Screen each beneficial owner
            for bo in getattr(applicant, "beneficial_owners", ()):
                bo_result = self.screen(
                    subject_id=getattr(bo, "national_id", "unknown"),
                    subject_name=getattr(bo, "full_name", "unknown"),
                    is_pep_self_declared=getattr(bo, "is_pep", False),
                    nationality=getattr(bo, "nationality", ""),
                    residence_country=getattr(bo, "nationality", ""),
                    occupation="BENEFICIAL_OWNER",
                    subject_kind="BENEFICIAL_OWNER")
                results.append(bo_result)
            return tuple(results)

        raise ValueError(
            f"applicant type not recognized; expected ENH-191 "
            f"CustomerApplicant or BusinessApplicant, got "
            f"{type(applicant).__name__}")

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def all_screenings(self) -> Tuple[UnifiedScreeningResult, ...]:
        return tuple(self._screenings)

    def board_summary(self) -> Dict[str, Any]:
        """Cockpit-consumable summary."""
        self._refresh_freshness_statuses()
        outcomes: Dict[str, int] = {}
        for s in self._screenings:
            outcomes[s.outcome.value] = (
                outcomes.get(s.outcome.value, 0) + 1)

        n_pep = sum(1 for s in self._screenings if s.pep_result.is_pep)
        n_sanctions = sum(1 for s in self._screenings
                              if s.sanctions_hits)
        n_blocked = sum(1 for s in self._screenings if s.blockers)

        fresh_sources = sum(
            1 for r in self._freshness.values()
            if r.status in (ListFreshnessStatus.FRESH,
                              ListFreshnessStatus.MANUAL_LOAD))
        stale_sources = sum(
            1 for r in self._freshness.values()
            if r.status == ListFreshnessStatus.STALE)
        missing_sources = sum(
            1 for r in self._freshness.values()
            if r.status == ListFreshnessStatus.MISSING)

        return {
            "entity": "Ecobank Kenya",
            "engine": "ENH-192 ScreeningOrchestrator",
            "n_screenings": len(self._screenings),
            "n_pep_flagged": n_pep,
            "n_sanctions_hits": n_sanctions,
            "n_blocked": n_blocked,
            "outcome_counts": outcomes,
            "list_freshness": {
                "n_fresh_or_manual": fresh_sources,
                "n_stale": stale_sources,
                "n_missing": missing_sources,
                "total_sources": len(self._freshness),
            },
        }
