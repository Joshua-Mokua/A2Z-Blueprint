# CHANGELOG v10.568 — Batch B4: deal -> credit handoff fires on "Compliance"
#                       + login diagnostic

## 1. Submit-to-credit was a no-op (main fix)
The React deal detail offers "Compliance" as an advance target and shows
"✓ Stage advanced. Loan application created." But the backend
LMS_DEFERRED_STAGES had been changed to config stage names (Credit Review,
Approval, …) and DROPPED "Compliance". So advancing a loan deal to Compliance
showed the toast yet created NO loan application — there was no path from the
RM's deal into credit analysis.

Fix: utils/api_pipeline_mutations.py — add "Compliance" back to
LMS_DEFERRED_STAGES. handle_lms_handoff gates only on the stage transition (no
product guard), so advancing a loan deal to Compliance now creates the linked
loan application, and H6 surfaces the cross-link + toast.

Account-pipeline deals never reach "Compliance" (their stages are
Information Gathered / Documentation Complete), so no false handoffs.

Verified: Negotiation→Compliance is now a handoff; Qualified→Proposal and
Lead→Contacted are not; Proposal→Credit Review still is.

## 2. Login diagnostic (tool, no behaviour change)
scripts/check_login.py <username> — reports exists/active/password-format and
runs the real authenticate() path, with the stored hash REDACTED (format +
length only). Pinpoints why a login is declined (missing account vs plaintext
vs inactive) without exposing credentials.

## Test
tests/test_batchB4_compliance_handoff.py (run in the project venv).
