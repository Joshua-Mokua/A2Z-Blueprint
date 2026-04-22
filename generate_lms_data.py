"""
generate_lms_data.py — Generate simulated LMS data for all five modules.
Run from project root: python generate_lms_data.py
"""
import json, random, csv
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict

random.seed(42)
DATA = Path('data')

# ── Load existing data ──────────────────────────────────────────────
pipeline  = json.loads((DATA/'pipeline.json').read_text())
users     = json.loads((DATA/'users.json').read_text())

# Build role→staff maps
rm_staff = [(u, d) for u, d in users.items()
            if any(x in d.get('role','') for x in
                   ('Relationship','Business Banker','Corporate','SME','Personal Banker'))]
credit_analysts = [(u, d) for u, d in users.items()
                   if any(x in d.get('role','') for x in
                          ('Credit Analyst','Credit Admin','Credit Analysis',
                           'Senior Manager -Credit'))]
compliance_staff = [(u, d) for u, d in users.items()
                    if any(x in d.get('role','') for x in
                           ('Compliance','AML','Legal','Risk'))]

print(f"RMs: {len(rm_staff)}, Credit staff: {len(credit_analysts)}, Compliance: {len(compliance_staff)}")

# ── Swim lane classification ────────────────────────────────────────
def swim_lane(amount, product, is_repeat_borrower, clean_history):
    """Classify a loan application into a swim lane."""
    if is_repeat_borrower and clean_history and amount <= 5_000_000:
        return 'Express'          # auto-score, fast track
    if amount >= 100_000_000 or 'Corporate' in product or 'Syndic' in product:
        return 'Complex'          # committee required
    return 'Standard'             # full appraisal

PRODUCTS_RETAIL  = ['Personal Loan','Salary Advance','Staff Loan','Mortgage','Asset Finance']
PRODUCTS_MSME    = ['Business Loan','LPO Financing','Invoice Discounting',
                    'MSME Working Capital','Agribusiness Loan','Overdraft Facility']
PRODUCTS_CORP    = ['Corporate Bond','Import Finance','Export Finance LC',
                    'Trade Finance LC','Performance Bond','Bid Bond']
PRODUCTS_FD      = ['Fixed Deposit — 30 Days','Fixed Deposit — 90 Days',
                    'Fixed Deposit — 180 Days','Fixed Deposit — 364 Days']

DECLINE_REASONS  = [
    'Insufficient cash flow','Inadequate collateral','Poor credit history',
    'Incomplete documentation','Policy limit exceeded','Sector concentration risk',
    'Negative equity','Unacceptable business plan','Director adverse listing',
    'AML/KYC concerns','Regulatory restriction','High debt-service ratio',
]
REWORK_REASONS   = [
    'Missing audited accounts','Collateral valuation expired',
    'Board resolution not provided','Insurance certificate missing',
    'Financial projections unrealistic','CRB report outstanding',
    'Title deed not submitted','Guarantor financials missing',
    'Business registration expired','Land search required',
]
CONDITION_TYPES  = [
    'Insurance certificate','Valuation report','Board resolution',
    'Title deed registration','Land search','Legal charge','Debenture',
    'Board minutes','CRB clearance','KRA PIN certificate',
]
BANKS_KE = ['KCB','Equity Bank','Co-operative Bank','NCBA','Absa',
            'Standard Chartered','DTB','I&M Bank','Family Bank','Prime Bank']

def rdate(start_days_ago=180, end_days_ago=0):
    d = date.today() - timedelta(days=random.randint(end_days_ago, start_days_ago))
    return d.isoformat()

def pick(lst): return random.choice(lst)
def pickn(lst, n): return random.sample(lst, min(n, len(lst)))

# ═══════════════════════════════════════════════════════════════════
# 1. LOAN APPLICATIONS (pipeline → credit handoff)
# ═══════════════════════════════════════════════════════════════════
print("Generating loan applications...")

