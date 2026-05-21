"""utils/channels/registry.py — Channel registry and unified submit API.

Single discovery point: `get_channel("rtgs")` -> RTGSSimulator instance.
Unified entry: `submit_channel(channel, payload, ...)` -> ChannelResponse.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from utils.channels.atm import ATMSimulator
from utils.channels.base import (
    BaseChannelSimulator, ChannelRequest, ChannelResponse, ChannelStatus,
)
from utils.channels.cards import CardsSimulator
from utils.channels.kic import KICSimulator
from utils.channels.mpesa import MPesaSimulator
from utils.channels.rtgs import RTGSSimulator
from utils.channels.swift import SwiftSimulator
from utils.channels.ussd import USSDSimulator


SUPPORTED_CHANNELS: Dict[str, type] = {
    "rtgs":  RTGSSimulator,
    "swift": SwiftSimulator,
    "atm":   ATMSimulator,
    "ussd":  USSDSimulator,
    "mpesa": MPesaSimulator,
    "kic":   KICSimulator,
    "cards": CardsSimulator,
}


_instance_cache: Dict[str, BaseChannelSimulator] = {}


def get_channel(name: str, *, seed: Optional[int] = None,
                 fresh: bool = False) -> BaseChannelSimulator:
    """Return a simulator for the named channel.

    If `seed` is given, returns a freshly-seeded instance.
    If `fresh=True`, returns a new instance regardless of cache.
    Otherwise, returns a cached unseeded instance for performance.
    """
    name = (name or "").lower().strip()
    cls = SUPPORTED_CHANNELS.get(name)
    if cls is None:
        raise ValueError(
            f"unknown channel {name!r}; supported: {list_channels()}"
        )
    if seed is not None or fresh:
        return cls(seed=seed)
    if name not in _instance_cache:
        _instance_cache[name] = cls()
    return _instance_cache[name]


def list_channels() -> List[str]:
    """Return all supported channel names."""
    return sorted(SUPPORTED_CHANNELS.keys())


def submit_channel(channel: str, payload: Dict[str, Any],
                    *, amount: Optional[float] = None,
                    currency: str = "KES",
                    debit_account: Optional[str] = None,
                    credit_account: Optional[str] = None,
                    reference: Optional[str] = None,
                    actor: str = "system",
                    seed: Optional[int] = None) -> ChannelResponse:
    """One-call entry: submit a payload against a named channel.

    Convenience wrapper that:
      1. Resolves the channel by name
      2. Builds the ChannelRequest envelope
      3. Calls submit() and returns the response

    All events are emitted via event_bus automatically.
    """
    sim = get_channel(channel, seed=seed, fresh=(seed is not None))
    req = ChannelRequest(
        channel=channel, payload=payload, amount=amount,
        currency=currency, debit_account=debit_account,
        credit_account=credit_account, reference=reference, actor=actor,
    )
    return sim.submit(req)


__all__ = [
    "SUPPORTED_CHANNELS", "get_channel", "list_channels", "submit_channel",
]
