"""scripts/generate_all_docs.py — Living Doc orchestrator CLI (v8.14).

Per docs/A2Z_LIVING_DOCS_PLAN.md Part 4, generates the full set of audit-locked
sales-grade collateral in one command:
    1. A2Z_MIS_360_Brochure.pptx
    2. A2Z_MIS_360_Magazine.pdf
    3. A2Z_MIS_360_Security_Whitepaper.pdf
    4. A2Z_MIS_360_Compliance_Pack.pdf

Each generator validates its claims through scripts.docgen._claim_validator
BEFORE writing output. If any claim diverges from the registry, that generator
aborts and reports a clear diagnostic. Other generators continue.

Usage:
    python -m scripts.generate_all_docs [--out DIR] [--only TARGET]
    python scripts/generate_all_docs.py [--out DIR] [--only TARGET]

Where TARGET is one of: brochure | magazine | security | compliance
(omit --only to generate all four)

Exit codes:
    0 — all targets generated cleanly
    1 — one or more targets aborted (claim divergence or rendering error)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

# Allow running as a script (`python scripts/generate_all_docs.py`) by adding
# the repo root to sys.path. When run as a module, this is a no-op.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _generate_brochure(out_dir: Path) -> Dict[str, Any]:
    from scripts.docgen.ppt_generator import generate_brochure
    return generate_brochure(out_dir / "A2Z_MIS_360_Brochure.pptx")


def _generate_magazine(out_dir: Path) -> Dict[str, Any]:
    from scripts.docgen.magazine_generator import generate_magazine
    return generate_magazine(out_dir / "A2Z_MIS_360_Magazine.pdf")


def _generate_security(out_dir: Path) -> Dict[str, Any]:
    from scripts.docgen.whitepaper_generator import generate_security_whitepaper
    return generate_security_whitepaper(
        out_dir / "A2Z_MIS_360_Security_Whitepaper.pdf")


def _generate_compliance(out_dir: Path) -> Dict[str, Any]:
    from scripts.docgen.whitepaper_generator import generate_compliance_pack
    return generate_compliance_pack(
        out_dir / "A2Z_MIS_360_Compliance_Pack.pdf")


TARGETS: Dict[str, Callable[[Path], Dict[str, Any]]] = {
    "brochure": _generate_brochure,
    "magazine": _generate_magazine,
    "security": _generate_security,
    "compliance": _generate_compliance,
}


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="A2Z Living Documentation orchestrator (v8.14)")
    parser.add_argument(
        "--out", default="generated_docs",
        help="Output directory (default: generated_docs)")
    parser.add_argument(
        "--only", choices=sorted(TARGETS.keys()),
        help="Generate only one target (default: generate all)")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    targets_to_run = [args.only] if args.only else list(TARGETS.keys())

    print(f"A2Z Living Documentation orchestrator (v8.14)")
    print(f"Output directory: {out_dir.resolve()}")
    print(f"Targets: {', '.join(targets_to_run)}")
    print()

    successes = 0
    aborts = 0
    total_claims_validated = 0

    for target in targets_to_run:
        print(f"→ {target}")
        try:
            result = TARGETS[target](out_dir)
        except Exception as e:
            print(f"  ✗ EXCEPTION: {type(e).__name__}: {e}")
            aborts += 1
            continue

        if result.get("status") == "OK":
            output = result.get("output_path", "?")
            claims = result.get("claims_validated", 0)
            try:
                size_kb = Path(output).stat().st_size / 1024
                print(f"  ✓ {output} ({size_kb:.1f}KB; {claims} claims validated)")
            except Exception:
                print(f"  ✓ {output} ({claims} claims validated)")
            successes += 1
            total_claims_validated += claims
        else:
            reason = result.get("reason", "unknown")
            print(f"  ✗ ABORTED: {reason}")
            for f in result.get("failures", []):
                print(f"     {f.get('error', f)}")
            aborts += 1

    print()
    print(f"Summary: {successes}/{len(targets_to_run)} generated, "
          f"{aborts}/{len(targets_to_run)} aborted")
    print(f"Total audit-locked claims validated: {total_claims_validated}")

    return 1 if aborts > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
