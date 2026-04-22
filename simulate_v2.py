#!/usr/bin/env python3
"""
simulate_v2.py — Full A2Z Blueprint simulation for v2.
Run from inside a2z/: python simulate_v2.py
"""
import json, csv, random, openpyxl, shutil
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict, Counter

random.seed(2026)
DATA  = Path('data')
CBS   = Path('../cbs_data')
today = date.today()

def rdate(start=180, end=0):
    return (today - timedelta(days=random.randint(end, start))).isoformat()
def fdate(days):
    return (today + timedelta(days=days)).isoformat()
def pick(lst): return random.choice(lst)
def pct(n, d): return round(n/d*100, 2) if d else 0

print("="*60)
print("A2Z BLUEPRINT v2 — FULL SIMULATION")
print("="*60)

# ── Load base data ─────────────────────────────────────────────────
users     = json.loads((DATA/'users.json').read_text())
lib       = json.loads((DATA/'kpi_library.json').read_text())
org       = json.loads((DATA/'org_config.json').read_text())
lms_cfg   = json.loads((DATA/'lms_config.json').read_text())
pipeline  = json.loads((DATA/'pipeline.json').read_text())
apps_existing = json.loads((DATA/'loan_applications.json').read_text())

# Staff by role
staff_by_role = defaultdict(list)
wb_sr = openpyxl.load_workbook(str(DATA/'staff_register.xlsx'))
ws_sr = wb_sr.active
sr_h  = [ws_sr.cell(1,c).value for c in range(1, ws_sr.max_column+1)]
sc_i  = sr_h.index('Staff Code'); rc_i = sr_h.index('Role')
uc_i  = sr_h.index('Unit'); nc_i = sr_h.index('Staff Name')
all_staff = []
for row in ws_sr.iter_rows(min_row=2, values_only=True):
    if not row[sc_i]: continue
    s = {'code': str(row[sc_i]), 'name': str(row[nc_i] or ''),
         'role': str(row[rc_i] or ''), 'unit': str(row[uc_i] or '')}
    all_staff.append(s)
    staff_by_role[s['role']].append(s)

# Branches
branches = sorted(set(s['unit'] for s in all_staff
                       if s['unit'] not in ('Head Office','HO','') and s['unit']))
print(f"\nLoaded: {len(all_staff)} staff, {len(branches)} branches")

# Role helpers
def find_staff(role_keywords):
    return [s for s in all_staff if any(k in s['role'] for k in role_keywords)]
rms        = find_staff(['Relationship','Business Banker'])
credit_ana = find_staff(['Credit Analyst','Credit Analysis'])
legal_off  = find_staff(['Legal','Company Secretary','Paralegal'])
comp_off   = find_staff(['Compliance','Risk','AML'])
treasury_s = find_staff(['Treasury','CFO','Chief Finance'])
branch_mgrs= find_staff(['Branch Manager'])

print(f"RMs: {len(rms)}, Credit: {len(credit_ana)}, Legal: {len(legal_off)}")

# ══════════════════════════════════════════════════════════════════
# STEP 1: KPI LIBRARY — Add new KPIs for all teams
# ══════════════════════════════════════════════════════════════════
print("\n[1/8] Expanding KPI library...")

NEW_KPIS = {
    # Credit team KPIs
    "CREDIT_APPROVAL_RATE":  {"name":"Credit Approval Rate",        "unit":"%",  "direction":"higher","pillar":"Financial",   "default_weight":0.20,"cbs_source":"loan_applications"},
    "CREDIT_REWORK_RATE":    {"name":"Credit Rework Rate",           "unit":"%",  "direction":"lower", "pillar":"Operational","default_weight":0.15,"cbs_source":"loan_applications"},
    "CREDIT_TAT_EXPRESS":    {"name":"Credit TAT — Express Lane",    "unit":"days","direction":"lower","pillar":"Operational","default_weight":0.15,"cbs_source":"loan_applications"},
    "CREDIT_TAT_STANDARD":   {"name":"Credit TAT — Standard Lane",   "unit":"days","direction":"lower","pillar":"Operational","default_weight":0.15,"cbs_source":"loan_applications"},
    "CREDIT_TAT_COMPLEX":    {"name":"Credit TAT — Complex Lane",    "unit":"days","direction":"lower","pillar":"Operational","default_weight":0.10,"cbs_source":"loan_applications"},
    "CREDIT_DECLINE_RATE":   {"name":"Credit Decline Rate",          "unit":"%",  "direction":"lower", "pillar":"Financial",  "default_weight":0.10,"cbs_source":"loan_applications"},
    "LOAN_DISBURSEMENT_TAT": {"name":"Loan Disbursement TAT",        "unit":"days","direction":"lower","pillar":"Operational","default_weight":0.15,"cbs_source":"credit_admin"},
    # Legal team KPIs
    "LEGAL_SLA_SECURITY":    {"name":"Legal TAT — Security Perfection","unit":"%","direction":"higher","pillar":"Operational","default_weight":0.20,"cbs_source":"legal_matters"},
    "LEGAL_SLA_DOCS":        {"name":"Legal TAT — Loan Documentation", "unit":"%","direction":"higher","pillar":"Operational","default_weight":0.20,"cbs_source":"legal_matters"},
    "LEGAL_SLA_ATTORNEY":    {"name":"Legal TAT — External Counsel",   "unit":"%","direction":"higher","pillar":"Operational","default_weight":0.15,"cbs_source":"legal_matters"},
    "LEGAL_SLA_VALUATION":   {"name":"Legal TAT — Valuation",          "unit":"%","direction":"higher","pillar":"Operational","default_weight":0.15,"cbs_source":"legal_matters"},
    "LEGAL_SLA_CUSTODY":     {"name":"Legal TAT — Title Deed Custody", "unit":"%","direction":"higher","pillar":"Operational","default_weight":0.10,"cbs_source":"legal_matters"},
    "LEGAL_SLA_OPINION":     {"name":"Legal TAT — Legal Opinion",      "unit":"%","direction":"higher","pillar":"Operational","default_weight":0.10,"cbs_source":"legal_matters"},
    "LEGAL_OVERDUE_RATE":    {"name":"Legal Overdue Rate",             "unit":"%","direction":"lower","pillar":"Operational","default_weight":0.10,"cbs_source":"legal_matters"},
    # Treasury KPIs
    "TREASURY_FD_VOLUME":    {"name":"FD Ratification Volume",         "unit":"KES","direction":"higher","pillar":"Financial","default_weight":0.25,"cbs_source":"treasury_fd"},
    "TREASURY_FD_TAT":       {"name":"FD Ratification TAT",            "unit":"days","direction":"lower","pillar":"Operational","default_weight":0.20,"cbs_source":"treasury_fd"},
    "TREASURY_FD_APPROVAL":  {"name":"FD Approval Rate",               "unit":"%","direction":"higher","pillar":"Operational","default_weight":0.20,"cbs_source":"treasury_fd"},
    "TREASURY_RATE_VARIANCE":{"name":"FD Rate Variance vs Market",     "unit":"%","direction":"lower","pillar":"Financial","default_weight":0.20,"cbs_source":"treasury_fd"},
    "TREASURY_NIM":          {"name":"Net Interest Margin",            "unit":"%","direction":"higher","pillar":"Financial","default_weight":0.15,"cbs_source":"accounts"},
    # Compliance KPIs
    "COMP_CLEARANCE_RATE":   {"name":"Compliance Case Clearance Rate", "unit":"%","direction":"higher","pillar":"Operational","default_weight":0.30,"cbs_source":"compliance_cases"},
    "COMP_SLA_CRITICAL":     {"name":"Compliance SLA — Critical Cases","unit":"%","direction":"higher","pillar":"Operational","default_weight":0.25,"cbs_source":"compliance_cases"},
    "COMP_SLA_HIGH":         {"name":"Compliance SLA — High Risk Cases","unit":"%","direction":"higher","pillar":"Operational","default_weight":0.20,"cbs_source":"compliance_cases"},
    "COMP_OPEN_CASES":       {"name":"Open Compliance Cases",          "unit":"count","direction":"lower","pillar":"Operational","default_weight":0.15,"cbs_source":"compliance_cases"},
    "COMP_ESCALATION_RATE":  {"name":"Compliance Escalation Rate",     "unit":"%","direction":"lower","pillar":"Operational","default_weight":0.10,"cbs_source":"compliance_cases"},
}

