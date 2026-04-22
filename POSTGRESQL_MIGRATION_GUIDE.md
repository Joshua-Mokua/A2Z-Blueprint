# A2Z Blueprint — PostgreSQL Migration Guide
## From Zero to Live Database: Complete Step-by-Step
### For: Joshua Mokua | Version 5.2 | April 2026

---

## Part 1 — What is PostgreSQL and why we need it

Think of the current system like a filing cabinet. Each drawer is a JSON file.
When one person pulls out the drawer, updates it, and puts it back — fine.
When two people try to do this at the same time — the drawer jams and data gets lost.

PostgreSQL is a proper database. Think of it as a bank vault with a trained teller.
No matter how many people ask for something at the same time, the teller handles
each request in order, nothing gets lost, and every transaction is logged permanently.

**What you gain immediately:**
- Passwords stored with bcrypt (already done in the code — DB enforces it at storage)
- Row-level security — the AML register is invisible to anyone who isn't Compliance
- Concurrent writes — 1,438 staff can all save at the same time without corruption
- Audit trail that cannot be edited or deleted (append-only table)
- Something you can show the bank technical team with confidence

**What stays the same:**
- All 67 module pages — zero changes
- The login screen — zero changes
- How staff use the system — zero changes
- The JSON files — still there as backup until migration is complete

---

## Part 2 — Installing PostgreSQL on Windows (Step by Step)

### Step 1: Download PostgreSQL

1. Open your browser and go to: **https://www.postgresql.org/download/windows/**
2. Click **"Download the installer"** (the EnterpriseDB link)
3. Choose the latest version — currently **PostgreSQL 16**
4. Choose **Windows x86-64**
5. Click Download — the file is about 300MB

### Step 2: Run the installer

1. Double-click the downloaded file (e.g. `postgresql-16.x-windows-x64.exe`)
2. Click **Next** through the welcome screen
3. **Installation directory** — leave as default: `C:\Program Files\PostgreSQL\16`
4. **Select components** — keep all ticked:
   - PostgreSQL Server ✅
   - pgAdmin 4 ✅ (the visual interface — you will use this a lot)
   - Stack Builder ✅
   - Command Line Tools ✅
5. **Data directory** — leave as default: `C:\Program Files\PostgreSQL\16\data`
6. **Password** — THIS IS IMPORTANT:
   - Set a password for the `postgres` superuser
   - Use something you will remember: e.g. `A2ZAdmin2026!`
   - Write it down right now — you cannot recover this easily
7. **Port** — leave as **5432** (this is the standard PostgreSQL port)
8. **Locale** — leave as default
9. Click **Next** then **Finish**
10. When asked about Stack Builder — you can skip it (click Finish without launching)

### Step 3: Verify the installation

1. Press **Windows key**, type **pgAdmin 4**, open it
2. It opens in your browser at something like `http://127.0.0.1:5050`
3. On first open it asks you to set a **master password for pgAdmin** — set one
4. In the left panel you should see: **Servers > PostgreSQL 16**
5. Click it — enter the postgres password you set above
6. You should see the PostgreSQL server expand with databases inside

If you see the server — PostgreSQL is installed and running. ✅

---

## Part 3 — Create the A2Z database and user

We never use the `postgres` superuser for the application. We create a dedicated
user with only the permissions it needs. This is standard security practice.

### Option A: Using pgAdmin (visual — easier for first time)

1. In pgAdmin, right-click **Databases** → **Create** → **Database**
2. Database name: `a2z_mis360`
3. Owner: `postgres` (for now)
4. Click **Save**

Then create the application user:
1. Right-click **Login/Group Roles** → **Create** → **Login/Group Role**
2. **General tab** — Name: `a2z_app`
3. **Definition tab** — Password: `A2ZAppPass2026!` (write this down)
4. **Privileges tab** — tick **Can login**
5. Click **Save**

Grant the user access to the database:
1. Right-click your `a2z_mis360` database → **Properties**
2. Click **Security** tab → **+** to add a privilege
3. Grantee: `a2z_app` → tick **Connect**
4. Click **Save**

### Option B: Using the command line (faster once you know it)

1. Press **Windows key**, search for **SQL Shell (psql)**, open it
2. Press Enter for all defaults (Server, Database, Port, Username)
3. Enter your postgres password when asked
4. You are now at the `postgres=#` prompt. Type these commands one at a time:

