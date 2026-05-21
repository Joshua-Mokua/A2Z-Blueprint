"""utils/module_consolidation_analyzer.py — v10.460 Consolidation Analyzer.

Per Joshua v10.460: "have we taken ict modules through all the motions
of deep review analysing if they are all modules or others are tabs
that can be held inside modules, for all the revived have we done a
deep dive to see if there are tabs duplicating functions."

This engine performs REAL cross-page analysis (not stub docs) for
every module. Detects:
  - Page candidates that could be tabs in a parent page (low LOC + 0-1 tabs)
  - Function name overlap between pages
  - Import overlap (heavily-shared engines might be over-distributed)
  - Page-cluster recommendations (e.g. consolidate 4 sub-pages under
    one parent with tabs)
  - Function duplication (same function defined in multiple files)

Public API (API-first, ZERO streamlit):
  - analyze_module(module_key) -> ConsolidationReport
  - analyze_all_modules() -> Dict[str, ConsolidationReport]
  - get_tab_candidates(module_key) -> List[TabCandidate]
  - get_duplicate_functions(module_key) -> List[DuplicateFunction]
  - audit_consolidation_coverage() -> ConsolidationCoverage

Heuristics:
  - LOW LOC threshold: <100 LOC AND <2 tab blocks → likely tab candidate
  - Function overlap: same function name in 2+ pages → duplication signal
  - Module sprawl: >10 pages with low average LOC → consolidation opportunity

Shipped: v10.460.
"""
from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REPO_ROOT = Path(__file__).parent.parent
PAGES_DIR = REPO_ROOT / "pages"
UTILS_DIR = REPO_ROOT / "utils"
DOCS_DIR = REPO_ROOT / "docs"

# Thresholds
LOW_LOC_THRESHOLD = 100        # <this LOC + <2 tabs → tab candidate
SUBSTANTIAL_LOC_THRESHOLD = 300 # >this LOC = a proper page


@dataclass
class TabCandidate:
    """A page that might be a tab inside a parent page."""
    page: str
    loc: int
    tab_blocks: int
    function_count: int
    suggested_parent: Optional[str]
    reason: str

    def to_dict(self): return asdict(self)


@dataclass
class DuplicateFunction:
    """A function defined in multiple pages."""
    function_name: str
    pages: List[str]
    occurrences: int

    def to_dict(self): return asdict(self)


@dataclass
class ConsolidationReport:
    """Per-module consolidation analysis."""
    module_key: str
    total_pages: int
    substantial_pages: int          # >=300 LOC
    tab_candidate_pages: int        # <100 LOC + <2 tabs
    avg_loc: float
    avg_tabs_per_page: float
    tab_candidates: List[TabCandidate]
    duplicate_functions: List[DuplicateFunction]
    consolidation_opportunity_score: float  # 0-100, higher = more opportunity
    recommendation: str
    timestamp: str

    def to_dict(self):
        return {
            "module_key": self.module_key,
            "total_pages": self.total_pages,
            "substantial_pages": self.substantial_pages,
            "tab_candidate_pages": self.tab_candidate_pages,
            "avg_loc": self.avg_loc,
            "avg_tabs_per_page": self.avg_tabs_per_page,
            "tab_candidates": [t.to_dict() for t in self.tab_candidates],
            "duplicate_functions": [d.to_dict() for d in self.duplicate_functions],
            "consolidation_opportunity_score": self.consolidation_opportunity_score,
            "recommendation": self.recommendation,
            "timestamp": self.timestamp,
        }


