"""
Core Banking Simulation Generator — Ecobank Kenya
Produces: customers.csv, accounts.csv, transactions.csv (sample), branches.json, portfolio_map.csv
700,000 customers | 1.1M accounts | realistic Kenyan demographics
"""
import csv, json, random, sqlite3, os
from datetime import date, timedelta, datetime
from pathlib import Path

random.seed(42)
# Output folder sits next to this script — works on Windows and Mac/Linux
OUT = Path(__file__).parent / "cbs_data"
OUT.mkdir(exist_ok=True)

# ─── KENYAN NAME POOLS ────────────────────────────────────────────────
FIRST_NAMES_M = [
    "James","John","Peter","David","Paul","Joseph","Michael","Patrick","Francis","Daniel",
    "Samuel","Philip","George","Charles","Robert","William","Thomas","Richard","Edward","Henry",
    "Kevin","Dennis","Eric","Stephen","Brian","Victor","Felix","Moses","Aaron","Simon",
    "Emmanuel","Kenneth","Leonard","Alex","Mark","Anthony","Benedict","Calvin","Dominic","Edwin",
    "Festus","Gilbert","Harold","Isaac","Joel","Keith","Lawrence","Martin","Nathan","Oscar",
    "Phillip","Quentin","Raymond","Solomon","Timothy","Usman","Vincent","Walter","Xavier","Yusuf",
    "Zachary","Abiud","Baraka","Caleb","Derek","Elijah","Frank","Geoffrey","Hassan","Ishmael",
    "Julius","Kelvin","Levi","Maurice","Nicholas","Oliver","Pius","Quince","Rodgers","Stanley",
]
FIRST_NAMES_F = [
    "Mary","Grace","Faith","Ann","Rose","Jane","Susan","Patricia","Elizabeth","Catherine",
    "Agnes","Beatrice","Charity","Diana","Esther","Florence","Gloria","Hannah","Irene","Joyce",
    "Karen","Lydia","Margaret","Nancy","Olive","Priscilla","Queen","Rebecca","Sarah","Teresa",
    "Ursula","Violet","Winnie","Yvonne","Zipporah","Alice","Bernadette","Caroline","Daisy","Ellen",
    "Fatuma","Gladys","Harriet","Ida","Jacqueline","Kezia","Lilian","Miriam","Naomi","Olivia",
    "Pauline","Rachael","Stella","Tabitha","Unique","Veronica","Wanjiku","Xenia","Yasmin","Zainab",
    "Aisha","Brenda","Cynthia","Dorcas","Eunice","Felicia","Georgina","Helena","Isabella","Janet",
    "Kemunto","Lucy","Mildred","Njeri","Otieno","Peninah","Ruth","Sharon","Tina","Uma",
]
SURNAMES = [
    "Kamau","Odhiambo","Wanjiku","Mwangi","Otieno","Kariuki","Mutua","Njoroge","Akinyi","Ochieng",
    "Kiprotich","Chebet","Langat","Ruto","Koech","Bett","Sang","Kemboi","Chepkemoi","Mutai",
    "Waweru","Ngugi","Githu","Gicheru","Kabui","Njenga","Ndegwa","Mungai","Murage","Kinyanjui",
    "Ouma","Ogolla","Okello","Anyango","Adhiambo","Awino","Auma","Odongo","Omondi","Owino",
    "Hassan","Omar","Abdullahi","Mohamed","Ali","Sheikh","Issa","Abdi","Farah","Maalim",
    "Mwenda","Kithinji","Kirimi","Murithi","Njue","Mugambi","Karithi","Gakunju","Micheni","Ntiba",
    "Wafula","Simiyu","Barasa","Masinde","Wekesa","Khaemba","Nasambu","Nekesa","Nafula","Khisa",
    "Mwamba","Mwanzia","Munyao","Ndeti","Musyoka","Mutiso","Muema","Nzuki","Matheka","Mbatha",
    "Shimba","Mwanake","Katana","Kazungu","Ngumbao","Sidi","Mwaburi","Karisa","Baya","Charo",
    "Onyango","Okeyo","Achola","Awuor","Aluoch","Omolo","Odero","Oguda","Obiero","Asande",
]
BIZ_TYPES = ["Limited","Ltd","& Co","Enterprises","Holdings","Group","Associates","Brothers",
             "Sisters","Family","Solutions","Services","Trading","Investments","Properties",
             "Supplies","Agency","Ventures","Industries","Consultants"]
BIZ_PREFIX = ["Nairobi","Kenya","East Africa","Summit","Excel","Prime","Alpha","Beta","Delta",
              "Phoenix","Eagle","Lion","Savanna","Acacia","Baobab","Kilimanjaro","Serengeti",
              "Maasai","Heritage","Sunrise","Horizon","Pioneer","Vision","Future","Unity",
              "Green","Blue","Golden","Royal","Imperial","National","Capital","Metro","Urban",]

