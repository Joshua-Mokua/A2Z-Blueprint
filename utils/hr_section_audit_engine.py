"""HR Section Audit Engine — v10.436 (HR rescue diagnostic).

Per Joshua directive: "We need a very deep review of every tab and
functionality and identify how first we can harmonise them within HR.
This body needs rescue."

This engine diagnoses the People (HR) section state across 6 dimensions:

  1. **Module placement**: Pages tagged `people_hr` that shouldn't be
     (CIMS, SLA Tracker) and pages that SHOULD be HR but aren't
     (staff onboarding/exit, currently engines only).

  2. **Page completeness**: stub vs substantial - LOC count, tab count,
     engine imports per page.

  3. **Engine wiring**: which HR-related engines (Std #14-#20 + new
     v10.434/v10.435) are NOT actually rendered in any page.

  4. **REACT readiness**: ZERO streamlit imports invariant + dataclass
     returns + JSON serializability across HR engines.

  5. **API readiness**: which HR engines have FastAPI endpoints in
     utils/api.py.

  6. **Data backing**: JSON vs Excel vs PostgreSQL per engine.

Read-only diagnostic. No rescue actions — those go to v10.437+.

Public API (API-first, ZERO streamlit):
  - audit_module_placement() -> ModulePlacementAudit
  - audit_page_completeness() -> PageCompletenessAudit
  - audit_engine_wiring() -> EngineWiringAudit
  - audit_react_readiness() -> ReactReadinessAudit
  - audit_api_coverage() -> APICoverageAudit
  - audit_data_backing() -> DataBackingAudit
  - hr_full_audit() -> HRFullAudit (master rollup with health %)

Shipped: v10.436.
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
PAGES_DIR = REPO_ROOT / "pages"
UTILS_DIR = REPO_ROOT / "utils"
API_FILE = REPO_ROOT / "utils" / "api.py"
MANIFEST = REPO_ROOT / "pages" / "_manifest.json"

# Canonical 7 HR-domain engines per Standards #14-#20 + 2 new from
# v10.434/v10.435. These are the engines that SHOULD back HR pages.
HR_DOMAIN_ENGINES: Dict[str, Dict[str, str]] = {
    "peer_learning":            {"std": "#14", "name": "Peer Learning Network",     "page_target": "lms"},
    "coaching_intelligence":    {"std": "#15", "name": "Coaching Intelligence",     "page_target": "pip"},
    "predictive_performance":   {"std": "#16", "name": "Predictive Performance",    "page_target": "people"},
    "gamification":             {"std": "#17", "name": "Gamification Engine",       "page_target": "people"},
    "efficiency":               {"std": "#18", "name": "Efficiency Engine",          "page_target": "people"},
    "wellness":                 {"std": "#19", "name": "Wellness Engine",            "page_target": "people"},
    "staff_onboarding_engine":  {"std": "v10.434", "name": "Staff Onboarding",      "page_target": "onboarding"},
    "staff_exit_engine":        {"std": "v10.435", "name": "Staff Exit Risk",        "page_target": "exit"},
}

# Pages CURRENTLY in people_hr department per manifest. Two are
# expected to be misplaced (CIMS, SLA Tracker per Joshua).
EXPECTED_HR_PAGES: Set[str] = {
    "2_people.py",
    "42_lms.py",
    "43_pip.py",
    "58_workforce.py",
    "60_disciplinary.py",
}

MISPLACED_HR_PAGES: Dict[str, str] = {
    "13_sla.py":  "operations_or_compliance",  # SLA Tracker is operational
    "18_cims.py": "sales_customer",            # CIMS = Customer Information Mgmt System
}

# Stub threshold: pages below this are considered non-substantive
STUB_LINE_THRESHOLD = 200
STUB_TAB_THRESHOLD = 2


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class ModulePlacementAudit:
    """Audit which pages are correctly tagged as people_hr."""
    pages_currently_in_hr: List[str]
    correctly_placed: List[str]
    misplaced_in_hr: List[Dict[str, str]]  # [{file, should_be_dept}]
    should_be_in_hr_but_arent: List[str]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PageStats:
    file: str
    title: str
    line_count: int
    tab_count: int
    engine_imports: List[str]
    is_stub: bool


@dataclass
class PageCompletenessAudit:
    """Audit substantiveness of each HR page."""
    pages: List[PageStats]
    stub_count: int
    substantial_count: int
    avg_lines_per_page: float
    total_lines: int
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pages": [asdict(p) for p in self.pages],
            "stub_count": self.stub_count,
            "substantial_count": self.substantial_count,
            "avg_lines_per_page": self.avg_lines_per_page,
            "total_lines": self.total_lines,
            "timestamp": self.timestamp,
        }


@dataclass
class EngineWiringAudit:
    """Audit whether HR-domain engines are imported into HR pages."""
    total_hr_engines: int
    wired_engines: List[Dict[str, Any]]    # [{engine, in_pages}]
    unwired_engines: List[Dict[str, Any]]   # [{engine, std, name}]
    wiring_coverage_pct: float
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReactReadinessAudit:
    """Per-engine REACT readiness: zero streamlit + dataclasses + JSON."""
    engines_checked: int
    react_ready_count: int
    engines_with_streamlit: List[str]
    engines_without_dataclasses: List[str]
    react_readiness_pct: float
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class APICoverageAudit:
    """Which HR engines have FastAPI endpoints."""
    total_engines: int
    engines_with_api: List[str]
    engines_without_api: List[Dict[str, str]]
    api_coverage_pct: float
    endpoint_count_by_engine: Dict[str, int]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DataBackingAudit:
    """Data layer per HR engine: JSON / Excel / PostgreSQL."""
    engines: List[Dict[str, Any]]
    pg_ready_count: int
    json_only_count: int
    excel_dependent_count: int
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HRFullAudit:
    """Master rollup with HR health score."""
    module_placement: ModulePlacementAudit
    page_completeness: PageCompletenessAudit
    engine_wiring: EngineWiringAudit
    react_readiness: ReactReadinessAudit
    api_coverage: APICoverageAudit
    data_backing: DataBackingAudit
    hr_health_pct: float
    severity_counts: Dict[str, int]
    rescue_priorities: List[str]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_placement": self.module_placement.to_dict(),
            "page_completeness": self.page_completeness.to_dict(),
            "engine_wiring": self.engine_wiring.to_dict(),
            "react_readiness": self.react_readiness.to_dict(),
            "api_coverage": self.api_coverage.to_dict(),
            "data_backing": self.data_backing.to_dict(),
            "hr_health_pct": self.hr_health_pct,
            "severity_counts": self.severity_counts,
            "rescue_priorities": self.rescue_priorities,
            "timestamp": self.timestamp,
        }


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _load_manifest() -> Dict[str, Any]:
    if not MANIFEST.exists():
        return {}
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _hr_pages_from_manifest() -> List[Dict[str, str]]:
    """Get pages currently tagged department_primary='people_hr'."""
    m = _load_manifest()
    out = []
    for fname, p in m.get("pages", {}).items():
        if isinstance(p, dict) and p.get("department_primary") == "people_hr":
            out.append({
                "file": fname,
                "title": str(p.get("title", "")),
                "icon": str(p.get("icon", "")),
            })
    return sorted(out, key=lambda x: x["file"])


def _count_lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeDecodeError):
        return 0


def _count_tabs(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    # Count st.tabs() calls
    return len(re.findall(r"st\.tabs\s*\(", text))


def _engine_imports(path: Path) -> List[str]:
    """List utils.* engine modules imported by a page."""
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    imports: Set[str] = set()
    for m in re.finditer(r"from\s+utils\.([a-z_]+)\s+import", text):
        imports.add(m.group(1))
    for m in re.finditer(r"import\s+utils\.([a-z_]+)", text):
        imports.add(m.group(1))
    return sorted(imports)


def _has_streamlit_imports(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return bool(re.search(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    ))


def _has_dataclasses(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return "@dataclass" in text


def _api_endpoint_count_for(engine_name: str) -> int:
    """Count FastAPI endpoints that reference this engine."""
    if not API_FILE.exists():
        return 0
    try:
        text = API_FILE.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return 0
    # Count routes whose handlers import from this engine
    handlers = re.findall(r"@app\.(?:get|post|put|delete)\([^)]+\)\s*\ndef\s+\w+[^}]+?", text)
    count = 0
    # Simpler heuristic: count occurrences of "from utils.{engine}" inside
    # function bodies within api.py. Approximation works for our pattern.
    pattern = f"from utils.{engine_name}"
    count = text.count(pattern)
    return count


def _data_backing_of(engine_name: str) -> Dict[str, Any]:
    """Inspect what data sources an engine touches."""
    p = UTILS_DIR / f"{engine_name}.py"
    if not p.exists():
        return {"backing": "missing"}
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {"backing": "unreadable"}

    uses_json = bool(re.search(r"json\.load|\.json[\"']\s*[,)]", text))
    uses_excel = bool(re.search(r"\.xlsx|read_excel|to_excel", text))
    uses_postgres = bool(re.search(
        r"psycopg|sqlalchemy|postgres|SELECT\s+|INSERT\s+INTO",
        text, re.IGNORECASE,
    ))
    return {
        "backing": "postgres" if uses_postgres else
                   "excel" if uses_excel else
                   "json" if uses_json else "memory",
        "uses_json": uses_json,
        "uses_excel": uses_excel,
        "uses_postgres": uses_postgres,
    }


# ════════════════════════════════════════════════════════════════════
# Audits
# ════════════════════════════════════════════════════════════════════

def audit_module_placement() -> ModulePlacementAudit:
    """Audit which pages are correctly in HR vs misplaced."""
    current = _hr_pages_from_manifest()
    current_files = {p["file"] for p in current}

    correctly_placed = sorted(EXPECTED_HR_PAGES & current_files)
    misplaced = [
        {"file": f, "should_be_dept": MISPLACED_HR_PAGES[f]}
        for f in sorted(MISPLACED_HR_PAGES.keys() & current_files)
    ]
    # Should-be-in-HR-but-aren't: dynamically detect whether the
    # staff onboarding + exit engines have user-facing pages yet.
    should_be: List[str] = []
    onboarding_page_exists = (PAGES_DIR / "79_staff_onboarding.py").exists()
    exit_page_exists = (PAGES_DIR / "80_staff_exit.py").exists()
    if not onboarding_page_exists:
        should_be.append(
            "(no page yet) — Staff Onboarding (engine: staff_onboarding_engine)"
        )
    if not exit_page_exists:
        should_be.append(
            "(no page yet) — Staff Exit & Succession (engine: staff_exit_engine)"
        )

    return ModulePlacementAudit(
        pages_currently_in_hr=sorted(current_files),
        correctly_placed=correctly_placed,
        misplaced_in_hr=misplaced,
        should_be_in_hr_but_arent=should_be,
        timestamp=datetime.now().isoformat(),
    )


def audit_page_completeness() -> PageCompletenessAudit:
    """Audit substantiveness of each HR page."""
    current = _hr_pages_from_manifest()
    stats: List[PageStats] = []
    total_lines = 0
    stubs = 0
    substantial = 0

    for p in current:
        file = p["file"]
        path = PAGES_DIR / file
        lines = _count_lines(path)
        tabs = _count_tabs(path)
        engines = _engine_imports(path)
        is_stub = lines < STUB_LINE_THRESHOLD and tabs < STUB_TAB_THRESHOLD
        if is_stub:
            stubs += 1
        else:
            substantial += 1
        total_lines += lines
        stats.append(PageStats(
            file=file, title=p["title"],
            line_count=lines, tab_count=tabs,
            engine_imports=engines, is_stub=is_stub,
        ))

    avg = total_lines / len(stats) if stats else 0.0

    return PageCompletenessAudit(
        pages=stats,
        stub_count=stubs,
        substantial_count=substantial,
        avg_lines_per_page=round(avg, 1),
        total_lines=total_lines,
        timestamp=datetime.now().isoformat(),
    )


def audit_engine_wiring() -> EngineWiringAudit:
    """Audit which HR-domain engines are wired into pages."""
    # Build set of engines imported across all pages
    page_engine_uses: Dict[str, List[str]] = {}  # engine -> pages
    for p in PAGES_DIR.glob("[0-9]*.py"):
        imports = _engine_imports(p)
        for imp in imports:
            page_engine_uses.setdefault(imp, []).append(p.name)

    wired: List[Dict[str, Any]] = []
    unwired: List[Dict[str, Any]] = []

    for eng, meta in HR_DOMAIN_ENGINES.items():
        in_pages = page_engine_uses.get(eng, [])
        if in_pages:
            wired.append({
                "engine": eng,
                "std": meta["std"],
                "name": meta["name"],
                "in_pages": in_pages,
            })
        else:
            unwired.append({
                "engine": eng,
                "std": meta["std"],
                "name": meta["name"],
                "page_target": meta["page_target"],
            })

    pct = (
        len(wired) / len(HR_DOMAIN_ENGINES) * 100
        if HR_DOMAIN_ENGINES else 0.0
    )

    return EngineWiringAudit(
        total_hr_engines=len(HR_DOMAIN_ENGINES),
        wired_engines=wired,
        unwired_engines=unwired,
        wiring_coverage_pct=round(pct, 1),
        timestamp=datetime.now().isoformat(),
    )


def audit_react_readiness() -> ReactReadinessAudit:
    """Per-engine: zero streamlit imports + dataclass usage."""
    with_streamlit: List[str] = []
    no_dataclasses: List[str] = []
    ready = 0

    for eng in HR_DOMAIN_ENGINES:
        p = UTILS_DIR / f"{eng}.py"
        if not p.exists():
            with_streamlit.append(f"{eng} (missing file)")
            continue
        has_st = _has_streamlit_imports(p)
        has_dc = _has_dataclasses(p)
        if has_st:
            with_streamlit.append(eng)
        if not has_dc:
            no_dataclasses.append(eng)
        if not has_st and has_dc:
            ready += 1

    pct = ready / len(HR_DOMAIN_ENGINES) * 100 if HR_DOMAIN_ENGINES else 0.0

    return ReactReadinessAudit(
        engines_checked=len(HR_DOMAIN_ENGINES),
        react_ready_count=ready,
        engines_with_streamlit=with_streamlit,
        engines_without_dataclasses=no_dataclasses,
        react_readiness_pct=round(pct, 1),
        timestamp=datetime.now().isoformat(),
    )


def audit_api_coverage() -> APICoverageAudit:
    """Per-engine: how many FastAPI endpoints in api.py."""
    with_api: List[str] = []
    without_api: List[Dict[str, str]] = []
    endpoint_counts: Dict[str, int] = {}

    for eng, meta in HR_DOMAIN_ENGINES.items():
        count = _api_endpoint_count_for(eng)
        endpoint_counts[eng] = count
        if count > 0:
            with_api.append(eng)
        else:
            without_api.append({
                "engine": eng,
                "std": meta["std"],
                "name": meta["name"],
            })

    pct = (
        len(with_api) / len(HR_DOMAIN_ENGINES) * 100
        if HR_DOMAIN_ENGINES else 0.0
    )

    return APICoverageAudit(
        total_engines=len(HR_DOMAIN_ENGINES),
        engines_with_api=with_api,
        engines_without_api=without_api,
        api_coverage_pct=round(pct, 1),
        endpoint_count_by_engine=endpoint_counts,
        timestamp=datetime.now().isoformat(),
    )


def audit_data_backing() -> DataBackingAudit:
    """Per-engine: JSON / Excel / PostgreSQL data source."""
    engines: List[Dict[str, Any]] = []
    pg = 0
    json_only = 0
    excel = 0
    for eng in HR_DOMAIN_ENGINES:
        d = _data_backing_of(eng)
        d["engine"] = eng
        engines.append(d)
        if d.get("uses_postgres"):
            pg += 1
        elif d.get("uses_excel"):
            excel += 1
        elif d.get("uses_json"):
            json_only += 1

    return DataBackingAudit(
        engines=engines,
        pg_ready_count=pg,
        json_only_count=json_only,
        excel_dependent_count=excel,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Master rollup
# ════════════════════════════════════════════════════════════════════

def hr_full_audit() -> HRFullAudit:
    """Run all 6 audits + compute HR health %."""
    mp = audit_module_placement()
    pc = audit_page_completeness()
    ew = audit_engine_wiring()
    rr = audit_react_readiness()
    api = audit_api_coverage()
    db = audit_data_backing()

    # Health calculation: 6 dimensions, each 0-100
    placement_score = 100.0 if not mp.misplaced_in_hr else max(
        0, 100 - 25 * len(mp.misplaced_in_hr),
    )
    completeness_score = (
        pc.substantial_count / max(1, len(pc.pages)) * 100
    )
    wiring_score = ew.wiring_coverage_pct
    react_score = rr.react_readiness_pct
    api_score = api.api_coverage_pct
    backing_score = (
        (db.pg_ready_count + db.json_only_count) / max(1, len(db.engines)) * 100
    )

    health = (
        placement_score + completeness_score + wiring_score
        + react_score + api_score + backing_score
    ) / 6

    # Severity counts
    severity: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0}
    if pc.stub_count >= 3:
        severity["critical"] += 1
    if mp.misplaced_in_hr:
        severity["high"] += 1
    if ew.wiring_coverage_pct < 50:
        severity["critical"] += 1
    if api.api_coverage_pct < 30:
        severity["high"] += 1

    # Rescue priorities (ordered actions)
    priorities: List[str] = []
    if mp.misplaced_in_hr:
        priorities.append(
            f"Move {len(mp.misplaced_in_hr)} misplaced page(s) out of HR: "
            f"{[m['file'] for m in mp.misplaced_in_hr]}"
        )
    if ew.unwired_engines:
        priorities.append(
            f"Wire {len(ew.unwired_engines)} HR engines into pages: "
            f"{[u['engine'] for u in ew.unwired_engines[:5]]}"
        )
    if pc.stub_count > 0:
        stub_files = [p.file for p in pc.pages if p.is_stub]
        priorities.append(
            f"Build out {pc.stub_count} stub page(s): {stub_files}"
        )
    if api.api_coverage_pct < 100:
        priorities.append(
            f"Add API endpoints for {len(api.engines_without_api)} engines"
        )
    if mp.should_be_in_hr_but_arent:
        priorities.append(
            f"Create HR pages for: {mp.should_be_in_hr_but_arent}"
        )

    return HRFullAudit(
        module_placement=mp,
        page_completeness=pc,
        engine_wiring=ew,
        react_readiness=rr,
        api_coverage=api,
        data_backing=db,
        hr_health_pct=round(health, 1),
        severity_counts=severity,
        rescue_priorities=priorities,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ hr_section_audit_engine self-test ─")

    # Zero streamlit
    text = Path(__file__).read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports")

    # Module placement
    mp = audit_module_placement()
    print(f"\n  Module placement:")
    print(f"    Pages currently in HR: {len(mp.pages_currently_in_hr)}")
    print(f"    Correctly placed:      {len(mp.correctly_placed)}: {mp.correctly_placed}")
    print(f"    Misplaced in HR:       {len(mp.misplaced_in_hr)}: "
          f"{[m['file'] for m in mp.misplaced_in_hr]}")
    print(f"    Should be in HR:       {len(mp.should_be_in_hr_but_arent)}")

    # Page completeness
    pc = audit_page_completeness()
    print(f"\n  Page completeness:")
    print(f"    Total pages:       {len(pc.pages)}")
    print(f"    Stubs (<200 lines, <2 tabs): {pc.stub_count}")
    print(f"    Substantial:       {pc.substantial_count}")
    print(f"    Avg lines/page:    {pc.avg_lines_per_page}")
    for p in pc.pages:
        marker = "⚠️ STUB" if p.is_stub else "✓"
        print(f"      {marker:6} {p.file:25} {p.line_count:5} lines, "
              f"{p.tab_count} tabs, {len(p.engine_imports)} engines")

    # Engine wiring
    ew = audit_engine_wiring()
    print(f"\n  Engine wiring:")
    print(f"    Total HR engines:  {ew.total_hr_engines}")
    print(f"    Wired into pages:  {len(ew.wired_engines)}")
    print(f"    Unwired:           {len(ew.unwired_engines)}")
    print(f"    Coverage:          {ew.wiring_coverage_pct}%")
    if ew.unwired_engines:
        print(f"    Unwired list:")
        for u in ew.unwired_engines:
            print(f"      • {u['engine']:30} {u['std']:8} {u['name']}")

    # React readiness
    rr = audit_react_readiness()
    print(f"\n  REACT readiness:")
    print(f"    Ready:             {rr.react_ready_count}/{rr.engines_checked} ({rr.react_readiness_pct}%)")
    if rr.engines_with_streamlit:
        print(f"    Has streamlit:     {rr.engines_with_streamlit}")
    if rr.engines_without_dataclasses:
        print(f"    No @dataclass:     {rr.engines_without_dataclasses}")

    # API coverage
    api = audit_api_coverage()
    print(f"\n  API coverage:")
    print(f"    With API endpoints: {len(api.engines_with_api)}/{api.total_engines} ({api.api_coverage_pct}%)")
    if api.engines_without_api:
        for e in api.engines_without_api:
            print(f"      • {e['engine']:30} {e['std']:8} {e['name']}")

    # Data backing
    db = audit_data_backing()
    print(f"\n  Data backing:")
    print(f"    PostgreSQL-ready:  {db.pg_ready_count}")
    print(f"    JSON-only:         {db.json_only_count}")
    print(f"    Excel-dependent:   {db.excel_dependent_count}")

    # Master
    full = hr_full_audit()
    print(f"\n  ═══ HR HEALTH: {full.hr_health_pct}% ═══")
    print(f"  Severity: {full.severity_counts}")
    print(f"  Rescue priorities:")
    for i, p in enumerate(full.rescue_priorities, 1):
        print(f"    {i}. {p}")

    # JSON
    json.dumps(full.to_dict())
    print(f"\n  ✓ JSON-serializable")

    print("\n✓ self_test passed")


if __name__ == "__main__":
    self_test()
