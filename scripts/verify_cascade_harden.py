#!/usr/bin/env python3
"""scripts/verify_cascade_harden.py — in-process proof of the CascadeManager
hardening, using TEMP files only (never mutates real config).

    python scripts\\verify_cascade_harden.py
"""
import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.core import CascadeManager

cm = CascadeManager()

# 1) real config loaded as dicts (non-destructive read)
assert isinstance(cm.cascade, dict), "cascade not a dict"
assert isinstance(cm.bank_targets, dict), "bank_targets not a dict"
assert isinstance(cm.fixed_kpis, dict), "fixed_kpis not a dict"
print(f"real load OK: cascade={len(cm.cascade)} keys, bank={len(cm.bank_targets)}, fixed={len(cm.fixed_kpis)}")

with tempfile.TemporaryDirectory() as td:
    tdp = Path(td)

    # 2) atomic write round-trips
    p = tdp / "rt.json"
    payload = {"a|PBT|2026": {"total": 1, "alloc": [1, 2, 3]}, "deadline|x|2026": {"t": "deadline"}}
    cm._atomic_write_json(p, payload)
    assert json.loads(p.read_text()) == payload, "atomic round-trip mismatch"
    print("atomic write round-trip OK")

    # 3) missing file -> seeds + returns empty (no raise)
    miss = tdp / "missing.json"
    out = cm._safe_load_json(miss, {})
    assert out == {} and miss.exists(), "missing-file seed failed"
    print("missing-file seed OK")

    # 4) valid file -> returns its dict
    val = tdp / "valid.json"
    val.write_text(json.dumps({"k": 1}), encoding="utf-8")
    assert cm._safe_load_json(val, {}) == {"k": 1}
    print("valid-file load OK")

    # 5) NON-EMPTY corrupt file -> RAISES (the critical anti-wipe behaviour)
    bad = tdp / "corrupt.json"
    bad.write_text("{this is : not json,,,", encoding="utf-8")
    raised = False
    try:
        cm._safe_load_json(bad, {})
    except RuntimeError:
        raised = True
    assert raised, "FAIL: corrupt non-empty file did NOT raise (would risk a wipe)"
    print("corrupt-file RAISES (no silent {} -> no wipe) OK")

    # 6) empty file -> returns empty (legitimate)
    emp = tdp / "empty.json"
    emp.write_text("   ", encoding="utf-8")
    assert cm._safe_load_json(emp, {}) == {}
    print("empty-file -> {} OK")

print("ALL CASCADE-HARDEN VERIFY CHECKS PASSED")