# Add to pillars
for kid, kd in NEW_KPIS.items():
    pillar = kd['pillar']
    if not any(k['id'] == kid for k in lib['pillars'].get(pillar, [])):
        if pillar not in lib['pillars']:
            lib['pillars'][pillar] = []
        lib['pillars'][pillar].append({
            'id': kid, 'name': kd['name'], 'unit': kd['unit'],
            'direction': kd['direction'], 'cbs_source': kd['cbs_source'],
            'fixed': False, 'default_weight': kd['default_weight'],
        })

# Assign KPIs to roles
ROLE_KPI_MAP = {
    'Chief Credit Officer':                ['CREDIT_APPROVAL_RATE','CREDIT_REWORK_RATE','CREDIT_TAT_STANDARD',
                                             'CREDIT_TAT_COMPLEX','CREDIT_DECLINE_RATE','LOAN_DISBURSEMENT_TAT',
                                             'NPL_RATIO','PAR','LOAN_GROWTH','PBT','COMPLIANCE_SCORE','AUDIT_SCORE'],
    'Senior Manager -Credit Analysis':     ['CREDIT_APPROVAL_RATE','CREDIT_REWORK_RATE','CREDIT_TAT_STANDARD',
                                             'CREDIT_TAT_COMPLEX','CREDIT_DECLINE_RATE'],
    'Credit Analyst':                       ['CREDIT_APPROVAL_RATE','CREDIT_REWORK_RATE','CREDIT_TAT_EXPRESS',
                                             'CREDIT_TAT_STANDARD','LOAN_DISBURSEMENT_TAT'],
    'Credit Admin Officer':                 ['LOAN_DISBURSEMENT_TAT','CREDIT_APPROVAL_RATE','NEW_ACCOUNTS'],
    'Supervisor Credit Reporting':          ['CREDIT_APPROVAL_RATE','CREDIT_DECLINE_RATE','CREDIT_REWORK_RATE'],
    'Consumer and Staff Loan Analysis Manager': ['CREDIT_APPROVAL_RATE','CREDIT_TAT_EXPRESS','LOAN_DISBURSEMENT_TAT'],
    'Manager-Credit Monitoring':            ['NPL_RATIO','PAR','COLLECTION_THROUGHPUT','CREDIT_DECLINE_RATE'],
    'Collections and Recoveries Officer':   ['COLLECTION_THROUGHPUT','NPL_RATIO','PAR'],
    'Company Secretary and Chief Legal Officer': ['LEGAL_SLA_SECURITY','LEGAL_SLA_DOCS','LEGAL_SLA_ATTORNEY',
                                                    'LEGAL_SLA_VALUATION','LEGAL_OVERDUE_RATE','COMPLIANCE_SCORE'],
    'Senior Manager Internal Audit':        ['AUDIT_SCORE','COMPLIANCE_SCORE','LEGAL_OVERDUE_RATE'],
    'Chief Financial Officer':              ['PBT','TREASURY_FD_VOLUME','TREASURY_NIM','TOTAL_NFI',
                                              'CASA_RATIO','LOAN_GROWTH','COMPLIANCE_SCORE'],
    'Chief Risk Officer':                   ['NPL_RATIO','PAR','COMP_CLEARANCE_RATE','COMP_SLA_CRITICAL',
                                              'COMP_SLA_HIGH','LEGAL_OVERDUE_RATE','COMPLIANCE_SCORE'],
    'Operational Risk Manager':             ['COMP_CLEARANCE_RATE','COMP_SLA_CRITICAL','COMP_ESCALATION_RATE'],
    'Risk Manager':                         ['COMP_CLEARANCE_RATE','COMP_SLA_HIGH','NPL_RATIO'],
}

# Map KPI names to IDs for the library
name_to_id = {}
for pillar, kpis in lib['pillars'].items():
    for k in kpis:
        name_to_id[k['name']] = k['id']
        name_to_id[k['id']]   = k['id']  # id lookup too

for role, kpi_list in ROLE_KPI_MAP.items():
    existing = set(lib['role_kpis'].get(role, []))
    merged   = list(existing)
    for kid in kpi_list:
        kpi_id = kid if kid in NEW_KPIS else name_to_id.get(kid, kid)
        if kpi_id not in merged:
            merged.append(kpi_id)
    lib['role_kpis'][role] = merged

(DATA/'kpi_library.json').write_text(json.dumps(lib, indent=2))
print(f"  ✅ {len(NEW_KPIS)} new KPIs added, {len(ROLE_KPI_MAP)} roles updated")

