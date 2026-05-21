# A2Z MIS 360 — CHANGELOG v5.86

**v5.86 Sixteenth Integration Batch — KYC/AML Risk (#36)**
**Released:** May 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt — 12th clean-first-try in a row)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **🛡️ COMPLIANCE AXIS COMPLETE.** v5.81 CBK Returns + v5.85 Internal Controls/Op Risk + v5.86 KYC/AML now together cover the full compliance product surface a tier-1 bank typically buys. Cumulative: **35 of 116 standards integrated.** Sixteenth integration batch.

---

## Strategic milestone — compliance axis complete

| Batch | Component | What it covers |
|---|---|---|
| v5.81 | CBK Returns (#80) | Regulatory reporting (BSD-1/2/3/17 prudential returns) |
| v5.85 | Internal Controls (#44) + Operational Risk (#43) | COSO control attestation + Basel ORM loss tracking |
| **v5.86** | **KYC/AML Risk (#36)** | **FATF-aligned customer risk scoring + portfolio aggregation** |

These three batches together cover what would typically be **3 separate compliance products** in a tier-1 bank:
- Regulatory reporting (CBK BSD returns submission)
- Internal control attestation (COSO/SOX 404)
- Customer risk management (KYC/AML/PEP/Sanctions)

The Compliance/AML team operating `pages/55_aml.py` can now use deterministic engine-generated KYC risk assessments alongside the existing manual alert flow — engine output is the input to STR filing decisions.

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.86 wires **Standard #36 KYC/AML Risk** (`kyc_aml_risk.py`) — the engine for FATF + CBK PG/05 aligned customer risk scoring across 5 components (geography, product, customer type, channel, behavior).

---

## What was modified

### `pages/55_aml.py` — KYC Risk Assessment + Portfolio Summary tabs added
**150 → 639 lines (+489)**

Top-level tabs expanded from 5 to 7 (exactly at G4's 7-tab limit):

| # | Tab | Status |
|---|---|---|
| 0-4 | High Risk · All Alerts · Analytics · New Alert · STR Log | unchanged |
| **5** | **🛡️ Customer KYC Risk (Standard #36)** | **NEW** |
| **6** | **📊 Portfolio Risk Summary (Standard #36)** | **NEW** |

### Customer KYC Risk tab — 5 sub-tabs

**🔍 Single Customer Assessment** — input customer profile with all 8 engine-recognized fields. Engine returns:
- Risk score 0-100
- Risk band: **LOW** (0-19) / **MEDIUM** (20-49) / **HIGH** (50-79) / **PROHIBITED** (≥80)
- CDD level: SIMPLIFIED / STANDARD / ENHANCED / ONBOARDING_REJECTED
- Component breakdown table with reasons surfaced byte-for-byte
- Auto-prohibition banner with reason if triggered
- PEP/sanctions warnings with FATF Rec. 12 + STR filing guidance

**🌍 Geography Reference** — full FATF jurisdiction list:

| Tier | Jurisdictions | Points |
|---|---|---|
| 🚫 PROHIBITED | KP, IR | 100 |
| 🔴 HIGH | AF, MM, SY, YE, SS | 30 |
| 🟡 MEDIUM | PK, TR, JO, MZ | 15 |
| 🟡 PENDING KYC | (missing) | 15 (Rule 6) |
| 🟢 LOW | (any other) | 0 |

**📦 Product Risk Reference** — sorted descending (engine takes MAX risk product, NOT sum):

| Product | Tier | Points |
|---|---|---|
| CASH_INTENSIVE / CORRESPONDENT_BANKING | 🔴 HIGH | 25 |
| PRIVATE_BANKING / BEARER_SHARE_ENTITY | 🔴 HIGH | 20 |
| TRADE_FINANCE / WEALTH_MANAGEMENT | 🟡 MEDIUM | 15 |
| ... | ... | ... |

**👤 Customer Type Reference** — PEP_FOREIGN/BEARER_SHARE_ENTITY=20, PEP_DOMESTIC/NGO_NPO=15, HIGH_NET_WORTH=10. Unrecognized types default to 10 pts.

**🌳 Engine Reference** — 4 reference tables: risk band thresholds, channel risk points, behavior thresholds (structuring + velocity), all bound byte-for-byte.

### Portfolio Risk Summary tab

8-customer demo dataset (RET_001/RET_002 retail, SME_001 with trade finance, NGO_001, HNW_001 PEP_DOMESTIC, PEP_F_001 PEP_FOREIGN PK + private banking, SANC_001 sanctions hit, PROH_001 IR jurisdiction).

Engine returns by_band distribution + pep_count + sanctions_count + auto_prohibited_count. Per-customer breakdown table with band/CDD/PEP/sanctions/auto-prohibited columns. Bar chart of band distribution. Executive guidance based on PROHIBITED% > 5% (review controls) or HIGH% > 20% (EDD resourcing).

### Engine file — UNCHANGED
`utils/kyc_aml_risk.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED
Page already registered.

---

## 2 engine paths verified end-to-end (8 customer profiles)

**`assess_customer` — 8 profiles spanning all bands and triggers:**

| Customer | Score | Band | CDD | Auto-prohibited |
|---|---|---|---|---|
| RET_001 (KE/KE/INDIVIDUAL/SAVINGS/branch) | 10 | **LOW** | SIMPLIFIED | False |
| SME_001 (KE/SME/TRADE_FINANCE+FX/branch) | 25 | **MEDIUM** | STANDARD | False |
| NGO_001 (KE/NGO_NPO/CURRENT/branch) | 20 | **MEDIUM** | STANDARD | False |
| HNW_001 (KE/PEP_DOMESTIC/private_banking) | 35 | **MEDIUM** | STANDARD | False |
| PEP_F_001 (PK/PEP_FOREIGN/private_banking/INTRODUCED) | 65 | **HIGH** | ENHANCED | False |
| **SANC_001 (sanctions_hit=True)** | 100 | **PROHIBITED** | REJECTED | **True** (sanctions_list_hit) |
| **PROH_001 (IR jurisdiction)** | 100 | **PROHIBITED** | REJECTED | **True** (prohibited_jurisdiction:IR) |
| BEH_001 (CASH_INTENSIVE + structuring + velocity) | 45 | **MEDIUM** | STANDARD | False (behavior=10 capped) |

**`portfolio_risk_summary` across 8 customers:**
- by_band: LOW=1, MEDIUM=4, HIGH=1, **PROHIBITED=2**
- pep_count=2, sanctions_count=1, auto_prohibited_count=2

**Engine logic confirmed**: 4-band distribution works correctly. Sanctions hit and prohibited jurisdiction both trigger auto-prohibition with score 100. PEP_FOREIGN with high-risk products + INTRODUCED channel correctly lands in HIGH band requiring Enhanced Due Diligence.

---

## Critical engine API specifics documented

These were verified during build (14 findings — strict schema warrants special attention):

1. **`KycAmlRiskEngine` has 2 STATIC class methods** — `assess_customer(customer: Dict)` returns `KycRiskAssessment` dataclass and `portfolio_risk_summary(assessments: List[KycRiskAssessment])` returns aggregate dict. No instance state, no DI callbacks, easy to wire.

2. **🆕 `assess_customer` customer dict expected keys** (STRICT):

| Key | Type | Purpose |
|---|---|---|
| `customer_id` | str (REQUIRED) | Customer identifier |
| `country_code` | ISO-2 str | Country of residence |
| `citizenship_code` | ISO-2 str | **Engine takes MAX of country + citizenship** |
| `customer_type` | str | See CUSTOMER_TYPE_PTS for recognized types |
| `products` | List[str] | Engine takes MAX risk product (not sum) |
| **`onboarding_channel`** | str | **NOT 'channel'!** |
| **`pep_flag`** | bool | **NOT 'is_pep'!** |
| **`sanctions_hit`** | bool | **NOT 'is_sanctioned'!** |
| `behavior` | Dict | Nested: `txn_count_30d`, `txn_amount_kes_30d`, `structured_deposits_count_30d` |

3. **🆕 Engine schema is strict** — using wrong key names silently scores 0 for that component. **e.g. passing `is_pep=True` instead of `pep_flag=True` results in pep_flag=False on the assessment**. Documented gotcha.

4. **🆕 MAX-of-geography logic** — KE customer without `citizenship_code` gets 15 pts (country_unknown_pending_kyc per Rule 6). **UI must encourage entering BOTH fields** for accurate scoring.

5. `_score_geography(None)` returns `(GEOGRAPHY_MEDIUM_PTS=15, 'country_unknown_pending_kyc')` — Rule 6 transparency: missing geography is NOT zero-risk.

6. **`_score_product` takes MAX of product points** (NOT sum) — customer with multiple high-risk products doesn't compound score.

7. Unknown products score 5 ('unknown_products_pending_review') if no recognized products. Product NOT in PRODUCT_PTS (like SAVINGS, CURRENT) scores 0 silently.

8. **`_score_customer_type` returns 10 for both None AND unrecognized strings** — both default to medium-risk pending KYC. Reasons differ ('customer_type_unknown_pending_kyc' vs 'customer_type_unrecognized') for transparency.

9. **`_score_behavior` is CAPPED at 10** — even if all 3 flags trigger (5+3+2=10) the cap still applies. Missing behavior dict scores 0.

10. **🆕 Auto-prohibition triggers** (in priority order):
    - sanctions_hit=True → score=100 IMMEDIATELY (early return)
    - country_code/citizenship_code in PROHIBITED_JURISDICTIONS → score=100 IMMEDIATELY (early return)
    - Otherwise composite score ≥80 → PROHIBITED band but **NOT** auto_prohibited (band-driven only, not flag-driven)

11. `KycRiskAssessment` dataclass exposes `to_dict()` method returning serializable dict suitable for JSON persistence.

12. **🆕 Engine has NO ongoing-monitoring API** — single-point-in-time assessor. Periodic re-assessment is the CALLER's responsibility (FATF Rec.: annually for HIGH, every 5y for LOW). Production must schedule via cron/trigger framework.

13. `portfolio_risk_summary` returns dict with all 4 bands explicitly even if zero customers in some — caller can build complete chart without missing keys.

14. **🆕 Engine HARD-CODES Basel/FATF jurisdiction lists** (KP/IR prohibited; AF/MM/SY/YE/SS high-risk; PK/TR/JO/MZ medium-risk) — AS OF engine authoring date. **Production must periodically refresh** from official FATF black/grey list publications.

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "KYC #36: PEP_F_001 score=65 band=HIGH cdd=ENHANCED_DUE_DILIGENCE auto_prohibited=False")
audit_log("IFRS_ENGINE_USED", uname, "KYC #36: SANC_001 score=100 band=PROHIBITED cdd=ONBOARDING_REJECTED auto_prohibited=True")
audit_log("IFRS_ENGINE_USED", uname, "KYC #36: portfolio summary total=8 PEP=2 sanctions=1 prohibited=2")
```

---

## ✅ Twelfth clean-first-try batch in a row

Audit clean on first attempt (after v5.74 → v5.85). G3 + G4 lessons embedded. Page now sits at exactly G4's 7-tab limit.

---

## Honesty discipline visualised

- **All bands and thresholds surfaced** byte-for-byte from engine constants
- **MAX-of-geography logic explained** in tooltip
- **Auto-prohibition reasons surfaced verbatim** (sanctions_list_hit, prohibited_jurisdiction:IR)
- **Component reasons displayed** (e.g. country_unknown_pending_kyc, customer_type_unrecognized) — Rule 6 transparency
- **Behavior cap at 10** documented in caption
- **PEP guidance with FATF Rec. 12** reference
- **STR filing 3-day rule** referenced for sanctions hits
- **Portfolio executive guidance** thresholds (PROHIBITED >5%, HIGH >20%)
- **Hard-coded jurisdiction list disclaimer** — must be refreshed from FATF
- Every engine call audit-logged

---

## What didn't change

- Engine source file — byte-for-byte unchanged
- `scripts/audit.py` — gate G36 still passes exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v5.85 pages — unchanged
- The 5 existing tabs in `55_aml.py` (High Risk / All Alerts / Analytics / New Alert / STR Log) — completely untouched
- The existing `aml_alerts.json` and `str_log.json` data stores — completely untouched
- `app.py` — unchanged

---

## Comparison vs v5.85

| | v5.85 | v5.86 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **34** | **35** ⭐ (+1) |
| Audit gates | 103/103 | 103/103 (clean first try) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| **Modified existing pages cumulative** | 12 | **13** (55_aml.py is a new entry) |
| Lines added across pages this batch | +704 (rcsa) | +489 (aml) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Page passes `python -m py_compile`, module-level engine import test, and 2-path engine call simulation across 8 customer profiles. User must run `streamlit run app.py` locally to confirm browser rendering — especially the 5-sub-tab nesting under Customer KYC Risk and the bar chart in Portfolio Risk Summary.

2. **35 of 116 integrated** — 81 standards remain library-only.

3. **Single Customer Assessment uses user-entered values** — does NOT auto-pull from CBS or customer master data. Production deployment would feed via `customers_register.json` or live CBS query through `assess_customer`. The page is a teaching/QA tool not a production batch processor.

4. **Portfolio Risk Summary uses hard-coded 8-customer demo dataset** — production deployment would feed via `customers_register.json`. Not blocking; engine works and Compliance team can validate engine outputs against demo data before connecting real CBS data.

5. **🆕 Engine HARD-CODES Basel/FATF jurisdiction lists** — PROHIBITED=KP/IR, HIGH_RISK=AF/MM/SY/YE/SS, MEDIUM_RISK=PK/TR/JO/MZ. **AS OF engine authoring date.** Production deployment should periodically refresh these constants from official FATF publications — specifically the FATF "black list" (currently KP, IR, MM as of recent updates) and "grey list" (varies). Engine code change required for updates.

6. **🆕 Customer dict schema is strict** — using wrong key names (e.g. `is_pep` instead of `pep_flag`) silently scores that component as 0 with NO error. The page provides correct fields but external integrations feeding this engine MUST use the exact documented keys. Documented gotcha.

7. **Engine has NO ongoing monitoring API** — single-point-in-time assessor. Periodic re-assessment (e.g. annually for HIGH-band, every 5y for LOW-band per FATF Rec.) is the CALLER's responsibility. Production deployment must schedule via cron/trigger framework. Documented deferred enhancement.

8. **PEP/sanctions list maintenance is OUT OF SCOPE for this engine** — engine takes the `pep_flag` and `sanctions_hit` booleans as inputs. Bank must maintain its own sanctions screening service (typically using LSEG World-Check, Refinitiv, or similar) that sets these flags before calling assess_customer. **Engine doesn't replace screening; it processes screening results.**

9. **Behavior data is OPTIONAL** — customers without 30-day behavior history score 0 for behavior component. For new customers this is correct; for established customers it represents a data gap that production deployment should fill from CBS transaction data.

10. **Engine assumes customer_id is unique** — no validation against duplicates. Production deployment must enforce uniqueness at the persistence layer.

11. **🆕 No support for legal entity beneficial owner (UBO) screening** — engine assesses the customer entity directly. For complex corporate structures, FATF requires looking through to UBOs. Production deployment would need to call assess_customer for the customer + each UBO and aggregate. Documented as future enhancement.

12. **Behavior cap of 10 pts** means even extreme combined behavior signals (structuring + high velocity count + high velocity amount) max out at 10 pts. For extremely suspicious activity, the bank's internal escalation should override the engine score (e.g. via the existing manual alert flow in tabs[3]). The two flows are deliberately decoupled.

---

## Strategic narrative — compliance axis complete

**The major functional surface coverage is now COMPLETE:**

| Axis | Status | Batches |
|---|---|---|
| Daily risk-management trifecta | ✅ Complete | v5.72, v5.76, v5.78 |
| HR temporal picture | ✅ Complete | v5.79, v5.84 |
| Branch axis | ✅ Complete | v5.80, v5.82 |
| Channels axis | ✅ Complete | v5.80, v5.83 |
| Regulatory framework arc | ✅ Complete | v5.72, v5.76, v5.78, v5.80, v5.81 |
| Governance/control axis | ✅ Complete | v5.85 |
| **Compliance axis** | **✅ NEW** | **v5.81 + v5.85 + v5.86** |

v5.87+ will fill in remaining gaps (channel income, smart alerts, customer insights, cross-sell) but the major strategic skeleton is in place across all 7 functional axes.

---

## Next batch options ranked by impact

| Priority | Batch | Engine | Strategy |
|---|---|---|---|
| **(1) Recommended** | Channel Income | channel_income | Third Channels enhancement (cost-to-serve) — completes Channels picture (cost + reliability + profitability) |
| (2) | Smart Alerts | smart_alerts | Enhance pages/36_smart_alerts.py |
| (3) | Customer Insights | customer_insights | If engine exists |
| (4) | Cross-sell | cross_sell | Enhance pages/45_crosssell.py |
| (5) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer) |

With compliance axis complete, recommend **(1) Channel Income** for v5.87 — completes a long-standing Channels theme. The DFS team running channels would have a complete picture: **cost (v5.80) + reliability (v5.83) + profitability (v5.87)**.

---

**Cumulative tally:** 116 standards delivered, **35 integrated into UI via 3 dedicated pages + 13 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.

🛡️ **Compliance axis COMPLETE** (CBK Returns + Internal Controls + Operational Risk + KYC/AML).
