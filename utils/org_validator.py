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

    # The sheet was named "Staff Register" historically; the live file exports
    # as "Sheet1". Reading only the named sheet raised, was swallowed, and
    # returned an EMPTY frame — which made every validator lookup in this module
    # (daily logs AND deals) fall through to the admin fallback, silently.
    # Try the named sheet, then the first sheet.
    df = pd.DataFrame()
    for sheet in ("Staff Register", 0):
        try:
            df = pd.read_excel(sr, sheet_name=sheet, header=0)
            if df is not None and len(df):
                break
        except Exception:
            continue
    if df is None or df.empty:
        return pd.DataFrame()

    df.columns = [str(c).strip() for c in df.columns]

    # Column aliases: the live register carries "Reports To Code" (a staff code)
    # and a separate "Branch" alongside "Unit". Normalise without renaming the
    # source file.
    if "Reports To" not in df.columns and "Reports To Code" in df.columns:
        df["Reports To"] = df["Reports To Code"]
    if "Unit" not in df.columns and "Branch" in df.columns:
        df["Unit"] = df["Branch"]

    for col in ("Staff Code", "Staff Name", "Role", "Unit", "Branch",
                "Department", "Region", "Reports To", "Reports To Code"):
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

    # The live register stores "Reports To Code" — an actual staff code — where
    # older exports stored a ROLE NAME. A direct code lookup is both cheaper and
    # exact, so prefer it and keep the role-resolution path as the fallback.
    direct = df[df["Staff Code"] == want]
    if not direct.empty:
        res = _found(direct.iloc[0])
        res["via"] = "reports-to code"
        return res

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
    # The register carries BOTH Branch and Unit. Branch is the physical site
    # the triad belongs to; Unit can hold a department on some rows.
    unit = _s(p.get("Branch", "")) or _s(p.get("Unit", ""))

    # Head Office (and anyone with no unit) keeps the line-manager model.
    if not unit or unit.lower() == _HEAD_OFFICE:
        return {"mode": "line_manager", "unit": unit,
                "validators": [line_manager_of(staff_code)]}

    wanted = _triad_roles()
    out, seen = [], set()
    for _, row in df.iterrows():
        row_branch = _s(row.get("Branch", "")) or _s(row.get("Unit", ""))
        if row_branch.lower() != unit.lower():
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


def staff_validated_by(validator_code: str) -> dict:
    """INVERSE of daily_log_validators_for: whose daily logs may this person
    validate? One register scan.

    Asking the forward question per staff member is O(n^2) — the queue endpoint
    did exactly that across 363 staff and hung. This answers it once:

      * a triad-role holder in a BRANCH validates everyone in that branch
        (plus any branch they are the acting BM for)
      * anyone else validates their direct reports (Reports To == their code)

    Returns {"mode": "triad"|"line_manager"|"", "codes": [staff_code, ...]}.
    """
    df = _register()
    vc = _s(validator_code)
    if df.empty or not vc or "Staff Code" not in df.columns:
        return {"mode": "", "codes": []}

    me = df[df["Staff Code"] == vc]
    if me.empty:
        return {"mode": "", "codes": []}
    m = me.iloc[0]
    my_branch = _s(m.get("Branch", "")) or _s(m.get("Unit", ""))
    my_role = _s(m.get("Role", ""))

    wanted = _triad_roles()
    is_triad_role = any(_role_matches(my_role, w) for w in wanted)

    # Branches this person covers as a triad member or as acting BM.
    branches = set()
    if is_triad_role and my_branch and my_branch.lower() != _HEAD_OFFICE:
        branches.add(my_branch.lower())
    try:
        from utils.config import load_org_config
        for bname, acting in (load_org_config().get("acting_bm") or {}).items():
            if _s(acting) == vc:
                branches.add(_s(bname).lower())
    except Exception:
        pass

    # Vectorised on purpose: iterrows() over the register per request is what
    # made the queue hang. These are boolean masks, not Python loops.
    codes_col = df["Staff Code"].astype(str).str.strip()
    not_me = codes_col != vc

    if branches:
        if "Branch" in df.columns:
            bcol = df["Branch"].astype(str).str.strip()
            if "Unit" in df.columns:
                bcol = bcol.where(bcol.str.len() > 0, df["Unit"].astype(str).str.strip())
        else:
            bcol = df["Unit"].astype(str).str.strip()
        mask = bcol.str.lower().isin(branches) & not_me
        return {"mode": "triad",
                "codes": [c for c in codes_col[mask].tolist() if c]}

    if "Reports To" in df.columns:
        mask = (df["Reports To"].astype(str).str.strip() == vc) & not_me
        return {"mode": "line_manager",
                "codes": [c for c in codes_col[mask].tolist() if c]}

    return {"mode": "line_manager", "codes": []}


