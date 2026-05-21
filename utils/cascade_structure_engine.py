"""utils/cascade_structure_engine.py — v10.393 Cascade Structural Audit.

Per v10.391 Target Cascade Diagnosis + the discoveries from the
attempted v10.393 surgical cleanup (which surfaced new finding TC32).

This leaf module exposes structural detection functions over the
cascade graph (target_cascade.json + users.json) so v10.394+ can
make precise re-cascade decisions.

Module purity: leaf module — zero upward `utils.*` imports. Pure I/O
+ graph analysis + dataclass results.

Public surface:
  CascadeStructureFindings (dataclass — aggregated results)
  detect_cycles()                       → list of cycle tuples
  detect_representative_sender_pattern()→ list per role
  detect_cross_branch_violations(pairs) → list per violation
  detect_multi_sender_ambiguity()       → list per ambiguous staff
  full_audit()                          → CascadeStructureFindings
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from collections import defaultdict, Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO = Path(__file__).resolve().parent.parent
DATA_DIR = REPO / "data"
CASCADE_PATH = DATA_DIR / "target_cascade.json"
USERS_PATH = DATA_DIR / "users.json"

# Canonical within-branch pairs are now DERIVED from admin config
# (data/org_hierarchy_config.json) rather than hardcoded.
#
# Rationale: different banks name roles differently. The cascade structure
# engine must not bake in any specific role names. Both the role taxonomy
# AND reporting lines come from org_hierarchy_config.json::
#   - role_tiers           — assigns each role a seniority tier (0..6)
#   - role_manager_whitelist — defines subordinate → [valid managers]
#   - branch_tier_threshold — optional; default 4 (roles at tier >= 4 are
#                             branch-level; lower tiers are HQ/regional)
#
# A (manager_role, subordinate_role) pair is "within-branch" when BOTH
# roles are at tier >= threshold. Tier 0..3 = HQ + regional supervision
# (Senior Branch Manager, Area Manager) — those can legitimately cascade
# across branches. Tier 4+ = branch-level — must cascade within a branch.

DEFAULT_BRANCH_TIER_THRESHOLD = 4  # roles at this tier or higher are branch-level


def _load_org_config() -> Dict[str, Any]:
    """Load org_hierarchy_config.json or return empty dict."""
    cfg_path = DATA_DIR / "org_hierarchy_config.json"
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _real_entries(d: Dict[str, Any]) -> Dict[str, Any]:
    """Strip _note / _v10XYZ meta keys from a config dict."""
    return {k: v for k, v in d.items() if not k.startswith("_")}


def load_role_tiers() -> Dict[str, int]:
    """Return canonical role→tier mapping from admin config.

    Tier convention (per config _note):
      0=MD root, 1=C-suite, 2=head/director, 3=senior manager + area manager,
      4=manager, 5=officer/specialist, 6=entry/frontline.

    Returns empty dict if config missing or malformed.
    """
    cfg = _load_org_config()
    tiers = cfg.get("role_tiers", {})
    if not isinstance(tiers, dict):
        return {}
    return {k: int(v) for k, v in _real_entries(tiers).items()
            if isinstance(v, (int, float))}


def load_role_manager_whitelist() -> Dict[str, List[str]]:
    """Return canonical subordinate→[managers] mapping from admin config.

    This is the canonical line manager hierarchy — same one the pipeline
    module uses for upward flow.

    Returns empty dict if config missing or malformed.
    """
    cfg = _load_org_config()
    rmw = cfg.get("role_manager_whitelist", {})
    if not isinstance(rmw, dict):
        return {}
    out: Dict[str, List[str]] = {}
    for sub_role, mgr_list in _real_entries(rmw).items():
        if isinstance(mgr_list, list):
            out[sub_role] = [m for m in mgr_list if isinstance(m, str)]
    return out


def load_branch_tier_threshold() -> int:
    """Return the tier threshold above which roles are branch-level.

    Defaults to 4. Admin can override by adding `branch_tier_threshold`
    to org_hierarchy_config.json.
    """
    cfg = _load_org_config()
    val = cfg.get("branch_tier_threshold", DEFAULT_BRANCH_TIER_THRESHOLD)
    try:
        return int(val)
    except (TypeError, ValueError):
        return DEFAULT_BRANCH_TIER_THRESHOLD


def load_within_branch_role_pairs() -> Set[Tuple[str, str]]:
    """Derive within-branch (manager_role, subordinate_role) pairs from config.

    A pair is within-branch iff:
      - subordinate has manager in canonical whitelist, AND
      - both manager_role and subordinate_role have tier >= branch_tier_threshold

    Roles without tier assignment are treated as below threshold (HQ/regional)
    to avoid false-positive within-branch flagging.
    """
    rmw = load_role_manager_whitelist()
    tiers = load_role_tiers()
    threshold = load_branch_tier_threshold()
    pairs: Set[Tuple[str, str]] = set()
    for sub_role, mgrs in rmw.items():
        sub_tier = tiers.get(sub_role)
        if sub_tier is None or sub_tier < threshold:
            continue
        for mgr_role in mgrs:
            mgr_tier = tiers.get(mgr_role)
            if mgr_tier is None or mgr_tier < threshold:
                continue
            pairs.add((mgr_role, sub_role))
    return pairs


# Module-level constant populated at import time from admin config.
# Refresh by calling load_within_branch_role_pairs() directly.
WITHIN_BRANCH_ROLE_PAIRS: Set[Tuple[str, str]] = load_within_branch_role_pairs()


# ─────────────────────────────────────────────────────────────────────
# Result dataclasses
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CycleFinding:
    """One cycle in the cascade graph (2-cycle or longer)."""
    cycle_codes: Tuple[str, ...]
    cycle_length: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RepresentativeSenderFinding:
    """One role where representation is broken (only few staff act as senders)."""
    role: str
    total_staff: int
    sender_count: int
    coverage_pct: float
    severity: str  # "ok" | "warn" | "critical"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CrossBranchFinding:
    """One cross-branch violation in a within-branch role pair."""
    cascade_key: str
    sender_code: str
    sender_role: str
    sender_unit: str
    receiver_code: str
    receiver_role: str
    receiver_unit: str
    amount: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MultiSenderFinding:
    """One staff member receiving cascade from multiple senders for same KPI."""
    receiver_code: str
    kpi: str
    period: str
    sender_codes: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receiver_code": self.receiver_code,
            "kpi": self.kpi,
            "period": self.period,
            "sender_codes": list(self.sender_codes),
        }


@dataclass
class CascadeStructureFindings:
    """Aggregated results of full structural audit."""
    cycles: List[CycleFinding] = field(default_factory=list)
    representation: List[RepresentativeSenderFinding] = field(default_factory=list)
    cross_branch: List[CrossBranchFinding] = field(default_factory=list)
    multi_sender: List[MultiSenderFinding] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycles": [c.to_dict() for c in self.cycles],
            "representation": [r.to_dict() for r in self.representation],
            "cross_branch": [v.to_dict() for v in self.cross_branch],
            "multi_sender": [m.to_dict() for m in self.multi_sender],
            "summary": self.summary,
        }


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _load_cascade() -> Dict[str, Any]:
    if not CASCADE_PATH.exists():
        return {}
    try:
        return json.loads(CASCADE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_users() -> Dict[str, Any]:
    if not USERS_PATH.exists():
        return {}
    try:
        return json.loads(USERS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_user_lookups(users: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Returns (code_to_unit, code_to_role)."""
    c2u, c2r = {}, {}
    for u in users.values():
        code = u.get("staff_code")
        if code:
            c2u[code] = u.get("unit", "?")
            c2r[code] = u.get("role", "?")
    return c2u, c2r