# ══════════════════════════════════════════════════════════════════
# STEP 2: 20 NEW INITIATIVES THROUGH ALL G0-G5 STAGES
# ══════════════════════════════════════════════════════════════════
print("\n[2/8] Generating 20 initiatives through all G-stages...")

WORKSTREAMS = ['WS01','WS02','WS03','WS04','WS05','WS06','WS07','WS08','WS09','WS10','WS11']
INITIATIVE_NAMES = [
    'Digital Onboarding Platform','Mobile Banking Enhancement','Branch Network Expansion',
    'Credit Scoring Engine','Treasury Management System','Compliance Automation',
    'Customer Experience Programme','Trade Finance Digitalisation',
    'SME Banking Growth Initiative','Bancassurance Scale-Up',
    'Data Analytics Centre','Cybersecurity Upgrade','Green Finance Products',
    'Agency Banking Rollout','Islamic Finance Window','Diaspora Banking Service',
    'Operational Excellence Programme','HR Digital Transformation',
    'Supply Chain Finance Product','Real Estate Finance Growth',
]

STAGES = ['G0','G1','G2','G3','G4','G5']
STAGE_LABELS = {
    'G0':'Concept','G1':'Feasibility','G2':'Design',
    'G3':'Development','G4':'Testing','G5':'Deployed',
}

md_code = next((s['code'] for s in all_staff
                if 'Managing' in s['role'] or 'Chief Executive' in s['role']), '300001')
senior_staff = [s for s in all_staff if any(x in s['role'] for x in
                ('Director','Chief','Head Of','Regional'))]

existing_ini = json.loads((DATA/'execute_initiatives.json').read_text())
ini_ids_used = {i.get('id','') for i in existing_ini}

new_initiatives = list(existing_ini)  # keep existing INI0001
for i, name in enumerate(INITIATIVE_NAMES):
    ini_id = f'INI{str(i+2).zfill(4)}'
    while ini_id in ini_ids_used:
        i += 1
        ini_id = f'INI{str(i+2).zfill(4)}'
    ini_ids_used.add(ini_id)

    # Each initiative goes to a different stage
    stage_idx = i % len(STAGES)
    stage     = STAGES[stage_idx]
    owner     = pick(senior_staff)
    ws        = pick(WORKSTREAMS)

    # Build gate history up to current stage
    gates = []
    open_date = today - timedelta(days=random.randint(30, 300))
    for g_idx, g in enumerate(STAGES[:stage_idx+1]):
        gate_date = open_date + timedelta(days=g_idx * random.randint(10, 30))
        gates.append({
            'gate': g, 'status': 'passed' if g_idx < stage_idx else 'current',
            'date': gate_date.isoformat(),
            'approver': pick(senior_staff)['name'],
            'notes': f'{STAGE_LABELS[g]} gate {"passed" if g_idx < stage_idx else "in progress"}',
            'budget_approved': random.randint(1, 50) * 1_000_000,
        })

    new_initiatives.append({
        'id':           ini_id,
        'name':         name,
        'workstream':   ws,
        'owner_code':   owner['code'],
        'owner':        owner['name'],
        'owner_role':   owner['role'],
        'status':       'Active' if stage != 'G5' else 'Completed',
        'current_gate': stage,
        'description':  f'Strategic initiative: {name}',
        'start_date':   open_date.isoformat(),
        'target_date':  fdate(random.randint(30, 180)),
        'budget':       random.randint(5, 200) * 1_000_000,
        'spent':        random.randint(1, 5) * 1_000_000 * (stage_idx+1),
        'priority':     pick(['High','High','Medium','Critical']),
        'milestones':   [{'name': f'Milestone {j+1}', 'due': fdate(j*30),
                           'status': 'completed' if j < stage_idx else 'pending'}
                          for j in range(5)],
        'gates':        gates,
        'kpis':         [{'kpi': 'Cost Savings KES', 'target': random.randint(10,100)*1e6, 'actual': 0}],
        'team_members': [{'staff_code': pick(senior_staff)['code'],
                           'name': pick(senior_staff)['name'], 'role': 'Member'}
                          for _ in range(random.randint(2,5))],
        'risks':        [],
        'last_updated': today.isoformat(),
    })

(DATA/'execute_initiatives.json').write_text(json.dumps(new_initiatives, indent=2))
by_stage = Counter(i.get("current_gate", i.get("gate","?")) for i in new_initiatives)
print(f"  ✅ {len(new_initiatives)} total initiatives: {dict(by_stage)}")

# ══════════════════════════════════════════════════════════════════
# STEP 3: 10 ACCOUNTS PER BRANCH + 5 LOAN CASES THROUGH ALL MODULES
# ══════════════════════════════════════════════════════════════════
print("\n[3/8] Simulating 10 accounts + 5 loans per branch...")

