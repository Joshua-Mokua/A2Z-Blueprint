"""utils.channels — Phase O3 banking channel simulators.

7 channels through which money moves through a Kenyan bank.
Shipped across two batches:

v10.477 (Phase O3-A):
  RTGS  — CBK real-time gross settlement (ISO 20022 pacs.008/009)
  SWIFT — Cross-border MT messaging (MT103/MT202/MT940)
  ATM   — Card-present cash withdrawal/inquiry (ISO 8583 0200)
  USSD  — Feature-phone session-based banking
  M-Pesa — Safaricom Daraja STK Push / B2C / C2B

v10.478 (Phase O3-B — THIS COMPLETES THE 7):
  KIC   — Kenya Interbank Clearing (EFT + cheque truncation)
  CARDS — Card transactions (Visa/Mastercard 0100 merchant auth)
"""

from utils.channels.base import (
    ChannelStatus, ChannelRequest, ChannelResponse,
    BaseChannelSimulator,
)
from utils.channels.registry import (
    get_channel, list_channels, submit_channel,
    SUPPORTED_CHANNELS,
)

__all__ = [
    "ChannelStatus", "ChannelRequest", "ChannelResponse",
    "BaseChannelSimulator",
    "get_channel", "list_channels", "submit_channel",
    "SUPPORTED_CHANNELS",
]