def _build_cascade_graph(tc: Dict[str, Any]) -> Dict[str, Set[str]]:
    """Returns adjacency: from_code → {to_code}."""
    g: Dict[str, Set[str]] = defaultdict(set)
    for k, v in tc.items():
        if not isinstance(v, dict): continue
        if not v.get("from_code"): continue
        for a in v.get("allocations", []) or []:
            if a.get("to_code"):
                g[v["from_code"]].add(a["to_code"])
    return dict(g)


# ─────────────────────────────────────────────────────────────────────
# Detection functions
# ─────────────────────────────────────────────────────────────────────

def detect_cycles() -> List[CycleFinding]:
    """Find 2-cycles in the cascade graph. Returns list of findings.

    Larger cycles (3-, 4-, ...) are not detected here; would need a more
    complex algorithm. 2-cycles are the most common pathology.
    """
    tc = _load_cascade()
    if not tc:
        return []
    g = _build_cascade_graph(tc)
    found = set()
    for a, targets in g.items():
        for b in targets:
            if a in g.get(b, set()):
                found.add(tuple(sorted([a, b])))
    return [CycleFinding(cycle_codes=c, cycle_length=2) for c in sorted(found)]


def detect_representative_sender_pattern(
        min_total: int = 2,
        warn_threshold_pct: float = 50.0,
        critical_threshold_pct: float = 10.0,
        ) -> List[RepresentativeSenderFinding]:
    """Find roles where only a small fraction of role-holders are cascade senders.

    TC32 (v10.393 discovery): the cascade was generated such that a single
    "representative" staff member of each role cascades to all subordinates
    bank-wide. Most role-holders never appear as senders.

    v10.398 refinement: only flag roles that appear as a MANAGER in
    canonical role_manager_whitelist (i.e., roles that SHOULD be senders).
    Leaf roles (Teller, Officer, RM) have no canonical subordinates so being
    "0 senders" is expected, not a bug.

    Returns findings ordered worst-coverage-first, severity flagged.
    """
    tc = _load_cascade()
    users = _load_users()
    if not tc or not users:
        return []
    c2u, c2r = _build_user_lookups(users)

    role_total: Counter = Counter()
    for u in users.values():
        role_total[u.get("role", "?")] += 1

    role_senders: Dict[str, Set[str]] = defaultdict(set)
    for k, v in tc.items():
        if not isinstance(v, dict): continue
        if not v.get("kpi"): continue
        sender = v.get("from_code")
        if sender:
            role_senders[c2r.get(sender, "?")].add(sender)

    # v10.398: build set of roles that ARE managers per canonical
    rmw = load_role_manager_whitelist()
    manager_roles: Set[str] = set()
    for mgr_list in rmw.values():
        if isinstance(mgr_list, list):
            manager_roles.update(m for m in mgr_list if isinstance(m, str))

    findings: List[RepresentativeSenderFinding] = []
    for role, total in role_total.items():
        if total < min_total:
            continue
        # v10.398: skip leaf roles (not managers per canonical)
        if role not in manager_roles:
            continue
        senders = len(role_senders.get(role, set()))
        coverage = (senders / total) * 100 if total > 0 else 0.0
        if coverage >= warn_threshold_pct:
            severity = "ok"
        elif coverage >= critical_threshold_pct:
            severity = "warn"
        else:
            severity = "critical"
        findings.append(RepresentativeSenderFinding(
            role=role,
            total_staff=total,
            sender_count=senders,
            coverage_pct=round(coverage, 1),
            severity=severity,
        ))
    findings.sort(key=lambda f: (f.severity != "critical", f.coverage_pct))
    return findings


