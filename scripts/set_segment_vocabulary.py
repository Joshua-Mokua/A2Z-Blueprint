#!/usr/bin/env python3
"""
set_segment_vocabulary.py  —  CONFIG mutation (backup-first). No deal data touched.

Makes the admin segment config the single source of truth for Analytics:

  1. customer_segments  (deal-form options) -> canonical Ecobank vocabulary,
     dropping the legacy Individual / Business orphan keys. Consumer = the three
     tiers only (Premier / Advantage / Direct); add more later from Admin Config.

  2. segment_labels  (Analytics display/alias map) -> folds the historical
     generated-data segment values onto the canonical vocabulary, so by_segment
     shows clean buckets WITHOUT re-tagging a single deal. `_segment_of` already
     applies this map, so this is purely presentation.

Writes data/pipeline_settings.json. Backs the file up first to
data/pipeline_settings.json.pre-segmentvocab-<timestamp>.

Run:
    python scripts\\set_segment_vocabulary.py            (apply)
    python scripts\\set_segment_vocabulary.py --dry-run  (show, write nothing)
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

# import the SAME helpers the API uses, so we hit the exact same file/path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.core import DATA_DIR, get_pipeline_settings, save_pipeline_settings  # noqa: E402

# ── Canonical vocabulary ────────────────────────────────────────────────
CANONICAL_CUSTOMER_SEGMENTS = {
    "Consumer":   ["Premier", "Advantage", "Direct"],
    "Commercial": ["Large Corporate", "Corporate", "SME", "Micro Enterprise"],
    "CIB":        ["Multinational", "Large Local Corporate",
                   "Financial Institution", "Public Sector"],
}

# Historical / generated segment values -> canonical bucket. The first three are
# the pre-existing Ecobank base-key aliases; the rest fold the demo data in.
SEGMENT_ALIASES = {
    "Mass / Retail":        "Direct",
    "Core Middle":          "Advantage",
    "Affluent":             "Premier",
    "Mass Market":          "Direct",
    "Youth":                "Direct",
    "Salaried":             "Advantage",
    "Self-Employed":        "Advantage",
    "Diaspora":             "Premier",
    "Corporate / Business": "Corporate",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    settings = get_pipeline_settings()
    before_cust = settings.get("customer_segments") or {}
    before_labels = settings.get("segment_labels") or {}

    print("BEFORE")
    print("  customer_segments keys:", ", ".join(before_cust.keys()) or "(none)")
    print("  segment_labels entries:", len(before_labels))

    # merge aliases over any existing labels (existing wins only if not in our map)
    new_labels = {**before_labels, **SEGMENT_ALIASES}
    new_cust = dict(CANONICAL_CUSTOMER_SEGMENTS)

    if args.dry_run:
        print("\n--dry-run: would write:")
        print("  customer_segments:", json.dumps(new_cust, indent=2))
        print("  segment_labels:   ", json.dumps(new_labels, indent=2))
        print("\n(no file written)")
        return

    # backup first
    f = DATA_DIR / "pipeline_settings.json"
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if f.exists():
        bak = DATA_DIR / f"pipeline_settings.json.pre-segmentvocab-{ts}"
        bak.write_text(f.read_text())
        print(f"\nbackup -> {bak.name}")

    settings["customer_segments"] = new_cust
    settings["segment_labels"] = new_labels
    save_pipeline_settings(settings)

    print("\nAFTER")
    print("  customer_segments keys:", ", ".join(new_cust.keys()))
    print("  segment_labels entries:", len(new_labels))
    print("\nDone. Settings are read fresh from disk, so no API restart is needed.")
    print("Re-run:  python scripts\\diag_segment_alignment.py   to confirm.")


if __name__ == "__main__":
    main()
