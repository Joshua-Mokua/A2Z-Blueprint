"""
api_lms_cr.py — Credit Report (CR) template: structure, auto-population, save.

The CR is the per-case credit appraisal memo the relationship owner completes.
It is a HYBRID:
  - some fields AUTO-POPULATE from the loan application + (best-effort) CBS
    customer data — name, CIF, sector, segment, relationship-since, deposit/
    loan balances, KYC/risk rating, etc.;
  - the rest are RM-filled judgement fields (financial analysis, risk,
    recommendation).

The field STRUCTURE is config-driven (lms_config.json -> cr_template) so the
bank can tune which fields are auto vs RM-filled and which are required, once
the CBS data is validated. CBS enrichment is best-effort: if the CIF lookup
returns nothing, the CR still works and those fields fall to the RM.
"""
from __future__ import annotations

import json as _json
from pathlib import Path as _Path
from typing import Any, Dict, List


# Default CR template — best-practice bank credit-report anatomy.
# Each field: {key, label, source, required}. source ∈ {auto, cbs, rm}.
#   auto = from the loan application; cbs = from CBS customer record (best-
#   effort); rm = relationship owner fills it.
_CR_TEMPLATE_DEFAULT: Dict[str, Any] = {
    "sections": [
        {
            "key": "memo_header",
            "title": "Memo Header",
            "fields": [
                {"key": "to", "label": "To", "source": "rm", "required": False},
                {"key": "from_branch", "label": "From (Branch)", "source": "cbs", "required": False},
                {"key": "memo_date", "label": "Date", "source": "auto", "required": False},
                {"key": "pp_ref", "label": "PP Ref", "source": "rm", "required": False},
            ],
        },
        {
            "key": "customer_profile",
            "title": "Customer Profile",
            "fields": [
                {"key": "client_name", "label": "Customer name", "source": "auto", "required": True},
                {"key": "client_cif", "label": "CIF", "source": "auto", "required": False},
                {"key": "customer_type", "label": "Customer type", "source": "cbs", "required": False},
                {"key": "segment", "label": "Segment", "source": "cbs", "required": False},
                {"key": "sector", "label": "Sector / industry", "source": "auto", "required": False},
                {"key": "relationship_since", "label": "Relationship since", "source": "cbs", "required": False},
                {"key": "branch_name", "label": "Branch", "source": "cbs", "required": False},
                {"key": "kyc_status", "label": "KYC status", "source": "cbs", "required": False},
                {"key": "risk_rating", "label": "Customer risk rating", "source": "cbs", "required": False},
                {"key": "employer_name", "label": "Employer name", "source": "cbs", "required": False},
                {"key": "employer_sector", "label": "Employer sector", "source": "cbs", "required": False},
                {"key": "orr", "label": "ORR (Obligor Risk Rating)", "source": "cbs", "required": False},
                {"key": "frr", "label": "FRR (Facility Risk Rating)", "source": "cbs", "required": False},
                {"key": "crb_pd", "label": "CRB PD (%)", "source": "cbs", "required": False},
                {"key": "crb_orr", "label": "CRB ORR", "source": "cbs", "required": False},
                {"key": "frr_crb", "label": "FRR based on CRB", "source": "cbs", "required": False},
            ],
        },
        {
            "key": "obligor_analysis",
            "title": "Obligor Analysis",
            "fields": [
                {"key": "background", "label": "Background / obligor analysis", "source": "rm", "required": False},
                {"key": "statements", "label": "Statements — significant credit & debit apart from salary", "source": "rm", "required": False},
                {"key": "crb_arrears", "label": "CRB — overdue days & amounts in arrears", "source": "rm", "required": False},
            ],
        },
        {
            "key": "facility_details",
            "title": "Facility Details",
            "fields": [
                {"key": "product", "label": "Product / facility", "source": "auto", "required": True},
                {"key": "amount", "label": "Amount requested (KES)", "source": "auto", "required": True},
                {"key": "purpose", "label": "Purpose of facility", "source": "rm", "required": True},
                {"key": "tenor_months", "label": "Tenor (months)", "source": "rm", "required": True},
                {"key": "repayment_source", "label": "Primary source of repayment", "source": "rm", "required": True},
                {"key": "pricing", "label": "Proposed pricing / rate", "source": "rm", "required": False},
            ],
        },
        {
            "key": "facilities",
            "title": "Facilities",
            "fields": [
                {"key": "facilities_table", "label": "Facilities", "source": "rm", "required": False, "type": "table"},
            ],
        },
        {
            "key": "financial_analysis",
            "title": "Financial Analysis",
            "fields": [
                {"key": "annual_turnover", "label": "Annual turnover (KES)", "source": "rm", "required": False},
                {"key": "net_profit", "label": "Net profit (KES)", "source": "rm", "required": False},
                {"key": "existing_deposits", "label": "Existing deposit balances (KES)", "source": "cbs", "required": False},
                {"key": "existing_loans", "label": "Existing loan balances (KES)", "source": "cbs", "required": False},
                {"key": "dscr", "label": "Debt service coverage ratio", "source": "rm", "required": False},
                {"key": "account_conduct", "label": "Account conduct / turnover in account", "source": "rm", "required": False},
                {"key": "dsr_computation", "label": "DSR computation", "source": "rm", "required": False},
                {"key": "policy_exception", "label": "Policy / PP exception", "source": "rm", "required": False},
                {"key": "other_bank_facilities", "label": "Existing facilities with other banks", "source": "rm", "required": False},
                {"key": "other_bank_securities", "label": "Securities pledged to other banks", "source": "rm", "required": False},
            ],
        },
        {
            "key": "security",
            "title": "Security / Collateral",
            "fields": [
                {"key": "security_type", "label": "Security offered", "source": "rm", "required": False},
                {"key": "security_value", "label": "Security value (KES)", "source": "rm", "required": False},
                {"key": "coverage_ratio", "label": "Security coverage (%)", "source": "rm", "required": False},
            ],
        },
        {
            "key": "risk_assessment",
            "title": "Risk Assessment",
            "fields": [
                {"key": "strengths", "label": "Strengths", "source": "rm", "required": False},
                {"key": "weaknesses", "label": "Weaknesses / risks", "source": "rm", "required": False},
                {"key": "mitigants", "label": "Risk mitigants", "source": "rm", "required": False},
                {"key": "aml_pep_flags", "label": "AML / PEP flags", "source": "cbs", "required": False},
                {"key": "risk_summary", "label": "Risk summary", "source": "rm", "required": False},
            ],
        },
        {
            "key": "recommendation",
            "title": "Relationship Owner Recommendation",
            "fields": [
                {"key": "rm_recommendation", "label": "Recommendation", "source": "rm", "required": True},
                {"key": "conditions", "label": "Proposed conditions / covenants", "source": "rm", "required": False},
            ],
        },
        {
            "key": "sign_off",
            "title": "Sign-off (wet signatures on the printed copy)",
            "fields": [
                {"key": "ro_name", "label": "Relationship Officer (name)", "source": "rm", "required": False},
                {"key": "bm_name", "label": "Branch Manager (name)", "source": "rm", "required": False},
            ],
        },
    ],
}