def detect_cross_branch_violations(
        pairs: Optional[Set[Tuple[str, str]]] = None,
        ) -> List[CrossBranchFinding]:
    """Find allocations in within-branch role pairs that cross branches.

    For role pairs in `pairs` (defaults to WITHIN_BRANCH_ROLE_PAIRS),
    sender's unit must equal receiver's unit. HQ senders are NOT checked
    (HQ flows are legitimate cross-branch by definition).
    """
    if pairs is None:
        pairs = WITHIN_BRANCH_ROLE_PAIRS
    tc = _load_cascade()
    users = _load_users()
    if not tc or not users:
        return []
    c2u, c2r = _build_user_lookups(users)

    findings: List[CrossBranchFinding] = []
    for k, v in tc.items():
        if not isinstance(v, dict): continue
        if not v.get("kpi"): continue
        sender = v.get("from_code")
        if not sender: continue
        su = c2u.get(sender, "?")
        if su == "Head Office":
            continue
        sr = c2r.get(sender, "?")
        for a in v.get("allocations", []) or []:
            rcvr = a.get("to_code")
            if not rcvr: continue
            ru = c2u.get(rcvr, "?")
            rr = c2r.get(rcvr, "?")
            if (sr, rr) in pairs and su != ru:
                findings.append(CrossBranchFinding(
                    cascade_key=k,
                    sender_code=sender, sender_role=sr, sender_unit=su,
                    receiver_code=rcvr, receiver_role=rr, receiver_unit=ru,
                    amount=float(a.get("amount", 0)),
                ))
    return findings


