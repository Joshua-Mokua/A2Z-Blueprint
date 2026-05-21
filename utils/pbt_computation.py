"""utils/pbt_computation.py — v10.364 PBT computation from CBS + OpEx.

Closes the highest-priority MD BSC gap: bank_targets.json::PBT|2026 has
target 650B but no CBS-computable actual existed before v10.364.

What this module produces
-------------------------
PBT (Profit Before Tax) = Operating Income - OpEx - Impairment

Where:
  Operating Income = NII + Non-Interest Income
  NII (Net Interest Income) = Interest Income - Interest Expense
  Non-Interest Income       = Fee Income + Other Non-Interest
  OpEx                       = Staff + IT + Premises + Other
  Impairment                 = NPL Stage 3 × LGD%

Data sources
------------
1. CBS accounts.csv (via aggregate flows)
   - Interest Income YTD: sum of interest_income_ytd
   - Fee Income YTD: sum of fee_income_ytd
   - Loan portfolio (NPL × LGD → impairment)
   - Deposit base (× cost_of_funds_pct → interest expense, configurable)

2. data/opex_data.json (configurable via admin/finance)
   - total_opex_kes_b (preferred — direct value)
   - OR staff_costs + it_costs + premises + other_opex (computed)
   - OR fallback to cir_pct * operating_income (computed)

3. data/pbt_assumptions.json (NEW in v10.364 — configurable factors)
   - cost_of_funds_pct: % of deposits paid as interest expense (default 3%)
   - lgd_pct: Loss Given Default % for impairment (default 45%, per Basel)
   - non_interest_other_pct: % uplift on fee income for FX/investment income (default 15%)

Why a separate module
---------------------
PBT is a composite metric — not a single CBS aggregation. Keeping it in
its own module makes the assumptions visible and configurable. Per Rule N1,
all factors must be admin-configurable, not hardcoded.

How callers use it
------------------
utils.actuals_engine.compute_bank_aggregates calls compute_pbt_from_cbs
and includes the returned PBT in its result dict. The MD's BSC view
then displays PBT alongside Deposit Growth, etc.

The full PBTComponents breakdown is also available for executive drill-down
("why is PBT what it is?" — see the components).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"


@dataclass
class PBTComponents:
    """Full P&L breakdown for executive drill-down. All values in KES (not KES B)."""
    # Income side
    interest_income: Decimal = Decimal("0")
    fee_income: Decimal = Decimal("0")
    non_interest_other: Decimal = Decimal("0")  # FX, investment etc.
    interest_expense: Decimal = Decimal("0")    # Cost of funds
    # Derived
    nii: Decimal = Decimal("0")                  # Net Interest Income
    non_interest_income: Decimal = Decimal("0")
    operating_income: Decimal = Decimal("0")
    # Cost side
    staff_costs: Decimal = Decimal("0")
    it_costs: Decimal = Decimal("0")
    premises: Decimal = Decimal("0")
    other_opex: Decimal = Decimal("0")
    total_opex: Decimal = Decimal("0")
    # Impairment
    npl_stage_3: Decimal = Decimal("0")
    impairment_charge: Decimal = Decimal("0")
    # Bottom line
    pbt: Decimal = Decimal("0")
    # Assumptions snapshot
    cost_of_funds_pct: Decimal = Decimal("0")
    lgd_pct: Decimal = Decimal("0")
    non_interest_other_pct: Decimal = Decimal("0")
    # Source metadata
    opex_source: str = "unknown"  # "opex_data.json" | "cir_pct" | "default_cir"
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """For JSON serialization."""
        d = asdict(self)
        # Convert Decimals to floats for JSON
        for k, v in list(d.items()):
            if isinstance(v, Decimal):
                d[k] = float(v)
        return d


def _load_pbt_assumptions() -> Dict[str, Decimal]:
    """Load PBT computation assumptions from data/pbt_assumptions.json.

    Returns defaults if file missing. Configurable via admin/finance.
    """
    path = DATA_DIR / "pbt_assumptions.json"
    defaults = {
        "cost_of_funds_pct":      Decimal("3.0"),   # 3% of deposits paid as interest
        "lgd_pct":                Decimal("45.0"),  # 45% Loss Given Default (Basel)
        "non_interest_other_pct": Decimal("15.0"),  # 15% uplift on fees for FX/investment
    }
    if not path.exists():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "cost_of_funds_pct":      Decimal(str(data.get("cost_of_funds_pct", defaults["cost_of_funds_pct"]))),
            "lgd_pct":                Decimal(str(data.get("lgd_pct", defaults["lgd_pct"]))),
            "non_interest_other_pct": Decimal(str(data.get("non_interest_other_pct", defaults["non_interest_other_pct"]))),
        }
    except Exception:
        return defaults


def _load_opex_estimate() -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, str]:
    """Load OpEx breakdown from data/opex_data.json.

    Returns: (staff_costs, it_costs, premises, other_opex, total_opex, source).
    All in KES (raw, not billions).

    If file missing or malformed, returns zeros + source="missing".
    Callers can detect missing data and either omit PBT or use a CIR-based estimate.
    """
    path = DATA_DIR / "opex_data.json"
    if not path.exists():
        return (Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"),
                Decimal("0"), "missing")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        bank = data.get("bank", {})
        # Values are in KES Billions in the file — convert to raw KES
        BILLION = Decimal("1000000000")
        staff      = Decimal(str(bank.get("staff_costs_kes_b", 0))) * BILLION
        it         = Decimal(str(bank.get("it_costs_kes_b", 0))) * BILLION
        premises   = Decimal(str(bank.get("premises_kes_b", 0))) * BILLION
        other      = Decimal(str(bank.get("other_opex_kes_b", 0))) * BILLION
        total      = Decimal(str(bank.get("total_opex_kes_b", 0))) * BILLION
        # If total is given, trust it (may include rebates etc.); else sum components
        if total == 0:
            total = staff + it + premises + other
        return (staff, it, premises, other, total, "opex_data.json")
    except Exception:
        return (Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"),
                Decimal("0"), "malformed")


def compute_pbt_from_cbs(cbs_dir: Path) -> PBTComponents:
    """Compute PBT from CBS accounts.csv + opex_data.json + pbt_assumptions.json.

    Read once, compute the full P&L. Returns PBTComponents with all
    drill-down values so executives can see *why* PBT is what it is,
    not just the final number.

    PBT formula:
        Operating Income = (Interest Income - Interest Expense) + Non-Interest Income
        PBT             = Operating Income - OpEx - Impairment

    Where:
        Interest Expense   = total deposits × cost_of_funds_pct
        Non-Interest Income = fee income × (1 + non_interest_other_pct)
        Impairment         = NPL Stage 3 × lgd_pct
        OpEx               = from data/opex_data.json (configurable)

    All assumptions configurable in data/pbt_assumptions.json.
    """
    components = PBTComponents()

    # ── Load assumptions ─────────────────────────────────────────────
    assumptions = _load_pbt_assumptions()
    components.cost_of_funds_pct = assumptions["cost_of_funds_pct"]
    components.lgd_pct = assumptions["lgd_pct"]
    components.non_interest_other_pct = assumptions["non_interest_other_pct"]

    # ── Walk accounts.csv for income / loan / deposit totals ─────────
    acct_csv = None
    for name in ("accounts.csv", "cbs_accounts.csv"):
        p = cbs_dir / name
        if p.exists():
            acct_csv = p
            break

    total_deposits = Decimal("0")
    total_loans_outstanding = Decimal("0")
    npl_outstanding = Decimal("0")

    if acct_csv is not None:
        with open(str(acct_csv), encoding="utf-8") as f:
            for row in csv.DictReader(f):
                # Income
                try:
                    components.interest_income += Decimal(str(row.get("interest_income_ytd") or "0"))
                except Exception:
                    pass
                try:
                    components.fee_income += Decimal(str(row.get("fee_income_ytd") or "0"))
                except Exception:
                    pass

                cat = row.get("category", "")
                try:
                    bal = Decimal(str(row.get("current_balance") or "0"))
                except Exception:
                    bal = Decimal("0")
                try:
                    lo = Decimal(str(row.get("loan_outstanding") or "0"))
                except Exception:
                    lo = Decimal("0")

                # Deposits
                if cat in ("CASA", "Term Deposit"):
                    total_deposits += bal
                # Loans
                if cat == "Loan":
                    total_loans_outstanding += lo
                    if row.get("npl_status") == "NPL":
                        npl_outstanding += lo
    else:
        components.notes.append("accounts.csv not found in cbs_dir — PBT will be zero")

    # ── Income side ──────────────────────────────────────────────────
    components.interest_expense = (total_deposits * components.cost_of_funds_pct / 100).quantize(Decimal("1"))
    components.nii = components.interest_income - components.interest_expense
    components.non_interest_other = (
        components.fee_income * components.non_interest_other_pct / 100
    ).quantize(Decimal("1"))
    components.non_interest_income = components.fee_income + components.non_interest_other
    components.operating_income = components.nii + components.non_interest_income

    # ── Cost side ────────────────────────────────────────────────────
    staff, it, premises, other, total_opex, opex_source = _load_opex_estimate()
    components.staff_costs = staff
    components.it_costs = it
    components.premises = premises
    components.other_opex = other
    components.total_opex = total_opex
    components.opex_source = opex_source

    # ── Impairment ───────────────────────────────────────────────────
    components.npl_stage_3 = npl_outstanding
    components.impairment_charge = (npl_outstanding * components.lgd_pct / 100).quantize(Decimal("1"))

    # ── Bottom line ──────────────────────────────────────────────────
    components.pbt = components.operating_income - components.total_opex - components.impairment_charge

    if opex_source in ("missing", "malformed"):
        components.notes.append(
            f"OpEx source '{opex_source}' — PBT computation incomplete. "
            f"Configure data/opex_data.json via admin or finance."
        )

    return components


def format_pbt_summary(components: PBTComponents) -> str:
    """Human-readable P&L drill-down."""
    def fmt(v: Decimal) -> str:
        try:
            return f"KES {float(v):,.0f}"
        except Exception:
            return str(v)
    lines = []
    lines.append(f"PBT Computation — Bank P&L breakdown")
    lines.append(f"{'─' * 50}")
    lines.append(f"  Interest Income           {fmt(components.interest_income):>20}")
    lines.append(f"  Interest Expense (-)      {fmt(-components.interest_expense):>20}")
    lines.append(f"  ─ NII                     {fmt(components.nii):>20}")
    lines.append(f"  Fee Income                {fmt(components.fee_income):>20}")
    lines.append(f"  Non-Interest Other        {fmt(components.non_interest_other):>20}")
    lines.append(f"  ─ Non-Interest Income     {fmt(components.non_interest_income):>20}")
    lines.append(f"  ═ Operating Income        {fmt(components.operating_income):>20}")
    lines.append(f"")
    lines.append(f"  Staff Costs (-)           {fmt(-components.staff_costs):>20}")
    lines.append(f"  IT Costs (-)              {fmt(-components.it_costs):>20}")
    lines.append(f"  Premises (-)              {fmt(-components.premises):>20}")
    lines.append(f"  Other OpEx (-)            {fmt(-components.other_opex):>20}")
    lines.append(f"  ─ Total OpEx              {fmt(-components.total_opex):>20}")
    lines.append(f"")
    lines.append(f"  NPL Stage 3               {fmt(components.npl_stage_3):>20}")
    lines.append(f"  Impairment Charge (-)     {fmt(-components.impairment_charge):>20}")
    lines.append(f"")
    lines.append(f"  ═ PBT                     {fmt(components.pbt):>20}")
    lines.append(f"")
    lines.append(f"  OpEx source:  {components.opex_source}")
    lines.append(f"  Assumptions:  cost_of_funds={components.cost_of_funds_pct}%, "
                 f"lgd={components.lgd_pct}%, nfi_uplift={components.non_interest_other_pct}%")
    if components.notes:
        lines.append(f"  Notes:")
        for n in components.notes:
            lines.append(f"    - {n}")
    return "\n".join(lines)


def _load_segment_sbu_mapping() -> Dict[str, Any]:
    """v10.368 — load segment→SBU mapping from data/segment_sbu_mapping.json.

    Returns defaults if file missing. Per Rule N1, mapping is admin-editable.
    """
    defaults = {
        "segment_to_sbu": {
            "AFFLUENT":         "Retail Banking",
            "CORE_MIDDLE":      "Retail Banking",
            "MASS":             "Retail Banking",
            "MICRO":            "Retail Banking",
            "SMALL":            "Commercial Banking",
            "MEDIUM":           "Commercial Banking",
            "CORPORATE":        "Corporate Banking",
            "RETAIL":           "Retail Banking",
            "HNW":              "Retail Banking",
            "PRIVATE_BANKING":  "Retail Banking",
            "SME":              "Commercial Banking",
        },
        "operational_sbus": ["Treasury", "Digital/Agency"],
    }
    path = DATA_DIR / "segment_sbu_mapping.json"
    if not path.exists():
        return defaults
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "segment_to_sbu": data.get("segment_to_sbu", defaults["segment_to_sbu"]),
            "operational_sbus": data.get("operational_sbus", defaults["operational_sbus"]),
        }
    except Exception:
        return defaults


def _load_opex_by_sbu() -> Dict[str, Dict[str, Decimal]]:
    """v10.368 — load per-SBU OpEx from data/opex_data.json::by_sbu.

    Returns dict keyed by SBU name with {opex, income, pbt_config} values
    in raw KES. Empty dict if file missing.
    """
    path = DATA_DIR / "opex_data.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        BILLION = Decimal("1000000000")
        out: Dict[str, Dict[str, Decimal]] = {}
        for sbu, v in data.get("by_sbu", {}).items():
            out[sbu] = {
                "opex":        Decimal(str(v.get("opex_b", 0))) * BILLION,
                "income":      Decimal(str(v.get("income_b", 0))) * BILLION,
                "pbt_config":  Decimal(str(v.get("pbt_b", 0))) * BILLION,
            }
        return out
    except Exception:
        return {}


def _load_customer_segment_lookup(cbs_dir: Path) -> Dict[str, str]:
    """v10.368 — read cbs_dir/customers.csv → {cif: segment_code}.

    Returns empty dict if customers.csv doesn't exist (in which case
    every account falls into 'Unallocated').
    """
    p = cbs_dir / "customers.csv"
    if not p.exists():
        return {}
    out: Dict[str, str] = {}
    try:
        with open(str(p), encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cif = row.get("cif", "")
                seg = row.get("segment", "")
                if cif:
                    out[cif] = seg
        return out
    except Exception:
        return {}


def compute_pbt_by_sbu(
    cbs_dir: Path,
    customer_segment_lookup: Optional[Dict[str, str]] = None,
) -> Dict[str, PBTComponents]:
    """v10.368 — Per-SBU PBT computation. The first concrete unification step.

    Walks accounts.csv, attributes each account to its customer's SBU via
    the segment→SBU mapping. Computes per-SBU NII, NFI, OpEx, impairment, PBT.

    The reconciliation identity that holds:
        Σ(PBTComponents.pbt for sbu in returned dict) == compute_pbt_from_cbs(cbs_dir).pbt
        (within KES 100 tolerance — locked by G254)

    SBU buckets returned:
      • Customer-facing SBUs (Retail Banking, Commercial Banking, Corporate
        Banking) — get their income from customer-attributed accounts
      • Operational SBUs (Treasury, Digital/Agency) — get 0 customer-attributable
        income, just their config OpEx (PBT = -OpEx until production GL feeds
        treasury revenue)
      • "Unallocated" — catches accounts whose customer has no segment OR
        whose segment doesn't map to any SBU. Also absorbs the OpEx gap
        (bank.total_opex - Σ(by_sbu.opex)) so reconciliation holds.

    Args:
        cbs_dir: directory containing accounts.csv and customers.csv
        customer_segment_lookup: optional {cif: segment_code} override.
                                  If None, reads cbs_dir/customers.csv.

    Returns: dict keyed by SBU name → PBTComponents for that SBU.
    """
    assumptions = _load_pbt_assumptions()
    sbu_mapping = _load_segment_sbu_mapping()
    seg_to_sbu = sbu_mapping["segment_to_sbu"]
    operational_sbus = sbu_mapping["operational_sbus"]
    opex_by_sbu = _load_opex_by_sbu()

    # Get customer lookup
    if customer_segment_lookup is None:
        customer_segment_lookup = _load_customer_segment_lookup(cbs_dir)

    # Initialize per-SBU buckets. Pre-populate ALL known SBUs so result
    # always has consistent shape; later add "Unallocated" if needed.
    known_sbus: List[str] = list(opex_by_sbu.keys()) + ["Unallocated"]
    sbu_buckets: Dict[str, PBTComponents] = {}
    for sbu in known_sbus:
        sbu_buckets[sbu] = PBTComponents(
            cost_of_funds_pct=assumptions["cost_of_funds_pct"],
            lgd_pct=assumptions["lgd_pct"],
            non_interest_other_pct=assumptions["non_interest_other_pct"],
        )

    # Per-SBU income/deposit accumulation from accounts.csv
    # We track total deposits per SBU to compute per-SBU interest expense
    deposits_by_sbu: Dict[str, Decimal] = {s: Decimal("0") for s in known_sbus}

    acct_csv = cbs_dir / "accounts.csv"
    if not acct_csv.exists():
        # No CBS — empty result with notes
        for s, b in sbu_buckets.items():
            b.notes.append("accounts.csv not found")
        return sbu_buckets

    with open(str(acct_csv), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cif = row.get("cif", "")
            segment = customer_segment_lookup.get(cif, "")
            sbu = seg_to_sbu.get(segment, "Unallocated")
            if sbu not in sbu_buckets:
                # New SBU discovered — add bucket
                sbu_buckets[sbu] = PBTComponents(
                    cost_of_funds_pct=assumptions["cost_of_funds_pct"],
                    lgd_pct=assumptions["lgd_pct"],
                    non_interest_other_pct=assumptions["non_interest_other_pct"],
                )
                deposits_by_sbu[sbu] = Decimal("0")
                known_sbus.append(sbu)

            bucket = sbu_buckets[sbu]
            # Income
            try:
                bucket.interest_income += Decimal(str(row.get("interest_income_ytd") or "0"))
            except Exception:
                pass
            try:
                bucket.fee_income += Decimal(str(row.get("fee_income_ytd") or "0"))
            except Exception:
                pass
            # Deposits (CASA + Term Deposit) → drive per-SBU interest expense
            try:
                bal = Decimal(str(row.get("current_balance") or "0"))
            except Exception:
                bal = Decimal("0")
            cat = row.get("category", "")
            if cat in ("CASA", "Term Deposit"):
                deposits_by_sbu[sbu] = deposits_by_sbu.get(sbu, Decimal("0")) + bal
            # Loans & NPL
            try:
                lo = Decimal(str(row.get("loan_outstanding") or "0"))
            except Exception:
                lo = Decimal("0")
            if cat == "Loan" and row.get("npl_status") == "NPL":
                bucket.npl_stage_3 += lo

    # Compute per-SBU derived figures
    bank_total_opex = Decimal("0")
    if (DATA_DIR / "opex_data.json").exists():
        try:
            bank_total_opex = Decimal(str(
                json.loads((DATA_DIR / "opex_data.json").read_text())
                .get("bank", {}).get("total_opex_kes_b", 0)
            )) * Decimal("1000000000")
        except Exception:
            pass

    # OpEx allocation: each customer-facing/operational SBU gets its config opex
    # Unallocated bucket absorbs (bank_total - Σ assigned)
    assigned_opex = Decimal("0")
    for sbu in list(sbu_buckets.keys()):
        bucket = sbu_buckets[sbu]
        if sbu in opex_by_sbu:
            bucket.total_opex = opex_by_sbu[sbu]["opex"]
            # Pro-rata staff/IT/premises split would need finer config;
            # for now leave as 0 (they're rolled up into total_opex)
            bucket.staff_costs = Decimal("0")
            bucket.it_costs = Decimal("0")
            bucket.premises = Decimal("0")
            bucket.other_opex = bucket.total_opex
            bucket.opex_source = "opex_data.json::by_sbu"
            assigned_opex += bucket.total_opex
        else:
            # Unallocated or unknown — opex set later
            pass

    # Unallocated bucket absorbs the OpEx gap (~0.7B)
    if "Unallocated" in sbu_buckets:
        unalloc = sbu_buckets["Unallocated"]
        gap = bank_total_opex - assigned_opex
        unalloc.total_opex = gap if gap > 0 else Decimal("0")
        unalloc.other_opex = unalloc.total_opex
        unalloc.opex_source = "bank_total - Σ(by_sbu)"
        unalloc.notes.append(
            f"Absorbs OpEx gap: bank.total_opex {float(bank_total_opex):,.0f} "
            f"- Σ(by_sbu) {float(assigned_opex):,.0f} = {float(gap):,.0f}"
        )

    # Compute derived figures (NII, OI, impairment, PBT) per SBU
    for sbu, bucket in sbu_buckets.items():
        deposits_in_sbu = deposits_by_sbu.get(sbu, Decimal("0"))
        bucket.interest_expense = (
            deposits_in_sbu * bucket.cost_of_funds_pct / 100
        ).quantize(Decimal("1"))
        bucket.nii = bucket.interest_income - bucket.interest_expense
        bucket.non_interest_other = (
            bucket.fee_income * bucket.non_interest_other_pct / 100
        ).quantize(Decimal("1"))
        bucket.non_interest_income = bucket.fee_income + bucket.non_interest_other
        bucket.operating_income = bucket.nii + bucket.non_interest_income
        bucket.impairment_charge = (
            bucket.npl_stage_3 * bucket.lgd_pct / 100
        ).quantize(Decimal("1"))
        bucket.pbt = bucket.operating_income - bucket.total_opex - bucket.impairment_charge

    # Tag operational SBUs in notes
    for sbu in operational_sbus:
        if sbu in sbu_buckets:
            sbu_buckets[sbu].notes.append(
                "Operational SBU — no customer-attributable income in CBS "
                "(treasury revenue, channel ops). PBT = -OpEx until "
                "production treasury GL feed is wired."
            )

    return sbu_buckets


def sum_sbu_pbts(sbu_pbts: Dict[str, PBTComponents]) -> PBTComponents:
    """v10.368 — sum all SBU PBTComponents into a bank-total view.

    Used by G254 to verify the reconciliation identity: this sum should
    equal compute_pbt_from_cbs(cbs_dir).pbt within tolerance.
    """
    total = PBTComponents()
    for bucket in sbu_pbts.values():
        total.interest_income += bucket.interest_income
        total.interest_expense += bucket.interest_expense
        total.fee_income += bucket.fee_income
        total.non_interest_other += bucket.non_interest_other
        total.staff_costs += bucket.staff_costs
        total.it_costs += bucket.it_costs
        total.premises += bucket.premises
        total.other_opex += bucket.other_opex
        total.total_opex += bucket.total_opex
        total.npl_stage_3 += bucket.npl_stage_3
        total.impairment_charge += bucket.impairment_charge
    total.nii = total.interest_income - total.interest_expense
    total.non_interest_income = total.fee_income + total.non_interest_other
    total.operating_income = total.nii + total.non_interest_income
    total.pbt = total.operating_income - total.total_opex - total.impairment_charge
    total.opex_source = "Σ(SBU OpEx)"
    if sbu_pbts:
        # Carry assumption snapshot from any non-empty bucket
        any_bucket = next(iter(sbu_pbts.values()))
        total.cost_of_funds_pct = any_bucket.cost_of_funds_pct
        total.lgd_pct = any_bucket.lgd_pct
        total.non_interest_other_pct = any_bucket.non_interest_other_pct
    return total


def format_sbu_breakdown(sbu_pbts: Dict[str, PBTComponents]) -> str:
    """Human-readable per-SBU P&L summary."""
    def fmt(v: Decimal) -> str:
        try: return f"KES {float(v):>18,.0f}"
        except Exception: return str(v)
    lines = []
    lines.append("Per-SBU PBT Breakdown")
    lines.append("=" * 88)
    lines.append(f"{'SBU':<22} {'OpIncome':>22} {'OpEx':>22} {'PBT':>22}")
    lines.append("-" * 88)
    for sbu, b in sbu_pbts.items():
        lines.append(f"{sbu:<22} {fmt(b.operating_income)} {fmt(-b.total_opex)} {fmt(b.pbt)}")
    lines.append("-" * 88)
    total = sum_sbu_pbts(sbu_pbts)
    lines.append(f"{'Σ Bank Total':<22} {fmt(total.operating_income)} {fmt(-total.total_opex)} {fmt(total.pbt)}")
    return "\n".join(lines)


def self_test() -> None:
    """v10.364 self_test — PBT computation against a hand-rolled CSV fixture.

    Deliberately does NOT import from utils.virtual_bank_seed or
    utils.virtual_bank_cbs_writer — those would create a circular
    dependency back through utils.actuals_engine (which imports this
    module). Integration-style testing happens in
    tests/integration/test_v10364_pbt_computation.py instead, which
    can safely import the seeder + bridge because it's outside the
    utils/ package.

    The fixture below mirrors the minimal CSV shape that
    compute_pbt_from_cbs walks: category, current_balance,
    loan_outstanding, interest_income_ytd, fee_income_ytd, npl_status.
    """
    import tempfile
    tests_run = 0

    # Test 1: PBTComponents dataclass
    c = PBTComponents()
    assert c.pbt == Decimal("0")
    assert c.opex_source == "unknown"
    tests_run += 1

    # Test 2: _load_pbt_assumptions returns the right shape
    a = _load_pbt_assumptions()
    assert "cost_of_funds_pct" in a
    assert "lgd_pct" in a
    assert a["cost_of_funds_pct"] > 0
    tests_run += 1

    # Test 3: _load_opex_estimate returns the expected tuple shape
    staff, it, premises, other, total, source = _load_opex_estimate()
    if source == "opex_data.json":
        assert total > 0, "opex_data.json present but total is 0"
    tests_run += 1

    # Test 4: compute_pbt_from_cbs runs on an empty cbs_dir (no CSV)
    with tempfile.TemporaryDirectory() as td:
        c = compute_pbt_from_cbs(Path(td))
    assert isinstance(c, PBTComponents)
    assert c.interest_income == Decimal("0")
    assert c.fee_income == Decimal("0")
    # Should note the missing CSV
    assert any("accounts.csv not found" in n for n in c.notes)
    tests_run += 1

    # Test 5: compute_pbt_from_cbs against a hand-rolled minimal CSV
    csv_header = (
        "category,current_balance,loan_outstanding,"
        "interest_income_ytd,fee_income_ytd,npl_status\n"
    )
    csv_rows = [
        # Three CASA deposits totalling 1B
        "CASA,500000000,0,0,1000000,\n",
        "CASA,300000000,0,0,500000,\n",
        "CASA,200000000,0,0,300000,\n",
        # One term deposit
        "Term Deposit,100000000,0,0,0,\n",
        # Two loans, one NPL
        "Loan,0,80000000,5000000,0,\n",
        "Loan,0,20000000,1000000,0,NPL\n",
    ]
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "accounts.csv"
        csv_path.write_text(csv_header + "".join(csv_rows))
        c = compute_pbt_from_cbs(Path(td))

    # Income side
    assert c.interest_income == Decimal("6000000")  # 5M + 1M
    assert c.fee_income == Decimal("1800000")       # 1M + 0.5M + 0.3M
    # Deposits = 500M + 300M + 200M + 100M (term) = 1.1B
    expected_deposits = Decimal("1100000000")
    expected_interest_expense = (
        expected_deposits * c.cost_of_funds_pct / 100
    ).quantize(Decimal("1"))
    assert c.interest_expense == expected_interest_expense
    # NII = 6M - interest_expense
    assert c.nii == c.interest_income - c.interest_expense
    # Impairment = NPL (20M) × LGD
    expected_impairment = (
        Decimal("20000000") * c.lgd_pct / 100
    ).quantize(Decimal("1"))
    assert c.impairment_charge == expected_impairment
    tests_run += 1

    # Test 6: PBT identity
    expected_pbt = c.operating_income - c.total_opex - c.impairment_charge
    assert c.pbt == expected_pbt, (
        f"PBT identity broken: {c.pbt} != {expected_pbt}"
    )
    tests_run += 1

    # Test 7: format_pbt_summary produces readable output
    s = format_pbt_summary(c)
    assert "PBT Computation" in s
    assert "Operating Income" in s
    assert "Total OpEx" in s
    tests_run += 1

    # Test 8: to_dict serializes (no Decimals leak)
    d = c.to_dict()
    import json as _json
    _ = _json.dumps(d)  # must not raise
    assert isinstance(d["pbt"], float)
    tests_run += 1

    print(f"✓ pbt_computation self-test passed ({tests_run} tests)")


if __name__ == "__main__":
    self_test()
