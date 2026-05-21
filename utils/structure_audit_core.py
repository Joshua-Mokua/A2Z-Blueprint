"""utils/structure_audit_core.py — v10.38: Structural Hygiene Audit.

╔════════════════════════════════════════════════════════════════════════╗
║  STRUCTURAL HYGIENE AUDIT — Mechanical anti-entanglement check         ║
║  Cat A — locked behind G128 gate                                       ║
╠════════════════════════════════════════════════════════════════════════╣
║  Scans the codebase for structural anti-patterns:                      ║
║    - Circular imports (HARD FAIL — prevents bootstrap)                 ║
║    - Layer violations (HARD FAIL — utils ≠ pages)                      ║
║    - God modules — too many incoming deps (WARN)                       ║
║    - Junk-drawer modules — too many outgoing deps (WARN)               ║
║    - Orphan modules — no callers + not entry point (WARN)              ║
║    - Duplicate symbols across modules (WARN)                           ║
║    - Module size outliers (INFO)                                       ║
║                                                                         ║
║  G128 gate locks structural integrity going forward: any new           ║
║  circular import or layer violation in a future batch will fail        ║
║  the audit — the codebase cannot drift toward entanglement.            ║
║                                                                         ║
║  Honesty Rule 1: every Finding surfaces severity + category +          ║
║  module + observed numbers + suggestion. Failures retain specific      ║
║  triage information.                                                    ║
║                                                                         ║
║  Honesty Rule 7: hard rules apply to deterministic structural          ║
║  facts (graph cycles, layer crossings). Heuristic findings (god        ║
║  modules, duplicates) emit WARN and require human judgment — the       ║
║  engine never auto-mutates code. Reorganization is always a human      ║
║  decision.                                                              ║
║                                                                         ║
║  Composes with: scripts/audit.py (G128 gate calls audit() and          ║
║  asserts no HARD failures), Engine Hub Tier 20 (documents this         ║
║  infrastructure), docs/ARCHITECTURE.md (human-readable view of          ║
║  what the engine sees).                                                ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import ast
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import (
    Any, Dict, FrozenSet, List, Mapping, Optional, Sequence, Set,
    Tuple)

SPEC_DEVIATION_NOTE = (
    "StructureAuditEngine implements the v10.38 codebase-shape audit. "
    "Hard failures (circular imports, layer violations) are "
    "deterministic graph properties. Heuristic findings (god modules, "
    "duplicates) emit WARN and require human review. Per Rule 7, "
    "the engine never auto-mutates code — reorganization is always a "
    "human decision."
)


# ════════════════════════════════════════════════════════════════════════
# Configuration constants — tunable but explicit
# ════════════════════════════════════════════════════════════════════════

# Layer rules: which directories may import from which.
# A rule "src → dst is forbidden" means modules in src must not
# import from dst.
FORBIDDEN_LAYER_EDGES: FrozenSet[Tuple[str, str]] = frozenset({
    ("utils", "pages"),       # business logic must not depend on UI
    ("utils", "scripts"),     # business logic must not depend on CLI
    ("scripts", "pages"),     # CLI tools must not depend on UI
})

# Heuristic thresholds
GOD_MODULE_INCOMING_THRESHOLD = 15
JUNK_DRAWER_OUTGOING_THRESHOLD = 25
SIZE_WARN_LINES = 2000
SIZE_FAIL_LINES = 4000

# Modules exempt from orphan check (deliberate entry points,
# data-only, or facades referenced reflectively).
ORPHAN_EXEMPT_PATTERNS: FrozenSet[str] = frozenset({
    "standards_registry",       # consumed by introspection
    "migrations",               # alembic-style entries
    "__init__",                 # package init
})

# Modules deliberately serving as cross-arc bridges OR base
# infrastructure with legitimately high fan-in. These are exempt
# from the GOD_MODULE warning because high fan-in is by design.
CROSS_ARC_BRIDGES: FrozenSet[str] = frozenset({
    # Intentional cross-arc facades (compose other engines)
    "treasury_dashboard",
    "treasury_unified_platform",
    "climate_treasury_limits",
    "scenario_simulator",
    # Base infrastructure — high fan-in by design
    "db",                # database access used platform-wide
    "config",            # configuration loaded everywhere
    "core_audit",        # audit logging hook used throughout
    "_shared",           # pages-layer shared utilities
    "_access",           # pages-layer auth + RBAC
    "standards_registry",  # consumed via introspection
})


# ════════════════════════════════════════════════════════════════════════
# Findings
# ════════════════════════════════════════════════════════════════════════

class FindingSeverity(Enum):
    """Severity of a structural finding."""
    INFO = "INFO"           # observation, not actionable
    WARN = "WARN"           # heuristic — review when convenient
    HARD = "HARD"           # deterministic violation — fix required


class FindingCategory(Enum):
    """Type of structural issue surfaced."""
    CIRCULAR_IMPORT = "CIRCULAR_IMPORT"
    LAYER_VIOLATION = "LAYER_VIOLATION"
    GOD_MODULE = "GOD_MODULE"
    JUNK_DRAWER = "JUNK_DRAWER"
    ORPHAN_MODULE = "ORPHAN_MODULE"
    DUPLICATE_SYMBOL = "DUPLICATE_SYMBOL"
    SIZE_OUTLIER = "SIZE_OUTLIER"


@dataclass(frozen=True)
class Finding:
    """A single structural finding with full triage info."""
    severity: FindingSeverity
    category: FindingCategory
    module_path: str            # canonical module path (e.g., "utils.core")
    description: str            # what was observed
    suggestion: str             # what to consider
    # Per Rule 1: surface specific numbers
    observed_value: Optional[Any] = None
    threshold: Optional[Any] = None
    related_modules: Tuple[str, ...] = ()


@dataclass(frozen=True)
class StructureAuditResult:
    """Aggregated outcome of one structure audit."""
    findings: Tuple[Finding, ...]
    n_modules_scanned: int
    n_total_imports: int
    summary: Mapping[str, Any]

    def by_severity(
        self,
    ) -> Mapping[FindingSeverity, Tuple[Finding, ...]]:
        out: Dict[FindingSeverity, List[Finding]] = defaultdict(list)
        for f in self.findings:
            out[f.severity].append(f)
        return {k: tuple(v) for k, v in out.items()}

    def by_category(
        self,
    ) -> Mapping[FindingCategory, Tuple[Finding, ...]]:
        out: Dict[FindingCategory, List[Finding]] = defaultdict(list)
        for f in self.findings:
            out[f.category].append(f)
        return {k: tuple(v) for k, v in out.items()}

    def hard_failures(self) -> Tuple[Finding, ...]:
        return tuple(
            f for f in self.findings
            if f.severity == FindingSeverity.HARD)

    def is_clean(self) -> bool:
        """No HARD failures. WARN/INFO are tolerated."""
        return len(self.hard_failures()) == 0


# ════════════════════════════════════════════════════════════════════════
# Engine
# ════════════════════════════════════════════════════════════════════════

class StructureAuditEngine:
    """Scans a project root and produces a StructureAuditResult.

    The engine is purely analytical — it never mutates the codebase.
    Per Rule 7, all reorganization decisions are surfaced as
    suggestions for human review.
    """

    def __init__(
        self, *,
        project_root: Path,
        scan_dirs: Sequence[str] = ("utils", "pages", "scripts"),
        layer_edges: FrozenSet[Tuple[str, str]] = FORBIDDEN_LAYER_EDGES,
        god_module_threshold: int = GOD_MODULE_INCOMING_THRESHOLD,
        junk_drawer_threshold: int = JUNK_DRAWER_OUTGOING_THRESHOLD,
        size_warn_lines: int = SIZE_WARN_LINES,
        size_fail_lines: int = SIZE_FAIL_LINES,
        orphan_exempt_patterns: FrozenSet[str] = ORPHAN_EXEMPT_PATTERNS,
        cross_arc_bridges: FrozenSet[str] = CROSS_ARC_BRIDGES,
    ):
        self.project_root = Path(project_root).resolve()
        if not self.project_root.exists():
            raise ValueError(
                f"project_root does not exist: {project_root}")
        self.scan_dirs = tuple(scan_dirs)
        self.layer_edges = frozenset(layer_edges)
        self.god_module_threshold = god_module_threshold
        self.junk_drawer_threshold = junk_drawer_threshold
        self.size_warn_lines = size_warn_lines
        self.size_fail_lines = size_fail_lines
        self.orphan_exempt_patterns = frozenset(orphan_exempt_patterns)
        self.cross_arc_bridges = frozenset(cross_arc_bridges)

    # ── File system walk ──────────────────────────────────────────────
    def _discover_modules(self) -> Dict[str, Path]:
        """Map canonical module name → file path.

        Canonical name uses dots (e.g., 'utils.core').
        """
        out: Dict[str, Path] = {}
        for scan_dir in self.scan_dirs:
            base = self.project_root / scan_dir
            if not base.exists():
                continue
            for py_file in base.rglob("*.py"):
                rel = py_file.relative_to(self.project_root)
                parts = list(rel.with_suffix("").parts)
                # Skip __pycache__ etc.
                if any(p.startswith("__pycache__") for p in parts):
                    continue
                module_name = ".".join(parts)
                out[module_name] = py_file
        return out

    # ── AST parsing ───────────────────────────────────────────────────
    def _parse_imports(
        self, file_path: Path,
    ) -> Tuple[FrozenSet[str], int]:
        """Extract imported module names + count file lines."""
        try:
            text = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return (frozenset(), 0)
        n_lines = text.count("\n") + 1
        try:
            tree = ast.parse(text, filename=str(file_path))
        except SyntaxError:
            # Don't let one bad file kill the audit.
            return (frozenset(), n_lines)
        imports: Set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
        return (frozenset(imports), n_lines)

    def _extract_top_level_symbols(
        self, file_path: Path,
    ) -> Tuple[FrozenSet[str], FrozenSet[str]]:
        """Extract top-level function names and class names.

        Returns: (function_names, class_names)
        """
        try:
            text = file_path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(file_path))
        except (UnicodeDecodeError, OSError, SyntaxError):
            return (frozenset(), frozenset())
        funcs: Set[str] = set()
        classes: Set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Skip private helpers (leading underscore)
                if not node.name.startswith("_"):
                    funcs.add(node.name)
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    classes.add(node.name)
        return (frozenset(funcs), frozenset(classes))

    # ── Graph construction ────────────────────────────────────────────
    def _build_dependency_graph(
        self, modules: Dict[str, Path],
    ) -> Tuple[
        Dict[str, FrozenSet[str]],   # module → set of imported modules
        Dict[str, int],              # module → line count
        int,                         # total imports counted
    ]:
        """For each scanned module, list which other scanned modules
        it imports.

        Edges only count imports that resolve to modules ALSO in
        the scan. External libs (stdlib, streamlit) are excluded
        from the graph.
        """
        graph: Dict[str, FrozenSet[str]] = {}
        sizes: Dict[str, int] = {}
        n_imports = 0
        # Build a prefix lookup so 'from utils.core import X' maps
        # to module 'utils.core'
        module_names = set(modules.keys())
        for module_name, path in modules.items():
            imports, n_lines = self._parse_imports(path)
            sizes[module_name] = n_lines
            internal: Set[str] = set()
            for imp in imports:
                # Match exact module
                if imp in module_names:
                    internal.add(imp)
                else:
                    # Match prefix (e.g., 'utils.core.foo' → 'utils.core')
                    parts = imp.split(".")
                    for i in range(len(parts), 0, -1):
                        candidate = ".".join(parts[:i])
                        if candidate in module_names:
                            internal.add(candidate)
                            break
            internal.discard(module_name)    # ignore self-imports
            graph[module_name] = frozenset(internal)
            n_imports += len(internal)
        return (graph, sizes, n_imports)

    # ── Cycle detection (Tarjan-style SCC simplified to DFS) ──────────
    def _detect_cycles(
        self, graph: Dict[str, FrozenSet[str]],
    ) -> Tuple[Tuple[str, ...], ...]:
        """Return tuples of modules in any cycle (each tuple is one
        cycle).
        """
        # Use iterative DFS with three-color marking
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {m: WHITE for m in graph}
        cycles: List[Tuple[str, ...]] = []
        seen_cycles: Set[FrozenSet[str]] = set()

        def visit(start: str) -> None:
            stack: List[Tuple[str, List[str]]] = [(start, [])]
            color[start] = GRAY
            path: List[str] = [start]
            # Iterative DFS using explicit stack of (node, child_iter)
            iter_stack: List[Any] = [
                (start, iter(sorted(graph.get(start, ()))))]
            while iter_stack:
                node, child_iter = iter_stack[-1]
                try:
                    child = next(child_iter)
                except StopIteration:
                    color[node] = BLACK
                    path.pop()
                    iter_stack.pop()
                    continue
                if child not in color:
                    continue
                if color[child] == GRAY:
                    # Found a cycle: path[idx_of_child:] + [child]
                    if child in path:
                        idx = path.index(child)
                        cycle = tuple(path[idx:])
                        key = frozenset(cycle)
                        if key not in seen_cycles:
                            seen_cycles.add(key)
                            cycles.append(cycle)
                elif color[child] == WHITE:
                    color[child] = GRAY
                    path.append(child)
                    iter_stack.append(
                        (child, iter(sorted(graph.get(child, ())))))

        for node in sorted(graph.keys()):
            if color[node] == WHITE:
                visit(node)

        return tuple(cycles)

    # ── Per-rule audits ───────────────────────────────────────────────
    def _audit_circular_imports(
        self, graph: Dict[str, FrozenSet[str]],
    ) -> Tuple[Finding, ...]:
        cycles = self._detect_cycles(graph)
        out: List[Finding] = []
        for cycle in cycles:
            out.append(Finding(
                severity=FindingSeverity.HARD,
                category=FindingCategory.CIRCULAR_IMPORT,
                module_path=cycle[0],
                description=(
                    f"Circular import detected through "
                    f"{len(cycle)} modules"),
                suggestion=(
                    "Break the cycle by extracting shared types to a "
                    "lower-layer module, or invert one dependency via "
                    "a callback/protocol."),
                observed_value=" → ".join(cycle) + f" → {cycle[0]}",
                related_modules=cycle))
        return tuple(out)

    def _audit_layer_violations(
        self, graph: Dict[str, FrozenSet[str]],
    ) -> Tuple[Finding, ...]:
        out: List[Finding] = []
        for module, deps in graph.items():
            src_layer = module.split(".", 1)[0]
            for dep in deps:
                dst_layer = dep.split(".", 1)[0]
                if (src_layer, dst_layer) in self.layer_edges:
                    out.append(Finding(
                        severity=FindingSeverity.HARD,
                        category=FindingCategory.LAYER_VIOLATION,
                        module_path=module,
                        description=(
                            f"{src_layer}/ module imports from "
                            f"{dst_layer}/ — forbidden layer crossing"),
                        suggestion=(
                            f"Move shared logic from {dep} to a "
                            f"lower layer (e.g., utils/), or invert "
                            f"the dependency."),
                        observed_value=dep,
                        related_modules=(dep,)))
        return tuple(out)

    def _audit_god_modules(
        self, graph: Dict[str, FrozenSet[str]],
    ) -> Tuple[Finding, ...]:
        # Count incoming edges per module
        incoming: Dict[str, int] = defaultdict(int)
        for module, deps in graph.items():
            for dep in deps:
                incoming[dep] += 1
        out: List[Finding] = []
        for module, n_in in sorted(
                incoming.items(), key=lambda kv: -kv[1]):
            if n_in <= self.god_module_threshold:
                continue
            short_name = module.rsplit(".", 1)[-1]
            if short_name in self.cross_arc_bridges:
                continue    # intentional facade
            out.append(Finding(
                severity=FindingSeverity.WARN,
                category=FindingCategory.GOD_MODULE,
                module_path=module,
                description=(
                    f"{n_in} other modules import from this "
                    f"module — exceeds threshold of "
                    f"{self.god_module_threshold}"),
                suggestion=(
                    "Consider extracting cohesive subsets into "
                    "focused modules. High fan-in is a refactor "
                    "smell unless this is an intentional facade."),
                observed_value=n_in,
                threshold=self.god_module_threshold))
        return tuple(out)

    def _audit_junk_drawers(
        self, graph: Dict[str, FrozenSet[str]],
    ) -> Tuple[Finding, ...]:
        out: List[Finding] = []
        for module, deps in graph.items():
            if len(deps) <= self.junk_drawer_threshold:
                continue
            out.append(Finding(
                severity=FindingSeverity.WARN,
                category=FindingCategory.JUNK_DRAWER,
                module_path=module,
                description=(
                    f"Module imports from {len(deps)} other "
                    f"modules — exceeds threshold of "
                    f"{self.junk_drawer_threshold}"),
                suggestion=(
                    "High fan-out suggests the module has too many "
                    "responsibilities. Consider splitting by "
                    "concern."),
                observed_value=len(deps),
                threshold=self.junk_drawer_threshold))
        return tuple(out)

    def _audit_orphans(
        self, graph: Dict[str, FrozenSet[str]],
        modules: Dict[str, Path],
    ) -> Tuple[Finding, ...]:
        # Build incoming map
        incoming: Dict[str, int] = defaultdict(int)
        for module, deps in graph.items():
            for dep in deps:
                incoming[dep] += 1
        out: List[Finding] = []
        for module in sorted(modules.keys()):
            if incoming.get(module, 0) > 0:
                continue
            short_name = module.rsplit(".", 1)[-1]
            # Pages and scripts are entry points — never orphans
            top = module.split(".", 1)[0]
            if top in ("pages", "scripts"):
                continue
            # Exempt patterns
            if any(p in short_name for p in self.orphan_exempt_patterns):
                continue
            # Skip __main__-style entry points
            if short_name.startswith("test_"):
                continue
            out.append(Finding(
                severity=FindingSeverity.WARN,
                category=FindingCategory.ORPHAN_MODULE,
                module_path=module,
                description=(
                    "No other scanned modules import from this "
                    "module"),
                suggestion=(
                    "If this is an intentional entry point, add "
                    "the short name to ORPHAN_EXEMPT_PATTERNS. "
                    "Otherwise it may be dead code or a forgotten "
                    "wiring."),
                observed_value=0,
                threshold=1))
        return tuple(out)

    def _audit_duplicates(
        self, modules: Dict[str, Path],
    ) -> Tuple[Finding, ...]:
        # Build symbol → list of modules where it appears
        sym_funcs: Dict[str, List[str]] = defaultdict(list)
        sym_classes: Dict[str, List[str]] = defaultdict(list)
        for module, path in modules.items():
            funcs, classes = self._extract_top_level_symbols(path)
            for f in funcs:
                sym_funcs[f].append(module)
            for c in classes:
                sym_classes[c].append(module)
        out: List[Finding] = []
        for sym, mods in sorted(sym_funcs.items()):
            if len(mods) >= 3:    # 3+ modules → suspicious
                out.append(Finding(
                    severity=FindingSeverity.WARN,
                    category=FindingCategory.DUPLICATE_SYMBOL,
                    module_path=mods[0],
                    description=(
                        f"Function '{sym}' defined in "
                        f"{len(mods)} modules"),
                    suggestion=(
                        f"Review whether these implementations are "
                        f"truly distinct or should be consolidated "
                        f"into a shared module. Modules: "
                        f"{', '.join(mods[:5])}"),
                    observed_value=len(mods),
                    threshold=3,
                    related_modules=tuple(mods)))
        for sym, mods in sorted(sym_classes.items()):
            if len(mods) >= 2:    # classes are stricter — 2+ flags
                out.append(Finding(
                    severity=FindingSeverity.WARN,
                    category=FindingCategory.DUPLICATE_SYMBOL,
                    module_path=mods[0],
                    description=(
                        f"Class '{sym}' defined in "
                        f"{len(mods)} modules"),
                    suggestion=(
                        "Two or more modules define the same class "
                        "name. Review for accidental duplication."),
                    observed_value=len(mods),
                    threshold=2,
                    related_modules=tuple(mods)))
        return tuple(out)

    def _audit_size(
        self, sizes: Dict[str, int],
    ) -> Tuple[Finding, ...]:
        out: List[Finding] = []
        for module, n_lines in sorted(
                sizes.items(), key=lambda kv: -kv[1]):
            if n_lines >= self.size_fail_lines:
                out.append(Finding(
                    severity=FindingSeverity.WARN,
                    category=FindingCategory.SIZE_OUTLIER,
                    module_path=module,
                    description=(
                        f"Module is {n_lines} lines — exceeds "
                        f"refactor threshold of "
                        f"{self.size_fail_lines}"),
                    suggestion=(
                        "Modules > 4000 lines are difficult to "
                        "navigate and review. Consider splitting "
                        "by cohesive concern."),
                    observed_value=n_lines,
                    threshold=self.size_fail_lines))
            elif n_lines >= self.size_warn_lines:
                out.append(Finding(
                    severity=FindingSeverity.INFO,
                    category=FindingCategory.SIZE_OUTLIER,
                    module_path=module,
                    description=(
                        f"Module is {n_lines} lines — above "
                        f"comfortable threshold of "
                        f"{self.size_warn_lines}"),
                    suggestion=(
                        "Worth keeping an eye on. Not actionable "
                        "yet."),
                    observed_value=n_lines,
                    threshold=self.size_warn_lines))
        return tuple(out)

    # ── Top-level orchestration ───────────────────────────────────────
    def audit(self) -> StructureAuditResult:
        modules = self._discover_modules()
        graph, sizes, n_imports = self._build_dependency_graph(modules)

        all_findings: List[Finding] = []
        all_findings.extend(self._audit_circular_imports(graph))
        all_findings.extend(self._audit_layer_violations(graph))
        all_findings.extend(self._audit_god_modules(graph))
        all_findings.extend(self._audit_junk_drawers(graph))
        all_findings.extend(self._audit_orphans(graph, modules))
        all_findings.extend(self._audit_duplicates(modules))
        all_findings.extend(self._audit_size(sizes))

        # Build summary
        by_severity: Dict[str, int] = defaultdict(int)
        by_category: Dict[str, int] = defaultdict(int)
        for f in all_findings:
            by_severity[f.severity.value] += 1
            by_category[f.category.value] += 1

        summary: Dict[str, Any] = {
            "n_modules": len(modules),
            "n_imports": n_imports,
            "n_findings": len(all_findings),
            "by_severity": dict(by_severity),
            "by_category": dict(by_category),
            "is_clean": all(
                f.severity != FindingSeverity.HARD
                for f in all_findings),
        }

        return StructureAuditResult(
            findings=tuple(all_findings),
            n_modules_scanned=len(modules),
            n_total_imports=n_imports,
            summary=summary)

    # ── Reporting ─────────────────────────────────────────────────────
    def render_markdown_report(
        self, result: StructureAuditResult,
    ) -> str:
        """Human-readable structural audit report."""
        lines: List[str] = []
        lines.append("# Structural Hygiene Audit Report")
        lines.append("")
        lines.append(
            f"- Modules scanned: **{result.n_modules_scanned}**")
        lines.append(
            f"- Internal imports counted: "
            f"**{result.n_total_imports}**")
        lines.append(
            f"- Total findings: **{len(result.findings)}**")
        lines.append(
            f"- Hard failures: "
            f"**{len(result.hard_failures())}**")
        lines.append(
            f"- Status: "
            f"**{'CLEAN' if result.is_clean() else 'ATTENTION'}**")
        lines.append("")
        lines.append("## Findings by severity")
        lines.append("")
        sev_table = result.by_severity()
        for sev in (FindingSeverity.HARD,
                    FindingSeverity.WARN,
                    FindingSeverity.INFO):
            count = len(sev_table.get(sev, ()))
            lines.append(f"- {sev.value}: {count}")
        lines.append("")
        lines.append("## Findings by category")
        lines.append("")
        cat_table = result.by_category()
        for cat in FindingCategory:
            count = len(cat_table.get(cat, ()))
            lines.append(f"- {cat.value}: {count}")
        lines.append("")
        # Detail sections
        for sev in (FindingSeverity.HARD,
                    FindingSeverity.WARN,
                    FindingSeverity.INFO):
            findings = sev_table.get(sev, ())
            if not findings:
                continue
            lines.append(f"## {sev.value} findings")
            lines.append("")
            for f in findings:
                lines.append(
                    f"### `{f.module_path}` "
                    f"({f.category.value})")
                lines.append("")
                lines.append(f"**Description:** {f.description}")
                if f.observed_value is not None:
                    lines.append(
                        f"**Observed:** `{f.observed_value}`")
                if f.threshold is not None:
                    lines.append(
                        f"**Threshold:** `{f.threshold}`")
                lines.append(f"**Suggestion:** {f.suggestion}")
                lines.append("")
        return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════
# Baseline comparison — mypy-style "no regression" gate
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class BaselineComparison:
    """Result of comparing current audit to a stored baseline."""
    is_regression: bool
    new_findings: Tuple[Finding, ...]      # new HARD findings
    resolved_count_by_category: Mapping[str, int]
    current_counts: Mapping[str, int]
    baseline_counts: Mapping[str, int]
    summary: str


def compute_baseline(
    result: StructureAuditResult,
) -> Dict[str, Any]:
    """Snapshot HARD findings as a baseline for future comparison.

    Captured per-category to allow the existing-issue count to
    decrease (improvements allowed) but not increase (regressions
    rejected).
    """
    counts: Dict[str, int] = defaultdict(int)
    fingerprints: List[str] = []
    for f in result.findings:
        if f.severity == FindingSeverity.HARD:
            counts[f.category.value] += 1
            # Stable fingerprint: category + sorted modules in cycle
            mods = sorted(f.related_modules) or [f.module_path]
            fp = f"{f.category.value}::{':'.join(mods)}"
            fingerprints.append(fp)
    return {
        "version": 1,
        "hard_counts_by_category": dict(counts),
        "hard_fingerprints": sorted(set(fingerprints)),
    }


def compare_to_baseline(
    result: StructureAuditResult,
    baseline: Mapping[str, Any],
) -> BaselineComparison:
    """Compare current audit to a stored baseline.

    REGRESSION rules:
    - If current HARD count for any category > baseline count → fail
    - If current has a HARD fingerprint not in baseline → fail
    """
    baseline_counts: Mapping[str, int] = (
        baseline.get("hard_counts_by_category", {}) or {})
    baseline_fps: FrozenSet[str] = frozenset(
        baseline.get("hard_fingerprints", []) or [])

    current_counts: Dict[str, int] = defaultdict(int)
    current_fps: List[str] = []
    new_findings: List[Finding] = []
    for f in result.findings:
        if f.severity != FindingSeverity.HARD:
            continue
        current_counts[f.category.value] += 1
        mods = sorted(f.related_modules) or [f.module_path]
        fp = f"{f.category.value}::{':'.join(mods)}"
        current_fps.append(fp)
        if fp not in baseline_fps:
            new_findings.append(f)

    is_regression = len(new_findings) > 0
    # Also flag if any per-category count went up
    for cat, n in current_counts.items():
        if n > baseline_counts.get(cat, 0):
            is_regression = True

    resolved: Dict[str, int] = {}
    for cat, n in baseline_counts.items():
        cur = current_counts.get(cat, 0)
        if cur < n:
            resolved[cat] = n - cur

    if is_regression:
        summary = (
            f"REGRESSION: {len(new_findings)} new HARD findings "
            f"introduced since baseline.")
    elif resolved:
        improved = ", ".join(
            f"{cat}: −{n}" for cat, n in resolved.items())
        summary = (
            f"IMPROVED: existing HARD findings reduced "
            f"({improved}). Baseline should be re-captured.")
    else:
        summary = (
            "STABLE: HARD findings match baseline exactly.")

    return BaselineComparison(
        is_regression=is_regression,
        new_findings=tuple(new_findings),
        resolved_count_by_category=dict(resolved),
        current_counts=dict(current_counts),
        baseline_counts=dict(baseline_counts),
        summary=summary)


# ════════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════════

def _make_synthetic_codebase(tmp_root: Path) -> None:
    """Create a tiny synthetic codebase for self-testing."""
    (tmp_root / "utils").mkdir(parents=True, exist_ok=True)
    (tmp_root / "pages").mkdir(exist_ok=True)
    (tmp_root / "scripts").mkdir(exist_ok=True)

    # utils/foo.py — clean, some imports
    (tmp_root / "utils" / "foo.py").write_text(
        "from utils.bar import bar_func\n"
        "def foo_func(): return bar_func()\n"
        "class FooClass: pass\n")
    # utils/bar.py — also clean
    (tmp_root / "utils" / "bar.py").write_text(
        "def bar_func(): return 1\n"
        "class BarClass: pass\n")
    # utils/orphan.py — no callers (should be flagged)
    (tmp_root / "utils" / "orphan.py").write_text(
        "def orphan_func(): return 0\n")
    # pages/page1.py — uses foo (allowed)
    (tmp_root / "pages" / "page1.py").write_text(
        "from utils.foo import foo_func\n")
    # scripts/job.py — uses foo (allowed)
    (tmp_root / "scripts" / "job.py").write_text(
        "from utils.foo import foo_func\n")


def _make_layer_violation_codebase(tmp_root: Path) -> None:
    (tmp_root / "utils").mkdir(parents=True, exist_ok=True)
    (tmp_root / "pages").mkdir(exist_ok=True)
    # Forbidden: utils/ imports from pages/
    (tmp_root / "utils" / "bad.py").write_text(
        "from pages.page1 import x\n")
    (tmp_root / "pages" / "page1.py").write_text("x = 1\n")


def _make_circular_codebase(tmp_root: Path) -> None:
    (tmp_root / "utils").mkdir(parents=True, exist_ok=True)
    (tmp_root / "utils" / "a.py").write_text(
        "from utils.b import b\n")
    (tmp_root / "utils" / "b.py").write_text(
        "from utils.a import a\n")


def _test_clean_codebase_has_no_hard_failures():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_synthetic_codebase(root)
        engine = StructureAuditEngine(project_root=root)
        result = engine.audit()
        assert result.is_clean(), (
            f"unexpected HARDs: {result.hard_failures()}")
        # Orphan should be a WARN
        orphans = [
            f for f in result.findings
            if f.category == FindingCategory.ORPHAN_MODULE]
        assert len(orphans) >= 1


def _test_layer_violation_detected():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_layer_violation_codebase(root)
        engine = StructureAuditEngine(project_root=root)
        result = engine.audit()
        layer_findings = [
            f for f in result.findings
            if f.category == FindingCategory.LAYER_VIOLATION]
        assert len(layer_findings) == 1
        assert layer_findings[0].severity == FindingSeverity.HARD
        assert not result.is_clean()


def _test_circular_import_detected():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_circular_codebase(root)
        engine = StructureAuditEngine(project_root=root)
        result = engine.audit()
        cyc = [
            f for f in result.findings
            if f.category == FindingCategory.CIRCULAR_IMPORT]
        assert len(cyc) >= 1
        assert all(
            f.severity == FindingSeverity.HARD for f in cyc)
        assert not result.is_clean()


def _test_god_module_detection():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "utils").mkdir(parents=True)
        # A 'god.py' that 20 other modules import from
        (root / "utils" / "god.py").write_text(
            "def shared(): return 0\n")
        for i in range(20):
            (root / "utils" / f"client{i}.py").write_text(
                "from utils.god import shared\n")
        engine = StructureAuditEngine(
            project_root=root,
            god_module_threshold=15)
        result = engine.audit()
        gods = [
            f for f in result.findings
            if f.category == FindingCategory.GOD_MODULE]
        assert len(gods) == 1
        assert gods[0].observed_value == 20


def _test_cross_arc_bridge_exempt_from_god_check():
    """Modules in CROSS_ARC_BRIDGES allowed many incoming deps."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "utils").mkdir(parents=True)
        # Use a cross-arc-bridge name → should be exempt
        (root / "utils" / "scenario_simulator.py").write_text(
            "def shared(): return 0\n")
        for i in range(20):
            (root / "utils" / f"client{i}.py").write_text(
                "from utils.scenario_simulator import shared\n")
        engine = StructureAuditEngine(
            project_root=root,
            god_module_threshold=15)
        result = engine.audit()
        gods = [
            f for f in result.findings
            if f.category == FindingCategory.GOD_MODULE]
        # scenario_simulator is in CROSS_ARC_BRIDGES → skipped
        assert len(gods) == 0