# ─── BRANCHES ────────────────────────────────────────────────────────
BRANCHES = [
    # Format: (branch_code, branch_name, region, county, town, type, tier)
    # Tier: 1=flagship, 2=main, 3=standard, 4=light
    ("BRN001","Head Office","Nairobi","Nairobi","Nairobi CBD","HO",1),
    ("BRN002","Upper Hill Branch","Nairobi","Nairobi","Upper Hill","Flagship",1),
    ("BRN003","Westlands Branch","Nairobi","Nairobi","Westlands","Flagship",1),
    ("BRN004","Sarit Centre Branch","Nairobi","Nairobi","Westlands","Main",2),
    ("BRN005","Industrial Area Branch","Nairobi","Nairobi","Industrial Area","Main",2),
    ("BRN006","Karen Branch","Nairobi","Nairobi","Karen","Standard",3),
    ("BRN007","Eastleigh Branch","Nairobi","Nairobi","Eastleigh","Standard",3),
    ("BRN008","Gigiri Branch","Nairobi","Nairobi","Gigiri","Standard",3),
    ("BRN009","Mombasa Road Branch","Nairobi","Nairobi","South B","Standard",3),
    ("BRN010","Thika Road Mall Branch","Nairobi","Nairobi","Roysambu","Standard",3),
    ("BRN011","Mombasa Main Branch","Coastal","Mombasa","Mombasa CBD","Flagship",1),
    ("BRN012","Nyali Branch","Coastal","Mombasa","Nyali","Main",2),
    ("BRN013","Diani Branch","Coastal","Kwale","Diani","Standard",3),
    ("BRN014","Malindi Branch","Coastal","Kilifi","Malindi","Standard",3),
    ("BRN015","Kisumu Main Branch","Nyanza","Kisumu","Kisumu CBD","Flagship",1),
    ("BRN016","Kisumu Mega Branch","Nyanza","Kisumu","Kisumu","Main",2),
    ("BRN017","Migori Branch","Nyanza","Migori","Migori","Standard",3),
    ("BRN018","Homabay Branch","Nyanza","Homabay","Homabay","Standard",3),
    ("BRN019","Nakuru Main Branch","Rift Valley","Nakuru","Nakuru CBD","Flagship",1),
    ("BRN020","Nakuru West Branch","Rift Valley","Nakuru","Nakuru West","Main",2),
    ("BRN021","Eldoret Main Branch","Rift Valley","Uasin Gishu","Eldoret","Flagship",1),
    ("BRN022","Kitale Branch","Rift Valley","Trans Nzoia","Kitale","Main",2),
    ("BRN023","Bungoma Branch","Western","Bungoma","Bungoma","Main",2),
    ("BRN024","Kakamega Branch","Western","Kakamega","Kakamega","Standard",3),
    ("BRN025","Kisii Main Branch","Nyanza","Kisii","Kisii CBD","Main",2),
    ("BRN026","Nyeri Branch","Central","Nyeri","Nyeri","Standard",3),
    ("BRN027","Thika Branch","Central","Kiambu","Thika","Main",2),
    ("BRN028","Kikuyu Branch","Central","Kiambu","Kikuyu","Standard",3),
    ("BRN029","Meru Branch","Eastern","Meru","Meru","Standard",3),
    ("BRN030","Embu Branch","Eastern","Embu","Embu","Standard",3),
    ("BRN031","Machakos Branch","Eastern","Machakos","Machakos","Standard",3),
    ("BRN032","Kitui Branch","Eastern","Kitui","Kitui","Light",4),
    ("BRN033","Garissa Branch","North Eastern","Garissa","Garissa","Light",4),
    ("BRN034","Wajir Branch","North Eastern","Wajir","Wajir","Light",4),
    ("BRN035","Lamu Branch","Coastal","Lamu","Lamu","Light",4),
]

# Branch customer capacity by tier (approx distribution)
BRANCH_WEIGHTS = {1: 0.12, 2: 0.06, 3: 0.025, 4: 0.008}

# ─── SEGMENTS ────────────────────────────────────────────────────────
IND_SEGMENTS = [
    ("Individual","Affluent",0.05),
    ("Individual","Core Middle",0.25),
    ("Individual","Mass / Retail",0.50),
]
BIZ_SEGMENTS = [
    ("Business","Large Corporate",0.02),
    ("Business","Corporate",0.04),
    ("Business","SME",0.08),
    ("Business","Micro Enterprise",0.06),
]
ALL_SEGMENTS = IND_SEGMENTS + BIZ_SEGMENTS

