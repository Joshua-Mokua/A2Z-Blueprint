"""utils/hierarchy_synth.py — Org hierarchy synthesis (v10.316).

Closes B-012 (logged v10.314): 1,236 of 1,428 active staff have no
manager_code linkage in source data. Without a walkable hierarchy
for the full org, the cascade demo the client specifically asked
for can only walk 13% of the universe.

v10.316 refinements (Joshua's review):
  - Reporting lines now CONFIG-DRIVEN via data/org_hierarchy_config.json
  - Synthetic MD + Chiefs injected when not present in source data
  - hr.json linkages validated against role_manager_whitelist;
    violators get overridden (basis=hr_json_overridden) so the
    cascade stays clean
  - "Only chiefs report to MD" is a hardcoded invariant — synthesis
    enforces it
  - cascade_from_root() walks from MD downward (right direction for
    target cascade displays)

Configurable (admin-editable in JSON):
  - Reporting chains per department
  - Role → tier mapping
  - Role → manager whitelist
  - Synthetic top-org structure (MD + Chiefs)
  - Max span of control / chain depth

Hardcoded (system invariants):
  - Validation algorithm (no cycles, 1 root, all reachable)
  - "Only chiefs report to MD" rule
  - Synthesis algorithm

Per Rule 7, this module is diagnostic. It computes a hierarchy view
in-memory and returns it. It does NOT write to source data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


__all__ = [
    "role_tier",
    "find_root_md",
    "synthesise_full_hierarchy",
    "validate_hierarchy",
    "cascade_from_root",
    "build_synthetic_top_org",
    "HierarchyLink",
    "SyntheticStaffView",
]


# ════════════════════════════════════════════════════════════════════
# Dataclasses
# ════════════════════════════════════════════════════════════════════

@dataclass
class HierarchyLink:
    """A single synthesised manager linkage."""
    staff_code: str
    manager_code: Optional[str]
    basis: str
    # bases: hr_json, hr_json_overridden, retail_branch, retail_hq,
    # dept_seniority, chief_to_md, root, synthetic_chief, synthetic_md


@dataclass(frozen=True)
class SyntheticStaffView:
    """A synthetic staff record (MD or Chief) injected into the
    universe by the synthesiser. Has the same shape as StaffRecord."""
    staff_code: str
    full_name: str
    role: str
    department: str
    manager_code: Optional[str]
    band: Optional[str]
    source: str  # always 'synthetic'
    active: bool


# ════════════════════════════════════════════════════════════════════
# Role tier (config-driven, replaces v10.315 hardcoded regex)
# ════════════════════════════════════════════════════════════════════

def role_tier(role: str) -> int:
    """Map a role string to a seniority tier (0-6) via config."""
    from utils.org_hierarchy_config import classify_role_tier
    return classify_role_tier(role)


# ════════════════════════════════════════════════════════════════════
# Synthetic top-org injection
# ════════════════════════════════════════════════════════════════════

def build_synthetic_top_org(cfg, universe: Dict[str, Any]) -> Dict[str, SyntheticStaffView]:
    """Build synthetic MD + Chief records to inject into the universe.

    Rules:
      - MD injected if synthetic_top_enabled and no tier-0 real staff
      - Each configured Chief injected only if no real staff has that
        role; otherwise the real staff acts as the Chief

    Returns: dict of staff_code → SyntheticStaffView. MD has
    manager_code=None (root). Each Chief has manager_code=<MD>.
    """
    synthetic: Dict[str, SyntheticStaffView] = {}

    if not cfg.synthetic_top_enabled:
        return synthetic

    real_md_codes = [s.staff_code for s in universe.values()
                     if role_tier(s.role) == 0]

    md_code: Optional[str] = None
    if real_md_codes:
        md_code = sorted(real_md_codes)[0]
    elif cfg.synthetic_md:
        md = cfg.synthetic_md
        synthetic[md.staff_code] = SyntheticStaffView(
            staff_code=md.staff_code,
            full_name=md.full_name,
            role=md.role,
            department=md.department,
            manager_code=None,
            band=md.band,
            source="synthetic",
            active=True,
        )
        md_code = md.staff_code

    if md_code is None:
        return synthetic

    real_roles_in_universe = {s.role for s in universe.values()}
    for chief_spec in cfg.synthetic_chiefs:
        if chief_spec.role in real_roles_in_universe:
            continue
        if not chief_spec.staff_code:
            continue
        synthetic[chief_spec.staff_code] = SyntheticStaffView(
            staff_code=chief_spec.staff_code,
            full_name=chief_spec.full_name or chief_spec.role,
            role=chief_spec.role,
            department=chief_spec.department,
            manager_code=md_code,
            band=chief_spec.band,
            source="synthetic",
            active=True,
        )

    return synthetic


# ════════════════════════════════════════════════════════════════════
# Root identification
# ════════════════════════════════════════════════════════════════════

def find_root_md(universe: Dict[str, Any]) -> Optional[str]:
    """Find the org root.

    With synthetic_top enabled, returns the MD's staff_code (real or
    configured synthetic). Otherwise falls back to most senior real
    staff (v10.315 behaviour).
    """
    if not universe:
        return None

    try:
        from utils.org_hierarchy_config import load_config
        cfg = load_config()
    except Exception:  # noqa: BLE001
        cfg = None

    if cfg and cfg.synthetic_top_enabled and cfg.synthetic_md:
        return cfg.synthetic_md.staff_code

    tier0 = [s for s in universe.values() if role_tier(s.role) == 0]
    if tier0:
        return sorted(tier0, key=lambda s: s.staff_code)[0].staff_code

    for fallback_tier in range(1, 7):
        candidates = [s for s in universe.values()
                      if role_tier(s.role) == fallback_tier]
        if candidates:
            return sorted(
                candidates, key=lambda s: s.staff_code)[0].staff_code
    return None


# ════════════════════════════════════════════════════════════════════
# Chief lookup
# ════════════════════════════════════════════════════════════════════

def _find_chief_for_department(
    department: str,
    universe_with_synth: Dict[str, Any],
    cfg,
) -> Optional[str]:
    """Find a department's Chief staff_code via config mapping."""
    chief_role = cfg.department_chief_mapping.get(department)
    if not chief_role:
        return None
    candidates = [s for s in universe_with_synth.values()
                  if s.role == chief_role]
    if not candidates:
        return None
    return sorted(candidates, key=lambda s: s.staff_code)[0].staff_code


