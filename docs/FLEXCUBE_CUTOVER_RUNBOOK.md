# FLEXCUBE Live-Mode Cutover Runbook
## A2Z MIS 360 — Production Integration with Ecobank Kenya

> **Status:** TEMPLATE  
> **Owner:** A2Z Integration Lead  
> **Approver:** Ecobank IT Director, A2Z CEO  
> **Last review:** _to be filled_  
> **CBK reference:** ICT Risk Management Guideline § 7 (Outsourcing & Integration)

---

## 1. Cutover Readiness Checklist

This is the canonical gate before flipping `FLEXCUBE adapter mode = live`. Every box must be checked, signed, and dated.

### 1.1 Documentation & Approvals
- [ ] **Data Processing Agreement (DPA)** signed (Ecobank as controller, A2Z as processor)
- [ ] **NDA** specifically covering FLEXCUBE schema and architecture
- [ ] **Sandbox access** request signed by Ecobank IT director
- [ ] **CBK notification** filed (ICT outsourcing notification)
- [ ] **Information Security Sign-off** from Ecobank CISO
- [ ] **Penetration test report** completed and remediated
- [ ] **Disaster Recovery plan** approved
- [ ] **Cutover RACI** distributed to all stakeholders

### 1.2 Environment & Credentials
- [ ] OAuth2 client_id provisioned in Ecobank Apigee
- [ ] OAuth2 client_secret stored in production secrets manager (NOT in `.env` file)
- [ ] `FLEXCUBE_API_BASE` URL whitelisted in A2Z firewall
- [ ] TLS certificate installed (mutual TLS if required)
- [ ] Production VPN or IPsec tunnel tested
- [ ] DNS resolution verified from production server
- [ ] Production server has static outbound IP (whitelisted by Ecobank)

### 1.3 Pre-flight Tests
- [ ] `python scripts/preflight_flexcube.py` returns exit code 0
- [ ] All FLEXCUBE service calls respond within SLA
- [ ] Reconciliation engine runs without breaks against SIT data
- [ ] PostgreSQL backup completed within last 4 hours
- [ ] Audit chain test record successfully written

### 1.4 Operations Readiness
- [ ] On-call rotation defined (24/7 for first 72 hours)
- [ ] Escalation matrix to Ecobank IT documented
- [ ] Rollback procedure tested in staging
- [ ] Communication plan (Slack/email) ready
- [ ] Post-cutover monitoring dashboard live

---

## 2. Cutover Timeline

### T-7 days
- Final UAT sign-off from Finance, Risk, Compliance
- Freeze KPI library and BSC Excel uploads
- Finalize CBK notification
- Stakeholder communication: cutover date, downtime window, contacts

### T-3 days
- Full backup of synthetic data state (`tar -czf a2z_pre_live_backup.tar.gz data/`)
- Verify backup restoration on dev box
- Deploy production code with `mode=mock` still active
- Run preflight script with `--skip-auth` to verify infrastructure

### T-1 day
- Dry-run cutover in pre-production environment
- Walk through rollback procedure with Ops team
- Confirm Ecobank IT support team availability

### T-0 (typically Sunday 8pm Nairobi)
1. **20:00** — Send "cutover starting" notification
2. **20:05** — Set adapter mode to `live` in `data/flexcube_config.json`
3. **20:10** — Run `scripts/preflight_flexcube.py` — must return 0
4. **20:15** — Trigger manual ETL: `python scripts/etl_flexcube.py --mode=full`
5. **20:30** — Run reconciliation: open Admin → 🔍 Reconciliation → Run all checks
6. **20:35** — Verify all 5 checks return MATCH
7. **20:40** — Send "cutover complete" notification

### T+1 to T+3 (Hypercare)
- 24/7 monitoring
- Daily reconciliation reports to CFO at 06:00
- Daily review meeting at 09:00 with Ecobank IT
- Any reconciliation BREAK escalates immediately

### T+7
- First weekly reconciliation report
- Post-mortem meeting

### T+30
- Hypercare officially ends
- Handover to BAU support
- Quarterly review schedule established

---

## 3. Rollback Procedure (15-minute target)

If at any point reconciliation breaks exceed tolerance OR uptime drops below 95% over a 4-hour window:

1. Open Admin → 🔌 FLEXCUBE Integration → Config tab
2. Change `mode` from `live` to `synthetic`
3. Save (audit-logged automatically)
4. Restore last good backup if data was corrupted: `tar -xzf a2z_pre_live_backup.tar.gz`
5. Restart Streamlit service
6. Send notification to all stakeholders: "Rollback executed, investigating"
7. Open root-cause investigation ticket

