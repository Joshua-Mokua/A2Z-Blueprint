#!/usr/bin/env bash
# scripts/measure_coverage.sh — Run pytest with coverage and produce
# coverage.xml + an HTML report.
#
# v10.97 — Phase 1C kickoff. The audit script's G18 gate parses
# coverage.xml; SCOPE_LEDGER's Phase 1C section reports against this.
#
# Prerequisites:
#   pip install --break-system-packages pytest pytest-cov coverage
#
# Usage (from repo root):
#   ./scripts/measure_coverage.sh                      # full suite
#   ./scripts/measure_coverage.sh tests/test_api_*.py  # subset
#   ./scripts/measure_coverage.sh -m "not slow"        # filter by marker
#
# Outputs:
#   coverage.xml         (cobertura format — G18 audit gate parses this)
#   htmlcov/index.html   (human-readable report)
#   .coverage            (raw data file for combining/incremental runs)
#
# After this script runs, re-run the audit to see G18's verdict:
#   python3 scripts/audit.py | grep G18
#
# Or check the headline numbers:
#   python3 scripts/audit_completion_state.py | grep -A 8 "Test coverage"

set -euo pipefail

cd "$(dirname "$0")/.."

# Defaults can be overridden by passing arguments to this script
EXTRA_ARGS=("$@")

if [[ ${#EXTRA_ARGS[@]} -eq 0 ]]; then
    EXTRA_ARGS=("tests/")
fi

echo "▶ Running pytest with coverage on: ${EXTRA_ARGS[*]}"
echo

# .coveragerc handles source/omit configuration; we just pass --cov flags
pytest \
    --cov \
    --cov-report=xml \
    --cov-report=html \
    --cov-report=term-missing:skip-covered \
    "${EXTRA_ARGS[@]}" \
    || EXIT_CODE=$?

EXIT_CODE=${EXIT_CODE:-0}

echo
echo "▶ Coverage artifacts:"
[[ -f coverage.xml ]] && \
    echo "  ✓ coverage.xml ($(wc -l <coverage.xml) lines)" || \
    echo "  ✗ coverage.xml MISSING"
[[ -d htmlcov ]] && \
    echo "  ✓ htmlcov/ ($(find htmlcov -type f -name '*.html' | wc -l) HTML files)" || \
    echo "  ✗ htmlcov/ MISSING"

echo
echo "▶ Re-run audit to surface G18 verdict:"
echo "  python3 scripts/audit.py | grep G18"
echo
echo "▶ Phase 1C state report:"
echo "  python3 scripts/audit_completion_state.py | grep -A 12 'Test coverage'"

exit $EXIT_CODE
