# CHANGELOG v10.79 — trade_finance arc batches 9-10 (10/12)

**Status:** Dual batch. ENH-271 Corporate Trade Portal (data layer) + ENH-276 Multi-Bank Connectivity (diagnostic adapter surface). Both deterministic — neither benefits from ML, both follow the ENH-274 caller-supplied data discipline.

**Audit:** 136/136 PASS (unchanged — closure ratchets at v10.80)
**G117:** 99.0% (195/197) (unchanged)
**G128:** STABLE (347 modules · 882 imports · HARD=3) (+2 modules, +3 imports)
**Active standards:** 147/260 (was 145; +2 from this drop)
**Scenario library:** 162 (was 158; +4 from this drop — PRT-01..02 + CON-01..02)
**Engine self-tests:** 146/146 via orchestrator (was 144; +2 from this drop)

---

## Why these two together

ENH-271 and ENH-276 both sit at the network boundary of the trade finance platform — ENH-271 receives application + amendment + document + message submissions from corporate clients (the front-office boundary); ENH-276 receives messages from external trade networks (the inter-bank boundary). Both are validation + classification + routing engines. Neither does the actual processing — operations and downstream systems do that. They share the same architectural shape and the same Rule 7 discipline ("validate and surface; never auto-act"), so pairing them in v10.79 is the natural cadence.

Trade finance closes at v10.80 with the closure cockpit + remaining scope notes (ENH-279 mobile app — out-of-scope for the diagnostic-engine pattern; the cockpit page documents the deferral and references mobile-friendly client patterns instead).

## v10.79a — ENH-271 Corporate Trade Portal (data layer)

**Module:** `utils/trade_finance_corporate_portal.py` (~1100 lines, 27/27 tests pass)

The data-layer engine for the corporate self-service portal. The UI lives in the trade finance arc closure cockpit page at v10.80; this engine is what the cockpit calls into.

### Five capabilities

**1. `validate_lc_application`** — Corporate-submitted LC application validation. Returns `LCApplicationValidation` with `FieldFinding` objects (4-tier severity: CRITICAL / HIGH / MEDIUM / LOW) and 3-tier `ApplicationCompleteness` (COMPLETE / INCOMPLETE / INVALID).

