"""org_validator.py — resolve the LINE MANAGER who validates a deal owner's
reopen / hold request (Phase V).

STRICTLY READ-ONLY. This module never writes to the staff register, the role
hierarchy, or any config — it only reads the register to decide who approves.

Confirmed model (grounded on the real staff register, 2026-07-07):
  * 'Reports To' in the register is a ROLE name, resolved to a PERSON within
    the owner's unit (then region, then escalated up the chain).
  * A BRANCH deal owner (RM / RO / DSA — anyone whose unit is a branch, not
    Head Office) is validated by the BRANCH MANAGER of that branch. This
    reflects the bank's model: the whole branch sales team rolls up to the
    branch manager. "Branch Manager" also matches "Senior Branch Manager".
  * A HEAD OFFICE deal owner is validated by the holder of their 'Reports To'
    role in Head Office.
  * If a validator can't be resolved uniquely, escalate to the role above;
    if still unresolved (or the owner isn't in the register), fall back to
    admin, clearly labelled — so a validation is never routed to the wrong
    person.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd


def _s(v) -> str:
    t = str(v).strip()
    return t[:-2] if t.endswith(".0") else t


# "want role" -> acceptable equivalents (senior / variant spellings)
_ROLE_FAMILIES = {
    "branch manager": {"branch manager", "senior branch manager"},
}

_HEAD_OFFICE = "head office"


def _role_matches(have: str, want: str) -> bool:
    have = have.strip().lower()
    want = want.strip().lower()
    if have == want:
        return True
    fam = _ROLE_FAMILIES.get(want)
    return bool(fam and have in fam)


@lru_cache(maxsize=1)
def _register() -> pd.DataFrame:
    """Load the staff register with its REAL header (row 0). Cached.

    Note: we deliberately read the file directly rather than via
    build_staff_registry(), which reads header=1 and mis-parses this file.
    """
    from utils.core import DATA_DIR
    sr = Path(DATA_DIR) / "staff_register.xlsx"
    if not sr.exists():
        return pd.DataFrame()
    try:
        df = pd.read_excel(sr, sheet_name="Staff Register", header=0)
    except Exception:
        return pd.DataFrame()
    df.columns = [str(c).strip() for c in df.columns]
    for col in ("Staff Code", "Staff Name", "Role", "Unit", "Region", "Reports To"):
        if col in df.columns:
            df[col] = df[col].map(_s)
    return df


def _admin_fallback(reason: str) -> dict:
    return {
        "validator_code": None,
        "validator_name": None,
        "validator_role": None,
        "validator_unit": None,
        "resolved": False,
        "via": reason,
        "admin_fallback": True,
    }


def _found(row) -> dict:
    return {
        "validator_code": _s(row["Staff Code"]),
        "validator_name": _s(row.get("Staff Name", "")),
        "validator_role": _s(row.get("Role", "")),
        "validator_unit": _s(row.get("Unit", "")),
        "resolved": True,
        "via": "",
        "admin_fallback": False,
    }


def _resolve_role_in_unit(df: pd.DataFrame, want_role: str, unit: str,
                          region: str) -> tuple[Optional["pd.Series"], str]:
    """Resolve want_role -> a unique person, escalating up the chain.

    Tries unit -> role-above -> (up to 4 levels). Region is available for
    inherently-regional roles. Returns (row_or_None, how)."""
    cur = want_role
    tried = []
    for level in range(4):
        cand = df[df["Role"].map(lambda r: _role_matches(r, cur)) & (df["Unit"] == unit)]
        if len(cand) == 1:
            return cand.iloc[0], f"unit '{unit}' role '{cur}'" + (f" (escalated {level})" if level else "")
        if len(cand) == 0 and region:
            rc = df[df["Role"].map(lambda r: _role_matches(r, cur)) & (df["Region"] == region)]
            if len(rc) == 1:
                return rc.iloc[0], f"region '{region}' role '{cur}'" + (f" (escalated {level})" if level else "")
        tried.append(f"{cur}@{unit}={len(cand)}")
        # role above = the 'Reports To' of whoever holds cur
        holders = df[df["Role"].map(lambda r: _role_matches(r, cur))]
        nxt = _s(holders.iloc[0]["Reports To"]) if len(holders) else ""
        if not nxt or nxt.lower() == "nan" or nxt == cur:
            break
        cur = nxt
    return None, "unresolved [" + " ; ".join(tried) + "]"


def line_manager_of(staff_code: str) -> dict:
    """Pure reporting-tree line manager: the holder of this person's own
    'Reports To' role in their unit — with NO branch->Branch Manager override.
    Used for daily-log validation, where each person's immediate supervisor
    (Teller -> Branch Operations Supervisor, RO -> Branch RM, ...) validates.
    Same return shape as resolve_validator; read-only, never raises.
    """
    df = _register()
    if df.empty or "Staff Code" not in df.columns:
        return _admin_fallback("staff register unavailable")
    person = df[df["Staff Code"] == _s(staff_code)]
    if person.empty:
        return _admin_fallback(f"staff {staff_code} not in register")
    p = person.iloc[0]
    unit = _s(p.get("Unit", ""))
    region = _s(p.get("Region", ""))
    want = _s(p.get("Reports To", ""))
    if not want or want.lower() == "nan":
        return _admin_fallback("person is top-of-tree (no Reports To)")
    row, how = _resolve_role_in_unit(df, want, unit or _HEAD_OFFICE, region)
    if row is None:
        return _admin_fallback(how + " -> admin fallback")
    res = _found(row)
    res["via"] = how
    return res


# ── Daily-log validators ─────────────────────────────────────────────────────
# RULING (2026-08-08): a BRANCH log is validated by the branch management triad;
# a HEAD OFFICE log is validated by the pure line manager.
#
# The triad role names live in org_config.json, not here — branch titles change
# and a rename must not require a code deploy. The fallback below is only used
# when the key is absent.
_DEFAULT_TRIAD_ROLES = [
    "Branch Manager",
    "Assistant Branch Service & Operations Manager",
    "Customer Service Manager",
]


def _triad_roles() -> list:
    """Branch roles permitted to validate daily logs, from org_config.json."""
    try:
        from utils.config import load_org_config
        roles = load_org_config().get("daily_log_branch_validator_roles")
        if isinstance(roles, list) and roles:
            return [str(r) for r in roles if str(r).strip()]
    except Exception:
        pass
    return list(_DEFAULT_TRIAD_ROLES)


def _acting_bm_for(unit: str) -> str:
    """org_config.acting_bm covers branches with no substantive Branch Manager
    (11 BMs across 17 branches). Returns a staff code or ''."""
    try:
        from utils.config import load_org_config
        acting = load_org_config().get("acting_bm") or {}
        for k, v in acting.items():
            if _s(k).lower() == _s(unit).lower():
                return _s(v)
    except Exception:
        pass
    return ""


def daily_log_validators_for(staff_code: str) -> dict:
    """Who may validate this person's DAILY LOG.

    Branch staff  -> every holder of a triad role in their own unit, plus the
                     acting Branch Manager where org_config names one.
    Head Office    -> the pure reporting-tree line manager (line_manager_of).

    Returns {"mode": "triad"|"line_manager", "unit": str,
             "validators": [{validator_code, validator_name, validator_role,
                             validator_unit, ...}]}
    Read-only; never raises. An empty validators list means "unresolved" and the
    caller should fall back to admin, exactly as resolve_validator does.
    """
    df = _register()
    if df.empty or "Staff Code" not in df.columns:
        return {"mode": "line_manager", "unit": "",
                "validators": [_admin_fallback("staff register unavailable")]}

    person = df[df["Staff Code"] == _s(staff_code)]
    if person.empty:
        return {"mode": "line_manager", "unit": "",
                "validators": [_admin_fallback(f"staff {staff_code} not in register")]}

    p = person.iloc[0]
    unit = _s(p.get("Unit", ""))

    # Head Office (and anyone with no unit) keeps the line-manager model.
    if not unit or unit.lower() == _HEAD_OFFICE:
        return {"mode": "line_manager", "unit": unit,
                "validators": [line_manager_of(staff_code)]}

    wanted = _triad_roles()
    out, seen = [], set()
    for _, row in df.iterrows():
        if _s(row.get("Unit", "")).lower() != unit.lower():
            continue
        have = _s(row.get("Role", ""))
        if not any(_role_matches(have, w) for w in wanted):
            continue
        code = _s(row.get("Staff Code", ""))
        if code and code not in seen and code != _s(staff_code):
            seen.add(code)
            out.append(_found(row))

    acting = _acting_bm_for(unit)
    if acting and acting not in seen:
        hit = df[df["Staff Code"] == acting]
        if not hit.empty:
            rec = _found(hit.iloc[0])
            rec["via"] = "acting BM for %s" % unit
            out.append(rec)
            seen.add(acting)

    if not out:
        # No triad member in this branch — fall back to the line manager rather
        # than leaving the log unvalidatable.
        return {"mode": "line_manager", "unit": unit,
                "validators": [line_manager_of(staff_code)]}

    return {"mode": "triad", "unit": unit, "validators": out}


def can_validate_daily_log(validator_code: str, staff_code: str) -> bool:
    """True when validator_code is permitted to validate staff_code's daily log."""
    vc = _s(validator_code)
    if not vc:
        return False
    res = daily_log_validators_for(staff_code)
    return any(_s(v.get("validator_code")) == vc for v in res.get("validators", []))