IND_SECTORS = [
    "Salaried — Civil Servant / Government",
    "Salaried — Private Sector",
    "Salaried — NGO / International Organisation",
    "Self-Employed Professional",
    "Teacher / Lecturer",
    "Military / Police / Uniformed Services",
    "Small Business Owner",
    "Farmer / Agri-preneur",
    "Landlord / Property Owner",
    "Student",
    "Retired",
    "Housewife / Homemaker",
    "Diaspora / Returning Resident",
]
BIZ_SECTORS = [
    "Agriculture, Forestry & Fishing","Mining & Quarrying","Manufacturing",
    "Electricity, Gas & Water Supply","Building & Construction",
    "Trade (Wholesale & Retail)","Tourism, Restaurant & Hotels",
    "Transport & Communication","Real Estate & Business Services",
    "Financial Services","Community, Social & Personal Services",
    "Government & Public Sector","Non-Profit / NGO",
]

# ─── PRODUCTS / ACCOUNT TYPES ────────────────────────────────────────
ACCOUNT_TYPES = [
    # (code, name, category, currency, min_balance, typical_balance_range)
    ("CASA001","Current Account","CASA","KES",0,(5000,5000000)),
    ("CASA002","Savings Account","CASA","KES",1000,(1000,500000)),
    ("CASA003","Salary Account","CASA","KES",0,(10000,300000)),
    ("CASA004","Junior Account","CASA","KES",500,(500,50000)),
    ("CASA005","Business Current Account","CASA","KES",0,(50000,50000000)),
    ("CASA006","Business Savings Account","CASA","KES",5000,(5000,10000000)),
    ("TERM001","Fixed Deposit — 30 Days","Term Deposit","KES",50000,(50000,5000000)),
    ("TERM002","Fixed Deposit — 90 Days","Term Deposit","KES",50000,(50000,10000000)),
    ("TERM003","Fixed Deposit — 180 Days","Term Deposit","KES",100000,(100000,20000000)),
    ("TERM004","Fixed Deposit — 364 Days","Term Deposit","KES",100000,(100000,50000000)),
    ("TERM005","Call Deposit","Term Deposit","KES",500000,(500000,100000000)),
    ("LOAN001","Personal Loan","Loan","KES",0,(100000,3000000)),
    ("LOAN002","Business Loan","Loan","KES",0,(500000,50000000)),
    ("LOAN003","Mortgage / Home Loan","Loan","KES",0,(2000000,30000000)),
    ("LOAN004","Overdraft Facility","Loan","KES",0,(100000,5000000)),
    ("LOAN005","Asset Finance","Loan","KES",0,(500000,20000000)),
    ("LOAN006","LPO Finance","Loan","KES",0,(200000,10000000)),
    ("FCASA01","USD Current Account","CASA","USD",0,(1000,500000)),
    ("FCASA02","GBP Savings","CASA","GBP",0,(500,100000)),
    ("FTERM01","USD Fixed Deposit","Term Deposit","USD",10000,(10000,1000000)),
]

# Segment → likely account types (weights)
SEG_PRODUCT_WEIGHTS = {
    "Affluent":        {"CASA001":2,"CASA002":1,"TERM003":2,"TERM004":2,"LOAN003":1,"LOAN002":1,"FCASA01":1,"FTERM01":1},
    "Core Middle":     {"CASA001":3,"CASA002":2,"CASA003":2,"TERM001":1,"TERM002":1,"LOAN001":1},
    "Mass / Retail":   {"CASA002":3,"CASA003":3,"CASA004":1,"LOAN001":1},
    "Large Corporate": {"CASA005":3,"CASA006":1,"TERM004":2,"TERM005":2,"LOAN002":2,"LOAN004":1,"FCASA01":2,"FTERM01":1},
    "Corporate":       {"CASA005":3,"CASA006":1,"TERM003":1,"TERM004":1,"LOAN002":2,"LOAN004":1,"FCASA01":1},
    "SME":             {"CASA005":3,"CASA006":1,"TERM001":1,"LOAN002":2,"LOAN004":1,"LOAN006":1},
    "Micro Enterprise":{"CASA005":2,"CASA002":1,"LOAN002":1,"LOAN006":1},
}

CURRENCIES = {"KES":"KES","USD":"USD","GBP":"GBP","EUR":"EUR"}

# ─── STAFF / PORTFOLIO ALLOCATION ────────────────────────────────────
# Loaded from the BSC file — we'll use a representative set
# Branch staff: RM-type roles get portfolios
BRANCH_RM_ROLES = [
    "Relationship Officer Personal Banking",
    "Relationship Officer Business Banking",
    "Direct Sales Officer",
    "Branch Credit Manager",
    "Branch Manager",
]
HO_RM_ROLES = [
    "Relationship Manager Corporate",
    "Relationship Manager SME",
    "Head Of Corporate",
    "Head Of SME",
]

# Simulate 217 staff from the BSC data across 35 branches
# We'll generate realistic staff codes and distribute
print("Building branch & staff reference data...")

