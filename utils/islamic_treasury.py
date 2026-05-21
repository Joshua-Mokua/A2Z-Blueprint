"""utils/islamic_treasury.py — v10.37 ENH-239: Islamic Treasury Products.

╔════════════════════════════════════════════════════════════════════════╗
║  ISLAMIC TREASURY PRODUCTS — Sharia-compliant non-interest products    ║
║  Cat A — implements ENH-239 per AAOIFI / IFSB standards               ║
╠════════════════════════════════════════════════════════════════════════╣
║  Implements ENH-239: Sharia-compliant treasury products.              ║
║                                                                         ║
║  Core principle: Riba (interest) is prohibited in Islamic finance.    ║
║  All products replace interest with profit-sharing, asset-backing,    ║
║  or fee-based structures.                                              ║
║                                                                         ║
║  Six product types ship:                                               ║
║    MURABAHA: cost-plus-markup sale; bank buys asset, sells to         ║
║      customer at marked-up price; deferred payment. Markup is        ║
║      disclosed at contract; not interest because tied to a specific  ║
║      asset purchase. Common for trade finance.                       ║
║    WAKALA: agency arrangement; investor (Muwakkil) appoints bank    ║
║      (Wakil) to invest on their behalf. Bank earns fixed fee +     ║
║      may earn performance incentive. Used for treasury liquidity.  ║
║    SUKUK: Islamic bond; investor owns proportional share of         ║
║      underlying asset/project. Returns from asset's economic       ║
║      performance, not coupon. Eligible HQLA-equivalent if           ║
║      structured as Sukuk Ijara on tangible assets.                  ║
║    MUDARABAH: profit-sharing partnership; investor provides capital,║
║      bank provides expertise. Returns split per pre-agreed ratio.  ║
║      Loss falls on capital provider unless bank negligent.         ║
║    IJARAH: leasing; bank buys asset, leases to customer. Lease     ║
║      payments are rent for use of asset, not interest. May end    ║
║      in ownership transfer (Ijara wa Iqtina) or revert to bank.    ║
║    QARD HASAN: benevolent loan; principal-only repayment, no       ║
║      markup. Used for charitable/community purposes; rare in       ║
║      commercial treasury.                                            ║
║                                                                         ║
║  Sharia compliance audit fields per AAOIFI FAS 28 + IFSB-7:           ║
║    - sharia_board_approval_date                                       ║
║    - underlying_asset_required (Murabaha/Sukuk/Ijarah)               ║
║    - profit_sharing_disclosed (Mudarabah/Wakala)                     ║
║    - prohibited_industries (alcohol/pork/gambling/conventional bank) ║
║                                                                         ║
║  Coexists with conventional treasury products (utils/treasury_       ║
║  products.py); banks running Islamic windows alongside conventional ║
║  banking need both registries side-by-side.                          ║
║                                                                         ║
║  Honesty Rule 1: every IslamicProductValuation surfaces principal +   ║
║  markup_or_profit + sharia_compliant flag + non-compliance_reasons + ║
║  AAOIFI/IFSB framework refs. Dual-currency support (KES + AED for     ║
║  Gulf-region funding).                                                 ║
║  Honesty Rule 7: profit-sharing rates for Mudarabah/Wakala without    ║
║  formal sharia board approval raise REQUIRES_PROVIDER:                ║
║  sharia_supervisory_board.                                             ║
╠════════════════════════════════════════════════════════════════════════╣
║  Regulatory provenance:                                                 ║
║    AAOIFI FAS 28 — Murabaha & other deferred payment sales            ║
║    AAOIFI FAS 30 — Impairment, credit losses, onerous commitments    ║
║    AAOIFI Sharia Standard 8 — Murabaha to the purchase orderer       ║
║    AAOIFI Sharia Standard 17 — Investment Sukuk                      ║
║    AAOIFI Sharia Standard 23 — Agency (Wakala)                       ║
║    IFSB-7 — Capital adequacy for Sukuk, securitisations & RE         ║
║    IFSB-12 — Liquidity risk management for IFSI                      ║
║    CBK Banking Act §47 — Islamic banking provisions                   ║
║    CBK Prudential Guideline (Islamic) — operational requirements     ║
║    Kenya Finance Act 2017 — Islamic finance tax neutrality            ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from typing import (
    Any, Dict, List, Mapping, Optional, Sequence, Tuple)

getcontext().prec = 28

SPEC_DEVIATION_NOTE = (
    "IslamicTreasuryEngine implements ENH-239 per AAOIFI + IFSB. "
    "Six core product types: Murabaha, Wakala, Sukuk, Mudarabah, "
    "Ijarah, Qard Hasan. Per Rule 1, every valuation surfaces "
    "principal + markup/profit + Sharia compliance flag + AAOIFI/"
    "IFSB framework refs. Per Rule 7, Mudarabah/Wakala profit rates "
    "without formal Sharia board approval raise REQUIRES_PROVIDER."
)

# ════════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════════════════════════════════

# Industries prohibited under Sharia (haram)
PROHIBITED_INDUSTRIES: Tuple[str, ...] = (
    "alcohol", "pork", "gambling", "conventional_banking",
    "conventional_insurance", "tobacco", "weapons", "adult_entertainment")

# Minimum tangible-asset ratio for Sukuk-Ijara (AAOIFI guidance)
SUKUK_IJARA_MIN_TANGIBLE_RATIO = Decimal("0.51")

# Maximum acceptable haram revenue ratio (5% per AAOIFI tolerance)
MAX_HARAM_REVENUE_RATIO = Decimal("0.05")


# ════════════════════════════════════════════════════════════════════════
# Product taxonomy
# ════════════════════════════════════════════════════════════════════════

class IslamicProductType(Enum):
    """Six core Islamic treasury product types."""
    MURABAHA = "MURABAHA"
    WAKALA = "WAKALA"
    SUKUK = "SUKUK"
    MUDARABAH = "MUDARABAH"
    IJARAH = "IJARAH"
    QARD_HASAN = "QARD_HASAN"


class SukukStructure(Enum):
    """Sukuk sub-structures per AAOIFI Sharia Standard 17."""
    SUKUK_IJARA = "SUKUK_IJARA"           # leasing-backed (HQLA-eligible)
    SUKUK_MURABAHA = "SUKUK_MURABAHA"     # trade-finance backed
    SUKUK_MUDARABA = "SUKUK_MUDARABA"     # PSP-backed
    SUKUK_WAKALA = "SUKUK_WAKALA"         # agency-backed
    SUKUK_HYBRID = "SUKUK_HYBRID"         # mixed pool


class ShariaComplianceStatus(Enum):
    """Outcome of compliance check."""
    COMPLIANT = "COMPLIANT"
    PROVISIONAL = "PROVISIONAL"           # pending Sharia board sign-off
    NON_COMPLIANT = "NON_COMPLIANT"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"


# ════════════════════════════════════════════════════════════════════════
# Product dataclasses
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class IslamicProduct:
    """Generic Islamic treasury product."""
    product_id: str
    product_type: IslamicProductType
    counterparty: str
    principal_kes: Decimal               # capital amount
    contract_date: str                    # ISO-8601
    maturity_date: str
    currency: str = "KES"
    # Structure-specific fields (only some apply per type)
    markup_pct: Optional[Decimal] = None  # Murabaha cost-plus
    profit_share_ratio: Optional[Decimal] = None  # Mudarabah/Wakala
    fixed_fee_kes: Optional[Decimal] = None  # Wakala fee
    rental_kes: Optional[Decimal] = None  # Ijarah lease payment
    sukuk_structure: Optional[SukukStructure] = None
    underlying_asset_description: str = ""
    sharia_board_approval_date: Optional[str] = None
    sharia_board_reference: str = ""
    counterparty_business_sector: str = ""
    notes: str = ""

    def is_asset_backed_required(self) -> bool:
        """Some structures require tangible underlying asset."""
        return self.product_type in (
            IslamicProductType.MURABAHA,
            IslamicProductType.IJARAH,
            IslamicProductType.SUKUK)


@dataclass(frozen=True)
class IslamicProductValuation:
    """Result of valuing/checking an Islamic product."""
    product_id: str
    product_type: IslamicProductType
    principal_kes: Decimal
    expected_return_kes: Decimal          # markup, profit, rental sum
    total_payable_kes: Decimal            # principal + return
    sharia_compliance: ShariaComplianceStatus
    non_compliance_reasons: Tuple[str, ...]
    framework_refs: Tuple[str, ...]
    notes: str = ""


# ════════════════════════════════════════════════════════════════════════
# Sharia compliance checks
# ════════════════════════════════════════════════════════════════════════

def check_sharia_compliance(
    product: IslamicProduct,
) -> Tuple[ShariaComplianceStatus, Tuple[str, ...]]:
    """Evaluate product against AAOIFI/IFSB requirements."""
    reasons: List[str] = []

    # 1. Counterparty industry must not be prohibited
    if product.counterparty_business_sector:
        sector_lower = product.counterparty_business_sector.lower()
        for prohibited in PROHIBITED_INDUSTRIES:
            if prohibited in sector_lower:
                reasons.append(
                    f"counterparty operates in prohibited industry: "
                    f"{prohibited}")

    # 2. Asset-backed products require underlying asset description
    if (product.is_asset_backed_required()
            and not product.underlying_asset_description):
        reasons.append(
            f"{product.product_type.value} requires "
            f"underlying_asset_description (AAOIFI Sharia Std 8/17)")

    # 3. Murabaha must disclose markup
    if (product.product_type == IslamicProductType.MURABAHA
            and product.markup_pct is None):
        reasons.append(
            "Murabaha requires disclosed markup_pct at contract "
            "(AAOIFI Sharia Std 8 §3/2/1)")

    # 4. Mudarabah/Wakala profit-sharing requires ratio disclosure
    if (product.product_type
            in (IslamicProductType.MUDARABAH,
                IslamicProductType.WAKALA)
            and product.profit_share_ratio is None
            and product.fixed_fee_kes is None):
        reasons.append(
            f"{product.product_type.value} requires either "
            f"profit_share_ratio or fixed_fee_kes "
            f"(AAOIFI Sharia Std 23)")

    # 5. Ijarah requires rental
    if (product.product_type == IslamicProductType.IJARAH
            and (product.rental_kes is None
                 or product.rental_kes <= Decimal("0"))):
        reasons.append(
            "Ijarah requires positive rental_kes (rent for use of "
            "asset; not interest)")

    # 6. Qard Hasan must have zero markup
    if (product.product_type == IslamicProductType.QARD_HASAN
            and product.markup_pct is not None
            and product.markup_pct != Decimal("0")):
        reasons.append(
            "Qard Hasan must have zero markup (benevolent loan; "
            "principal-only repayment)")

    # Determine status
    if reasons:
        return ShariaComplianceStatus.NON_COMPLIANT, tuple(reasons)
    if product.sharia_board_approval_date is None:
        return (
            ShariaComplianceStatus.PROVISIONAL,
            ("pending Sharia Supervisory Board approval — set "
             "sharia_board_approval_date when received",))
    return ShariaComplianceStatus.COMPLIANT, ()


# ════════════════════════════════════════════════════════════════════════
# Per-product valuation
# ════════════════════════════════════════════════════════════════════════

def value_murabaha(product: IslamicProduct) -> IslamicProductValuation:
    """Murabaha: cost + disclosed markup."""
    if product.product_type != IslamicProductType.MURABAHA:
        raise ValueError("not a Murabaha product")
    markup = product.markup_pct if product.markup_pct else Decimal("0")
    expected_return = (
        product.principal_kes * markup / Decimal("100")).quantize(
        Decimal("0.01"))
    total = (product.principal_kes + expected_return).quantize(
        Decimal("0.01"))
    status, reasons = check_sharia_compliance(product)
    return IslamicProductValuation(
        product_id=product.product_id,
        product_type=product.product_type,
        principal_kes=product.principal_kes,
        expected_return_kes=expected_return,
        total_payable_kes=total,
        sharia_compliance=status,
        non_compliance_reasons=reasons,
        framework_refs=(
            "AAOIFI FAS 28", "AAOIFI Sharia Std 8"),
        notes=f"cost-plus markup {markup}% disclosed at contract")


def value_wakala(
    product: IslamicProduct,
    require_sharia_board_for_profit: bool = False,
) -> IslamicProductValuation:
    """Wakala: fixed fee or profit-sharing.

    Per Rule 7: if require_sharia_board_for_profit=True and product
    uses profit_share_ratio without sharia_board_approval_date,
    raises REQUIRES_PROVIDER.
    """
    if product.product_type != IslamicProductType.WAKALA:
        raise ValueError("not a Wakala product")
    if (require_sharia_board_for_profit
            and product.profit_share_ratio is not None
            and product.sharia_board_approval_date is None):
        raise ValueError(
            "REQUIRES_PROVIDER: sharia_supervisory_board — "
            "Wakala profit-sharing requires Sharia board sign-off "
            "before valuation can proceed")
    if product.fixed_fee_kes is not None:
        expected_return = product.fixed_fee_kes
    elif product.profit_share_ratio is not None:
        # Estimate using assumed gross return = principal × 5% p.a.
        # (placeholder; real calc reads investment performance)
        # Per Rule 1: this is a NOMINAL projection; actual is
        # determined by underlying investment performance.
        gross_return = (
            product.principal_kes * Decimal("0.05")).quantize(
            Decimal("0.01"))
        expected_return = (
            gross_return * product.profit_share_ratio).quantize(
            Decimal("0.01"))
    else:
        expected_return = Decimal("0")
    total = (product.principal_kes + expected_return).quantize(
        Decimal("0.01"))
    status, reasons = check_sharia_compliance(product)
    return IslamicProductValuation(
        product_id=product.product_id,
        product_type=product.product_type,
        principal_kes=product.principal_kes,
        expected_return_kes=expected_return,
        total_payable_kes=total,
        sharia_compliance=status,
        non_compliance_reasons=reasons,
        framework_refs=(
            "AAOIFI Sharia Std 23", "IFSB-12"),
        notes=(
            "fixed-fee Wakala"
            if product.fixed_fee_kes is not None
            else "profit-sharing Wakala (nominal 5% gross assumption)"))


def value_sukuk(product: IslamicProduct) -> IslamicProductValuation:
    """Sukuk: ownership share of underlying asset/project."""
    if product.product_type != IslamicProductType.SUKUK:
        raise ValueError("not a Sukuk product")
    # Expected return depends on structure
    if product.sukuk_structure == SukukStructure.SUKUK_IJARA:
        # Rental-based; estimated 8% p.a.
        annual = (
            product.principal_kes * Decimal("0.08")).quantize(
            Decimal("0.01"))
        expected_return = annual
    elif product.sukuk_structure == SukukStructure.SUKUK_MURABAHA:
        markup = (
            product.markup_pct if product.markup_pct else Decimal("0"))
        expected_return = (
            product.principal_kes * markup / Decimal("100")).quantize(
            Decimal("0.01"))
    else:
        # Other structures: profit-sharing based; placeholder
        expected_return = (
            product.principal_kes * Decimal("0.06")).quantize(
            Decimal("0.01"))
    total = (product.principal_kes + expected_return).quantize(
        Decimal("0.01"))
    status, reasons = check_sharia_compliance(product)
    # HQLA eligibility check: only Sukuk-Ijara on sovereign/quasi-sov
    notes = f"Sukuk structure: {product.sukuk_structure}"
    if product.sukuk_structure == SukukStructure.SUKUK_IJARA:
        notes += " — potentially HQLA-eligible (IFSB-12 §3.4)"
    return IslamicProductValuation(
        product_id=product.product_id,
        product_type=product.product_type,
        principal_kes=product.principal_kes,
        expected_return_kes=expected_return,
        total_payable_kes=total,
        sharia_compliance=status,
        non_compliance_reasons=reasons,
        framework_refs=(
            "AAOIFI Sharia Std 17", "IFSB-7"),
        notes=notes)


def value_ijarah(product: IslamicProduct) -> IslamicProductValuation:
    """Ijarah: lease payments are rent."""
    if product.product_type != IslamicProductType.IJARAH:
        raise ValueError("not an Ijarah product")
    rental = (
        product.rental_kes if product.rental_kes else Decimal("0"))
    # Total rental = monthly rental × 12 × tenor (assume 1y default)
    expected_return = (rental * Decimal("12")).quantize(
        Decimal("0.01"))
    total = (product.principal_kes + expected_return).quantize(
        Decimal("0.01"))
    status, reasons = check_sharia_compliance(product)
    return IslamicProductValuation(
        product_id=product.product_id,
        product_type=product.product_type,
        principal_kes=product.principal_kes,
        expected_return_kes=expected_return,
        total_payable_kes=total,
        sharia_compliance=status,
        non_compliance_reasons=reasons,
        framework_refs=(
            "AAOIFI FAS 8", "IFSB-7"),
        notes=f"monthly rental {rental:,.2f} × 12")


def value_mudarabah(
    product: IslamicProduct,
    require_sharia_board_for_profit: bool = False,
) -> IslamicProductValuation:
    """Mudarabah: pre-agreed profit-sharing ratio."""
    if product.product_type != IslamicProductType.MUDARABAH:
        raise ValueError("not a Mudarabah product")
    if (require_sharia_board_for_profit
            and product.profit_share_ratio is not None
            and product.sharia_board_approval_date is None):
        raise ValueError(
            "REQUIRES_PROVIDER: sharia_supervisory_board — "
            "Mudarabah profit-sharing requires Sharia board sign-off")
    if product.profit_share_ratio is None:
        expected_return = Decimal("0")
    else:
        # Nominal gross return assumption 6% p.a. (placeholder)
        gross_return = (
            product.principal_kes * Decimal("0.06")).quantize(
            Decimal("0.01"))
        expected_return = (
            gross_return * product.profit_share_ratio).quantize(
            Decimal("0.01"))
    total = (product.principal_kes + expected_return).quantize(
        Decimal("0.01"))
    status, reasons = check_sharia_compliance(product)
    return IslamicProductValuation(
        product_id=product.product_id,
        product_type=product.product_type,
        principal_kes=product.principal_kes,
        expected_return_kes=expected_return,
        total_payable_kes=total,
        sharia_compliance=status,
        non_compliance_reasons=reasons,
        framework_refs=(
            "AAOIFI FAS 30", "AAOIFI Sharia Std 13"),
        notes=(
            f"profit-share ratio "
            f"{product.profit_share_ratio} (nominal 6% gross)"))


def value_qard_hasan(
    product: IslamicProduct,
) -> IslamicProductValuation:
    """Qard Hasan: principal-only, no markup."""
    if product.product_type != IslamicProductType.QARD_HASAN:
        raise ValueError("not a Qard Hasan product")
    status, reasons = check_sharia_compliance(product)
    return IslamicProductValuation(
        product_id=product.product_id,
        product_type=product.product_type,
        principal_kes=product.principal_kes,
        expected_return_kes=Decimal("0"),
        total_payable_kes=product.principal_kes,
        sharia_compliance=status,
        non_compliance_reasons=reasons,
        framework_refs=("AAOIFI Sharia Std 19",),
        notes="benevolent loan — principal-only repayment")


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class IslamicTreasuryEngine:
    """Orchestrator for ENH-239 Islamic treasury products."""

    def __init__(
        self, *, entity_name: str = "Ecobank Kenya — Islamic Window",
        require_sharia_board: bool = False,
    ):
        self.entity_name = entity_name
        self.require_sharia_board = require_sharia_board
        self._products: Dict[str, IslamicProduct] = {}
        self._valuations: Dict[str, IslamicProductValuation] = {}

    def register_product(
        self, product: IslamicProduct,
    ) -> None:
        if product.product_id in self._products:
            raise ValueError(
                f"product {product.product_id} already registered")
        self._products[product.product_id] = product

    def value_product(
        self, product_id: str,
    ) -> IslamicProductValuation:
        if product_id not in self._products:
            raise KeyError(f"product {product_id} not found")
        product = self._products[product_id]
        if product.product_type == IslamicProductType.MURABAHA:
            v = value_murabaha(product)
        elif product.product_type == IslamicProductType.WAKALA:
            v = value_wakala(
                product,
                require_sharia_board_for_profit=(
                    self.require_sharia_board))
        elif product.product_type == IslamicProductType.SUKUK:
            v = value_sukuk(product)
        elif product.product_type == IslamicProductType.IJARAH:
            v = value_ijarah(product)
        elif product.product_type == IslamicProductType.MUDARABAH:
            v = value_mudarabah(
                product,
                require_sharia_board_for_profit=(
                    self.require_sharia_board))
        elif product.product_type == IslamicProductType.QARD_HASAN:
            v = value_qard_hasan(product)
        else:
            raise ValueError(
                f"unsupported type: {product.product_type}")
        self._valuations[product_id] = v
        return v

    def value_all(self) -> Tuple[IslamicProductValuation, ...]:
        return tuple(
            self.value_product(pid) for pid in self._products)

    @property
    def product_count(self) -> int:
        return len(self._products)

    def non_compliant_products(
        self,
    ) -> Tuple[IslamicProductValuation, ...]:
        return tuple(
            v for v in self._valuations.values()
            if v.sharia_compliance ==
            ShariaComplianceStatus.NON_COMPLIANT)

    def board_summary(self) -> Dict[str, Any]:
        compliant = sum(
            1 for v in self._valuations.values()
            if v.sharia_compliance ==
            ShariaComplianceStatus.COMPLIANT)
        provisional = sum(
            1 for v in self._valuations.values()
            if v.sharia_compliance ==
            ShariaComplianceStatus.PROVISIONAL)
        non_comp = sum(
            1 for v in self._valuations.values()
            if v.sharia_compliance ==
            ShariaComplianceStatus.NON_COMPLIANT)
        total_principal = sum(
            (p.principal_kes for p in self._products.values()),
            Decimal("0"))
        total_return = sum(
            (v.expected_return_kes
             for v in self._valuations.values()),
            Decimal("0"))
        return {
            "entity": self.entity_name,
            "n_products": self.product_count,
            "n_valuations": len(self._valuations),
            "n_compliant": compliant,
            "n_provisional": provisional,
            "n_non_compliant": non_comp,
            "total_principal_kes": str(total_principal),
            "total_expected_return_kes": str(total_return),
            "require_sharia_board": self.require_sharia_board,
        }


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_murabaha() -> IslamicProduct:
    return IslamicProduct(
        product_id="MUR-001",
        product_type=IslamicProductType.MURABAHA,
        counterparty="Trade Co Ltd",
        principal_kes=Decimal("10000000"),
        contract_date="2026-05-01",
        maturity_date="2027-05-01",
        markup_pct=Decimal("8"),
        underlying_asset_description="100 MT steel inventory",
        sharia_board_approval_date="2026-04-15",
        sharia_board_reference="SSB-2026-042",
        counterparty_business_sector="manufacturing")


def _test_murabaha_valuation():
    p = _make_murabaha()
    v = value_murabaha(p)
    # 10M × 8% = 800K markup; total 10.8M
    assert v.expected_return_kes == Decimal("800000.00")
    assert v.total_payable_kes == Decimal("10800000.00")
    assert v.sharia_compliance == ShariaComplianceStatus.COMPLIANT


def _test_murabaha_no_underlying_asset_fails():
    p = IslamicProduct(
        product_id="MUR-002",
        product_type=IslamicProductType.MURABAHA,
        counterparty="X",
        principal_kes=Decimal("1000000"),
        contract_date="2026-05-01",
        maturity_date="2027-05-01",
        markup_pct=Decimal("5"))
    v = value_murabaha(p)
    assert v.sharia_compliance == ShariaComplianceStatus.NON_COMPLIANT
    assert any("underlying_asset" in r
               for r in v.non_compliance_reasons)


def _test_murabaha_haram_industry_fails():
    p = IslamicProduct(
        product_id="MUR-003",
        product_type=IslamicProductType.MURABAHA,
        counterparty="Brewery Co",
        principal_kes=Decimal("1000000"),
        contract_date="2026-05-01",
        maturity_date="2027-05-01",
        markup_pct=Decimal("5"),
        underlying_asset_description="bottling line",
        counterparty_business_sector="alcohol production")
    v = value_murabaha(p)
    assert v.sharia_compliance == ShariaComplianceStatus.NON_COMPLIANT


def _test_wakala_fixed_fee_valuation():
    p = IslamicProduct(
        product_id="WAK-001",
        product_type=IslamicProductType.WAKALA,
        counterparty="Sovereign Liquidity Fund",
        principal_kes=Decimal("100000000"),
        contract_date="2026-05-01",
        maturity_date="2026-08-01",
        fixed_fee_kes=Decimal("250000"),
        sharia_board_approval_date="2026-04-15",
        underlying_asset_description="diversified Sukuk pool",
        counterparty_business_sector="public_sector")
    v = value_wakala(p)
    assert v.expected_return_kes == Decimal("250000")


def _test_wakala_profit_sharing_requires_board():
    p = IslamicProduct(
        product_id="WAK-002",
        product_type=IslamicProductType.WAKALA,
        counterparty="X",
        principal_kes=Decimal("10000000"),
        contract_date="2026-05-01",
        maturity_date="2027-05-01",
        profit_share_ratio=Decimal("0.7"),
        sharia_board_approval_date=None)    # no approval
    try:
        value_wakala(p, require_sharia_board_for_profit=True)
        assert False
    except ValueError as e:
        assert "REQUIRES_PROVIDER" in str(e)


def _test_sukuk_ijara_valuation():
    p = IslamicProduct(
        product_id="SUK-001",
        product_type=IslamicProductType.SUKUK,
        counterparty="Govt of Kenya",
        principal_kes=Decimal("100000000"),
        contract_date="2026-05-01",
        maturity_date="2031-05-01",
        sukuk_structure=SukukStructure.SUKUK_IJARA,
        underlying_asset_description="port lease assets",
        sharia_board_approval_date="2026-04-15",
        counterparty_business_sector="public_sector")
    v = value_sukuk(p)
    # 8% nominal annual
    assert v.expected_return_kes == Decimal("8000000.00")
    assert v.sharia_compliance == ShariaComplianceStatus.COMPLIANT
    assert "HQLA" in v.notes


def _test_ijarah_rental_valuation():
    p = IslamicProduct(
        product_id="IJA-001",
        product_type=IslamicProductType.IJARAH,
        counterparty="Logistics Co",
        principal_kes=Decimal("5000000"),    # asset cost
        contract_date="2026-05-01",
        maturity_date="2027-05-01",
        rental_kes=Decimal("50000"),         # monthly
        underlying_asset_description="warehouse equipment",
        sharia_board_approval_date="2026-04-15",
        counterparty_business_sector="logistics")
    v = value_ijarah(p)
    assert v.expected_return_kes == Decimal("600000.00")    # 50K×12


def _test_qard_hasan_zero_markup():
    p = IslamicProduct(
        product_id="QAR-001",
        product_type=IslamicProductType.QARD_HASAN,
        counterparty="Community Fund",
        principal_kes=Decimal("1000000"),
        contract_date="2026-05-01",
        maturity_date="2027-05-01",
        markup_pct=Decimal("0"),
        sharia_board_approval_date="2026-04-15")
    v = value_qard_hasan(p)
    assert v.expected_return_kes == Decimal("0")
    assert v.total_payable_kes == p.principal_kes


def _test_qard_hasan_with_markup_fails():
    p = IslamicProduct(
        product_id="QAR-002",
        product_type=IslamicProductType.QARD_HASAN,
        counterparty="X",
        principal_kes=Decimal("1000000"),
        contract_date="2026-05-01",
        maturity_date="2027-05-01",
        markup_pct=Decimal("3"))    # not zero
    v = value_qard_hasan(p)
    assert v.sharia_compliance == ShariaComplianceStatus.NON_COMPLIANT


def _test_engine_register_and_value():
    eng = IslamicTreasuryEngine()
    eng.register_product(_make_murabaha())
    v = eng.value_product("MUR-001")
    assert v.expected_return_kes == Decimal("800000.00")


def _test_engine_dup_id_raises():
    eng = IslamicTreasuryEngine()
    eng.register_product(_make_murabaha())
    try:
        eng.register_product(_make_murabaha())
        assert False
    except ValueError:
        pass


def _test_engine_value_all_aggregates():
    eng = IslamicTreasuryEngine()
    eng.register_product(_make_murabaha())
    vs = eng.value_all()
    assert len(vs) == 1


def _test_engine_board_summary():
    eng = IslamicTreasuryEngine()
    eng.register_product(_make_murabaha())
    eng.value_all()
    s = eng.board_summary()
    assert s["n_compliant"] == 1
    assert s["n_non_compliant"] == 0
    assert s["total_principal_kes"] == "10000000"


def _test_engine_non_compliant_filter():
    eng = IslamicTreasuryEngine()
    bad = IslamicProduct(
        product_id="BAD-001",
        product_type=IslamicProductType.MURABAHA,
        counterparty="Casino Co",
        principal_kes=Decimal("1000000"),
        contract_date="2026-05-01",
        maturity_date="2027-05-01",
        markup_pct=Decimal("5"),
        underlying_asset_description="slot machines",
        counterparty_business_sector="gambling")
    eng.register_product(bad)
    eng.value_all()
    assert len(eng.non_compliant_products()) == 1


def self_test() -> None:
    tests = [
        _test_murabaha_valuation,
        _test_murabaha_no_underlying_asset_fails,
        _test_murabaha_haram_industry_fails,
        _test_wakala_fixed_fee_valuation,
        _test_wakala_profit_sharing_requires_board,
        _test_sukuk_ijara_valuation,
        _test_ijarah_rental_valuation,
        _test_qard_hasan_zero_markup,
        _test_qard_hasan_with_markup_fails,
        _test_engine_register_and_value,
        _test_engine_dup_id_raises,
        _test_engine_value_all_aggregates,
        _test_engine_board_summary,
        _test_engine_non_compliant_filter,
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
        print(f"✗ islamic_treasury self-test: "
              f"{len(failed)} failures", file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(f"✓ islamic_treasury self-test passed "
          f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
