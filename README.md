# A2Z MIS 360 — Ecobank Kenya

**Banking management information system built on Oracle FLEXCUBE 12.**

A2Z MIS 360 (codenamed A2Z Blueprint) is a full-scale performance and MIS platform for Ecobank Kenya: 700K customers, 35 branches, 232 RMs, 487 staff. It covers balanced scorecards, CRM pipeline, CBS data exploration, target cascade, KPI library management, risk analytics, and ~100 specialized modules from teller daily log to MD command centre.

**Version:** v10.496 (December 2025) · Master Prompt v5.40 · 413 audit gates passing

> ⚠️ **For external testers:** this is a demo build on simulated CBS data. No production data, no real customer records. The login scheme is deterministic for testing only — see "Test credentials" below.

---

## 🏗 Stack

A2Z MIS 360 runs two parallel frontends against a shared Python backend:

- **Streamlit** (existing, primary) — the full ~100-module app. Used today by Ecobank Kenya internally.
- **React + Vite + Tailwind** (in progress) — a modern SPA frontend being built out under Phase 3. Currently ships Dashboard + Showcase pages; full feature parity is being delivered version by version.
- **Backend:** Python 3.11+, FastAPI, Pandas/NumPy, Plotly
- **Storage:** JSON files by default, PostgreSQL backend toggleable per table via `A2Z_DB_BACKEND`
- **Auth:** Session-based today; JWT (v10.497) and OAuth2 in progress
- **Core banking:** Reads from Oracle FLEXCUBE 12 (simulated in dev via in-process CBS data generator)

---

## 🚀 Getting started

### Prerequisites

- **Python 3.11+** (3.12 recommended)
- **Node 18+** and **pnpm 8+** for the React frontend (install pnpm with `npm install -g pnpm`)
- **Git**

### 1. Clone and install backend (Streamlit + Python)

```bash
git clone https://github.com/Joshua-Mokua/A2Z-Blueprint.git
cd A2Z-Blueprint

# Create and activate a virtual environment
python -m venv .venv

# Windows (CMD)
.venv\Scripts\activate.bat
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Configure environment

```bash
# Copy the env template and fill in any local overrides
cp .env.example .env
# Windows: copy .env.example .env
```

The defaults work for local dev — leave most values blank. Only `A2Z_JWT_SECRET` becomes important once v10.497 ships JWT auth. See `.env.example` for full documentation of each variable.

### 3. Seed demo data

```bash
# Generate the simulated CBS data + staff register
python generate_cbs.py
python generate_staff.py
python compute_actuals.py
```

This creates `cbs_data/`, `data/staff_register.xlsx`, `data/actuals_2025_Dec_25.xlsx`, and `data/users.json` (the demo user database). All four are gitignored — they live only in your local copy.

### 4. Run the Streamlit app

```bash
streamlit run app.py
```

Open **http://localhost:8501** in your browser. The login page loads first.

### 5. Run the React frontend (optional, separate terminal)

```bash
cd frontend/web
pnpm install
pnpm dev
```

Open **http://localhost:5173/** (Dashboard) or **http://localhost:5173/components** (Design System Showcase).

The React side currently runs against the FastAPI backend on port 8000. Start the API in a third terminal with:

```bash
# From the project root
uvicorn utils.api:app --reload --port 8000
```

---

## 🔑 Test credentials

Demo logins use a deterministic password scheme: **`EcoStaff` + last 4 digits of the staff code**.

| Role | Username | Password |
|------|----------|----------|
| MD (Managing Director) | `olive001` | `EcoStaff0001` |
| Director Retail Banking | `william002` | `EcoStaff0002` |
| Branch Manager (sample) | `branch_mgr_001` | `EcoStaff` + last 4 of staff code |
| RO PB (sample) | `ro_pb_001` | (same pattern) |

The full user list is in your local `data/users.json` after running `generate_staff.py`. Browse it to find usernames for any role you want to test.

> ⚠️ These credentials work only on simulated data in your local install. They unlock nothing real. v10.497 introduces hashed passwords (bcrypt) and JWT-signed sessions, after which these plaintext patterns go away.

---

## 📁 Project structure

```
A2Z-Blueprint/
├── app.py                       # Streamlit entry point
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variable template
│
├── utils/                       # Backend modules
│   ├── core.py                  # Managers (User, Cascade, KPI, etc.)
│   ├── auth_jwt.py              # JWT auth (v10.497+)
│   ├── api.py                   # FastAPI app
│   └── ...                      # ~150 specialized engines (CBS, risk, IT, treasury…)
│
├── pages/                       # Streamlit pages (~100 modules)
│   ├── 1_perform.py             # BSC scorecard
│   ├── 3_pipeline.py            # CRM pipeline
│   ├── 7_admin.py               # Admin + KPI library
│   ├── 12_cascade.py            # Target cascade
│   ├── 15_cbs.py                # CBS explorer
│   └── ...
│
├── frontend/web/                # React SPA (parallel frontend, in progress)
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/Dashboard.tsx
│   │   ├── pages/Showcase.tsx   # Design system primitives
│   │   └── components/          # Design system (Button, Card, Input, etc.)
│   ├── package.json
│   └── pnpm-lock.yaml
│
├── tests/                       # Pytest suite (897 integration tests, growing)
├── scripts/audit.py             # G128 audit gate (mechanical quality enforcement)
└── docs/                        # Architecture & deployment docs
    ├── DEPLOYMENT_GUIDE.md
    ├── SECURITY_ARCHITECTURE.md
    ├── DR_RUNBOOK.md
    └── Master_Prompt_v5.40.md   # Current development context
