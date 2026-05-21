"""utils/macro_bridge.py — Phase O4-B macro state + tick scheduler bridge.

The MacroBridge wires MacroEvolution + MacroCalendar to a TickScheduler:
  - On each periodic drift tick, evolves the macro state by the elapsed
    sim time and writes the result back to the global macro state
  - When a calendar event is reached, applies the event's economic
    impact (e.g. CBK MPC sets a new CBR)
  - Emits macro.update events to the event bus for telemetry

Pattern:
    clock = get_simulation_clock()
    clock.set(datetime(2026, 1, 1, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    bridge = MacroBridge(
        evolution=MacroEvolution(seed=42),
        calendar=MacroCalendar.kenya_2026_calendar(),
    )
    bridge.attach_to_scheduler(sched, drift_interval_days=1.0)
    sched.tick(advance_by=timedelta(days=180))   # → 6 months evolved
    state = get_macro_state()                    # reflects 6m drift + events
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from utils.macro_calendar import MacroCalendar, MacroEvent
from utils.macro_evolution import MacroEvolution
from utils.macro_state import (
    MacroState, get_macro_state, set_macro_state,
)
from utils.simulation_clock import sim_now


class MacroBridge:
    """Wires macro state evolution into the tick scheduler."""

    def __init__(self, *, evolution: MacroEvolution,
                  calendar: Optional[MacroCalendar] = None):
        self.evolution = evolution
        self.calendar = calendar or MacroCalendar()
        self._last_evolved_at: Optional[datetime] = None
        self._drift_count: int = 0
        self._events_fired: List[str] = []
        # Default shock parameters for known event types
        self._default_shocks: Dict[str, Dict[str, Any]] = {
            # CBK MPC: small CBR adjustment (mean-reverting toward 10%)
            "cbk_mpc": {"shock": "cbr_change_default"},
            # Budget: small GDP revision
            "budget": {"shock": "mof_budget", "gdp_revision": 0.002},
            # CPI release: may revise inflation (small delta)
            "cpi_release": {"shock": "cpi_release_default"},
            # EOM / EOQ: book impact only (no shock by default; consumers
            # can subscribe via _macro_event listeners)
        }

    def attach_to_scheduler(self, scheduler,
                               *, drift_interval_days: float = 1.0) -> None:
        """Register drift + calendar callbacks on the scheduler.

        ``drift_interval_days`` controls how often the state evolves.
        Default 1.0 means daily drift; can be sub-day for finer detail.

        Side effect: initialises the global macro state at the current
        sim moment so that drift callbacks have a valid anchor when they
        fire after a fast-forward tick.
        """
        now = sim_now()
        # Anchor the macro state at attach time. Without this, the first
        # drift callback to fire (after a fast-forward tick) would call
        # get_macro_state() which would lazy-init state.as_of to that
        # post-advance moment, making elapsed days = 0 on first drift.
        from utils.macro_state import get_macro_state
        _ = get_macro_state()  # forces init at current sim time
        self._last_evolved_at = now
        # 1. Periodic drift callback
        scheduler.schedule_recurring(
            start_at=now + timedelta(days=drift_interval_days),
            interval=timedelta(days=drift_interval_days),
            callback=self._drift_tick,
            label="macro_drift",
            priority=-10,    # lower priority than calendar events
        )
        # 2. Calendar events
        for event in self.calendar.events_after(now):
            # Use default to bind event at lambda creation time
            scheduler.schedule_at(
                event.when,
                lambda e=event: self._fire_calendar_event(e),
                label=f"macro_event.{event.name}",
                priority=0,
            )

    # ── Drift ─────────────────────────────────────────────────────

    def _drift_tick(self) -> Dict[str, Any]:
        """Evolve macro state by sim time since last drift."""
        state = get_macro_state()
        now = sim_now()
        anchor = self._last_evolved_at or state.as_of
        elapsed_seconds = (now - anchor).total_seconds()
        days = max(0.0, elapsed_seconds / 86400.0)
        if days > 0:
            new_state = self.evolution.evolve(state, days_elapsed=days)
            set_macro_state(new_state)
            self._emit_macro_update(new_state, source="drift")
            self._last_evolved_at = now
            self._drift_count += 1
            return {
                "drift_days": days,
                "cbr": new_state.cbk_central_bank_rate,
                "usd_kes": new_state.usd_kes,
                "npl": new_state.npl_ratio,
            }
        return {"drift_days": 0.0}

    # ── Calendar event firing ─────────────────────────────────────

    def _fire_calendar_event(self, event: MacroEvent) -> Dict[str, Any]:
        """Apply an event's economic impact to the macro state."""
        state = get_macro_state()
        new_state = state

        if event.event_type == "cbk_mpc":
            # If event payload specifies new_rate, use it; else apply
            # a small mean-reverting adjustment toward long-run CBR
            new_rate = event.payload.get("new_rate")
            if new_rate is None:
                lr = self.evolution.long_run_cbr
                d = (lr - state.cbk_central_bank_rate) * 0.25  # 25% of gap
                d = max(-0.005, min(0.005, d))  # cap at ±50bps
                new_rate = state.cbk_central_bank_rate + d
            new_state = self.evolution.apply_shock(
                state, shock="cbr_change", new_rate=new_rate,
                at=event.when,
            )

        elif event.event_type == "budget":
            gdp_rev = event.payload.get("gdp_revision", 0.002)
            new_state = self.evolution.apply_shock(
                state, shock="mof_budget", gdp_revision=gdp_rev,
                at=event.when,
            )

        elif event.event_type == "cpi_release":
            delta = event.payload.get("inflation_delta", 0.0)
            if delta:
                new_state = self.evolution.apply_shock(
                    state, shock="inflation_spike", delta=delta,
                    at=event.when,
                )

        # eom / eoq: no automatic state change, just emit telemetry

        if new_state is not state:
            set_macro_state(new_state)
        self._emit_macro_update(
            new_state, source="event", event_name=event.name,
            event_type=event.event_type,
        )
        self._events_fired.append(event.name)
        return {
            "event_name": event.name,
            "event_type": event.event_type,
            "cbr": new_state.cbk_central_bank_rate,
            "usd_kes": new_state.usd_kes,
        }

    # ── Telemetry ─────────────────────────────────────────────────

    def _emit_macro_update(self, state: MacroState, *,
                              source: str, **extra) -> None:
        """Emit a macro.update event."""
        try:
            from utils.event_bus import get_event_bus
            bus = get_event_bus()
            payload = state.to_dict()
            payload["source"] = source
            payload.update(extra)
            bus.emit(
                event_type="macro.update",
                actor="macro_bridge",
                entity_id="kenya",
                module="macro",
                payload=payload,
            )
        except Exception:
            pass  # never let telemetry break drift

    # ── Introspection ────────────────────────────────────────────

    def drift_count(self) -> int:
        return self._drift_count

    def events_fired(self) -> List[str]:
        return list(self._events_fired)


__all__ = ["MacroBridge"]