# Distribute staff across branches realistically
STAFF_POOL = []
staff_counter = 300001
roles_by_branch = [
    # (role, count_per_main_branch, count_per_light_branch)
    ("Branch Manager",1,1),
    ("Branch Operations Manager",1,1),
    ("Branch Credit Manager",1,0),
    ("Branch Operations Supervisor",1,0),
    ("Relationship Officer Personal Banking",2,1),
    ("Relationship Officer Business Banking",1,0),
    ("Direct Sales Officer",2,1),
    ("Customer Service Officer",2,1),
    ("Teller",3,1),
]

for brn_code,brn_name,region,county,town,brn_type,tier in BRANCHES:
    if brn_code == "BRN001":  # HO — skip branch roles
        continue
    for role, cnt_main, cnt_light in roles_by_branch:
        count = cnt_light if tier == 4 else cnt_main
        for _ in range(count):
            STAFF_POOL.append({
                "staff_code": str(staff_counter),
                "role": role,
                "branch_code": brn_code,
                "branch_name": brn_name,
                "region": region,
            })
            staff_counter += 1

# HO RMs
for role in ["Relationship Manager Corporate","Relationship Manager SME"]:
    for _ in range(5):
        STAFF_POOL.append({
            "staff_code": str(staff_counter),
            "role": role,
            "branch_code": "BRN001",
            "branch_name": "Head Office",
            "region": "All",
        })
        staff_counter += 1

RM_ROLES_ALL = set(BRANCH_RM_ROLES + HO_RM_ROLES)
RM_STAFF = [s for s in STAFF_POOL if s["role"] in RM_ROLES_ALL]
print(f"  Total staff: {len(STAFF_POOL)} | RMs: {len(RM_STAFF)}")

# Save branch reference
with open(OUT/"branches.json","w") as f:
    json.dump([{
        "branch_code":b[0],"branch_name":b[1],"region":b[2],
        "county":b[3],"town":b[4],"branch_type":b[5],"tier":b[6]
    } for b in BRANCHES], f, indent=2)
print("  ✅ branches.json written")

# ─── CIF & CUSTOMER GENERATION ───────────────────────────────────────
print("\nGenerating 700,000 customers...")
N_CUSTOMERS = 700_000
TODAY = date(2025, 12, 31)
BASE_DATE = date(2005, 1, 1)

def random_date(start, end):
    return start + timedelta(days=random.randint(0,(end-start).days))

def kenyan_phone():
    prefix = random.choice(["0700","0711","0722","0733","0740","0757","0768","0790","0110","0114"])
    return prefix + "".join([str(random.randint(0,9)) for _ in range(6)])

def id_number():
    return str(random.randint(10000000, 43000000))

def biz_reg():
    types = ["PVT","CPY","NGO","CBO","LLP"]
    return f"{random.choice(types)}-{random.randint(100000,999999)}"

# Build CIF sequence
CIF_START = 100000001

# Compute branch weights for customer distribution
branch_weights_list = []
total_w = 0
for b in BRANCHES:
    tier = b[6]
    w = BRANCH_WEIGHTS[tier]
    # HO has no retail customers
    if b[0] == "BRN001": w = 0
    branch_weights_list.append(w)
    total_w += w
branch_probs = [w/total_w for w in branch_weights_list]

# Segment probabilities
seg_names = [s[1] for s in ALL_SEGMENTS]
seg_types  = [s[0] for s in ALL_SEGMENTS]
seg_probs  = [s[2] for s in ALL_SEGMENTS]
seg_total  = sum(seg_probs)
seg_probs  = [p/seg_total for p in seg_probs]

def pick_segment():
    r = random.random()
    cumul = 0
    for i,(n,t,p) in enumerate(zip(seg_names,seg_types,seg_probs)):
        cumul += p
        if r <= cumul: return t, n
    return "Individual","Mass / Retail"

def pick_branch():
    r = random.random()
    cumul = 0
    for i,p in enumerate(branch_probs):
        cumul += p
        if r <= cumul: return BRANCHES[i]
    return BRANCHES[-1]

# Write customers CSV
cust_fields = [
    "cif","full_name","customer_type","segment","sub_segment","sector",
    "id_type","id_number","phone","email","date_of_birth","gender",
    "nationality","kra_pin","date_onboarded","kyc_status","kyc_expiry",
    "risk_rating","branch_code","branch_name","region","county",
    "relationship_manager_code","is_dormant_customer","last_activity_date",
    "preferred_currency","total_deposit_balance","total_loan_balance",
    "total_accounts","aml_flag","fatf_flag","pep_flag","deceased",
]

# Track RM → customer list for portfolio
rm_portfolio: dict = {s["staff_code"]: [] for s in RM_STAFF}
branch_rms: dict = {}  # branch_code → list of RM staff_codes
for s in RM_STAFF:
    branch_rms.setdefault(s["branch_code"], []).append(s["staff_code"])

