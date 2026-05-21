"""scripts/precompute_cascade_scores.py — v10.321 cascade tree
score pre-computation.

For demo performance, pre-compute the recursive score for every
node in the org tree once, save to data/cascade_scores_<PERIOD>.json.
The cascade page can read this file directly instead of computing
on every page load (which would be 128s for the MD's subtree).

Usage:
    python scripts/precompute_cascade_scores.py --period 2026-Q1
    python scripts/precompute_cascade_scores.py --all-shipped
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def precompute_period(
    period: str,
    verbose: bool = True,
    include_rollups: bool = True,
) -> dict:
    """Compute recursive scores for every staff in the universe
    for one period, save to JSON.

    Args:
        period: e.g. '2026-Q1'
        verbose: log progress
        include_rollups: also pre-compute team_rollup for MD +
            Chiefs + Heads (adds ~1-2 minutes per period).
    """
    from utils.virtual_bank import staff_universe
    from utils.manager_rollup import (
        compute_recursive_score,
        compute_team_rollup,
    )

    u = staff_universe()
    universe_size = len(u)
    if verbose:
        print(f"Computing recursive scores for {universe_size} "
               f"staff in {period}...")

    results: dict = {
        "period": period,
        "scores": {},
        "rollups": {},
        "generated_at": "v10.322",
    }
    t0 = time.time()
    processed = 0
    # Process leaves first so cache warms naturally
    leaves = [
        s for s in u.values()
        if not any(other.manager_code == s.staff_code
                    for other in u.values())
    ]
    if verbose:
        print(f"  Leaves: {len(leaves)} — warming cache...")
    for s in leaves:
        score = compute_recursive_score(s.staff_code, period)
        if score is not None:
            results["scores"][s.staff_code] = score
        processed += 1
    if verbose:
        print(f"    {processed}/{universe_size} done in "
               f"{time.time()-t0:.1f}s")

    # Now non-leaves (managers) — cache should help dramatically
    non_leaves = [s for s in u.values() if s not in leaves]
    for s in non_leaves:
        score = compute_recursive_score(s.staff_code, period)
        if score is not None:
            results["scores"][s.staff_code] = score
        processed += 1
        if verbose and processed % 200 == 0:
            print(f"    {processed}/{universe_size} done in "
                   f"{time.time()-t0:.1f}s")

    if verbose:
        print(f"  Total: {processed} processed in "
               f"{time.time()-t0:.1f}s")
        print(f"  Scores computed: {len(results['scores'])}")

    # Team rollups for top 3 levels (only when requested)
    if include_rollups:
        md_codes = {"EXEC-MD-001"}
        chief_codes = {
            s.staff_code for s in u.values()
            if s.role and s.role.startswith("Chief")
        }
        head_codes = {
            s.staff_code for s in u.values()
            if s.role and s.role.startswith("Head of")
        }

        if verbose:
            top_count = len(
                md_codes | chief_codes | head_codes)
            print(f"  Computing team rollups for "
                   f"{top_count} top-tier managers...")
        rollup_t0 = time.time()
        for code in (md_codes | chief_codes | head_codes):
            rollup = compute_team_rollup(code, period)
            results["rollups"][code] = {
                "role": rollup.manager_role,
                "direct_reports": rollup.direct_reports_count,
                "total_subordinates": (
                    rollup.indirect_reports_count),
                "team_avg_score": rollup.team_avg_score,
                "kpi_aggregates": [
                    {
                        "kpi": a.kpi_id,
                        "team_actual": a.team_actual,
                        "team_target": a.team_target,
                        "achievement_pct": a.achievement_pct,
                        "score": a.aggregated_score,
                        "method": a.aggregation_method,
                    }
                    for a in rollup.team_kpi_aggregates
                    if a.aggregated_score is not None
                ],
            }
        if verbose:
            print(f"  Rollups computed in "
                   f"{time.time()-rollup_t0:.1f}s")

    # Save
    out_path = (
        Path(__file__).resolve().parent.parent / "data"
        / f"cascade_scores_{period}.json"
    )
    from utils.db import db as _db
    _db.save_json(out_path, results)
    if verbose:
        print(f"  Saved to {out_path}")
        print(f"  Size: {out_path.stat().st_size:,} bytes")

    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default="2026-Q1")
    parser.add_argument("--all-shipped", action="store_true")
    parser.add_argument(
        "--skip-rollups", action="store_true",
        help="Skip team rollups (faster — scores only)",
    )
    args = parser.parse_args()

    if args.all_shipped:
        periods = ["2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"]
    else:
        periods = [args.period]

    for p in periods:
        precompute_period(p, include_rollups=not args.skip_rollups)
    return 0


if __name__ == "__main__":
    sys.exit(main())
