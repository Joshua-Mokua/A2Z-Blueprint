"""
================================================================================
A2Z MIS 360 — Standard #367: Segment-Specific KPI Library
================================================================================

Risk classification: Cat B (deterministic KPI catalog)

Curated catalog of per-segment KPIs with formula contracts. Each KPI
is a frozen descriptor specifying the formula, data sources, target
direction (max/min), and the rule for computing actual value.

Public API:
    list_segment_kpis(segment_code) -> [KpiDescriptor dicts]
    get_kpi(kpi_id) -> KpiDescriptor or None
    register_custom_kpi(segment_code, kpi_config, actor, reason)
    kpi_catalog_summary() -> per-segment counts + total

KPI categories per Continuation.docx #367:
    WOMEN     -- financial inclusion + business growth
    DIASPORA  -- remittance volume + investment uptake
    ASSET_FIN -- asset deployment efficiency + collateral coverage
    AGRI      -- crop calendar adherence + insurance penetration
    YOUTH     -- digital adoption + financial-literacy completion
    SME       -- working-capital cycle + asset-light vs asset-heavy mix

KPI directions byte-for-byte:
    MAX -- higher is better (e.g. inclusion rate, completion %)
    MIN -- lower is better (e.g. dropout rate, NPL ratio)

KPI formula types byte-for-byte:
    RATIO          -- numerator / denominator × scale
    COUNT          -- absolute count of qualifying records
    SUM            -- aggregated amount over period
    AVERAGE        -- mean of qualifying values
    PERCENTILE     -- Pn of distribution

Honesty rules:
    Rule 6: invalid segment_code or kpi_id rejected
    Rule 4: actor + reason required for custom KPI registration

================================================================================
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.specialized_segments_tagging import SEGMENT_CODES


# ────────────────────────────────────────────────────────────────────
# Catalogs — byte-for-byte
# ────────────────────────────────────────────────────────────────────

KPI_DIRECTIONS: Tuple[str, ...] = ("MAX", "MIN")

KPI_FORMULA_TYPES: Tuple[str, ...] = (
    "RATIO", "COUNT", "SUM", "AVERAGE", "PERCENTILE",
)


@dataclass(frozen=True)
class KpiDescriptor:
    kpi_id: str
    segment_code: str
    name: str
    description: str
    formula_type: str
    direction: str
    target_value: Optional[Decimal] = None
    target_unit: str = ""
    numerator_source: str = ""
    denominator_source: str = ""
    rationale: str = ""


# ────────────────────────────────────────────────────────────────────
# Default segment-specific KPI library — byte-for-byte
# ────────────────────────────────────────────────────────────────────

DEFAULT_SEGMENT_KPIS: Dict[str, Tuple[KpiDescriptor, ...]] = {
    "WOMEN": (
        KpiDescriptor(
            kpi_id="W-INC-001",
            segment_code="WOMEN",
            name="Financial Inclusion Rate",
            description="Active women customers / total women in catchment",
            formula_type="RATIO",
            direction="MAX",
            target_value=Decimal("60"),
            target_unit="percent",
            numerator_source="tagging.active_count(WOMEN)",
            denominator_source="external.women_population_estimate",
            rationale="UN SDG 5 alignment + IFC inclusive finance benchmark",
        ),
        KpiDescriptor(
            kpi_id="W-BIZ-001",
            segment_code="WOMEN",
            name="Women-Owned Business Loan Growth",
            description="Period-over-period growth in WOMEN business loan book",
            formula_type="RATIO",
            direction="MAX",
            target_value=Decimal("15"),
            target_unit="percent_yoy",
            rationale="Track women's business growth proposition uptake",
        ),
        KpiDescriptor(
            kpi_id="W-NPL-001",
            segment_code="WOMEN",
            name="Women Segment NPL Ratio",
            description="Non-performing loans / total WOMEN loan book",
            formula_type="RATIO",
            direction="MIN",
            target_value=Decimal("3"),
            target_unit="percent",
            rationale="Quality control on inclusive lending",
        ),
    ),
    "DIASPORA": (
        KpiDescriptor(
            kpi_id="D-REM-001",
            segment_code="DIASPORA",
            name="Diaspora Remittance Volume",
            description="Total inbound remittance value through DIASPORA accounts",
            formula_type="SUM",
            direction="MAX",
            target_unit="kes_thousands",
            rationale="Key revenue + relationship indicator",
        ),
        KpiDescriptor(
            kpi_id="D-INV-001",
            segment_code="DIASPORA",
            name="Diaspora Investment Uptake",
            description="DIASPORA customers holding investment products / total DIASPORA",
            formula_type="RATIO",
            direction="MAX",
            target_value=Decimal("25"),
            target_unit="percent",
            rationale="Cross-sell depth indicator",
        ),
        KpiDescriptor(
            kpi_id="D-MTG-001",
            segment_code="DIASPORA",
            name="Diaspora Mortgage Origination",
            description="New diaspora mortgage book per period",
            formula_type="SUM",
            direction="MAX",
            target_unit="kes_millions",
        ),
    ),
    "ASSET_FINANCE": (
        KpiDescriptor(
            kpi_id="AF-LTV-001",
            segment_code="ASSET_FINANCE",
            name="Loan-to-Value Adherence",
            description="LTV at origination vs policy max",
            formula_type="AVERAGE",
            direction="MIN",
            target_value=Decimal("80"),
            target_unit="percent",
            rationale="Collateral coverage discipline",
        ),
        KpiDescriptor(
            kpi_id="AF-DEPLOY-001",
            segment_code="ASSET_FINANCE",
            name="Asset Deployment Period",
            description="Days from approval to asset delivery",
            formula_type="AVERAGE",
            direction="MIN",
            target_value=Decimal("21"),
            target_unit="days",
            rationale="Operational efficiency indicator",
        ),
    ),
    "AGRI": (
        KpiDescriptor(
            kpi_id="AG-CAL-001",
            segment_code="AGRI",
            name="Crop Calendar Adherence",
            description="Loans disbursed within crop-calendar window / total agri loans",
            formula_type="RATIO",
            direction="MAX",
            target_value=Decimal("90"),
            target_unit="percent",
            rationale="Mistimed disbursements miss the production cycle",
        ),
        KpiDescriptor(
            kpi_id="AG-INS-001",
            segment_code="AGRI",
            name="Insurance Penetration",
            description="Agri customers with weather-indexed insurance / total agri",
            formula_type="RATIO",
            direction="MAX",
            target_value=Decimal("50"),
            target_unit="percent",
        ),
    ),
    "YOUTH": (
        KpiDescriptor(
            kpi_id="Y-DIG-001",
            segment_code="YOUTH",
            name="Digital Adoption Rate",
            description="YOUTH customers active on mobile/web / total YOUTH",
            formula_type="RATIO",
            direction="MAX",
            target_value=Decimal("85"),
            target_unit="percent",
            rationale="Mobile-first proposition discipline",
        ),
        KpiDescriptor(
            kpi_id="Y-LIT-001",
            segment_code="YOUTH",
            name="Financial Literacy Completion",
            description="YOUTH customers completing literacy module / enrolled",
            formula_type="RATIO",
            direction="MAX",
            target_value=Decimal("60"),
            target_unit="percent",
        ),
        KpiDescriptor(
            kpi_id="Y-DROP-001",
            segment_code="YOUTH",
            name="Account Dormancy Rate",
            description="YOUTH accounts dormant 90+ days / total YOUTH accounts",
            formula_type="RATIO",
            direction="MIN",
            target_value=Decimal("15"),
            target_unit="percent",
        ),
    ),
    "SME": (
        KpiDescriptor(
            kpi_id="SME-WC-001",
            segment_code="SME",
            name="Working Capital Cycle Days",
            description="Average days customer receivables outstanding",
            formula_type="AVERAGE",
            direction="MIN",
            target_value=Decimal("45"),
            target_unit="days",
        ),
        KpiDescriptor(
            kpi_id="SME-MIX-001",
            segment_code="SME",
            name="Asset-Heavy Loan Share",
            description="Asset-finance SME loans / total SME loan book",
            formula_type="RATIO",
            direction="MAX",
            target_value=Decimal("40"),
            target_unit="percent",
        ),
    ),
}


# ────────────────────────────────────────────────────────────────────
# Engine
# ────────────────────────────────────────────────────────────────────

class SegmentKpiLibrary:
    """Catalog of per-segment KPIs (default + custom)."""

    def __init__(self, custom_kpis_path: Optional[Path] = None):
        self.custom_kpis_path = (
            custom_kpis_path
            if custom_kpis_path is not None
            else Path(__file__).parent.parent / "data" / "segment_custom_kpis.json"
        )

    def _load_custom(self) -> Dict[str, List[Dict[str, Any]]]:
        try:
            from utils.db import db as _db   # singleton Database instance
            records = _db.dual_load(
                self.custom_kpis_path,
                table="segment_custom_kpis",
                index_cols=("kpi_id",))
            if not isinstance(records, list):
                return {}
            from collections import defaultdict
            by_segment: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for r in records:
                sc = r.get("segment_code")
                if sc:
                    by_segment[sc].append(r)
            return dict(by_segment)
        except Exception:
            return {}

    def _save_custom(self, data: Dict[str, List[Dict[str, Any]]]) -> bool:
        try:
            from utils.db import db as _db   # singleton Database instance
            self.custom_kpis_path.parent.mkdir(parents=True, exist_ok=True)
            flat: List[Dict[str, Any]] = []
            for sc, records in data.items():
                for r in records:
                    rec = dict(r)
                    rec["segment_code"] = sc
                    flat.append(rec)
            _db.dual_save(
                self.custom_kpis_path,
                data=flat,
                table="segment_custom_kpis",
                pk_col="kpi_id")
            return True
        except Exception:
            return False

    def list_segment_kpis(self, segment_code: str) -> List[Dict[str, Any]]:
        """Return default + custom KPIs for a segment."""
        if segment_code not in SEGMENT_CODES:
            return []

        out = []
        for kpi in DEFAULT_SEGMENT_KPIS.get(segment_code, ()):
            d = asdict(kpi)
            if d.get("target_value") is not None:
                d["target_value"] = str(d["target_value"])
            d["source"] = "default_catalog"
            out.append(d)

        custom = self._load_custom().get(segment_code, [])
        for c in custom:
            entry = dict(c)
            entry["source"] = "custom_catalog"
            out.append(entry)

        return out

    def get_kpi(self, kpi_id: str) -> Optional[Dict[str, Any]]:
        """Lookup a single KPI by id across all segments."""
        for sc in SEGMENT_CODES:
            for kpi in self.list_segment_kpis(sc):
                if kpi.get("kpi_id") == kpi_id:
                    return kpi
        return None

    def register_custom_kpi(
        self,
        segment_code: str,
        kpi_config: Dict[str, Any],
        actor: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Register custom KPI for a segment."""
        if segment_code not in SEGMENT_CODES:
            return {"registered": False, "error": f"invalid_segment:{segment_code}"}
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}

        for f in ("kpi_id", "name", "formula_type", "direction"):
            if f not in kpi_config or not kpi_config[f]:
                return {"registered": False, "error": f"missing_field:{f}"}

        if kpi_config["formula_type"] not in KPI_FORMULA_TYPES:
            return {
                "registered": False,
                "error": f"invalid_formula_type:{kpi_config['formula_type']}",
            }
        if kpi_config["direction"] not in KPI_DIRECTIONS:
            return {
                "registered": False,
                "error": f"invalid_direction:{kpi_config['direction']}",
            }

        # Reject duplicate kpi_id (across all segments)
        if self.get_kpi(kpi_config["kpi_id"]) is not None:
            return {"registered": False, "error": "duplicate_kpi_id"}

        custom = self._load_custom()
        seg_list = custom.get(segment_code, [])
        record = dict(kpi_config)
        record["segment_code"] = segment_code
        record["registered_by"] = actor
        record["registered_at"] = datetime.utcnow().isoformat()
        record["reason"] = reason
        seg_list.append(record)
        custom[segment_code] = seg_list
        ok = self._save_custom(custom)
        return {
            "registered": ok,
            "kpi_id": kpi_config["kpi_id"],
            "segment_code": segment_code,
        }

    def kpi_catalog_summary(self) -> Dict[str, Any]:
        """Per-segment KPI counts + total."""
        out: Dict[str, Dict[str, int]] = {}
        total = 0
        for sc in SEGMENT_CODES:
            kpis = self.list_segment_kpis(sc)
            default_n = sum(1 for k in kpis if k["source"] == "default_catalog")
            custom_n = sum(1 for k in kpis if k["source"] == "custom_catalog")
            out[sc] = {
                "default": default_n,
                "custom": custom_n,
                "total": default_n + custom_n,
            }
            total += default_n + custom_n
        return {
            "by_segment": out,
            "total_kpis": total,
        }


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        lib = SegmentKpiLibrary(custom_kpis_path=Path(tmpdir) / "custom_kpis.json")

        # Test 1: list default WOMEN KPIs
        women_kpis = lib.list_segment_kpis("WOMEN")
        assert len(women_kpis) == 3
        ids = {k["kpi_id"] for k in women_kpis}
        assert ids == {"W-INC-001", "W-BIZ-001", "W-NPL-001"}

        # Test 2: lookup specific KPI
        kpi = lib.get_kpi("W-INC-001")
        assert kpi is not None
        assert kpi["direction"] == "MAX"
        assert kpi["target_value"] == "60"

        # Test 3: unknown KPI returns None
        assert lib.get_kpi("UNKNOWN") is None

        # Test 4: Rule 6 — invalid segment returns []
        assert lib.list_segment_kpis("INVALID") == []

        # Test 5: register custom KPI
        result = lib.register_custom_kpi(
            "WOMEN",
            {
                "kpi_id": "W-CUSTOM-001",
                "name": "Custom KPI",
                "formula_type": "RATIO",
                "direction": "MAX",
                "target_value": "50",
            },
            actor="cfo", reason="board mandate",
        )
        assert result["registered"], result

        # Test 6: invalid formula_type rejected
        bad = lib.register_custom_kpi(
            "WOMEN",
            {
                "kpi_id": "W-BAD-001",
                "name": "Bad",
                "formula_type": "INVALID",
                "direction": "MAX",
            },
            actor="cfo", reason="test",
        )
        assert not bad["registered"]
        assert "invalid_formula_type" in bad["error"]

        # Test 7: duplicate kpi_id rejected
        dup = lib.register_custom_kpi(
            "DIASPORA",  # different segment, but same id
            {
                "kpi_id": "W-CUSTOM-001",
                "name": "Dup",
                "formula_type": "COUNT",
                "direction": "MAX",
            },
            actor="cfo", reason="test",
        )
        assert not dup["registered"]
        assert dup["error"] == "duplicate_kpi_id"

        # Test 8: actor + reason required (Rule 4)
        missing_actor = lib.register_custom_kpi(
            "WOMEN",
            {"kpi_id": "X-001", "name": "X", "formula_type": "COUNT", "direction": "MAX"},
            actor="", reason="",
        )
        assert not missing_actor["registered"]

        # Test 9: catalog summary includes custom + defaults
        summary = lib.kpi_catalog_summary()
        assert summary["by_segment"]["WOMEN"]["default"] == 3
        assert summary["by_segment"]["WOMEN"]["custom"] == 1
        assert summary["by_segment"]["WOMEN"]["total"] == 4
        # Total across segments
        assert summary["total_kpis"] >= 14

    print("  ✅ segment_kpi_library self-test PASS")


if __name__ == "__main__":
    _self_test()
