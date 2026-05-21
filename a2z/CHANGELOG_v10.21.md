# CHANGELOG v10.21 — RMS Arc Batch 4: Realtime + Learning + Continuous + Cert + Sub-Monthly

**Audit:** 121/121 PASS — **104th consecutive clean. All 17 RMS standards now active.**

## What ships in v10.21

`utils/reconciliation_realtime.py` — 984 lines, **Cat A**. 5 of 17 RMS standards active (the largest single-batch standards count of the arc):

| Standard | Implemented as |
|---|---|
| **ENH-184** Real-time Reconciliation Dashboard | `DashboardKPI` with G/A/R thresholds + direction-aware status (`higher_is_better` flag); `DashboardSnapshot` with 4 KPIs (Auto-Match Rate, Open Exceptions, SLA Breaches, Critical Alerts); `build_dashboard_snapshot()` factory with sensible defaults; engine stores time-series of snapshots for trend display |
| **ENH-188** AI-Powered Reconciliation Learning | `FeedbackOutcome` enum (CONFIRMED_MATCH / REJECTED_NOT_A_MATCH / UNCERTAIN); `LearningFeedback` dataclass capturing reviewer + score + algorithm; `LearningStore` with feedback aggregation + `LearningStats` (confirmation/rejection rate); Rule 7 `train_callable` hookable for actual model fitting; honest no-fab signal when no trainer wired |
| **ENH-189** Continuous/Real-time Reconciliation | `StreamingWatermark` for high-watermark tracking per source; `LateArrivalRecord` capturing record_timestamp + received_at + lateness; `detect_late_arrival()` returns None for in-order, populated record for late; `is_acceptable_lag()` boundary check |
| **ENH-190** Reconciliation Audit & Certification | `CertifierRole` enum (6 roles: PREPARER/REVIEWER/APPROVER/CFO/INTERNAL_AUDIT/EXTERNAL_AUDIT); `CertificationStatus` enum (8 states with explicit `ALLOWED_CERT_TRANSITIONS` graph); `CertificationSignoff` + `AuditTrailEntry` immutable records; `CertificationRecord.is_dual_approved()` requires distinct PREPARER + REVIEWER users |
| **ENH-RMS-R7** Sub-Monthly Daily Reconciliation Support | `ReconCadence` enum (8 levels: REAL_TIME → MONTHLY → AD_HOC); `CADENCE_POLICY` per-account-type minimum (NOSTRO=DAILY per CBK CRMF §6.5, KEPSS=REAL_TIME); `is_cadence_compliant()` with cadence-order comparison; faster cadence always meets slower-cadence policy |

## Regulatory provenance

- **Kenya Banking Act §39** — books and records integrity
- **CBK Prudential Guideline CBK/PG/02** — operational risk framework
- **CBK CRMF April 2021 §6** — internal controls + reconciliation
- **CBK CRMF §6.5** — daily reconciliation cadence requirement
- **SOX §404** — internal control over financial reporting
- **SOX §302** — corporate responsibility for financial reports
- **PCAOB AS 2110** — risk assessment + walkthroughs
- **COSO ERM** — three lines of defense
- **Basel BCBS 239 §11** — completeness, timeliness, adaptability
- **Basel BCBS 239 §12** — accuracy and integrity
- **EU AI Act Art 10** — AI training data quality requirements
- **EU AI Act Art 12** — record-keeping for high-risk systems
- **Kenya Data Protection Act 2019 §28** — retention principles

## Key design decisions

### Cadence as ordered enum, comparison is order-aware
`ReconCadence` ordered REAL_TIME (0) → MINUTELY → HOURLY → INTRADAY → DAILY → WEEKLY → MONTHLY → AD_HOC (7). `is_cadence_compliant()` compares cadence indices: faster cadence (lower index) is always compliant if policy requires slower. So a real-time stream meets daily policy automatically. This avoids the trap of "DAILY > REAL_TIME" string-compare bugs.

