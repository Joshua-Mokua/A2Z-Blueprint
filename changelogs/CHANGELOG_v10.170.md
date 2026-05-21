# CHANGELOG v10.170 — ENH-222 Obligation & Renewal Tracking (Legal Arc)

**Phase 4 begins.** First greenfield engine of the Legal arc (ENH-222..230, 9 standards). Mirrors AML cluster pattern.

**Audit:** `Score: 153/153 gates = 100.0% — PASS` (unchanged). G142 floor 86→87. Active 188→189. v10.170 tests 28/28 pass.

## Engine surface
- `utils/obligation_tracking.py` ~340 LOC. 4 enums (ObligationStatus 4, ObligationKind 6, AlertLevel 6, TransitionOutcome 4), 1 frozen Obligation dataclass.
- T-90/60/30/7 alert thresholds: NOTICE/PLANNING/ACTION/CRITICAL/BREACHED computed per obligation
- ACTIVE→COMPLETED/BREACHED/CANCELLED lifecycle
- COMPLETED requires `discharge_evidence`; BREACHED + CANCELLED require `reason`

## Honest deferrals
- `automated_alerting_status` DEFERRED — engine computes alert_level; notification dispatch (email/SMS/Slack) operator-side
- `contract_text_integration_status` META_ONLY — engine references contract_id; full ENH-221 contract_review integration future work

## Tier 31 — Legal Suite — added to ENGINE_HUB_TIERS as the new arc tier (matches AML's Tier 30 pattern).

## Legal arc progression: 1 of 9 active
| | | |
|---|---|---|
| ENH-221 AI-Powered Contract Review | active | (pre-existing) |
| **ENH-222 Obligation & Renewal Tracking** | **active** | **v10.170** |
| ENH-223 Legal Case Management | planned | v10.171 next |
| ENH-224 Outside Counsel Portal | planned | |
| ENH-225 Legal Spend Management | planned | |
| ENH-226 Clause Library & Playbooks | planned | |
| ENH-227 Legal Hold Management | planned | |
| ENH-228 Legal Dashboard | planned | |
| ENH-229 Legal Document Management | planned | |
| ENH-230 Legal Analytics & Reporting | planned | |

After ENH-222..230 all active: v10.180 module closure with G154+G155 audit gates.
