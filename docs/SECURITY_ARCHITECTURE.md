# A2Z MIS 360 — Security Architecture

This document is the security reference for A2Z MIS 360. It documents
the threat model, the controls in place against each threat, the
audit gates that enforce those controls, and the residual risks.

Read this with the [Deployment Guide](DEPLOYMENT_GUIDE.md) (for
network-level controls) and [DR Runbook](DR_RUNBOOK.md) (for incident
response).

## Threat model

A2Z handles bank performance data: BSC scorecards, customer information
(via FLEXCUBE), pipeline deals, AML cases, disciplinary records.
The threat model is shaped by what each user role can see and what
external attackers might try.

### Asset inventory

| Asset | Sensitivity | Where it lives |
|---|---|---|
| User credentials | Critical | `users` table (PG) |
| JWT secret | Critical | env var `A2Z_JWT_SECRET` |
| BSC scorecards | High | `bsc_scores` table |
| Customer PII | High | `customers` table (sourced from FLEXCUBE) |
| Audit trail | High | `audit.audit_logs` (immutable, archived monthly) |
| Pipeline deals | Medium | `pipeline_deals` table |
| AML alerts | High | `aml_alerts` table |
| Disciplinary records | Critical | `disciplinary` table (HR-restricted) |

### Threat actors

1. **Unauthenticated external attacker** — internet-facing API surface
2. **Authenticated low-privilege staff** — privilege escalation,
   exfiltration
3. **Compromised credentials** — stolen via phishing or password reuse
4. **Insider threat — disgruntled employee** — data exfiltration,
   audit tampering
5. **Insider threat — accidental** — destructive UI action, leaked
   export
6. **Supply chain** — malicious dependency, vendor compromise
7. **Infrastructure** — host compromise, PG exposure

### Vulnerabilities tracked

These are the named vulnerabilities the codebase defends against. Each
has an audit gate that enforces the mitigation.

| ID | Name | Mitigation | Gate |
|---|---|---|---|
| **V-001** | API endpoints accept unauthenticated requests | Every route except `/api/health` declares `Depends(get_current_user)` | **G12** |
| **V-002** | SQL injection via concatenated identifiers | `_check_table` whitelist + `_qid` Identifier wrapping; no `f"SELECT ... FROM {table}"` | **G9** |
| **V-003** | XSS via `unsafe_allow_html` interpolating user data | Pages may use `unsafe_allow_html` but never with raw user-controlled strings | **G10** |
| **V-004** | Plain-text password storage | bcrypt via `_hash_password`; no plain `hashlib.sha256` etc. | **G11** |

## Authentication

### JWT-based

A2Z uses HS256-signed JWTs (HMAC-SHA-256, symmetric). Issuance:

```python
# utils/auth_jwt.py
def issue_token(username: str) -> str:
    payload = {
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_TTL_SECONDS,  # 8 hours
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")
```

Verification on every protected request:

```python
def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload["sub"]
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token")
```

### Why HS256, not RS256?

- A2Z is a single-tenant deployment; there's no need for asymmetric
  keys (no third-party identity provider verifying signatures
  independently)
- HMAC has lower verification overhead at the API tier
- Rotating the secret invalidates all sessions — useful for incident
  response

