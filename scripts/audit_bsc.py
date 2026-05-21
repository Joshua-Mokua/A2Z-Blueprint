"""Run the BSC deep audit and print findings.

Per v10.424 (BSC Rescue Phase opens):
Every staff has complete befitting BSC; React migration ready; admin
config functioning; 100% interconnection BSC↔cascade; canonical hierarchy.

This script runs the 7-category audit and produces a human-readable
report. Pass --json for machine-readable output.

Examples:
    # Human-readable report
    python scripts/audit_bsc.py

    # JSON for tooling
    python scripts/audit_bsc.py --json
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _h(text: str) -> str:
    return f"\n{'═' * 60}\n {text}\n{'═' * 60}"


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--json", action="store_true",
                   help="Emit JSON instead of human-readable report")
    args = p.parse_args()

    from utils.bsc_audit_engine import bsc_full_audit

    audit = bsc_full_audit()

    if args.json:
        print(json.dumps(audit.to_dict(), indent=2, default=str))
        return 0

    # Human-readable report
    print(_h("BSC DEEP AUDIT (v10.424)"))
    print(f"Overall health:    {audit.overall_health_pct}%")
    print(f"Issues:            {audit.issues_by_severity}")
    print(f"Generated:         {audit.timestamp}")

    # 1. Staff coverage
    c = audit.staff_coverage
    print(_h("1. STAFF COVERAGE"))
    print(f"  Register:          {c.register_count}")
    print(f"  In BSC:            {c.bsc_unique_staff}")
    print(f"  Missing BSC:       {len(c.in_register_not_in_bsc)}")
    print(f"  Ghost entries:     {len(c.in_bsc_not_in_register)}")
    print(f"  Coverage:          {c.coverage_pct}%")
    if c.in_register_not_in_bsc:
        print(f"  Sample missing:    {c.in_register_not_in_bsc[:5]}")
    if c.in_bsc_not_in_register:
        print(f"  Sample ghosts:     {c.in_bsc_not_in_register[:5]}")

    # 2. KPI completeness
    k = audit.kpi_completeness
    print(_h("2. KPI COMPLETENESS"))
    print(f"  Total staff:       {k.total_staff}")
    print(f"  Incomplete BSCs:   {k.incomplete_count}")
    print(f"  Avg KPIs/staff:    {k.avg_kpis_per_staff}")
    print(f"  Range:             {k.min_kpis} - {k.max_kpis}")
    if k.incomplete_entries:
        print(f"  Incomplete BSCs:")
        for e in k.incomplete_entries[:15]:
            print(f"    {e.role:48} — {e.staff_name:30} — {e.kpi_count}/{e.threshold} KPIs, "
                  f"{e.pillars_covered} pillars")

    # 3. Pillar canonical
    p_audit = audit.pillar_canonical
    print(_h("3. PILLAR CANONICAL"))
    print(f"  Canonical pillars: {p_audit.canonical_pillars}")
    print(f"  In BSC:            {p_audit.pillars_in_bsc}")
    if p_audit.non_canonical_pillars:
        print(f"  ✗ Non-canonical:   {p_audit.non_canonical_pillars}")
        print(f"  Affected KPIs (top 10): {dict(list(p_audit.affected_kpis.items())[:10])}")
        print(f"  Affected roles: {p_audit.affected_roles}")
    else:
        print(f"  ✓ All pillars canonical")

    # 4. Weight normalization
    w = audit.weight_normalization
    print(_h("4. WEIGHT NORMALIZATION"))
    print(f"  Total staff:       {w.total_staff}")
    print(f"  Normalized:        {w.normalized_count}")
    print(f"  ✗ Not normalized:  {w.not_normalized_count}")
    print(f"  Avg weight sum:    {w.avg_weight_sum}")
    print(f"  Range:             {w.min_weight_sum} - {w.max_weight_sum}")
    if w.not_normalized_samples:
        print(f"  Sample (top 10):")
        for staff, ws in w.not_normalized_samples[:10]:
            print(f"    {staff:30} sum={ws}")

    # 5. Library alignment
    la = audit.library_alignment
    print(_h("5. LIBRARY ALIGNMENT"))
    print(f"  BSC unique KPIs:   {la.bsc_unique_kpis}")
    print(f"  Library KPI univ:  {la.library_kpi_count}")
    print(f"  Alignment:         {la.alignment_pct}%")
    if la.bsc_kpis_not_in_library:
        print(f"  ✗ Unregistered ({len(la.bsc_kpis_not_in_library)} BSC KPIs not in library):")
        for kpi in la.bsc_kpis_not_in_library[:15]:
            print(f"    - {kpi}")
        if len(la.bsc_kpis_not_in_library) > 15:
            print(f"    ... and {len(la.bsc_kpis_not_in_library) - 15} more")

    # 6. Cascade linkage
    cl = audit.cascade_linkage
    print(_h("6. CASCADE LINKAGE"))
    print(f"  Staff in cascade:  {cl.cascaded_staff_count}")
    print(f"  Staff in BSC:      {cl.bsc_staff_count}")
    print(f"  Missing from BSC:  {len(cl.cascaded_targets_not_in_bsc)}")
    if cl.cascaded_targets_not_in_bsc:
        print(f"  Sample: {cl.cascaded_targets_not_in_bsc[:10]}")

    # 7. Duplicate rows
    d = audit.duplicate_rows
    print(_h("7. DUPLICATE ROWS"))
    print(f"  Total BSC rows:    {d.total_bsc_rows}")
    print(f"  Duplicate pairs:   {d.duplicate_count}")
    if d.duplicate_pairs:
        for staff, kpi, cnt in d.duplicate_pairs[:10]:
            print(f"    {staff:30} {kpi:40} x{cnt}")

    print(_h("SUMMARY"))
    print(f"  ✓ {7 - audit.issues_by_severity['critical'] - audit.issues_by_severity['warning']}/7 categories healthy")
    print(f"  🔴 {audit.issues_by_severity['critical']} critical")
    print(f"  ⚠️  {audit.issues_by_severity['warning']} warning")
    print(f"\nNext: fix batches v10.425+ will address findings in order of severity.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
