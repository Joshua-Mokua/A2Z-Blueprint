"""scripts/export_openapi.py — Dump the FastAPI app's OpenAPI spec to stdout.

Usage:
  python scripts/export_openapi.py > docs/openapi.json
  python scripts/export_openapi.py --pretty > docs/openapi.json

This produces a static, version-controllable copy of the API contract.
The live spec at /api/docs (Swagger UI) remains the runtime source of
truth — the static dump is for offline reference, contract testing,
and changelogs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--pretty", action="store_true",
                   help="pretty-print with 2-space indent (default: compact)")
    args = p.parse_args()

    # Import lazily so failures (missing deps) don't crash on -h
    try:
        from utils.api import app
    except Exception as e:
        print(f"ERROR: could not import utils.api: {e}", file=sys.stderr)
        return 1

    spec = app.openapi()
    if args.pretty:
        json.dump(spec, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        json.dump(spec, sys.stdout, separators=(",", ":"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
