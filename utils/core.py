"""utils/core.py — Shared state: all managers, constants, helpers, data processing."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
import hashlib
import json
import re
import io
import smtplib
import secrets
import string
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart




import smtplib
import secrets
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
for f in ["users.json", "validations.json", "audit_log.json", "calendar_events.json",
          "staff_history.json", "email_config.json", "pending_tokens.json"]:
    p = DATA_DIR / f
    if not p.exists():
        p.write_text("{}")

# ─── PASSWORD UTILITIES ──────────────────────────────────────────────
def check_password_strength(pw):
    """Returns (ok: bool, issues: list[str])"""
    issues = []
    if len(pw) < 8:            issues.append("At least 8 characters")
    if not re.search(r'[A-Z]', pw): issues.append("At least one uppercase letter")
    if not re.search(r'[a-z]', pw): issues.append("At least one lowercase letter")
    if not re.search(r'\d', pw):    issues.append("At least one number")
    if not re.search(r'[^A-Za-z0-9]', pw): issues.append("At least one special character (!@#$%^&*)")
    return (len(issues) == 0, issues)

def generate_temp_password(length=12):
    alpha  = string.ascii_letters
    digits = string.digits
    spec   = "!@#$%^&*"
    chars  = alpha + digits + spec
    while True:
        pw = ''.join(secrets.choice(chars) for _ in range(length))
        ok, _ = check_password_strength(pw)
        if ok: return pw

def generate_token():
    return secrets.token_urlsafe(32)

# ─── EMAIL SENDER ────────────────────────────────────────────────────
def load_email_config():
    try:
        raw = (DATA_DIR/"email_config.json").read_text()
        return json.loads(raw) if raw.strip() else {}
    except: return {}

def save_email_config(cfg):
    (DATA_DIR/"email_config.json").write_text(json.dumps(cfg, indent=2))

def send_milestone_alert_email(to_email, recipient_name, ms_name, init_name,
                               due_date, days_info, esc_level, workstream, io_name):
    """Send milestone escalation/due-soon email."""
    cfg = load_email_config()
    if not cfg.get("smtp_host") or not cfg.get("sender_email"):
        return False, "Email not configured"
    esc_cfg = ESC_CONFIG.get(esc_level, ESC_CONFIG[1])
    subject = f"A2Z Execute — {esc_cfg['icon']} Milestone alert: {ms_name}"
    body = f"""
<html><body style="font-family:Arial,sans-serif;max-width:520px;margin:auto">
<div style="background:#1B4F72;padding:20px;border-radius:8px 8px 0 0">
  <h2 style="color:white;margin:0">A2Z Execute</h2>
  <p style="color:#AED6F1;margin:4px 0 0">Milestone Alert</p>
</div>
<div style="padding:20px;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px">
  <div style="padding:10px 14px;background:{esc_cfg['bg']};border-left:4px solid {esc_cfg['color']};
              border-radius:0 6px 6px 0;margin-bottom:16px">
    <b style="color:{esc_cfg['color']}">{esc_cfg['icon']} {esc_cfg['label']}</b>
  </div>
  <p>Hi <b>{recipient_name}</b>,</p>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin:12px 0">
    <tr style="background:#F8F9FA"><td style="padding:6px 10px;color:#555">Milestone</td>
        <td style="padding:6px 10px"><b>{ms_name}</b></td></tr>
    <tr><td style="padding:6px 10px;color:#555">Initiative</td>
        <td style="padding:6px 10px">{init_name}</td></tr>
    <tr style="background:#F8F9FA"><td style="padding:6px 10px;color:#555">Workstream</td>
        <td style="padding:6px 10px">{workstream}</td></tr>
    <tr><td style="padding:6px 10px;color:#555">Due date</td>
        <td style="padding:6px 10px"><b>{due_date}</b> — {days_info}</td></tr>
    <tr style="background:#F8F9FA"><td style="padding:6px 10px;color:#555">IO</td>
        <td style="padding:6px 10px">{io_name}</td></tr>
  </table>
  <p style="font-size:13px;color:#555">Please update the milestone status on A2Z Execute immediately.</p>
  <p style="font-size:11px;color:#bbb;margin-top:24px">A2Z Perform · Automated alert</p>
</div></body></html>"""
    try:
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        import smtplib
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = cfg["sender_email"]
        msg["To"]      = to_email
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP(cfg["smtp_host"], int(cfg.get("smtp_port",587))) as s:
            s.starttls()
            s.login(cfg["sender_email"], cfg["sender_password"])
            s.sendmail(cfg["sender_email"], to_email, msg.as_string())
        return True, "Sent"
    except Exception as e:
        return False, str(e)

def send_structural_delay_email(to_emails, ms_name, init_name, workstream,
                                 delay_category, delay_reason, owner, io_name):
    """Immediate all-parties alert for structural/regulatory delay."""
    cfg = load_email_config()
    if not cfg.get("smtp_host"): return False, "Email not configured"
    subject = f"🚨 A2Z Execute — IMMEDIATE: Structural delay on {ms_name}"
    body = f"""
<html><body style="font-family:Arial,sans-serif;max-width:520px;margin:auto">
<div style="background:#A32D2D;padding:20px;border-radius:8px 8px 0 0">
  <h2 style="color:white;margin:0">A2Z Execute — Immediate escalation</h2>
  <p style="color:#F7C1C1;margin:4px 0 0">Structural / Regulatory Delay — All parties notified</p>
</div>
<div style="padding:20px;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px">
  <div style="padding:10px 14px;background:#FCEBEB;border-left:4px solid #A32D2D;border-radius:0 6px 6px 0;margin-bottom:16px">
    <b style="color:#A32D2D">Category: {delay_category}</b><br>
    <span style="font-size:13px;color:#791F1F">{delay_reason}</span>
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin:12px 0">
    <tr style="background:#F8F9FA"><td style="padding:6px 10px;color:#555">Milestone</td><td style="padding:6px 10px"><b>{ms_name}</b></td></tr>
    <tr><td style="padding:6px 10px;color:#555">Initiative</td><td style="padding:6px 10px">{init_name}</td></tr>
    <tr style="background:#F8F9FA"><td style="padding:6px 10px;color:#555">Workstream</td><td style="padding:6px 10px">{workstream}</td></tr>
    <tr><td style="padding:6px 10px;color:#555">Milestone owner</td><td style="padding:6px 10px">{owner}</td></tr>
    <tr style="background:#F8F9FA"><td style="padding:6px 10px;color:#555">Initiative owner</td><td style="padding:6px 10px">{io_name}</td></tr>
  </table>
  <p style="color:#A32D2D;font-weight:bold;font-size:13px">This delay requires immediate management intervention. Please review and take action on A2Z Execute.</p>
  <p style="font-size:11px;color:#bbb;margin-top:24px">A2Z Perform · Automated alert</p>
</div></body></html>"""
    try:
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        import smtplib
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = cfg["sender_email"]
        msg["To"]      = ", ".join(to_emails)
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP(cfg["smtp_host"], int(cfg.get("smtp_port",587))) as s:
            s.starttls()
            s.login(cfg["sender_email"], cfg["sender_password"])
            s.sendmail(cfg["sender_email"], to_emails, msg.as_string())
        return True, "Sent"
    except Exception as e:
        return False, str(e)


def send_start_alert_email(to_email, recipient_name, ms_name, init_name, start_date, workstream):
    """Email to milestone owner when start date arrives."""
    cfg = load_email_config()
    if not cfg.get("smtp_host"): return False, "Email not configured"
    subject = f"A2Z Execute — ⏰ Milestone starting today: {ms_name}"
    body = f"""
<html><body style="font-family:Arial,sans-serif;max-width:520px;margin:auto">
<div style="background:#185FA5;padding:20px;border-radius:8px 8px 0 0">
  <h2 style="color:white;margin:0">A2Z Execute</h2>
  <p style="color:#B5D4F4;margin:4px 0 0">Milestone starting today</p>
</div>
<div style="padding:20px;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px">
  <p>Hi <b>{recipient_name}</b>,</p>
  <p>Your milestone is scheduled to <b>start today</b>.</p>
  <table style="width:100%;border-collapse:collapse;font-size:13px;margin:12px 0">
    <tr style="background:#F8F9FA"><td style="padding:6px 10px;color:#555">Milestone</td><td style="padding:6px 10px"><b>{ms_name}</b></td></tr>
    <tr><td style="padding:6px 10px;color:#555">Initiative</td><td style="padding:6px 10px">{init_name}</td></tr>
    <tr style="background:#F8F9FA"><td style="padding:6px 10px;color:#555">Workstream</td><td style="padding:6px 10px">{workstream}</td></tr>
    <tr><td style="padding:6px 10px;color:#555">Start date</td><td style="padding:6px 10px"><b>{start_date}</b></td></tr>
  </table>
  <p style="font-size:13px;color:#555">Please mark the milestone as <b>In Progress</b> on A2Z Execute to confirm it has started.</p>
  <p style="font-size:11px;color:#bbb;margin-top:24px">A2Z Perform · Automated alert</p>
</div></body></html>"""
    try:
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        import smtplib
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = cfg["sender_email"]
        msg["To"]      = to_email
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP(cfg["smtp_host"], int(cfg.get("smtp_port",587))) as s:
            s.starttls()
            s.login(cfg["sender_email"], cfg["sender_password"])
            s.sendmail(cfg["sender_email"], to_email, msg.as_string())
        return True, "Sent"
    except Exception as e:
        return False, str(e)


def run_escalation_scan(em, user_registry):
    """
    Called once per session on app load.
    Scans all active milestones and sends alerts where needed.
    user_registry: dict of {username: {email, full_name, role}}
    Returns list of alert log entries.
    """
    alerts = []
    today  = date.today()

    def get_email(username):
        u = user_registry.get(username, {})
        return u.get('email',''), u.get('full_name', username)

    for init in em.get_initiatives(status='All'):
        if init.get('gate') not in ('G3','G4'): continue
        for ms in init.get('milestones', []):
            if ms['status'] == 'Complete': continue
            esc = ExecuteManager._escalation_level(ms)
            if esc == 0: continue

            owner_email, owner_name = get_email(ms['owner'])
            io_email,    io_name    = get_email(init.get('io',''))
            workstream   = init.get('workstream','')

            try:
                due       = date.fromisoformat(ms['due_date'])
                days_over = (today - due).days
                days_to   = (due - today).days
            except:
                days_over, days_to = 0, 0

            # ── Due in exactly 2 days — due-soon email to owner ────
            if days_to == 2:
                if owner_email:
                    send_milestone_alert_email(
                        owner_email, owner_name, ms['name'], init['name'],
                        ms['due_date'], f"due in 2 days", 1, workstream, io_name)
                    alerts.append({'type':'due_soon','ms':ms['name'],'to':owner_email})

            # ── Start date = today — start alert ──────────────────
            if (ms.get('start_date') == str(today) and
                ms['status'] == 'Not Started' and not ms.get('has_started')):
                if owner_email:
                    send_start_alert_email(
                        owner_email, owner_name, ms['name'], init['name'],
                        ms['start_date'], workstream)
                    alerts.append({'type':'start_today','ms':ms['name'],'to':owner_email})

            # ── Structural/regulatory delay → all parties immediately ─
            if (ms.get('delay_category','') in STRUCTURAL_CATEGORIES and
                ms['status'] == 'Delayed'):
                all_emails = [e for e in [owner_email, io_email] if e]
                # Try to find lead/sponsor from workstream
                if all_emails:
                    send_structural_delay_email(
                        all_emails, ms['name'], init['name'], workstream,
                        ms['delay_category'], ms.get('delay_reason',''),
                        ms['owner'], io_name)
                    alerts.append({'type':'structural','ms':ms['name'],'level':4})

            # ── Day 2 overdue → IO email ───────────────────────────
            elif days_over >= 2 and esc >= 2 and io_email:
                send_milestone_alert_email(
                    io_email, io_name, ms['name'], init['name'],
                    ms['due_date'], f"{days_over}d overdue", esc, workstream, io_name)
                alerts.append({'type':'overdue_io','ms':ms['name'],'days':days_over})

    return alerts


def should_run_scan():
    """Run escalation scan once per day per session."""
    last = st.session_state.get('last_esc_scan')
    today_str = str(date.today())
    if last != today_str:
        st.session_state['last_esc_scan'] = today_str
        return True
    return False


def send_welcome_email(to_email, full_name, username, temp_password):
    cfg = load_email_config()
    if not cfg.get("smtp_host") or not cfg.get("sender_email"):
        return False, "Email not configured. Go to Admin → Email Settings."
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "A2Z Perform — Your account has been created"
        msg["From"]    = cfg["sender_email"]
        msg["To"]      = to_email
        body = f"""
<html><body style="font-family:Arial,sans-serif;max-width:500px;margin:auto">
<div style="background:#1B4F72;padding:20px;border-radius:8px 8px 0 0">
  <h2 style="color:white;margin:0">🏦 A2Z Perform</h2>
  <p style="color:#AED6F1;margin:4px 0 0">Performance Management System</p>
</div>
<div style="padding:24px;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px">
  <p>Hi <strong>{full_name}</strong>,</p>
  <p>Your account has been created on <strong>A2Z Perform</strong>.</p>
  <table style="background:#F8F9FA;padding:16px;border-radius:6px;width:100%;border-collapse:collapse">
    <tr><td style="padding:4px 8px;color:#555">Username</td><td style="padding:4px 8px"><strong>{username}</strong></td></tr>
    <tr><td style="padding:4px 8px;color:#555">Temp password</td><td style="padding:4px 8px"><strong style="font-size:18px;letter-spacing:2px">{temp_password}</strong></td></tr>
  </table>
  <p style="color:#E74C3C;font-weight:bold">⚠️ You will be prompted to set a new password on first login.</p>
  <p style="font-size:12px;color:#999">Your new password must be at least 8 characters and include uppercase, lowercase, a number, and a special character.</p>
  <p style="font-size:12px;color:#bbb;margin-top:32px">This is an automated message from A2Z Perform. Do not reply.</p>