def resolve_validator(owner_code: str) -> dict:
    """Return the validator for a deal owner.

    dict: {validator_code, validator_name, validator_role, validator_unit,
           resolved: bool, via: str, admin_fallback: bool}
    Read-only; never raises for missing data — returns an admin fallback.
    """
    df = _register()
    if df.empty or "Staff Code" not in df.columns:
        return _admin_fallback("staff register unavailable")
    owner = df[df["Staff Code"] == _s(owner_code)]
    if owner.empty:
        return _admin_fallback(f"owner {owner_code} not in register")
    o = owner.iloc[0]
    unit = _s(o.get("Unit", ""))
    region = _s(o.get("Region", ""))
    role = _s(o.get("Role", ""))

    if not unit or unit.lower() == _HEAD_OFFICE:
        # Head Office deal owner -> holder of their 'Reports To' role.
        want = _s(o.get("Reports To", ""))
        if not want or want.lower() == "nan":
            return _admin_fallback("owner is top-of-tree (no Reports To)")
        row, how = _resolve_role_in_unit(df, want, unit or _HEAD_OFFICE, region)
    else:
        # Branch deal owner -> the Branch Manager of their branch.
        row, how = _resolve_role_in_unit(df, "Branch Manager", unit, region)

    if row is None:
        return _admin_fallback(how + " -> admin fallback")
    res = _found(row)
    res["via"] = how
    return res
