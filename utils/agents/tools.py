"""utils/agents/tools.py — agent tool registry.

Wraps the digital twin's capabilities as agent-callable tools. Each
tool has a structured name, description, and typed handler. The
default registry exposes:

  channel:submit         - submit a transaction on a channel
  channel:list           - list registered channels
  scenario:list          - list available scenarios
  scenario:run           - run a scenario by name
  chaos:list             - list chaos templates
  chaos:activate         - activate a chaos event by name
  chaos:active           - list currently active chaos
  macro:snapshot         - current macro state
  macro:apply_shock      - apply a macro shock
  ml:list                - list registered models
  ml:predict             - predict using a registered model
  ml:train_classifier    - train a new classifier
  events:query           - query the event bus
  time:advance           - advance the sim clock by a duration

Tools are pure functions over the digital twin singletons. They never
fail silently - errors propagate as AgentToolResult.success=False with
an error message.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from utils.agents.base import (
    AgentTool, AgentToolResult, ToolHandler,
)


class ToolRegistry:
    """Registry of tools available to agents. Thread-safe."""

    def __init__(self):
        self._tools: Dict[str, AgentTool] = {}
        self._lock = threading.RLock()

    # ── registration ─────────────────────────────────────────────

    def register(self, tool: AgentTool) -> None:
        with self._lock:
            self._tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        with self._lock:
            return self._tools.pop(name, None) is not None

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._tools

    def get(self, name: str) -> Optional[AgentTool]:
        with self._lock:
            return self._tools.get(name)

    def list_names(self) -> List[str]:
        with self._lock:
            return sorted(self._tools.keys())

    def list_by_category(self, category: str) -> List[str]:
        with self._lock:
            return sorted(
                n for n, t in self._tools.items()
                if t.category == category
            )

    def descriptions(self) -> Dict[str, str]:
        with self._lock:
            return {n: t.description for n, t in self._tools.items()}

    # ── invocation ───────────────────────────────────────────────

    def call(self, tool_name: str, **kwargs) -> AgentToolResult:
        """Invoke a tool and wrap result/exception in AgentToolResult.

        Note: the registry method param is ``tool_name`` (not ``name``)
        to avoid collision with tool handlers that accept a ``name``
        kwarg of their own (e.g. ``ml:train_classifier(name=...)``).
        """
        tool = self.get(tool_name)
        if tool is None:
            return AgentToolResult(
                tool_name=tool_name, success=False,
                error=f"unknown tool: {tool_name}",
            )
        start = time.time()
        try:
            output = tool.handler(**kwargs) or {}
            if not isinstance(output, dict):
                output = {"value": output}
            latency_ms = (time.time() - start) * 1000.0
            return AgentToolResult(
                tool_name=tool_name, success=True,
                output=output, latency_ms=latency_ms,
            )
        except Exception as exc:
            latency_ms = (time.time() - start) * 1000.0
            return AgentToolResult(
                tool_name=tool_name, success=False,
                error=f"{type(exc).__name__}: {exc}",
                latency_ms=latency_ms,
            )


# ─── Default registry builders ──────────────────────────────────────


def _make_default_registry() -> ToolRegistry:
    """Build the standard tool set wrapping the digital twin."""
    reg = ToolRegistry()

    # ─── channel:* ───────────────────────────────────────────────
    def channel_list_handler() -> Dict[str, Any]:
        from utils.channels import list_channels
        return {"channels": list_channels()}

    reg.register(AgentTool(
        name="channel:list",
        description="List all registered channel names",
        handler=channel_list_handler, category="channel",
    ))

    def channel_submit_handler(*, channel: str,
                                  payload: Optional[Dict] = None,
                                  amount: Optional[float] = None,
                                  reference: str = "agent",
                                  actor: str = "agent",
                                  seed: int = 0) -> Dict[str, Any]:
        from utils.channels import submit_channel
        r = submit_channel(channel,
            payload=payload or {}, amount=amount,
            reference=reference, actor=actor, seed=seed)
        return {
            "channel": r.channel,
            "status": (r.status.value if hasattr(r.status, "value")
                        else str(r.status)),
            "success": r.success,
            "latency_ms": r.latency_ms,
            "correlation_id": r.correlation_id,
            "error_code": getattr(r, "error_code", "") or "",
        }

    reg.register(AgentTool(
        name="channel:submit",
        description=("Submit a transaction on a channel. "
                       "Args: channel, payload, amount, reference, actor"),
        handler=channel_submit_handler, category="channel",
        schema={
            "channel": "str", "payload": "dict",
            "amount": "float", "reference": "str", "actor": "str",
            "seed": "int",
        },
    ))

    # ─── scenario:* ──────────────────────────────────────────────
    def scenario_list_handler() -> Dict[str, Any]:
        from utils.scenarios import list_scenarios
        return {"scenarios": list_scenarios()}

    reg.register(AgentTool(
        name="scenario:list",
        description="List all scenario names",
        handler=scenario_list_handler, category="scenario",
    ))

    def scenario_run_handler(*, name: str) -> Dict[str, Any]:
        from utils.scenarios import get_scenario
        from utils.scenarios.base import ScenarioRunner
        scenario = get_scenario(name)
        runner = ScenarioRunner()
        result = runner.run(scenario, seed=0)
        return {
            "name": name,
            "ran": True,
        }

    reg.register(AgentTool(
        name="scenario:run",
        description="Run a named scenario. Args: name",
        handler=scenario_run_handler, category="scenario",
        schema={"name": "str"},
    ))

    # ─── chaos:* ─────────────────────────────────────────────────
    def chaos_list_handler() -> Dict[str, Any]:
        from utils.chaos import list_chaos_events
        return {"chaos_templates": list_chaos_events()}

    reg.register(AgentTool(
        name="chaos:list",
        description="List all chaos event template names",
        handler=chaos_list_handler, category="chaos",
    ))

    def chaos_activate_handler(*, name: str,
                                  when: Optional[str] = None) -> Dict[str, Any]:
        from utils.chaos import get_chaos_event, get_chaos_injector
        from utils.simulation_clock import sim_now
        if when:
            when_dt = datetime.fromisoformat(when)
        else:
            when_dt = sim_now()
        ev = get_chaos_event(name, when=when_dt)
        get_chaos_injector().activate(ev)
        return {
            "activated": name,
            "kind": ev.kind.value,
            "target": ev.target,
            "duration_seconds": int(ev.duration.total_seconds()),
        }

    reg.register(AgentTool(
        name="chaos:activate",
        description=("Activate a chaos event by template name. "
                       "Args: name, when (ISO datetime, optional)"),
        handler=chaos_activate_handler, category="chaos",
        schema={"name": "str", "when": "str"},
    ))

    def chaos_active_handler() -> Dict[str, Any]:
        from utils.chaos import get_chaos_injector
        active = get_chaos_injector().active_events()
        return {
            "count": len(active),
            "events": [
                {"name": e.name, "kind": e.kind.value, "target": e.target}
                for e in active
            ],
        }

    reg.register(AgentTool(
        name="chaos:active",
        description="List currently-active chaos events",
        handler=chaos_active_handler, category="chaos",
    ))

    # ─── macro:* ─────────────────────────────────────────────────
    def macro_snapshot_handler() -> Dict[str, Any]:
        from utils.macro_state import get_macro_state
        return get_macro_state().to_dict()

    reg.register(AgentTool(
        name="macro:snapshot",
        description="Get the current macro economic state snapshot",
        handler=macro_snapshot_handler, category="macro",
    ))

    def macro_apply_shock_handler(*, shock: str,
                                      **kwargs) -> Dict[str, Any]:
        from utils.macro_state import get_macro_state, set_macro_state
        from utils.macro_evolution import MacroEvolution
        state = get_macro_state()
        ev = MacroEvolution(seed=0)
        new_state = ev.apply_shock(state, shock=shock, **kwargs)
        set_macro_state(new_state)
        return {
            "shock": shock,
            "new_state": new_state.to_dict(),
        }

    reg.register(AgentTool(
        name="macro:apply_shock",
        description=("Apply a macro shock. Args: shock (one of "
                       "cbr_change/fx_devaluation/credit_shock/"
                       "inflation_spike/mof_budget), plus shock-specific "
                       "kwargs"),
        handler=macro_apply_shock_handler, category="macro",
        schema={"shock": "str"},
    ))

    # ─── ml:* ────────────────────────────────────────────────────
    def ml_list_handler() -> Dict[str, Any]:
        from utils.ml import get_model_registry
        reg_ml = get_model_registry()
        return {
            "models": [
                {
                    "name": n,
                    "meta": (m.to_dict() if (m := reg_ml.get_meta(n))
                              else {}),
                }
                for n in reg_ml.list_models()
            ],
        }

    reg.register(AgentTool(
        name="ml:list",
        description="List all registered ML models with provenance",
        handler=ml_list_handler, category="ml",
    ))

    def ml_predict_handler(*, model_name: str,
                              n: int = 5) -> Dict[str, Any]:
        from utils.ml import get_model_registry, DatasetBuilder
        from utils.ml.dataset import DatasetSpec
        rows = DatasetBuilder().build(DatasetSpec(max_rows=n))
        if not rows:
            return {"predictions": [], "note": "no rows available"}
        preds = get_model_registry().predict(model_name, rows)
        return {
            "model_name": model_name,
            "predictions": [
                {"correlation_id": r.correlation_id,
                 "channel": r.channel, "prediction": p}
                for r, p in zip(rows, preds)
            ],
        }

    reg.register(AgentTool(
        name="ml:predict",
        description=("Predict using a registered model on recent rows. "
                       "Args: model_name, n (rows, default 5)"),
        handler=ml_predict_handler, category="ml",
        schema={"model_name": "str", "n": "int"},
    ))

    def ml_train_classifier_handler(*, name: str, target_label: str,
                                          seed: int = 0,
                                          notes: str = "") -> Dict[str, Any]:
        from utils.ml import MLBridge
        meta, metrics = MLBridge().train_classifier(
            name=name, target_label=target_label,
            seed=seed, notes=notes, persist=True,
        )
        return {
            "name": name,
            "sample_count": meta.sample_count,
            "metrics": meta.metrics,
            "fingerprint": meta.dataset_fingerprint,
        }

    reg.register(AgentTool(
        name="ml:train_classifier",
        description=("Train a new classifier. Args: name, target_label, "
                       "seed, notes"),
        handler=ml_train_classifier_handler, category="ml",
        schema={"name": "str", "target_label": "str",
                  "seed": "int", "notes": "str"},
    ))

    # ─── events:* ────────────────────────────────────────────────
    def events_query_handler(*, event_type: Optional[str] = None,
                                 limit: int = 10) -> Dict[str, Any]:
        from utils.event_bus import get_event_bus
        bus = get_event_bus()
        kwargs: Dict[str, Any] = {"limit": limit}
        if event_type:
            kwargs["event_type"] = event_type
        events = bus.query(**kwargs)
        return {
            "count": len(events),
            "events": [
                {"event_type": e.event_type,
                 "timestamp": e.timestamp,
                 "correlation_id": getattr(e, "correlation_id", "")}
                for e in events
            ],
        }

    reg.register(AgentTool(
        name="events:query",
        description=("Query the event bus. Args: event_type (optional), "
                       "limit (default 10)"),
        handler=events_query_handler, category="info",
        schema={"event_type": "str", "limit": "int"},
    ))

    # ─── time:* ──────────────────────────────────────────────────
    def time_advance_handler(*, seconds: float = 0,
                                 minutes: float = 0,
                                 hours: float = 0,
                                 days: float = 0) -> Dict[str, Any]:
        from utils.simulation_clock import (
            get_simulation_clock, sim_now,
        )
        delta = timedelta(seconds=seconds, minutes=minutes,
                           hours=hours, days=days)
        clock = get_simulation_clock()
        clock.advance(delta)
        return {
            "advanced_by_seconds": delta.total_seconds(),
            "now": sim_now().isoformat(),
        }

    reg.register(AgentTool(
        name="time:advance",
        description=("Advance the sim clock. Args: seconds, minutes, "
                       "hours, days (any combination)"),
        handler=time_advance_handler, category="info",
        schema={"seconds": "float", "minutes": "float",
                  "hours": "float", "days": "float"},
    ))

    def time_now_handler() -> Dict[str, Any]:
        from utils.simulation_clock import sim_now
        return {"now": sim_now().isoformat()}

    reg.register(AgentTool(
        name="time:now",
        description="Return the current sim time",
        handler=time_now_handler, category="info",
    ))

    return reg


# ─── Module singleton ───────────────────────────────────────────────

_GLOBAL_REGISTRY: Optional[ToolRegistry] = None
_REGISTRY_LOCK = threading.Lock()


def get_default_tool_registry() -> ToolRegistry:
    """Lazy singleton default registry."""
    global _GLOBAL_REGISTRY
    with _REGISTRY_LOCK:
        if _GLOBAL_REGISTRY is None:
            _GLOBAL_REGISTRY = _make_default_registry()
        return _GLOBAL_REGISTRY


def reset_default_tool_registry() -> None:
    """Reset the default registry (forces rebuild on next access)."""
    global _GLOBAL_REGISTRY
    with _REGISTRY_LOCK:
        _GLOBAL_REGISTRY = None


__all__ = [
    "ToolRegistry",
    "get_default_tool_registry",
    "reset_default_tool_registry",
]
