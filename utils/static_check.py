"""utils/static_check.py — AST-based static analysis for render functions.

Catches two bug classes that pure module-load smoke tests can't detect:

  CLASS 1: undefined module-level constants used inside a function
    Example (v10.350):
        def render_executive_tab(engines):
            if not STREAMLIT_AVAILABLE:   # ← NameError when called
                return
        # STREAMLIT_AVAILABLE never assigned anywhere

  CLASS 2: shadowing local imports that produce UnboundLocalError
    Example (v10.351):
        from utils.system_stocks import get_stock_snapshot  # top-level
        def render_systems_view(actor):
            snapshot = get_stock_snapshot(stock_id)  # line 444 ← USE first
            ...
            from utils.system_stocks import get_stock_snapshot  # line 1150 ← shadow

Conservative heuristics — false positives suppressed:
  - CLASS 1: only flag ALL_CAPS names, only when not resolvable through
    function scope, enclosing scopes, module top, or builtins.
  - CLASS 2: only flag when the local import is positioned AFTER a use
    of the same name in the same function — that's the actual UnboundLocalError
    trigger. A shadowing import before any use is wasteful but not a bug.
  - Wildcard imports anywhere disable both checks for that file (can't
    reason about what `from X import *` brought in).
"""

from __future__ import annotations

import ast
import builtins
from pathlib import Path
from typing import Iterable, List, NamedTuple


class Finding(NamedTuple):
    file: str
    function: str
    line: int
    name: str
    category: str
    detail: str


_BUILTIN_NAMES = frozenset(dir(builtins))
_HIDDEN_GLOBALS = frozenset({
    "__name__", "__file__", "__doc__", "__loader__", "__spec__",
    "__package__", "__builtins__", "__class__", "__qualname__",
})


def _names_bound_in_stmt(node: ast.AST) -> set[str]:
    """Names that a single statement binds in the current scope."""
    out: set[str] = set()
    if isinstance(node, ast.Import):
        for a in node.names:
            if a.name != "*":
                out.add(a.asname or a.name.split(".")[0])
    elif isinstance(node, ast.ImportFrom):
        for a in node.names:
            if a.name == "*":
                out.add("__WILDCARD__")
            else:
                out.add(a.asname or a.name)
    elif isinstance(node, ast.Assign):
        for tgt in node.targets:
            for n in ast.walk(tgt):
                if isinstance(n, ast.Name):
                    out.add(n.id)
    elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
        if isinstance(node.target, ast.Name):
            out.add(node.target.id)
    elif isinstance(node, (ast.For, ast.AsyncFor)):
        for n in ast.walk(node.target):
            if isinstance(n, ast.Name):
                out.add(n.id)
    elif isinstance(node, (ast.With, ast.AsyncWith)):
        for item in node.items:
            if item.optional_vars:
                for n in ast.walk(item.optional_vars):
                    if isinstance(n, ast.Name):
                        out.add(n.id)
    elif isinstance(node, ast.ExceptHandler):
        if node.name:
            out.add(node.name)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        out.add(node.name)
    elif isinstance(node, (ast.Global, ast.Nonlocal)):
        for nm in node.names:
            out.add(nm)
    return out


def _walk_in_scope(root: ast.AST):
    """Yield nodes in the same scope as root — descends into compound
    statements (if/try/with/for/while) but NOT into nested function or
    class definitions. The root itself is yielded first."""
    yield root
    stack = list(ast.iter_child_nodes(root))
    while stack:
        node = stack.pop(0)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node  # yield the def header but don't descend into body
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _collect_function_scope(fn: ast.AST) -> set[str]:
    """All names bound in a function's own scope: parameters + body
    assignments (anywhere in the body, per Python's scoping rule)."""
    bound: set[str] = set()
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for arg in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs:
            bound.add(arg.arg)
        if fn.args.vararg:
            bound.add(fn.args.vararg.arg)
        if fn.args.kwarg:
            bound.add(fn.args.kwarg.arg)
    for node in _walk_in_scope(fn):
        if node is fn:
            continue
        bound.update(_names_bound_in_stmt(node))
        if isinstance(node, ast.NamedExpr):
            if isinstance(node.target, ast.Name):
                bound.add(node.target.id)
        if isinstance(node, ast.comprehension):
            for n in ast.walk(node.target):
                if isinstance(n, ast.Name):
                    bound.add(n.id)
        if isinstance(node, ast.Lambda):
            for arg in node.args.args:
                bound.add(arg.arg)
    return bound


