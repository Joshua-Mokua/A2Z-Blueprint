# v10.465 Deep Module Review & Organ Assignment

**Date**: 2026-05-15
**Mission**: Align all 87 remaining unclaimed pages into the body. No orphan modules.
**Per Joshua mantra doc**: Complete the body — remaining organs are Operations, CRM, and Reporting & Analytics. Add business-chief command centres for CRBO + CCO sharing CRM modules.

---

## Confirmed business chiefs (from users.json)

| Chief | Name | Code | Span |
|---|---|---|---|
| CEO / MD | William Mwanake | 300001 | Top of pyramid |
| Chief Retail Banking Officer (CRBO) | Nicholas Ndegwa | 300002 | Retail customers |
| Chief Commercial Officer (CCO) | Emmanuel Kuria | 300003 | Commercial customers |
| Chief Operating Officer (COO) | Grace Makokha | 300008 | Operations |

---

## 3 NEW ORGANS — completing the body per mantra doc

### Organ 11: **Operations** (Muscular & Movement System)
**Chief**: COO Grace Makokha. **Role per mantra**: "Operations = Muscular & Movement System"

Operations is the COO's domain. The COO oversees several sub-departments:
- Branch Operations
- Centralized Processing
- Service Delivery / SLA Management
- Cards & Channels Operations
- Payments / Clearing / Settlement
- Procurement / Vendor Management
- Asset & Facilities Management
- Project Management Office

### Organ 12: **CRM & Customer Functions** (Sensory & Interaction Systems)
**Chiefs**: SHARED CRBO + CCO. **Role per mantra**: "CRM & Customer Functions = Sensory & Interaction Systems"

This is where Joshua's "business chiefs share modules" pattern applies. The CRM organ contains the shared sensory modules:
- Pipeline (lead creation — every staff)
- Customer 360
- Value Propositions
- Campaigns
- Cross-sell
- Contact Centre
- NPS / Voice of Customer
- Customer Behavioral Intelligence

**CRBO and CCO each get their own command centre** filtering this shared organ by their staff hierarchy. Pipeline specifically allows EVERY staff to create a lead and SUPPORT staff to assign them.

### Organ 13: **Reporting & Analytics** (Vital Signs Monitoring & Diagnostic Systems)
**Role per mantra**: "Reporting & Analytics = Vital Signs Monitoring & Diagnostic Systems"

This is the diagnostic organ:
- Reporting & Analytics (28_ra)
- Analytics Workbench (101_analytics_workbench)
- Analytics Advanced (102_analytics_advanced)
- Branch Ranking (113_branch_ranking)
- Tier-1 Benchmarking (87_benchmarking)
- Competitor Intelligence (11_competitor + 93_competitor_intelligence + 118_competitor_hub)

---

## Cross-cutting modules per Joshua's special attention

These modules serve **multiple organs** but have a primary home:

| Module | Primary organ | Secondary visibility | Joshua's note |
|---|---|---|---|
| **3_pipeline.py** | CRM | __all_departments__ | "enable every staff to be able to create a lead and if in support function be able to assign" |
| **31_edms.py** (Electronic Document Management) | Operations | Legal, Finance, HR, Credit | "cut across and are very crucial" |
| **18_cims.py + 105-109_cims_*** (Customer Instruction Management) | Operations | Compliance, Credit | "cut across" |
| **13_sla.py** (SLA tracker) | Operations | __all_departments__ | "very crucial in performance management per individual and unlocking 100% automation of all the BSC pillars" |
| **34_customer360.py** | CRM | Retail, Commercial, Credit | shared |
| **37_approvals.py** (Maker-Checker) | Operations | __all_departments__ | universal approval workflow |

---

## FULL ASSIGNMENT TABLE (87 pages)

### → OPERATIONS organ (COO domain) — 22 pages

| Page | LOC | Notes |
|---|---|---|
| 13_sla.py | 836 | SLA Tracker — shared visibility |
| 14_branch_log.py | 1266 | Daily Branch Log — branch ops |
| 18_cims.py | 1591 | CIMS — shared visibility |
| 30_rms.py | 215 | Reconciliation Management |
| 31_edms.py | 237 | EDMS — shared visibility |
| 37_approvals.py | 150 | Maker-Checker approvals |
| 44_incidents.py | 136 | IT Incident Management |
| 51_agency_banking.py | 103 | Agency Banking |
| 59_cab.py | 139 | Change Management (CAB) |
| 61_projects.py | 635 | Project Management Office |
| 62_p2p.py | 246 | Procure-to-Pay |
| 63_assets.py | 190 | Asset Management |
| 64_vendors.py | 598 | Vendor Management |
| 65_contracts.py | 143 | Contracts Register |
| 67_fraud.py | 261 | Agent Fraud Detection |
| 68_clearing.py | 292 | Clearing & Settlement |
| 99_swift_cockpit.py | 450 | SWIFT Operational Cockpit |
| 105_cims_capture.py | 742 | CIMS Batch 1 |
| 106_cims_process.py | 742 | CIMS Batch 2 |
| 107_cims_compliance.py | 30,759 bytes | CIMS Batch 3 |
| 108_cims_closure.py | 744 | CIMS Batch 4 |
| 109_cims_live.py | 47 | CIMS Live Cockpit |