# ════════════════════════════════════════════════════════════════════
# Department synthesis (whitelist-aware)
# ════════════════════════════════════════════════════════════════════

def _synthesise_with_whitelist(
    dept_staff: List[Any],
    universe_with_synth: Dict[str, Any],
    chief_code: Optional[str],
    md_code: Optional[str],
    cfg,
) -> Dict[str, HierarchyLink]:
    """Synthesise hierarchy within a department, respecting the
    role_manager_whitelist from config.

    Algorithm:
      1. Sort staff by tier (lowest = most senior first)
      2. Most-senior staff at tier > 1 → Chief (or MD if no Chief)
      3. Each lower tier → whitelisted candidates above (round-robin)
    """
    links: Dict[str, HierarchyLink] = {}
    by_tier: Dict[int, List[Any]] = {}
    for s in dept_staff:
        t = role_tier(s.role)
        by_tier.setdefault(t, []).append(s)
    for t in by_tier:
        by_tier[t].sort(key=lambda s: s.staff_code)
    if not by_tier:
        return links

    fallback_parent = chief_code or md_code
    tiers_present = sorted(by_tier.keys())

    # Most senior tier → Chief
    for s in by_tier[tiers_present[0]]:
        links[s.staff_code] = HierarchyLink(
            staff_code=s.staff_code,
            manager_code=fallback_parent,
            basis="dept_seniority",
        )

    # Subsequent tiers → tier above with whitelist preference
    for i, tier in enumerate(tiers_present):
        if i == 0:
            continue
        candidates_above: List[Any] = []
        for higher_tier in tiers_present[:i]:
            candidates_above.extend(by_tier[higher_tier])
        if not candidates_above:
            for s in by_tier[tier]:
                links[s.staff_code] = HierarchyLink(
                    staff_code=s.staff_code,
                    manager_code=fallback_parent,
                    basis="dept_seniority",
                )
            continue

        for j, s in enumerate(by_tier[tier]):
            whitelist = cfg.role_manager_whitelist.get(s.role, [])
            preferred = [c for c in candidates_above
                         if c.role in whitelist] if whitelist else []
            if preferred:
                assigned = preferred[j % len(preferred)]
            else:
                assigned = candidates_above[
                    j % len(candidates_above)]
            links[s.staff_code] = HierarchyLink(
                staff_code=s.staff_code,
                manager_code=assigned.staff_code,
                basis="dept_seniority",
            )

    return links