Checks: required fields (applicant, beneficiary, amount, currency, expiry — CRITICAL when missing), currency format (3-letter ISO 4217 — HIGH when malformed), amount sanity (positive — CRITICAL; below caller-configurable upper bound default 10b KES — HIGH when exceeded as likely data-entry error or special-approval case), date ordering (latest_shipment ≤ expiry — HIGH; expiry > submission — HIGH so an LC isn't issued already-expired), description of goods present (UCP 600 §14(e) — MEDIUM), incoterms specified (LOW advisory).

Preliminary fee estimate: 0.5% of requested amount, returned as indicative information for the corporate's awareness — explicitly NOT a posted fee per Rule 7. The bank's actual fee schedule applies downstream when operations posts fees via ENH-275.

**2. `classify_amendment_request`** — 8-type amendment classification (EXPIRY_EXTENSION / AMOUNT_INCREASE / AMOUNT_DECREASE / BENEFICIARY_CHANGE / GOODS_DESCRIPTION_CHANGE / TERMS_CHANGE / WITHDRAW / UNKNOWN). Per Rule 1, ALL detected types surface (operator sees the full picture). The `primary_type` is mechanically derived as the most-impactful type present. 3-tier `AmendmentImpact` ladder (LOW / MEDIUM / HIGH) drives the `required_approvals` tuple — operations always required, plus credit_committee for HIGH impact, limit_review for AMOUNT_INCREASE, compliance_screening for BENEFICIARY_CHANGE, rm_approval for WITHDRAW.

The amount comparison takes an optional `existing_lc_amount_kes` so the engine can distinguish increase from decrease. When that's not supplied (the engine has no existing LC reference), classification falls back to "tentative AMOUNT_INCREASE pending operations confirmation" — a deliberately conservative posture so credit_committee gets pulled in by default.

**3. `track_instrument_status`** — Read-only snapshot from a `TradeInstrument` (ENH-269). Computes days_until_expiry and days_until_latest_shipment with simple subtraction. Surfaces `is_within_presentation_period` as `None` when the actual shipment date isn't in the instrument record — per Rule 1, surface the gap rather than fabricate a value. Builds a milestones tuple (issue date, expiry date, latest shipment date if known, current state, as-of date) for cockpit display.

**4. `validate_document_upload`** — Structural validation of upload metadata only — does NOT touch file contents (upstream extraction territory; that's the document checking engine's caller's responsibility). Allowed-extensions list (default: pdf/jpg/jpeg/png/tiff/tif), max size (default: 10MB), required document_type field, required-metadata-keys check (caller-supplied — e.g., uploader_id for audit). 4-tier `DocumentValidationOutcome` (ACCEPTED / REJECTED_TYPE / REJECTED_SIZE / REJECTED_METADATA) — the most-fundamental rejection wins (type before size before metadata).

**5. `classify_message_routing`** — Word-boundary regex match against caller-supplied keyword → `MessageRoutingDestination` map. 4-tier destination ladder (OPS_QUEUE / RM_QUEUE / ESCALATION_QUEUE / INFO_ONLY). Most-escalated destination wins on multi-match. 3-character keyword floor (rejected silently — same discipline as ENH-278) to prevent substring false positives. Default to OPS_QUEUE on no-match (triage default).

The keyword catalogue is operationally maintained per bank routing policy — same discipline as ENH-274 sanctions lists, ENH-278 taxonomies. The bank's RM team curates "credit"/"facility"/"limit" → RM_QUEUE; compliance curates "fraud"/"sanctions"/"AML" → ESCALATION_QUEUE; operations curates the OPS_QUEUE keywords. Engine bundles no defaults.

### Per Rule 7

Engine NEVER: issues LCs (operations + RM + Credit decide based on engine output); amends LCs (operations layer); stores documents (DMS territory); sends messages or notifications (messaging system territory); posts fees or accounting entries (ENH-275 territory); decides accept/reject on applications.

## v10.79b — ENH-276 Multi-Bank Connectivity (diagnostic adapter surface)

**Module:** `utils/trade_finance_connectivity.py` (~1050 lines, 21/21 tests pass)

Diagnostic adapter surface for inbound trade-finance network messages. The 6 supported networks reflect the major published trade-finance protocols 2025-2026: we.trade, Marco Polo, Contour, Bolero, SWIFT GPI, SWIFT FIN, plus an OTHER bucket. Engine validates structure, maps foreign protocol fields to internal schema, classifies routing actions, detects anomalies, builds reports. Engine NEVER sends, NEVER connects, NEVER processes payments, NEVER decides accept/reject on inbound messages.

### Five capabilities

**1. `validate_inbound_message_structure`** — Required-fields check per protocol. Defaults supplied for the 6 major networks based on publicly-documented field lists (e.g. we.trade requires message_id + message_type + sender_bin + receiver_bin + lc_reference + amount + currency + version; Marco Polo uses msg_type + originator + destination + trade_id + protocol_version; Contour uses from_node + to_node + lc_id; Bolero uses messageType + senderId + receiverId + documentId; SWIFT GPI requires UETR uniquely). Caller can REPLACE the defaults entirely via constructor — no merge semantics, because protocol updates require complete refresh discipline. 4-tier `MessageValidationStatus` (VALID / MISSING_REQUIRED_FIELDS / MALFORMED / UNKNOWN_PROTOCOL). Empty strings classify as MALFORMED rather than VALID — a present-but-empty field is not a valid field.

**2. `map_to_internal_schema`** — Caller-supplied `FieldMapping` sequence projects inbound fields onto internal canonical schema. Surfaces both `unmapped_inbound_fields` (fields in the message that the mapping doesn't account for — operator sees them, decides whether to extend mappings) and `missing_required_internal_fields` (caller-declared internal fields the mapping didn't populate — operator sees the gap, decides whether to reject downstream). Per Rule 1, both surface explicitly; engine never silently drops or fabricates. Skips empty inbound values rather than mapping them through.

**3. `classify_routing_action`** — Caller-supplied `message_type → RoutingAction` map. 7-value `RoutingAction` ladder (NEW_LC_ISSUANCE / AMENDMENT_NOTIFICATION / DRAWDOWN_NOTIFICATION / DOCUMENT_DISPATCH / STATUS_UPDATE / PAYMENT_INSTRUCTION / UNKNOWN). UNKNOWN surfaced rather than guessed when message_type field missing or unmapped — per Rule 7, no auto-classification beyond explicit caller intent.

**4. `detect_protocol_anomalies`** — Stream-level anomaly detection across a sequence of messages. Four anomaly types:
- DUPLICATE_MESSAGE_ID (HIGH severity) — same message_id appears multiple times in the batch
- OUT_OF_SEQUENCE (MEDIUM) — sequence_number decreases across received_at-ordered messages within a (network × sender) stream
- VERSION_MISMATCH (MEDIUM) — protocol_version not in caller-supplied supported_versions per network (when configured)
- UNKNOWN_SENDER (MEDIUM) — sender_id not in caller-supplied known_senders set (when configured)

The two configurable detectors (version + sender) silently disable when caller doesn't supply the lookup data — engine doesn't fabricate "expected" values.

**5. `build_connectivity_report`** — Portfolio rollup orchestrator. by_network_count, by_status_count, by_action_count, anomaly_count_by_type, top_5 error_types. Per Rule 7, report data only; cockpit renders; operator interprets.

### Per Rule 7

Engine NEVER: sends outbound messages or notifications; connects to external networks; processes payments or settles obligations; decides accept/reject on inbound messages (operator examines findings + decides per banking workflow); mutates messages or augments fields beyond explicit caller-supplied mappings (no implicit fabrication); retains message contents (audit-log responsibility lives elsewhere).

## 4 new scenarios

**PRT-01** clean LC application — applicant + beneficiary + amount + currency + expiry + shipment + description + incoterms all valid. Outcome COMPLETE, zero findings, fee estimate 10,000.00 KES (0.5% of 2m), ENH-271 cited per Rule 1.

**PRT-02** multi-type amendment — amount 2m→3m + expiry extension + beneficiary change. Detected types include all 3; primary AMOUNT_INCREASE; impact HIGH; required_approvals span compliance_screening + limit_review + credit_committee. Demonstrates Rule 1 (full picture) + Rule 7 (engine classifies; ops + Credit decide).

**CON-01** clean we.trade ISSUE_LC message — validates VALID (all 8 required fields), maps 3 internal fields with 0 missing, surfaces 5 unmapped inbound fields per Rule 1, routes to NEW_LC_ISSUANCE.

**CON-02** anomaly detection on 3-message stream — duplicate message_id (HIGH severity), version 3.5 not in supported (2.0, 2.1), sender ROGUE not in known_senders. All 3 anomaly types surfaced with appropriate severity per Rule 1.

## Tier 28 expansion

Tier 28 label updated to `(v10.70-v10.79, in flight, closes vTBD)`. Two new entries appended:
- `trade_finance_corporate_portal` / `TradeFinanceCorporatePortalEngine` — full description with 5-capability summary, Rule 7 boundaries, ENH-274 caller-supplied data discipline reference
- `trade_finance_connectivity` / `TradeFinanceConnectivityEngine` — full description with 5-capability summary, 6-network protocol coverage, anomaly detection types

Tier 28 now has **10 of 12 expected entries**. Closure batch v10.80 adds the remaining 2 (ENH-279 mobile app scope-resolution note + closure cockpit page itself).

## Files changed in this drop

- **NEW** `utils/trade_finance_corporate_portal.py` (~1100 lines, 27 tests)
- **NEW** `utils/trade_finance_connectivity.py` (~1050 lines, 21 tests)
- **MOD** `utils/standards_registry.py` (ENH-271 + ENH-276 activated, comprehensive descriptions)
- **MOD** `utils/scenario_simulator.py` (4 new scenarios + library wiring)
- **MOD** `pages/7_admin.py` (Tier 28 +2 entries, label v10.70-v10.79)
- **NEW** `CHANGELOG_v10.79.md` (this file)

## Trade finance arc state — one drop from closure

| Standard | Engine | Drop | Status |
|---|---|---|---|
| ENH-269 | trade_finance_instruments | v10.70 | active |
| ENH-273 | trade_finance_limits | v10.71 | active |
| ENH-272 | trade_finance_swift | v10.72 | active |
| ENH-274 | trade_finance_compliance | v10.73 | active |
| ENH-275 | trade_finance_accounting | v10.75 | active |
| ENH-280 | trade_finance_reporting | v10.76 | active |
| ENH-278 | trade_finance_sustainability | v10.77 | active |
| ENH-270 | trade_finance_document_checking | v10.78 | active |
| ENH-271 | trade_finance_corporate_portal | **v10.79** | **active** |
| ENH-276 | trade_finance_connectivity | **v10.79** | **active** |
| ENH-279 | (mobile app) | v10.80 | scope-resolution note in closure batch |
| (closure) | trade_finance_arc_cockpit | v10.80 | closure batch |

**10 of 12 active.** One drop to closure.

## What v10.80 closure looks like

Closure batches ship five things per the standing protocol:

1. **G-gate ratchet pair** — G137 + G138 establishing trade_finance arc as the 14th closed arc with audit-locked engine signatures
2. **Engine Hub Tier expansion** — Tier 28 fully populated with all 12 entries (11 engines + ENH-279 deferral note); label changes from "in flight" to "closed at v10.80"
3. **Master Prompt update** — trade_finance arc moves from "in flight" section to "closed arcs" section
4. **UI cockpit page** — `pages/97_trade_finance_arc_cockpit.py` providing the per-engine cockpit interface with cross-engine workflows (LC issuance → document examination → drawdown approval pipeline visualization)
5. **CHANGELOG_v10.80.md** — closure batch with arc retrospective

The mobile-app scope question (ENH-279) gets its resolution note in the closure batch. The diagnostic-engine pattern doesn't fit a mobile UI deliverable directly — the right framing is that the corporate portal data-layer engine (ENH-271) supports both web and mobile UI clients, and any mobile-specific scope is a UI delivery concern not an engine-architecture concern. The closure note documents this decisively rather than leaving it as a planned standard with no engine target.

After v10.80, the natural next thing is the post-closure ML governance arc (drift monitoring + model registry + adjudication feedback loop + scheduled retraining + A/B comparison + per-model model cards). Roughly 4-5 focused drops on its own cadence.