### Per-account-type policy aligned to CBK CRMF §6.5
`CADENCE_POLICY` codifies CBK guidance:
- NOSTRO/VOSTRO: DAILY (per §6.4 + §6.5)
- INTERBANK_KEPSS: REAL_TIME (RTGS — instant settlement)
- PESALINK: REAL_TIME (retail real-time)
- MOBILE_MONEY: HOURLY (high volume but batch-feasible)
- GL_TO_CBS / INTERCOMPANY / SUSPENSE / REGULATORY: DAILY

Unknown account types default to DAILY (the most common minimum).

### Watermark-based streaming model
`StreamingWatermark` tracks the high-water timestamp processed per source. Records arriving after watermark are treated as late and explicitly logged. This is the standard streaming-data pattern (Apache Flink, Beam, Kafka Streams) for handling out-of-order events. The `is_acceptable_lag()` check distinguishes acceptable lag (e.g., network jitter under 1 hour) from genuine investigation triggers.

### Learning loop is honest about ML capability (Rule 7)
`LearningStore.trigger_training()` returns `(fired, message)`:
- No `train_callable` injected → `(False, "no train_callable injected — Rule 7 honesty: no model trained, feedback stored for later")`
- Trainer present → fires it; if it raises, returns `(False, "training failed: <exception>")`

This means deploying the engine without a trained ML model is fine — feedback collects in the store, ready for downstream training when the model wires up. **No fabricated "we trained on your data" claim** if no training actually happened.

### Certification has explicit transition graph + immutable audit trail
`ALLOWED_CERT_TRANSITIONS` enforces DRAFT → PREPARED → REVIEWED → APPROVED → SIGNED_OFF. Skipping (e.g., DRAFT → SIGNED_OFF) raises `ValueError`. Each transition appends both a `CertificationSignoff` (who certified what) and an `AuditTrailEntry` (immutable before/after state). The audit trail is cumulative — earlier entries cannot be modified, only appended.

### Dual approval requires distinct people, not just distinct roles
`is_dual_approved()` checks both:
1. Both PREPARER and REVIEWER roles are present, AND
2. At least 2 distinct user IDs

This prevents the same user from "self-approving" by switching role hats — a common SOX §404 control bypass. Real dual-approval requires segregation of duties between actual humans.

### Dashboard KPIs are direction-aware
`DashboardKPI.higher_is_better` flag inverts threshold semantics:
- Match rate (higher better): below amber → AMBER, below red → RED
- SLA breaches (lower better): above amber → AMBER, above red → RED

This avoids the trap where the same threshold logic is wrong for some metrics. Auditable: each KPI explicitly declares its direction.

### Compose, don't reimplement
v10.21 doesn't reimplement matching, workflow, or specialized recon. It produces:
- Snapshots from KPIs derived by v10.18 (match rates) + v10.19 (open exceptions, SLA breaches) + v10.20 (Nostro stale items, CBK overdue returns)
- Feedback records that v10.18's `match_pair()` will use when ML hookup happens
- Late-arrival records that v10.18 ingestion can backfill
- Certification records over closing periods of v10.18-v10.20 reconciliations

The integration is "v10.21 surfaces operational intelligence over what v10.18-v10.20 produces."

## Engine Hub integration

Tier 10 expanded from 3 to 4 engines. The `reconciliation_realtime` entry covers all 5 surfaces. **G117 coverage holds at ≥ 95%.**

## Tests

- 25 self-tests in `reconciliation_realtime.py`
- 23 integration tests in `tests/integration/test_v10_21_recon_realtime.py`

## Verified output

```
✓ reconciliation_realtime self-test passed (25 tests)
Ran 410 tests in 39.618s OK
Audit: 121/121 gates PASS
```

## Standards registry — RMS fully active

