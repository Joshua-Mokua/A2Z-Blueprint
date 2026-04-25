"""utils/flexcube_adapter.py — FLEXCUBE Integration Adapter Layer.

This module is the SEAM between A2Z Blueprint and Oracle FLEXCUBE.

Three modes (configured in data/flexcube_config.json):
- "synthetic" : Reads from synthetic CSV/JSON files (current dev/demo state)
- "mock"      : Reads from synthetic data BUT pretends to call real APIs (for integration testing)
- "live"      : Calls real FLEXCUBE REST APIs via Ecobank's Apigee gateway (production)

Every function returns a normalised dict so the calling code (modules, BSC engine,
CBS Explorer) does not need to know which mode is active.

Reference: Oracle FLEXCUBE Universal Banking REST Services Guide
           Oracle Banking APIs (OBAPI/OBDX) Host Integration Guide
           Ecobank Group + Google Cloud (Apigee) Partnership 2025
"""
from __future__ import annotations
import json
import time
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from decimal import Decimal

DATA_DIR    = Path(__file__).parent.parent / "data"
CBS_DIR     = Path(__file__).parent.parent / "cbs_data"
CONFIG_FILE = DATA_DIR / "flexcube_config.json"

# ══════════════════════════════════════════════════════════════════
# Configuration loader
# ══════════════════════════════════════════════════════════════════

