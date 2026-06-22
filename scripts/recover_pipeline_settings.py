#!/usr/bin/env python3
"""
recover_pipeline_settings.py — restore the rich pipeline_settings.json.

ROOT CAUSE (2026-06-22): the live pipeline_settings.json was thinned to 3 keys
(disbursement_roles, sla_config, product_flows) — the admin-write surfaces — so
the advance-stage allowlist (which derives 'Application'/'Credit Assessment' ONLY
from stage_flows) went empty and pipeline advance 400'd. The committed copy is
the correct rich baseline (15 keys incl. stage_flows + deal_categories +
product_catalogue).

This restores the committed rich config and MERGES BACK the live override values
that are worth keeping (sla_config, disbursement_roles), so no genuine admin edit
is lost. product_flows is intentionally re-seeded fresh by seed_product_flows.py
AFTER this (the live one was empty anyway).

SAFE: dry-run unless --apply. Backs up the current (thin) file first so nothing
is destroyed.

    python scripts\\recover_pipeline_settings.py            # dry-run
    python scripts\\recover_pipeline_settings.py --apply    # backup thin + write rich
"""
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "data" / "pipeline_settings.json"

# Keys whose LIVE value (admin-overridden) we preserve across the restore.
# product_flows is NOT here — it was empty live and gets re-seeded afterward.
PRESERVE_LIVE = ("sla_config", "disbursement_roles")

# Core keys the rich config MUST have for the app to function.
REQUIRED_CORE = ("stage_flows", "deal_categories", "product_catalogue", "stages")


def committed_config() -> dict:
    """The rich pipeline_settings.json as committed at HEAD."""
    out = subprocess.run(
        ["git", "show", "HEAD:data/pipeline_settings.json"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    if out.returncode != 0:
        print("ERROR: could not read committed config:", out.stderr.strip())
        sys.exit(1)
    return json.loads(out.stdout)


def main():
    apply = "--apply" in sys.argv

    live = {}
    if CFG.exists():
        try:
            live = json.loads(CFG.read_text(encoding="utf-8"))
        except Exception:
            live = {}

    rich = committed_config()

    missing = [k for k in REQUIRED_CORE if k not in rich]
    if missing:
        print(f"ERROR: committed config missing core keys {missing}; aborting.")
        sys.exit(1)

    # Merge: rich baseline + preserved live overrides.
    merged = dict(rich)
    preserved = []
    for k in PRESERVE_LIVE:
        if k in live:
            merged[k] = live[k]
            preserved.append(k)

    print(f"live config currently: {len(live)} keys -> {sorted(live.keys())}")
    print(f"rich committed config: {len(rich)} keys")
    print(f"merged result: {len(merged)} keys")
    print(f"preserved live overrides: {preserved or '(none)'}")
    print(f"core keys restored: {[k for k in REQUIRED_CORE]}")
    print(f"  stage_flows.asset includes 'Application': "
          f"{'Application' in merged.get('stage_flows', {}).get('asset', [])}")

    if not apply:
        print("\n[DRY-RUN] No file written. Re-run with --apply to back up + restore.")
        return

    if CFG.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = CFG.with_name(f"pipeline_settings.json.pre_recover_{ts}")
        backup.write_text(CFG.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"\n[backup] {backup.name} (the thin file, preserved)")

    CFG.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[apply] restored rich config ({len(merged)} keys). "
          "Advance allowlist now includes Application/Credit Assessment.")


if __name__ == "__main__":
    main()
