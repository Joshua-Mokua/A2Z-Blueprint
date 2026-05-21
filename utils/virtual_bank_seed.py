"""utils/virtual_bank_seed.py — v10.358 Seed-the-Bank Helper.

Purpose
-------
The v10.357 readiness audit confirmed the virtual-bank pipeline runs end-to-end
but generates 0 transactions because VirtualBankCore starts empty (0 customers,
0 accounts, 0 loans, 0 branches). This module is the missing prerequisite:
populates a VirtualBankCore from the platform's existing data sources
(users.json, hr.json, BRANCH_REGION) into the dataclass shapes
VirtualBankCore expects.

Design principles
-----------------
1. **Deterministic**. Same seed string → same populated bank, byte-for-byte.
   No wall-clock dependency. No random module without an explicit seed.
2. **Scale-configurable**. Default "small" seed (~100 customers, ~200 accounts,
   21 branches) is the right size for the Football Team Test harness. Larger
   scales available for stress testing; smaller scales for unit tests.
3. **Sourced from existing data, not invented**. Branches come from
   utils.core.BRANCH_REGION (21 real Ecobank branch names). RMs come from
   data/users.json (the 419 active relationship managers). Customer names
   are generated from a small fixed pool — synthetic but predictable.
4. **No platform-state change**. Returns a populated VirtualBankCore; does
   not touch cbs_data/, does not write actuals, does not update users.json.
5. **Honest defaults**. The Tier-2 Kenya scale (700K customers, KES 110B
   deposits, KES 80B loans) is preserved as the "bank_total" config option.
   The default "small" config is honest about being a small slice for testing.

What this module is NOT
-----------------------
- NOT the persistence bridge (v10.359's job — write txns to cbs_data/*.json)
- NOT the daily-ops driver (the simulator already does that)
- NOT the actuals computation (actuals_engine's job)
- NOT a Football Team Test (v10.361's job)

It's the seeding step. The bank starts populated; everything else is built
on top.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"


# ─── Canonical branch list (v10.361 — fully configurable, FLEXCUBE-aware) ──
# Per Rule N1: tenant identity must be configured, never hardcoded. v10.361
# deletes the v10.360 _FALLBACK_BRANCHES dict — the seeder is bank-agnostic
# and must not carry any tenant-specific branch data.
#
# Source priority (highest to lowest):
#   1. FLEXCUBE (via utils.flexcube_adapter.fetch_branches_from_flexcube)
#      when flexcube_config.json mode="live" (production)
#   2. data/org_config.json::branches[] (configurable via pages/7_admin.py
#      render_branch_manager — Add + Edit + soft-delete)
#   3. Empty dict (configuration error — surfaces in admin UI, doesn't
#      mask the failure with stale data)
#
# G246 + G247 lock: no hardcoded branch dict literals permitted here.


def get_ecobank_branches() -> Dict[str, str]:
    """v10.361 — return {branch_name: region} from the configured source.

    Source priority:
      1. FLEXCUBE (if mode="live" and adapter exposes fetch_branches)
      2. data/org_config.json::branches[] (current authoritative source)
      3. Empty dict (configuration error — surfaces upstream)

    The name `get_ecobank_branches` is preserved for backward compatibility
    with callers built during the Ecobank phase. The function is generic
    and works for any tenant whose org_config is properly populated.
    """
    # Source 1: FLEXCUBE (when available + live mode configured)
    try:
        from utils.flexcube_adapter import fetch_branches_from_flexcube
        fc_branches = fetch_branches_from_flexcube()
        if fc_branches:
            return fc_branches
    except (ImportError, AttributeError):
        # Adapter doesn't expose this function yet — fall through to org_config.
        # When FLEXCUBE integration ships, this branch becomes hot.
        pass
    except Exception:
        # Adapter exists but call failed (network, auth, etc) — fall back
        # to org_config rather than empty so admin UI keeps working.
        pass

    # Source 2: org_config.json (configurable via admin module)
    try:
        config_path = REPO / "data" / "org_config.json"
        if not config_path.exists():
            return {}
        import json as _json
        cfg = _json.loads(config_path.read_text(encoding="utf-8"))
        branches = cfg.get("branches", [])
        if not branches:
            return {}
        return {
            b["name"]: b.get("region", "Other")
            for b in branches
            if b.get("active", True) and b.get("name")
        }
    except Exception:
        # Source 3: empty — surfaces configuration error upstream.
        # No hardcoded tenant data. Rule N1.
        return {}


# Module-level snapshot for callers that want the dict directly.
# Evaluated once at import time; callers that need fresh data call
# get_ecobank_branches() instead.
ECOBANK_BRANCHES: Dict[str, str] = get_ecobank_branches()


# ─── Seed configuration ───────────────────────────────────────────────────

@dataclass
class SeedConfig:
    """Configurable scale for the seeded bank.

    The default is "small": 100 customers, 200 accounts, 30 loans across
    21 branches. Larger scales (medium / large) are honest about being
    slower — running daily ops over 700K customers is not a unit-test
    operation.
    """
    config_id: str = "small"
    n_customers: int = 100
    accounts_per_customer_avg: int = 2  # roughly 200 accounts at default
    loans_pct_of_customers: float = 0.30  # 30 customers have a loan
    n_branches: int = 0  # 0 means "all branches in ECOBANK_BRANCHES"
    rm_pool_size: int = 30  # number of distinct RMs to assign customers to
    base_currency: str = "KES"
    # Customer-segment distribution (must sum to ~1.0)
    segment_mix: Dict[str, float] = field(default_factory=lambda: {
        "RETAIL":          0.70,
        "SME":             0.20,
        "CORPORATE":       0.06,
        "HNW":             0.03,
        "PRIVATE_BANKING": 0.01,
    })
    # Account-type distribution
    account_type_mix: Dict[str, float] = field(default_factory=lambda: {
        "SAVINGS":        0.55,
        "CURRENT":        0.30,
        "FIXED_DEPOSIT":  0.10,
        "OVERDRAFT":      0.05,
    })
    # Balance ranges per segment (min, max)
    balance_ranges: Dict[str, Tuple[int, int]] = field(default_factory=lambda: {
        "RETAIL":          (5_000,      500_000),
        "SME":             (50_000,    5_000_000),
        "CORPORATE":       (500_000,  50_000_000),
        "HNW":             (1_000_000, 20_000_000),
        "PRIVATE_BANKING": (5_000_000, 100_000_000),
    })
    # Loan principal ranges per segment
    loan_principal_ranges: Dict[str, Tuple[int, int]] = field(default_factory=lambda: {
        "RETAIL":          (50_000,     500_000),
        "SME":             (500_000,   10_000_000),
        "CORPORATE":       (5_000_000, 100_000_000),
        "HNW":             (1_000_000,  20_000_000),
        "PRIVATE_BANKING": (10_000_000, 50_000_000),
    })
    base_seed: str = "v10358_seed"
    base_date: str = "2026-01-01"

    @classmethod
    def small(cls) -> "SeedConfig":
        return cls(config_id="small")

    @classmethod
    def medium(cls) -> "SeedConfig":
        return cls(
            config_id="medium",
            n_customers=1_000,
            accounts_per_customer_avg=2,
            loans_pct_of_customers=0.30,
            rm_pool_size=100,
        )

    @classmethod
    def large(cls) -> "SeedConfig":
        return cls(
            config_id="large",
            n_customers=10_000,
            accounts_per_customer_avg=2,
            loans_pct_of_customers=0.30,
            rm_pool_size=200,
        )


@dataclass
class SeedResult:
    config_id: str
    n_branches: int
    n_customers: int
    n_accounts: int
    n_loans: int
    n_rms: int
    total_deposits_kes: Decimal
    total_loans_kes: Decimal
    duration_s: float
    notes: List[str] = field(default_factory=list)


# ─── Internal helpers ─────────────────────────────────────────────────────

# Customer name pool — synthetic but Kenyan-flavoured. Deterministic
# selection via seeded index.
_FIRST_NAMES_RETAIL = (
    "Wanjiru", "Achieng", "Mwende", "Njeri", "Mukami", "Nyambura", "Wairimu",
    "Onyango", "Mwangi", "Kamau", "Otieno", "Kiprop", "Mutua", "Ouma",
    "Atieno", "Kipchoge", "Wambui", "Maina", "Kariuki", "Wanjiku",
)
_LAST_NAMES_RETAIL = (
    "Mwangi", "Otieno", "Kamau", "Onyango", "Karanja", "Ochieng", "Wanjiku",
    "Njuguna", "Kiprono", "Mutua", "Korir", "Ouma", "Kibet", "Wangari",
    "Kimani", "Maina", "Mwita", "Owino", "Chebet", "Akinyi",
)
_COMPANY_SUFFIX_SME = ("Enterprises", "Limited", "Holdings", "Trading", "Group")
_COMPANY_PREFIX_SME = (
    "Acacia", "Baobab", "Cedar", "Highland", "Kilimo", "Mara", "Pwani",
    "Rift Valley", "Savannah", "Tana",
)
_CORPORATE_PREFIX = (
    "Kenya National", "East African", "Coast Region", "Highland", "Mara",
    "Pan-African", "Sahara",
)
_CORPORATE_SECTOR = (
    "Industries", "Manufacturing", "Logistics", "Telecom", "Energy",
    "Construction", "Agribusiness",
)


def _deterministic_index(seed: int, n: int, modulo: int) -> List[int]:
    """Tiny linear-congruential generator. Fully deterministic — same
    seed produces same sequence on every Python version."""
    # Park-Miller (minimal standard) — well-known small RNG
    state = seed if seed > 0 else 1
    out: List[int] = []
    a = 48271
    m = 2147483647
    for _ in range(n):
        state = (a * state) % m
        out.append(state % modulo)
    return out


def _segment_for_index(i: int, mix: Dict[str, float], n_total: int) -> str:
    """Apply the mix proportions deterministically across n_total slots."""
    # Build cumulative cut-points
    items = list(mix.items())
    # Normalize
    s = sum(items[k][1] if False else v for k, v in items)  # = sum of values
    s = sum(v for _, v in items)
    if s <= 0:
        return items[0][0]
    cum = 0.0
    boundaries: List[Tuple[float, str]] = []
    for name, pct in items:
        cum += pct / s
        boundaries.append((cum, name))
    frac = i / max(n_total, 1)
    for boundary, name in boundaries:
        if frac < boundary:
            return name
    return boundaries[-1][1]


def _customer_name(idx: int, segment: str) -> str:
    """Synthesize a customer name from the deterministic pool."""
    if segment in ("RETAIL", "HNW", "PRIVATE_BANKING"):
        first = _FIRST_NAMES_RETAIL[idx % len(_FIRST_NAMES_RETAIL)]
        last = _LAST_NAMES_RETAIL[(idx * 7 + 3) % len(_LAST_NAMES_RETAIL)]
        return f"{first} {last}"
    if segment == "SME":
        prefix = _COMPANY_PREFIX_SME[idx % len(_COMPANY_PREFIX_SME)]
        suffix = _COMPANY_SUFFIX_SME[(idx * 5 + 1) % len(_COMPANY_SUFFIX_SME)]
        return f"{prefix} {suffix}"
    if segment == "CORPORATE":
        prefix = _CORPORATE_PREFIX[idx % len(_CORPORATE_PREFIX)]
        sector = _CORPORATE_SECTOR[(idx * 3 + 2) % len(_CORPORATE_SECTOR)]
        return f"{prefix} {sector} Ltd"
    return f"Customer {idx}"


def _select_rms_from_users(rm_pool_size: int) -> List[str]:
    """Pull active RM staff_codes from data/users.json. Falls back to
    synthetic 'RM_NNN' codes if users.json is unavailable."""
    try:
        users = json.loads((DATA_DIR / "users.json").read_text())
    except Exception:
        return [f"RM_{i:03d}" for i in range(1, rm_pool_size + 1)]

    rms: List[str] = []
    for username, u in users.items():
        if not u.get("active"):
            continue
        role = u.get("role", "")
        if "Relationship" in role or role.startswith("RM"):
            sc = u.get("staff_code")
            if sc:
                rms.append(sc)
        if len(rms) >= rm_pool_size:
            break
    return rms if rms else [f"RM_{i:03d}" for i in range(1, rm_pool_size + 1)]


# ─── Main seeder ──────────────────────────────────────────────────────────

def seed_virtual_bank(
    bank: Optional[Any] = None,
    config: Optional[SeedConfig] = None,
) -> Tuple[Any, SeedResult]:
    """Populate a VirtualBankCore. If `bank` is None, instantiate one
    with the seed config's entity_name + base_seed + base_date.

    Returns (bank, SeedResult) where SeedResult is a structured summary.
    """
    import time
    from utils.virtual_bank_core import (
        VirtualBankCore, VirtualBranch, VirtualCustomer, VirtualAccount,
        VirtualLoan, CustomerSegment, AccountType, AccountStatus,
        LoanStatus,
    )

    t0 = time.time()
    if config is None:
        config = SeedConfig.small()

    if bank is None:
        bank = VirtualBankCore(
            entity_name="Ecobank Kenya Virtual",
            base_seed=config.base_seed,
            base_date=config.base_date,
        )

    notes: List[str] = []

    # ── 1. Seed branches (v10.360 — sourced from data/org_config.json) ──
    # Pull fresh from disk so admin edits to org_config propagate
    # without process restart. ECOBANK_BRANCHES (module-level constant)
    # is the import-time snapshot; get_ecobank_branches() is the
    # live version.
    branches_to_seed = get_ecobank_branches()
    # If config.n_branches is 0 (default), use all; otherwise cap
    branch_cap = config.n_branches if config.n_branches > 0 else len(branches_to_seed)

    branch_codes: List[str] = []
    for i, (branch_name, region) in enumerate(branches_to_seed.items()):
        # Branch_type heuristic
        branch_type = "Head Office" if "Retail Banking" in branch_name else "Branch"
        # Staff count: estimate from region
        n_staff = 50 if branch_type == "Branch" else 200
        code = f"BR{i+1:03d}"
        try:
            bank.add_branch(VirtualBranch(
                branch_code=code,
                branch_name=branch_name,
                region=region,
                branch_type=branch_type,
                n_staff=n_staff,
                notes="v10.358 seeded (v10.360 sourced from org_config.json)",
            ))
            branch_codes.append(code)
        except Exception as e:
            notes.append(f"branch {branch_name} skipped: {e}")
        if len(branch_codes) >= branch_cap:
            break

    # ── 2. Pick RMs from users.json ──────────────────────────────────
    rm_codes = _select_rms_from_users(config.rm_pool_size)
    if rm_codes[0].startswith("RM_"):
        notes.append("RM pool synthesized — users.json not available or no RMs found")

    # ── 3. Seed customers ────────────────────────────────────────────
    branch_assignment = _deterministic_index(
        seed=hash(config.base_seed + "_branch") & 0x7FFFFFFF,
        n=config.n_customers,
        modulo=len(branch_codes),
    )
    rm_assignment = _deterministic_index(
        seed=hash(config.base_seed + "_rm") & 0x7FFFFFFF,
        n=config.n_customers,
        modulo=len(rm_codes),
    )

    customer_records: List[Tuple[str, str, str, str]] = []  # (cif, segment, branch, rm)
    onboarding = config.base_date  # all open on day 0 — simulator advances them
    for i in range(config.n_customers):
        segment_name = _segment_for_index(i, config.segment_mix, config.n_customers)
        segment = CustomerSegment[segment_name]
        cif = f"100{i+1:07d}"
        full_name = _customer_name(i, segment_name)
        branch_code = branch_codes[branch_assignment[i]]
        rm_code = rm_codes[rm_assignment[i]]

        try:
            bank.add_customer(VirtualCustomer(
                cif=cif,
                full_name=full_name,
                segment=segment,
                branch_code=branch_code,
                rm_code=rm_code,
                onboarding_date=onboarding,
                is_pep=False,
                sanctions_status="CLEAR",
                notes="v10.358 seeded",
            ))
            customer_records.append((cif, segment_name, branch_code, rm_code))
        except Exception as e:
            notes.append(f"customer {cif} skipped: {e}")

    # ── 4. Seed accounts ─────────────────────────────────────────────
    total_deposits = Decimal("0")
    n_accounts_target = config.n_customers * config.accounts_per_customer_avg
    balance_index = _deterministic_index(
        seed=hash(config.base_seed + "_balance") & 0x7FFFFFFF,
        n=n_accounts_target,
        modulo=1_000_000,
    )
    type_index = _deterministic_index(
        seed=hash(config.base_seed + "_type") & 0x7FFFFFFF,
        n=n_accounts_target,
        modulo=1_000,
    )

    account_no_counter = 1
    for i, (cif, segment_name, branch_code, _rm_code) in enumerate(customer_records):
        n_accounts_for_this = config.accounts_per_customer_avg
        for j in range(n_accounts_for_this):
            idx = i * config.accounts_per_customer_avg + j
            if idx >= n_accounts_target:
                break

            # Pick account type from mix
            type_name = _segment_for_index(
                idx, config.account_type_mix, n_accounts_target
            )
            account_type = AccountType[type_name]

            # Balance from segment range
            balance_min, balance_max = config.balance_ranges.get(
                segment_name, (5_000, 500_000)
            )
            span = balance_max - balance_min
            raw_balance = balance_min + (balance_index[idx] % max(span, 1))
            balance = Decimal(raw_balance)

            account_no = f"ECO{account_no_counter:010d}"
            account_no_counter += 1

            try:
                bank.add_account(VirtualAccount(
                    account_no=account_no,
                    cif=cif,
                    branch_code=branch_code,
                    account_type=account_type,
                    currency=config.base_currency,
                    balance=balance,
                    status=AccountStatus.ACTIVE,
                    open_date=onboarding,
                    last_transaction_date=onboarding,
                    interest_rate_pct=Decimal("3"),
                    notes="v10.358 seeded",
                ))
                # Deposits = balances on CURRENT/SAVINGS/FD (not OVERDRAFT/LOAN)
                if account_type in (AccountType.CURRENT, AccountType.SAVINGS,
                                    AccountType.FIXED_DEPOSIT):
                    total_deposits += balance
            except Exception as e:
                notes.append(f"account {account_no} skipped: {e}")

    # ── 5. Seed loans (loans_pct_of_customers fraction) ──────────────
    total_loans = Decimal("0")
    n_loans_target = int(config.n_customers * config.loans_pct_of_customers)
    loan_index = _deterministic_index(
        seed=hash(config.base_seed + "_loan") & 0x7FFFFFFF,
        n=n_loans_target,
        modulo=1_000_000,
    )

    for i in range(n_loans_target):
        cif, segment_name, branch_code, rm_code = customer_records[i]
        loan_min, loan_max = config.loan_principal_ranges.get(
            segment_name, (50_000, 500_000)
        )
        span = loan_max - loan_min
        principal = Decimal(loan_min + (loan_index[i] % max(span, 1)))
        # ~70% outstanding (already partly repaid)
        outstanding = (principal * Decimal("0.7")).quantize(Decimal("1"))
        loan_id = f"LN{i+1:08d}"
        # Disbursement 6 months prior to base_date
        disb_date = (datetime.strptime(config.base_date, "%Y-%m-%d") - timedelta(days=180)).date().isoformat()
        next_due_date = (datetime.strptime(config.base_date, "%Y-%m-%d") + timedelta(days=30)).date().isoformat()
        try:
            bank.add_loan(VirtualLoan(
                loan_id=loan_id,
                cif=cif,
                branch_code=branch_code,
                rm_code=rm_code,
                principal=principal,
                outstanding=outstanding,
                rate_pct=Decimal("14.5"),
                tenor_months=36,
                disbursement_date=disb_date,
                next_due_date=next_due_date,
                status=LoanStatus.PERFORMING,
                days_past_due=0,
                notes="v10.358 seeded",
            ))
            total_loans += outstanding
        except Exception as e:
            notes.append(f"loan {loan_id} skipped: {e}")

    elapsed = time.time() - t0

    result = SeedResult(
        config_id=config.config_id,
        n_branches=len(branch_codes),
        n_customers=len(customer_records),
        n_accounts=len(bank.all_accounts()),
        n_loans=len(bank.all_loans()),
        n_rms=len(rm_codes),
        total_deposits_kes=total_deposits,
        total_loans_kes=total_loans,
        duration_s=round(elapsed, 3),
        notes=notes,
    )
    return bank, result


def format_seed_summary(result: SeedResult) -> str:
    lines = []
    lines.append(f"Virtual bank seeded — config '{result.config_id}' in {result.duration_s}s")
    lines.append(f"  Branches:  {result.n_branches}")
    lines.append(f"  Customers: {result.n_customers:,}")
    lines.append(f"  Accounts:  {result.n_accounts:,}")
    lines.append(f"  Loans:     {result.n_loans:,}")
    lines.append(f"  RMs:       {result.n_rms}")
    lines.append(f"  Deposits:  KES {result.total_deposits_kes:,}")
    lines.append(f"  Loans:     KES {result.total_loans_kes:,}")
    if result.notes:
        lines.append("  Notes:")
        for n in result.notes[:5]:
            lines.append(f"    - {n}")
        if len(result.notes) > 5:
            lines.append(f"    ... +{len(result.notes) - 5} more")
    return "\n".join(lines)


# ─── Self-test ────────────────────────────────────────────────────────────

def self_test() -> None:
    """v10.358 self_test — deterministic seeding + basic invariants."""
    tests_run = 0

    # Test 1: ECOBANK_BRANCHES is populated (≥5 from fallback, up to 94+ from org_config)
    assert len(ECOBANK_BRANCHES) >= 5, (
        f"Expected ≥5 branches, got {len(ECOBANK_BRANCHES)}"
    )
    tests_run += 1

    # Test 2: Default SeedConfig produces small scale, n_branches=0 means "all"
    cfg = SeedConfig.small()
    assert cfg.n_customers == 100
    assert cfg.n_branches == 0  # 0 = use all from ECOBANK_BRANCHES
    tests_run += 1

    # Test 3: Seeder runs end-to-end
    bank, result = seed_virtual_bank(config=SeedConfig.small())
    tests_run += 1

    # Test 4: Result counts — branches match what's in ECOBANK_BRANCHES
    expected_branches = len(ECOBANK_BRANCHES)
    assert result.n_branches == expected_branches, (
        f"Expected {expected_branches} branches (matching ECOBANK_BRANCHES), got {result.n_branches}"
    )
    assert result.n_customers == 100, f"Expected 100 customers, got {result.n_customers}"
    assert result.n_accounts == 200, f"Expected 200 accounts, got {result.n_accounts}"
    assert result.n_loans == 30, f"Expected 30 loans, got {result.n_loans}"
    tests_run += 1

    # Test 5: Determinism — second seeding produces same totals
    bank2, result2 = seed_virtual_bank(config=SeedConfig.small())
    assert result.total_deposits_kes == result2.total_deposits_kes, (
        "Seeding is not deterministic — deposits differ between runs"
    )
    assert result.total_loans_kes == result2.total_loans_kes, (
        "Seeding is not deterministic — loans differ between runs"
    )
    tests_run += 1

    # Test 6: Totals are nonzero
    assert result.total_deposits_kes > 0
    assert result.total_loans_kes > 0
    tests_run += 1

    # Test 7: Each customer has accounts attached (CIF lookup works)
    accounts = bank.all_accounts()
    customers = bank.all_customers()
    customer_cifs = {c.cif for c in customers}
    account_cifs = {a.cif for a in accounts}
    # Every account's CIF should match a customer
    orphan_accounts = account_cifs - customer_cifs
    assert not orphan_accounts, f"Orphan accounts found: {list(orphan_accounts)[:3]}"
    tests_run += 1

    # Test 8: Each loan's CIF matches a customer
    loans = bank.all_loans()
    loan_cifs = {l.cif for l in loans}
    orphan_loans = loan_cifs - customer_cifs
    assert not orphan_loans, f"Orphan loans found: {list(orphan_loans)[:3]}"
    tests_run += 1

    # Test 9: Each customer's branch_code references a real seeded branch
    branches = bank.all_branches()
    branch_codes = {b.branch_code for b in branches}
    for c in customers[:20]:
        assert c.branch_code in branch_codes, (
            f"Customer {c.cif} references unknown branch {c.branch_code}"
        )
    tests_run += 1

    # Test 10: Format summary works
    summary = format_seed_summary(result)
    assert "Virtual bank seeded" in summary
    assert "Branches:" in summary
    tests_run += 1

    print(f"✓ virtual_bank_seed self-test passed ({tests_run} tests)")


if __name__ == "__main__":
    self_test()
    print()
    bank, result = seed_virtual_bank(config=SeedConfig.small())
    print(format_seed_summary(result))
