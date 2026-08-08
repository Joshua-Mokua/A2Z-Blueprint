"""api_branch_log.py — FastAPI routes for the Daily Branch Log.

Staff submit their own daily activity log; supervisors (managers) review and
validate. Scope: a manager validates within their unit; staff see their own
history. Mounted by utils/api.py.
"""
from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth_jwt import get_current_user
from utils.core_audit import audit_log
from utils.branch_log import BranchLogManager, fields_schema

router = APIRouter(prefix="/api/branch-log", tags=["branch-log"])


def _identity(user: dict) -> dict:
    """Resolve the caller's staff identity (code, name, unit, role) server-side."""
    username = str(user.get("username", "") or "")
    code = str(user.get("staff_code", "") or "")
    name = ""
    unit = ""
    role = str(user.get("role", "") or "")
    try:
        from utils.core import UserManager
        full = UserManager().users.get(username) or {}
        code = str(full.get("staff_code", "") or code)
        name = str(full.get("full_name", "") or "")
        role = str(full.get("role", "") or role)
        unit = str(full.get("unit", "") or full.get("department", "") or "")
    except Exception:
        pass
    if not unit and code:
        try:
            from utils.api_pipeline_scope import get_staff_roster
            df = get_staff_roster()
            hit = df[df["Staff Code"].astype(str).str.strip() == code]
            if not hit.empty:
                r0 = hit.iloc[0]
                unit = str(r0.get("Unit", "") or "")
                if not name:
                    name = str(r0.get("Staff Name", "") or "")
                if not role:
                    role = str(r0.get("Role", "") or "")
        except Exception:
            pass
    return {"staff_code": code, "staff_name": name, "unit": unit, "role": role}


def _is_manager(user: dict) -> bool:
    try:
        from utils.api_pipeline_manager_actions import is_manager
        if is_manager(user):
            return True
    except Exception:
        pass
    role = str(user.get("role", "") or "").lower()
    return user.get("is_admin") or "admin" in role or "manager" in role or "head" in role


@router.get("/day-context")
def branch_log_day_context(user: dict = Depends(get_current_user)):
    """Calendar context for today: position in the year, what remains of it, and
    how much of that is actually working time under the Kenya work calendar.

    Read-only and cheap; the Daily Log header calls it once on mount.
    """
    me = _identity(user)
    try:
        from utils import workcal
        ctx = dict(workcal.day_context())
    except Exception as exc:
        raise HTTPException(status_code=500,
                            detail=f"Work calendar unavailable: {exc}")
    ctx["staff_name"] = me.get("staff_name", "")
    ctx["staff_code"] = me.get("staff_code", "")
    return ctx


@router.get("/fields")
def branch_log_fields(user: dict = Depends(get_current_user)):
    """Role-aware daily-log schema: common base fields + this role's extras."""
    from utils.branch_log import fields_for_role
    return {"fields": fields_for_role(_identity(user).get("role", ""))}


@router.get("/activities")
def branch_log_activities(user: dict = Depends(get_current_user)):
    """The admin-added extra activities catalogue (head-office / role specific)."""
    from utils.branch_log import load_log_config, fields_schema as _fs
    return {"base": _fs(), "extra": load_log_config().get("extra_activities", []) or []}


@router.post("/activities")
def branch_log_activities_set(payload: dict = Body(default_factory=dict),
                              user: dict = Depends(get_current_user)):
    """Admin: replace the extra-activities catalogue. Each item:
    {key, label, type, unit, weight, roles:[...]}."""
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin authority required.")
    from utils.branch_log import load_log_config, save_log_config
    items = payload.get("extra_activities")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="extra_activities must be a list")
    clean = []
    for a in items:
        if not isinstance(a, dict):
            continue
        k = str(a.get("key") or "").strip()
        if not k:
            continue
        clean.append({
            "key": k, "label": str(a.get("label") or k),
            "type": str(a.get("type") or "int"),
            "unit": str(a.get("unit") or ""),
            "weight": float(a.get("weight") or 0),
            "roles": [str(x).strip() for x in (a.get("roles") or []) if str(x).strip()],
        })
    cfg = load_log_config()
    cfg["extra_activities"] = clean
    save_log_config(cfg)
    audit_log("BRANCH_LOG_ACTIVITIES", str(user.get("username", "") or ""), f"{len(clean)} extra activities")
    return {"status": "saved", "extra_activities": clean}


