"""pages/33_statement_analyzer.py — AI-Powered Bank Statement Analyzer.
Paste any bank statement; Claude extracts income, expenses, obligations, risk
flags, affordability, and generates a full credit narrative in seconds.
Configurable DSR limits, risk keywords, and product rules via Admin.
"""
import streamlit as st
from utils.db import db as a2z_db
import json
import re
import requests
from pathlib import Path
from datetime import date
from pages._shared import load_shared_state
from utils.core import audit_log
from pages._access import require_access

require_access("statement_analyzer")

def _bsc_trigger(username: str, kpi: str = ""):
    """Non-blocking BSC update — called after every save action."""
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass
DATA  = Path(__file__).parent.parent / "data"
today = date.today()

um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)

@st.cache_data(ttl=30, show_spinner=False)
def _sa_cfg():
    p = DATA / "proposition_config.json"
    if not p.exists(): return {}
    return a2z_db.load_json(p).get("statement_analyzer_config",{})

cfg          = _sa_cfg()
DSR_LIMIT    = cfg.get("dsr_limit", 40)
MIN_MONTHS   = cfg.get("min_months", 3)
LIVING_PCT   = cfg.get("living_expense_pct", 30)
MONTHLY_RATE = cfg.get("interest_rate_monthly", 1.5)
RISK_KEYWORDS= cfg.get("risk_keywords",[
    "bet","betika","sportpesa","mozzart","odibets","1xbet","casino",
    "return item","refer to drawer","r/d","unpaid","dishonoured","bounce",
    "fuliza","okoa","tala","branch loan","haraka","timiza","loop",
    "kopa","zidisha","fadhili","mshwari","kcb mpesa","okolea",
])

# ── Sample statement for testing ────────────────────────────────────
SAMPLE_STMT = """EQUITY BANK KENYA LIMITED
Account Statement
Account Name: GRACE WANJIKU MUTHONI
Account Number: 0190451237890
Period: 01/07/2025 - 31/12/2025

Date        Description                             Debit        Credit       Balance
01/07/2025  Opening Balance                                                   32,450.00
03/07/2025  SALARY CR-NAIROBI COUNTY GOVT                        185,000.00  217,450.00
05/07/2025  RENT WESTGATE APTS-GRACE W               55,000.00               162,450.00
07/07/2025  ATM WITHDRAWAL CBD BRANCH                20,000.00               142,450.00
10/07/2025  EQUITY BANK LOAN REPAYMENT               18,500.00               123,950.00
12/07/2025  KPLC TOKEN PURCHASE                       3,200.00               120,750.00
14/07/2025  NAIVAS SUPERMARKET LAVINGTON              8,700.00               112,050.00
20/07/2025  UBER KENYA LTD                            1,500.00               110,550.00
31/07/2025  BANK CHARGES                              1,200.00               109,350.00
03/08/2025  SALARY CR-NAIROBI COUNTY GOVT                        185,000.00  294,350.00
05/08/2025  RENT WESTGATE APTS-GRACE W               55,000.00               239,350.00
10/08/2025  EQUITY BANK LOAN REPAYMENT               18,500.00               220,850.00
12/08/2025  MPESA FULIZA REPAYMENT                    2,500.00               218,350.00
20/08/2025  SANLAM INSURANCE PREMIUM                  3,500.00               214,850.00
31/08/2025  BANK CHARGES                              1,200.00               213,650.00
03/09/2025  SALARY CR-NAIROBI COUNTY GOVT                        185,000.00  398,650.00
05/09/2025  RENT WESTGATE APTS-GRACE W               55,000.00               343,650.00
10/09/2025  EQUITY BANK LOAN REPAYMENT               18,500.00               325,150.00
12/09/2025  BETIKA DEPOSIT                            3,000.00               322,150.00
20/09/2025  JUBILEE INSURANCE MEDICAL                 8,000.00               314,150.00
31/09/2025  BANK CHARGES                              1,200.00               312,950.00
03/10/2025  SALARY CR-NAIROBI COUNTY GOVT                        185,000.00  497,950.00
05/10/2025  RENT WESTGATE APTS-GRACE W               55,000.00               442,950.00
10/10/2025  EQUITY BANK LOAN REPAYMENT               18,500.00               424,450.00
22/10/2025  RETURN ITEM-STANDING ORDER HELB           8,000.00               416,450.00
31/10/2025  BANK CHARGES                              1,200.00               415,250.00
03/11/2025  SALARY CR-NAIROBI COUNTY GOVT                        185,000.00  600,250.00
05/11/2025  RENT WESTGATE APTS-GRACE W               55,000.00               545,250.00
10/11/2025  EQUITY BANK LOAN REPAYMENT               18,500.00               526,750.00
25/11/2025  SPORTPESA WAGER                           5,000.00               521,750.00
31/11/2025  BANK CHARGES                              1,200.00               520,550.00
03/12/2025  SALARY CR-NAIROBI COUNTY GOVT                        185,000.00  705,550.00
05/12/2025  RENT WESTGATE APTS-GRACE W               55,000.00               650,550.00
10/12/2025  EQUITY BANK LOAN REPAYMENT               18,500.00               632,050.00
12/12/2025  MPESA FULIZA REPAYMENT                    1,800.00               630,250.00
25/12/2025  CHRISTMAS WITHDRAWAL                     50,000.00               580,250.00
31/12/2025  Closing Balance                                                  580,250.00
End of Statement"""

