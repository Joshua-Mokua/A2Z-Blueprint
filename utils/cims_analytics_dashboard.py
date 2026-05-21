"""
================================================================================
A2Z MIS 360 — Standard #179: CIMS Performance Analytics Dashboard
================================================================================

Risk classification: Cat C (read-side aggregation; never modifies
upstream metrics; surfaces composed KPIs and trend snapshots only).

Subcategory: cims

Executive dashboard with KPIs and trends across the entire CIMS arc.
Composes upstream capture (#166), classification (#167), STP (#168),
identity (#173), process intelligence (#169), dropout prevention
(#170), NBA (#174), exception management (#175), regulatory SLA
(#171), secure docs (#172), audit history (#176), agent workspace
(#178), and self-service portal (#177) — registers KPI definitions
and observation snapshots, never writes to upstream tables.

Public API:
    register_kpi_definition(definition_data, actor, reason)
    transition_definition_state(definition_id, new_state, actor, reason)
    record_kpi_observation(observation_data, actor)
    register_trend_snapshot(snapshot_data, actor, reason)
    register_executive_view(view_data, actor, reason)
    kpi_status_report(definition_id, days=30) -> Dict
    dashboard_summary() -> Dict

KPI_DOMAINS byte-for-byte (8):
    CAPTURE, CLASSIFICATION, STP, IDENTITY, PROCESS,
    EXCEPTIONS, COMPLIANCE, AGENT_WORKSPACE

KPI_DEFINITION_STATES byte-for-byte (4):
    DRAFT, ACTIVE, DEPRECATED, ARCHIVED

ALLOWED_DEFINITION_TRANSITIONS (Rule 4):
    DRAFT      → ACTIVE | ARCHIVED
    ACTIVE     → DEPRECATED | ARCHIVED
    DEPRECATED → ARCHIVED
    ARCHIVED   → ()

KPI_FREQUENCIES byte-for-byte (5):
    REAL_TIME, HOURLY, DAILY, WEEKLY, MONTHLY

KPI_DIRECTIONS byte-for-byte (3):
    HIGHER_IS_BETTER, LOWER_IS_BETTER, ON_TARGET

KPI_STATUS_BANDS byte-for-byte (4):
    GREEN, AMBER, RED, NO_DATA

EXECUTIVE_VIEW_TYPES byte-for-byte (5):
    BOARD_PACK, MD_DAILY, COO_OPERATIONS, CCO_COMPLIANCE,
    HEAD_OF_CIMS

TREND_DIRECTIONS byte-for-byte (4):
    IMPROVING, STABLE, DETERIORATING, INSUFFICIENT_DATA

DEFAULT_GREEN_AMBER_BUFFER_PCT = 5
DEFAULT_AMBER_RED_BUFFER_PCT = 15
DEFAULT_TREND_MIN_OBSERVATIONS = 5

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


KPI_DOMAINS: Tuple[str, ...] = (
    "CAPTURE", "CLASSIFICATION", "STP", "IDENTITY",
    "PROCESS", "EXCEPTIONS", "COMPLIANCE", "AGENT_WORKSPACE",
)

KPI_DEFINITION_STATES: Tuple[str, ...] = (
    "DRAFT", "ACTIVE", "DEPRECATED", "ARCHIVED",
)

ALLOWED_DEFINITION_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "DRAFT":      ("ACTIVE", "ARCHIVED"),
    "ACTIVE":     ("DEPRECATED", "ARCHIVED"),
    "DEPRECATED": ("ARCHIVED",),
    "ARCHIVED":   (),
}

KPI_FREQUENCIES: Tuple[str, ...] = (
    "REAL_TIME", "HOURLY", "DAILY", "WEEKLY", "MONTHLY",
)

KPI_DIRECTIONS: Tuple[str, ...] = (
    "HIGHER_IS_BETTER", "LOWER_IS_BETTER", "ON_TARGET",
)

KPI_STATUS_BANDS: Tuple[str, ...] = (
    "GREEN", "AMBER", "RED", "NO_DATA",
)

EXECUTIVE_VIEW_TYPES: Tuple[str, ...] = (
    "BOARD_PACK", "MD_DAILY", "COO_OPERATIONS",
    "CCO_COMPLIANCE", "HEAD_OF_CIMS",
)

TREND_DIRECTIONS: Tuple[str, ...] = (
    "IMPROVING", "STABLE", "DETERIORATING", "INSUFFICIENT_DATA",
)

DEFAULT_GREEN_AMBER_BUFFER_PCT = 5
DEFAULT_AMBER_RED_BUFFER_PCT = 15
DEFAULT_TREND_MIN_OBSERVATIONS = 5


def _classify_status(
    actual: float, target: float, direction: str,
) -> str:
    """Classify a KPI observation into GREEN/AMBER/RED/NO_DATA."""
    if target == 0 and direction != "LOWER_IS_BETTER":
        return "NO_DATA"
    green_buffer = DEFAULT_GREEN_AMBER_BUFFER_PCT / 100
    amber_buffer = DEFAULT_AMBER_RED_BUFFER_PCT / 100
    if direction == "HIGHER_IS_BETTER":
        green_threshold = target * (1 - green_buffer)
        amber_threshold = target * (1 - amber_buffer)
        if actual >= green_threshold:
            return "GREEN"
        if actual >= amber_threshold:
            return "AMBER"
        return "RED"
    if direction == "LOWER_IS_BETTER":
        if target == 0:
            return "GREEN" if actual == 0 else "AMBER"
        green_threshold = target * (1 + green_buffer)
        amber_threshold = target * (1 + amber_buffer)
        if actual <= green_threshold:
            return "GREEN"
        if actual <= amber_threshold:
            return "AMBER"
        return "RED"
    # ON_TARGET — within ±5% green, ±15% amber, else red
    if target == 0:
        return "NO_DATA"
    diff_pct = abs(actual - target) / target
    if diff_pct <= green_buffer:
        return "GREEN"
    if diff_pct <= amber_buffer:
        return "AMBER"
    return "RED"


class CIMSAnalyticsDashboardEngine:
    """KPI definition + observation + trend + executive view registry."""

    def __init__(
        self,
        definitions_path: Optional[Path] = None,
        observations_path: Optional[Path] = None,
        trends_path: Optional[Path] = None,
        views_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.definitions_path = (
            definitions_path or base / "cims_kpi_definitions.json"
        )
        self.observations_path = (
            observations_path or base / "cims_kpi_observations.json"
        )
        self.trends_path = (
            trends_path or base / "cims_trend_snapshots.json"
        )
        self.views_path = (
            views_path or base / "cims_executive_views.json"
        )

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

    def register_kpi_definition(
        self, definition_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("definition_id", "name", "domain",
                      "frequency", "direction", "target"):
            if f not in definition_data or definition_data[f] in (None, ""):
                return {"registered": False, "error": f"missing_field:{f}"}
        if definition_data["domain"] not in KPI_DOMAINS:
            return {"registered": False,
                       "error": f"invalid_domain:{definition_data['domain']}"}
        if definition_data["frequency"] not in KPI_FREQUENCIES:
            return {"registered": False,
                       "error": f"invalid_frequency:{definition_data['frequency']}"}
        if definition_data["direction"] not in KPI_DIRECTIONS:
            return {"registered": False,
                       "error": f"invalid_direction:{definition_data['direction']}"}
        try:
            target = float(definition_data["target"])
        except (TypeError, ValueError):
            return {"registered": False, "error": "target_not_numeric"}
        records = self._load(self.definitions_path,
                                "cims_kpi_definitions",
                                ("definition_id",))
        if any(r.get("definition_id") == definition_data["definition_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_definition_id"}
        record = {
            "definition_id": definition_data["definition_id"],
            "name": definition_data["name"],
            "domain": definition_data["domain"],
            "frequency": definition_data["frequency"],
            "direction": definition_data["direction"],
            "target": target,
            "unit": definition_data.get("unit", ""),
            "narrative": definition_data.get("narrative", ""),
            "state": "DRAFT",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "DRAFT", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.definitions_path, records,
                          "cims_kpi_definitions", "definition_id")
        return {"registered": ok,
                  "definition_id": definition_data["definition_id"]}

    def transition_definition_state(
        self, definition_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in KPI_DEFINITION_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.definitions_path,
                                "cims_kpi_definitions",
                                ("definition_id",))
        for r in records:
            if r.get("definition_id") == definition_id:
                current = r.get("state", "DRAFT")
                allowed = ALLOWED_DEFINITION_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.definitions_path, records,
                                  "cims_kpi_definitions", "definition_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "definition_not_found"}

    def record_kpi_observation(
        self, observation_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("observation_id", "definition_id", "actual"):
            if f not in observation_data or observation_data[f] in (None, ""):
                return {"recorded": False, "error": f"missing_field:{f}"}
        try:
            actual = float(observation_data["actual"])
        except (TypeError, ValueError):
            return {"recorded": False, "error": "actual_not_numeric"}
        # Look up the definition
        defs = self._load(self.definitions_path,
                              "cims_kpi_definitions", ("definition_id",))
        defn = next((d for d in defs
                          if d.get("definition_id")
                              == observation_data["definition_id"]), None)
        if defn is None:
            return {"recorded": False,
                       "error": "definition_not_found"}
        target = float(defn.get("target", 0))
        direction = defn.get("direction", "ON_TARGET")
        status = _classify_status(actual, target, direction)
        records = self._load(self.observations_path,
                                "cims_kpi_observations",
                                ("observation_id",))
        if any(r.get("observation_id") == observation_data["observation_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_observation_id"}
        record = {
            "observation_id": observation_data["observation_id"],
            "definition_id": observation_data["definition_id"],
            "actual": actual,
            "target": target,
            "direction": direction,
            "status": status,
            "narrative": observation_data.get("narrative", ""),
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.observations_path, records,
                          "cims_kpi_observations", "observation_id")
        return {"recorded": ok,
                  "observation_id": observation_data["observation_id"],
                  "status": status}

    def register_trend_snapshot(
        self, snapshot_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("snapshot_id", "definition_id",
                      "trend_direction", "narrative"):
            if f not in snapshot_data or not snapshot_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if snapshot_data["trend_direction"] not in TREND_DIRECTIONS:
            return {"registered": False,
                       "error": f"invalid_trend_direction:{snapshot_data['trend_direction']}"}
        records = self._load(self.trends_path,
                                "cims_trend_snapshots", ("snapshot_id",))
        if any(r.get("snapshot_id") == snapshot_data["snapshot_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_snapshot_id"}
        record = {
            "snapshot_id": snapshot_data["snapshot_id"],
            "definition_id": snapshot_data["definition_id"],
            "trend_direction": snapshot_data["trend_direction"],
            "narrative": snapshot_data["narrative"],
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.trends_path, records,
                          "cims_trend_snapshots", "snapshot_id")
        return {"registered": ok,
                  "snapshot_id": snapshot_data["snapshot_id"]}

    def register_executive_view(
        self, view_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("view_id", "view_type", "title"):
            if f not in view_data or not view_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if view_data["view_type"] not in EXECUTIVE_VIEW_TYPES:
            return {"registered": False,
                       "error": f"invalid_view_type:{view_data['view_type']}"}
        records = self._load(self.views_path,
                                "cims_executive_views", ("view_id",))
        if any(r.get("view_id") == view_data["view_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_view_id"}
        record = {
            "view_id": view_data["view_id"],
            "view_type": view_data["view_type"],
            "title": view_data["title"],
            "kpi_definition_ids": view_data.get(
                "kpi_definition_ids", [],
            ),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.views_path, records,
                          "cims_executive_views", "view_id")
        return {"registered": ok, "view_id": view_data["view_id"]}

    def kpi_status_report(
        self, definition_id: str, days: int = 30,
    ) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        observations = [
            o for o in self._load(self.observations_path,
                                            "cims_kpi_observations",
                                            ("observation_id",))
            if o.get("definition_id") == definition_id
                 and o.get("recorded_at", "") >= cutoff
        ]
        if not observations:
            return {
                "definition_id": definition_id,
                "window_days": days,
                "observation_count": 0,
                "current_status": "NO_DATA",
                "trend_direction": "INSUFFICIENT_DATA",
            }
        observations.sort(key=lambda x: x.get("recorded_at", ""))
        latest = observations[-1]
        per_status: Dict[str, int] = {}
        for o in observations:
            s = o.get("status", "")
            per_status[s] = per_status.get(s, 0) + 1
        # Trend: compare first half avg vs second half avg
        if len(observations) < DEFAULT_TREND_MIN_OBSERVATIONS:
            trend = "INSUFFICIENT_DATA"
        else:
            half = len(observations) // 2
            first_avg = (
                sum(o.get("actual", 0) for o in observations[:half])
                / half
            )
            second_avg = (
                sum(o.get("actual", 0) for o in observations[half:])
                / (len(observations) - half)
            )
            direction = latest.get("direction", "ON_TARGET")
            if direction == "HIGHER_IS_BETTER":
                trend = (
                    "IMPROVING" if second_avg > first_avg
                    else "DETERIORATING" if second_avg < first_avg
                    else "STABLE"
                )
            elif direction == "LOWER_IS_BETTER":
                trend = (
                    "IMPROVING" if second_avg < first_avg
                    else "DETERIORATING" if second_avg > first_avg
                    else "STABLE"
                )
            else:
                trend = "STABLE"
        return {
            "definition_id": definition_id,
            "window_days": days,
            "observation_count": len(observations),
            "latest_actual": latest.get("actual"),
            "latest_status": latest.get("status"),
            "current_status": latest.get("status"),
            "trend_direction": trend,
            "per_status": per_status,
        }

    def dashboard_summary(self) -> Dict[str, Any]:
        defs = self._load(self.definitions_path,
                              "cims_kpi_definitions", ("definition_id",))
        observations = self._load(self.observations_path,
                                              "cims_kpi_observations",
                                              ("observation_id",))
        views = self._load(self.views_path,
                                "cims_executive_views", ("view_id",))
        trends = self._load(self.trends_path,
                                  "cims_trend_snapshots", ("snapshot_id",))
        per_domain: Dict[str, int] = {}
        for d in defs:
            dom = d.get("domain", "")
            per_domain[dom] = per_domain.get(dom, 0) + 1
        per_view_type: Dict[str, int] = {}
        for v in views:
            vt = v.get("view_type", "")
            per_view_type[vt] = per_view_type.get(vt, 0) + 1
        return {
            "kpi_definitions": len(defs),
            "kpi_observations": len(observations),
            "executive_views": len(views),
            "trend_snapshots": len(trends),
            "per_domain": per_domain,
            "per_view_type": per_view_type,
        }


def _self_test() -> None:
    import tempfile

    assert KPI_DOMAINS == (
        "CAPTURE", "CLASSIFICATION", "STP", "IDENTITY",
        "PROCESS", "EXCEPTIONS", "COMPLIANCE",
        "AGENT_WORKSPACE",
    )
    assert KPI_DEFINITION_STATES == (
        "DRAFT", "ACTIVE", "DEPRECATED", "ARCHIVED",
    )
    assert ALLOWED_DEFINITION_TRANSITIONS["ARCHIVED"] == ()
    assert KPI_FREQUENCIES == (
        "REAL_TIME", "HOURLY", "DAILY", "WEEKLY", "MONTHLY",
    )
    assert KPI_DIRECTIONS == (
        "HIGHER_IS_BETTER", "LOWER_IS_BETTER", "ON_TARGET",
    )
    assert KPI_STATUS_BANDS == ("GREEN", "AMBER", "RED", "NO_DATA")
    assert EXECUTIVE_VIEW_TYPES == (
        "BOARD_PACK", "MD_DAILY", "COO_OPERATIONS",
        "CCO_COMPLIANCE", "HEAD_OF_CIMS",
    )
    assert TREND_DIRECTIONS == (
        "IMPROVING", "STABLE", "DETERIORATING",
        "INSUFFICIENT_DATA",
    )
    assert DEFAULT_GREEN_AMBER_BUFFER_PCT == 5
    assert DEFAULT_AMBER_RED_BUFFER_PCT == 15
    assert DEFAULT_TREND_MIN_OBSERVATIONS == 5

    # Status classification
    assert _classify_status(100, 100, "HIGHER_IS_BETTER") == "GREEN"
    assert _classify_status(96, 100, "HIGHER_IS_BETTER") == "GREEN"  # 4% off
    assert _classify_status(90, 100, "HIGHER_IS_BETTER") == "AMBER"  # 10% off
    assert _classify_status(50, 100, "HIGHER_IS_BETTER") == "RED"
    assert _classify_status(50, 100, "LOWER_IS_BETTER") == "GREEN"
    assert _classify_status(110, 100, "LOWER_IS_BETTER") == "AMBER"
    assert _classify_status(200, 100, "LOWER_IS_BETTER") == "RED"
    assert _classify_status(100, 100, "ON_TARGET") == "GREEN"
    assert _classify_status(110, 100, "ON_TARGET") == "AMBER"
    assert _classify_status(150, 100, "ON_TARGET") == "RED"

    with tempfile.TemporaryDirectory() as tmpdir:
        e = CIMSAnalyticsDashboardEngine(
            definitions_path=Path(tmpdir) / "d.json",
            observations_path=Path(tmpdir) / "o.json",
            trends_path=Path(tmpdir) / "t.json",
            views_path=Path(tmpdir) / "v.json",
        )

        # Definition
        r = e.register_kpi_definition(
            {"definition_id": "KPI-001",
             "name": "STP rate",
             "domain": "STP",
             "frequency": "DAILY",
             "direction": "HIGHER_IS_BETTER",
             "target": 80,
             "unit": "%"},
            actor="ops", reason="setup",
        )
        assert r["registered"]
        # Bad domain
        r = e.register_kpi_definition(
            {"definition_id": "X", "name": "Y",
             "domain": "WHATEVER",
             "frequency": "DAILY",
             "direction": "HIGHER_IS_BETTER",
             "target": 100},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Bad direction
        r = e.register_kpi_definition(
            {"definition_id": "Z", "name": "Y",
             "domain": "STP",
             "frequency": "DAILY",
             "direction": "WHATEVER",
             "target": 100},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Definition lifecycle
        r = e.transition_definition_state(
            "KPI-001", "ACTIVE",
            actor="ops", reason="ready",
        )
        assert r["transitioned"]

        # Observation — 95% with target 80 HIGHER_IS_BETTER → GREEN
        r = e.record_kpi_observation(
            {"observation_id": "OBS-001",
             "definition_id": "KPI-001",
             "actual": 95},
            actor="ops",
        )
        assert r["recorded"]
        assert r["status"] == "GREEN"
        # Observation — 70% → AMBER (because target=80, 70 is 12.5% off)
        r = e.record_kpi_observation(
            {"observation_id": "OBS-002",
             "definition_id": "KPI-001",
             "actual": 70},
            actor="ops",
        )
        assert r["recorded"]
        assert r["status"] == "AMBER"
        # Definition not found
        r = e.record_kpi_observation(
            {"observation_id": "X",
             "definition_id": "NONEXISTENT",
             "actual": 50},
            actor="x",
        )
        assert not r["recorded"]

        # Trend snapshot
        r = e.register_trend_snapshot(
            {"snapshot_id": "TRD-001",
             "definition_id": "KPI-001",
             "trend_direction": "STABLE",
             "narrative": "STP holding"},
            actor="ops", reason="weekly review",
        )
        assert r["registered"]
        # Bad trend direction
        r = e.register_trend_snapshot(
            {"snapshot_id": "X",
             "definition_id": "Y",
             "trend_direction": "WHATEVER",
             "narrative": "n"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Executive view
        r = e.register_executive_view(
            {"view_id": "VIEW-001",
             "view_type": "MD_DAILY",
             "title": "MD daily CIMS pulse",
             "kpi_definition_ids": ["KPI-001"]},
            actor="ops", reason="setup",
        )
        assert r["registered"]
        # Bad view type
        r = e.register_executive_view(
            {"view_id": "X",
             "view_type": "WHATEVER",
             "title": "Y"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Status report — 2 observations < threshold of 5 → INSUFFICIENT_DATA
        rep = e.kpi_status_report("KPI-001", days=30)
        assert rep["observation_count"] == 2
        assert rep["latest_status"] == "AMBER"
        assert rep["trend_direction"] == "INSUFFICIENT_DATA"

        # Add more observations to satisfy trend threshold
        for i, val in enumerate([60, 65, 70], start=3):
            e.record_kpi_observation(
                {"observation_id": f"OBS-00{i}",
                 "definition_id": "KPI-001",
                 "actual": val},
                actor="ops",
            )
        rep = e.kpi_status_report("KPI-001", days=30)
        assert rep["observation_count"] == 5
        # First half avg=(95+70)/2=82.5; second half=(60+65+70)/3=65
        # HIGHER_IS_BETTER → 65<82.5 → DETERIORATING
        assert rep["trend_direction"] == "DETERIORATING"

        # Dashboard summary
        s = e.dashboard_summary()
        assert s["kpi_definitions"] == 1
        assert s["kpi_observations"] == 5
        assert s["executive_views"] == 1
        assert s["trend_snapshots"] == 1
        assert s["per_domain"]["STP"] == 1

    print("  ✅ cims_analytics_dashboard self-test PASS")


if __name__ == "__main__":
    _self_test()