</div>
</body></html>"""
        msg.attach(MIMEText(body, "html"))
        with smtplib.SMTP(cfg["smtp_host"], int(cfg.get("smtp_port", 587))) as s:
            s.starttls()
            s.login(cfg["sender_email"], cfg["sender_password"])
            s.sendmail(cfg["sender_email"], to_email, msg.as_string())
        return True, "Email sent"
    except Exception as e:
        return False, str(e)

# ─── HELPER FUNCTIONS ────────────────────────────────────────────────
def get_performance_remarks(score):
    if pd.isna(score):   return "No Data"
    elif score < 2.5:    return "Unmet"
    elif score < 3.0:    return "Partially Met"
    elif score < 3.1:    return "Met"
    elif score < 4.0:    return "Exceeded"
    else:                return "Exceeded By Far"

def highlight_performance(val):
    colors = {
        "Exceeded By Far": "background-color:#90EE90;color:#000",
        "Exceeded":        "background-color:#C1E1C1;color:#000",
        "Met":             "background-color:#FFE4B5;color:#000",
        "Partially Met":   "background-color:#FFD700;color:#000",
        "Unmet":           "background-color:#FFB6C1;color:#000",
        "No Data":         "background-color:#D3D3D3;color:#000",
    }
    return colors.get(val, "")

def fmt_num(v, short=False):
    """Accounting format: comma separator, 2 decimal places."""
    try:
        if pd.isna(v): return "—"
        f = float(v)
        if short:
            if abs(f) >= 1_000_000_000: return f"{f/1e9:,.2f}B"
            if abs(f) >= 1_000_000:     return f"{f/1e6:,.2f}M"
            if abs(f) >= 1_000:         return f"{f/1e3:,.2f}K"
        return f"{f:,.2f}"
    except: return str(v)

def fmt_pct(v):
    try:
        if pd.isna(v): return "—"
        return f"{float(v):.1f}%"
    except: return str(v)

def fmt_score(v):
    try:
        if pd.isna(v): return "—"
        return f"{float(v):.2f}"
    except: return str(v)

def clean_code(v):
    """Normalize staff code — strip spaces and Excel apostrophe on both sides."""
    return str(v).strip().strip("'").strip()


# ═══════════════════════════════════════════════════════════════════════
# PRODUCT LIFECYCLE MODULE — Banking product registry
# Assets · Liabilities · NFI · Channels
# ═══════════════════════════════════════════════════════════════════════

PRODUCT_CATEGORIES = {
    "Assets": {
        "color": "#185FA5", "bg": "#E6F1FB", "icon": "📈",
        "description": "Lending products — income generating",
        "kpi_links": ["Loans Disbursement","Loan Book Growth","Trade Finance","NPL","PAR"],
        "lifecycle": ["Concept","Pilot","Active","Growth","Mature","Sunset"],
        "sub_categories": {
            "Retail Lending":    ["Personal Loan","Salary Advance","Mortgage / Home Loan",
                                   "Auto Finance","Education Loan","Emergency Loan"],
            "Business Lending":  ["Business Loan","Overdraft (OD)","Invoice Discounting",
                                   "Asset Finance","Contract Finance","Working Capital Loan"],
            "Corporate & SME":   ["Term Loan","Revolving Credit Facility","Trade Finance",
                                   "Supply Chain Finance","Syndicated Loan"],
            "Specialised":       ["Agricultural Loan","Green Finance","Government / County Loan"],
        },
    },
    "Liabilities": {
        "color": "#0F6E56", "bg": "#E1F5EE", "icon": "🏦",
        "description": "Deposit-taking products — balance sheet funding",
        "kpi_links": ["Deposit Growth"],
        "lifecycle": ["Concept","Pilot","Active","Growth","Mature","Sunset"],
        "sub_categories": {
            "Retail Deposits":   ["Current Account","Savings Account","Fixed Deposit",
                                   "Junior Account","Senior Account"],
            "Business Deposits": ["Business Current Account","Business Savings",
                                   "Business Fixed Deposit","Salary Processing Account"],
            "Corporate":         ["Call Account","Treasury Placement","Structured Deposit"],
            "Digital Deposits":  ["Mobile Wallet","Digital Savings (App)","Virtual Account"],
        },
    },
    "NFI": {
        "color": "#534AB7", "bg": "#EEEDFE", "icon": "💰",
        "description": "Non-funded income — fees, commissions, insurance",
        "kpi_links": ["Fees and Commission","DFS Revenue","Bancassurance","Treasury","Acquiring"],
        "lifecycle": ["Concept","Pilot","Active","Growth","Mature","Sunset"],
        "sub_categories": {
            "Bancassurance":  ["Life Cover","Credit Life","Motor Insurance",
                               "Home Insurance","Business Insurance"],
            "DFS":            ["Mobile Banking","Internet Banking","USSD Banking",
                               "Agency Banking","Merchant Acquiring"],
            "Transactional":  ["Forex / FX","Wire Transfers","Trade LC","Bank Guarantees"],
            "Treasury":       ["T-Bills","Bonds","FX Trading","Structured Products"],
            "Cards":          ["Debit Card","Credit Card","Prepaid Card"],
        },
    },
    "Channels": {
        "color": "#BA7517", "bg": "#FAEEDA", "icon": "📡",
        "description": "Delivery mechanisms — how products reach customers",
        "kpi_links": ["Digital Transaction Migration","Transactions","Customer Growth"],
        "lifecycle": ["Planning","Development","Launch","Active","Optimising","Decommissioned"],
        "sub_categories": {
            "Physical":    ["Branch Network","ATM Network","Agent Banking","Kiosks"],
            "Digital":     ["Mobile App","Internet Banking Portal","USSD (*XXX#)","WhatsApp Banking"],
            "Partnership": ["Bancassurance Partners","Telco Partnerships",
                            "Fintech Integrations","Government Portals"],
        },
    },
}

PRODUCT_LIFECYCLE_STAGES = {
    "Concept":         {"color":"#888780","bg":"#F1EFE8","desc":"Idea stage — being evaluated"},
    "Pilot":           {"color":"#185FA5","bg":"#E6F1FB","desc":"Limited rollout — testing"},
    "Active":          {"color":"#1D9E75","bg":"#E1F5EE","desc":"Live and available to customers"},
    "Growth":          {"color":"#3B6D11","bg":"#EAF3DE","desc":"Scaling — high acquisition focus"},
    "Mature":          {"color":"#BA7517","bg":"#FAEEDA","desc":"Stable — optimise & retain"},
    "Sunset":          {"color":"#A32D2D","bg":"#FCEBEB","desc":"Being phased out"},
    "Planning":        {"color":"#534AB7","bg":"#EEEDFE","desc":"Under development"},
    "Development":     {"color":"#185FA5","bg":"#E6F1FB","desc":"Being built"},
    "Launch":          {"color":"#0F6E56","bg":"#E1F5EE","desc":"Recently launched"},
    "Optimising":      {"color":"#3B6D11","bg":"#EAF3DE","desc":"Active improvement cycle"},
    "Decommissioned":  {"color":"#5F5E5A","bg":"#F1EFE8","desc":"Retired"},
}

PRODUCT_HEALTH_SIGNALS = ["On track","Needs review","At risk","Suspended"]
PRODUCT_OWNERS         = []  # populated from staff registry at runtime



# ─── FILE UPLOAD CACHE HELPER ─────────────────────────────────────────
def cache_upload(uploaded_file, session_key: str) -> bytes | None:
    """
    Safely extract bytes from a Streamlit UploadedFile and persist them
    in session state so they survive reruns.
    Returns the cached bytes, or None if nothing has been uploaded yet.
    """
    if uploaded_file is not None:
        try:
            raw = uploaded_file.getvalue()
        except Exception:
            try:
                raw = uploaded_file.read()
            except Exception:
                raw = None
        if raw:
            st.session_state[session_key] = raw
            return raw
    return st.session_state.get(session_key)

# ─── ECOBANK BRAND THEME ────────────────────────────────────────────
BRAND = {
    'primary':      '#006B3F',   # Ecobank deep green
    'secondary':    '#F5A623',   # Ecobank gold
    'primary_light':'#E8F5EE',   # light green surface
    'secondary_light':'#FEF6E4', # light gold surface
    'dark':         '#004A2B',   # deep dark green
    'text_on_primary': '#FFFFFF',
    'text_on_secondary': '#3D2600',
    'app_name':     'A2Z Blueprint',
    'tagline':      'Perform · Execute · Integrate',
}

# ─── REGION MAPPING ───────────────────────────────────────────────────
BRANCH_REGION: dict = {
    'Mombasa Branch':        'South',
    'Nyali Branch':          'South',
    'Malindi Branch':        'South',
    'Machakos Branch':       'South',
    'Gikomba Branch':        'South',
    'Industrial Area Branch':'South',
    'Retail Banking':        'Central',
    'Nairobi CBD Branch':    'Central',
    'Thika Branch':          'Central',
    'Nyeri Branch':          'Central',
    'Meru Branch':           'Central',
    'Eldoret Branch':        'North',
    'Kisumu Branch':         'North',
    'Nakuru Branch':         'North',
    'Kericho Branch':        'North',
    'Kisii Branch':          'North',
    'Nyamira Branch':        'North',
    'Kabsabet Branch':       'North',
    'Kitale Branch':         'North',
    'Bungoma Branch':        'North',
    'Busia Branch':          'North',
}
REGIONS: list = ['South', 'Central', 'North']
REGIONAL_HEAD_ROLE = 'Regional Head'

def get_unit_region(unit: str) -> str:
    return BRANCH_REGION.get(unit, 'Head Office')

# ─── BANKING METRICS HELPERS ─────────────────────────────────────────
def calc_nim(nii, avg_earning_assets):
    """Net Interest Margin = NII / Avg Earning Assets × 100"""
    return round(nii / avg_earning_assets * 100, 2) if avg_earning_assets else 0.0

def calc_roa(pbt, avg_total_assets):
    """Return on Assets = PBT / Avg Total Assets × 100"""
    return round(pbt / avg_total_assets * 100, 2) if avg_total_assets else 0.0

def calc_roe(pbt, avg_equity):
    """Return on Equity = PBT / Avg Equity × 100"""
    return round(pbt / avg_equity * 100, 2) if avg_equity else 0.0

def calc_cir(opex, operating_income):
    """Cost-to-Income Ratio = Opex / Operating Income × 100"""
    return round(abs(opex) / operating_income * 100, 1) if operating_income else 0.0

def calc_jaws(rev_growth_pct, cost_growth_pct):
    """Jaws ratio = Revenue growth % - Cost growth %. Positive = expanding margins."""
    return round(rev_growth_pct - cost_growth_pct, 1)

def calc_rev_per_staff(operating_income, staff_count):
    """Revenue per head — productivity metric"""
    return round(operating_income / staff_count, 0) if staff_count else 0.0

def calc_npl_coverage(provisions, npl_balance):
    """Provision coverage ratio = Cumulative provisions / NPL balance × 100"""
    return round(provisions / npl_balance * 100, 1) if npl_balance else 0.0

def calc_pipeline_win_rate(won_deals, total_closed):
    """Win rate = Won deals / (Won + Lost) × 100"""
    return round(won_deals / total_closed * 100, 1) if total_closed else 0.0

def calc_avg_deal_size(total_pipeline_value, deal_count):
    """Average deal size"""
    return round(total_pipeline_value / deal_count, 0) if deal_count else 0.0

# ─── ROLE FUNCTION CLASSIFIER ───────────────────────────────────────
# Business roles = revenue-generating / client-facing
# Support roles  = enablement / infrastructure
BUSINESS_ROLES: frozenset = frozenset([
    'Relationship Manager SME','Relationship Manager Corporate',
    'Relationship Officer Business Banking','Relationship Officer Personal Banking',
    'Direct Sales Officer','Head Of SME','Head Of Corporate','Head Of Retail',
    'Director Commercial Banking','Director Retail',
    'Head Of Digital Innovation','Digital Innovation Manager','Digital Innovation Officer',
    'Head Of Products','Products Manager','Products Officer',
    'Marketing Manager','Marketing Officer','Head Of Marketing',
])
BRANCH_MANAGEMENT: frozenset = frozenset([
    'Branch Manager','Branch Operations Manager','Branch Operations Supervisor',
    'Credit Manager','Customer Service Officer',
])

def get_role_function(role, category):
    """
    Returns 'Business', 'Support', or 'Branch Management'.
    Branch staff are all treated as Business (sales-focused).
    """
    if str(category).strip() == 'Branch':
        if role in BRANCH_MANAGEMENT:  return 'Branch Management'
        return 'Business'
    if role in BUSINESS_ROLES:         return 'Business'
    return 'Support'

# ─── PIPELINE CONSTANTS (Banking CRM) ────────────────────────────────
PIPELINE_STAGES = [
    {"stage": "Lead",           "icon": "🎯", "description": "Identified prospect, no contact yet"},
    {"stage": "Contacted",      "icon": "📞", "description": "Initial call / meeting booked"},
    {"stage": "Qualified",      "icon": "✅", "description": "Needs confirmed, fits product criteria"},
    {"stage": "Proposal",       "icon": "📄", "description": "Term sheet / offer presented"},
    {"stage": "Negotiation",    "icon": "🤝", "description": "Terms being discussed / docs in progress"},
    {"stage": "Compliance",     "icon": "🔏", "description": "KYC / AML / credit checks underway"},
    {"stage": "Closed Won",     "icon": "🏆", "description": "Deal signed, account opened / facility drawn"},
    {"stage": "Closed Lost",    "icon": "❌", "description": "Prospect chose competitor or declined"},
]
STAGE_NAMES    = [s["stage"] for s in PIPELINE_STAGES]
ACTIVE_STAGES  = [s["stage"] for s in PIPELINE_STAGES if s["stage"] not in ("Closed Won","Closed Lost")]

# ─── REVENUE INTELLIGENCE — KPI CATEGORY MAPPING ────────────────────
RI_CATEGORIES = {
    'Deposits': {
        'kpis':      ['Deposit Growth'],
        'color':     '#0F6E56',   # teal-600
        'bg':        '#E1F5EE',   # teal-50
        'label':     'Liabilities',
        'unit':      'KES',
        'pipeline_product_types': ['Fixed Deposit','Savings Account','Current Account',
                                    'Salary Processing','SACCO Placement','Corporate Deposit','Other Deposit'],
        'stages':    ['Prospect','Engaged','Proposal','Negotiation','Approval','Funds In'],
        'closed_won':'Funds In',
        'closed_lost':'Lost',
        'stage_weights': {'Prospect':0.05,'Engaged':0.15,'Proposal':0.35,
                          'Negotiation':0.60,'Approval':0.85,'Funds In':1.0,'Lost':0.0},
    },
    'Loans': {
        'kpis':      ['Loans Disbursement','Loan Book Growth','Trade Finance'],
        'color':     '#185FA5',   # blue-600
        'bg':        '#E6F1FB',   # blue-50
        'label':     'Assets',
        'unit':      'KES',
        'pipeline_product_types': ['Business Loan','Personal Loan','Mortgage','Overdraft',
                                    'Asset Finance','Invoice Discounting','Trade Finance','Other Loan'],
        'stages':    ['Prospect','Application','Credit Appraisal','Approval','Documentation','Disbursed'],
        'closed_won':'Disbursed',
        'closed_lost':'Declined',
        'stage_weights': {'Prospect':0.05,'Application':0.20,'Credit Appraisal':0.45,
                          'Approval':0.75,'Documentation':0.90,'Disbursed':1.0,'Declined':0.0},
    },
    'NFI': {
        'kpis':      ['Fees and Commission','Bancassurance','DFS Revenue','Treasury'],
        'color':     '#534AB7',   # purple-600
        'bg':        '#EEEDFE',   # purple-50
        'label':     'Non-Funded Income',
        'unit':      'KES',
        'pipeline_product_types': ['Bancassurance Policy','DFS Onboarding','Treasury Deal',
                                    'Trade Finance Fee','Forex','Account Fee','Other NFI'],
        'stages':    ['Prospect','Pitched','Proposal','Committed','Converted'],
        'closed_won':'Converted',
        'closed_lost':'Lost',
        'stage_weights': {'Prospect':0.10,'Pitched':0.25,'Proposal':0.50,
                          'Committed':0.80,'Converted':1.0,'Lost':0.0},
    },
    'Customers': {
        'kpis':      ['Customer Growth'],
        'color':     '#BA7517',   # amber-600
        'bg':        '#FAEEDA',   # amber-50
        'label':     'New Customers',
        'unit':      'No.',
        'pipeline_product_types': ['Individual','SME','Corporate','Institutional','Other'],
        'stages':    ['Lead','Contacted','KYC Submitted','Account Opened'],
        'closed_won':'Account Opened',
        'closed_lost':'Lost',
        'stage_weights': {'Lead':0.10,'Contacted':0.30,'KYC Submitted':0.75,
                          'Account Opened':1.0,'Lost':0.0},
    },
}

RI_KPI_TO_CATEGORY = {}
for cat, cfg in RI_CATEGORIES.items():
    for kpi in cfg['kpis']:
        RI_KPI_TO_CATEGORY[kpi] = cat

# Months remaining in year (for forecast)
def months_remaining():
    return max(1, 12 - datetime.now().month)

def months_elapsed():
    return max(1, datetime.now().month)


# ═══════════════════════════════════════════════════════════════════════
# EXECUTE MODULE — STRATEGY EXECUTION TRACKING
# ═══════════════════════════════════════════════════════════════════════

EXECUTE_GATES = {
    'G0': {'label': 'Idea',           'color': '#888780', 'bg': '#F1EFE8',
           'desc': 'Initiative created — not yet submitted'},
    'G1': {'label': 'Validated',      'color': '#185FA5', 'bg': '#E6F1FB',
           'desc': 'Initiative approved as submitted'},
    'G2': {'label': 'Business case',  'color': '#0F6E56', 'bg': '#E1F5EE',
           'desc': 'Business case approved, prioritised'},
    'G3': {'label': 'Implementation', 'color': '#BA7517', 'bg': '#FAEEDA',
           'desc': 'Milestone plan locked, executing'},
    'G4': {'label': 'Impact tracking','color': '#993C1D', 'bg': '#FAECE7',
           'desc': 'Money step reached, tracking impact'},
    'G5': {'label': 'Embedded',       'color': '#3B6D11', 'bg': '#EAF3DE',
           'desc': 'Complete — impact sustained'},
    'On Hold':  {'label': 'On hold',  'color': '#5F5E5A', 'bg': '#F1EFE8', 'desc': 'Paused'},
    'Dropped':  {'label': 'Dropped',  'color': '#A32D2D', 'bg': '#FCEBEB', 'desc': 'Discontinued'},
}

GATE_ORDER = ['G0','G1','G2','G3','G4','G5']

INITIATIVE_CATEGORIES = [
    'Impact Generation',   # Revenue / PBT focused
    'Cost Optimisation',   # Cost reduction
    'Enabler',             # Infrastructure / capability
    'Customer Experience', # NPS / retention
    'Compliance & Risk',   # Regulatory
    'Digital & Innovation',
    'People & Culture',
    'Other',
]

MILESTONE_TYPES = ['Implementation', 'Health Check', 'Money Step']

# ── ESCALATION DISPLAY HELPERS ──────────────────────────────────────
# Banking-grade escalation — tight timelines, immediate visibility
ESC_CONFIG = {
    0: {'label': 'On track',          'color': '#3B6D11', 'bg': '#EAF3DE', 'icon': '✅'},
    1: {'label': 'Due soon — alert',  'color': '#BA7517', 'bg': '#FAEEDA', 'icon': '🟡'},
    2: {'label': 'Overdue — IO',      'color': '#993C1D', 'bg': '#FAECE7', 'icon': '🔴'},
    3: {'label': 'Escalated — Lead',  'color': '#A32D2D', 'bg': '#FCEBEB', 'icon': '🚨'},
    4: {'label': 'CRITICAL — Sponsor','color': '#791F1F', 'bg': '#F7C1C1', 'icon': '💥'},
    5: {'label': 'NOT STARTED',       'color': '#5F5E5A', 'bg': '#F1EFE8', 'icon': '⏰'},
}
# Banking escalation tiers:
#   L0  On track        — start date future, due date > 2 days away
#   L1  Due soon        — due within 2 days (email kicks in here)
#   L2  Overdue (day 1) — 1–2 days overdue → IO notified immediately
#   L3  Escalated       — 3–7 days overdue OR blocker raised → Lead notified
#   L4  Critical        — >7 days overdue OR Structural delay → Sponsor immediately
#   L5  Not started     — start date passed, status still "Not Started"

# Delay categories — determines who gets notified immediately
DELAY_CATEGORIES = [
    'Structural',          # Org/resource issue — immediate sponsor alert regardless of days
    'Dependency blocked',  # Waiting on another team/milestone
    'Regulatory / compliance', # External constraint
    'Resource constraint', # Capacity / budget issue
    'Technical challenge', # System / data issue
    'Stakeholder alignment', # Sign-off pending
    'Data / information gap',
    'Other / in progress', # Normal delay — follow standard escalation
]

STRUCTURAL_CATEGORIES = frozenset({'Structural', 'Regulatory / compliance'})
# These trigger immediate Level 4 (Sponsor) escalation regardless of days overdue

def escalation_badge(level):
    cfg = ESC_CONFIG.get(level, ESC_CONFIG[0])
    return (f"<span style='background:{cfg['bg']};color:{cfg['color']};"
            f"padding:2px 8px;border-radius:4px;font-size:11px;font-weight:500'>"
            f"{cfg['icon']} {cfg['label']}</span>")

def days_label(days):
    if days < -7:   return f"<span style='color:#791F1F;font-weight:500'>{-days}d overdue</span>"
    elif days < 0:  return f"<span style='color:#A32D2D;font-weight:500'>{-days}d overdue</span>"
    elif days == 0: return "<span style='color:#A32D2D;font-weight:500'>Due today</span>"
    elif days <= 2: return f"<span style='color:#BA7517;font-weight:500'>Due in {days}d ⚡</span>"
    else:           return f"<span style='color:var(--color-text-secondary)'>Due in {days}d</span>"

def start_label(days_to_start):
    """Label for milestone start date status."""
    if days_to_start < -1:  return f"<span style='color:#791F1F;font-weight:500'>Should have started {-days_to_start}d ago</span>"
    elif days_to_start < 0: return "<span style='color:#A32D2D;font-weight:500'>Should have started yesterday</span>"
    elif days_to_start == 0:return "<span style='color:#BA7517;font-weight:500'>Starts today</span>"
    elif days_to_start <= 3:return f"<span style='color:#BA7517;font-weight:500'>Starts in {days_to_start}d</span>"
    else:                    return f"<span style='color:var(--color-text-secondary)'>Starts in {days_to_start}d</span>"

# Approvers required per gate transition
GATE_APPROVERS = {
    'G0→G1': ['workstream_lead', 'sponsor'],
    'G1→G2': ['workstream_lead', 'sponsor', 'finance'],
    'G2→G3': ['workstream_lead', 'sponsor', 'finance'],   # after milestone owner confirmations
    'G3→G4': ['workstream_lead', 'sponsor', 'finance'],
    'G4→G5': ['workstream_lead', 'sponsor', 'finance'],
}

# Impact KPI options for business case
IMPACT_KPI_OPTIONS = [
    'PBT', 'Revenue', 'Cost Savings', 'Deposit Growth', 'Loan Book Growth',
    'Customer Growth', 'NPS / Cx Score', 'Fees and Commission', 'DFS Revenue',
    'NPL Reduction', 'Staff Productivity', 'Process Efficiency', 'Other',
]

PRODUCT_TYPES  = [
    "Business Loan","Personal Loan","Mortgage","Overdraft","Trade Finance",
    "Asset Finance","Invoice Discounting","Deposit Account","Current Account",
    "Insurance","Bancassurance","Treasury","Digital Banking","Other",
]
ACTIVITY_TYPES = [
    "Cold Call","Discovery Meeting","Follow-up Call","Product Presentation",
    "Site Visit","Credit Committee","Proposal Submitted","Contract Signing",
    "Account Opening","Referral","Email","WhatsApp","Other",
]
LOSS_REASONS   = [
    "Pricing","Competitor offer","Credit declined","Customer withdrew",
    "Documentation issues","Relationship breakdown","Other",
]

# ─── KPI INSIGHT ENGINE ──────────────────────────────────────────────
def get_kpi_insights(kpis_df):
    """
    Analyse a staff member's KPI rows and return structured insights.
    Returns dict: strengths, weaknesses, critical, summary_text
    """
    if kpis_df.empty:
        return {"strengths":[], "weaknesses":[], "critical":[], "summary":"No KPI data available."}

    strengths  = []
    weaknesses = []
    critical   = []

    for _, r in kpis_df.iterrows():
        score = r.get('Score', np.nan)
        ach   = r.get('Percent_Achieved', np.nan)
        kpi   = str(r.get('KPI',''))
        pillar= str(r.get('Pillar','General'))
        w     = r.get('Weight', 0)
        tgt   = r.get('Annual Target', np.nan)
        act   = r.get('YTD_Actual', np.nan)

        if pd.isna(score): continue

        gap = ""
        if pd.notna(tgt) and pd.notna(act) and tgt > 0:
            shortfall = tgt - act
            if shortfall > 0:
                gap = f" (gap: {fmt_num(shortfall, short=True)})"

        entry = {"kpi": kpi, "pillar": pillar, "score": score,
                 "achievement": ach, "weight": w, "gap": gap,
                 "weighted": round(score * w, 3)}

        if score >= 3.5:
            strengths.append(entry)
        elif score < 2.5:
            critical.append(entry)
        elif score < 3.0:
            weaknesses.append(entry)

    # Sort by weight × impact descending
    critical.sort(key=lambda x: x['weight'], reverse=True)
    weaknesses.sort(key=lambda x: x['weight'], reverse=True)
    strengths.sort(key=lambda x: x['weighted'], reverse=True)

    # Build narrative summary
    bsc = kpis_df['Weighted_Score'].sum() if 'Weighted_Score' in kpis_df.columns else 0
    remark = get_performance_remarks(bsc)

    if critical:
        top_crit = critical[0]
        crit_names = ", ".join(x['kpi'] for x in critical[:3])
        summary = (f"{remark}. Critical attention needed on: {crit_names}. "
                   f"These carry {sum(x['weight'] for x in critical)*100:.0f}% of total weight.")
    elif weaknesses:
        weak_names = ", ".join(x['kpi'] for x in weaknesses[:3])
        summary = (f"{remark}. Improvement needed in: {weak_names}. "
                   f"Addressing these could add ~{sum(x['weight']*(3-x['score']) for x in weaknesses):.2f} to BSC score.")
    elif strengths:
        str_names = ", ".join(x['kpi'] for x in strengths[:3])
        summary = f"{remark}. Performing strongly on: {str_names}. Maintain momentum."
    else:
        summary = f"{remark}. Performance is broadly on target."

    return {"strengths": strengths, "weaknesses": weaknesses,
            "critical": critical, "summary": summary, "bsc": round(bsc, 2)}


def render_insight_card(insights, staff_name=""):
    """Render a colour-coded insight card using st.markdown."""
    summary = insights.get("summary","")
    critical = insights.get("critical",[])
    weaknesses = insights.get("weaknesses",[])
    strengths  = insights.get("strengths",[])

    # Summary banner
    bsc = insights.get("bsc", 0)
    remark = get_performance_remarks(bsc)
    banner_colour = {
        "Exceeded By Far":"#2ECC71","Exceeded":"#58D68D","Met":"#F39C12",
        "Partially Met":"#E67E22","Unmet":"#E74C3C","No Data":"#BDC3C7"
    }.get(remark,"#BDC3C7")

    st.markdown(
        f"<div style='padding:12px 16px;background:{banner_colour}22;"
        f"border-left:5px solid {banner_colour};border-radius:6px;margin-bottom:12px'>"
        f"<strong>{staff_name + ' — ' if staff_name else ''}{remark} ({fmt_score(bsc)})</strong><br>"
        f"<span style='font-size:13px'>{summary}</span></div>",
        unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("##### 🔴 Needs attention")
        if critical:
            for x in critical[:4]:
                st.markdown(
                    f"<div style='padding:7px 10px;background:#FFB6C122;border-left:3px solid #E74C3C;"
                    f"border-radius:4px;margin:3px 0;font-size:13px'>"
                    f"<b>{x['kpi']}</b><br>"
                    f"Score {fmt_score(x['score'])} | {fmt_pct(x['achievement'])} achieved"
                    f"{x['gap']}<br>"
                    f"<span style='color:#888'>Weight {x['weight']*100:.0f}% | Pillar: {x['pillar']}</span>"
                    f"</div>", unsafe_allow_html=True)
        else:
            st.success("No critical KPIs")

    with c2:
        st.markdown("##### 🟡 Below target")
        if weaknesses:
            for x in weaknesses[:4]:
                st.markdown(
                    f"<div style='padding:7px 10px;background:#FFD70022;border-left:3px solid #F39C12;"
                    f"border-radius:4px;margin:3px 0;font-size:13px'>"
                    f"<b>{x['kpi']}</b><br>"
                    f"Score {fmt_score(x['score'])} | {fmt_pct(x['achievement'])} achieved"
                    f"{x['gap']}<br>"
                    f"<span style='color:#888'>Weight {x['weight']*100:.0f}% | Pillar: {x['pillar']}</span>"
                    f"</div>", unsafe_allow_html=True)
        else:
            st.success("No below-target KPIs")

    with c3:
        st.markdown("##### 🟢 Strengths")
        if strengths:
            for x in strengths[:4]:
                st.markdown(
                    f"<div style='padding:7px 10px;background:#90EE9022;border-left:3px solid #2ECC71;"
                    f"border-radius:4px;margin:3px 0;font-size:13px'>"
                    f"<b>{x['kpi']}</b><br>"
                    f"Score {fmt_score(x['score'])} | {fmt_pct(x['achievement'])} achieved<br>"
                    f"<span style='color:#888'>Weight {x['weight']*100:.0f}% | Pillar: {x['pillar']}</span>"
                    f"</div>", unsafe_allow_html=True)
        else:
            st.info("No standout strengths yet")

def parse_month_column(col_name):
    col_str = str(col_name).strip()
    col_str = col_str.replace(" Actual","").replace(" actual","")
    month_map = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
                 'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
    for name, num in month_map.items():
        if name in col_str.upper():
            digits = ''.join(filter(str.isdigit, col_str))
            year = 2000 + int(digits) if digits and int(digits) < 100 else (
                   int(digits) if digits else datetime.now().year)
            return datetime(year, num, 1)
    return None

def detect_month_actual_columns(df):
    results = []
    month_abbr = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
                  'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
    skip = ['target','ytd','modulator','unnamed','annual']
    for col in df.columns:
        col_str = str(col).strip().lower()
        if any(x in col_str for x in skip): continue
        for abbr, num in month_abbr.items():
            if abbr in col_str:
                digits = re.findall(r'\d+', col_str)
                yr = 2000 + int(digits[0]) if digits and int(digits[0]) < 100 else (
                     int(digits[0]) if digits else datetime.now().year)
                results.append((datetime(yr, num, 1), col))
                break
    results.sort(key=lambda x: x[0])
    return [col for _, col in results]

# ─── DATA PROCESSING ─────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def process_kpi_data(df):
    # ── Strip any repeated header rows (row where KPI == 'KPI') ──────
    # Happens when Excel has a title row + header row → header=1 picks
    # up row 2 as headers, but row 2 is sometimes duplicated as data.
    if 'KPI' in df.columns:
        mask_hdr = df['KPI'].astype(str).str.strip().str.lower() == 'kpi'
        if mask_hdr.any():
            df = df[~mask_hdr].copy()
    # Also drop rows where Staff Name == 'Staff Name' (same issue)
    if 'Staff Name' in df.columns:
        mask_sn = df['Staff Name'].astype(str).str.strip().str.lower() == 'staff name'
        if mask_sn.any():
            df = df[~mask_sn].copy()

    # ── Normalise column names from either Excel format ───────────────
    # New format: 'Jan-26 Actual' → rename to 'Jan-26'
    rename_map = {}
    for col in df.columns:
        for month in ['Jan','Feb','Mar','Apr','May','Jun',
                      'Jul','Aug','Sep','Oct','Nov','Dec']:
            if col.startswith(month) and col.endswith(' Actual'):
                # e.g. 'Jan-26 Actual' → 'Jan-26'
                rename_map[col] = col.replace(' Actual','')
    if rename_map:
        df = df.rename(columns=rename_map)

    df = df.copy()
    df['Staff Code'] = df['Staff Code'].astype(str).str.strip()

    month_cols    = detect_month_actual_columns(df)
    now           = datetime.now()
    active_months = [c for c in month_cols
                     if (lambda d: d and (d.year < now.year or
                         (d.year == now.year and d.month <= now.month))
                        )(parse_month_column(c))]

    # YTD_Actual: sum of active month actuals if available, else use Annual Actual column
    if active_months:
        df['YTD_Actual'] = df[active_months].apply(
            pd.to_numeric, errors='coerce').fillna(0).sum(axis=1)
    elif 'Annual Actual' in df.columns:
        df['YTD_Actual'] = pd.to_numeric(df['Annual Actual'], errors='coerce').fillna(0)
    elif 'YTD_Actual' in df.columns:
        df['YTD_Actual'] = pd.to_numeric(df['YTD_Actual'], errors='coerce').fillna(0)
    else:
        df['YTD_Actual'] = 0.0

    # Always keep Annual Actual as a separate column for reference
    if 'Annual Actual' not in df.columns and 'YTD_Actual' in df.columns:
        df['Annual Actual'] = df['YTD_Actual']

    if 'Weight' in df.columns:
        df['Weight'] = (
            df['Weight'].astype(str).str.replace('%','',regex=False)
            .apply(lambda x: float(x) if x not in ['nan','','None'] else np.nan)
            .apply(lambda x: x/100 if pd.notna(x) and x > 1 else x)
            .fillna(0)
        )
    else:
        df['Weight'] = 1.0

    if 'Annual Target' not in df.columns and 'Target' in df.columns:
        df['Annual Target'] = df['Target']

    reverse_kpis = ['PAR','NPL','PORTFOLIO AT RISK','DELINQUENCY','COST','EXPENSE']
    # Vectorized scoring — no iterrows, runs 50x faster on 2782 rows
    target = pd.to_numeric(df['Annual Target'], errors='coerce')
    actual = pd.to_numeric(df['YTD_Actual'],    errors='coerce').fillna(0)
    kpi_up = df['KPI'].astype(str).str.upper()

    is_rev  = kpi_up.apply(lambda k: any(t in k for t in reverse_kpis))
    valid   = target.notna() & (target != 0)

    ach = pd.Series(np.nan, index=df.index)
    # Forward KPIs
    fwd = valid & ~is_rev
    ach[fwd] = (actual[fwd] / target[fwd]).clip(0, 1.5)
    # Reverse KPIs
    rev = valid & is_rev
    has_actual = actual > 0
    ach[rev & has_actual] = (target[rev & has_actual] / actual[rev & has_actual]).clip(0, 1.5)
    ach[rev & ~has_actual] = 0.0

    # Score from achievement using vectorized np.select
    conditions = [
        ach.isna(),
        ach < 0.30, ach <= 0.50, ach <= 0.60, ach <= 0.90,
        ach <= 1.00, ach <= 1.10, ach <= 1.20, ach <= 1.30,
    ]
    choices = [np.nan, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5]
    score = pd.Series(np.select(conditions, choices, default=5.0), index=df.index)

    df['Score']            = score.round(2)
    df['Weighted_Score']   = (score * df['Weight'].fillna(0)).round(2)
    df['Percent_Achieved'] = (ach * 100).round(1)
    return df

@st.cache_data(show_spinner=False)
def build_staff_scores(df):
    grp = [c for c in ['Staff Name','Role','Unit','Category','Staff Code','Staff Status'] if c in df.columns]
    staff = df.groupby(grp, as_index=False).agg(
        Final_BSC_Score     = ('Weighted_Score','sum'),
        Avg_KPI_Score       = ('Score','mean'),
        Avg_Achievement_Pct = ('Percent_Achieved','mean'),
        KPI_Count           = ('KPI','count'),
    )
    if 'Role' in staff.columns and 'Category' in staff.columns:
        staff['Role_Function'] = staff.apply(
            lambda r: get_role_function(r['Role'], r['Category']), axis=1)
    staff['Final_BSC_Score']     = staff['Final_BSC_Score'].round(2)
    staff['Avg_KPI_Score']       = staff['Avg_KPI_Score'].round(2)
    staff['Avg_Achievement_Pct'] = staff['Avg_Achievement_Pct'].round(1)
    staff['Performance_Remark']  = staff['Final_BSC_Score'].apply(get_performance_remarks)
    staff['Overall_Rank']        = staff['Final_BSC_Score'].rank(method='dense', ascending=False).astype(int)
    staff['Role_Rank']           = staff.groupby('Role')['Final_BSC_Score'].rank(method='dense', ascending=False).astype(int)
    staff['Role_Total']          = staff.groupby('Role')['Staff Name'].transform('count')
    staff['Percentile']          = (staff['Final_BSC_Score'].rank(pct=True)*100).round(1)
    if 'Unit' in staff.columns:
        staff['Region'] = staff['Unit'].map(BRANCH_REGION).fillna('Head Office')
    return staff.sort_values(by='Overall_Rank').reset_index(drop=True)


@st.cache_data(show_spinner=False)
def build_staff_registry(_raw_bytes: bytes):
    """Extract staff master data — accepts raw bytes. Handles multi-sheet and single-sheet formats."""
    try:
        raw = _raw_bytes
        xl  = pd.ExcelFile(io.BytesIO(raw))

        # ── Try new multi-sheet format (Staff Register sheet) ─────────
        if 'Staff Register' in xl.sheet_names:
            df = pd.read_excel(io.BytesIO(raw), sheet_name='Staff Register', header=1)
            # Normalise column names
            df.columns = [str(c).strip() for c in df.columns]
            # Strip any repeated header row (where Staff Code == 'Staff Code')
            if 'Staff Code' in df.columns:
                df = df[df['Staff Code'].astype(str).str.strip().str.lower() != 'staff code'].copy()
            rename = {'Reports To Code': 'Reports_To', 'Staff Status': 'Staff Status',
                      'Hire Date': 'Hire Date', 'Role Function': 'Role Function'}
            df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
            if 'Region' not in df.columns and 'Unit' in df.columns:
                df['Region'] = df['Unit'].map(BRANCH_REGION).fillna('Head Office')
            return df

        # ── Fallback: single-sheet format (original system build file) ─
        for sheet in xl.sheet_names:
            df = pd.read_excel(io.BytesIO(raw), sheet_name=sheet)
            if 'Hire Date' in df.columns or 'Staff Status' in df.columns:
                df.columns = [str(c).strip() for c in df.columns]
                if 'Region' not in df.columns and 'Unit' in df.columns:
                    df['Region'] = df['Unit'].map(BRANCH_REGION).fillna('Head Office')
                return df

        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()



# ─── KENYA LEAVE TYPES (Employment Act 2007 & amendments) ────────────
LEAVE_TYPES = {
    "Annual Leave": {
        "days_entitled": 21,
        "max_days":      21,
        "description":   "21 working days per year (Employment Act s.28)",
        "paid":          True,
        "affects_performance": False,
        "compensation":  "pro_rata",
        "color":         "#006B3F",
    },
    "Sick Leave": {
        "days_entitled": 14,
        "max_days":      14,
        "description":   "7 days full pay + 7 days half pay per year (s.30)",
        "paid":          True,
        "affects_performance": True,
        "compensation":  "exclude_month",
        "color":         "#E24B4A",
    },
    "Maternity Leave": {
        "days_entitled": 91,
        "max_days":      91,
        "description":   "3 months fully paid maternity leave (s.29)",
        "paid":          True,
        "affects_performance": True,
        "compensation":  "exclude_all",
        "color":         "#9B59B6",
    },
    "Paternity Leave": {
        "days_entitled": 14,
        "max_days":      14,
        "description":   "2 weeks fully paid paternity leave (s.29A)",
        "paid":          True,
        "affects_performance": False,
        "compensation":  "pro_rata",
        "color":         "#185FA5",
    },
    "Compassionate Leave": {
        "days_entitled": 5,
        "max_days":      5,
        "description":   "Bereavement/compassionate — immediate family",
        "paid":          True,
        "affects_performance": False,
        "compensation":  "pro_rata",
        "color":         "#7F8C8D",
    },
    "Study Leave": {
        "days_entitled": 0,
        "max_days":      0,
        "description":   "Employer-discretionary; exam preparation or professional courses",
        "paid":          True,
        "affects_performance": False,
        "compensation":  "pro_rata",
        "color":         "#F5A623",
    },
    "Leave Without Pay": {
        "days_entitled": 0,
        "max_days":      0,
        "description":   "Unpaid leave by mutual agreement",
        "paid":          False,
        "affects_performance": True,
        "compensation":  "exclude_month",
        "color":         "#E67E22",
    },
    "Garden Leave": {
        "days_entitled": 0,
        "max_days":      0,
        "description":   "Notice period served at home on full pay",
        "paid":          True,
        "affects_performance": True,
        "compensation":  "exclude_all",
        "color":         "#BDC3C7",
    },
    "Sabbatical Leave": {
        "days_entitled": 0,
        "max_days":      0,
        "description":   "Extended leave for research, development or personal growth",
        "paid":          False,
        "affects_performance": True,
        "compensation":  "exclude_all",
        "color":         "#1ABC9C",
    },
    "Public Holiday": {
        "days_entitled": 0,
        "max_days":      0,
        "description":   "Public/gazetted holidays as per Kenya Public Holidays Act",
        "paid":          True,
        "affects_performance": False,
        "compensation":  "none",
        "color":         "#95A5A6",
    },
}

# ─── EXIT REASONS ─────────────────────────────────────────────────────

COMPENSATION_LABELS: dict = {
    "none":          "✅ No impact — full score applies",
    "pro_rata":      "⚠️ Pro-rata — score weighted by days worked",
    "exclude_month": "⚠️ Month excluded — that period removed from BSC",
    "exclude_all":   "🔴 All affected months excluded from scoring",
}

EXIT_REASONS = [
    "Resignation — Better opportunity",
    "Resignation — Salary/compensation",
    "Resignation — Work environment",
    "Resignation — Career growth concerns",
    "Resignation — Personal reasons",
    "Resignation — Relocation",
    "Contract end — Not renewed",
    "Retirement — Mandatory",
    "Retirement — Voluntary (early)",
    "Dismissal — Gross misconduct",
    "Dismissal — Performance",
    "Dismissal — Redundancy",
    "Dismissal — Abscondment",
    "Mutual separation",
    "Medical — Incapacitation",
    "Death in service",
]

# ─── TRANSFER REASONS ─────────────────────────────────────────────────
TRANSFER_REASONS = [
    "Performance improvement — new environment",
    "Branch need — skills gap",
    "Staff request — personal reasons",
    "Staff request — proximity to home",
    "Disciplinary — conflict resolution",
    "Rotational development",
    "Promotion transfer",
    "Role restructuring",
]

# ─── DISCIPLINARY CATEGORIES ──────────────────────────────────────────
DISCIPLINARY_CATEGORIES = [
    "Gross misconduct",
    "Insubordination",
    "Absenteeism / lateness",
    "Fraud / financial irregularity",
    "Sexual harassment",
    "Conflict of interest",
    "Breach of confidentiality",
    "Performance negligence",
    "Policy violation",
    "Substance abuse at workplace",
    "Bullying / workplace violence",
    "Misrepresentation",
]

DISCIPLINARY_STAGES = [
    "Verbal warning",
    "Written warning (1st)",
    "Written warning (final)",
    "Show cause notice",
    "Suspension pending investigation",
    "Disciplinary hearing scheduled",
    "Disciplinary hearing held",
    "Decision — Dismissed",
    "Decision — Demoted",
    "Decision — Final warning",
    "Decision — Exonerated",
    "Appeal filed",
    "Appeal resolved",
]

# ─── PIP CONSTANTS ────────────────────────────────────────────────────
PIP_DURATIONS = [30, 60, 90]   # days
PIP_OUTCOMES  = [
    "In progress",
    "Successfully completed",
    "Extended",
    "Terminated — dismissal",
    "Terminated — resignation",
    "Converted to final warning",
]

PIP_REVIEW_FREQUENCIES = ["Weekly", "Fortnightly", "Monthly"]

# ─── DILIGENCE SCORE WEIGHTS ──────────────────────────────────────────
# Used to compute per-staff HR diligence score (0-100)
DILIGENCE_WEIGHTS = {
    "milestone_on_time_rate":   0.30,   # % milestones completed on time
    "action_acceptance_rate":   0.20,   # % action items accepted within 24h
    "leave_compliance":         0.15,   # no AWOL / unexplained absence
    "disciplinary_clean":       0.20,   # no active disciplinary = 1.0
    "pip_clear":                0.15,   # not on PIP = 1.0
}

class LeaveManager:
    def __init__(self):
        self.file = DATA_DIR / "leave_records.json"
        if not self.file.exists(): self.file.write_text("[]")
        try:
            raw = self.file.read_text()
            self.records = json.loads(raw) if raw.strip() else []
            if not isinstance(self.records, list): self.records = []
        except:
            self.records = []

    def save(self):
        self.file.write_text(json.dumps(self.records, indent=2))

    def add_leave(self, staff_code, staff_name, leave_type, start_date, end_date,
                  reason, approved_by, notify_suppress=True):
        days = (end_date - start_date).days + 1
        record = {
            "id":              len(self.records) + 1,
            "staff_code":      clean_code(staff_code),
            "staff_name":      staff_name,
            "leave_type":      leave_type,
            "start_date":      str(start_date),
            "end_date":        str(end_date),
            "days":            days,
            "reason":          reason,
            "approved_by":     approved_by,
            "notify_suppress": notify_suppress,
            "compensation":    LEAVE_TYPES.get(leave_type, LEAVE_TYPES["Annual Leave"]).get("compensation", "none"),
            "affects_perf":    LEAVE_TYPES.get(leave_type, LEAVE_TYPES["Annual Leave"]).get("affects_performance", False),
            "status":          "Active" if start_date <= datetime.now().date() <= end_date else (
                               "Upcoming" if start_date > datetime.now().date() else "Completed"),
            "recorded_at":     datetime.now().isoformat(),
        }
        self.records.append(record)
        self.save()
        return record

    def get_active_leave(self, staff_code=None):
        today = datetime.now().date()
        active = [r for r in self.records
                  if r['start_date'] <= str(today) <= r['end_date']]
        if staff_code:
            active = [r for r in active if r['staff_code'] == clean_code(staff_code)]
        return active

    def get_staff_leave(self, staff_code):
        return [r for r in self.records if r['staff_code'] == clean_code(staff_code)]

    def is_on_leave(self, staff_code):
        return len(self.get_active_leave(staff_code)) > 0

    def get_leave_months(self, staff_code, year=None):
        """Return set of (year, month) tuples when staff was on leave — for score compensation."""
        year = year or datetime.now().year
        leave_months = set()
        for r in self.get_staff_leave(staff_code):
            if not r.get('affects_perf'): continue
            sd = datetime.strptime(r['start_date'], "%Y-%m-%d").date()
            ed = datetime.strptime(r['end_date'],   "%Y-%m-%d").date()
            current = sd
            while current <= ed:
                if current.year == year:
                    leave_months.add((current.year, current.month))
                current = (current.replace(day=1) + timedelta(days=32)).replace(day=1)
        return leave_months

    def compensated_score(self, staff_code, monthly_scores, year=None):
        """
        Apply leave compensation to monthly scores.
        Returns (adjusted_score, explanation).
        monthly_scores = {month_num: weighted_score}
        """
        year = year or datetime.now().year
        leave_months = self.get_leave_months(staff_code, year)
        if not leave_months:
            total = sum(monthly_scores.values())
            return total, "No leave compensation applied."

        # Find compensation type from most recent affecting leave
        comp_type = None
        for r in self.get_staff_leave(staff_code):
            if r.get('affects_perf'):
                comp_type = r['compensation']
                break

        active_months = {m: s for m, s in monthly_scores.items()
                         if (year, m) not in leave_months}

        if comp_type == "exclude_period":
            if not active_months:
                return 0.0, "All months on leave — no score."
            avg = sum(active_months.values()) / len(active_months)
            explanation = (f"Leave months excluded ({len(leave_months)} months). "
                           f"Score based on {len(active_months)} active months.")
            return round(avg * len(monthly_scores), 2), explanation

        elif comp_type == "pro_rata":
            if not active_months:
                return 0.0, "All months on leave — no score."
            pro_score = sum(active_months.values())
            explanation = (f"Pro-rata: scored on {len(active_months)}/{len(monthly_scores)} months "
                           f"({len(leave_months)} leave months excluded).")
            return round(pro_score, 2), explanation

        else:
            total = sum(monthly_scores.values())
            return total, "Leave noted but full score applied."

# ─── HR MANAGER (exits, transfers, disciplinary, PIP) ────────────────
class HRManager:
    """Central HR data manager — exits, transfers, disciplinary, PIP, diligence scores."""

    def __init__(self):
        self.exits_file  = DATA_DIR / "hr_exits.json"
        self.trans_file  = DATA_DIR / "hr_transfers.json"
        self.disc_file   = DATA_DIR / "hr_disciplinary.json"
        self.pip_file    = DATA_DIR / "hr_pip.json"
        self.exits       = self._load(self.exits_file)
        self.transfers   = self._load(self.trans_file)
        self.disciplinary= self._load(self.disc_file)
        self.pips        = self._load(self.pip_file)

    def _load(self, path):
        if not path.exists(): path.write_text("[]")
        try:
            raw = path.read_text()
            d = json.loads(raw) if raw.strip() else []
            return d if isinstance(d, list) else []
        except: return []

    def _save(self, path, data):
        path.write_text(json.dumps(data, indent=2, default=str))

    # ── EXITS ─────────────────────────────────────────────────────
    def record_exit(self, data: dict) -> dict:
        rec = {
            "id":           f"EX{len(self.exits)+1:04d}",
            "staff_code":   clean_code(data.get("staff_code","")),
            "staff_name":   data.get("staff_name",""),
            "unit":         data.get("unit",""),
            "region":       data.get("region",""),
            "role":         data.get("role",""),
            "exit_date":    str(data.get("exit_date", date.today())),
            "reason":       data.get("reason",""),
            "reason_detail":data.get("reason_detail",""),
            "final_bsc":    data.get("final_bsc", None),
            "tenure_years": data.get("tenure_years", 0),
            "exit_interview":data.get("exit_interview",""),
            "rehire_eligible":data.get("rehire_eligible", True),
            "recorded_by":  data.get("recorded_by",""),
            "recorded_at":  datetime.now().isoformat(),
        }
        self.exits.append(rec)
        self._save(self.exits_file, self.exits)
        return rec

    def get_exits(self, months_back=12):
        cutoff = (datetime.now() - timedelta(days=months_back*30)).date()
        return [e for e in self.exits
                if datetime.strptime(e['exit_date'][:10], "%Y-%m-%d").date() >= cutoff]

    def exit_analytics(self):
        exits = self.exits
        if not exits: return {}
        by_reason   = {}
        by_unit     = {}
        by_quarter  = {}
        avg_tenure  = []
        bsc_at_exit = []
        for e in exits:
            r = e.get("reason","Unknown"); by_reason[r]  = by_reason.get(r, 0)+1
            u = e.get("unit","Unknown");   by_unit[u]    = by_unit.get(u, 0)+1
            try:
                d = datetime.strptime(e['exit_date'][:10], "%Y-%m-%d")
                q = f"{d.year} Q{(d.month-1)//3+1}"
                by_quarter[q] = by_quarter.get(q, 0)+1
            except: pass
            if e.get("tenure_years"): avg_tenure.append(float(e["tenure_years"]))
            if e.get("final_bsc"):    bsc_at_exit.append(float(e["final_bsc"]))
        return {"by_reason": by_reason, "by_unit": by_unit, "by_quarter": by_quarter,
                "avg_tenure": sum(avg_tenure)/len(avg_tenure) if avg_tenure else 0,
                "avg_bsc_at_exit": sum(bsc_at_exit)/len(bsc_at_exit) if bsc_at_exit else None,
                "total": len(exits)}

    # ── TRANSFERS ─────────────────────────────────────────────────
    def record_transfer(self, data: dict) -> dict:
        rec = {
            "id":           f"TR{len(self.transfers)+1:04d}",
            "staff_code":   clean_code(data.get("staff_code","")),
            "staff_name":   data.get("staff_name",""),
            "from_unit":    data.get("from_unit",""),
            "to_unit":      data.get("to_unit",""),
            "from_region":  data.get("from_region",""),
            "to_region":    data.get("to_region",""),
            "transfer_date":str(data.get("transfer_date", date.today())),
            "reason":       data.get("reason",""),
            "bsc_before":   data.get("bsc_before", None),
            "bsc_after":    data.get("bsc_after", None),
            "initiated_by": data.get("initiated_by",""),
            "recorded_at":  datetime.now().isoformat(),
        }
        self.transfers.append(rec)
        self._save(self.trans_file, self.transfers)
        return rec

    def get_transfers(self, months_back=12):
        cutoff = (datetime.now() - timedelta(days=months_back*30)).date()
        return [t for t in self.transfers
                if datetime.strptime(t['transfer_date'][:10], "%Y-%m-%d").date() >= cutoff]

    # ── DISCIPLINARY ──────────────────────────────────────────────
    def open_case(self, data: dict) -> dict:
        rec = {
            "id":            f"DC{len(self.disciplinary)+1:04d}",
            "staff_code":    clean_code(data.get("staff_code","")),
            "staff_name":    data.get("staff_name",""),
            "unit":          data.get("unit",""),
            "category":      data.get("category",""),
            "incident_date": str(data.get("incident_date", date.today())),
            "description":   data.get("description",""),
            "stage":         DISCIPLINARY_STAGES[0],
            "stage_history": [{"stage": DISCIPLINARY_STAGES[0],
                                "date": str(date.today()), "by": data.get("opened_by","")}],
            "opened_by":     data.get("opened_by",""),
            "status":        "Open",
            "outcome":       None,
            "outcome_date":  None,
            "notes":         [],
            "recorded_at":   datetime.now().isoformat(),
        }
        self.disciplinary.append(rec)
        self._save(self.disc_file, self.disciplinary)
        return rec

    def advance_stage(self, case_id: str, new_stage: str, note: str, by: str):
        for case in self.disciplinary:
            if case["id"] == case_id:
                case["stage"] = new_stage
                case["stage_history"].append({"stage": new_stage,
                                               "date": str(date.today()), "by": by})
                if note: case["notes"].append({"note": note, "date": str(date.today()), "by": by})
                if "Decision" in new_stage:
                    case["status"]   = "Closed"
                    case["outcome"]  = new_stage
                    case["outcome_date"] = str(date.today())
                self._save(self.disc_file, self.disciplinary)
                return case
        return None

    def get_active_cases(self):
        return [c for c in self.disciplinary if c.get("status") == "Open"]

    def staff_has_active_case(self, staff_code: str) -> bool:
        sc = clean_code(staff_code)
        return any(c["staff_code"]==sc and c.get("status")=="Open"
                   for c in self.disciplinary)

    # ── PIP ───────────────────────────────────────────────────────
    def open_pip(self, data: dict) -> dict:
        start = data.get("start_date", date.today())
        dur   = int(data.get("duration_days", 90))
        end   = start + timedelta(days=dur) if isinstance(start, date) else                 datetime.strptime(start, "%Y-%m-%d").date() + timedelta(days=dur)
        rec = {
            "id":              f"PIP{len(self.pips)+1:04d}",
            "staff_code":      clean_code(data.get("staff_code","")),
            "staff_name":      data.get("staff_name",""),
            "unit":            data.get("unit",""),
            "role":            data.get("role",""),
            "manager":         data.get("manager",""),
            "hr_officer":      data.get("hr_officer",""),
            "start_date":      str(start),
            "end_date":        str(end),
            "duration_days":   dur,
            "reason":          data.get("reason",""),
            "performance_gaps":data.get("performance_gaps",[]),
            "objectives":      data.get("objectives",[]),
            "review_frequency":data.get("review_frequency","Fortnightly"),
            "support_offered": data.get("support_offered",""),
            "reviews":         [],
            "outcome":         "In progress",
            "outcome_date":    None,
            "current_bsc":     data.get("current_bsc", None),
            "target_bsc":      data.get("target_bsc", 3.0),
            "opened_by":       data.get("opened_by",""),
            "recorded_at":     datetime.now().isoformat(),
        }
        self.pips.append(rec)
        self._save(self.pip_file, self.pips)
        return rec

    def add_pip_review(self, pip_id: str, review: dict):
        for pip in self.pips:
            if pip["id"] == pip_id:
                pip["reviews"].append({
                    "date":     str(date.today()),
                    "score":    review.get("score"),
                    "progress": review.get("progress",""),
                    "concerns": review.get("concerns",""),
                    "support":  review.get("support",""),
                    "by":       review.get("by",""),
                })
                if review.get("outcome") and review["outcome"] != "In progress":
                    pip["outcome"]      = review["outcome"]
                    pip["outcome_date"] = str(date.today())
                self._save(self.pip_file, self.pips)
                return pip
        return None

    def get_active_pips(self):
        return [p for p in self.pips if p.get("outcome") == "In progress"]

    def staff_on_pip(self, staff_code: str) -> bool:
        sc = clean_code(staff_code)
        return any(p["staff_code"]==sc and p.get("outcome")=="In progress"
                   for p in self.pips)

    def pip_days_remaining(self, pip: dict) -> int:
        try:
            end = datetime.strptime(pip["end_date"][:10], "%Y-%m-%d").date()
            return max(0, (end - date.today()).days)
        except: return 0

    # ── DILIGENCE SCORE ───────────────────────────────────────────
    def compute_diligence(self, staff_code: str, em=None, action_plans: dict=None) -> float:
        """
        Compute an HR diligence score (0-100) based on:
        - Milestone on-time rate (from ExecuteManager)
        - Action plan acceptance rate
        - No active disciplinary case
        - Not on PIP
        - Leave compliance (no unexplained absence)
        Returns a float 0-100.
        """
        sc = clean_code(staff_code)
        score = 0.0

        # Milestone on-time rate
        if em:
            try:
                all_ms = [ms for i in em.get_initiatives(status='All')
                          for ms in i.get('milestones',[])
                          if clean_code(ms.get('owner','')) == sc]
                if all_ms:
                    on_time = sum(1 for m in all_ms if m.get('status')=='Complete'
                                  and em._escalation_level(m) == 0)
                    rate = on_time / len(all_ms)
                else:
                    rate = 1.0
            except: rate = 1.0
            score += rate * DILIGENCE_WEIGHTS["milestone_on_time_rate"] * 100

        # Action plan acceptance rate
        if action_plans:
            my_actions = [a for plans in action_plans.values()
                          for a in plans if a.get('owner') == sc or a.get('owner') == staff_code]
            if my_actions:
                accepted = sum(1 for a in my_actions if a.get('accepted'))
                rate = accepted / len(my_actions)
            else:
                rate = 1.0
            score += rate * DILIGENCE_WEIGHTS["action_acceptance_rate"] * 100
        else:
            score += DILIGENCE_WEIGHTS["action_acceptance_rate"] * 100

        # Disciplinary
        disc_score = 0.0 if self.staff_has_active_case(sc) else 1.0
        score += disc_score * DILIGENCE_WEIGHTS["disciplinary_clean"] * 100

        # PIP
        pip_score = 0.0 if self.staff_on_pip(sc) else 1.0
        score += pip_score * DILIGENCE_WEIGHTS["pip_clear"] * 100

        # Leave compliance — assume clean if no unexplained absence recorded
        score += DILIGENCE_WEIGHTS["leave_compliance"] * 100

        return min(100.0, round(score, 1))



# ─── TARGET CASCADING MANAGER ─────────────────────────────────────────
class CascadeManager:
    """
    Manages top-down target allocation:
    MD → Director → Head/Manager → Staff
    Each level allocates portions of their own target downwards.
    """
    def __init__(self):
        self.file    = DATA_DIR / "target_cascade.json"
        self.cascade = self._load()

    def _load(self):
        if not self.file.exists(): self.file.write_text("{}")
        try:
            raw = self.file.read_text()
            d = json.loads(raw) if raw.strip() else {}
            return d if isinstance(d, dict) else {}
        except: return {}

    def _save(self):
        self.file.write_text(json.dumps(self.cascade, indent=2, default=str))

    def set_allocation(self, from_code: str, kpi: str, period: str,
                       allocations: list, total_target: float):
        """
        Set target allocations from one person to their direct reports.
        allocations = [{"to_code": "xxx", "to_name": "...", "amount": 1000000}, ...]
        """
        key = f"{from_code}|{kpi}|{period}"
        self.cascade[key] = {
            "from_code":    from_code,
            "kpi":          kpi,
            "period":       period,
            "total_target": total_target,
            "allocations":  allocations,
            "allocated_sum":sum(a["amount"] for a in allocations),
            "updated_at":   datetime.now().isoformat(),
        }
        self._save()
        return self.cascade[key]

    def get_allocation(self, from_code: str, kpi: str, period: str):
        key = f"{from_code}|{kpi}|{period}"
        return self.cascade.get(key)

    def get_my_allocations(self, staff_code: str, period: str):
        """What has this person cascaded down to their reports?"""
        sc = clean_code(staff_code)
        return {k: v for k, v in self.cascade.items()
                if v.get("from_code") == sc and v.get("period") == period}

    def get_what_i_was_given(self, staff_code: str, period: str):
        """What targets have been cascaded TO this person?"""
        sc = clean_code(staff_code)
        result = []
        for key, entry in self.cascade.items():
            for alloc in entry.get("allocations", []):
                if clean_code(alloc.get("to_code","")) == sc:
                    result.append({
                        "kpi":        entry["kpi"],
                        "period":     entry["period"],
                        "from_code":  entry["from_code"],
                        "amount":     alloc["amount"],
                        "total_pool": entry["total_target"],
                        "my_share":   alloc["amount"]/entry["total_target"]*100 if entry["total_target"] else 0,
                    })
        return result

    def cascade_coverage(self, from_code: str, kpi: str, period: str):
        """
        % of target that has been allocated down. 
        Returns (allocated_sum, total_target, coverage_pct, unallocated).
        """
        entry = self.get_allocation(from_code, kpi, period)
        if not entry:
            return 0, 0, 0, 0
        total = entry["total_target"]
        alloc = entry["allocated_sum"]
        cov   = round(alloc/total*100, 1) if total else 0
        return alloc, total, cov, max(0, total-alloc)


# ─── VALIDATION MANAGER (performance sign-off) ───────────────────────
class ValidationManager:
    """Manager sign-off on staff performance per period."""
    def __init__(self):
        self.file    = DATA_DIR / "validations.json"
        self.records = self._load()

    def _load(self):
        if not self.file.exists(): self.file.write_text("{}")
        try:
            raw = self.file.read_text()
            d = json.loads(raw) if raw.strip() else {}
            return d if isinstance(d, dict) else {}
        except: return {}

    def _save(self):
        self.file.write_text(json.dumps(self.records, indent=2, default=str))

    def validate(self, manager: str, staff_name: str, period: str,
                 status: str, action_plan: str = '', comments: str = ''):
        key = f"{staff_name}|{period}"
        self.records[key] = {
            "staff_name":   staff_name,
            "period":       period,
            "manager":      manager,
            "status":       status,
            "action_plan":  action_plan,
            "comments":     comments,
            "validated_at": datetime.now().isoformat(),
        }
        self._save()
        return self.records[key]

    def get(self, staff_name: str, period: str):
        return self.records.get(f"{staff_name}|{period}")

    def get_period_summary(self, period: str):
        return {k:v for k,v in self.records.items() if v.get('period')==period}


# ─── REPORTING LINE MANAGER ───────────────────────────────────────────
class ReportingLineManager:
    """
    Stores admin overrides to the reporting hierarchy.
    Overrides take precedence over the uploaded spreadsheet's 'Reports To Code'.
    Supports: remap staff → new manager, transfer staff between units,
    bulk unit reassignment, and full org-tree rebuild.
    """
    def __init__(self):
        self.file      = DATA_DIR / "reporting_lines.json"
        self.overrides = self._load()   # {staff_code: {manager_code, unit, region, updated_by, updated_at}}
        self.unit_map  = DATA_DIR / "unit_map.json"
        self.units     = self._load_units()  # {staff_code: {unit, region}}

    def _load(self):
        if not self.file.exists(): self.file.write_text("{}")
        try:
            raw = self.file.read_text()
            d = json.loads(raw) if raw.strip() else {}
            return d if isinstance(d, dict) else {}
        except: return {}

    def _load_units(self):
        if not self.unit_map.exists(): self.unit_map.write_text("{}")
        try:
            raw = self.unit_map.read_text()
            d = json.loads(raw) if raw.strip() else {}
            return d if isinstance(d, dict) else {}
        except: return {}

    def _save(self):
        self.file.write_text(json.dumps(self.overrides, indent=2, default=str))

    def _save_units(self):
        self.unit_map.write_text(json.dumps(self.units, indent=2, default=str))

    def remap(self, staff_code: str, new_manager_code: str,
              updated_by: str, reason: str = ''):
        """Remap a staff member to a new line manager."""
        sc = clean_code(staff_code)
        self.overrides[sc] = {
            'manager_code': clean_code(new_manager_code),
            'reason':       reason,
            'updated_by':   updated_by,
            'updated_at':   datetime.now().isoformat(),
        }
        self._save()

    def transfer(self, staff_code: str, new_unit: str, new_region: str,
                 new_manager_code: str, updated_by: str, reason: str = ''):
        """Transfer staff to a new unit + new manager."""
        sc = clean_code(staff_code)
        self.overrides[sc] = {
            'manager_code': clean_code(new_manager_code),
            'reason':       reason,
            'updated_by':   updated_by,
            'updated_at':   datetime.now().isoformat(),
        }
        self.units[sc] = {
            'unit':       new_unit,
            'region':     new_region,
            'updated_by': updated_by,
            'updated_at': datetime.now().isoformat(),
        }
        self._save()
        self._save_units()

    def bulk_remap_unit(self, old_manager_code: str, new_manager_code: str,
                        staff_codes: list, updated_by: str, reason: str = ''):
        """Remap multiple staff from one manager to another."""
        for sc in staff_codes:
            self.remap(sc, new_manager_code, updated_by, reason)

    def clear_override(self, staff_code: str, updated_by: str):
        """Remove override — staff reverts to uploaded data."""
        sc = clean_code(staff_code)
        if sc in self.overrides:
            self.overrides.pop(sc)
            self._save()
        if sc in self.units:
            self.units.pop(sc)
            self._save_units()

    def get_manager(self, staff_code: str) -> str:
        """Return overridden manager code, or None if not overridden."""
        return self.overrides.get(clean_code(staff_code), {}).get('manager_code')

    def get_unit(self, staff_code: str):
        """Return overridden unit info, or None."""
        return self.units.get(clean_code(staff_code))

    def apply_to_registry(self, registry_df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply all overrides to a staff registry DataFrame.
        Returns enriched DataFrame with overrides applied.
        """
        df = registry_df.copy()
        sc_col = 'Staff Code' if 'Staff Code' in df.columns else None
        if sc_col is None:
            return df
        df['Staff Code'] = df['Staff Code'].astype(str).str.strip()

        for sc, ov in self.overrides.items():
            mask = df['Staff Code'] == sc
            if mask.any() and 'Reports_To' in df.columns:
                df.loc[mask, 'Reports_To'] = ov['manager_code']

        for sc, unit_ov in self.units.items():
            mask = df['Staff Code'] == sc
            if mask.any():
                df.loc[mask, 'Unit']   = unit_ov['unit']
                df.loc[mask, 'Region'] = unit_ov['region']
        return df

    def get_all_overrides(self) -> list:
        """Return list of all current overrides for display."""
        result = []
        for sc, ov in self.overrides.items():
            rec = {'staff_code': sc, **ov}
            if sc in self.units:
                rec.update(self.units[sc])
            result.append(rec)
        return result

    def get_direct_reports(self, manager_code: str, registry_df: pd.DataFrame) -> list:
        """
        Return staff codes that report to this manager,
        combining uploaded data + overrides.
        """
        mc = clean_code(manager_code)
        applied = self.apply_to_registry(registry_df)
        rt_col = 'Reports_To' if 'Reports_To' in applied.columns else None
        if rt_col is None:
            return []
        mask = applied[rt_col].astype(str).str.strip() == mc
        return applied[mask]['Staff Code'].tolist()

    def get_org_tree(self, registry_df: pd.DataFrame) -> dict:
        """
        Build full org tree as nested dict {manager_code: [direct_report_codes]}.
        """
        applied = self.apply_to_registry(registry_df)
        tree = {}
        rt_col = 'Reports_To' if 'Reports_To' in applied.columns else None
        if rt_col is None:
            return {}
        for _, row in applied.iterrows():
            mgr = str(row.get(rt_col,'')).strip()
            sc  = str(row.get('Staff Code','')).strip()
            if mgr and mgr not in ('nan','None',''):
                tree.setdefault(mgr, []).append(sc)
        return tree

    def summary(self) -> dict:
        return {
            'total_overrides':  len(self.overrides),
            'total_transfers':  len(self.units),
            'last_updated':     max((v['updated_at'] for v in self.overrides.values()),
                                     default='Never'),
        }