CLIENT_NAMES = [
    'Safaricom PLC','Java House Kenya','Bidco Africa','Twiga Foods',
    'Mabati Rolling Mills','Bamburi Cement','East African Breweries',
    'Nation Media Group','Equity Group Holdings','Stanbic Holdings',
    'Britam Holdings','Jubilee Holdings','TransCentury PLC','BOC Kenya',
    'WPP Scangroup','Sameer Africa','Flame Tree Group','Longhorn Publishers',
    'Uchumi Supermarkets','Naivas Ltd','Quickmart Ltd','Carrefour Kenya',
    'Nakumatt Supermarkets','Tuskys Supermarkets','Woolworths Kenya',
    'Kenya Airways','Jambojet','Kenya Power','Kenya Ports Authority',
    'Kenya Pipeline Company','National Oil Corporation','Kenol Kobil',
    'TotalEnergies Kenya','Rubis Energy Kenya','Gulf Energy Ltd',
    'Strathmore University','United States International University',
    'Aga Khan Hospital','Nairobi Hospital','MP Shah Hospital',
    'Kenyatta National Hospital','Gertrude Garden Hospital',
    'Unga Group','Kakuzi PLC','Kapchorua Tea','Williamson Tea Kenya',
    'Del Monte Kenya','Kakuzi Avocados','Sunripe Kenya','Flamingo Horticulture',
    'Deacons East Africa','Mr Price Group','LC Waikiki Kenya','Pepco Kenya',
    'Nakuru Millers','Eldoret Grains','Trans-Nzoia Cooperative','Bomet Farmers',
    'Kisumu Fish Processors','Lake Basin Development','Mwea Rice Mills',
    'Kirinyaga Water Services','Narok Water Services','Laikipia County',
    'Murang\'a County Government','Kiambu County Sacco','Meru County Saccos',
]

STATUSES = {
    'draft':        0.08,
    'submitted':    0.07,
    'completeness': 0.05,
    'assigned':     0.10,
    'analysis':     0.15,
    'committee':    0.08,
    'approved':     0.22,
    'declined':     0.10,
    'returned':     0.08,
    'credit_admin': 0.04,
    'disbursed':    0.03,
}

def weighted_status():
    r = random.random(); cum = 0
    for s, w in STATUSES.items():
        cum += w
        if r < cum: return s
    return 'analysis'

applications = []
for i in range(350):
    # Pull from pipeline or create fresh
    use_pipeline = i < len(pipeline) and random.random() < 0.6
    if use_pipeline:
        deal = pipeline[i % len(pipeline)]
        rm_code = str(deal['staff_code'])
        rm_name = deal['staff_name']
        rm_unit = deal['unit']
        client  = deal['client_name']
        product = deal['product']
        amount  = deal['amount']
    else:
        rm_u, rm_d = pick(rm_staff)
        rm_code = rm_d.get('staff_code', rm_u)
        rm_name = rm_d.get('full_name', rm_u)
        rm_unit = rm_d.get('unit', '')
        client  = pick(CLIENT_NAMES)
        all_products = PRODUCTS_RETAIL + PRODUCTS_MSME + PRODUCTS_CORP
        product = pick(all_products)
        amount  = random.choice([
            random.randint(500_000, 5_000_000),
            random.randint(5_000_000, 50_000_000),
            random.randint(50_000_000, 250_000_000),
        ])

    is_repeat   = random.random() < 0.4
    clean_hist  = random.random() < 0.7 if is_repeat else False
    lane        = swim_lane(amount, product, is_repeat, clean_hist)
    status      = weighted_status()
    app_date    = rdate(120, 5)

    # Analyst assignment
    analyst = None
    if status not in ('draft','submitted','completeness') and credit_analysts:
        a_u, a_d = pick(credit_analysts)
        analyst  = {'code': a_d.get('staff_code', a_u),
                    'name': a_d.get('full_name', a_u)}

    # Decision details
    decision = None
    if status in ('approved','declined','returned','credit_admin','disbursed'):
        decision = {
            'verdict':     status if status in ('approved','declined','returned') else 'approved',
            'date':        rdate(60, 1),
            'authority':   pick(['Branch Manager','Credit Committee',
                                 'Chief Credit Officer','Board Credit Committee']),
            'conditions':  (pickn(CONDITION_TYPES, random.randint(2,5))
                            if status in ('approved','credit_admin','disbursed') else []),
            'reason':      (pick(DECLINE_REASONS) if status == 'declined' else
                            pick(REWORK_REASONS)  if status == 'returned'  else None),
            'comments':    '',
        }

    # Completeness checklist
    docs_required = ['CRB Report','Bank Statements (6 months)','Business Registration',
                     'ID/Passport','KRA PIN','Financial Statements']
    if amount > 10_000_000:
        docs_required += ['Audited Accounts','Business Plan','Valuation Report']
    if product in PRODUCTS_CORP:
        docs_required += ['Board Resolution','Memorandum of Association',
                          'Certificate of Incorporation']
    docs_submitted = docs_required.copy()
    if status in ('draft','submitted'):
        # Some docs missing
        missing_n = random.randint(1, min(3, len(docs_required)))
        missing   = pickn(docs_required, missing_n)
        docs_submitted = [d for d in docs_required if d not in missing]

    completeness_score = round(len(docs_submitted) / len(docs_required) * 100, 1)

    # Compliance flag
    compliance_flag  = random.random() < 0.08
    compliance_type  = pick(['PEP','Sanctioned Entity','Adverse Media',
                              'Restricted Sector','AML Flag']) if compliance_flag else None

    app = {
        'id':              f'LMS{str(i+1).zfill(5)}',
        'pipeline_deal_id':deal['id'] if use_pipeline else None,
        'client_name':     client,
        'client_cif':      f'CIF{random.randint(100000, 999999)}',
        'product':         product,
        'amount':          amount,
        'currency':        'KES',
        'swim_lane':       lane,
        'status':          status,
        'application_date':app_date,
        'rm_code':         rm_code,
        'rm_name':         rm_name,
        'rm_unit':         rm_unit,
        'analyst':         analyst,
        'is_repeat_borrower': is_repeat,
        'clean_repayment_history': clean_hist,
        'docs_required':   docs_required,
        'docs_submitted':  docs_submitted,
        'completeness_score': completeness_score,
        'compliance_flag': compliance_flag,
        'compliance_type': compliance_type,
        'decision':        decision,
        'appraisal_notes': '',
        'tat_days':        random.randint(1, 45) if status not in ('draft',) else 0,
        'sla_target_days': 3 if lane == 'Express' else 10 if lane == 'Standard' else 21,
        'last_updated':    rdate(30, 0),
    }
    applications.append(app)