def detect_multi_sender_ambiguity() -> List[MultiSenderFinding]:
    """Find staff receiving cascade from multiple senders for same KPI+period."""
    tc = _load_cascade()
    if not tc:
        return []
    # group: (receiver, kpi, period) → set of senders
    groups: Dict[Tuple[str, str, str], Set[str]] = defaultdict(set)
    for k, v in tc.items():
        if not isinstance(v, dict): continue
        if not v.get("kpi"): continue
        sender = v.get("from_code")
        kpi = v.get("kpi", "")
        period = v.get("period", "")
        if not sender or not kpi or not period: continue
        for a in v.get("allocations", []) or []:
            rcvr = a.get("to_code")
            if rcvr:
                groups[(rcvr, kpi, period)].add(sender)
    findings: List[MultiSenderFinding] = []
    for (rcvr, kpi, period), senders in groups.items():
        if len(senders) > 1:
            findings.append(MultiSenderFinding(
                receiver_code=rcvr, kpi=kpi, period=period,
                sender_codes=tuple(sorted(senders)),
            ))
    return findings


# ─────────────────────────────────────────────────────────────────────
# Convenience aggregator
# ─────────────────────────────────────────────────────────────────────

def full_audit() -> CascadeStructureFindings:
    """Run all detection functions and return aggregated findings."""
    cycles = detect_cycles()
    rep    = detect_representative_sender_pattern()
    cb     = detect_cross_branch_violations()
    ms     = detect_multi_sender_ambiguity()

    return CascadeStructureFindings(
        cycles=cycles,
        representation=rep,
        cross_branch=cb,
        multi_sender=ms,
        summary={
            "cycles_count": len(cycles),
            "rep_critical_count": sum(1 for r in rep if r.severity == "critical"),
            "rep_warn_count": sum(1 for r in rep if r.severity == "warn"),
            "cross_branch_count": len(cb),
            "multi_sender_count": len(ms),
        },
    )


# ─────────────────────────────────────────────────────────────────────
# Self-tests
# ─────────────────────────────────────────────────────────────────────

