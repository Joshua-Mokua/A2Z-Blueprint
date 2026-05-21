#!/usr/bin/env python3
"""Resume the championship readiness battery from a given check index.

Reads existing data/cert_reports/championship_stream.json, runs only
checks not yet completed, appends results, and produces the final
ChampionshipReport.
"""
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

for k in list(sys.modules):
    if any(s in k for s in ('cert', 'arena', 'agents', 'ml', 'chaos',
                              'channels', 'event_bus', 'simulation',
                              'tick', 'macro', 'scenarios', 'audit')):
        del sys.modules[k]

from utils.cert.championship import (
    build_championship_full, CHAMPIONSHIP_CHECKLIST, ChampionshipReport,
)
from utils.cert.base import CertReport, CheckOutcome
from utils.cert.certifier import _reset_singletons, _normalise_check_result


proto = build_championship_full()

# Load existing stream
stream_path = REPO / "data" / "cert_reports" / "championship_stream.json"
done_outcomes = []
done_names = set()
if stream_path.exists():
    with open(stream_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    for r in raw:
        oc = CheckOutcome(
            name=r["name"], organ=r["organ"], passed=r["passed"],
            duration_ms=r["duration_ms"], note=r.get("note", ""),
            metrics=r.get("metrics", {}), error=r.get("error", ""),
            critical=r.get("critical", True),
        )
        done_outcomes.append(oc)
        done_names.add(oc.name)
    print(f"Resuming from {len(done_outcomes)} completed checks")

# Run remaining
remaining = [c for c in proto.checks if c.name not in done_names]
print(f"Remaining: {len(remaining)} checks\n")

started_at = datetime.now(timezone.utc).isoformat()
batch_start = time.time()
all_outcomes = list(done_outcomes)

for i, check in enumerate(remaining, 1):
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
    print(f"  [{i:2}/{len(remaining)}] {flag} {check.name:55} "
          f"{outcome.duration_ms:7.0f}ms  [elapsed {elapsed:5.1f}s]")
    if not outcome.passed:
        snip = (outcome.note or outcome.error[:200])[:200]
        print(f"             ↳ {snip}")
    all_outcomes.append(outcome)
    with open(stream_path, "w", encoding="utf-8") as f:
        json.dump([o.to_dict() for o in all_outcomes], f, indent=2)

print(f"\n{len(all_outcomes)}/{proto.check_count()} total checks complete")