# ── Page header ──────────────────────────────────────────────────────

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🧾 Statement Analyzer</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "AI-powered · Bank statements · Credit analysis</span></div>",
    unsafe_allow_html=True)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🧾 Statement Analyzer</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "AI-powered · Any bank format · Instant credit analysis</span></div>",
    unsafe_allow_html=True)

st.markdown(
    f"<div style='background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;"
    f"padding:8px 16px;font-size:12px;margin-bottom:10px'>"
    f"Paste the statement text (copy from PDF or portal) → click Analyse → get income, expenses, "
    f"obligations, risk flags, DSR ({DSR_LIMIT}% limit), affordability and a credit narrative. "
    f"Analysis saves to the linked loan application. "
    f"Configured: DSR {DSR_LIMIT}% · Living est. {LIVING_PCT}% · Rate {MONTHLY_RATE}%/month</div>",
    unsafe_allow_html=True)

# ── Input form ───────────────────────────────────────────────────────
c1, c2 = st.columns([3,1])
with c1:
    client_name    = st.text_input("Customer name *", key="sa_cn", placeholder="e.g. John Otieno Kamau")
    client_cif     = st.text_input("CIF / Account number", key="sa_cif", placeholder="Optional — links to CBS")
with c2:
    product = st.selectbox("Loan product", [
        "Personal Loan","Business Loan","Mortgage / Home Loan","Salary Advance",
        "Asset Finance","Overdraft Facility","SME Term Loan","Agri Loan",
        "Staff Loan","LPO Financing","Invoice Discounting",
    ], key="sa_prod")
    tenure_months  = st.selectbox("Tenure (months)", [6,12,18,24,36,48,60,84], index=2, key="sa_ten")
    amount_applied = st.number_input("Amount applied (KES)", min_value=0.0, step=100000.0, key="sa_amt")

st.markdown("**Paste statement text:**")
statement_text = st.text_area("Statement", height=220, key="sa_txt",
    placeholder="Paste the full statement here — any Kenyan bank format accepted (Equity, KCB, Co-op, NCBA, Stanbic, Absa, DTB, etc.)",
    label_visibility="collapsed")

sb1, sb2, _ = st.columns([1,1,2])
load_sample = sb1.button("📋 Load sample statement", key="sa_sample")
if load_sample:
    st.session_state["_sa_use_sample"] = True
    st.rerun()

if st.session_state.get("_sa_use_sample") and not statement_text.strip():
    st.info("Sample statement for Grace Wanjiku (County employee, personal loan request). Click Analyse to test.")