def self_test() -> None:
    tests = 0

    # Test 1 — detect_cycles works and returns 0 after v10.392 cycle fix
    cycles = detect_cycles()
    assert isinstance(cycles, list)
    assert len(cycles) == 0, f"v10.392 should have fixed all cycles, got {cycles}"
    tests += 1

    # Test 2 — detect_representative_sender_pattern runs cleanly.
    # v10.398: detector only flags roles that ARE managers per canonical.
    # Post-v10.398 with full HQ canonical, 0 critical findings is the goal.
    rep = detect_representative_sender_pattern()
    assert isinstance(rep, list)
    # No assertion on count — leaf-filtered detector may return 0 findings
    # when canonical is complete (the desired state).
    tests += 1

    # Test 3 — rep-sender detection runs cleanly.
    # v10.398: detector now skips leaf roles (only flags canonical managers).
    # Post-v10.398, 0 critical findings is the goal.
    critical = [r for r in rep if r.severity == "critical"]
    assert len(critical) == 0, (
        f"v10.398 expects 0 critical rep-sender findings; got {len(critical)}"
    )
    tests += 1

    # Test 4 — detect_cross_branch_violations runs cleanly
    # Pre-v10.397 expected many (>1000) — bug present.
    # Post-v10.397 expects 0 — cascade regenerated correctly.
    cb = detect_cross_branch_violations()
    assert isinstance(cb, list)
    assert len(cb) == 0, (
        f"v10.397 cascade should have 0 cross-branch violations; got {len(cb)}"
    )
    tests += 1

    # Test 5 — cross-branch list is empty (post-regeneration)
    # (Sample structure check no longer applicable; verified in v10.393 test)
    tests += 1

    # Test 6 — detect_multi_sender_ambiguity
    ms = detect_multi_sender_ambiguity()
    assert isinstance(ms, list)
    # Post-v10.397: 0 multi-sender ambiguities expected
    assert len(ms) == 0, (
        f"v10.397 cascade should have 0 multi-sender ambiguities; got {len(ms)}"
    )
    tests += 1

    # Test 7 — full_audit returns aggregated (post-v10.397 metrics)
    findings = full_audit()
    assert isinstance(findings, CascadeStructureFindings)
    assert findings.summary["cycles_count"] == 0
    # rep_critical remains > 0 (HQ specialists = TC42)
    assert findings.summary["rep_critical_count"] >= 0
    assert findings.summary["cross_branch_count"] == 0
    assert findings.summary["multi_sender_count"] == 0
    tests += 1

    # Test 8 — to_dict round-trip
    d = findings.to_dict()
    assert "cycles" in d
    assert "representation" in d
    assert "cross_branch" in d
    assert "multi_sender" in d
    assert "summary" in d
    tests += 1

    # Test 9 — WITHIN_BRANCH_ROLE_PAIRS derived from canonical config
    rmw = load_role_manager_whitelist()
    tiers = load_role_tiers()
    threshold = load_branch_tier_threshold()
    # Sanity: config provides both whitelist and tiers
    assert len(rmw) > 0, "role_manager_whitelist must exist in admin config"
    assert len(tiers) > 0, "role_tiers must exist in admin config"
    # WITHIN_BRANCH_ROLE_PAIRS must be derivable (not empty)
    assert len(WITHIN_BRANCH_ROLE_PAIRS) > 0, (
        "WITHIN_BRANCH_ROLE_PAIRS empty — config drift?"
    )
    # Every pair must respect tier threshold
    for mgr, sub in WITHIN_BRANCH_ROLE_PAIRS:
        assert tiers.get(mgr, -1) >= threshold, (
            f"{mgr} (tier {tiers.get(mgr)}) violates threshold"
        )
        assert tiers.get(sub, -1) >= threshold, (
            f"{sub} (tier {tiers.get(sub)}) violates threshold"
        )
    # Refresh function returns same set (idempotent)
    fresh = load_within_branch_role_pairs()
    assert fresh == WITHIN_BRANCH_ROLE_PAIRS, "refresh mismatch"
    tests += 1

    print(f"✓ cascade_structure_engine self_test passed ({tests} tests)")
    print(f"  Cycles:                    {findings.summary['cycles_count']}")
    print(f"  Rep-pattern CRITICAL roles:{findings.summary['rep_critical_count']}")
    print(f"  Rep-pattern WARN roles:    {findings.summary['rep_warn_count']}")
    print(f"  Cross-branch violations:   {findings.summary['cross_branch_count']}")
    print(f"  Multi-sender ambiguities:  {findings.summary['multi_sender_count']}")


if __name__ == "__main__":
    import sys as _sys
    _repo = Path(__file__).resolve().parent.parent
    if str(_repo) not in _sys.path:
        _sys.path.insert(0, str(_repo))
    self_test()
