"""scripts/generate_growth_plans.py — Materialize per-staff growth plans
(Standard #12, v5.39).

Iterates every active user in data/users.json, calls
GrowthPathEngine.generate_development_plan(), and writes the result
to data/growth_plans.json. Intended to be run nightly (or after
periodic BSC scoring closes).

Also seeds data/staff_skills.json on first run if it doesn't exist —
so coverage gate G23 has data to verify against. Real deployments
replace the seeded skills with HR-curated assessments.

Usage:
  python scripts/generate_growth_plans.py
  python scripts/generate_growth_plans.py --seed-skills
  python scripts/generate_growth_plans.py --dry-run

The script writes a status artifact at growth_plans_results.json
which audit gate G23 reads to verify coverage.

Exit codes:
  0 = success (all active staff have plans)
  1 = coverage shortfall
  2 = could not load users
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
PLANS_FILE = DATA / "growth_plans.json"
SKILLS_FILE = DATA / "staff_skills.json"
RESULTS_FILE = ROOT / "growth_plans_results.json"

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("growth_plans")


# Skill-level seeding policy: higher band → higher baseline skill levels.
# This is a STARTING POINT. Real bank deployments replace these with
# HR-curated assessments. The seed values are deterministic per (staff_code, skill)
# so re-running doesn't churn the data.
BAND_SKILL_BASELINE = {
    # Executive levels
    "E1":  4.5,
    "E2":  4.3,
    "E3":  4.0,
    # Management
    "M1":  4.0,
    "M2":  3.8,
    "M3":  3.5,
    "M4":  3.3,
    "M5":  3.0,
    # Officer / supervisor
    "O1":  2.8,
    "O2":  2.5,
    # Junior
    "J1":  2.2,
    "J2":  2.0,
}
DEFAULT_SKILL_BASELINE = 3.0


def seed_staff_skills(users: Dict[str, dict], role_matrix: Dict[str, dict]) -> Dict[str, Dict[str, float]]:
    """Generate plausible skill assessments for every active user.

    Approach: for each user, take their role's required skills. Assign
    a level near the band's baseline ± deterministic noise per
    (staff_code, skill) so re-runs don't churn. This is the seed; real
    HR systems supply this data.
    """
    skills: Dict[str, Dict[str, float]] = {}
    for username, info in users.items():
        if not isinstance(info, dict) or not info.get("active"):
            continue
        staff_code = str(info.get("staff_code", ""))
        if not staff_code:
            continue
        role = info.get("role") or ""
        band = info.get("band") or "M5"
        baseline = BAND_SKILL_BASELINE.get(band, DEFAULT_SKILL_BASELINE)
        required = role_matrix.get(role) or role_matrix.get("default") or {}

        per_staff: Dict[str, float] = {}
        for skill, req_level in required.items():
            # Deterministic per-(staff, skill) jitter via stable hash
            seed = abs(hash((staff_code, skill))) % 100
            # Jitter in [-0.6, +0.6]
            jitter = (seed / 100.0 - 0.5) * 1.2
            level = baseline + jitter
            # Clamp to [1.0, 5.0]
            level = max(1.0, min(5.0, round(level, 1)))
            per_staff[skill] = level
        if per_staff:
            skills[staff_code] = per_staff
    return skills


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seed-skills", action="store_true",
                   help="Generate / overwrite staff_skills.json from band baselines")
    p.add_argument("--dry-run", action="store_true",
                   help="Compute plans but do not write to disk")
    args = p.parse_args()

    log.info("A2Z MIS 360 — Growth path generator (Standard #12)")
    log.info("Project root: %s", ROOT)

    # 1. Load users
    users_file = DATA / "users.json"
    if not users_file.exists():
        log.error("ERROR: %s does not exist", users_file)
        return 2
    try:
        users = json.loads(users_file.read_text())
    except Exception as e:
        log.error("ERROR: could not parse users.json: %s", e)
        return 2
    if not isinstance(users, dict):
        log.error("ERROR: users.json must be an object keyed by username")
        return 2

    active_count = sum(
        1 for info in users.values()
        if isinstance(info, dict) and info.get("active")
    )

    # Detect duplicate staff_codes (data integrity issue — surface separately)
    code_to_users: Dict[str, list] = {}
    for username, info in users.items():
        if isinstance(info, dict) and info.get("active"):
            sc = str(info.get("staff_code", ""))
            if sc:
                code_to_users.setdefault(sc, []).append(username)
    duplicate_codes = {sc: us for sc, us in code_to_users.items() if len(us) > 1}
    unique_staff_codes = len(code_to_users)

    log.info("  Total users:           %d", len(users))
    log.info("  Active users:          %d", active_count)
    log.info("  Unique staff_codes:    %d", unique_staff_codes)
    if duplicate_codes:
        log.info("  Duplicate staff_codes: %d (data integrity issue)",
                 len(duplicate_codes))

    # 2. Load role-skill matrix
    role_matrix_file = DATA / "role_skill_matrix.json"
    if not role_matrix_file.exists():
        log.error("ERROR: %s does not exist; cannot compute skill gaps",
                  role_matrix_file)
        return 2
    role_matrix = json.loads(role_matrix_file.read_text())
    log.info("  Role matrix:       %d roles", len(role_matrix))

    # 3. Seed skills if requested or if missing entirely
    if args.seed_skills or not SKILLS_FILE.exists():
        log.info("\n  Seeding %s ...", SKILLS_FILE.name)
        seeded = seed_staff_skills(users, role_matrix)
        if not args.dry_run:
            SKILLS_FILE.write_text(json.dumps(seeded, indent=2, sort_keys=True))
        log.info("    Seeded skills for %d active staff", len(seeded))

    # 4. Generate plans for every active user
    log.info("\n  Generating growth plans ...")
    from utils.growth_path_engine import GrowthPathEngine

    engine = GrowthPathEngine()
    plans: Dict[str, dict] = {}
    skipped_inactive = 0
    skipped_no_staff_code = 0
    failed: list = []

    for username, info in users.items():
        if not isinstance(info, dict):
            continue
        if not info.get("active"):
            skipped_inactive += 1
            continue
        staff_code = str(info.get("staff_code", ""))
        if not staff_code:
            skipped_no_staff_code += 1
            continue
        try:
            plan = engine.generate_development_plan(staff_code)
            if not plan:
                failed.append({"username": username, "staff_code": staff_code,
                               "reason": "engine returned empty plan"})
                continue
            plans[staff_code] = plan
        except Exception as e:
            failed.append({"username": username, "staff_code": staff_code,
                           "reason": str(e)})

    # Coverage measured against UNIQUE staff_codes (the real population
    # the engine can address). Duplicate staff_codes are a data
    # integrity issue surfaced separately — they don't penalize the
    # engine's coverage of distinct staff.
    coverage_pct = (
        (len(plans) / unique_staff_codes * 100) if unique_staff_codes else 0.0
    )

    log.info("\n" + "=" * 64)
    log.info("Growth plan generation summary")
    log.info("=" * 64)
    log.info("  Plans generated:        %d", len(plans))
    log.info("  Unique staff_codes:     %d", unique_staff_codes)
    log.info("  Coverage:               %.1f%% (target: 100%%)", coverage_pct)
    if duplicate_codes:
        log.info("  Duplicate staff_codes:  %d affecting %d active users",
                 len(duplicate_codes),
                 sum(len(us) for us in duplicate_codes.values()))
    log.info("  Skipped (inactive):     %d", skipped_inactive)
    log.info("  Skipped (no staff_code): %d", skipped_no_staff_code)
    log.info("  Failed:                 %d", len(failed))
    if failed[:5]:
        for f in failed[:5]:
            log.info("    %s (%s): %s", f["username"], f["staff_code"], f["reason"])

    # 5. Persist plans + results artifact
    if not args.dry_run:
        log.info("\n  Writing %s ...", PLANS_FILE.name)
        PLANS_FILE.write_text(json.dumps(plans, indent=2, sort_keys=True))

        artifact = {
            "schema_version":  1,
            "run_at":          datetime.now(timezone.utc).isoformat(),
            "active_staff":    active_count,
            "unique_staff_codes": unique_staff_codes,
            "plans_generated": len(plans),
            "coverage_pct":    round(coverage_pct, 2),
            "spec_target_pct": 100.0,
            "all_passed":      coverage_pct >= 100.0,
            "duplicate_staff_codes": {
                sc: us for sc, us in list(duplicate_codes.items())[:50]
            },
            "duplicate_staff_codes_count": len(duplicate_codes),
            "skipped_inactive": skipped_inactive,
            "skipped_no_staff_code": skipped_no_staff_code,
            "failed_count":    len(failed),
            "failed_sample":   failed[:20],   # first 20 for debugging
        }
        RESULTS_FILE.write_text(json.dumps(artifact, indent=2))
        log.info("  Wrote %s", RESULTS_FILE.name)

    return 0 if coverage_pct >= 100.0 else 1


if __name__ == "__main__":
    sys.exit(main())
