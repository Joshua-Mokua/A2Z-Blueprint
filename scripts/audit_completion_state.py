"""scripts/audit_completion_state.py — Scope completion state report.

Produces a structured report on platform completion state across the
four anti-drift dimensions documented in SCOPE_LEDGER.md:

  1. continuation_doc standards (active vs planned)
  2. research_addition standards (active count)
  3. PG migration coverage (FLAT_MIGRATIONS tables vs target)
  4. API endpoint count (@app/@router decorators across codebase)

Per the v10.88 anti-drift protocol, this script is run before AND
after every drop. The CHANGELOG's "Scope completion delta" section
must include the headline numbers from this report. Mismatches
between this report and SCOPE_LEDGER.md headline numbers fail the
drop's review.

Output formats:
  - Default (text): human-readable summary with the four headline
    numbers and per-subcategory active/planned breakdown
  - --json: machine-readable for CHANGELOG inclusion

Usage:
    python3 scripts/audit_completion_state.py
    python3 scripts/audit_completion_state.py --json
    python3 scripts/audit_completion_state.py --baseline v10.86 \\
        --current v10.88
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def count_standards():
    """Count standards by source + status."""
    from utils.standards_registry import STANDARDS_REGISTRY

    by_source_status: Counter = Counter()
    by_subcategory: dict = {}
    for s in STANDARDS_REGISTRY:
        by_source_status[(s.source, s.status)] += 1
        sc = s.subcategory or "(none)"
        if sc not in by_subcategory:
            by_subcategory[sc] = {
                "active": 0, "planned": 0, "other": 0}
        bucket = (
            s.status if s.status in ("active", "planned")
            else "other")
        by_subcategory[sc][bucket] += 1

    cd_active = by_source_status.get(
        ("continuation_doc", "active"), 0)
    cd_planned = by_source_status.get(
        ("continuation_doc", "planned"), 0)
    cd_total = cd_active + cd_planned + by_source_status.get(
        ("continuation_doc", "deferred"), 0)
    cbk_active = by_source_status.get(
        ("cbk_regulatory", "active"), 0)
    cbk_planned = by_source_status.get(
        ("cbk_regulatory", "planned"), 0)
    ra_active = by_source_status.get(
        ("research_addition", "active"), 0)
    ra_planned = by_source_status.get(
        ("research_addition", "planned"), 0)
    internal_active = by_source_status.get(
        ("internal", "active"), 0)

    return {
        "continuation_doc_active": cd_active,
        "continuation_doc_planned": cd_planned,
        "continuation_doc_total": cd_total,
        "cbk_regulatory_active": cbk_active,
        "cbk_regulatory_planned": cbk_planned,
        "research_addition_active": ra_active,
        "research_addition_planned": ra_planned,
        "internal_active": internal_active,
        "total_active": (
            cd_active + cbk_active + ra_active
            + internal_active),
        "total_registry": len(STANDARDS_REGISTRY),
        "by_subcategory": by_subcategory,
    }


def count_pg_migration():
    """Count PG migration coverage. Includes FLAT_MIGRATIONS tables AND
    NESTED_MIGRATIONS sub-tables (each sub-table is a separate PG
    table; the v10.88 baseline missed counting NESTED sub-tables and
    under-reported coverage)."""
    mig_path = ROOT / "scripts" / "migrate_to_postgres.py"
    if not mig_path.exists():
        return {
            "flat_tables": 0, "nested_tables": 0,
            "schema_tables": 0, "covered_jsons": 0,
            "total_jsons": 0,
            "error": "migrate_to_postgres.py not found"}
    src = mig_path.read_text(encoding="utf-8")

    # FLAT_MIGRATIONS entries: ("file.json", "table_name", (cols))
    flat_entries = re.findall(
        r'\(\s*"([^"]+\.json)"\s*,\s*"([^"]+)"', src)
    flat_jsons = {f for f, _ in flat_entries}
    flat_tables = {t for _, t in flat_entries}

    # NESTED_MIGRATIONS — extract block and count sub-tables.
    # Pattern: each sub-table reads as `key: ("table_name", (cols))`.
    nested_match = re.search(
        r'NESTED_MIGRATIONS\s*=\s*\{(.*?)^\}',
        src, re.DOTALL | re.MULTILINE)
    nested_tables = set()
    nested_jsons = set()
    if nested_match:
        nested_block = nested_match.group(1)
        # Extract each top-level json filename
        for jm in re.finditer(
            r'"([^"]+\.json)"\s*:\s*\{', nested_block
        ):
            nested_jsons.add(jm.group(1))
        # Extract each sub-table name
        for tm in re.finditer(
            r':\s*\(\s*"(\w+)"\s*,\s*\(', nested_block
        ):
            nested_tables.add(tm.group(1))

    # SPECIAL_MIGRATIONS — extract dict block and count entries (each
    # entry is one custom-handler-driven table).
    special_match = re.search(
        r'SPECIAL_MIGRATIONS\s*=\s*\{(.*?)^\}',
        src, re.DOTALL | re.MULTILINE)
    special_jsons = set()
    special_tables = set()
    if special_match:
        special_block = special_match.group(1)
        for jm in re.finditer(
            r'"([^"]+\.json)"\s*:\s*(\w+)', special_block
        ):
            special_jsons.add(jm.group(1))
            # Map handler name → table (best effort)
            handler_name = jm.group(2)
            if handler_name == "migrate_bank_targets":
                special_tables.add("bank_targets")
            elif handler_name == "migrate_baselines":
                special_tables.add("baselines")
            else:
                special_tables.add(
                    handler_name.replace("migrate_", ""))

    # Legacy in-main() migrations — flexcube_config, flexcube_events,
    # module_config are migrated via inline code in main()'s STEP 4 + 5
    # rather than through FLAT/NESTED/SPECIAL dicts. Detect by string
    # match on the inline INSERT statements so coverage count is honest.
    legacy_tables = set()
    legacy_jsons = set()
    legacy_patterns = [
        ("flexcube_config.json", "flexcube_config",
         "INSERT INTO flexcube_config"),
        ("flexcube_events.json", "flexcube_events",
         "INSERT INTO flexcube_events"),
        ("module_config.json", "module_config",
         "INSERT INTO module_config"),
    ]
    for json_name, table_name, marker in legacy_patterns:
        if marker in src:
            legacy_tables.add(table_name)
            legacy_jsons.add(json_name)

    # Schema tables in utils/db.py
    db_path = ROOT / "utils" / "db.py"
    schema_tables = 0
    if db_path.exists():
        db_src = db_path.read_text(encoding="utf-8")
        schema_tables = len(set(re.findall(
            r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+(\w+)",
            db_src, re.IGNORECASE)))

    # JSON file inventory
    data_dir = ROOT / "data"
    total_jsons = 0
    if data_dir.is_dir():
        total_jsons = len([
            f for f in os.listdir(data_dir)
            if f.endswith(".json")])

    total_tables_wired = (
        len(flat_tables) + len(nested_tables)
        + len(special_tables) + len(legacy_tables))
    total_jsons_covered = (
        len(flat_jsons) + len(nested_jsons)
        + len(special_jsons) + len(legacy_jsons))

    return {
        "flat_tables": len(flat_tables),
        "flat_migrations_entries": len(flat_entries),
        "nested_tables": len(nested_tables),
        "nested_jsons": len(nested_jsons),
        "special_tables": len(special_tables),
        "special_jsons": len(special_jsons),
        "legacy_tables": len(legacy_tables),
        "legacy_jsons": len(legacy_jsons),
        "total_tables_wired": total_tables_wired,
        "schema_tables_in_db_py": schema_tables,
        "covered_jsons": total_jsons_covered,
        "total_jsons": total_jsons,
        "uncovered_jsons": total_jsons - total_jsons_covered,
        "target_tables": 52,
        "coverage_pct": round(
            100 * total_tables_wired / 52, 1),
    }


def check_migration_consistency():
    """Verify that every FLAT_MIGRATIONS entry's flat_cols tuple has a
    matching column in the corresponding CREATE TABLE block in
    utils/db.py. This catches the column-mismatch error pattern that
    caused issues in v10.88 + v10.89 (notes dropped from asset_register;
    duplicate aml_alerts/loan_applications).

    Returns dict with:
      - mismatches: list of (table, [missing_cols])
      - duplicate_tables: list of tables with >1 CREATE TABLE statement
      - total_flat_entries: count of FLAT_MIGRATIONS entries checked
    """
    mig_path = ROOT / "scripts" / "migrate_to_postgres.py"
    db_path = ROOT / "utils" / "db.py"
    if not mig_path.exists() or not db_path.exists():
        return {
            "mismatches": [],
            "duplicate_tables": [],
            "total_flat_entries": 0,
            "error": "missing source file",
        }

    mig_src = mig_path.read_text(encoding="utf-8")
    db_src = db_path.read_text(encoding="utf-8")

    # Extract FLAT_MIGRATIONS entries
    flat = re.findall(
        r'\(\s*"([^"]+\.json)"\s*,\s*"([^"]+)"\s*,'
        r'\s*\(([^)]+)\)\s*\)', mig_src)

    mismatches: list = []
    duplicate_tables: list = []
    seen_tables = set()

    for json_file, table, cols_str in flat:
        # Duplicate detection: a table appearing twice in FLAT_MIGRATIONS
        # would be a hard error
        if table in seen_tables:
            duplicate_tables.append(
                (table, "duplicate FLAT_MIGRATIONS entry"))
        seen_tables.add(table)

        # Find table in schema
        table_matches = list(re.finditer(
            rf'CREATE TABLE IF NOT EXISTS {table}\s*\((.*?)\);',
            db_src, re.DOTALL))
        if len(table_matches) > 1:
            duplicate_tables.append(
                (table,
                 f"{len(table_matches)} CREATE TABLE statements "
                 f"in utils/db.py"))
            continue
        if not table_matches:
            mismatches.append(
                (table, ["NO_SCHEMA_DEFINITION"]))
            continue

        block = table_matches[0].group(1)
        sch_cols = re.findall(
            r'^\s+(\w+)\s+(?:VARCHAR|INTEGER|INT|NUMERIC'
            r'|BOOLEAN|TEXT|JSONB|DATE|TIMESTAMPTZ|CHAR|UUID'
            r'|BIGINT|SMALLINT|FLOAT|DOUBLE|DECIMAL)',
            block, re.MULTILINE)

        # Skip the synthetic data/created_at/updated_at — those are
        # added by insert_records, not in flat_cols
        flat_cols = [
            c.strip().strip('"')
            for c in cols_str.split(',')]
        missing = [
            c for c in flat_cols if c not in sch_cols]
        if missing:
            mismatches.append((table, missing))

    return {
        "mismatches": mismatches,
        "duplicate_tables": duplicate_tables,
        "total_flat_entries": len(flat),
    }


def count_test_coverage():
    """Test coverage signals — combines static analysis (test/source
    file ratios) with dynamic coverage (coverage.xml if present).

    Two kinds of signal:
      1. STATIC: count test files vs source files per directory.
         Identifies under-tested modules even when coverage.py
         hasn't been run. Uses heuristics:
           - test_<name>.py filename match
           - `from utils.X import` / `from pages.X import` match
      2. DYNAMIC: parse coverage.xml if present (produced by
         `pytest --cov --cov-report=xml`). G18's threshold gate is
         the enforcement layer; this is the visibility layer.

    Returns dict with both signals so the report can show the
    measurable count and the static-analysis indication of where
    coverage gaps live.
    """
    import xml.etree.ElementTree as ET

    # ── STATIC ANALYSIS ─────────────────────────────────────────────
    sources: list = []
    for sub in ("utils", "pages", "scripts"):
        d = ROOT / sub
        if not d.is_dir():
            continue
        for f in os.listdir(d):
            if f.endswith(".py") and not f.startswith("_"):
                sources.append(d / f)

    # For each source, count test references
    tests_dir = ROOT / "tests"
    test_refs: dict = {str(s.relative_to(ROOT)): 0 for s in sources}
    if tests_dir.is_dir():
        for tdir, _, tfiles in os.walk(tests_dir):
            for tf in tfiles:
                if not tf.endswith(".py"):
                    continue
                tpath = Path(tdir) / tf
                try:
                    content = tpath.read_text(encoding="utf-8")
                except Exception:
                    continue
                # Import-based references
                for m in re.finditer(
                    r"from (utils|pages|scripts)\."
                    r"(\w+)\s+import", content
                ):
                    src_key = f"{m.group(1)}/{m.group(2)}.py"
                    if src_key in test_refs:
                        test_refs[src_key] += 1
                # Filename-pattern references (test_<stem>.py)
                if tf.startswith("test_"):
                    stem = tf[5:-3]
                    for src_key in test_refs:
                        src_stem = (
                            src_key.split("/")[-1][:-3])
                        if (stem == src_stem
                                or stem.startswith(
                                    src_stem + "_")):
                            test_refs[src_key] += 1

    well_tested = sum(1 for n in test_refs.values() if n >= 3)
    moderately = sum(
        1 for n in test_refs.values() if 1 <= n < 3)
    untested = sum(1 for n in test_refs.values() if n == 0)

    # Aggregate by directory
    by_dir: dict = {}
    for src_key, n in test_refs.items():
        d = src_key.split("/")[0]
        if d not in by_dir:
            by_dir[d] = {"well": 0, "mod": 0, "none": 0}
        if n >= 3:
            by_dir[d]["well"] += 1
        elif n >= 1:
            by_dir[d]["mod"] += 1
        else:
            by_dir[d]["none"] += 1

    # Top 10 biggest under-tested modules
    untested_sources = [
        (k, (ROOT / k).stat().st_size)
        for k, n in test_refs.items()
        if n == 0 and (ROOT / k).exists()
    ]
    untested_sources.sort(key=lambda x: -x[1])
    biggest_untested = [
        {"path": k, "size_kb": sz // 1024}
        for k, sz in untested_sources[:10]
    ]

    # ── DYNAMIC: coverage.xml ───────────────────────────────────────
    coverage_xml_path = ROOT / "coverage.xml"
    dynamic = {
        "coverage_xml_present": False,
        "overall_pct": None,
        "per_module_status": "no coverage.xml — run "
                             "`pytest --cov --cov-report=xml`",
    }
    if coverage_xml_path.exists():
        try:
            tree = ET.parse(coverage_xml_path)
            root_el = tree.getroot()
            line_rate = root_el.get("line-rate", "0")
            overall_pct = round(float(line_rate) * 100, 1)
            # Per-spec thresholds (Standard #4)
            spec_targets = {
                "utils/bsc_engine.py": 95,
                "utils/db.py": 90,
                "utils/auth_jwt.py": 95,
                "utils/core_kpi.py": 85,
                "pages/": 70,
            }
            dynamic = {
                "coverage_xml_present": True,
                "overall_pct": overall_pct,
                "spec_targets": spec_targets,
                "per_module_status": (
                    f"coverage.xml parsed; G18 enforces "
                    f"per-module thresholds"),
            }
        except Exception as e:
            dynamic = {
                "coverage_xml_present": True,
                "overall_pct": None,
                "per_module_status": (
                    f"coverage.xml present but unparseable: "
                    f"{type(e).__name__}: {e}"),
            }

    return {
        "static": {
            "total_sources": len(sources),
            "well_tested": well_tested,
            "moderately_tested": moderately,
            "untested": untested,
            "by_directory": by_dir,
            "biggest_untested_top10": biggest_untested,
        },
        "dynamic": dynamic,
        "target_pct": 80,
    }


def count_api_endpoints():
    """Count FastAPI endpoints across the codebase. Three components:

    1. Direct @app.* / @router.* decorators in source (excluding the
       audit script itself, which contains regex string literals that
       false-match this pattern).
    2. CRUD factory expansions — each `make_crud_router(module=X)` call
       in production code generates 8 endpoints via the factory in
       utils/api_crud.py. Counted via the api_crud.register_module()
       registry pattern (parsed statically from utils/api.py).

    Returns dict with:
      - total: combined count
      - direct_decorators: count from approach 1
      - crud_modules: count of make_crud_router calls
      - crud_endpoints: 8 × crud_modules (the factory's verb count)
      - target: 136
      - coverage_pct: percentage of target
    """
    # 1. Direct decorators across all .py files except audit.py
    # (audit.py contains regex string literals that match this
    # pattern — they're checks looking FOR the decorators, not
    # the decorators themselves)
    direct_count = 0
    by_file: dict = {}
    AUDIT_PATH = ROOT / "scripts" / "audit.py"
    for path in ROOT.rglob("*.py"):
        skip = False
        for s in (
            "__pycache__", ".venv", "node_modules", "/build/",
            "/tests/"
        ):
            if s in str(path):
                skip = True
                break
        if skip or path == AUDIT_PATH:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        endpoints = re.findall(
            r"@(?:app|router)\.(get|post|put|delete|patch)\(",
            content)
        if endpoints:
            by_file[str(path.relative_to(ROOT))] = len(
                endpoints)
            direct_count += len(endpoints)

    # 2. CRUD factory expansions — count make_crud_router() calls
    # in production code (excluding test files) and multiply by 8
    crud_modules = 0
    api_path = ROOT / "utils" / "api.py"
    if api_path.exists():
        api_src = api_path.read_text(encoding="utf-8")
        crud_modules = len(re.findall(
            r'make_crud_router\s*\(\s*\n?\s*module\s*=',
            api_src))
    # The factory's 8 verbs: list, get, create, update, delete,
    # export, search, dashboard
    CRUD_VERBS_PER_MODULE = 8
    crud_endpoints = crud_modules * CRUD_VERBS_PER_MODULE

    # The factory's own 8 decorators (in api_crud.py) are part
    # of direct_count above — we DON'T want to double-count them.
    # Subtract them to get just the "non-factory" direct count.
    crud_factory_path = ROOT / "utils" / "api_crud.py"
    factory_decorators = 0
    if crud_factory_path.exists():
        factory_src = crud_factory_path.read_text(
            encoding="utf-8")
        factory_decorators = len(re.findall(
            r"@(?:app|router)\.(get|post|put|delete|patch)\(",
            factory_src))

    # True total: direct (excluding factory's template decorators,
    # which only count once regardless of how many modules use them)
    # + crud expansions (one set of 8 per module call)
    direct_excluding_factory = direct_count - factory_decorators
    total = direct_excluding_factory + crud_endpoints

    return {
        "total": total,
        "direct_decorators": direct_count,
        "direct_excluding_factory": direct_excluding_factory,
        "factory_template_decorators": factory_decorators,
        "crud_modules": crud_modules,
        "crud_endpoints": crud_endpoints,
        "target": 136,
        "coverage_pct": round(100 * total / 136, 1),
        "by_file_top10": dict(
            sorted(by_file.items(),
                   key=lambda x: -x[1])[:10]),
    }


def render_text_report(state) -> str:
    s = state["standards"]
    pg = state["pg_migration"]
    api = state["api_endpoints"]
    lines = []
    lines.append("=" * 72)
    lines.append("A2Z MIS 360 — Scope Completion State Report")
    lines.append("=" * 72)
    lines.append("")
    lines.append("HEADLINE NUMBERS (anti-drift dimensions)")
    lines.append("-" * 72)
    lines.append(
        f"  continuation_doc active:   "
        f"{s['continuation_doc_active']:3d} / "
        f"{s['continuation_doc_total']:3d}  "
        f"({100 * s['continuation_doc_active'] / max(s['continuation_doc_total'], 1):.1f}%)")
    lines.append(
        f"  cbk_regulatory active:     "
        f"{s['cbk_regulatory_active']:3d} / "
        f"{s['cbk_regulatory_active'] + s['cbk_regulatory_planned']:3d}")
    lines.append(
        f"  research_addition active:  "
        f"{s['research_addition_active']:3d}  "
        f"(planned {s['research_addition_planned']})")
    lines.append(
        f"  internal active:           "
        f"{s['internal_active']:3d}")
    lines.append(
        f"  TOTAL ACTIVE:              "
        f"{s['total_active']:3d} / "
        f"{s['total_registry']:3d}")
    lines.append("")
    lines.append(
        f"  PG migration coverage:     "
        f"{pg['total_tables_wired']:2d} / "
        f"{pg['target_tables']} "
        f"tables wired ({pg['coverage_pct']}%)")
    lines.append(
        f"    flat tables:             "
        f"{pg['flat_tables']}")
    lines.append(
        f"    nested sub-tables:       "
        f"{pg['nested_tables']}")
    lines.append(
        f"    special-case tables:     "
        f"{pg.get('special_tables', 0)}")
    lines.append(
        f"    legacy in-main():        "
        f"{pg.get('legacy_tables', 0)}")
    lines.append(
        f"    schema tables in db.py:  "
        f"{pg['schema_tables_in_db_py']}")
    lines.append(
        f"    JSONs covered:           "
        f"{pg['covered_jsons']} / {pg['total_jsons']}")
    lines.append("")
    lines.append(
        f"  API endpoints:             "
        f"{api['total']:3d} / {api['target']:3d}  "
        f"({api['coverage_pct']}%)")
    lines.append(
        f"    direct decorators:       "
        f"{api.get('direct_excluding_factory', 0)}")
    lines.append(
        f"    CRUD factory modules:    "
        f"{api.get('crud_modules', 0)}  "
        f"(× 8 verbs = "
        f"{api.get('crud_endpoints', 0)} endpoints)")
    lines.append("")

    # Test coverage block (added v10.97 — Phase 1C kickoff)
    tc = state.get("test_coverage", {})
    if tc:
        st = tc.get("static", {})
        dy = tc.get("dynamic", {})
        lines.append(
            f"  Test coverage:")
        if dy.get("coverage_xml_present") and \
                dy.get("overall_pct") is not None:
            lines.append(
                f"    overall (coverage.xml):  "
                f"{dy['overall_pct']}%  "
                f"(target ≥ {tc.get('target_pct', 80)}%)")
        else:
            lines.append(
                f"    overall (coverage.xml):  "
                f"{dy.get('per_module_status', 'unavailable')}")
        lines.append(
            f"    static signal:           "
            f"{st.get('well_tested', 0)} well, "
            f"{st.get('moderately_tested', 0)} mod, "
            f"{st.get('untested', 0)} untested  "
            f"(of {st.get('total_sources', 0)} source files)")
        for d, c in sorted(
            (st.get("by_directory") or {}).items()
        ):
            total = c["well"] + c["mod"] + c["none"]
            if total == 0:
                continue
            covered_pct = round(
                100 * (c["well"] + c["mod"]) / total, 1)
            lines.append(
                f"      {d:8s}             "
                f"{c['well']:3d} well / "
                f"{c['mod']:3d} mod / "
                f"{c['none']:3d} none  "
                f"({covered_pct}% file-count)")
    lines.append("")

    lines.append(
        "PER-SUBCATEGORY (active / planned, "
        "subcategories with planned > 0)")
    lines.append("-" * 72)
    relevant = sorted(
        ((sc, c) for sc, c in s["by_subcategory"].items()
         if c["planned"] > 0),
        key=lambda x: -x[1]["planned"])
    for sc, c in relevant:
        lines.append(
            f"  {sc:30s}  active={c['active']:3d} "
            f"planned={c['planned']:3d}")
    lines.append("")
    lines.append("PHASE 3 BLOCKED ITEMS (need user-supplied spec)")
    lines.append("-" * 72)
    lines.append(
        "  - Peer Learning standards #14–#20 "
        "(Amplification API)")
    lines.append("  - FATCA/CRS XML schema")
    lines.append("  - Specific deferred CBK reports")
    lines.append("  - React/React Native standards #37–#38")
    lines.append("  (Per Joshua's directive at v10.90: deferred to end;")
    lines.append("   planned after Phase 1 + Phase 2 close)")
    lines.append("")

    # Migration consistency block (added v10.90)
    mc = state.get("migration_consistency", {})
    if mc:
        lines.append(
            "MIGRATION CONSISTENCY (FLAT_MIGRATIONS vs schema)")
        lines.append("-" * 72)
        n_entries = mc.get("total_flat_entries", 0)
        n_mismatches = len(mc.get("mismatches", []))
        n_duplicates = len(mc.get("duplicate_tables", []))
        if n_mismatches == 0 and n_duplicates == 0:
            lines.append(
                f"  ✓ {n_entries} FLAT_MIGRATIONS entries "
                f"verified, all flat_cols match schema columns")
        else:
            if n_mismatches > 0:
                lines.append(
                    f"  ✗ {n_mismatches} table(s) with "
                    f"flat_cols not in schema:")
                for table, missing in mc["mismatches"]:
                    lines.append(
                        f"    - {table}: missing {missing}")
            if n_duplicates > 0:
                lines.append(
                    f"  ✗ {n_duplicates} duplicate table(s):")
                for table, reason in mc["duplicate_tables"]:
                    lines.append(
                        f"    - {table}: {reason}")
        lines.append("")
    return "\n".join(lines)


def main():
    # Windows + non-UTF-8 console fix: state report uses ≥ ✓ ↑ — etc.
    # which crash on cp1252. Same fix as scripts/audit.py main(). See
    # CHANGELOG_v10.100 for the audit.py fix; v10.101 extends it here.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    parser = argparse.ArgumentParser(
        description="Scope completion state report")
    parser.add_argument(
        "--json", action="store_true",
        help="Output machine-readable JSON")
    args = parser.parse_args()

    state = {
        "standards": count_standards(),
        "pg_migration": count_pg_migration(),
        "api_endpoints": count_api_endpoints(),
        "migration_consistency": check_migration_consistency(),
        "test_coverage": count_test_coverage(),
    }
    if args.json:
        print(json.dumps(state, indent=2))
    else:
        print(render_text_report(state))


if __name__ == "__main__":
    main()
