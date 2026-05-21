"""utils/chaos/scheduler.py — bridge chaos events into the tick scheduler.

Pattern (parallel to MacroBridge):
    clock = get_simulation_clock()
    clock.set(datetime(2026, 5, 15, tzinfo=NAIROBI_TZ))
    sched = TickScheduler(clock)
    chaos_sched = ChaosScheduler(scheduler=sched)
    chaos_sched.schedule(get_chaos_event(
        "safaricom_mpesa_outage_30min",
        when=datetime(2026, 5, 15, 14, 30, tzinfo=NAIROBI_TZ),
    ))
    sched.tick(advance_by=timedelta(hours=6))
    # At sim 14:30 the outage activates; by 15:00 it has expired.

Macro shock events (kind=MACRO_SHOCK) delegate to MacroEvolution via
MacroBridge — they directly call apply_shock on the global macro state
rather than activating in the injector.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from utils.chaos.base import ChaosEvent, ChaosKind
from utils.chaos.injector import get_chaos_injector


class ChaosScheduler:
    """Schedule chaos events into a TickScheduler."""

    def __init__(self, *, scheduler):
        self.scheduler = scheduler
        self._scheduled: List[ChaosEvent] = []

    def schedule(self, event: ChaosEvent) -> str:
        """Schedule a chaos event to fire at event.when."""
        self._scheduled.append(event)
        return self.scheduler.schedule_at(
            event.when,
            lambda e=event: self._fire(e),
            label=f"chaos.{event.name}",
            priority=5,  # fire before drift recurring (priority -10)
        )

    def schedule_many(self, events: List[ChaosEvent]) -> List[str]:
        return [self.schedule(ev) for ev in events]

    def _fire(self, event: ChaosEvent) -> dict:
        """Apply an event when its time comes."""
        if event.kind == ChaosKind.MACRO_SHOCK:
            return self._fire_macro_shock(event)
        # All other kinds activate in the injector
        get_chaos_injector().activate(event)
        return {
            "fired": event.name,
            "kind": event.kind.value,
            "target": event.target,
        }

    def _fire_macro_shock(self, event: ChaosEvent) -> dict:
        """Apply a macro shock directly to global macro state."""
        try:
            from utils.macro_state import get_macro_state, set_macro_state
            from utils.macro_evolution import MacroEvolution
            state = get_macro_state()
            ev_engine = MacroEvolution(seed=hash(event.name) & 0xFFFF)
            shock_kind = event.payload.get("shock", "")
            kwargs = {k: v for k, v in event.payload.items()
                       if k != "shock"}
            # Map "new_rate_delta" → "new_rate" (CBR shock convenience)
            if "new_rate_delta" in kwargs:
                kwargs["new_rate"] = (state.cbk_central_bank_rate
                                        + kwargs.pop("new_rate_delta"))
            new_state = ev_engine.apply_shock(state, shock=shock_kind,
                                                at=event.when, **kwargs)
            set_macro_state(new_state)
            # Emit telemetry directly
            try:
                from utils.event_bus import get_event_bus
                bus = get_event_bus()
                bus.emit(
                    event_type="chaos.macro_shock_applied",
                    actor="chaos_scheduler",
                    entity_id=event.name,
                    module="chaos",
                    payload={
                        "name": event.name,
                        "shock": shock_kind,
                        "new_cbr": new_state.cbk_central_bank_rate,
                        "new_usd_kes": new_state.usd_kes,
                        "new_npl": new_state.npl_ratio,
                    },
                )
            except Exception:
                pass
            return {
                "fired": event.name,
                "kind": "macro_shock",
                "shock": shock_kind,
            }
        except Exception as exc:
            return {"error": str(exc), "fired": event.name}

    def scheduled_count(self) -> int:
        return len(self._scheduled)


__all__ = ["ChaosScheduler"]