# ════════════════════════════════════════════════════════════════════
# Retail Banking specialised synthesis
# ════════════════════════════════════════════════════════════════════

def _synthesise_retail_banking(
    retail_staff: List[Any],
    universe_with_synth: Dict[str, Any],
    chief_code: Optional[str],
    md_code: Optional[str],
    cfg,
) -> Dict[str, HierarchyLink]:
    """Retail Banking: Tellers/CSOs → Operations Supervisor →
    Operations Manager → Branch Manager → Area Manager → Head of
    Branches → Chief Retail Banking Officer → MD."""
    links: Dict[str, HierarchyLink] = {}
    by_role: Dict[str, List[Any]] = {}
    for s in retail_staff:
        by_role.setdefault(s.role, []).append(s)
    for r in by_role:
        by_role[r].sort(key=lambda s: s.staff_code)

    fallback_parent = chief_code or md_code

    def _link(s, manager_code, basis="retail_branch"):
        if s.staff_code in links:
            return
        links[s.staff_code] = HierarchyLink(
            staff_code=s.staff_code,
            manager_code=manager_code,
            basis=basis,
        )

    # Layer 1: Head of Branches → Chief Retail Banking Officer
    for s in by_role.get("Head of Branches", []):
        _link(s, chief_code, "retail_hq")
    for s in by_role.get("Head of Retail Banking", []):
        _link(s, chief_code, "retail_hq")

    head_of_branches = by_role.get("Head of Branches", [])
    hob_code = (sorted(head_of_branches,
                       key=lambda s: s.staff_code)[0].staff_code
                if head_of_branches else fallback_parent)

    # Layer 1.5: Retail HQ specialists → Head of Branches
    for role in ("Senior Manager Direct Sales Force",
                  "Head Of Women Banking"):
        for s in by_role.get(role, []):
            _link(s, hob_code, "retail_hq")

    # Layer 2: ONLY Area Managers → Head of Branches
    # (v10.330 — per banking convention, Senior Branch Managers are
    # peers of standard Branch Managers, both reporting through
    # Area Managers. Previously Senior BMs were incorrectly treated
    # as another tier between BMs and Area Managers.)
    for s in by_role.get("Area Manager", []):
        _link(s, hob_code, "retail_hq")

    # Layer 3: Branch Managers + Senior Branch Managers → Area Manager
    # (v10.330 — both BM tiers report to Area Managers; Senior BMs
    # may run flagship branches but they don't supervise other BMs)
    area_managers = sorted(
        by_role.get("Area Manager", []),
        key=lambda s: s.staff_code,
    )
    branch_managers = sorted(
        by_role.get("Branch Manager", []) +
        by_role.get("Senior Branch Manager", []),
        key=lambda s: s.staff_code,
    )
    if area_managers:
        for i, bm in enumerate(branch_managers):
            _link(bm, area_managers[i % len(area_managers)].staff_code)
    else:
        for bm in branch_managers:
            _link(bm, hob_code, "retail_hq")

    # Layer 4: Branch-level senior staff → Branch Manager
    # (uses the original branch_managers list which is now BM + Senior BM combined)
    if branch_managers:
        for role in ("Branch Operations Manager",
                      "Branch Relationship Manager",
                      "Branch Senior Relationship Officer"):
            staff = by_role.get(role, [])
            for i, s in enumerate(staff):
                _link(s, branch_managers[
                    i % len(branch_managers)].staff_code)

    # Layer 5: Branch Operations Supervisor → Branch Operations Manager
    ops_managers = sorted(
        by_role.get("Branch Operations Manager", []),
        key=lambda s: s.staff_code,
    )
    if ops_managers:
        for i, s in enumerate(
                by_role.get("Branch Operations Supervisor", [])):
            _link(s, ops_managers[i % len(ops_managers)].staff_code)

    # Layer 6: RO-Business/Personal Banker → Branch Relationship Manager
    rel_managers = sorted(
        by_role.get("Branch Relationship Manager", []),
        key=lambda s: s.staff_code,
    )
    parents_for_ros = rel_managers or branch_managers
    if parents_for_ros:
        for role in ("Relationship Officer-Business Banker",
                      "Relationship Officer-Personal Banker"):
            staff = by_role.get(role, [])
            for i, s in enumerate(staff):
                _link(s, parents_for_ros[
                    i % len(parents_for_ros)].staff_code)

    # Layer 7: Tellers + CSOs + DSRs → Branch Operations Supervisor
    supervisors = sorted(
        by_role.get("Branch Operations Supervisor", []),
        key=lambda s: s.staff_code,
    )
    parents_for_frontline = (
        supervisors or ops_managers or branch_managers)
    if parents_for_frontline:
        for role in ("Teller",
                      "Customer Service Officer",
                      "Direct Sales Representative - Assets & Liabilities",
                      "Direct Sales Representative"):
            staff = by_role.get(role, [])
            for i, s in enumerate(staff):
                _link(s, parents_for_frontline[
                    i % len(parents_for_frontline)].staff_code)

    for s in retail_staff:
        if s.staff_code not in links:
            _link(s, fallback_parent, "retail_hq")
    return links


