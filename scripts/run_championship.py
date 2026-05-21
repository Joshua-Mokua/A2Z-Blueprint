#!/usr/bin/env python3
"""Run the championship readiness battery with streaming output."""
import json
import sys
import time
from pathlib import Path
from datetime import datetime

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# Reset all simulator state before starting
for k in list(sys.modules):
    if any(s in k for s in ('cert', 'arena', 'agents', 'ml', 'chaos',
                              'channels', 'event_bus', 'simulation',
                              'tick', 'macro', 'scenarios', 'audit')):
        del sys.modules[k]

from utils.cert.championship import (
    build_championship_full, CHAMPIONSHIP_CHECKLIST, ChampionshipReport,
)
from utils.cert.base import CertReport
from utils.cert.certifier import Certifier, _reset_singletons, _normalise_check_result
from utils.cert.base import CheckOutcome

proto = build_championship_full()
print(f"Championship protocol: {proto.check_count()} checks across "
      f"{len(proto.organs())} organs")
print(f"Organs: {proto.organs()}")
print()

# Stream-run each check, write incremental results to disk
outcomes = []
results_path = REPO / "data" / "cert_reports" / "championship_stream.json"
results_path.parent.mkdir(parents=True, exist_ok=True)

started_at = datetime.utcnow().isoformat()
batch_start = time.time()

for i, check in enumerate(proto.checks, 1):
    _reset_singletons()
    t0 = time.time()
    try:
        raw = check.fn()
        norm = _normalise_check_result(raw)
        outcome = CheckOutcome(
            name=check.name, organ=check.organ,
            passed=norm["passed"],
            duration_ms=(time.time() - t0) * 1000.0,
            note=norm["note"], metrics=norm["metrics"],
            critical=check.critical,
        )
    except Exception as exc:
        import traceback
        outcome = CheckOutcome(
            name=check.name, organ=check.organ,
            passed=False,
            duration_ms=(time.time() - t0) * 1000.0,
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[:300]}",
            critical=check.critical,
        )
    flag = "✓" if outcome.passed else "✗"
    elapsed = time.time() - batch_start
    print(f"  [{i:2}/{proto.check_count()}] {flag} {check.name:55} "
          f"{outcome.duration_ms:7.0f}ms  [elapsed {elapsed:5.1f}s]")
    if not outcome.passed:
        snippet = (outcome.note or outcome.error[:200] or "")[:200]
        print(f"             ↳ {snippet}")
    outcomes.append(outcome)
    # Stream save
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump([o.to_dict() for o in outcomes], f, indent=2)

# Build cert report
finished_at = datetime.utcnow().isoformat()
cert_report = CertReport(
    protocol_name="championship_full",
    started_at=started_at,
    finished_at=finished_at,
    duration_seconds=time.time() - batch_start,
)
for o in outcomes:
    cert_report.outcomes.append(o)
    bucket = cert_report.by_organ.setdefault(o.organ, {"total": 0, "passed": 0})
    bucket["total"] += 1
    cert_report.total_checks += 1
    if o.passed:
        bucket["passed"] += 1
        cert_report.passed_checks += 1
    else:
        cert_report.failed_checks += 1
        if o.critical:
            cert_report.critical_failures += 1

# Build checklist verdicts
outcome_by_name = {o.name: o for o in outcomes}
checklist_verdicts = {}
for item in CHAMPIONSHIP_CHECKLIST:
    backing = [outcome_by_name.get(n) for n in item.check_names]
    missing = [n for n, o in zip(item.check_names, backing) if o is None]
    if missing:
        checklist_verdicts[item.item_id] = {
            "passed": False, "evidence": "",
            "why_failed": f"backing check(s) missing: {missing}",
        }
        continue
    passed = all(o.passed for o in backing if o is not None)
    evid = " | ".join(f"`{o.name}`: {o.note or 'ok'}"
                       for o in backing if o is not None and o.passed)
    why = " | ".join(
        f"`{o.name}` failed: {o.note or o.error[:200] or ''}"
        for o in backing if o is not None and not o.passed
    )
    checklist_verdicts[item.item_id] = {
        "passed": passed,
        "evidence": evid if passed else "",
        "why_failed": why if not passed else "",
    }

report = ChampionshipReport(cert_report=cert_report,
                              checklist_verdicts=checklist_verdicts)

# Persist final report
final_path = REPO / "data" / "cert_reports" / f"championship_full_{started_at.replace(':', '-').replace('.', '-')}.json"
with open(final_path, "w", encoding="utf-8") as f:
    json.dump(report.to_dict(), f, indent=2, default=str)
print(f"\nFinal report: {final_path}")

# Write markdown
md_path = REPO / "data" / "cert_reports" / "championship_readiness_report.md"
md_path.write_text(report.checklist_markdown(), encoding="utf-8")
print(f"Markdown:     {md_path}")

print()
print("=" * 75)
print(report.summary_line())
print("=" * 75)