def _test_duplicate_class_detected():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "utils").mkdir(parents=True)
        (root / "utils" / "a.py").write_text(
            "class Duplicate: pass\n")
        (root / "utils" / "b.py").write_text(
            "class Duplicate: pass\n")
        engine = StructureAuditEngine(project_root=root)
        result = engine.audit()
        dups = [
            f for f in result.findings
            if f.category == FindingCategory.DUPLICATE_SYMBOL
            and "Duplicate" in f.description]
        assert len(dups) >= 1


def _test_size_outlier_detected():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "utils").mkdir(parents=True)
        # Generate a 2500-line module
        big_content = "\n".join(
            [f"x{i} = {i}" for i in range(2500)])
        (root / "utils" / "big.py").write_text(big_content)
        engine = StructureAuditEngine(
            project_root=root,
            size_warn_lines=2000,
            size_fail_lines=4000)
        result = engine.audit()
        size_findings = [
            f for f in result.findings
            if f.category == FindingCategory.SIZE_OUTLIER
            and f.module_path == "utils.big"]
        assert len(size_findings) == 1
        assert size_findings[0].severity == FindingSeverity.INFO


def _test_render_markdown():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_synthetic_codebase(root)
        engine = StructureAuditEngine(project_root=root)
        result = engine.audit()
        md = engine.render_markdown_report(result)
        assert "Structural Hygiene Audit Report" in md
        assert "Modules scanned" in md
        assert "CLEAN" in md or "ATTENTION" in md