def branches_validated_by(validator_code: str) -> dict:
    """TIER 2: which BRANCHES may this person validate (not individuals)?

    Ruling 2026-08-08: a Branch Manager validates the individuals and closes the
    branch day; the Head of Branches validates the BRANCH SUBMISSION and may
    return it to the BM. Two tiers, two different objects.

    A branch belongs to this caller when the caller is the line manager of that
    branch's triad head (its Branch Manager), or when the caller holds an
    all-view role, in which case every branch is theirs.

    Returns {"mode": "branch"|"", "branches": [name, ...], "all_view": bool}.
    Vectorised — one register pass, no per-branch resolution.
    """
    df = _register()
    vc = _s(validator_code)
    if df.empty or not vc or "Staff Code" not in df.columns:
        return {"mode": "", "branches": [], "all_view": False}

    me = df[df["Staff Code"] == vc]
    if me.empty:
        return {"mode": "", "branches": [], "all_view": False}
    my_role = _s(me.iloc[0].get("Role", "")).lower()

    if "Branch" in df.columns:
        bcol = df["Branch"].astype(str).str.strip()
        if "Unit" in df.columns:
            bcol = bcol.where(bcol.str.len() > 0, df["Unit"].astype(str).str.strip())
    else:
        bcol = df["Unit"].astype(str).str.strip()
    branch_names = sorted({b for b in bcol.tolist()
                           if b and b.lower() != _HEAD_OFFICE})

    # All-view roles (MD, Head of Branches, register roots, admins) own every
    # branch. Reuse the same sets the visibility engine uses — do not restate.
    all_view = False
    try:
        from utils.core import _ALL_VIEW_ROLES
        all_view = my_role in {r.lower() for r in _ALL_VIEW_ROLES} or "admin" in my_role
    except Exception:
        all_view = "admin" in my_role
    if all_view:
        return {"mode": "branch", "branches": branch_names, "all_view": True}

    # Otherwise: branches whose Branch Manager reports to this caller.
    if "Reports To" not in df.columns:
        return {"mode": "", "branches": [], "all_view": False}
    wanted = [w.lower() for w in _triad_roles()]
    head_role = wanted[0] if wanted else "branch manager"
    roles = df["Role"].astype(str).str.strip().str.lower()
    reports = df["Reports To"].astype(str).str.strip()
    mask = (roles == head_role) & (reports == vc)
    mine = sorted({b for b in bcol[mask].tolist() if b})
    return {"mode": "branch" if mine else "", "branches": mine, "all_view": False}


def md_reporting_roles() -> list:
    """The roles that report to the Managing Director in org_config.hierarchy.

    These ARE the Head Office units — Internal Control, Finance, HR, Treasury,
    CCB, Corporate Banking and the rest. They are not derived from the roster's
    Department string and not listed in code: change a reporting line in
    org_config and this follows on the next read.
    """
    try:
        from utils.config import load_org_config
        hier = (load_org_config() or {}).get("hierarchy") or {}
    except Exception:
        return []
    out = []
    for role, info in hier.items():
        parents = (list(info.get("reports_to", []) or [])
                   if isinstance(info, dict) else list(info or []))
        if any("managing director" in str(p).lower() for p in parents):
            out.append(role)
    return sorted(out)


def _is_top_of_house(role: str) -> bool:
    """MD, Business Manager or an admin — the observation tier.

    Ruling 2026-08-08: the Business Manager is the last gate to the MD and
    carries the MD's profile plus admin.
    """
    r = str(role or "").strip().lower()
    return ("managing director" in r or "chief executive" in r
            or r == "business manager" or "admin" in r)


def direct_reports_of_role(role: str) -> list:
    """Staff codes of the people who report DIRECTLY to the holder(s) of a role.

    Ruling 2026-08-08: a person's index belongs to the unit that employs them,
    and a higher level ADDS its own increment rather than re-summing what is
    already counted below. A unit is therefore its direct reports — not its
    subtree. Taking the subtree would pull every branch staff member back into
    CCB and count them twice.

    Resolved from the register's Reports To (the live "Reports To Code"), so it
    follows the same column the rest of the hierarchy uses.
    """
    df = _register()
    r = _s(role)
    if df.empty or not r or "Staff Code" not in df.columns:
        return []
    if "Role" not in df.columns or "Reports To" not in df.columns:
        return []

    roles = df["Role"].astype(str).str.strip()
    holders = [c for c in df["Staff Code"][roles.str.lower() == r.lower()].tolist()
               if _s(c)]
    if not holders:
        return []
    hold = {_s(h) for h in holders}
    reports = df["Reports To"].astype(str).str.strip()
    codes = df["Staff Code"].astype(str).str.strip()
    mask = reports.isin(hold) & (~codes.isin(hold))
    return [c for c in codes[mask].tolist() if c]