# HO RMs handle cross-branch corporate
ho_rms = [s["staff_code"] for s in RM_STAFF if s["branch_code"]=="BRN001"]

with open(OUT/"customers.csv","w",newline="",encoding="utf-8") as cf:
    writer = csv.DictWriter(cf, fieldnames=cust_fields)
    writer.writeheader()

    for i in range(N_CUSTOMERS):
        cif = str(CIF_START + i)
        branch = pick_branch()
        branch_code, branch_name, region, county, town, btype, tier = branch

        cust_type, sub_seg = pick_segment()
        is_biz = cust_type == "Business"

        # Name
        if is_biz:
            full_name = (random.choice(BIZ_PREFIX)+" "+random.choice(SURNAMES)+" "+
                         random.choice(BIZ_TYPES))
            gender = "N/A"
            dob = ""
            id_type = "Company Reg No"
            id_num = biz_reg()
            sector = random.choice(BIZ_SECTORS)
        else:
            gender = random.choice(["Male","Female"])
            fname  = random.choice(FIRST_NAMES_M if gender=="Male" else FIRST_NAMES_F)
            sname  = random.choice(SURNAMES)
            full_name = f"{fname} {sname}"
            age = random.randint(18,72)
            dob = str(TODAY - timedelta(days=age*365+random.randint(0,364)))
            id_type = random.choice(["National ID","Passport"] if age>18 else ["National ID"])
            id_num  = id_number()
            sector  = random.choice(IND_SECTORS)

        kra = "A"+str(random.randint(1000000,9999999))+"X"
        phone = kenyan_phone()
        email = (full_name.split()[0].lower() + str(random.randint(10,99)) +
                 "@" + random.choice(["gmail.com","yahoo.com","outlook.com","hotmail.com","ke.ecobank.com"]))
        onboarded = random_date(BASE_DATE, TODAY)
        last_active = random_date(onboarded, TODAY)
        days_inactive = (TODAY - last_active).days
        is_dormant_cust = 1 if days_inactive > 180 else 0

        kyc_status = random.choices(["Verified","Pending","Expired"], weights=[0.85,0.10,0.05])[0]
        kyc_expiry = str(last_active + timedelta(days=random.choice([365,730,1095])))

        risk = random.choices(["Low","Medium","High","Very High"], weights=[0.60,0.28,0.10,0.02])[0]
        nationality = random.choices(
            ["Kenyan","Ugandan","Tanzanian","Rwandan","Ethiopian","South Sudanese","Other"],
            weights=[0.88,0.04,0.03,0.01,0.01,0.01,0.02])[0]

        # Assign RM
        if sub_seg in ("Large Corporate","Corporate") and ho_rms:
            rm_code = random.choice(ho_rms)
        elif branch_code in branch_rms and branch_rms[branch_code]:
            rm_code = random.choice(branch_rms[branch_code])
        elif RM_STAFF:
            rm_code = random.choice(RM_STAFF)["staff_code"]
        else:
            rm_code = "UNASSIGNED"

        if rm_code in rm_portfolio:
            rm_portfolio[rm_code].append(cif)

        row = {
            "cif": cif,
            "full_name": full_name,
            "customer_type": cust_type,
            "segment": cust_type,
            "sub_segment": sub_seg,
            "sector": sector,
            "id_type": id_type,
            "id_number": id_num,
            "phone": phone,
            "email": email,
            "date_of_birth": dob,
            "gender": gender,
            "nationality": nationality,
            "kra_pin": kra,
            "date_onboarded": str(onboarded),
            "kyc_status": kyc_status,
            "kyc_expiry": kyc_expiry,
            "risk_rating": risk,
            "branch_code": branch_code,
            "branch_name": branch_name,
            "region": region,
            "county": county,
            "relationship_manager_code": rm_code,
            "is_dormant_customer": is_dormant_cust,
            "last_activity_date": str(last_active),
            "preferred_currency": "KES",
            "total_deposit_balance": 0,  # updated after accounts
            "total_loan_balance": 0,
            "total_accounts": 0,
            "aml_flag": 1 if risk=="Very High" else 0,
            "fatf_flag": 0,
            "pep_flag": random.choices([0,1],[0.99,0.01])[0],
            "deceased": random.choices([0,1],[0.998,0.002])[0],
        }
        writer.writerow(row)

        if (i+1) % 100000 == 0:
            print(f"  {i+1:,} customers...")

print("  ✅ customers.csv written")

# Save portfolio map
print("\nWriting portfolio_map.csv...")
with open(OUT/"portfolio_map.csv","w",newline="") as pf:
    pw = csv.writer(pf)
    pw.writerow(["staff_code","branch_code","cif_count"])
    for s in RM_STAFF:
        sc = s["staff_code"]
        bc = s["branch_code"]
        cnt = len(rm_portfolio.get(sc,[]))
        pw.writerow([sc, bc, cnt])
