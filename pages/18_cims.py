"""pages/18_cims.py — CIMS: Customer Instruction Management System."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *
from pages._shared import load_shared_state, safe_html
from pages._access import require_access, get_my_scope
require_access("cims")

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass



um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()
staff_scores = st.session_state.get("staff_scores", pd.DataFrame())
registry     = st.session_state.get("staff_registry", pd.DataFrame())

# ════════════════════════════════════════════════════════════════
# CIMS CONFIGURATION — all admin-configurable
# ════════════════════════════════════════════════════════════════
CIMS_CONFIG_FILE = DATA_DIR / "cims_config.json"
CIMS_TICKETS_FILE = DATA_DIR / "cims_tickets.json"

DEFAULT_INSTRUCTION_TYPES = {
    # ── CREDIT & LENDING ─────────────────────────────────────
    "Loan Drawdown Request": {
        "category": "Credit & Lending",
        "sla_hours": 4, "priority": "High",
        "owner_unit": "Credit",
        "description": "Customer request to draw down approved loan facility",
        "required_docs": ["Drawdown request letter", "Proof of purpose (if required)"],
    },
    "Credit Limit Review": {
        "category": "Credit & Lending",
        "sla_hours": 48, "priority": "High",
        "owner_unit": "Credit",
        "description": "Request to review and adjust credit limit on facility",
        "required_docs": ["Financial statements (6 months)", "Credit review form"],
    },
    "Loan Restructuring": {
        "category": "Credit & Lending",
        "sla_hours": 72, "priority": "High",
        "owner_unit": "Credit",
        "description": "Request to restructure loan terms — tenor, rate, repayment schedule",
        "required_docs": ["Restructuring request form", "Financial statements", "Board resolution (corporates)"],
    },
    "Collateral Substitution": {
        "category": "Credit & Lending",
        "sla_hours": 48, "priority": "Medium",
        "owner_unit": "Credit",
        "description": "Customer requests to substitute pledged collateral",
        "required_docs": ["Collateral valuation report", "Substitution request form"],
    },
    "Partial Discharge of Security": {
        "category": "Credit & Lending",
        "sla_hours": 48, "priority": "Medium",
        "owner_unit": "Credit",
        "description": "Release portion of pledged security upon partial repayment",
        "required_docs": ["Discharge form", "Proof of repayment"],
    },
    "Letter of Offer Amendment": {
        "category": "Credit & Lending",
        "sla_hours": 24, "priority": "High",
        "owner_unit": "Credit",
        "description": "Amendment to terms in an issued letter of offer",
        "required_docs": ["Amendment request", "Reason for amendment"],
    },
    # ── ACCOUNT OPERATIONS ────────────────────────────────────
    "Account Mandate Change": {
        "category": "Account Operations",
        "sla_hours": 24, "priority": "High",
        "owner_unit": "Operations",
        "description": "Change of authorised signatories or mandate requirements",
        "required_docs": ["Mandate update form", "ID of new signatories", "Board resolution (corporates)"],
    },
    "Account Name Change": {
        "category": "Account Operations",
        "sla_hours": 48, "priority": "Medium",
        "owner_unit": "Operations",
        "description": "Legal name change on account following marriage, deed poll or corporate rename",
        "required_docs": ["Name change document", "ID", "Gazette notice (corporate)"],
    },
    "Account Closure": {
        "category": "Account Operations",
        "sla_hours": 24, "priority": "High",
        "owner_unit": "Operations",
        "description": "Customer request to close an active account",
        "required_docs": ["Closure form", "ID", "Original documents"],
    },
    "Stop Payment Order": {
        "category": "Account Operations",
        "sla_hours": 2, "priority": "Critical",
        "owner_unit": "Operations",
        "description": "Instruct bank to stop payment on a specific cheque or transaction",
        "required_docs": ["Stop order form", "Cheque details"],
    },
    "Standing Order Setup/Amendment": {
        "category": "Account Operations",
        "sla_hours": 4, "priority": "Medium",
        "owner_unit": "Operations",
        "description": "Create, amend or cancel a recurring standing order",
        "required_docs": ["Standing order form"],
    },
    "Direct Debit Setup/Amendment": {
        "category": "Account Operations",
        "sla_hours": 4, "priority": "Medium",
        "owner_unit": "Operations",
        "description": "Authorise or amend direct debit mandate",
        "required_docs": ["Direct debit mandate form", "ID"],
    },
    "Lien Placement/Release": {
        "category": "Account Operations",
        "sla_hours": 4, "priority": "High",
        "owner_unit": "Operations",
        "description": "Place or release a lien on customer funds",
        "required_docs": ["Lien form", "Authorisation letter"],
    },
    # ── TRADE FINANCE ────────────────────────────────────────
    "Letter of Credit Opening": {
        "category": "Trade Finance",
        "sla_hours": 24, "priority": "High",
        "owner_unit": "Treasury",
        "description": "Open a documentary letter of credit on behalf of importer",
        "required_docs": ["LC application form", "Pro-forma invoice", "Import licence (if applicable)"],
    },
    "Letter of Credit Amendment": {
        "category": "Trade Finance",
        "sla_hours": 8, "priority": "High",
        "owner_unit": "Treasury",
        "description": "Amend terms of an existing LC",
        "required_docs": ["Amendment form", "Justification letter"],
    },
    "Bank Guarantee Issuance": {
        "category": "Trade Finance",
        "sla_hours": 48, "priority": "High",
        "owner_unit": "Treasury",
        "description": "Issue a performance, bid or advance payment guarantee",
        "required_docs": ["Guarantee form", "Underlying contract", "Indemnity agreement"],
    },
    "Documentary Collection": {
        "category": "Trade Finance",
        "sla_hours": 24, "priority": "Medium",
        "owner_unit": "Treasury",
        "description": "Process inward or outward documentary collection",
        "required_docs": ["Collection application", "Shipping documents"],
    },
    # ── TREASURY & FX ────────────────────────────────────────
    "Foreign Currency Purchase": {
        "category": "Treasury & FX",
        "sla_hours": 2, "priority": "High",
        "owner_unit": "Treasury",
        "description": "Customer request to purchase foreign currency",
        "required_docs": ["FX purchase form", "Supporting documents (purpose)"],
    },
    "Forward Contract Booking": {
        "category": "Treasury & FX",
        "sla_hours": 4, "priority": "High",
        "owner_unit": "Treasury",
        "description": "Book a forward FX contract to hedge future currency exposure",
        "required_docs": ["Forward contract form", "Underlying trade documents"],
    },
    "RTGS/SWIFT Transfer": {
        "category": "Treasury & FX",
        "sla_hours": 2, "priority": "Critical",
        "owner_unit": "Operations",
        "description": "Large-value real-time gross settlement or SWIFT wire transfer",
        "required_docs": ["Transfer instruction form", "ID", "Source of funds (if required)"],
    },
    # ── CUSTOMER SERVICE / BRANCH ─────────────────────────────
    "Cheque Book Request": {
        "category": "Customer Service",
        "sla_hours": 24, "priority": "Low",
        "owner_unit": "Operations",
        "description": "Request new cheque book for an account",
        "required_docs": ["Cheque book request form"],
    },
    "Banker's Cheque": {
        "category": "Customer Service",
        "sla_hours": 1, "priority": "Medium",
        "owner_unit": "Operations",
        "description": "Request for a bank-certified cheque",
        "required_docs": ["Banker's cheque form", "ID"],
    },
    "Reference Letter": {
        "category": "Customer Service",
        "sla_hours": 24, "priority": "Low",
        "owner_unit": "Operations",
        "description": "Request for bank reference letter for visa, tenancy or other purpose",
        "required_docs": ["Reference letter request form"],
    },
    "Statement of Account": {
        "category": "Customer Service",
        "sla_hours": 4, "priority": "Low",
        "owner_unit": "Operations",
        "description": "Request for detailed account statement",
        "required_docs": ["Statement request form"],
    },
    "Confirmation of Balance": {
        "category": "Customer Service",
        "sla_hours": 4, "priority": "Low",
        "owner_unit": "Operations",
        "description": "Confirmation of balance for audit or due diligence purposes",
        "required_docs": ["Confirmation request", "Auditor authorisation"],
    },
    # ── COMPLIANCE & LEGAL ────────────────────────────────────
    "KYC/CDD Update": {
        "category": "Compliance",
        "sla_hours": 48, "priority": "High",
        "owner_unit": "Compliance & Legal",
        "description": "Customer due diligence refresh — update KYC documents",
        "required_docs": ["Updated ID", "Proof of address", "Source of funds declaration"],
    },
    "Garnishee Order Processing": {
        "category": "Compliance",
        "sla_hours": 4, "priority": "Critical",
        "owner_unit": "Compliance & Legal",
        "description": "Court-ordered garnishee — freeze and process as instructed",
        "required_docs": ["Court order (original)", "Legal team sign-off"],
    },
    "AML Query Response": {
        "category": "Compliance",
        "sla_hours": 24, "priority": "Critical",
        "owner_unit": "Compliance & Legal",
        "description": "Respond to AML or KYC query from regulator or correspondent bank",
        "required_docs": ["Query letter", "Customer documents"],
    },
    # ── CARD SERVICES ─────────────────────────────────────────
    "Card Hotlisting": {
        "category": "Card Services",
        "sla_hours": 0.5, "priority": "Critical",
        "owner_unit": "Operations",
        "description": "Immediately block a lost, stolen or compromised card",
        "required_docs": ["Customer ID or PIN verification"],
    },
    "Card Limit Adjustment": {
        "category": "Card Services",
        "sla_hours": 4, "priority": "Medium",
        "owner_unit": "Operations",
        "description": "Increase or decrease card transaction or credit limit",
        "required_docs": ["Limit adjustment form", "ID verification"],
    },
    "Chargeback Dispute": {
        "category": "Card Services",
        "sla_hours": 48, "priority": "High",
        "owner_unit": "Operations",
        "description": "Customer disputes a card transaction — initiate chargeback",
        "required_docs": ["Dispute form", "Transaction details"],
    },
}

OWNER_UNITS = [
    "Credit", "Operations", "Treasury", "Compliance & Legal",
    "Human Resources", "ICT", "Finance", "Risk", "Internal Audit",
    "Strategy", "Marketing", "Procurement",
]

PRIORITY_COLORS = {
    "Critical": "#E24B4A",
    "High":     "#F5A623",
    "Medium":   "#185FA5",
    "Low":      "#7F8C8D",
}

TICKET_STATUSES = ["Open", "Allocated", "In Progress", "Pending Customer", "Resolved", "Escalated", "Cancelled"]
STATUS_COLORS   = {
    "Open":             "#E24B4A",
    "Allocated":        "#F5A623",
    "In Progress":      "#185FA5",
    "Pending Customer": "#9B59B6",
    "Resolved":         "var(--brand-primary,#006B3F)",
    "Escalated":        "#C0392B",
    "Cancelled":        "#7F8C8D",
}

# ════════════════════════════════════════════════════════════════
# CIMS MANAGER
# ════════════════════════════════════════════════════════════════
CIMS_DOCS_DIR    = DATA_DIR / "cims_docs"
CIMS_AUTO_CFG    = DATA_DIR / "cims_auto_assign.json"

class CIMSManager:
    def __init__(self):
        self.cfg_file    = CIMS_CONFIG_FILE
        self.tick_file   = CIMS_TICKETS_FILE
        self.auto_file   = CIMS_AUTO_CFG
        self.config      = self._load_config()
        self.tickets     = self._load_tickets()
        self.auto_config = self._load_auto()
        CIMS_DOCS_DIR.mkdir(parents=True, exist_ok=True)

    def _load_auto(self):
        """Load auto-assignment config: mode + unit->staff mapping."""
        if not self.auto_file.exists():
            default = {
                "mode": "team_leader",      # "auto" or "team_leader"
                "unit_map": {},              # unit_name -> [staff_code, ...]
                "exclude_on_leave": True,    # skip staff on leave
                "round_robin": {},           # unit -> last_index
            }
            self.auto_file.write_text(json.dumps(default, indent=2))
            return default
        try:
            return json.loads(self.auto_file.read_text())
        except:
            return {"mode":"team_leader","unit_map":{},"exclude_on_leave":True,"round_robin":{}}

    def save_auto_config(self):
        self.auto_file.write_text(json.dumps(self.auto_config, indent=2))

    # ── Config (instruction types + SLAs) ────────────────────
    def _load_config(self):
        if not self.cfg_file.exists():
            self.cfg_file.write_text(json.dumps(DEFAULT_INSTRUCTION_TYPES, indent=2))
        try:
            raw = self.cfg_file.read_text()
            d = json.loads(raw) if raw.strip() else {}
            return d if isinstance(d, dict) else DEFAULT_INSTRUCTION_TYPES.copy()
        except:
            return DEFAULT_INSTRUCTION_TYPES.copy()

    def save_config(self):
        self.cfg_file.write_text(json.dumps(self.config, indent=2))

    def add_instruction_type(self, name: str, data: dict):
        self.config[name] = data
        self.save_config()

    def update_sla(self, instruction_type: str, sla_hours: float,
                   priority: str, owner_unit: str):
        if instruction_type in self.config:
            self.config[instruction_type].update({
                "sla_hours":  sla_hours,
                "priority":   priority,
                "owner_unit": owner_unit,
            })
            self.save_config()

    # ── Tickets ───────────────────────────────────────────────
    def _load_tickets(self):
        if not self.tick_file.exists():
            self.tick_file.write_text("[]")
        try:
            raw = self.tick_file.read_text()
            d = json.loads(raw) if raw.strip() else []
            return d if isinstance(d, list) else []
        except:
            return []

    def _save_tickets(self):
        self.tick_file.write_text(json.dumps(self.tickets, indent=2, default=str))

    def raise_instruction(self, data: dict) -> dict:
        """Log a new customer instruction from any originating branch/unit."""
        inst_type  = data.get("instruction_type", "")
        cfg        = self.config.get(inst_type, {})
        sla_hrs    = cfg.get("sla_hours", 24)
        owner_unit = data.get("owner_unit") or cfg.get("owner_unit", "Operations")
        now        = datetime.now()
        due_dt     = now + timedelta(hours=sla_hrs)
        ticket_id  = f"CIMS{len(self.tickets)+1:06d}"

        rec = {
            "id":                ticket_id,
            "instruction_type":  inst_type,
            "category":          cfg.get("category", ""),
            "priority":          data.get("priority") or cfg.get("priority", "Medium"),
            "owner_unit":        owner_unit,
            "sla_hours":         sla_hrs,
            "customer_name":     data.get("customer_name", ""),
            "account_no":        data.get("account_no", ""),
            "amount":            data.get("amount", 0),
            "currency":          data.get("currency", "KES"),
            "originating_branch":data.get("originating_branch", ""),
            "originating_staff": data.get("originating_staff", ""),
            "description":       data.get("description", ""),
            "required_docs":     cfg.get("required_docs", []),
            "docs_received":     data.get("docs_received", False),
            "status":            "Open",
            "allocated_to_code": "",
            "allocated_to_name": "",
            "allocated_at":      None,
            "allocation_note":   "",
            "opened_at":         now.isoformat(),
            "due_at":            due_dt.isoformat(),
            "first_response_at": None,
            "resolved_at":       None,
            "resolution_notes":  "",
            "breached":          False,
            "tat_hours":         None,
            "escalation_level":  0,
            "audit_trail":       [{
                "action":    "Raised",
                "by":        data.get("originating_staff", ""),
                "at":        now.isoformat(),
                "note":      f"Instruction raised — due {due_dt.strftime('%d %b %Y %H:%M')}",
            }],
        }
        self.tickets.append(rec)
        self._save_tickets()

        # Auto-assign if mode is "auto"
        if self.auto_config.get("mode") == "auto":
            self._auto_assign(rec)

        return rec

    def _auto_assign(self, ticket: dict):
        """Auto-assign ticket to available staff in owner unit (round-robin, skip leave)."""
        unit = ticket.get("owner_unit","")
        staff_pool = self.auto_config.get("unit_map",{}).get(unit, [])
        if not staff_pool:
            return  # no mapping configured, leave unassigned

        # Get leave records to exclude staff on leave
        on_leave = set()
        if self.auto_config.get("exclude_on_leave", True):
            try:
                leave_file = DATA_DIR / "leave_records.json"
                if leave_file.exists():
                    records = json.loads(leave_file.read_text())
                    today   = datetime.now().date().isoformat()
                    on_leave = {r["staff_code"] for r in records
                                if r.get("status") == "Active"
                                and r.get("start_date","") <= today <= r.get("end_date","9999")}
            except:
                pass

        available = [s for s in staff_pool if s.get("code","") not in on_leave]
        if not available:
            available = staff_pool  # everyone on leave — assign anyway

        # Round-robin index
        rr = self.auto_config.get("round_robin", {})
        idx = rr.get(unit, 0) % len(available)
        chosen = available[idx]
        rr[unit] = (idx + 1) % len(available)
        self.auto_config["round_robin"] = rr
        self.save_auto_config()

        # Assign
        for t in self.tickets:
            if t["id"] == ticket["id"]:
                t["status"]            = "Allocated"
                t["allocated_to_code"] = chosen.get("code","")
                t["allocated_to_name"] = chosen.get("name","")
                t["allocated_at"]      = datetime.now().isoformat()
                t["allocation_note"]   = "Auto-assigned (round-robin, leave-aware)"
                if not t.get("first_response_at"):
                    t["first_response_at"] = t.get("allocated_at", "")
                t.setdefault("audit_trail", []).append({
                    "action": "Auto-allocated",
                    "by":     "SYSTEM",
                    "at":     datetime.now().isoformat(),
                    "note":   f"Auto-assigned to {chosen.get('name','')} (round-robin)",
                })
        self._save_tickets()

    def reroute_ticket(self, ticket_id: str, new_staff_code: str,
                       new_staff_name: str, reason: str, by: str):
        """Staff member reroutes their ticket to someone else."""
        for t in self.tickets:
            if t["id"] == ticket_id:
                old_name = t.get("allocated_to_name","")
                t["allocated_to_code"] = new_staff_code
                t["allocated_to_name"] = new_staff_name
                t["status"]            = "Allocated"
                t.setdefault("audit_trail", []).append({
                    "action": f"Rerouted from {old_name}",
                    "by":     by,
                    "at":     datetime.now().isoformat(),
                    "note":   reason,
                })
                self._save_tickets()
                return t
        return {}

    def save_document(self, ticket_id: str, filename: str,
                      file_bytes: bytes, uploaded_by: str) -> str:
        """Save uploaded document for a ticket. Returns saved path."""
        tick_dir = CIMS_DOCS_DIR / ticket_id
        tick_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
        save_path = tick_dir / safe_name
        save_path.write_bytes(file_bytes)
        # Record in ticket
        for t in self.tickets:
            if t["id"] == ticket_id:
                if "documents" not in t:
                    t["documents"] = []
                t["documents"].append({
                    "filename":    safe_name,
                    "uploaded_by": uploaded_by,
                    "uploaded_at": datetime.now().isoformat(),
                    "size_kb":     round(len(file_bytes)/1024, 1),
                })
                self._save_tickets()
                break
        return str(save_path)

    def get_documents(self, ticket_id: str) -> list:
        for t in self.tickets:
            if t["id"] == ticket_id:
                return t.get("documents", [])
        return []

    def allocate(self, ticket_id: str, staff_code: str, staff_name: str,
                 note: str, by: str) -> dict:
        """Allocate an open instruction to a specific staff member."""
        for t in self.tickets:
            if t["id"] == ticket_id:
                now = datetime.now()
                t["status"]            = "Allocated"
                t["allocated_to_code"] = staff_code
                t["allocated_to_name"] = staff_name
                t["allocated_at"]      = now.isoformat()
                t["allocation_note"]   = note
                if not t.get("first_response_at"):
                    t["first_response_at"] = now.isoformat()
                t.setdefault("audit_trail", []).append({
                    "action": "Allocated",
                    "by":     by,
                    "at":     now.isoformat(),
                    "note":   f"Allocated to {staff_name}. {note}",
                })
                self._save_tickets()
                return t
        return {}

    def update_status(self, ticket_id: str, new_status: str,
                      note: str, by: str) -> dict:
        for t in self.tickets:
            if t["id"] == ticket_id:
                now       = datetime.now()
                old_status= t["status"]
                t["status"] = new_status
                if new_status == "In Progress" and not t.get("first_response_at"):
                    t["first_response_at"] = now.isoformat()
                if new_status == "Resolved":
                    t["resolved_at"]     = now.isoformat()
                    opened  = datetime.fromisoformat(t["opened_at"][:19])
                    tat_hrs = round((now - opened).total_seconds() / 3600, 2)
                    t["tat_hours"]   = tat_hrs
                    due_dt  = datetime.fromisoformat(t["due_at"][:19])
                    t["breached"]    = now > due_dt
                    t["resolution_notes"] = note
                t.setdefault("audit_trail", []).append({
                    "action": f"Status → {new_status}",
                    "by":     by,
                    "at":     now.isoformat(),
                    "note":   note,
                })
                self._save_tickets()
                return t
        return {}

    def escalate(self, ticket_id: str, by: str) -> dict:
        for t in self.tickets:
            if t["id"] == ticket_id:
                t["escalation_level"] = t.get("escalation_level", 0) + 1
                t["status"] = "Escalated"
                t.setdefault("audit_trail", []).append({
                    "action": "Escalated",
                    "by": by,
                    "at": datetime.now().isoformat(),
                    "note": f"Escalated to level {t['escalation_level']}",
                })
                self._save_tickets()
                return t
        return {}

    # ── Analytics & scoring ───────────────────────────────────
    def tat_score(self, staff_code: str = None, unit: str = None,
                  days_back: int = 30) -> dict:
        """
        TAT score = (tickets resolved within SLA / total resolved) × 100
        Returns dict with score, total, breached, avg_tat_hours.
        """
        cutoff   = datetime.now() - timedelta(days=days_back)
        resolved = [t for t in self.tickets
                    if t.get("status") == "Resolved"
                    and t.get("resolved_at")
                    and datetime.fromisoformat(t["resolved_at"][:19]) >= cutoff]

        if staff_code:
            resolved = [t for t in resolved
                        if t.get("allocated_to_code") == str(staff_code)]
        if unit and unit != "All":
            resolved = [t for t in resolved if t.get("owner_unit") == unit]

        if not resolved:
            return {"score": 1.0, "total": 0, "breached": 0, "avg_tat": 0,
                    "by_type": {}, "by_priority": {}}

        total    = len(resolved)
        breached = sum(1 for t in resolved if t.get("breached"))
        score    = round((total - breached) / total, 4) if total else 0.0
        avg_tat  = round(sum(t.get("tat_hours", 0) or 0 for t in resolved) / max(total, 1), 2)

        by_type = {}
        by_pri  = {}
        for t in resolved:
            it = t.get("instruction_type", "Unknown")
            pr = t.get("priority", "Medium")
            if it not in by_type:
                by_type[it] = {"total":0,"breached":0}
            if pr not in by_pri:
                by_pri[pr]  = {"total":0,"breached":0}
            by_type[it]["total"] += 1
            by_pri[pr]["total"]  += 1
            if t.get("breached"):
                by_type[it]["breached"] += 1
                by_pri[pr]["breached"]  += 1

        return {"score": score, "total": total, "breached": breached,
                "avg_tat": avg_tat, "by_type": by_type, "by_priority": by_pri}

    def unit_performance(self, days_back: int = 30) -> pd.DataFrame:
        rows = []
        for unit in OWNER_UNITS:
            result = self.tat_score(unit=unit, days_back=days_back)
            open_t = [t for t in self.tickets
                      if t.get("owner_unit")==unit and t.get("status") not in ("Resolved","Cancelled")]
            overdue = sum(1 for t in open_t
                          if datetime.now() > datetime.fromisoformat(t["due_at"][:19]))
            unalloc = sum(1 for t in open_t if not t.get("allocated_to_code"))
            rows.append({
                "Unit":            unit,
                "Open":            len(open_t),
                "Overdue":         overdue,
                "Unallocated":     unalloc,
                "Resolved (30d)":  result["total"],
                "Breached":        result["breached"],
                "TAT Score":       result["score"],
                "Avg TAT (hrs)":   result["avg_tat"],
            })
        return pd.DataFrame(rows).sort_values("TAT Score")

    def staff_tat_scores(self, days_back: int = 30) -> pd.DataFrame:
        """Per-staff TAT scores — feeds BSC."""
        if len(staff_scores) == 0:
            return pd.DataFrame()
        rows = []
        for _, sr in staff_scores.iterrows():
            sc   = str(sr["Staff Code"])
            res  = self.tat_score(staff_code=sc, days_back=days_back)
            if res["total"] > 0:
                rows.append({
                    "Staff Code":  sc,
                    "Staff Name":  sr["Staff Name"],
                    "Unit":        sr.get("Unit", ""),
                    "Role":        sr.get("Role", ""),
                    "Tickets":     res["total"],
                    "Breached":    res["breached"],
                    "TAT Score":   res["score"],
                    "Avg TAT (h)": res["avg_tat"],
                    "Rating": ("🟢 Excellent" if res["score"] >= 0.95 else
                               ("🟡 Good"     if res["score"] >= 0.85 else
                                ("🟠 At risk"  if res["score"] >= 0.70 else "🔴 Critical"))),
                })
        return pd.DataFrame(rows).sort_values("TAT Score")

    def get_open(self, unit: str = None, staff_code: str = None,
                 include_overdue_only: bool = False) -> list:
        now  = datetime.now()
        open_t = [t for t in self.tickets
                  if t.get("status") not in ("Resolved","Cancelled")]
        for t in open_t:
            try:
                due = datetime.fromisoformat(t["due_at"][:19])
                t["_overdue"]       = now > due
                t["_hours_remaining"] = round((due - now).total_seconds()/3600, 1)
                opened = datetime.fromisoformat(t["opened_at"][:19])
                t["_age_hours"] = round((now - opened).total_seconds()/3600, 1)
                t["_unallocated"] = not t.get("allocated_to_code")
            except:
                t["_overdue"] = False
                t["_hours_remaining"] = 0
                t["_age_hours"]       = 0
                t["_unallocated"]     = True
        if unit and unit != "All":
            open_t = [t for t in open_t if t.get("owner_unit") == unit]
        if staff_code:
            open_t = [t for t in open_t if t.get("allocated_to_code") == str(staff_code)]
        if include_overdue_only:
            open_t = [t for t in open_t if t.get("_overdue")]
        return sorted(open_t, key=lambda x: (not x.get("_overdue"), x.get("_hours_remaining", 999)))


# ── Initialise ───────────────────────────────────────────────────────
if "cims_manager" not in st.session_state:
    st.session_state["cims_manager"] = CIMSManager()
cims = st.session_state.get("cims_manager")
if cims is None: st.info("CIMS loading..."); st.stop()

role_low  = str(ud.get("role","")).lower()
is_admin  = "admin" in role_low or ud.get("can_view_all", False)
my_unit   = ud.get("unit", "")
my_sc     = str(ud.get("staff_code", ""))
is_mgr    = any(k in role_low for k in
                ("manager","director","head","regional","chief","admin"))

# ── Build unit → staff mapping ────────────────────────────────────────
unit_staff_map: dict = {}
if len(staff_scores):
    for _, sr in staff_scores.iterrows():
        u = str(sr.get("Unit",""))
        unit_staff_map.setdefault(u, []).append({
            "code": str(sr["Staff Code"]),
            "name": sr["Staff Name"],
            "role": sr.get("Role",""),
        })

# ════════════════════════════════════════════════════════════════
# PAGE HEADER
# ════════════════════════════════════════════════════════════════


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📨 CIMS</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Customer instructions · Processing · SLA</span></div>",
    unsafe_allow_html=True)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📨 CIMS</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Customer instructions · Processing</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📨 CIMS</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Customer instructions · Processing · SLA</span></div>",
    unsafe_allow_html=True)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📨 CIMS</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Customer instructions · SLA · Escalations</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style=\'padding:16px 22px;background:#1A252F;border-radius:12px;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.15)\'><div style=\'display:flex;align-items:center;justify-content:space-between\'><div><div style=\'color:var(--color-background-primary);font-size:16px;font-weight:700;letter-spacing:-0.2px\'>CIMS — Customer Instruction Management System</div><div style=\'color:rgba(255,255,255,0.65);font-size:11px;margin-top:3px;font-weight:400\'>Raise · Allocate · Track · Resolve · Score TAT performance across all processing units</div></div><div style=\'opacity:0.12;font-size:36px;line-height:1;color:white\'>◆</div></div></div>",
    unsafe_allow_html=True)

tabs = st.tabs([
    "📊 Command centre",
    "➕ Raise instruction",
    "📋 Allocate & manage",
    "👤 My instructions",
    "📈 TAT performance",
    "🏆 Unit scoreboard",
    "⚙️ Admin / SLA config",
])

# ════════════════════════════════════════════════════════════════
# TAB 1 — COMMAND CENTRE
# ════════════════════════════════════════════════════════════════
with tabs[0]:
    open_all    = cims.get_open()
    overdue_all = [t for t in open_all if t.get("_overdue")]
    unalloc_all = [t for t in open_all if t.get("_unallocated")]
    resolved_30 = [t for t in cims.tickets
                   if t.get("status")=="Resolved" and t.get("resolved_at")
                   and datetime.fromisoformat(t["resolved_at"][:19])
                   >= datetime.now()-timedelta(days=30)]
    breached_30 = [t for t in resolved_30 if t.get("breached")]
    overall_score = (len(resolved_30)-len(breached_30))/max(len(resolved_30),1)

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("Open instructions",  len(open_all))
    c2.metric("Overdue now",        len(overdue_all),
              delta=f"-{len(overdue_all)}" if overdue_all else "0", delta_color="inverse")
    c3.metric("Unallocated",        len(unalloc_all),
              delta=f"-{len(unalloc_all)}" if unalloc_all else "0", delta_color="inverse")
    c4.metric("Resolved (30d)",     len(resolved_30))
    c5.metric("Breached (30d)",     len(breached_30),
              delta_color="inverse")
    c6.metric("TAT score",          f"{overall_score:.1%}",
              delta="Target: 90%",
              delta_color="normal" if overall_score >= 0.9 else "inverse")

    # TAT gauge
    ga1, ga2 = st.columns(2)
    with ga1:
        score_clr = 'var(--brand-primary,#006B3F)' if overall_score>=0.9 else ('#F5A623' if overall_score>=0.75 else '#E24B4A')
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=overall_score*100,
            delta={"reference": 90, "suffix": "%"},
            title={"text": "Network TAT Score (%)"},
            gauge={
                "axis":  {"range": [0, 100]},
                "bar":   {"color": score_clr},
                "steps": [
                    {"range":[0,70],  "color":"#FDEDEC"},
                    {"range":[70,90], "color":"#FEF6E4"},
                    {"range":[90,100],"color":"var(--brand-light,#E8F5EE)"},
                ],
                "threshold": {"line":{"color":"var(--brand-primary,#006B3F)","width":3},"value":90},
            }))
        fig_g.update_layout(height=240, paper_bgcolor='rgba(0,0,0,0)',
                            margin=dict(l=20,r=20,t=40,b=20))
        st.plotly_chart(fig_g, use_container_width=True)

    with ga2:
        unit_df = cims.unit_performance()
        if not unit_df.empty:
            def hl_tat(v):
                try:
                    fv = float(v)
                    if fv >= 0.95: return 'color:var(--brand-primary,#006B3F);font-weight:600'
                    if fv >= 0.85: return 'color:#F5A623'
                    return 'color:#E24B4A;font-weight:600'
                except: return ''
            unit_disp = unit_df.copy()
            unit_disp["TAT Score"] = unit_disp["TAT Score"].apply(lambda x: f"{x:.1%}")
            st.markdown("**Unit performance**")
            st.dataframe(
                unit_disp.style.map(hl_tat, subset=["TAT Score"]),
                use_container_width=True, hide_index=True, height=220)

    # Age buckets — how long have open tickets been waiting?
    _age_buckets = {"< 1 day": 0, "1–2 days": 0, "2–5 days": 0, "5–14 days": 0, "> 14 days": 0}
    for _t in open_all:
        try:
            _age_h = (datetime.now() - datetime.fromisoformat(_t["created_at"][:19])).total_seconds()/3600
            if   _age_h < 24:   _age_buckets["< 1 day"]    += 1
            elif _age_h < 48:   _age_buckets["1–2 days"]   += 1
            elif _age_h < 120:  _age_buckets["2–5 days"]   += 1
            elif _age_h < 336:  _age_buckets["5–14 days"]  += 1
            else:               _age_buckets["> 14 days"]  += 1
        except: pass
    if any(_age_buckets.values()):
        _ab_df = pd.DataFrame(list(_age_buckets.items()), columns=["Age","Count"])
        _ab_fig = px.bar(_ab_df, x="Age", y="Count",
                         title="Open instructions by age",
                         color="Count",
                         color_continuous_scale=["var(--brand-primary,#006B3F)","#F5A623","#E24B4A"])
        _ab_fig.update_layout(height=200, showlegend=False,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0,r=0,t=30,b=0), coloraxis_showscale=False)
        st.plotly_chart(_ab_fig, use_container_width=True)

    # Overdue alerts
    if overdue_all:
        st.markdown(f"#### 🔴 {len(overdue_all)} overdue instruction(s) — immediate action required")
        for t in overdue_all[:10]:
            hrs = abs(t.get("_hours_remaining", 0))
            pri_clr = PRIORITY_COLORS.get(t.get("priority","Medium"),"#888")
            alloc = t.get("allocated_to_name","Unallocated") or "Unallocated"
            st.markdown(
                f"<div style='padding:8px 14px;background:#FFF0F0;"
                f"border-left:4px solid #E24B4A;border-radius:0 6px 6px 0;margin:3px 0;font-size:12px'>"
                f"<div style='display:flex;justify-content:space-between'>"
                f"<span><b>{t['id']}</b> · {t['instruction_type']} "
                f"<span style='background:{pri_clr};color:var(--color-background-primary);padding:1px 5px;"
                f"border-radius:8px;font-size:10px'>{t['priority']}</span></span>"
                f"<span style='color:#E24B4A;font-weight:600'>🔴 {hrs:.1f}h overdue</span></div>"
                f"<div style='color:#666;margin-top:2px'>"
                f"{t.get('customer_name','')} · {t.get('originating_branch','')} → {t.get('owner_unit','')} "
                f"· Assigned: {alloc}</div>"
                f"</div>", unsafe_allow_html=True)

    # Unallocated — needs a manager to assign
    if unalloc_all:
        st.markdown(f"#### ⚠️ {len(unalloc_all)} unallocated instruction(s)")
        for t in unalloc_all[:8]:
            hrs = t.get("_hours_remaining", 0)
            hrs_clr = "#E24B4A" if hrs < 4 else ("#F5A623" if hrs < 24 else "#185FA5")
            st.markdown(
                f"<div style='padding:7px 12px;background:#FFFBF0;"
                f"border-left:3px solid #F5A623;border-radius:0 5px 5px 0;margin:2px 0;font-size:11px'>"
                f"<b>{t['id']}</b> · {t['instruction_type']} · {t.get('owner_unit','')} "
                f"· <span style='color:{hrs_clr}'>{hrs:.1f}h remaining</span></div>",
                unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# TAB 2 — RAISE INSTRUCTION
# ════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Raise a customer instruction")
    st.caption("Log any customer request that requires processing, approval or action "
               "by another unit. The instruction is automatically routed and timed against the SLA.")

    with st.form("raise_cims_form"):
        # Instruction type
        inst_categories = sorted(set(v.get("category","Other")
                                     for v in cims.config.values()))
        cat_sel = st.selectbox("Category", inst_categories, key="raise_cat")
        inst_types_in_cat = [k for k,v in cims.config.items()
                              if v.get("category","") == cat_sel]
        inst_sel = st.selectbox("Instruction type *", inst_types_in_cat, key="raise_inst")

        if inst_sel and inst_sel in cims.config:
            cfg = cims.config[inst_sel]
            st.markdown(
                f"<div style='padding:6px 10px;background:#EBF0F7;"
                f"border-left:3px solid #185FA5;font-size:11px;margin:4px 0'>"
                f"SLA: <b>{cfg['sla_hours']}h</b> · Priority: <b>{cfg['priority']}</b> · "
                f"Owner unit: <b>{cfg['owner_unit']}</b><br>"
                f"📋 Required docs: {', '.join(cfg.get('required_docs',[]) or ['None specified'])}"
                f"</div>", unsafe_allow_html=True)

        rc1, rc2 = st.columns(2)
        cust_name  = rc1.text_input("Customer name *")
        acct_no    = rc2.text_input("Account number")
        rc3, rc4   = st.columns(2)
        amount_val = rc3.number_input("Amount (KES)", min_value=0.0, step=10000.0, format="%.0f")
        currency   = rc4.selectbox("Currency", ["KES","USD","EUR","GBP","ZAR"])

        # Originating branch
        all_branches = sorted(set(staff_scores["Unit"].tolist())
                               if len(staff_scores) and "Unit" in staff_scores.columns
                               else [])
        orig_branch = st.selectbox("Originating branch / unit *",
                                    all_branches or ["Head Office"])
        desc = st.text_area("Instruction details / notes", height=70)
        docs_recd = st.checkbox("Required documents received from customer")

        st.markdown("**Supporting documents** (optional — upload later too)")
        uploaded_docs = st.file_uploader(
            "Attach documents",
            type=["pdf","docx","xlsx","jpg","jpeg","png","msg","eml"],
            accept_multiple_files=True,
            key="raise_docs",
            help="Upload required documents: ID, forms, contracts, etc.")

        if st.form_submit_button("📤 Raise instruction", type="primary"):
            if inst_sel and cust_name and orig_branch:
                my_row = (staff_scores[staff_scores["Staff Code"].astype(str)==my_sc]
                          if len(staff_scores) else pd.DataFrame())
                my_name = my_row["Staff Name"].values[0] if len(my_row) else uname
                ticket  = cims.raise_instruction({
                    "instruction_type":   inst_sel,
                    "customer_name":      cust_name,
                    "account_no":         acct_no,
                    "amount":             amount_val,
                    "currency":           currency,
                    "originating_branch": orig_branch,
                    "originating_staff":  my_name,
                    "description":        desc,
                    "docs_received":      docs_recd,
                })
                audit_log("CIMS_RAISED", uname,
                          f"{ticket['id']}:{inst_sel}:{cust_name}")
                # Save uploaded documents
                if uploaded_docs:
                    for doc in uploaded_docs:
                        cims.save_document(ticket['id'], doc.name,
                                           doc.read(), uname)
                cfg_sel = cims.config.get(inst_sel, {})
                due_str = datetime.fromisoformat(ticket["due_at"][:19]).strftime("%d %b %Y %H:%M")
                st.success(
                    f"✅ **{ticket['id']}** raised — {inst_sel} → {cfg_sel.get('owner_unit','Operations')} "
                    f"| Due by: **{due_str}**")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Instruction type, customer name and originating branch are required.")

# ════════════════════════════════════════════════════════════════
# TAB 3 — ALLOCATE & MANAGE
# ════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Allocate and manage instructions")
    if not is_mgr:
        st.info("Allocation is available to unit managers. "
                "You can view and update your own instructions in 'My instructions'.")
        st.stop()

    # Unit filter
    if is_admin:
        mgmt_unit = st.selectbox("Unit", ["All"] + OWNER_UNITS, key="mgmt_unit")
    else:
        mgmt_unit = my_unit or "All"

    open_tickets = cims.get_open(unit=mgmt_unit if mgmt_unit!="All" else None)
    unalloc      = [t for t in open_tickets if t.get("_unallocated")]
    allocated    = [t for t in open_tickets if not t.get("_unallocated")]

    ma1, ma2, ma3 = st.columns(3)
    ma1.metric("Open in queue",   len(open_tickets))
    ma2.metric("Unallocated",     len(unalloc),
               delta=f"-{len(unalloc)}" if unalloc else "0", delta_color="inverse")
    ma3.metric("Overdue",
               len([t for t in open_tickets if t.get("_overdue")]),
               delta_color="inverse")

    # ── Unallocated — needs manager assignment ────────────────
    if unalloc:
        st.markdown(f"#### Unallocated ({len(unalloc)}) — assign now")
        for t in unalloc:
            overdue_flag = t.get("_overdue", False)
            hrs_rem      = t.get("_hours_remaining", 0)
            pri_clr      = PRIORITY_COLORS.get(t.get("priority","Medium"),"#888")
            border_clr   = "#E24B4A" if overdue_flag else pri_clr

            with st.expander(
                f"{'🔴' if overdue_flag else '⚠️'} {t['id']} — "
                f"{t['instruction_type']} | {t.get('customer_name','')} | "
                f"{'OVERDUE' if overdue_flag else f'{hrs_rem:.1f}h left'}",
                expanded=overdue_flag):

                ec1, ec2 = st.columns(2)
                ec1.markdown(
                    f"**Customer:** {t.get('customer_name','')}  \n"
                    f"**Account:** {t.get('account_no','')}  \n"
                    f"**Amount:** {t.get('currency','KES')} {t.get('amount',0):,.0f}  \n"
                    f"**From:** {t.get('originating_branch','')}  \n"
                    f"**Docs received:** {'✅' if t.get('docs_received') else '❌ No'}")
                ec2.markdown(
                    f"**Category:** {t.get('category','')}  \n"
                    f"**Priority:** {t.get('priority','')}  \n"
                    f"**Owner unit:** {t.get('owner_unit','')}  \n"
                    f"**Raised at:** {t.get('opened_at','')[:16]}  \n"
                    f"**Due at:** {t.get('due_at','')[:16]}")
                if t.get("description"):
                    st.caption(f"Details: {t['description']}")

                # Allocate form
                owner_unit = t.get("owner_unit","Operations")
                unit_members = unit_staff_map.get(owner_unit, [])
                if not unit_members and len(staff_scores):
                    # Fallback: all staff
                    unit_members = [
                        {"code": str(r["Staff Code"]),
                         "name": r["Staff Name"],
                         "role": r.get("Role","")}
                        for _, r in staff_scores.iterrows()]
                staff_opts = {f"{s['name']} ({s['role']})": s["code"]
                              for s in unit_members}

                with st.form(f"alloc_{t['id']}"):
                    af1, af2 = st.columns(2)
                    sel_staff_lbl = af1.selectbox(
                        f"Assign to ({owner_unit})",
                        list(staff_opts.keys()) or ["— no staff mapped —"],
                        key=f"alloc_staff_{t['id']}")
                    alloc_note = af2.text_input("Note / instruction",
                                               key=f"alloc_note_{t['id']}")
                    if st.form_submit_button("✅ Allocate", type="primary"):
                        sc = staff_opts.get(sel_staff_lbl, "")
                        cims.allocate(t["id"], sc, sel_staff_lbl.split("(")[0].strip(),
                                      alloc_note, uname)
                        audit_log("CIMS_ALLOCATED", uname,
                                  f"{t['id']} → {sel_staff_lbl}")
                        st.success(f"Allocated to {sel_staff_lbl.split('(')[0].strip()}")
                        st.cache_data.clear()
                        st.rerun()

    # ── Allocated — update status ─────────────────────────────
    if allocated:
        st.markdown(f"#### In progress ({len(allocated)})")
        for t in allocated:
            overdue_flag = t.get("_overdue", False)
            hrs_rem      = t.get("_hours_remaining", 0)
            stat_clr     = STATUS_COLORS.get(t.get("status","Open"),"#888")
            border_clr   = "#E24B4A" if overdue_flag else stat_clr

            with st.expander(
                f"{t['id']} — {t['instruction_type']} | "
                f"Assigned: {t.get('allocated_to_name','—')} | "
                f"Status: {t.get('status','')} | "
                f"{'🔴 OVERDUE' if overdue_flag else f'{hrs_rem:.1f}h left'}"):

                st.markdown(
                    f"**Customer:** {t.get('customer_name','')} · "
                    f"**Account:** {t.get('account_no','')} · "
                    f"**Amount:** {t.get('currency','KES')} {t.get('amount',0):,.0f}  \n"
                    f"**Assigned to:** {t.get('allocated_to_name','—')} "
                    f"at {t.get('allocated_at','—')[:16]}")

                with st.form(f"status_{t['id']}"):
                    sf1, sf2 = st.columns(2)
                    new_stat = sf1.selectbox("New status",
                        [s for s in TICKET_STATUSES if s != t.get("status")],
                        key=f"stat_{t['id']}")
                    stat_note = sf2.text_input("Notes",
                                              key=f"stat_note_{t['id']}")
                    if st.form_submit_button("Update status", type="primary"):
                        cims.update_status(t["id"], new_stat, stat_note, uname)
                        audit_log("CIMS_STATUS", uname,
                                  f"{t['id']} → {new_stat}")
                        st.success(f"Status updated to {new_stat}")
                        st.cache_data.clear()
                        st.rerun()

# ════════════════════════════════════════════════════════════════
# TAB 4 — MY INSTRUCTIONS
# ════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("My instructions")
    st.caption("Instructions allocated to you. Resolve them within the SLA to maintain your TAT score.")

    my_open   = cims.get_open(staff_code=my_sc)
    my_resolved = [t for t in cims.tickets
                   if t.get("allocated_to_code")==my_sc
                   and t.get("status")=="Resolved"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Assigned to me",   len(my_open))
    m2.metric("Overdue",
              len([t for t in my_open if t.get("_overdue")]),
              delta_color="inverse")
    m3.metric("Resolved (all time)", len(my_resolved))
    my_tat = cims.tat_score(staff_code=my_sc)
    m4.metric("My TAT score",     f"{my_tat['score']:.1%}",
              delta="Target: 90%",
              delta_color="normal" if my_tat['score']>=0.9 else "inverse")

    if not my_open:
        st.success("No open instructions assigned to you. 🎉")
    else:
        for t in my_open:
            overdue_flag = t.get("_overdue", False)
            hrs_rem      = t.get("_hours_remaining", 0)
            pri_clr      = PRIORITY_COLORS.get(t.get("priority","Medium"),"#888")
            border_clr   = "#E24B4A" if overdue_flag else pri_clr

            st.markdown(
                f"<div style='padding:9px 14px;background:var(--color-background-secondary);"
                f"border-left:4px solid {border_clr};border-radius:0 6px 6px 0;margin:4px 0'>"
                f"<div style='display:flex;justify-content:space-between'>"
                f"<div><b>{t['id']}</b> · {t['instruction_type']} "
                f"<span style='background:{pri_clr};color:var(--color-background-primary);padding:1px 5px;"
                f"border-radius:8px;font-size:10px'>{t['priority']}</span></div>"
                f"<span style='color:{border_clr};font-weight:600'>"
                f"{'🔴 OVERDUE ' + str(abs(hrs_rem))[:4] + 'h' if overdue_flag else '⏱ ' + str(hrs_rem)[:4] + 'h left'}"
                f"</span></div>"
                f"<div style='color:#666;font-size:11px;margin-top:3px'>"
                f"Customer: {t.get('customer_name','')} · "
                f"Account: {t.get('account_no','')} · "
                f"From: {t.get('originating_branch','')} · "
                f"Status: {t.get('status','')}</div>"
                f"</div>", unsafe_allow_html=True)

            with st.form(f"my_{t['id']}"):
                mf1, mf2 = st.columns(2)
                new_s    = mf1.selectbox("Update status",
                    [s for s in TICKET_STATUSES if s != t.get("status")],
                    key=f"my_stat_{t['id']}")
                res_note = mf2.text_input("Resolution / notes",
                                          key=f"my_note_{t['id']}")
                sub_cols = st.columns(2)
                if sub_cols[0].form_submit_button("Submit update", type="primary"):
                    cims.update_status(t["id"], new_s, res_note, uname)
                    audit_log("CIMS_MY_UPDATE", uname, f"{t['id']} → {new_s}")
                    st.success(f"Updated to {new_s}")
                    st.cache_data.clear()
                    st.rerun()

            # Document upload (outside form so it works independently)
            docs = cims.get_documents(t["id"])
            with st.expander(f"📎 Documents ({len(docs)})", expanded=False):
                if docs:
                    for d in docs:
                        st.markdown(
                            f"<div style='padding:4px 8px;background:var(--color-background-secondary);"
                            f"border-radius:6px;font-size:11px;margin:2px 0'>"
                            f"📄 <b>{d['filename']}</b> · {d['size_kb']} KB "
                            f"· {d['uploaded_at'][:10]} by {d['uploaded_by']}"
                            f"</div>", unsafe_allow_html=True)
                up_file = st.file_uploader(
                    "Upload document",
                    type=["pdf","docx","xlsx","jpg","jpeg","png","msg","eml"],
                    key=f"doc_up_{t['id']}")
                if up_file:
                    cims.save_document(t["id"], up_file.name, up_file.read(), uname)
                    st.toast(f"✅ {up_file.name} uploaded", icon="📎")
                    st.cache_data.clear()
                    st.rerun()

            # Reroute option
            if t.get("status") not in ("Resolved","Cancelled"):
                with st.expander("🔀 Reroute to someone else", expanded=False):
                    unit_members_r = unit_staff_map.get(t.get("owner_unit",""), [])
                    if unit_members_r:
                        rr_opts = {f"{s['name']} ({s['role']})": s["code"]
                                   for s in unit_members_r
                                   if s["code"] != my_sc}
                        if rr_opts:
                            rr_sel  = st.selectbox("Reroute to", list(rr_opts.keys()),
                                                    key=f"rr_{t['id']}")
                            rr_note = st.text_input("Reason for rerouting",
                                                     key=f"rr_note_{t['id']}")
                            if st.button("🔀 Confirm reroute", key=f"rr_btn_{t['id']}",
                                         type="secondary"):
                                new_sc_r = rr_opts[rr_sel]
                                cims.reroute_ticket(
                                    t["id"], new_sc_r,
                                    rr_sel.split("(")[0].strip(),
                                    rr_note or "Rerouted by staff", uname)
                                audit_log("CIMS_REROUTE", uname, f"{t['id']} → {rr_sel}")
                                st.toast("✅ Ticket rerouted", icon="🔀")
                                st.cache_data.clear()
                                st.rerun()
                        else:
                            st.info("No other staff available in this unit.")

# ════════════════════════════════════════════════════════════════
# TAB 5 — TAT PERFORMANCE
# ════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("TAT performance analytics")
    st.caption(
        "TAT Score = instructions resolved within SLA ÷ total resolved. "
        "This score feeds directly into the Credit Approval TAT and "
        "Procurement TAT KPIs in each staff member's BSC.")

    days_back = st.slider("Period (days)", 7, 90, 30, key="tat_days")

    if not cims.tickets:
        st.info("No CIMS tickets yet. Raise instructions to start tracking TAT performance.")
    else:
        staff_tat = cims.staff_tat_scores(days_back)
        if not staff_tat.empty:
            # Chart
            fig_tat = px.bar(
                staff_tat.sort_values("TAT Score"),
                x="Staff Name", y="TAT Score",
                color="TAT Score",
                color_continuous_scale=["#E24B4A","#F5A623","var(--brand-primary,#006B3F)"],
                range_color=[0,1],
                title=f"Staff TAT scores — last {days_back} days",
                hover_data={"Tickets":True,"Breached":True,"Avg TAT (h)":True})
            fig_tat.add_hline(y=0.90, line_dash="dash", line_color="var(--brand-primary,#006B3F)",
                               annotation_text="90% target")
            fig_tat.update_yaxes(tickformat=".0%")
            fig_tat.update_layout(height=340, xaxis_tickangle=-30,
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_tat, use_container_width=True)

            # Table
            disp_tat = staff_tat.copy()
            disp_tat["TAT Score"] = disp_tat["TAT Score"].apply(lambda x: f"{x:.1%}")
            def hl_tat_col(v):
                try:
                    fv = float(str(v).replace('%',''))/100
                    if fv >= 0.95: return 'color:var(--brand-primary,#006B3F);font-weight:600'
                    if fv >= 0.85: return 'color:#F5A623'
                    return 'color:#E24B4A;font-weight:600'
                except: return ''
            st.dataframe(
                disp_tat.style.map(hl_tat_col, subset=["TAT Score"]),
                use_container_width=True, hide_index=True)

        # Breach analysis by instruction type
        resolved_t = [t for t in cims.tickets if t.get("status")=="Resolved"]
        if resolved_t:
            bt_rows = {}
            for t in resolved_t:
                it = t.get("instruction_type","Unknown")
                bt_rows.setdefault(it, {"total":0,"breached":0,"avg_tat":[]})
                bt_rows[it]["total"] += 1
                if t.get("breached"): bt_rows[it]["breached"] += 1
                if t.get("tat_hours"): bt_rows[it]["avg_tat"].append(t["tat_hours"])
            bt_df = pd.DataFrame([{
                "Instruction Type": k[:30],
                "Total":    v["total"],
                "Breached": v["breached"],
                "Breach %": f"{v['breached']/v['total']*100:.0f}%",
                "Avg TAT (h)": round(sum(v["avg_tat"])/len(v["avg_tat"]),1) if v["avg_tat"] else 0,
            } for k,v in bt_rows.items()]).sort_values("Breached", ascending=False)

            st.markdown("#### Breach rate by instruction type")
            st.dataframe(bt_df, use_container_width=True, hide_index=True)
        else:
            st.info(f"No resolved tickets in the last {days_back} days.")

# ════════════════════════════════════════════════════════════════
# TAB 6 — UNIT SCOREBOARD
# ════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("Unit TAT scoreboard")
    st.caption("How each processing unit is performing against SLA targets.")

    unit_df = cims.unit_performance()
    if not unit_df.empty and unit_df["Resolved (30d)"].sum() > 0:
        fig_u = px.bar(
            unit_df.sort_values("TAT Score"),
            x="TAT Score", y="Unit",
            orientation="h",
            color="TAT Score",
            color_continuous_scale=["#E24B4A","#F5A623","var(--brand-primary,#006B3F)"],
            range_color=[0,1],
            title="Unit TAT scores — last 30 days",
            text=unit_df.sort_values("TAT Score")["TAT Score"].apply(lambda x: f"{x:.0%}"),
        )
        fig_u.add_vline(x=0.90, line_dash="dash", line_color="var(--brand-primary,#006B3F)",
                         annotation_text="Target 90%")
        fig_u.update_xaxes(tickformat=".0%")
        fig_u.update_layout(height=360,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_u, use_container_width=True)

    unit_disp = unit_df.copy()
    unit_disp["TAT Score"] = unit_disp["TAT Score"].apply(lambda x: f"{x:.1%}")
    def hl_unit_tat(v):
        try:
            fv = float(str(v).replace('%',''))/100
            if fv >= 0.95: return 'color:var(--brand-primary,#006B3F);font-weight:600'
            if fv >= 0.85: return 'color:#F5A623'
            return 'color:#E24B4A;font-weight:600'
        except: return ''
    st.dataframe(
        unit_disp.style.map(hl_unit_tat, subset=["TAT Score"]),
        use_container_width=True, hide_index=True)

    # Comparison radar — top 5 units
    if len(unit_df) >= 3 and unit_df["Resolved (30d)"].sum() > 0:
        top5 = unit_df.nlargest(5, "Resolved (30d)")
        radar_metrics = ["TAT Score","Open","Overdue","Unallocated"]
        max_vals = {m: max(unit_df[m].max(), 1) for m in radar_metrics[1:]}
        fig_r = go.Figure()
        for _, row in top5.iterrows():
            vals = [
                row["TAT Score"],
                1 - row["Open"]/max_vals["Open"],
                1 - row["Overdue"]/max_vals["Overdue"],
                1 - row["Unallocated"]/max_vals["Unallocated"],
            ]
            fig_r.add_scatterpolar(
                r=vals + [vals[0]],
                theta=["TAT Score","Open (inv)","Overdue (inv)","Unalloc (inv)","TAT Score"],
                fill="toself", name=row["Unit"])
        fig_r.update_layout(
            polar=dict(radialaxis=dict(range=[0,1])),
            height=380, title="Unit performance radar",
            legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig_r, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 7 — ADMIN / SLA CONFIG
# ════════════════════════════════════════════════════════════════
with tabs[6]:
    if not is_admin:
        st.info("Admin configuration is restricted to system administrators.")
        st.stop()

    st.subheader("CIMS administration")

    admin_tabs = st.tabs([
        "📋 Instruction types & SLAs",
        "➕ Add instruction type",
        "🗂️ Unit allocation matrix",
        "⚙️ Edit SLA",
        "🤖 Auto-assignment",
    ])

    # ── A: View all instruction types ────────────────────────
    with admin_tabs[0]:
        st.caption("All instruction types with their SLAs, priority, and owner unit. "
                   "Edit any row via the 'Edit SLA' tab.")
        rows = []
        for name, cfg in sorted(cims.config.items()):
            rows.append({
                "Instruction Type": name,
                "Category":         cfg.get("category",""),
                "SLA (hours)":      cfg.get("sla_hours",24),
                "Priority":         cfg.get("priority","Medium"),
                "Owner Unit":       cfg.get("owner_unit","Operations"),
                "Required Docs":    len(cfg.get("required_docs",[]) or []),
            })
        cfg_df = pd.DataFrame(rows)
        def hl_pri(v):
            clr = {"Critical":"#FDEDEC","High":"#FEF6E4",
                   "Medium":"#EAF2FB","Low":"#F2F3F4"}.get(str(v),"")
            return f"background-color:{clr}" if clr else ""
        st.dataframe(
            cfg_df.style.map(hl_pri, subset=["Priority"]),
            use_container_width=True, hide_index=True, height=500)

    # ── B: Add new instruction type ───────────────────────────
    with admin_tabs[1]:
        st.subheader("Add new instruction type")
        with st.form("add_inst_type"):
            at1, at2 = st.columns(2)
            new_name  = at1.text_input("Instruction type name *",
                placeholder="e.g. Fixed Deposit Rollover")
            new_cat   = at2.selectbox("Category",
                ["Credit & Lending","Account Operations","Trade Finance",
                 "Treasury & FX","Customer Service","Compliance","Card Services","Other"])
            at3, at4  = st.columns(2)
            new_sla   = at3.number_input("SLA (hours) *", min_value=0.5,
                                          value=24.0, step=0.5)
            new_pri   = at4.selectbox("Priority",
                ["Critical","High","Medium","Low"])
            new_unit  = st.selectbox("Owner unit *", OWNER_UNITS)
            new_desc  = st.text_area("Description", height=60)
            new_docs  = st.text_area("Required documents (one per line)", height=80,
                placeholder="e.g.\nCustomer ID\nSigned instruction form")
            if st.form_submit_button("Add instruction type", type="primary"):
                if new_name.strip():
                    docs_list = [d.strip() for d in new_docs.strip().split("\n") if d.strip()]
                    cims.add_instruction_type(new_name.strip(), {
                        "category":    new_cat,
                        "sla_hours":   new_sla,
                        "priority":    new_pri,
                        "owner_unit":  new_unit,
                        "description": new_desc,
                        "required_docs": docs_list,
                    })
                    audit_log("CIMS_INST_TYPE_ADDED", uname, new_name.strip())
                    st.success(f"✅ '{new_name}' added to CIMS instruction types.")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Instruction type name is required.")

    # ── C: Unit allocation matrix ─────────────────────────────
    with admin_tabs[2]:
        st.subheader("Unit → instruction type allocation matrix")
        st.caption(
            "This matrix shows which unit owns each instruction category. "
            "When a ticket is raised, it auto-routes to the owner unit's queue.")

        matrix_rows = {}
        for name, cfg in cims.config.items():
            unit = cfg.get("owner_unit","Operations")
            cat  = cfg.get("category","Other")
            matrix_rows.setdefault(unit, {}).setdefault(cat, 0)
            matrix_rows[unit][cat] += 1

        mat_df = pd.DataFrame(matrix_rows).T.fillna(0).astype(int)
        if not mat_df.empty:
            st.dataframe(mat_df, use_container_width=True)

        st.markdown("---")
        st.markdown("**Bulk reassign a category to a different unit:**")
        with st.form("bulk_reroute"):
            br1, br2, br3 = st.columns(3)
            br_cat   = br1.selectbox("Category to reassign",
                sorted(set(v.get("category","") for v in cims.config.values())))
            br_old   = br2.selectbox("Current owner unit", OWNER_UNITS)
            br_new   = br3.selectbox("New owner unit", OWNER_UNITS, index=1)
            if st.form_submit_button("Reassign", type="secondary"):
                count = 0
                for name, cfg in cims.config.items():
                    if cfg.get("category")==br_cat and cfg.get("owner_unit")==br_old:
                        cfg["owner_unit"] = br_new
                        count += 1
                cims.save_config()
                audit_log("CIMS_BULK_REROUTE", uname,
                          f"{br_cat}: {br_old}→{br_new} ({count} types)")
                st.success(f"✅ {count} instruction types in '{br_cat}' reassigned "
                           f"from {br_old} to {br_new}.")
                st.cache_data.clear()
                st.rerun()

    # ── D: Edit individual SLA ────────────────────────────────
    with admin_tabs[3]:
        st.subheader("Edit SLA for an instruction type")
        inst_to_edit = st.selectbox(
            "Select instruction type", sorted(cims.config.keys()), key="sla_edit_sel")

        if inst_to_edit:
            cur = cims.config.get(inst_to_edit, {})
            with st.form("edit_sla_form"):
                es1, es2 = st.columns(2)
                new_sla_hrs = es1.number_input(
                    "SLA hours", min_value=0.5,
                    value=float(cur.get("sla_hours", 24)), step=0.5)
                new_pri_ed  = es2.selectbox(
                    "Priority",
                    ["Critical","High","Medium","Low"],
                    index=["Critical","High","Medium","Low"].index(
                        cur.get("priority","Medium")))
                new_unit_ed = st.selectbox(
                    "Owner unit",
                    OWNER_UNITS,
                    index=OWNER_UNITS.index(cur.get("owner_unit","Operations"))
                    if cur.get("owner_unit","Operations") in OWNER_UNITS else 0)
                new_docs_ed = st.text_area(
                    "Required documents (one per line)",
                    value="\n".join(cur.get("required_docs", []) or []),
                    height=100)
                if st.form_submit_button("💾 Save SLA", type="primary"):
                    docs_l = [d.strip() for d in new_docs_ed.strip().split("\n") if d.strip()]
                    cims.update_sla(inst_to_edit, new_sla_hrs, new_pri_ed, new_unit_ed)
                    cims.config[inst_to_edit]["required_docs"] = docs_l
                    cims.save_config()
                    audit_log("CIMS_SLA_EDITED", uname,
                              f"{inst_to_edit}: {new_sla_hrs}h / {new_pri_ed} / {new_unit_ed}")
                    st.success(f"✅ SLA updated for '{inst_to_edit}'")
                    st.cache_data.clear()
                    st.rerun()

    # ── E: Auto-assignment configuration ─────────────────────────────
    with admin_tabs[4]:
        st.subheader("Auto-assignment configuration")
        st.caption(
            "Choose how new tickets are assigned: "
            "**Auto** (system assigns immediately, round-robin, skipping staff on leave) or "
            "**Team leader** (sits in unallocated queue for manager to assign).")

        cur_mode = cims.auto_config.get("mode","team_leader")
        new_mode = st.radio(
            "Assignment mode",
            ["auto", "team_leader"],
            format_func=lambda x: (
                "🤖 Auto-assign — system assigns immediately on ticket raise (round-robin, leave-aware)"
                if x=="auto" else
                "👤 Team leader — tickets queue for manager to manually allocate"),
            index=0 if cur_mode=="auto" else 1,
            key="auto_mode_sel")

        excl_leave = st.checkbox(
            "Skip staff currently on leave",
            value=cims.auto_config.get("exclude_on_leave", True),
            help="When auto-assigning, leave management records are checked. "
                 "Staff on active leave are excluded from the round-robin pool.")

        if st.button("💾 Save assignment mode", type="primary"):
            cims.auto_config["mode"]           = new_mode
            cims.auto_config["exclude_on_leave"]= excl_leave
            cims.save_auto_config()
            audit_log("CIMS_AUTO_CFG", uname, f"mode:{new_mode}|leave:{excl_leave}")
            st.success(f"✅ Assignment mode set to: {new_mode}")
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.subheader("Unit → staff mapping")
        st.caption(
            "Map each processing unit to its eligible staff pool. "
            "Auto-assignment and workload-aware allocation use this mapping. "
            "Staff can still reroute tickets to peers.")

        cur_map = cims.auto_config.get("unit_map", {})

        for unit in OWNER_UNITS:
            current_staff = cur_map.get(unit, [])
            current_codes = [s.get("code","") for s in current_staff]

            with st.expander(f"{unit} ({len(current_staff)} staff mapped)", expanded=False):
                # Show available staff
                if len(staff_scores):
                    unit_staff_avail = staff_scores[staff_scores["Unit"]==unit] if "Unit" in staff_scores.columns else pd.DataFrame()
                    if unit_staff_avail.empty:
                        # Try by category or all staff
                        unit_staff_avail = staff_scores

                    staff_opts = {}
                    for _,sr in unit_staff_avail.iterrows():
                        sc   = str(sr["Staff Code"])
                        nm   = sr["Staff Name"]
                        role = sr.get("Role","")
                        staff_opts[f"{nm} ({role})"] = {"code":sc,"name":nm,"role":role}

                    sel_staff = st.multiselect(
                        f"Staff pool for {unit}",
                        list(staff_opts.keys()),
                        default=[f"{s['name']} ({s['role']})" for s in current_staff
                                 if any(s["code"]==v["code"] for v in staff_opts.values())],
                        key=f"unit_map_{unit}")

                    if st.button(f"Save {unit} mapping", key=f"save_map_{unit}"):
                        new_pool = [staff_opts[k] for k in sel_staff if k in staff_opts]
                        cur_map[unit] = new_pool
                        cims.auto_config["unit_map"] = cur_map
                        cims.save_auto_config()
                        st.toast(f"✅ {unit}: {len(new_pool)} staff mapped", icon="✅")
                        st.cache_data.clear()
                        st.rerun()
                else:
                    st.info("Upload BSC data to see staff for mapping.")

                if current_staff:
                    st.markdown("**Currently mapped:**")
                    for s in current_staff:
                        st.markdown(
                            f"<div style='padding:3px 8px;background:#F0FDF4;"
                            f"border-radius:4px;font-size:11px;margin:1px 0'>"
                            f"✓ {s.get('name','')} ({s.get('role','')})</div>",
                            unsafe_allow_html=True)