def get_cr_template() -> Dict[str, Any]:
    """Load the CR template structure (sections/fields) from lms_config.json
    -> cr_template, falling back to the best-practice default."""
    try:
        p = _Path(__file__).resolve().parent.parent / "data" / "lms_config.json"
        if p.exists():
            section = (_json.loads(p.read_text(encoding="utf-8")) or {}).get("cr_template")
            if isinstance(section, dict) and isinstance(section.get("sections"), list):
                return section
    except Exception:
        pass
    return _CR_TEMPLATE_DEFAULT


def _cbs_lookup(cif: str) -> Dict[str, Any]:
    """Best-effort CBS customer fetch. Never raises; returns {} on any miss."""
    cif = str(cif or "").strip()
    if not cif:
        return {}
    try:
        from utils.cbs_manager import get_customer_by_cif as _gcbc
        return _gcbc(cif) or {}
    except Exception:
        return {}


def autopopulate_cr(app: Dict[str, Any]) -> Dict[str, Any]:
    """Build the auto-populated value map for a CR from the application plus
    best-effort CBS data. Returns {field_key: value} for the auto/cbs fields
    that can be resolved; rm fields and unresolved fields are simply absent
    (the RM fills them). This is read-only — it does not persist anything."""
    vals: Dict[str, Any] = {}

    # ── from the application itself (auto) ──
    vals["client_name"] = app.get("client_name") or ""
    cif = str(app.get("client_cif") or "").strip()
    if cif:
        vals["client_cif"] = cif
    vals["sector"] = app.get("sector") or ""
    vals["product"] = app.get("product") or app.get("product_type") or ""
    amt = app.get("amount")
    if amt is None:
        amt = (app.get("metadata") or {}).get("amount_kes") if isinstance(app.get("metadata"), dict) else None
    if amt is not None:
        vals["amount"] = amt

    # ── from CBS (best-effort) ──
    cust = _cbs_lookup(cif)
    if cust:
        if not vals.get("client_name"):
            vals["client_name"] = cust.get("full_name") or ""
        vals["customer_type"] = cust.get("customer_type") or ""
        vals["segment"] = cust.get("segment") or ""
        if not vals.get("sector"):
            vals["sector"] = cust.get("sector") or ""
        vals["relationship_since"] = cust.get("date_onboarded") or ""
        vals["branch_name"] = cust.get("branch_name") or ""
        vals["kyc_status"] = cust.get("kyc_status") or ""
        vals["risk_rating"] = cust.get("risk_rating") or ""
        dep = cust.get("total_deposit_balance")
        if dep is not None:
            vals["existing_deposits"] = dep
        ln = cust.get("total_loan_balance")
        if ln is not None:
            vals["existing_loans"] = ln
        flags = []
        if cust.get("aml_flag"):
            flags.append("AML")
        if cust.get("pep_flag"):
            flags.append("PEP")
        if cust.get("fatf_flag"):
            flags.append("FATF")
        vals["aml_pep_flags"] = ", ".join(flags) if flags else "None"

    return vals