# ── Link to existing application ─────────────────────────────────────
apps_all = json.loads((DATA/"loan_applications.json").read_text()) if (DATA/"loan_applications.json").exists() else []
pending  = [a for a in apps_all if a.get("status") in ("submitted","analysis","assigned") and not a.get("statement_analysis")]
app_opts = ["— New / don't link"] + [f"{a['id']} | {a['client_name'][:25]} | {a['product']}" for a in pending[:30]]
linked_app = st.selectbox("Link results to existing application (optional)", app_opts, key="sa_link")

# ── Analyse ─────────────────────────────────────────────────────────
_stmt = statement_text.strip() or (SAMPLE_STMT if st.session_state.get("_sa_use_sample") else "")
_name = client_name.strip() or ("Grace Wanjiku Muthoni" if st.session_state.get("_sa_use_sample") else "")
can_go = bool(_name and _stmt and len(_stmt) > 50)

if st.button("🔍 Analyse Statement", type="primary", disabled=not can_go, key="sa_run"):

    SYSTEM = (
        f"You are a senior credit analyst at Ecobank Kenya. Analyse the bank statement and return "
        f"ONLY a valid JSON object — no markdown, no text outside the JSON.\n\n"
        f"PARAMETERS: Product={product} | Amount=KES {amount_applied:,.0f} | Tenure={tenure_months}m | "
        f"DSR limit={DSR_LIMIT}% | Living estimate={LIVING_PCT}% of income | Rate={MONTHLY_RATE}%/month\n"
        f"RISK KEYWORDS (flag if found): {', '.join(RISK_KEYWORDS[:20])}\n\n"
        f"REQUIRED JSON STRUCTURE:\n"
        f"{{"
        f"\"statement_summary\":{{\"bank_name\":\"\",\"account_number\":\"\",\"account_holder\":\"\","
        f"\"period_from\":\"\",\"period_to\":\"\",\"months_covered\":0}},"
        f"\"income_analysis\":{{\"avg_monthly_credit\":0,\"highest_month_credit\":0,\"lowest_month_credit\":0,"
        f"\"income_sources\":[],\"salary_detected\":false,\"salary_day\":null,\"salary_amount\":0,"
        f"\"income_consistency_score\":0,\"income_notes\":\"\"}},"
        f"\"expenditure_analysis\":{{\"avg_monthly_debit\":0,\"categories\":{{"
        f"\"rent_utilities\":0,\"loan_repayments\":0,\"mobile_money_out\":0,"
        f"\"cash_withdrawals\":0,\"transfers_out\":0,\"insurance\":0,\"shopping_food\":0,\"other\":0}}}},"
        f"\"obligations\":{{\"existing_loans\":[],\"total_monthly_obligation\":0,"
        f"\"digital_loans_detected\":false,\"digital_loan_names\":[]}},"
        f"\"risk_flags\":[],\"risk_score\":0,"
        f"\"balance_analysis\":{{\"avg_closing_balance\":0,\"min_closing_balance\":0,"
        f"\"months_negative_balance\":0,\"return_items_count\":0}},"
        f"\"affordability\":{{\"net_monthly_income\":0,\"total_obligations\":0,"
        f"\"living_expenses_est\":0,\"net_disposable_income\":0,"
        f"\"max_installment_at_dsr\":0,\"applied_installment\":0,\"dsr_ratio\":0,"
        f"\"recommended_max_loan\":0,\"affordability_verdict\":\"\"}},"
        f"\"recommendation\":{{\"decision\":\"\",\"confidence\":\"\","
        f"\"key_strengths\":[],\"key_concerns\":[],"
        f"\"conditions_if_approve\":[],\"narrative\":\"\"}}"
        f"}}"
        f"\n\nRules: decision=APPROVE/REFER/DECLINE | confidence=High/Medium/Low | "
        f"risk_score=0-100 | consistency=0-100 | all money in KES numbers no commas | "
        f"applied_installment = amount*(r*(1+r)^n)/((1+r)^n-1) where r={MONTHLY_RATE/100} n={tenure_months}"
    )

    with st.spinner("🤖 Claude is reading the statement…"):
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json"},
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 2000,
                    "system": SYSTEM,
                    "messages": [{"role":"user","content": f"Analyse statement for {_name}:\n\n{_stmt[:8000]}"}]
                },
                timeout=60
            )
            resp.raise_for_status()
            raw = resp.json()["content"][0]["text"].strip()
            raw = re.sub(r"^```json\s*","",raw); raw = re.sub(r"\s*```$","",raw)
            result = json.loads(raw)
            st.session_state.update({
                "sa_result":result, "sa_cname":_name, "sa_product":product,
                "sa_tenure":tenure_months, "sa_amount":amount_applied,
                "sa_link_val":linked_app, "sa_raw":_stmt,
            })
        except json.JSONDecodeError:
            st.error(f"Could not parse AI response. Raw output:\n\n{raw[:600]}")
            st.stop()
        except requests.exceptions.Timeout:
            st.error("Request timed out (60s). Try with a shorter statement.")
            st.stop()
        except requests.exceptions.RequestException as e:
            st.error(f"API request failed: {str(e)[:200]}")
            st.stop()
        except Exception as e:
            st.error(f"Unexpected error: {str(e)[:200]}")
            st.stop()

