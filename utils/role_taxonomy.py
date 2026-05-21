"""utils/role_taxonomy.py — v10.374 Role Taxonomy Engine.

Phase A first batch from the v10.373 system state review. Joshua's
directive: "I will be keen to ensure what we have done with profitability
unification happens across" + "constantly zoom out and review the system
as a whole" + "ensure the tree also aligns from the pipeline management".

This module establishes the **profitability axis** for every role —
orthogonal to the existing seniority axis (role_tiers in
org_hierarchy_config.json). Five profitability tiers:

  portfolio_owner    — tagged to customers via accounts.csv::
                       relationship_manager_code. Drives sales. Includes
                       Branch sales (RM PB/BB, DSO, BRM, SRO, RO) and
                       Head Office sales (HO Corporate/SME/Sector RMs
                       reporting to Chief Commercial / Chief Credit, etc.).
                       HO RMs' customers span multiple branches but fit
                       one SBU.

  proposition_owner  — owns an OVERLAPPING proposition (Women Banking,
                       Diaspora, Agribusiness). NOT tagged to accounts.
                       Per Rule 6, propositions overlap by design — a
                       customer can be in a portfolio AND a proposition.

  structural_owner   — owns PBT at structural level via rollup. NOT tagged
                       to customers directly. Branch Manager owns branch
                       PBT (via branch_pbt_allocator). Regional Head owns
                       region. Head of business line owns SBU. Directors
                       and MD own bank.

  service            — branch operational roles (Teller, CSO, BOS,
                       Digital Channels). Can occasionally be tagged when
                       introducing accounts, but not their primary sales
                       responsibility.

  support            — head office functions (Risk, Compliance, IT, HR,
                       Finance, Audit, Legal). Owns cost center / function,
                       not direct PBT.

Two complementary attributes per role:
  branch_scope: branch_bound | head_office | national
  sbu:          Retail Banking | Commercial Banking | Corporate Banking |
                Treasury | Digital_Agency | Support | Executive

Module API
----------
  get_profitability_tier(role)  → 'portfolio_owner' | ... | 'support'
  get_branch_scope(role)         → 'branch_bound' | 'head_office' | 'national'
  get_sbu(role)                  → SBU string or 'Support'
  can_be_tagged(role)            → bool (portfolio_owner or service)
  classify_role(role)            → full RoleClassification dataclass
  list_all_classified_roles()    → list of all roles known to the taxonomy
  validate_role_coverage()       → list of unclassified roles seen in users/hr

Module purity
-------------
Zero upward imports. Reads only data/org_hierarchy_config.json and
data/users.json + data/hr.json for the coverage audit.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"

# Profitability tier values
TIER_PORTFOLIO_OWNER = "portfolio_owner"
TIER_PROPOSITION_OWNER = "proposition_owner"
TIER_STRUCTURAL_OWNER = "structural_owner"
TIER_SERVICE = "service"
TIER_SUPPORT = "support"

ALL_TIERS = (
    TIER_PORTFOLIO_OWNER,
    TIER_PROPOSITION_OWNER,
    TIER_STRUCTURAL_OWNER,
    TIER_SERVICE,
    TIER_SUPPORT,
)

# Branch scope values
SCOPE_BRANCH_BOUND = "branch_bound"
SCOPE_HEAD_OFFICE = "head_office"
SCOPE_NATIONAL = "national"
ALL_SCOPES = (SCOPE_BRANCH_BOUND, SCOPE_HEAD_OFFICE, SCOPE_NATIONAL)

# SBU values (must align with segment_sbu_mapping.json)
SBU_RETAIL = "Retail Banking"
SBU_COMMERCIAL = "Commercial Banking"
SBU_CORPORATE = "Corporate Banking"
SBU_TREASURY = "Treasury"
SBU_DIGITAL = "Digital_Agency"
SBU_SUPPORT = "Support"
SBU_EXECUTIVE = "Executive"
ALL_SBUS = (SBU_RETAIL, SBU_COMMERCIAL, SBU_CORPORATE, SBU_TREASURY,
            SBU_DIGITAL, SBU_SUPPORT, SBU_EXECUTIVE)

# Tiers eligible to be tagged in accounts.csv::relationship_manager_code
_TAGGABLE_TIERS = frozenset({TIER_PORTFOLIO_OWNER, TIER_SERVICE})


@dataclass(frozen=True)
class RoleClassification:
    """Full taxonomy classification of a single role."""
    role: str
    tier: str               # one of ALL_TIERS
    branch_scope: str       # one of ALL_SCOPES
    sbu: str                # one of ALL_SBUs
    matched_via: str        # 'explicit' or 'keyword_fallback:<keyword>'


def _load_org_hierarchy_config() -> Dict[str, Any]:
    """Load org_hierarchy_config.json; returns {} on failure."""
    p = DATA_DIR / "org_hierarchy_config.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_axis() -> Dict[str, Any]:
    """Convenience accessor for the profitability_axis subtree."""
    return _load_org_hierarchy_config().get("profitability_axis", {})


def classify_role(role: str) -> RoleClassification:
    """Classify a role on the profitability axis.

    Returns a RoleClassification. Falls back to keyword matching when role
    is not explicitly in role_classification. If no match at all, returns
    a 'support' classification with national scope (the safe default).
    """
    if not role or not isinstance(role, str):
        return RoleClassification(
            role=str(role) if role else "",
            tier=TIER_SUPPORT,
            branch_scope=SCOPE_HEAD_OFFICE,
            sbu=SBU_SUPPORT,
            matched_via="empty_role_fallback",
        )

    axis = _get_axis()
    classification = axis.get("role_classification", {})
    explicit = classification.get(role)
    if explicit:
        return RoleClassification(
            role=role,
            tier=explicit.get("tier", TIER_SUPPORT),
            branch_scope=explicit.get("branch_scope", SCOPE_HEAD_OFFICE),
            sbu=explicit.get("sbu", SBU_SUPPORT),
            matched_via="explicit",
        )

    # Keyword fallback
    fallback = axis.get("tier_keyword_fallback", {})
    role_lower = role.lower()

    tier_keyword_order = [
        (TIER_PORTFOLIO_OWNER,   "portfolio_owner_keywords"),
        (TIER_PROPOSITION_OWNER, "proposition_owner_keywords"),
        (TIER_STRUCTURAL_OWNER,  "structural_owner_keywords"),
        (TIER_SERVICE,           "service_keywords"),
        (TIER_SUPPORT,           "support_keywords"),
    ]
    for tier, kw_key in tier_keyword_order:
        for kw in fallback.get(kw_key, []):
            if kw.lower() in role_lower:
                return RoleClassification(
                    role=role,
                    tier=tier,
                    branch_scope=(
                        SCOPE_BRANCH_BOUND if tier in (TIER_SERVICE,) else
                        SCOPE_HEAD_OFFICE
                    ),
                    sbu=SBU_SUPPORT,
                    matched_via=f"keyword_fallback:{kw}",
                )

    # No match — safe support default
    return RoleClassification(
        role=role,
        tier=TIER_SUPPORT,
        branch_scope=SCOPE_HEAD_OFFICE,
        sbu=SBU_SUPPORT,
        matched_via="no_match_default",
    )


def get_profitability_tier(role: str) -> str:
    """Convenience: just the tier string."""
    return classify_role(role).tier


def get_branch_scope(role: str) -> str:
    """Convenience: just the branch scope."""
    return classify_role(role).branch_scope


def get_sbu(role: str) -> str:
    """Convenience: just the SBU."""
    return classify_role(role).sbu


def can_be_tagged(role: str) -> bool:
    """Returns True iff this role can legitimately appear in
    accounts.csv::relationship_manager_code or customers.csv::rm_code.

    Only portfolio_owner and service tiers qualify. Proposition owners
    don't tag (their attribution is via overlap views). Structural
    owners and support roles MUST NOT tag.
    """
    return classify_role(role).tier in _TAGGABLE_TIERS


def list_all_classified_roles() -> List[str]:
    """Return all roles explicitly in role_classification (not keyword fallback)."""
    return sorted(_get_axis().get("role_classification", {}).keys())


def list_roles_by_tier(tier: str) -> List[str]:
    """All explicitly classified roles in a given tier."""
    if tier not in ALL_TIERS:
        raise ValueError(f"tier '{tier}' not in {ALL_TIERS}")
    rc = _get_axis().get("role_classification", {})
    return sorted([r for r, d in rc.items() if d.get("tier") == tier])


def list_roles_by_sbu(sbu: str) -> List[str]:
    """All explicitly classified roles primarily owning a given SBU."""
    if sbu not in ALL_SBUS:
        raise ValueError(f"sbu '{sbu}' not in {ALL_SBUS}")
    rc = _get_axis().get("role_classification", {})
    return sorted([r for r, d in rc.items() if d.get("sbu") == sbu])


def _collect_used_roles_from_data() -> Set[str]:
    """Walk users.json + hr.json and return all roles in use."""
    roles: Set[str] = set()
    users_path = DATA_DIR / "users.json"
    if users_path.exists():
        try:
            users = json.loads(users_path.read_text(encoding="utf-8"))
            for u, rec in users.items():
                if isinstance(rec, dict):
                    r = rec.get("role", "")
                    if r and isinstance(r, str):
                        roles.add(r)
        except Exception:
            pass
    hr_path = DATA_DIR / "hr.json"
    if hr_path.exists():
        try:
            hr = json.loads(hr_path.read_text(encoding="utf-8"))
            if isinstance(hr, list):
                for staff in hr:
                    if isinstance(staff, dict):
                        r = staff.get("role", "")
                        if r and isinstance(r, str):
                            roles.add(r)
        except Exception:
            pass
    return roles


def validate_role_coverage() -> Dict[str, Any]:
    """Audit: every role used in users.json + hr.json must classify.

    Returns dict with:
      total_used: count of distinct roles in users + hr
      explicit:   number with role_classification entry
      keyword:    number matched via keyword fallback
      default:    number that fell to no_match_default (these are flagged
                  because they get assigned support/HO/Support — admin
                  should review and add explicit entries)
      unclassified: list of roles that fell to default (sorted)
      by_tier:    counts of mapped roles per tier
    """
    used = _collect_used_roles_from_data()
    explicit = []
    keyword = []
    default = []
    by_tier: Dict[str, int] = {t: 0 for t in ALL_TIERS}

    for role in used:
        c = classify_role(role)
        if c.matched_via == "explicit":
            explicit.append(role)
        elif c.matched_via.startswith("keyword_fallback"):
            keyword.append(role)
        else:
            default.append(role)
        by_tier[c.tier] = by_tier.get(c.tier, 0) + 1

    return {
        "total_used": len(used),
        "explicit": len(explicit),
        "keyword": len(keyword),
        "default": len(default),
        "unclassified": sorted(default),
        "by_tier": by_tier,
    }


def self_test() -> None:
    """v10.374 self_test — uses real org_hierarchy_config.json (not synthetic)."""
    tests_run = 0

    # Test 1: known explicit portfolio_owner classifies correctly
    c = classify_role("Relationship Officer-Personal Banker")
    assert c.tier == TIER_PORTFOLIO_OWNER, c.tier
    assert c.branch_scope == SCOPE_BRANCH_BOUND
    assert c.sbu == SBU_RETAIL
    assert c.matched_via == "explicit"
    tests_run += 1

    # Test 2: HO RM (multi-branch portfolio owner)
    c = classify_role("Relationship Manager - Corporate Banking")
    assert c.tier == TIER_PORTFOLIO_OWNER
    assert c.branch_scope == SCOPE_HEAD_OFFICE
    assert c.sbu == SBU_CORPORATE
    tests_run += 1

    # Test 3: Proposition owner
    c = classify_role("Head Of Women Banking")
    assert c.tier == TIER_PROPOSITION_OWNER
    assert not can_be_tagged("Head Of Women Banking"), (
        "Proposition owners must NOT be taggable"
    )
    tests_run += 1

    # Test 4: Structural owner (not tagged)
    c = classify_role("Branch Manager")
    assert c.tier == TIER_STRUCTURAL_OWNER
    assert not can_be_tagged("Branch Manager")
    tests_run += 1

    # Test 5: Service (can be tagged but not primary)
    c = classify_role("Teller")
    assert c.tier == TIER_SERVICE
    assert can_be_tagged("Teller")  # occasionally tagged
    tests_run += 1

    # Test 6: Support
    c = classify_role("Compliance Officer")
    assert c.tier == TIER_SUPPORT
    assert not can_be_tagged("Compliance Officer")
    tests_run += 1

    # Test 7: MD is structural at national scope
    c = classify_role("Managing Director")
    assert c.tier == TIER_STRUCTURAL_OWNER
    assert c.branch_scope == SCOPE_NATIONAL
    tests_run += 1

    # Test 8: Keyword fallback works for unknown sales role
    c = classify_role("Senior Relationship Manager - Wholesale")
    assert c.tier == TIER_PORTFOLIO_OWNER, (
        f"Wholesale RM should classify as portfolio_owner via 'relationship manager' keyword, got {c.tier}"
    )
    assert "keyword_fallback" in c.matched_via
    tests_run += 1

    # Test 9: empty role → safe default
    c = classify_role("")
    assert c.tier == TIER_SUPPORT
    tests_run += 1

    # Test 10: list_roles_by_tier
    owners = list_roles_by_tier(TIER_PORTFOLIO_OWNER)
    assert len(owners) >= 10, f"expected ≥10 portfolio owners, got {len(owners)}"
    assert "Relationship Manager - SME" in owners
    tests_run += 1

    # Test 11: validate_role_coverage runs without error
    coverage = validate_role_coverage()
    assert "total_used" in coverage
    assert coverage["total_used"] > 0
    # Sum of explicit + keyword + default must equal total
    assert (coverage["explicit"] + coverage["keyword"] +
            coverage["default"]) == coverage["total_used"]
    tests_run += 1

    # Test 12: bad inputs
    try:
        list_roles_by_tier("bogus_tier")
        assert False, "should have raised"
    except ValueError:
        pass
    tests_run += 1

    print(f"✓ role_taxonomy self-test passed ({tests_run} tests)")


if __name__ == "__main__":
    self_test()
    cov = validate_role_coverage()
    print(f"\nRole coverage on production data:")
    print(f"  Total distinct roles used:  {cov['total_used']}")
    print(f"  Explicit classifications:   {cov['explicit']}")
    print(f"  Keyword fallback matches:   {cov['keyword']}")
    print(f"  Default (no-match):         {cov['default']}")
    if cov['unclassified']:
        print(f"\n  Unclassified roles (review):")
        for r in cov['unclassified'][:20]:
            print(f"    {r}")
    print(f"\n  Distribution by tier:")
    for t, n in cov['by_tier'].items():
        print(f"    {t:<22}: {n}")