def build_cr_view(app: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble the CR for display: the template structure, the auto-populated
    values, any RM-saved values (app['cr']['values']), and a flag of whether
    CBS enrichment was available. Saved RM values take precedence over auto."""
    template = get_cr_template()
    auto = autopopulate_cr(app)
    saved = {}
    cr = app.get("cr") or {}
    if isinstance(cr, dict) and isinstance(cr.get("values"), dict):
        saved = cr["values"]
    merged = {**auto, **saved}
    cbs_available = bool(_cbs_lookup(str(app.get("client_cif") or "")))
    return {
        "template": template,
        "values": merged,
        "auto_values": auto,
        "saved_values": saved,
        "cbs_available": cbs_available,
        "completed": bool(cr.get("completed")) if isinstance(cr, dict) else False,
        "updated_by": cr.get("updated_by") if isinstance(cr, dict) else None,
        "updated_at": cr.get("updated_at") if isinstance(cr, dict) else None,
    }


def missing_required(app: Dict[str, Any], values: Dict[str, Any]) -> List[str]:
    """Return labels of required fields that are still empty (auto + provided)."""
    template = get_cr_template()
    auto = autopopulate_cr(app)
    merged = {**auto, **(values or {})}
    missing = []
    for sec in template.get("sections", []):
        for f in sec.get("fields", []):
            if f.get("required"):
                v = merged.get(f["key"])
                if v is None or (isinstance(v, str) and not v.strip()):
                    missing.append(f.get("label", f["key"]))
    return missing