# ════════════════════════════════════════════════════════════════════
# Full synthesis
# ════════════════════════════════════════════════════════════════════

def synthesise_full_hierarchy(
    universe: Dict[str, Any],
) -> Dict[str, HierarchyLink]:
    """Synthesise the full org hierarchy (v10.316 algorithm).

    Steps:
      1. Load config (or fall back to v10.315 behaviour)
      2. Build synthetic MD + Chiefs (inject into extended universe)
      3. MD → None (root, basis=synthetic_md or root)
      4. Each Chief → MD (basis=chief_to_md or synthetic_chief)
      5. For each department → synthesise (retail_branch or
         dept_seniority) with whitelist preference
      6. Apply hr.json linkages, BUT validate against whitelist:
         - whitelist-compliant → basis=hr_json
         - whitelist-violating → keep synthesis, basis=hr_json_overridden
    """
    try:
        from utils.org_hierarchy_config import load_config
        cfg = load_config()
    except Exception:  # noqa: BLE001
        return _synthesise_without_config(universe)

    synth_top = build_synthetic_top_org(cfg, universe)
    universe_ext: Dict[str, Any] = dict(universe)
    universe_ext.update(synth_top)

    md_code = (cfg.synthetic_md.staff_code
                if cfg.synthetic_md and cfg.synthetic_top_enabled
                else find_root_md(universe))

    all_links: Dict[str, HierarchyLink] = {}

    if md_code:
        all_links[md_code] = HierarchyLink(
            staff_code=md_code,
            manager_code=None,
            basis="synthetic_md" if md_code in synth_top else "root",
        )

    for code, view in synth_top.items():
        if code == md_code:
            continue
        all_links[code] = HierarchyLink(
            staff_code=code,
            manager_code=md_code,
            basis="synthetic_chief",
        )

    # Real Chiefs (tier-1 in universe) → MD
    for s in universe.values():
        if role_tier(s.role) == 1 and s.staff_code not in all_links:
            all_links[s.staff_code] = HierarchyLink(
                staff_code=s.staff_code,
                manager_code=md_code,
                basis="chief_to_md",
            )

    # Group remaining staff by department
    by_dept: Dict[str, List[Any]] = {}
    for s in universe.values():
        if s.staff_code in all_links:
            continue
        by_dept.setdefault(s.department, []).append(s)

    # Synthesise per department
    for dept, staff in by_dept.items():
        chief_code = _find_chief_for_department(
            dept, universe_ext, cfg)
        if dept == "Retail Banking":
            dept_links = _synthesise_retail_banking(
                staff, universe_ext, chief_code, md_code, cfg)
        else:
            dept_links = _synthesise_with_whitelist(
                staff, universe_ext, chief_code, md_code, cfg)
        all_links.update(dept_links)

    # Apply hr.json linkages with whitelist validation.
    # IMPORTANT: only treat manager_code as hr.json source data if
    # the staff record's `source` field is 'hr' or 'both'. Staff
    # whose source is 'users' may have manager_code populated from
    # a previous synthesis pass (when staff_universe() injects
    # synthesised linkages back into StaffRecord) — those are NOT
    # raw hr.json data and shouldn't be tagged as such.
    for code, staff in universe.items():
        if not staff.manager_code:
            continue
        source = getattr(staff, "source", None)
        if source not in ("hr", "both"):
            continue  # not raw hr.json data
        mgr = universe.get(staff.manager_code)
        if not mgr:
            continue  # Unresolved — keep synth
        whitelist = cfg.role_manager_whitelist.get(staff.role, [])
        if whitelist and mgr.role not in whitelist:
            existing = all_links.get(code)
            if existing:
                all_links[code] = HierarchyLink(
                    staff_code=code,
                    manager_code=existing.manager_code,
                    basis="hr_json_overridden",
                )
        else:
            all_links[code] = HierarchyLink(
                staff_code=code,
                manager_code=staff.manager_code,
                basis="hr_json",
            )

    return all_links