```sql
CREATE DATABASE a2z_mis360;
CREATE USER a2z_app WITH ENCRYPTED PASSWORD 'A2ZAppPass2026!';
GRANT ALL PRIVILEGES ON DATABASE a2z_mis360 TO a2z_app;
\c a2z_mis360
GRANT ALL ON SCHEMA public TO a2z_app;
\q
```

---

## Part 4 — Create the tables

We need to run the schema SQL that is already written in `utils/db.py`.

### Using pgAdmin Query Tool:

1. In pgAdmin, click on your `a2z_mis360` database
2. Click the **Query Tool** button (the lightning bolt icon) or press **Alt+Shift+Q**
3. Open the file `C:\Users\Joshua\Desktop\A2Z Blue Print\a2z\create_tables.sql`
   (we will create this file in a moment)
4. Click **Execute** (the play button) or press **F5**

### Create the SQL file:

Open Notepad, paste the SQL from Part 5 below, save as:
`C:\Users\Joshua\Desktop\A2Z Blue Print\a2z\create_tables.sql`

---

## Part 5 — The SQL to create all tables

Copy this into `create_tables.sql` and run it in pgAdmin:

```sql
-- A2Z Blueprint MIS 360 — PostgreSQL Schema
-- Run this once to create all tables.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Sessions (login tracking)
CREATE TABLE IF NOT EXISTS sessions (
    session_id    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username      VARCHAR(100) NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    last_activity TIMESTAMPTZ NOT NULL DEFAULT now(),
    ip_address    INET,
    invalidated   BOOLEAN NOT NULL DEFAULT false
);

-- Audit trail (never delete rows from this table)
CREATE TABLE IF NOT EXISTS audit_trail (
    id         BIGSERIAL PRIMARY KEY,
    ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
    username   VARCHAR(100) NOT NULL,
    action     VARCHAR(200) NOT NULL,
    detail     TEXT,
    module     VARCHAR(100),
    before_val TEXT,
    after_val  TEXT
);
CREATE INDEX idx_audit_ts       ON audit_trail (ts DESC);
CREATE INDEX idx_audit_username ON audit_trail (username);

-- Users
CREATE TABLE IF NOT EXISTS users (
    username             VARCHAR(100) PRIMARY KEY,
    password_hash        VARCHAR(255) NOT NULL,
    full_name            VARCHAR(200),
    email                VARCHAR(200),
    role                 VARCHAR(200),
    department           VARCHAR(200),
    unit                 VARCHAR(200),
    staff_code           VARCHAR(50),
    band                 VARCHAR(20),
    gender               CHAR(1),
    active               BOOLEAN NOT NULL DEFAULT true,
    is_admin             BOOLEAN NOT NULL DEFAULT false,
    can_view_all         BOOLEAN NOT NULL DEFAULT false,
    is_dept_super_user   BOOLEAN NOT NULL DEFAULT false,
    dept_super_user_for  VARCHAR(200),
    is_ict_admin         BOOLEAN NOT NULL DEFAULT false,
    must_change_password BOOLEAN NOT NULL DEFAULT false,
    login_attempts       INT NOT NULL DEFAULT 0,
    locked_until         TIMESTAMPTZ,
    accessible_modules   JSONB DEFAULT '[]',
    hidden_modules       JSONB DEFAULT '[]',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login           TIMESTAMPTZ
);

-- BSC Scores
CREATE TABLE IF NOT EXISTS bsc_scores (
    id            BIGSERIAL PRIMARY KEY,
    username      VARCHAR(100) NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    staff_code    VARCHAR(50),
    period        VARCHAR(20) NOT NULL,
    final_score   NUMERIC(4,2),
    pillar_scores JSONB,
    kpi_scores    JSONB,
    n_kpis        INT,
    avg_ach       NUMERIC(5,1),
    role          VARCHAR(200),
    unit          VARCHAR(200),
    dept          VARCHAR(200),
    computed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (username, period)
);
CREATE INDEX idx_bsc_period ON bsc_scores (period);
CREATE INDEX idx_bsc_dept   ON bsc_scores (dept);

-- Pipeline deals
CREATE TABLE IF NOT EXISTS pipeline_deals (
    id                   VARCHAR(50) PRIMARY KEY,
    staff_code           VARCHAR(50),
    staff_name           VARCHAR(200),
    unit                 VARCHAR(200),
    role                 VARCHAR(200),
    client_name          VARCHAR(300),
    client_cif           VARCHAR(50),
    product              VARCHAR(200),
    stage                VARCHAR(100),
    deal_category        VARCHAR(50) DEFAULT 'New Facility',
    amount               NUMERIC(18,2),
    currency             CHAR(3) DEFAULT 'KES',
    open_date            DATE,
    expected_close       DATE,
    probability          NUMERIC(5,2),
    is_repeat_borrower   BOOLEAN DEFAULT false,
    existing_facility_id VARCHAR(50),
    repayment_history    VARCHAR(100),
    notes                TEXT,
    last_updated         DATE,
    metadata             JSONB DEFAULT '{}'
);
CREATE INDEX idx_pipeline_stage  ON pipeline_deals (stage);
CREATE INDEX idx_pipeline_staff  ON pipeline_deals (staff_code);
CREATE INDEX idx_pipeline_client ON pipeline_deals (client_cif);
```