@lru_cache(maxsize=1)
def _role_to_unit_map() -> dict:
    """{role -> the MD-reporting unit it rolls into}, by walking the SOLID line.

    Used for CUMULATIVE RANKING only. Ranking is a different lens from index
    ownership: the ruling that a person's index belongs to their employing unit
    governs what a unit's own number is, while a cumulative ranking asks "how
    much activity sits beneath this unit in total". Each person is counted
    exactly ONCE per level, so a level always sums to the bank.

    The dotted (functional) line is deliberately NOT used here — it would place
    a branch RM in both Fortis and Consumer and the level would stop summing.
    """
    try:
        from utils.config import load_org_config
        hier = (load_org_config() or {}).get("hierarchy") or {}
    except Exception:
        return {}

    def parents(role):
        info = hier.get(role)
        if isinstance(info, dict):
            return list(info.get("reports_to") or [])
        return list(info or [])

    tops = set(md_reporting_roles())
    out = {}
    for role in hier:
        cur, seen = role, set()
        for _ in range(14):
            if cur in tops:
                out[role] = cur
                break
            if cur in seen:
                break
            seen.add(cur)
            ps = parents(cur)
            if not ps:
                break
            cur = ps[0]
    return out


# ── Branch segments ─────────────────────────────────────────────────────────
# RULING (2026-08-09): at a BRANCH the meaningful split is Consumer, Commercial
# and Operations - "operations which will include tellers and the operations
# team". The MD-reporting unit is the wrong label there: a teller does not think
# of themselves as sitting under "Director Consumer & Commercial Banking (CCB)".
#
# It cannot come from the register's Department either: branch staff carry only
# Commercial Banking (100) and Consumer Banking (93), with every operations role
# filed under Commercial. So the segment is derived from ROLE, and the mapping
# lives in org_config.json under `branch_segments` so the bank can move a role
# between segments without a deploy.
_DEFAULT_SEGMENTS = {
    "Operations": [
        "branch operations officer", "assistant branch service & operations manager",
        "customer service manager", "teller", "branch operations manager",
        "service assistant, operations officer",
        # RULING 2026-08-09: the BRANCH MANAGER is deliberately absent. They cut
        # across all three segments, so "they simply bear the branch" - the same
        # logic that already applies when branches are ranked against each
        # other. Placing them in Operations would credit operations with a
        # contribution that is really the whole branch's.
    ],
    "Consumer": [
        "relationship officer", "relationship manager, premier banking",
        "relationship officer, premier banking", "direct sales agent",
        "branch dsa team lead", "bancassurance officer",
        "relationship manager, employee schemes",
    ],
    "Commercial": [
        "relationship manager, sme", "relationship manager, local corporate",
        "relationship manager", "relationship manager, corporate",
    ],
}


def branch_segments() -> dict:
    """{segment: [role, ...]} from org_config, falling back to the defaults."""
    try:
        from utils.config import load_org_config
        cfg = (load_org_config() or {}).get("branch_segments")
        if isinstance(cfg, dict) and cfg:
            return {str(k): [str(r).lower() for r in (v or [])] for k, v in cfg.items()}
    except Exception:
        pass
    return {k: list(v) for k, v in _DEFAULT_SEGMENTS.items()}


@lru_cache(maxsize=1)
def _segment_index() -> dict:
    out = {}
    for seg, roles in branch_segments().items():
        for r in roles:
            out[str(r).strip().lower()] = seg
    return out


def segment_for_role(role: str) -> str:
    """Consumer / Commercial / Operations for a branch role, or '' if unmapped.

    An UNMAPPED role returns '' rather than being guessed into a segment - a
    quietly miscategorised teller is worse than a visible gap, because nobody
    goes looking for a number that already looks plausible.
    """
    r = _s(role).lower()
    idx = _segment_index()
    if r in idx:
        return idx[r]
    # Substring fallback for variant spellings, longest match first so
    # "relationship manager, sme" beats "relationship manager".
    for known in sorted(idx, key=len, reverse=True):
        if known and known in r:
            return idx[known]
    return ""


def unit_for_role(role: str) -> str:
    """The MD-reporting unit a role rolls into, or '' when it reaches nothing."""
    m = _role_to_unit_map()
    r = _s(role)
    return m.get(r, "")


def units_validated_by(validator_code: str) -> dict:
    """Which HEAD OFFICE UNITS does this person own?

    A unit is an MD-reporting role. Its owner is the holder of that role, and
    that owner's countersignature IS the unit's validation — validation
    TERMINATES there (ruling 2026-08-08). The MD and Business Manager observe
    every unit and may return one for amendment, but never re-validate.

    Returns {"units": [role, ...], "owns": [role, ...], "top_of_house": bool}
        units - what this person can SEE
        owns  - what this person may COUNTERSIGN (empty at the observation tier)
    """
    df = _register()
    vc = _s(validator_code)
    all_units = md_reporting_roles()
    if df.empty or not vc or "Staff Code" not in df.columns:
        return {"units": [], "owns": [], "top_of_house": False}

    me = df[df["Staff Code"] == vc]
    if me.empty:
        return {"units": [], "owns": [], "top_of_house": False}
    my_role = _s(me.iloc[0].get("Role", ""))

    if _is_top_of_house(my_role):
        return {"units": all_units, "owns": [], "top_of_house": True}

    owns = [u for u in all_units if _role_matches(my_role, u) or
            _s(my_role).lower() == _s(u).lower()]
    return {"units": owns, "owns": owns, "top_of_house": False}


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