# ─── PIPELINE MANAGER ────────────────────────────────────────────────
class PipelineManager:
    def __init__(self):
        self.deals_file      = DATA_DIR / "pipeline_deals.json"
        self.activities_file = DATA_DIR / "pipeline_activities.json"
        for f in [self.deals_file, self.activities_file]:
            if not f.exists(): f.write_text("[]")
        self.deals      = self._load(self.deals_file)
        self.activities = self._load(self.activities_file)

    def _load(self, f):
        try:
            raw = f.read_text()
            d = json.loads(raw) if raw.strip() else []
            return d if isinstance(d, list) else []
        except: return []

    def _save_deals(self):
        self.deals_file.write_text(json.dumps(self.deals, indent=2))

    def _save_activities(self):
        self.activities_file.write_text(json.dumps(self.activities, indent=2))

    def add_deal(self, d):
        d['id']         = f"D{len(self.deals)+1:04d}"
        d['created_at'] = datetime.now().isoformat()
        d['updated_at'] = datetime.now().isoformat()
        d['staff_code'] = clean_code(d.get('staff_code',''))
        self.deals.append(d)
        self._save_deals()
        return d['id']

    def update_stage(self, deal_id, new_stage, note, updated_by):
        for d in self.deals:
            if d['id'] == deal_id:
                old_stage = d['stage']
                d['stage']      = new_stage
                d['updated_at'] = datetime.now().isoformat()
                d['updated_by'] = updated_by
                if new_stage == 'Closed Won':
                    d['closed_date'] = str(datetime.now().date())
                self.add_activity({
                    'deal_id': deal_id, 'staff_code': d['staff_code'],
                    'staff_name': d['staff_name'], 'activity_type': 'Stage Change',
                    'note': f"Stage: {old_stage} → {new_stage}. {note}",
                    'outcome': new_stage,
                })
                break
        self._save_deals()

    def add_activity(self, a):
        a['id']          = f"A{len(self.activities)+1:04d}"
        a['recorded_at'] = datetime.now().isoformat()
        a['staff_code']  = clean_code(a.get('staff_code',''))
        self.activities.append(a)
        self._save_activities()
        return a['id']

    def get_deals(self, staff_code=None, stage=None, active_only=False):
        result = self.deals
        if staff_code: result = [d for d in result if d['staff_code'] == clean_code(staff_code)]
        if stage:      result = [d for d in result if d['stage'] == stage]
        if active_only:result = [d for d in result if d['stage'] in ACTIVE_STAGES]
        return result

    def get_activities(self, staff_code=None, deal_id=None, limit=50):
        result = self.activities
        if staff_code: result = [a for a in result if a['staff_code'] == clean_code(staff_code)]
        if deal_id:    result = [a for a in result if a.get('deal_id') == deal_id]
        return list(reversed(result))[:limit]

    def pipeline_value(self, deals):
        return sum(float(d.get('deal_value', 0)) for d in deals if d['stage'] in ACTIVE_STAGES)

    def weighted_pipeline(self, deals):
        weights = {
            'Lead':0.05,'Contacted':0.10,'Qualified':0.25,'Proposal':0.40,
            'Negotiation':0.60,'Compliance':0.80,'Closed Won':1.0,'Closed Lost':0.0
        }
        return sum(float(d.get('deal_value',0)) * weights.get(d['stage'],0) for d in deals)


