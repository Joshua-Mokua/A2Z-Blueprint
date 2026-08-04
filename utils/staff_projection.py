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
           "email", "metadata")


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
            "Band": str(meta.get("band") or ""),
            "Gender": str(meta.get("gender") or ""),
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


def export_logins_from_db(keep=("william001", "admin")) -> dict:
    """Rebuild data/users.json (the LOGIN store) from the users table.

    The register projection gives uploaded staff a position in the org tree, but
    authentication reads users.json — so without this they exist in the hierarchy
    and still cannot sign in.

    Rules:
      * users in `keep` are never touched (your test logins keep their passwords)
      * NEW people get a login with the standard convention: EcoStaff<last 4 of code>
      * EXISTING people have role / unit / staff_code / active refreshed, and their
        PASSWORD IS LEFT ALONE — a projection must never reset someone's credentials
      * people no longer in the DB are DEACTIVATED, not deleted (audit trail)

    Returns {"added": n, "updated": n, "deactivated": n}.
    """
    from utils.db import db as _db
    from utils.core import UserManager

    rows = _db.fetch_all(
        "SELECT username, full_name, email, role, department, unit, staff_code, "
        "active, is_admin, can_view_all FROM users WHERE staff_code IS NOT NULL "
        "AND staff_code <> ''"
    ) or []
    um = UserManager()
    keep = set(keep or ())
    added = updated = deactivated = 0
    seen = set()

    for raw in rows:
        try:
            d = {k: raw[k] for k in ("username", "full_name", "email", "role", "department",
                                     "unit", "staff_code", "active", "is_admin", "can_view_all")}
        except Exception:
            d = dict(zip(("username", "full_name", "email", "role", "department", "unit",
                          "staff_code", "active", "is_admin", "can_view_all"), list(raw)))
        un = str(d.get("username") or "").strip()
        if not un or un in keep:
            continue
        seen.add(un)
        code = str(d.get("staff_code") or "")
        existing = um.users.get(un)
        if existing:
            existing["full_name"] = d.get("full_name") or existing.get("full_name")
            existing["role"] = d.get("role") or existing.get("role")
            existing["unit"] = d.get("unit") or existing.get("unit")
            existing["department"] = d.get("department") or existing.get("department")
            existing["staff_code"] = code
            existing["active"] = bool(d.get("active", True))
            existing["is_admin"] = bool(d.get("is_admin"))
            existing["can_view_all"] = bool(d.get("can_view_all"))
            updated += 1                      # password deliberately untouched
        else:
            um.add_user(
                username=un, password=f"EcoStaff{code[-4:]}",
                full_name=d.get("full_name") or un, email=d.get("email") or "",
                role=d.get("role") or "Staff", unit=d.get("unit") or "",
                staff_code=code, can_view_all=bool(d.get("can_view_all")),
                is_admin=bool(d.get("is_admin")),
            )
            added += 1

    for un, u in um.users.items():
        if un in keep or un in seen:
            continue
        if u.get("active"):
            u["active"] = False               # gone from the DB -> deactivate, never delete
            deactivated += 1

    um.save_users()
    return {"added": added, "updated": updated, "deactivated": deactivated}


def project_quietly() -> None:
    """Best-effort projection for call sites that must not fail on it."""
    try:
        n = export_register_from_db()
        print(f"[staff_projection] register rebuilt from DB: {n} rows")
    except Exception as exc:
        print(f"[staff_projection] PROJECTION FAILED — register is now STALE: {exc}")
    try:
        r = export_logins_from_db()
        print(f"[staff_projection] logins: +{r['added']} new, {r['updated']} refreshed, "
              f"{r['deactivated']} deactivated")
    except Exception as exc:
        print(f"[staff_projection] LOGIN PROJECTION FAILED — new staff cannot sign in: {exc}")
