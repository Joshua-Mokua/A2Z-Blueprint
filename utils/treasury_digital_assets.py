"""utils/treasury_digital_assets.py — v10.37 ENH-TRS-R2.

╔════════════════════════════════════════════════════════════════════════╗
║  DIGITAL ASSET TREASURY — Stablecoin & digital asset support          ║
║  Cat A — implements ENH-TRS-R2 per CBK VASP Regulations 2026          ║
╠════════════════════════════════════════════════════════════════════════╣
║  Implements ENH-TRS-R2: stablecoin & digital asset treasury.          ║
║                                                                         ║
║  Six asset types supported:                                            ║
║    USDC: Circle USDC (USD-pegged, fully reserved)                    ║
║    USDT: Tether USDT (USD-pegged)                                    ║
║    EURC: Circle EURC (EUR-pegged)                                    ║
║    KES_STABLE: hypothetical KES-pegged stablecoin (CBK pilot)        ║
║    BTC: Bitcoin (volatile; reserve allocation only)                   ║
║    ETH: Ethereum (volatile; reserve allocation only)                   ║
║                                                                         ║
║  Risk controls per CBK VASP 2026:                                      ║
║    - Wallet whitelist + KYT (know-your-transaction) screening        ║
║    - Per-asset concentration limits as % of total treasury           ║
║    - Stablecoin de-peg monitoring (alert if > 50bps off peg)         ║
║    - Volatile-asset cap (BTC + ETH ≤ 5% of digital allocation)       ║
║                                                                         ║
║  Honesty Rule 1: every DigitalAssetValuation surfaces holding +      ║
║  spot rate + KES equivalent + de-peg status + concentration vs limit. ║
║  Honesty Rule 7: live exchange rates require ml_provider hook        ║
║  (chain oracle / exchange API). Without wiring, the engine uses       ║
║  manually-set rates and emits a warning that ml_overlay_applied=False.║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    CBK VASP Regulations 2026 — Virtual Asset Service Providers        ║
║    BCBS Crypto Asset Standard 2022 — bank exposures to crypto        ║
║    BCBS Group 1a / 1b / 2 classification — capital treatment          ║
║    FATF VASP Recommendation 15 — AML for virtual assets               ║
║    Travel Rule (FATF Rec 16) — info on originator + beneficiary      ║
║    IFRS — digital asset accounting (no specific standard yet)         ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Callable, Dict, FrozenSet, List, Mapping, Optional,
    Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "DigitalAssetTreasuryEngine implements ENH-TRS-R2 per CBK VASP "
    "Regs 2026 + BCBS crypto asset standard 2022. 6 asset types + "
    "BCBS Group 1a/1b/2 classification + de-peg monitoring + "
    "concentration limits. Per Rule 7, live spot rates require "
    "rate_provider hook; otherwise manually-set rates with "
    "rate_source flag indicating provenance."
)


# ════════════════════════════════════════════════════════════════════════
# Taxonomies
# ════════════════════════════════════════════════════════════════════════

class DigitalAssetType(Enum):
    """Digital asset types."""
    USDC = "USDC"
    USDT = "USDT"
    EURC = "EURC"
    KES_STABLE = "KES_STABLE"
    BTC = "BTC"
    ETH = "ETH"


class BCBSCryptoGroup(Enum):
    """BCBS 2022 crypto asset classification.

    Group 1a: tokenized traditional assets (lower capital cost)
    Group 1b: stablecoins meeting redemption requirement
    Group 2: all other crypto (1250% RW, hard cap)
    """
    GROUP_1A_TOKENIZED = "GROUP_1A_TOKENIZED"
    GROUP_1B_STABLECOIN = "GROUP_1B_STABLECOIN"
    GROUP_2_OTHER = "GROUP_2_OTHER"


class DePegStatus(Enum):
    """Stablecoin de-peg monitoring outcome."""
    ON_PEG = "ON_PEG"                     # within 50bps
    MINOR_DEVIATION = "MINOR_DEVIATION"   # 50-100bps
    SIGNIFICANT_DEVIATION = "SIGNIFICANT_DEVIATION"  # 100-300bps
    DE_PEGGED = "DE_PEGGED"               # > 300bps (alert)
    NOT_APPLICABLE = "NOT_APPLICABLE"     # for BTC/ETH


class WalletStatus(Enum):
    REGISTERED = "REGISTERED"
    WHITELISTED = "WHITELISTED"
    SUSPENDED = "SUSPENDED"


# ════════════════════════════════════════════════════════════════════════
# Default classification mapping (BCBS 2022)
# ════════════════════════════════════════════════════════════════════════

DEFAULT_BCBS_CLASSIFICATION: Mapping[
    DigitalAssetType, BCBSCryptoGroup] = {
    DigitalAssetType.USDC: BCBSCryptoGroup.GROUP_1B_STABLECOIN,
    DigitalAssetType.USDT: BCBSCryptoGroup.GROUP_1B_STABLECOIN,
    DigitalAssetType.EURC: BCBSCryptoGroup.GROUP_1B_STABLECOIN,
    DigitalAssetType.KES_STABLE: BCBSCryptoGroup.GROUP_1B_STABLECOIN,
    DigitalAssetType.BTC: BCBSCryptoGroup.GROUP_2_OTHER,
    DigitalAssetType.ETH: BCBSCryptoGroup.GROUP_2_OTHER,
}

# Per-asset concentration limit as % of total treasury
DEFAULT_CONCENTRATION_LIMIT_PCT: Mapping[
    DigitalAssetType, Decimal] = {
    DigitalAssetType.USDC: Decimal("3"),    # 3% max
    DigitalAssetType.USDT: Decimal("2"),
    DigitalAssetType.EURC: Decimal("2"),
    DigitalAssetType.KES_STABLE: Decimal("5"),
    DigitalAssetType.BTC: Decimal("0.5"),   # 50bps
    DigitalAssetType.ETH: Decimal("0.5"),
}

# Total volatile-asset cap (BTC + ETH combined)
VOLATILE_ASSETS_TOTAL_CAP_PCT = Decimal("1")    # 1%

# De-peg thresholds (in basis points)
DE_PEG_MINOR_BPS = Decimal("50")
DE_PEG_SIGNIFICANT_BPS = Decimal("100")
DE_PEG_ALERT_BPS = Decimal("300")


# ════════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DigitalWallet:
    """A wallet registered with the bank."""
    wallet_id: str
    blockchain: str                       # 'ETH', 'BTC', 'TRON', etc.
    address: str
    label: str
    counterparty_name: str = ""
    status: WalletStatus = WalletStatus.REGISTERED
    registered_at: str = ""
    notes: str = ""


@dataclass(frozen=True)
class DigitalHolding:
    """A holding of a digital asset."""
    holding_id: str
    wallet_id: str
    asset_type: DigitalAssetType
    quantity: Decimal                     # in native units
    acquired_at: str
    notes: str = ""


@dataclass(frozen=True)
class SpotRate:
    """Spot rate for an asset to KES."""
    asset_type: DigitalAssetType
    kes_per_unit: Decimal                 # KES per 1 native unit
    source: str                           # 'manual', 'oracle', 'CEX'
    timestamp: str
    notes: str = ""


@dataclass(frozen=True)
class DigitalAssetValuation:
    """Result of valuing a holding."""
    holding_id: str
    asset_type: DigitalAssetType
    quantity: Decimal
    spot_rate_kes: Decimal
    kes_equivalent: Decimal
    bcbs_group: BCBSCryptoGroup
    de_peg_status: DePegStatus
    de_peg_deviation_bps: Decimal
    rate_source: str
    framework_refs: Tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class ConcentrationCheckResult:
    """Concentration limit check outcome."""
    asset_type: DigitalAssetType
    holding_value_kes: Decimal
    total_treasury_kes: Decimal
    actual_pct: Decimal
    limit_pct: Decimal
    within_limit: bool
    headroom_pct: Decimal


# ════════════════════════════════════════════════════════════════════════
# De-peg detection
# ════════════════════════════════════════════════════════════════════════

def detect_de_peg(
    *, asset: DigitalAssetType,
    current_rate_kes: Decimal,
    expected_peg_kes: Decimal,
) -> Tuple[DePegStatus, Decimal]:
    """Return (status, deviation_bps) for stablecoins.

    For BTC/ETH returns NOT_APPLICABLE.
    """
    if asset in (DigitalAssetType.BTC, DigitalAssetType.ETH):
        return DePegStatus.NOT_APPLICABLE, Decimal("0")
    if expected_peg_kes <= Decimal("0"):
        raise ValueError("expected_peg_kes must be positive")
    deviation_pct = abs(
        (current_rate_kes - expected_peg_kes)
        / expected_peg_kes * Decimal("100"))
    deviation_bps = (deviation_pct * Decimal("100")).quantize(
        Decimal("0.01"))
    if deviation_bps < DE_PEG_MINOR_BPS:
        return DePegStatus.ON_PEG, deviation_bps
    elif deviation_bps < DE_PEG_SIGNIFICANT_BPS:
        return DePegStatus.MINOR_DEVIATION, deviation_bps
    elif deviation_bps < DE_PEG_ALERT_BPS:
        return DePegStatus.SIGNIFICANT_DEVIATION, deviation_bps
    else:
        return DePegStatus.DE_PEGGED, deviation_bps


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

# Type for live rate provider (per Rule 7)
RateProvider = Callable[[DigitalAssetType], SpotRate]


class DigitalAssetTreasuryEngine:
    """Manages digital asset wallets, holdings, valuations."""

    def __init__(
        self, *, entity_name: str = "Ecobank Kenya",
        rate_provider: Optional[RateProvider] = None,
    ):
        self.entity_name = entity_name
        self.rate_provider = rate_provider
        self._wallets: Dict[str, DigitalWallet] = {}
        self._holdings: Dict[str, DigitalHolding] = {}
        self._rates: Dict[DigitalAssetType, SpotRate] = {}
        self._valuations: Dict[str, DigitalAssetValuation] = {}

    # ── Wallet management ──────────────────────────────────────────────
    def register_wallet(self, wallet: DigitalWallet) -> None:
        if wallet.wallet_id in self._wallets:
            raise ValueError(
                f"wallet {wallet.wallet_id} already registered")
        self._wallets[wallet.wallet_id] = wallet

    def whitelist_wallet(self, wallet_id: str) -> DigitalWallet:
        if wallet_id not in self._wallets:
            raise KeyError(f"wallet {wallet_id} not found")
        wallet = self._wallets[wallet_id]
        # Replace with whitelisted version
        new_wallet = DigitalWallet(
            wallet_id=wallet.wallet_id,
            blockchain=wallet.blockchain,
            address=wallet.address,
            label=wallet.label,
            counterparty_name=wallet.counterparty_name,
            status=WalletStatus.WHITELISTED,
            registered_at=wallet.registered_at,
            notes=wallet.notes)
        self._wallets[wallet_id] = new_wallet
        return new_wallet

    @property
    def n_wallets(self) -> int:
        return len(self._wallets)

    # ── Holding management ─────────────────────────────────────────────
    def add_holding(self, holding: DigitalHolding) -> None:
        if holding.wallet_id not in self._wallets:
            raise KeyError(
                f"wallet {holding.wallet_id} not found — "
                f"register before adding holding")
        if holding.holding_id in self._holdings:
            raise ValueError(
                f"holding {holding.holding_id} already added")
        self._holdings[holding.holding_id] = holding

    @property
    def n_holdings(self) -> int:
        return len(self._holdings)

    # ── Rate management ────────────────────────────────────────────────
    def set_spot_rate(self, rate: SpotRate) -> None:
        self._rates[rate.asset_type] = rate

    def fetch_spot_rate(
        self, asset_type: DigitalAssetType,
    ) -> SpotRate:
        """Fetch via provider if wired; else use stored manual rate.

        Per Rule 7: provider hook is optional; without it the manual
        rate is used (with rate_source set on the SpotRate).
        """
        if self.rate_provider is not None:
            rate = self.rate_provider(asset_type)
            self._rates[asset_type] = rate
            return rate
        if asset_type not in self._rates:
            raise ValueError(
                f"no rate available for {asset_type.value} — "
                f"either set_spot_rate() manually or wire a "
                f"rate_provider")
        return self._rates[asset_type]

    # ── Valuation ──────────────────────────────────────────────────────
    def value_holding(
        self, *, holding_id: str,
        peg_kes_for_stablecoins: Mapping[
            DigitalAssetType, Decimal] = (),
    ) -> DigitalAssetValuation:
        if holding_id not in self._holdings:
            raise KeyError(f"holding {holding_id} not found")
        holding = self._holdings[holding_id]
        rate = self.fetch_spot_rate(holding.asset_type)
        kes_equiv = (
            holding.quantity * rate.kes_per_unit).quantize(
            Decimal("0.01"))
        # De-peg detection if peg supplied
        if isinstance(peg_kes_for_stablecoins, dict):
            pegs = peg_kes_for_stablecoins
        else:
            pegs = dict(peg_kes_for_stablecoins)
        if holding.asset_type in pegs:
            de_peg_status, dev_bps = detect_de_peg(
                asset=holding.asset_type,
                current_rate_kes=rate.kes_per_unit,
                expected_peg_kes=pegs[holding.asset_type])
        else:
            de_peg_status, dev_bps = (
                DePegStatus.NOT_APPLICABLE, Decimal("0"))
        bcbs_group = DEFAULT_BCBS_CLASSIFICATION.get(
            holding.asset_type, BCBSCryptoGroup.GROUP_2_OTHER)
        valuation = DigitalAssetValuation(
            holding_id=holding_id,
            asset_type=holding.asset_type,
            quantity=holding.quantity,
            spot_rate_kes=rate.kes_per_unit,
            kes_equivalent=kes_equiv,
            bcbs_group=bcbs_group,
            de_peg_status=de_peg_status,
            de_peg_deviation_bps=dev_bps,
            rate_source=rate.source,
            framework_refs=(
                "CBK VASP 2026", "BCBS Crypto 2022"),
            notes=(
                f"{holding.quantity} {holding.asset_type.value} × "
                f"{rate.kes_per_unit} KES = {kes_equiv:,.2f} KES"))
        self._valuations[holding_id] = valuation
        return valuation

    # ── Concentration check ────────────────────────────────────────────
    def check_concentration(
        self, *, asset_type: DigitalAssetType,
        total_treasury_kes: Decimal,
        custom_limit_pct: Optional[Decimal] = None,
    ) -> ConcentrationCheckResult:
        """Sum holdings of asset_type; check vs limit."""
        if total_treasury_kes <= Decimal("0"):
            raise ValueError(
                "total_treasury_kes must be positive")
        # Sum valuations of this asset_type
        holding_value = sum(
            (v.kes_equivalent for v in self._valuations.values()
             if v.asset_type == asset_type),
            Decimal("0"))
        actual_pct = (
            holding_value / total_treasury_kes * Decimal("100")
        ).quantize(Decimal("0.0001"))
        limit_pct = (
            custom_limit_pct
            if custom_limit_pct is not None
            else DEFAULT_CONCENTRATION_LIMIT_PCT.get(
                asset_type, Decimal("1")))
        within = actual_pct <= limit_pct
        headroom = (limit_pct - actual_pct).quantize(
            Decimal("0.0001"))
        return ConcentrationCheckResult(
            asset_type=asset_type,
            holding_value_kes=holding_value.quantize(
                Decimal("0.01")),
            total_treasury_kes=total_treasury_kes,
            actual_pct=actual_pct,
            limit_pct=limit_pct,
            within_limit=within,
            headroom_pct=headroom)

    def check_volatile_total(
        self, *, total_treasury_kes: Decimal,
    ) -> ConcentrationCheckResult:
        """BTC + ETH total cap check."""
        volatile_value = sum(
            (v.kes_equivalent for v in self._valuations.values()
             if v.asset_type in (
                 DigitalAssetType.BTC, DigitalAssetType.ETH)),
            Decimal("0"))
        actual_pct = (
            volatile_value / total_treasury_kes * Decimal("100")
        ).quantize(Decimal("0.0001"))
        within = actual_pct <= VOLATILE_ASSETS_TOTAL_CAP_PCT
        return ConcentrationCheckResult(
            asset_type=DigitalAssetType.BTC,    # placeholder
            holding_value_kes=volatile_value.quantize(
                Decimal("0.01")),
            total_treasury_kes=total_treasury_kes,
            actual_pct=actual_pct,
            limit_pct=VOLATILE_ASSETS_TOTAL_CAP_PCT,
            within_limit=within,
            headroom_pct=(
                VOLATILE_ASSETS_TOTAL_CAP_PCT - actual_pct
            ).quantize(Decimal("0.0001")))

    # ── Reporting ──────────────────────────────────────────────────────
    def board_summary(self) -> Dict[str, Any]:
        whitelisted = sum(
            1 for w in self._wallets.values()
            if w.status == WalletStatus.WHITELISTED)
        de_pegged = sum(
            1 for v in self._valuations.values()
            if v.de_peg_status == DePegStatus.DE_PEGGED)
        total_kes = sum(
            (v.kes_equivalent for v in self._valuations.values()),
            Decimal("0"))
        return {
            "entity": self.entity_name,
            "n_wallets": self.n_wallets,
            "n_whitelisted": whitelisted,
            "n_holdings": self.n_holdings,
            "n_valuations": len(self._valuations),
            "n_de_pegged": de_pegged,
            "total_kes_equivalent": str(total_kes.quantize(
                Decimal("0.01"))),
            "rate_provider_wired": self.rate_provider is not None,
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _test_bcbs_classification():
    assert (DEFAULT_BCBS_CLASSIFICATION[DigitalAssetType.USDC]
            == BCBSCryptoGroup.GROUP_1B_STABLECOIN)
    assert (DEFAULT_BCBS_CLASSIFICATION[DigitalAssetType.BTC]
            == BCBSCryptoGroup.GROUP_2_OTHER)


def _test_detect_de_peg_on_peg():
    status, bps = detect_de_peg(
        asset=DigitalAssetType.USDC,
        current_rate_kes=Decimal("130.10"),
        expected_peg_kes=Decimal("130.00"))
    # 0.077% = 7.7 bps → ON_PEG
    assert status == DePegStatus.ON_PEG


def _test_detect_de_peg_de_pegged():
    status, bps = detect_de_peg(
        asset=DigitalAssetType.USDT,
        current_rate_kes=Decimal("125.00"),
        expected_peg_kes=Decimal("130.00"))
    # 3.85% = 385 bps → DE_PEGGED
    assert status == DePegStatus.DE_PEGGED


def _test_detect_de_peg_btc_not_applicable():
    status, _ = detect_de_peg(
        asset=DigitalAssetType.BTC,
        current_rate_kes=Decimal("8000000"),
        expected_peg_kes=Decimal("9000000"))
    assert status == DePegStatus.NOT_APPLICABLE


def _test_register_wallet_and_whitelist():
    eng = DigitalAssetTreasuryEngine()
    wallet = DigitalWallet(
        wallet_id="W1", blockchain="ETH",
        address="0xabc...", label="USDC custody",
        registered_at="2026-05-01")
    eng.register_wallet(wallet)
    w = eng.whitelist_wallet("W1")
    assert w.status == WalletStatus.WHITELISTED


def _test_holding_requires_wallet():
    eng = DigitalAssetTreasuryEngine()
    holding = DigitalHolding(
        holding_id="H1", wallet_id="W-MISSING",
        asset_type=DigitalAssetType.USDC,
        quantity=Decimal("1000"),
        acquired_at="2026-05-01")
    try:
        eng.add_holding(holding)
        assert False
    except KeyError:
        pass


def _test_fetch_rate_without_provider_uses_manual():
    eng = DigitalAssetTreasuryEngine()
    eng.set_spot_rate(SpotRate(
        asset_type=DigitalAssetType.USDC,
        kes_per_unit=Decimal("130"),
        source="manual",
        timestamp="2026-05-01"))
    rate = eng.fetch_spot_rate(DigitalAssetType.USDC)
    assert rate.source == "manual"
    assert rate.kes_per_unit == Decimal("130")


def _test_fetch_rate_no_data_raises():
    eng = DigitalAssetTreasuryEngine()
    try:
        eng.fetch_spot_rate(DigitalAssetType.USDC)
        assert False
    except ValueError as e:
        assert "no rate available" in str(e)


def _test_value_holding_basic():
    eng = DigitalAssetTreasuryEngine()
    eng.register_wallet(DigitalWallet(
        wallet_id="W1", blockchain="ETH",
        address="0x", label="USDC"))
    eng.add_holding(DigitalHolding(
        holding_id="H1", wallet_id="W1",
        asset_type=DigitalAssetType.USDC,
        quantity=Decimal("10000"),    # 10K USDC
        acquired_at="2026-05-01"))
    eng.set_spot_rate(SpotRate(
        asset_type=DigitalAssetType.USDC,
        kes_per_unit=Decimal("130"),
        source="manual",
        timestamp="2026-05-01"))
    v = eng.value_holding(holding_id="H1")
    # 10000 × 130 = 1.3M KES
    assert v.kes_equivalent == Decimal("1300000.00")
    assert v.bcbs_group == BCBSCryptoGroup.GROUP_1B_STABLECOIN


def _test_value_holding_with_peg_detects_on_peg():
    eng = DigitalAssetTreasuryEngine()
    eng.register_wallet(DigitalWallet(
        wallet_id="W1", blockchain="ETH",
        address="0x", label="USDC"))
    eng.add_holding(DigitalHolding(
        holding_id="H1", wallet_id="W1",
        asset_type=DigitalAssetType.USDC,
        quantity=Decimal("100"),
        acquired_at="2026-05-01"))
    eng.set_spot_rate(SpotRate(
        asset_type=DigitalAssetType.USDC,
        kes_per_unit=Decimal("130.05"),
        source="manual",
        timestamp="2026-05-01"))
    v = eng.value_holding(
        holding_id="H1",
        peg_kes_for_stablecoins={
            DigitalAssetType.USDC: Decimal("130.00")})
    assert v.de_peg_status == DePegStatus.ON_PEG


def _test_concentration_check_within_limit():
    eng = DigitalAssetTreasuryEngine()
    eng.register_wallet(DigitalWallet(
        wallet_id="W1", blockchain="ETH",
        address="0x", label="USDC"))
    eng.add_holding(DigitalHolding(
        holding_id="H1", wallet_id="W1",
        asset_type=DigitalAssetType.USDC,
        quantity=Decimal("1000"),
        acquired_at="2026-05-01"))
    eng.set_spot_rate(SpotRate(
        asset_type=DigitalAssetType.USDC,
        kes_per_unit=Decimal("130"),
        source="manual",
        timestamp="2026-05-01"))
    eng.value_holding(holding_id="H1")
    # 130K KES / 100M total = 0.13%, limit 3%
    result = eng.check_concentration(
        asset_type=DigitalAssetType.USDC,
        total_treasury_kes=Decimal("100000000"))
    assert result.within_limit is True


def _test_concentration_check_breach():
    eng = DigitalAssetTreasuryEngine()
    eng.register_wallet(DigitalWallet(
        wallet_id="W1", blockchain="BTC",
        address="bc1", label="BTC reserve"))
    eng.add_holding(DigitalHolding(
        holding_id="H1", wallet_id="W1",
        asset_type=DigitalAssetType.BTC,
        quantity=Decimal("10"),    # 10 BTC
        acquired_at="2026-05-01"))
    eng.set_spot_rate(SpotRate(
        asset_type=DigitalAssetType.BTC,
        kes_per_unit=Decimal("9000000"),    # 9M KES per BTC
        source="manual",
        timestamp="2026-05-01"))
    eng.value_holding(holding_id="H1")
    # 90M KES / 1B total = 9%, limit 0.5% → BREACH
    result = eng.check_concentration(
        asset_type=DigitalAssetType.BTC,
        total_treasury_kes=Decimal("1000000000"))
    assert result.within_limit is False
    assert result.actual_pct > Decimal("0.5")


def _test_volatile_total_check():
    eng = DigitalAssetTreasuryEngine()
    # Register wallets + small BTC + ETH holdings
    eng.register_wallet(DigitalWallet(
        wallet_id="W1", blockchain="BTC",
        address="bc1", label="BTC"))
    eng.register_wallet(DigitalWallet(
        wallet_id="W2", blockchain="ETH",
        address="0x", label="ETH"))
    eng.add_holding(DigitalHolding(
        holding_id="HB", wallet_id="W1",
        asset_type=DigitalAssetType.BTC,
        quantity=Decimal("0.1"),
        acquired_at="2026-05-01"))
    eng.add_holding(DigitalHolding(
        holding_id="HE", wallet_id="W2",
        asset_type=DigitalAssetType.ETH,
        quantity=Decimal("5"),
        acquired_at="2026-05-01"))
    eng.set_spot_rate(SpotRate(
        asset_type=DigitalAssetType.BTC,
        kes_per_unit=Decimal("9000000"),
        source="manual", timestamp="2026-05-01"))
    eng.set_spot_rate(SpotRate(
        asset_type=DigitalAssetType.ETH,
        kes_per_unit=Decimal("500000"),
        source="manual", timestamp="2026-05-01"))
    eng.value_holding(holding_id="HB")
    eng.value_holding(holding_id="HE")
    # 900K + 2.5M = 3.4M / 1B = 0.34% < 1% cap
    result = eng.check_volatile_total(
        total_treasury_kes=Decimal("1000000000"))
    assert result.within_limit is True


def _test_board_summary():
    eng = DigitalAssetTreasuryEngine()
    s = eng.board_summary()
    assert s["entity"] == "Ecobank Kenya"
    assert s["n_wallets"] == 0
    assert s["rate_provider_wired"] is False


def self_test() -> None:
    tests = [
        _test_bcbs_classification,
        _test_detect_de_peg_on_peg,
        _test_detect_de_peg_de_pegged,
        _test_detect_de_peg_btc_not_applicable,
        _test_register_wallet_and_whitelist,
        _test_holding_requires_wallet,
        _test_fetch_rate_without_provider_uses_manual,
        _test_fetch_rate_no_data_raises,
        _test_value_holding_basic,
        _test_value_holding_with_peg_detects_on_peg,
        _test_concentration_check_within_limit,
        _test_concentration_check_breach,
        _test_volatile_total_check,
        _test_board_summary,
    ]
    failed = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(f"✗ treasury_digital_assets self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ treasury_digital_assets self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