# ─── EXECUTE MANAGER ─────────────────────────────────────────────────
class ExecuteManager:
    def __init__(self):
        self.init_file    = DATA_DIR / "execute_initiatives.json"
        self.ideas_file   = DATA_DIR / "execute_ideas.json"
        self.ws_file      = DATA_DIR / "execute_workstreams.json"
        self.impact_file  = DATA_DIR / "execute_impact.json"
        for f in [self.init_file, self.ideas_file, self.ws_file, self.impact_file]:
            if not f.exists(): f.write_text("[]" if f != self.ws_file else "{}")
        self.initiatives  = self._load_list(self.init_file)
        self.ideas        = self._load_list(self.ideas_file)
        self.workstreams  = self._load_dict(self.ws_file)
        self.impact_data  = self._load_list(self.impact_file)

    def _load_list(self, f):
        try:
            raw = f.read_text()
            d = json.loads(raw) if raw.strip() else []
            return d if isinstance(d, list) else []
        except: return []

    def _load_dict(self, f):
        try:
            raw = f.read_text()
            d = json.loads(raw) if raw.strip() else {}
            return d if isinstance(d, dict) else {}
        except: return {}

    def _save_initiatives(self):
        self.init_file.write_text(json.dumps(self.initiatives, indent=2))

    def _save_ideas(self):
        self.ideas_file.write_text(json.dumps(self.ideas, indent=2))

    def _save_workstreams(self):
        self.ws_file.write_text(json.dumps(self.workstreams, indent=2))

    def _save_impact(self):
        self.impact_file.write_text(json.dumps(self.impact_data, indent=2))

    # ── WORKSTREAM MANAGEMENT ─────────────────────────────────────
    def upsert_workstream(self, ws_id, name, sponsor, sub_workstreams=None):
        self.workstreams[ws_id] = {
            'name': name, 'sponsor': sponsor,
            'sub_workstreams': sub_workstreams or [],
            'updated_at': datetime.now().isoformat()
        }
        self._save_workstreams()

    # ── INITIATIVE CRUD ───────────────────────────────────────────
    def create_initiative(self, data):
        init_id = f"INI{len(self.initiatives)+1:04d}"
        init = {
            'id':               init_id,
            'name':             data['name'],
            'objective':        data['objective'],
            'category':         data['category'],
            'workstream':       data['workstream'],
            'sub_workstream':   data.get('sub_workstream',''),
            'io':               data['io'],           # Initiative Owner
            'io_backup':        data.get('io_backup',''),
            'gate':             'G0',
            'gate_history':     [{'gate':'G0','date': str(datetime.now().date()),
                                  'by': data['created_by'], 'note':'Created'}],
            'approvals':        {},   # gate_key → {approver: {status, date, note}}
            'business_case':    {},
            'milestones':       [],
            'milestone_confirmations': {},  # milestone_id → {owner: confirmed bool}
            'impact_kpis':      [],
            'monthly_impacts':  [],
            'created_by':       data['created_by'],
            'created_at':       datetime.now().isoformat(),
            'updated_at':       datetime.now().isoformat(),
            'status':           'Active',
            'priority_score':   None,
            'estimated_impact': data.get('estimated_impact', 0),
            'tags':             data.get('tags', []),
        }
        self.initiatives.append(init)
        self._save_initiatives()
        return init_id

    def get_initiative(self, init_id):
        return next((i for i in self.initiatives if i['id'] == init_id), None)

    def update_initiative(self, init_id, updates):
        for i in self.initiatives:
            if i['id'] == init_id:
                i.update(updates)
                i['updated_at'] = datetime.now().isoformat()
                break
        self._save_initiatives()

    # ── GATE TRANSITIONS ──────────────────────────────────────────
    def submit_for_gate(self, init_id, target_gate, submitted_by, note=''):
        init = self.get_initiative(init_id)
        if not init: return False, "Initiative not found"
        current = init['gate']
        transition_key = f"{current}→{target_gate}"
        # Mark as pending approval
        if 'pending_gate' not in init:
            init['pending_gate'] = {}
        init['pending_gate'] = {
            'target': target_gate, 'submitted_by': submitted_by,
            'submitted_at': datetime.now().isoformat(), 'note': note,
            'approvals': {r: {'status':'Pending','date':None,'note':''}
                          for r in GATE_APPROVERS.get(transition_key, [])}
        }
        init['updated_at'] = datetime.now().isoformat()
        self._save_initiatives()
        return True, f"Submitted to {target_gate} — awaiting approvals"

    def approve_gate(self, init_id, approver_role, approver_name, approved, note=''):
        init = self.get_initiative(init_id)
        if not init or 'pending_gate' not in init: return False, "No pending gate"
        pg = init['pending_gate']
        if approver_role not in pg['approvals']: return False, "You are not an approver for this gate"
        pg['approvals'][approver_role] = {
            'status': 'Approved' if approved else 'Rejected',
            'by': approver_name, 'date': str(datetime.now().date()), 'note': note
        }
        # Check if all approved
        statuses = [v['status'] for v in pg['approvals'].values()]
        if all(s == 'Approved' for s in statuses):
            # Advance gate
            new_gate = pg['target']
            init['gate'] = new_gate
            init['gate_history'].append({
                'gate': new_gate, 'date': str(datetime.now().date()),
                'by': approver_name, 'note': f"All approvers confirmed. {note}"
            })
            init['approvals'][f"{init['gate_history'][-2]['gate']}→{new_gate}"] = pg['approvals']
            del init['pending_gate']
        elif 'Rejected' in statuses:
            init['gate_history'].append({
                'gate': init['gate'], 'date': str(datetime.now().date()),
                'by': approver_name, 'note': f"REJECTED at {pg['target']}. {note}"
            })
            del init['pending_gate']
        init['updated_at'] = datetime.now().isoformat()
        self._save_initiatives()
        return True, "Approval recorded"

    # ── BUSINESS CASE ─────────────────────────────────────────────
    def save_business_case(self, init_id, bc):
        init = self.get_initiative(init_id)
        if not init: return
        init['business_case'] = bc
        init['priority_score']   = bc.get('priority_score')
        init['estimated_impact'] = bc.get('estimated_impact', 0)
        init['impact_kpis']      = bc.get('impact_kpis', [])
        init['updated_at'] = datetime.now().isoformat()
        self._save_initiatives()

    # ── MILESTONES ────────────────────────────────────────────────
    def add_milestone(self, init_id, milestone):
        init = self.get_initiative(init_id)
        if not init: return None
        ms_id = f"MS{len(init['milestones'])+1:03d}"
        ms = {
            'id':              ms_id,
            'name':            milestone['name'],
            'type':            milestone['type'],
            'owner':           milestone['owner'],
            'co_owners':       milestone.get('co_owners', []),
            'due_date':        milestone['due_date'],
            'start_date':      milestone.get('start_date', str(datetime.now().date())),
            'description':     milestone.get('description', ''),
            'dependencies':    milestone.get('dependencies', []),  # list of ms_ids
            'status':          'Not Started',
            'completion_date': None,
            'confirmed':       False,
            'confirmed_at':    None,
            'notes':           [],
            'delay_reason':    '',
            'blockers':        [],   # list of {blocker, raised_by, raised_at, resolved}
            'escalation_level': 0,   # 0=none 1=IO 2=lead 3=sponsor
            'escalation_history': [],
            'last_update_by':  '',
            'last_update_at':  '',
        }
        init['milestones'].append(ms)
        init['updated_at'] = datetime.now().isoformat()
        self._save_initiatives()
        return ms_id

    def confirm_milestone(self, init_id, ms_id, owner_name):
        init = self.get_initiative(init_id)
        if not init: return
        for ms in init['milestones']:
            if ms['id'] == ms_id:
                ms['confirmed']   = True
                ms['confirmed_at'] = datetime.now().isoformat()
                break
        init['updated_at'] = datetime.now().isoformat()
        self._save_initiatives()

    def update_milestone_status(self, init_id, ms_id, status, note='',
                                 delay_reason='', delay_category='',
                                 updated_by='', started=None):
        """
        started: True/False/None — whether the milestone has physically started.
        delay_category: one of DELAY_CATEGORIES — drives escalation tier.
        """
        init = self.get_initiative(init_id)
        if not init: return
        for ms in init['milestones']:
            if ms['id'] == ms_id:
                prev_status           = ms.get('status')
                ms['status']          = status
                ms['last_update_by']  = updated_by
                ms['last_update_at']  = datetime.now().isoformat()

                # Started flag
                if started is True and not ms.get('actual_start_date'):
                    ms['actual_start_date'] = str(datetime.now().date())
                    ms['has_started'] = True
                elif started is False:
                    ms['has_started'] = False

                if status == 'Complete':
                    ms['completion_date'] = str(datetime.now().date())
                    ms['delay_reason']    = ''
                    ms['delay_category']  = ''
                if status == 'Delayed':
                    if delay_reason:   ms['delay_reason']   = delay_reason
                    if delay_category: ms['delay_category'] = delay_category

                if note:
                    ms['notes'].append({
                        'date': str(datetime.now().date()),
                        'note': note, 'by': updated_by,
                        'status_was': prev_status, 'status_now': status,
                    })

                # Recompute escalation
                ms['escalation_level'] = ExecuteManager._escalation_level(ms)

                # Log to escalation history if level changed
                new_esc = ms['escalation_level']
                if new_esc > 0:
                    prev_esc = ms.get('escalation_history',[-1])
                    prev_level = prev_esc[-1]['level'] if prev_esc else 0
                    if new_esc != prev_level:
                        if 'escalation_history' not in ms: ms['escalation_history'] = []
                        ms['escalation_history'].append({
                            'level': new_esc,
                            'label': ESC_CONFIG.get(new_esc,{}).get('label',''),
                            'reason': f"Status: {status}" + (f" | {delay_category}" if delay_category else ""),
                            'date': str(datetime.now().date()),
                            'by': updated_by,
                        })
                break
        init['updated_at'] = datetime.now().isoformat()
        self._save_initiatives()

    def raise_blocker(self, init_id, ms_id, blocker_text, raised_by):
        init = self.get_initiative(init_id)
        if not init: return
        for ms in init['milestones']:
            if ms['id'] == ms_id:
                if 'blockers' not in ms: ms['blockers'] = []
                ms['blockers'].append({
                    'blocker':    blocker_text,
                    'raised_by':  raised_by,
                    'raised_at':  datetime.now().isoformat(),
                    'resolved':   False,
                    'resolved_at': None,
                    'resolution': '',
                })
                ms['escalation_level'] = max(ms.get('escalation_level',0), 2)
                if 'escalation_history' not in ms: ms['escalation_history'] = []
                ms['escalation_history'].append({
                    'level': 2, 'reason': f'Blocker raised: {blocker_text}',
                    'date': str(datetime.now().date()), 'by': raised_by,
                })
                break
        init['updated_at'] = datetime.now().isoformat()
        self._save_initiatives()

    def resolve_blocker(self, init_id, ms_id, blocker_idx, resolution, resolved_by):
        init = self.get_initiative(init_id)
        if not init: return
        for ms in init['milestones']:
            if ms['id'] == ms_id and blocker_idx < len(ms.get('blockers',[])):
                ms['blockers'][blocker_idx].update({
                    'resolved': True,
                    'resolved_at': datetime.now().isoformat(),
                    'resolution': resolution,
                })
                break
        init['updated_at'] = datetime.now().isoformat()
        self._save_initiatives()

    @staticmethod
    def _escalation_level(ms):
        """
        Banking escalation — tight timelines:
          0 On track        : all good
          1 Due soon        : due ≤ 2 days (email notification)
          2 Overdue / IO    : 1-2 days overdue
          3 Lead escalated  : 3-7 days overdue OR any open blocker
          4 Sponsor critical: >7 days overdue OR structural/regulatory delay category
          5 Not started     : start_date passed, status still Not Started
        """
        if ms.get('status') == 'Complete': return 0

        today = date.today()

        # Not started alert — start date has passed
        if ms.get('status') == 'Not Started' and ms.get('start_date'):
            try:
                start = date.fromisoformat(ms['start_date'])
                if start < today: return 5
            except: pass

        # Structural / regulatory delay → immediate Sponsor escalation
        delay_cat = ms.get('delay_category', '')
        if delay_cat in STRUCTURAL_CATEGORIES and ms.get('status') == 'Delayed':
            return 4

        # Open blockers → Lead escalation (at minimum)
        has_blocker = ms.get('blockers') and any(not b['resolved'] for b in ms['blockers'])

        try:
            due = date.fromisoformat(ms['due_date'])
            days_overdue = (today - due).days
            days_to_due  = (due - today).days
        except:
            return 3 if has_blocker else 0

        if days_overdue > 7:  return 4  # Critical — Sponsor
        if days_overdue >= 3: return 3  # Lead escalation
        if days_overdue >= 1: return 2  # IO notified immediately
        if has_blocker:       return 3  # Blocker regardless of due date
        if days_to_due <= 2:  return 1  # Due soon — email alert
        return 0

    @staticmethod
    def _needs_start_alert(ms):
        """True if milestone should have started but hasn't."""
        if ms.get('status') != 'Not Started': return False
        if not ms.get('start_date'): return False
        try:
            start = date.fromisoformat(ms['start_date'])
            return start <= date.today()
        except: return False

    def all_milestones_confirmed(self, init_id):
        init = self.get_initiative(init_id)
        if not init or not init['milestones']: return False
        return all(ms['confirmed'] for ms in init['milestones'])

    def money_step_complete(self, init_id):
        init = self.get_initiative(init_id)
        if not init: return False
        money_steps = [ms for ms in init['milestones'] if ms['type'] == 'Money Step']
        return money_steps and all(ms['status'] == 'Complete' for ms in money_steps)

    # ── IMPACT TRACKING ───────────────────────────────────────────
    def record_impact(self, init_id, month, kpi_name, target, actual, note=''):
        entry = {
            'initiative_id': init_id,
            'month':   month,
            'kpi':     kpi_name,
            'target':  target,
            'actual':  actual,
            'note':    note,
            'recorded_at': datetime.now().isoformat(),
        }
        self.impact_data.append(entry)
        self._save_impact()

    def get_impact(self, init_id):
        return [e for e in self.impact_data if e['initiative_id'] == init_id]

    # ── IDEAS ─────────────────────────────────────────────────────
    def submit_idea(self, data):
        idea_id = f"IDEA{len(self.ideas)+1:04d}"
        idea = {
            'id':          idea_id,
            'title':       data['title'],
            'description': data['description'],
            'submitted_by': data['submitted_by'],
            'workstream':  data.get('workstream',''),
            'status':      'Submitted',   # Submitted / Under Review / Adopted / Declined
            'votes':       [],
            'comments':    [],
            'created_at':  datetime.now().isoformat(),
            'adopted_as':  None,  # initiative ID if adopted
        }
        self.ideas.append(idea)
        self._save_ideas()
        return idea_id

    def vote_idea(self, idea_id, voter):
        for idea in self.ideas:
            if idea['id'] == idea_id:
                if voter not in idea['votes']:
                    idea['votes'].append(voter)
                    self._save_ideas()
                break

    # ── QUERIES ───────────────────────────────────────────────────
    def get_initiatives(self, workstream=None, gate=None, io=None, status='Active'):
        result = [i for i in self.initiatives if i.get('status','Active') == status or status == 'All']
        if workstream: result = [i for i in result if i.get('workstream') == workstream]
        if gate:       result = [i for i in result if i.get('gate') == gate]
        if io:         result = [i for i in result if i.get('io') == io or i.get('io_backup') == io]
        return result

    def gate_counts(self):
        counts = {g: 0 for g in GATE_ORDER}
        for i in self.initiatives:
            g = i.get('gate','G0')
            if g in counts: counts[g] += 1
        return counts

    def get_my_actions(self, username, role):
        """Items requiring action from this user."""
        actions = []
        role_lower = role.lower()
        for init in self.initiatives:
            pg = init.get('pending_gate')
            if pg:
                role_map = {
                    'workstream_lead': ['workstream lead','head of','branch manager','department head'],
                    'sponsor':         ['director','sponsor'],
                    'finance':         ['finance'],
                }
                for approver_role, role_keywords in role_map.items():
                    if (approver_role in pg.get('approvals',{}) and
                        pg['approvals'][approver_role]['status'] == 'Pending' and
                        any(kw in role_lower for kw in role_keywords)):
                        actions.append({
                            'type':         'gate_approval',
                            'init_id':       init['id'],
                            'name':         init['name'],
                            'gate':         pg['target'],
                            'approver_role': approver_role,
                            'workstream':   init.get('workstream',''),
                        })
            for ms in init.get('milestones',[]):
                is_owner = (ms['owner'] == username or username in ms.get('co_owners',[]))
                if not is_owner: continue
                # Confirmation needed
                if not ms['confirmed']:
                    actions.append({
                        'type': 'milestone_confirm', 'init_id': init['id'],
                        'ms_id': ms['id'], 'name': init['name'],
                        'ms_name': ms['name'], 'due_date': ms.get('due_date',''),
                        'workstream': init.get('workstream',''),
                    })
                # Due soon alerts
                elif ms['status'] not in ('Complete',):
                    esc = ExecuteManager._escalation_level(ms)
                    if esc > 0:
                        try:
                            due = date.fromisoformat(ms['due_date'])
                            overdue = (date.today() - due).days
                        except: overdue = 0
                        actions.append({
                            'type':       'milestone_overdue' if overdue > 0 else 'milestone_due_soon',
                            'init_id':     init['id'], 'ms_id': ms['id'],
                            'name':       init['name'], 'ms_name': ms['name'],
                            'due_date':   ms.get('due_date',''),
                            'overdue_days': overdue,
                            'esc_level':  esc,
                            'workstream': init.get('workstream',''),
                            'has_blocker': any(not b['resolved'] for b in ms.get('blockers',[])),
                        })
        return actions

    def get_all_milestones_for_owner(self, username):
        """Return every milestone where username is owner or co-owner, with initiative context."""
        result = []
        for init in self.initiatives:
            for ms in init.get('milestones', []):
                if ms['owner'] == username or username in ms.get('co_owners', []):
                    esc = ExecuteManager._escalation_level(ms)
                    try:
                        due = date.fromisoformat(ms['due_date'])
                        days_diff = (due - date.today()).days
                    except:
                        days_diff = 999
                    try:
                        days_to_start = (date.fromisoformat(ms.get('start_date','9999-12-31')) - date.today()).days
                    except: days_to_start = 999
                    needs_start = ExecuteManager._needs_start_alert(ms)
                    entry = dict(ms)   # explicit copy — avoids unhashable type warning
                    entry.update({
                        'initiative_id':    init['id'],
                        'initiative_name':  init['name'],
                        'workstream':       init.get('workstream',''),
                        'sub_workstream':   init.get('sub_workstream',''),
                        'gate':             init.get('gate',''),
                        'io':               init.get('io',''),
                        'escalation_level': esc,
                        'days_to_due':      days_diff,
                        'days_to_start':    days_to_start,
                        'needs_start_alert': needs_start,
                        'is_primary_owner': ms['owner'] == username,
                    })
                    result.append(entry)
        result.sort(key=lambda x: (0 if int(x.get('escalation_level',0)) > 0 else 1, int(x.get('days_to_due',999))))
        return result

    def get_escalation_dashboard(self, scope_initiatives=None):
        """All milestones at risk — grouped by escalation level (banking timelines)."""
        inits = scope_initiatives or self.initiatives
        buckets = {4: [], 3: [], 2: [], 1: [], 5: []}  # level → list
        for init in inits:
            for ms in init.get('milestones',[]):
                if ms.get('status') == 'Complete': continue
                esc = ExecuteManager._escalation_level(ms)
                if esc > 0:
                    try:
                        due = date.fromisoformat(ms['due_date'])
                        overdue = (date.today() - due).days
                    except: overdue = 0
                    try:
                        days_to_start = (date.fromisoformat(ms.get('start_date','9999-12-31')) - date.today()).days
                    except: days_to_start = 999
                    item = dict(ms)   # explicit copy — avoids unhashable type warning
                    item.update({
                        'initiative_id':   init['id'],
                        'initiative_name': init['name'],
                        'workstream':      init.get('workstream',''),
                        'io':              init.get('io',''),
                        'gate':            init.get('gate',''),
                        'overdue_days':    max(0, overdue),
                        'days_to_due':     (date.fromisoformat(ms['due_date']) - date.today()).days
                                           if ms.get('due_date') else 0,
                        'days_to_start':   days_to_start,
                        'needs_start_alert': ExecuteManager._needs_start_alert(ms),
                    })
                    if esc in buckets:
                        buckets[esc].append(item)
                    else:
                        buckets[max(buckets.keys())].append(item)
        for level in buckets:
            buckets[level].sort(key=lambda x: -x.get('overdue_days', 0))
        return buckets