If A2Z ever federates with corporate SSO (Azure AD / Okta), the
signing strategy changes to RS256 with the IdP's public key — see the
[Roadmap](#roadmap) section.

### Password storage

Passwords are bcrypt-hashed via `utils/core._hash_password`:

```python
def _hash_password(plain: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")
```

Every site that stores or verifies a password goes through these
helpers. **Audit gate G11** scans for any direct `hashlib.*` /
`md5` / `sha1` use on password material and fails if any is found.

Password policy (configurable):
- Minimum length: 12 characters
- Must include mixed case, digit, symbol
- 90-day expiry
- Last-5 history (no reuse)
- Account lockout after 5 failed attempts within 15 minutes

### Session lifetime

JWTs expire 8 hours after issuance. There is no refresh endpoint —
clients must re-authenticate. This trades some UX friction for the
ability to invalidate everyone simultaneously by rotating the secret
(see [DR Runbook](DR_RUNBOOK.md) scenario 7).

## Authorization (RBAC)

Roles are defined in `utils/core` and enforced at two layers:

1. **API routes** — `Depends(get_current_user)` returns the username,
   then the route logic checks the user's role
2. **Page-level** — every Streamlit page has a `_require_role(...)` guard
   at the top

### Standard roles

| Role | Scope |
|---|---|
| **Staff** | Own scorecard, own pipeline, own AML alerts |
| **Manager** | All Staff + team views, approvals, target cascading |
| **Branch Manager** | All Manager + branch-wide views, user creation |
| **Regional Head** | All Branch Manager + multi-branch reports |
| **Director** | All Regional Head + bank-wide reports + score overrides |
| **Admin** | All Director + user management + module config |
| **CEO/MD** | Read-only across the bank, including HR-restricted views |

Role assignment is in the `users` table. Changing a role triggers a
JWT invalidation for that user (they re-login to get the new role's
permissions).

## Data protection

### In transit

- All client traffic terminates TLS at the reverse proxy
  (recommended: nginx with Let's Encrypt or your bank's CA)
- API → DB traffic uses TLS if PG is configured with SSL (recommended
  for cross-host deployments)
- API → FLEXCUBE traffic uses TLS for HTTPS endpoints; SFTP for file
  drops uses SSH host key verification

### At rest

- PG data files reside on encrypted disks (LUKS or cloud-provider
  equivalent — operator's responsibility, documented in
  [Deployment Guide](DEPLOYMENT_GUIDE.md))
- Backup files (`pg_dump -Fc`) are encrypted before upload to S3
- Audit archive in S3 uses server-side encryption (Glacier with
  default KMS key)

### Sensitive field handling

Some fields require extra care:

| Field | Class | Display | Export |
|---|---|---|---|
| `users.password_hash` | Secret | Never displayed | Never exported |
| `customers.id_number` | PII | Masked except for back-4 | Masked in CSV exports |
| `customers.phone` | PII | Visible to RM, masked otherwise | Masked in CSV |
| `disciplinary.detail` | HR-restricted | Visible only to HR + line manager | Not exported |

The masking is implemented in the read path (`utils/db.py`'s row
post-processing for views with sensitive columns).

## Audit trail

### What's logged

Every state-changing action writes to `audit.audit_logs`:

```
{
  "id": uuid,
  "actor": "jane002",
  "actor_role": "Branch Manager",
  "entity": "pipeline_deals",
  "entity_id": "d-12345",
  "action": "update",
  "before": { ... },     -- old row
  "after":  { ... },     -- new row
  "diff":   ["stage", "value"],   -- changed keys
  "request_id": "uuid",
  "ip_address": "10.x.x.x",
  "user_agent": "...",
  "created_at": "2026-04-29T08:13:02Z"
}
```

**Audit gate G3** verifies that every page that writes data also calls
`audit_log()`. Pages that mutate without auditing fail the gate.

### What's NOT logged

- Read actions (too high volume; logged at the API access layer for
  security forensics)
- Cache hits/misses
- The actual JWT (logged as `request_id` only — JWT is never in audit
  trail, otherwise compromised audit = compromised tokens)

### Retention

- Online (PG): 90 days
- Cold (S3 Glacier, immutable): 13 months
- Total retention: configurable via `A2Z_AUDIT_RETENTION_DAYS`,
  default 730 days (2 years)

The bank's regulator may specify minimums; configure accordingly.

### Querying

Use **Admin → Audit → Search** in the UI. For complex queries, SQL:

```sql
-- Who modified user X's role in the last week?
SELECT actor, before->'role' AS old, after->'role' AS new, created_at
  FROM audit.audit_logs
 WHERE entity = 'users' AND entity_id = '<user-uuid>'
   AND 'role' = ANY(diff)
   AND created_at > now() - interval '7 days';
```

## Defenses against named vulnerabilities

### V-001: Unauthenticated API access

**Threat:** Attackers hit `/api/dashboard/md` without a token and read
sensitive bank data.

**Mitigation:** FastAPI dependency injection. Every route declares
`Depends(get_current_user)`. The exempt endpoints are:
- `/api/health` — needed for load balancer probes
- `/api/auth/login` — by definition unauthenticated

**Audit gate:** G12 scans `utils/api.py` and `utils/api_crud.py`. If
any route definition lacks the dependency declaration (and isn't
exempt), the gate fails.

**How to test:**
```bash
# Should return 401 without token
curl -i http://localhost:8502/api/dashboard/md
# Expected: HTTP/1.1 401 Unauthorized

# Should work with token
TOKEN=...
curl -i -H "Authorization: Bearer $TOKEN" http://localhost:8502/api/dashboard/md
# Expected: HTTP/1.1 200 OK
```

### V-002: SQL injection via identifiers

**Threat:** A request specifies `?table=users; DROP TABLE users` and
the API concatenates the value into a query.

**Mitigation:**
1. **Whitelist:** `_check_table` rejects table names not in
   `TABLE_REGISTRY`. Even if a malicious value reaches the helper,
   `KeyError` is raised before any SQL runs.
2. **Identifier wrapping:** `_qid` returns a `psycopg2.sql.Identifier`
   object. SQL is built with the `sql.SQL` composer; identifiers can
   never be substituted as raw strings.
3. **Parameterised values:** All value substitutions use `%s`
   placeholders + a separate args tuple. Never `f"WHERE x = {value}"`.

**Audit gate:** G9 greps for unsafe SQL patterns:
- `f"SELECT ... FROM {<expr>}"`
- `'... ' + table_name + ' ...'`
- `'%(table)s' % vars`
Any hit is a violation.

### V-003: XSS via `unsafe_allow_html`

**Threat:** A page renders user-controlled text inside `st.markdown(...,
unsafe_allow_html=True)`. The text contains a `<script>` tag.

**Mitigation:**
- Pages that use `unsafe_allow_html` only do so for **bank-controlled**
  content (e.g. styled badges, brand colors)
- User-controlled strings are NEVER passed through `unsafe_allow_html`
- HTML escaping is applied via `streamlit`'s default text handling
  for any user input rendered via `st.text()`, `st.dataframe()`, etc.

**Audit gate:** G10 scans for sites where `unsafe_allow_html=True` is
used together with f-string interpolation of variables that look like
user-data field names (`name`, `comment`, `narrative`, etc.).

### V-004: Weak password hashing

**Threat:** Database leak exposes the `users` table; passwords were
hashed with MD5 / SHA-1 / SHA-256; offline brute-force breaks them.

**Mitigation:** All password handling routes through bcrypt with
12 rounds (configurable, never below 10). The `_hash_password` helper
is the only sanctioned site for password hashing.

**Audit gate:** G11 scans for:
- `hashlib.md5`, `hashlib.sha1`, `hashlib.sha256` operating on a
  variable named like `password` / `pwd` / `pass*`
- bcrypt missing from `requirements.txt`
- direct `bcrypt.hashpw` calls outside `_hash_password`

## Network controls

These are operator's responsibility (covered in [Deployment Guide](DEPLOYMENT_GUIDE.md)):

- **TLS termination** at the reverse proxy
- **Rate limiting** at the reverse proxy / Cloudflare (no app-level
  rate limit today)
- **WAF rules** for common patterns (recommended: ModSecurity OWASP
  Core Rule Set)
- **Egress allow-list** — A2Z only needs outbound to FLEXCUBE +
  monitoring/log forwarders
- **No public PG** — PG only listens on the internal VPC; never on
  `0.0.0.0`

## Application controls

### Input validation

- All API request bodies parse through Pydantic models. Pydantic
  rejects type-incorrect input with 422
- All UI form inputs validate with regex / range / enum checks
- File uploads (CSV imports, document attachments) are size-capped
  and MIME-sniffed

### Output encoding

- API JSON output uses standard `json.dumps` (no custom encoder that
  could embed scripts)
- UI uses Streamlit's default which HTML-escapes everything except
  explicit `unsafe_allow_html` blocks (see V-003)
- CSV exports quote field values with double quotes, escape internal
  quotes by doubling

### Secret management

- Production secrets (DB password, JWT secret, FLEXCUBE creds) are
  injected via `EnvironmentFile=` to systemd, never checked into git
- `.gitignore` excludes `.env*` and `data/*.json` files containing
  user data
- The repo's `data/` is seed data only (synthetic / test fixtures);
  production-side `data/` lives outside git

## Roadmap

Items not yet implemented but on the security roadmap:

- **WCAG 2.1 AA accessibility** — Standard #8, gate G20 planned
- **2FA / TOTP** — currently planned but not built; relies on JWT TTL
  + IP allow-list as compensating controls
- **Federated SSO (Azure AD / Okta)** — RS256 JWTs, IdP-provided keys
- **Field-level encryption for PII** — currently relies on
  storage-level encryption; field-level (e.g. via pgcrypto) is a
  future upgrade
- **Anomaly detection** — flag unusual patterns (off-hours admin
  actions, high-volume exports) for review

### Delivered

- **SBOM + dependency scanning** (Standard #9, v5.37) — `pip-audit`
  + `safety` driven by `scripts/run_dependency_audit.py`. Fails CI on
  any unsuppressed CRITICAL CVE. Suppression list at
  `.cve-ignore.json` requires per-entry `id` + `reason` + optional
  `expires` date (expired suppressions auto-reactivate the CVE).
  Audit gate **G21** enforces the spec's "zero CRITICAL" target.
  Manual + weekly-scheduled CI workflow at
  `.github/workflows/depaudit.yml` — CVE databases update
  continuously, so even unchanged code can develop new vulnerabilities.

## Compliance mapping

| Requirement | A2Z control |
|---|---|
| **Access control** (BIS / CBK) | RBAC + JWT + audit log |
| **Audit trail integrity** | append-only, immutable archive after 90 days |
| **Data residency** (CBK) | All data in-country PG + S3 region |
| **Password complexity** (PCI 8.2.3) | 12-char, mixed, 90-day expiry |
| **Session timeout** (PCI 8.5.15) | 8-hour JWT TTL, no idle session |
| **Encryption in transit** (PCI 4.1) | TLS at proxy, TLS to PG (recommended) |
| **Vendor due diligence** (CBK) | `pip-audit` + `safety` weekly scans, audit gate G21 |

## Reporting a security issue

Internal: email `security@<bank>` or page on-call security.
External: `security-disclosure@<bank>`. Acknowledgement within 24h, fix
ETA within 5 business days for high-severity.

## Where to learn more

- [Deployment Guide](DEPLOYMENT_GUIDE.md) — network + infrastructure
- [DR Runbook](DR_RUNBOOK.md) — incident response procedures
- [Admin Guide](ADMIN_GUIDE.md) — operational tasks
- Source of truth: `utils/auth_jwt.py`, `utils/core._hash_password`,
  `utils/db._check_table` / `_qid`