print("  ✅ portfolio_map.csv written")

# ─── ACCOUNTS GENERATION ─────────────────────────────────────────────
print("\nGenerating accounts...")
ACCT_MAP = {a[0]:a for a in ACCOUNT_TYPES}
ACC_NUM_COUNTER = [1000000001]

def next_acc():
    n = ACC_NUM_COUNTER[0]
    ACC_NUM_COUNTER[0] += 1
    return f"ECO{n:010d}"

acct_fields = [
    "account_number","cif","branch_code","branch_name","region",
    "account_type_code","account_type_name","category","currency",
    "date_opened","maturity_date","interest_rate",
    "current_balance","available_balance","hold_amount",
    "account_status","dormancy_status","days_since_last_txn",
    "last_transaction_date","last_transaction_amount","last_transaction_type",
    "relationship_manager_code","overdraft_limit","loan_amount","loan_outstanding",
    "loan_disbursement_date","loan_maturity","npl_status","npl_days",
    "collateral_type","collateral_value","interest_income_ytd","fee_income_ytd",
]

total_accts = 0
cust_balances: dict = {}  # cif → {deposits:0, loans:0, accts:0}

# Re-read customers to generate accounts (streaming — don't hold 700K in RAM)
print("  Streaming customers for account generation...")
with open(OUT/"customers.csv","r",encoding="utf-8") as cf, \
     open(OUT/"accounts.csv","w",newline="",encoding="utf-8") as af:
    reader = csv.DictReader(cf)
    writer = csv.DictWriter(af, fieldnames=acct_fields)
    writer.writeheader()

    for i, cust in enumerate(reader):
        cif = cust["cif"]
        sub_seg = cust["sub_segment"]
        bc = cust["branch_code"]
        bn = cust["branch_name"]
        reg = cust["region"]
        rm = cust["relationship_manager_code"]
        onboarded = date.fromisoformat(cust["date_onboarded"])
        is_dormant = int(cust["is_dormant_customer"])

        # How many accounts?
        n_accts = random.choices([1,2,3,4,5],
            weights=[0.40,0.28,0.17,0.10,0.05])[0]

        # Pick account types based on segment
        wts = SEG_PRODUCT_WEIGHTS.get(sub_seg, {"CASA002":3,"CASA003":2})
        pool = list(wts.keys())
        wt   = list(wts.values())
        chosen = []
        for _ in range(n_accts):
            pick = random.choices(pool, weights=wt)[0]
            if pick not in chosen:
                chosen.append(pick)
            if len(chosen) >= len(pool):
                break

        dep_bal = 0; loan_bal = 0
        for at_code in chosen:
            if at_code not in ACCT_MAP: continue
            _,at_name,cat,currency,min_bal,(bal_lo,bal_hi) = ACCT_MAP[at_code]
            acct_num = next_acc()

            opened = random_date(onboarded, TODAY)
            _dorm_end = min(TODAY, onboarded+timedelta(days=180))
            last_txn= random_date(opened, TODAY) if not is_dormant else random_date(opened, _dorm_end if _dorm_end > opened else opened+timedelta(days=1))
            days_stale = (TODAY - last_txn).days

            dormant = "Dormant" if days_stale > 180 else "Active"
            status  = random.choices(["Active","Frozen","Closed"],
                weights=[0.93,0.04,0.03])[0]
            if is_dormant and status == "Active": status = "Active"  # keep open

            bal = round(random.uniform(max(0,bal_lo*0.1), bal_hi), 2) if status=="Active" else round(random.uniform(0,5000),2)
            if sub_seg in ("Large Corporate","Corporate"): bal *= random.uniform(3,15)
            if sub_seg == "Affluent": bal *= random.uniform(1.5,5)
            bal = round(bal, 2)

            hold = round(bal * random.uniform(0,0.05), 2) if random.random()<0.1 else 0
            avail = max(0, bal - hold)

            # Loan fields
            is_loan = cat == "Loan"
            loan_amt = bal if is_loan else 0
            loan_outs= round(loan_amt * random.uniform(0.1,0.95),2) if is_loan else 0
            npl = "NPL" if is_loan and days_stale>90 and random.random()<0.12 else "Performing"
            npl_days = days_stale if npl=="NPL" else 0
            disb = str(opened) if is_loan else ""
            mat  = str(opened+timedelta(days=random.choice([365,730,1095,1460]))) if is_loan else ""
            mat_td = str(opened+timedelta(days=random.choice([30,90,180,364,730]))) if cat=="Term Deposit" else ""
            collat_type = random.choice(["Land Title","Motor Vehicle","Shares","Cash Deposit","Guarantor","None"]) if is_loan else ""
            collat_val  = round(loan_amt*random.uniform(1.1,2.5),2) if is_loan and collat_type!="None" else 0
            odlimit = round(bal*random.uniform(0.5,2),2) if at_code=="LOAN004" else 0
            rate = round(random.uniform(0.12,0.18),4) if is_loan else (round(random.uniform(0.08,0.13),4) if cat=="Term Deposit" else round(random.uniform(0.025,0.07),4))
            int_ytd = round(loan_outs*rate*random.uniform(0.1,1),2) if is_loan else round(bal*rate*random.uniform(0.1,1),2)
            fee_ytd = round(random.uniform(500,50000),2)

            last_txn_amt  = round(random.uniform(-500000,500000),2) if not is_loan else 0
            last_txn_type = random.choice(["Debit","Credit"]) if not is_loan else "Repayment"

            writer.writerow({
                "account_number":acct_num,"cif":cif,
                "branch_code":bc,"branch_name":bn,"region":reg,
                "account_type_code":at_code,"account_type_name":at_name,
                "category":cat,"currency":currency,
                "date_opened":str(opened),"maturity_date":mat_td,
                "interest_rate":rate,
                "current_balance":round(bal,2),"available_balance":round(avail,2),"hold_amount":hold,
                "account_status":status,"dormancy_status":dormant,"days_since_last_txn":days_stale,
                "last_transaction_date":str(last_txn),"last_transaction_amount":last_txn_amt,
                "last_transaction_type":last_txn_type,
                "relationship_manager_code":rm,
                "overdraft_limit":odlimit,"loan_amount":loan_amt,"loan_outstanding":loan_outs,
                "loan_disbursement_date":disb,"loan_maturity":mat,
                "npl_status":npl,"npl_days":npl_days,
                "collateral_type":collat_type,"collateral_value":collat_val,
                "interest_income_ytd":int_ytd,"fee_income_ytd":fee_ytd,
            })
            total_accts += 1
            if cat in ("CASA","Term Deposit"): dep_bal += bal
            if is_loan: loan_bal += loan_outs

        cust_balances[cif] = {"dep":round(dep_bal,2),"loan":round(loan_bal,2),"accts":len(chosen)}

        if (i+1) % 100000 == 0:
            print(f"  {i+1:,} customers processed → {total_accts:,} accounts...")