def _collect_module_top_scope(tree: ast.Module) -> set[str]:
    """Names bound at module top (defs, imports, assignments, including
    those inside `if`/`try`/`with` at top level)."""
    bound: set[str] = set()
    for node in _walk_in_scope(tree):
        if node is tree:
            continue
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
            continue
        bound.update(_names_bound_in_stmt(node))
    return bound


def _build_parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _enclosing_function_scopes(
    fn: ast.AST,
    parent_of: dict[ast.AST, ast.AST],
) -> List[set[str]]:
    """All ancestor function scopes that fn can read names from (closure access)."""
    scopes: List[set[str]] = []
    cur = parent_of.get(fn)
    while cur is not None and not isinstance(cur, ast.Module):
        if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scopes.append(_collect_function_scope(cur))
        cur = parent_of.get(cur)
    return scopes


def find_undefined_caps_constants(path: Path) -> List[Finding]:
    """CLASS 1 — ALL_CAPS names used inside a function body not resolvable
    through own scope, enclosing function scopes, enclosing class body
    scope (for default args), module top, or builtins.

    Excludes Name nodes that are children of:
      - args.defaults / args.kw_defaults (evaluated in enclosing scope)
      - decorator_list (evaluated in enclosing scope)
    These don't represent uses inside the function body — they're class
    or module-level evaluations even when textually inside def.
    """
    findings: List[Finding] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    module_top = _collect_module_top_scope(tree)
    if "__WILDCARD__" in module_top:
        return []

    parent_of = _build_parent_map(tree)

    # v10.353 — memoize function scope computations. Without this, a
    # 2000-line outer function with 10 nested functions causes the
    # outer scope to be re-walked 10× (once per inner enclosing-scope
    # query). Cache by id().
    scope_cache: dict[int, set[str]] = {}
    def cached_scope(fn: ast.AST) -> set[str]:
        if id(fn) not in scope_cache:
            scope_cache[id(fn)] = _collect_function_scope(fn)
        return scope_cache[id(fn)]

    def enclosing_class_scope(fn: ast.AST) -> set[str]:
        """If fn is a method, return the class body's bound names."""
        cur = parent_of.get(fn)
        while cur is not None and not isinstance(cur, ast.Module):
            if isinstance(cur, ast.ClassDef):
                bound: set[str] = set()
                for stmt in cur.body:
                    bound.update(_names_bound_in_stmt(stmt))
                    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        bound.add(stmt.name)
                return bound
            cur = parent_of.get(cur)
        return set()

    def collect_in_default_or_decorator(fn: ast.AST) -> set[int]:
        """Return the set of node ids reachable via args.defaults /
        kw_defaults / decorator_list. Computed ONCE per function — far
        cheaper than walking args.defaults per Name node."""
        ids: set[int] = set()
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return ids
        roots = list(fn.args.defaults) + list(fn.args.kw_defaults or []) + list(fn.decorator_list)
        for root in roots:
            if root is None:
                continue
            for sub in ast.walk(root):
                ids.add(id(sub))
        return ids

    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        own = cached_scope(fn)
        # Enclosing function scopes (closure access)
        enclosing_fns: List[set[str]] = []
        cur = parent_of.get(fn)
        while cur is not None and not isinstance(cur, ast.Module):
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                enclosing_fns.append(cached_scope(cur))
            cur = parent_of.get(cur)
        class_scope = enclosing_class_scope(fn)
        default_node_ids = collect_in_default_or_decorator(fn)

        for node in _walk_in_scope(fn):
            if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
                continue
            nm = node.id
            if not nm.isupper() or len(nm) < 2:
                continue
            if len(nm) <= 3 and "_" not in nm:
                continue
            # Skip if in default-arg or decorator (different scope)
            if id(node) in default_node_ids:
                # For these, check class scope too
                if nm in class_scope or nm in module_top or nm in _BUILTIN_NAMES:
                    continue
            if nm in own:
                continue
            if any(nm in s for s in enclosing_fns):
                continue
            if nm in module_top:
                continue
            if nm in _BUILTIN_NAMES or nm in _HIDDEN_GLOBALS:
                continue
            findings.append(Finding(
                file=str(path),
                function=fn.name,
                line=node.lineno,
                name=nm,
                category="undefined_caps_constant",
                detail=(
                    f"function {fn.name!r} uses {nm!r} which is not bound "
                    f"anywhere reachable — will raise NameError when this "
                    f"code path runs"
                ),
            ))
    return findings