# Build CBS branch_code map
branch_to_code = {}
with open(CBS/'accounts.csv', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        bn = row.get('branch_name','').strip()
        bc = row.get('branch_code','').strip()
        if bn and bc:
            branch_to_code[bn] = bc
            branch_to_code[bn.replace(' Branch','').replace(' Main','').strip()] = bc

CLIENT_NAMES = [
    'Aisha Wanjiku','Brian Otieno','Caroline Muthoni','David Kamau','Esther Njeri',
    'Francis Ochieng','Grace Wambua','Hassan Mwangi','Irene Njoroge','James Kipchoge',
    'Kendi Wairimu','Lucas Odhiambo','Mary Chebet','Nathan Muriuki','Olivia Akinyi',
    'Patrick Maina','Queen Auma','Robert Kariuki','Sarah Omondi','Thomas Gitau',
    'Usha Patel','Victor Mutiso','Winnie Adhiambo','Xavier Ndung\'u','Yasmin Hassan',
    'Zara Abdi','Albert Njogu','Beatrice Waweru','Charles Okeyo','Dorothy Wambui',
]
PRODUCTS_RETAIL = ['Personal Loan','Salary Advance','Asset Finance','Mortgage / Home Loan']
PRODUCTS_MSME   = ['Business Loan','LPO Financing','Invoice Discounting','MSME Working Capital']
PRODUCTS_CORP   = ['Corporate Bond','Import Finance','Trade Finance LC','Project Finance']
ALL_PRODUCTS    = PRODUCTS_RETAIL + PRODUCTS_MSME + PRODUCTS_CORP

new_apps   = list(apps_existing)
new_legal  = json.loads((DATA/'legal_matters.json').read_text())
new_comp   = json.loads((DATA/'compliance_cases.json').read_text())
new_ca     = json.loads((DATA/'credit_admin.json').read_text())
new_fd     = json.loads((DATA/'treasury_fd.json').read_text())

import re as _re
def _max_id(lst):
    nums = [int(m.group()) for item in lst
            for m in [_re.search(r'\d+', item.get('id',''))] if m]
    return max(nums, default=0)
app_counter   = _max_id(new_apps)
legal_counter = _max_id(new_legal)
comp_counter  = _max_id(new_comp)
ca_counter    = _max_id(new_ca)
fd_counter    = _max_id(new_fd)

MATTER_SLA  = {'Security Perfection':14,'Loan Documentation':5,'Title Deed Custody':3,
               'Attorney Instruction':21,'Legal Opinion':7}
MATTER_STEPS= {
    'Security Perfection': ['Instruction received','Title search ordered','Charge instrument drafted',
                             'Client signed','Land registry lodged','Title returned to bank'],
    'Loan Documentation':  ['Instruction received','Facility letter drafted','Client signed',
                             'Bank countersigned','Documents filed'],
    'Title Deed Custody':  ['Deed received','Deed verified','Custody register','Strong room'],
    'Attorney Instruction':['Brief sent','Attorney acknowledges','Opinion issued','File returned'],
    'Legal Opinion':       ['Query received','Research','Opinion drafted','Opinion issued'],
}

processed_branches = 0
for branch in branches[:35]:  # use 35 branches (CBS has data for these)
    bc = branch_to_code.get(branch, '')
    branch_rm = [s for s in rms if s['unit'] == branch]
    if not branch_rm: continue
    processed_branches += 1

    for acct_n in range(10):
        client   = pick(CLIENT_NAMES)
        rm       = pick(branch_rm)
        product  = pick(ALL_PRODUCTS)
        amount   = random.choice([
            random.randint(500_000, 5_000_000),
            random.randint(5_000_000, 50_000_000),
            random.randint(50_000_000, 200_000_000),
        ])
        is_loan  = product in PRODUCTS_MSME + PRODUCTS_RETAIL + PRODUCTS_CORP
        if not is_loan: continue

        # Swim lane
        if amount <= 5_000_000 and random.random() < 0.4:
            lane = 'Express'
        elif amount >= 100_000_000 or product in PRODUCTS_CORP:
            lane = 'Complex'
        else:
            lane = 'Standard'

        # Docs — mix complete and incomplete
        docs_req = ['CRB Report','Bank Statements (6 months)','Business Registration','ID/Passport','KRA PIN']
        if amount > 10e6:   docs_req += ['Audited Accounts','Business Plan']
        if product in PRODUCTS_CORP: docs_req += ['Board Resolution','Memorandum of Association']
        docs_sub = docs_req if acct_n < 7 else docs_req[:-1]  # last 3 are incomplete
        comp_pct = round(len(docs_sub)/len(docs_req)*100, 1)

        # Compliance flag (1 in 10 accounts)
        comp_flag = (acct_n == 9)
        comp_type = pick(['PEP','AML Flag','Unusual Transaction']) if comp_flag else None

        # Status — simulate full pipeline: some go all the way, some stop early
        if acct_n < 3:
            status = pick(['approved','credit_admin','disbursed'])
        elif acct_n < 5:
            status = pick(['analysis','committee'])
        elif acct_n < 7:
            status = pick(['submitted','assigned'])
        else:
            status = pick(['draft','completeness','returned'])

        analyst = pick(credit_ana) if credit_ana and status not in ('draft','submitted','completeness') else None
        decision = None
        if status in ('approved','credit_admin','disbursed'):
            decision = {'verdict':'approved', 'date': rdate(30,1),
                        'authority': pick(['Branch Manager','Chief Credit Officer','Credit Committee']),
                        'conditions': random.sample(['Insurance certificate','Title deed',
                                                      'Board resolution','Legal charge'], k=2),
                        'reason': None, 'comments': ''}
        elif status == 'declined':
            decision = {'verdict':'declined','date': rdate(20,1),
                        'authority':'Chief Credit Officer',
                        'reason': pick(['Insufficient cash flow','Inadequate collateral']),
                        'conditions':[],'comments':''}
        elif status == 'returned':
            decision = {'verdict':'returned','date': rdate(15,1),
                        'authority':'Credit Analyst',
                        'reason': pick(['Missing audited accounts','CRB report outstanding']),
                        'conditions':[],'comments':''}

        app_counter += 1
        app_id = f'LMS{str(app_counter).zfill(5)}'

        new_app = {
            'id': app_id, 'pipeline_deal_id': None,
            'client_name': f'{client} ({branch})', 'client_cif': f'CIF{random.randint(100000,999999)}',
            'product': product, 'amount': amount, 'currency': 'KES',
            'swim_lane': lane, 'status': status,
            'application_date': rdate(90, 5),
            'rm_code': rm['code'], 'rm_name': rm['name'], 'rm_unit': branch,
            'analyst': ({'code': analyst['code'], 'name': analyst['name']} if analyst else None),
            'is_repeat_borrower': random.random() < 0.3,
            'clean_repayment_history': random.random() < 0.7,
            'docs_required': docs_req, 'docs_submitted': docs_sub,
            'completeness_score': comp_pct,
            'compliance_flag': comp_flag, 'compliance_type': comp_type,
            'decision': decision,
            'tat_days': random.randint(1, 35),
            'sla_target_days': 3 if lane=='Express' else 10 if lane=='Standard' else 21,
            'last_updated': rdate(10, 0),
        }
        new_apps.append(new_app)

        # ── Credit Admin for approved apps ─────────────────────────
        if status in ('approved','credit_admin','disbursed'):
            conds = decision.get('conditions',[]) if decision else []
            ca_conds = [{'type': c, 'required': True,
                          'fulfilled': True if status=='disbursed' else random.random()<0.6,
                          'date_set': decision['date'] if decision else rdate(20,1),
                          'date_met': rdate(15,1) if status=='disbursed' or random.random()<0.5 else None,
                          'officer': pick(credit_ana)['name'] if credit_ana else '',
                          'notes': ''} for c in conds]
            all_met = all(c['fulfilled'] for c in ca_conds)
            ca_counter += 1
            new_ca.append({
                'id': f'CA{str(ca_counter).zfill(5)}',
                'application_id': app_id, 'client_name': new_app['client_name'],
                'product': product, 'amount': amount,
                'rm_code': rm['code'], 'rm_name': rm['name'],
                'approval_date': decision['date'] if decision else rdate(20,1),
                'conditions': ca_conds, 'all_conditions_met': all_met,
                'ready_for_disbursement': all_met,
                'disbursed': status == 'disbursed',
                'disbursement_date': rdate(10,1) if status=='disbursed' else None,
                'last_updated': rdate(5,0),
            })

        # ── Legal matter for approved/disbursed ────────────────────
        if status in ('approved','credit_admin','disbursed') and random.random() < 0.8:
            mt_name = pick(['Security Perfection','Loan Documentation','Title Deed Custody'])
            sla_d   = MATTER_SLA[mt_name]
            steps   = MATTER_STEPS[mt_name]
            lo      = pick(legal_off) if legal_off else None
            opened  = rdate(sla_d + random.randint(0,20), 2)
            sla_due = (date.fromisoformat(opened) + timedelta(days=sla_d)).isoformat()
            done_s  = len(steps) if status == 'disbursed' else random.randint(1, len(steps)-1)
            mat_status = 'completed' if done_s == len(steps) else 'in_progress'
            dtsl    = (date.fromisoformat(sla_due) - today).days

            legal_counter += 1
            new_legal.append({
                'id': f'LGL{str(legal_counter).zfill(5)}',
                'matter_type': mt_name, 'status': mat_status,
                'priority': 'Normal', 'opened_date': opened,
                'sla_due_date': sla_due,
                'completed_date': rdate(5,1) if mat_status=='completed' else None,
                'days_elapsed': (today - date.fromisoformat(opened)).days,
                'days_to_sla': dtsl, 'sla_days': sla_d,
                'sla_breached': dtsl < 0 and mat_status != 'completed',
                'sla_kpi': f'{mt_name} TAT',
                'client_name': new_app['client_name'],
                'client_cif': new_app['client_cif'],
                'application_id': app_id,
                'product': product, 'amount': amount,
                'legal_officer': ({'code': lo['code'], 'name': lo['name']} if lo else None),
                'attorney': None, 'attorney_ref': None,
                'steps_total': len(steps), 'steps_completed': done_s,
                'current_step': steps[done_s-1],
                'next_step': steps[done_s] if done_s < len(steps) else None,
                'step_history': [{'step': steps[j], 'status': 'completed',
                                   'date': (date.fromisoformat(opened)+timedelta(days=j*2)).isoformat(),
                                   'officer': lo['name'] if lo else '', 'notes': ''}
                                  for j in range(done_s)],
                'documents': [], 'notes': '', 'last_updated': rdate(3,0),
            })

        # ── Compliance case for flagged accounts ───────────────────
        if comp_flag:
            co = pick(comp_off) if comp_off else None
            comp_counter += 1
            new_comp.append({
                'id': f'COMP{str(comp_counter).zfill(4)}',
                'source': 'loan_application', 'source_ref': app_id,
                'client_name': new_app['client_name'],
                'client_cif': new_app['client_cif'],
                'flag_type': comp_type,
                'risk_level': pick(['High','Critical','Medium']),
                'status': pick(['open','under_review','cleared']),
                'raised_by': rm['name'], 'raised_date': rdate(60,5),
                'assigned_officer': co['name'] if co else '',
                'officer_code': co['code'] if co else '',
                'review_notes': '', 'cleared_date': None,
                'escalated_to': None,
                'documents_required': pick([['SAR Form','Enhanced DD Report'],
                                             ['PEP Declaration','AML questionnaire'],
                                             ['Source of Funds','Board Resolution']]),
                'last_updated': rdate(10,0),
            })

# FD requests for treasury (1 per 3 branches)
for branch in branches[::3]:
    branch_rm = [s for s in rms if s['unit'] == branch]
    if not branch_rm: continue
    rm = pick(branch_rm)
    for _ in range(2):
        tenure = pick([30, 60, 90, 182, 364])
        amount = random.randint(5, 500) * 1_000_000
        prop_r = round(random.uniform(8.5, 13.5), 2)
        fd_counter += 1
        new_fd.append({
            'id': f'FD{str(fd_counter).zfill(4)}',
            'pipeline_deal_id': None,
            'client_name': pick(CLIENT_NAMES) + f' ({branch})',
            'client_cif': f'CIF{random.randint(100000,999999)}',
            'product': f'Fixed Deposit — {tenure} Days',
            'amount': amount, 'currency': 'KES', 'tenure_days': tenure,
            'proposed_rate': prop_r,
            'ratified_rate': round(prop_r + random.uniform(-0.5, 0.25), 2),
            'market_rate_ref': round(random.uniform(9.0, 12.5), 2),
            'status': pick(['pending','approved','booked','counter_offered']),
            'rm_code': rm['code'], 'rm_name': rm['name'], 'rm_unit': branch,
            'submitted_date': rdate(30, 1),
            'ratified_date': rdate(20, 1),
            'treasury_officer': 'Treasury Dealer',
            'counter_rate': None, 'notes': '',
            'booked_date': rdate(10, 1), 'maturity_date': fdate(tenure),
        })

(DATA/'loan_applications.json').write_text(json.dumps(new_apps, indent=2))
(DATA/'credit_admin.json').write_text(json.dumps(new_ca, indent=2))
(DATA/'legal_matters.json').write_text(json.dumps(new_legal, indent=2))
(DATA/'compliance_cases.json').write_text(json.dumps(new_comp, indent=2))
(DATA/'treasury_fd.json').write_text(json.dumps(new_fd, indent=2))

print(f"  ✅ {len(new_apps)} loan applications | {len(new_ca)} credit admin cases")
print(f"  ✅ {len(new_legal)} legal matters | {len(new_comp)} compliance cases")
print(f"  ✅ {len(new_fd)} FD requests | {processed_branches} branches processed")

# ══════════════════════════════════════════════════════════════════
# STEP 4: COMPUTE ACTUALS FROM ALL MODULES
# ══════════════════════════════════════════════════════════════════
print("\n[4/8] Computing actuals from all modules...")

# 4a. From loan_applications: compute per-RM and per-staff credit KPIs
apps_all = new_apps
decided  = [a for a in apps_all if a['status'] in ('approved','declined','returned',
                                                      'credit_admin','disbursed')]

def actuals_from_lms():
    """Returns {staff_code: {kpi_name: value}}"""
    rm_stats = defaultdict(lambda: defaultdict(float))
    for a in apps_all:
        rm = str(a.get('rm_code',''))
        if not rm: continue
        amt = float(a.get('amount',0) or 0)
        prod = str(a.get('product','') or '').lower()
        st   = a.get('status','')
        tat  = float(a.get('tat_days',0) or 0)
        lane = a.get('swim_lane','Standard')

        if st in ('approved','credit_admin','disbursed'):
            if any(x in prod for x in ('personal','salary','mortgage','asset','staff','advance')):
                rm_stats[rm]['Disbursements Retail Loans'] += amt
            elif any(x in prod for x in ('corporate','trade','import','export','bond','project')):
                rm_stats[rm]['Disbursements Corporate Loans'] += amt
            else:
                rm_stats[rm]['Disbursements MSME Loans'] += amt
                rm_stats[rm]['Number of Business Borrowers'] += 1
            rm_stats[rm]['Loan Book Growth'] += amt
            rm_stats[rm]['New Accounts']      += 1

        if a.get('analyst'):
            an_code = str(a['analyst'].get('code',''))
            if an_code:
                if st in ('approved','credit_admin','disbursed'):
                    rm_stats[an_code]['Credit Approval Rate'] += 1
                elif st == 'declined':
                    rm_stats[an_code]['Credit Decline Rate'] += 1
                elif st == 'returned':
                    rm_stats[an_code]['Credit Rework Rate'] += 1
                rm_stats[an_code]['_total_decided'] += 1
                if tat > 0:
                    rm_stats[an_code][f'_tat_{lane}'] += tat
                    rm_stats[an_code][f'_tat_{lane}_n'] += 1

    # Convert rates to percentages
    for sc, kpis in rm_stats.items():
        tot = kpis.get('_total_decided', 0) or 1
        for k in ('Credit Approval Rate','Credit Decline Rate','Credit Rework Rate'):
            if k in kpis:
                kpis[k] = round(kpis[k]/tot*100, 2)
        for lane in ('Express','Standard','Complex'):
            n = kpis.get(f'_tat_{lane}_n', 0)
            if n:
                kpis[f'Credit TAT — {lane} Lane'] = round(kpis[f'_tat_{lane}']/n, 1)

    return {sc: {k:v for k,v in kpis.items() if not k.startswith('_')}
            for sc, kpis in rm_stats.items()}

lms_actuals = actuals_from_lms()
print(f"  LMS actuals: {len(lms_actuals)} staff with credit KPIs")

# 4b. From credit_admin: disbursement TAT per officer
ca_tat = defaultdict(list)
for c in new_ca:
    if c.get('disbursed') and c.get('approval_date') and c.get('disbursement_date'):
        try:
            tat = (date.fromisoformat(c['disbursement_date']) -
                   date.fromisoformat(c['approval_date'])).days
            officer = str(c.get('rm_code',''))
            if officer: ca_tat[officer].append(tat)
        except: pass
for sc, tats in ca_tat.items():
    if tats:
        if sc not in lms_actuals: lms_actuals[sc] = {}
        lms_actuals[sc]['Loan Disbursement TAT'] = round(sum(tats)/len(tats), 1)

# 4c. From legal_matters: SLA compliance per officer
legal_all = new_legal
legal_by_officer = defaultdict(lambda: defaultdict(lambda: {'total':0,'on_time':0}))
for m in legal_all:
    if m['status'] == 'completed':
        lo_code = m.get('legal_officer',{}).get('code','') if m.get('legal_officer') else ''
        if lo_code:
            kpi = m.get('sla_kpi','').replace(' TAT','') if m.get('sla_kpi') else m['matter_type']
            legal_by_officer[lo_code][kpi]['total'] += 1
            if not m.get('sla_breached'):
                legal_by_officer[lo_code][kpi]['on_time'] += 1

legal_kpi_map = {
    'Security Perfection': 'Legal TAT — Security Perfection',
    'Loan Documentation':  'Legal TAT — Loan Documentation',
    'Attorney Instruction':'Legal TAT — External Counsel',
    'Property Valuation Oversight':'Legal TAT — Valuation',
    'Title Deed Custody':  'Legal TAT — Title Deed Custody',
    'Legal Opinion':       'Legal TAT — Legal Opinion',
}
overdue_by_officer = defaultdict(int)
total_by_officer   = defaultdict(int)
for m in legal_all:
    lo_code = m.get('legal_officer',{}).get('code','') if m.get('legal_officer') else ''
    if lo_code:
        total_by_officer[lo_code] += 1
        if m.get('sla_breached'): overdue_by_officer[lo_code] += 1

for lo_code, kpi_data in legal_by_officer.items():
    if lo_code not in lms_actuals: lms_actuals[lo_code] = {}
    for mt_key, kpi_name in legal_kpi_map.items():
        data = kpi_data.get(mt_key, {})
        if data.get('total',0) > 0:
            lms_actuals[lo_code][kpi_name] = pct(data['on_time'], data['total'])
    tot = total_by_officer.get(lo_code, 0)
    if tot:
        lms_actuals[lo_code]['Legal Overdue Rate'] = pct(overdue_by_officer.get(lo_code,0), tot)

print(f"  Legal actuals: {sum(1 for sc,d in lms_actuals.items() if any('Legal' in k for k in d))} officers")

# 4d. From compliance_cases
comp_all  = new_comp
cleared   = sum(1 for c in comp_all if c['status']=='cleared')
escalated = sum(1 for c in comp_all if c['status']=='escalated')
open_n    = sum(1 for c in comp_all if c['status'] in ('open','under_review'))
critical_clear = pct(sum(1 for c in comp_all if c.get('risk_level')=='Critical' and c['status']=='cleared'),
                     sum(1 for c in comp_all if c.get('risk_level')=='Critical'))
high_clear     = pct(sum(1 for c in comp_all if c.get('risk_level')=='High' and c['status']=='cleared'),
                     sum(1 for c in comp_all if c.get('risk_level')=='High'))
comp_actuals_global = {
    'Compliance Case Clearance Rate': pct(cleared, len(comp_all)),
    'Compliance SLA — Critical Cases': critical_clear,
    'Compliance SLA — High Risk Cases': high_clear,
    'Open Compliance Cases': open_n,
    'Compliance Escalation Rate': pct(escalated, len(comp_all)),
}
print(f"  Compliance actuals: {comp_actuals_global}")

# Apply to compliance officers
for co in comp_off:
    if co['code'] not in lms_actuals: lms_actuals[co['code']] = {}
    lms_actuals[co['code']].update(comp_actuals_global)

# 4e. From treasury_fd
fd_all    = new_fd
fd_booked = [r for r in fd_all if r['status'] in ('approved','booked')]
fd_vol    = sum(r['amount'] for r in fd_booked if r['currency']=='KES')
fd_app_rate = pct(len(fd_booked), len(fd_all))
fd_var    = round(sum(abs(r.get('ratified_rate',r['proposed_rate'])-r['market_rate_ref'])
                      for r in fd_booked)/max(len(fd_booked),1), 2)
fd_tat    = round(random.uniform(1.5, 3.5), 1)
treasury_actuals = {
    'FD Ratification Volume':       fd_vol,
    'FD Ratification TAT':          fd_tat,
    'FD Approval Rate':             fd_app_rate,
    'FD Rate Variance vs Market':   fd_var,
    'Net Interest Margin':          round(random.uniform(6.5, 8.5), 2),
}
print(f"  Treasury actuals: vol={fd_vol/1e9:.1f}B, rate={fd_app_rate:.1f}%")
for ts in treasury_s:
    if ts['code'] not in lms_actuals: lms_actuals[ts['code']] = {}
    lms_actuals[ts['code']].update(treasury_actuals)

# ══════════════════════════════════════════════════════════════════
# STEP 5: UPDATE ACTUALS XLSX
# ══════════════════════════════════════════════════════════════════
print("\n[5/8] Updating BSC actuals xlsx...")

act_file = [f for f in sorted(DATA.glob('actuals_*.xlsx'), reverse=True)
            if 'backup' not in f.name][0]

# Backup
shutil.copy2(str(act_file), str(DATA/f'actuals_backup_v2.xlsx'))

wb = openpyxl.load_workbook(str(act_file))
ws = wb.active
hdr = [ws.cell(2,c).value for c in range(1, ws.max_column+1)]
sc_c  = hdr.index('Staff Code')    + 1
kpi_c = hdr.index('KPI')           + 1
ac_c  = hdr.index('YTD_Actual')    + 1
aa_c  = hdr.index('Annual Actual') + 1
tc_c  = hdr.index('Annual Target') + 1
mo_c  = next((i+1 for i,h in enumerate(hdr)
              if h and (str(h).endswith('-25') or str(h).endswith('-26'))), None)
rc_c  = hdr.index('Role')          + 1
uc_c  = hdr.index('Unit')          + 1
nc_c  = hdr.index('Staff Name')    + 1
pc_c  = hdr.index('Pillar')        + 1
wc_c  = hdr.index('Weight')        + 1

# Index existing rows
existing_rows = {}  # (sc, kpi) → row_idx
for r in range(3, ws.max_row+1):
    sc  = str(ws.cell(r, sc_c).value  or '').strip()
    kpi = str(ws.cell(r, kpi_c).value or '').strip()
    if sc and kpi: existing_rows[(sc, kpi)] = r

# Update existing rows + create new ones
updated = created = 0
id_to_kpi_name = {k['id']: k['name'] for p, ks in lib['pillars'].items() for k in ks}
kpi_name_to_meta = {k['name']: k for p, ks in lib['pillars'].items() for k in ks}

# Staff metadata for new rows
staff_meta = {s['code']: s for s in all_staff}

def _write(row_idx, value):
    ws.cell(row_idx, ac_c).value = round(float(value), 2)
    if aa_c: ws.cell(row_idx, aa_c).value = round(float(value), 2)
    if mo_c: ws.cell(row_idx, mo_c).value  = round(float(value), 2)

for sc, kpi_data in lms_actuals.items():
    for kpi_name, value in kpi_data.items():
        if not kpi_name or value == 0: continue
        key = (sc, kpi_name)
        if key in existing_rows:
            _write(existing_rows[key], value)
            updated += 1
        else:
            # Create new row
            sm = staff_meta.get(sc, {})
            if not sm: continue
            km = kpi_name_to_meta.get(kpi_name, {'pillar':'Operational','default_weight':0.05})
            # Find target
            tgt = 0
            if 'Rate' in kpi_name or 'Ratio' in kpi_name:
                tgt = 75.0   # target 75% for rate KPIs
            elif 'TAT' in kpi_name:
                tgt = 5.0    # target 5 days
            elif 'Volume' in kpi_name:
                tgt = 1_000_000_000  # 1B target
            elif 'Open' in kpi_name:
                tgt = 10.0   # target <10 open cases

            new_row = [''] * len(hdr)
            new_row[sc_c-1]  = sc
            new_row[nc_c-1]  = sm.get('name','')
            new_row[rc_c-1]  = sm.get('role','')
            new_row[uc_c-1]  = sm.get('unit','')
            new_row[hdr.index('Category')] = ''
            new_row[hdr.index('Staff Status')] = 'Active'
            new_row[kpi_c-1] = kpi_name
            new_row[pc_c-1]  = km.get('pillar','Operational')
            new_row[wc_c-1]  = km.get('default_weight', 0.05)
            new_row[tc_c-1]  = float(tgt)
            new_row[ac_c-1]  = round(float(value), 2)
            if aa_c:  new_row[aa_c-1]  = round(float(value), 2)
            if mo_c:  new_row[mo_c-1]  = round(float(value), 2)
            ws.append(new_row)
            existing_rows[key] = ws.max_row
            created += 1

# Also update initiative count from new initiatives
active_ini = [i for i in new_initiatives if i.get('status')=='Active']
owner_counts = Counter(i.get('owner_code','') for i in active_ini)
for sc, count in owner_counts.items():
    key = (sc, 'Active Initiatives Count')
    if key in existing_rows:
        _write(existing_rows[key], count)
        updated += 1

wb.save(str(act_file))
total_r2 = ws.max_row - 2
scoreable2 = sum(1 for r in range(3, ws.max_row+1)
                 if ws.cell(r,1).value
                 and float(ws.cell(r,tc_c).value or 0) > 0
                 and float(ws.cell(r,ac_c).value or 0) > 0)
print(f"  ✅ Updated: {updated}, Created: {created}")
print(f"  ✅ BSC: {scoreable2:,}/{total_r2:,} rows scoreable ({pct(scoreable2,total_r2):.1f}%)")

# ══════════════════════════════════════════════════════════════════
# STEP 6: INJECT CASCADE TARGETS FOR NEW KPIs
# ══════════════════════════════════════════════════════════════════
print("\n[6/8] Injecting cascade targets for new KPIs...")

import sys, importlib
sys.path.insert(0, '.')
try:
    from unittest.mock import MagicMock
    for mod in ['streamlit','plotly','plotly.express','plotly.graph_objects']:
        sys.modules[mod] = MagicMock()
    import utils.actuals_engine as ae
    importlib.reload(ae)
    result = ae.inject_cascade_targets(act_file)
    print(f"  ✅ inject_cascade_targets: {result} rows updated")
except Exception as e:
    print(f"  ⚠️  inject_cascade_targets: {e}")

# ══════════════════════════════════════════════════════════════════
# STEP 7: COMPUTE BSC SCORES
# ══════════════════════════════════════════════════════════════════
print("\n[7/8] Computing BSC scores per staff...")

def bsc_score(pct_val, is_reverse=False):
    p = pct_val
    if p is None: return None
    if is_reverse: p = min(p, 200)  # cap
    thresholds = [(130,5.0),(120,4.5),(110,4.0),(100,3.5),(91,3.0),(61,2.5),(51,2.0),(31,1.5)]
    for thresh, score in thresholds:
        if p >= thresh: return score
    return 1.0

wb3 = openpyxl.load_workbook(str(act_file))
ws3 = wb3.active
hdr3= [ws3.cell(2,c).value for c in range(1, ws3.max_column+1)]
sc3  = hdr3.index('Staff Code')    + 1
kpi3 = hdr3.index('KPI')           + 1
tc3  = hdr3.index('Annual Target') + 1
ac3  = hdr3.index('YTD_Actual')    + 1
rc3  = hdr3.index('Role')          + 1
wt3  = hdr3.index('Weight')        + 1

REVERSE_KPIS = {'NPL Ratio','PAR','Credit Rework Rate','Credit Decline Rate',
                'Legal Overdue Rate','Open Compliance Cases','Compliance Escalation Rate',
                'FD Rate Variance vs Market','Loan Disbursement TAT',
                'Credit TAT — Express Lane','Credit TAT — Standard Lane',
                'Credit TAT — Complex Lane','FD Ratification TAT',
                'Account Dormancy','Channel Dormancy','Cost-to-Income Ratio'}

staff_scores = defaultdict(lambda: {'kpis':[],'role':'','unit':''})
for row in ws3.iter_rows(min_row=3, values_only=True):
    if not row[0]: continue
    sc  = str(row[sc3-1] or '')
    kpi = str(row[kpi3-1] or '')
    tgt = float(row[tc3-1] or 0)
    act = float(row[ac3-1] or 0)
    wt  = float(row[wt3-1] or 0.05)
    role= str(row[rc3-1] or '')
    if not sc or tgt == 0 or act == 0: continue
    is_rev = kpi in REVERSE_KPIS or any(x in kpi.lower() for x in ('npl','dormancy','overdue','rework'))
    ach    = (tgt/act*100 if is_rev else act/tgt*100)
    score  = bsc_score(ach, is_rev)
    staff_scores[sc]['kpis'].append({'kpi':kpi,'ach':ach,'score':score,'weight':wt})
    staff_scores[sc]['role']  = role
    staff_scores[sc]['unit']  = str(row[hdr3.index('Unit')] if 'Unit' in hdr3 else '')

final_scores = {}
for sc, data in staff_scores.items():
    kpis = [k for k in data['kpis'] if k['score'] is not None]
    if not kpis: continue
    total_wt   = sum(k['weight'] for k in kpis)
    wtd_score  = sum(k['score'] * k['weight'] for k in kpis) / max(total_wt, 0.01)
    final_scores[sc] = {
        'final_score': round(wtd_score, 2),
        'role':        data['role'],
        'n_kpis':      len(kpis),
        'avg_ach':     round(sum(k['ach'] for k in kpis)/len(kpis), 1),
    }

print(f"  ✅ BSC scores computed for {len(final_scores)} staff")
score_dist = Counter(round(s['final_score']) for s in final_scores.values())
print(f"  Score distribution: {dict(sorted(score_dist.items()))}")

# ══════════════════════════════════════════════════════════════════
# STEP 8: VERIFY HIERARCHY AND MODULE CROSS-TALK
# ══════════════════════════════════════════════════════════════════
print("\n[8/8] Verifying hierarchy and module cross-talk...")

# Check MD score
md_code2 = '300001'
md_score  = final_scores.get(md_code2, {})
print(f"  MD score: {md_score.get('final_score','?')} ({md_score.get('n_kpis','?')} KPIs, avg ach {md_score.get('avg_ach','?')}%)")

# Check credit team
credit_scored = [(sc,s) for sc,s in final_scores.items()
                 if 'Credit' in s['role'] or 'Analyst' in s['role']]
print(f"  Credit team scored: {len(credit_scored)} staff")

# Check legal team
legal_scored = [(sc,s) for sc,s in final_scores.items()
                if 'Legal' in s['role'] or 'Company Secretary' in s['role']]
print(f"  Legal team scored: {len(legal_scored)} staff")

# Pipeline → LMS linkage
apps_all2 = json.loads((DATA/'loan_applications.json').read_text())
pip_linked = sum(1 for a in apps_all2 if a.get('pipeline_deal_id'))
print(f"  Pipeline→LMS links: {pip_linked}/{len(apps_all2)}")

# LMS → Legal
legal_all2 = json.loads((DATA/'legal_matters.json').read_text())
legal_linked = sum(1 for m in legal_all2 if m.get('application_id'))
print(f"  LMS→Legal links:    {legal_linked}/{len(legal_all2)}")

# LMS → Compliance
comp_all2 = json.loads((DATA/'compliance_cases.json').read_text())
comp_linked = sum(1 for c in comp_all2 if c.get('source_ref','').startswith('LMS'))
print(f"  LMS→Compliance:     {comp_linked}/{len(comp_all2)}")

# Bank-level KPIs
bank_kpis = {
    'Total Applications': len(apps_all2),
    'Approved':           sum(1 for a in apps_all2 if a['status'] in ('approved','credit_admin','disbursed')),
    'Disbursed':          sum(1 for a in apps_all2 if a['status']=='disbursed'),
    'Legal Matters':      len(legal_all2),
    'Compliance Cases':   len(comp_all2),
    'FD Requests':        len(json.loads((DATA/'treasury_fd.json').read_text())),
    'Initiatives':        len(new_initiatives),
}
print(f"\n  Bank-level summary:")
for k,v in bank_kpis.items():
    print(f"    {k:<30} {v:>6}")

# Save final scores
(DATA/'feb_2026_staff_scores.json').write_text(json.dumps(final_scores, indent=2))
print(f"\n  ✅ Scores saved to feb_2026_staff_scores.json")
print(f"\n{'='*60}")
print(f"SIMULATION COMPLETE")
print(f"{'='*60}")