# ─── PRODUCT MANAGER ─────────────────────────────────────────────────
class ProductManager:
    """
    Banking product registry — tracks products across their full lifecycle.
    Linked to KPIs (Perform), pipeline deals (RI), and initiatives (Execute).
    """
    def __init__(self):
        self.file = DATA_DIR / "product_registry.json"
        if not self.file.exists(): self.file.write_text("[]")
        try:
            raw = self.file.read_text()
            self.products = json.loads(raw) if raw.strip() else []
            if not isinstance(self.products, list): self.products = []
        except:
            self.products = []

    def save(self):
        self.file.write_text(json.dumps(self.products, indent=2))

    def add_product(self, data: dict) -> str:
        prod_id = f"PRD{len(self.products)+1:04d}"
        product = {
            "id":               prod_id,
            "name":             data["name"],
            "category":         data["category"],         # Assets/Liabilities/NFI/Channels
            "sub_category":     data.get("sub_category",""),
            "product_type":     data.get("product_type",""),
            "lifecycle_stage":  data.get("lifecycle_stage","Active"),
            "health":           data.get("health","On track"),
            "owner":            data.get("owner",""),     # username
            "sponsor":          data.get("sponsor",""),   # Director
            "description":      data.get("description",""),
            "launch_date":      data.get("launch_date",""),
            "review_date":      data.get("review_date",""),
            "linked_kpis":      data.get("linked_kpis",[]),
            "linked_initiatives": data.get("linked_initiatives",[]),
            "target_segment":   data.get("target_segment",""),  # Retail/SME/Corporate
            "channels":         data.get("channels",[]),
            "annual_target":    data.get("annual_target",0),
            "ytd_actual":       data.get("ytd_actual",0),
            "customer_count":   data.get("customer_count",0),
            "notes":            [],
            "stage_history":    [{"stage": data.get("lifecycle_stage","Active"),
                                  "date": str(datetime.now().date()),
                                  "by": data.get("created_by","")}],
            "created_by":       data.get("created_by",""),
            "created_at":       datetime.now().isoformat(),
            "updated_at":       datetime.now().isoformat(),
            "active":           True,
        }
        self.products.append(product)
        self.save()
        return prod_id

    def update_product(self, prod_id: str, updates: dict, updated_by: str = ""):
        for p in self.products:
            if p["id"] == prod_id:
                old_stage = p.get("lifecycle_stage")
                p.update(updates)
                p["updated_at"] = datetime.now().isoformat()
                # Log stage changes
                if "lifecycle_stage" in updates and updates["lifecycle_stage"] != old_stage:
                    if "stage_history" not in p: p["stage_history"] = []
                    p["stage_history"].append({
                        "stage": updates["lifecycle_stage"],
                        "date": str(datetime.now().date()),
                        "by": updated_by,
                    })
                break
        self.save()

    def get_products(self, category: str = None, stage: str = None,
                     health: str = None, active_only: bool = True):
        result = [p for p in self.products if not active_only or p.get("active", True)]
        if category: result = [p for p in result if p.get("category") == category]
        if stage:    result = [p for p in result if p.get("lifecycle_stage") == stage]
        if health:   result = [p for p in result if p.get("health") == health]
        return result

    def get_product(self, prod_id: str):
        return next((p for p in self.products if p["id"] == prod_id), None)

    def lifecycle_summary(self):
        """Count products per stage for funnel view."""
        counts: dict = {}
        for p in self.products:
            if not p.get("active", True): continue
            s = p.get("lifecycle_stage","Active")
            counts[s] = counts.get(s, 0) + 1
        return counts

    def category_summary(self):
        """Count and aggregate per category."""
        summary: dict = {}
        for cat in PRODUCT_CATEGORIES:
            prods = self.get_products(category=cat)
            summary[cat] = {
                "count":    len(prods),
                "active":   sum(1 for p in prods if p.get("lifecycle_stage") in ("Active","Growth","Mature","Optimising")),
                "at_risk":  sum(1 for p in prods if p.get("health") == "At risk"),
                "in_pilot": sum(1 for p in prods if p.get("lifecycle_stage") == "Pilot"),
                "sunset":   sum(1 for p in prods if p.get("lifecycle_stage") in ("Sunset","Decommissioned")),
            }
        return summary

    def link_to_initiative(self, prod_id: str, init_id: str):
        for p in self.products:
            if p["id"] == prod_id:
                if init_id not in p.get("linked_initiatives", []):
                    if "linked_initiatives" not in p: p["linked_initiatives"] = []
                    p["linked_initiatives"].append(init_id)
                break
        self.save()

    def add_note(self, prod_id: str, note: str, author: str):
        for p in self.products:
            if p["id"] == prod_id:
                if "notes" not in p: p["notes"] = []
                p["notes"].append({"note": note, "by": author,
                                    "date": str(datetime.now().date())})
                break
        self.save()