def find_unbound_local_imports(path: Path) -> List[Finding]:
    """CLASS 2 — local imports inside a function that shadow a module-top
    import AND have a USE of the same name BEFORE the EARLIEST local
    binding line in that function.

    For each name `X` imported at module top:
      - If X is locally re-bound anywhere in a function F, X is local in F
      - Find the FIRST binding line of X in F (earliest assignment or import)
      - If F uses X at any line BEFORE that first binding → UnboundLocalError

    Subsequent local re-imports (after the earliest) are wasteful but not
    bugs — skipped to suppress false positives.
    """
    findings: List[Finding] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    top_imported: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                if a.name != "*":
                    top_imported.add(a.asname or a.name.split(".")[0])
    if not top_imported:
        return []

    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # For each top-imported name, collect ALL local binding lines + ALL use lines
        binding_lines: dict[str, List[int]] = {}
        use_lines: dict[str, List[int]] = {}

        for node in _walk_in_scope(fn):
            if node is fn:
                continue
            # Bindings: any statement that binds the name
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    if a.name == "*":
                        continue
                    nm = a.asname or a.name.split(".")[0]
                    if nm in top_imported:
                        binding_lines.setdefault(nm, []).append(node.lineno)
            elif isinstance(node, ast.Assign):
                for tgt in node.targets:
                    for n in ast.walk(tgt):
                        # Only Name nodes with Store context are bindings.
                        # `st.session_state["x"] = ...` has Name('st') with Load,
                        # not Store — that's an attribute-access read.
                        if (isinstance(n, ast.Name)
                                and isinstance(n.ctx, ast.Store)
                                and n.id in top_imported):
                            binding_lines.setdefault(n.id, []).append(node.lineno)
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                if (isinstance(node.target, ast.Name)
                        and isinstance(node.target.ctx, ast.Store)
                        and node.target.id in top_imported):
                    binding_lines.setdefault(node.target.id, []).append(node.lineno)
            # Uses
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in top_imported:
                    use_lines.setdefault(node.id, []).append(node.lineno)

        # For each name with both binding and use sites, check use-before-earliest-bind
        for nm, binds in binding_lines.items():
            earliest_bind = min(binds)
            pre_uses = [u for u in use_lines.get(nm, []) if u < earliest_bind]
            if pre_uses:
                findings.append(Finding(
                    file=str(path),
                    function=fn.name,
                    line=earliest_bind,
                    name=nm,
                    category="unbound_local_import",
                    detail=(
                        f"function {fn.name!r} locally re-binds {nm!r} at line "
                        f"{earliest_bind} (module-top already imports it). "
                        f"{nm!r} is used at line(s) {pre_uses[:3]} BEFORE the "
                        f"earliest local binding → UnboundLocalError. Remove "
                        f"the local binding or move it above all uses."
                    ),
                ))
    return findings


def static_check_file(path: Path) -> List[Finding]:
    return (
        find_undefined_caps_constants(path)
        + find_unbound_local_imports(path)
    )


def static_check_paths(paths: Iterable[Path]) -> List[Finding]:
    out: List[Finding] = []
    for p in paths:
        out.extend(static_check_file(p))
    return out


def format_findings(findings: List[Finding]) -> str:
    if not findings:
        return "  (no findings — static checks clean)"
    lines = []
    by_cat: dict[str, list[Finding]] = {}
    for f in findings:
        by_cat.setdefault(f.category, []).append(f)
    for cat, items in sorted(by_cat.items()):
        lines.append(f"\n  {cat} ({len(items)} findings):")
        for f in items[:30]:
            rel = f.file.replace("/tmp/a2z_fix/", "")
            lines.append(f"    {rel}:{f.line}  in {f.function}()  →  {f.name}")
        if len(items) > 30:
            lines.append(f"    ... and {len(items) - 30} more")
    return "\n".join(lines)