def get_config() -> Dict[str, Any]:
    """Load FLEXCUBE integration config. Falls back to safe defaults."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return _default_config()

def _default_config() -> Dict[str, Any]:
    return {
        "mode": "synthetic",
        "endpoints": {
            "apigee_base":     "https://api.ecobank.co.ke/v1",
            "fcubs_rest":      "https://api.ecobank.co.ke/flexcube",
            "obdx_rest":       "https://api.ecobank.co.ke/obdx/v1",
            "fcubs_soap_wsdl": "https://fcubs.ecobank.co.ke:8001/FCUBSAccService/FCUBSAccService?wsdl",
            "jms_broker":      "tcp://mq.ecobank.co.ke:61616",
        },
        "auth": {
            "method":            "oauth2",
            "client_id":         "${FLEXCUBE_CLIENT_ID}",
            "client_secret_ref": "${FLEXCUBE_CLIENT_SECRET}",
            "token_url":         "https://api.ecobank.co.ke/oauth2/token",
            "scopes":            ["accounts.read","loans.read","payments.read","customers.read"],
            "mtls_enabled":      True,
        },
        "jms_topics": {
            "loan_disbursed":     "ecobank.fcubs.loans.disbursed",
            "account_opened":     "ecobank.fcubs.accounts.opened",
            "account_closed":     "ecobank.fcubs.accounts.closed",
            "transaction_posted": "ecobank.fcubs.txns.posted",
            "aml_alert":          "ecobank.fcubs.aml.alert",
            "kyc_updated":        "ecobank.fcubs.kyc.updated",
        },
        "timeouts": {
            "rest_seconds":     5,
            "soap_seconds":    10,
            "batch_seconds":  300,
        },
        "rate_limits": {
            "rest_per_minute":   600,
            "burst_per_second":   20,
        },
        "fcubs_version":   "14.7",
        "deployment":      "on-prem-eti-ghana",
        "environments":    ["dev","sit","uat","prod"],
        "active_environment":"dev",
        "iso20022_enabled":True,
        "swift_enabled":   True,
        "iso8583_enabled": True,
        "data_residency":  "Kenya",
        "encryption":      {"in_transit":"TLS1.2+","at_rest":"TDE-AES256"},
        "last_updated":    "",
    }

def save_config(cfg: Dict[str, Any]) -> None:
    cfg["last_updated"] = datetime.utcnow().isoformat() + "Z"
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

# ══════════════════════════════════════════════════════════════════
# Mode dispatch
# ══════════════════════════════════════════════════════════════════

def get_mode() -> str:
    """Return current integration mode: synthetic | mock | live"""
    return get_config().get("mode", "synthetic")

def is_live() -> bool:
    return get_mode() == "live"

def _safe(v):
    if isinstance(v, Decimal): return float(v)
    return v

# ══════════════════════════════════════════════════════════════════
# FLEXCUBE REST API CALLS
# Each function tries live, falls back to synthetic if unavailable.
# ══════════════════════════════════════════════════════════════════

def fetch_account_balance(account_no: str, branch: str = "001") -> Dict[str, Any]:
    """
    Fetches account balance from FLEXCUBE.
    
    Live mode: GET /flexcube/AccountBalanceService/AccountBalance/QueryAcctBal/
               brhcode/{branch}/custAcNo/{account_no}
    
    Returns normalised dict:
    {"account_no", "branch", "available_balance", "ledger_balance",
     "currency", "as_of", "source"}
    """
    if get_mode() == "live":
        return _live_account_balance(account_no, branch)
    return _synthetic_account_balance(account_no, branch)

def _live_account_balance(account_no: str, branch: str) -> Dict[str, Any]:
    """Real FLEXCUBE REST call. Falls back to synthetic on failure."""
    try:
        import requests
        cfg = get_config()
        url = f"{cfg['endpoints']['fcubs_rest']}/AccountBalanceService/AccountBalance/QueryAcctBal/brhcode/{branch}/custAcNo/{account_no}"
        token = _get_oauth_token()
        resp = requests.get(url,
                           headers={"Authorization": f"Bearer {token}",
                                    "Content-Type": "application/json"},
                           timeout=cfg["timeouts"]["rest_seconds"])
        resp.raise_for_status()
        d = resp.json()
        return {
            "account_no":        d.get("AccountNo", account_no),
            "branch":            d.get("BranchCode", branch),
            "available_balance": _safe(d.get("AvailableBalance", 0)),
            "ledger_balance":    _safe(d.get("LedgerBalance", 0)),
            "currency":          d.get("currency", "KES"),
            "as_of":             d.get("as_of", datetime.utcnow().isoformat()+"Z"),
            "source":            "flexcube_live",
        }
    except Exception as e:
        result = _synthetic_account_balance(account_no, branch)
        result["source"]   = "synthetic_fallback"
        result["error"]    = str(e)[:100]
        return result

def _synthetic_account_balance(account_no: str, branch: str) -> Dict[str, Any]:
    """Read from synthetic CBS data."""
    try:
        import csv as _csv
        accts_csv = CBS_DIR / "accounts.csv"
        if accts_csv.exists():
            with accts_csv.open("r", encoding="utf-8") as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    if row.get("account_no","") == account_no:
                        return {
                            "account_no":        account_no,
                            "branch":            row.get("branch", branch),
                            "available_balance": _safe(row.get("available_balance", 0)),
                            "ledger_balance":    _safe(row.get("ledger_balance", row.get("balance",0))),
                            "currency":          row.get("currency","KES"),
                            "as_of":             datetime.utcnow().isoformat()+"Z",
                            "source":            "synthetic",
                        }
    except Exception:
        pass
    # If nothing else, return zero-balance stub
    return {"account_no":account_no,"branch":branch,"available_balance":0,
            "ledger_balance":0,"currency":"KES",
            "as_of":datetime.utcnow().isoformat()+"Z","source":"stub"}

def fetch_customer(cif: str) -> Dict[str, Any]:
    """
    Fetch customer profile by CIF.
    Live: GET /flexcube/CustomerService/QueryCustomer/customer_no/{cif}
    """
    if get_mode() == "live":
        return _live_customer(cif)
    return _synthetic_customer(cif)

def _live_customer(cif: str) -> Dict[str, Any]:
    try:
        import requests
        cfg = get_config()
        url = f"{cfg['endpoints']['fcubs_rest']}/CustomerService/QueryCustomer/customer_no/{cif}"
        token = _get_oauth_token()
        resp = requests.get(url,
                           headers={"Authorization": f"Bearer {token}"},
                           timeout=cfg["timeouts"]["rest_seconds"])
        resp.raise_for_status()
        d = resp.json()
        return {
            "cif":               cif,
            "name":              d.get("CustomerName",""),
            "type":              d.get("CustomerType","INDIVIDUAL"),
            "branch":            d.get("BranchCode",""),
            "rm_code":           d.get("RMCode",""),
            "kyc_status":        d.get("KYCStatus",""),
            "risk_rating":       d.get("RiskRating","Low"),
            "country":           d.get("Country","KEN"),
            "id_number":         d.get("IDNumber",""),
            "phone":             d.get("Phone",""),
            "email":             d.get("Email",""),
            "opened_date":       d.get("CustomerSince",""),
            "source":            "flexcube_live",
        }
    except Exception as e:
        result = _synthetic_customer(cif)
        result["source"] = "synthetic_fallback"
        result["error"]  = str(e)[:100]
        return result

def _synthetic_customer(cif: str) -> Dict[str, Any]:
    try:
        import csv as _csv
        cust_csv = CBS_DIR / "customers.csv"
        if cust_csv.exists():
            with cust_csv.open("r", encoding="utf-8") as f:
                reader = _csv.DictReader(f)
                for row in reader:
                    if row.get("cif","") == cif:
                        return {
                            "cif":         cif,
                            "name":        row.get("name",""),
                            "type":        row.get("type","INDIVIDUAL"),
                            "branch":      row.get("branch",""),
                            "rm_code":     row.get("rm_code",""),
                            "kyc_status":  row.get("kyc_status","Active"),
                            "risk_rating": row.get("risk_rating","Low"),
                            "country":     row.get("country","KEN"),
                            "id_number":   row.get("id_number",""),
                            "phone":       row.get("phone",""),
                            "email":       row.get("email",""),
                            "opened_date": row.get("opened_date",""),
                            "source":      "synthetic",
                        }
    except Exception:
        pass
    return {"cif":cif,"name":"","type":"","branch":"","rm_code":"","kyc_status":"","risk_rating":"",
            "country":"KEN","id_number":"","phone":"","email":"","opened_date":"","source":"stub"}

def fetch_loan_status(loan_id: str) -> Dict[str, Any]:
    """
    Fetch loan account status.
    Live: GET /flexcube/LoanAccountService/QueryLoan/account_no/{loan_id}
    """
    if get_mode() == "live":
        return _live_loan(loan_id)
    return _synthetic_loan(loan_id)

def _live_loan(loan_id: str) -> Dict[str, Any]:
    try:
        import requests
        cfg = get_config()
        url = f"{cfg['endpoints']['fcubs_rest']}/LoanAccountService/QueryLoan/account_no/{loan_id}"
        token = _get_oauth_token()
        resp = requests.get(url,
                           headers={"Authorization": f"Bearer {token}"},
                           timeout=cfg["timeouts"]["rest_seconds"])
        resp.raise_for_status()
        d = resp.json()
        return {
            "loan_id":      loan_id,
            "cif":          d.get("CustomerId",""),
            "principal":    _safe(d.get("PrincipalAmount",0)),
            "outstanding":  _safe(d.get("OutstandingAmount",0)),
            "rate":         _safe(d.get("InterestRate",0)),
            "tenor_months": _safe(d.get("TenorMonths",0)),
            "status":       d.get("Status",""),
            "dpd":          _safe(d.get("DPD",0)),
            "classification":d.get("Classification","Performing"),
            "next_emi_date":d.get("NextEMIDate",""),
            "source":       "flexcube_live",
        }
    except Exception as e:
        result = _synthetic_loan(loan_id)
        result["source"] = "synthetic_fallback"
        result["error"]  = str(e)[:100]
        return result

def _synthetic_loan(loan_id: str) -> Dict[str, Any]:
    try:
        loans = json.loads((DATA_DIR/"credit_monitoring.json").read_text(encoding="utf-8"))
        for l in loans if isinstance(loans, list) else []:
            if str(l.get("loan_id","")) == str(loan_id) or str(l.get("id","")) == str(loan_id):
                return {
                    "loan_id":     str(loan_id),
                    "cif":         l.get("cif",""),
                    "principal":   _safe(l.get("principal_kes", l.get("amount_kes",0))),
                    "outstanding": _safe(l.get("outstanding_kes",0)),
                    "rate":        _safe(l.get("interest_rate_pa",0)),
                    "tenor_months":_safe(l.get("tenor_months",0)),
                    "status":      l.get("status","Active"),
                    "dpd":         _safe(l.get("dpd",0)),
                    "classification":l.get("classification","Performing"),
                    "next_emi_date":l.get("next_emi_date",""),
                    "source":      "synthetic",
                }
    except Exception:
        pass
    return {"loan_id":loan_id,"cif":"","principal":0,"outstanding":0,"rate":0,"tenor_months":0,
            "status":"","dpd":0,"classification":"","next_emi_date":"","source":"stub"}

# ══════════════════════════════════════════════════════════════════
# AGGREGATE QUERIES — used by BSC engine
# These pull large datasets. Live calls go via batch/replica DB.
# ══════════════════════════════════════════════════════════════════

def fetch_rm_portfolio(rm_code: str) -> Dict[str, Any]:
    """
    Aggregate portfolio metrics for an RM.
    Live: GET /flexcube/PortfolioService/RMPortfolio/rm/{rm_code}
    Returns deposit/loan totals and counts.
    """
    if get_mode() == "live":
        try:
            import requests
            cfg = get_config()
            url = f"{cfg['endpoints']['fcubs_rest']}/PortfolioService/RMPortfolio/rm/{rm_code}"
            token = _get_oauth_token()
            resp = requests.get(url,
                               headers={"Authorization": f"Bearer {token}"},
                               timeout=cfg["timeouts"]["batch_seconds"])
            resp.raise_for_status()
            d = resp.json()
            return {
                "rm_code":      rm_code,
                "total_deposits_kes":  _safe(d.get("TotalDeposits",0)),
                "total_loans_kes":     _safe(d.get("TotalLoans",0)),
                "active_customers":    _safe(d.get("ActiveCustomers",0)),
                "active_accounts":     _safe(d.get("ActiveAccounts",0)),
                "npl_kes":             _safe(d.get("NPLBalance",0)),
                "npl_pct":             _safe(d.get("NPLRatio",0)),
                "fees_ytd_kes":        _safe(d.get("FeesYTD",0)),
                "as_of":               d.get("AsOf",""),
                "source":              "flexcube_live",
            }
        except Exception as e:
            return _synthetic_rm_portfolio(rm_code, error=str(e)[:100])
    return _synthetic_rm_portfolio(rm_code)

def _synthetic_rm_portfolio(rm_code: str, error: str="") -> Dict[str, Any]:
    """Read from existing actuals_*.xlsx aggregates if available."""
    result = {
        "rm_code":             rm_code,
        "total_deposits_kes":  0,
        "total_loans_kes":     0,
        "active_customers":    0,
        "active_accounts":     0,
        "npl_kes":             0,
        "npl_pct":             0,
        "fees_ytd_kes":        0,
        "as_of":               datetime.utcnow().isoformat()+"Z",
        "source":              "synthetic_fallback" if error else "synthetic",
    }
    if error: result["error"] = error
    try:
        import openpyxl
        for fname in ["actuals_2025_Dec_25.xlsx","actuals_2025_Sep.xlsx"]:
            xlsx = DATA_DIR / fname
            if xlsx.exists():
                wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
                for sheet_name in wb.sheetnames:
                    ws = wb[sheet_name]
                    headers = [c.value for c in ws[1]] if ws.max_row > 0 else []
                    rm_col = next((i for i,h in enumerate(headers) if h and "rm" in str(h).lower()),None)
                    if rm_col is None: continue
                    for row in ws.iter_rows(min_row=2, values_only=True):
                        if str(row[rm_col]) == str(rm_code):
                            for i,h in enumerate(headers):
                                if not h: continue
                                hl = str(h).lower()
                                v  = row[i]
                                if v is None: continue
                                if "deposit" in hl: result["total_deposits_kes"] += _safe(v)
                                elif "loan"  in hl: result["total_loans_kes"]    += _safe(v)
                                elif "fee"   in hl: result["fees_ytd_kes"]       += _safe(v)
                wb.close()
                if result["total_deposits_kes"] or result["total_loans_kes"]:
                    break
    except Exception:
        pass
    return result

def fetch_branch_metrics(branch_code: str) -> Dict[str, Any]:
    """Aggregate metrics by branch."""
    if get_mode() == "live":
        try:
            import requests
            cfg = get_config()
            url = f"{cfg['endpoints']['fcubs_rest']}/PortfolioService/Branch/{branch_code}"
            token = _get_oauth_token()
            resp = requests.get(url,
                               headers={"Authorization": f"Bearer {token}"},
                               timeout=cfg["timeouts"]["batch_seconds"])
            resp.raise_for_status()
            d = resp.json()
            return {**d, "source":"flexcube_live"}
        except Exception as e:
            return {"branch_code":branch_code,"source":"synthetic_fallback","error":str(e)[:100]}
    return {"branch_code":branch_code,"source":"synthetic"}

# ══════════════════════════════════════════════════════════════════
# OAUTH2 TOKEN HANDLING
# ══════════════════════════════════════════════════════════════════

_TOKEN_CACHE = {"token": None, "expires_at": 0}

def _get_oauth_token() -> str:
    """Get cached OAuth2 token from Apigee. Renews automatically."""
    now = time.time()
    if _TOKEN_CACHE["token"] and _TOKEN_CACHE["expires_at"] > now + 60:
        return _TOKEN_CACHE["token"]
    cfg = get_config()
    if cfg.get("mode") != "live":
        return "MOCK_TOKEN"
    try:
        import os
        import requests
        client_id     = os.environ.get("FLEXCUBE_CLIENT_ID","")
        client_secret = os.environ.get("FLEXCUBE_CLIENT_SECRET","")
        token_url     = cfg["auth"]["token_url"]
        scopes        = " ".join(cfg["auth"].get("scopes",[]))
        resp = requests.post(token_url,
                            data={"grant_type":"client_credentials",
                                  "client_id":client_id,
                                  "client_secret":client_secret,
                                  "scope":scopes},
                            timeout=10)
        resp.raise_for_status()
        d = resp.json()
        _TOKEN_CACHE["token"]      = d["access_token"]
        _TOKEN_CACHE["expires_at"] = now + int(d.get("expires_in",3600))
        return _TOKEN_CACHE["token"]
    except Exception:
        return ""

# ══════════════════════════════════════════════════════════════════
# JMS EVENT SUBSCRIPTIONS — for real-time BSC updates
# In synthetic/mock mode, this is a no-op.
# In live mode, this would be wired to a JMS consumer (separate process).
# ══════════════════════════════════════════════════════════════════

def publish_event(topic: str, payload: Dict[str, Any]) -> bool:
    """Publish a JMS event. Live: real broker. Synthetic: log only."""
    cfg = get_config()
    if cfg.get("mode") != "live":
        # Log to event journal for visibility
        log = DATA_DIR / "flexcube_events.json"
        events = []
        if log.exists():
            try: events = json.loads(log.read_text(encoding="utf-8"))
            except: events = []
        events.insert(0, {
            "timestamp": datetime.utcnow().isoformat()+"Z",
            "topic":     topic,
            "payload":   payload,
            "mode":      cfg.get("mode","synthetic"),
        })
        # Keep last 500
        log.write_text(json.dumps(events[:500], indent=2))
        return True
    # Live: would use stomp.py, pika, or oracle-jms-client here
    # Skipped intentionally — real implementation depends on broker chosen
    return False

# ══════════════════════════════════════════════════════════════════
# HEALTH CHECK
# ══════════════════════════════════════════════════════════════════

def health_check() -> Dict[str, Any]:
    """Probe FLEXCUBE endpoints. Returns service status dict."""
    cfg = get_config()
    mode = cfg.get("mode","synthetic")
    
    services = {
        "FLEXCUBE REST":    {"endpoint":cfg["endpoints"]["fcubs_rest"],     "status":"unknown","latency_ms":0},
        "OBDX REST":        {"endpoint":cfg["endpoints"]["obdx_rest"],      "status":"unknown","latency_ms":0},
        "Apigee Gateway":   {"endpoint":cfg["endpoints"]["apigee_base"],    "status":"unknown","latency_ms":0},
        "OAuth2 Token":     {"endpoint":cfg["auth"]["token_url"],           "status":"unknown","latency_ms":0},
        "JMS Broker":       {"endpoint":cfg["endpoints"]["jms_broker"],     "status":"unknown","latency_ms":0},
    }
    
    if mode == "synthetic":
        for k in services: services[k]["status"] = "Mocked (synthetic mode)"
        return {"mode":mode,"overall":"OK","services":services,"checked_at":datetime.utcnow().isoformat()+"Z"}
    
    if mode == "mock":
        for k in services: services[k]["status"] = "Mocked (integration test)"
        return {"mode":mode,"overall":"OK","services":services,"checked_at":datetime.utcnow().isoformat()+"Z"}
    
    # Live mode — probe each endpoint
    try:
        import requests
        for svc_name, svc in services.items():
            try:
                t0 = time.time()
                if "JMS" in svc_name:
                    svc["status"] = "Skipped (JMS probe needs separate consumer)"
                    continue
                resp = requests.get(svc["endpoint"], timeout=3)
                svc["latency_ms"] = int((time.time()-t0)*1000)
                svc["status"]     = "Up" if resp.status_code < 500 else f"Degraded ({resp.status_code})"
            except Exception as e:
                svc["status"] = f"Down: {str(e)[:50]}"
        ok = sum(1 for s in services.values() if "Up" in s.get("status",""))
        overall = "OK" if ok >= 3 else "DEGRADED" if ok >= 1 else "DOWN"
        return {"mode":mode,"overall":overall,"services":services,
                "checked_at":datetime.utcnow().isoformat()+"Z"}
    except ImportError:
        return {"mode":mode,"overall":"UNKNOWN",
                "services":services,
                "error":"requests library not installed",
                "checked_at":datetime.utcnow().isoformat()+"Z"}

# ══════════════════════════════════════════════════════════════════
# Helper for CBS Explorer / module pages
# ══════════════════════════════════════════════════════════════════

def get_status_badge() -> str:
    """Returns a one-line status indicator for use in page headers."""
    mode = get_mode()
    if mode == "live":      return "🟢 FLEXCUBE Live"
    if mode == "mock":      return "🟡 FLEXCUBE Mock"
    return "🔵 Synthetic Data"

__all__ = [
    "get_config","save_config","get_mode","is_live","get_status_badge",
    "fetch_account_balance","fetch_customer","fetch_loan_status",
    "fetch_rm_portfolio","fetch_branch_metrics",
    "publish_event","health_check",
]