# ─── REVENUE INTELLIGENCE PIPELINE MANAGER ──────────────────────────
class RIPipelineManager:
    """
    Manages the 4-category revenue pipeline:
    Deposits · Loans · NFI · New Customers
    Each deal is tagged to a category and links back to a KPI.
    """
    def __init__(self):
        self.file = DATA_DIR / "ri_pipeline.json"
        if not self.file.exists(): self.file.write_text("[]")
        try:
            raw = self.file.read_text()
            self.deals = json.loads(raw) if raw.strip() else []
            if not isinstance(self.deals, list): self.deals = []
        except:
            self.deals = []

    def save(self):
        self.file.write_text(json.dumps(self.deals, indent=2))

    def add_deal(self, d):
        d['id']         = f"RI{len(self.deals)+1:05d}"
        d['created_at'] = datetime.now().isoformat()
        d['updated_at'] = datetime.now().isoformat()
        d['staff_code'] = clean_code(d.get('staff_code',''))
        d['history']    = [{'stage': d['stage'], 'date': str(datetime.now().date()),
                            'note': d.get('notes','')}]
        self.deals.append(d)
        self.save()
        return d['id']

    def update_stage(self, deal_id, new_stage, note, updated_by):
        for d in self.deals:
            if d['id'] == deal_id:
                d['stage']      = new_stage
                d['updated_at'] = datetime.now().isoformat()
                d['updated_by'] = updated_by
                if not isinstance(d.get('history'), list): d['history'] = []
                d['history'].append({'stage': new_stage, 'date': str(datetime.now().date()), 'note': note})
                if new_stage in [RI_CATEGORIES[d['category']]['closed_won']]:
                    d['closed_date'] = str(datetime.now().date())
                break
        self.save()

    def get_deals(self, staff_code=None, category=None, team_names=None, active_only=False):
        result = self.deals
        if staff_code:   result = [d for d in result if d.get('staff_code') == clean_code(staff_code)]
        if team_names:   result = [d for d in result if d.get('staff_name') in team_names]
        if category:     result = [d for d in result if d.get('category') == category]
        if active_only:
            result = [d for d in result if d.get('stage') not in
                      [RI_CATEGORIES.get(d.get('category',{}) or 'Loans',{}).get('closed_lost','Lost'),
                       RI_CATEGORIES.get(d.get('category',{}) or 'Loans',{}).get('closed_won','')]]
        return result

    def weighted_value(self, deals):
        total = 0
        for d in deals:
            cat  = d.get('category','Loans')
            cfg  = RI_CATEGORIES.get(cat, {})
            wts  = cfg.get('stage_weights', {})
            val  = float(d.get('deal_value', 0))
            wt   = wts.get(d.get('stage',''), 0)
            total += val * wt
        return total

    def pipeline_value(self, deals):
        """Raw total of active deals (not weighted)."""
        closed_lost_stages = set()
        for cat, cfg in RI_CATEGORIES.items():
            closed_lost_stages.add(cfg['closed_lost'])
        return sum(float(d.get('deal_value', 0)) for d in deals
                   if d.get('stage') not in closed_lost_stages)

    def won_value(self, deals):
        total = 0
        for d in deals:
            cat = d.get('category','Loans')
            cw  = RI_CATEGORIES.get(cat,{}).get('closed_won','')
            if d.get('stage') == cw:
                total += float(d.get('deal_value', 0))
        return total

    def category_summary(self, deals, kpi_actuals, kpi_targets):
        """
        For each RI category return:
        ytd_actual, annual_target, pipeline_raw, pipeline_weighted, won,
        gap_to_target, forecast_eoy, coverage_pct, conversion_needed
        """
        summary = {}
        for cat, cfg in RI_CATEGORIES.items():
            cat_deals   = [d for d in deals if d.get('category') == cat]
            won_stage   = cfg['closed_won']
            lost_stage  = cfg['closed_lost']
            active_d    = [d for d in cat_deals if d.get('stage') not in (won_stage, lost_stage)]
            won_d       = [d for d in cat_deals if d.get('stage') == won_stage]

            ytd_act  = kpi_actuals.get(cat, 0)
            ann_tgt  = kpi_targets.get(cat, 0)
            pip_raw  = self.pipeline_value(active_d)
            pip_wt   = self.weighted_value(active_d)
            won_val  = self.won_value(won_d)

            # Forecast: ytd_actual / months_elapsed * 12  +  weighted pipeline
            run_rate = (ytd_act / months_elapsed()) * 12 if ytd_act > 0 else 0
            forecast = run_rate + pip_wt
            gap      = max(0, ann_tgt - ytd_act)
            coverage = (pip_wt / gap * 100) if gap > 0 else 100

            # Conversion needed: if pipeline_raw > 0, what % must convert to close gap
            conv_needed = (gap / pip_raw * 100) if pip_raw > 0 else None

            # Current conversion rate (won / (won + lost) deals)
            lost_d = [d for d in cat_deals if d.get('stage') == lost_stage]
            total_closed = len(won_d) + len(lost_d)
            curr_conv = (len(won_d) / total_closed * 100) if total_closed > 0 else None

            summary[cat] = {
                'ytd_actual':     ytd_act,
                'annual_target':  ann_tgt,
                'pipeline_raw':   pip_raw,
                'pipeline_wtd':   pip_wt,
                'won_ytd':        won_val,
                'gap_to_target':  gap,
                'forecast_eoy':   forecast,
                'coverage_pct':   coverage,
                'conv_needed':    conv_needed,
                'curr_conv':      curr_conv,
                'active_deals':   len(active_d),
                'won_deals':      len(won_d),
                'unit':           cfg['unit'],
            }
        return summary


