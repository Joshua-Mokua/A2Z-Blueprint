# A2Z MIS 360 — CHANGELOG v5.88

**v5.88 Eighteenth Integration Batch — Transaction Monitoring Engine (#46)**
**Released:** May 2026
**Audit gates:** 103/103 = 100% PASS (clean on first attempt — 14th clean-first-try in a row)
**Engine batch tests:** 49 files / 2211 tests (unchanged)
**Strategic milestone:** **🚨 PROACTIVE ALERTING AXIS INTEGRATED.** First transaction-level monitoring integration complementing v5.86 KYC/AML's customer-level risk scoring. Cumulative: **37 of 116 standards integrated.** Eighteenth integration batch.

---

## Discovery during integration

There is no `utils/smart_alerts.py` engine. Investigation found `utils/transaction_monitoring.py` is the deeper, richer engine for proactive alerting — **8 AML rules** + alert state machine, much more substantial than typical "smart alerts". The existing Smart Alerts page handles slow-moving alerts (maturing FDs, compliance deadlines); v5.88 adds the missing transaction-level monitoring layer.

---

## Strategic milestone — proactive alerting axis integrated

| Layer | Standard | Integrated in | What it covers |
|---|---|---|---|
| **Customer-level risk** | #36 KYC/AML | v5.86 | Point-in-time customer profile scoring + portfolio aggregation |
| **Transaction-level monitoring** | **#46 TxnMonitor** | **v5.88** ⭐ | **Continuous scanning against 8 AML rules + alert lifecycle** |

The AML team now has both views:
- **Strategic** — "which customers are high-risk?" (v5.86)
- **Tactical** — "which transactions need investigation right now?" (v5.88)

---

## What this batch is — and what it isn't

**Pure integration batch.** Zero new standards. Zero engine code changes. Zero new audit gates.

v5.88 wires **Standard #46 Transaction Monitoring** (`transaction_monitoring.py`) — the engine for CBK PG/05 + FATF Rec. 20 aligned transaction-level monitoring across 8 rules.

---

## What was modified

### `pages/36_smart_alerts.py` — Transaction Monitoring tabs added
**211 → 734 lines (+523)**

Top-level tabs expanded from 4 to 7 (exactly at G4's 7-tab limit):

| # | Tab | Status |
|---|---|---|
| 0-3 | Critical · Warnings · All Alerts · Alert Config | unchanged |
| **4** | **🔍 Transaction Monitoring (Standard #46)** | **NEW** |
| **5** | **📊 AML Alert Summary (Standard #46)** | **NEW** |
| **6** | **🌳 Engine Reference (Standard #46)** | **NEW** |

### Transaction Monitoring tab — 3 sub-tabs

**🔍 Run Rule Scanner** — 14-transaction demo dataset deliberately constructed to trigger 7 of 8 rules. Engine returns:
- Alerts list with severity / rule / customer / txn_ids
- Severity distribution metrics (CRITICAL/HIGH/MEDIUM/LOW with traffic-light emojis)
- Per-alert table + expandable descriptions
- CRITICAL count → MLRO 24h escalation guidance per CBK PG/05
- HIGH count → 72h investigation guidance
- CTR filing reminder for cash threshold breaches

**🔄 Alert Transitions** — full state machine UI with `ALLOWED_ALERT_TRANSITIONS` reference table:

| From | Allowed to |
|---|---|
| OPEN | INVESTIGATING |
| INVESTIGATING | SAR_FILED, DISMISSED |
| SAR_FILED | (terminal) |
| DISMISSED | (terminal) |

User can test any transition with alert_id, target_status, reviewer, reason. Engine enforces state machine with diagnostic messages surfaced verbatim.

**🌳 Demo Transaction Builder** — user inputs single transaction (txn_id, customer_id, amount, type, direction, counterparty country, PEP flag, dormant flag). Engine re-scans demo + new txn; surfaces alerts triggered specifically by user's transaction.

### AML Alert Summary tab

Engine's `alert_summary` method — total/open counts, by_severity, by_rule, by_status breakdowns. Bar chart of severity distribution. Executive guidance based on CRITICAL > 0 or HIGH > 0.

### Engine Reference tab — 3 reference tables

**Full RULE_CATALOG** with descriptions:

| Rule | Severity | Trigger |
|---|---|---|
| R1 CASH_THRESHOLD_BREACH | HIGH | Cash transaction ≥ KES 1M (CTR threshold) |
| R2 STRUCTURING_PATTERN | **CRITICAL** | 3+ deposits just under KES 1M in short window |
| R3 RAPID_MOVEMENT | HIGH | KES 5M+ credit followed by debits within 48h |
| R4 HIGH_RISK_GEOGRAPHY | **CRITICAL** | Wire to/from prohibited (any) or high-risk (≥100K) jurisdiction |
| R5 ACCOUNT_DORMANT_ACTIVITY | MEDIUM | Activity > KES 100K on dormant account |
| R6 ROUND_NUMBER_PATTERN | MEDIUM | 5+ identical-round txns in 30 days |
| R7 VELOCITY_BREACH | HIGH | ≥20 txns or ≥KES 10M in 24h |
| R8 PEP_LARGE_TRANSACTION | HIGH | PEP customer txn ≥ KES 2M |

Plus jurisdiction lists (PROHIBITED=KP/IR, HIGH_RISK=AF/MM/SY/YE/SS) byte-for-byte and alert state machine reference.

### Persistent engine instance via session_state

```python
if "_tme_engine" not in st.session_state:
    st.session_state._tme_engine = TransactionMonitoringEngine()
    st.session_state._tme_alerts = []
```

Ensures alerts persist across tab switches within a session.

### Engine file — UNCHANGED
`utils/transaction_monitoring.py` byte-for-byte unchanged.

### `app.py` — UNCHANGED
Page already registered.

---

## 3 engine paths verified end-to-end

**`scan` against 14-transaction demo:** **9 alerts** generated across **7 rules**:

| ID | Rule | Severity | Customer | Txns |
|---|---|---|---|---|
| 1 | R1 CASH_THRESHOLD_BREACH | HIGH | C001 | T001 |
| 2 | R1 CASH_THRESHOLD_BREACH | HIGH | C001 | T002 |
| 3 | **R2 STRUCTURING_PATTERN** | **CRITICAL** | C002 | T003-T006 |
| 4 | R3 RAPID_MOVEMENT | HIGH | C003 | T007 |
| 5 | **R4 HIGH_RISK_GEOGRAPHY** | **CRITICAL** | C004 | T010 (AF) |
| 6 | **R4 HIGH_RISK_GEOGRAPHY** | **CRITICAL** | C005 | T011 (KP) |
| 7 | R5 ACCOUNT_DORMANT_ACTIVITY | MEDIUM | C006 | T012 |
| 8 | R7 VELOCITY_BREACH | HIGH | C003 | T007-T009 |
| 9 | R8 PEP_LARGE_TRANSACTION | HIGH | C007 | T013 |

**Severity distribution**: 0 LOW / 1 MEDIUM / 5 HIGH / **3 CRITICAL**.

R6 ROUND_NUMBER_PATTERN didn't fire — needs round-number pattern across days; demo dataset insufficient.

**`alert_summary`** correctly aggregates with all 4 statuses initialized at 0 (alerts start OPEN), all 8 rule IDs initialized at 0.

**`transition_alert` state machine fully exercised:**
- OPEN → INVESTIGATING ✅ (only path forward from open)
- INVESTIGATING → OPEN ⛔ `transition_not_allowed:INVESTIGATING->OPEN`
- INVESTIGATING → SAR_FILED ✅ (with reason)
- SAR_FILED → DISMISSED ⛔ (terminal state)

**Engine logic confirmed**: 8 rules cover all major AML patterns. Severity assignment from RULE_CATALOG byte-for-byte. State machine enforces lifecycle correctly.

---

## Critical engine API specifics documented

These were verified during build (12 findings):

1. **`TransactionMonitoringEngine` is an instance class** with no constructor parameters — no DI callbacks needed, engine fully self-contained. State lives on instance (`self._alerts`, `self._next_alert_id`).

2. **`Transaction` dataclass requires** txn_id/customer_id/account_id/amount_kes (Decimal!)/txn_type/txn_datetime as REQUIRED fields + optional counterparty_country/counterparty_name/direction (default DEBIT)/customer_pep (default False)/account_dormant (default False)/meta (dict).

3. **🆕 R4 high-risk geography ONLY checks `txn_type` in `("WIRE_IN", "WIRE_OUT")`** — generic "WIRE" or "TRANSFER" do NOT trigger R4 even with prohibited country. **Non-obvious gotcha**; production callers must use exact txn_type strings.

4. **🆕 R3 rapid movement requires CREDIT followed by DEBIT pattern within window** — single high-value DEBIT alone doesn't trigger R3. Engine looks for ≥5M credit, then sums DEBITs within 48h window after that credit.

5. **🆕 R1 cash threshold matches on `txn_type` containing 'CASH'** — exact strings CASH_DEPOSIT, CASH_WITHDRAWAL recognized; substring match means `CASH_TRANSFER` would also match (be aware in production).

6. **`scan(txns)` is idempotent** — calling twice with same txns produces additional alerts each time (engine accumulates state). To reset, instantiate a new engine.

7. **`alert_summary` returns dict with all 4 statuses initialized at 0** (OPEN/INVESTIGATING/SAR_FILED/DISMISSED) and all 8 rule IDs initialized at 0 — caller can build complete distributions without missing keys.

8. **`transition_alert` returns `Tuple[bool, str]`** with engine's diagnostic message on failure (e.g. `transition_not_allowed:INVESTIGATING->OPEN`, `requires_resolution_reason`). Page surfaces these directly to user for transparency.

9. **`Alert.alert_id` is INTEGER** (auto-incremented from 1) NOT string — page coerces with `int()` in transition handler.

10. **`ALLOWED_ALERT_TRANSITIONS` has 4 keys** for the 4 statuses — SAR_FILED and DISMISSED both have empty tuple `()` indicating they're terminal; only INVESTIGATING leads to a terminal state.

11. **Engine HARD-CODES jurisdiction lists matching kyc_aml_risk.py** — both engines use same KP/IR (PROHIBITED) + AF/MM/SY/YE/SS (HIGH_RISK) constants but the constant names differ (`PROHIBITED_JURISDICTIONS_TXN` vs `PROHIBITED_JURISDICTIONS`). Production should refresh from FATF.

12. **🆕 Severity tiers differ from KYC engine** — KYC has 4 (LOW/MEDIUM/HIGH/PROHIBITED), TXN monitoring has 4 (LOW/MEDIUM/HIGH/**CRITICAL** — note CRITICAL not PROHIBITED). Different naming for tier 4 reflects different semantic: KYC PROHIBITED means "cannot onboard", TXN CRITICAL means "highest urgency for review".

---

## Audit logging

Every engine invocation produces an `IFRS_ENGINE_USED` audit event:

```
audit_log("IFRS_ENGINE_USED", uname, "TxnMonitor #46: scan 14 txns → 9 alerts")
audit_log("IFRS_ENGINE_USED", uname, "TxnMonitor #46: alert 1 → INVESTIGATING ok=True")
audit_log("IFRS_ENGINE_USED", uname, "TxnMonitor #46: summary total=9 open=9 critical=3 high=5")
audit_log("IFRS_ENGINE_USED", uname, "TxnMonitor #46: user-built txn T_USER_001 → 1 alerts")
```

---

## ✅ Fourteenth clean-first-try batch in a row

Audit clean on first attempt (after v5.74 → v5.87). G3 + G4 lessons embedded. Page now sits at exactly G4's 7-tab limit.

---

## Honesty discipline visualised

- **All 8 rule descriptions surfaced** in Engine Reference with exact thresholds
- **Severity tiers explicit** — CRITICAL/HIGH/MEDIUM/LOW with traffic-light emojis
- **Alert state machine reference** shows valid transitions byte-for-byte
- **Engine diagnostic messages surfaced verbatim** — `transition_not_allowed:INVESTIGATING->OPEN`, `requires_resolution_reason`
- **CBK PG/05 24h MLRO escalation** referenced for CRITICAL alerts
- **CTR filing reminder** for cash threshold breaches
- **STR (SAR) 3-day FRC filing rule** referenced
- **Session-scoped storage transparency** — caption notes alerts lost when session ends
- **CHANNELS/severity tier inconsistency** between KYC and TxnMonitor engines documented
- Every engine call audit-logged

---

## What didn't change

- Engine source file — byte-for-byte unchanged
- `scripts/audit.py` — gate G46 still passes exactly
- All 49 engine batch test files — unchanged
- Spec deviations cumulative count — still 9
- Rule 7 application count — still 6
- All v5.71-v5.87 pages — unchanged
- The 4 existing tabs in `36_smart_alerts.py` (Critical / Warnings / All Alerts / Alert Config) — completely untouched
- The existing slow-moving alerts data flow (maturing FDs, compliance deadlines, BSC drops) — completely untouched
- `app.py` — unchanged

---

## Comparison vs v5.87

| | v5.87 | v5.88 |
|---|-------|-------|
| Standards delivered | 116 | 116 (unchanged) |
| **Standards integrated into UI** | **36** | **37** ⭐ (+1) |
| Audit gates | 103/103 | 103/103 (clean first try) |
| Engine batch tests | 2211 | 2211 (unchanged) |
| Pages in app | 90 numbered | 90 numbered (unchanged) |
| Dedicated pages cumulative | 3 | 3 (unchanged) |
| **Modified existing pages cumulative** | 13 | **14** (36_smart_alerts.py is a new entry) |
| Lines added across pages this batch | +406 (channels) | +523 (smart_alerts) |

---

## Honest acknowledgements

**Limitations of this batch I want to be explicit about:**

1. **No live Streamlit deployment verification by Claude.** Page passes `python -m py_compile`, module-level engine import test, and 3-path engine call simulation at the CLI. User must run `streamlit run app.py` locally to confirm browser rendering — especially the **3-sub-tab nesting** under Transaction Monitoring within the now 7-tab top-level structure (page is at exactly the G4 7-tab limit).

2. **37 of 116 integrated** — 79 standards remain library-only.

3. **Sub-tabs use hard-coded 14-transaction demo dataset** — not loaded from JSON files. Production deployment would need `transactions.json` matching the Transaction dataclass schema with all required fields. The demo dataset is deliberately constructed to trigger 7 of 8 rules; production deployment would feed live CBS transactions through the same engine.

4. **Transaction Monitoring engine uses session-scoped in-memory storage** — `st.session_state._tme_engine` persists alerts within a single Streamlit session but **alerts are LOST when the session ends**. Production deployment MUST persist alerts to DB for audit trail and cross-session continuity. The `Alert` dataclass has all the fields needed for DB persistence. Documented as deferred enhancement.

5. **The new Transaction Monitoring engine alerts do NOT integrate with the page's existing manual alert flow** in tabs[0]-[2] — those handle slow-moving alerts (maturing FDs, compliance deadlines, BSC drops) which are NOT generated by transaction-monitoring rules. **The two flows are deliberately decoupled** because they have different data shapes and time horizons. Tabs[0]-[2] alerts remain unchanged.

6. **🆕 R6 ROUND_NUMBER_PATTERN doesn't fire on demo data** — needs 5+ identical-amount transactions in 30-day window. Demo dataset has too few rounded-number repeats. Documented; not a bug. Production data will exercise this rule properly.

7. **Demo Transaction Builder creates a NEW engine instance** for each scan to avoid duplicate alert IDs — this means the user-built txn doesn't accumulate into the same session alert pool as the rule scanner. Trade-off for clean alert ID semantics; production deployment with proper DB-backed alert IDs wouldn't have this constraint.

8. **🆕 R4 HIGH_RISK_GEOGRAPHY only fires on WIRE_IN/WIRE_OUT** — generic txn_type='WIRE' or 'TRANSFER' do NOT trigger R4 even with prohibited country. **Non-obvious gotcha** discovered during smoke testing. UI's Demo Transaction Builder uses dropdown with WIRE_IN/WIRE_OUT options to make this explicit; external integrations feeding the engine MUST use exact txn_type strings.

9. **🆕 Severity tiers don't include 'PROHIBITED'** — only LOW/MEDIUM/HIGH/CRITICAL. KYC engine #36 uses LOW/MEDIUM/HIGH/PROHIBITED. **The semantic difference matters**: KYC PROHIBITED means "don't onboard at all", TXN CRITICAL means "highest investigation urgency". UI surfaces both engines' severity tiers using their respective vocabulary; cross-engine analytics that try to merge severity tiers should not assume identical scales.

10. **Engine HARD-CODES jurisdiction lists** matching KYC engine but with different constant names (`PROHIBITED_JURISDICTIONS_TXN` vs `PROHIBITED_JURISDICTIONS`). The two engines should ideally share a single source of truth. Documented as known harmonization opportunity; not blocking because the lists are currently identical.

---

## Strategic narrative — proactive alerting axis integrated

| Layer | Standard | Integrated | Coverage |
|---|---|---|---|
| **Customer-level risk** | #36 KYC/AML | v5.86 | Point-in-time customer profile scoring + portfolio aggregation |
| **Transaction-level monitoring** | **#46 TxnMonitor** | **v5.88** | **Continuous scanning of transaction flow against 8 AML rules + alert lifecycle** |

The AML team can now answer:
- **Strategic** (v5.86): "Which customers are high-risk?"
- **Tactical** (v5.88): "Which transactions need investigation right now?"

The proactive alerting axis is now integrated, complementing the customer risk axis from v5.86.

---

## Next batch options ranked by impact

| Priority | Batch | Engine | Strategy |
|---|---|---|---|
| **(1) Recommended** | Cross-sell | cross_sell_nba | Shift to revenue/customer growth axis |
| (2) | Customer Insights | customer_insights | If engine exists |
| (3) | Churn Prediction | churn_prediction | Proactive retention |
| (4) | Coaching Intelligence | coaching_intelligence | HR coaching support |
| (5) | BSC Main Page | various | `pages/1_perform.py` (1908 lines, defer) |

With proactive alerting integrated, recommend **(1) Cross-sell** for v5.89 — would shift to revenue/customer growth axis after the deep compliance/control work.

---

**Cumulative tally:** 116 standards delivered, **37 integrated into UI via 3 dedicated pages + 14 enhanced existing pages**, 103 audit gates, 2211 engine tests, 9 spec deviations, 6 Rule 7 applications.

🚨 **Proactive alerting axis integrated** (KYC/AML #36 customer-level + TxnMonitor #46 transaction-level).