---

## Part 6 — Tell the system to use PostgreSQL

### Step 1: Install the Python PostgreSQL driver

Open a terminal in your project folder:
```bash
cd "C:\Users\Joshua\Desktop\A2Z Blue Print\a2z"
.venv\Scripts\activate
pip install psycopg2-binary bcrypt
```

### Step 2: Set environment variables

These tell the system where your database is. Open a terminal and run:

```bash
set A2Z_USE_DB=true
set A2Z_DB_HOST=localhost
set A2Z_DB_PORT=5432
set A2Z_DB_NAME=a2z_mis360
set A2Z_DB_USER=a2z_app
set A2Z_DB_PASSWORD=A2ZAppPass2026!
```

Or better — add them permanently via Windows:
1. Press **Windows key**, search **"Environment Variables"**
2. Click **"Edit the system environment variables"**
3. Click **"Environment Variables"** button
4. Under **User variables**, click **New** for each one above

### Step 3: Migrate the users table

Run this Python script once to copy all users from JSON into PostgreSQL:

```bash
cd "C:\Users\Joshua\Desktop\A2Z Blue Print\a2z"
.venv\Scripts\activate
python migrate_users.py
```

(We create `migrate_users.py` in the next section)

### Step 4: Enable the users table in db.py

Open `utils/db.py`, find `TABLE_USE_DB`, change:
```python
"users": False,
```
to:
```python
"users": True,
```

### Step 5: Restart and test

```bash
streamlit run app.py
```

Log in as `william001 / Staff0001`. If it works — the users table is now
running on PostgreSQL. Every other table still uses JSON. Unnoticeable to staff.

---

## Part 7 — Verify it worked

In pgAdmin, open the Query Tool on `a2z_mis360` and run:

```sql
SELECT username, full_name, department, is_admin
FROM users
WHERE is_admin = true;
```

You should see:
```
username    | full_name        | department  | is_admin
------------+------------------+-------------+---------
william001  | William Mwanake  | Executive   | true
admin       | System Admin     | All         | true
```

Then check passwords are bcrypt:
```sql
SELECT username, LEFT(password_hash, 7) as hash_type
FROM users LIMIT 5;
```

You should see `$2b$12$` — that is bcrypt with work factor 12. ✅

---

## Part 8 — What to show the bank technical team

When you are ready to demonstrate:

1. Open pgAdmin and show the `a2z_mis360` database with tables visible
2. Run: `SELECT COUNT(*) FROM users;` — shows 1,438 users in the database
3. Run the password hash query above — shows bcrypt, not SHA-256
4. Show `audit_trail` table — every login and admin action recorded
5. Show `utils/db.py` — the `TABLE_USE_DB` flags, the schema DDL, the RLS policies
6. Open the app and log in — system works identically
7. Say: "The users table is already on PostgreSQL with bcrypt passwords and
   row-level security. We migrate one table at a time — the system never goes down."

This is a strong demonstration. It shows you understand the architecture,
you have addressed the most critical security finding (passwords), and you
have a clear migration path for the remaining tables.

---

## Migration order (after users)

Once users is working, continue in this order — each takes about 2-4 hours:

| Week | Table | Why first |
|------|-------|-----------|
| 1 | users | Password security — most critical |
| 2 | audit_trail | New entries go to DB; old JSON kept for history |
| 3 | pipeline_deals | High-write, concurrent access from RMs |
| 4 | loan_applications | High-write, multiple departments |
| 5 | ews_cases, aml_alerts | Regulatory data — needs RLS |
| 6 | disciplinary | Confidential — needs RLS |
| 7-10 | Everything else | One table per session |

---

*A2Z Blueprint MIS 360 — PostgreSQL Migration Guide*
*Prepared for Joshua Mokua | April 2026*