print(f"  ✅ accounts.csv written — {total_accts:,} total accounts")

# ─── SAMPLE TRANSACTIONS (last 90 days, 50K records) ─────────────────
print("\nGenerating sample transactions (50,000 records for last 90 days)...")
TXN_TYPES = [
    ("MPESA IN","Credit","M-Pesa"),("MPESA OUT","Debit","M-Pesa"),
    ("ATM WITHDRAWAL","Debit","ATM"),("CASH DEPOSIT","Credit","Branch"),
    ("CASH WITHDRAWAL","Debit","Branch"),("CHEQUE DEPOSIT","Credit","Branch"),
    ("STANDING ORDER","Debit","System"),("SALARY CREDIT","Credit","RTGS"),
    ("INTER ACCOUNT TRANSFER","Credit","Core Banking"),("SWIFT IN","Credit","SWIFT"),
    ("SWIFT OUT","Debit","SWIFT"),("UTILITY PAYMENT","Debit","Bill Pay"),
    ("LOAN REPAYMENT","Debit","Core Banking"),("LOAN DISBURSEMENT","Credit","Core Banking"),
    ("INTEREST CREDIT","Credit","System"),("FEE DEBIT","Debit","System"),
    ("REVERSAL","Credit","System"),("RTGS IN","Credit","RTGS"),
    ("RTGS OUT","Debit","RTGS"),("POS","Debit","POS"),
]
TXN_CHANNELS = ["Mobile Banking","Internet Banking","Branch","ATM","Agent","SWIFT","RTGS","System"]

txn_fields = [
    "txn_id","account_number","cif","branch_code","txn_date","txn_time",
    "value_date","txn_type","txn_channel","amount","currency","dr_cr",
    "balance_after","narrative","reference","status","reversal","initiator",
]

# Read a sample of account numbers for transactions
sample_accounts = []
with open(OUT/"accounts.csv","r",encoding="utf-8") as af:
    ar = csv.DictReader(af)
    for row in ar:
        if row["account_status"]=="Active" and row["category"] in ("CASA","Term Deposit"):
            sample_accounts.append((row["account_number"],row["cif"],row["branch_code"],row["currency"]))
        if len(sample_accounts) >= 200000:
            break

TXN_START = date(2025,10,2)
txn_id_counter = [800000001]

def next_txn():
    n = txn_id_counter[0]; txn_id_counter[0]+=1
    return f"TXN{n:010d}"

