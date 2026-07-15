"""Projection: PostgreSQL ``users`` -> ``data/staff_register.xlsx``.

DOCTRINE
--------
PostgreSQL ``users`` is the SYSTEM OF RECORD for staff data. It is the only place
staff are written (Admin -> Staff, and the Excel upload).

``staff_register.xlsx`` is a GENERATED PROJECTION. Ten modules still read it
directly (scoping, core, core_audit, org_validator, BSC audit + cascade, HR
actuals, staff onboarding/exit), so it is rebuilt from the DB after every staff
mutation and the roster cache is invalidated.

It must NEVER be hand-edited and NEVER treated as a source. Any code that writes
it outside this module is a bug — that divergence is what silently emptied every
scoped view before (see OPERATIONAL_PROTOCOL trap: the two-catalog trap).
"""
import json
import os
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data"
REGISTER = _DATA / "staff_register.xlsx"

_COLS = ["Staff Code", "Staff Name", "Role", "Unit", "Department", "Branch",
         "Region", "Reports To Code", "Email", "Band", "Gender"]
_SELECT = ("staff_code", "full_name", "role", "department", "unit",
           "email", "band", "gender", "metadata")


def _branch_region_map() -> dict:
    try:
        cfg = json.loads((_DATA / "org_config.json").read_text(encoding="utf-8"))
        return {str(b.get("name") or ""): str(b.get("region") or "")
                for b in cfg.get("branches", []) if b.get("name")}
    except Exception:
        return {}


def _as_dict(row) -> dict:
    """db.fetch_all may yield dict-likes or plain sequences — handle both."""
    try:
        return {k: row[k] for k in _SELECT}
    except Exception:
        return dict(zip(_SELECT, list(row)))


def export_register_from_db() -> int:
    """Rebuild staff_register.xlsx from the users table. Returns rows written.

    Never raises: a projection failure must not break the mutation that triggered
    it, but it IS logged loudly because the register is then stale.
    """
    import pandas as pd
    from utils.db import db as _db

    rows = _db.fetch_all(
        f"SELECT {', '.join(_SELECT)} FROM users "
        "WHERE active = true AND staff_code IS NOT NULL AND staff_code <> '' "
        "ORDER BY staff_code"
    ) or []
    breg = _branch_region_map()

    out = []
    for raw in rows:
        d = _as_dict(raw)
        meta = d.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        unit = str(d.get("unit") or "").strip()
        # the upload stores the branch in `unit`; it is only a branch if it names one
        branch = unit if unit in breg else ""
        out.append({
            "Staff Code": str(d.get("staff_code") or ""),
            "Staff Name": str(d.get("full_name") or ""),
            "Role": str(d.get("role") or ""),
            "Unit": unit,
            "Department": str(d.get("department") or meta.get("department") or ""),
            "Branch": branch,
            "Region": str(meta.get("region") or breg.get(branch, "") or ""),
            "Reports To Code": str(meta.get("reports_to") or ""),
            "Email": str(d.get("email") or ""),
            "Band": str(d.get("band") or ""),
            "Gender": str(d.get("gender") or ""),
        })

    _DATA.mkdir(exist_ok=True)
    tmp = REGISTER.with_name(REGISTER.name + ".tmp")
    pd.DataFrame(out, columns=_COLS).to_excel(tmp, index=False)
    os.replace(tmp, REGISTER)      # atomic: readers never see a half-written file

    try:
        from utils.api_pipeline_scope import invalidate_staff_roster_cache
        invalidate_staff_roster_cache()
    except Exception:
        pass
    return len(out)


def project_quietly() -> None:
    """Best-effort projection for call sites that must not fail on it."""
    try:
        n = export_register_from_db()
        print(f"[staff_projection] register rebuilt from DB: {n} rows")
    except Exception as exc:
        print(f"[staff_projection] PROJECTION FAILED — register is now STALE: {exc}")