```
RMS (subcategory) — 17 of 17 active after v10.21:
  ENH-181:    Multi-Source Data Ingestion                   (v10.18)
  ENH-182:    Intelligent Matching Engine                   (v10.18)
  ENH-183:    Exception Management & Workflow               (v10.19)
  ENH-184:    Real-time Reconciliation Dashboard           (v10.21) ← NEW
  ENH-185:    CBK Regulatory Reconciliation                 (v10.20)
  ENH-186:    Nostro/Vostro Reconciliation                  (v10.20)
  ENH-187:    Intercompany & Internal Suspense Recon        (v10.20)
  ENH-188:    AI-Powered Reconciliation Learning           (v10.21) ← NEW
  ENH-189:    Continuous/Real-time Reconciliation          (v10.21) ← NEW
  ENH-190:    Reconciliation Audit & Certification         (v10.21) ← NEW
  ENH-RMS-R1: 90%+ AI-Matching Threshold Target             (v10.18)
  ENH-RMS-R2: Memory-Layer Architecture                     (v10.19)
  ENH-RMS-R3: Vendor Name Normalization Library             (v10.18)
  ENH-RMS-R4: Timing-Difference Auto-Handling               (v10.19)
  ENH-RMS-R5: Governed Execution Layer (TruePath-style)    (v10.19)
  ENH-RMS-R6: Real-time KEPSS / PesaLink Reconciliation     (v10.20)
  ENH-RMS-R7: Sub-Monthly Daily Reconciliation Support     (v10.21) ← NEW

RMS still planned: 0
```

## Honest acknowledgements

1. **No actual streaming infrastructure ships.** `StreamingWatermark` is the data structure for watermark tracking; real-time ingestion (Kafka, Flink, Pulsar) is per-deployment. The framework supports the watermark model; the wiring is downstream.

2. **No actual ML model ships.** `LearningStore` collects feedback; `train_callable` accepts the trainer. Real models (gradient boosting on confirmed-match features, transformer-based pair scoring, etc.) are per-deployment.

3. **Dashboard is data-only.** This batch produces `DashboardSnapshot` records; the actual UI rendering (Streamlit page, web component) belongs in `pages/30_rms.py` or a new dashboard page. The data model is stable; the rendering is per-presentation-layer.

4. **Late-arrival handling is detection-only.** The engine flags late arrivals; the backfill action (re-running matching on the affected period) is per-deployment workflow. Some banks may auto-backfill; others require manual review of late items.

5. **Certification is in-memory.** No external e-signature integration (DocuSign, Adobe Sign), no QES (qualified electronic signature). Real certification flows for SOX §302 / external audit may require these; the framework supports linking to external sign-offs via `notes` field.

6. **No formal proof of segregation of duties beyond user-id distinctness.** Real production should integrate with the bank's identity provider to verify that PREPARER + REVIEWER users have appropriate (mutually exclusive) entitlements, not just different IDs.

7. **Cadence policy is a seed catalog.** The 10 account types listed are common Kenya bank examples. Production deployments should add their specific account types + override the policy where their CBK supervisor's specific letters require differently.

8. **No persistence.** All engines are in-memory per instance.

## What v10.22 ships next — RMS arc closure

**G122 audit gate + RMS arc closure.** Per the established 6-batch arc closure pattern (Climate at v10.10, Credit at v10.16):

1. Add `gate_rms_engines_implemented()` to `scripts/audit.py` as G122
2. Verify all 17 RMS standards have `status='active'`
3. Verify all 4 RMS engines exist on disk + import cleanly:
   - `reconciliation_matching` (v10.18)
   - `reconciliation_workflow` (v10.19)
   - `reconciliation_specialized` (v10.20)
   - `reconciliation_realtime` (v10.21)
4. Verify integration test files exist for v10.18-v10.21
5. Drift-test G122 (rename engine → fail; demote standard → fail; restore → pass)
6. Closing CHANGELOG with the full 5-batch retrospective
7. Phase 2 batch 3 closure package

## Phase 2 progress

| Arc | Standards | Status |
|---|---|---|
| Batch 1 — Climate/ESG (v10.6–v10.10) | 13/13 | ✅ closed |
| Batch 2 — Credit (v10.11–v10.16) | 19/19 | ✅ closed |
| Enhancement — KESONIA (v10.17) | 1/1 | ✅ closed |
| **Batch 3 — RMS Reconciliation (v10.18–v10.22)** | **17/17** | **🟢 ready for v10.22 closure** |
| Batch 4 — Audit/GRC | 0/17 | pending |