with open(OUT/"transactions_sample.csv","w",newline="",encoding="utf-8") as tf:
    tw = csv.DictWriter(tf, fieldnames=txn_fields)
    tw.writeheader()
    for _ in range(50000):
        acc = random.choice(sample_accounts)
        acc_no, cif, bc, curr = acc
        txn_date = random_date(TXN_START, TODAY)
        txn_type, dr_cr, channel_hint = random.choice(TXN_TYPES)
        channel = random.choice(TXN_CHANNELS)
        amount = round(random.lognormvariate(9, 2), 2)  # log-normal for realistic amounts
        amount = min(max(amount,100), 5000000)
        bal_after = round(random.uniform(0, 2000000), 2)
        tw.writerow({
            "txn_id": next_txn(),
            "account_number": acc_no,
            "cif": cif,
            "branch_code": bc,
            "txn_date": str(txn_date),
            "txn_time": f"{random.randint(8,17):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}",
            "value_date": str(txn_date + timedelta(days=random.choice([0,1]))),
            "txn_type": txn_type,
            "txn_channel": channel,
            "amount": amount,
            "currency": curr,
            "dr_cr": dr_cr,
            "balance_after": bal_after,
            "narrative": f"{txn_type} - {random.choice(['Payment','Transfer','Purchase','Deposit','Withdrawal'])}",
            "reference": f"REF{random.randint(10000000,99999999)}",
            "status": random.choices(["Completed","Reversed","Pending"],[0.95,0.03,0.02])[0],
            "reversal": random.choices(["N","Y"],[0.97,0.03])[0],
            "initiator": random.choice(["Customer","System","Branch Staff","HO"]),
        })
print("  ✅ transactions_sample.csv written — 50,000 records")

# ─── BRANCH & RM SUMMARY INDEX FILES ────────────────────────────────
print("\nBuilding summary index files...")

branch_stats = {}
with open(OUT/"accounts.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        bc  = row["branch_code"]
        cat = row["category"]
        bal = float(row["current_balance"] or 0)
        loan= float(row["loan_outstanding"] or 0)
        npl = row["npl_status"]
        status = row["account_status"]
        if bc not in branch_stats:
            branch_stats[bc] = {"deposit_bal":0,"loan_bal":0,"npl_bal":0,
                                  "acct_count":0,"loan_count":0,
                                  "dormant_count":0,"active_count":0}
        s = branch_stats[bc]
        s["acct_count"] += 1
        if cat in ("CASA","Term Deposit"): s["deposit_bal"] += bal
        if cat == "Loan": s["loan_bal"] += loan; s["loan_count"] += 1
        if npl == "NPL":  s["npl_bal"]  += loan
        if status == "Active": s["active_count"] += 1
        else: s["dormant_count"] += 1

with open(OUT/"branch_summary.json","w") as f:
    json.dump(branch_stats, f)
print("  ✅ branch_summary.json")

rm_stats = {}
with open(OUT/"accounts.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        rm  = row["relationship_manager_code"]
        cat = row["category"]
        bal = float(row["current_balance"] or 0)
        loan= float(row["loan_outstanding"] or 0)
        if rm not in rm_stats:
            rm_stats[rm] = {"deposit_bal":0,"loan_bal":0,
                             "acct_count":0,"customer_count":0,"npl_bal":0}
        rm_stats[rm]["acct_count"] += 1
        if cat in ("CASA","Term Deposit"): rm_stats[rm]["deposit_bal"] += bal
        if cat == "Loan":                  rm_stats[rm]["loan_bal"]    += loan

cust_rm = {}
with open(OUT/"customers.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        rm = row["relationship_manager_code"]
        cust_rm.setdefault(rm, set()).add(row["cif"])
for rm, cifs in cust_rm.items():
    if rm in rm_stats:
        rm_stats[rm]["customer_count"] = len(cifs)

with open(OUT/"rm_portfolio_summary.json","w") as f:
    json.dump(rm_stats, f)
print(f"  ✅ rm_portfolio_summary.json ({len(rm_stats)} RMs)")

total_dep  = sum(v["deposit_bal"] for v in branch_stats.values())
total_loan = sum(v["loan_bal"]    for v in branch_stats.values())
total_npl  = sum(v["npl_bal"]     for v in branch_stats.values())
print(f"  Deposits: KES {total_dep/1e9:.1f}B | Loans: KES {total_loan/1e9:.1f}B | NPL: {total_npl/max(total_loan,1)*100:.1f}%")

# ─── SUMMARY STATS ────────────────────────────────────────────────────
print("\n" + "="*60)
print("CORE BANKING SIMULATION — SUMMARY")
print("="*60)
print(f"Customers:     {N_CUSTOMERS:>12,}")
print(f"Accounts:      {total_accts:>12,}")
print(f"Transactions:  {50000:>12,}  (90-day sample)")
print(f"Branches:      {len(BRANCHES):>12,}")
print(f"Total RM staff:{len(RM_STAFF):>12,}")
print()
print("Output files:")
for f in sorted(OUT.iterdir()):
    size = f.stat().st_size
    print(f"  {f.name:<35} {size/1024/1024:6.1f} MB")
print("="*60)