### → CRM & Customer Functions organ — 13 pages (shared CRBO + CCO)

| Page | LOC | Notes |
|---|---|---|
| 3_pipeline.py | 2028 | **Pipeline** (every staff creates leads) |
| 5_products.py | 761 | Products catalog |
| 16_commission.py | 533 | DSO commission |
| 17_campaigns.py | 482 | Campaign Management |
| 27_propositions.py | 44 | Proposition overlay |
| 34_customer360.py | 3314 | **Customer 360** |
| 38_nps.py | 111 | NPS / Voice of Customer |
| 45_crosssell.py | 1091 | Cross-sell & Upsell |
| 47_digital_channels.py | 121 | Digital Channels (retail-leaning) |
| 48_contact_centre.py | 91 | Contact Centre |
| 49_bancassurance.py | 119 | Bancassurance (retail) |
| 66_partnerships.py | 616 | Partnerships (commercial-leaning) |
| 69_consent.py | 173 | Consent Management |
| 73_channels.py | 1271 | Channels Management |
| 78_onboarding.py | 196 | Customer Onboarding |
| 79_cards.py | 179 | Card Lifecycle (retail) |
| 80_merchant.py | 156 | Merchant Acquiring (commercial) |
| 91_customer_behavioral_intelligence.py | 516 | Behavioral intelligence |
| 92_propositions_workbench.py | 44 | Propositions Workbench |
| 94_campaigns_management.py | 446 | Campaigns Workbench |
| 104_tf_mobile.py | 309 | Trade Finance Mobile |
| 117_propositions_hub.py | 132 | Propositions Hub |

### → REPORTING & ANALYTICS organ — 9 pages

| Page | LOC | Notes |
|---|---|---|
| 11_competitor.py | 44 | Competitor Intelligence overview |
| 28_ra.py | 446 | Reporting & Analytics |
| 87_benchmarking.py | 418 | Tier-1 Benchmarking |
| 93_competitor_intelligence.py | 45 | Competitor Intelligence |
| 101_analytics_workbench.py | 494 | Analytics Workbench |
| 102_analytics_advanced.py | 549 | Analytics NLQ + Anomaly |
| 113_branch_ranking.py | 463 | Branch Ranking |
| 114_sbu_drilldown.py | 48 | SBU Drilldown |
| 118_competitor_hub.py | 126 | Competitor Hub |

### → EXTEND existing organs (re-home stranded pages)

**→ admin** (+8 strategy/MD pages):
- 0_home.py, 4_execute.py, 8_export.py, 9_sbu.py, 10_opex.py, 41_budget.py, 52_mgmt_accounts.py
- 82_system_vitals.py, 83_strategy.py, 95_command_centre.py, 100_md_cockpit.py, 115_live_cockpits.py, 120_staff_pbt.py

**→ finance** (+5 IFRS/finance pages):
- 32_ifrs9.py, 33_statement_analyzer.py, 88_ifrs_engines.py, 90_remaining_ifrs.py
- 29_revenue_assurance.py

**→ treasury** (+4 ALM/FTP):
- 53_irrbb.py, 56_ftp.py, 81_alm.py
- 77_capital.py (Basel - shared finance/treasury/risk)

**→ risk** (+3 stress/capital):
- 35_stress_testing.py, 54_rcsa.py, 36_smart_alerts.py

**→ compliance** (+4):
- 55_aml.py, 75_data_protection.py, 85_esg.py, 92_climate_esg.py

**→ credit** (+2):
- 19_credit_monitoring.py, 20_debt_recovery.py

**→ ict** (+1):
- 15_cbs.py, 57_deal_room.py

**→ bsc_cascade** (+2):
- 15_optimize.py (Branch Optimization for BSC)

---

## v10.465 work plan

1. **Add 3 new organs** to MODULE_REGISTRY: operations, crm, reporting_analytics
2. **Extend existing organs** with re-homed pages
3. **Add 3 new chiefs** to SUPER_USER_MAP: COO, CRBO, CCO
4. **Extend EVENT_TYPES** with 3 new organ event prefixes
5. **Update MODULE_STANDARD_DOMAINS** to include 3 new organs
6. **Generate doctrine docs** for 3 new organs (27 doc types × 3 = 81 new docs)
7. **Run honest baseline audit** — expect crisis state for new organs
8. **G351 audit gate** + tests + verifier + master + CHANGELOG + brief + patch

**Chief centres** for COO/CRBO/CCO/Reporting Chief deferred to v10.466 (5 chief centres to build).

---

## After v10.465 — body status

- **13 organs in body** (Admin + HR + BSC + Credit + ICT + Finance + Treasury + Legal + Risk + Compliance + **Operations + CRM + Reporting&Analytics**)
- Old: 10 organs at avg 84.6%
- Expected new state: 10 mature organs preserved + 3 new in crisis (~40-50%) = avg ~75% across 13 organs
- Zero orphan pages
- v10.466: build 4-5 new chief centres → restore avg to ~80%+

This is what Joshua means by "we have to get every module into the body, fit it perfectly resuscitate it and get the entire body out of a coma."
