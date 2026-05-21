"""
================================================================================
A2Z MIS 360 — Standard #311: Command Centre Dashboard
================================================================================

Risk classification: Cat C (read-only KPI aggregation + drill-down navigation)

Real-time MD/CEO dashboard with top-line KPIs, alerts, trend signals, and
drill-down to root cause. Mobile-first responsive layout supporting
desktop and phone form factors.

Public API:
    register_kpi_widget(widget_data, actor, reason)
    set_widget_priority(widget_id, priority, actor, reason)
    dashboard_snapshot(role, refresh_seconds=60) -> Dict
    drill_down(widget_id, dimension, value) -> Dict
    record_view(widget_id, viewer_role)

DASHBOARD_WIDGET_TYPES byte-for-byte (8):
    KPI_TILE        -- single big number with delta + sparkline
    TREND_CHART     -- time-series for a single KPI
    HEATMAP         -- 2D matrix (e.g. segment × product NPL)
    ALERT_LIST      -- ranked active alerts requiring exec attention
    DRILL_TABLE     -- tabular breakdown for click-through
    MAP_VIEW        -- geographic distribution
    GAUGE           -- threshold-based gauge (e.g. CAR vs target)
    TEXT_BRIEFING   -- prose briefing pasted from analyst desk

WIDGET_PRIORITIES byte-for-byte (4): TOP, HIGH, MEDIUM, LOW

REFRESH_INTERVALS_SECONDS byte-for-byte (5): 30, 60, 300, 900, 3600

Honesty rules:
    Rule 1: dashboard_snapshot returns explicit "stale" flag if any widget's
            last refresh exceeded 2× interval; never silent
    Rule 4: actor + reason mandatory on widget registration / priority changes
    Rule 6: invalid widget_type / priority rejected explicitly

================================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DASHBOARD_WIDGET_TYPES: Tuple[str, ...] = (
    "KPI_TILE", "TREND_CHART", "HEATMAP", "ALERT_LIST",
    "DRILL_TABLE", "MAP_VIEW", "GAUGE", "TEXT_BRIEFING",
)

WIDGET_PRIORITIES: Tuple[str, ...] = ("TOP", "HIGH", "MEDIUM", "LOW")

REFRESH_INTERVALS_SECONDS: Tuple[int, ...] = (30, 60, 300, 900, 3600)


class CommandCentreDashboardEngine:
    """MD/CEO real-time dashboard with widget registry + drill-down."""

    def __init__(
        self,
        widgets_path: Optional[Path] = None,
        views_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.widgets_path = widgets_path or base / "command_centre_widgets.json"
        self.views_path = views_path or base / "command_centre_views.json"

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

    def register_kpi_widget(
        self, widget_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("widget_id", "widget_name", "widget_type"):
            if f not in widget_data or not widget_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if widget_data["widget_type"] not in DASHBOARD_WIDGET_TYPES:
            return {
                "registered": False,
                "error": f"invalid_widget_type:{widget_data['widget_type']}",
            }
        priority = widget_data.get("priority", "MEDIUM")
        if priority not in WIDGET_PRIORITIES:
            return {"registered": False, "error": f"invalid_priority:{priority}"}
        refresh = widget_data.get("refresh_seconds", 60)
        if refresh not in REFRESH_INTERVALS_SECONDS:
            return {"registered": False,
                       "error": f"invalid_refresh:{refresh}",
                       "valid": list(REFRESH_INTERVALS_SECONDS)}

        records = self._load(self.widgets_path, "command_centre_widgets",
                                ("widget_id",))
        if any(r.get("widget_id") == widget_data["widget_id"] for r in records):
            return {"registered": False, "error": "duplicate_widget_id"}

        record = {
            "widget_id": widget_data["widget_id"],
            "widget_name": widget_data["widget_name"],
            "widget_type": widget_data["widget_type"],
            "kpi_source": widget_data.get("kpi_source", ""),
            "priority": priority,
            "refresh_seconds": refresh,
            "visible_to_roles": widget_data.get("visible_to_roles",
                                                       ["MD", "CEO", "EXECUTIVE"]),
            "drill_down_dimensions": widget_data.get("drill_down_dimensions", []),
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "last_refreshed_at": None,
            "registration_reason": reason,
        }
        records.append(record)
        ok = self._save(self.widgets_path, records,
                          "command_centre_widgets", "widget_id")
        return {"registered": ok, "widget_id": widget_data["widget_id"]}

    def set_widget_priority(
        self, widget_id: str, priority: str, actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"updated": False, "error": "actor_and_reason_required"}
        if priority not in WIDGET_PRIORITIES:
            return {"updated": False, "error": f"invalid_priority:{priority}"}
        records = self._load(self.widgets_path, "command_centre_widgets",
                                ("widget_id",))
        for r in records:
            if r.get("widget_id") == widget_id:
                r["priority"] = priority
                r.setdefault("priority_history", []).append({
                    "priority": priority, "actor": actor,
                    "at": datetime.utcnow().isoformat(), "reason": reason,
                })
                ok = self._save(self.widgets_path, records,
                                  "command_centre_widgets", "widget_id")
                return {"updated": ok, "widget_id": widget_id,
                          "new_priority": priority}
        return {"updated": False, "error": "widget_not_found"}

    def dashboard_snapshot(
        self, role: str, kpi_values: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return active widget set for role, with stale flagging.

        Caller passes kpi_values dict mapping widget_id -> latest value;
        the engine enforces the staleness contract independently.
        """
        kpi_values = kpi_values or {}
        records = self._load(self.widgets_path, "command_centre_widgets",
                                ("widget_id",))
        active_widgets = []
        for r in records:
            if role and role not in r.get("visible_to_roles", []):
                continue
            widget_id = r["widget_id"]
            value_payload = kpi_values.get(widget_id, {})
            stale = False
            if value_payload.get("last_refreshed_at"):
                try:
                    last = datetime.fromisoformat(value_payload["last_refreshed_at"])
                    age = (datetime.utcnow() - last).total_seconds()
                    if age > 2 * r["refresh_seconds"]:
                        stale = True
                except (ValueError, TypeError):
                    stale = True
            else:
                stale = True

            active_widgets.append({
                "widget_id": widget_id,
                "widget_name": r["widget_name"],
                "widget_type": r["widget_type"],
                "priority": r["priority"],
                "value": value_payload.get("value"),
                "delta": value_payload.get("delta"),
                "stale": stale,
                "last_refreshed_at": value_payload.get("last_refreshed_at"),
            })

        # Sort by priority TOP→LOW
        priority_order = {p: i for i, p in enumerate(WIDGET_PRIORITIES)}
        active_widgets.sort(key=lambda w: priority_order.get(w["priority"], 99))

        return {
            "role": role,
            "snapshot_at": datetime.utcnow().isoformat(),
            "widget_count": len(active_widgets),
            "widgets": active_widgets,
            "stale_count": sum(1 for w in active_widgets if w["stale"]),
        }

    def drill_down(
        self, widget_id: str, dimension: str,
        value: Any = None, drill_data: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        records = self._load(self.widgets_path, "command_centre_widgets",
                                ("widget_id",))
        widget = next((r for r in records
                          if r.get("widget_id") == widget_id), None)
        if widget is None:
            return {"available": False, "error": "widget_not_found"}
        if dimension not in widget.get("drill_down_dimensions", []):
            return {
                "available": False,
                "error": f"dimension_not_drillable:{dimension}",
                "valid_dimensions": widget.get("drill_down_dimensions", []),
            }
        return {
            "available": True,
            "widget_id": widget_id,
            "dimension": dimension,
            "filter_value": value,
            "rows": drill_data or [],
            "row_count": len(drill_data or []),
        }

    def record_view(self, widget_id: str, viewer_role: str) -> Dict[str, Any]:
        if not viewer_role:
            return {"recorded": False, "error": "viewer_role_required"}
        views = self._load(self.views_path, "command_centre_views",
                              ("view_id",))
        view_id = (f"VIEW-{widget_id}-{viewer_role}-"
                       f"{int(datetime.utcnow().timestamp() * 1000)}")
        views.append({
            "view_id": view_id,
            "widget_id": widget_id,
            "viewer_role": viewer_role,
            "viewed_at": datetime.utcnow().isoformat(),
        })
        ok = self._save(self.views_path, views,
                          "command_centre_views", "view_id")
        return {"recorded": ok, "view_id": view_id}


def _self_test() -> None:
    import tempfile

    assert "KPI_TILE" in DASHBOARD_WIDGET_TYPES
    assert len(DASHBOARD_WIDGET_TYPES) == 8
    assert "TOP" in WIDGET_PRIORITIES
    assert 60 in REFRESH_INTERVALS_SECONDS

    with tempfile.TemporaryDirectory() as tmpdir:
        engine = CommandCentreDashboardEngine(
            widgets_path=Path(tmpdir) / "w.json",
            views_path=Path(tmpdir) / "v.json",
        )
        # Test 1: register
        r = engine.register_kpi_widget(
            {"widget_id": "W-NPL", "widget_name": "NPL Ratio",
             "widget_type": "KPI_TILE", "priority": "TOP",
             "refresh_seconds": 60,
             "drill_down_dimensions": ["segment", "product"]},
            actor="md", reason="MD dashboard",
        )
        assert r["registered"]
        # Test 2: invalid widget type
        r = engine.register_kpi_widget(
            {"widget_id": "X", "widget_name": "Y", "widget_type": "INVALID"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 3: invalid priority
        r = engine.register_kpi_widget(
            {"widget_id": "Y", "widget_name": "Y",
             "widget_type": "KPI_TILE", "priority": "URGENT"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 4: invalid refresh interval
        r = engine.register_kpi_widget(
            {"widget_id": "Z", "widget_name": "Z",
             "widget_type": "KPI_TILE", "refresh_seconds": 17},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Test 5: priority change
        r = engine.set_widget_priority("W-NPL", "HIGH",
                                            actor="md", reason="re-prioritize")
        assert r["updated"]
        # Test 6: snapshot
        snap = engine.dashboard_snapshot(
            "MD",
            kpi_values={"W-NPL": {"value": "5.2",
                                       "last_refreshed_at": datetime.utcnow().isoformat()}},
        )
        assert snap["widget_count"] == 1
        assert snap["widgets"][0]["stale"] is False
        # Test 7: stale detection
        old = (datetime.utcnow() - timedelta(seconds=300)).isoformat()
        snap = engine.dashboard_snapshot(
            "MD",
            kpi_values={"W-NPL": {"value": "5.2", "last_refreshed_at": old}},
        )
        assert snap["widgets"][0]["stale"] is True
        # Test 8: role filter
        snap = engine.dashboard_snapshot("BRANCH_MANAGER")
        assert snap["widget_count"] == 0  # widget visible to MD/CEO/EXECUTIVE
        # Test 9: drill-down
        d = engine.drill_down("W-NPL", "segment", "RETAIL",
                                  drill_data=[{"k": "v"}])
        assert d["available"]
        # Test 10: invalid drill dimension
        d = engine.drill_down("W-NPL", "INVALID")
        assert not d["available"]
        # Test 11: record view
        v = engine.record_view("W-NPL", "MD")
        assert v["recorded"]

    print("  ✅ command_centre_dashboard self-test PASS")


if __name__ == "__main__":
    _self_test()