```

Generated data and backups (`data/actuals_*.xlsx`, `cbs_data/`, `data/users.json`, `data/_v*_backups/`) are gitignored — they're produced locally by the seed scripts.

---

## 📊 BSC scoring scale

The Balanced Scorecard uses a 1.0–5.0 score band derived from achievement percentages:

| Achievement | Score | Band |
|-------------|-------|------|
| < 30% | 1.0 | Unmet |
| 30–50% | 1.5 | Unmet |
| 50–60% | 2.0 | Unmet |
| 60–90% | 2.5 | Partially met |
| 90–100% | 3.0 | Met |
| 100–110% | 3.5 | Exceeded |
| 110–120% | 4.0 | Exceeded |
| 120–130% | 4.5 | Exceeded |
| > 130% | 5.0 | Exceeded by far |

Weights default to 40% Financial, 25% Customer Focus, 25% Operational Excellence, 10% People & Learning — configurable per role in `data/kpi_library.json`.

---

## 🔒 Security notes for testers

- This build runs on simulated CBS data. No production records.
- Local data files (`data/users.json`, `data/actuals_*.xlsx`, `cbs_data/`) are gitignored.
- Default JWT secret is intentionally weak for dev — a warning logs at startup. Production deployments must set `A2Z_JWT_SECRET`.
- CORS in dev allows `localhost:5173` (Vite) and `localhost:8501` (Streamlit). Production deployments must set `A2Z_CORS_ORIGINS` to explicit production hostnames; wildcard `*` is rejected at startup (V-009 guard).
- See `docs/SECURITY_ARCHITECTURE.md` for the full threat model.

---

## 🧪 Running tests

```bash
# Full integration suite
pytest tests/integration/ -v

# Audit gate (mechanical quality enforcement, 413 gates)
python scripts/audit.py
```

Audit must pass before any release. Integration suite currently at ~900 tests.

---

## 🐛 Known caveats (v10.496)

- React frontend ships only Dashboard + Showcase so far. Other modules are accessible via Streamlit only — feature parity is being built version by version.
- JWT auth is scaffolded but session-based auth is still the active path. v10.497 wires JWT into the login flow end-to-end.
- CBS auto-loads from `data/actuals_*.xlsx` on startup. Manual BSC Excel upload works as override only.
- Some branch roles (BOS, Teller in specific branches) may be missing from generated staff data — this gets fixed as part of the next data-quality batch.

---

## 📚 Further reading

- `docs/Master_Prompt_v5.40.md` — current development context and architectural decisions
- `docs/DEPLOYMENT_GUIDE.md` — production deployment
- `docs/SECURITY_ARCHITECTURE.md` — auth, encryption, audit trail
- `docs/API_REFERENCE.md` — REST API contract
- `docs/USER_MANUAL_STAFF.md` — end-user guide

---

## 🙋 Reporting issues

For testers: log issues with reproduction steps and the build version (visible bottom-left of any Streamlit page, or in `package.json` for the React side). Include the role you logged in as — many behaviours are role-gated.

---

*A2Z MIS 360 · Ecobank Kenya · v10.496 · Built on Oracle FLEXCUBE 12*