@router.get("/auto-activities")
def branch_log_auto_activities(user: dict = Depends(get_current_user)):
    """Today's system-tracked activities for the current user, to pre-fill the
    daily-log feed (read-only) so they only key untracked items. Derived from the
    activity stream (stage changes / updates) and referral hops they made."""
    me = _identity(user)
    code = str(me.get("staff_code") or "")
    if not code:
        return {"activities": [], "date": ""}
    from utils.core import PipelineManager
    from datetime import date
    pm = PipelineManager()
    today = date.today().isoformat()

    def hhmm(ts: str) -> str:
        s = str(ts or "")
        return s[11:16] if len(s) >= 16 else ""

    feed = []
    deal_map = {}
    try:
        deal_map = {str(d.get("id")): d for d in pm.get_deals()}
    except Exception:
        deal_map = {}

    def _client_of(deal_id) -> str:
        return str((deal_map.get(str(deal_id)) or {}).get("client_name") or "")

    # 1. deal-level events derived from the deal record (clear labels)
    for d in deal_map.values():
        if str(d.get("staff_code") or "") != code:
            continue
        client = str(d.get("client_name") or "a client")
        product = str(d.get("product") or "")
        ca = str(d.get("created_at") or "")
        if ca.startswith(today):
            feed.append({"at": ca, "time": hhmm(ca), "kind": "Deal created",
                         "detail": f"{client}{(' — ' + product) if product else ''}"})
        for h in (d.get("referral_chain") or []):
            if str(h.get("from_code") or "") != code:
                continue
            ts = str(h.get("at") or "")
            if not ts.startswith(today):
                continue
            to = str(h.get("to_name") or h.get("to_code") or "")
            to_dept = str(h.get("to_dept") or "")
            suffix = f" ({to_dept})" if to_dept else ""
            feed.append({"at": ts, "time": hhmm(ts), "kind": "Referral made",
                         "detail": f"{client} \u2192 {to}{suffix}"})

    # 2. activity stream — relabel stage changes by their outcome (target stage)
    try:
        for a in pm.get_activities(staff_code=code, limit=300):
            ts = str(a.get("recorded_at") or "")
            if not ts.startswith(today):
                continue
            outcome = str(a.get("outcome") or "").strip()
            kind = str(a.get("activity_type") or "Activity")
            if outcome == "Closed Won":
                kind = "Deal won"
            elif outcome == "Closed Lost":
                kind = "Deal lost"
            elif kind == "Stage Change" and outcome:
                kind = f"Advanced to {outcome}"
            client = _client_of(a.get("deal_id"))
            note = str(a.get("note") or "")
            detail = (f"{client} \u2014 " if client else "") + (note or outcome)
            feed.append({"at": ts, "time": hhmm(ts), "kind": kind, "detail": detail})
    except Exception:
        pass

    feed.sort(key=lambda e: e.get("at") or "")
    return {"activities": feed, "date": today}


@router.get("/config")
def branch_log_config_get(user: dict = Depends(get_current_user)):
    """Per-activity weights + daily index target (admin-configured), with fields."""
    from utils.branch_log import load_log_config
    cfg = load_log_config()
    return {"activity_weights": cfg.get("activity_weights", {}) or {},
            "daily_index_target": cfg.get("daily_index_target", 0) or 0,
            "fields": fields_schema()}


@router.post("/config")
def branch_log_config_set(payload: dict = Body(default_factory=dict),
                          user: dict = Depends(get_current_user)):
    """Set activity weights (points) + daily index target. Admin only."""
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin authority required.")
    from utils.branch_log import load_log_config, save_log_config
    cfg = load_log_config()
    if isinstance(payload.get("activity_weights"), dict):
        weights = {}
        for k, v in payload["activity_weights"].items():
            try:
                weights[str(k)] = float(v or 0)
            except (TypeError, ValueError):
                weights[str(k)] = 0.0
        cfg["activity_weights"] = weights
    if "daily_index_target" in payload:
        try:
            cfg["daily_index_target"] = float(payload.get("daily_index_target") or 0)
        except (TypeError, ValueError):
            cfg["daily_index_target"] = 0.0
    save_log_config(cfg)
    audit_log("BRANCH_LOG_CONFIG", str(user.get("username", "") or ""), "weights/target updated")
    return {"status": "saved",
            "activity_weights": cfg.get("activity_weights", {}),
            "daily_index_target": cfg.get("daily_index_target", 0)}