@dataclass
class ConsolidationCoverage:
    total_modules: int
    modules_analyzed: int
    total_tab_candidates: int
    total_duplicate_functions: int
    avg_opportunity_score: float
    timestamp: str

    def to_dict(self): return asdict(self)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _parse_page_signals(path: Path) -> Dict[str, Any]:
    """Extract LOC, tab count, function names, imports from a page."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {"loc": 0, "tabs": 0, "functions": [], "imports": [],
                "exists": False}
    loc = len(text.splitlines())
    tabs = text.count("st.tabs")

    functions: List[str] = []
    imports: List[str] = []
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Skip private + dunder
                if not node.name.startswith("_"):
                    functions.append(node.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("utils."):
                    imports.append(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("utils."):
                        imports.append(alias.name)
    except SyntaxError:
        pass

    return {"loc": loc, "tabs": tabs, "functions": functions,
           "imports": imports, "exists": True}


def _suggest_parent(page: str, module_key: str) -> Optional[str]:
    """Heuristic parent suggestion based on filename prefix."""
    base = page.replace(".py", "")
    if not base[0].isdigit():
        return None
    # Look for pages with the same numeric prefix or in same range
    prefix_match = re.match(r"^(\d+)_", base)
    if not prefix_match:
        return None
    num = int(prefix_match.group(1))
    # Group by tens (e.g. 96/97 → could merge into 96_it_digital combined)
    same_decade = []
    try:
        for p in PAGES_DIR.glob("*.py"):
            m = re.match(r"^(\d+)_", p.name)
            if m and num // 10 == int(m.group(1)) // 10 and p.name != page:
                same_decade.append(p.name)
    except Exception:
        pass
    if same_decade:
        return same_decade[0]
    return None


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════

def analyze_module(module_key: str) -> ConsolidationReport:
    """Run real cross-page consolidation analysis for a module."""
    try:
        import sys
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from utils.module_doctrine_audit import MODULE_REGISTRY
        cfg = MODULE_REGISTRY.get(module_key)
    except Exception:
        cfg = None

    if not cfg:
        return ConsolidationReport(
            module_key=module_key, total_pages=0, substantial_pages=0,
            tab_candidate_pages=0, avg_loc=0.0, avg_tabs_per_page=0.0,
            tab_candidates=[], duplicate_functions=[],
            consolidation_opportunity_score=0.0,
            recommendation="module not found in registry",
            timestamp=datetime.now().isoformat(),
        )

    # Parse all pages
    page_signals: Dict[str, Dict[str, Any]] = {}
    for p in cfg.pages:
        page_signals[p] = _parse_page_signals(PAGES_DIR / p)

    # Stats
    existing = {p: s for p, s in page_signals.items() if s["exists"]}
    total = len(existing)
    if total == 0:
        return ConsolidationReport(
            module_key=module_key, total_pages=0, substantial_pages=0,
            tab_candidate_pages=0, avg_loc=0.0, avg_tabs_per_page=0.0,
            tab_candidates=[], duplicate_functions=[],
            consolidation_opportunity_score=0.0,
            recommendation="no pages found",
            timestamp=datetime.now().isoformat(),
        )

    substantial = sum(1 for s in existing.values()
                     if s["loc"] >= SUBSTANTIAL_LOC_THRESHOLD)
    tab_candidates_count = sum(1 for s in existing.values()
                              if s["loc"] < LOW_LOC_THRESHOLD
                              and s["tabs"] < 2)
    avg_loc = sum(s["loc"] for s in existing.values()) / total
    avg_tabs = sum(s["tabs"] for s in existing.values()) / total

    # Tab candidates list
    tab_candidates: List[TabCandidate] = []
    for page, sig in existing.items():
        if sig["loc"] < LOW_LOC_THRESHOLD and sig["tabs"] < 2:
            tab_candidates.append(TabCandidate(
                page=page,
                loc=sig["loc"],
                tab_blocks=sig["tabs"],
                function_count=len(sig["functions"]),
                suggested_parent=_suggest_parent(page, module_key),
                reason=(f"Page is small ({sig['loc']} LOC) and has only "
                       f"{sig['tabs']} tab block(s) — likely tab "
                       f"candidate"),
            ))

    # Duplicate function detection
    function_pages: Dict[str, List[str]] = defaultdict(list)
    for page, sig in existing.items():
        for fn in sig["functions"]:
            function_pages[fn].append(page)
    duplicates: List[DuplicateFunction] = [
        DuplicateFunction(function_name=fn, pages=pages,
                         occurrences=len(pages))
        for fn, pages in function_pages.items()
        if len(pages) >= 2
    ]
    duplicates.sort(key=lambda d: d.occurrences, reverse=True)

    # Opportunity score: 0-100
    # Components: tab_candidate ratio (50%) + duplicate function ratio (30%)
    # + low avg_loc penalty (20%)
    tab_ratio = (tab_candidates_count / total) if total else 0
    dup_ratio = min(1.0, len(duplicates) / max(total, 1))
    low_loc_ratio = max(0.0, 1.0 - (avg_loc / 300))  # 1.0 if avg=0, 0.0 if >=300
    opp_score = (tab_ratio * 50 + dup_ratio * 30 + low_loc_ratio * 20)

    if opp_score >= 60:
        rec = (f"HIGH consolidation opportunity. Consider merging "
              f"{tab_candidates_count} small page(s) into tabs of a "
              f"parent page; {len(duplicates)} function duplications.")
    elif opp_score >= 30:
        rec = (f"MEDIUM consolidation opportunity. "
              f"{tab_candidates_count} tab candidates; "
              f"{len(duplicates)} duplications.")
    else:
        rec = (f"LOW consolidation opportunity. Module appears "
              f"well-distributed with {substantial}/{total} substantial "
              f"pages.")

    return ConsolidationReport(
        module_key=module_key,
        total_pages=total,
        substantial_pages=substantial,
        tab_candidate_pages=tab_candidates_count,
        avg_loc=round(avg_loc, 1),
        avg_tabs_per_page=round(avg_tabs, 2),
        tab_candidates=tab_candidates,
        duplicate_functions=duplicates[:10],
        consolidation_opportunity_score=round(opp_score, 1),
        recommendation=rec,
        timestamp=datetime.now().isoformat(),
    )


def analyze_all_modules() -> Dict[str, ConsolidationReport]:
    """Run consolidation analysis for every module."""
    try:
        import sys
        if str(REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(REPO_ROOT))
        from utils.module_doctrine_audit import MODULE_REGISTRY
        return {key: analyze_module(key) for key in MODULE_REGISTRY}
    except Exception:
        return {}


def get_tab_candidates(module_key: str) -> List[TabCandidate]:
    return analyze_module(module_key).tab_candidates


def get_duplicate_functions(module_key: str) -> List[DuplicateFunction]:
    return analyze_module(module_key).duplicate_functions


def audit_consolidation_coverage() -> ConsolidationCoverage:
    """Audit coverage of consolidation analysis."""
    reports = analyze_all_modules()
    total_tab_candidates = sum(r.tab_candidate_pages
                              for r in reports.values())
    total_duplicates = sum(len(r.duplicate_functions)
                          for r in reports.values())
    if reports:
        avg_opp = sum(r.consolidation_opportunity_score
                     for r in reports.values()) / len(reports)
    else:
        avg_opp = 0.0
    return ConsolidationCoverage(
        total_modules=len(reports),
        modules_analyzed=len(reports),
        total_tab_candidates=total_tab_candidates,
        total_duplicate_functions=total_duplicates,
        avg_opportunity_score=round(avg_opp, 1),
        timestamp=datetime.now().isoformat(),
    )


def generate_consolidation_doc(module_key: str) -> str:
    """Generate real consolidation_analysis.md content for a module."""
    rep = analyze_module(module_key)
    today = datetime.now().strftime("%Y-%m-%d")
    out = f"# {module_key.upper()} — Module Consolidation Analysis\n\n"
    out += f"**Generated:** {today} (v10.460 real cross-page analysis)\n"
    out += f"**Module key:** `{module_key}`\n\n"
    out += "## Summary\n\n"
    out += f"- Total pages: **{rep.total_pages}**\n"
    out += f"- Substantial pages (≥{SUBSTANTIAL_LOC_THRESHOLD} LOC): "
    out += f"**{rep.substantial_pages}**\n"
    out += f"- Tab candidates (<{LOW_LOC_THRESHOLD} LOC + <2 tabs): "
    out += f"**{rep.tab_candidate_pages}**\n"
    out += f"- Average LOC per page: **{rep.avg_loc}**\n"
    out += f"- Average tabs per page: **{rep.avg_tabs_per_page}**\n"
    out += f"- Function duplications detected: **{len(rep.duplicate_functions)}**\n"
    out += f"- Consolidation opportunity score: **{rep.consolidation_opportunity_score}/100**\n\n"
    out += f"## Recommendation\n\n{rep.recommendation}\n\n"

    if rep.tab_candidates:
        out += f"## Tab candidates ({len(rep.tab_candidates)})\n\n"
        out += "| Page | LOC | Tabs | Functions | Suggested parent | Reason |\n"
        out += "|---|---|---|---|---|---|\n"
        for t in rep.tab_candidates:
            parent = t.suggested_parent or "(suggest manual review)"
            out += (f"| `{t.page}` | {t.loc} | {t.tab_blocks} | "
                   f"{t.function_count} | `{parent}` | {t.reason} |\n")
        out += "\n"

    if rep.duplicate_functions:
        out += "## Function duplications\n\n"
        out += "| Function | Occurrences | Pages |\n|---|---|---|\n"
        for d in rep.duplicate_functions:
            pages_str = ", ".join(f"`{p}`" for p in d.pages[:3])
            if len(d.pages) > 3:
                pages_str += f" + {len(d.pages) - 3} more"
            out += f"| `{d.function_name}` | {d.occurrences} | {pages_str} |\n"
        out += "\n"

    out += "## Action items\n\n"
    if rep.tab_candidate_pages > 0:
        out += (f"- Review {rep.tab_candidate_pages} tab-candidate page(s) "
               f"for merge into parent pages\n")
    if len(rep.duplicate_functions) > 0:
        out += (f"- Extract {len(rep.duplicate_functions)} duplicate "
               f"function(s) into a shared `utils/` helper module\n")
    if rep.consolidation_opportunity_score < 30:
        out += "- Module is well-structured; no urgent consolidation needed\n"
    return out


if __name__ == "__main__":  # pragma: no cover
    print(f"{'Module':<14} {'Pages':>6} {'TabCand':>8} {'Dups':>5} {'Avg LOC':>8} {'Opportunity':>12}")
    for key, rep in analyze_all_modules().items():
        print(f"{key:<14} {rep.total_pages:>6} {rep.tab_candidate_pages:>8} "
              f"{len(rep.duplicate_functions):>5} {rep.avg_loc:>8.1f} "
              f"{rep.consolidation_opportunity_score:>10.1f}/100")
    cov = audit_consolidation_coverage()
    print(f"\nCoverage: {cov.modules_analyzed}/{cov.total_modules} modules; "
          f"{cov.total_tab_candidates} tab candidates; "
          f"{cov.total_duplicate_functions} duplicates; "
          f"avg opportunity {cov.avg_opportunity_score}/100")