# ─── AUDIT LOG ───────────────────────────────────────────────────────
def audit_log(action, username, detail=""):
    log_file = DATA_DIR / "audit_log.json"
    try:
        raw = log_file.read_text()
        log = json.loads(raw) if raw.strip() else []
        if not isinstance(log, list): log = []
    except:
        log = []
    log.append({"time": datetime.now().isoformat(), "user": username, "action": action, "detail": detail})
    log_file.write_text(json.dumps(log[-500:], indent=2))

# ─── USER MANAGER ────────────────────────────────────────────────────
class UserManager:
    def __init__(self):
        self.users_file = DATA_DIR / "users.json"
        self.users = self._load()

    def _load(self):
        try:
            raw = self.users_file.read_text()
            users = json.loads(raw) if raw.strip() else {}
            if not users: raise ValueError("empty")
            if 'admin' in users:
                users['admin'].update({'can_view_all': True, 'role': 'Admin', 'active': True})
            self._save(users)
            return users
        except:
            return self._defaults()

    def _defaults(self):
        u = {
            "admin": {
                "password": hashlib.sha256("admin123".encode()).hexdigest(),
                "full_name": "System Admin", "role": "Admin", "department": "All",
                "can_view_all": True, "managed_roles": [], "managed_units": [],
                "managed_staff_codes": [], "staff_code": "ADMIN001",
                "email": "admin@bank.com", "active": True,
            },
            "manager1": {
                "password": hashlib.sha256("manager123".encode()).hexdigest(),
                "full_name": "John Manager", "role": "Manager", "department": "Retail Banking",
                "can_view_all": False, "managed_roles": [], "managed_units": ["Retail Banking"],
                "managed_staff_codes": [], "staff_code": "MGR001",
                "email": "manager@bank.com", "active": True,
            },
            "staff1": {
                "password": hashlib.sha256("staff123".encode()).hexdigest(),
                "full_name": "Jane Staff", "role": "Staff", "department": "Retail Banking",
                "can_view_all": False, "managed_roles": [], "managed_units": [],
                "managed_staff_codes": [], "staff_code": "STF001",
                "email": "staff1@bank.com", "active": True,
            },
        }
        self._save(u)
        return u

    def _save(self, u=None):
        self.users_file.write_text(json.dumps(u or self.users, indent=2))

    def save(self):
        """Alias for save_users — keeps all call sites consistent."""
        self.save_users()

    def save_users(self):
        self._save(self.users)

    def hash_pw(self, pw):
        return hashlib.sha256(pw.encode()).hexdigest()

    def authenticate(self, username, password):
        u = self.users.get(username)
        if u and u.get('active') and u['password'] == self.hash_pw(password):
            return True, u
        return False, None

    def change_password(self, username, new_password):
        self.users[username]['password'] = self.hash_pw(new_password)
        self.users[username]['must_change_password'] = False
        self.save_users()

    def get_managed_staff_codes(self, username):
        u = self.users.get(username, {})
        role = str(u.get('role','')).lower()
        if role in ('admin','director') or u.get('can_view_all'):
            return "all"
        codes = u.get('managed_staff_codes', [])
        if codes: return [str(c).strip() for c in codes if c]
        sc = u.get('staff_code','')
        return [sc] if sc else []

    def add_user(self, username, password, full_name, email="",
                 role="Staff", unit="", staff_code="",
                 can_view_all=False, can_execute=False, is_admin=False):
        """Create a new user account."""
        self.users[username] = {
            "password":    self.hash_pw(password),
            "full_name":   full_name,
            "email":       email,
            "role":        role,
            "unit":        unit,
            "department":  unit,
            "staff_code":  str(staff_code),
            "can_view_all":can_view_all,
            "can_execute": can_execute,
            "is_admin":    is_admin,
            "active":      True,
            "managed_roles": [],
            "managed_units": [unit] if unit else [],
            "managed_staff_codes": [str(staff_code)] if staff_code else [],
            "must_change_password": False,
        }
        self.save_users()
        return self.users[username]

    def filter_data(self, user_data, staff_df):
        role = str(user_data.get('role','')).strip().lower()
        if user_data.get('can_view_all') or role in ('admin','director'):
            return staff_df, f"Full access — {len(staff_df)} staff"

        codes = [str(c).strip() for c in user_data.get('managed_staff_codes',[]) if c]
        roles = user_data.get('managed_roles', [])
        units = user_data.get('managed_units', [])
        sc    = user_data.get('staff_code','')

        mask = pd.Series([False]*len(staff_df), index=staff_df.index)
        if codes and 'Staff Code' in staff_df.columns:
            mask |= staff_df['Staff Code'].astype(str).isin(codes)
        if roles and 'Role' in staff_df.columns:
            mask |= staff_df['Role'].isin(roles)
        if units and 'Unit' in staff_df.columns:
            mask |= staff_df['Unit'].isin(units)
        if units and 'Category' in staff_df.columns:
            mask |= staff_df['Category'].isin(units)
        if sc and 'Staff Code' in staff_df.columns:
            mask |= staff_df['Staff Code'].astype(str) == str(sc)

        filtered = staff_df[mask]
        if len(filtered): return filtered, f"Filtered — {len(filtered)} staff"
        return pd.DataFrame(), "No matching staff — check permissions in Admin panel"

# ─── ADMIN PANEL ─────────────────────────────────────────────────────