The system continues to function in synthetic mode — no end-user disruption. Reconciliation engine continues running so the restored state is verifiable.

---

## 4. Network & Security Reference

### Required Outbound Ports
| Port | Protocol | Destination | Purpose |
|------|----------|-------------|---------|
| 443  | HTTPS    | `api.ecobank.co.ke` | FLEXCUBE REST API |
| 443  | HTTPS    | `oauth.ecobank.co.ke` | OAuth2 token endpoint |
| 8883 | MQTT-TLS | `events.ecobank.co.ke` | JMS event broker (if used) |
| 5432 | TCP/TLS  | `pg.ecobank.local` | PostgreSQL (if shared) |

### TLS Requirements
- **Minimum:** TLS 1.2
- **Cipher suites:** ECDHE-RSA-AES256-GCM-SHA384 or stronger
- **Cert pinning:** Enabled for production
- **Mutual TLS:** Required (FLEXCUBE serves cert + A2Z presents client cert)

### Secret Management
**Never** commit secrets to git. Production options (in priority order):
1. AWS Secrets Manager (if hosted on AWS)
2. Azure Key Vault (if Azure)
3. HashiCorp Vault (on-prem Kenya)
4. systemd EnvironmentFile with mode 0600 (last resort)

---

## 5. Common Cutover Issues & Resolutions

| Symptom | Likely Cause | Resolution |
|---------|--------------|------------|
| `401 Unauthorized` from FLEXCUBE | Token expired or wrong secret | Verify `FLEXCUBE_CLIENT_SECRET`, re-run preflight |
| Slow response (>5s for `fetch_customer`) | Network or FLEXCUBE load | Engage Ecobank IT, check Apigee dashboard |
| Reconciliation BREAK on day 1 | Timezone difference (UTC vs EAT) | Ensure `metric_date` uses EAT consistently |
| `403 Forbidden` on specific accounts | RBAC mismatch | Confirm A2Z service account permissions in FLEXCUBE |
| JMS messages not received | Broker auth failure | Check `FLEXCUBE_JMS_BROKER` credentials |

---

## 6. Sign-Off

This runbook represents the operational handover from Integration to BAU.

| Role | Name | Date | Signature |
|------|------|------|-----------|
| A2Z Integration Lead | _____________ | _________ | _____________ |
| Ecobank IT Director  | _____________ | _________ | _____________ |
| Ecobank CISO         | _____________ | _________ | _____________ |
| Ecobank CFO          | _____________ | _________ | _____________ |
| A2Z CEO              | _____________ | _________ | _____________ |

---

## Appendix A — Pre-flight Script Output (sample)

```
============================================================================
  FLEXCUBE PRE-FLIGHT - A2Z MIS 360
============================================================================
  Time: 2026-04-26T20:05:00Z

============================================================================
  STAGE 1 / 5 - Environment variables
============================================================================
[PASS] env: FLEXCUBE_CLIENT_ID                  0ms  abc12345...
[PASS] env: FLEXCUBE_CLIENT_SECRET              0ms  ********
[PASS] env: FLEXCUBE_API_BASE                   0ms  https://...
[PASS] env: FLEXCUBE_OAUTH_URL                  0ms  https://...
[PASS] env: FLEXCUBE_JMS_BROKER                 0ms  set
[WARN] env: FLEXCUBE_PROXY_HOST                 0ms  not set (optional)
[PASS] env: FLEXCUBE_TLS_CERT_PATH              0ms  set

============================================================================
  STAGE 2 / 5 - OAuth
============================================================================
[PASS] OAuth token acquisition                240ms  URL parseable

(...continued for all 5 stages...)

============================================================================
  PRE-FLIGHT SUMMARY
============================================================================
  PASS: 12
  WARN: 1
  FAIL: 0
  SKIP: 0
  Total checks: 13

  CAUTION - proceed but address warnings first
```

---

## Appendix B — CBK Reporting

Within 30 days of going live, the following must be filed:

1. **CBK Form ICT-7** — IT outsourcing notification with technology summary
2. **DPC notification** to the Office of the Data Protection Commissioner
3. **Internal Audit charter update** to include the FLEXCUBE integration
4. **Incident reporting plan** filed with CBK Bank Supervision

---

*End of runbook. v1.0 generated for tender preparation.*
