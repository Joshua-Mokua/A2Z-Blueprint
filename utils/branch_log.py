"""branch_log.py — Daily Branch Log backend (staff activity reporting +
supervisor validation). Clean, reusable manager over data/branch_logs.json.

Mirrors the schema used by the Streamlit page (pages/14_branch_log.py) so the
two surfaces share one data file. Atomic writes; no Streamlit dependency.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from utils.core import DATA_DIR

# (key, label, type, unit, bsc_kpi_link) — the daily activity metrics.
LOG_FIELDS = [
    ("accounts_opened",     "Accounts Opened",                 "int",    "accounts", "New Customer Acquisition"),
    ("accounts_activated",  "Dormant Accounts Reactivated",    "int",    "accounts", "Dormancy Reactivation"),
    ("transactions_count",  "Transactions Processed",          "int",    "count",    "Transactions"),
    ("cards_issued",        "Cards Issued/Renewed",            "int",    "cards",    None),
    ("dfs_registrations",   "DFS / Mobile Money Registrations", "int",   "count",    "Digital Acquiring"),
    ("loans_referred",      "Loans Referred",                  "int",    "count",    "Loans Disbursement"),
    ("loans_disbursed",     "Loans Disbursed (KES)",           "amount", "KES",      "Loan Book Growth"),
    ("deposits_mobilised",  "Deposits Mobilised (KES)",        "amount", "KES",      "Deposit Growth"),
    ("bancassurance_sold",  "Bancassurance Policies Sold",     "int",    "policies", "Bancassurance"),
    ("complaints_received", "Customer Complaints Received",    "int",    "count",    None),
    ("complaints_resolved", "Complaints Resolved Same Day",    "int",    "count",    "Complaint Resolution Rate"),
    ("digital_txns",        "Digital Transactions Assisted",   "int",    "count",    "Digital Transaction Migration"),
    ("new_leads",           "New Sales Leads Generated",       "int",    "leads",    None),
    ("cross_sell_success",  "Cross-sell Successes",            "int",    "count",    None),
    ("teller_errors",       "Teller Errors / Differences",     "int",    "count",    "Timely Reconciliations"),
    ("customer_visits",     "Customers Served",                "int",    "count",    "CX Score"),
    ("nps_collected",       "NPS Survey Responses Collected",  "int",    "count",    "NPS Score"),
    ("remarks",             "Remarks / Challenges",            "text",   "",         None),
]

_METRIC_KEYS = [k for k, _, t, _, _ in LOG_FIELDS if t != "text"]


_CONFIG_FILE = Path(DATA_DIR) / "branch_log_config.json"


def load_log_config() -> dict:
    """Admin-set daily-log config: per-activity weights + daily index target."""
    try:
        if _CONFIG_FILE.exists():
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        pass
    return {}


def save_log_config(cfg: dict) -> None:
    _CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def activity_weights() -> dict:
    return load_log_config().get("activity_weights", {}) or {}


def daily_index_target() -> float:
    try:
        return float(load_log_config().get("daily_index_target", 0) or 0)
    except Exception:
        return 0.0


def compute_index(metrics: dict) -> float:
    """Productivity index for a log = sum(activity count x admin weight)."""
    w = activity_weights()
    total = 0.0
    for k, v in (metrics or {}).items():
        try:
            total += float(v or 0) * float(w.get(k, 0) or 0)
        except (TypeError, ValueError):
            continue
    return round(total, 2)


def _extra_activities() -> list:
    """Admin-added activities beyond the common base (e.g. head-office / role
    specific), each: {key, label, type, unit, weight, roles:[...]}."""
    return load_log_config().get("extra_activities", []) or []


def metric_keys() -> list:
    """All numeric activity keys — common base (LOG_FIELDS) + admin extras."""
    keys = list(_METRIC_KEYS)
    for a in _extra_activities():
        k = str(a.get("key") or "").strip()
        if k and str(a.get("type", "int")) != "text" and k not in keys:
            keys.append(k)
    return keys


def derive_from_hourly(hourly: dict) -> dict:
    """Sum per-hour activity counts into flat day-total metrics.

    hourly = { "HH": {"counts": {metric_key: n, ...}, "meetings": [...]}, ... }
    Only numeric activity counts are summed; meetings are time-spans handled separately
    (they carry their own impact tier and do not contribute to metric counts). Returns a
    {metric_key: total} dict spanning all metric_keys() (missing keys default to 0).
    """
    totals = {k: 0.0 for k in metric_keys()}
    if not isinstance(hourly, dict):
        return totals
    for _hh, block in hourly.items():
        if not isinstance(block, dict):
            continue
        counts = block.get("counts", {}) if isinstance(block.get("counts"), dict) else {}
        for k, v in counts.items():
            if k in totals:
                try:
                    totals[k] += float(v or 0)
                except (TypeError, ValueError):
                    continue
    return totals


def sanitize_hourly(hourly: dict) -> dict:
    """Normalise an incoming hourly map: keep only known metric counts + well-formed meetings,
    keyed by 2-digit hour strings "00".."23". Defensive against malformed client input."""
    out: dict = {}
    if not isinstance(hourly, dict):
        return out
    valid_keys = set(metric_keys())
    for hh, block in hourly.items():
        try:
            h = int(str(hh))
        except (TypeError, ValueError):
            continue
        if h < 0 or h > 23 or not isinstance(block, dict):
            continue
        counts_in = block.get("counts", {}) if isinstance(block.get("counts"), dict) else {}
        counts = {}
        for k, v in counts_in.items():
            if k in valid_keys:
                try:
                    n = float(v or 0)
                except (TypeError, ValueError):
                    n = 0
                if n:
                    counts[k] = n
        meetings_in = block.get("meetings", []) if isinstance(block.get("meetings"), list) else []
        meetings = []
        for m in meetings_in:
            if isinstance(m, dict) and m.get("label"):
                meetings.append({
                    "label": str(m.get("label", "")),
                    "tier": str(m.get("tier", "medium")).lower(),
                    "span": int(m.get("span", 1) or 1),
                    "source": str(m.get("source", "manual")),
                })
        note = str(block.get("note", "") or "").strip()[:500]
        if counts or meetings or note:
            blk = {"counts": counts, "meetings": meetings}
            if note:
                blk["note"] = note
            out[f"{h:02d}"] = blk
    return out


def fields_schema() -> list:
    w = activity_weights()
    return [{"key": k, "label": lbl, "type": t, "unit": u, "bsc_kpi": kpi,
             "weight": float(w.get(k, 0) or 0)}
            for k, lbl, t, u, kpi in LOG_FIELDS]


def fields_for_role(role: str) -> list:
    """Activity fields for a role: the common base + admin extras whose 'roles'
    is empty (common) or includes this role."""
    out = fields_schema()
    w = activity_weights()
    rl = str(role or "").strip().lower()
    for a in _extra_activities():
        k = str(a.get("key") or "").strip()
        if not k:
            continue
        roles = [str(x).strip().lower() for x in (a.get("roles") or [])]
        if roles and rl and rl not in roles:
            continue
        out.append({"key": k, "label": a.get("label", k), "type": a.get("type", "int"),
                    "unit": a.get("unit", ""), "bsc_kpi": None,
                    "weight": float(w.get(k, a.get("weight", 0)) or 0),
                    "roles": a.get("roles") or []})
    return out


class BranchLogManager:
    def __init__(self):
        self.file = Path(DATA_DIR) / "branch_logs.json"
        self.logs = self._load()

    def _load(self) -> list:
        if not self.file.exists():
            return []
        try:
            raw = self.file.read_text(encoding="utf-8")
            d = json.loads(raw) if raw.strip() else []
            return d if isinstance(d, list) else list(d.values())
        except Exception:
            return []

    def _save(self) -> None:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.file.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.logs, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.file)
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
            raise

    def submit(self, staff_code: str, staff_name: str, unit: str, role: str,
               values: dict) -> dict:
        """Create or update today's log for this staff member. Re-submitting
        the same day updates the entry and resets validation."""
        today = str(date.today())
        code = str(staff_code)

        def _num(v):
            try:
                return float(v or 0)
            except (TypeError, ValueError):
                return 0

        hourly = sanitize_hourly(values.get("hourly", {}))
        if hourly:
            derived = derive_from_hourly(hourly)
            metrics = {k: _num(derived.get(k, 0)) for k in metric_keys()}
        else:
            metrics = {k: _num(values.get(k, 0)) for k in metric_keys()}
        remarks = str(values.get("remarks", "") or "")

        existing = next((l for l in self.logs
                         if str(l.get("staff_code")) == code and l.get("log_date") == today), None)
        if existing:
            existing.update(metrics)
            existing["remarks"] = remarks
            if hourly:
                existing["hourly"] = hourly
            existing["index"] = compute_index(metrics)
            existing["updated_at"] = datetime.now().isoformat()
            existing["validated"] = False
            existing["rejected"] = False
            existing["status"] = "submitted"
            self._save()
            return existing

        rec = {
            "id": f"LOG{len(self.logs) + 1:06d}",
            "log_date": today,
            "staff_code": code,
            "staff_name": staff_name,
            "unit": unit,
            "role": role,
            "submitted_at": datetime.now().isoformat(),
            "validated": False,
            "validated_by": "",
            "validated_at": "",
            "manager_note": "",
            "rejected": False,
            "status": "submitted",
            "hourly": hourly,
            **metrics,
            "index": compute_index(metrics),
            "remarks": remarks,
        }
        self.logs.append(rec)
        self._save()
        return rec

    def validate(self, log_id: str, manager: str, note: str, approved: bool) -> Optional[dict]:
        for l in self.logs:
            if l.get("id") == log_id:
                l["validated"] = bool(approved)
                l["rejected"] = not approved
                l["validated_by"] = manager
                l["validated_at"] = datetime.now().isoformat()
                l["manager_note"] = note
                self._save()
                return l
        return None

    def get_history(self, staff_code: Optional[str] = None, unit: Optional[str] = None,
                    days: int = 7) -> list:
        cutoff = str(date.today() - timedelta(days=days))
        logs = [l for l in self.logs if str(l.get("log_date", "")) >= cutoff]
        if staff_code:
            logs = [l for l in logs if str(l.get("staff_code")) == str(staff_code)]
        if unit and unit != "All":
            logs = [l for l in logs if l.get("unit") == unit]
        return sorted(logs, key=lambda l: l.get("submitted_at", ""), reverse=True)

    def get_pending_validation(self, unit: Optional[str] = None) -> list:
        # Drafts (status="draft") are private to the author and never enter the
        # manager validation queue until explicitly submitted.
        logs = [l for l in self.logs
                if l.get("status") != "draft"
                and not l.get("validated") and not l.get("rejected", False)]
        if unit and unit != "All":
            logs = [l for l in logs if l.get("unit") == unit]
        return sorted(logs, key=lambda l: l.get("submitted_at", ""), reverse=True)

    def save_draft(self, staff_code: str, staff_name: str, unit: str, role: str,
                   values: dict) -> dict:
        """Save (upsert) today's log as a DRAFT for this staff member. A draft is
        NOT submitted for validation and never appears in a manager's queue; the
        author can keep editing and later submit(). Survives logout (persisted)."""
        today = str(date.today())
        code = str(staff_code)

        def _num(v):
            try:
                return float(v or 0)
            except (TypeError, ValueError):
                return 0

        hourly = sanitize_hourly(values.get("hourly", {}))
        if hourly:
            derived = derive_from_hourly(hourly)
            metrics = {k: _num(derived.get(k, 0)) for k in metric_keys()}
        else:
            metrics = {k: _num(values.get(k, 0)) for k in metric_keys()}
        remarks = str(values.get("remarks", "") or "")

        existing = next((l for l in self.logs
                         if str(l.get("staff_code")) == code and l.get("log_date") == today), None)
        if existing:
            existing.update(metrics)
            existing["remarks"] = remarks
            if hourly:
                existing["hourly"] = hourly
            existing["index"] = compute_index(metrics)
            existing["updated_at"] = datetime.now().isoformat()
            existing["status"] = "draft"
            existing["validated"] = False
            existing["rejected"] = False
            self._save()
            return existing

        rec = {
            "id": f"LOG{len(self.logs) + 1:06d}",
            "log_date": today,
            "staff_code": code,
            "staff_name": staff_name,
            "unit": unit,
            "role": role,
            "submitted_at": "",
            "updated_at": datetime.now().isoformat(),
            "validated": False,
            "validated_by": "",
            "validated_at": "",
            "manager_note": "",
            "rejected": False,
            "status": "draft",
            "hourly": hourly,
            **metrics,
            "index": compute_index(metrics),
            "remarks": remarks,
        }
        self.logs.append(rec)
        self._save()
        return rec

    def get_today(self, staff_code: str) -> Optional[dict]:
        """Return today's log (draft or submitted) for this staff member, so the
        Daily Log form can re-hydrate on return. None if nothing saved today."""
        today = str(date.today())
        code = str(staff_code)
        return next((l for l in self.logs
                     if str(l.get("staff_code")) == code and l.get("log_date") == today), None)

    def get_all(self) -> list:
        return list(self.logs)
