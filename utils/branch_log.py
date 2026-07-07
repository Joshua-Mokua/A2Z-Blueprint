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


def fields_schema() -> list:
    return [{"key": k, "label": lbl, "type": t, "unit": u, "bsc_kpi": kpi}
            for k, lbl, t, u, kpi in LOG_FIELDS]


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

        metrics = {k: _num(values.get(k, 0)) for k in _METRIC_KEYS}
        remarks = str(values.get("remarks", "") or "")

        existing = next((l for l in self.logs
                         if str(l.get("staff_code")) == code and l.get("log_date") == today), None)
        if existing:
            existing.update(metrics)
            existing["remarks"] = remarks
            existing["updated_at"] = datetime.now().isoformat()
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
            "submitted_at": datetime.now().isoformat(),
            "validated": False,
            "validated_by": "",
            "validated_at": "",
            "manager_note": "",
            "rejected": False,
            **metrics,
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
        logs = [l for l in self.logs
                if not l.get("validated") and not l.get("rejected", False)]
        if unit and unit != "All":
            logs = [l for l in logs if l.get("unit") == unit]
        return sorted(logs, key=lambda l: l.get("submitted_at", ""), reverse=True)

    def get_all(self) -> list:
        return list(self.logs)