@router.get("/ranking")
def branch_log_ranking(days: int = 30, user: dict = Depends(get_current_user)):
    """Staff ranked by cumulative productivity index over the period. Admin sees
    all; a manager sees their reporting team; others see themselves."""
    from utils.branch_log import daily_index_target, compute_index, metric_keys
    me = _identity(user)
    blm = BranchLogManager()
    logs = blm.get_history(days=days)
    if not _is_admin(user):
        mycode = me["staff_code"]
        if _is_manager(user):
            logs = _subtree_logs(logs, user, me)
        else:
            logs = [l for l in logs if str(l.get("staff_code")) == mycode]
    agg: dict = {}
    for l in logs:
        sc = str(l.get("staff_code") or "")
        if not sc:
            continue
        idx = l.get("index")
        if idx is None:
            idx = compute_index({k: l.get(k, 0) for k in metric_keys()})
        r = agg.setdefault(sc, {"staff_code": sc, "staff_name": l.get("staff_name"),
                                "unit": l.get("unit"), "index": 0.0, "days": 0})
        r["index"] += float(idx or 0)
        r["days"] += 1
    target = daily_index_target()
    rows = sorted(agg.values(), key=lambda x: x["index"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
        r["index"] = round(r["index"], 2)
        r["avg_per_day"] = round(r["index"] / r["days"], 2) if r["days"] else 0
        r["target"] = target
    return {"ranking": rows, "days": days, "daily_index_target": target}


_DIMS_CACHE = None
_DIMS_AT = 0.0
_DIMS_TTL = 300.0   # seconds; matches the roster loader's own cache horizon


def _roster_dims() -> dict:
    """Canonical {canon(staff_code) -> {department, branch, full_name, role}}.

    SOURCE OF TRUTH: data/staff_register.xlsx, read through
    utils.api_pipeline_scope.get_staff_roster() — the SAME loader the pipeline
    hierarchy and visibility engine uses. It carries Department, Branch, Unit,
    Region and Reports To Code, so the grid's dimensions cannot drift from the
    hierarchy the rest of the system reports against.

    (An earlier revision of this joined data/staff_roster.json — a 362-row
    shadow of the same population without the reporting column. Two readers,
    two files, one concept: exactly the drift this codebase keeps paying for.)

    The Daily Log record's own `unit` is free text typed at submit time and is
    inconsistent in live data ("Fortis" / "Fortis Branch" / "Consumer" /
    "EKE-CONSUMER BANKING DEPARTMENT"); it is used only as a fallback.

    Keyed on utils.staff_code.canon so KE0439 / KE439 / 439 all resolve.
    """
    global _DIMS_CACHE, _DIMS_AT
    import time as _time
    from utils.staff_code import canon as _canon

    # P3e: memoised. Without this the map was rebuilt from df.iterrows() on
    # EVERY call. get_staff_roster() has its own TTL cache; this memoises the
    # derived lookup so a request does one build, not one per row.
    if _DIMS_CACHE is not None and (_time.monotonic() - _DIMS_AT) < _DIMS_TTL:
        return _DIMS_CACHE

    out: dict = {}
    try:
        from utils.api_pipeline_scope import get_staff_roster
        df = get_staff_roster()
        if df is None or len(df) == 0:
            return out
        cols = set(df.columns)

        def pick(row, *names):
            for n in names:
                if n in cols:
                    v = row.get(n)
                    if v is not None and str(v).strip() and str(v) != "nan":
                        return str(v).strip()
            return ""

        for _, row in df.iterrows():
            code = pick(row, "Staff Code", "staff_code")
            if not code:
                continue
            out[_canon(code)] = {
                "department": pick(row, "Department", "department"),
                "branch":     pick(row, "Branch", "Unit", "branch", "unit"),
                "full_name":  pick(row, "Staff Name", "staff_name", "full_name"),
                "role":       pick(row, "Role", "role"),
                "code":       code,
            }
    except Exception:
        return _DIMS_CACHE or out

    _DIMS_CACHE, _DIMS_AT = out, _time.monotonic()
    return out


def _dims_for(staff_code) -> dict:
    """Roster dimensions for a staff code, empty dict when unmatched."""
    from utils.staff_code import canon as _canon
    return _roster_dims().get(_canon(staff_code)) or {}


@router.get("/validation-queue")
def branch_log_validation_queue(date: str = "", user: dict = Depends(get_current_user)):
    """Daily-log validation queue for ONE day, in the same row shape as the
    history grid so Manager Queues can reuse its column and colour vocabulary.

    WHO APPEARS: every staff member this caller is a permitted validator for,
    per utils.org_validator.daily_log_validators_for — the branch management
    triad inside a branch, the pure line manager at Head Office. This endpoint
    does not decide that rule; it asks for it.

    Staff who filed NOTHING are included (ruling 2026-08-08) so a manager can
    see who owes a log, carrying status='missing' and no actions.

    Rest days are excluded outright: nobody should be asked to validate a Sunday.
    """
    from datetime import date as _date
    from utils.branch_log import metric_keys, fields_schema
    from utils.branch_log_analytics import _target_for
    from utils.staff_code import canon as _canon_q

    me = _identity(user)
    my_code = str(me.get("staff_code", "") or "")

    try:
        day = _date.fromisoformat(str(date)[:10]) if date else _date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    # Rest days carry no target and nothing to validate.
    try:
        from utils import workcal as _wc
        if not _wc.is_working_day(day):
            return {"rows": [], "columns": [], "date": day.isoformat(),
                    "working_day": False, "label": _wc.holiday_label(day),
                    "mode": "", "pending": 0}
    except Exception:
        pass

    dims = _roster_dims()
    from utils.org_validator import daily_log_validators_for

    # Everyone this caller may validate. Resolved from the roster, so it covers
    # staff who have never filed.
    mine, mode = [], ""
    for ck, d in dims.items():
        code = d.get("code") or ck
        if _canon_q(code) == _canon_q(my_code):
            continue
        try:
            res = daily_log_validators_for(code)
        except Exception:
            continue
        if any(str(v.get("validator_code") or "") == my_code
               for v in res.get("validators", [])):
            mine.append((code, d))
            mode = mode or res.get("mode", "")

    if not mine:
        return {"rows": [], "columns": [], "date": day.isoformat(),
                "working_day": True, "label": "", "mode": mode, "pending": 0}

    blm = BranchLogManager()
    logs = blm.get_history(days=45)
    iso = day.isoformat()
    by_code = {}
    for l in logs:
        if str(l.get("log_date"))[:10] == iso:
            by_code[_canon_q(l.get("staff_code"))] = l

    mkeys = metric_keys()
    rows, pending = [], 0
    for code, d in mine:
        l = by_code.get(_canon_q(code))
        base = {
            "log_date": iso,
            "staff_code": code,
            "staff_name": d.get("full_name", ""),
            "role": d.get("role", ""),
            "department": d.get("department", ""),
            "branch": d.get("branch", ""),
        }
        if not l:
            base.update({"log_id": "", "status": "missing", "validated": False,
                         "auto_submitted": False, "index": 0.0,
                         "target": _target_for({"log_date": iso}),
                         "remarks": "", "manager_note": "", "can_act": False})
            for k in mkeys:
                base[k] = 0
        else:
            status = str(l.get("status", "submitted"))
            validated = bool(l.get("validated"))
            base.update({
                "log_id": str(l.get("id", "")),
                "status": status,
                "validated": validated,
                "auto_submitted": bool(l.get("auto_submitted")),
                "index": round(float(l.get("index") or 0), 2),
                "target": _target_for(l),
                "remarks": str(l.get("remarks") or ""),
                "manager_note": str(l.get("manager_note") or ""),
                "validated_by": str(l.get("validated_by") or ""),
                "can_act": (not validated) and status in ("submitted", "auto_submitted"),
            })
            for k in mkeys:
                base[k] = l.get(k, 0)
            if base["can_act"]:
                pending += 1
        rows.append(base)

    rows.sort(key=lambda r: (r["status"] != "missing", str(r.get("staff_name") or "")))

    from utils.branch_log_analytics import tier_of
    columns = [{"key": f["key"], "label": f["label"], "unit": f.get("unit", ""),
                "type": f.get("type", "int"), "tier": tier_of(f["key"])}
               for f in fields_schema() if f.get("type") != "text"]

    return {"rows": rows, "columns": columns, "date": iso, "working_day": True,
            "label": "", "mode": mode, "pending": pending}


@router.get("/history-grid")
def branch_log_history_grid(days: int = 30, unit: str = "", include_missing: bool = True,
                            user: dict = Depends(get_current_user)):
    """Wide history grid: one row per staff per day with all metric columns, the daily index,
    target, variance, and the running CARRIED-FORWARD variance (per staff). Scope-aware:
    admin sees all; a manager sees their reporting subtree; everyone else sees themselves.

    Carried-forward variance is computed at read time per staff member (honouring admin reset
    markers and healing on validation) via utils.branch_log_analytics.carried_forward.
    """
    from utils.branch_log import metric_keys, fields_schema
    from utils.branch_log_analytics import carried_forward, deadline_time

    me = _identity(user)
    blm = BranchLogManager()
    logs = blm.get_history(days=days)
    if unit and unit != "All":
        logs = [l for l in logs if str(l.get("unit", "")) == unit]

    # SCOPE IS NOT DECIDED HERE. get_visible_staff_codes -> core_audit.
    # get_visible_staff is the same engine the Pipeline, Referrals and BSC use.
    # It already knows admins, the MD, _ALL_VIEW_ROLES (which includes Head of
    # Branches), register root roles, data custodians, Head-Office segment scope
    # for CIB/CCB/Consumer/Commercial, and the REPORTING_TREE walk.
    #
    # It reads full_name, unit, department and can_view_all from user_data - a
    # stripped-down dict silently degrades it toward self-only - so enrich the
    # caller context from the stored record before calling.
    _stored = {}
    try:
        from utils.core import UserManager
        _stored = UserManager().users.get(str(user.get("username", "")) or "") or {}
    except Exception:
        _stored = {}
    user_ctx = {
        "staff_code":   me.get("staff_code", "") or str(_stored.get("staff_code", "") or ""),
        "role":         me.get("role", "") or str(_stored.get("role", "") or ""),
        "full_name":    str(_stored.get("full_name", "") or me.get("staff_name", "") or ""),
        "unit":         me.get("unit", "") or str(_stored.get("unit", "") or ""),
        "department":   str(_stored.get("department", "") or ""),
        "is_admin":     bool(user.get("is_admin") or _stored.get("is_admin")),
        "can_view_all": bool(user.get("can_view_all") or _stored.get("can_view_all")),
    }
    from utils.staff_code import canon as _canon_scope
    try:
        from utils.api_pipeline_scope import get_visible_staff_codes
        visible = {_canon_scope(c) for c in get_visible_staff_codes(user_ctx)}
    except Exception:
        visible = set()
    visible.discard("")
    if not visible and user_ctx["staff_code"]:
        visible = {_canon_scope(user_ctx["staff_code"])}

    scoped = [l for l in logs if _canon_scope(l.get("staff_code")) in visible]

    # Group by staff so carried-forward runs per person, then flatten to grid rows.
    by_staff: dict = {}
    for l in scoped:
        by_staff.setdefault(str(l.get("staff_code") or ""), []).append(l)

    mkeys = metric_keys()

    # Resolve the roster ONCE per request; the row loop then does plain dict
    # lookups instead of re-deriving the map for every row.
    from utils.staff_code import canon as _canon_code
    _dims = _roster_dims()

    if include_missing:
        from datetime import date as _date, timedelta as _td
        from utils.staff_code import canon as _canon
        try:
            from utils import workcal as _wc
        except Exception:
            _wc = None

        dims = _dims
        # One scope decision per request, made above by the canonical engine.
        # Intersected with the roster so rows are only synthesised for people
        # who actually exist in staff_register.xlsx.
        scope_codes = {c for c in visible if c in dims} or set(visible)
        scope_codes.discard("")

        # Working days in the window, newest-inclusive.
        today = _date.today()
        window = [today - _td(days=i) for i in range(int(days))]
        work_days = [d for d in window if (_wc.is_working_day(d) if _wc else d.weekday() != 6)]

        # Index existing logs by canonical code + date so the fill never
        # duplicates a day someone actually filed.
        filed = {}
        for code, ls in by_staff.items():
            for l in ls:
                filed.setdefault(_canon(code), set()).add(str(l.get("log_date"))[:10])

        for ck in scope_codes:
            d = dims.get(ck) or {}
            have = filed.get(ck, set())
            bucket = by_staff.setdefault(d.get("code") or ck, [])
            for day in work_days:
                iso = day.isoformat()
                if iso in have:
                    continue
                blank = {
                    "log_date": iso,
                    "staff_code": d.get("code") or ck,
                    "staff_name": d.get("full_name", ""),
                    "role": d.get("role", ""),
                    "unit": d.get("branch", ""),
                    "status": "missing",
                    "validated": False,
                    "auto_submitted": False,
                    "index": 0.0,
                    "remarks": "",
                    "manager_note": "",
                }
                for k in mkeys:
                    blank[k] = 0
                bucket.append(blank)
    rows = []
    for sc, staff_logs in by_staff.items():
        annotated = carried_forward(staff_logs)  # sorted asc, adds target/variance/cf_variance
        for r in annotated:
            row = {
                "log_date":   r.get("log_date"),
                "staff_code": r.get("staff_code"),
                "staff_name": r.get("staff_name"),
                "role":       r.get("role"),
                "unit":       r.get("unit"),
                "status":     r.get("status", "submitted"),
                "validated":  bool(r.get("validated")),
                "auto_submitted": bool(r.get("auto_submitted")),
                "index":      round(float(r.get("index") or 0), 2),
                "target":     r.get("target"),
                "variance":   r.get("variance"),
                "cf_variance": r.get("cf_variance"),
                # WC-2b sets working_day on the annotated row (false on Sundays
                # and gazetted holidays). The endpoint was dropping it, so the
                # grid could never distinguish a rest day from a missed one and
                # rendered every Sunday as 0/0/0.
                "working_day":  bool(r.get("working_day", True)),
                # P3b: the day's note travels with the row so a manager reading
                # the spreadsheet sees the context without opening each entry.
                "remarks":      str(r.get("remarks") or ""),
                "manager_note": str(r.get("manager_note") or ""),
            }
            # P3c: canonical dimensions from the roster. The log's own free-text
            # `unit` stays on the row for backward compatibility, but the grid
            # filters on department/branch because those are the structure the
            # bank actually reports against.
            _d = _dims.get(_canon_code(r.get("staff_code"))) or {}
            row["department"] = _d.get("department", "")
            row["branch"] = _d.get("branch", "") or str(r.get("unit") or "")
            if _d.get("full_name"):
                row["staff_name"] = _d["full_name"]
            for k in mkeys:
                row[k] = r.get(k, 0)
            rows.append(row)

    # newest first for display; the client can re-sort
    rows.sort(key=lambda x: (str(x.get("log_date", "")), str(x.get("staff_code", ""))), reverse=True)

    # column metadata for the grid header (label + unit + tier), derived from the schema
    from utils.branch_log_analytics import tier_of
    schema = fields_schema()
    columns = [{"key": f["key"], "label": f["label"], "unit": f.get("unit", ""),
                "type": f.get("type", "int"), "tier": tier_of(f["key"])}
               for f in schema if f.get("type") != "text"]

    return {
        "rows": rows,
        "columns": columns,
        "days": days,
        # Derived from what the engine RETURNED, so the chip reflects real
        # visibility rather than a role-string guess.
        "scope_tier": ("bank" if len(visible) >= max(len(_dims), 1)
                       else ("subtree" if len(visible) > 1 else "self")),
        "visible_staff": len(visible),

        "deadline_time": deadline_time(),
    }


@router.post("/{log_id}/return")
def branch_log_return(log_id: str, payload: dict = Body(default_factory=dict),
                      user: dict = Depends(get_current_user)):
    """Manager returns a submitted/auto-submitted log for fill/resubmission (within 3 days)."""
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Supervisor/manager access required.")
    from utils.branch_log_state import return_log
    note = str(payload.get("note", "") or "")
    blm = BranchLogManager()
    try:
        rec = return_log(blm, log_id, str(user.get("username", "") or ""), note)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit_log("BRANCH_LOG_RETURN", str(user.get("username", "") or ""), detail=f"log={log_id}")
    return {"log": rec}


@router.post("/{log_id}/unlock")
def branch_log_unlock(log_id: str, user: dict = Depends(get_current_user)):
    """Admin reopens a locked log to 'returned' (editable by the author)."""
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin authority required.")
    from utils.branch_log_state import admin_unlock
    blm = BranchLogManager()
    try:
        rec = admin_unlock(blm, log_id, str(user.get("username", "") or ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit_log("BRANCH_LOG_UNLOCK", str(user.get("username", "") or ""), detail=f"log={log_id}")
    return {"log": rec}


@router.get("/impact-tiers")
def branch_log_impact_tiers_get(user: dict = Depends(get_current_user)):
    """The 80/20 impact matrix: {activity_key: 'high'|'medium'|'low'} + the activity schema."""
    from utils.branch_log_analytics import impact_tiers
    from utils.branch_log import fields_schema
    schema = [{"key": f["key"], "label": f["label"], "unit": f.get("unit", "")}
              for f in fields_schema() if f.get("type") != "text"]
    return {"impact_tiers": impact_tiers(), "activities": schema}


@router.post("/impact-tiers")
def branch_log_impact_tiers_set(payload: dict = Body(default_factory=dict),
                                user: dict = Depends(get_current_user)):
    """Admin assigns activities to impact tiers. payload: {tiers: {activity_key: tier}}."""
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin authority required.")
    from utils.branch_log_analytics import set_impact_tier, impact_tiers
    tiers_in = payload.get("tiers", {})
    if not isinstance(tiers_in, dict):
        raise HTTPException(status_code=400, detail="tiers must be an object")
    for k, v in tiers_in.items():
        try:
            set_impact_tier(str(k), str(v))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    audit_log("BRANCH_LOG_IMPACT_TIERS", str(user.get("username", "") or ""), "tiers updated")
    return {"status": "saved", "impact_tiers": impact_tiers()}


@router.post("/cf-reset")
def branch_log_cf_reset(payload: dict = Body(default_factory=dict),
                        user: dict = Depends(get_current_user)):
    """Admin records a carried-forward variance reset effective on a date (default today)."""
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin authority required.")
    from utils.branch_log_analytics import add_cf_reset_marker
    from datetime import date as _date
    reset_date = str(payload.get("date") or _date.today())
    markers = add_cf_reset_marker(reset_date, str(user.get("username", "") or ""))
    audit_log("BRANCH_LOG_CF_RESET", str(user.get("username", "") or ""), detail=f"date={reset_date}")
    return {"status": "saved", "cf_reset_markers": markers}


@router.get("/analytics")
def branch_log_analytics(days: int = 30, unit: str = "", user: dict = Depends(get_current_user)):
    """Daily-log analytics, scope-aware. Includes the 80/20 impact-tier breakdown (for the pie),
    validation split, and totals. Admin sees all; manager sees subtree; else self."""
    from utils.branch_log_analytics import impact_breakdown, high_impact_keys
    me = _identity(user)
    blm = BranchLogManager()
    try:
        from utils.branch_log_state import run_maintenance
        run_maintenance(blm)
    except Exception:
        pass
    logs = blm.get_history(days=days)
    if unit and unit != "All":
        logs = [l for l in logs if str(l.get("unit", "")) == unit]
    if _is_admin(user):
        scoped = logs
    elif _is_manager(user):
        scoped = _subtree_logs(logs, user, me)
    else:
        scoped = [l for l in logs if str(l.get("staff_code")) == me["staff_code"]]

    breakdown = impact_breakdown(scoped)
    submitters = len({str(l.get("staff_code")) for l in scoped if l.get("staff_code")})
    validated = sum(1 for l in scoped if l.get("validated"))
    auto = sum(1 for l in scoped if l.get("auto_submitted"))
    returned = sum(1 for l in scoped if l.get("status") == "returned")
    pending = sum(1 for l in scoped
                  if l.get("status") in ("submitted", "auto_submitted") and not l.get("validated"))
    return {
        "days": days,
        "scope_tier": "bank" if _is_admin(user) else ("subtree" if _is_manager(user) else "self"),
        "impact": breakdown,
        "high_impact_keys": sorted(high_impact_keys()),
        "totals": {
            "logs": len(scoped),
            "submitters": submitters,
            "validated": validated,
            "auto_submitted": auto,
            "returned": returned,
            "pending": pending,
            "validation_rate": round((validated / len(scoped)) * 100, 1) if scoped else 0.0,
        },
    }


@router.post("/control-totals")
def branch_log_control_totals_set(payload: dict = Body(default_factory=dict),
                                  user: dict = Depends(get_current_user)):
    """Manager/admin sets branch control totals for a date (the reconciliation source).
    payload: { branch, date, totals: {metric: actual} }. Designed to be replaced later by an
    automatic CBS end-of-day feed without changing the reconciliation checker."""
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Supervisor/manager access required.")
    from utils.branch_log_reconcile import set_control_totals
    from datetime import date as _date
    branch = str(payload.get("branch", "") or "").strip()
    day = str(payload.get("date") or _date.today())
    totals = payload.get("totals", {})
    if not branch:
        raise HTTPException(status_code=400, detail="branch is required")
    if not isinstance(totals, dict):
        raise HTTPException(status_code=400, detail="totals must be an object")
    stored = set_control_totals(branch, day, totals)
    audit_log("BRANCH_LOG_CONTROL_TOTALS", str(user.get("username", "") or ""),
              detail=f"branch={branch} date={day}")
    return {"status": "saved", "branch": branch, "date": day, "totals": stored}


@router.get("/reconciliation")
def branch_log_reconciliation(days: int = 7, user: dict = Depends(get_current_user)):
    """Over-reporting anomaly report: per branch+day, where the summed individual reports exceed the
    branch control total for a metric. Scope-aware: admin sees all branches; a manager sees the
    branches present in their reporting subtree; individuals get an empty report (not their view)."""
    if not _is_manager(user):
        return {"reconciliations": [], "scope_tier": "self"}
    from utils.branch_log_reconcile import reconcile_branch_day
    me = _identity(user)
    blm = BranchLogManager()
    logs = blm.get_history(days=days)
    if not _is_admin(user):
        logs = _subtree_logs(logs, user, me)
    # distinct branch+day pairs present in scope
    pairs = sorted({(str(l.get("unit", "")), str(l.get("log_date", "")))
                    for l in logs if l.get("unit") and l.get("log_date")}, reverse=True)
    out = []
    for branch, day in pairs:
        rec = reconcile_branch_day(logs, branch, day)
        if rec["metrics"]:  # only include branch+days that HAVE control totals to check
            out.append(rec)
    anomaly_total = sum(r["anomaly_count"] for r in out)
    return {
        "reconciliations": out,
        "anomaly_total": anomaly_total,
        "days": days,
        "scope_tier": "bank" if _is_admin(user) else "subtree",
    }


@router.get("/mine")
def branch_log_mine(days: int = 14, user: dict = Depends(get_current_user)):
    """The caller's own recent log entries."""
    me = _identity(user)
    if not me["staff_code"]:
        return {"logs": [], "identity": me}
    blm = BranchLogManager()
    return {"logs": blm.get_history(staff_code=me["staff_code"], days=days), "identity": me}


def _is_admin(user: dict) -> bool:
    return bool(user.get("is_admin")) or "admin" in str(user.get("role", "")).lower()


def _reports_to_me(logs: list, my_code: str) -> list:
    """Keep only logs whose submitter's direct line manager (pure reporting
    tree) is this manager. Resolution is cached per submitter within the call."""
    if not my_code:
        return []
    from utils.org_validator import line_manager_of
    cache: dict = {}
    out = []
    for l in logs:
        sc = str(l.get("staff_code", "") or "")
        if sc not in cache:
            cache[sc] = str(line_manager_of(sc).get("validator_code") or "")
        if cache[sc] == my_code:
            out.append(l)
    return out


def _subtree_logs(logs: list, user: dict, me: dict) -> list:
    """Logs for the caller's full reporting subtree (line manager -> ... -> MD),
    via the hierarchy visibility engine. Falls back to direct reports on error."""
    try:
        from utils.api_pipeline_scope import get_visible_staff_codes
        codes = {str(c) for c in get_visible_staff_codes({
            "staff_code": me.get("staff_code", ""),
            "role": me.get("role", ""),
            "is_admin": bool(user.get("is_admin")),
        })}
        return [l for l in logs if str(l.get("staff_code") or "") in codes]
    except Exception:
        return _reports_to_me(logs, me.get("staff_code", ""))


@router.get("/pending")
def branch_log_pending(user: dict = Depends(get_current_user)):
    """Entries awaiting validation, routed by the reporting tree: a manager
    sees logs from staff who report to them; admin sees all."""
    if not _is_manager(user):
        raise HTTPException(status_code=403, detail="Supervisor/manager access required.")
    me = _identity(user)
    blm = BranchLogManager()
    try:
        from utils.branch_log_state import run_maintenance
        run_maintenance(blm)
    except Exception:
        pass
    all_pending = blm.get_pending_validation(unit=None)
    if _is_admin(user):
        return {"logs": all_pending}
    return {"logs": _subtree_logs(all_pending, user, me)}


@router.get("/history")
def branch_log_history(unit: str = "", days: int = 7, user: dict = Depends(get_current_user)):
    """History routed by the reporting tree: managers see their reports'
    submitted logs; admin sees all; everyone else sees their own."""
    me = _identity(user)
    blm = BranchLogManager()
    if _is_manager(user):
        if _is_admin(user):
            return {"logs": blm.get_history(days=days)}
        return {"logs": _subtree_logs(blm.get_history(days=days), user, me)}
    return {"logs": blm.get_history(staff_code=me["staff_code"], days=days)}


@router.post("/draft")
def branch_log_save_draft(payload: dict = Body(default_factory=dict),
                          user: dict = Depends(get_current_user)):
    """Save the caller's Daily Log as a DRAFT (private, not submitted for
    validation). Survives logout; the author can keep editing and later submit."""
    me = _identity(user)
    if not me["staff_code"]:
        raise HTTPException(status_code=400, detail="Your staff identity could not be resolved.")
    values = payload.get("values") if isinstance(payload.get("values"), dict) else payload
    blm = BranchLogManager()
    rec = blm.save_draft(me["staff_code"], me["staff_name"], me["unit"], me["role"], values or {})
    audit_log("BRANCH_LOG_DRAFT", user.get("username", "unknown"),
              detail=f"draft={rec.get('id')} unit={me['unit']}")
    return {"log": rec}


@router.get("/draft")
def branch_log_get_draft(user: dict = Depends(get_current_user)):
    """Return the caller's log for today (draft or already-submitted) so the
    Daily Log form can re-hydrate on return. Empty when nothing saved today."""
    me = _identity(user)
    if not me["staff_code"]:
        return {"log": None}
    blm = BranchLogManager()
    return {"log": blm.get_today(me["staff_code"])}


@router.post("")
def branch_log_submit(payload: dict = Body(default_factory=dict),
                      user: dict = Depends(get_current_user)):
    """Submit (or update) the caller's log for today."""
    me = _identity(user)
    if not me["staff_code"]:
        raise HTTPException(status_code=400, detail="Your staff identity could not be resolved.")
    values = payload.get("values") if isinstance(payload.get("values"), dict) else payload
    blm = BranchLogManager()
    rec = blm.submit(me["staff_code"], me["staff_name"], me["unit"], me["role"], values or {})
    audit_log("BRANCH_LOG_SUBMIT", user.get("username", "unknown"),
              detail=f"log={rec.get('id')} unit={me['unit']}")
    return {"log": rec}


@router.post("/{log_id}/validate")
def branch_log_validate(log_id: str, payload: dict = Body(default_factory=dict),
                        user: dict = Depends(get_current_user)):
    """Validate (approve/reject) a submitted log.

    Permission comes from utils.org_validator.can_validate_daily_log - the
    branch triad inside a branch, the line manager at Head Office - not from a
    role-substring guess. Admins retain an override.
    """
    me = _identity(user)
    blm_probe = BranchLogManager()
    _target = next((l for l in blm_probe.get_history(days=120)
                    if str(l.get("id")) == str(log_id)), None)
    if not _target:
        raise HTTPException(status_code=404, detail=f"Log {log_id} not found")
    if not _is_admin(user):
        try:
            from utils.org_validator import can_validate_daily_log
            allowed = can_validate_daily_log(me.get("staff_code", ""),
                                             str(_target.get("staff_code") or ""))
        except Exception:
            allowed = False
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail="You are not a permitted validator for this staff member.")

    approved = bool(payload.get("approved", True))
    note = str(payload.get("note", "") or "")
    blm = BranchLogManager()
    rec = blm.validate(log_id, str(user.get("username", "") or ""), note, approved)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Log {log_id} not found")
    audit_log("BRANCH_LOG_VALIDATE", user.get("username", "unknown"),
              detail=f"log={log_id} approved={approved}")
    return {"log": rec}
