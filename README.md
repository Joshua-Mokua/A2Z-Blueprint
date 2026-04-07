# A2Z Blueprint — Perform · Execute · Integrate

**Ecobank Kenya Performance Management System**

A full-stack Streamlit application connecting bank strategy to individual execution — from MD board pack to teller daily log.

---

## 📋 Modules (17 total)

| Module | Description |
|--------|-------------|
| 🏆 Perform | BSC scorecard, rankings, individual view, validation |
| 🏦 SBU Performance | Branch P&L, turnaround tracker, action plans |
| 📉 Operating Leverage | CIR analysis, industry benchmarking, turnaround |
| 🎯 Target Cascade | MD→Director→Manager→Staff target allocation |
| 👥 People & HR | Leave, exits, disciplinary, PIP, diligence scores |
| 💼 Pipeline | CRM deal board, revenue intelligence |
| ⚡ Execute | G0–G5 initiative gates, milestones, ideation |
| 🏷️ Products | Product lifecycle registry |
| 🔗 Integrate | MD command centre — P&L, people, pipeline, signals |
| 🔍 Competitor Intel | 39-bank Kenya industry analysis |
| 🎯 SLA Tracker | Service level tracking, CX scoring |
| 📝 Branch Daily Log | Daily activity submission and validation |
| 🏦 Branch Optimizer | Staff mix, revenue efficiency, network comparison |
| 💰 Commission | DSO/RM tier-based commissions, leaderboard |
| 🚀 Campaigns | Campaign lifecycle management |
| ⚙️ Admin | Users, reporting lines, org tree, upload guide |
| 📥 Export | PDF and Excel export |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11 or higher
- pip

### Installation

```powershell
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/a2z-blueprint.git
cd a2z-blueprint

# 2. Create virtual environment
python -m venv .venv

# 3. Activate it (Windows PowerShell)
.venv\Scripts\Activate.ps1

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run the application
streamlit run app.py
```

### First login
- Username: `admin`
- Password: `admin123`
- Change your password immediately after first login

### Uploading data
Upload `A2Z_Blueprint_Data_v2.xlsx` from the sidebar after logging in.

---

## 📁 Project structure

```
a2z-blueprint/
├── app.py                    # Entry point — navigation
├── requirements.txt          # Python dependencies
├── README.md
├── .gitignore
├── utils/
│   └── core.py               # Data managers, constants, helpers
├── pages/
│   ├── _shared.py            # Shared session state loader
│   ├── _sidebar.py           # File upload sidebar
│   ├── _login.py             # Authentication
│   ├── 1_perform.py          # BSC Scorecard
│   ├── 2_people.py           # HR module
│   ├── 3_pipeline.py         # CRM Pipeline
│   ├── 4_execute.py          # Strategy execution
│   ├── 5_products.py         # Product registry
│   ├── 6_integrate.py        # MD command centre
│   ├── 7_admin.py            # Administration
│   ├── 8_export.py           # Export
│   ├── 9_sbu.py              # SBU Performance
│   ├── 10_opex.py            # Operating leverage
│   ├── 11_competitor.py      # Competitor intelligence
│   ├── 12_cascade.py         # Target cascade
│   ├── 13_sla.py             # SLA Tracker
│   ├── 14_branch_log.py      # Branch daily log
│   ├── 15_optimize.py        # Branch optimizer
│   ├── 16_commission.py      # Commission model
│   └── 17_campaigns.py       # Campaign management
└── data/                     # Auto-created, gitignored — local only
```

---

## ⚙️ Configuration

The system uses local JSON files in `/data/` for all records (PIPs, leave, SLA tickets etc.). These are **gitignored** and never committed — each installation has its own data.

Users are managed via `data/users.json` — created automatically on first run.

---

## 🔒 Security notes

- Never commit the `data/` folder — it contains staff records
- Never commit Excel files — they contain bank financial data  
- The `.gitignore` is configured to block both automatically
- Change the default admin password immediately after deployment

---

## 📊 BSC scoring scale

| Achievement | Score | Band |
|-------------|-------|------|
| < 30% | 1.0 | Unmet |
| 30–50% | 1.5 | Unmet |
| 50–60% | 2.0 | Unmet |
| 60–90% | 2.5 | Partially Met |
| 90–100% | 3.0 | Met |
| 100–110% | 3.5 | Exceeded |
| 110–120% | 4.0 | Exceeded |
| 120–130% | 4.5 | Exceeded |
| > 130% | 5.0 | Exceeded By Far |

---

## 🏦 Stack

- **Frontend/App:** [Streamlit](https://streamlit.io) 1.29+
- **Data:** Pandas, NumPy
- **Charts:** Plotly Express + Graph Objects
- **Storage:** Local JSON files (no database required)
- **Auth:** Custom session-based authentication

---

*Ecobank Kenya | Performance Management System | v1.0*