def _synthesise_without_config(
    universe: Dict[str, Any],
) -> Dict[str, HierarchyLink]:
    """Fallback when config can't be loaded."""
    md_code = find_root_md(universe)
    links: Dict[str, HierarchyLink] = {}
    if md_code:
        links[md_code] = HierarchyLink(
            staff_code=md_code, manager_code=None, basis="root")
        for s in universe.values():
            if s.staff_code == md_code:
                continue
            links[s.staff_code] = HierarchyLink(
                staff_code=s.staff_code,
                manager_code=md_code,
                basis="fallback",
            )
    return links


# ════════════════════════════════════════════════════════════════════
# Validation (hardcoded — system invariants)
# ════════════════════════════════════════════════════════════════════

def validate_hierarchy(
    links: Dict[str, HierarchyLink],
    universe: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate a synthesised hierarchy.

    Hardcoded invariants (NOT admin-configurable):
      1. Coverage — every staff has a link
      2. Resolution — every manager_code resolves
      3. Roots — exactly 1 root
      4. Cycles — no cycles
      5. **Only chiefs report to MD** (v10.316)
    """
    violations: List[str] = []

    try:
        from utils.org_hierarchy_config import load_config
        cfg = load_config()
        synth_top = build_synthetic_top_org(cfg, universe)
        universe_ext: Dict[str, Any] = dict(universe)
        universe_ext.update(synth_top)
        max_depth_config = cfg.max_chain_depth
    except Exception:  # noqa: BLE001
        universe_ext = universe
        max_depth_config = 20
        cfg = None

    # 1. Coverage
    missing = set(universe_ext.keys()) - set(links.keys())
    if missing:
        violations.append(
            f"{len(missing)} staff missing from hierarchy")

    # 2. Resolution
    unresolved = []
    for code, link in links.items():
        if link.manager_code and link.manager_code not in universe_ext:
            unresolved.append(code)
    if unresolved:
        violations.append(
            f"{len(unresolved)} staff have unresolved manager_code")

    # 3. Exactly 1 root
    roots = [code for code, link in links.items()
             if link.manager_code is None]
    if len(roots) != 1:
        violations.append(
            f"Expected 1 root, found {len(roots)}: {roots[:5]}")

    # 4. No cycles
    unreachable = 0
    max_depth_seen = 0
    for code in links:
        depth = 0
        cur = code
        visited = {cur}
        while True:
            link = links.get(cur)
            if not link or link.manager_code is None:
                break
            if link.manager_code in visited:
                violations.append(f"Cycle detected from {code}")
                unreachable += 1
                break
            cur = link.manager_code
            visited.add(cur)
            depth += 1
            if depth > max_depth_config + 5:
                violations.append(
                    f"Chain too deep from {code}: > "
                    f"{max_depth_config + 5} levels")
                unreachable += 1
                break
        max_depth_seen = max(max_depth_seen, depth)

    # 5. Only chiefs report to MD
    if len(roots) == 1 and cfg:
        md = roots[0]
        direct_to_md = [code for code, link in links.items()
                        if link.manager_code == md]
        non_chief_md_reports = []
        for code in direct_to_md:
            staff = universe_ext.get(code)
            if staff is None:
                continue
            tier = role_tier(staff.role)
            if tier != 1:
                non_chief_md_reports.append(
                    (code, staff.role, tier))
        if non_chief_md_reports:
            violations.append(
                f"{len(non_chief_md_reports)} non-Chief staff "
                f"report directly to MD: "
                f"{non_chief_md_reports[:3]}"
            )

    # Span of control
    span: Dict[str, int] = {}
    for link in links.values():
        if link.manager_code:
            span[link.manager_code] = span.get(
                link.manager_code, 0) + 1
    if span:
        span_counts = list(span.values())
        median_span = sorted(span_counts)[len(span_counts) // 2]
        max_span = max(span_counts)
    else:
        median_span = 0
        max_span = 0

    basis_count: Dict[str, int] = {}
    for link in links.values():
        basis_count[link.basis] = basis_count.get(link.basis, 0) + 1

    return {
        "valid": len(violations) == 0,
        "violations": violations,
        "total_links": len(links),
        "roots": roots,
        "max_depth_observed": max_depth_seen,
        "unreachable": unreachable,
        "managers": len(span),
        "median_span_of_control": median_span,
        "max_span_of_control": max_span,
        "basis_distribution": basis_count,
    }


# ════════════════════════════════════════════════════════════════════
# Cascade from root (top-down view)
# ════════════════════════════════════════════════════════════════════

def cascade_from_root(
    universe: Dict[str, Any],
    max_depth: Optional[int] = None,
) -> Dict[str, Any]:
    """Build the cascade tree starting at the MD (root), walking down.

    Returns:
      {
        "root": {staff_code, full_name, role, department},
        "children": [{staff, depth, children: [...]}],
        "max_depth": N,
        "total_nodes": N,
      }

    This is the right shape for the "target cascade starts from
    the MD" demo: drill DOWN from MD → Chiefs → Heads → ... →
    frontline.
    """
    links = synthesise_full_hierarchy(universe)

    try:
        from utils.org_hierarchy_config import load_config
        cfg = load_config()
        synth_top = build_synthetic_top_org(cfg, universe)
        universe_ext = dict(universe)
        universe_ext.update(synth_top)
        depth_cap = max_depth or cfg.max_chain_depth
    except Exception:  # noqa: BLE001
        universe_ext = universe
        depth_cap = max_depth or 12

    root_code = None
    for code, link in links.items():
        if link.manager_code is None:
            root_code = code
            break
    if root_code is None:
        return {"root": None, "children": [],
                "max_depth": 0, "total_nodes": 0}

    children_of: Dict[str, List[str]] = {}
    for code, link in links.items():
        if link.manager_code:
            children_of.setdefault(link.manager_code, []).append(code)

    def _staff_brief(code):
        s = universe_ext.get(code)
        if not s:
            return {"staff_code": code, "full_name": "?",
                    "role": "?", "department": "?"}
        return {
            "staff_code": s.staff_code,
            "full_name": s.full_name,
            "role": s.role,
            "department": s.department,
        }

    total_nodes = 0
    max_depth_seen = 0

    def _build(code, depth):
        nonlocal total_nodes, max_depth_seen
        total_nodes += 1
        max_depth_seen = max(max_depth_seen, depth)
        if depth >= depth_cap:
            return {"staff": _staff_brief(code), "depth": depth,
                    "children": []}
        kids = sorted(children_of.get(code, []))
        return {
            "staff": _staff_brief(code),
            "depth": depth,
            "children": [_build(c, depth + 1) for c in kids],
        }

    tree = _build(root_code, 0)
    return {
        "root": _staff_brief(root_code),
        "children": tree["children"],
        "max_depth": max_depth_seen,
        "total_nodes": total_nodes,
    }


SPEC_DEVIATION_NOTE = (
    "Per Rule 7, this module is diagnostic. It reads admin config "
    "(utils.org_hierarchy_config) and the staff universe, then "
    "computes a hierarchy view in-memory. It does NOT write to "
    "users.json, hr.json, or org_hierarchy_config.json. Validation "
    "invariants (no cycles, exactly 1 root, only chiefs report to "
    "MD) are HARDCODED — they're system rules, not admin-tunable."
)
