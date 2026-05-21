# CHANGELOG v10.172 — ENH-224 Outside Counsel Portal

Third Legal arc engine. Greenfield.

**Audit:** `Score: 153/153 gates = 100.0% — PASS`. Active 190→191; G142 floor 88→89. Tests 24/24 pass.

## Engine
- `utils/outside_counsel_portal.py` ~530 LOC. 4 enums (CounselStatus 4, AssignmentStatus 5, BillingStatus 5, TransitionOutcome 5). 4 frozen dataclasses (Counsel, MatterAssignment, BillingLine, BillingSubmission).
- 3 lifecycles: Counsel (PENDING_VERIFICATION→ACTIVE→SUSPENDED→RETIRED), MatterAssignment (ASSIGNED→IN_PROGRESS→DELIVERED→ACCEPTED/REJECTED), BillingSubmission (SUBMITTED→UNDER_REVIEW→APPROVED/DISPUTED/REJECTED, with DISPUTED→APPROVED loopback)
- Cannot assign matter to non-ACTIVE counsel
- 23 UTBMS task codes supported (L100-L450 litigation phases + A101-A111 activity codes); engine validates submitted codes against the supported set
- Mixed-currency billing lines rejected
- DISPUTED + REJECTED billing transitions require review_notes; SUSPENDED counsel transition requires reason

## Honest deferrals — 3 surfaces
- PORTAL_UI_STATUS DEFERRED — engine ships API; portal UI operator-side
- AUTHENTICATION_STATUS DEFERRED — external counsel auth (vendor SSO, OAuth) operator-side
- AP_INTEGRATION_STATUS DEFERRED — engine tracks approval ledger; payment dispatch via FLEXCUBE Payments operator-side

## Legal arc: 3 of 9 active. v10.173 next: ENH-225 Legal Spend Management.
