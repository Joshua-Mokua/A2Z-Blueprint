# CHANGELOG v10.171 — ENH-223 Legal Case Management

Second engine of Legal arc. Greenfield.

**Audit:** `Score: 153/153 gates = 100.0% — PASS`. Active 189→190; G142 floor 87→88. Tests 26/26 pass.

## Engine
- `utils/legal_case_management.py` ~430 LOC. 3 enums (CaseStage 6, CaseOutcome 7, TransitionOutcome 4). 3 frozen dataclasses (CommunicationEntry, BillableEntry, LegalCase).
- 5-stage forward-only lifecycle: INTAKE → ANALYSIS → STRATEGY → EXECUTION → RESOLUTION (+ WITHDRAWN escape from any pre-RESOLUTION stage)
- RESOLUTION requires CaseOutcome (SETTLED/WON/LOST/PARTIALLY_WON/DISMISSED) + resolution_notes
- WITHDRAWN requires reason
- Tracks document_refs (idempotent linking), communications log, billable hours per timekeeper (internal_counsel/external_counsel)
- Materiality tiering LOW/MEDIUM/HIGH/CRITICAL; surfaces critical_open count

## Honest deferrals
- DOCUMENT_STORAGE META_ONLY — engine references doc IDs; storage operator-side via document_management.py
- BILLING_INTEGRATION DEFERRED — engine accumulates hours; invoice/AP-AR wiring operator-side

## Legal arc: 2 of 9 active. v10.172 next: ENH-224 Outside Counsel Portal.