(DATA/'loan_applications.json').write_text(json.dumps(applications, indent=2))
print(f"  ✅ loan_applications.json: {len(applications)} applications")

# Status distribution
from collections import Counter
st_dist = Counter(a['status'] for a in applications)
for s, c in sorted(st_dist.items(), key=lambda x:-x[1]):
    print(f"    {s:<15}: {c}")

# ═══════════════════════════════════════════════════════════════════
# 2. CREDIT ADMIN CONDITIONS (pre-disbursement)
# ═══════════════════════════════════════════════════════════════════
print("\nGenerating credit admin conditions...")

approved_apps = [a for a in applications
                 if a['status'] in ('approved','credit_admin','disbursed')]
credit_admin_cases = []

for app in approved_apps:
    conditions = app.get('decision',{}).get('conditions',[]) or pickn(CONDITION_TYPES, 3)
    case_conditions = []
    for cond in conditions:
        fulfilled = random.random() < (0.9 if app['status'] == 'disbursed' else 0.6)
        case_conditions.append({
            'type':         cond,
            'required':     True,
            'fulfilled':    fulfilled,
            'date_set':     app.get('decision',{}).get('date',''),
            'date_met':     rdate(30,1) if fulfilled else None,
            'officer':      (credit_analysts[0][1].get('full_name','') if credit_analysts else ''),
            'notes':        '',
        })

    all_met = all(c['fulfilled'] for c in case_conditions)
    credit_admin_cases.append({
        'id':             f'CA{app["id"]}',
        'application_id': app['id'],
        'client_name':    app['client_name'],
        'product':        app['product'],
        'amount':         app['amount'],
        'rm_code':        app['rm_code'],
        'rm_name':        app['rm_name'],
        'approval_date':  app.get('decision',{}).get('date',''),
        'conditions':     case_conditions,
        'all_conditions_met': all_met,
        'ready_for_disbursement': all_met,
        'disbursed':      app['status'] == 'disbursed',
        'disbursement_date': rdate(20,1) if app['status'] == 'disbursed' else None,
        'last_updated':   rdate(10,0),
    })

(DATA/'credit_admin.json').write_text(json.dumps(credit_admin_cases, indent=2))
print(f"  ✅ credit_admin.json: {len(credit_admin_cases)} cases")

# ═══════════════════════════════════════════════════════════════════
# 3. COMPLIANCE CASES
# ═══════════════════════════════════════════════════════════════════
print("\nGenerating compliance cases...")

compliance_cases = []
flagged_apps = [a for a in applications if a['compliance_flag']]