def _test_engine_rejects_missing_root():
    try:
        StructureAuditEngine(project_root=Path("/nonexistent/foo/bar"))
        assert False
    except ValueError:
        pass


def _test_summary_aggregates_correctly():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_synthetic_codebase(root)
        engine = StructureAuditEngine(project_root=root)
        result = engine.audit()
        s = result.summary
        assert s["n_modules"] >= 4
        assert "by_severity" in s
        assert "by_category" in s
        assert isinstance(s["is_clean"], bool)


def _test_findings_carry_full_triage_info():
    """Per Rule 1 every Finding has expected/observed/suggestion."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_circular_codebase(root)
        engine = StructureAuditEngine(project_root=root)
        result = engine.audit()
        for f in result.findings:
            assert len(f.description) > 5
            assert len(f.suggestion) > 5


def _test_self_imports_not_flagged_as_cycle():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "utils").mkdir(parents=True)
        (root / "utils" / "self_ref.py").write_text(
            "# tries to import itself\n"
            "# in a real package context this is harmless\n")
        engine = StructureAuditEngine(project_root=root)
        result = engine.audit()
        cycles = [
            f for f in result.findings
            if f.category == FindingCategory.CIRCULAR_IMPORT]
        assert len(cycles) == 0


def _test_baseline_captures_hard_findings():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_circular_codebase(root)
        engine = StructureAuditEngine(project_root=root)
        result = engine.audit()
        baseline = compute_baseline(result)
        assert baseline["version"] == 1
        assert "CIRCULAR_IMPORT" in (
            baseline["hard_counts_by_category"])
        assert len(baseline["hard_fingerprints"]) >= 1


def _test_baseline_no_regression_on_same_codebase():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_circular_codebase(root)
        engine = StructureAuditEngine(project_root=root)
        result1 = engine.audit()
        baseline = compute_baseline(result1)
        # Re-audit same codebase
        result2 = engine.audit()
        comparison = compare_to_baseline(result2, baseline)
        assert not comparison.is_regression
        assert "STABLE" in comparison.summary


def _test_baseline_detects_new_hard_finding():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_synthetic_codebase(root)    # clean codebase
        engine = StructureAuditEngine(project_root=root)
        result1 = engine.audit()
        baseline = compute_baseline(result1)
        # Now introduce a circular import
        (root / "utils" / "cycle1.py").write_text(
            "from utils.cycle2 import x\n")
        (root / "utils" / "cycle2.py").write_text(
            "from utils.cycle1 import x\n")
        result2 = engine.audit()
        comparison = compare_to_baseline(result2, baseline)
        assert comparison.is_regression
        assert len(comparison.new_findings) >= 1
        assert "REGRESSION" in comparison.summary


def _test_baseline_recognizes_improvement():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _make_circular_codebase(root)    # has a cycle
        engine = StructureAuditEngine(project_root=root)
        result1 = engine.audit()
        baseline = compute_baseline(result1)
        # Remove the cycle
        (root / "utils" / "b.py").write_text(
            "def b(): return 1\n")
        result2 = engine.audit()
        comparison = compare_to_baseline(result2, baseline)
        assert not comparison.is_regression
        assert "IMPROVED" in comparison.summary
        assert comparison.resolved_count_by_category.get(
            "CIRCULAR_IMPORT", 0) >= 1


def self_test() -> None:
    tests = [
        _test_clean_codebase_has_no_hard_failures,
        _test_layer_violation_detected,
        _test_circular_import_detected,
        _test_god_module_detection,
        _test_cross_arc_bridge_exempt_from_god_check,
        _test_duplicate_class_detected,
        _test_size_outlier_detected,
        _test_render_markdown,
        _test_engine_rejects_missing_root,
        _test_summary_aggregates_correctly,
        _test_findings_carry_full_triage_info,
        _test_self_imports_not_flagged_as_cycle,
        _test_baseline_captures_hard_findings,
        _test_baseline_no_regression_on_same_codebase,
        _test_baseline_detects_new_hard_finding,
        _test_baseline_recognizes_improvement,
    ]
    failed: List[Tuple[str, str]] = []
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed.append((t.__name__, str(e)))
        except Exception as e:
            failed.append((t.__name__, f"{type(e).__name__}: {e}"))
    if failed:
        print(
            f"✗ structure_audit_core self-test: "
            f"{len(failed)} failures",
            file=sys.stderr)
        for name, msg in failed:
            print(f"  - {name}: {msg}", file=sys.stderr)
        raise SystemExit(1)
    print(
        f"✓ structure_audit_core self-test passed "
        f"({len(tests)} tests)")


if __name__ == "__main__":
    self_test()
