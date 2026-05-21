"""scripts/rebaseline_g162.py — Re-baseline G162 after a cleanup batch.

Run after each cleanup batch that reduces G162's count. Encapsulates the
multi-step ritual into one command.

USAGE
    python scripts/rebaseline_g162.py
    python scripts/rebaseline_g162.py --version v10.224 --note "cleanup of X"

WHAT IT DOES
    1. Reads current G162 baseline from data/audit_baselines.json
    2. Saves the existing scope_history list
    3. Deletes the g162_tenant_hardcoding key
    4. Runs `python scripts/audit.py` so G162 re-establishes baseline at
       its current authoritative count
    5. Re-attaches scope_history with a new entry for this batch

The ritual is deliberately not automatic — kaizen discipline says scope
expansions and reductions should be intentional operator acts, not silent.
This script just removes the typing-busywork so the operator can focus on
the cleanup itself.

Per master prompt addendum Rule N5 — ratchets, not heroics. This helper
preserves the audit trail (scope_history) so every reduction has a clear
provenance.
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
BASELINE_PATH = ROOT / "data/audit_baselines.json"
BASELINE_KEY = "g162_tenant_hardcoding"


def main():
    parser = argparse.ArgumentParser(
        description="Re-baseline G162 after a cleanup batch.")
    parser.add_argument(
        "--version", default=None,
        help="Batch version, e.g. v10.224. Defaults to today's date.")
    parser.add_argument(
        "--note", default=None,
        help="Free-text note describing the cleanup. Required if --version "
             "is set; auto-generated otherwise.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen without modifying files.")
    args = parser.parse_args()

    if not BASELINE_PATH.exists():
        print(f"ERROR: {BASELINE_PATH} does not exist. Run audit first.",
              file=sys.stderr)
        return 1

    baselines = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if BASELINE_KEY not in baselines:
        print(f"ERROR: {BASELINE_KEY} key not in {BASELINE_PATH}. "
              f"Run audit to establish initial baseline.", file=sys.stderr)
        return 1

    old_entry = baselines[BASELINE_KEY]
    old_total = old_entry.get("total")
    old_per_token = old_entry.get("per_token", {})
    history = old_entry.get("scope_history", [])

    print(f"Current baseline: {old_total} "
          f"({sum(old_per_token.values())} from per_token sum)")
    print(f"  Per token: {old_per_token}")
    print(f"  Scope history entries: {len(history)}")

    if args.dry_run:
        print("\n[DRY RUN] Would clear key and re-establish via audit.")
        return 0

    # Step 1: Delete the key so audit re-establishes
    del baselines[BASELINE_KEY]
    BASELINE_PATH.write_text(
        json.dumps(baselines, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print("\n✅ Step 1: Cleared baseline key")

    # Step 2: Run audit so G162 re-establishes at authoritative count
    print("\n✅ Step 2: Running audit to re-establish baseline...")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/audit.py")],
        capture_output=True, text=True, cwd=str(ROOT))
    if result.returncode != 0:
        print("WARNING: audit returned non-zero", file=sys.stderr)
    # Read the new baseline
    baselines = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    new_entry = baselines.get(BASELINE_KEY, {})
    new_total = new_entry.get("total")
    new_per_token = new_entry.get("per_token", {})

    print(f"   New baseline: {new_total}")
    print(f"   Per token:    {new_per_token}")

    # Step 3: Re-attach scope_history with a new entry
    delta = (new_total - old_total) if old_total is not None else 0
    version = args.version or f"manual-{datetime.date.today().isoformat()}"
    note = args.note or (
        f"Re-baseline after cleanup batch ({delta:+d} from {old_total} "
        f"to {new_total}).")
    history.append({
        "version": version,
        "total": new_total,
        "tokens": list(new_per_token.keys()),
        "note": note,
    })
    new_entry["scope_history"] = history
    new_entry["established_in"] = version
    baselines[BASELINE_KEY] = new_entry
    BASELINE_PATH.write_text(
        json.dumps(baselines, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print(f"\n✅ Step 3: Re-attached scope_history with {version} entry")

    # Step 4: Verify
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/audit.py")],
        capture_output=True, text=True, cwd=str(ROOT))
    last_lines = result.stdout.strip().split("\n")[-3:]
    print()
    for line in last_lines:
        print(f"   {line}")

    print(f"\n✨ Re-baseline complete. {old_total} → {new_total} ({delta:+d}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