# ── Display results ──────────────────────────────────────────────────
if "sa_result" in st.session_state:
    r    = st.session_state.get("sa_result")
    inc  = r.get("income_analysis",{})
    exp  = r.get("expenditure_analysis",{})
    obs  = r.get("obligations",{})
    bal  = r.get("balance_analysis",{})
    aff  = r.get("affordability",{})
    rec  = r.get("recommendation",{})
    summ = r.get("statement_summary",{})
    flags= r.get("risk_flags",[])

    decision  = rec.get("decision","REFER")
    dec_clr   = {"APPROVE":"#16A34A","REFER":"#D97706","DECLINE":"#DC2626"}.get(decision,"#6B7280")
    dec_icon  = {"APPROVE":"✅","REFER":"⚠️","DECLINE":"❌"}.get(decision,"❓")
    confidence= rec.get("confidence","Medium")
    risk_sc   = r.get("risk_score",50)
    _cname    = st.session_state.get("sa_cname","")
    _prod     = st.session_state.get("sa_product","")
    _amt      = st.session_state.get("sa_amount",0)
    _ten      = st.session_state.get("sa_tenure",0)

    # Decision banner
    st.markdown(
        f"<div style='background:{dec_clr}12;border:2.5px solid {dec_clr};"
        f"border-radius:12px;padding:14px 20px;margin:10px 0;"
        f"display:flex;align-items:center;gap:16px'>"
        f"<div style='font-size:40px'>{dec_icon}</div>"
        f"<div style='flex:1'>"
        f"<div style='font-size:20px;font-weight:800;color:{dec_clr}'>"
        f"{decision} — {confidence} Confidence</div>"
        f"<div style='font-size:12px;color:var(--color-text-secondary);margin-top:2px'>"
        f"{_cname} · {_prod} · KES {_amt/1e6:.1f}M · {_ten}m tenure · "
        f"Risk score {risk_sc}/100</div></div>"
        f"<div style='text-align:right'>"
        f"<div style='font-size:12px;font-weight:600'>{summ.get('bank_name','')}</div>"
        f"<div style='font-size:11px;color:var(--color-text-tertiary)'>"
        f"{summ.get('period_from','')} – {summ.get('period_to','')} "
        f"({summ.get('months_covered',0)} months)</div></div></div>",
        unsafe_allow_html=True)

    # Risk flags
    if flags:
        fl_html = "".join(
            f"<span style='background:#FEF2F2;border:1px solid #FECACA;"
            f"color:#991B1B;border-radius:14px;padding:2px 9px;font-size:11px;margin:2px'>"
            f"🚩 {f}</span>" for f in flags)
        st.markdown(f"<div style='margin:6px 0'>{fl_html}</div>", unsafe_allow_html=True)

    # Key metrics row
    avg_in  = inc.get("avg_monthly_credit",0)
    avg_out = exp.get("avg_monthly_debit",0)
    net_di  = aff.get("net_disposable_income",0)
    dsr     = aff.get("dsr_ratio",0)
    dsr_ok  = dsr <= DSR_LIMIT

    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Avg Monthly Income",  f"KES {avg_in/1e3:.0f}K",
              "Salaried" if inc.get("salary_detected") else "Business/Mixed")
    m2.metric("Avg Monthly Expenses",f"KES {avg_out/1e3:.0f}K",
              f"{avg_out/max(avg_in,1)*100:.0f}% of income")
    m3.metric("Monthly Obligations", f"KES {obs.get('total_monthly_obligation',0)/1e3:.0f}K")
    m4.metric("Net Disposable",      f"KES {net_di/1e3:.0f}K")
    m5.metric("DSR Ratio",           f"{dsr:.1f}% / {DSR_LIMIT}%",
              "Within limit" if dsr_ok else "EXCEEDS LIMIT",
              delta_color="normal" if dsr_ok else "inverse")

    st.markdown("---")

    # Detail tabs
    t1,t2,t3,t4,t5 = st.tabs([
        "💰 Income","📤 Expenses & Obligations","⚖️ Affordability","📋 Narrative","💾 Save"
    ])

    with t1:
        i1,i2 = st.columns(2)
        i1.markdown("**Income summary:**")
        i1.markdown(f"- Average monthly credit: **KES {avg_in/1e3:.0f}K**")
        i1.markdown(f"- Highest month: KES {inc.get('highest_month_credit',0)/1e3:.0f}K")
        i1.markdown(f"- Lowest month:  KES {inc.get('lowest_month_credit',0)/1e3:.0f}K")
        i1.markdown(f"- Consistency:   **{inc.get('income_consistency_score',0)}/100**")
        if inc.get("salary_detected"):
            i1.markdown(f"- ✅ Salary: **KES {inc.get('salary_amount',0)/1e3:.0f}K** (day {inc.get('salary_day','?')})")
        if inc.get("income_notes"):
            i1.markdown(f"- {inc['income_notes']}")
        i2.markdown("**Income sources:**")
        for s in inc.get("income_sources",[]): i2.markdown(f"  • {s}")
        i2.markdown("**Account behaviour:**")
        i2.markdown(f"- Avg closing balance: KES {bal.get('avg_closing_balance',0)/1e3:.0f}K")
        i2.markdown(f"- Min closing balance: KES {bal.get('min_closing_balance',0)/1e3:.0f}K")
        neg = bal.get("months_negative_balance",0)
        ret = bal.get("return_items_count",0)
        i2.markdown(f"- Negative months: **{'🔴 ' if neg>0 else ''}{neg}**")
        i2.markdown(f"- Return items: **{'🔴 ' if ret>0 else ''}{ret}**")

    with t2:
        e1,e2 = st.columns(2)
        cats = exp.get("categories",{})
        e1.markdown("**Expense categories (monthly avg):**")
        for cat,amt in sorted(cats.items(),key=lambda x:-x[1]):
            if amt>0:
                e1.markdown(f"  • {cat.replace('_',' ').title()}: KES {amt/1e3:.0f}K")
        e2.markdown("**Existing obligations:**")
        e2.markdown(f"- Total monthly: **KES {obs.get('total_monthly_obligation',0)/1e3:.0f}K**")
        dls = obs.get("digital_loan_names",[])
        if dls: e2.markdown(f"  ⚠️ Digital loans: {', '.join(dls)}")
        for loan in obs.get("existing_loans",[]): e2.markdown(f"  • {loan}")

    with t3:
        af1,af2 = st.columns(2)
        af1.markdown("**Affordability waterfall:**")
        ni  = aff.get("net_monthly_income",0)
        obl = aff.get("total_obligations",0)
        liv = aff.get("living_expenses_est",0)
        ndi = aff.get("net_disposable_income",0)
        mx  = aff.get("max_installment_at_dsr",0)
        ai  = aff.get("applied_installment",0)
        rl  = aff.get("recommended_max_loan",0)
        af1.markdown(f"- Gross income:           KES {ni/1e3:.0f}K")
        af1.markdown(f"- Less obligations:      -KES {obl/1e3:.0f}K")
        af1.markdown(f"- Less living (est {LIVING_PCT}%): -KES {liv/1e3:.0f}K")
        af1.markdown(f"- **Net disposable:        KES {ndi/1e3:.0f}K**")
        af1.markdown("---")
        af1.markdown(f"- Max installment ({DSR_LIMIT}% DSR): **KES {mx/1e3:.0f}K/mo**")
        af1.markdown(f"- Applied installment:     KES {ai/1e3:.0f}K/mo")
        af1.markdown(f"- Recommended max loan:   **KES {rl/1e6:.2f}M**")
        af2.markdown(f"**{aff.get('affordability_verdict','').upper()}**")
        bar_pct = min(dsr/max(DSR_LIMIT,1)*100,100)
        bar_clr = "#16A34A" if dsr<DSR_LIMIT*0.7 else "#D97706" if dsr<DSR_LIMIT else "#DC2626"
        af2.markdown(
            f"<b>DSR: {dsr:.1f}% / {DSR_LIMIT}%</b>"
            f"<div style='background:#E5E7EB;height:10px;border-radius:5px;margin:6px 0'>"
            f"<div style='width:{bar_pct:.0f}%;background:{bar_clr};height:100%;border-radius:5px'>"
            f"</div></div>", unsafe_allow_html=True)
        if dsr > DSR_LIMIT:
            af2.error(f"DSR exceeds bank limit of {DSR_LIMIT}%")

    with t4:
        if rec.get("key_strengths"):
            st.markdown("**Strengths:**")
            for s in rec["key_strengths"]: st.markdown(f"  ✅ {s}")
        if rec.get("key_concerns"):
            st.markdown("**Concerns:**")
            for c in rec["key_concerns"]: st.markdown(f"  ⚠️ {c}")
        if rec.get("conditions_if_approve"):
            st.markdown("**Conditions precedent:**")
            for cond in rec["conditions_if_approve"]: st.markdown(f"  📋 {cond}")
        st.markdown("---")
        st.markdown("**Credit narrative:**")
        st.markdown(rec.get("narrative",""))

        # Follow-up Q&A
        st.markdown("---")
        st.markdown("**🤖 Ask Claude a follow-up question:**")
        st.caption("e.g. 'What if tenure is 24 months?', 'Summarise for credit committee', 'Is income sustainable?'")
        fq = st.text_input("Question", key="sa_fq", placeholder="Ask anything about this analysis…")
        if st.button("💬 Ask", key="sa_ask", disabled=not fq.strip()):
            with st.spinner("Thinking…"):
                try:
                    r2 = requests.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={"Content-Type":"application/json"},
                        json={
                            "model":"claude-sonnet-4-20250514",
                            "max_tokens":600,
                            "system":"You are a senior credit analyst at Ecobank Kenya. Answer questions about statement analyses concisely and professionally.",
                            "messages":[{"role":"user","content":
                                f"Statement analysis:\n{json.dumps(r,indent=2)[:3000]}\n\nQuestion: {fq}"}]
                        },
                        timeout=30
                    )
                    r2.raise_for_status()
                    ans = r2.json()["content"][0]["text"]
                    st.markdown(f"**Claude:** {ans}")
                except Exception as e2:
                    st.error(f"Could not get answer: {str(e2)[:100]}")

    with t5:
        st.markdown("**Save this analysis to a loan application:**")
        payload = {
            "analysed_at":str(today),"analysed_by":name,
            "decision":rec.get("decision",""),"confidence":rec.get("confidence",""),
            "risk_score":risk_sc,
            "avg_monthly_income":avg_in,"avg_monthly_debit":avg_out,
            "total_obligations":obs.get("total_monthly_obligation",0),
            "net_disposable":net_di,"dsr_ratio":dsr,
            "max_installment":aff.get("max_installment_at_dsr",0),
            "recommended_max_loan":aff.get("recommended_max_loan",0),
            "return_items":bal.get("return_items_count",0),
            "risk_flags":flags,"narrative":rec.get("narrative",""),
            "full_result":r,
        }
        st.json(payload, expanded=False)

        s1,s2 = st.columns(2)
        if s1.button("💾 Save to linked application", key="sa_save", type="primary"):
            lv = st.session_state.get("sa_link_val","")
            if lv.startswith("—"):
                st.warning("Select an application from the dropdown first.")
            else:
                app_id = lv.split(" | ")[0]
                all_apps2 = json.loads((DATA/"loan_applications.json").read_text())
                saved = False
                for a in all_apps2:
                    if a["id"]==app_id:
                        a["statement_analysis"]=payload; a["last_updated"]=str(today)
                        saved=True; break
                if saved:
                    (DATA/"loan_applications.json").write_text(json.dumps(all_apps2,indent=2))
                    audit_log("SA_SAVE", name, "Data saved")
                    _bsc_trigger(uname, "K046")
                    st.cache_data.clear(); st.success(f"✅ Saved to {app_id}"); st.rerun()
                else:
                    st.error(f"Application {app_id} not found")

        # Excel download
        try:
            import pandas as pd, io
            rpt_rows = [
                {"Field":"Customer",           "Value":_cname},
                {"Field":"Product",            "Value":_prod},
                {"Field":"Amount Applied",     "Value":f"KES {_amt:,.0f}"},
                {"Field":"Tenure",             "Value":f"{_ten} months"},
                {"Field":"Bank",               "Value":summ.get("bank_name","")},
                {"Field":"Statement Period",   "Value":f"{summ.get('period_from','')} – {summ.get('period_to','')}"},
                {"Field":"Months Covered",     "Value":summ.get("months_covered",0)},
                {"Field":"Decision",           "Value":decision},
                {"Field":"Confidence",         "Value":confidence},
                {"Field":"Risk Score",         "Value":f"{risk_sc}/100"},
                {"Field":"Avg Monthly Income", "Value":f"KES {avg_in:,.0f}"},
                {"Field":"Avg Monthly Expenses","Value":f"KES {avg_out:,.0f}"},
                {"Field":"Total Obligations",  "Value":f"KES {obs.get('total_monthly_obligation',0):,.0f}"},
                {"Field":"Net Disposable",     "Value":f"KES {net_di:,.0f}"},
                {"Field":"DSR Ratio",          "Value":f"{dsr:.1f}%"},
                {"Field":"Max Installment",    "Value":f"KES {aff.get('max_installment_at_dsr',0):,.0f}"},
                {"Field":"Recommended Max Loan","Value":f"KES {aff.get('recommended_max_loan',0):,.0f}"},
                {"Field":"Return Items",       "Value":bal.get("return_items_count",0)},
                {"Field":"Risk Flags",         "Value":", ".join(flags)},
                {"Field":"Narrative",          "Value":rec.get("narrative","")},
            ]
            buf = io.BytesIO()
            pd.DataFrame(rpt_rows).to_excel(buf,index=False,engine="openpyxl")
            buf.seek(0)
            s2.download_button(
                "📥 Download report (Excel)",
                data=buf.getvalue(),
                file_name=f"StatementAnalysis_{_cname.replace(' ','_')}_{today}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="sa_dl")
        except Exception:
            pass

    st.markdown("---")
    if st.button("🔄 New analysis", key="sa_clear"):
        for k in ["sa_result","sa_cname","sa_product","sa_tenure","sa_amount",
                  "sa_link_val","sa_raw","_sa_use_sample"]:
            st.session_state.pop(k,None)
        st.rerun()