# Add some CIMS-sourced compliance cases too
for i in range(80):
    is_from_app = i < len(flagged_apps)
    source_app  = flagged_apps[i] if is_from_app else None
    flag_type   = (source_app['compliance_type'] if is_from_app
                   else pick(['PEP','Sanctioned Entity','Adverse Media',
                               'Restricted Sector','AML Flag','Unusual Transaction']))
    comp_status = pick(['open','under_review','cleared','escalated','rejected'])
    rm_u, rm_d  = pick(rm_staff)
    officer     = (pick(compliance_staff)[1] if compliance_staff else {'full_name':'Compliance Officer','staff_code':'C001'})

    compliance_cases.append({
        'id':              f'COMP{str(i+1).zfill(4)}',
        'source':          'loan_application' if is_from_app else pick(['cims','account_opening','periodic_review']),
        'source_ref':      source_app['id'] if is_from_app else f'REF{random.randint(1000,9999)}',
        'client_name':     source_app['client_name'] if is_from_app else pick(CLIENT_NAMES),
        'client_cif':      source_app['client_cif'] if is_from_app else f'CIF{random.randint(100000,999999)}',
        'flag_type':       flag_type,
        'risk_level':      pick(['Low','Medium','High','Critical']),
        'status':          comp_status,
        'raised_by':       (rm_d.get('full_name','') if is_from_app else 'System'),
        'raised_date':     rdate(90,5),
        'assigned_officer': officer.get('full_name',''),
        'officer_code':    officer.get('staff_code',''),
        'review_notes':    '',
        'cleared_date':    rdate(30,1) if comp_status == 'cleared' else None,
        'escalated_to':    pick(['Head of Compliance','CCO','Central Bank']) if comp_status == 'escalated' else None,
        'documents_required': pickn(['SAR Form','Enhanced DD Report','Source of Funds',
                                     'PEP Declaration','AML questionnaire','Board Resolution'], 3),
        'last_updated':    rdate(20,0),
    })

(DATA/'compliance_cases.json').write_text(json.dumps(compliance_cases, indent=2))
print(f"  ✅ compliance_cases.json: {len(compliance_cases)} cases")

# ═══════════════════════════════════════════════════════════════════
# 4. TREASURY — FD RATIFICATION
# ═══════════════════════════════════════════════════════════════════
print("\nGenerating treasury FD ratification data...")

# Pull FD deals from pipeline + add some standalone
fd_ratifications = []
fd_pipeline = [d for d in pipeline if any(x in d.get('product','') for x in ('Fixed Deposit','Term Deposit','Treasury'))]
print(f"  FD deals in pipeline: {len(fd_pipeline)}")

# Add fresh FD requests
for i in range(120):
    use_pip = i < len(fd_pipeline)
    deal    = fd_pipeline[i] if use_pip else None
    rm_u, rm_d = pick(rm_staff)
    tenure_days = pick([30, 60, 90, 182, 364])
    amount      = random.randint(1_000_000, 500_000_000)
    client      = deal['client_name'] if deal else pick(CLIENT_NAMES)
    proposed_rate = round(random.uniform(8.5, 14.5), 2)
    ratified_rate = round(proposed_rate + random.uniform(-1.5, 0.5), 2)
    rat_status  = pick(['pending','approved','counter_offered','rejected','booked'])

    fd_ratifications.append({
        'id':               f'FD{str(i+1).zfill(4)}',
        'pipeline_deal_id': deal['id'] if deal else None,
        'client_name':      client,
        'client_cif':       f'CIF{random.randint(100000,999999)}',
        'product':          pick(PRODUCTS_FD),
        'amount':           amount,
        'currency':         pick(['KES','USD','EUR']),
        'tenure_days':      tenure_days,
        'proposed_rate':    proposed_rate,
        'ratified_rate':    ratified_rate if rat_status in ('approved','counter_offered','booked') else None,
        'market_rate_ref':  round(random.uniform(9.0, 13.0), 2),   # CBK market reference
        'status':           rat_status,
        'rm_code':          rm_d.get('staff_code', rm_u),
        'rm_name':          rm_d.get('full_name', rm_u),
        'rm_unit':          rm_d.get('unit',''),
        'submitted_date':   rdate(60, 1),
        'ratified_date':    rdate(30, 1) if rat_status in ('approved','counter_offered','booked','rejected') else None,
        'treasury_officer': 'Treasury Dealer',
        'counter_rate':     round(ratified_rate - 0.25, 2) if rat_status == 'counter_offered' else None,
        'notes':            '',
        'booked_date':      rdate(15,1) if rat_status == 'booked' else None,
        'maturity_date':    (date.today() + timedelta(days=tenure_days)).isoformat() if rat_status == 'booked' else None,
    })

(DATA/'treasury_fd.json').write_text(json.dumps(fd_ratifications, indent=2))
print(f"  ✅ treasury_fd.json: {len(fd_ratifications)} FD ratification requests")

# ═══════════════════════════════════════════════════════════════════
# 5. SUMMARY
# ═══════════════════════════════════════════════════════════════════
print("\n" + "="*55)
print("DATA GENERATION COMPLETE")
print("="*55)
for fname, desc in [
    ('loan_applications.json', 'Loan applications (all stages)'),
    ('credit_admin.json',      'Credit admin conditions tracker'),
    ('compliance_cases.json',  'Compliance case management'),
    ('treasury_fd.json',       'Treasury FD ratification queue'),
]:
    p = DATA / fname
    print(f"  ✅ {fname:<35} {p.stat().st_size/1024:>7.1f} KB  {desc}")
